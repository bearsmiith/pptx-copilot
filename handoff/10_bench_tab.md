# WP11 — LLM 비교 벤치 탭 (자동 실행 → 채점 → 스코어보드) + 모델 프로파일

> 요구: 가용 LLM(haiku / qwen3.5-122b / qwen3.6-27b) 비교 테스트를 **자동으로 실행해
> 평가까지 도출하는 탭**. 테스트셋 + 벤치 방법 + 점수 시스템 설계 포함.
> 채점(사용자 확정): **결정적 채점이 기본 + 심판 LLM은 설정 가능**(끄거나, 어느
> 엔드포인트든 심판으로 지정).
> 신규: `backend/bench.py`, `frontend/bench.html`, `tests/bench_set.jsonl`,
> `data/bench/`(런 기록, gitignore). 변경: `app.py`(+4 엔드포인트, nav는 §5),
> `config.py`(judge/profile), `llm.py`(프로파일 소비), `eval_llm.py`(채점기 공유·재사용).

## 0. 설계 원칙

- **결정적 우선**: 재현 가능한 코드 채점이 점수의 본체. LLM 심판은 보조 축이며 끌 수 있고,
  심판 신원이 런에 기록된다(심판 바뀌면 런 간 비교에 경고 표시).
- **기존 자산 재사용**: 채점기는 `eval_llm.py`의 스키마/kind/라벨/lint 체크를 함수로 추출해
  공유. 실행은 기존 `JOBS` 폴링. 생성 경로는 실제 서비스 경로(`generate_diagram_slide`/
  `generate_brief_slide`/`generate_slide_layout`/`generate_plan+figures`)를 그대로 호출 —
  벤치가 곧 통합 테스트가 된다.
- **모델 선택은 config의 endpoints를 그대로**: haiku(claude_cli)/qwen122b/qwen27b + mock
  (하니스 자가 테스트용).

## 1. 테스트셋 — `tests/bench_set.jsonl` (~54케이스)

케이스 스키마(slide_testset와 호환 확장):

```json
{"id": "b-021", "mode": "diagram",            // diagram | slide | deck
 "category": "mobile",                         // packaging|photonic|mobile|watch|infographic|slide|deck
 "prompt": "스마트폰 메인보드 실장 단면. AP는 PoP, 쉴드캔 포함",
 "expect": {"genre": "physical", "figure_kind": null,
            "must_include_labels": ["PoP", "shield"], "must_not": ["wirebond"],
            "structure": "smartphone_mainboard", "slide_count": null},
 "judge_focus": "PoP 2단 볼과 쉴드캔 덮개가 실제 기하로 표현됐는가"}
```

구성(기존 18 + 신규 ~36): packaging 10(FCBGA/CoWoS/EMIB/HBM/fan-out/하이브리드/글라스/
백사이드/QFN/PoP), photonic 8(TX/RX/CPO/laser-on-PIC/V-groove/버터플라이/CIS/VCSEL),
mobile 6, watch 4(WP9 골든 포함), infographic 12(kind별 2 — 라우팅 함정 케이스 포함:
"HBM 로드맵"=timeline), slide 8(이미지+텍스트 slsessions 경로), deck 2(장수 준수),
질문 트리거 4(정보 부족 → questions 반환 기대). 각 케이스 `tags`로 WP9 신규 도메인 표시.

## 2. 점수 시스템

### 2.1 결정적 채점 (100점 만점 기준 70점, 심판 off면 100으로 재정규화)

| 항목 | 배점 | 판정 |
|---|---|---|
| schema_valid | 15 | 1차 검증 통과(수리 후 통과는 절반) |
| kind/genre_expected | 10 | expect.figure_kind/genre/structure 일치 |
| must_include_labels | 15 | 부분일치 허용, 개수 비례 |
| must_not | 10 | 위반 0 = 만점, 건당 감점 |
| lint_clean | 10 | error 0 = 만점, warn 건당 소감점 |
| geomcheck | 5 | 레이아웃 사후 검사 통과 |
| render_ok | 5 | SVG+pptx 왕복(smoke 기준) |
| question_behavior | 10 | 질문 기대 케이스에서 질문함 / 명확 케이스에서 안 함 |

부가 지표(점수 외 별도 컬럼): p50/p95 지연, 재시도(수리 루프 진입) 비율, 출력 토큰,
비어있는 figure 비율. **품질 점수와 비용 지표를 섞지 않는다.**

### 2.2 LLM 심판 (30점, 설정 가능)

- config에 `bench: {judge_endpoint: "haiku" | "qwen122b" | ... | "off"}` — settings 탭이
  아니라 **bench 탭 안 셀렉터**(런 파라미터, 런 기록에 저장).
- 루브릭 3축 × 0-2점(각 10점 환산): **accuracy**(도메인 사실·구조 순서),
  **faithfulness**(요청·judge_focus 충족), **design**(kb 디자인 카드 기준 가독/밀도/위계).
- 심판 입력: 요청 + 산출 슬라이드 JSON + 결정적 채점 결과(Findings) + judge_focus.
  JSON 강제(`{"accuracy":0-2,"faithfulness":0-2,"design":0-2,"rationale":"..."}`) —
  guided_json 가능한 엔드포인트면 스키마 고정, haiku면 프롬프트 강제+수리 1회.
- 편향 통제: 절대 채점(모델 간 비교 없음), 모델명 비노출, 같은 런은 같은 심판, 심판=피평가
  모델인 셀은 결과표에 `*` 표시.

### 2.3 집계

