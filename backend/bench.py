"""WP11 — LLM comparison bench: run the real service generation paths across
endpoints, score deterministically (shared with eval_llm), save runs.

Deterministic score is the body (max 80 raw). An optional configurable LLM judge
adds up to 30 (scaled). Off → deterministic normalized to 100.
"""
from __future__ import annotations

import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH_SET = os.path.join(HERE, "..", "tests", "bench_set.jsonl")
BENCH_DIR = os.path.join(HERE, "..", "data", "bench")
os.makedirs(BENCH_DIR, exist_ok=True)

_DET_MAX = 80


def load_cases() -> list[dict]:
    return [json.loads(l) for l in open(BENCH_SET, encoding="utf-8") if l.strip()]


def _findings(slide):
    try:
        from lint import lint_slide
        from geomcheck import check_layout
        import slidewrite
        return lint_slide(slide) + check_layout(slide) + slidewrite.lint_slide(slide)
    except Exception:
        return []


def score_case(case: dict, slide, questions: list, findings: list) -> dict:
    exp = case.get("expect", {}) or {}
    dump = ""
    kind = genre = None
    if slide is not None:
        import json as _j
        dump = _j.dumps(slide.model_dump(exclude_none=True), ensure_ascii=False).lower()
        if slide.figure:
            kind = slide.figure.kind
    p = {}
    p["schema"] = 15 if slide is not None else 0
    ek = exp.get("figure_kind")
    p["kind"] = (10 if (kind == ek) else 0) if ek else 10
    labels = exp.get("must_include_labels", []) or []
    if labels:
        hit = sum(1 for l in labels if l.lower() in dump)
        p["labels"] = round(15 * hit / len(labels))
    else:
        p["labels"] = 15
    mn = exp.get("must_not", []) or []
    viol = sum(1 for m in mn if m.lower() in dump)
    p["must_not"] = max(0, 10 - 5 * viol)
    errs = sum(1 for f in findings if getattr(f, "level", "") == "error")
    warns = sum(1 for f in findings if getattr(f, "level", "") == "warn")
    p["lint"] = max(0, 10 - (10 if errs else 0) - min(4, warns))
    p["geom"] = 5 if errs == 0 else 0
    p["render"] = 5 if slide is not None else 0
    qe = exp.get("questions_expected")
    if qe is not None:
        p["question"] = 10 if bool(questions) == bool(qe) else 0
    else:
        p["question"] = 10 if not questions else 6
    det_raw = sum(p.values())
    return {"breakdown": p, "det_raw": det_raw, "det_max": _DET_MAX,
            "kind": kind, "lint_errors": errs, "lint_warns": warns,
            "asked": bool(questions)}


def _generate(case: dict):
    """Run the actual service path; return (slide, questions)."""
    from llm import generate_brief_slide, generate_slide_layout
    prompt = case["prompt"]
    mode = case.get("mode", "diagram")
    if mode == "slide":
        manifest = [{"kind": "image", "name": "fig.png", "read_path": None,
                     "text_path": None, "note": "cross-section", "ref": 0,
                     "aspect": 16 / 9}]
        sl = generate_slide_layout(prompt, manifest, "A", [])
        from models import Slide
        return (sl if isinstance(sl, Slide) else None), []
    # diagram: compute intake questions like the app does, then generate
    questions = []
    try:
        import router
        questions = list(router.classify(prompt).needs)
        gq = router.genre_question(prompt)
        if gq:
            questions = [gq] + questions
    except Exception:
        pass
    slide, _brief = generate_brief_slide(prompt, "A", [])
    return slide, questions


def run_bench(endpoints: list[str], job_id: str, jobs: dict,
              case_ids=None, categories=None, judge: str | None = None,
              case_timeout: int = 180) -> dict:
    import config
    from render_svg import render_slide_svg
    cases = load_cases()
    if case_ids:
        cases = [c for c in cases if c["id"] in case_ids]
    if categories:
        cases = [c for c in cases if c["category"] in categories]
    run = {"ts": int(time.time()), "endpoints": list(endpoints), "judge": judge or "off",
           "config": config.public(), "cases": {}, "agg": {}}
    total = max(1, len(endpoints) * len(cases))
    done = 0
    for ep in endpoints:
        config.bench_override(ep)
        for c in cases:
            done += 1
            if job_id in jobs:
                jobs[job_id]["progress"] = f"{ep} · {done}/{total} · {c['id']}"
            t0 = time.time()
            try:
                slide, questions = _generate(c)
                findings = _findings(slide) if slide is not None else []
                sc = score_case(c, slide, questions, findings)
                svg = render_slide_svg(slide) if slide is not None else ""
            except Exception as e:
                sc = {"breakdown": {}, "det_raw": 0, "det_max": _DET_MAX,
                      "error": str(e)[:160]}
                svg = ""
            sc["sec"] = round(time.time() - t0, 1)
            sc["score"] = round(sc["det_raw"] / _DET_MAX * 100)   # judge off
            run["cases"].setdefault(c["id"], {"category": c["category"],
                                              "prompt": c["prompt"]})[ep] = {**sc, "svg": svg}
    config.bench_override(None)

    # aggregate: model × category means + overall
    cats = sorted({c["category"] for c in cases})
    for ep in endpoints:
        by_cat = {}
        for cat in cats:
            scores = [run["cases"][cid][ep]["score"]
                      for cid in run["cases"]
                      if run["cases"][cid]["category"] == cat and ep in run["cases"][cid]]
            if scores:
                by_cat[cat] = round(sum(scores) / len(scores))
        overall = round(sum(by_cat.values()) / len(by_cat)) if by_cat else 0
        run["agg"][ep] = {"by_category": by_cat, "overall": overall}

    path = os.path.join(BENCH_DIR, f"run_{run['ts']}.json")
    json.dump(run, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    run["run_id"] = str(run["ts"])
    return run


def list_runs() -> list[dict]:
    out = []
    for fn in sorted(os.listdir(BENCH_DIR), reverse=True):
        if not fn.startswith("run_") or not fn.endswith(".json"):
            continue
        try:
            r = json.load(open(os.path.join(BENCH_DIR, fn), encoding="utf-8"))
            out.append({"run_id": str(r.get("ts")), "ts": r.get("ts"),
                        "endpoints": r.get("endpoints"), "judge": r.get("judge"),
                        "overall": {e: r["agg"].get(e, {}).get("overall")
                                    for e in r.get("endpoints", [])}})
        except Exception:
            continue
    return out


def get_run(run_id: str) -> dict | None:
    path = os.path.join(BENCH_DIR, f"run_{run_id}.json")
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
