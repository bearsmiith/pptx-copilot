"""LLM client for the LAYOUT_DRAFT stage.

Providers (LLM_PROVIDER env):
  claude_cli — spawn `claude -p --model <m>` (Claude Code CLI, uses its login;
               no API key needed on this host). Default when claude binary exists.
  openai     — OpenAI-compatible endpoint (vLLM/Qwen) with schema-constrained
               decoding (guided_json / json_schema).
  mock       — deterministic sample deck, no model.

All providers share: pydantic validation + one repair round-trip.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from pydantic import ValidationError

from models import Deck, DeckPlan, Slide, SlideLayout
from prompts import (LAYOUT_SYSTEM, LAYOUT_USER_TEMPLATE,
                     EDIT_APPENDIX, EDIT_USER_TEMPLATE,
                     PLAN_SYSTEM, PLAN_USER_TEMPLATE, PLAN_REVISE_TEMPLATE,
                     FIGURE_USER_TEMPLATE, FIGURE_REVISE_TEMPLATE,
                     DIAGRAM_DIRECTIONS, REVISE_DIRECTIONS,
                     DIAGRAM_USER_TEMPLATE, DIAGRAM_REVISE_TEMPLATE,
                     SLIDE_SYSTEM, SLIDE_DIRECTIONS, SLIDE_REVISE_DIRECTIONS,
                     SLIDE_USER_TEMPLATE, SLIDE_REVISE_TEMPLATE,
                     slide_image_block, history_block, layout_system)

import router

# ---- provider selection (runtime, from config.py — settable in UI) ----

import config

MODEL = os.environ.get("LLM_MODEL", "haiku")            # claude default model
CLAUDE_BIN = os.environ.get("CLAUDE_BIN") or shutil.which("claude")


def _use_mock(stage: str | None = None) -> bool:
    return config.resolve(stage).get("provider") == "mock"


def provider_info() -> dict:
    r = config.resolve(None)
    return {"provider": r["provider"],
            "model": r.get("model") if r["provider"] != "mock" else None}


def _extract_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(m.group(0) if m else text)


def _coerce_shape(model_cls, data):
    """Tolerate a model wrapping its answer in the wrong envelope. Small models
    sometimes return a single Slide inside a deck {"slides":[...]} or a bare
    list — unwrap to the first slide so one stray envelope doesn't kill a draft."""
    if model_cls is Slide:
        if isinstance(data, list) and data:
            data = data[0]
        if (isinstance(data, dict) and isinstance(data.get("slides"), list)
                and data["slides"] and "layout_type" not in data):
            return data["slides"][0]
    return data


# ---- WP3 deterministic refinement (normalize; optional lint loop) -------

LINT_REPAIR_ROUNDS = int(os.environ.get("LINT_REPAIR_ROUNDS", "0"))
TEMPLATE_FIRST = os.environ.get("TEMPLATE_FIRST", "").strip() in ("1", "true", "yes")


def _retrieval_block(prompt: str) -> str:
    """WP5 tier-1: prepend past accepted examples + user preference profile.
    Safe: returns '' on any failure or when disabled. No new behavior when
    there's no accepted history yet (fresh install)."""
    try:
        from retrieve import fewshot_block
        from profile import build_profile, profile_prompt_block
        return profile_prompt_block(build_profile()) + fewshot_block(prompt)
    except Exception:
        return ""


def _kb_block(prompt: str, kinds, k: int = 4) -> str:
    """WP6 RAG: prepend grounding cards (domain facts / design principles).
    figure diagrams get domain cards only; text slides get design+domain.
    Safe: '' on failure or when RAG_KB=0."""
    try:
        import kb
        from templates import match_structure
        cands = match_structure(prompt)
        structure = cands[0] if cands else None
        return kb.block(prompt, kinds, k=k, structure=structure)
    except Exception:
        return ""


