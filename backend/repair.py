"""WP3 — deterministic normalization (fix what code can, before the LLM).

Absorbs small-model slips (material aliases, misaligned vias, out-of-range
values) with NO LLM round-trip. Policy: only meaning-preserving fixes — never
reorder/restructure (that stays with the LLM). Returns (fixed, findings).
"""
from __future__ import annotations

from typing import Any

from palette import MATERIALS
from lint import Finding
from models import (Deck, Slide, StackFigure, CompareFigure,
                    TreeFigure, ChartFigure)


# common material aliases small models emit -> canonical palette role
MATERIAL_ALIAS: dict[str, str] = {
    "cu": "copper", "au": "gold", "al": "metal", "ag": "metal", "mo": "metal",
    "ti": "metal", "w": "metal", "sn": "solder", "solder_ball": "solder",
    "si": "silicon", "silicon_die": "silicon", "die": "silicon",
    "abf": "dielectric", "ajinomoto": "dielectric", "buildup": "dielectric",
    "build-up": "dielectric", "pi": "polymer", "polyimide": "polymer",
    "epoxy": "mold", "emc_mold": "emc", "mold_compound": "mold",
    "sin": "nitride", "sinx": "nitride", "si3n4": "nitride",
    "sio": "oxide", "sio2": "oxide", "siox": "oxide",
    "fr4": "pcb", "fr-4": "pcb", "laminate": "pcb", "core": "pcb",
    "ubm": "metal", "rdl_cu": "rdl", "redistribution": "rdl",
    "gan": "gan", "n-gan": "n_gan", "ngan": "n_gan", "p-gan": "p_gan",
    "pgan": "p_gan", "mqw": "mqw", "quantum_dot": "qd", "phosphor": "phosphor",
    "glass_core": "glass", "sapphire": "glass", "lcd_cell": "lcd",
    "sicn": "bond_oxide", "bond": "bond_oxide", "hybrid_bond": "bond_oxide",
    "eml": "emission", "htl": "organic", "etl": "organic", "hil": "organic",
    "transistor": "device", "nanosheet": "device", "finfet": "device",
    "lead_frame": "leadframe", "lead-frame": "leadframe",
    # WP7 general-infographic semantic aliases (color name / synonym -> role)
    "category1": "accent1", "category2": "accent2", "category3": "accent3",
    "category4": "accent4", "series1": "accent1", "series2": "accent2",
    "series3": "accent3", "positive": "good", "negative": "bad",
    "up": "good", "down": "bad", "green": "good", "red": "bad",
    "amber": "warn", "yellow": "warn", "orange": "warn", "blue": "accent1",
    "gridline": "grid", "axis": "track",
}


def _canon_material(role: str | None) -> tuple[str | None, str | None]:
    """Returns (canonical_role, note). note set when changed/fallback."""
    if role is None:
        return None, None
    r = role.lower().strip().replace(" ", "_")
    if r in MATERIALS:
        return r, None
    if r in MATERIAL_ALIAS:
        return MATERIAL_ALIAS[r], f"'{role}'->'{MATERIAL_ALIAS[r]}'"
    return "gray", f"'{role}'->gray (unknown)"


def _fix_stack(fig: StackFigure, where: str, out: list[Finding]):
    rows = fig.rows
    # 1) material aliasing (layer/die/dies/balls/chips/bond/embed/vias)
    for i, r in enumerate(rows):
        rw = f"{where}.rows[{i}]"
        for attr in ("material", "pad_material"):
            if hasattr(r, attr):
                canon, note = _canon_material(getattr(r, attr))
                if note:
                    setattr(r, attr, canon)
                    out.append(Finding("info", f"{rw}.{attr}", "MATERIAL_ALIASED",
                                       f"material normalized: {note}", ""))
        if getattr(r, "vias", None) is not None:
            canon, note = _canon_material(r.vias.material)
            if note:
                r.vias.material = canon
                out.append(Finding("info", f"{rw}.vias", "MATERIAL_ALIASED",
                                   f"via material normalized: {note}", ""))
        for e in (getattr(r, "embeds", None) or []):
            canon, note = _canon_material(e.material)
            if note:
                e.material = canon
        for it in (getattr(r, "items", None) or []):
            canon, note = _canon_material(getattr(it, "material", None))
            if note:
                it.material = canon

    # NOTE: via count is NOT auto-snapped to adjacent balls — not every via row
    # maps 1:1 to balls (e.g. substrate PTH vs BGA balls), and x-alignment is
    # already handled by layout._aligned_via_xs. Count mismatch is advisory only
    # (lint info), never a meaning-changing auto-fix.

    # 2) dies width_frac sum overflow -> proportional scale
    from models import DiesRow
    for i, r in enumerate(rows):
        if isinstance(r, DiesRow):
            tot = sum(it.width_frac for it in r.items)
            if tot > 0.95:
                f = 0.9 / tot
                for it in r.items:
                    it.width_frac = round(it.width_frac * f, 3)
                out.append(Finding("info", f"{where}.rows[{i}]", "DIES_RESCALED",
                                   f"dies width_frac sum {tot:.2f} scaled to fit", ""))


def normalize_slide(slide: Slide) -> tuple[Slide, list[Finding]]:
    out: list[Finding] = []
    fig = slide.figure
    if isinstance(fig, StackFigure):
        _fix_stack(fig, "figure", out)
    elif isinstance(fig, CompareFigure):
        for pi, panel in enumerate(fig.panels):
            if isinstance(panel.figure, StackFigure):
                _fix_stack(panel.figure, f"figure.panels[{pi}]", out)
    elif isinstance(fig, TreeFigure):
        _fix_tree(fig, out)
    return slide, out


def _fix_tree(fig: TreeFigure, out: list[Finding]):
    """Snap a mistyped parent to the closest existing id (case/space-insensitive)."""
    ids = [n.id for n in fig.nodes]
    idset = set(ids)
    norm = {i.lower().replace(" ", ""): i for i in ids}
    for nd in fig.nodes:
        if nd.parent and nd.parent not in idset:
            key = nd.parent.lower().replace(" ", "")
            if key in norm:
                out.append(Finding("info", "figure", "TREE_PARENT_SNAP",
                                   f"parent '{nd.parent}'->'{norm[key]}'"))
                nd.parent = norm[key]


def normalize_deck(deck: Deck) -> tuple[Deck, list[Finding]]:
    out: list[Finding] = []
    for si, slide in enumerate(deck.slides):
        _, fs = normalize_slide(slide)
        for f in fs:
            out.append(Finding(f.level, f"slide[{si}].{f.where}", f.code,
                               f.message, f.fix_hint))
    return deck, out
