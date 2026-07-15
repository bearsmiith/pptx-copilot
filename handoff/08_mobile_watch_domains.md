# WP9 — 도메인 확장(mobile/watch 실장 + photonic·packaging 잔여 갭) + 디자인 품질

> 목표: photonic IC / packaging / **mobile 실장구조 / watch 실장구조** 4개 도메인을 이해하고
> 유연하게 그린다. 범위(사용자 확정): **보드/패키지 레벨 먼저**, 풀 디바이스 분해는 후순위 백로그.
> 기반: WP8 `assembly` 통합 scene이 이미 양면 실장(`side:"bottom"`)·chip-on-chip(`on`)·
> mount 8종·광빔·매립 채널을 지원 — mobile/watch는 **부품·레시피·지식 추가**가 본체다.
> 신규: `backend/assemblies.py`(assembly 레시피 단일 소스), `data/kb/mobile_watch_assembly.jsonl`.
> 변경: `parts.py`, `models.py`(글리프 소폭), `layout.py`(신규 글리프), `router.py`,
> `understand.py`, `examples.py`, `lint.py`, `eval_llm.py`, `tests/*`, kb 카드.

## 0. 현황 대비 갭 (2026-07 코드 기준)

| 도메인 | 현황 | 갭 |
|---|---|---|
| packaging | domain.py 레시피 + assembly + 07b 갭 1-5 반영 | PoP(2단 볼)·TMV·conformal shield 없음 |
| photonic | planar graph + assembly(빔/매립/edge_couple) + parts(laser/pd/pic/lens/fiber/mems) | V-groove 파이버, microlens array 행, CIS 컬러필터, glass lid (07b 갭 6-7 잔여) |
| mobile | **없음** | 부품(AP PoP, shield can, BTB, FEM…)·레시피·지식 전부 |
| watch | **없음** | SiP 오버몰드 레시피·지식 전부 |

## 1. 부품 추가 — `parts.py` (mobile/watch/photonic 잔여)

기존 스키마 그대로 확장. 각 부품: function 키, aka, 재질/글리프, 허용 interface, 실장 사실 주석.

```python
# ---- mobile board-level ----
"ap_pop":      {"aka": ["AP", "SoC", "PoP", "에이피"], "material": "silicon",
                # PoP: 하단 AP 패키지 위에 DRAM 패키지를 볼로 2단 적층 (internal 재귀로 표현)
                "interfaces": ["solder"], "internal": "pop_recipe", "width": 0.28},
"dram_pkg":    {"aka": ["LPDDR", "DRAM 패키지"], "material": "silicon",
                "interfaces": ["solder"]},
"nand":        {"aka": ["NAND", "UFS", "낸드"], "material": "silicon", "interfaces": ["solder"]},
"pmic":        {"aka": ["PMIC", "전력관리"], "material": "silicon", "interfaces": ["solder"], "width": 0.1},
"rf_fem":      {"aka": ["FEM", "front-end module", "PA 모듈"], "material": "silicon",
                "interfaces": ["solder"], "note": "내부가 SiP(PA+필터+스위치) — internal 재귀 가능"},
"shield_can":  {"aka": ["쉴드캔", "shield can", "EMI 쉴드", "차폐캔"], "glyph": "shield_can",
                "material": "leadframe", "covers": True,     # 아래 부품들을 덮는 뚜껑
                "interfaces": ["solder"],  # 접지 패드 fence에 솔더/클립
                "note": "프레임+리드 2피스, 보드 접지 fence 위"},
"btb_conn":    {"aka": ["BTB", "board-to-board", "커넥터"], "glyph": "connector",
                "material": "metal", "interfaces": ["solder"], "width": 0.12},
"flex_pcb":    {"aka": ["flex", "FPC", "플렉스"], "glyph": "flex_ribbon", "material": "polymer"},
"passive_01005": {"aka": ["MLCC", "01005", "0201", "passives"], "glyph": "chips",
                "material": "dielectric", "interfaces": ["solder"], "width": 0.03},
"crystal":     {"aka": ["크리스탈", "수정 발진기", "XTAL"], "material": "metal", "interfaces": ["solder"]},
# ---- watch ----
"sip_module":  {"aka": ["SiP", "watch SiP", "S-SiP"], "is_base": False, "internal": "watch_sip",
                "interfaces": ["solder"],  # 외부는 LGA/BGA
                "note": "보드 전체를 단일 오버몰드 모듈로 — 방수/소형화"},
# ---- photonic 잔여 (07b 갭 6-7) ----
"fiber_vgroove": {"aka": ["V-groove", "파이버 어레이", "FAU"], "glyph": "v_groove"},
"microlens_arr": {"aka": ["마이크로렌즈", "MLA"], "glyph": "dome_array", "material": "glass"},
"color_filter":  {"aka": ["컬러필터", "Bayer"], "glyph": "bayer_row"},
"glass_lid":     {"aka": ["글라스 리드", "cover glass"], "material": "glass"},
```

