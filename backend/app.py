"""FastAPI app: pptx copilot — staged infographic workflow.

Staged flow (원설계):
  1. PLAN    — outline only (layout+text+figure plans), feedback loop,
               LLM may ask clarifying questions
  2. FIGURES — per-figure generation, feedback loop, per-figure confirm
  3. FINAL   — full deck assembled; manual/AI edits + export

Sessions are numbered from 1 and carry a full event log (harness) that every
staged LLM call can reference. All LLM work runs as background jobs with a
progress string (poll /api/job/{id}) — no long-lived HTTP requests.
"""
from __future__ import annotations

import base64
import logging
import os
import threading
import time
import uuid

import re as _re
import uuid as _uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ValidationError

from models import Deck, DeckPlan, Slide, PlanSlide, SlideLayout
from llm import (generate_deck, edit_slide, provider_info,
                 generate_plan, revise_plan,
                 generate_figure_slide, revise_figure_slide)
from render_svg import render_slide_svg
from export_pptx import build_pptx
from truerender import pptx_to_pngs, libreoffice_bin
from examples import EXAMPLES, EXAMPLE_META
from ingest import save_attachments
from sessions import Session, new_session, get_session
import sessions
import dsessions
import slsessions
import telemetry
import config
from llm import (generate_diagram_slide, revise_diagram_slide,
                 generate_brief_slide, revise_brief_slide,
                 generate_slide_layout, revise_slide_layout)

_BRIEF_PIPELINE = os.environ.get("BRIEF_PIPELINE", "").strip() in ("1", "true", "yes")
from slide_render import render_slide_layout_svg, build_slide_pptx
from rasterize import svg_to_png

log = logging.getLogger("uvicorn.error")

app = FastAPI(title="pptx-copilot")

# ---- per-browser anonymous user id (cookie; no UI change) ----
_UID_COOKIE = "ppx_uid"
_UID_RE = _re.compile(r"^[a-f0-9]{24,40}$")


@app.middleware("http")
async def _uid_middleware(request: Request, call_next):
    uid = request.cookies.get(_UID_COOKIE)
    fresh = not (uid and _UID_RE.match(uid))
    if fresh:
        uid = _uuid.uuid4().hex
    telemetry.set_uid(uid)
    response = await call_next(request)
    if fresh:
        response.set_cookie(_UID_COOKIE, uid, max_age=63072000,
                            samesite="lax", path="/")
    return response


def _uid() -> str:
    return telemetry.current_uid()


HERE = os.path.dirname(os.path.abspath(__file__))
CANVAS = os.path.join(HERE, "..", "frontend", "index.html")
SLIDES_UI = os.path.join(HERE, "..", "frontend", "slides.html")
DECK_UI = os.path.join(HERE, "..", "frontend", "deck.html")


# ---------------- payload builders ----------------

def _plan_preview_deck(plan: DeckPlan) -> Deck:
    """Render the outline as a lightweight preview deck (figures = plan text)."""
    slides = []
    for ps in plan.slides:
        if ps.layout_type == "figure":
            slides.append(Slide(layout_type="content", title=ps.title,
                                bullets=[f"[그림 계획] {ps.figure_plan or '(미정)'}"]))
        else:
            slides.append(Slide(layout_type=ps.layout_type, title=ps.title,
                                subtitle=ps.subtitle, bullets=ps.bullets))
    return Deck(title=plan.title, slides=slides)


def _session_payload(s: Session) -> dict:
    sessions.save(s)                       # WP5: persist deck-session state on every change
    deck = s.deck if s.deck else (_plan_preview_deck(s.plan) if s.plan else None)
    return {
        "session_num": s.num,
        "stage": s.stage,
        "plan": s.plan.model_dump(exclude_none=True) if s.plan else None,
        "deck": s.deck.model_dump(exclude_none=True) if s.deck else None,
        "slides_svg": [render_slide_svg(sl) for sl in deck.slides] if deck else [],
        "figure_status": {str(k): v for k, v in s.figure_status.items()},
        "questions": (s.plan.questions if s.plan and s.stage == "plan" else []),
        "history": s.events[-40:],
        "llm": provider_info(),
        "libreoffice": libreoffice_bin() is not None,
    }


# ---------------- jobs ----------------

JOBS: dict[str, dict] = {}
JOB_TTL = 1800


def _gc_jobs():
    now = time.time()
    for k in [k for k, v in JOBS.items() if now - v["created"] > JOB_TTL]:
        JOBS.pop(k, None)


def _start_job(label: str, fn, *args) -> str:
    _gc_jobs()
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": "running", "created": time.time(),
                    "progress": label}
    uid = telemetry.current_uid()          # capture request uid for the thread
    def run():
        telemetry.set_uid(uid)             # propagate into the job thread
        t0 = time.time()
        try:
            payload = fn(job_id, *args)
            JOBS[job_id].update(status="done", payload=payload)
            log.info("[job %s] done %.0fs (%s)", job_id, time.time() - t0, label)
        except Exception as e:
            JOBS[job_id].update(status="error", error=str(e)[:800])
            log.warning("[job %s] FAILED %.0fs (%s): %s", job_id,
                        time.time() - t0, label, str(e)[:300])
    threading.Thread(target=run, daemon=True).start()
    return job_id