def _maybe_template(prompt: str):
    """WP2 template-first: if the request strongly matches a known structure,
    build it deterministically (small-model-safe). Off by default (env-gated).
    Skipped when attachments are present (user wants something image-specific)."""
    if not TEMPLATE_FIRST:
        return None
    try:
        from templates import match_structure, instantiate
        cands = match_structure(prompt)
        if not cands:
            return None
        name = cands[0]
        params = {}
        m = re.search(r"(\d+)\s*(단|하이|hi|-?high|층|layer|stack)", prompt, re.I)
        if m:
            n = int(m.group(1))
            if name == "hbm":
                params["n_dram"] = n
        return instantiate(name, params)
    except Exception:
        return None


def _mock_stream(slide, on_partial):
    """Simulate progressive generation (no model) — reveal a list figure element
    at a time so the live-preview path can be developed/demoed without a model."""
    if not on_partial:
        return
    import time
    fig = getattr(slide, "figure", None)
    seq_attr = next((a for a in ("rows", "milestones", "items", "nodes")
                     if getattr(fig, a, None)), None)
    if not seq_attr:
        try:
            on_partial(slide)
        except Exception:
            pass
        return
    full = list(getattr(fig, seq_attr))
    for k in range(1, len(full) + 1):
        part = slide.model_copy(deep=True)
        try:
            setattr(part.figure, seq_attr, full[:k])
            on_partial(part)
        except Exception:
            pass
        time.sleep(0.4)


def _figure_empty(slide) -> bool:
    """A 'figure' slide that would render blank: no figure, or a container
    figure with no content. (Schema allows figure=None / 0 flow-nodes, so this
    is the guard that catches the 'draft A came out empty' failure mode.)"""
    if getattr(slide, "layout_type", None) != "figure":
        return False
    fig = getattr(slide, "figure", None)
    if fig is None:
        return True
    kind = getattr(fig, "kind", None)
    if kind == "flow":
        return not getattr(fig, "nodes", None)
    if kind == "stack":
        return not getattr(fig, "rows", None)
    if kind == "compare":
        return len(getattr(fig, "panels", []) or []) < 2
    if kind == "photonic":
        return not (getattr(fig, "components", None) or getattr(fig, "nodes", None))
    return False


def _ensure_figure(slide, messages, *, workdir, allow_read, stage, prompt=None):
    """If a diagram draft rendered empty, correct it once (explicit instruction),
    then fall back to a template match if the model still returns nothing."""
    if not _figure_empty(slide):
        return slide
    messages = list(messages) + [
        {"role": "assistant",
         "content": json.dumps(slide.model_dump(exclude_none=True), ensure_ascii=False)},
        {"role": "user",
         "content": ("Your slide has layout_type=\"figure\" but no usable `figure` "
                     "(it renders blank). Return the SAME slide with a fully "
                     "populated `figure`: for a cross-section use kind=\"stack\" "
                     "with rows in BOTTOM-TO-TOP order; every row must have a "
                     "material and label. Do not return an empty or null figure. "
                     "JSON only.")},
    ]
    try:
        fixed = _validated(Slide, messages, workdir=workdir,
                           allow_read=allow_read, refine=True, stage=stage)
        if not _figure_empty(fixed):
            return fixed
    except (ValidationError, json.JSONDecodeError, RuntimeError):
        pass
    # last resort: nearest deterministic template so the draft is never blank
    if prompt:
        try:
            from templates import match_structure, instantiate
            cands = match_structure(prompt)
            if cands:
                return instantiate(cands[0], {})
        except Exception:
            pass
    return slide


def _refine(obj):
    """Deterministic normalization on a generated Slide/Deck (material aliases,
    via snap, dies rescale). Safe: a no-op when the output is already clean, so
    existing behavior is preserved. Never raises into the caller."""
    try:
        from repair import normalize_slide, normalize_deck
        if isinstance(obj, Deck):
            normalize_deck(obj)
        elif isinstance(obj, Slide):
            normalize_slide(obj)
    except Exception:
        pass
    return obj


def _lint_findings(obj) -> list:
    try:
        from lint import lint_slide, lint_deck
        from geomcheck import check_layout
        import slidewrite            # WP6 text linter (same Findings format)
        if isinstance(obj, Deck):
            fs = lint_deck(obj) + slidewrite.lint_deck(obj)
            for sl in obj.slides:
                fs += check_layout(sl)
            return fs
        if isinstance(obj, Slide):
            return lint_slide(obj) + slidewrite.lint_slide(obj) + check_layout(obj)
        if isinstance(obj, SlideLayout):
            return slidewrite.lint_layout(obj)
    except Exception:
        pass
    return []


