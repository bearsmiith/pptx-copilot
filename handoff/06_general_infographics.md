# WP7 — 범용 인포그래픽 (라우팅 + 신규 DSL + 질문 + 실시간 렌더)

> 대상: **단면도 스튜디오(`/`, dsessions) — figure 1장 단위 흐름.** 슬라이드 그리드 분할(패널
> 컨테이너)은 스코프 아웃(사용자 확정). 신규: `backend/archetypes.py`(범용 아키타입 단일 지식
> 소스), `backend/router.py`(kind 라우팅+intake), `backend/stream.py`(partial JSON→점진 렌더),
> `data/kb/infographic_design.jsonl`. 변경: `models.py`, `layout.py`, `palette.py`, `prompts.py`,
> `llm.py`, `app.py`, `tools.py`, `lint.py`, `repair.py`, `examples.py`, `eval_llm.py`,
> `tests/slide_testset.jsonl`, **`frontend/index.html`(전역 UI-불변 제약의 승인된 예외, §7)**.
>
> 목표: 단면도 특화는 그대로 두고, 단면도가 **아닌** 요청(엔지니어링 리포트향 범용 인포그래픽)
> 에도 같은 파이프라인이 잘 대응하게 한다. 사용자 요구 5개에 1:1 대응한다:
> ① general 인포그래픽 대응(§1) ② 요청 종합 판단→타입 선택(§2) ③ 정보 부족 시 질문(§3)
> ④ 다양한 인포그래픽 지식 세팅(§5) ⑤ 진행 실시간 렌더(§4).

## 0. 아키텍처 레버리지 (왜 이 설계가 싸게 먹히나)

`render_svg.py`와 `export_pptx.py`는 kind를 모른다 — `layout.py`가 반환하는 `FigureItem`의
범용 프리미티브(Rect/Poly/Circle/Edge/Callout/Text)만 소비한다. 따라서 **신규 kind 1개 =
models.py 모델 1개 + layout.py 함수 1개**로 끝나고 SVG 프리뷰와 pptx 내보내기가 자동으로
일치한다(기존 원칙 유지). 마찬가지로 잡 폴링(`/api/job/{id}`, 2.2s)이 이미 있어 실시간 렌더는
"running 응답에 partial SVG 필드 추가"로 구현된다 — 새 전송 채널이 필요 없다.

관통 명제(00_HANDOFF)는 그대로다: 소형 모델은 자유형을 줄일수록 안정된다. WP7의 신규 축은
**"프롬프트도 라우팅된다"** — 지금은 단면도 규약 130줄이 모든 요청에 상주하는데, 이것이 범용
요청에서 단면도 편향을 만든다. kind 문서를 분리해 라우터가 고른 후보의 문서만 주입하면 특화
지식은 조건부가 되고, 프롬프트는 짧아지고, 오선택은 줄어든다.

## 1. 신규 figure kinds — 엔지니어링 리포트향 6종 (`models.py`, `layout.py`)

기존 flow/stack/compare/array/photonic에 추가. 전부 `kind` Literal 태그(guided_json 신뢰성),
좌표·색·물리치수 없음. gantt는 별도 kind로 만들지 않고 timeline의 `phases`로 흡수(kind 수 절제).

