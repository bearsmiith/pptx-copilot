"""WP10 — user edit overrides as a diff layer over engine geometry.

The engine (layout.py) computes base DrawItems; a node may carry `overrides`
(moves/scales/text/role/hidden per eid + freely added elements). SVG preview and
pptx export BOTH pass through `apply_overrides`, so an edit shows identically in
both. The LLM never sees overrides (no schema pollution). Pure functions.
"""
from __future__ import annotations

from layout import (TextItem, RectShape, PolyShape, CircleShape, EdgeShape,
                    Callout, FigureItem)
from palette import MATERIALS

_MOVE = "dx", "dy"


def _apply_edit(prim, e: dict):
    """Mutate one primitive per its override dict (dx/dy/sw/sh/text/role)."""
    dx, dy = e.get("dx", 0) or 0, e.get("dy", 0) or 0
    if isinstance(prim, (TextItem, RectShape)):
        prim.x += dx; prim.y += dy
    elif isinstance(prim, CircleShape):
        prim.cx += dx; prim.cy += dy
    elif isinstance(prim, EdgeShape):
        prim.x1 += dx; prim.y1 += dy; prim.x2 += dx; prim.y2 += dy
    elif isinstance(prim, Callout):
        prim.tx += dx; prim.ty += dy; prim.lx += dx; prim.ly += dy
    elif isinstance(prim, PolyShape):
        prim.points = [(px + dx, py + dy) for px, py in prim.points]
    if isinstance(prim, RectShape):
        if e.get("sw"):
            prim.w *= float(e["sw"])
        if e.get("sh"):
            prim.h *= float(e["sh"])
    txt = e.get("text")
    if txt is not None:
        if isinstance(prim, TextItem):
            prim.text = txt
        elif isinstance(prim, RectShape):
            prim.inner_label = txt
        elif isinstance(prim, Callout):
            prim.text = txt
        elif isinstance(prim, EdgeShape):
            prim.label = txt
    role = e.get("role")
    if role and role in MATERIALS and hasattr(prim, "material"):
        prim.material = role
    return prim


def _added_to_prim(a: dict):
    t = a.get("type")
    role = a.get("role") if a.get("role") in MATERIALS else "accent1"
    if t == "text":
        r = "panel_title" if (a.get("size", 14) or 14) >= 20 else "caption"
        return TextItem(r, a.get("x", 1), a.get("y", 1), a.get("w", 2.0),
                        a.get("h", 0.4), text=a.get("text", ""))
    if t == "arrow":
        return EdgeShape(a.get("x1", 1), a.get("y1", 1), a.get("x2", 2),
                         a.get("y2", 2), label=a.get("label") or None)
    if t == "rect":
        return RectShape(a.get("x", 1), a.get("y", 1), a.get("w", 1.2),
                         a.get("h", 0.5), material=role, rx=0.06,
                         inner_label=a.get("label") or None, label_size=14)
    return None


def apply_overrides(items: list, ov: dict | None) -> list:
    if not ov:
        return items
    edits = ov.get("items", {}) or {}
    out = []
    for it in items:
        if isinstance(it, FigureItem):
            for coll in (it.shapes, it.callouts, it.texts):
                kept = []
                for p in coll:
                    e = edits.get(getattr(p, "eid", None))
                    if e and e.get("hidden"):
                        continue
                    if e:
                        _apply_edit(p, e)
                    kept.append(p)
                coll[:] = kept
            it.edges[:] = [e for e in it.edges
                           if not (edits.get(getattr(e, "eid", None)) or {}).get("hidden")]
            for e in it.edges:
                ed = edits.get(getattr(e, "eid", None))
                if ed:
                    _apply_edit(e, ed)
            out.append(it)
        elif isinstance(it, TextItem):
            e = edits.get(getattr(it, "eid", None))
            if e and e.get("hidden"):
                continue
            if e:
                _apply_edit(it, e)
            out.append(it)
        else:
            out.append(it)
    # freely-added elements -> into the first figure (or top-level as text)
    added = ov.get("added", []) or []
    if added:
        fig = next((o for o in out if isinstance(o, FigureItem)), None)
        for a in added:
            prim = _added_to_prim(a)
            if prim is None:
                continue
            if fig is None:
                out.append(prim)
            elif isinstance(prim, EdgeShape):
                fig.edges.append(prim)
            elif isinstance(prim, TextItem):
                fig.texts.append(prim)
            else:
                fig.shapes.append(prim)
    return out


def carry_forward(old_ov: dict | None, new_items: list) -> tuple[dict, int, int]:
    """After an LLM revision re-lays-out the slide, keep only edits whose eid
    still exists with the same primitive type; always keep `added`. Returns
    (new_overrides, kept, dropped)."""
    if not old_ov:
        return {}, 0, 0
    types = {}
    _fill_types(new_items, types)
    old_items = (old_ov.get("items", {}) or {})
    kept = {eid: e for eid, e in old_items.items() if eid in types}
    dropped = len(old_items) - len(kept)
    new_ov = {"v": old_ov.get("v", 1), "items": kept,
              "added": old_ov.get("added", []) or []}
    return new_ov, len(kept), dropped


def _fill_types(items: list, out: dict) -> None:
    for it in items:
        if isinstance(it, FigureItem):
            for coll in (it.shapes, it.edges, it.callouts, it.texts):
                for p in coll:
                    if getattr(p, "eid", None):
                        out[p.eid] = type(p).__name__
        elif getattr(it, "eid", None):
            out[it.eid] = type(it).__name__