## 2. 신규 글리프 — `layout.py` (assembly 렌더에 4종)

기존 프리미티브 조합, 렌더러 diff 0 원칙 유지:

- `shield_can`: ㄷ자(뚜껑+양쪽 벽) PolyShape, 덮는 대상은 `AssemblyPart.covers: list[str]`
  (models.py에 필드 추가) — 컴파일러가 대상 부품들의 bbox를 계산해 뚜껑 폭/높이 결정.
  벽 하단은 기판 위 접지 패드(작은 Rect 2개).
- `connector`: 낮은 직사각 + 상단 톱니(작은 Rect 나열) — BTB 수/높이 고정 상수.
- `flex_ribbon`: 완만한 S-곡선 리본(PolyShape, `_wirebonds`의 ribbon 기법 재사용) —
  보드 밖으로 나가는 표현(끝을 figure 경계에서 컷).
- `v_groove`: 사다리꼴 홈 + 파이버 원(CircleShape) in-groove; `dome_array`: `_dome_poly` N개
  나열; `bayer_row`: 얇은 layer를 3-4색 교대 셀로 분할(accent 계열 재사용).

`MountKind`에 변경 없음. **PoP·TMV**는 글리프가 아니라 구조로: PoP = 부품 내부 구조 재귀.
⚠ WP8 문서의 `Part.internal`은 **구현에서 빠졌음(2026-07-15 코드 확인)** — 이번에
`brief_model.Part.internal: Optional[Brief]`를 추가하고 compile_brief에 **1단 재귀만**
구현한다(재귀 부품은 자기 bbox 안에서 미니 assembly로 전개; 2단 이상은 라벨로 축약).
TMV = 몰드 layer에 `vias`(AssemblyBaseLayer.vias 재사용, 몰드 관통).

## 3. 레시피 단일 소스 — `backend/assemblies.py` (신규, domain/archetypes/parts와 대칭)

물리 scene 레시피를 Brief 형태로 저작 — understand의 few-shot, templates(template-first),
examples 갤러리, eval 골든이 전부 이걸 참조:

```python
ASSEMBLIES: dict[str, dict] = {
  "smartphone_mainboard": {
    "aka": ["스마트폰 메인보드", "휴대폰 기판", "mobile 실장", "logic board", "SLP"],
    "brief": {  # genre=physical, emphasis=section
      "base": "slp",   # SLP 다층 기판 (base_layers 3-4 + vias)
      "parts": [ap_pop(top, PoP), nand(top), pmic(bottom), rf_fem(bottom),
                passives(양면 다수), shield_can(covers=[ap_pop, nand]),
                btb_conn(top), flex_pcb(btb에 연결)],
      "requirements": ["양면 실장", "PoP 2단", "쉴드캔이 AP·NAND를 덮음"]},
    "must_label": ["PoP", "shield can", "SLP"], "caption": "smartphone main board (not to scale)"},
  "watch_sip": {
    "aka": ["워치 SiP", "watch SiP", "스마트워치 실장", "S-SiP"],
    "brief": {"base": "sip_substrate",
      "parts": [ap(top, flipchip), pmic(top), memory(top, wirebond), rf(top),
                passives(양면), mold(전체 오버몰드), bottom_balls(LGA)],
      "requirements": ["단일 오버몰드", "베어다이 와이어본드+플립칩 혼재", "외부 LGA"]},
    "must_label": ["SiP", "mold", "LGA"]},
  "pop_package":    {...},   # 단독 PoP 상세 (TMV 포함)
  "butterfly_laser": {...},  # photonic: laser-on-submount + TEC + 파이버 (07b 카탈로그)
  "cis_module":     {...},   # microlens + Bayer + BSI + 로직 하이브리드본드 + glass lid
  "fiber_attach":   {...},   # PIC + V-groove 파이버 어레이 + edge couple
}
```

