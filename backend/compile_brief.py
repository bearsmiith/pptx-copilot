"""WP8 — compile a Brief IR into a concrete renderable figure Slide.

Deterministic projection. genre=physical -> AssemblyFigure (parts positioned on a
substrate with resolved level/x/width and a mounting interface each). Position
resolution lives HERE so the LLM never emits coordinates. Revisions recompile.
"""
from __future__ import annotations

from brief_model import Brief, Part
from models import (Slide, AssemblyFigure, AssemblyPart, AssemblyBeam,
                    PhotonicFigure, PhotonicNode, PhotonicLink)
import parts as _parts               # WP8 P3: part knowledge single source

# function -> photonic-graph role (planar emphasis)
_FUNC_ROLE = {
    "laser_gain": "laser", "laser": "laser", "photodiode": "photodiode",
    "modulator": "modulator", "driver_ic": "driver", "driver": "driver",
    "tia": "tia", "eic": "eic", "fiber": "fiber", "lens": "generic",
    "logic_die": "chip", "hbm": "chip", "mlcc": "passive", "passive": "passive",
}

_MOUNT_MAP = {
    "none": "none", "stack": "stack", "die_attach": "die_attach", "solder": "solder",
    "c4": "c4", "cu_pillar": "cu_pillar", "flipchip": "flipchip",
    "wirebond": "wirebond", "hybrid_bond": "hybrid", "edge_couple": "edge_couple",
    "monolithic": "none", "epoxy": "die_attach", "eutectic": "die_attach",
}


def _is_base(p: Part) -> bool:
    return _parts.is_base(p.function) or bool((p.attributes or {}).get("is_base"))


def _mat(func: str) -> str:
    return _parts.material(func)


def compile_brief(brief: Brief) -> Slide:
    if brief.genre == "infographic":
        return _compile_infographic(brief)
    if brief.emphasis == "planar":               # same scene, network rendering
        s = _compile_planar(brief)
        if s is not None:
            return s
    return _compile_physical(brief)


def _compile_planar(brief: Brief):
    """emphasis=planar: render the same parts+relations as a photonic network
    (nodes/links) instead of a vertical cross-section. Returns None to fall back."""
    nodes, base_mat = [], "silicon"
    for p in brief.parts:
        if _parts.is_base(p.function):
            base_mat = _parts.material(p.function)
            continue
        if _parts.feature(p.function) or (p.attributes or {}).get("buried"):
            continue                             # waveguide/mold/balls are not nodes
        nodes.append(PhotonicNode(id=p.id, role=_FUNC_ROLE.get(p.function, "chip"),
                                  label=p.name))
    if len(nodes) < 2:
        return None
    ids = {n.id for n in nodes}
    links = [PhotonicLink(src=r.src, dst=r.dst,
                          kind=("electrical" if r.type == "electrical" else "optical"))
             for r in brief.relations if r.src in ids and r.dst in ids]
    fig = PhotonicFigure(caption=brief.caption, substrate=base_mat,
                         substrate_label=next((p.name for p in brief.parts
                                               if _parts.is_base(p.function)), "Substrate"),
                         nodes=nodes, links=links)
    return Slide(layout_type="figure", title=brief.title, figure=fig)


