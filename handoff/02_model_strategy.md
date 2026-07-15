# WP2 — 모델별 실행 전략 (haiku / qwen3.5-122b / qwen3.6-27b)

> 대상 파일: `backend/llm.py`, `backend/prompts.py`, `backend/app.py`(스테이지 라우팅),
> `README.md`(env 문서). UI 불변.
> 목표: 서로 능력 편차가 큰 3개 모델이 **같은 파이프라인**에서 신뢰성 있게 동작하도록,
> 디코딩 제약·프롬프트·태스크 분해·티어 라우팅을 모델 특성별로 정한다.
> 핵심 명제: **"소형 모델은 자유형 DSL을 줄이고, 확정적 도구(WP3)에 일을 넘길수록 안정된다."**

---

## 0. 현재 상태 (llm.py 기준)

- provider 자동 선택: `LLM_PROVIDER` → `MOCK` → `OPENAI_BASE_URL`(openai) → `claude` 바이너리(claude_cli) → mock.
- `MODEL` 단일 env로 모든 스테이지 공용. JSON 모드: `json_schema`(strict) / `guided_json`(vLLM) / `json_object`.
- 모든 호출에 pydantic 검증 + **1회 repair 왕복**이 이미 있음(`_validated`, `generate_deck`).
- 스테이지: PLAN(아웃라인) → FIGURES(도형별) → FINAL. 단면도 트리(dsession) A/B 병렬.

이 골격은 좋다. WP2는 **모델별 최적 파라미터 + 스테이지별 모델 라우팅 + 소형 모델용 template-first 경로**를 얹는다.

---

## 1. 모델 프로파일과 전략

### 1.1 haiku (Claude, `claude_cli` provider)
- 특성: 지시 준수·리페어 강함, **vision 지원**(첨부 이미지 Read), **tool-use 가능**.
  API 키 불필요(호스트 로그인). 저지연·저비용 → A/B 2안 병렬 부담 적음.
- 전략:
  - 자유형 DSL 생성 OK(플랜/피규어 모두). 시스템 프롬프트 few-shot 1개면 충분.
  - **디코딩 제약이 없다**(CLI는 grammar 미지원) → 대신 **WP3 validate→repair 루프에 의존**.
    현재 정규식 `_extract_json`이 마크다운 펜스를 견디게 유지.
  - tool-use 경로(선택): `validate_deck`/`instantiate_template`을 도구로 노출하면 haiku가
    스스로 검증·수정. 단, 기본은 post-gen 루프(전 provider 공통)로 두고 tool-use는 옵션.
  - 온도 낮게(0.2~0.3). 첨부 있으면 `allow_read=True` 유지.
  - 역할: **PLAN 스테이지 기본값**(질문 생성·판단 필요) + 첨부 해석.

### 1.2 qwen3.5-122b (vLLM, `openai` provider, 네이티브 멀티모달)
- 특성: 대형 MoE, 이미지 base64 파트 수용(코드 이미 가정). vLLM `guided_json`로 **스키마
  제약 디코딩** → JSON 파싱 실패가 구조적으로 사라짐.
- 전략:
  - `LLM_JSON_MODE=guided_json` 권장(strict json_schema보다 Union/oneOf 호환성 우수, §3).
  - 능력 충분 → 자유형 DSL + 상세 도메인 프롬프트 소화. **아키텍트(PLAN) 및 복잡 피규어** 담당.
  - 온도 0.3~0.4. A/B 방향(정석/대안)에서 다양성 담당.
  - 첨부 처리는 `_openai_user_content`(base64 image_url) 경로 유지.
  - 역할: **고난도 FIGURE 생성 기본값**, 필요 시 PLAN도.

### 1.3 qwen3.6-27b (vLLM, `openai` provider) — **소형 워크호스**
- 특성: 27B급 → 장기·다필드 자유형 DSL에서 오류율↑, 긴 프롬프트에 취약. 그러나 빠르고 저렴.
- 전략(가장 중요, WP3와 직결):
  - **Template-first**: 자유형 DSL 대신 **템플릿 선택 + 슬롯 채우기**를 우선.
    출력 예: `{"structure":"hbm","params":{"n_dram":8,"joint":"ubump"},"title":"..."}`.
    이 초소형 출력은 `guided_choice`(structure는 enum)로 강제 → 거의 실패 안 함.
    이후 WP3 `templates.instantiate()`가 확정적으로 full DSL로 팽창.
  - 템플릿이 없는 요청만 자유형 DSL 폴백(축소 스키마, 아래).
  - **축소 스키마**: 27B 전용으로 optional 필드가 적은 스키마 뷰를 guided_json에 사용
    (예: embeds/vias 등 고급 필드를 뺀 `StackRowLite`). 오류 표면적↓.
  - 프롬프트는 **짧게**. 도메인 규약 전체를 넣지 말고 선택된 구조의 `domain.STRUCTURES[x]["rules"]`만 주입.
  - 온도 0.1~0.2(결정성↑). repair 루프 최대 2회로 상향.
  - 역할: **단순 단일 단면도**, PLAN 확정 후 **FIGURE 대량 채우기**.

