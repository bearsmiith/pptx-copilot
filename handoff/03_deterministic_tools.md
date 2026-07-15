# WP3 — 확정적 코드 도구 + LLM 연동

> 대상 파일(신규): `backend/templates.py`, `backend/lint.py`, `backend/repair.py`,
> `backend/geomcheck.py`, `backend/domain.py`(WP1과 공유). 기존: `backend/llm.py`(루프 연동),
> `backend/models.py`(semantic validator). UI 불변.
> 목표: **LLM이 틀리기 쉬운 부분을 결정적 코드로 흡수**하고, LLM에는 기계검증 가능한
> 피드백만 돌려 "고칠 것만 고치게" 한다. 이것이 소형 모델 신뢰성(WP2)의 하부구조다.

핵심 철학: LLM은 **의미/판단**, 코드는 **geometry·규약·정합성**. 이미 `layout.py`가
geometry를 독점하듯, 규약·정합성도 코드가 독점하고 LLM은 그 결과를 받아 수정만 한다.

---

## 1. 도구 4종 (결정적)

### 1.1 `templates.py` — 파라메트릭 구조 빌더 (소형 모델의 주력)
`domain.STRUCTURES`(WP1 §5)를 입력받아 **확정적으로 full `StackFigure` DSL**을 생성.
LLM은 `structure`名 + 소수 `params`만 낸다(WP2 §2.1). 가장 신뢰성 높은 경로.
```python
def list_templates() -> list[dict]:
    """[{name, aka, params_schema, summary}] — LLM/도구 목록용."""

def instantiate(name: str, params: dict) -> Slide:
    """domain 레시피 + params로 검증된 figure 슬라이드를 결정적으로 생성.
    예: instantiate('hbm', {'n_dram':8,'joint':'ubump'}) ->
        base logic(TSV) + diestack(count=8). 좌표/색 없음(layout이 처리)."""
```
- 파라미터는 안전 범위로 clamp. 미지 param 무시. 결과는 반드시 `models` 검증 통과.
- 커버: fanout_info, hybrid_bond_soic, hbm, cowos_s, cowos_l, emib, glass_core_detailed,
  qfn_wirebond, pop, oled, fcbga, tgv, pcb, tft, microled, miniled (기존+신규 전부).

### 1.2 `lint.py` — 도메인 규약 린터 (기계검증 피드백)
Deck/Slide를 받아 **구조화된 경고 리스트**를 반환. 렌더 전에 돈다.
```python
@dataclass
class Finding:
    level: Literal["error","warn","info"]
    where: str                 # "slide[2].figure.rows[3]"
    code: str                  # "VIA_BALL_MISMATCH"
    message: str               # 사람이 읽는 설명
    fix_hint: str              # LLM repair용 구체 지시 ("set vias.count to 8")

def lint_deck(deck: Deck) -> list[Finding]: ...
def lint_slide(slide: Slide) -> list[Finding]: ...
```
검사 규칙(초안 — `domain.STRUCTURES[x]["rules"]`와 연동):
- `VIA_BALL_MISMATCH`: 인접 balls와 vias count가 정렬 불가(≠, 비정수배) → fix_hint에 목표값.
  (layout `_aligned_via_xs`가 정렬 못 하는 케이스를 사전 경고.)
- `BUMP_TIER_ORDER`: CoWoS류에서 아래→위로 조인트가 점점 작아져야 함(ball→C4→µbump) 위반.
- `UNKNOWN_MATERIAL`: 팔레트에 없는 role → 최근접 제안(repair가 실제 치환).
- `STACK_SANITY`: die가 PCB 아래, mold가 최하단, balls가 두 강체 사이가 아닌 곳 등 물리 위반.
- `THICKNESS_RANGE`: t 비율이 과도(한 layer가 전체의 >70%)면 가독성 경고.
- `LABEL_LEN`: callout 라벨 과길이(래핑 초과 위험) → 축약 제안.
- `MISSING_MUST_LABEL`: 선택 구조의 `must_label`이 없음(예: 팬아웃인데 RDL 라벨 없음).
- `TOO_MANY_ROWS`: stack rows > 8(가독성) / `EMPTY_FIGURE`.
- `FANOUT_HAS_SUBSTRATE`, `HYBRID_USES_BALLS` 등 구조 특이 규칙.

### 1.3 `repair.py` — 결정적 정규화(LLM 전에 자동 수정)
LLM 왕복 없이 **기계적으로 고칠 수 있는 것**은 코드가 먼저 고친다. 소형 모델의
사소한 실수를 흡수해 repair 왕복수↓.
```python
def normalize_deck(deck: Deck) -> tuple[Deck, list[Finding]]:
    """반환: (수정된 deck, 자동수정 로그). 수정 불가한 건 Finding으로 남겨 LLM에 위임."""
```
자동 수정 항목:
- 미지 material → `MATERIAL_ALIAS`(별칭 맵)로 치환(예: "cu"→copper, "abf"→dielectric,
  "si"→silicon, "emc"→mold/emc, "sin"/"sinx"→nitride). 매칭 실패는 `gray` + warn.
- via count를 인접 balls count로 스냅(정렬 가능하게).
- 범위 밖 수치(t, count, width_frac) clamp.
- 빈 라벨/중복 id 보정, width_frac 합 > 0.95면 비례 축소(dies).
- **정책**: repair는 "의미를 바꾸지 않는" 보정만. 구조 재배열 등 의미 변경은 LLM에 넘김.