def _compile_physical(brief: Brief) -> Slide:
    parts = list(brief.parts)
    # pick base
    base = next((p for p in parts if brief.base and p.id == brief.base), None)
    if base is None:
        base = next((p for p in parts if _is_base(p)), None)
    base_label = base.name if base else "Substrate"
    base_mat = _mat(base.function) if base else "substrate"

    others = [p for p in parts if p is not base]
    # mold/EMC and package (BGA) balls are figure-level features, not mounted boxes
    mold_part = next((p for p in others if _parts.feature(p.function) == "mold"), None)
    ball_part = next((p for p in others
                      if _parts.feature(p.function) == "bottom_balls"), None)
    others = [p for p in others if p is not mold_part and p is not ball_part]
    buried = [p for p in others if (p.attributes or {}).get("buried")
              or (p.function == "waveguide" and (base and base.function == "pic"))]
    buried_ids = {p.id for p in buried}
    mounts = [p for p in others if p.id not in buried_ids]

    # TRUE stacking depth via the `on` chain (chip-on-chip-on-chip): follow to
    # the base so a 4-tier stack gets levels 1..4 (not all "2") — the height
    # budget depends on this.
    byid = {p.id: p for p in mounts}
    base_id = base.id if base else None

    def depth(pid, seen=()):
        p = byid.get(pid)
        if (not p or not p.on or p.on == base_id or p.on not in byid or pid in seen):
            return 1
        return 1 + depth(p.on, seen + (pid,))
    levels = {p.id: depth(p.id) for p in mounts}
    lvl1 = [p for p in mounts if levels[p.id] == 1]
    deeper = sorted([p for p in mounts if levels[p.id] >= 2],
                    key=lambda p: levels[p.id])

    # order lvl1 left→right by optical flow (emitter left, detector right)
    def flow_key(p):
        a = p.attributes or {}
        return (0 if a.get("emits") else 2 if a.get("detects") else 1)
    lvl1.sort(key=flow_key)

    n = max(1, len(lvl1))
    # fit widths across the base, then SPREAD parts edge-to-edge so the substrate
    # (and any optical path / waveguide) is visible between them
    raw = [_parts.width(p.function) for p in lvl1]
    budget = 0.92
    scale = min(1.0, budget / (sum(raw) + 0.05 * n)) if raw else 1.0
    widths = [w * scale for w in raw]
    aparts: list[AssemblyPart] = []
    xpos = {}
    if n == 1:
        centers = [0.5]
    else:
        gap = (budget - sum(widths)) / (n - 1)
        centers, cur = [], (1 - budget) / 2
        for w in widths:
            centers.append(cur + w / 2)
            cur += w + gap
    for p, w, cx in zip(lvl1, widths, centers):
        xpos[p.id] = (cx, w)
        aparts.append(_apart(p, level=1, x_frac=cx, width_frac=w, on=None))
    for p in deeper:                              # chip-on-chip: inherit parent x
        pcx, pw = xpos.get(p.on, (0.5, 0.3))
        w = min(pw * 0.82, _parts.width(p.function) * scale)
        aparts.append(_apart(p, level=levels[p.id], x_frac=pcx, width_frac=w, on=p.on))
        xpos[p.id] = (pcx, w)
    for p in buried:
        lo = min((xpos[q.id][0] for q in lvl1 if (q.attributes or {}).get("emits")),
                 default=0.2)
        hi = max((xpos[q.id][0] for q in lvl1 if (q.attributes or {}).get("detects")),
                 default=0.8)
        aparts.append(AssemblyPart(id=p.id, label=p.name, material=_mat(p.function),
                                   level=0, buried=True, x_frac=(lo + hi) / 2,
                                   width_frac=max(0.4, hi - lo + 0.1)))

    beams = [AssemblyBeam(src=r.src, dst=r.dst, label=r.label)
             for r in brief.relations if r.type == "optical"
             and r.src in xpos and r.dst in xpos]

    bottom_balls = None
    bottom_ball_label = None
    if ball_part:
        bottom_balls = (ball_part.interface.pad_count
                        if ball_part.interface and ball_part.interface.pad_count else 10)
        bottom_ball_label = ball_part.name

    fig = AssemblyFigure(
        caption=brief.caption, base_label=base_label, base_material=base_mat,
        parts=aparts, beams=beams,
        mold=bool(mold_part), mold_label=(mold_part.name if mold_part else "Mold (EMC)"),
        bottom_balls=bottom_balls, bottom_ball_label=bottom_ball_label)
    return Slide(layout_type="figure", title=brief.title, figure=fig)


def _apart(p: Part, level: int, x_frac: float, width_frac: float, on) -> AssemblyPart:
    a = p.attributes or {}
    iface = p.interface
    mount = _MOUNT_MAP.get(iface.kind, "stack") if iface else "stack"
    pad_count = (iface.pad_count if iface and iface.pad_count else 6)
    side = "bottom" if a.get("side") == "bottom" else "top"
    kn = _parts.get(p.function)
    return AssemblyPart(
        id=p.id, label=p.name, material=_mat(p.function), level=level, side=side,
        on=on, x_frac=round(x_frac, 3), width_frac=round(width_frac, 3),
        mount=mount, pad_count=max(1, min(pad_count, 24)),
        emits=bool(a.get("emits")), detects=bool(a.get("detects")),
        glyph=kn.get("glyph"), covers=list(a.get("covers", []) or []))


def _compile_infographic(brief: Brief) -> Slide:
    """P1 stub — infographic briefs are produced with figure data directly by the
    WP7 path; full brief->infographic unification is P6. Fallback to a content slide."""
    bullets = [p.name for p in brief.parts] or ["(내용 필요)"]
    return Slide(layout_type="content", title=brief.title, bullets=bullets[:6])