`templates.match_structure`가 ASSEMBLIES aka도 검색(template-first 경로에 합류; 소형 모델은
레시피 인스턴스화가 가장 안전). `understand`의 부품 후보 목록에 parts 신규 키 주입.

## 4. 지식 카드 — `data/kb/mobile_watch_assembly.jsonl` (신규 ~18장)

type="domain", 기존 스키마. 핵심 사실(카드 초안 — Claude Code는 이를 다듬어 저작, 필요 시
공개 자료로 보강):

- **PoP**: AP 패키지 위 DRAM 패키지 볼 적층. 이유(면적 절약·배선 단축), 하단 fan-out/FC +
  상단 메모리 BGA, TMV로 상하 연결. must: 볼 2단이 보여야 함.
- **SLP/mSAP**: 스마트폰 보드는 substrate-like PCB(10+층, 세미어디티브 미세배선).
- **양면 실장**: 리플로우 2회(1차면 접착제/표면장력), 대형 BGA·커넥터는 보통 같은 면.
- **shield can**: EMI 차폐 뚜껑, 접지 패드 fence에 솔더/클립. 프레임+커버 2피스(리워크).
- **샌드위치 보드**(최근 폰): 보드 2장을 스페이서 보드로 적층해 부품 대면 배치 — 후순위 표현.
- **BTB 커넥터**: 디스플레이/배터리/카메라 flex 연결, 낮은 결합 높이, 다핀.
- **언더필/코너본드**: 낙하 신뢰성 위해 AP·대형 BGA 모서리 보강.
- **conformal shield**: 패키지 표면 스퍼터 금속막(캔 없는 차폐) — 외곽선 강조로 표현.
- **watch SiP**: 메인보드 전체를 단일 SiP 모듈로(수십 die+수백 passives를 한 기판에 실장 후
  오버몰드, 외부 LGA/BGA). 목적: 소형화·방수·낙하 신뢰성. 베어다이 WB/FC 혼재, 초소형
  01005 passives, 몰드 관통 비아(TMV)로 상면 차폐/접지.
- photonic 잔여: V-groove 파이버 정렬(passive alignment), 버터플라이 모듈(TEC+submount),
  CIS 적층(BSI+하이브리드본드 로직+마이크로렌즈+Bayer), VCSEL+MLA.
- packaging 잔여: EMC 몰드 vs 리드 구분, LGA vs BGA 차이.

각 카드에 `structure` 키(위 ASSEMBLIES 키와 일치) — kb 검색 가중치 재사용.

## 5. 라우팅/이해 확장 — `router.py`, `understand.py`

- `router.py`의 kind 키워드 셋(stack 항목)과 `_genre`/`genre_question` 경로에 mobile/watch
  신호 추가: 메인보드/실장/mainboard/PoP/SiP/쉴드캔/양면/logic board/워치/스마트폰 기판 →
  genre=physical 신뢰도↑. `_INTENT`는 무변경(물리 구조는 Brief 경로가 담당).
- `understand` 프롬프트의 function 후보 목록에 신규 parts 주입(§1) — 자유 서술이 아니라
  키 선택. `open_questions` 트리거에 "양면인지", "쉴드캔 포함 여부", "PoP 여부" 추가
  (모호 시에만 — filler 금지 원칙 유지).

## 6. 디자인 품질 (보기 좋은 슬라이드) — 지식 + 렌더 폴리시

