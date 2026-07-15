"""WP2 — provider/model golden eval (model-swap safety net).

Generates representative prompts against the current provider and scores each:
schema-valid, lint-clean, and structure keyword-label presence. Shares its
metric definition with WP5 adapter promotion. Run manually or in CI.

    python eval_llm.py                 (uses current LLM_* env)
    LLM_PROVIDER=mock python eval_llm.py
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from llm import generate_diagram_slide, provider_info          # noqa: E402
from lint import lint_slide                                    # noqa: E402
from geomcheck import check_layout                             # noqa: E402
from domain import STRUCTURES                                  # noqa: E402

GOLDEN = [
    ("HBM 12단 적층 구조 단면도. base die와 TSV 강조.", "hbm", ["dram", "tsv"]),
    ("하이브리드 본딩 SoIC 단면도", "hybrid_bond_soic", ["hybrid", "bond"]),
    ("Fan-out InFO 패키지 단면도", "fanout_info", ["rdl", "mold"]),
    ("FC-BGA 패키지 단면도", None, ["substrate", "ball"]),
    ("TGV 글라스 기판 단면도", None, ["glass", "tgv"]),
    # WP7 general infographic kinds (expected kind checked via _kind_of)
    ("2026 하반기 HBM4E 양산 로드맵, 분기 마일스톤 6개", "timeline", ["양산"]),
    ("FC-BGA vs FO-PLP 스펙 비교표: 배선폭/두께/비용", "table", ["배선"]),
    ("수율/대역폭/전력/사이클타임 핵심 지표 4개 요약 카드", "kpi", []),
    ("세대별 HBM 대역폭 추이 3.6 6.4 9.2 11 GB/s 막대차트", "chart", []),
    ("AI 가속기 패키지 구성 계층도 (로직/메모리/인터포저)", "tree", []),
]

# for GOLDEN rows whose "struct" names a figure kind, we check the produced kind
_EXPECT_KIND = {"timeline", "table", "kpi", "chart", "tree", "matrix"}


def score_one(prompt, must_kw, expect=None):
    t0 = time.time()
    try:
        slide = generate_diagram_slide(prompt, "A", [])
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}
    dump = json.dumps(slide.model_dump(exclude_none=True), ensure_ascii=False).lower()
    lint = lint_slide(slide) + check_layout(slide)
    errs = [f for f in lint if f.level == "error"]
    warns = [f for f in lint if f.level == "warn"]
    kw = {k: (k in dump) for k in must_kw}
    kind = slide.figure.kind if slide.figure else None
    kind_ok = (expect not in _EXPECT_KIND) or (kind == expect)
    return {
        "ok": True, "sec": round(time.time() - t0, 1),
        "kind": kind, "kind_ok": kind_ok,
        "lint_errors": len(errs), "lint_warns": len(warns),
        "kw_hit": sum(kw.values()), "kw_total": len(kw), "kw": kw,
    }


def main():
    print("provider:", provider_info())
    rows = []
    for prompt, struct, kw in GOLDEN:
        r = score_one(prompt, kw, expect=struct)
        rows.append(r)
        ok = r.get("ok") and r.get("lint_errors", 1) == 0 and r.get("kind_ok", True)
        tag = "OK " if ok else "!! "
        km = "" if r.get("kind_ok", True) else f" (want {struct})"
        print(f"  {tag}{prompt[:34]:36} kind={r.get('kind')}{km} "
              f"lint(e/w)={r.get('lint_errors')}/{r.get('lint_warns')} "
              f"kw={r.get('kw_hit')}/{r.get('kw_total')} {r.get('sec','')}s")
    ok = [r for r in rows if r.get("ok")]
    clean = [r for r in ok if r.get("lint_errors") == 0]
    kwrate = (sum(r["kw_hit"] for r in ok) / max(1, sum(r["kw_total"] for r in ok)))
    print(f"\nsummary: {len(ok)}/{len(rows)} generated, {len(clean)}/{len(rows)} "
          f"lint-clean, keyword-label rate {kwrate:.0%}")


# ---- WP6 testset scoring (deterministic gate) ----

TESTSET = os.path.join(os.path.dirname(__file__), "handoff", "tests",
                       "slide_testset.jsonl")


def _dump_text(slide) -> str:
    import json as _j
    return _j.dumps(slide.model_dump(exclude_none=True), ensure_ascii=False).lower()


def score_testset(path: str = TESTSET, limit: int | None = None) -> dict:
    """Deterministic checks per handoff §5.2 (schema/slide_count/labels/must_not/
    lint). Diagram cases only in this harness (single-slide)."""
    import json as _j
    cases = [ _j.loads(l) for l in open(path, encoding="utf-8") if l.strip() ]
    if limit:
        cases = cases[:limit]
    passed = 0
    for c in cases:
        exp = c.get("expect", {})
        try:
            slide = generate_diagram_slide(c["prompt"], "A", [])
        except Exception as e:
            print(f"  !! {c['id']}: gen failed {str(e)[:60]}")
            continue
        dump = _dump_text(slide)
        checks = {}
        labels = exp.get("must_include_labels", [])
        hit = sum(1 for l in labels if any(tok in dump for tok in l.lower().split(" or ")))
        checks["labels"] = f"{hit}/{len(labels)}"
        mn = exp.get("must_not", [])
        viol = [m for m in mn if _viol(m, dump)]
        checks["must_not_viol"] = len(viol)
        fs = lint_slide(slide) + check_layout(slide)
        checks["lint_e"] = sum(1 for f in fs if f.level == "error")
        ok = (hit >= max(1, len(labels) - 1) and not viol and checks["lint_e"] == 0)
        passed += ok
        print(f"  {'OK ' if ok else '!! '}{c['id']:6} labels={checks['labels']} "
              f"must_not_viol={checks['must_not_viol']} lint_e={checks['lint_e']}")
    print(f"\ntestset: {passed}/{len(cases)} passed deterministic gate")
    return {"passed": passed, "total": len(cases)}


def _viol(rule: str, dump: str) -> bool:
    r = rule.lower()
    if "wire bond" in r or "wirebond" in r:
        # actual usage only ('wirebond': false is always present as a field)
        return '"wirebond": true' in dump or "wire bond" in dump
    if "invented dimension" in r or " um" in r or "µm" in r or "dimension" in r:
        import re as _re
        return bool(_re.search(r"\d+\s?(um|µm|nm|gb/s|tb/s)", dump))
    if "substrate" in r:      # e.g. fan-out "no substrate"
        return '"material": "substrate"' in dump
    # generic: require the full distinctive phrase, not any single word
    kws = [w for w in _re_words(r) if len(w) > 4]
    return bool(kws) and all(w in dump for w in kws)


def _re_words(s: str):
    import re as _re
    return _re.split(r"[^a-z0-9]+", s)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "testset":
        score_testset(limit=int(sys.argv[2]) if len(sys.argv) > 2 else None)
    else:
        main()