---

## 2. 스테이지별 모델 라우팅 (신규)

단일 `LLM_MODEL` → **스테이지별 오버라이드**로 확장. `_call`/`_validated`에 `role`/`stage` 인자를 추가하고
모델·provider·JSON모드를 조회하는 얇은 레지스트리를 둔다.
```
LLM_MODEL_PLAN     = haiku            # 판단·질문 생성 (없으면 LLM_MODEL로 폴백)
LLM_MODEL_FIGURE   = qwen3.5-122b     # 도형 생성
LLM_MODEL_FILL     = qwen3.6-27b      # 템플릿 슬롯필/대량 채우기
LLM_MODEL          = <기존 단일 폴백>
```
- 라우팅 원칙: **판단이 필요한 곳엔 큰 모델, 확정적 팽창이 가능한 곳엔 작은 모델**.
  - PLAN(아웃라인/질문) → PLAN 모델
  - FIGURE(그림 계획→DSL) → 복잡하면 FIGURE 모델, 템플릿 매치되면 FILL 모델+templates
  - EDIT/REVISE(국소 수정) → FILL 모델로 충분(적은 변경)
- 구현은 얇게: provider별 클라이언트/바이너리 선택 로직을 모델명 기준으로 분기.
  하위호환: 오버라이드 env가 없으면 지금과 100% 동일 동작.

### 2.1 Template-first 결정 로직 (FILL 경로)
```
1) 요청/plan을 domain.STRUCTURES의 aka/키워드로 매칭 → 후보 structure.
2) 후보 있으면: FILL 모델에 guided_choice로 structure∈{후보들, "custom"} + params 요청.
3) structure != custom → templates.instantiate(structure, params) (LLM 자유형 DSL 안 씀).
4) structure == custom → 축소 스키마 자유형 DSL + repair.
5) 결과는 항상 WP3 lint→repair 통과 후 확정.
```

---

## 3. 디코딩/스키마 호환성 노트 (구현 주의)

- **guided_json vs json_schema(strict)**: DSL의 Union(`StackRow`)은 oneOf/discriminator로
  표현된다. OpenAI strict json_schema는 일부 oneOf/`$ref` 조합을 거부할 수 있다 →
  vLLM는 `guided_json`(xgrammar/outlines) 사용 권장. Union엔 `Field(discriminator="type")`를
  명시해 문법을 작게/명확하게(디코딩 속도·정확도↑).
- **신규 row 추가 시 문법 팽창**: `BondRow`·`DieStackRow`가 늘면 grammar가 커진다.
  소형 모델(27B)엔 축소 스키마로 완화(§1.3).
- **guided_choice**: 템플릿/enum 선택엔 full json 대신 choice 문법 사용(가장 안정).
- **claude_cli**: grammar 없음 → 검증은 전적으로 post-gen. `_extract_json` 견고성 유지.

---

## 4. 프롬프트 조정 (모델 공통 + 소형 특화)

- 공통: 현재 HARD RULES/few-shot 유지. 도메인 규약은 WP1대로 **요약만** 상주.
- 소형(27B): 스테이지에서 **선택된 구조의 rules/must_label만** 동적 주입(`domain.py`에서).
  전체 규약 블록을 빼서 컨텍스트를 짧게.
- repair 메시지: 현재 "Your output failed validation: {err}"에 더해, WP3 lint 경고를
  **구체 지시**로 변환해 붙인다(예: "vias.count=5 must equal balls.count=8 to align; set 8").
  소형 모델일수록 "무엇을 어떻게" 고쳐야 하는지 명시가 효과 큼.

---

## 5. 평가/회귀 (모델 교체 안전망)

- `smoke_test.py`는 mock 전용 → **provider별 골든 평가 스크립트** 추가 권장(`eval_llm.py`):
  대표 프롬프트 N개 × 모델별로 생성 → (a)스키마 유효 (b)lint 경고 0~허용치
  (c)구조 키워드 라벨 존재율 측정. CI/수동으로 모델 회귀 감지.
- 지표: JSON 유효율, lint pass율, 평균 repair 왕복수, 지연/토큰. 27B는 template-first
  적용 전후 비교로 효과 정량화.

---

## 6. 수용 기준 (WP2)

1. env 오버라이드 없이 실행하면 **기존과 동일 동작**(하위호환).
2. `LLM_MODEL_PLAN/FIGURE/FILL` 지정 시 스테이지별로 다른 모델이 호출됨(로그로 확인).
3. 27B FILL 경로에서 template-match 요청은 자유형 DSL을 생성하지 않고 templates로 팽창.
4. guided_json 경로에서 신규 row 포함 스키마가 디코딩되고 유효 JSON을 반환.
5. lint 경고가 repair 메시지에 구체 지시로 반영된다.
6. 프론트엔드 diff = 0.
