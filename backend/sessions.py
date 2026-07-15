"""Session harness for the staged workflow.

Sessions are numbered from 1 (per server process — in-memory prototype).
Each session accumulates an event log (generations, feedback, questions,
answers, confirms) which is injected into staged LLM calls so the model can
reference everything that happened before in the session.
"""
from __future__ import annotations

import itertools
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from models import Deck, DeckPlan

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "data", "sessions")
os.makedirs(BASE, exist_ok=True)

_lock = threading.Lock()


def _next_num() -> int:
    """Numbered from 1, continuing past persisted sessions across restarts."""
    with _lock:
        nums = [int(m.group(1)) for f in os.listdir(BASE)
                if (m := re.match(r"^(\d+)\.json$", f))]
        n = (max(nums) + 1) if nums else 1
    return n


@dataclass
class Session:
    num: int
    uid: Optional[str] = None           # owning browser
    stage: str = "plan"                 # plan | figures | final
    prompt: str = ""
    workdir: Optional[str] = None
    manifest: Optional[list] = None
    plan: Optional[DeckPlan] = None
    deck: Optional[Deck] = None
    # slide_index -> "draft" | "confirmed"  (figure slides only)
    figure_status: dict[int, str] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    created: float = field(default_factory=time.time)

    def log(self, kind: str, content: str, stage: str | None = None):
        self.events.append({
            "ts": round(time.time() - self.created),
            "kind": kind,
            "stage": stage or self.stage,
            "content": content[:2000],
        })


SESSIONS: dict[int, Session] = {}


def _path(num: int) -> str:
    return os.path.join(BASE, f"{num}.json")


def save(s: "Session") -> None:
    """Persist the learnable state (WP5). workdir/manifest are transient and
    excluded (raw attachments never stored). Never raises into callers."""
    try:
        data = {
            "num": s.num, "uid": s.uid, "stage": s.stage, "prompt": s.prompt,
            "created": s.created, "events": s.events,
            "figure_status": {str(k): v for k, v in s.figure_status.items()},
            "plan": s.plan.model_dump(exclude_none=True) if s.plan else None,
            "deck": s.deck.model_dump(exclude_none=True) if s.deck else None,
        }
        tmp = _path(s.num) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, _path(s.num))
    except Exception:
        pass


def new_session(prompt: str = "", workdir=None, manifest=None,
                uid: str | None = None) -> Session:
    num = _next_num()
    s = Session(num=num, uid=uid, prompt=prompt, workdir=workdir, manifest=manifest)
    SESSIONS[num] = s
    if len(SESSIONS) > 150:  # in-memory cap (disk copy persists)
        for k in sorted(SESSIONS)[:30]:
            SESSIONS.pop(k, None)
    save(s)
    return s


def get_session(num: int) -> Session | None:
    return SESSIONS.get(num)


def owns(s: "Session", uid: str | None) -> bool:
    return s.uid is None or uid is None or s.uid == uid
