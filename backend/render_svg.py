"""Render a Slide to SVG for the browser live preview.

Consumes the same DrawItems as the pptx exporter (inches -> px at 96dpi).
Text wrapping is delegated to the browser via <foreignObject>.
"""
from __future__ import annotations

from html import escape

from layout import (
    SLIDE_W, SLIDE_H, layout_slide,
    TextItem, FigureItem, RectShape, PolyShape, CircleShape, EdgeShape, Callout,
)
from models import Slide
from palette import material_colors, DARK_ROLES

PX = 96.0
W = int(SLIDE_W * PX)
H = int(SLIDE_H * PX)

NAVY = "#1f2a44"
ACCENT = "#2f6fed"
GRAY = "#5b6472"
LEADER = "#8a93a0"

_TEXT_STYLE = {
    "title": f"font:700 34px system-ui,sans-serif;color:{NAVY};",
    "subtitle": f"font:400 22px system-ui,sans-serif;color:{GRAY};",
    "caption": f"font:italic 400 16px system-ui,sans-serif;color:{GRAY};text-align:center;",
    "body": f"font:400 22px system-ui,sans-serif;color:{NAVY};",
    "bullets": f"font:400 21px system-ui,sans-serif;color:{NAVY};",
    "panel_title": f"font:600 19px system-ui,sans-serif;color:{NAVY};text-align:center;",
}


def _fo(x, y, w, h, inner, style, valign="flex-start"):
    return (
        f'<foreignObject x="{x*PX:.1f}" y="{y*PX:.1f}" width="{w*PX:.1f}" height="{h*PX:.1f}">'
        f'<div xmlns="http://www.w3.org/1999/xhtml" style="width:100%;height:100%;display:flex;'
        f'flex-direction:column;justify-content:{valign};box-sizing:border-box;{style}">'
        f'{inner}</div></foreignObject>'
    )


def _text_item_svg(t: TextItem) -> str:
    style = _TEXT_STYLE.get(t.role, _TEXT_STYLE["body"])
    if t.role == "bullets":
        lis = "".join(f'<li style="margin:0 0 9px 0;">{escape(b)}</li>' for b in t.bullets)
        return _fo(t.x, t.y, t.w, t.h, f'<ul style="margin:0;padding-left:1.1em;">{lis}</ul>', style)
    return _fo(t.x, t.y, t.w, t.h, f"<div>{escape(t.text)}</div>", style)


def _shape_svg(s) -> str:
    if isinstance(s, RectShape):
        fill, stroke = material_colors(s.material)
        out = (f'<rect x="{s.x*PX:.1f}" y="{s.y*PX:.1f}" width="{s.w*PX:.1f}" '
               f'height="{s.h*PX:.1f}" rx="{s.rx*PX:.1f}" fill="{fill}" '
               f'stroke="{stroke}" stroke-width="1.6"/>')
        if s.inner_label:
            color = "#f2f4f7" if s.material in DARK_ROLES else NAVY
            style = (f"font:600 {s.label_size}px system-ui,sans-serif;color:{color};"
                     "text-align:center;")
            out += _fo(s.x + 0.04, s.y, s.w - 0.08, s.h,
                       f'<div style="width:100%">{escape(s.inner_label)}</div>',
                       style, valign="center")
        return out
    if isinstance(s, PolyShape):
        fill, stroke = material_colors(s.material)
        pts = " ".join(f"{px*PX:.1f},{py*PX:.1f}" for px, py in s.points)
        return f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
    if isinstance(s, CircleShape):
        fill, stroke = material_colors(s.material)
        return (f'<circle cx="{s.cx*PX:.1f}" cy="{s.cy*PX:.1f}" r="{s.r*PX:.1f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>')
    return ""


def _callout_svg(c: Callout) -> str:
    # elbow leader: target -> horizontal segment -> label
    if c.side == "right":
        midx = c.lx - 0.12
        text_anchor_x = c.lx
        align = "left"
    else:
        midx = c.lx + 0.12
        text_anchor_x = c.lx - 2.3
        align = "right"
    path = (f'M {c.tx*PX:.1f} {c.ty*PX:.1f} L {midx*PX:.1f} {c.ly*PX:.1f} '
            f'L {c.lx*PX:.1f} {c.ly*PX:.1f}') if c.side == "right" else \
           (f'M {c.tx*PX:.1f} {c.ty*PX:.1f} L {midx*PX:.1f} {c.ly*PX:.1f} '
            f'L {c.lx*PX:.1f} {c.ly*PX:.1f}')
    dot = f'<circle cx="{c.tx*PX:.1f}" cy="{c.ty*PX:.1f}" r="3" fill="{LEADER}"/>'
    line = f'<path d="{path}" fill="none" stroke="{LEADER}" stroke-width="1.3"/>'
    style = (f"font:500 15px system-ui,sans-serif;color:{NAVY};text-align:{align};"
             "line-height:1.15;")
    # two-line height so long labels wrap instead of clipping
    label = _fo(text_anchor_x, c.ly - 0.14, 2.35, 0.55,
                f"<div>{escape(c.text)}</div>", style)
    return dot + line + label


def _figure_svg(f: FigureItem) -> str:
    parts = []
    for e in f.edges:
        marker = ' marker-end="url(#arrow)"' if getattr(e, "arrow", True) else ""
        parts.append(
            f'<line x1="{e.x1*PX:.1f}" y1="{e.y1*PX:.1f}" x2="{e.x2*PX:.1f}" '
            f'y2="{e.y2*PX:.1f}" stroke="{ACCENT}" stroke-width="2.5"{marker}/>')
        if e.label:
            mx, my = (e.x1 + e.x2) / 2, (e.y1 + e.y2) / 2
            parts.append(f'<text x="{mx*PX:.1f}" y="{my*PX-6:.1f}" fill="{GRAY}" '
                         f'font-size="14" text-anchor="middle">{escape(e.label)}</text>')
    for s in f.shapes:
        parts.append(_shape_svg(s))
    for c in f.callouts:
        parts.append(_callout_svg(c))
    for t in f.texts:
        parts.append(_text_item_svg(t))
    return "".join(parts)


def render_slide_svg(slide: Slide) -> str:
    body = []
    for it in layout_slide(slide):
        if isinstance(it, TextItem):
            body.append(_text_item_svg(it))
        elif isinstance(it, FigureItem):
            body.append(_figure_svg(it))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" '
        f'style="background:#fff;border:1px solid #d7dbe3;border-radius:8px;display:block;">'
        f'<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{ACCENT}"/></marker></defs>'
        f'{"".join(body)}</svg>'
    )
