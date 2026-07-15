# WP6 — 슬라이드 작성 능력 향상 (RAG + 확정적 도구 + 통합/테스트)

> 대상 파일(신규): `backend/kb.py`(지식베이스 로더/검색), `backend/slidewrite.py`(텍스트 린터),
> `backend/tools.py`(LLM 도구 레지스트리), `data/kb/`(임베딩 인덱스). 기존: `backend/prompts.py`,
> `backend/llm.py`(RAG 주입·도구선택), `backend/slide_layout.py`/`slide_render.py`(무변경 확인),
> `eval_llm.py`(WP2, 테스트셋 소비). UI 불변.
> 목표: 크로스섹션 인포그래픽(WP1)은 그대로 두고 **슬라이드의 텍스트·레이아웃·구성 품질**과
> **내용 정확성(환각 감소)** 을 올린다. 소형 모델도 쓰도록 지식은 RAG로 주입하고, 판단이 필요
> 없는 부분은 확정적 코드가 처리하며 LLM은 **도구 선택/활용**만 잘 하게 한다.

## Cowork가 이미 만들어 둔 산출물 (이 폴더)

| 파일 | 내용 | 용도 |
|------|------|------|
| `kb/slide_design.jsonl` | 슬라이드 디자인·작문 카드 25개(assertion-evidence, Tufte data-ink, Knaflic declutter, 타이포/화이트스페이스/정렬, 캡션/숫자/약어, 템플릿 선택, 이미지 조화 등) | RAG 코퍼스(형식·작문 기준) |
| `kb/electronics_packaging.jsonl` | 전자·패키징 도메인 팩트 카드 28개(FC-BGA, CoWoS-S/L, EMIB, 하이브리드본딩, HBM, 백사이드파워, 글라스코어, OLED/µLED/miniLED, 와이어본드 등) | RAG 코퍼스(내용 정확성) |
| `tests/slide_testset.jsonl` | 골든 테스트 18케이스(입력·기대구조·필수라벨·환각금지·루브릭) | 회귀/평가 |

카드 스키마: `{id,type,tags,applies_to|structure,title,body,source}`. **Claude Code는 이 JSONL을
그대로 청크·임베딩**하면 된다(카드 1장 = 1청크, 이미 짧게 저작됨). WP1 `domain.py`의 구조
레시피와 상호참조되며(같은 structure 키), 중복 시 `domain.py`=기계용 레시피 / KB=서술형 근거로 역할 분리.

---

## 1. RAG 아키텍처 — `kb.py`

```python
def build_index() -> None:
    """data/kb/*.jsonl → 임베딩 인덱스. 임베딩은 vLLM 로컬 임베딩 모델(있음) 사용,
    실패 시 결정적 BM25/키워드(tags+title) 폴백. 인덱스는 디스크 캐시."""

def retrieve(query: str, kinds: list[str], k: int = 4,
             structure: str | None = None) -> list[dict]:
    """query(요청/플랜 텍스트)와 kinds('design'|'domain')로 top-k 카드.
    structure가 정해지면 해당 structure 카드에 가중치. 반환: 카드 dict 리스트."""
```
- **provider 무관**: 검색은 백엔드가 수행하고 결과를 프롬프트에 주입 → haiku(claude_cli)도
  동일 이득. vLLM 임베딩은 정확도 업그레이드, 없으면 키워드로도 동작.
- 인덱스는 KB + (WP5가 있으면) **사용자 채택 예시**까지 합쳐 검색 가능(교차 시너지).
- 카드 수가 작아(수십 장) 초기엔 임베딩 없이 키워드만으로도 충분. 규모 커지면 임베딩.

