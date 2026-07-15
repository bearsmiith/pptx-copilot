"""Persistent single-slide sessions (image+text layout branching tree).

Mirrors dsessions but each node is a SlideLayout and each session owns an
assets directory of image files (uploaded images + rasterized diagrams) that
must survive for re-render and pptx export. Numbered from 1, separate from
diagram sessions.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time

from PIL import Image

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "data", "slsessions")
os.makedirs(BASE, exist_ok=True)

_lock = threading.Lock()


def _path(num: int) -> str:
    return os.path.join(BASE, f"{num}.json")


def assets_dir(num: int) -> str:
    d = os.path.join(BASE, f"{num}_assets")
    os.makedirs(d, exist_ok=True)
    return d


def next_num() -> int:
    with _lock:
        nums = [int(m.group(1)) for f in os.listdir(BASE)
                if (m := re.match(r"^(\d+)\.json$", f))]
        return (max(nums) + 1) if nums else 1


def _content_hash(path: str) -> str | None:
    """Exact content hash — dedup re-uploads of the identical file with ZERO
    false positives. (Perceptual/embedding dedup is risky here: technical
    cross-sections are structurally similar; a compare-two-diagrams request
    must NOT collapse them. WP6 §3 — exact is the safe default.)"""
    import hashlib
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except Exception:
        return None


def _register_image(s: dict, filename: str, note: str | None = None) -> dict:
    """filename is basename inside the session assets dir. Reads dimensions.
    Exact-duplicate uploads are skipped (returns the existing entry)."""
    path = os.path.join(assets_dir(s["num"]), filename)
    h = _content_hash(path)
    if h is not None:
        for e in s["images"]:
            if e.get("sha") == h:
                log_event(s, "dedup", f"{filename} == {e['name']} (skipped)")
                return e
    try:
        with Image.open(path) as im:
            w, h_px = im.size
    except Exception:
        w, h_px = 1280, 720
    ref = len(s["images"])
    entry = {"ref": ref, "name": filename, "path": path, "sha": h,
             "w": w, "h": h_px, "aspect": (w / h_px if h_px else 16 / 9), "note": note}
    s["images"].append(entry)
    return entry


def new_session(prompt: str, uid: str | None = None) -> dict:
    s = {
        "num": next_num(),
        "uid": uid,
        "title": prompt.strip().splitlines()[0][:60] or "untitled",
        "created": time.time(),
        "prompt": prompt,
        "images": [],       # asset manifest [{ref,name,path,w,h,aspect,note}]
        "next_node": 1,
        "nodes": [],        # {id, parent, instruction, layout, ts, confirmed}
        "events": [],
    }
    save(s)
    return s


def save_upload(s: dict, filename: str, data: bytes, note: str | None = None) -> dict:
    from ingest import _safe_name
    safe = _safe_name(filename)
    # avoid collisions
    dst = os.path.join(assets_dir(s["num"]), safe)
    if os.path.exists(dst):
        stem, ext = os.path.splitext(safe)
        safe = f"{stem}_{len(s['images'])}{ext}"
        dst = os.path.join(assets_dir(s["num"]), safe)
    with open(dst, "wb") as f:
        f.write(data)
    return _register_image(s, safe, note)


def save_png(s: dict, filename: str, png_bytes: bytes, note: str | None = None) -> dict:
    dst = os.path.join(assets_dir(s["num"]), filename)
    with open(dst, "wb") as f:
        f.write(png_bytes)
    return _register_image(s, filename, note)


def assets_map(s: dict) -> dict:
    return {e["ref"]: {"path": e["path"], "aspect": e["aspect"]}
            for e in s["images"]}


def add_node(s: dict, parent: str | None, instruction: str, layout_dict: dict) -> dict:
    node = {"id": f"n{s['next_node']}", "parent": parent,
            "instruction": instruction[:500], "layout": layout_dict,
            "ts": round(time.time() - s["created"]), "confirmed": False}
    s["next_node"] += 1
    s["nodes"].append(node)
    return node


def get_node(s: dict, node_id: str) -> dict | None:
    return next((n for n in s["nodes"] if n["id"] == node_id), None)


def log_event(s: dict, kind: str, content: str):
    s["events"].append({"kind": kind, "stage": "slide",
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
    for f in os.listdir(BASE):
        m = re.match(r"^(\d+)\.json$", f)
        if not m:
            continue
        try:
            s = load(int(m.group(1)))
            if not s:
                continue
            owner = s.get("uid")
            if uid is not None and owner is not None and owner != uid:
                continue
            out.append({"num": s["num"], "title": s["title"],
                        "created": s["created"],
                        "node_count": len(s["nodes"]),
                        "image_count": len(s["images"])})
        except Exception:
            continue
    out.sort(key=lambda x: -x["num"])
    return out


def owns(s: dict, uid: str | None) -> bool:
    owner = s.get("uid")
    return owner is None or uid is None or owner == uid