```python
class Milestone(BaseModel):
    label: str
    date_label: Optional[str] = None      # "2026 Q3" — 표기용 문자열, 수치 아님
    note: Optional[str] = None
    emphasis: bool = False

class TimelinePhase(BaseModel):           # gantt-lite: 마일스톤 인덱스 스팬 바
    label: str
    start: int = Field(ge=0)              # milestones 인덱스
    end: int = Field(ge=0)

class TimelineFigure(BaseModel):          # 로드맵/연혁/일정
    kind: Literal["timeline"] = "timeline"
    caption: Optional[str] = None
    milestones: list[Milestone] = Field(min_length=3, max_length=8)
    phases: list[TimelinePhase] = Field(default_factory=list, max_length=4)

class KpiItem(BaseModel):
    value: str                            # "99.2%", "1.2 TB/s" — 문자열(단위 포함)
    label: str
    delta: Optional[str] = None           # "+0.8%p"
    tone: Literal["good", "bad", "neutral"] = "neutral"

class KpiFigure(BaseModel):               # 지표 카드 2-6
    kind: Literal["kpi"] = "kpi"
    caption: Optional[str] = None
    items: list[KpiItem] = Field(min_length=2, max_length=6)

class TableFigure(BaseModel):             # 스펙/파라미터 비교표
    kind: Literal["table"] = "table"
    caption: Optional[str] = None
    columns: list[str] = Field(min_length=2, max_length=6)   # 첫 칸 = row 라벨 헤더
    rows: list[list[str]] = Field(min_length=1, max_length=8)
    emphasis_col: Optional[int] = None    # 강조 열(예: 자사/권장안)

class MatrixFigure(BaseModel):            # 2x2 포지셔닝/우선순위
    kind: Literal["matrix"] = "matrix"
    caption: Optional[str] = None
    x_low: str; x_high: str; y_low: str; y_high: str
    quadrants: list["Quadrant"] = Field(min_length=4, max_length=4)
    # 순서 고정: [top_left, top_right, bottom_left, bottom_right]

class Quadrant(BaseModel):
    title: str
    items: list[str] = Field(default_factory=list, max_length=4)

class ChartSeries(BaseModel):
    name: str
    values: list[float] = Field(min_length=2, max_length=8)

class ChartFigure(BaseModel):             # 데이터가 주어졌을 때만 (§2 intake 가드)
    kind: Literal["chart"] = "chart"
    chart_type: Literal["bar", "line"] = "bar"
    caption: Optional[str] = None
    categories: list[str] = Field(min_length=2, max_length=8)
    series: list[ChartSeries] = Field(min_length=1, max_length=3)
    y_label: Optional[str] = None

class TreeNode(BaseModel):
    id: str; label: str
    parent: Optional[str] = None          # None = root(1개), depth ≤ 3, 자식 ≤ 5

class TreeFigure(BaseModel):              # 시스템 분해/조직/BOM 계층
    kind: Literal["tree"] = "tree"
    caption: Optional[str] = None
    nodes: list[TreeNode] = Field(min_length=2, max_length=15)
```

`Figure` Union과 `models.py` docstring의 kind 목록에 6종 추가. (옵션) `ComparePanel.figure`
Union에 `TimelineFigure|KpiFigure|TableFigure` 추가 — 기존 compare가 1단 중첩을 이미
담당하므로 이것만으로 "표+표", "타임라인 A/B" 병치가 열린다. 위험 낮음, 그러나 후순위.

### 1.1 layout.py — 신규 함수 + 공용 헬퍼 (기존 함수 무변경)

회귀 위험을 없애기 위해 **기존 `_layout_*`는 한 줄도 건드리지 않는다**. 신규 헬퍼만 추가:

- `_grid(x, y, w, h, n, cols=None, gap=0.25) -> list[tuple]` — kpi 카드/quadrant 셀 배치.
- `_hband(x, y, w, h, fracs) -> list[tuple]` — timeline 축·phase 바, chart 플롯 영역 분할.
- 신규 디스패치: `_layout_timeline / _layout_kpi / _layout_table / _layout_matrix /
  _layout_chart / _layout_tree` → `layout_figure()`의 kind 분기에 6줄 추가.
- 구성 규약(수치는 archetypes.py에 상수로, §5): timeline = 중앙 수평 축 + 교대 상/하 라벨 +
  emphasis 마일스톤만 accent; kpi = 1행(≤3) 또는 2행 grid, value 큰 글자·delta는 tone 색;
  table = 헤더 행 accent 배경, emphasis_col 열 배경 tint, 셀은 Callout이 아닌 TextItem;
  matrix = 십자축 + 4 셀 + 축 끝 라벨; chart = 값 정규화해 막대/폴리라인 + 축 + 값 라벨,
  그리드선은 `grid` role의 얇은 Rect; tree = 레벨별 수평 밴드, 부모-자식 직교 커넥터.