### 1.1 주입 방식 (프롬프트) — `prompts.py`/`llm.py`
생성 진입 시 `retrieve()` 결과를 **근거 블록**으로 시스템/유저 프롬프트에 추가:
```
[KNOWLEDGE — 아래 카드의 사실/원칙만 근거로 사용. 카드에 없는 수치는 지어내지 말고
 "[data needed: ...]"로 표기. 각 카드는 id로 식별.]
- (domain ep-006) CoWoS-S: SoC/HBM side-by-side on monolithic Si interposer with TSV ...
- (design sd-001) Title states the message, not the topic ...
```
- 규칙: **도메인 주장은 카드 근거 우선, 없으면 data-needed**(기존 HARD RULES와 정합).
  디자인 카드는 형식(타이틀=assertion, 병렬 불릿, 캡션 honesty)에 반영.
- **소형 모델 배려(WP2)**: k를 모델별로(27B=3, 122b/haiku=5), 카드 body는 이미 짧음.
  전체 규약을 다 넣지 말고 **검색된 카드만** 주입 → 컨텍스트 절약 + 정밀도↑.

---

## 2. 확정적 도구 + LLM 도구선택 — `slidewrite.py`, `tools.py`

원칙: **판단이 필요 없는 형식/정합은 코드가, 의미/선택은 LLM이.** (WP3와 동일 철학의 텍스트판)

### 2.1 슬라이드 텍스트 린터 `slidewrite.py` (결정적, Findings 반환 — WP3 lint와 동일 포맷)
- `TITLE_NOT_ASSERTION`: 타이틀이 명사구/토픽(동사·서술 없음) → assertion으로 재작성 지시(sd-001).
- `BULLET_TOO_LONG` / `BULLET_NOT_PARALLEL` / `BULLET_COUNT`: 1줄·병렬·3-6개 규칙(sd-003/004).
- `PARAGRAPH_ON_SLIDE`: 문장/문단 감지 → 불릿/헤드라인으로(sd-004b).
- `ACRONYM_UNEXPANDED`: 첫 등장 약어 미확장(sd-015). `NUMBER_STYLE`: SI 간격/유효숫자(sd-014).
- `INVENTED_NUMBER_SUSPECT`: 근거 카드 없이 등장한 구체 수치 → data-needed 제안(정확성 가드).
- `MISSING_SO_WHAT`(warn): 콘텐츠 슬라이드에 함의/테이크어웨이 부재(sd-005).
- `CAPTION_SCALE`: 두께 과장 stack인데 not-to-scale 캡션 없음(sd-013/ep-028).
→ 대부분 **경고**로 두고 repair 루프(WP3)에서 구체 지시로 환류. 하드 실패는 최소화(소형 모델).

### 2.2 LLM 도구 레지스트리 `tools.py` (도구선택을 잘 하게)
LLM에 **얇은 순수 함수 도구**를 노출하고, 선택/호출만 맡긴다(자유 생성 최소화):
- `search_knowledge(query, kinds)` → 카드(RAG를 모델이 능동 호출; 미지원 provider는 자동 주입으로 대체).
- `list_templates()` / `instantiate_template(name, params)` (WP3) — 구조/레이아웃 확정 생성.
- `choose_layout(intent, n_images)` → 결정적 템플릿 추천(sd-018 규칙 코드화: 1도해설명→image+text,
  2비교→two_images/compare, 시퀀스→flow, 1강조→hero, N그리드→image_grid).
- `lint_slide(slide)` / `lint_text(slide)` → Findings(자가검증).
- `check_figure(slide)`(WP3 geomcheck) → 배치 문제.
두 가지 연동 모드(WP3 §2와 동일): (a)기본 = 백엔드가 도구를 순차 적용하는 post-gen 파이프라인
(전 provider), (b)옵션 = tool-calling 지원 모델(haiku, vLLM)에서 LLM이 직접 도구 호출.
소형 모델은 (a) + template-first가 안전.

### 2.3 결정적 레이아웃은 그대로
`slide_layout.py`/`layout.py`가 geometry를 계속 독점. LLM은 좌표를 만들지 않는다.
`choose_layout`도 후보 추천까지만; 실제 배치는 엔진이.

