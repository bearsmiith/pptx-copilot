"""WP7 — deterministic kind router (pure function, no model).

Ranks figure kinds by keyword/aka signal and flags missing info for intake.
Archetype keywords come from archetypes.ARCHETYPES (single source); the
cross-section / photonic / flow / compare / array keyword sets live here.
The router is a candidate REDUCER — when ambiguous it returns near-ties and
lets the LLM (given the kind docs) make the final call.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from archetypes import ARCHETYPES

# keyword sets for the non-archetype kinds
_KW: dict[str, list[str]] = {
    "stack": ["단면", "적층", "패키지", "패키징", "기판", "substrate", "cross-section",
              "cross section", "레이어", "layer stack", "스택업", "stackup", "bga",
              "fcbga", "cowos", "hbm", "tsv", "rdl", "interposer", "인터포저", "oled",
              "tft", "pcb", "via", "범프", "bump", "솔더", "solder", "wafer", "die",
              "다이", "몰드", "mold", "글라스 코어", "glass core", "fan-out", "fanout",
              "emib", "wirebond", "와이어본드", "적층 구조", "빌드업", "build-up"],
    "photonic": ["광경로", "광 경로", "포토닉", "photonic", "optical path", "waveguide",
                 "도파로", "실리콘 포토닉", "silicon photonics", "레이저", "laser",
                 "photodiode", "포토다이오드", "grating", "mzm", "ring mod",
                 "공동 패키징", "co-packaged", "cpo", "수광", "발광"],
    "flow": ["공정", "프로세스", "process", "절차", "단계별 공정", "step", "순서도",
             "flow", "워크플로", "workflow", "procedure", "파이프라인", "pipeline",
             "process flow"],
    "compare": ["비교", " vs ", "versus", "대비", "장단점", "트레이드오프", "tradeoff",
                "차이점", "a안", "b안"],
    "array": ["어레이", "array", "그리드", "grid", "픽셀 매트릭스", "pixel",
              "디밍", "dimming", "셀 배열", "격자"],
}

_ALL_KINDS = ["stack", "photonic", "flow", "compare", "array",
              "timeline", "kpi", "table", "matrix", "chart", "tree"]

# words that NAME the figure type (intent) — they should outweigh subject nouns
# (a "패키지 구성도" is a tree even though "패키지/HBM/TSV" scream stack)
_INTENT: dict[str, list[str]] = {
    "tree": ["구성도", "계층", "조직도", "분해도", "트리", "breakdown", "hierarchy"],
    "timeline": ["로드맵", "타임라인", "연혁", "일정", "마일스톤", "roadmap", "gantt"],
    "table": ["비교표", "사양표", "스펙 비교", "대비표"],
    "matrix": ["사분면", "2x2", "2×2", "포지셔닝", "우선순위 맵", "포트폴리오 매트릭스"],
    "chart": ["차트", "그래프", "막대그래프", "추이 그래프"],
    "kpi": ["지표 카드", "스코어카드", "대시보드", "요약 카드"],
    "flow": ["순서도", "공정 흐름", "플로우차트", "flowchart"],
    "array": ["배열", "픽셀 매트릭스", "어레이", "디밍존", "디밍 존", "pixel matrix"],
}
_INTENT_BONUS = 6

_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_MODEL = re.compile(r"[a-z]+\d+[a-z0-9]*", re.I)      # hbm4e, ddr5, m2...
# a number acting as a count/ordinal, not a plottable value
_COUNTER = re.compile(r"\d+\s*(?:개|단|차|세대|명|장|번|월|일|년|분기|위|층|"
                      r"q[1-4]|st|nd|rd|th)\b", re.I)
_DATA_FILE = re.compile(r"\.(csv|xlsx?|tsv|json)\b", re.I)


def _series_values(t: str) -> list[str]:
    """Plottable numbers only — strip years, model names (HBM4E), and
    counts/ordinals (5개, 3단계) so they don't masquerade as a data series."""
    s = _MODEL.sub(" ", t)
    s = _YEAR.sub(" ", s)
    s = _COUNTER.sub(" ", s)
    return _NUM.findall(s)


@dataclass
class RouteHint:
    ranked: list                       # [(kind, score, reason)] desc
    needs: list = field(default_factory=list)   # missing info → intake questions
    has_series_data: bool = False


def _kw_for(kind: str) -> list[str]:
    if kind in ARCHETYPES:
        return ARCHETYPES[kind]["aka"]
    return _KW.get(kind, [])


