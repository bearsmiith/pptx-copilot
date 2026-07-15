# pptx-copilot 개선 핸드오프 (Claude Code 실행용)

작성: 2026-07-08 · 대상 저장소: `pptx-copilot` · 실행 주체: **Claude Code**

이 문서는 **설계/리서치 결과**다. 실제 코드 구현은 Claude Code가 이 핸드오프를 이어받아
수행한다. 각 WP 문서는 파일별 변경·스니펫·수용 기준까지 구체화되어 있으므로, Claude Code는
저장소 컨텍스트에서 그대로 착수할 수 있다.

## 무엇을 / 왜

현재 pptx-copilot은 반도체 패키징 **단면도(cross-section) 인포그래픽**에 특화된 대화형
덱 빌더다. 아키텍처 골격(JSON=진실, `layout.py`=geometry 독점, 스테이지 워크플로, A/B 분기,
mock/claude_cli/openai provider + repair 루프)은 견고하다. 이번 개선은 **골격을 유지한 채**
4가지를 보강한다:

1. **단면도 도메인 지식 + 디자인 확장** — 최신 어드밴스드 패키징/디스플레이 구조(팬아웃,
   하이브리드 본딩, HBM, CoWoS-L, 백사이드 파워, 글라스 코어, OLED, 와이어본드…)와 작도
   규약을 DSL·팔레트·프롬프트·예제로 흡수. → **[01_domain_knowledge.md](01_domain_knowledge.md)**
2. **모델별 실행 전략** — haiku / qwen3.5-122b / qwen3.6-27b가 같은 파이프라인에서
   신뢰성 있게 동작하도록 디코딩 제약·프롬프트·태스크 분해·스테이지 라우팅 정의.
   → **[02_model_strategy.md](02_model_strategy.md)**
3. **확정적 코드 도구 + LLM 연동** — 파라메트릭 템플릿·린터·정규화·레이아웃 검사로
   LLM이 틀리기 쉬운 부분을 결정적 코드로 흡수하고, LLM엔 기계검증 피드백만 돌려준다.
   → **[03_deterministic_tools.md](03_deterministic_tools.md)**
4. **UI 유지** — `frontend/*.html`는 손대지 않는다(전역 제약, 아래).
5. **사용자 기록 축적 + 학습 루프** — A/B 선택·피드백·confirm·export 등 상호작용의 암묵적
   정답 신호를 저장·정제해 (검색 주입 → 미세튜닝 → 규칙 채굴)로 되먹여 **첫 초안 적중률**을
   시간이 갈수록 높인다. → **[04_learning_loop.md](04_learning_loop.md)**
6. **슬라이드 작성 능력(텍스트·구성·정확성) + RAG** — 엔지니어링/사이언스 슬라이드 작법과
   전자·패키징 팩트를 지식카드로 저작해 RAG로 주입하고, 형식/정합은 확정적 코드가, 선택은
   LLM이 도구로 처리. 업로드 인포그래픽과 조화, 기존 인포그래픽과 무충돌. 테스트셋 포함.
   → **[05_slide_authoring.md](05_slide_authoring.md)** (+ `kb/*.jsonl`, `tests/*.jsonl` — Cowork 저작 완료)
7. **범용 인포그래픽 (WP7, 2026-07-10 추가)** — 단면도 특화를 유지한 채, figure 1장 흐름
   (dsessions)이 단면도가 아닌 요청에도 대응: 엔지니어링 리포트향 신규 6 kind(timeline/kpi/
   table/matrix/chart/tree), 결정적 kind 라우팅 + 프롬프트 동적 조립(단면도 규약의 조건부
   주입화), 정보 부족 시 질문(intake), 생성 중 실시간 partial 렌더, 아키타입 지식
   (`archetypes.py` + kb 카드). → **[06_general_infographics.md](06_general_infographics.md)**
8. **점진적 구체화 파이프라인 (WP8)** — 조기 kind 확정을 없애는 Brief IR(genre/부품/실장/관계)
   + `compile_brief`(통합 physical scene = `assembly` figure) + `understand`/`parts`/`critic`
   (형태 유사 대체). → **[07_brief_pipeline.md](07_brief_pipeline.md)**, 근거
   **[07b_coverage_research.md](07b_coverage_research.md)**
