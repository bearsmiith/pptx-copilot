"""Deterministic layout engine (v2).

Turns semantic figures (models.py) into positioned draw primitives in INCHES.
Single source of geometry: render_svg.py and export_pptx.py both consume
these, so browser preview and .pptx match by construction.

Slide is 16:9 = 13.333in x 7.5in.

Primitives:
  RectShape / PolyShape / CircleShape — filled shapes keyed by material role
  EdgeShape — arrow (flow)
  Callout   — side label with an elbow leader line to a target point
  TextItem  — plain positioned text (titles, bullets, captions)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Optional

from models import (
    Slide, Figure, FlowFigure, StackFigure, CompareFigure, ArrayFigure,
    PhotonicFigure, PhotonicNode, PhotonicLink,
    LayerRow, DieRow, DiesRow, BallsRow, ChipsRow, BondRow, DieStackRow,
    TimelineFigure, KpiFigure, TableFigure, MatrixFigure, ChartFigure, TreeFigure,
    AssemblyFigure,
)

SLIDE_W = 13.333
SLIDE_H = 7.5

MARGIN_X = 0.7
TITLE_Y = 0.42
TITLE_H = 0.95
BODY_TOP = TITLE_Y + TITLE_H + 0.15


# ---- primitives ------------------------------------------------------

@dataclass
class TextItem:
    role: Literal["title", "subtitle", "body", "bullets", "caption", "panel_title"]
    x: float; y: float; w: float; h: float
    text: str = ""
    bullets: list[str] = field(default_factory=list)


@dataclass
class RectShape:
    x: float; y: float; w: float; h: float
    material: str = "gray"
    rx: float = 0.0                      # corner radius (inches)
    inner_label: Optional[str] = None    # centered text inside
    label_size: int = 15                 # px at 96dpi (svg); pptx converts


@dataclass
class PolyShape:
    points: list[tuple[float, float]]
    material: str = "gray"


@dataclass
class CircleShape:
    cx: float; cy: float; r: float
    material: str = "solder"


@dataclass
class EdgeShape:
    x1: float; y1: float; x2: float; y2: float
    label: Optional[str] = None
    arrow: bool = True             # False = plain line (chart line, tree connector)


@dataclass
class Callout:
    text: str
    tx: float; ty: float      # target point (on the feature)
    lx: float; ly: float      # label anchor (text start)
    side: Literal["left", "right"] = "right"


@dataclass
class FigureItem:
    x: float; y: float; w: float; h: float
    shapes: list = field(default_factory=list)       # Rect/Poly/Circle
    edges: list[EdgeShape] = field(default_factory=list)
    callouts: list[Callout] = field(default_factory=list)
    texts: list[TextItem] = field(default_factory=list)


DrawItem = TextItem | FigureItem

# row band heights (relative units, scaled to fit)
_BALL_T = 0.85
_BUMP_T = 0.45


# ---- flow ------------------------------------------------------------

def _layout_flow(fig: FlowFigure, x: float, y: float, w: float, h: float) -> FigureItem:
    item = FigureItem(x=x, y=y, w=w, h=h)
    n = len(fig.nodes)
    if n == 0:
        return item
    cap_h = 0.5 if fig.caption else 0.0
    band_h = h - cap_h
    gap = 0.5
    node_h = min(1.3, band_h * 0.55)
    node_w = max(1.2, min(2.6, (w - gap * (n - 1)) / n))
    chain_w = node_w * n + gap * (n - 1)
    sx = x + max(0.0, (w - chain_w) / 2)
    ny = y + band_h / 2 - node_h / 2
    pos = {}
    for i, node in enumerate(fig.nodes):
        nx = sx + i * (node_w + gap)
        r = RectShape(nx, ny, node_w, node_h, material="accent", rx=0.1,
                      inner_label=node.label, label_size=17)
        item.shapes.append(r)
        pos[node.id] = r
    for e in fig.edges:
        s, d = pos.get(e.src), pos.get(e.dst)
        if not s or not d:
            continue
        item.edges.append(EdgeShape(s.x + s.w, s.y + s.h / 2, d.x, d.y + d.h / 2, e.label))
    return item


# ---- stack -----------------------------------------------------------

_BOND_T = 0.32


def _row_t(row) -> float:
    if isinstance(row, (LayerRow, DieRow, DiesRow, ChipsRow)):
        return row.t
    if isinstance(row, BallsRow):
        return _BALL_T if row.size == "ball" else _BUMP_T
    if isinstance(row, BondRow):
        return _BOND_T
    if isinstance(row, DieStackRow):
        return row.count * row.t_each
    return 1.0


# ---- ball/bump shape helpers (polygon approximations — renderer-agnostic) --

def _ellipse_poly(cx: float, cy: float, rx: float, ry: float,
                  material: str, n: int = 22) -> PolyShape:
    pts = [(cx + rx * math.cos(2 * math.pi * i / n),
            cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return PolyShape(pts, material)


def _dome_poly(cx: float, base_y: float, rx: float, h: float,
               material: str, up: bool = True, n: int = 14) -> PolyShape:
    """Hemisphere. up=True: flat base at base_y, apex above (encapsulation,
    bump-on-pad). up=False: flat top at base_y, round side below (solder cap
    hanging from a Cu pillar)."""
    sign = -1.0 if up else 1.0
    pts = [(cx + rx * math.cos(math.pi * (1 - i / n)),
            base_y + sign * h * math.sin(math.pi * (1 - i / n)))
           for i in range(n + 1)]
    return PolyShape(pts, material)


def _barrel_poly(cx: float, top: float, bot: float, w: float,
                 material: str) -> PolyShape:
    """C4 joint: pad-width top/bottom, concave waist (~72%)."""
    h = bot - top
    wm = w * 0.72
    q1, q3 = top + h * 0.3, top + h * 0.7
    return PolyShape(
        [(cx - w / 2, top), (cx + w / 2, top),
         (cx + wm / 2, q1), (cx + wm / 2, q3),
         (cx + w / 2, bot), (cx - w / 2, bot),
         (cx - wm / 2, q3), (cx - wm / 2, q1)], material)


def _ball_shapes(shape: str, cx: float, band_top: float, rt: float,
                 r: float, step: float, n: int, material: str) -> list:
    """Primitives for one ball/bump at grid position cx."""
    cy = band_top + rt / 2
    max_rx = (step * 0.46) if n > 1 else r * 1.2
    if shape == "flat":       # post-reflow BGA ball: wider than tall
        return [_ellipse_poly(cx, cy, min(r * 1.18, max_rx), r * 0.8, material)]
    if shape == "barrel":     # C4 joint between pads
        w = min(2 * r * 0.95, max_rx * 1.7)
        return [_barrel_poly(cx, band_top + rt * 0.06, band_top + rt * 0.94,
                             w, material)]
    if shape == "pillar":     # Cu pillar + solder dome cap (die above)
        pw = min(r * 1.15, max_rx * 1.5)
        ph = rt * 0.52
        cap_h = rt * 0.34
        return [
            RectShape(cx - pw / 2, band_top + rt * 0.05, pw, ph,
                      material="copper"),
            _dome_poly(cx, band_top + rt * 0.05 + ph, pw * 0.52, cap_h,
                       material, up=False),
        ]
    if shape == "dome":       # hemisphere, flat base down
        return [_dome_poly(cx, band_top + rt * 0.95, min(r * 1.1, max_rx),
                           rt * 0.82, material, up=True)]
    return [CircleShape(cx, cy, r, material)]   # round


def _ball_xs(body_x: float, body_w: float, width_frac: float, n: int) -> list[float]:
    """Shared x-grid for balls rows — vias snap to this so connected
    ball/via stacks align vertically."""
    span = body_w * width_frac * 0.92
    x0 = body_x + (body_w - span) / 2
    if n == 1:
        return [x0 + span / 2]
    step = span / (n - 1)
    return [x0 + i * step for i in range(n)]


def _aligned_die_xs(rows, idx: int, count: int, body_x: float, body_w: float,
                    bx: float, bw: float) -> list[float]:
    """Evenly spaced x-centers for bond pad columns across the interface width,
    inset from the edges so they sit under the dies."""
    span = bw * 0.86
    x0 = bx + (bw - span) / 2
    if count <= 1:
        return [bx + bw / 2]
    step = span / (count - 1)
    return [x0 + i * step for i in range(count)]


def _wirebonds(item, dx: float, dw: float, die_top: float,
               body_x: float, body_w: float, land_y: float):
    """Gold wire-bond ribbon arcs from the die's top corners out and down to the
    row below, on both sides (QFN/leadframe legacy packages)."""
    import math as _m

    def ribbon(x_start, y_start, x_end, y_end, tw=0.03, n=14):
        peak = min(y_start, y_end) - 0.28    # arc rises above both endpoints
        top, bot = [], []
        for k in range(n + 1):
            u = k / n
            # quadratic bezier through (start, control=peak apex, end)
            cx = (x_start + x_end) / 2
            px = (1 - u) ** 2 * x_start + 2 * (1 - u) * u * cx + u ** 2 * x_end
            py = (1 - u) ** 2 * y_start + 2 * (1 - u) * u * peak + u ** 2 * y_end
            top.append((px, py))
            bot.append((px, py + tw))
        item.shapes.append(PolyShape(top + bot[::-1], "gold"))

    npairs = 3
    for k in range(npairs):
        inset = 0.12 + k * 0.14
        # left wires: die top-left area -> landing left of the die
        ribbon(dx + inset, die_top + 0.03,
               max(body_x + 0.1, dx - 0.35 - k * 0.22), land_y)
        # right wires: mirror
        ribbon(dx + dw - inset, die_top + 0.03,
               min(body_x + body_w - 0.1, dx + dw + 0.35 + k * 0.22), land_y)


def _aligned_via_xs(rows, idx: int, vcount: int,
                    body_x: float, body_w: float) -> list[float] | None:
    """x-centers for a layer's vias, snapped onto the grid of the nearest
    balls row (±2 rows). Equal counts align 1:1; fewer vias sit exactly on
    an evenly-chosen subset of the ball positions."""
    for di in (1, -1, 2, -2):
        j = idx + di
        if 0 <= j < len(rows) and isinstance(rows[j], BallsRow):
            n = rows[j].count
            if vcount > n:
                continue
            bxs = _ball_xs(body_x, body_w, rows[j].width_frac, n)
            if vcount == 1:
                return [bxs[(n - 1) // 2]]
            picks, seen = [], set()
            for i in range(vcount):
                k = round(i * (n - 1) / (vcount - 1))
                if k in seen:
                    return None
                seen.add(k)
                picks.append(bxs[k])
            return picks
    return None


def _vias_polys(v, lx: float, lw: float, ly: float, lh: float,
                xs: list[float] | None = None) -> list[PolyShape]:
    """Vias through a layer band. hourglass = TGV canonical shape.
    xs (optional) = explicit x-centers from ball-grid alignment."""
    polys = []
    n = v.count
    if xs is None:
        span = lw * 0.76
        x0 = lx + (lw - span) / 2
        step = span / max(1, n - 1) if n > 1 else 0
        xs = [x0 + (i * step if n > 1 else span / 2) for i in range(n)]
    wide = min(0.34, lh * 0.9)          # top/bottom width
    narrow = wide * 0.42
    for cx in xs:
        t, b = ly, ly + lh
        if v.shape == "straight":
            polys.append(PolyShape(
                [(cx - narrow / 2, t), (cx + narrow / 2, t),
                 (cx + narrow / 2, b), (cx - narrow / 2, b)], v.material))
        elif v.shape == "tapered":
            polys.append(PolyShape(
                [(cx - wide / 2, t), (cx + wide / 2, t),
                 (cx + narrow / 2, b), (cx - narrow / 2, b)], v.material))
        else:  # hourglass
            m = (t + b) / 2
            polys.append(PolyShape(
                [(cx - wide / 2, t), (cx + wide / 2, t), (cx + narrow / 2, m),
                 (cx + wide / 2, b), (cx - wide / 2, b), (cx - narrow / 2, m)],
                v.material))
    return polys


def _layout_stack(fig: StackFigure, x: float, y: float, w: float, h: float,
                  labels: str = "callout") -> FigureItem:
    """Bottom-to-top cross-section. labels='callout' uses a right gutter;
    'inline' puts labels inside bands (for nested/compare panels)."""
    item = FigureItem(x=x, y=y, w=w, h=h)
    rows = fig.rows
    if not rows:
        return item

    cap_h = 0.45 if fig.caption else 0.0
    gutter = 3.0 if labels == "callout" else 0.0
    body_w = w - gutter
    body_x = x
    body_h = h - cap_h

    total_t = sum(_row_t(r) for r in rows)
    scale = body_h / total_t
    # cap band size so few-row stacks don't become huge slabs
    scale = min(scale, 1.15)
    used_h = total_t * scale
    y_cursor = y + (body_h - used_h) / 2 + used_h   # bottom of stack (grows upward)

    # callout bookkeeping: (text, tx, ty)
    pending: list[tuple[str, float, float]] = []

    def _draw_underfill(dx: float, dw: float, rt: float, yb: float,
                        gap_h: float, insert_at: int) -> tuple[float, float]:
        """Realistic underfill: a body filling the bump gap under the die
        (inserted BELOW the bumps in paint order so bumps stay visible) plus
        small fillets climbing the die sidewalls, feet resting on the layer
        below. Returns (fillet width, base y) for callout targeting."""
        climb = min(rt * 0.25, 0.22)          # how far it climbs the die wall
        fw = max(0.12, min(0.28, dw * 0.12))  # fillet foot width
        base = yb + gap_h                      # top of the layer below
        if gap_h > 0.02:
            item.shapes.insert(insert_at,
                               RectShape(dx, yb, dw, gap_h, material="underfill"))
        item.shapes.append(PolyShape(
            [(dx - fw, base), (dx, yb - climb), (dx, base)], "underfill"))
        item.shapes.append(PolyShape(
            [(dx + dw + fw, base), (dx + dw, yb - climb), (dx + dw, base)],
            "underfill"))
        return fw, base

    marks: list[int] = []                      # shapes-list index per row

    for idx, row in enumerate(rows):
        marks.append(len(item.shapes))
        rt = _row_t(row) * scale
        band_top = y_cursor - rt
        if isinstance(row, LayerRow):
            lw = body_w * row.width_frac
            lx = body_x + (body_w - lw) / 2
            # a layer with vias/embeds gets a callout — inner text would collide
            can_inner = (row.vias is None and not row.embeds) or labels == "inline"
            inner = row.label if can_inner and (
                (labels == "inline" and rt >= 0.26) or
                (labels == "callout" and rt >= 0.42 and row.width_frac >= 0.55)
            ) else None
            item.shapes.append(RectShape(lx, band_top, lw, rt, material=row.material,
                                         inner_label=inner,
                                         label_size=14 if rt < 0.5 else 15))
            if inner is None:
                pending.append((row.label, lx + lw, band_top + rt / 2))
            if row.vias:
                # snap via x-centers onto the nearest balls row grid
                xs = _aligned_via_xs(rows, idx, row.vias.count, body_x, body_w)
                if xs is not None:
                    xs = [cx for cx in xs if lx + 0.2 < cx < lx + lw - 0.2] or None
                vp = _vias_polys(row.vias, lx, lw, band_top, rt, xs=xs)
                item.shapes.extend(vp)
                if row.vias.label and vp:
                    last = vp[-1].points
                    vx = max(p[0] for p in last)
                    pending.append((row.vias.label, vx, band_top + rt / 2))
            for e in (row.embeds or []):
                ew = lw * e.width_frac
                pad = lw * 0.05
                ex = {"left": lx + pad, "center": lx + (lw - ew) / 2,
                      "right": lx + lw - ew - pad}[e.align]
                eh = min(rt * 0.55, 0.5)
                ey = {"top": band_top + rt * 0.06,
                      "middle": band_top + (rt - eh) / 2,
                      "bottom": band_top + rt - eh - rt * 0.06}[e.position]
                e_inner = e.label if (labels == "inline" and eh >= 0.26 and ew >= 1.0) \
                    or (ew >= 1.4 and eh >= 0.32) else None
                item.shapes.append(RectShape(ex, ey, ew, eh, material=e.material,
                                             inner_label=e_inner, label_size=13))
                if e_inner is None and labels == "callout":
                    pending.append((e.label, ex + ew, ey + eh / 2))
        elif isinstance(row, DieRow):
            dw = body_w * row.width_frac
            dx = {"left": body_x, "center": body_x + (body_w - dw) / 2,
                  "right": body_x + body_w - dw}[row.align]
            inner = row.label if rt >= 0.34 and dw >= 1.2 else None
            # underfill needs something below to rest on; fillets only make
            # sense when the die is narrower than the stack
            if row.underfill and idx > 0 and row.width_frac <= 0.9:
                below = rows[idx - 1]
                gap_h = _row_t(below) * scale if isinstance(below, BallsRow) else 0.0
                fw, base = _draw_underfill(dx, dw, rt, y_cursor, gap_h, marks[idx - 1])
                pending.append(("Underfill", dx + dw + fw * 0.75,
                                (base + y_cursor - 0.1) / 2))
            item.shapes.append(RectShape(dx, band_top, dw, rt, material=row.material,
                                         inner_label=inner, label_size=16))
            if inner is None:
                pending.append((row.label, dx + dw, band_top + rt / 2))
            if row.wirebond and idx > 0:
                below = rows[idx - 1]
                land_y = y_cursor + (_row_t(below) * scale) * 0.4
                _wirebonds(item, dx, dw, band_top, body_x, body_w, land_y)
                pending.append(("Wire bond", dx + dw + 0.5, band_top - 0.15))
        elif isinstance(row, BondRow):
            bw = body_w * row.width_frac
            bx = body_x + (body_w - bw) / 2
            # thin dielectric interface band
            item.shapes.append(RectShape(bx, band_top, bw, rt, material=row.material))
            # central bond line
            mid = band_top + rt / 2
            item.shapes.append(RectShape(bx, mid - 0.012, bw, 0.024, material="dark"))
            # fine Cu pad columns straddling the bond line, snapped to the die above
            xs = _aligned_die_xs(rows, idx, row.count, body_x, body_w, bx, bw)
            pw = min(0.12, (bw / row.count) * 0.5)
            ph = rt * 0.42
            for cx in xs:
                item.shapes.append(RectShape(cx - pw / 2, mid - ph, pw, ph,
                                             material=row.pad_material))
                item.shapes.append(RectShape(cx - pw / 2, mid, pw, ph,
                                             material=row.pad_material))
            pending.append((row.label, bx + bw, mid))
        elif isinstance(row, DieStackRow):
            dw = body_w * row.width_frac
            dx = body_x + (body_w - dw) / 2
            seg = rt / row.count
            die_h = seg * 0.80
            joint_h = seg - die_h
            # TSV columns through the whole stack (drawn first, behind dies)
            if row.tsv:
                ncol = min(6, max(3, row.count // 2))
                tspan = dw * 0.7
                tx0 = dx + (dw - tspan) / 2
                tstep = tspan / (ncol - 1) if ncol > 1 else 0
                tw = min(0.09, dw * 0.05)
                for c in range(ncol):
                    cx = tx0 + c * tstep
                    item.shapes.append(RectShape(cx - tw / 2, band_top, tw, rt,
                                                 material="copper"))
            for i in range(row.count):
                die_bottom = band_top + rt - i * seg
                die_top = die_bottom - die_h
                item.shapes.append(RectShape(dx, die_top, dw, die_h,
                                             material=row.material))
                # joint below this die (except the very bottom die)
                if i > 0 and row.joint != "none":
                    jy = die_bottom
                    if row.joint == "hybrid":
                        item.shapes.append(RectShape(dx, jy - joint_h / 2, dw,
                                                     max(0.02, joint_h * 0.5),
                                                     material="bond_oxide"))
                    else:  # ubump
                        nb = min(10, max(4, int(dw / 0.35)))
                        bspan = dw * 0.86
                        bx0 = dx + (dw - bspan) / 2
                        bstep = bspan / (nb - 1) if nb > 1 else 0
                        br = min(joint_h * 0.42, bstep * 0.34)
                        for b in range(nb):
                            item.shapes.append(CircleShape(bx0 + b * bstep, jy, br,
                                                           "solder"))
            pending.append((f"{row.label} ×{row.count}", dx + dw,
                            band_top + rt / 2))
        elif isinstance(row, DiesRow):
            # side-by-side dies, group centered; rescale if the sum overflows
            k = len(row.items)
            gap = body_w * 0.05
            widths = [body_w * it.width_frac for it in row.items]
            total = sum(widths) + gap * (k - 1)
            if total > body_w * 0.96:
                f = (body_w * 0.96 - gap * (k - 1)) / sum(widths)
                widths = [w * f for w in widths]
                total = body_w * 0.96
            cx0 = body_x + (body_w - total) / 2
            uf_marked = False
            below = rows[idx - 1] if idx > 0 else None
            gap_h = _row_t(below) * scale if isinstance(below, BallsRow) else 0.0
            for it, dw in zip(row.items, widths):
                inner = it.label if rt >= 0.34 and dw >= 1.0 else None
                if it.underfill and idx > 0:
                    fw, base = _draw_underfill(cx0, dw, rt, y_cursor, gap_h,
                                               marks[idx - 1])
                    if not uf_marked:
                        pending.append(("Underfill", cx0 + dw + fw * 0.75,
                                        (base + y_cursor - 0.1) / 2))
                        uf_marked = True
                item.shapes.append(RectShape(cx0, band_top, dw, rt,
                                             material=it.material,
                                             inner_label=inner, label_size=15))
                if inner is None:
                    pending.append((it.label, cx0 + dw, band_top + rt / 2))
                cx0 += dw + gap
        elif isinstance(row, BallsRow):
            n = row.count
            xs = _ball_xs(body_x, body_w, row.width_frac, n)
            step = xs[1] - xs[0] if n > 1 else 0
            # diameter bounded by both band height and pitch (no overlap)
            r = min(rt * 0.46, (step * 0.72 / 2) if n > 1 else rt * 0.46)
            for cx in xs:
                item.shapes.extend(_ball_shapes(row.shape, cx, band_top, rt,
                                                r, step, n, row.material))
            pending.append((row.label, xs[-1] + r * 1.2, band_top + rt / 2))
        elif isinstance(row, ChipsRow):
            n = row.count
            span = body_w * row.width_frac * 0.94
            x0 = body_x + (body_w - span) / 2
            cw = span / n * 0.62
            gap = span / n - cw
            for i in range(n):
                item.shapes.append(RectShape(x0 + i * (cw + gap), band_top, cw, rt,
                                             material=row.material, rx=0.02))
            pending.append((row.label, x0 + span, band_top + rt / 2))
        y_cursor = band_top

    # distribute callouts in the right gutter without overlap.
    # long labels wrap to 2 lines, so the gap below them must be larger.
    if labels == "callout" and pending:
        label_x = x + body_w + 0.55

        def gap_after(text: str) -> float:
            return 0.56 if len(text) > 26 else 0.34

        pending.sort(key=lambda p: p[2])
        n = len(pending)
        top = y + 0.05
        bot = y + body_h - 0.15
        ys = [p[2] for p in pending]
        for i in range(1, n):
            need = gap_after(pending[i - 1][0])
            if ys[i] < ys[i - 1] + need:
                ys[i] = ys[i - 1] + need
        overflow = ys[-1] - bot
        if overflow > 0:
            for i in range(n):
                ys[i] -= overflow
            for i in range(n - 2, -1, -1):
                need = gap_after(pending[i][0])
                if ys[i] > ys[i + 1] - need:
                    ys[i] = ys[i + 1] - need
        for (text, tx, ty), ly in zip(pending, ys):
            item.callouts.append(Callout(text=text, tx=tx, ty=ty, lx=label_x, ly=ly))

    if fig.caption:
        item.texts.append(TextItem("caption", x, y + h - 0.4, w, 0.35, text=fig.caption))
    return item


# ---- compare ---------------------------------------------------------

def _layout_compare(fig: CompareFigure, x: float, y: float, w: float, h: float) -> FigureItem:
    item = FigureItem(x=x, y=y, w=w, h=h)
    p = len(fig.panels)
    gap = 0.45
    pw = (w - gap * (p - 1)) / p
    cap_h = 0.45 if fig.caption else 0.0
    for i, panel in enumerate(fig.panels):
        px = x + i * (pw + gap)
        item.shapes.append(RectShape(px, y, pw, h - cap_h, material="white", rx=0.12))
        item.texts.append(TextItem("panel_title", px + 0.15, y + 0.12, pw - 0.3, 0.4,
                                   text=panel.title))
        sub_y = y + 0.62
        sub_h = h - cap_h - 0.78
        sub_x, sub_w = px + 0.25, pw - 0.5
        if panel.figure is not None:
            if isinstance(panel.figure, StackFigure):
                sub = _layout_stack(panel.figure, sub_x, sub_y, sub_w, sub_h, labels="inline")
            else:
                sub = _layout_flow(panel.figure, sub_x, sub_y, sub_w, sub_h)
            item.shapes.extend(sub.shapes)
            item.edges.extend(sub.edges)
            item.callouts.extend(sub.callouts)
            item.texts.extend(sub.texts)
        elif panel.items:
            item.texts.append(TextItem("bullets", sub_x, sub_y, sub_w, sub_h,
                                       bullets=panel.items))
    if fig.caption:
        item.texts.append(TextItem("caption", x, y + h - 0.4, w, 0.35, text=fig.caption))
    return item


# ---- array -----------------------------------------------------------

def _layout_array(fig: ArrayFigure, x: float, y: float, w: float, h: float) -> FigureItem:
    item = FigureItem(x=x, y=y, w=w, h=h)
    cap_h = 0.45 if fig.caption else 0.0
    gw, gh = w * 0.72, h - cap_h - 0.2
    gx = x + (w - gw) / 2 - 0.8            # leave right space for callout
    gy = y + 0.1
    cell_gap = 0.12
    cw = (gw - cell_gap * (fig.cols - 1)) / fig.cols
    ch = (gh - cell_gap * (fig.rows - 1)) / fig.rows
    s = min(cw, ch)                         # square-ish cells
    total_w = s * fig.cols + cell_gap * (fig.cols - 1)
    total_h = s * fig.rows + cell_gap * (fig.rows - 1)
    gx = x + (w - total_w) / 2 - 0.6
    gy = y + (gh - total_h) / 2 + 0.1
    for r in range(fig.rows):
        for c in range(fig.cols):
            item.shapes.append(RectShape(gx + c * (s + cell_gap), gy + r * (s + cell_gap),
                                         s, s, material=fig.material, rx=min(0.05, s * 0.2)))
    item.callouts.append(Callout(text=fig.cell_label,
                                 tx=gx + total_w, ty=gy + s / 2,
                                 lx=gx + total_w + 0.5, ly=gy + s / 2))
    if fig.caption:
        item.texts.append(TextItem("caption", x, y + h - 0.4, w, 0.35, text=fig.caption))
    return item


# ---- photonic (planar, in-plane optical path) ------------------------

_PHOTONIC_MATERIAL = {
    "laser": "light", "photodiode": "device", "chip": "silicon",
    "passive": "metal", "modulator": "device", "generic": "silicon",
}


def _h_arrow_poly(x1: float, x2: float, cy: float, material: str = "optical",
                  thick: float = 0.07, head_l: float = 0.28,
                  head_h: float = 0.17) -> PolyShape:
    """Right- or left-pointing horizontal arrow as a filled polygon, so it can
    be drawn ON TOP of the waveguide (edges always render beneath shapes)."""
    if x2 >= x1:
        tip, base = x2, x2 - head_l
    else:
        tip, base = x2, x2 + head_l
    pts = [
        (x1, cy - thick), (base, cy - thick), (base, cy - head_h),
        (tip, cy), (base, cy + head_h), (base, cy + thick), (x1, cy + thick),
    ]
    return PolyShape(pts, material)


def _layout_photonic(fig: PhotonicFigure, x: float, y: float,
                     w: float, h: float) -> FigureItem:
    # GRAPH form (branching / rings / fiber / driving electronics) vs the
    # simple LINEAR row form.
    if fig.nodes:
        return _layout_photonic_graph(fig, x, y, w, h)
    return _layout_photonic_linear(fig, x, y, w, h)


def _layout_photonic_linear(fig: PhotonicFigure, x: float, y: float,
                            w: float, h: float) -> FigureItem:
    item = FigureItem(x=x, y=y, w=w, h=h)
    comps = fig.components
    n = len(comps)
    if n == 0:
        return item
    cap_h = 0.45 if fig.caption else 0.0
    right_label = 2.35                       # reserve for material callouts
    band_x = x
    band_w = max(3.0, w - right_label)
    avail_h = h - cap_h
    inline = fig.waveguide_placement == "inline"

    # size bands, then center the whole assembly vertically. surface: parts sit
    # ABOVE a separate waveguide strip; inline: parts sit directly on the
    # substrate and the waveguide runs THROUGH their level (behind them).
    sub_h = min(1.05, avail_h * 0.22)
    comp_h = min(1.9, avail_h * (0.46 if inline else 0.42))
    strip_h = min(0.44, avail_h * 0.11)      # surface-mode waveguide strip
    assembly_h = comp_h + sub_h + (0.0 if inline else strip_h)
    top_pad = max(0.1, (avail_h - assembly_h) / 2)
    comp_y = y + top_pad
    if inline:
        sub_y = comp_y + comp_h              # parts directly on the substrate
    else:
        wg_y = comp_y + comp_h               # waveguide strip on the surface
        sub_y = wg_y + strip_h               # substrate below the strip
    wg_inset = 0.3
    wg_x, wg_w = band_x + wg_inset, band_w - 2 * wg_inset

    # component x-spans (widths by relative footprint), computed up front so the
    # waveguide can be sized/placed relative to them
    gap = 0.28
    tot = sum(c.width_frac for c in comps) or float(n)
    inner_w = wg_w - gap * (n - 1)
    xspan: dict[int, tuple[float, float]] = {}
    cx = wg_x
    for i, c in enumerate(comps):
        cw = inner_w * (c.width_frac / tot)
        xspan[i] = (cx, cx + cw)
        cx += cw + gap

    # glass substrate + optional Cu routing/pad skin on its top face
    item.shapes.append(RectShape(band_x, sub_y, band_w, sub_h,
                                 material=fig.substrate, rx=0.04))
    if fig.routing:
        skin = min(0.14, sub_h * 0.28)
        item.shapes.append(RectShape(band_x, sub_y, band_w, skin, material="copper"))

    # waveguide + the level the optical path travels at
    if inline:
        wg_bar_h = min(0.6, comp_h * 0.42)
        wg_bar_y = comp_y + comp_h / 2 - wg_bar_h / 2
        wlo, whi = xspan[0][0], xspan[n - 1][1]
        item.shapes.append(RectShape(wlo, wg_bar_y, whi - wlo, wg_bar_h,
                                     material=fig.waveguide_material, rx=0.03))
        y_opt = comp_y + comp_h / 2
        wg_target = (whi, y_opt)
    else:
        item.shapes.append(RectShape(wg_x, wg_y, wg_w, strip_h,
                                     material=fig.waveguide_material, rx=0.03))
        y_opt = wg_y + strip_h / 2
        wg_target = (wg_x + wg_w, y_opt)

    # in-plane optical path arrow (distinct 'optical' color). surface: below the
    # parts, fully visible -> draw AFTER parts. inline: at part level -> draw
    # BEFORE parts so it shows only in the gaps (light runs behind the chips).
    emit = next((i for i, c in enumerate(comps) if c.emits), None)
    if emit is None:
        emit = next((i for i, c in enumerate(comps) if c.role == "laser"), None)
    det = next((i for i, c in enumerate(comps) if c.detects), None)
    if det is None:
        det = next((i for i, c in enumerate(comps) if c.role == "photodiode"), None)
    arrow = None
    if emit is not None and det is not None and emit != det:
        (el, er), (dl, dr) = xspan[emit], xspan[det]
        if er <= dl:                          # emitter left of detector
            arrow = _h_arrow_poly(er + 0.04, dl - 0.02, y_opt)
        else:
            arrow = _h_arrow_poly(el - 0.04, dr + 0.02, y_opt)
        if fig.optical_label:
            lo, hi = sorted([xspan[emit][0], xspan[det][1]])
            oy = (comp_y - 0.3) if inline else (wg_y + strip_h + 0.02)
            item.texts.append(TextItem("caption", lo, max(y, oy),
                                       hi - lo, 0.3, text=fig.optical_label))

    if inline and arrow is not None:
        item.shapes.append(arrow)             # behind parts

    # components
    for i, c in enumerate(comps):
        cxs, cxe = xspan[i]
        mat = _PHOTONIC_MATERIAL.get(c.role, "silicon")
        item.shapes.append(RectShape(cxs, comp_y, cxe - cxs, comp_h, material=mat,
                                     rx=0.06, inner_label=c.label, label_size=14))

    if not inline and arrow is not None:
        item.shapes.append(arrow)             # on top of the strip

    # material callouts on the right
    lx = band_x + band_w + 0.45
    item.callouts.append(Callout(text=fig.waveguide_label,
                                 tx=wg_target[0], ty=wg_target[1],
                                 lx=lx, ly=wg_target[1]))
    item.callouts.append(Callout(text=fig.substrate_label,
                                 tx=band_x + band_w, ty=sub_y + sub_h / 2,
                                 lx=lx, ly=sub_y + sub_h / 2))
    if fig.caption:
        item.texts.append(TextItem("caption", x, y + h - 0.38, w, 0.33,
                                   text=fig.caption))
    return item


# ---- photonic GRAPH (branching / rings / fiber / electronics) --------

# role -> (material, glyph_type)
_PH_STYLE = {
    "laser":           ("light", "box"),
    "fiber":           ("gray", "fiber"),
    "grating_coupler": ("oxide", "grating"),
    "edge_coupler":    ("oxide", "taper"),
    "splitter":        ("polymer", "tri"),
    "combiner":        ("polymer", "tri_l"),
    "mzm":             ("device", "mzm"),
    "modulator":       ("device", "box"),
    "ring_mod":        ("device", "ring"),
    "mux":             ("dielectric", "awg"),
    "demux":           ("dielectric", "awg"),
    "photodiode":      ("device", "box"),
    "tia":             ("metal", "box"),
    "driver":          ("metal", "box"),
    "eic":             ("dark", "box"),
    "heater":          ("copper", "box"),
    "chip":            ("silicon", "box"),
    "passive":         ("metal", "box"),
    "generic":         ("gray", "box"),
}
_PH_ELECTRONIC = {"tia", "driver", "eic", "heater"}


def _rect_poly(xa: float, xb: float, yc: float, t: float,
               material: str) -> PolyShape:
    return PolyShape([(xa, yc - t), (xb, yc - t), (xb, yc + t), (xa, yc + t)],
                     material)


def _vrect_poly(xc: float, ya: float, yb: float, t: float,
                material: str) -> PolyShape:
    return PolyShape([(xc - t, ya), (xc + t, ya), (xc + t, yb), (xc - t, yb)],
                     material)


def _rail(x1: float, y1: float, x2: float, y2: float, material: str,
          t: float = 0.045) -> list:
    """Elbow waveguide/wire as thin filled rects (renderer-agnostic)."""
    if abs(y1 - y2) < 0.05:
        return [_rect_poly(x1, x2, (y1 + y2) / 2, t, material)]
    xm = (x1 + x2) / 2
    return [_rect_poly(x1, xm + (t if x2 >= x1 else -t), y1, t, material),
            _vrect_poly(xm, y1, y2, t, material),
            _rect_poly(xm - (t if x2 >= x1 else -t), x2, y2, t, material)]


def _tip(x: float, y: float, right: bool, material: str = "optical",
         l: float = 0.17, hh: float = 0.11) -> PolyShape:
    s = 1.0 if right else -1.0
    return PolyShape([(x - s * l, y - hh), (x, y), (x - s * l, y + hh)], material)


def _photonic_glyph(role: str, cx: float, cy: float, w: float, h: float,
                    label: str) -> tuple[list, list]:
    """Return (shapes, label_texts) for one node centered at (cx, cy)."""
    mat, gt = _PH_STYLE.get(role, ("gray", "box"))
    x0, y0 = cx - w / 2, cy - h / 2
    shapes: list = []
    labels: list = []

    def under(extra_w: float = 0.4):
        labels.append(TextItem("caption", x0 - extra_w / 2, y0 + h + 0.02,
                               w + extra_w, 0.32, text=label))

    if gt == "box":
        shapes.append(RectShape(x0, y0, w, h, material=mat, rx=0.06,
                                inner_label=label, label_size=13))
    elif gt == "grating":
        shapes.append(RectShape(x0, y0, w, h, material="oxide", rx=0.03))
        nb = 6
        for i in range(nb):
            bx = x0 + w * (i + 0.5) / nb - w / (4 * nb)
            shapes.append(RectShape(bx, y0 + h * 0.15, w / (2 * nb), h * 0.7,
                                    material="metal"))
        under()
    elif gt == "taper":
        shapes.append(PolyShape([(x0, cy - h * 0.42), (x0 + w, cy - h * 0.12),
                                 (x0 + w, cy + h * 0.12), (x0, cy + h * 0.42)], mat))
        under()
    elif gt in ("tri", "tri_l"):
        if gt == "tri":
            shapes.append(PolyShape([(x0, cy - h * 0.42), (x0 + w, cy),
                                     (x0, cy + h * 0.42)], mat))
        else:
            shapes.append(PolyShape([(x0 + w, cy - h * 0.42), (x0, cy),
                                     (x0 + w, cy + h * 0.42)], mat))
        under()
    elif gt == "ring":
        r = min(w, h) * 0.46
        shapes.append(CircleShape(cx, cy, r, material=mat))
        shapes.append(CircleShape(cx, cy, r * 0.52, material="white"))
        under()
    elif gt == "awg":
        shapes.append(PolyShape([(x0, cy - h * 0.46), (x0 + w, cy - h * 0.24),
                                 (x0 + w, cy + h * 0.24), (x0, cy + h * 0.46)], mat))
        under()
    elif gt == "fiber":
        fh = h * 0.3
        shapes.append(RectShape(x0 - 0.15, cy - fh / 2, w + 0.15, fh,
                                material="gray", rx=fh / 2))
        under()
    elif gt == "mzm":
        shapes.append(RectShape(x0, y0, w, h, material=mat, rx=0.06))
        for dy in (-h * 0.17, h * 0.17):
            shapes.append(_rect_poly(x0 + w * 0.14, x0 + w * 0.86, cy + dy,
                                     0.028, "white"))
        under()
    else:
        shapes.append(RectShape(x0, y0, w, h, material=mat, rx=0.06,
                                inner_label=label, label_size=13))
    return shapes, labels


def _longest_path_ranks(ids: set, edges: list) -> dict:
    from collections import defaultdict, deque
    succ = defaultdict(list)
    indeg = {i: 0 for i in ids}
    for s, d in edges:
        if s in ids and d in ids and s != d:
            succ[s].append(d)
            indeg[d] += 1
    rank = {i: 0 for i in ids}
    q = deque([i for i in ids if indeg[i] == 0])
    left = dict(indeg)
    while q:
        u = q.popleft()
        for v in succ[u]:
            rank[v] = max(rank[v], rank[u] + 1)
            left[v] -= 1
            if left[v] == 0:
                q.append(v)
    return rank


def _layout_photonic_graph(fig: PhotonicFigure, x: float, y: float,
                           w: float, h: float) -> FigureItem:
    item = FigureItem(x=x, y=y, w=w, h=h)
    nodes = fig.nodes
    if not nodes:
        return item
    id2n = {n.id: n for n in nodes}
    optical = [n for n in nodes if n.role not in _PH_ELECTRONIC]
    elec = [n for n in nodes if n.role in _PH_ELECTRONIC]
    opt_ids = {n.id for n in optical}

    cap_h = 0.6 if fig.caption else 0.0    # room for a 2-line caption
    avail_h = h - cap_h
    band_x = x + 0.2
    band_w = w - 0.4

    # substrate strip at the bottom
    sub_h = min(0.55, avail_h * 0.13)
    sub_y = y + avail_h - sub_h
    item.shapes.append(RectShape(band_x, sub_y, band_w, sub_h,
                                 material=fig.substrate, rx=0.04,
                                 inner_label=fig.substrate_label, label_size=12))

    # vertical bands: optical (upper) + electronic (just above substrate)
    top = y + 0.15
    elec_h = 1.05 if elec else 0.0
    opt_bot = sub_y - 0.2 - elec_h
    opt_top = top

    # ---- rank & place optical nodes ----
    opt_edges = [(l.src, l.dst) for l in fig.links
                 if l.src in opt_ids and l.dst in opt_ids]
    rank = _longest_path_ranks(opt_ids, opt_edges)
    ranks = sorted(set(rank[n.id] for n in optical)) or [0]
    by_rank: dict[int, list] = {r: [] for r in ranks}
    for n in optical:                                # keep insertion order
        by_rank[rank[n.id]].append(n.id)

    ncol = len(ranks)
    col_w = band_w / ncol
    node_w = min(1.7, col_w * 0.78)
    maxrow = max(len(v) for v in by_rank.values())
    opt_h = max(1.0, opt_bot - opt_top)
    row_h = min(1.4, opt_h / max(1, maxrow))
    # reserve room under each node for below-glyph labels so rows never collide
    node_h = min(0.95, max(0.6, row_h - 0.42))

    pos: dict[str, tuple[float, float]] = {}
    for j, r in enumerate(ranks):
        cx = band_x + col_w * (j + 0.5)
        col = by_rank[r]
        total = len(col) * row_h
        sy = opt_top + (opt_h - total) / 2
        for i, nid in enumerate(col):
            cy = sy + i * row_h + row_h / 2
            pos[nid] = (cx, cy)

    # ---- place electronic nodes in the lower band under their neighbors ----
    elec_y = (opt_bot + sub_y) / 2 if elec else 0.0
    if elec:
        targets = []
        for n in elec:
            xs = [pos[o][0] for o in
                  [l.dst for l in fig.links if l.src == n.id]
                  + [l.src for l in fig.links if l.dst == n.id] if o in pos]
            targets.append([n.id, sum(xs) / len(xs) if xs else band_x + band_w / 2])
        targets.sort(key=lambda t: t[1])
        xs = [t[1] for t in targets]
        min_gap = node_w + 0.25
        for k in range(1, len(xs)):               # de-overlap left-to-right
            xs[k] = max(xs[k], xs[k - 1] + min_gap)
        lo_lim, hi_lim = band_x + node_w / 2, band_x + band_w - node_w / 2
        if xs[-1] > hi_lim:                        # shift whole group left to fit
            xs = [xx - (xs[-1] - hi_lim) for xx in xs]
        if xs[0] < lo_lim:
            xs = [xx + (lo_lim - xs[0]) for xx in xs]
            if len(xs) > 1 and xs[-1] > hi_lim:   # still too wide -> spread evenly
                span = hi_lim - lo_lim
                xs = [lo_lim + span * i / (len(xs) - 1) for i in range(len(xs))]
        for (nid, _), ex in zip(targets, xs):
            pos[nid] = (ex, elec_y)

    # ---- draw links (before nodes so rails show in the gaps) ----
    for l in fig.links:
        if l.src not in pos or l.dst not in pos:
            continue
        sx, syc = pos[l.src]
        dx, dyc = pos[l.dst]
        right = dx >= sx
        x1 = sx + (node_w / 2 if right else -node_w / 2)
        x2 = dx - (node_w / 2 if right else -node_w / 2)
        if l.kind == "electrical":
            item.edges.append(EdgeShape(x1, syc, x2, dyc))
        else:
            for p in _rail(x1, syc, x2, dyc, fig.waveguide_material):
                item.shapes.append(p)
            item.shapes.append(_tip(x2, dyc, right))

    # ---- draw nodes ----
    node_labels = []
    for n in nodes:
        if n.id not in pos:
            continue
        cx, cy = pos[n.id]
        sh, lb = _photonic_glyph(n.role, cx, cy, node_w, node_h, n.label)
        item.shapes.extend(sh)
        node_labels.extend(lb)
    item.texts.extend(node_labels)

    if fig.caption:
        item.texts.append(TextItem("caption", x, y + h - 0.52, w, 0.5,
                                   text=fig.caption))
    return item


# ================ general infographic layouts (WP7) ================

def _grid(x, y, w, h, n, cols=None, gap=0.25):
    if cols is None:
        cols = n if n <= 3 else math.ceil(n / 2)
    cols = max(1, cols)
    rows = math.ceil(n / cols)
    cw = (w - gap * (cols - 1)) / cols
    ch = (h - gap * (rows - 1)) / rows
    return [(x + (i % cols) * (cw + gap), y + (i // cols) * (ch + gap), cw, ch)
            for i in range(n)]


def _seg_poly(x1, y1, x2, y2, t, material):
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L * t, dx / L * t
    return PolyShape([(x1 + nx, y1 + ny), (x2 + nx, y2 + ny),
                      (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)], material)


def _layout_timeline(fig: TimelineFigure, x, y, w, h) -> FigureItem:
    item = FigureItem(x=x, y=y, w=w, h=h)
    ms = fig.milestones
    n = len(ms)
    cap_h = 0.4 if fig.caption else 0.0
    ph = fig.phases
    prow = 0.36
    phase_band = (prow * len(ph) + 0.15) if ph else 0.0
    avail = h - cap_h
    axis_y = y + phase_band + (avail - phase_band) * 0.5
    mx0, mx1 = x + 0.9, x + w - 0.9
    xs = [mx0 + (mx1 - mx0) * (i / max(1, n - 1)) for i in range(n)]
    slot = (mx1 - mx0) / max(1, n - 1)
    item.shapes.append(RectShape(mx0 - 0.3, axis_y - 0.03, (mx1 - mx0) + 0.6, 0.06,
                                 material="track"))
    for pi, p in enumerate(ph):
        s = max(0, min(n - 1, p.start))
        e = max(0, min(n - 1, p.end))
        if e < s:
            s, e = e, s
        item.shapes.append(RectShape(xs[s], y + 0.1 + pi * prow, max(0.4, xs[e] - xs[s]),
                                     prow - 0.1, material=f"accent{(pi % 6) + 1}",
                                     rx=0.06, inner_label=p.label, label_size=12))
    for i, m in enumerate(ms):
        cxp = xs[i]
        item.shapes.append(CircleShape(cxp, axis_y, 0.1 if m.emphasis else 0.07,
                                       material="accent3" if m.emphasis else "accent1"))
        lw = min(2.0, slot * 1.2)
        if i % 2 == 0:                                   # label above
            if m.date_label:
                item.texts.append(TextItem("caption", cxp - lw / 2, axis_y - 0.34, lw, 0.24,
                                           text=m.date_label))
            item.texts.append(TextItem("panel_title", cxp - lw / 2, axis_y - 0.76, lw, 0.42,
                                       text=m.label))
        else:                                            # label below
            if m.date_label:
                item.texts.append(TextItem("caption", cxp - lw / 2, axis_y + 0.14, lw, 0.24,
                                           text=m.date_label))
            item.texts.append(TextItem("panel_title", cxp - lw / 2, axis_y + 0.40, lw, 0.42,
                                       text=m.label))
    if fig.caption:
        item.texts.append(TextItem("caption", x, y + h - 0.36, w, 0.32, text=fig.caption))
    return item


def _layout_kpi(fig: KpiFigure, x, y, w, h) -> FigureItem:
    item = FigureItem(x=x, y=y, w=w, h=h)
    items = fig.items
    n = len(items)
    cap_h = 0.4 if fig.caption else 0.0
    cols = n if n <= 3 else math.ceil(n / 2)
    cells = _grid(x, y, w, h - cap_h, n, cols=cols, gap=0.3)
    tone_bg = {"good": "good", "bad": "bad", "neutral": "neutral"}
    for (cx, cy, cw, ch), it in zip(cells, items):
        val_h = ch * 0.62
        item.shapes.append(RectShape(cx, cy, cw, val_h, material=tone_bg.get(it.tone, "neutral"),
                                     rx=0.12, inner_label=it.value, label_size=30))
        lab = it.label + (f"    {it.delta}" if it.delta else "")
        item.texts.append(TextItem("panel_title", cx, cy + val_h + 0.05, cw,
                                   ch - val_h - 0.05, text=lab))
    if fig.caption:
        item.texts.append(TextItem("caption", x, y + h - 0.36, w, 0.32, text=fig.caption))
    return item


def _layout_table(fig: TableFigure, x, y, w, h) -> FigureItem:
    item = FigureItem(x=x, y=y, w=w, h=h)
    cap_h = 0.4 if fig.caption else 0.0
    cols = fig.columns
    ncol = len(cols)
    body = fig.rows
    nrow = len(body) + 1
    cw = w / ncol
    chh = (h - cap_h) / nrow
    emc = fig.emphasis_col
    for c, name in enumerate(cols):
        item.shapes.append(RectShape(x + c * cw, y, cw, chh, material="accent1",
                                     inner_label=name, label_size=13))
    for r, row in enumerate(body):
        for c in range(ncol):
            txt = row[c] if c < len(row) else ""
            mat = "accent2" if (emc is not None and c == emc) else "white"
            item.shapes.append(RectShape(x + c * cw, y + (r + 1) * chh, cw, chh,
                                         material=mat, inner_label=txt, label_size=12))
    if fig.caption:
        item.texts.append(TextItem("caption", x, y + h - 0.36, w, 0.32, text=fig.caption))
    return item


def _layout_matrix(fig: MatrixFigure, x, y, w, h) -> FigureItem:
    item = FigureItem(x=x, y=y, w=w, h=h)
    cap_h = 0.45 if fig.caption else 0.0
    lab = 0.5
    side = max(2.0, min(w - 2 * lab, (h - cap_h) - 2 * lab))
    ox = x + (w - side) / 2
    oy = y + lab
    half = side / 2
    gap = 0.06
    q_pos = [(ox, oy), (ox + half, oy), (ox, oy + half), (ox + half, oy + half)]
    tints = ["accent2", "accent1", "accent5", "accent3"]
    for (qx, qy), quad, tint in zip(q_pos, fig.quadrants, tints):
        item.shapes.append(RectShape(qx + gap, qy + gap, half - 2 * gap, half - 2 * gap,
                                     material=tint, rx=0.08))
        item.texts.append(TextItem("panel_title", qx + gap + 0.12, qy + gap + 0.08,
                                   half - 2 * gap - 0.24, 0.36, text=quad.title))
        if quad.items:
            item.texts.append(TextItem("bullets", qx + gap + 0.16, qy + gap + 0.52,
                                       half - 2 * gap - 0.3, half - 0.72, bullets=quad.items))
    item.texts.append(TextItem("caption", ox, oy + side + 0.06, side, 0.3,
                               text=f"{fig.x_low}   ←  X  →   {fig.x_high}"))
    item.texts.append(TextItem("caption", ox - lab + 0.02, oy - 0.02, 1.7, 0.26,
                               text=f"↑ {fig.y_high}"))
    item.texts.append(TextItem("caption", ox - lab + 0.02, oy + side - 0.26, 1.7, 0.26,
                               text=f"↓ {fig.y_low}"))
    if fig.caption:
        item.texts.append(TextItem("caption", x, y + h - 0.38, w, 0.32, text=fig.caption))
    return item


def _layout_chart(fig: ChartFigure, x, y, w, h) -> FigureItem:
    item = FigureItem(x=x, y=y, w=w, h=h)
    cap_h = 0.4 if fig.caption else 0.0
    legend_h = 0.34 if len(fig.series) > 1 else 0.0
    pad_l, pad_b, pad_r = 0.75, 0.5, 0.3
    pad_t = 0.32 + legend_h
    px, pw = x + pad_l, w - pad_l - pad_r
    py, phh = y + pad_t, (h - cap_h) - pad_t - pad_b
    cats = fig.categories
    ncat = len(cats)
    allv = [v for s in fig.series for v in s.values] + [0.0]
    vmax, vmin = max(allv), min(allv)
    lo = min(0.0, vmin)
    span = (vmax - lo) or 1.0

    def vy(val):
        return py + phh - (val - lo) / span * phh

    for g in range(5):                                   # horizontal grid lines
        gy = py + phh * g / 4
        item.shapes.append(RectShape(px, gy - 0.005, pw, 0.01, material="grid"))
    item.shapes.append(RectShape(px - 0.02, py, 0.02, phh, material="track"))
    item.shapes.append(RectShape(px, vy(lo) - 0.01, pw, 0.02, material="track"))
    slot = pw / ncat
    series = fig.series
    ns = len(series)
    if fig.chart_type == "bar":
        gp = slot * 0.22
        barw = (slot - gp) / ns
        for ci in range(ncat):
            for si, s in enumerate(series):
                val = s.values[ci] if ci < len(s.values) else 0.0
                bx = px + ci * slot + gp / 2 + si * barw
                top, base = vy(val), vy(0)
                item.shapes.append(RectShape(bx, min(top, base), barw * 0.9,
                                             max(0.02, abs(base - top)),
                                             material=f"accent{(si % 6) + 1}", rx=0.02))
                if ns == 1:
                    item.texts.append(TextItem("caption", bx - 0.2, top - 0.26,
                                               barw * 0.9 + 0.4, 0.24, text=_num(val)))
    else:
        for si, s in enumerate(series):
            pts = [(px + ci * slot + slot / 2,
                    vy(s.values[ci] if ci < len(s.values) else 0.0)) for ci in range(ncat)]
            for a, b in zip(pts, pts[1:]):
                item.shapes.append(_seg_poly(a[0], a[1], b[0], b[1], 0.028,
                                             f"accent{(si % 6) + 1}"))
            for pxx, pyy in pts:
                item.shapes.append(CircleShape(pxx, pyy, 0.05,
                                               material=f"accent{(si % 6) + 1}"))
    for ci, c in enumerate(cats):
        item.texts.append(TextItem("caption", px + ci * slot, py + phh + 0.05, slot, 0.3,
                                   text=c))
    if fig.y_label:
        item.texts.append(TextItem("caption", x, y + 0.02, 1.3, 0.28, text=fig.y_label))
    if legend_h:
        for si, s in enumerate(series):
            lx = px + si * 2.4
            item.shapes.append(RectShape(lx, y + 0.06, 0.24, 0.18,
                                         material=f"accent{(si % 6) + 1}", rx=0.03))
            item.texts.append(TextItem("caption", lx + 0.32, y + 0.03, 2.0, 0.24, text=s.name))
    if fig.caption:
        item.texts.append(TextItem("caption", x, y + h - 0.34, w, 0.3, text=fig.caption))
    return item


def _num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


def _layout_tree(fig: TreeFigure, x, y, w, h) -> FigureItem:
    item = FigureItem(x=x, y=y, w=w, h=h)
    nodes = fig.nodes
    byid = {n.id: n for n in nodes}
    children: dict[str, list] = {}
    roots = []
    for n in nodes:
        if n.parent and n.parent in byid and n.parent != n.id:
            children.setdefault(n.parent, []).append(n.id)
        else:
            roots.append(n.id)
    depth: dict[str, int] = {}

    def setd(nid, d, seen):
        if nid in seen:
            return
        seen.add(nid)
        depth[nid] = d
        for c in children.get(nid, []):
            setd(c, d + 1, seen)
    seen: set = set()
    for r in roots:
        setd(r, 0, seen)
    for n in nodes:                                      # orphans safety
        depth.setdefault(n.id, 0)
    maxd = max(depth.values()) if depth else 0
    leaf = [0]
    slot_of: dict[str, float] = {}

    def assign(nid, seen2):
        if nid in seen2:
            return leaf[0]
        seen2.add(nid)
        ch = children.get(nid, [])
        if not ch:
            xi = leaf[0] + 0.5
            leaf[0] += 1
            slot_of[nid] = xi
            return xi
        xs = [assign(c, seen2) for c in ch]
        slot_of[nid] = sum(xs) / len(xs)
        return slot_of[nid]
    s2: set = set()
    for r in roots:
        assign(r, s2)
    for n in nodes:                                      # any node missed (cycle)
        if n.id not in slot_of:
            slot_of[n.id] = leaf[0] + 0.5
            leaf[0] += 1
    nleaf = max(1, leaf[0])
    cap_h = 0.4 if fig.caption else 0.0
    band = (h - cap_h) / (maxd + 1)
    colw = w / nleaf
    nw = min(2.1, colw * 0.86)
    nh = min(0.78, band * 0.58)

    def cx(nid):
        return x + slot_of[nid] * colw

    def cy(d):
        return y + d * band + band / 2

    for n in nodes:                                      # connectors first
        if n.parent and n.parent in byid and n.parent != n.id:
            x1, y1 = cx(n.parent), cy(depth[n.parent]) + nh / 2
            x2, y2 = cx(n.id), cy(depth[n.id]) - nh / 2
            ym = (y1 + y2) / 2
            t = 0.017
            item.shapes.append(_vrect_poly(x1, y1, ym, t, "track"))
            item.shapes.append(_rect_poly(min(x1, x2), max(x1, x2), ym, t, "track"))
            item.shapes.append(_vrect_poly(x2, ym, y2, t, "track"))
    for n in nodes:
        d = depth[n.id]
        cxx, cyy = cx(n.id), cy(d)
        mat = "accent1" if d == 0 else ("accent5" if d == 1 else "neutral")
        item.shapes.append(RectShape(cxx - nw / 2, cyy - nh / 2, nw, nh, material=mat,
                                     rx=0.08, inner_label=n.label, label_size=12))
    if fig.caption:
        item.texts.append(TextItem("caption", x, y + h - 0.36, w, 0.32, text=fig.caption))
    return item


# ================ assembly (WP8 — parts positioned on a substrate) ========

_MOUNT_BUMP = {"solder": "round", "c4": "barrel", "cu_pillar": "pillar",
               "flipchip": "barrel"}


def _assembly_wire(item, x0, pw, part_top, land_y):
    """Gold wire-bond arcs from a part's top corners down to the surface it
    sits on (both sides), for a face-up wire-bonded die."""
    for side in (-1, 1):
        sx = x0 + (0.12 if side < 0 else pw - 0.12)
        ex = x0 + (-0.26 if side < 0 else pw + 0.26)
        sy = part_top + 0.02
        peak = min(sy, land_y) - 0.22
        cxm = (sx + ex) / 2
        tw, N = 0.026, 12
        top, bot = [], []
        for k in range(N + 1):
            u = k / N
            px = (1 - u) ** 2 * sx + 2 * (1 - u) * u * cxm + u ** 2 * ex
            py = (1 - u) ** 2 * sy + 2 * (1 - u) * u * peak + u ** 2 * land_y
            top.append((px, py))
            bot.append((px, py + tw))
        item.shapes.append(PolyShape(top + bot[::-1], "gold"))


def _draw_mount(item, p, x0, pw, part_bottom, parent_top):
    """Draw the interface in the gap under a part per its mount type."""
    gap = parent_top - part_bottom
    if p.mount in _MOUNT_BUMP:
        if p.mount == "flipchip":                 # underfill behind the bumps
            item.shapes.append(RectShape(x0 + 0.02, part_bottom, pw - 0.04, gap,
                                         material="underfill"))
        n = max(2, min(p.pad_count, 14))
        span_w = pw * 0.86
        sx0 = x0 + (pw - span_w) / 2
        step = span_w / (n - 1) if n > 1 else span_w
        r = min(gap * 0.42, step * 0.4)
        for i in range(n):
            cx = sx0 + (i * step if n > 1 else span_w / 2)
            item.shapes.extend(_ball_shapes(_MOUNT_BUMP[p.mount], cx, part_bottom,
                                            gap, r, step, n, "solder"))
    elif p.mount == "hybrid":
        item.shapes.append(_rect_poly(x0, x0 + pw, (part_bottom + parent_top) / 2,
                                      0.02, "bond_oxide"))
    elif p.mount == "die_attach":
        item.shapes.append(RectShape(x0, parent_top - gap, pw, gap, material="dielectric"))
    elif p.mount == "wirebond":                   # thin die-attach; arcs drawn later
        item.shapes.append(RectShape(x0 + pw * 0.1, parent_top - gap, pw * 0.8, gap,
                                     material="metal"))
    # stack / none / edge_couple: nothing under the part


def _assembly_glyph(item, glyph, x0, y0, w, h, material, label):
    """Dedicated assembly glyphs (WP9) — composed from existing primitives."""
    cx = x0 + w / 2
    if glyph == "connector":                      # low body + pin teeth on top
        bh = h * 0.55
        item.shapes.append(RectShape(x0, y0 + h - bh, w, bh, material=material, rx=0.02,
                                     inner_label=label, label_size=10))
        n = 5
        tw = w / (2 * n)
        for i in range(n):
            item.shapes.append(RectShape(x0 + w * (i + 0.5) / n - tw / 2,
                                         y0 + h - bh - h * 0.3, tw, h * 0.3, material=material))
    elif glyph == "flex_ribbon":                  # thin flexible band running off-board
        t = 0.06
        item.shapes.append(RectShape(x0 - 0.1, y0 + h / 2 - t, w + 0.3, 2 * t,
                                     material=material, rx=t))
        item.texts.append(TextItem("caption", x0 - 0.1, y0 + h / 2 + 0.1, w + 0.3, 0.2,
                                   text=label))
    elif glyph == "v_groove":                     # trapezoidal groove + fiber in it
        item.shapes.append(PolyShape([(x0, y0), (x0 + w, y0),
                                      (x0 + w * 0.62, y0 + h), (x0 + w * 0.38, y0 + h)], material))
        item.shapes.append(CircleShape(cx, y0 + h * 0.4, min(w, h) * 0.22, material="oxide"))
        item.texts.append(TextItem("caption", x0 - 0.1, y0 + h + 0.02, w + 0.2, 0.2, text=label))
    elif glyph == "dome_array":                   # microlens array
        n = max(3, int(w / 0.16))
        dw = w / n
        for i in range(n):
            item.shapes.append(_dome_poly(x0 + dw * (i + 0.5), y0 + h, dw * 0.46, h * 0.95,
                                          "glass", up=True))
        item.texts.append(TextItem("caption", x0, y0 + h + 0.02, w, 0.2, text=label))
    elif glyph == "bayer_row":                    # alternating color-filter cells
        n = max(4, int(w / 0.13))
        cw = w / n
        cols = ["accent6", "accent2", "accent1", "accent2"]
        for i in range(n):
            item.shapes.append(RectShape(x0 + i * cw, y0, cw, h, material=cols[i % 4]))
        item.texts.append(TextItem("caption", x0, y0 - 0.22, w, 0.2, text=label))
    elif glyph == "chips":                         # row of tiny passives
        n = max(3, int(w / 0.09))
        cw = w / (2 * n)
        for i in range(n):
            item.shapes.append(RectShape(x0 + w * (i + 0.5) / n - cw / 2, y0, cw, h,
                                         material=material))
        item.texts.append(TextItem("caption", x0 - 0.1, y0 + h + 0.02, w + 0.2, 0.2, text=label))
    else:
        item.shapes.append(RectShape(x0, y0, w, h, material=material, rx=0.06,
                                     inner_label=label, label_size=12))


def _layout_assembly(fig: AssemblyFigure, x, y, w, h) -> FigureItem:
    item = FigureItem(x=x, y=y, w=w, h=h)
    parts = fig.parts
    cap_h = 0.4 if fig.caption else 0.0
    avail = h - cap_h
    bx0, bx1 = x + 0.2, x + w - 0.2
    base_w = bx1 - bx0
    top_mounted = [p for p in parts if not p.buried and p.level >= 1 and p.side == "top"]
    bot_parts = [p for p in parts if not p.buried and p.side == "bottom"]
    maxlevel = max([p.level for p in top_mounted], default=1)
    base_h = min(1.0, avail * 0.2 if maxlevel <= 2 else avail * 0.14)
    bottom_space = 0.5 if (fig.bottom_balls or bot_parts) else 0.0
    mold_pad = 0.26 if fig.mold else 0.0
    # part height adapts to stack depth so a tall chip-on-chip stack always fits
    room = avail - base_h - bottom_space - mold_pad - 0.25
    mount_gap = 0.3 if maxlevel <= 2 else 0.18
    part_h0 = max(0.42, min(1.15, room / (maxlevel * 1.0) - mount_gap))
    assembly_h = mold_pad + maxlevel * (part_h0 + mount_gap) + base_h + bottom_space
    margin = max(0.08, (avail - assembly_h) / 2)     # center vertically
    base_bottom = y + avail - margin - bottom_space
    base_top = base_bottom - base_h

    if fig.base_layers:                           # multilayer substrate build-up
        tot = sum(l.t for l in fig.base_layers) or 1.0
        cyv = base_bottom
        for l in fig.base_layers:
            lh = base_h * (l.t / tot)
            ly = cyv - lh
            item.shapes.append(RectShape(bx0, ly, base_w, lh, material=l.material,
                                         inner_label=(l.label if lh > 0.24 else None),
                                         label_size=11))
            if l.vias:
                vxs = _ball_xs(bx0, base_w, 0.9, l.vias)
                vw = min(0.09, base_w / (l.vias * 3 + 1))
                for vx in vxs:
                    item.shapes.append(RectShape(vx - vw / 2, ly, vw, lh, material="copper"))
            cyv = ly
    else:
        item.shapes.append(RectShape(bx0, base_top, base_w, base_h,
                                     material=fig.base_material, rx=0.04,
                                     inner_label=fig.base_label, label_size=12))
    for p in parts:                               # buried channels near the top face
        if p.buried:
            cw = p.width_frac * base_w
            cx = bx0 + p.x_frac * base_w
            ch = min(0.2, base_h * 0.26)
            item.shapes.append(RectShape(cx - cw / 2, base_top + base_h * 0.14, cw, ch,
                                         material=p.material, rx=0.03))
    # package balls (BGA/LGA) under the substrate
    if fig.bottom_balls:
        n = max(2, min(fig.bottom_balls, 16))
        xs = _ball_xs(bx0, base_w, 0.94, n)
        step = (xs[1] - xs[0]) if n > 1 else base_w
        bt = min(0.42, bottom_space * 0.7)
        for cx in xs:
            item.shapes.extend(_ball_shapes("flat", cx, base_bottom, bt,
                                            min(bt * 0.55, step * 0.42), step, n, "solder"))
        if fig.bottom_ball_label:
            item.texts.append(TextItem("caption", bx0, base_bottom + bt + 0.02, base_w,
                                       0.24, text=fig.bottom_ball_label))
    # bottom-side discrete parts hang under the substrate
    for p in bot_parts:
        pw = p.width_frac * base_w
        cx = bx0 + p.x_frac * base_w
        ph = min(part_h0 * 0.7, bottom_space - 0.1)
        item.shapes.append(RectShape(cx - pw / 2, base_bottom + 0.06, pw, ph,
                                     material=p.material, rx=0.05,
                                     inner_label=p.label, label_size=11))

    # ---- top parts: compute boxes first (so mold can sit behind them) ----
    span = {"__base__": (bx0, bx1, base_top, base_bottom)}
    placed = []                                   # (part, x0, pw, top_y, part_bottom, parent_top)
    for lv in range(1, maxlevel + 1):
        for p in [q for q in top_mounted if q.level == lv]:
            parent = span.get(p.on) if p.on else span["__base__"]
            if parent is None:
                parent = span["__base__"]
            _, _, ptop, _ = parent
            cx = bx0 + p.x_frac * base_w
            pw = p.width_frac * base_w
            x0 = cx - pw / 2
            mgap = (0.3 if p.mount in _MOUNT_BUMP
                    else 0.08 if p.mount in ("die_attach", "hybrid", "wirebond")
                    else 0.0)
            part_bottom = ptop - mgap
            top_y = part_bottom - part_h0 * min(p.t, 2.0)
            span[p.id] = (x0, x0 + pw, top_y, part_bottom)
            placed.append((p, x0, pw, top_y, part_bottom, ptop))

    if fig.mold and placed:                       # EMC cap behind the top parts
        mtop = min(pl[3] for pl in placed) - 0.16
        # label sits in the thin mold strip ABOVE the parts (light text on dark EMC)
        item.shapes.append(RectShape(bx0, mtop, base_w, 0.2, material="mold",
                                     inner_label=fig.mold_label, label_size=11))
        item.shapes.append(RectShape(bx0, mtop + 0.2, base_w, base_top - mtop - 0.2,
                                     material="mold", rx=0.0))

    wires = []
    shields = []
    for p, x0, pw, top_y, part_bottom, ptop in placed:
        if p.glyph == "shield_can":               # drawn last as an overlay lid
            shields.append(p)
            continue
        _draw_mount(item, p, x0, pw, part_bottom, ptop)
        if p.glyph:
            _assembly_glyph(item, p.glyph, x0, top_y, pw, part_bottom - top_y,
                            p.material, p.label)
        else:
            item.shapes.append(RectShape(x0, top_y, pw, part_bottom - top_y,
                                         material=p.material, rx=0.06,
                                         inner_label=p.label, label_size=12))
        if p.mount == "wirebond":
            wires.append((x0, pw, top_y, ptop))
    for x0, pw, top_y, land in wires:
        _assembly_wire(item, x0, pw, top_y, land)
    for p in shields:                             # ㄷ-shaped shield-can lid + walls
        covered = [span[c] for c in p.covers if c in span] or \
            [b for cid, b in span.items() if cid not in ("__base__",)
             and cid != p.id]
        if not covered:
            continue
        cx0 = min(b[0] for b in covered) - 0.12
        cx1 = max(b[1] for b in covered) + 0.12
        ctop = min(b[2] for b in covered) - 0.16
        wall = 0.05
        item.shapes.append(RectShape(cx0, ctop, cx1 - cx0, 0.13, material="leadframe",
                                     inner_label=p.label, label_size=10))
        item.shapes.append(RectShape(cx0, ctop, wall, base_top - ctop, material="leadframe"))
        item.shapes.append(RectShape(cx1 - wall, ctop, wall, base_top - ctop,
                                     material="leadframe"))

    for b in fig.beams:                           # in-plane optical beams
        s, d = span.get(b.src), span.get(b.dst)
        if not s or not d:
            continue
        (sx0, sx1, stop, sbot), (dx0, dx1, dtop, dbot) = s, d
        cy = (stop + sbot) / 2
        if sx1 <= dx0:
            item.shapes.append(_h_arrow_poly(sx1 + 0.03, dx0 - 0.02, cy))
        elif dx1 <= sx0:
            item.shapes.append(_h_arrow_poly(sx0 - 0.03, dx1 + 0.02, cy))
        if b.label:
            lo, hi = sorted([sx0, sx1, dx0, dx1])[0], sorted([sx0, sx1, dx0, dx1])[-1]
            item.texts.append(TextItem("caption", lo, cy - 0.32, hi - lo, 0.24,
                                       text=b.label))
    if fig.caption:
        item.texts.append(TextItem("caption", x, y + h - 0.34, w, 0.3, text=fig.caption))
    return item


# ---- dispatch --------------------------------------------------------

def layout_figure(fig: Figure, x: float, y: float, w: float, h: float) -> FigureItem:
    if isinstance(fig, StackFigure):
        return _layout_stack(fig, x, y, w, h)
    if isinstance(fig, CompareFigure):
        return _layout_compare(fig, x, y, w, h)
    if isinstance(fig, ArrayFigure):
        return _layout_array(fig, x, y, w, h)
    if isinstance(fig, PhotonicFigure):
        return _layout_photonic(fig, x, y, w, h)
    if isinstance(fig, TimelineFigure):
        return _layout_timeline(fig, x, y, w, h)
    if isinstance(fig, KpiFigure):
        return _layout_kpi(fig, x, y, w, h)
    if isinstance(fig, TableFigure):
        return _layout_table(fig, x, y, w, h)
    if isinstance(fig, MatrixFigure):
        return _layout_matrix(fig, x, y, w, h)
    if isinstance(fig, ChartFigure):
        return _layout_chart(fig, x, y, w, h)
    if isinstance(fig, TreeFigure):
        return _layout_tree(fig, x, y, w, h)
    if isinstance(fig, AssemblyFigure):
        return _layout_assembly(fig, x, y, w, h)
    return _layout_flow(fig, x, y, w, h)


def layout_slide(slide: Slide) -> list[DrawItem]:
    items: list[DrawItem] = []
    content_w = SLIDE_W - 2 * MARGIN_X

    if slide.layout_type == "title":
        items.append(TextItem("title", MARGIN_X, 2.6, content_w, 1.6, text=slide.title))
        if slide.subtitle:
            items.append(TextItem("subtitle", MARGIN_X, 4.3, content_w, 1.0, text=slide.subtitle))
        return items

    items.append(TextItem("title", MARGIN_X, TITLE_Y, content_w, TITLE_H, text=slide.title))
    body_h = SLIDE_H - BODY_TOP - 0.45

    if slide.layout_type == "figure" and slide.figure:
        items.append(layout_figure(slide.figure, MARGIN_X, BODY_TOP, content_w, body_h))
    else:
        items.append(TextItem("bullets", MARGIN_X, BODY_TOP, content_w, body_h,
                              bullets=slide.bullets or []))
    return items
