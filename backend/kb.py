"""WP6 — knowledge-base loader + retrieval (RAG).

Loads design + domain cards from data/kb/*.jsonl and returns the top-k most
relevant cards for a request, injected into generation prompts as grounding.
Deterministic keyword/tag search (provider-independent → helps every model,
incl. claude_cli). Embedding upgrade is optional and orthogonal.

Card schema: {id, type: 'design'|'domain', tags[], applies_to[]|structure,
              title, body, source}
Disabled with RAG_KB=0 (for A/B eval).
"""
from __future__ import annotations

import json
import os
import re

KB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "kb")

ENABLED = os.environ.get("RAG_KB", "1").strip() not in ("0", "false", "no")

_cards: list[dict] | None = None
_STOP = {"the", "a", "of", "and", "to", "for", "on", "in", "with", "그림",
         "단면도", "슬라이드", "구조", "장", "한", "및"}


def _load() -> list[dict]:
    global _cards
    if _cards is not None:
        return _cards
    out = []
    try:
        for fn in sorted(os.listdir(KB_DIR)):
            if not fn.endswith(".jsonl") or fn.startswith("._"):
                continue
            for line in open(os.path.join(KB_DIR, fn), encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    _cards = out
    return out


def _tokens(text: str) -> set[str]:
    t = (text or "").lower()
    out = set()
    for w in re.split(r"[^0-9a-z가-힣]+", t):
        if len(w) >= 2 and w not in _STOP:
            out.add(w)
    return out


def retrieve(query: str, kinds: list[str] | None = None, k: int = 4,
             structure: str | None = None) -> list[dict]:
    """Top-k cards for the query. kinds filters card type ('design'/'domain');
    structure adds weight to cards for that structure."""
    if not ENABLED:
        return []
    cards = _load()
    q = _tokens(query)
    kinds = set(kinds) if kinds else None
    scored = []
    for c in cards:
        if kinds and c.get("type") not in kinds:
            continue
        hay = _tokens(" ".join(c.get("tags", []))) | _tokens(c.get("title", "")) \
            | _tokens(c.get("body", ""))
        score = len(q & hay)
        # tag/title matches weigh more than body
        score += 2 * len(q & _tokens(" ".join(c.get("tags", []))))
        if structure and c.get("structure") == structure:
            score += 6
        if structure and structure in _tokens(" ".join(c.get("tags", []))):
            score += 3
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:k]]


def block(query: str, kinds: list[str] | None = None, k: int = 4,
          structure: str | None = None) -> str:
    """Grounding block to prepend to a generation prompt (or '')."""
    cards = retrieve(query, kinds, k, structure)
    if not cards:
        return ""
    lines = ["[KNOWLEDGE — use ONLY these cards' facts/principles as grounding. "
             "Do NOT invent numbers not in a card; write \"[data needed: ...]\" "
             "instead. Cards are identified by id.]"]
    for c in cards:
        lines.append(f"- ({c.get('type')} {c.get('id')}) {c.get('title')}: "
                     + c.get("body", "")[:400])
    return "\n".join(lines) + "\n\n"


def index_stats() -> dict:
    cards = _load()
    return {"total": len(cards),
            "design": sum(1 for c in cards if c.get("type") == "design"),
            "domain": sum(1 for c in cards if c.get("type") == "domain")}