# ---- claude CLI provider ---------------------------------------------

def _call_claude_cli(messages: list[dict], workdir: str | None = None,
                     allow_read: bool = False, model: str | None = None) -> str:
    """One-shot: flatten messages into a single prompt for `claude -p`.

    With attachments, run in the upload workdir and allow ONLY the Read tool
    so the model can inspect files (images via vision) before answering.
    """
    parts = []
    for m in messages:
        tag = m["role"].upper()
        parts.append(f"[{tag}]\n{m['content']}")
    prompt = "\n\n".join(parts)
    cmd = [CLAUDE_BIN, "-p", "--model", model or MODEL,
           "--settings", json.dumps({"disableAllHooks": True})]
    if allow_read:
        cmd += ["--allowedTools", "Read"]
    proc = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, timeout=300,
        cwd=workdir or "/tmp",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude cli failed: {proc.stderr[:400]}")
    return proc.stdout


def _attachment_block(manifest: list[dict]) -> str:
    lines = [
        "[ATTACHMENTS]",
        "The user attached the following files. BEFORE designing the deck, "
        "use the Read tool to read EVERY listed path and understand it "
        "(images/SVG: identify the depicted structures, layers, labels, "
        "values; data files: extract the real numbers). Base the deck on the "
        "ACTUAL attachment content — reproduce real layer orders, names and "
        "figures from them instead of inventing generic ones.",
    ]
    for m in manifest:
        if m["read_path"]:
            note = f" ({m['note']})" if m["note"] else ""
            lines.append(f"- {m['name']}{note}: Read \"{m['read_path']}\"")
        else:
            lines.append(f"- {m['name']}: {m['note']}")
    return "\n".join(lines)


# ---- openai-compatible provider --------------------------------------

def _openai_user_content(user_text: str, manifest: list[dict] | None):
    """Build multimodal content parts for a vision-capable OpenAI-compatible
    model (e.g. Qwen3.5-122B-A10B, which is natively multimodal). Images ->
    base64 image_url parts; text-like attachments -> inline text blocks.
    Returns str when no attachments."""
    if not manifest:
        return user_text
    import base64
    from ingest import IMAGE_MIME

    parts: list[dict] = []
    texts: list[str] = []
    for m in manifest:
        if m["kind"] == "image" and m["read_path"]:
            ext = os.path.splitext(m["read_path"])[1].lower()
            mime = IMAGE_MIME.get(ext, "image/png")
            b64 = base64.b64encode(open(m["read_path"], "rb").read()).decode()
            parts.append({"type": "image_url",
                          "image_url": {"url": f"data:{mime};base64,{b64}"}})
            texts.append(f"(첨부 이미지: {m['name']} — 위 이미지 참조)")
        elif m.get("text_path"):
            body = open(m["text_path"], encoding="utf-8",
                        errors="replace").read()[:20000]
            texts.append(f"--- 첨부: {m['name']} ---\n{body}")
        elif m["note"]:
            texts.append(f"--- 첨부: {m['name']} — {m['note']} ---")
    header = ("[ATTACHMENTS] 아래 첨부(이미지 포함)를 먼저 이해하고, 실제 내용"
              "(레이어 순서/명칭/수치)을 반영해 덱을 설계하라. 지어내지 마라.\n\n")
    parts.append({"type": "text",
                  "text": header + "\n\n".join(texts) + "\n\n" + user_text})
    return parts