@app.get("/api/job/{job_id}")
def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    if job["status"] == "running":
        return {"status": "running", "progress": job.get("progress", ""),
                "elapsed": round(time.time() - job["created"]),
                "partial": job.get("partial", {})}
    if job["status"] == "error":
        return {"status": "error", "error": job["error"]}
    return {"status": "done", **job["payload"]}


# ---------------- static ----------------

@app.get("/", response_class=HTMLResponse)
def index():
    with open(CANVAS, encoding="utf-8") as f:
        return f.read()


@app.get("/editor.js")
def editor_js():
    with open(os.path.join(HERE, "..", "frontend", "editor.js"), encoding="utf-8") as f:
        return Response(content=f.read(), media_type="application/javascript")


@app.get("/slides", response_class=HTMLResponse)
def slides_ui():
    with open(SLIDES_UI, encoding="utf-8") as f:
        return f.read()


@app.get("/deck", response_class=HTMLResponse)
def deck_ui():
    with open(DECK_UI, encoding="utf-8") as f:
        return f.read()


@app.get("/settings", response_class=HTMLResponse)
def settings_ui():
    with open(os.path.join(HERE, "..", "frontend", "settings.html"),
              encoding="utf-8") as f:
        return f.read()


# ---------------- settings / LLM backend config ----------------

@app.get("/api/config")
def get_config():
    return config.public()


class ConfigReq(BaseModel):
    active: str | None = None
    haiku_model: str | None = None
    endpoints: dict | None = None      # {id: {base_url, model, api_key?, json_mode}}
    stage: dict | None = None          # {plan, figure, fill: endpoint_id or ""}


@app.post("/api/config")
def set_config(req: ConfigReq):
    patch = {}
    if req.active is not None:
        patch["active"] = req.active
    if req.haiku_model:
        patch["haiku_model"] = req.haiku_model
    if req.stage is not None:
        patch["stage"] = req.stage
    if req.endpoints is not None:
        # drop empty api_key so it doesn't wipe a stored key (mask round-trip)
        eps = {}
        for eid, ep in req.endpoints.items():
            ep = dict(ep)
            if ep.get("api_key") in (None, ""):
                ep.pop("api_key", None)
            eps[eid] = ep
        patch["endpoints"] = eps
    config.save(patch)
    return config.public()


class TestReq(BaseModel):
    base_url: str
    model: str
    api_key: str | None = None