**렌더러 최소 변경 1건(승인)**: `EdgeShape`(dataclass)에 `arrow: bool = True` 필드 추가.
line 차트 폴리라인과 tree 커넥터는 화살촉이 없어야 한다. `render_svg._figure_svg`의 edge
루프(`marker-end="url(#arrow)"`)와 `export_pptx._add_figure`의 `_add_arrowhead(conn)`
호출부에 각각 한 줄 분기. 그 외 렌더러 diff 없음.

### 1.2 palette.py — semantic 네임스페이스 추가

재료 role과 충돌하지 않는 이름으로 `MATERIALS`에 추가(같은 dict, 같은 메커니즘):

```python
# WP7 general-infographic semantic roles (재료 아님 — 범용 도해용)
"accent1": ("#dbe7fd", "#2f6fed"), "accent2": ("#dff3e7", "#2e9e5b"),
"accent3": ("#fdeeda", "#d97917"), "accent4": ("#f3e3f5", "#a24bb8"),
"accent5": ("#e8eef4", "#5b6472"), "accent6": ("#fde3e4", "#d64550"),
"good": ("#dff3e7", "#2e9e5b"), "bad": ("#fde3e4", "#d64550"),
"warn": ("#fdeeda", "#d97917"), "neutral": ("#eef1f6", "#8a93a0"),
"ink": ("#1f2a44", "#1f2a44"), "grid": ("#eef1f6", "#d7dbe3"),
"track": ("#e3e6ea", "#c3c9d1"),   # timeline 축/gantt 트랙
```

LLM 규약(§2 프롬프트): 범용 kind에서는 material 대신 semantic role만 사용. `repair.py`의
`MATERIAL_ALIAS`에 범용 alias 추가(`"category1"→"accent1"`, `"positive"→"good"`,
`"red"→"bad"` 등 — 색 이름이 와도 색 지정이 아니라 role로 정규화). `DARK_ROLES`에 `ink` 추가.

## 2. 요청 종합 판단 → kind 라우팅 (`router.py`, `prompts.py`, `llm.py`, `tools.py`)

### 2.1 결정적 라우터 — `backend/router.py` (신규, 순수 함수)

```python
@dataclass
class RouteHint:
    ranked: list[tuple[str, float, str]]  # (kind, score, 근거) 내림차순, 상위 2-3만 사용
    needs: list[str]                      # 부족 정보 → §3 질문 후보 (예: "차트에 쓸 수치")
    has_series_data: bool                 # 프롬프트/첨부에 숫자 시리즈 존재

def classify(prompt: str, manifest: list[dict] | None = None) -> RouteHint: ...
```

시그널(아키타입 키워드는 §5 `archetypes.py`가 단일 소스, 라우터는 그걸 소비):
단면/적층/패키지/기판/OLED…→stack, 광경로→photonic, 공정/단계/절차→flow, 로드맵/연혁/
분기/마일스톤→timeline, vs/스펙 비교/사양표→table(대상≥2)·compare, 사분면/포지셔닝/
우선순위 맵→matrix, KPI/핵심 지표/요약 수치→kpi, 추이/증감/시리즈 수치 감지→chart,
구성도/분해/조직/모듈 계층→tree, 그리드/어레이→array. 숫자 시리즈 감지는 정규식
(`\d+(\.\d+)?` 3개 이상 + 구분자/단위 패턴). **모호하면 무리하게 1위를 정하지 않고 동률
후보를 그대로 반환** — 판단은 LLM이 kind 문서를 보고 내린다(라우터는 후보 축소기).

### 2.2 프롬프트 동적 조립 — `prompts.py` 재구성 (핵심)

`LAYOUT_SYSTEM`을 상수 1개에서 **CORE + kind 문서 사전**으로 분해:

```python
LAYOUT_CORE = "..."                      # HARD RULES, 슬라이드 타입, 공통 규약 (~30줄)
FIGURE_KIND_DOCS: dict[str, str] = {     # kind별 DSL 문서 + 미니 예시 (각 15-40줄)
    "stack": "...(기존 stack 문서 + DOMAIN CONVENTIONS + MATERIAL ROLES 전부 이관)...",
    "photonic": "...", "flow": "...", "compare": "...", "array": "...",
    "timeline": "...", "kpi": "...", "table": "...", "matrix": "...",
    "chart": "...", "tree": "...",       # 신규 6종 — archetypes.py 규약 요약 포함
}
def layout_system(kinds: list[str]) -> str:
    """CORE + 선택된 kind 문서만 조립. kinds=None → 전체(하위호환)."""
```