---

## 3. 업로드 인포그래픽과의 조화 (vLLM 비전)

기존 slsessions(이미지+텍스트) 흐름을 강화한다. UI/엔드포인트 구조는 유지.
- **비전 캡션**: 업로드 이미지를 vLLM(122B 멀티모달)/haiku vision으로 읽어 **덱 용어에 맞춘
  한 줄 캡션** 생성. KB의 도메인 카드로 캡션 용어를 정규화(예: 이미지가 CoWoS면 ep-006 용어 사용).
- **구성 규칙(sd-019)**: 캡션 병렬화, 서사 순서(맥락→상세 / A→B / 공정 순서), 크기 일관,
  **근접중복 업로드 dedup**(지각 해시 or 임베딩 유사도 — 결정적 코드).
- **혼합 소스**: 생성된 크로스섹션(WP1)을 이미지로 래스터화(기존 `from_diagrams`)해 업로드
  이미지와 **한 슬라이드에서 조화** — 캡션·순서·템플릿을 위 규칙으로 통일.
- **정확성 가드**: 비전이 읽은 내용과 KB가 충돌하면(예: 잘못 읽은 라벨) data-needed/보수적 캡션.

---

## 4. 기존 인포그래픽 기능과의 무충돌 통합 (점검 포인트)

WP6은 **텍스트/구성/근거** 계층에만 개입하고 DSL·geometry는 건드리지 않는다. 확인 항목:
- **슬라이드 타입 분리 유지**: figure 슬라이드(WP1 DSL)는 RAG 도메인 카드로 **라벨 정확성**만
  보강하고 형식 린터(불릿 규칙 등)는 적용하지 않음. content/slide 타입에 텍스트 린터 적용.
- **HARD RULES 정합**: RAG 주입이 "좌표/색/치수 금지", "숫자 지어내지 말 것"을 강화할 뿐 위배 안 함.
- **프롬프트 예산**: 검색 주입으로 길어지지 않게 k 제한·카드 body 단문 유지(WP2). 도메인 규약
  전체 상주 대신 **검색된 카드로 대체** 가능(프롬프트 다이어트).
- **repair/lint 통합**: `slidewrite` Findings를 WP3 `lint`와 같은 포맷/루프에 합류(중복 루프 금지).
- **캐시/성능**: KB 인덱스는 프로세스 1회 로드. 검색은 생성당 1회.
- **UI 불변**: 신규 엔드포인트/화면 없음. 모든 개입은 생성 파이프라인 내부.

---

## 5. 테스트 계획 (Cowork가 테스트셋 제공, Claude Code가 하니스 연결)

### 5.1 테스트셋 (`tests/slide_testset.jsonl`, 18케이스)
커버: 정석 단면(t-01), 비교(t-02/t-15), 신규구조(HBM/하이브리드/팬아웃/백사이드/글라스/OLED/EMIB/QFN),
덱 장수 준수(t-09), 환각 가드(t-14 수치·t-03 대역폭), 업로드 조화(t-11/t-12/t-18), 모호요청 질문(t-17).
각 케이스: `expect`(structure/figure_kind/template/slide_count/must_include_labels/must_use_kb_cards/
must_not) + `rubric`(accuracy/design/conciseness/grounding/integration).

### 5.2 자동 채점(결정적) + LLM 채점(루브릭)
- **결정적 체크**(빠른 게이트, `eval_llm.py`에 추가): 스키마 유효 / slide_count 일치 /
  must_include_labels 포함(부분일치 허용) / must_not 위반 없음(예: flip-chip에 wirebond 텍스트,
  근거 없는 um 수치 정규식) / 템플릿·figure_kind 일치 / WP3 lint·`slidewrite` 경고 수 임계.
- **LLM 루브릭 채점**(상위 게이트): 큰 모델로 accuracy/design/conciseness/grounding/integration을
  0-2 채점(카드 근거 제시 요구). 채점자와 생성자 모델 분리.
