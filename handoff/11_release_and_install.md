# WP12 — GitHub 공개 릴리스 + Ubuntu 24 설치 가이드 + 에이전트(opencode) 사용성

> 요구: ① 공개 커밋/푸시(기존 원격 repo — **Claude Code 로컬 환경에 remote/토큰 설정
> 있음**, `gh auth status`·기존 설정으로 확인, 불명 시 사용자에게 질문) ② URL만 알면
> **Ubuntu 24 + 로컬 LLM(qwen3.5-122b 또는 qwen3.6-27b) + opencode** 환경에서 충분히
> 셋업·사용 가능한 설치 가이드 동봉.
> 신규: `.gitignore`, `README.md`(전면 개편), `docs/INSTALL_UBUNTU.md`, `AGENTS.md`,
> (원격에 LICENSE 없으면) `LICENSE`. 이 WP는 **가장 먼저 R0(공개)를 실행**하고 나머지
> WP9~11을 커밋 단위로 쌓는다(§4).

## 1. 저장소 위생 (R0 — 최우선 실행)

현재 로컬에 git이 **없다**. 순서:

```bash
git init && git checkout -b main
# 원격: Claude Code 환경의 기존 설정/gh로 확인. 원격에 커밋이 있으면 fetch 후
# 병합 전략을 사용자에게 확인(빈 repo면 그대로 push -u).
```

`.gitignore` (누출 방지가 핵심 — **`data/config.json`에 API 키가 저장된다**):

```gitignore
.venv/
__pycache__/
*.pyc
.env
data/*                 # 세션·상호작용·설정(키!)·벤치 런 = 사용자 데이터
!data/kb/              # 지식카드는 코드 자산 — 버전 관리
data/kb/._*
._*                    # macOS AppleDouble (SMB 잔재)
.smbdelete*
*.tmp
```

- 첫 커밋 전 점검: `git grep -iI "api_key\|sk-" -- ':!*.md'`로 하드코딩 키 없음 확인,
  `data/` 밖의 개인 정보 없음 확인, `handoff/`는 공개에 포함(설계 이력 = 프로젝트 문서;
  사용자가 빼길 원하면 R0에서 질문 1회).
- `sample_deck.pptx`는 유지(데모). AppleDouble(`._*`)·`.smbdelete*`는 커밋 전 삭제.
- LICENSE: 원격 repo에 이미 있으면 그대로, 없으면 MIT 초안 추가 후 커밋 메시지에 명시
  (사용자 확인 항목으로 PR/커밋 본문에 남김).
- 커밋 단위: R0(위생+현재 스냅샷) → 이후 WP9/10/11 각각 독립 커밋(메시지에 WP 번호).

## 2. README.md 전면 개편 (공개용 첫인상)

현 README는 "thin vertical slice" 시절 — 실제는 WP1~8이 구현된 상태. 구성:

1. 한 줄 소개 + 데모 GIF/스크린샷 자리(단면도 트리·실시간 partial·벤치 히트맵 3장 —
   Claude Code가 mock으로 캡처).
2. 핵심 아키텍처 원칙 4개(JSON=진실 / LLM은 의미·코드는 geometry / Brief IR → 컴파일 /
   결정적 도구+RAG로 소형 모델 안정화) + mermaid 파이프라인 다이어그램
   (`프롬프트 → understand(Brief) → compile → layout → SVG/pptx`).
3. 탭 소개: 단면도 스튜디오(A/B 트리·Brief·편집기), 슬라이드, 덱, 설정, 벤치.
4. Quick start(MOCK=1 — 모델 없이 3분), 실모델 연결(설정 탭/env), 지원 도메인 표
   (packaging/photonic/mobile/watch/infographic), 벤치 실행법.
5. 문서 링크: `docs/INSTALL_UBUNTU.md`, `AGENTS.md`, `handoff/00_HANDOFF.md`(설계 이력).

## 3. `docs/INSTALL_UBUNTU.md` — Ubuntu 24.04 + vLLM(qwen) + opencode

**작성 원칙(요구의 핵심)**: 이 가이드는 사람뿐 아니라 **로컬 LLM 에이전트(opencode)가
그대로 실행해도 성공**하도록 쓴다 — 모든 단계가 ① 복붙 가능한 커맨드 ② 성공 판정
커맨드+기대 출력 ③ 실패 시 진단 힌트의 3줄 구조. 모호한 서술 금지.

목차(각 절을 위 3줄 구조로):