- `llm.generate_diagram_slide/revise_diagram_slide`: `router.classify()` 상위 후보(2-3개)의
  문서만 주입. **단면도 DOMAIN CONVENTIONS·MATERIAL ROLES는 stack/photonic이 후보일 때만
  들어간다** — 범용 요청에서 단면도 편향과 프롬프트 낭비가 함께 사라진다. 비후보 kind는
  한 줄 인덱스로만 알려 잘못된 라우팅에서 LLM이 이탈할 여지를 남긴다:
  `[OTHER KINDS AVAILABLE: timeline(일정/로드맵), table(사양 비교), ...]`.
- `DIAGRAM_USER_TEMPLATE`의 "cross-section diagram" 문구를 "infographic figure"로 일반화하고
  `{kind_hint}` 슬롯 추가(라우터 1위 + 근거).
- deck 흐름(`generate_deck/generate_figure_slide`)도 같은 조립 함수를 쓰되 kinds=None
  기본값으로 **기존과 동일 동작**(하위호환) — deck 쪽 라우팅 적용은 후속.
- revise 경로는 현재 slide의 kind 문서 + 라우터 후보를 함께 주입(“이 요청이면 kind를 바꿔도
  된다”를 허용 — 예: “이걸 표로 바꿔줘”).

### 2.3 A/B 방향과 라우팅 결합 (기존 UI 그대로 학습 신호 획득)

`DIAGRAM_DIRECTIONS` 확장: 라우터 1·2위 kind가 다르고 점수가 근접(비율 ≥0.6)하면 —
**A = 1위 kind로 정석 구성, B = 2위 kind로 같은 내용 재구성** (예: A=timeline, B=table).
점수가 명확하면 기존 의미(A=정석/B=대안 구성) 유지. 사용자의 branch/confirm/export가
telemetry에 kind와 함께 남으므로(§6) **kind 선택 자체가 WP5 학습 신호가 된다** — 시간이
갈수록 retrieve/profile이 이 사용자의 타입 취향을 반영한다. UI 변경 없음.

### 2.4 tools.py — `choose_figure_kind`

`choose_layout`과 동일 패턴의 얇은 도구: `choose_figure_kind(intent: str) -> dict`
(ranked 후보+근거 반환, 내부는 `router.classify`). 기본 모드는 백엔드 자동 주입(post-gen
파이프라인)이고 tool-calling 지원 모델은 직접 호출 가능(WP6 §2.2와 동일한 이원화).

## 3. 정보 부족 시 질문 (intake) — `router.py`, `app.py`, `llm.py`

원칙은 PLAN 스테이지의 questions 규약 재사용: **도해가 실제로 달라질 때만, 0-3개, filler
금지.** dsessions 흐름에 intake를 넣는다:

- 결정적 트리거(`router.classify().needs`): chart 후보인데 수치 없음 / 비교 요청인데 대상
  1개 / timeline인데 항목·기간 없음 / kpi인데 지표 없음 / tree인데 구성요소 없음.
- (옵션, env `INTAKE_LLM=1`) 결정적 트리거가 비었을 때 소형 모델로 1회 확인:
  `DiagramBrief{sufficient: bool, questions: list[str] (≤3), assumptions: list[str]}`.
- **기본은 non-blocking**: 질문이 있어도 초안 A/B를 **가정 명시**와 함께 생성하고
  (caption 또는 노드 instruction에 `가정: ...` 표기), 질문을 payload로 함께 반환한다.
  사용자는 질문에 답해 branch하거나 초안을 바로 수정한다 — 첫 응답 시간을 지키면서
  질문 요구를 충족. `INTAKE_BLOCKING=1`이면 질문만 반환하고 생성 보류(엄격 모드).