def _call_openai(messages: list[dict], base_url: str, api_key: str,
                 model: str, json_mode: str, on_partial=None) -> str:
    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key or "EMPTY")
    kwargs: dict = {"model": model, "messages": messages, "temperature": 0.4}
    schema = Deck.model_json_schema()
    if json_mode == "json_schema":
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "deck", "schema": schema, "strict": True},
        }
    elif json_mode == "guided_json":
        kwargs["extra_body"] = {"guided_json": schema}
    elif json_mode == "json_object":
        kwargs["response_format"] = {"type": "json_object"}
    if not on_partial:
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""
    # streaming: accumulate deltas, emit a partial slide each time a new list
    # element closes (throttle — don't parse on every token)
    import stream as _stream
    buf = ""
    closes = 0
    for chunk in client.chat.completions.create(stream=True, **kwargs):
        delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
        if not delta:
            continue
        buf += delta
        nc = buf.count("}") + buf.count("]")
        if nc > closes:
            closes = nc
            sl = _stream.try_partial_slide(buf)
            if sl is not None:
                try:
                    on_partial(sl)
                except Exception:
                    pass
    return buf


# ---- shared entry -----------------------------------------------------

def _provider(stage: str | None = None) -> str:
    """Runtime provider for a stage (config-driven; used for claude_cli checks)."""
    return config.resolve(stage).get("provider")


def _call(messages: list[dict], workdir: str | None = None,
          allow_read: bool = False, stage: str | None = None, on_partial=None) -> str:
    r = config.resolve(stage)
    if r["provider"] == "claude_cli":
        return _call_claude_cli(messages, workdir=workdir, allow_read=allow_read,
                                model=r.get("model"))
    if r["provider"] == "openai":
        return _call_openai(messages, r["base_url"], r.get("api_key", ""),
                            r["model"], r.get("json_mode", "guided_json"),
                            on_partial=on_partial)
    raise RuntimeError("mock provider should not reach _call")


def generate_deck(prompt: str, workdir: str | None = None,
                  manifest: list[dict] | None = None) -> Deck:
    if _use_mock():
        return _mock_deck(prompt)

    user = _kb_block(prompt, ["design", "domain"]) + LAYOUT_USER_TEMPLATE.replace("{prompt}", prompt)
    has_files = bool(manifest and any(m["read_path"] for m in manifest))
    if manifest and _provider("figure") == "claude_cli":
        user_content = _attachment_block(manifest) + "\n\n" + user
    elif manifest:
        # vision-capable OpenAI-compatible model (Qwen3.5-122B-A10B 등):
        # images as base64 parts, text attachments inlined
        user_content = _openai_user_content(user, manifest)
    else:
        user_content = user

    messages = [
        {"role": "system", "content": LAYOUT_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    raw = _call(messages, workdir=workdir, allow_read=has_files, stage="figure")
    try:
        return _refine(Deck.model_validate(_extract_json(raw)))
    except (ValidationError, json.JSONDecodeError) as e:
        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": ("Your output failed validation:\n"
                        f"{str(e)[:1500]}\n\nReturn corrected JSON only."),
        })
        raw2 = _call(messages, workdir=workdir, allow_read=has_files, stage="figure")
        return _refine(Deck.model_validate(_extract_json(raw2)))


def edit_slide(slide_dict: dict, instruction: str, deck_title: str) -> Slide:
    """Apply a natural-language edit to ONE slide; returns the revised Slide."""
    if _use_mock():
        s = Slide.model_validate(slide_dict)
        s.title = f"{s.title} (edited)"
        return s

    user = EDIT_USER_TEMPLATE.format(
        deck_title=deck_title,
        slide_json=json.dumps(slide_dict, ensure_ascii=False),
        instruction=instruction,
    )
    messages = [
        {"role": "system", "content": LAYOUT_SYSTEM + EDIT_APPENDIX},
        {"role": "user", "content": user},
    ]
    raw = _call(messages, stage="fill")
    try:
        return _refine(Slide.model_validate(_extract_json(raw)))
    except (ValidationError, json.JSONDecodeError) as e:
        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": ("Your output failed validation:\n"
                        f"{str(e)[:1200]}\n\nReturn the corrected slide JSON only."),
        })
        raw2 = _call(messages, stage="fill")
        return _refine(Slide.model_validate(_extract_json(raw2)))


# ---- staged workflow --------------------------------------------------