@app.post("/api/config/test")
def test_endpoint(req: TestReq):
    """Probe an OpenAI-compatible endpoint: connectivity + a tiny completion."""
    if not req.base_url or not req.model:
        raise HTTPException(400, "base_url과 model이 필요합니다")
    try:
        import httpx
        from openai import OpenAI
        client = OpenAI(base_url=req.base_url, api_key=req.api_key or "EMPTY",
                        timeout=httpx.Timeout(15.0, connect=5.0), max_retries=0)
        t0 = time.time()
        resp = client.chat.completions.create(
            model=req.model, max_tokens=8, temperature=0,
            messages=[{"role": "user", "content": 'reply with the word ok'}])
        txt = (resp.choices[0].message.content or "").strip()
        return {"ok": True, "latency": round(time.time() - t0, 2),
                "reply": txt[:40]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


# ---------------- diagram branching sessions (단면도 트리) ----------------

def _dnode_slide(node: dict) -> Slide:
    return Slide.model_validate(node["slide"])


def _partial_cb(job_id: str, d: str):
    """on_partial callback: render the in-progress slide to SVG for live preview.
    Fully defensive — a partial (pre-lint) render must never kill the job."""
    def cb(slide):
        try:
            svg = render_slide_svg(slide)
            JOBS[job_id].setdefault("partial", {})[d] = svg
        except Exception:
            pass
    return cb


def _brief_summary(brief: dict | None) -> dict | None:
    """Compact, human-readable view of a node's Brief IR (WP8 hybrid UX)."""
    if not brief:
        return None
    parts = []
    for p in brief.get("parts", []):
        iface = (p.get("interface") or {}).get("kind")
        parts.append({"name": p.get("name", ""), "function": p.get("function", ""),
                      "mount": iface, "on": p.get("on")})
    return {"genre": brief.get("genre"), "emphasis": brief.get("emphasis"),
            "parts": parts, "base": brief.get("base")}


def _dsession_payload(s: dict) -> dict:
    nodes = []
    for n in s["nodes"]:
        try:
            svg = render_slide_svg(_dnode_slide(n), overrides=n.get("overrides"))
        except Exception as e:
            svg = f"<svg xmlns='http://www.w3.org/2000/svg'></svg><!--{e}-->"
        nodes.append({"id": n["id"], "parent": n["parent"],
                      "instruction": n["instruction"], "ts": n["ts"],
                      "title": n["slide"].get("title", ""), "svg": svg,
                      "brief": _brief_summary(n.get("brief")),
                      "edited": bool(n.get("overrides"))})
    return {"session_num": s["num"], "title": s["title"], "prompt": s["prompt"],
            "nodes": nodes, "llm": provider_info(),
            "questions": s.get("questions", [])}


@app.get("/api/d/sessions")
def d_sessions():
    return {"sessions": dsessions.list_sessions(_uid())}


@app.get("/api/d/session/{num}")
def d_session_get(num: int):
    s = dsessions.load(num)
    if not s or not dsessions.owns(s, _uid()):
        raise HTTPException(404, "unknown session")
    return _dsession_payload(s)


@app.post("/api/d/session")
async def d_session_create(prompt: str = Form(...),
                           files: list[UploadFile] = File(default=[])):
    if not prompt.strip():
        raise HTTPException(400, "empty prompt")
    workdir, manifest = None, None
    if files:
        try:
            pairs = [(f.filename or "file", await f.read()) for f in files]
            workdir, manifest = save_attachments(pairs)
        except ValueError as e:
            raise HTTPException(400, str(e))
    s = dsessions.new_session(prompt, uid=_uid())
    dsessions.log_event(s, "prompt", prompt)
    if manifest:
        dsessions.log_event(s, "attachments",
                            ", ".join(m["name"] for m in manifest))
    # WP7 intake: surface missing info as questions (non-blocking by default)
    import router as _router
    s["questions"] = _router.classify(prompt, manifest).needs
    # WP8 genre gate: if physical-vs-infographic is ambiguous, ASK FIRST (blocking)
    gq = _router.genre_question(prompt) if not manifest else None
    if gq:
        s["questions"] = [gq] + s["questions"]
        dsessions.save(s)
        return {"session_num": s["num"], "questions": s["questions"], "job_id": None}
    if s["questions"] and os.environ.get("INTAKE_BLOCKING", "").strip() in ("1", "true", "yes"):
        dsessions.save(s)                    # hold generation, ask first
        return {"session_num": s["num"], "questions": s["questions"], "job_id": None}
    log.info("[dsession #%d] created prompt=%r", s["num"], prompt[:120])

    def run(job_id):
        results: dict[str, object] = {}
        briefs: dict[str, object] = {}
        def gen(d):
            try:
                if _BRIEF_PIPELINE:              # WP8 understand -> Brief -> compile
                    sl, br = generate_brief_slide(prompt, d, s["events"], workdir, manifest)
                    results[d], briefs[d] = sl, br
                else:
                    results[d] = generate_diagram_slide(
                        prompt, d, s["events"], workdir, manifest,
                        on_partial=_partial_cb(job_id, d))
            except Exception as e:
                results[d] = e
        ths = [threading.Thread(target=gen, args=(d,)) for d in ("A", "B")]
        JOBS[job_id]["progress"] = "초안 2안 병렬 생성 중 (A: 정석 / B: 대안)"
        for t in ths: t.start()
        for t in ths: t.join()
        errs = [d for d in ("A", "B") if isinstance(results[d], Exception)]
        if len(errs) == 2:
            raise RuntimeError(f"both drafts failed: {results['A']}")
        for d in ("A", "B"):
            if isinstance(results[d], Exception):
                dsessions.log_event(s, "error", f"draft {d} failed")
                continue
            node = dsessions.add_node(s, None, f"초안 {d}",
                                      results[d].model_dump(exclude_none=True),
                                      brief=briefs.get(d))
            dsessions.log_event(s, "draft", f"{node['id']} ({d}): "
                                + results[d].title)
        dsessions.save(s)
        return _dsession_payload(s)

    return {"job_id": _start_job(f"dsession#{s['num']} drafts", run),
            "session_num": s["num"]}


class BranchReq(BaseModel):
    node_id: str
    instruction: str


@app.post("/api/d/session/{num}/branch")
def d_branch(num: int, req: BranchReq):
    s = dsessions.load(num)
    if not s:
        raise HTTPException(404, "unknown session")
    base = next((n for n in s["nodes"] if n["id"] == req.node_id), None)
    if not base:
        raise HTTPException(404, "unknown node")
    if not req.instruction.strip():
        raise HTTPException(400, "empty instruction")
    dsessions.log_event(s, "feedback",
                        f"{req.node_id} <- {req.instruction}")
    log.info("[dsession #%d] branch %s: %r", num, req.node_id,
             req.instruction[:120])

    base_brief = base.get("brief")
    def run(job_id):
        results: dict[str, object] = {}
        briefs: dict[str, object] = {}
        def gen(d):
            try:
                if _BRIEF_PIPELINE and base_brief:   # WP8: edit the Brief, recompile
                    sl, br = revise_brief_slide(base_brief, req.instruction, d, s["events"])
                    if sl is not None:
                        results[d], briefs[d] = sl, br
                        return
                results[d] = revise_diagram_slide(
                    base["slide"], req.instruction, d, s["events"],
                    on_partial=_partial_cb(job_id, d))
            except Exception as e:
                results[d] = e
        ths = [threading.Thread(target=gen, args=(d,)) for d in ("A", "B")]
        JOBS[job_id]["progress"] = "수정안 2안 병렬 생성 중 (A: 최소 / B: +개선)"
        for t in ths: t.start()
        for t in ths: t.join()
        errs = [d for d in ("A", "B") if isinstance(results[d], Exception)]
        if len(errs) == 2:
            raise RuntimeError(f"both variants failed: {results['A']}")
        base_ov = base.get("overrides")           # WP10 carry-forward
        for d in ("A", "B"):
            if isinstance(results[d], Exception):
                dsessions.log_event(s, "error", f"variant {d} failed")
                continue
            carried = None
            if base_ov:
                try:
                    from layout import layout_slide
                    from overrides import carry_forward
                    carried, kept, dropped = carry_forward(
                        base_ov, layout_slide(results[d]))
                    dsessions.log_event(s, "overrides",
                                        f"유지 {kept}건 / 폐기 {dropped}건")
                except Exception:
                    carried = None
            node = dsessions.add_node(s, req.node_id,
                                      f"({d}) {req.instruction}",
                                      results[d].model_dump(exclude_none=True),
                                      brief=briefs.get(d), overrides=carried)
            dsessions.log_event(s, "variant", f"{node['id']} from "
                                f"{req.node_id} ({d})")
        dsessions.save(s)
        return _dsession_payload(s)

    return {"job_id": _start_job(f"dsession#{num} branch", run)}


@app.post("/api/d/session/{num}/export/{node_id}")
def d_export(num: int, node_id: str):
    s = dsessions.load(num)
    if not s:
        raise HTTPException(404, "unknown session")
    node = next((n for n in s["nodes"] if n["id"] == node_id), None)
    if not node:
        raise HTTPException(404, "unknown node")
    deck = Deck(title=s["title"], slides=[_dnode_slide(node)])
    ov = [node["overrides"]] if node.get("overrides") else None   # WP10
    dsessions.log_event(s, "export", node_id)
    dsessions.save(s)
    telemetry.record({"session_kind": "diagram", "session_num": num,
                      "action": "export", "accepted": True, "node_id": node_id,
                      "prompt": s.get("prompt"), "after": node["slide"],
                      "provider": provider_info().get("provider"),
                      "model": provider_info().get("model")})
    return Response(
        content=build_pptx(deck, overrides_by_slide=ov),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition":
                 f'attachment; filename="diagram_s{num}_{node_id}.pptx"'})


