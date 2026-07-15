# WP5 — 사용자 기록 축적 + 학습 루프 (적중률 향상)

> 대상 파일(신규): `backend/telemetry.py`, `backend/corpus.py`, `backend/profile.py`,
> `backend/retrieve.py`, `backend/metrics.py`, `train/*`(오프라인 스텁), `data/interactions/`,
> `data/learning/`. 기존: `backend/app.py`(캡처 훅), `backend/llm.py`(검색·프로필 주입),
> `backend/sessions.py`(영속화). UI 불변.
> 목표: 사용자와의 상호작용에서 **암묵적 정답/선호 신호**를 축적하고, 이를 (1) 즉시 검색
> 주입, (2) 주기적 미세튜닝, (3) 결정적 규칙 채굴로 되먹여 **첫 초안 적중률(first-draft
> acceptance)** 을 시간이 갈수록 끌어올린다.

핵심 명제: **"우리는 이미 정답을 받고 있다."** 사용자가 A/B 중 하나를 고르고, 피드백으로
고치고, confirm/export하는 모든 순간이 라벨이다. 새 UI 없이 이 신호를 저장·정제·환류만 하면 된다.

---

## 0. 이미 있는 신호 (그대로 활용)

| 소스 | 구조 | 학습 신호 |
|------|------|-----------|
| `dsessions/*.json`(영속) | 트리: `node{id,parent,instruction,slide}`, events(draft/variant/**export**) | parent→child = (수정 전 slide, instruction)→(수정 후 slide) SFT 쌍. 형제 A/B = DPO 쌍. export = 강한 positive |
| `slsessions/*.json`(영속) | `node{parent,instruction,confirmed,layout}` | `confirmed`=명시적 채택, export=positive, parent/instruction=수정 쌍 |
| 메인 세션(`sessions.py`, **in-memory**) | `plan`,`deck`,`figure_status{idx:draft|confirmed}`,`events` | plan_feedback=계획 교정, figure_feedback=도형 교정, slide_edit=수동 정답, export=최종 채택 |
| A/B 방향 | `DIAGRAM_DIRECTIONS`/`SLIDE_DIRECTIONS` A(정석)/B(대안) | 어느 방향이 채택되나 = 방향 선호 |
| WP3 lint/repair | Findings, repair 왕복수 | 반복 오류 패턴 = 규칙 채굴 후보 |

**갭**: 메인 스테이지 세션은 디스크에 남지 않는다(재시작 시 소실, 150개 캡). → §1에서 영속화.
`slide` JSON만 저장하면 엔진 개선이 소급 적용되는 성질(dsessions 주석)을 **학습 타깃 형식**으로 그대로 쓴다.

---

## 1. 데이터 캡처 — `telemetry.py` + 세션 영속화

### 1.1 append-only 상호작용 로그 (신규, 단일 진실)
모든 provider·스테이지에서 동일하게 호출되는 얇은 캡처. 부작용 최소, 실패해도 본 기능 무영향(try/except).
```python
# backend/telemetry.py
def record(event: dict) -> None:
    """data/interactions/{user}/{yyyymmdd}.jsonl 에 1줄 append. 스키마:
    {ts, user, session_kind: 'deck'|'diagram'|'slide', session_num, stage,
     action: 'generate'|'feedback'|'revise'|'confirm'|'edit'|'export'|'ab_pick',
     model, provider, direction?('A'|'B'),
     prompt?, instruction?, before?(slide/deck json), after?(slide/deck json),
     accepted?(bool), repair_rounds?, lint_findings?[]}"""
```
- **호출 지점**(app.py 엔드포인트에 1줄씩): `create_session`/`d_session_create`/`s_session_create`
  (generate), `*_feedback`/`*branch`(revise+before/after), `*_confirm`/`confirm_plan`(confirm),
  `slide_edit`/`*_update`(edit, before/after), `*export`(export, accepted=True).
- **before/after**: 수정·편집 시 반드시 이전/이후 slide JSON을 함께 기록(= 지도학습 쌍의 원천).
  현재 코드가 `model_dump(exclude_none=True)`로 이미 dict를 갖고 있으니 저비용.

### 1.2 메인 세션 영속화 (sessions.py)
dsessions처럼 `data/sessions/{num}.json`에 저장(plan/deck/figure_status/events).
export/confirm 시점에 save. in-memory 캡 문제 해소 + ETL이 읽을 소스 확보.
- 하위호환: 저장 실패해도 기능 정상. 로드는 선택적(재시작 복구 용도).

### 1.3 user_id
현 프로토타입은 단일 사용자. `LEARN_USER`(env, 기본 "default") 또는 향후 인증 연동으로
`user`를 채운다. 지금은 "default" 1인이라도 **기록 축적은 즉시 가치**(반복·유사 요청 적중).

---

## 2. 데이터셋 정제 — `corpus.py` (오프라인 ETL)

세션/트리/상호작용 로그를 걸어 학습용 JSONL을 생성. 순수 배치, 언제든 재실행 가능.
```
python -m backend.corpus --out data/learning/
```
산출물(`data/learning/`):

1. **`sft_generate.jsonl`** — (요청+컨텍스트 → 채택된 산출).
   원천: 피드백/편집 없이 confirm 또는 export된 첫 초안, 그리고 최종 export된 deck.
   `{"prompt","profile","retrieved":[...],"target": <deck|slide json>}`
2. **`sft_revise.jsonl`** — (수정 전 slide + 지시 → 수정 후 slide). 이후 채택된 revision만.
   `{"before","instruction","after"}` (dsessions parent→child, figure_feedback before/after).
3. **`dpo.jsonl`** — 선호쌍. A/B 형제 중 채택(자식 존재/confirm/export)=chosen, 나머지=rejected.
   revision도 (after=chosen, before=rejected)로 추가 가능.
   `{"prompt","chosen","rejected"}`
4. **`corrections.jsonl`** — 라벨/재료/구조 단위 diff(before→after 토큰). 규칙 채굴용(§5).

**라벨 규칙(적중 정의)**:
- `export` = 최강 positive. `confirm`(figure_confirm/s_confirm/confirm_plan) = positive.
- 피드백·편집 0회로 confirm/export = **first-draft hit**(지표 분자).
- revise 발생 = parent는 "빌드 기반은 됐으나" 해당 축에서 child가 우월 → DPO/ SFT-revise.
- 실패 draft(both failed 등)·lint error = 약한 negative(가중치↓).

**중복·품질**: 동일 prompt 재현은 최신 채택본으로 dedupe. 첨부 원본 바이트는 **코퍼스에서 제외**,
파생 slide JSON만 보존(§6 거버넌스).

---

## 3. 티어 1 — 검색 주입 (즉시효과, 학습 불필요, 전 provider)

**가장 높은 ROI.** 반복·유사 요청에서 과거 채택 구조를 그대로 끌어와 초안에 반영 → 적중률 즉시 상승.

### 3.1 `retrieve.py`
```python
def index_accepted(user: str) -> None:
    """채택된 slide/figure를 인덱싱. 키(기본): 구조 태그(domain.STRUCTURES 매칭) +
    라벨 토큰 + prompt 텍스트. 임베딩(옵션): 로컬 임베딩 모델(vLLM) 또는 BM25 폴백."""

def retrieve(user: str, prompt: str, k: int = 2) -> list[dict]:
    """유사 채택 예시 top-k. 같은 user 우선 → 전역 폴백. 반환: few-shot용 slide json."""
```
- **기본 구현은 결정적 키워드/구조태그 검색**(모델 의존 없음, 온프렘 안전). 임베딩은 선택적 업그레이드.
- 소형 모델(WP2 27B)에 특히 효과적: 자유 생성 대신 "이전에 이 사용자가 승인한 유사 구조"를 few-shot으로.

### 3.2 `profile.py`
```python
def build_profile(user: str) -> dict:
    """상호작용 집계: preferred_materials(빈도), label_lexicon(선호 표기: 예 'PTH'>'Cu via'),
    default_slide_count, direction_bias(A/B 채택률), favorite_structures(빈도),
    common_corrections(재작성 규칙), language."""

def profile_prompt_block(profile: dict) -> str:
    """system 프롬프트에 주입할 간결한 선호 블록(길지 않게)."""
```

### 3.3 llm.py 주입
- `generate_deck`/`generate_figure_slide`/`generate_diagram_slide` 진입 시:
  `retrieve()` few-shot + `profile_prompt_block()`를 **기존 프롬프트에 추가**(HARD RULES 위배 없이).
- WP2의 template-first와 결합: 프로필의 favorite_structures가 템플릿 선택 우선순위를 준다.
- 켜고 끄기: `LEARN_RETRIEVAL=1`(기본 on), 실패 시 조용히 우회(무주입).

---

## 4. 티어 2 — 주기적 미세튜닝 (오프라인, 인프라 의존, 선택)

소형 모델일수록 LoRA 이득이 크다. 앱 밖 GPU에서 배치 실행하고 어댑터만 교체.
```
train/build_corpus.py   # = backend.corpus 래핑
train/train_lora.py     # SFT: sft_generate + sft_revise → qwen3.6-27b / 3.5-122b LoRA
train/run_dpo.py        # DPO: dpo.jsonl 선호 정렬
train/promote_adapter.py# 골든 평가(WP2 eval_llm) 통과 시에만 승격
```
- **회귀 가드**: 새 어댑터는 WP2 `eval_llm.py`로 현행 대비 first-draft 적중률·lint pass율을
  비교해 **개선 시에만 승격**. vLLM은 어댑터 핫스왑, 베이스 가중치 불변, 어댑터 버전 관리.
- haiku(claude_cli)는 파인튜닝 대상 아님 → 티어1·3로만 개선.
- 데이터 임계치 전에는 실행 불필요(예: SFT는 채택쌍 ≥ 수백 개부터 의미). 그 전엔 티어1이 주력.

---

## 5. 티어 3 — 결정적 규칙 채굴 (WP3와 폐루프)

`corrections.jsonl`에서 **반복되는 교정**을 규칙으로 승격(사람 검토 게이트 필수).
```
python -m train.mine_rules --min-count 5
```
- 반복 재료 별칭(예 "cu"→copper) → WP3 `repair.MATERIAL_ALIAS` 추가 제안.
- 반복 라벨 재작성 → 사용자 `label_lexicon`(티어1) 또는 전역 도메인 용어.
- 반복 구조 파라미터 기본값 → WP3 `templates` 기본값/ `domain.py` 갱신 제안.
- 산출은 **제안 diff**(자동 머지 금지). 검토 후 반영 → 결정성·안전성 유지.
- 효과: LLM이 매번 틀리던 것을 코드가 영구히 흡수 → 적중률의 계단식 상승.

---

## 6. 지표 — `metrics.py` ("적중률"의 정의와 추적)

새 UI 없이 CLI/리포트 파일로 산출(주간 등).
- **1차(북극성): first-draft acceptance rate** = 피드백·편집 0회로 confirm/export된 비율.
- 2차: 도형당 평균 feedback 횟수, 평균 repair 왕복수, A/B 첫선택 적중률, lint-clean율,
  검색 주입 기여도(주입 on/off A/B), revise까지 편집거리.
- user별 + 전역, **시간축**으로 추적해 루프가 실제로 작동함을 입증.
- WP2 `eval_llm.py`와 지표 정의 공유(어댑터 승격 기준과 동일 척도).

---

## 7. 거버넌스 (온프렘 전제와 정합)

- 모든 데이터 **로컬 보관**(vLLM 온프렘과 동일 경계). 외부 전송 없음. 학습도 온프렘.
- 첨부는 IP 민감 가능 → **원본 바이트 미보관**, 파생 slide JSON만. user별 격리.
- opt-out 플래그(`LEARN_CAPTURE=0`), 보존 기간(env), 삭제 CLI. PII 위험은 낮지만(기술 도면)
  prompt 텍스트에 사명/코드네임 가능 → 프로필 공유 범위는 user 내로 기본 제한(전역 폴백은 익명 구조태그만).

---

## 8. 데이터 흐름 (텍스트)
```
상호작용(생성/피드백/A·B선택/confirm/edit/export)
        │  telemetry.record()  + 세션 영속화
        ▼
data/interactions/*.jsonl  +  data/{sessions,dsessions,slsessions}/*.json
        │  corpus.py (ETL)
        ▼
data/learning/{sft_generate, sft_revise, dpo, corrections}.jsonl  +  profile/{user}.json
    ├── 티어1: retrieve + profile ──주입──► llm.py 생성(즉시 적중↑, 전 provider)
    ├── 티어2: LoRA/DPO ──평가통과시 승격──► vLLM 어댑터(주기)
    └── 티어3: mine_rules ──검토후──► WP3 repair/templates/domain(결정적, 계단식)
        │
        ▼  metrics.py: first-draft 적중률 시간추적 (WP2 eval와 공유)
```

---

## 9. 권장 착수 순서 (WP5 내부)

1. `telemetry.record()` + app.py 캡처 훅 + 메인 세션 영속화(§1) — **먼저**. 데이터가 있어야 학습.
2. `metrics.py`(§6) — 지금의 적중률 baseline을 먼저 찍는다(개선 측정용).
3. `corpus.py`(§2) + `profile.py`/`retrieve.py`(§3) — **티어1 배포**(최대 즉시효과).
4. `mine_rules`(§5, 티어3) — 데이터 쌓이면.
5. `train/*`(§4, 티어2) — 채택쌍 임계치 도달 후, 인프라 준비되면.

## 10. 수용 기준 (WP5)

1. 생성/피드백/A·B선택/confirm/edit/export가 `data/interactions/*.jsonl`에 before/after 포함 기록된다.
2. 메인 스테이지 세션이 디스크에 영속되어 재시작 후에도 ETL이 신호를 읽는다.
3. `corpus.py`가 4개 데이터셋을 생성하고, revise/edit이 (before,instruction,after) 쌍으로 잡힌다.
4. 티어1 on일 때 반복·유사 요청에서 과거 채택 예시가 few-shot으로 주입된다(로그 확인).
5. `metrics.py`가 first-draft 적중률을 user별·시간별로 산출한다.
6. `LEARN_CAPTURE=0`이면 캡처가 완전히 꺼지고, 캡처 실패가 본 기능을 절대 막지 않는다.
7. 첨부 원본 바이트가 코퍼스에 포함되지 않는다. 프론트엔드 diff = 0.
