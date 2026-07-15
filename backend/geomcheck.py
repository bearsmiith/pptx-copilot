"""WP3 — post-layout geometry check (from coordinates, no rendering).

Runs the layout engine and inspects the placed primitives for real placement
problems: callout overflow, out-of-bounds shapes, label crowding. Doubles as a
layout-engine regression guard when new row types are added.
"""
from __future__ import annotations

from lint import Finding
from layout import (layout_slide, SLIDE_W, SLIDE_H,
                    TextItem, FigureItem, RectShape, CircleShape, PolyShape,
                    Callout)

_EPS = 0.15


def check_layout(slide) -> list[Finding]:
    out: list[Finding] = []
    try:
        items = layout_slide(slide)
    except Exception as e:
        out.append(Finding("error", "layout", "LAYOUT_CRASH",
                           f"layout engine raised: {e}",
                           "simplify the figure (fewer/lighter rows)"))
        return out

    for it in items:
        if not isinstance(it, FigureItem):
            continue
        # callout vertical overflow
        for c in it.callouts:
            if c.ly < it.y - _EPS or c.ly > it.y + it.h + _EPS:
                out.append(Finding("warn", "figure.callouts", "CALLOUT_OVERFLOW",
                                   "a callout label falls outside the figure area",
                                   "reduce the number of labels or shorten them"))
                break
        # callout crowding (labels too close after distribution)
        ys = sorted(c.ly for c in it.callouts)
        crowded = sum(1 for a, b in zip(ys, ys[1:]) if b - a < 0.2)
        if crowded >= 2:
            out.append(Finding("info", "figure.callouts", "CALLOUT_CROWDED",
                               f"{crowded} callouts are tightly spaced",
                               "fewer callouts would read better"))
        # out-of-bounds shapes (regression guard)
        for s in it.shapes:
            if _out_of_bounds(s):
                out.append(Finding("warn", "figure.shapes", "OUT_OF_BOUNDS",
                                   "a shape extends beyond the slide bounds",
                                   "(engine) — likely a width_frac/thickness issue"))
                break
    return out


def _out_of_bounds(s) -> bool:
    if isinstance(s, RectShape):
        xs = [s.x, s.x + s.w]; ys = [s.y, s.y + s.h]
    elif isinstance(s, CircleShape):
        xs = [s.cx - s.r, s.cx + s.r]; ys = [s.cy - s.r, s.cy + s.r]
    elif isinstance(s, PolyShape):
        xs = [p[0] for p in s.points]; ys = [p[1] for p in s.points]
    else:
        return False
    return (min(xs) < -_EPS or max(xs) > SLIDE_W + _EPS
            or min(ys) < -_EPS or max(ys) > SLIDE_H + _EPS)
