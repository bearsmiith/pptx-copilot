"""WP5 tier-1 — per-user preference profile from accepted interactions.

Aggregates material/label/structure preferences and A/B bias from the session
stores. Injected as a short block into generation prompts. Deterministic.
"""
from __future__ import annotations

import glob
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


def _iter_accepted_slides(user: str | None = None):
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
                yield n["slide"], (n.get("instruction", "") or "")


def build_profile(user: str | None = None) -> dict:
    if user is None:
        try:
            from telemetry import current_uid
            user = current_uid()
        except Exception:
            user = "default"
    mats, labels, structs = Counter(), Counter(), Counter()
    ab = Counter()
    n = 0
    for slide, instr in _iter_accepted_slides(user):
        n += 1
        fig = slide.get("figure") or {}
        for r in fig.get("rows", []):
            if r.get("material"):
                mats[r["material"]] += 1
            if r.get("label"):
                labels[r["label"]] += 1
        try:
            from templates import match_structure
            for c in match_structure(slide.get("title", "") + " "
                                     + (fig.get("caption") or "")):
                structs[c] += 1
        except Exception:
            pass
        if instr.strip().startswith("("):  # "(A)"/"(B)" revise tag
            ab[instr.strip()[1]] += 1
    return {
        "n_accepted": n,
        "preferred_materials": [m for m, _ in mats.most_common(6)],
        "favorite_structures": [s for s, _ in structs.most_common(4)],
        "label_lexicon": [l for l, _ in labels.most_common(8)],
        "direction_bias": dict(ab),
    }


def profile_prompt_block(profile: dict) -> str:
    if not profile or profile.get("n_accepted", 0) < 2:
        return ""
    parts = []
    if profile["favorite_structures"]:
        parts.append("often uses: " + ", ".join(profile["favorite_structures"]))
    if profile["preferred_materials"]:
        parts.append("preferred materials: " + ", ".join(profile["preferred_materials"]))
    if profile["label_lexicon"]:
        parts.append("label wording seen before: " + ", ".join(profile["label_lexicon"][:6]))
    if not parts:
        return ""
    return "[USER PREFERENCES] " + " · ".join(parts) + "\n\n"
