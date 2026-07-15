"""WP8 — verify -> adapt. Check that the compiled figure actually expresses what
the Brief intended; where the current primitives can't, substitute the nearest
shape (compile already falls back an unknown function to a generic box) and, if a
core element still can't be shown, surface it HONESTLY rather than dropping it.
"""
from __future__ import annotations

from brief_model import Brief

# functions with no dedicated glyph → drawn as a generic box (shape substitution)
_APPROXIMATED = {"generic"}


def critique(brief: Brief, fig) -> list[str]:
    """Return human-readable unmet points (what the figure does NOT show)."""
    unmet: list[str] = []
    if getattr(fig, "kind", None) != "assembly":
        return unmet
    part_ids = {p.id for p in fig.parts}
    labels = {p.label for p in fig.parts}

    # every optical relation should have drawn a beam (both endpoints placed)
    for r in brief.relations:
        if r.type == "optical" and (r.src not in part_ids or r.dst not in part_ids):
            src = next((p.name for p in brief.parts if p.id == r.src), r.src)
            dst = next((p.name for p in brief.parts if p.id == r.dst), r.dst)
            unmet.append(f"광 경로 {src}→{dst}")

    # a part the brief named that the compiler could not place (not a base/feature)
    import parts as _parts
    placed = part_ids | labels
    for p in brief.parts:
        if _parts.is_base(p.function) or _parts.feature(p.function):
            continue
        if p.id not in placed and p.name not in placed:
            unmet.append(f"부품 {p.name}")

    # parts drawn only as an approximate generic shape (no dedicated glyph)
    for p in brief.parts:
        if p.function.lower().strip() in _APPROXIMATED and p.name in labels:
            unmet.append(f"{p.name}(≈ 근사 표현)")
    return unmet


def annotate_unmet(fig, unmet: list[str]) -> None:
    """Adapter: surface unmet points in the caption (honest, not hidden)."""
    if not unmet:
        return
    note = "[미표현/근사: " + "; ".join(dict.fromkeys(unmet))[:120] + "]"
    fig.caption = (fig.caption + "  " + note) if getattr(fig, "caption", None) else note
