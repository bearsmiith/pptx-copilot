"""WP5 — append-only interaction capture (single source of learning signal).

Thin, side-effect-minimal, never raises into callers. One JSONL line per
interaction under data/interactions/{user}/{yyyymmdd}.jsonl. Raw attachment
bytes are NEVER stored — only derived slide/deck JSON (governance §7).
Disabled entirely with LEARN_CAPTURE=0.
"""
from __future__ import annotations

import contextvars
import json
import os
import time

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "data", "interactions")

CAPTURE = os.environ.get("LEARN_CAPTURE", "1").strip() not in ("0", "false", "no")
USER = os.environ.get("LEARN_USER", "default")

# per-request browser id (set by app middleware; captured into job threads)
_uid_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("uid", default=None)


def set_uid(uid: str | None) -> None:
    _uid_var.set(uid)


def current_uid() -> str:
    return _uid_var.get() or USER


def record(event: dict) -> None:
    if not CAPTURE:
        return
    try:
        user = event.get("user") or current_uid()
        ev = {"ts": round(time.time(), 3), "user": user, **event}
        d = os.path.join(BASE, user)
        os.makedirs(d, exist_ok=True)
        day = time.strftime("%Y%m%d", time.gmtime())
        with open(os.path.join(d, f"{day}.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception:
        pass


def iter_events(user: str | None = None):
    """Yield all recorded events (optionally for one user)."""
    if not os.path.isdir(BASE):
        return
    users = [user] if user else os.listdir(BASE)
    for u in users:
        d = os.path.join(BASE, u)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".jsonl"):
                continue
            try:
                for line in open(os.path.join(d, f), encoding="utf-8"):
                    line = line.strip()
                    if line:
                        yield json.loads(line)
            except Exception:
                continue