# ---------------- WP10: canvas editor (edit -> derived node) ----------------

class EditReq(BaseModel):
    node_id: str
    overrides: dict


@app.get("/api/d/session/{num}/node/{node_id}/editable_svg")
def d_editable_svg(num: int, node_id: str):
    s = dsessions.load(num)
    if not s or not dsessions.owns(s, _uid()):
        raise HTTPException(404, "unknown session")
    node = next((n for n in s["nodes"] if n["id"] == node_id), None)
    if not node:
        raise HTTPException(404, "unknown node")
    svg = render_slide_svg(_dnode_slide(node), overrides=node.get("overrides"),
                           editable=True)
    return {"svg": svg, "overrides": node.get("overrides") or {"v": 1, "items": {}, "added": []}}


@app.post("/api/d/session/{num}/edit_node")
def d_edit_node(num: int, req: EditReq):
    s = dsessions.load(num)
    if not s or not dsessions.owns(s, _uid()):
        raise HTTPException(404, "unknown session")
    base = next((n for n in s["nodes"] if n["id"] == req.node_id), None)
    if not base:
        raise HTTPException(404, "unknown node")
    node = dsessions.add_node(s, req.node_id, "(직접 편집)", base["slide"],
                              brief=base.get("brief"), overrides=req.overrides)
    dsessions.log_event(s, "manual_edit", f"{node['id']} from {req.node_id}")
    dsessions.save(s)
    telemetry.record({"session_kind": "diagram", "session_num": num,
                      "action": "manual_edit", "node_id": node["id"]})
    return _dsession_payload(s)


class RecompileReq(BaseModel):
    node_id: str
    brief: dict


@app.post("/api/d/session/{num}/recompile")
def d_recompile(num: int, req: RecompileReq):
    s = dsessions.load(num)
    if not s or not dsessions.owns(s, _uid()):
        raise HTTPException(404, "unknown session")
    if not any(n["id"] == req.node_id for n in s["nodes"]):
        raise HTTPException(404, "unknown node")
    try:
        from brief_model import Brief
        from compile_brief import compile_brief
        slide = compile_brief(Brief.model_validate(req.brief))
    except Exception as e:
        raise HTTPException(400, f"brief compile failed: {str(e)[:200]}")
    node = dsessions.add_node(s, req.node_id, "(Brief 편집)",
                              slide.model_dump(exclude_none=True), brief=req.brief)
    dsessions.log_event(s, "recompile", f"{node['id']} from {req.node_id}")
    dsessions.save(s)
    return _dsession_payload(s)