### 6.1 kb 디자인 카드 확장 (`data/kb/slide_design.jsonl`에 +12장)
라벨 밀도(단면도 콜아웃 ≤7, 초과 시 그룹핑), 콜아웃 리더라인 규칙(교차 금지·같은 쪽 정렬),
색 위계(강조 1색 원칙, semantic accent 사용처), 여백 시스템(슬라이드 마진·figure 패딩 비율),
폰트 스케일(타이틀:본문:캡션 ≈ 1.6:1:0.8), 표 데이터-잉크(세로선 제거), 다크 재질 위 라이트
텍스트 대비, 캡션 honesty(not-to-scale), 양면 실장 도해 관례(위/아래 라벨 분리), 첫 슬라이드
어서션 타이틀, KPI 카드 위계(값>라벨>델타), 차트 0-기준선.

### 6.2 렌더 폴리시 패스 — `layout.py`/`render_svg.py`/`slide_render.py` 상수 정리
- 마진/갭/폰트 크기를 파일 상단 **디자인 토큰 상수 블록**으로 모으고(현재 함수별 산재),
  값 자체를 카드 규칙에 맞게 1회 튜닝(타이틀 밴드 높이, 캡션 위치, 콜아웃 리더라인 각도).
- 라벨 충돌 완화: 콜아웃 y-정렬 시 겹침 감지 → 최소 간격으로 y-쉬프트(순수 함수, 이미
  정렬 로직 있으면 보강).
- pptx 폰트: 한글 폴백 명시(예: Noto Sans KR → 맑은 고딕) — export_pptx 텍스트 런에 지정.
- **골든 SVG 회귀**: 대표 프리셋 12종의 SVG 해시를 `tests/golden_svg.json`에 저장,
  smoke_test가 비교(의도된 폴리시 변경 시 해시 갱신 커밋). 이후 시각 변경이 diff로 보인다.

## 7. 평가 확장 — `eval_llm.py`, `tests/`

- GOLDEN에 추가: "스마트폰 메인보드 단면, PoP와 쉴드캔 표시"(smartphone_mainboard,
  ["PoP", "shield"]), "애플워치식 SiP 실장 단면"(watch_sip, ["SiP", "mold"]),
  "PIC에 V-groove 파이버 어레이 결합"(fiber_attach, ["V-groove"]), "CIS 센서 적층
  단면"(cis_module, ["microlens"]).
- `tests/routing_testset.jsonl`에 mobile/watch genre 판정 케이스 +6.
- `tests/slide_testset.jsonl`에 도메인 케이스 +6 (WP11 벤치 세트가 이를 포함).

## 8. 착수 순서

```
1. parts.py 신규 부품 + models.covers + layout 글리프 4종 → mock/프리셋 렌더 확인
2. assemblies.py 레시피(6종) + templates/understand/examples 연결 → template-first로 즉시 동작
3. kb 카드 2파일(mobile_watch 18 + design 12) → 검색 확인
4. router/understand 신호 확장 → routing 골든 +6 통과
5. 렌더 폴리시(토큰화→튜닝→골든 SVG 스냅샷) → smoke 확장
6. eval GOLDEN/테스트셋 확장 → 3모델 실행 기록
```

## 9. 수용 기준

1. "스마트폰 메인보드 실장 단면, AP는 PoP, 쉴드캔 포함" → genre=physical, 양면 실장 +
   PoP 2단 볼 + 쉴드캔(뚜껑이 AP·NAND bbox를 덮음)이 **기하로** 렌더. pptx 왕복 일치.
2. "워치 SiP 단면" → 단일 오버몰드 + WB/FC 혼재 + 하단 LGA 렌더, must_label 포함.
3. photonic 잔여: V-groove 파이버, microlens array, CIS 스택 프리셋이 smoke 통과.
4. routing/eval 골든 신규 케이스 통과율 기존 수준(≥90%) 유지, 기존 골든 무회귀.
5. 골든 SVG 스냅샷 12종이 smoke에서 검증되고, 폴리시 변경이 해시 diff로 드러난다.
6. kb 카드가 검색되어 생성 프롬프트에 주입됨(로그 확인), 근거 없는 수치는 data-needed.
