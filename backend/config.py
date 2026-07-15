"""Runtime LLM backend configuration (settable from the Settings tab).

Persisted to data/config.json; read at call time so changes take effect
without a restart. Defaults derive from env → identical behavior when no
config file exists (backward compatible).

Backends:
  haiku    — Claude Code CLI (claude_cli provider)
  mock     — deterministic sample, no model
  qwen27b  — OpenAI-compatible endpoint (url + model name)
  qwen122b — OpenAI-compatible endpoint (url + model name)

`active` chooses the default backend; per-stage overrides (plan/figure/fill)
let a big model plan while a small one fills.
"""
from __future__ import annotations

import json
import os
import shutil
import threading

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "data", "config.json")
_lock = threading.Lock()
_cache: dict | None = None


def _default_active() -> str:
    # honor legacy env selectors for backward compat + tests
    p = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if p == "mock" or os.environ.get("MOCK", "").strip() in ("1", "true", "yes"):
        return "mock"
    if p == "openai" or os.environ.get("OPENAI_BASE_URL"):
        return "qwen122b"
    if p == "claude_cli" or os.environ.get("CLAUDE_BIN") or shutil.which("claude"):
        return "haiku"
    return "mock"


def _defaults() -> dict:
    # seed endpoints from env if present (backward compat)
    seed_url = os.environ.get("OPENAI_BASE_URL", "")
    seed_model = os.environ.get("LLM_MODEL", "") if seed_url else ""
    seed_jm = os.environ.get("LLM_JSON_MODE", "guided_json")
    return {
        "active": _default_active(),
        "haiku_model": os.environ.get("LLM_MODEL", "haiku"),
        "endpoints": {
            "qwen27b": {"label": "Qwen3.6-27B", "base_url": "", "model": "",
                        "api_key": "", "json_mode": "guided_json"},
            "qwen122b": {"label": "Qwen3.5-122B", "base_url": seed_url,
                         "model": seed_model, "api_key": os.environ.get("OPENAI_API_KEY", ""),
                         "json_mode": seed_jm},
        },
        "stage": {"plan": "", "figure": "", "fill": ""},
    }


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def get() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    cfg = _defaults()
    try:
        with open(PATH, encoding="utf-8") as f:
            cfg = _merge(cfg, json.load(f))
    except FileNotFoundError:
        pass
    except Exception:
        pass
    _cache = cfg
    return cfg


def save(new: dict) -> dict:
    global _cache
    with _lock:
        cur = get()
        merged = _merge(cur, new)
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=1)
        os.replace(tmp, PATH)
        _cache = merged
    return merged


def public() -> dict:
    """Config for the UI — api_key masked to has_key booleans."""
    c = json.loads(json.dumps(get()))
    for ep in c.get("endpoints", {}).values():
        ep["has_key"] = bool(ep.get("api_key"))
        ep.pop("api_key", None)
    return c


# ---- resolution used by llm.py ----

def resolve(stage: str | None = None) -> dict:
    """Return the backend to use for a stage:
    {provider, model, base_url?, api_key?, json_mode?}."""
    c = get()
    sid = (c.get("stage") or {}).get(stage or "") or c.get("active")
    if sid == "mock":
        return {"provider": "mock"}
    if sid == "haiku":
        return {"provider": "claude_cli", "model": c.get("haiku_model", "haiku")}
    ep = (c.get("endpoints") or {}).get(sid)
    if ep and ep.get("base_url") and ep.get("model"):
        return {"provider": "openai", "base_url": ep["base_url"],
                "api_key": ep.get("api_key") or "EMPTY", "model": ep["model"],
                "json_mode": ep.get("json_mode", "guided_json")}
    # misconfigured endpoint → safe fallback
    if os.environ.get("CLAUDE_BIN") or shutil.which("claude"):
        return {"provider": "claude_cli", "model": c.get("haiku_model", "haiku")}
    return {"provider": "mock"}