# ---------------- single-slide sessions (이미지+텍스트 레이아웃) ----------------

def _snode_layout(node: dict) -> SlideLayout:
    return SlideLayout.model_validate(node["layout"])


def _ssession_payload(s: dict) -> dict:
    amap = slsessions.assets_map(s)
    nodes = []
    for n in s["nodes"]:
        try:
            svg = render_slide_layout_svg(_snode_layout(n), amap)
        except Exception as e:
            svg = f"<svg xmlns='http://www.w3.org/2000/svg'></svg><!--{e}-->"
        nodes.append({"id": n["id"], "parent": n["parent"],
                      "instruction": n["instruction"], "ts": n["ts"],
                      "confirmed": n.get("confirmed", False),
                      "layout": n["layout"], "svg": svg})
    return {"session_num": s["num"], "title": s["title"], "prompt": s["prompt"],
            "images": [{"ref": e["ref"], "name": e["name"]} for e in s["images"]],
            "nodes": nodes, "llm": provider_info()}


def _s_gen_two(s, gen_fn, progress):
    """Run generate direction A & B in parallel. gen_fn(direction)->SlideLayout."""
    results: dict[str, object] = {}
    def worker(d):
        try:
            results[d] = gen_fn(d)
        except Exception as e:
            results[d] = e
    ths = [threading.Thread(target=worker, args=(d,)) for d in ("A", "B")]
    for t in ths: t.start()
    for t in ths: t.join()
    if all(isinstance(results[d], Exception) for d in ("A", "B")):
        raise RuntimeError(f"both failed: {results['A']}")
    return results


@app.get("/api/s/sessions")
def s_sessions():
    return {"sessions": slsessions.list_sessions(_uid())}


@app.get("/api/s/session/{num}")
def s_session_get(num: int):
    s = slsessions.load(num)
    if not s or not slsessions.owns(s, _uid()):
        raise HTTPException(404, "unknown session")
    return _ssession_payload(s)


@app.post("/api/s/session")
async def s_session_create(prompt: str = Form(...),
                           files: list[UploadFile] = File(default=[])):
    if not prompt.strip():
        raise HTTPException(400, "empty prompt")
    s = slsessions.new_session(prompt, uid=_uid())
    for f in files:
        data = await f.read()
        if len(data) > 15 * 1024 * 1024:
            raise HTTPException(400, f"{f.filename}: 15MB 초과")
        slsessions.save_upload(s, f.filename or "image", data)
    slsessions.log_event(s, "prompt", prompt)
    slsessions.save(s)
    log.info("[ssession #%d] created prompt=%r imgs=%d", s["num"], prompt[:100],
             len(s["images"]))

    def run(job_id):
        JOBS[job_id]["progress"] = "레이아웃 2안 병렬 생성 중 (A: 표준 / B: 대안)"
        manifest = s["images"]
        wd = slsessions.assets_dir(s["num"])
        res = _s_gen_two(s, lambda d: generate_slide_layout(
            prompt, manifest, d, s["events"], workdir=wd), None)
        for d in ("A", "B"):
            if isinstance(res[d], Exception):
                slsessions.log_event(s, "error", f"draft {d} failed")
                continue
            node = slsessions.add_node(s, None, f"레이아웃 {d}",
                                       res[d].model_dump(exclude_none=True))
            slsessions.log_event(s, "draft", f"{node['id']} ({d}): "
                                 + res[d].template)
        slsessions.save(s)
        return _ssession_payload(s)

    return {"job_id": _start_job(f"ssession#{s['num']} drafts", run),
            "session_num": s["num"]}


class FromDiagramsReq(BaseModel):
    diagram_session: int
    node_ids: list[str]
    prompt: str = ""


