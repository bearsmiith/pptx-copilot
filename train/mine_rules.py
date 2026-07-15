"""WP5 tier-3 — mine repeated corrections into proposed deterministic rules.

Reads data/learning/sft_revise.jsonl (before,instruction,after) and surfaces
recurring material/label rewrites. Emits PROPOSED diffs only — never auto-merges
(human review gate, handoff §5). Feeds backend/repair.MATERIAL_ALIAS + templates.

    python train/mine_rules.py --min-count 5
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
LEARN = os.path.join(HERE, "..", "data", "learning")


def _materials(slide: dict) -> dict:
    fig = (slide or {}).get("figure") or {}
    out = {}
    for i, r in enumerate(fig.get("rows", [])):
        if r.get("material"):
            out[(i, r.get("label", ""))] = r["material"]
    return out


def mine(min_count: int) -> dict:
    path = os.path.join(LEARN, "sft_revise.jsonl")
    if not os.path.exists(path):
        return {"material_rewrites": [], "note": "no sft_revise.jsonl yet"}
    mat_rewrites = Counter()
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        b, a = _materials(row.get("before")), _materials(row.get("after"))
        for k in b.keys() & a.keys():
            if b[k] != a[k]:
                mat_rewrites[(b[k], a[k])] += 1
    proposals = [{"from": f, "to": t, "count": c}
                 for (f, t), c in mat_rewrites.items() if c >= min_count]
    return {"material_rewrites": sorted(proposals, key=lambda x: -x["count"])}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-count", type=int, default=5)
    args = ap.parse_args()
    res = mine(args.min_count)
    print("PROPOSED rules (review before merging):")
    print(json.dumps(res, ensure_ascii=False, indent=2))