def classify(prompt: str, manifest: list[dict] | None = None) -> RouteHint:
    t = (prompt or "").lower()
    scores: dict[str, int] = {}
    reasons: dict[str, str] = {}
    for kind in _ALL_KINDS:
        s = 0
        hits = []
        for kw in _kw_for(kind):
            k = kw.lower()
            if k and k in t:
                s += len(k.strip())
                hits.append(kw.strip())
        if s:
            scores[kind] = s
            reasons[kind] = ", ".join(dict.fromkeys(hits))[:60]

    # an intent word NAMES the figure type — it should beat subject-noun volume
    # (a "패키지 구성도" is a tree even though 패키지/HBM/TSV scream stack)
    base_max = max(scores.values()) if scores else 0
    for kind, words in _INTENT.items():
        hit = next((w for w in words if w.lower() in t), None)
        if hit:
            scores[kind] = max(scores.get(kind, 0), base_max + 3)
            reasons[kind] = (f"의도어 '{hit}', " + reasons.get(kind, "")).strip(", ")[:60]

    vals = _series_values(t)
    nums = len(vals)
    has_series = nums >= 3                # ≥3 real plottable values present
    if manifest:
        for m in manifest:
            blob = f"{m.get('name', '')} {m.get('note', '')}"
            if _DATA_FILE.search(blob):
                has_series = True
    if has_series:
        scores["chart"] = scores.get("chart", 0) + 8
        reasons.setdefault("chart", "수치 시리즈 감지")

    ranked = sorted(((k, sc, reasons.get(k, "")) for k, sc in scores.items()),
                    key=lambda x: -x[1])
    if not ranked:
        ranked = [("stack", 0, "기본값(단면도 특화)")]

    needs = _needs(ranked[0][0], t, nums, has_series)
    return RouteHint(ranked=ranked, needs=needs, has_series_data=has_series)


def _needs(top: str, t: str, nums: int, has_series: bool) -> list[str]:
    out = []
    if top == "chart" and not has_series:
        out.append("차트로 그릴 실제 수치(카테고리별 값)")
    if top in ("compare", "table") and not _has_multiple_targets(t):
        out.append("비교 대상(2개 이상)")
    if top == "timeline" and nums == 0 and not re.search(
            r"(단계|phase|milestone|마일스톤|q[1-4]|분기|년|월|роад|roadmap)", t):
        out.append("일정 항목 또는 기간")
    if top == "kpi" and nums == 0:
        out.append("표시할 지표 수치")
    if top == "tree" and not re.search(
            r"(구성|모듈|하위|계층|component|module|sub|부품|블록)", t):
        out.append("구성 요소(하위 항목)")
    return out


def _has_multiple_targets(t: str) -> bool:
    return bool(re.search(r"( vs |,|·|/| 및 | 와 | 과 |대\s|비교|여러|각각)", t))


def top_kinds(hint: RouteHint, n: int = 3) -> list[str]:
    return [k for k, _, _ in hint.ranked[:n]]


# WP8 — physical structure vs abstract infographic (the top-level genre split)
_PHYSICAL_KINDS = {"stack", "photonic", "array"}
_INFOGRAPHIC_KINDS = {"timeline", "kpi", "table", "matrix", "chart", "tree"}


def _genre(kind: str) -> str | None:
    if kind in _PHYSICAL_KINDS:
        return "physical"
    if kind in _INFOGRAPHIC_KINDS:
        return "infographic"
    return None                                  # flow/compare are genre-neutral


def genre_question(prompt: str) -> str | None:
    """Return a genre-clarification question when physical-vs-infographic is
    genuinely ambiguous (the top-2 kinds straddle the split with close scores);
    else None. Deterministic — used to ask BEFORE drawing (user decision)."""
    h = classify(prompt)
    ranked = [(k, s, _genre(k)) for k, s, _ in h.ranked if _genre(k)]
    if len(ranked) < 2:
        return None
    (k1, s1, g1), (k2, s2, g2) = ranked[0], ranked[1]
    if g1 != g2 and s1 > 0 and s2 / s1 >= 0.7:
        return ("이 요청을 개념 인포그래픽으로 그릴까요, 아니면 부품 실장 "
                "단면도(물리 구조)로 그릴까요?")
    return None


def kind_hint_text(hint: RouteHint) -> str:
    """The {kind_hint} slot in DIAGRAM_USER_TEMPLATE."""
    k, _, why = hint.ranked[0]
    parts = [f'SUGGESTED KIND: "{k}"' + (f" (근거: {why})" if why else "") + "."]
    if len(hint.ranked) > 1:
        parts.append("Alternatives only if the suggested kind genuinely cannot "
                     "express the request: "
                     + ", ".join(k2 for k2, _, _ in hint.ranked[1:3]) + ".")
    parts.append("Strongly prefer the suggested kind.")
    if not hint.has_series_data:
        parts.append("There is NO numeric data series in this request — do NOT "
                     "use a chart; use kpi/table/timeline/tree as fits.")
    return "\n" + " ".join(parts)


def ab_kinds(hint: RouteHint) -> tuple[str, str] | None:
    """A/B coupling: if the top-2 kinds differ and are close (ratio ≥ 0.6),
    draft A uses kind #1 and draft B uses kind #2 (same content, different form)."""
    if len(hint.ranked) < 2:
        return None
    (k1, s1, _), (k2, s2, _) = hint.ranked[0], hint.ranked[1]
    if k1 != k2 and s1 > 0 and s2 / s1 >= 0.6:
        return (k1, k2)
    return None