- 지표: 케이스 통과율, 평균 루브릭 점수, must_not 위반율, data-needed 준수율. WP2 골든 평가·
  WP5 first-draft 적중률과 **지표/하니스 공유**.

### 5.3 통합/회귀 테스트
- `smoke_test.py` 확장: KB 로드→검색이 카드 반환, `slidewrite.lint`가 대표 위반 검출,
  RAG 주입 on/off로 figure 슬라이드 렌더가 불변인지(무충돌) 확인.
- **A/B**: RAG 주입 on vs off로 테스트셋을 돌려 정확성/루브릭 향상 정량화(효과 입증).
- **모델 3종**(haiku/122b/27b) 각각 테스트셋 실행 → 모델별 약점 카드화 → WP2/WP5로 환류.
- `git diff frontend/` = 0, `git diff slide_layout.py layout.py` = 0(형식 계층만 변경) 확인.

---

## 6. 착수 순서 (WP6 내부)
1. `kb.py`(로더+키워드 검색) + `data/kb/`에 JSONL 배치 → 검색 동작 확인.
2. `prompts`/`llm` RAG 주입(근거 블록) — figure는 도메인카드만, content/slide는 design+domain.
3. `slidewrite.py` 텍스트 린터 → WP3 lint/repair 루프에 합류.
4. `tools.py`(choose_layout 등 결정적 도구) + 도구선택 배선(기본 post-gen, 옵션 tool-calling).
5. 업로드 조화(캡션 정규화·dedup) 강화.
6. `eval_llm.py`에 테스트셋 채점 연결 → RAG on/off·모델 3종 A/B.
7. vLLM 임베딩 인덱스로 업그레이드(선택).

## 7. 수용 기준 (WP6)
1. `kb.retrieve("CoWoS-L 비교", ["design","domain"])`가 ep-007/ep-006/sd-016 등 관련 카드를 반환.
2. 생성 시 근거 블록이 주입되고, 도메인 주장이 카드에 근거하거나 data-needed로 표기된다.
3. `slidewrite.lint`가 토픽형 타이틀·문단·비병렬 불릿·미확장 약어·근거없는 수치를 검출하고
   repair가 구체 지시로 환류한다.
4. `choose_layout`이 의도/이미지 수에 따라 결정적으로 템플릿을 추천(sd-018 규칙).
5. 업로드 이미지 캡션이 덱 용어로 정규화되고 근접중복이 dedup된다.
6. 테스트셋 18케이스가 `eval_llm.py`로 채점되며, RAG on이 off 대비 정확성/루브릭에서 향상.
7. figure(WP1) 슬라이드 렌더 불변, `frontend/*`·`layout.py`·`slide_layout.py` diff=0(형식 계층만 변경).

## 참고 출처(리서치)
- Assertion-Evidence: [PSU writing.engr](http://writing.engr.psu.edu/assertion_evidence_EA.html), [iBiology — Alley](https://www.ibiology.org/professional-development/power-point-slide-design/)
- Tufte data-ink/chartjunk: [Graficto — Tufte principles](https://graficto.com/blog/discover-edward-tuftes-essential-principles-for-effective-data-visualization/)
- Storytelling with Data: [Knaflic 요약](https://medium.com/analytics-vidhya/key-points-from-the-book-storytelling-with-data-by-cole-nussbaumer-knaflic-8c0a7b08960)
- 슬라이드 레이아웃/타이포: [Deckary — design guide](https://deckary.com/blog/pillar-powerpoint-design-guide)
- 패키징 용어 표준: [PCBSync — IPC-7094](https://pcbsync.com/ipc-7094-explained-complete-guide-to-flip-chip-wlbga-design-and-assembly/), [Wikipedia — CSP](https://en.wikipedia.org/wiki/Chip-scale_package)
- (구조별 출처는 `01_domain_knowledge.md` 하단 참조)
