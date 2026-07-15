"""Persistent branching diagram sessions (단면도 탐색 트리).

One session = a tree of diagram variants. Root request spawns 2 drafts;
selecting a node + revision request spawns 2 children. Sessions are numbered
from 1 and auto-saved as JSON under data/dsessions/ so they survive restarts
and can be reloaded. SVGs are re-rendered on load (only slide JSON stored),
so engine improvements apply retroactively.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "data", "dsessions")
os.makedirs(DATA_DIR, exist_ok=True)

_lock = threading.Lock()


def _path(num: int) -> str:
    return os.path.join(DATA_DIR, f"{num}.json")


def next_num() -> int:
    with _lock:
        nums = [int(m.group(1)) for f in os.listdir(DATA_DIR)
                if (m := re.match(r"^(\d+)\.json$", f))]
        return (max(nums) + 1) if nums else 1


def new_session(prompt: str, uid: str | None = None) -> dict:
    s = {
        "num": next_num(),
        "uid": uid,      # owning browser (None = legacy/shared)
        "title": prompt.strip().splitlines()[0][:60] or "untitled",
        "created": time.time(),
        "prompt": prompt,
        "next_node": 1,
        "nodes": [],     # {id, parent, instruction, slide, ts}
        "events": [],    # harness log for LLM context
    }
    save(s)
    return s


def add_node(s: dict, parent: str | None, instruction: str, slide_dict: dict,
             brief: dict | None = None, overrides: dict | None = None) -> dict:
    node = {
        "id": f"n{s['next_node']}",
        "parent": parent,
        "instruction": instruction[:500],
        "slide": slide_dict,
        "ts": round(time.time() - s["created"]),
    }
    if brief is not None:                        # WP8: persist the Brief IR so
        node["brief"] = brief                    # revisions edit it and recompile
    if overrides:                                # WP10: user edit diff layer
        node["overrides"] = overrides
    s["next_node"] += 1
    s["nodes"].append(node)
    return node


def log_event(s: dict, kind: str, content: str):
    s["events"].append({"kind": kind, "stage": "diagram",
                        "content": content[:1000],
                        "ts": round(time.time() - s["created"])})


def save(s: dict):
    with _lock:
        tmp = _path(s["num"]) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False)
        os.replace(tmp, _path(s["num"]))


def load(num: int) -> dict | None:
    try:
        with open(_path(num), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def list_sessions(uid: str | None = None) -> list[dict]:
    out = []
    for f in os.listdir(DATA_DIR):
        m = re.match(r"^(\d+)\.json$", f)
        if not m:
            continue
        try:
            s = load(int(m.group(1)))
            if not s:
                continue
            owner = s.get("uid")
            # show own sessions + legacy (no owner) ones
            if uid is not None and owner is not None and owner != uid:
                continue
            out.append({"num": s["num"], "title": s["title"],
                        "created": s["created"],
                        "node_count": len(s["nodes"])})
        except Exception:
            continue
    out.sort(key=lambda x: -x["num"])
    return out


def owns(s: dict, uid: str | None) -> bool:
    owner = s.get("uid")
    return owner is None or uid is None or owner == uid