```
0. 요구 사양: Ubuntu 24.04, Python 3.12(기본), git, (모델 서빙 시) NVIDIA 드라이버+CUDA,
   VRAM 가이드 — qwen3.6-27b: bf16 ≈ 60GB+(2×A6000/1×H100), AWQ/GPTQ 4bit ≈ 20GB(1×3090/4090);
   qwen3.5-122b(A10B MoE): bf16 다GPU/서버급, 4bit ≈ 70GB+ — [모델 카드 기준으로 착수 시 재확인]
1. 앱 설치: git clone <REPO_URL> → python3 -m venv .venv → pip install -r requirements.txt
   검증: MOCK=1 uvicorn app:app --app-dir backend --port 8000 → curl localhost:8000/api/config
2. 스모크: cd backend && MOCK=1 python smoke_test.py → "ALL PASSED"
3. (옵션) true render: sudo apt install libreoffice poppler-utils
4. vLLM 서빙: uv venv 별도 권장 → uv pip install vllm →
   vllm serve <HF모델ID 또는 로컬경로> --port 8001 --max-model-len 32768 \
     --guided-decoding-backend xgrammar [--tensor-parallel-size N] [--quantization awq]
   ⚠ 모델 ID·플래그는 vLLM/모델 버전에 따라 다름 — Claude Code는 작성 시점의 vLLM 문서와
   Qwen 모델 카드를 확인해 실측 커맨드로 채울 것. 검증: curl localhost:8001/v1/models
5. 앱↔모델 연결: 설정 탭에서 qwen27b/qwen122b 엔드포인트 base_url=http://<host>:8001/v1,
   model=<서빙 모델명>, json_mode=guided_json 등록 → [테스트] 버튼 → ok
   (headless면 POST /api/config 커맨드 제공)
6. 검증 실행: python eval_llm.py (골든 통과율 출력) → 벤치 탭에서 소규모 카테고리 런
7. opencode 연동: opencode 설치(공식 설치 스크립트/npm — 작성 시점 문서 확인) →
   프로젝트 루트의 opencode 설정에 로컬 프로바이더 등록(OpenAI 호환:
   base_url=http://localhost:8001/v1, 모델명) → AGENTS.md가 자동 로드됨을 확인 →
   예시 태스크: "backend에서 smoke_test를 실행하고 실패가 있으면 고쳐줘"
8. 트러블슈팅: guided_json 미지원 버전 → json_object 폴백, VRAM 부족 → 양자화/27b,
   CORS/방화벽, LibreOffice 미설치 시 UI 동작(경고만) 등
```

- **버전 민감 항목**(vLLM 플래그, opencode 설정 스키마, 모델 HF ID)은 Claude Code가
  작성 시점에 공식 문서로 확정하고, 가이드에 "검증한 버전: vllm==X.Y, opencode==Z" 표기.
- 27b vs 122b 선택 가이드 1문단: 27b=단일 GPU·프로파일(template-first)로 실용,
  122b=품질·멀티모달(첨부 이미지) — 벤치 탭 결과 링크.

## 4. `AGENTS.md` — 에이전트(opencode/Claude Code 공용) 작업 규약

opencode가 자동 로드하는 파일. 로컬 qwen급 에이전트도 안전하게 작업하도록 **짧고 명령형**:

```markdown
# pptx-copilot agent guide
## 실행/테스트 (이 순서로 검증)
- 서버: MOCK=1 uvicorn app:app --app-dir backend --port 8000
- 스모크: cd backend && MOCK=1 python smoke_test.py   # "ALL PASSED" 필수
- 라우팅 골든: smoke에 포함. 모델 평가: python eval_llm.py
## 불변 규칙 (위반 금지)
- 좌표·픽셀 계산은 backend/layout.py 에만. 렌더러(render_svg/export_pptx)에 좌표 금지.
- LLM 출력 스키마(models.py)에 좌표/색/물리치수 필드 추가 금지. 신규 figure는
  kind Literal 태그 + layout 함수 1개. 렌더러는 프리미티브만 소비.
- 지식은 단일 소스: 구조=domain.py / 아키타입=archetypes.py / 부품=parts.py /
  실장 레시피=assemblies.py / 서술 근거=data/kb/*.jsonl. 문자열 중복 금지.
- frontend는 빌드스텝 없음(vanilla). data/(kb 제외)는 커밋 금지.
## 자주 하는 작업 레시피
- figure kind 추가: models.py 모델 → layout.py 함수 → archetypes/examples 프리셋 →
  lint 한도 → routing 케이스 → smoke.
- 부품 추가: parts.py → (글리프 필요시 layout) → assemblies 레시피 → kb 카드 → 벤치 케이스.
- 벤치: POST /api/bench/run 또는 bench 탭. 회귀 확인 후 커밋.
```

(위는 골자 — Claude Code가 실경로/실커맨드로 완성. CLAUDE.md가 별도로 필요하면
AGENTS.md를 include하는 1줄 스텁으로 — 중복 금지.)

## 5. 착수 순서

```
R0. git init → .gitignore → 위생 점검(키 grep, ._* 삭제) → 원격 확인 → 첫 push (즉시)
R1. README 개편 + 스크린샷(mock) → push
R2. AGENTS.md → opencode로 실검증(로컬 qwen 에이전트에 스모크 태스크 시켜 성공 확인)
R3. INSTALL_UBUNTU.md → 깨끗한 Ubuntu 24 컨테이너/VM에서 가이드 그대로 재현 테스트
     (vLLM 절은 GPU 없으면 문서 검증만 + "미검증" 표기)
R4. 이후 WP9/10/11 완료분을 WP 단위 커밋으로 push
```

## 6. 수용 기준

1. 공개 repo에 main이 push되고, clone→`MOCK=1` 스모크가 새 환경에서 "ALL PASSED".
2. `git log`에 키/개인 데이터 없음(`data/config.json` 등 gitignore 동작 확인,
   히스토리에 한 번도 들어가지 않음).
3. INSTALL 가이드만 보고(사전 지식 없이) Ubuntu 24에서 mock 실행까지 15분 내 도달 가능
   (각 단계에 검증 커맨드 존재). vLLM 절은 실측 커맨드+검증 버전 표기.
4. opencode + 로컬 qwen이 AGENTS.md를 로드한 상태에서 "스모크 실행" 태스크를 성공한다.
5. README에 아키텍처 다이어그램·탭 스크린샷·도메인 표·문서 링크가 있고 현 구현과 일치.
6. 이후 커밋이 WP 단위로 남아 벤치 런(WP11)과 대조 가능.
