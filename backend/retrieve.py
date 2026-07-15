"""WP5 tier-1 — retrieval of past accepted structures (no training, instant).

Deterministic keyword/structure-tag search over accepted diagram/slide nodes
(confirmed/exported/has-children) + the canonical domain library as seed.
Returns few-shot examples injected into generation. Highest-ROI learning lever;
on-prem safe (no embeddings required).
"""
from __future__ import annotations

import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

ENABLED = os.environ.get("LEARN_RETRIEVAL", "1").strip() not in ("0", "false", "no")

_STOP = {"the", "a", "및", "그림", "단면도", "구조", "슬라이드", "cross", "section"}


def _tokens(text: str) -> set[str]:
    t = (text or "").lower()
    out = set()
    for w in "".join(c if c.isalnum() else " " for c in t).split():
        if len(w) >= 2 and w not in _STOP:
            out.add(w)
    return out


def _accepted_nodes(user: str | None):
    """Yield (prompt, slide_json) for accepted diagram nodes owned by `user`
    (own sessions only; legacy no-owner sessions are shared seed)."""
    for f in glob.glob(os.path.join(DATA, "dsessions", "*.json")):
        try:
            s = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        owner = s.get("uid")
        if user is not None and owner is not None and owner != user:
            continue
        exported = {e.get("content") for e in s.get("events", [])
                    if e.get("kind") == "export"}
        childp = {n.get("parent") for n in s.get("nodes", []) if n.get("parent")}
        for n in s.get("nodes", []):
            if (n["id"] in exported or n["id"] in childp) and n.get("slide"):
                yield s.get("prompt", ""), n["slide"]


def _cur_uid() -> str:
    try:
        from telemetry import current_uid
        return current_uid()
    except Exception:
        return "default"


def index_stats(user: str | None = None) -> dict:
    return {"accepted": sum(1 for _ in _accepted_nodes(user))}


def retrieve(prompt: str, k: int = 2, user: str | None = None) -> list[dict]:
    """Top-k accepted slide JSON most similar to the prompt (token overlap +
    structure-tag match), scoped to the current browser's own history."""
    if not ENABLED:
        return []
    if user is None:
        user = _cur_uid()
    q = _tokens(prompt)
    try:
        from templates import match_structure
        q_struct = set(match_structure(prompt))
    except Exception:
        q_struct = set()

    scored = []
    for p, slide in _accepted_nodes(user):
        cand = _tokens(p) | _tokens(json.dumps(slide, ensure_ascii=False)[:400])
        score = len(q & cand)
        try:
            if q_struct & set(match_structure(p)):
                score += 5
        except Exception:
            pass
        if score > 0:
            scored.append((score, slide))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:k]]


def fewshot_block(prompt: str, k: int = 2) -> str:
    """Compact few-shot text to prepend to a generation prompt (or '')."""
    ex = retrieve(prompt, k=k)
    if not ex:
        return ""
    import json as _j
    lines = ["[ACCEPTED EXAMPLES] Past diagrams this user approved for similar "
             "requests. Reuse their structure/labels where it fits; adapt to the "
             "current request."]
    for e in ex:
        lines.append(_j.dumps(e, ensure_ascii=False)[:1200])
    return "\n".join(lines) + "\n\n"
