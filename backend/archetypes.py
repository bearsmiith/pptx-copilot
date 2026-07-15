"""WP7 — general-infographic archetype knowledge (single source).

Symmetric to domain.py (cross-section recipes): prompts, router, linter and
examples all reference THIS, so keyword lists / limits / rules / presets are
defined once. Each archetype maps to one figure `kind` in models.py.

  aka     — trigger keywords (router consumes these; do not duplicate elsewhere)
  when    — one-line "use this when" for the LLM
  limits  — hard counts the linter enforces (min,max) + label_chars
  rules   — authoring do's (injected into the kind prompt doc)
  anti    — "use a different kind instead" cases
  preset  — a valid figure dict (examples.py builds a Slide from it)
"""
from __future__ import annotations

from models import Slide


ARCHETYPES: dict[str, dict] = {
    "timeline": {
        "aka": ["로드맵", "roadmap", "연혁", "일정", "타임라인", "timeline",
                "마일스톤", "milestone", "gantt", "간트", "schedule", "history",
                "phase", "단계별 일정"],
        "when": "Events/steps/plans in time order. 3-8 items.",
        "limits": {"milestones": (3, 8), "phases": (0, 4), "label_chars": 26},
        "rules": ["emphasize only 1-2 milestones",
                  "date_label is a display string — never invent numbers",
                  "overlapping spans go in `phases` (start/end are milestone indices)"],
        "anti": ["9+ milestones (use a table)", "numeric trends (use a chart)"],
        "preset": {
            "kind": "timeline",
            "caption": "HBM4E 양산 로드맵 (예시)",
            "milestones": [
                {"label": "샘플 출하", "date_label": "2026 Q1"},
                {"label": "설계 확정", "date_label": "2026 Q2"},
                {"label": "리스크 양산", "date_label": "2026 Q3", "emphasis": True},
                {"label": "인증 완료", "date_label": "2026 Q4"},
                {"label": "양산 램프업", "date_label": "2027 Q1"},
                {"label": "2세대 착수", "date_label": "2027 Q2"},
            ],
            "phases": [
                {"label": "개발", "start": 0, "end": 1},
                {"label": "양산 준비", "start": 2, "end": 4},
            ],
        },
    },
    "kpi": {
        "aka": ["kpi", "지표", "핵심 지표", "요약 수치", "metric", "지표 카드",
                "성과", "summary numbers", "대시보드", "스코어카드", "scorecard"],
        "when": "A few headline metrics to summarize status. 2-6 cards.",
        "limits": {"items": (2, 6), "label_chars": 28},
        "rules": ["value is a string WITH its unit (\"1.2 TB/s\", \"99.2%\")",
                  "tone good/bad/neutral drives the delta color — set it honestly",
                  "delta is optional; omit if there is no baseline"],
        "anti": ["a full series over time (use a chart)",
                 "multi-dimension comparison (use a table)"],
        "preset": {
            "kind": "kpi",
            "caption": "패키징 라인 요약 지표 (예시)",
            "items": [
                {"value": "99.2%", "label": "수율", "delta": "+0.8%p", "tone": "good"},
                {"value": "1.2 TB/s", "label": "대역폭", "tone": "neutral"},
                {"value": "12 W", "label": "패키지 전력", "delta": "+1.5 W", "tone": "bad"},
                {"value": "48h", "label": "사이클 타임", "delta": "-6h", "tone": "good"},
            ],
        },
    },
    "table": {
        "aka": ["표", "table", "비교표", "사양표", "스펙 비교", "spec comparison",
                "parameter", "파라미터", "vs", "대비표", "매트릭스 표"],
        "when": "Compare 2+ options across several attributes. Grid of text.",
        "limits": {"columns": (2, 6), "rows": (1, 8), "label_chars": 30},
        "rules": ["first column is the row-label header",
                  "emphasis_col highlights one column (our option / recommendation)",
                  "keep cell text terse — a value or short phrase, not a sentence"],
        "anti": ["a single option (use kpi)", "numeric trend (use a chart)"],
        "preset": {
            "kind": "table",
            "caption": "패키지 기술 비교 (예시)",
            "columns": ["항목", "FC-BGA", "FO-PLP", "Glass Core"],
            "rows": [
                ["최소 배선폭", "10 µm", "5 µm", "2 µm"],
                ["코어 두께", "800 µm", "코어리스", "400 µm"],
                ["휨(warpage)", "중", "고", "저"],
                ["상대 비용", "1.0x", "0.8x", "1.4x"],
            ],
            "emphasis_col": 3,
        },
    },
    "matrix": {
        "aka": ["2x2", "사분면", "quadrant", "포지셔닝", "positioning",
                "우선순위 맵", "priority", "매트릭스", "matrix", "bcg", "포트폴리오"],
        "when": "Position items on two axes into four quadrants.",
        "limits": {"items_per_quadrant": (0, 4), "label_chars": 24},
        "rules": ["name both axis ends (x_low/x_high, y_low/y_high)",
                  "quadrants order is fixed: top-left, top-right, bottom-left, bottom-right",
                  "≤4 items per quadrant, terse labels"],
        "anti": ["a ranked list (use a table)", "time order (use a timeline)"],
        "preset": {
            "kind": "matrix",
            "caption": "기술 투자 우선순위 (예시)",
            "x_low": "구현 난이도 낮음", "x_high": "구현 난이도 높음",
            "y_low": "임팩트 낮음", "y_high": "임팩트 높음",
            "quadrants": [
                {"title": "우선 추진", "items": ["하이브리드 본딩", "글라스 코어"]},
                {"title": "전략 과제", "items": ["백사이드 파워"]},
                {"title": "빠른 성과", "items": ["패널 레벨 FO"]},
                {"title": "보류", "items": ["신규 몰드 소재"]},
            ],
        },
    },
    "chart": {
        "aka": ["차트", "chart", "그래프", "graph", "추이", "trend", "증감",
                "막대", "bar", "라인", "line", "시계열", "시리즈", "series"],
        "when": "Show numeric values across categories. ONLY when real numbers exist.",
        "limits": {"categories": (2, 8), "series": (1, 3), "label_chars": 16},
        "rules": ["bar for comparison, line for trend over ordered categories",
                  "every series length must equal categories length",
                  "do not fabricate numbers — if none given, ask (intake) or use kpi"],
        "anti": ["no real numbers (use kpi/table)", "one value per item (use kpi)"],
        "preset": {
            "kind": "chart",
            "chart_type": "bar",
            "caption": "세대별 HBM 대역폭 (예시)",
            "y_label": "GB/s",
            "categories": ["HBM2E", "HBM3", "HBM3E", "HBM4"],
            "series": [
                {"name": "핀당 속도", "values": [3.6, 6.4, 9.2, 11.0]},
            ],
        },
    },
    "tree": {
        "aka": ["구성도", "분해", "조직도", "org", "계층", "hierarchy", "tree",
                "트리", "bom", "모듈 구성", "breakdown", "시스템 구성", "block diagram"],
        "when": "Hierarchical decomposition: system→modules, org, BOM. depth ≤3.",
        "limits": {"nodes": (2, 15), "depth": (1, 3), "children": (0, 5),
                   "label_chars": 24},
        "rules": ["exactly one root (parent=None)", "depth ≤ 3, ≤5 children per node",
                  "each node id unique; parent must reference an existing id"],
        "anti": ["a flat list (use kpi/table)", "a process with arrows (use flow)"],
        "preset": {
            "kind": "tree",
            "caption": "AI 가속기 패키지 구성 (예시)",
            "nodes": [
                {"id": "pkg", "label": "AI 가속기 패키지"},
                {"id": "logic", "label": "로직 다이 (GPU)", "parent": "pkg"},
                {"id": "mem", "label": "메모리 서브시스템", "parent": "pkg"},
                {"id": "intp", "label": "인터포저 (CoWoS)", "parent": "pkg"},
                {"id": "hbm1", "label": "HBM 스택 ×6", "parent": "mem"},
                {"id": "phy", "label": "메모리 PHY", "parent": "mem"},
                {"id": "tsv", "label": "TSV / RDL", "parent": "intp"},
            ],
        },
    },
}


def all_names() -> list[str]:
    return list(ARCHETYPES)


def build_archetype(name: str) -> Slide:
    """Build a validated figure Slide from an archetype preset."""
    a = ARCHETYPES[name]
    fig = dict(a["preset"])
    title = a.get("title") or _default_title(name, a)
    return Slide.model_validate(
        {"layout_type": "figure", "title": title, "figure": fig})


def _default_title(name: str, a: dict) -> str:
    cap = a["preset"].get("caption") or name
    # strip a trailing "(예시)" for the slide title
    return cap.replace(" (예시)", "").strip() or name.capitalize()