@app.post("/api/s/session/from_diagrams")
def s_from_diagrams(req: FromDiagramsReq):
    ds = dsessions.load(req.diagram_session)
    if not ds:
        raise HTTPException(404, "unknown diagram session")
    picks = [n for n in ds["nodes"] if n["id"] in req.node_ids]
    if not picks:
        raise HTTPException(400, "no diagrams selected")
    prompt = req.prompt.strip() or f"첨부한 단면도 {len(picks)}개를 설명하는 슬라이드"
    s = slsessions.new_session(prompt, uid=_uid())
    slsessions.log_event(s, "prompt", prompt)
    slsessions.log_event(s, "source",
                         f"단면도 세션 #{req.diagram_session}에서 {len(picks)}개")
    log.info("[ssession #%d] from diagrams #%d nodes=%s", s["num"],
             req.diagram_session, req.node_ids)

    def run(job_id):
        JOBS[job_id]["progress"] = "단면도를 이미지로 변환 중"
        for n in picks:
            try:
                svg = render_slide_svg(Slide.model_validate(n["slide"]))
                png_path = os.path.join(slsessions.assets_dir(s["num"]),
                                        f"diagram_{n['id']}.png")
                svg_to_png(svg, png_path)
                slsessions.save_png(s, f"diagram_{n['id']}.png",
                                    open(png_path, "rb").read(),
                                    note=f"단면도 {n['id']}")
            except Exception as e:
                slsessions.log_event(s, "error", f"rasterize {n['id']}: {e}")
        slsessions.save(s)
        JOBS[job_id]["progress"] = "레이아웃 2안 병렬 생성 중 (A: 표준 / B: 대안)"
        manifest = s["images"]
        wd = slsessions.assets_dir(s["num"])
        res = _s_gen_two(s, lambda d: generate_slide_layout(
            prompt, manifest, d, s["events"], workdir=wd), None)
        for d in ("A", "B"):
            if isinstance(res[d], Exception):
                continue
            node = slsessions.add_node(s, None, f"레이아웃 {d}",
                                       res[d].model_dump(exclude_none=True))
            slsessions.log_event(s, "draft", f"{node['id']} ({d})")
        slsessions.save(s)
        return _ssession_payload(s)

    return {"job_id": _start_job(f"ssession#{s['num']} from-diagrams", run),
            "session_num": s["num"]}


class SBranchReq(BaseModel):
    node_id: str
    instruction: str


@app.post("/api/s/session/{num}/branch")
def s_branch(num: int, req: SBranchReq):
    s = slsessions.load(num)
    if not s:
        raise HTTPException(404, "unknown session")
    base = slsessions.get_node(s, req.node_id)
    if not base:
        raise HTTPException(404, "unknown node")
    if not req.instruction.strip():
        raise HTTPException(400, "empty instruction")
    slsessions.log_event(s, "feedback", f"{req.node_id} <- {req.instruction}")

    def run(job_id):
        JOBS[job_id]["progress"] = "수정안 2안 병렬 생성 중"
        wd = slsessions.assets_dir(s["num"])
        res = _s_gen_two(s, lambda d: revise_slide_layout(
            base["layout"], s["images"], req.instruction, d, s["events"],
            workdir=wd), None)
        for d in ("A", "B"):
            if isinstance(res[d], Exception):
                continue
            slsessions.add_node(s, req.node_id, f"({d}) {req.instruction}",
                                res[d].model_dump(exclude_none=True))
        slsessions.save(s)
        return _ssession_payload(s)

    return {"job_id": _start_job(f"ssession#{num} branch", run)}


class SConfirmReq(BaseModel):
    node_id: str


@app.post("/api/s/session/{num}/confirm")
def s_confirm(num: int, req: SConfirmReq):
    s = slsessions.load(num)
    if not s:
        raise HTTPException(404, "unknown session")
    node = slsessions.get_node(s, req.node_id)
    if not node:
        raise HTTPException(404, "unknown node")
    for n in s["nodes"]:
        n["confirmed"] = (n["id"] == req.node_id)
    slsessions.log_event(s, "confirm", f"{req.node_id} confirmed")
    slsessions.save(s)
    return _ssession_payload(s)


class SLayoutUpdateReq(BaseModel):
    node_id: str
    layout: dict


@app.post("/api/s/session/{num}/layout_update")
def s_layout_update(num: int, req: SLayoutUpdateReq):
    """Direct edit of a confirmed layout (text fields) — no LLM."""
    s = slsessions.load(num)
    if not s:
        raise HTTPException(404, "unknown session")
    node = slsessions.get_node(s, req.node_id)
    if not node:
        raise HTTPException(404, "unknown node")
    try:
        SlideLayout.model_validate(req.layout)
    except ValidationError as e:
        raise HTTPException(422, f"invalid layout: {e}")
    node["layout"] = req.layout
    slsessions.log_event(s, "edit", f"{req.node_id} manual edit")
    slsessions.save(s)
    return _ssession_payload(s)


@app.post("/api/s/session/{num}/export/{node_id}")
def s_export(num: int, node_id: str):
    s = slsessions.load(num)
    if not s:
        raise HTTPException(404, "unknown session")
    node = slsessions.get_node(s, node_id)
    if not node:
        raise HTTPException(404, "unknown node")
    data = build_slide_pptx(_snode_layout(node), slsessions.assets_map(s))
    slsessions.log_event(s, "export", node_id)
    slsessions.save(s)
    telemetry.record({"session_kind": "slide", "session_num": num,
                      "action": "export", "accepted": True, "node_id": node_id,
                      "prompt": s.get("prompt"), "after": node["layout"],
                      "provider": provider_info().get("provider"),
                      "model": provider_info().get("model")})
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition":
                 f'attachment; filename="slide_s{num}_{node_id}.pptx"'})


# ---------------- stage 1: plan ----------------