def _validated(model_cls, messages, workdir=None, allow_read=False, refine=False,
               stage=None, on_partial=None):
    """Call, validate, one schema-repair round-trip. When refine=True on a
    Slide/Deck: run deterministic normalize (always) + optional lint fix loop
    (LINT_REPAIR_ROUNDS>0; default 0 → behavior identical to before)."""
    raw = _call(messages, workdir=workdir, allow_read=allow_read, stage=stage,
                on_partial=on_partial)
    try:
        obj = model_cls.model_validate(_coerce_shape(model_cls, _extract_json(raw)))
    except (ValidationError, json.JSONDecodeError) as e:
        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": (f"Your output failed validation:\n{str(e)[:1200]}\n\n"
                        "Return corrected JSON only. Return a SINGLE object with "
                        "top-level \"layout_type\" and \"title\" — do NOT wrap it "
                        "in a \"slides\" array."),
        })
        raw2 = _call(messages, workdir=workdir, allow_read=allow_read, stage=stage)
        obj = model_cls.model_validate(_coerce_shape(model_cls, _extract_json(raw2)))

    if not refine:
        return obj
    _refine(obj)                                   # deterministic, no-op if clean
    for _ in range(LINT_REPAIR_ROUNDS):            # default 0 rounds
        errs = [f for f in _lint_findings(obj) if f.level == "error"]
        if not errs:
            break
        hints = "\n".join(f"- {f.where}: {f.fix_hint or f.message}" for f in errs)
        messages.append({"role": "assistant",
                         "content": json.dumps(obj.model_dump(exclude_none=True),
                                               ensure_ascii=False)})
        messages.append({"role": "user",
                         "content": ("Fix these issues, keep everything else:\n"
                                     + hints + "\nReturn corrected JSON only.")})
        try:
            obj = model_cls.model_validate(_extract_json(
                _call(messages, workdir=workdir, allow_read=allow_read, stage=stage)))
            _refine(obj)
        except (ValidationError, json.JSONDecodeError):
            break
    return obj


def generate_plan(prompt: str, events: list[dict], workdir=None,
                  manifest=None) -> DeckPlan:
    if _use_mock():
        return DeckPlan(title=prompt[:40] or "Untitled", slides=[
            {"layout_type": "title", "title": prompt[:40], "subtitle": "mock"},
            {"layout_type": "figure", "title": "구조 단면도",
             "figure_plan": "FC-BGA 단면: PCB, 볼, 기판, 범프, 다이, 몰드"},
            {"layout_type": "content", "title": "요약",
             "bullets": ["포인트 1", "포인트 2"]},
        ], questions=["대상 청중은 누구인가요? (mock)"])
    user = PLAN_USER_TEMPLATE.format(history=history_block(events), prompt=prompt)
    has_files = bool(manifest and any(m["read_path"] for m in manifest))
    if manifest and _provider("figure") == "claude_cli":
        user = _attachment_block(manifest) + "\n\n" + user
    elif manifest:
        user = _openai_user_content(user, manifest)
    messages = [{"role": "system", "content": PLAN_SYSTEM},
                {"role": "user", "content": user}]
    return _validated(DeckPlan, messages, workdir=workdir, allow_read=has_files, stage="plan")


def revise_plan(plan: DeckPlan, feedback: str, events: list[dict]) -> DeckPlan:
    if _use_mock():
        p = plan.model_copy(deep=True)
        p.questions = []
        p.slides[0].title += " (rev)"
        return p
    user = PLAN_REVISE_TEMPLATE.format(
        history=history_block(events),
        plan_json=json.dumps(plan.model_dump(exclude_none=True), ensure_ascii=False),
        feedback=feedback)
    messages = [{"role": "system", "content": PLAN_SYSTEM},
                {"role": "user", "content": user}]
    return _validated(DeckPlan, messages, stage="plan")


def generate_figure_slide(deck_title: str, title: str, figure_plan: str,
                          events: list[dict]) -> Slide:
    if _use_mock():
        from examples import EXAMPLES
        s = EXAMPLES["fcbga"].slides[0].model_copy(deep=True)
        s.title = title
        return s
    user = _kb_block(f"{title} {figure_plan}", ["domain"]) + FIGURE_USER_TEMPLATE.format(
        history=history_block(events), deck_title=deck_title,
        title=title, figure_plan=figure_plan)
    messages = [{"role": "system", "content": LAYOUT_SYSTEM},
                {"role": "user", "content": user}]
    return _validated(Slide, messages, refine=True, stage="figure")


