"""WP3 — domain-convention linter (machine-checkable feedback).

Pure functions: Deck/Slide -> list[Finding]. Findings carry a `fix_hint` that
the LLM repair loop turns into a concrete instruction. Runs before render.
Most issues are 'warn' (non-blocking) — hard failures are minimized so small
models aren't stuck (handoff global constraint).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal

from palette import MATERIALS
from models import (Deck, Slide, StackFigure, CompareFigure,
                    LayerRow, BallsRow, DieRow, DiesRow, DieStackRow, BondRow,
                    TimelineFigure, KpiFigure, TableFigure, MatrixFigure,
                    ChartFigure, TreeFigure)


@dataclass
class Finding:
    level: Literal["error", "warn", "info"]
    where: str
    code: str
    message: str
    fix_hint: str = ""

    def as_dict(self):
        return asdict(self)


def _material_ok(role: str | None) -> bool:
    from repair import MATERIAL_ALIAS
    if not role:
        return True
    r = role.lower().strip()
    return r in MATERIALS or r in MATERIAL_ALIAS


def _lint_stack(fig: StackFigure, where: str, out: list[Finding]):
    rows = fig.rows
    if not rows:
        out.append(Finding("warn", where, "EMPTY_FIGURE",
                           "stack figure has no rows", "add cross-section rows"))
        return
    if len(rows) > 9:
        out.append(Finding("info", where, "TOO_MANY_ROWS",
                           f"{len(rows)} rows may be cluttered (>9)",
                           "merge or drop the least important layers"))

    total_t = sum(getattr(r, "t", 1.0) if hasattr(r, "t") else 1.0 for r in rows)
    for i, r in enumerate(rows):
        rw = f"{where}.rows[{i}]"
        # unknown materials
        for attr in ("material", "pad_material"):
            role = getattr(r, attr, None)
            if role is not None and not _material_ok(role):
                out.append(Finding("warn", rw, "UNKNOWN_MATERIAL",
                                   f"material '{role}' not in palette",
                                   f"replace '{role}' with the nearest known role"))
        # via/ball alignment
        if isinstance(r, LayerRow) and r.vias:
            vc = r.vias.count
            for j in (i - 1, i + 1):
                if 0 <= j < len(rows) and isinstance(rows[j], BallsRow):
                    bc = rows[j].count
                    if vc != bc and not (bc % vc == 0 or vc % bc == 0):
                        out.append(Finding(
                            "info", f"{rw}.vias", "VIA_BALL_MISMATCH",
                            f"vias.count={vc} won't align 1:1 to balls.count={bc}",
                            f"set vias.count to {bc} if they should line up"))
                    break
        # thickness dominance
        if isinstance(r, LayerRow) and total_t and r.t / total_t > 0.7:
            out.append(Finding("info", rw, "THICKNESS_RANGE",
                               f"one layer is {r.t/total_t:.0%} of total thickness",
                               "reduce its t so thin layers stay legible"))
        # label length
        lbl = getattr(r, "label", "") or ""
        if len(lbl) > 42:
            out.append(Finding("info", rw, "LABEL_LEN",
                               f"label too long ({len(lbl)} chars)",
                               "shorten the label to fit the callout"))

    # physical sanity: mold/EMC should be at an outer position, not bottom row 0
    r0 = rows[0]
    if getattr(r0, "material", "") in ("mold", "emc"):
        out.append(Finding("warn", f"{where}.rows[0]", "STACK_SANITY",
                           "mold/EMC at the very bottom is unusual",
                           "move mold to the top (encapsulation) end"))

    # bump tier order: ball (big) should be below bump (small)
    ball_i = [i for i, r in enumerate(rows)
              if isinstance(r, BallsRow) and r.size == "ball"]
    bump_i = [i for i, r in enumerate(rows)
              if isinstance(r, BallsRow) and r.size == "bump"]
    if ball_i and bump_i and min(ball_i) > max(bump_i):
        out.append(Finding("warn", where, "BUMP_TIER_ORDER",
                           "large balls sit above small bumps (tier order inverted)",
                           "put big BGA balls at the bottom, µbumps higher up"))

    # structure-specific rules (fanout has no substrate, hybrid uses bond not balls)
    from templates import match_structure
    cands = match_structure(where_hint := (fig.caption or ""))
    labels_join = " ".join((getattr(r, "label", "") or "") for r in rows).lower()
    if "fanout_info" in cands or "fan-out" in labels_join or "info" in labels_join:
        if any(getattr(r, "material", "") == "substrate" for r in rows):
            out.append(Finding("warn", where, "FANOUT_HAS_SUBSTRATE",
                               "fan-out should have no organic substrate",
                               "remove the substrate layer (RDL replaces it)"))


def lint_slide(slide: Slide) -> list[Finding]:
    out: list[Finding] = []
    fig = slide.figure
    if fig is None:
        if slide.layout_type == "figure":
            out.append(Finding("error", "figure", "EMPTY_FIGURE",
                               "layout_type is 'figure' but no figure is present "
                               "(renders blank)",
                               "populate `figure` (e.g. a stack with rows)"))
        return out
    if isinstance(fig, StackFigure):
        _lint_stack(fig, "figure", out)
    elif isinstance(fig, CompareFigure):
        for pi, panel in enumerate(fig.panels):
            if isinstance(panel.figure, StackFigure):
                _lint_stack(panel.figure, f"figure.panels[{pi}]", out)
    elif isinstance(fig, (TimelineFigure, KpiFigure, TableFigure, MatrixFigure,
                          ChartFigure, TreeFigure)):
        _lint_general(fig, "figure", out)
    return out


# ---- WP7 general-infographic lints (limits single-sourced in archetypes) ----

def _limit(kind: str, key: str):
    from archetypes import ARCHETYPES
    return ARCHETYPES.get(kind, {}).get("limits", {}).get(key)


def _lint_general(fig, where: str, out: list[Finding]):
    if isinstance(fig, TimelineFigure):
        n = len(fig.milestones)
        for p in fig.phases:
            if p.start >= n or p.end >= n:
                out.append(Finding("error", where, "PHASE_OUT_OF_RANGE",
                                   f"phase '{p.label}' references a milestone index "
                                   f"outside 0..{n-1}",
                                   "set phase start/end to valid milestone indices"))
        emph = sum(1 for m in fig.milestones if m.emphasis)
        if emph > 2:
            out.append(Finding("warn", where, "TOO_MANY_EMPHASIS",
                               f"{emph} milestones emphasized",
                               "emphasize only 1-2 key milestones"))
    elif isinstance(fig, ChartFigure):
        nc = len(fig.categories)
        for si, s in enumerate(fig.series):
            if len(s.values) != nc:
                out.append(Finding("error", where, "SERIES_LENGTH_MISMATCH",
                                   f"series '{s.name}' has {len(s.values)} values "
                                   f"but there are {nc} categories",
                                   "make every series length equal categories length"))
    elif isinstance(fig, TableFigure):
        nc = len(fig.columns)
        for ri, row in enumerate(fig.rows):
            if len(row) != nc:
                out.append(Finding("warn", where, "TABLE_RAGGED",
                                   f"row {ri} has {len(row)} cells, expected {nc}",
                                   "give every row exactly one cell per column"))
        if fig.emphasis_col is not None and not (0 <= fig.emphasis_col < nc):
            out.append(Finding("warn", where, "EMPHASIS_COL_RANGE",
                               "emphasis_col out of range", "0 ≤ emphasis_col < columns"))
    elif isinstance(fig, MatrixFigure):
        if len(fig.quadrants) != 4:
            out.append(Finding("error", where, "MATRIX_QUADRANTS",
                               "matrix needs exactly 4 quadrants",
                               "provide 4 quadrants: TL, TR, BL, BR"))
    elif isinstance(fig, TreeFigure):
        ids = [n.id for n in fig.nodes]
        idset = set(ids)
        if len(ids) != len(idset):
            out.append(Finding("warn", where, "TREE_DUP_ID", "duplicate node ids",
                               "make every node id unique"))
        roots = [n for n in fig.nodes if not n.parent or n.parent not in idset]
        if len(roots) != 1:
            out.append(Finding("warn", where, "TREE_ROOTS",
                               f"{len(roots)} roots (expected 1)",
                               "exactly one node has parent=null; others reference a valid id"))
        for nd in fig.nodes:
            if nd.parent and nd.parent not in idset:
                out.append(Finding("warn", where, "TREE_ORPHAN",
                                   f"node '{nd.id}' parent '{nd.parent}' not found",
                                   "point parent to an existing node id"))


def lint_deck(deck: Deck) -> list[Finding]:
    out: list[Finding] = []
    for si, slide in enumerate(deck.slides):
        for f in lint_slide(slide):
            out.append(Finding(f.level, f"slide[{si}].{f.where}", f.code,
                               f.message, f.fix_hint))
    return out