@app.post("/api/session")
async def create_session(prompt: str = Form(...),
                         files: list[UploadFile] = File(default=[])):
    if not prompt.strip():
        raise HTTPException(400, "empty prompt")
    workdir, manifest = None, None
    if files:
        try:
            pairs = [(f.filename or "file", await f.read()) for f in files]
            workdir, manifest = save_attachments(pairs)
        except ValueError as e:
            raise HTTPException(400, str(e))
    s = new_session(prompt, workdir, manifest, uid=_uid())
    s.log("prompt", prompt, "plan")
    if manifest:
        s.log("attachments", ", ".join(m["name"] for m in manifest), "plan")
    log.info("[session #%d] created prompt=%r files=%d", s.num, prompt[:120],
             len(manifest or []))

    def run(job_id):
        JOBS[job_id]["progress"] = "계획(아웃라인) 생성 중"
        plan = generate_plan(s.prompt, s.events, s.workdir, s.manifest)
        s.plan = plan
        s.log("plan", f"{len(plan.slides)} slides: "
              + " / ".join(f"[{p.layout_type}] {p.title}" for p in plan.slides))
        if plan.questions:
            s.log("question", " | ".join(plan.questions))
        return _session_payload(s)

    return {"job_id": _start_job(f"session#{s.num} plan", run),
            "session_num": s.num}


@app.get("/api/session/{num}")
def session_state(num: int):
    s = get_session(num)
    if not s or not sessions.owns(s, _uid()):
        raise HTTPException(404, "unknown session")
    return _session_payload(s)


class FeedbackReq(BaseModel):
    message: str


@app.post("/api/session/{num}/plan_feedback")
def plan_feedback(num: int, req: FeedbackReq):
    s = get_session(num)
    if not s or not s.plan:
        raise HTTPException(404, "unknown session/plan")
    if s.stage != "plan":
        raise HTTPException(400, "plan already confirmed")
    s.log("feedback", req.message, "plan")
    log.info("[session #%d] plan feedback: %r", num, req.message[:120])

    def run(job_id):
        JOBS[job_id]["progress"] = "계획 수정 중"
        s.plan = revise_plan(s.plan, req.message, s.events)
        s.log("plan", "revised: "
              + " / ".join(f"[{p.layout_type}] {p.title}" for p in s.plan.slides))
        return _session_payload(s)

    return {"job_id": _start_job(f"session#{num} plan-revise", run)}


class PlanEditReq(BaseModel):
    plan: dict


@app.post("/api/session/{num}/plan_update")
def plan_update(num: int, req: PlanEditReq):
    """Direct (form-based) plan edit — no LLM."""
    s = get_session(num)
    if not s:
        raise HTTPException(404, "unknown session")
    if s.stage != "plan":
        raise HTTPException(400, "plan already confirmed")
    try:
        s.plan = DeckPlan.model_validate(req.plan)
    except ValidationError as e:
        raise HTTPException(422, f"invalid plan: {e}")
    s.log("plan_edit", "manual plan edit")
    return _session_payload(s)


@app.post("/api/session/{num}/confirm_plan")
def confirm_plan(num: int):
    s = get_session(num)
    if not s or not s.plan:
        raise HTTPException(404, "unknown session/plan")
    if s.stage != "plan":
        raise HTTPException(400, "already confirmed")
    s.stage = "figures"
    s.log("confirm", "plan confirmed", "plan")
    log.info("[session #%d] plan confirmed -> figures", num)

    def run(job_id):
        # assemble deck: text slides directly, figure slides via LLM
        fig_slides = [(i, ps) for i, ps in enumerate(s.plan.slides)
                      if ps.layout_type == "figure"]
        slides: list[Slide] = []
        done = 0
        for i, ps in enumerate(s.plan.slides):
            if ps.layout_type == "figure":
                done += 1
                JOBS[job_id]["progress"] = \
                    f"그림 생성 중 ({done}/{len(fig_slides)}): {ps.title}"
                sl = generate_figure_slide(s.plan.title, ps.title,
                                           ps.figure_plan or ps.title, s.events)
                sl.layout_type = "figure"
                sl.title = sl.title or ps.title
                slides.append(sl)
                s.figure_status[i] = "draft"
                s.log("figure", f"slide {i+1} '{ps.title}' generated "
                      f"(kind={sl.figure.kind if sl.figure else '?'})", "figures")
            else:
                slides.append(Slide(layout_type=ps.layout_type, title=ps.title,
                                    subtitle=ps.subtitle, bullets=ps.bullets))
        s.deck = Deck(title=s.plan.title, slides=slides)
        return _session_payload(s)

    return {"job_id": _start_job(f"session#{num} figures", run)}


# ---------------- stage 2: figures ----------------

class FigureFeedbackReq(BaseModel):
    slide_index: int
    message: str