def revise_figure_slide(deck_title: str, slide_dict: dict, feedback: str,
                        events: list[dict]) -> Slide:
    if _use_mock():
        s = Slide.model_validate(slide_dict)
        s.title += " (rev)"
        return s
    user = FIGURE_REVISE_TEMPLATE.format(
        history=history_block(events), deck_title=deck_title,
        slide_json=json.dumps(slide_dict, ensure_ascii=False),
        feedback=feedback)
    messages = [{"role": "system", "content": LAYOUT_SYSTEM},
                {"role": "user", "content": user}]
    return _validated(Slide, messages, refine=True, stage="figure")


# ---- diagram branching (단면도 2안) ------------------------------------

def generate_diagram_slide(prompt: str, direction: str, events: list[dict],
                           workdir=None, manifest=None, on_partial=None) -> Slide:
    """One infographic figure slide, steered by direction 'A' or 'B'.
    Direction A prefers a deterministic template for known structures
    (template-first); B stays LLM-generated for an alternative take.
    on_partial(slide) is called with progressively-built slides for live preview."""
    if _use_mock():
        from examples import EXAMPLES
        src = EXAMPLES["fcbga" if direction == "A" else "tgv"]
        s = src.slides[0].model_copy(deep=True)
        s.title = f"{prompt[:30]} ({direction})"
        _mock_stream(s, on_partial)
        return s
    # WP7: route the request to candidate kinds → inject only their prompt docs
    hint = router.classify(prompt, manifest)
    ab = router.ab_kinds(hint)
    if ab:                                   # A/B split across two close kinds
        forced = ab[0] if direction == "A" else ab[1]
        other = ab[1] if direction == "A" else ab[0]
        kinds = [forced]
        kind_hint = (f"\nMANDATORY: output figure.kind = \"{forced}\" and NOTHING "
                     f"else. Do not use \"{other}\" or any other kind for this "
                     f"draft, even if the subject suggests it.")
        direction_text = (f"Compose this request STRICTLY as a **{forced}** figure "
                          f"(the {other} framing is the other draft). Faithfully "
                          f"answer the same request.")
    else:
        kinds = router.top_kinds(hint, 3)
        kind_hint = router.kind_hint_text(hint)
        direction_text = DIAGRAM_DIRECTIONS[direction]
    # template-first: canonical structure as the "정석" draft (A), no attachments,
    # only when the request is actually a cross-section/photonic structure
    # (router top) — otherwise a stray keyword like "HBM4E" in a roadmap must
    # NOT hijack a timeline into an HBM stack
    if (direction == "A" and not manifest and not ab
            and hint.ranked[0][0] in ("stack", "photonic")):
        t = _maybe_template(prompt)
        if t is not None:
            return t
    if hint.needs:                           # intake: proceed with stated assumptions
        kind_hint += ("\nNOTE: the request is missing: " + "; ".join(hint.needs)
                      + ". Still produce a useful draft by making reasonable "
                      "assumptions, and state them in the caption prefixed "
                      "'가정: '. Do NOT fabricate precise numbers (dates, measured "
                      "values) — use qualitative placeholders.")
    sysmsg = layout_system(kinds)
    # domain cards ground cross-section facts; design cards ground general
    # infographic authoring (kind choice, chart honesty, table data-ink, ...)
    kb_kinds = ["design", "domain"] if any(
        k not in ("stack", "photonic") for k in kinds) else ["domain"]
    user = _kb_block(prompt, kb_kinds) + _retrieval_block(prompt) + DIAGRAM_USER_TEMPLATE.format(
        history=history_block(events), kind_hint=kind_hint,
        direction=direction_text, prompt=prompt)
    has_files = bool(manifest and any(m["read_path"] for m in manifest))
    if manifest and _provider("figure") == "claude_cli":
        user = _attachment_block(manifest) + "\n\n" + user
    elif manifest:
        user = _openai_user_content(user, manifest)
    messages = [{"role": "system", "content": sysmsg},
                {"role": "user", "content": user}]
    slide = _validated(Slide, messages, workdir=workdir, allow_read=has_files,
                       refine=True, stage="figure", on_partial=on_partial)
    return _ensure_figure(slide, messages, workdir=workdir,
                          allow_read=has_files, stage="figure", prompt=prompt)