9. **도메인 확장 + 디자인 품질 (WP9, 2026-07-15 추가)** — mobile/watch 실장구조(보드/패키지
   레벨 먼저), photonic·packaging 잔여 갭(PoP/TMV/쉴드캔/V-groove/CIS…), `assemblies.py`
   레시피 + kb 카드, 렌더 폴리시(디자인 토큰·골든 SVG 회귀).
   → **[08_mobile_watch_domains.md](08_mobile_watch_domains.md)**
10. **자유 캔버스 편집기 (WP10)** — 단면도·슬라이드 탭에서 생성물 직접 편집(드래그/텍스트/
    추가/삭제), 저장 시 **파생 노드로 연결**. 엔진 베이스 + 오버라이드 diff 레이어로
    JSON-진실 유지. WP8 잔여(recompile/Brief 편집) 흡수.
    → **[09_canvas_editor.md](09_canvas_editor.md)**
11. **LLM 비교 벤치 탭 (WP11)** — haiku/qwen3.5-122b/qwen3.6-27b 자동 비교: 테스트셋 54,
    결정적 채점(70) + 설정형 심판 LLM(30), 모델×카테고리 히트맵·런 비교, 엔드포인트별
    프로파일 튜닝 루프. → **[10_bench_tab.md](10_bench_tab.md)**
12. **공개 릴리스 + 설치/에이전트 가이드 (WP12)** — GitHub 공개 push(위생·키 누출 방지),
    README 개편, `docs/INSTALL_UBUNTU.md`(Ubuntu 24 + vLLM qwen + opencode, 에이전트가
    그대로 실행 가능한 3줄 구조), `AGENTS.md`.
    → **[11_release_and_install.md](11_release_and_install.md)**

**현황(2026-07-15)**: WP1~7 구현 완료(smoke ALL PASSED, 라우팅 골든 30/30), WP8 대부분 구현
(잔여 recompile/Brief 편집은 WP10에 포함). WP9~12가 이번 라운드 계획이며 **R0(WP12의 저장소
공개)를 가장 먼저** 실행한다.

전체를 관통하는 명제: **"소형 모델은 자유형 DSL을 줄이고 확정적 도구·지식카드·과거 채택
데이터에 일을 넘길수록 안정된다."** WP1이 구조 지식을, WP3이 그 지식을 결정적 도구로, WP2가
도구를 모델별로 배치하고, WP5가 사용자 상호작용을 데이터로 되먹이며, **WP6이 작법·도메인 지식을
RAG로 주입하고 텍스트/구성 품질과 정확성을 결정적 도구로 끌어올린다.** (WP3·WP5·WP6은 같은
Findings 포맷·검색 인프라·평가 하니스를 공유한다.)

## 전역 제약 (모든 WP 공통, 위반 금지)

- **UI 불변**: `frontend/index.html`, `slides.html`, `deck.html` diff = 0. 신규 재료/구조는
  전부 백엔드 렌더 산출물(SVG/pptx)로만 표현. 새 UI 컨트롤 추가 금지.
  **WP7 예외(사용자 승인, 2026-07-10)**: `index.html`에 한해 ① 실시간 partial 프리뷰
  ② 질문 배너의 최소 변경 허용(합계 ≤50줄, 06 문서 §7). 나머지 프런트 파일은 계속 diff=0.
  **WP10/WP11 개정(사용자 승인, 2026-07-15)**: `index.html`·`slides.html`·신규 `editor.js`에
  편집기 추가, `bench.html` 신규 탭 + 각 페이지 nav 링크 1줄 허용(09/10 문서 §7·§4).
  `deck.html`·`settings.html`은 불변 유지, 기존 흐름 회귀 금지.
- **geometry 단일 소스**: 좌표는 `layout.py`에서만. 신규 구조는 새 row 타입 + layout 함수로만
  확장하고, `render_svg.py`/`export_pptx.py`에 좌표를 직접 넣지 않는다(양쪽 일치 보장).