- 케이스 점수 → category별 평균 → 종합(카테고리 동일 가중). 모델×카테고리 히트맵.
- **회귀 비교**: 런 A vs B(같은 세트) 델타 표 — WP9/모델 프로파일 튜닝의 효과 측정 도구.
- 저장: `data/bench/run_{ts}.json` {config 스냅샷, 심판, 케이스별 원자료(생성 JSON·SVG·
  점수·심판 rationale), 집계}. 목록/조회 API로 과거 런 열람.

## 3. 실행기 — `backend/bench.py`

```python
def run_bench(endpoints: list[str], case_ids: list[str] | None, judge: str | None,
              job_id: str) -> dict:   # JOBS 진행문자열: "qwen27b · 12/54 · b-021"
```

- 엔드포인트별 순차 실행(케이스 순서 고정, 온도 등 생성 파라미터는 서비스 기본과 동일),
  케이스당 타임아웃(기본 180s)·실패 격리(예외 = 해당 케이스 0점 + 오류 기록).
- mode 디스패치: diagram → `generate_brief_slide`(physical) / `generate_diagram_slide`,
  slide → `generate_slide_layout`(번들 더미 이미지 자산 포함), deck → `generate_plan`→
  `confirm` 경로 함수 직접 호출. 질문 케이스는 intake 산출(questions)로 채점.
- 채점기는 `bench.score_case(case, output, findings, timings)` 순수 함수(단위테스트).
- 부분 실행(카테고리/케이스 필터, 엔드포인트 1개만)과 재개(런에 케이스 추가) 지원 —
  122b 풀런이 길어질 수 있으므로.

## 4. API + 탭 UI

```
POST /api/bench/run        {endpoints[], categories?, case_ids?, judge?} → {job_id, run_id}
GET  /api/bench/runs       → 목록(요약: 날짜/세트/모델/심판/종합점수)
GET  /api/bench/run/{id}   → 전체(집계+케이스 원자료)
GET  /api/bench/cases      → bench_set 목록(탭의 케이스 브라우저)
```

`frontend/bench.html`(신규 탭, nav에 "벤치" 링크 — 기존 3 html의 nav에 한 줄씩 추가 승인):
- 상단: 엔드포인트 체크박스(+mock), 카테고리 필터, 심판 셀렉터(off 기본), [실행 ▶].
- 진행: 기존 pollJob 재사용(진행 문자열 + 경과).
- 결과: ① 모델×카테고리 히트맵(점수 색상) ② 모델별 종합/비용 지표 카드
  ③ 케이스 드릴다운 — 한 케이스의 모델별 SVG 나란히 + 점수 내역 + 심판 rationale
  (실패 원인 육안 비교가 이 탭의 핵심 가치) ④ 런 비교 드롭다운(delta 표).

## 5. 모델 프로파일 ("그 외 개선" — 측정→개선 루프의 개선 절반)

벤치로 드러나는 모델별 약점을 **엔드포인트별 프로파일**로 흡수(`config.py` endpoints에
`profile` 키, `llm.py`가 resolve 시 적용):

```json
"qwen27b":  {"profile": {"kb_k": 3, "template_first": true,  "kind_docs_max": 2,
             "lint_repair_rounds": 1, "temperature": 0.3}},
"qwen122b": {"profile": {"kb_k": 5, "template_first": false, "kind_docs_max": 3}},
"haiku":    {"profile": {"kb_k": 5, "kind_docs_max": 3}}
```

- 현재 env 전역인 `TEMPLATE_FIRST`/`LINT_REPAIR_ROUNDS`/kb k를 프로파일이 오버라이드
  (env 미설정+프로파일 없음 = 기존과 동일 — 하위호환).
- 27b 기본 프로파일: template-first on, kind 문서 2개로 압축, 수리 1라운드 — WP2 방향의
  코드화. **프로파일 변경 → 벤치 재실행 → 델타 확인**이 표준 튜닝 루프가 된다.
- (탐색 항목, 벤치로 검증 후 채택) 27b에서 assembly 자유 생성 대신 Brief-경유 강제,
  122b 멀티모달로 첨부 이미지 케이스 확장, haiku CLI 병렬도 조정.

## 6. 착수 순서

```
1. bench_set.jsonl(기존 18 이관+확장) + score_case 채점기(eval_llm 로직 함수화 공유)
2. bench.py 실행기 (mock 엔드포인트로 하니스 e2e 검증 — 점수·저장·재개)
3. API 4종 + bench.html (히트맵→드릴다운→런 비교 순)
4. 심판 채점(설정형) + 심판=피평가 표시
5. 모델 프로파일(config/llm) + 3모델 실런 → 첫 공식 스코어보드 커밋(data/bench는 로컬,
   요약 markdown을 handoff/bench_baseline.md로 기록)
6. eval_llm.py는 채점기 공유 후 CLI 래퍼로 유지(CI/스모크용 축약 실행)
```

## 7. 수용 기준

1. mock 엔드포인트로 전 케이스 실행 → 점수/저장/조회/드릴다운 동작(모델 무관 하니스 검증).
2. 3모델 실행 시 모델×카테고리 히트맵과 케이스별 SVG 나란히 비교가 표시되고, 런 기록에
   config 스냅샷+심판 신원이 저장된다.
3. 심판 off 런과 on 런이 모두 가능하고, off 시 결정적 70점이 100으로 재정규화된다.
   심판=피평가 모델 셀에 `*` 표시.
4. 질문 트리거 케이스 4종이 question_behavior 항목으로 채점된다(질문해야 할 때 안 하면 감점,
   명확한데 물으면 감점).
5. 런 2개 비교에서 케이스 단위 델타가 표로 나오고, 프로파일 변경 전후 효과가 재현된다.
6. 부분 실행/재개가 동작하고 케이스 실패가 런 전체를 죽이지 않는다.
7. `python eval_llm.py`(축약 CLI)가 여전히 동작(채점기 공유, 기존 골든 무회귀).
