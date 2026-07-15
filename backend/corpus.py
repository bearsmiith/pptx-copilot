"""WP5 — offline ETL: session trees + interaction log -> learning datasets.

Reads the persisted session stores (data/{sessions,dsessions,slsessions}) and
telemetry, and emits SFT / DPO / corrections JSONL under data/learning/.
Pure batch, re-runnable. Raw attachment bytes are never included.

    python -m corpus            (run from backend/)
"""
from __future__ import annotations

import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(DATA, "learning")


def _load_all(subdir: str) -> list[dict]:
    out = []
    d = os.path.join(DATA, subdir)
    for f in glob.glob(os.path.join(d, "*.json")):
        try:
            out.append(json.load(open(f, encoding="utf-8")))
        except Exception:
            continue
    return out


def _tree_pairs(s: dict, payload_key: str):
    """Yield (parent_payload, instruction, child_payload) revise pairs, and
    (prompt, accepted_payload) generate rows, from a branching session tree."""
    by_id = {n["id"]: n for n in s.get("nodes", [])}
    child_count = {}
    for n in s["nodes"]:
        if n.get("parent"):
            child_count[n["parent"]] = child_count.get(n["parent"], 0) + 1

    exported = {e.get("content") for e in s.get("events", [])
                if e.get("kind") == "export"}
    for n in s["nodes"]:
        pay = n.get(payload_key)
        if pay is None:
            continue
        # revise pair: parent + this node's instruction -> this node
        if n.get("parent") and by_id.get(n["parent"]):
            par = by_id[n["parent"]].get(payload_key)
            if par is not None:
                yield ("revise", {"before": par, "instruction": n.get("instruction", ""),
                                  "after": pay})
        # generate row: a node that was confirmed or exported or has children
        accepted = (n.get("confirmed") or n["id"] in exported
                    or child_count.get(n["id"], 0) > 0)
        if accepted:
            yield ("generate", {"prompt": s.get("prompt", ""), "target": pay})
        # dpo: siblings — accepted vs not
    # sibling DPO
    sibs: dict[str, list[dict]] = {}
    for n in s["nodes"]:
        sibs.setdefault(n.get("parent"), []).append(n)
    for group in sibs.values():
        if len(group) < 2:
            continue
        def score(n):
            return (2 if n["id"] in exported else 0) + (1 if n.get("confirmed") else 0) \
                + child_count.get(n["id"], 0)
        ranked = sorted(group, key=score, reverse=True)
        if score(ranked[0]) > score(ranked[-1]):
            ch, rj = ranked[0].get(payload_key), ranked[-1].get(payload_key)
            if ch is not None and rj is not None:
                yield ("dpo", {"prompt": s.get("prompt", ""), "chosen": ch, "rejected": rj})


def build(out_dir: str = OUT) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    counts = {"sft_generate": 0, "sft_revise": 0, "dpo": 0}
    files = {k: open(os.path.join(out_dir, k + ".jsonl"), "w", encoding="utf-8")
             for k in counts}

    sources = [("dsessions", "slide"), ("slsessions", "layout")]
    for subdir, key in sources:
        for s in _load_all(subdir):
            for kind, row in _tree_pairs(s, key):
                if kind == "generate":
                    files["sft_generate"].write(json.dumps(row, ensure_ascii=False) + "\n")
                    counts["sft_generate"] += 1
                elif kind == "revise":
                    files["sft_revise"].write(json.dumps(row, ensure_ascii=False) + "\n")
                    counts["sft_revise"] += 1
                elif kind == "dpo":
                    files["dpo"].write(json.dumps(row, ensure_ascii=False) + "\n")
                    counts["dpo"] += 1

    # deck sessions: exported deck = generate target
    for s in _load_all("sessions"):
        if s.get("deck") and any(e.get("kind") == "export" for e in s.get("events", [])):
            files["sft_generate"].write(json.dumps(
                {"prompt": s.get("prompt", ""), "target": s["deck"]},
                ensure_ascii=False) + "\n")
            counts["sft_generate"] += 1

    for f in files.values():
        f.close()
    return counts


if __name__ == "__main__":
    c = build()
    print("learning datasets ->", OUT)
    for k, v in c.items():
        print(f"  {k}: {v} rows")
