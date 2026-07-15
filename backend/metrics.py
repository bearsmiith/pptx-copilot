"""WP5 — first-draft acceptance metrics (the north star).

Computed from the persisted session trees. first-draft hit = a draft accepted
(confirmed/exported/branched-from) with zero revise feedback on it.

    python -m metrics       (run from backend/)
"""
from __future__ import annotations

import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


def _load(subdir):
    for f in glob.glob(os.path.join(DATA, subdir, "*.json")):
        try:
            yield json.load(open(f, encoding="utf-8"))
        except Exception:
            continue


def _kind_of(node: dict):
    return ((node.get("slide") or {}).get("figure") or {}).get("kind")


def compute() -> dict:
    sessions = 0
    drafts = 0            # root drafts (direction A/B first generation)
    first_hits = 0        # a root draft accepted with no revision applied to it
    exports = 0
    revise_events = 0
    by_kind: dict[str, dict] = {}    # WP7: first-draft acceptance broken out by kind

    for subdir in ("dsessions", "slsessions"):
        for s in _load(subdir):
            sessions += 1
            roots = [n for n in s.get("nodes", []) if not n.get("parent")]
            drafts += len(roots)
            exported = {e.get("content") for e in s.get("events", [])
                        if e.get("kind") == "export"}
            exports += len(exported)
            revise_events += sum(1 for e in s.get("events", [])
                                 if e.get("kind") in ("feedback", "variant"))
            childp = {n.get("parent") for n in s.get("nodes", []) if n.get("parent")}
            for r in roots:
                # accepted directly (exported or confirmed) without being revised
                revised = r["id"] in childp
                accepted = r["id"] in exported or r.get("confirmed")
                k = _kind_of(r) or "unknown"
                b = by_kind.setdefault(k, {"drafts": 0, "hits": 0})
                b["drafts"] += 1
                if accepted and not revised:
                    first_hits += 1
                    b["hits"] += 1

    rate = (first_hits / drafts) if drafts else 0.0
    for k, b in by_kind.items():
        b["rate"] = round(b["hits"] / b["drafts"], 3) if b["drafts"] else 0.0
    return {
        "sessions": sessions,
        "root_drafts": drafts,
        "first_draft_hits": first_hits,
        "first_draft_acceptance_rate": round(rate, 3),
        "exports": exports,
        "revise_events": revise_events,
        "by_kind": dict(sorted(by_kind.items(), key=lambda kv: -kv[1]["drafts"])),
    }


if __name__ == "__main__":
    m = compute()
    print("first-draft acceptance metrics:")
    for k, v in m.items():
        print(f"  {k}: {v}")