- `app.py`: dsession create/branch 잡에서 intake 실행 → `_dsession_payload`에
  `"questions": [...]` 필드 추가(없으면 빈 리스트 — 하위호환). 답변은 새 프롬프트/branch
  instruction으로 들어와 `history_block`(SESSION LOG)을 타고 다음 생성에 반영된다 —
  별도 상태 머신 불필요.
- `frontend/index.html`: payload.questions가 있으면 트리 상단에 질문 배너 1개 렌더
  (§7 승인 예외, ~15줄). 입력은 기존 branch 입력/새 세션 텍스트영역을 그대로 쓴다.

## 4. 실시간 렌더 ("클로드 방식" 점진 프리뷰) — `stream.py`, `llm.py`, `app.py`

생성 토큰이 흐르는 동안 그려지는 모습을 보여준다. 전송은 기존 폴링을 재사용:

- `backend/stream.py` (신규, 순수 함수):
  ```python
  def close_partial(buf: str) -> str      # 열린 문자열/괄호를 보정해 닫음
  def try_partial_slide(buf: str) -> Slide | None
      # close_partial → json.loads → _coerce_shape → Slide.model_validate.
      # 실패하면 None (조용히). figure만 완성됐으면 Slide로 감싸는 관용 처리.
  ```
- `llm.py`: `_call_openai(..., on_delta=None)` — `stream=True`로 델타를 모으며 콜백 호출.
  `_validated(..., on_partial=None)`로 전달. **스로틀**: 매 델타가 아니라 top-level 리스트
  원소(rows/milestones/nodes/items)가 하나 완성될 때만 `try_partial_slide` 시도(원소 수
  카운트 비교). guided_json과 stream 동시 사용은 vLLM에서 지원 — WP2 골든으로 확인.
- provider별: openai=실스트리밍. **mock=행 단위 시뮬레이션**(0.4s 간격으로 rows를 하나씩
  늘리며 partial 콜백 — 프런트 개발/데모가 모델 없이 가능, 가장 먼저 구현). claude_cli=
  2차(옵션): `claude -p --output-format stream-json`으로 동일 콜백 구현 가능한지 확인 후
  적용, 안 되면 progress 텍스트 유지(성능 저하 없음).
- `app.py`: dsession 잡의 A/B 각 스레드가 `on_partial=lambda sl: JOBS[job_id]["partial"][d]
  = render_slide_svg(sl)` (try/except로 감싸 실패 시 직전 partial 유지 — partial은 lint 전
  상태라 방어적이어야 한다). `/api/job/{id}` running 응답에 `"partial": {"A": svg|None,
  "B": svg|None}` 추가(없으면 기존과 동일 — 하위호환).
- `frontend/index.html`: `pollJob`에서 `j.partial`이 있으면 진행 표시 아래에 A/B 라이브
  프리뷰 카드 2장을 그린다(완료 시 제거되고 기존 renderTree가 대체). §7 예외, ~25줄.

렌더 비용: `render_slide_svg`는 순수 파이썬 수 ms — 2.2s 폴링 대비 무시 가능. partial 렌더
실패는 절대 잡을 죽이지 않는다(전부 try/except, 최종 결과 경로는 기존과 동일).

## 5. 지식 세팅 — `archetypes.py`(신규), `data/kb/`, `lint.py`, `examples.py`

### 5.1 `backend/archetypes.py` — 범용 아키타입 단일 지식 소스 (domain.py의 범용판)

domain.py(단면도 레시피)와 대칭 구조. 프롬프트/라우터/린터/예제가 전부 이걸 참조해
문자열 중복·드리프트를 금지한다(전역 제약 그대로):

```python
ARCHETYPES: dict[str, dict] = {
  "timeline": {
    "aka": ["로드맵", "roadmap", "연혁", "일정", "마일스톤", "gantt", "schedule"],
    "when": "시간 순서의 사건/단계/계획. 항목 3-8개.",
    "limits": {"milestones": (3, 8), "phases": (0, 4), "label_chars": 24},
    "rules": ["emphasis는 1-2개만", "date_label은 표기 문자열(수치 창작 금지)",
              "기간 겹침은 phases로"],
    "anti": ["마일스톤 9개 이상(→표로)", "수치 추이(→chart)"],
    "preset": {...},                      # examples.py 프리셋 원본
  },
  "kpi": {...}, "table": {...}, "matrix": {...}, "chart": {...}, "tree": {...},
}
```