- **의미/geometry 분리**: LLM 출력에 좌표·색·물리치수(mm/µm) 금지 유지.
- **하위호환**: 새 env(스테이지별 모델 등)가 없으면 기존과 100% 동일 동작.
- **discriminated union 유지**: 모든 신규 row는 `type` Literal 태그(guided_json 신뢰성 핵심).
- **단일 지식 소스**: 구조 레시피는 신규 `backend/domain.py` 1곳. examples/prompt/template/lint가
  이를 참조(문자열 중복·드리프트 금지).
- **하드 실패 최소화**: 도메인 규칙은 pydantic 검증 실패가 아니라 lint/repair로 흡수(소형 모델 친화).

## 권장 실행 순서 (의존성)

```
WP1(domain.py + DSL/palette/prompt/examples)   ← 기반
   └─→ WP3(templates/lint/repair/geomcheck)     ← domain.py 소비
          └─→ WP2(스테이지 라우팅 + template-first) ← 도구 소비
WP5(telemetry/corpus/retrieve/profile/metrics)  ← 병행 착수 가능(캡처 먼저), 티어1은 WP1·WP3 이후 효과↑
WP6(kb/RAG + slidewrite + tools + 테스트셋)      ← WP1·WP3 이후, WP5 검색 인프라와 인덱스 공유
WP7(범용 kind + router + intake + 실시간 렌더)   ← WP1~WP6 완료 후. 내부 순서는 06 문서 §8
WP8(Brief IR + compile + understand/parts/critic) ← WP7 위. [구현됨 — 잔여는 WP10]
--- 이번 라운드 (2026-07-15) ---
WP12-R0(git 공개 + 위생)                          ← 즉시, 모든 것에 선행
WP9(mobile/watch 부품·레시피·kb + 렌더 폴리시)     ← WP8 assembly 위. 커밋 단위 push
WP10(편집기 + 오버라이드 + recompile)              ← WP9와 병행 가능(파일 겹침 적음)
WP11(벤치 탭 + bench_set + 프로파일)               ← WP9 케이스 포함하므로 WP9 뒤 권장
WP12-R1~R3(README/AGENTS/INSTALL 마감)             ← WP9~11 반영 후
```
1. **WP1 먼저**: `domain.py` 신설 → `BondRow`/`DieStackRow` + layout 대응 → palette role +
   alias → 프롬프트 규약 요약 → 신규 프리셋 → 스모크 통과.
2. **WP3 다음**: `templates`(domain 소비) → `repair`/`lint`/`geomcheck`(순수 함수) →
   `_validated` 확장(normalize→lint→fix_hint 루프) → 단위테스트.
3. **WP2**: 스테이지별 모델 오버라이드 env → template-first 결정 로직 → guided_json
   호환 점검 → provider별 골든 평가 스크립트.
4. **WP5**: 캡처(`telemetry`+세션 영속화)와 `metrics`(baseline)를 **가장 먼저** 심어 데이터를
   모으고, 티어1(검색·프로필 주입) 배포로 즉시 적중률↑. 티어2(LoRA/DPO)·티어3(규칙 채굴)은
   데이터 임계치 도달 후. WP2 골든 평가와 지표를 공유한다.
5. **WP6**: `kb/*.jsonl`(Cowork 저작 완료)을 `data/kb/`에 배치 → `kb.py` 검색 → 프롬프트 RAG
   주입 → `slidewrite` 텍스트 린터를 WP3 루프에 합류 → `tools.choose_layout` 등 결정적 도구 →
   업로드 조화 → `eval_llm.py`로 `tests/*.jsonl` 채점(RAG on/off·모델 3종 A/B). WP5 검색 인프라 재사용.
6. **WP7**: 신규 kind/아키타입(mock 검증) → 라우팅+프롬프트 분해 → intake 질문 →
   실시간 렌더(mock 시뮬 먼저) → kb/평가 확장. 상세 의존성은 06 문서 §8.

각 WP는 독립 PR로 나눌 수 있다(WP1 → WP3 → WP2 순 병합 권장; WP5 캡처는 조기 병합해 데이터 선확보;
WP6은 WP1·WP3 뒤).

## 검증 (완료 정의)