@app.post("/api/session/{num}/figure_feedback")
def figure_feedback(num: int, req: FigureFeedbackReq):
    s = get_session(num)
    if not s or not s.deck:
        raise HTTPException(404, "unknown session/deck")
    i = req.slide_index
    if not (0 <= i < len(s.deck.slides)) or i not in s.figure_status:
        raise HTTPException(400, "not a figure slide")
    s.log("feedback", f"slide {i+1}: {req.message}", "figures")
    log.info("[session #%d] figure %d feedback: %r", num, i, req.message[:120])

    def run(job_id):
        JOBS[job_id]["progress"] = f"그림 {i+1} 수정 중"
        sl = revise_figure_slide(
            s.deck.title, s.deck.slides[i].model_dump(exclude_none=True),
            req.message, s.events)
        s.deck.slides[i] = sl
        s.figure_status[i] = "draft"
        s.log("figure", f"slide {i+1} revised", "figures")
        return _session_payload(s)

    return {"job_id": _start_job(f"session#{num} fig-revise", run)}


class FigureConfirmReq(BaseModel):
    slide_index: int


@app.post("/api/session/{num}/figure_confirm")
def figure_confirm(num: int, req: FigureConfirmReq):
    s = get_session(num)
    if not s or not s.deck:
        raise HTTPException(404, "unknown session/deck")
    if req.slide_index not in s.figure_status:
        raise HTTPException(400, "not a figure slide")
    s.figure_status[req.slide_index] = "confirmed"
    s.log("confirm", f"figure slide {req.slide_index+1} confirmed", "figures")
    if all(v == "confirmed" for v in s.figure_status.values()):
        s.stage = "final"
        s.log("confirm", "all figures confirmed -> final", "figures")
        log.info("[session #%d] all figures confirmed -> final", num)
    return _session_payload(s)


# ---------------- stage 3: final (edits + export) ----------------

class SlideEditReq(BaseModel):
    slide_index: int
    instruction: str


@app.post("/api/session/{num}/slide_edit")
def slide_edit(num: int, req: SlideEditReq):
    """Natural-language edit of any slide (available in figures/final stage)."""
    s = get_session(num)
    if not s or not s.deck:
        raise HTTPException(404, "unknown session/deck")
    i = req.slide_index
    if not (0 <= i < len(s.deck.slides)):
        raise HTTPException(400, "slide_index out of range")
    s.log("feedback", f"slide {i+1}: {req.instruction}")
    log.info("[session #%d] slide %d edit: %r", num, i, req.instruction[:120])

    def run(job_id):
        JOBS[job_id]["progress"] = f"슬라이드 {i+1} 수정 중"
        s.deck.slides[i] = edit_slide(
            s.deck.slides[i].model_dump(exclude_none=True),
            req.instruction, s.deck.title)
        if i in s.figure_status:
            s.figure_status[i] = "draft"
            if s.stage == "final":
                s.stage = "figures"
        s.log("edit", f"slide {i+1} edited")
        return _session_payload(s)

    return {"job_id": _start_job(f"session#{num} slide-edit", run)}


class DeckUpdateReq(BaseModel):
    deck: dict


@app.post("/api/session/{num}/deck_update")
def deck_update(num: int, req: DeckUpdateReq):
    """Direct deck JSON edit — no LLM."""
    s = get_session(num)
    if not s or not s.deck:
        raise HTTPException(404, "unknown session/deck")
    try:
        s.deck = Deck.model_validate(req.deck)
    except ValidationError as e:
        raise HTTPException(422, f"invalid deck: {e}")
    s.log("edit", "manual deck edit")
    return _session_payload(s)


@app.post("/api/session/{num}/export")
def session_export(num: int):
    s = get_session(num)
    if not s or not s.deck:
        raise HTTPException(404, "no deck to export")
    s.log("export", "pptx exported")
    sessions.save(s)
    telemetry.record({"session_kind": "deck", "session_num": num,
                      "action": "export", "accepted": True,
                      "prompt": s.prompt, "after": s.deck.model_dump(exclude_none=True),
                      "provider": provider_info().get("provider"),
                      "model": provider_info().get("model")})
    return Response(
        content=build_pptx(s.deck),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition":
                 f'attachment; filename="deck_s{num}.pptx"'})


@app.post("/api/session/{num}/truerender")
def session_truerender(num: int):
    s = get_session(num)
    if not s or not s.deck:
        raise HTTPException(404, "no deck")
    try:
        pngs = pptx_to_pngs(build_pptx(s.deck))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return {"images": [base64.b64encode(p).decode() for p in pngs]}


# ---------------- gallery (loads as a final-stage session) ----------------

@app.get("/api/examples")
def examples_list():
    return {"examples": [{"name": n, "label": l} for n, l in EXAMPLE_META]}


@app.post("/api/example/{name}")
def example_load(name: str):
    deck = EXAMPLES.get(name)
    if not deck:
        raise HTTPException(404, "unknown example")
    s = new_session(f"(gallery) {name}", uid=_uid())
    s.deck = deck.model_copy(deep=True)
    s.stage = "final"
    for i, sl in enumerate(s.deck.slides):
        if sl.figure:
            s.figure_status[i] = "confirmed"
    s.log("gallery", f"loaded example '{name}'", "final")
    return _session_payload(s)