### 5.2 kb 카드 — `data/kb/infographic_design.jsonl` (신규, ~20장, Cowork 저작 가능)

kind="design", 기존 카드 스키마 그대로(`kb.py`는 디렉터리 로드라 **코드 무변경**). 내용:
아키타입 선택 가이드(요청 유형→kind 결정 트리, ig-001), 타임라인 밀도·라벨 규칙, 표
data-ink(선 최소화·정렬·강조 열 1개), KPI 카드 수·타이포 위계, 차트 정직성(0-기준선,
축 라벨, 시리즈 ≤3), 2x2 축 명명 규칙, 계층도 폭·깊이 한도, semantic 색 사용 규칙
(accent는 구분, good/bad는 의미 — 장식 금지), 숫자 표기(SI/유효숫자 — sd-014와 상호참조),
"차트 vs KPI vs 표" 판별(시리즈 수·비교 축 수 기준). `llm._kb_block` 호출은 무변경
(design 카드로 검색됨 — 범용 요청 토큰과 자연 매칭).

### 5.3 lint/repair/examples

- `lint.py`: `_lint_timeline/_lint_kpi/...` — archetypes limits 위반(개수·라벨 길이),
  chart 시리즈 길이 ≠ categories 길이(**이건 error** — 렌더 붕괴 방지), tree 고아 노드/
  다중 루트, matrix quadrants ≠ 4. 나머지는 warn + fix_hint(소형 모델 친화 원칙 유지).
- `repair.py`: tree parent 오타를 id 근사 매칭으로 스냅, chart values 문자열 숫자를 float로
  정규화, semantic alias(§1.2).
- `examples.py`: kind별 프리셋 1개(= `ARCHETYPES[*]["preset"]`에서 생성 — domain.py→examples
  패턴과 동일)를 `EXAMPLES`/`EXAMPLE_META`에 추가. 갤러리는 데이터 주도라 UI 변경 없이 노출.

## 6. 학습 루프·평가 연동 (`telemetry`, `eval_llm.py`, `tests/`)

- telemetry: dsession export/branch 기록의 `after` 슬라이드 JSON에 kind가 이미 포함되므로
  스키마 변경 없음. `metrics.py`에 kind별 first-draft 적중률 분해 추가(범용 kind가 실제로
  쓰이는지, 어느 kind가 약한지 관찰 — WP5 북극성 지표의 차원 추가).
- `eval_llm.py` GOLDEN 확장(기존 단면도 5종 유지 + 신규): kind별 1-2케이스 — 예:
  "2026 하반기 HBM4E 양산 로드맵, 분기 마일스톤 6개"(timeline), "FC-BGA vs FO-PLP 스펙
  비교표: 배선폭/두께/비용"(table), "수율 지표 4개 요약 카드"(kpi), "첨부 수치로 세대별
  대역폭 추이"(chart), "패키징 공정 조직 구성도"(tree). 채점: 스키마/기대 kind 일치/
  must_include_labels/lint 임계 — 기존 하니스 재사용.
- **라우팅 골든**(신규, 결정적·모델 불필요): `router.classify` 입출력 30케이스를
  `tests/routing_testset.jsonl`로 — 기대 1위 kind(또는 허용 집합), needs 트리거 여부.
  `smoke_test.py`에서 즉시 실행(빠른 게이트).
- `tests/slide_testset.jsonl`에 범용 케이스 + 질문 트리거 케이스(t-17 패턴) 추가.

## 7. 전역 제약 갱신 (00_HANDOFF의 "위반 금지" 중 1개 항목 예외 승인)

- **UI 불변 예외(승인됨)**: `frontend/index.html` 한정, 두 가지 최소 변경만 —
  ① pollJob의 partial 라이브 프리뷰(§4) ② 질문 배너(§3). 합계 diff ≤ 50줄 목표.
  `slides.html`/`deck.html`/`settings.html`은 **계속 diff = 0**.
