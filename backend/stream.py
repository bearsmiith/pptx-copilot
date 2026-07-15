"""WP7 — partial-JSON → progressive Slide (pure functions).

Used to render a figure as it streams. `close_partial` repairs a truncated JSON
buffer (open strings/brackets) so it can be parsed; `try_partial_slide` returns
the best-effort Slide so far, or None (silently) if nothing parses yet.
"""
from __future__ import annotations

import json
import re


def close_partial(buf: str) -> str:
    """Balance a truncated JSON string: close an open string literal and any
    unclosed objects/arrays, dropping a dangling comma/colon/partial key."""
    in_str = False
    esc = False
    stack: list[str] = []
    for ch in buf:
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]" and stack:
            stack.pop()
    res = buf + ('"' if in_str else "")
    # strip a trailing dangling key/comma/colon (e.g. `, "lab` or `,`)
    res = re.sub(r",\s*\"[^\"]*\"\s*:?\s*$", "", res)
    res = re.sub(r"[,:]\s*$", "", res)
    return res + "".join(reversed(stack))


def try_partial_slide(buf: str):
    """Best-effort Slide from a partial buffer. Trims back to successive element
    boundaries until one parses. Returns Slide or None (never raises)."""
    from models import Slide
    from llm import _coerce_shape
    if not buf or "{" not in buf:
        return None
    # candidate cut points: end, then each trailing '}' or ']' boundary
    cuts = [len(buf)] + [m.end() for m in re.finditer(r"[}\]]", buf)][::-1]
    seen = set()
    for cut in cuts:
        if cut in seen:
            continue
        seen.add(cut)
        try:
            data = json.loads(close_partial(buf[:cut]))
        except Exception:
            continue
        data = _coerce_shape(Slide, data)
        if not isinstance(data, dict):
            continue
        if "figure" in data and "layout_type" not in data:
            data = {"layout_type": "figure", "title": data.get("title", "…"),
                    "figure": data["figure"]}
        try:
            return Slide.model_validate(data)
        except Exception:
            continue
    return None
