"""WP6 — slide TEXT linter (deterministic, Findings — same format as lint.py).

Format/authoring rules from the design KB (assertion titles, parallel short
bullets, expanded acronyms, honest captions, grounded numbers). Applied to
content/slide text — NOT to figure-DSL geometry. Most findings are 'warn' and
flow back through the WP3 repair loop; hard failures minimized.
"""
from __future__ import annotations

import re

from lint import Finding
from models import Deck, Slide, SlideLayout, StackFigure

# a title that's an assertion has a verb/predicate; a topic label doesn't
_VERB_HINT = re.compile(r"\b(is|are|shorten|enable|reduce|increase|use|uses|"
                        r"replace|deliver|improve|cut|raise|lower|allow|"
                        r"provide|stack|bond|carry|route)\b", re.I)
_KO_PREDICATE = re.compile(r"(다|한다|된다|이다|줄|늘|높|낮|이고|이며|한|된)")


def _is_assertion(title: str) -> bool:
    t = (title or "").strip()
    if len(t) < 8:
        return False
    return bool(_VERB_HINT.search(t) or _KO_PREDICATE.search(t))


def _acronyms_unexpanded(text: str) -> list[str]:
    # ALLCAPS 2-6 chars not followed by an expansion "(...)"
    bad = []
    for m in re.finditer(r"\b([A-Z]{2,6})\b", text or ""):
        a = m.group(1)
        after = text[m.end():m.end() + 2]
        if "(" not in after and a not in ("SI", "IO", "AI", "3D", "2D"):
            bad.append(a)
    return sorted(set(bad))


def _bullet_findings(bullets, where, out):
    n = len(bullets)
    if n and (n < 2 or n > 6):
        out.append(Finding("info", where, "BULLET_COUNT",
                           f"{n} bullets (aim 3-6)",
                           "merge or split to land 3-6 bullets"))
    ends = [b.rstrip().endswith((".", "。")) for b in bullets]
    for i, b in enumerate(bullets):
        words = len(b.split())
        if len(b) > 72 or words > 12:
            out.append(Finding("warn", f"{where}[{i}]", "BULLET_TOO_LONG",
                               f"bullet is {len(b)} chars / {words} words",
                               "cut to one short phrase (<~12 words)"))
        if re.search(r"[.!?]\s+\S", b):
            out.append(Finding("warn", f"{where}[{i}]", "PARAGRAPH_ON_SLIDE",
                               "bullet contains multiple sentences",
                               "split into separate short bullets"))
    # parallelism: mixed sentence-ending punctuation
    if bullets and 0 < sum(ends) < len(ends):
        out.append(Finding("info", where, "BULLET_NOT_PARALLEL",
                           "bullets mix trailing punctuation / grammar",
                           "make bullets grammatically parallel"))


def _number_findings(text, where, out):
    if re.search(r"\d\s?(µm|um|nm|mm|GB/s|Gbps|TB/s|µm)", text or ""):
        if "[data needed" not in (text or ""):
            out.append(Finding("info", where, "INVENTED_NUMBER_SUSPECT",
                               "specific dimension/spec present — verify it's grounded",
                               "cite a KB card or replace with [data needed: ...]"))


def lint_slide(slide: Slide) -> list[Finding]:
    """Text-quality lint for a content/title slide (skips figure geometry)."""
    out: list[Finding] = []
    if slide.layout_type == "figure":
        # only caption honesty for thickness-exaggerated stacks
        fig = slide.figure
        if isinstance(fig, StackFigure):
            cap = (fig.caption or "").lower()
            if not any(w in cap for w in ("not to scale", "not-to-scale", "축소", "과장")):
                out.append(Finding("info", "figure.caption", "CAPTION_SCALE",
                                   "thickness is exaggerated but no not-to-scale note",
                                   "add 'not to scale' to the caption"))
        return out
    if not _is_assertion(slide.title):
        out.append(Finding("warn", "title", "TITLE_NOT_ASSERTION",
                           f"title '{slide.title}' reads as a topic, not a message",
                           "rewrite as a full-sentence assertion (the slide's point)"))
    ac = _acronyms_unexpanded(slide.title)
    if slide.bullets:
        _bullet_findings(slide.bullets, "bullets", out)
        for i, b in enumerate(slide.bullets):
            ac += _acronyms_unexpanded(b)
            _number_findings(b, f"bullets[{i}]", out)
        if not any(re.search(r"(so |therefore|따라서|→|enable|reduce|because|means)", b, re.I)
                   for b in slide.bullets):
            out.append(Finding("info", "bullets", "MISSING_SO_WHAT",
                               "no takeaway / implication among bullets",
                               "add a 'so what' — the implication of the points"))
    if ac:
        out.append(Finding("info", "text", "ACRONYM_UNEXPANDED",
                           f"acronyms not expanded on first use: {', '.join(sorted(set(ac))[:5])}",
                           "expand each acronym once, e.g. 'TSV (through-silicon via)'"))
    return out


def lint_layout(layout: SlideLayout) -> list[Finding]:
    """Text lint for a single-slide image+text layout."""
    out: list[Finding] = []
    if not _is_assertion(layout.title):
        out.append(Finding("warn", "title", "TITLE_NOT_ASSERTION",
                           f"title '{layout.title}' reads as a topic, not a message",
                           "rewrite as a full-sentence assertion"))
    if layout.bullets:
        _bullet_findings(layout.bullets, "bullets", out)
    return out


def lint_deck(deck: Deck) -> list[Finding]:
    out: list[Finding] = []
    for si, s in enumerate(deck.slides):
        for f in lint_slide(s):
            out.append(Finding(f.level, f"slide[{si}].{f.where}", f.code,
                               f.message, f.fix_hint))
    return out