### 1.4 `geomcheck.py` — 레이아웃 사후 검사
`layout.layout_slide()` 산출물(FigureItem)에서 **실제 배치 문제**를 검출(렌더링 없이 좌표로).
```python
def check_layout(slide: Slide) -> list[Finding]:
    """콜아웃 세로 overflow, 라벨 박스 충돌, 슬라이드 경계 이탈, 도형 겹침 등."""
```
- callout ys가 body 범위를 넘음 / 라벨 간 간격 부족 → "라벨 수 줄이거나 축약" 제안.
- shape가 [0,SLIDE_W]×[0,SLIDE_H] 밖 → geometry 회귀 감지(개발용 가드).
- 이 검사는 **레이아웃 엔진 회귀 테스트**로도 쓴다(신규 row 추가 시 안전망).

---

## 2. LLM 연동 — 두 가지 루프

### 2.1 기본: post-generation validate→repair 루프 (전 provider 공통, 권장 기본값)
guided_json/claude_cli 모두에서 동작. 현재 `_validated`를 확장:
```
raw = _call(...)
obj = extract_json(raw)
1) models 검증 실패 → 기존 repair 왕복(스키마 오류 메시지)
2) 검증 성공 → repair.normalize_deck()로 결정적 보정(+자동수정 로그)
3) lint_deck() + geomcheck() 실행
4) level=="error" 또는 warn 초과 시 → LLM에 **fix_hint를 구체 지시로** 재요청(최대 K회)
   (예: "- rows[3].vias.count=5 → 8 (align to balls above). Return corrected JSON only.")
5) 여전히 error면: 결정적 폴백(가능하면 templates로 최근접 구조 대체) 또는 경고 첨부 후 반환
```
- 소형 모델일수록 2)의 결정적 보정이 왕복을 크게 줄인다.
- K는 모델별로(27B=2, 122b/haiku=1) WP2 라우팅과 연동.

### 2.2 옵션: tool-use 루프 (도구를 지원하는 모델만: haiku, vLLM tool-calling)
LLM에 아래를 **함수 도구**로 노출하고 스스로 호출하게 함:
- `list_templates()`, `instantiate_template(name, params)` — 확정 구조 생성
- `validate_deck(deck_json)` → Findings — 자가 검증
- `lint_deck(deck_json)` → Findings
guided_json과 동시 사용 불가(디코딩 제약 충돌)이므로 **별도 모드**로 둔다.
기본은 2.1, tool-use는 haiku 등에서 선택적. 인터페이스는 2.1과 같은 함수를 재사용.

### 2.3 도구 표면(중요): 얇은 순수 함수로
`templates`/`lint`/`repair`/`geomcheck`는 **부작용 없는 순수 함수**로 만들어
(a)post-gen 루프, (b)tool-use, (c)테스트, (d)오프라인 배치에서 동일하게 재사용.
`app.py`/`llm.py`는 이 함수들을 조립만 한다.

---

## 3. models.py — semantic validator (경량, 스키마 레벨)
pydantic `model_validator`로 **즉시 실패해야 하는** 최소 규칙만(무거운 도메인 규칙은 lint로):
- `DieStackRow.count` 범위(이미 Field), `BondRow.count` 범위.
- `dies` items width_frac 합 상한 경고는 lint로(검증 실패로 만들면 소형 모델이 막힘) —
  **하드 실패는 최소화**하고 대부분 lint/ repair로 흡수(소형 모델 친화).

---

## 4. 파이프라인 배치도 (텍스트)
```
사용자 요청
  └─(WP2 라우팅)→ [PLAN 모델] plan
       └─ 확정 → per figure:
            ├─ template match? ─yes→ [FILL 모델] name+params ─→ templates.instantiate ─┐
            │                                                                          │
            └─ no ─→ [FIGURE/FILL 모델] 자유형 DSL ──────────────────────────────────┤
                                                                                       ▼
                                              repair.normalize (결정적 보정)
                                                        │
                                              lint + geomcheck  ──error/warn초과──→ LLM 재수정(fix_hint) ↺(K회)
                                                        │ ok
                                                        ▼
                                              layout.py → SVG / pptx  (기존 그대로)
```

---

## 5. 수용 기준 (WP3)

1. `templates.instantiate("hbm", {"n_dram":8})`가 LLM 없이 검증된 8단 HBM 슬라이드를 생성.
2. `lint_deck`가 대표 위반(via/ball mismatch, 미지 재료, 팬아웃-substrate)에서 정확한
   `code`+`fix_hint`를 반환(단위테스트로 고정).
3. `repair.normalize_deck`가 "cu"/"abf" 등 별칭을 치환하고 via count를 스냅하며,
   의미를 바꾸는 재배열은 하지 않음.
4. post-gen 루프가 lint error 시 fix_hint를 담아 재요청하고, 성공/폴백으로 수렴.
5. 모든 도구는 순수 함수 — mock provider로도 전 경로 테스트 가능.
6. `geomcheck`가 콜아웃 overflow 케이스를 검출(회귀 테스트 포함).
7. 프론트엔드 diff = 0. 기존 mock 스모크 통과.
