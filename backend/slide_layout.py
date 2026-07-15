"""Single-slide layout engine (image + text composition).

Same philosophy as the diagram engine: the LLM picks a template and assigns
content to slots; this module computes all geometry in INCHES. Images are
fitted 'contain' (aspect preserved) inside their slot. Produces TextItem
(reused from layout.py) + ImageItem, consumed by slide_render.py for both
SVG preview and pptx export.

Slide is 13.333 x 7.5 in.
"""
from __future__ import annotations

from dataclasses import dataclass

from layout import SLIDE_W, SLIDE_H, TextItem
from models import SlideLayout

MX = 0.7
TITLE_Y = 0.45
TITLE_H = 0.95


@dataclass
class ImageItem:
    x: float
    y: float
    w: float
    h: float
    ref: int
    path: str | None            # asset file path (None -> placeholder box)
    caption: str | None = None


def _fit(slot_x, slot_y, slot_w, slot_h, aspect: float):
    """Largest rect of given aspect (w/h) fitting inside slot, centered."""
    if aspect <= 0:
        aspect = 16 / 9
    slot_a = slot_w / slot_h
    if aspect > slot_a:
        fw, fh = slot_w, slot_w / aspect
    else:
        fh, fw = slot_h, slot_h * aspect
    return (slot_x + (slot_w - fw) / 2, slot_y + (slot_h - fh) / 2, fw, fh)


def _img(slot, refobj, assets) -> ImageItem:
    """slot=(x,y,w,h); refobj=SlideImage; assets: ref->{path,aspect}."""
    sx, sy, sw, sh = slot
    a = assets.get(refobj.ref, {})
    fx, fy, fw, fh = _fit(sx, sy, sw, sh, a.get("aspect", 16 / 9))
    return ImageItem(fx, fy, fw, fh, refobj.ref, a.get("path"), refobj.caption)


def _title_items(layout: SlideLayout, y=TITLE_Y, h=TITLE_H) -> list[TextItem]:
    items = [TextItem("title", MX, y, SLIDE_W - 2 * MX, h, text=layout.title)]
    return items


def _text_block(layout: SlideLayout, x, y, w, h) -> list[TextItem]:
    items = []
    cy = y
    if layout.subtitle:
        items.append(TextItem("subtitle", x, cy, w, 0.7, text=layout.subtitle))
        cy += 0.75
    if layout.bullets:
        items.append(TextItem("bullets", x, cy, w, y + h - cy, bullets=layout.bullets))
    return items


def layout_slide_layout(layout: SlideLayout, assets: dict) -> list:
    """assets: {ref: {"path": str, "aspect": float}}."""
    items: list = []
    t = layout.template
    imgs = layout.images
    content_w = SLIDE_W - 2 * MX
    body_top = TITLE_Y + TITLE_H + 0.2
    body_h = SLIDE_H - body_top - 0.4

    def cap_below(slot, refobj):
        """image + caption stacked in a slot."""
        sx, sy, sw, sh = slot
        has_cap = bool(refobj.caption)
        ih = sh - (0.4 if has_cap else 0)
        it = _img((sx, sy, sw, ih), refobj, assets)
        out = [it]
        if has_cap:
            out.append(TextItem("caption", sx, sy + ih + 0.02, sw, 0.35,
                                text=refobj.caption))
        return out

    if t == "text_only" or not imgs:
        items += _title_items(layout)
        items += _text_block(layout, MX, body_top, content_w, body_h)
        return items

    if t in ("image_left_text_right", "image_right_text_left"):
        items += _title_items(layout)
        half = (content_w - 0.5) / 2
        left = (MX, body_top, half, body_h)
        right = (MX + half + 0.5, body_top, half, body_h)
        img_slot, txt_slot = (left, right) if t == "image_left_text_right" else (right, left)
        items += cap_below(img_slot, imgs[0])
        items += _text_block(layout, txt_slot[0], txt_slot[1], txt_slot[2], txt_slot[3])
        return items

    if t in ("image_top_text_bottom", "text_top_image_bottom"):
        items += _title_items(layout)
        img_h = body_h * 0.62
        txt_h = body_h - img_h - 0.2
        if t == "image_top_text_bottom":
            img_slot = (MX, body_top, content_w, img_h)
            txt_y = body_top + img_h + 0.2
        else:
            txt_y = body_top
            img_slot = (MX, body_top + txt_h + 0.2, content_w, img_h)
        items += cap_below(img_slot, imgs[0])
        items += _text_block(layout, MX, txt_y, content_w, txt_h)
        return items

    if t == "hero_title":
        # big image fills body; title band on top (already there); caption bottom
        items += _title_items(layout)
        items += cap_below((MX, body_top, content_w, body_h), imgs[0])
        if layout.caption:
            items.append(TextItem("caption", MX, SLIDE_H - 0.45, content_w, 0.35,
                                  text=layout.caption))
        return items

    if t == "two_images":
        items += _title_items(layout)
        gap = 0.5
        w = (content_w - gap) / 2
        for i in range(min(2, len(imgs))):
            slot = (MX + i * (w + gap), body_top, w, body_h)
            items += cap_below(slot, imgs[i])
        return items

    if t == "image_grid":
        items += _title_items(layout)
        n = min(4, len(imgs))
        cols = 2 if n > 1 else 1
        rows = (n + cols - 1) // cols
        gap = 0.4
        cw = (content_w - gap * (cols - 1)) / cols
        ch = (body_h - gap * (rows - 1)) / rows
        for i in range(n):
            r, c = divmod(i, cols)
            slot = (MX + c * (cw + gap), body_top + r * (ch + gap), cw, ch)
            items += cap_below(slot, imgs[i])
        return items

    # fallback
    items += _title_items(layout)
    items += cap_below((MX, body_top, content_w, body_h), imgs[0])
    return items