- `python backend/smoke_test.py` 통과(신규 프리셋 포함): SVG `<svg` 시작, pptx `PK`+>5KB, round-trip.
- 각 WP 문서의 **수용 기준** 절 전부 충족.
- 신규 도구는 mock provider로 전 경로 테스트 가능(순수 함수).
- (권장) 고위험 변경은 서브에이전트로 검증 리뷰: layout geometry 회귀, guided_json 스키마 디코딩.
- `git diff frontend/` 가 비어 있음.

## 신규/변경 파일 요약

| 파일 | 상태 | 역할 | WP |
|------|------|------|----|
| `backend/domain.py` | 신규 | 구조 레시피/지식 단일 소스 | 1,3 |
| `backend/models.py` | 변경 | `BondRow`,`DieStackRow`(+`wirebond` 플래그) | 1 |
| `backend/layout.py` | 변경 | 신규 row geometry 디스패치 | 1 |
| `backend/palette.py` | 변경 | 신규 material role + alias 맵 | 1,3 |
| `backend/prompts.py` | 변경 | 도메인 규약 요약, 동적 rules 주입 | 1,2 |
| `backend/examples.py` | 변경 | 신규 프리셋(domain에서 생성) | 1 |
| `backend/templates.py` | 신규 | 파라메트릭 구조 빌더 | 3 |
| `backend/lint.py` | 신규 | 도메인 규약 린터(Findings) | 3 |
| `backend/repair.py` | 신규 | 결정적 정규화 | 3 |
| `backend/geomcheck.py` | 신규 | 레이아웃 사후 검사 | 3 |
| `backend/llm.py` | 변경 | 스테이지 라우팅, normalize→lint→fix 루프, template-first, 검색·프로필 주입 | 2,3,5 |
| `backend/app.py` | 변경(경미) | 스테이지별 모델 선택 배선, telemetry 캡처 훅 | 2,5 |
| `eval_llm.py` | 신규(권장) | provider별 골든 평가 | 2 |
| `backend/telemetry.py` | 신규 | append-only 상호작용 캡처 | 5 |
| `backend/sessions.py` | 변경 | 메인 세션 디스크 영속화 | 5 |
| `backend/corpus.py` | 신규 | 세션→학습 데이터셋 ETL | 5 |
| `backend/profile.py` | 신규 | user 선호 프로필 | 5 |
| `backend/retrieve.py` | 신규 | 과거 채택 예시 검색 | 5 |
| `backend/metrics.py` | 신규 | 첫초안 적중률 지표 | 5 |
| `train/*` | 신규(오프라인) | LoRA/DPO/규칙채굴 스텁 | 5 |
| `backend/kb.py` | 신규 | 지식카드 로더/검색(RAG) | 6 |
| `backend/slidewrite.py` | 신규 | 슬라이드 텍스트 린터(Findings) | 6 |
| `backend/tools.py` | 신규 | LLM 도구 레지스트리(choose_layout 등) | 6 |
| `data/kb/*.jsonl` | 신규(Cowork 저작) | 디자인 25 + 도메인 28 카드 | 6 |
| `handoff/tests/slide_testset.jsonl` | 신규(Cowork 저작) | 골든 18케이스 | 6 |
| `backend/archetypes.py` | 신규 | 범용 아키타입 단일 지식 소스 | 7 |
| `backend/router.py` | 신규 | kind 라우팅 + intake needs | 7 |
| `backend/stream.py` | 신규 | partial JSON → 점진 Slide | 7 |
| `backend/models.py`·`layout.py`·`palette.py` | 변경 | 신규 6 kind + semantic role | 7 |
| `backend/prompts.py`·`llm.py`·`app.py`·`tools.py` | 변경 | 동적 프롬프트·스트리밍·질문 | 7 |
| `data/kb/infographic_design.jsonl` | 신규 | 범용 디자인 카드 ~20 | 7 |
| `tests/routing_testset.jsonl` | 신규 | 라우팅 골든 30케이스 | 7 |
| `frontend/index.html` | 변경(WP7 예외, ≤50줄) | partial 프리뷰 + 질문 배너 | 7 |
| `frontend/slides.html`·`deck.html`·`settings.html` | **불변** | — | 4 |

## 리서치 출처

주요 출처는 [01_domain_knowledge.md](01_domain_knowledge.md) 하단에 정리.
