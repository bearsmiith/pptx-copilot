"""WP3 — parametric structure builder (deterministic, small-model workhorse).

The LLM emits only a structure name + a few params; this expands the
`domain.STRUCTURES` recipe into a validated full `StackFigure` slide with zero
free-form DSL. The most reliable generation path for small models.
"""
from __future__ import annotations

import copy

from models import Slide, StackFigure
from domain import STRUCTURES, PHOTONIC_STRUCTURES, build_photonic


# tunable params per structure (for list_templates + LLM guidance)
PARAM_SPECS: dict[str, dict] = {
    "hbm": {
        "n_dram": {"type": "int", "default": 8, "min": 2, "max": 16},
        "joint": {"type": "enum", "choices": ["ubump", "hybrid"], "default": "ubump"},
    },
    "hybrid_bond_soic": {
        "pad_count": {"type": "int", "default": 12, "min": 4, "max": 24},
    },
    "glass_core_detailed": {
        "tgv_count": {"type": "int", "default": 5, "min": 3, "max": 10},
    },
    "backside_power": {
        "nano_tsv_count": {"type": "int", "default": 5, "min": 3, "max": 10},
    },
}


def _clampi(v, lo, hi, default):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def list_templates() -> list[dict]:
    """[{name, aka, params, summary}] — for LLM/tool listing."""
    out = []
    for name, s in {**STRUCTURES, **PHOTONIC_STRUCTURES}.items():
        out.append({
            "name": name,
            "aka": s.get("aka", []),
            "params": PARAM_SPECS.get(name, {}),
            "summary": s.get("caption", s.get("title", name)),
        })
    return out


def instantiate(name: str, params: dict | None = None) -> Slide:
    """Deterministically build a validated figure slide from a structure recipe.
    Unknown params ignored; out-of-range clamped. Result passes model validation.
    e.g. instantiate('hbm', {'n_dram': 12, 'joint': 'ubump'})."""
    if name in PHOTONIC_STRUCTURES:                       # graph-form photonic
        slide = build_photonic(name)
        title = ((params or {}).get("title") or "").strip()
        if title:
            slide.title = title
        return slide
    if name not in STRUCTURES:
        raise KeyError(f"unknown structure: {name}")
    params = params or {}
    s = STRUCTURES[name]
    rows = copy.deepcopy(s["rows"])

    caption = s.get("caption")
    if name == "hbm":
        n = _clampi(params.get("n_dram"), 2, 16, 8)
        joint = params.get("joint", "ubump")
        joint = joint if joint in ("ubump", "hybrid", "none") else "ubump"
        for r in rows:
            if r["type"] == "diestack":
                r["count"], r["joint"] = n, joint
        caption = (f"{n}-Hi HBM: base logic die + DRAM via TSV / "
                   + ("hybrid bond" if joint == "hybrid" else "µbump"))
    elif name == "hybrid_bond_soic":
        pc = _clampi(params.get("pad_count"), 4, 24, 12)
        for r in rows:
            if r["type"] == "bond":
                r["count"] = pc
    elif name == "glass_core_detailed":
        c = _clampi(params.get("tgv_count"), 3, 10, 5)
        for r in rows:
            if r["type"] == "layer" and r.get("vias"):
                r["vias"]["count"] = c
    elif name == "backside_power":
        c = _clampi(params.get("nano_tsv_count"), 3, 10, 5)
        for r in rows:
            if r["type"] == "layer" and r.get("vias"):
                r["vias"]["count"] = c

    fig = StackFigure(kind="stack", caption=caption, rows=rows)
    title = (params.get("title") or "").strip() or s["title"]
    return Slide(layout_type="figure", title=title, figure=fig)


def match_structure(text: str) -> list[str]:
    """Keyword/aka match a request to candidate structure names (ranked)."""
    t = (text or "").lower()
    scored = []
    for name, s in {**STRUCTURES, **PHOTONIC_STRUCTURES}.items():
        score = 0
        for kw in [name] + s.get("aka", []):
            if kw.lower() in t:
                score += len(kw)          # longer match = stronger
        if score:
            scored.append((score, name))
    scored.sort(reverse=True)
    return [n for _, n in scored]