- 나머지 전역 제약은 전부 유지: geometry는 `layout.py` 독점(신규 kind 포함), LLM 출력에
  좌표·색·물리치수 금지(semantic role은 색이 아니라 역할), discriminated union 유지,
  domain 지식 단일 소스(단면도=domain.py, 범용=archetypes.py로 대칭 확장), 하드 실패
  최소화(신규 lint도 warn 우선), 신규 env 미설정 시 기존과 100% 동일 동작
  (`INTAKE_*` 기본 non-blocking, 스트리밍은 partial 필드 추가일 뿐).

## 8. 착수 순서 (WP7 내부 의존성)

```
1. archetypes.py + 신규 6 kind(models/layout/palette/repair) + examples 프리셋 + smoke
      └─→ 2. prompts 분해(CORE+kind docs) + router.py + llm 주입 + A/B 결합 + tools
                └─→ 3. intake 질문(needs → payload → index.html 배너)
4. stream.py + mock 시뮬 스트리밍 + JOBS.partial + index.html 프리뷰   ← 1-3과 독립, 병행 가능
5. kb 카드 + lint 확장 + eval/routing 골든 + metrics kind 분해          ← 1·2 이후
```

1은 순수 백엔드라 mock으로 전 경로 검증 가능. 4는 mock 시뮬부터(모델 불필요) → openai
스트리밍 → claude_cli(옵션). 각 단계는 독립 PR 가능, 1→2→3 순 병합 권장.

## 9. 수용 기준 (WP7 완료 정의)

1. 신규 6 kind 프리셋 각각: `python backend/smoke_test.py` 통과 — SVG `<svg` 시작,
   pptx `PK`+>5KB, round-trip, 신규 lint 0 error.
2. 범용 요청(예: 로드맵) 생성 시 시스템 프롬프트에 단면도 DOMAIN CONVENTIONS가 **주입되지
   않고**(로그 확인) 길이가 기존 대비 절반 이하; 단면도 요청은 기존과 동일 품질
   (eval GOLDEN 단면도 5종 무회귀).
3. `tests/routing_testset.jsonl` 30케이스에서 `router.classify` 1위(또는 허용 집합) 적중
   ≥ 90%, filler 질문 0(명확 케이스에서 needs 비어 있음).
4. 정보 부족 골든 케이스(차트+수치 없음 등)에서 payload에 questions 1-3개가 반환되고,
   non-blocking 기본에서 가정 명시 초안이 함께 생성된다. `INTAKE_BLOCKING=1`이면 보류.
5. mock 프로바이더로 dsession 생성 시 `/api/job/{id}` running 응답에 partial SVG가 단계적으로
   나타나고(행 수 증가 관찰 가능) index.html에 라이브 프리뷰가 표시되며, 완료 시 기존 트리
   렌더와 결과가 일치한다. openai(vLLM) 경로에서 guided_json+stream 동작 확인.
6. `eval_llm.py` 확장 케이스에서 kind 일치·라벨 포함 통과, 모델 3종(haiku/122b/27b) 실행
   기록. telemetry에 kind 포함 export 이벤트가 남고 `metrics.py`가 kind별 적중률을 출력.
7. `git diff frontend/`가 index.html 한 파일뿐이고 변경이 §7 두 블록에 국한된다.
   `render_svg.py`/`export_pptx.py` diff는 EdgeShape.arrow 분기 각 1곳뿐이다.

## 참고 (이 저장소 안 근거)

- 렌더러가 kind 무관 프리미티브만 소비: `layout.py` `FigureItem`(shapes/edges/callouts/texts),
  `render_svg.py` `_shape_svg`/`_figure_svg`, `export_pptx.py` `_add_shape`/`_add_figure`.
- 폴링 인프라: `app.py` `JOBS`/`_start_job`/`job_status`, `frontend/index.html` `pollJob`.
- questions 선례: `models.DeckPlan.questions` + `PLAN_SYSTEM`의 "no filler questions" 규약.
- 도구/RAG 선례: `tools.choose_layout`, `kb.block`, `llm._kb_block`/`_retrieval_block`.
- 학습 신호 선례: `telemetry.record`(export/branch), `metrics.py` first-draft 적중률.