def generate_brief_slide(prompt: str, direction: str, events: list[dict],
                         workdir=None, manifest=None):
    """WP8 brief pipeline: understand -> Brief -> compile. For physical requests
    returns (Slide, brief_dict). For infographic, falls back to the WP7 path
    (returns Slide, None). Direction B nudges an alternative interpretation."""
    from understand import understand
    from compile_brief import compile_brief
    # WP9: canonical mobile/watch/photonic ASSEMBLY recipes → template-first for
    # draft A (deterministic, safest for small models); draft B stays LLM.
    asm = None
    if not manifest:
        try:
            from templates import match_structure
            from assemblies import ASSEMBLIES, build_assembly
            asm = next((c for c in match_structure(prompt) if c in ASSEMBLIES), None)
            if direction == "A" and asm:
                return build_assembly(asm), None
        except Exception:
            asm = None
    # The Brief pipeline targets parts-on-substrate optical/mounting ASSEMBLIES.
    # Standard packaging stacks (router top = stack) keep their proven stack/
    # template path; infographics keep WP7. The pipeline intercepts photonic-class
    # requests and anything matching an assembly recipe.
    try:
        if asm is None and router.classify(prompt, manifest).ranked[0][0] != "photonic":
            return generate_diagram_slide(prompt, direction, events, workdir,
                                          manifest), None
    except Exception:
        pass
    p = prompt if direction == "A" else prompt + "\n(대안: 같은 구조를 다른 강조/디테일로)"
    try:
        brief = understand(p, events=events)
    except Exception:
        return generate_diagram_slide(prompt, direction, events, workdir, manifest), None
    if brief.genre == "physical":
        if brief.emphasis == "auto":             # default cross-section unless asked
            brief.emphasis = "section"           # (revise "네트워크 뷰로" -> planar)
        slide = compile_brief(brief)
        if not _figure_empty(slide):
            _verify_adapt(brief, slide)          # WP8 P4: honest unmet surfacing
            return slide, brief.model_dump(exclude_none=True)
    # infographic (or empty physical) → WP7 generation, no brief
    return generate_diagram_slide(prompt, direction, events, workdir, manifest), None


def revise_brief_slide(prior_brief: dict, instruction: str, direction: str,
                       events: list[dict]):
    """WP8: apply a revision to the stored Brief and recompile -> (Slide, brief_dict).
    Returns (None, None) if there is no prior brief (caller falls back to legacy)."""
    if not prior_brief:
        return None, None
    from understand import understand
    from compile_brief import compile_brief
    instr = instruction if direction == "A" else instruction + "\n(대안 구성)"
    try:
        brief = understand(instr, prior_brief=prior_brief, events=events)
        slide = compile_brief(brief)
    except Exception:
        return None, None
    if _figure_empty(slide):
        return None, None
    _verify_adapt(brief, slide)
    return slide, brief.model_dump(exclude_none=True)


def _verify_adapt(brief, slide):
    """WP8 P4: check the compiled figure vs the Brief; surface unmet points."""
    try:
        from critic import critique, annotate_unmet
        annotate_unmet(slide.figure, critique(brief, slide.figure))
    except Exception:
        pass


def revise_diagram_slide(slide_dict: dict, instruction: str, direction: str,
                         events: list[dict], on_partial=None) -> Slide:
    if _use_mock():
        s = Slide.model_validate(slide_dict)
        s.title = f"{s.title} ({direction}rev)"
        _mock_stream(s, on_partial)
        return s
    # inject the current figure's kind doc + kinds the instruction hints at, so a
    # revision can switch kind ("이걸 표로 바꿔줘") yet keep the current kind's rules
    cur_kind = ((slide_dict.get("figure") or {}).get("kind")) if slide_dict else None
    hint = router.classify(instruction)
    kinds = list(dict.fromkeys(([cur_kind] if cur_kind else []) + router.top_kinds(hint, 2)))
    user = DIAGRAM_REVISE_TEMPLATE.format(
        history=history_block(events),
        slide_json=json.dumps(slide_dict, ensure_ascii=False),
        instruction=instruction, direction=REVISE_DIRECTIONS[direction])
    messages = [{"role": "system", "content": layout_system(kinds or None)},
                {"role": "user", "content": user}]
    slide = _validated(Slide, messages, refine=True, stage="figure",
                       on_partial=on_partial)
    return _ensure_figure(slide, messages, workdir=None, allow_read=False,
                          stage="figure")


# ---- single-slide image+text layout -----------------------------------

def _slide_user_content(base_text: str, manifest: list[dict] | None,
                        image_paths: list[str] | None, provider: str = None):
    """Attach images for vision. claude_cli: prepend Read-block (files in cwd);
    openai: base64 image_url parts. Returns str or content-parts list."""
    if not manifest:
        return base_text
    if _provider("fill") == "claude_cli":
        block = "[ATTACHED IMAGES] Read EACH before composing; reference by ref:\n"
        for m in manifest:
            block += f'- ref {m["ref"]}: Read "{m["path"]}"\n'
        return block + "\n" + base_text
    # openai vision: inline base64
    import base64 as _b64
    parts = []
    for m in manifest:
        try:
            b = _b64.b64encode(open(m["path"], "rb").read()).decode()
            parts.append({"type": "image_url",
                          "image_url": {"url": f"data:image/png;base64,{b}"}})
        except Exception:
            pass
    parts.append({"type": "text", "text": base_text})
    return parts


def generate_slide_layout(prompt: str, manifest: list[dict], direction: str,
                          events: list[dict], workdir=None) -> SlideLayout:
    if _use_mock():
        n = len(manifest)
        tmpl = ("image_left_text_right" if direction == "A" else
                ("two_images" if n >= 2 else "hero_title"))
        return SlideLayout(template=tmpl if n else "text_only",
                           title=f"{prompt[:30]} ({direction})",
                           bullets=["mock 항목 1", "mock 항목 2"],
                           images=[{"ref": i, "caption": f"그림 {i}"}
                                   for i in range(min(n, 4))])
    base = _kb_block(prompt, ["design", "domain"]) + SLIDE_USER_TEMPLATE.format(
        history=history_block(events),
        images=slide_image_block(manifest) if manifest else "",
        direction=SLIDE_DIRECTIONS[direction], prompt=prompt)
    content = _slide_user_content(base, manifest, None)
    messages = [{"role": "system", "content": SLIDE_SYSTEM},
                {"role": "user", "content": content}]
    return _validated(SlideLayout, messages, workdir=workdir,
                      allow_read=bool(manifest), stage="fill")


def revise_slide_layout(layout_dict: dict, manifest: list[dict], instruction: str,
                        direction: str, events: list[dict], workdir=None) -> SlideLayout:
    if _use_mock():
        d = dict(layout_dict)
        d["title"] = f"{d.get('title','')} ({direction}rev)"
        return SlideLayout.model_validate(d)
    base = SLIDE_REVISE_TEMPLATE.format(
        history=history_block(events),
        images=slide_image_block(manifest) if manifest else "",
        layout_json=json.dumps(layout_dict, ensure_ascii=False),
        instruction=instruction, direction=SLIDE_REVISE_DIRECTIONS[direction])
    content = _slide_user_content(base, manifest, None)
    messages = [{"role": "system", "content": SLIDE_SYSTEM},
                {"role": "user", "content": content}]
    return _validated(SlideLayout, messages, workdir=workdir,
                      allow_read=bool(manifest), stage="fill")


# ---- mock -------------------------------------------------------------

def _mock_deck(prompt: str) -> Deck:
    from examples import EXAMPLES
    topic = prompt.strip().splitlines()[0][:60] if prompt.strip() else "Untitled"
    base = EXAMPLES["fcbga"].model_copy(deep=True)
    base.title = topic
    return base
