# WP1 — 단면도 도메인 지식 + 디자인 확장

> 대상 파일: `backend/models.py`, `backend/palette.py`, `backend/prompts.py`,
> `backend/examples.py`, (신규) `backend/domain.py`
> 목표: 현재 9개 프리셋(FC-BGA/TGV/SMT/TFT/µLED/miniLED/CoWoS-S/EMIB/PCB)이
> 커버하지 못하는 **최신 어드밴스드 패키징·디스플레이 단면 구조**와 **작도 규약**을
> DSL·팔레트·프롬프트·예제로 흡수한다. 스키마 철학(LLM=의미 / 코드=geometry)은 유지.

---

## 0. 설계 원칙 재확인 (변경 금지)

- LLM은 **의미만** 출력한다. 좌표·색·mm/µm 치수 금지.
- `layout.py`가 유일한 geometry 소스다. 신규 구조를 넣을 때도 **렌더러에 좌표를
  직접 넣지 말고** 새 row 타입 + layout 함수로만 확장한다.
- 새 row 타입은 반드시 `type` Literal 태그를 갖는다(= discriminated union).
  현재 `StackRow = Union[LayerRow, DieRow, DiesRow, BallsRow, ChipsRow]` 패턴 유지.
  이것이 guided_json/스키마 디코딩 신뢰도의 핵심이다(WP2 참조).
- 프론트엔드(`frontend/*.html`)는 **손대지 않는다**. 신규 재료/구조는 전부
  백엔드 렌더 산출물(SVG/ pptx)로만 표현된다.

---

## 1. 커버리지 갭 — 추가할 구조 (bottom→top 레시피)

아래 레시피는 그대로 `examples.py` 프리셋 + 프롬프트 few-shot으로 쓸 수 있다.
모두 **bottom-to-top** 물리 순서. 두께 `t`는 얇은 막을 보이게 과장한 상대값.

### 1.1 Fan-Out (FOWLP / InFO, RDL-first / die-first)
팬아웃은 **기판(substrate)이 없고** die가 mold에 재구성(reconstitution)된 뒤
**RDL이 직접 배선**한다. die-first(InFO, face-up)와 RDL-first(chip-last)가 있다.
- InFO(die-first) 레시피: `balls(solder, flat)` → `layer(RDL, copper/dielectric, 얇게 2~3층)`
  → `die(silicon, width_frac≈0.5, underfill 없음 — mold가 감쌈)` → `layer(EMC mold, mold, width_frac 1.0)`.
  die 옆을 mold가 채우는 게 팬아웃의 정체성 → die width_frac를 0.4~0.6으로.
- RDL-first(chip-last) 특징: RDL을 임시 글라스 캐리어 위에 먼저 만들고 die를 나중에 붙임.
  단면 표현은 InFO와 유사하되 caption에 "RDL-first / chip-last"를 명시.
- **핵심 라벨**: "RDL (n층)", "EMC / mold", "solder ball", "no Si substrate".

### 1.2 하이브리드 본딩 (SoIC / Foveros Direct) — **범프리스**
Cu–Cu 직접 접합. 마이크로범프가 **없고** 얇은 유전체(SiCN/SiO) 계면에 Cu 패드가
sub-10µm 피치로 맞물린다. 이건 balls로 표현하면 틀린다 → **신규 `bond` row 필요**(§2.1).
- 레시피: `die(bottom, silicon)` → `bond(hybrid, Cu-Cu, 얇은 계면)` → `die(top, silicon)`.
- caption: "Bumpless Cu-Cu hybrid bond, <10 µm pitch". µbump 스택과 대비해서 보여주면 강력.

### 1.3 HBM 스택 (base logic die + DRAM 8~12단)
DRAM die 다단 + 하단 base logic die, **TSV로 수직 관통 + µbump**(HBM4E/5부터 hybrid bond).
반복 die 스택이므로 매번 layer/bump를 나열하면 소형 모델이 실수 → **신규 `diestack` row 필요**(§2.2).
- 레시피: `layer(base logic die, silicon, TSV vias)` → `diestack(DRAM, count 8, joint "ubump"|"hybrid")`.
- caption: "8-Hi HBM: base logic + DRAM via TSV/µbump". HBM4는 2048-bit / 32ch(수치는 [data needed]).

### 1.4 CoWoS-L (LSI 브리지 + RDL 재구성 인터포저)
CoWoS-S의 **모놀리식 Si 인터포저** 대신, **LSI 실리콘 브리지 칩렛들을 RDL 인터포저에
임베드**한 "reconstituted interposer". 3000mm² 초과 대면적 가능.
- 기존 `LayerRow.embeds`(EMIB에서 쓰던 것)를 재사용한다. 인터포저 layer(dielectric/RDL)에
  `embeds:[{label:"LSI bridge", material:"silicon", position:"top"}]`.
- 레시피: `substrate(ABF, vias)` → `balls(C4, barrel)` → `layer(RDL interposer, dielectric,
  embeds:[LSI bridge ×1~2, top])` → `balls(µbump, pillar)` → `dies([SoC, HBM, HBM])` → `mold`.
- CoWoS-S와 **compare 2패널**로 나란히 두면 교육적. (S=Si interposer+TSV / L=RDL+LSI bridge)

### 1.5 백사이드 파워 (BSPDN / PowerVia / Super Power Rail) — 트랜지스터 레벨
프론트사이드 신호 BEOL + 디바이스층 + **백사이드 파워 배선 + nano-TSV**. 위아래가 뒤집힌 구성.
- 레시피(bottom→top): `layer(Backside power metal, copper)` →
  `layer(Backside PDN + nano-TSV, dielectric, vias straight material copper label "nano-TSV")` →
  `layer(Transistor / nanosheet device, semiconductor, width_frac 0.9)` →
  `layer(Frontside signal BEOL, metal/dielectric 교차 2~3층)`.
- caption: "Backside power delivery: power on back, signal on front". 신규 재료 `device` 권장(§3).

### 1.6 글라스 코어 기판 (상세 build-up + TGV) / CoPoS 패널
기존 TGV 프리셋은 단순하다. **build-up L1/L2 / 글라스 코어(TGV) / build-up L3/L4** 대칭 구조로 상세화.
- 레시피: `layer(Build-up L4 RDL, copper, t0.35)` → `layer(Build-up L3, dielectric, t0.4)` →
  `layer(Glass core, glass, t2.2, vias hourglass copper "TGV ~40µm")` →
  `layer(Build-up L2, dielectric, t0.4)` → `layer(Build-up L1 RDL, copper, t0.35)`.
- CoPoS = 원형 캐리어 대신 **310×310mm 사각 패널** — 이건 단면이 아니라 top-view 맥락이므로
  caption/텍스트로만 언급(도형은 동일 단면 유지).

### 1.7 와이어본드 / QFN·리드프레임 (레거시지만 필수 커버)
현재 전부 flip-chip이다. 와이어본드는 **die 상면 패드 → 리드프레임/기판으로 올라가는 호(arc)**.
새 커넥터 개념 → **신규 `wirebond` 표현**(§2.3, 우선순위 낮음/선택). 최소안: `die`에
`wirebond:true` 플래그 → die 상단 양끝에서 아래 layer 가장자리로 arc 2~4개.
- QFN 레시피: `layer(Leadframe / die pad, metal)` → `die(silicon, wirebond:true)` → `layer(EMC mold)`.

### 1.8 PoP (Package-on-Package)
하단 로직 패키지 위에 상단 메모리 패키지. 두 stack을 세로로 이어 붙이고 사이를
`balls(PoP solder, ball)`로 연결. 기존 row 조합으로 표현 가능 → 프롬프트 레시피만 추가.

### 1.9 OLED 디스플레이 스택 (µLED와 구분되는 유기 발광)
- 레시피: `layer(TFT backplane, 요약 1층 또는 tft 프리셋 참조)` →
  `layer(Anode ITO, ito, width_frac 0.6)` → `layer(HIL/HTL, polymer, 얇게)` →
  `layer(Emission layer EML, mqw 또는 신규 emission, width_frac 0.55)` →
  `layer(ETL/EIL, polymer)` → `layer(Cathode Mg:Ag, metal, 반투명)` →
  `layer(TFE: inorganic/organic/inorganic, passivation 3층 또는 요약)`.
- caption: "Top-emission OLED + thin-film encapsulation (TFE)".

---

## 2. DSL(모델) 확장 — `models.py`

새 row는 전부 `type` Literal 태그를 유지. 각 row는 `_row_t()`(layout.py:128)와
`_layout_stack()` 디스패치에 대응 추가가 필요(= WP1 구현 시 layout.py도 함께).

### 2.1 `BondRow` — 범프리스 하이브리드 본드 계면 (신규, 우선순위 高)
```python
class BondRow(BaseModel):
    """Bumpless Cu-Cu / fusion bond interface between two dies (SoIC, Foveros
    Direct). Rendered as a thin dielectric band with a bond line + fine Cu pad
    columns — NOT solder balls."""
    type: Literal["bond"] = "bond"
    label: str = "Hybrid bond (Cu-Cu)"
    style: Literal["hybrid", "fusion"] = "hybrid"
    material: str = "dielectric"      # SiCN/SiO interface
    pad_material: str = "copper"
    count: int = Field(default=10, ge=2, le=32, description="Cu pad columns")
    width_frac: float = Field(default=0.9, ge=0.1, le=1.0)
```
layout: 얇은 band(t≈0.25) + 중앙 수평 bond line + `count`개 Cu 패드(위/아래 절반씩) 미니 사각.
via 정렬 로직(`_aligned_via_xs`)과 동일하게 위/아래 die 폭에 스냅되면 이상적.

### 2.2 `DieStackRow` — 반복 die 수직 스택 (HBM/3D, 신규, 우선순위 高)
```python
class DieStackRow(BaseModel):
    """N identical dies stacked vertically (HBM DRAM cube, 3D logic stack).
    The engine repeats the die band `count` times with the chosen joint between
    layers — one compact row instead of 2N hand-written rows (small-model safe)."""
    type: Literal["diestack"] = "diestack"
    label: str                         # e.g. "DRAM die"
    count: int = Field(default=8, ge=2, le=16)
    material: str = "silicon"
    joint: Literal["ubump", "hybrid", "none"] = "ubump"
    width_frac: float = Field(default=0.7, ge=0.15, le=0.95)
    tsv: bool = Field(default=True, description="draw TSV columns through the stack")
    t_each: float = Field(default=0.5, ge=0.2, le=1.5)
```
layout: `count`개 die band을 위로 반복, 각 사이에 joint(µbump 작은 원 or hybrid bond line),
`tsv=True`면 스택 전체를 관통하는 straight via 컬럼. 콜아웃은 "×N"으로 1개만.

### 2.3 `wirebond` (선택, 우선순위 低)
`DieRow`에 `wirebond: bool = False` 필드만 추가하는 최소안 권장. layout에서 die 상단
양 끝 → 바로 아래 row 가장자리로 2~4개 2차 베지어/폴리 arc를 그린다(gold 재료).
독립 row 타입은 과설계이므로 지양.

### 2.4 `LayerRow` 보강 (스키마 변경 없음, 프롬프트/예제로만)
CoWoS-L·EMIB의 임베드 브리지는 기존 `embeds`로 충분. 백사이드 파워/RDF/글라스 build-up도
기존 `layer`+`vias`로 표현 가능. → **§1의 대부분은 신규 스키마 없이 프롬프트·예제만으로 커버**되고,
스키마 신규는 `BondRow`·`DieStackRow` 2개(+선택적 `wirebond` 플래그)로 한정한다. (소형 모델
관점에서 스키마 표면적을 최소로 유지 — WP2.)

---

## 3. 팔레트 확장 — `palette.py`

산업 관용색 유지. 아래 role 추가(기존 role 재사용 가능하면 신규 지양). hex는 흰 슬라이드 기준.
```python
# add to MATERIALS
"emission":   ("#8be0c0", "#4fae8c"),   # OLED EML (유기 발광층, 청록 계열)
"organic":    ("#e9dcc8", "#c7b48f"),   # HIL/HTL/ETL 유기 박막
"device":     ("#9aa7c4", "#6b7aa0"),   # 트랜지스터/나노시트 디바이스층
"rdl":        ("#e8983a", "#b87333"),   # RDL = copper와 동일 톤(별칭)  ← copper 재사용도 OK
"emc":        ("#4a4741", "#2f2d29"),   # 팬아웃 EMC 몰드(회흑, mold와 미세 구분)
"bond_oxide": ("#d5dbe0", "#9aa6b0"),   # 하이브리드 본드 유전체 계면
"leadframe":  ("#c9ccd1", "#9aa0a8"),   # 리드프레임(밝은 은색 금속)
```
`DARK_ROLES`에 `emc` 추가 검토(라벨 대비). 신규 role은 **반드시 alias 맵**(WP3 repair)에
등록해 미지의 role이 들어와도 최근접으로 폴백되게 한다.

---

## 4. 작도 규약 — 프롬프트 `DOMAIN CONVENTIONS`에 추가

리서치 기반 규약(엔지니어링 단면도 관례). `prompts.py`의 `LAYOUT_SYSTEM` DOMAIN
CONVENTIONS 블록에 아래를 **간결히** 추가한다(모델 부담 최소화 위해 핵심만):

- **Fan-out(InFO/FOWLP)**: no substrate. balls(flat) → RDL layers(copper/dielectric ×2-3)
  → die(width_frac 0.4-0.6, mold fills sides) → EMC mold(width_frac 1.0). RDL-first면 caption에 "chip-last".
- **Hybrid bond(SoIC/Foveros Direct)**: use a `bond` row (NOT balls) between two dies.
  "Bumpless Cu-Cu, <10 µm pitch".
- **HBM**: base logic die(TSV) → `diestack`(DRAM, count 8-12, joint ubump; HBM4E+ hybrid).
- **CoWoS-L**: RDL interposer `layer` with `embeds:[LSI bridge, top]` instead of a monolithic
  Si interposer. Contrast with CoWoS-S via a `compare`.
- **Backside power(PowerVia/SPR)**: backside metal → PDN+nano-TSV(vias) → device layer → frontside BEOL.
- **Glass core(상세)**: build-up L4/L3 → glass core(hourglass TGV) → build-up L2/L1, symmetric.
- **Wirebond/QFN**: leadframe → die(wirebond:true) → EMC mold (flip-chip 아님).
- **일반 작도**: 얇은 막은 t로 과장, "not to scale"를 caption에. 리더선(callout)은 서로
  교차 금지·너무 길지 않게(엔지니어링 관례) — 이미 `layout._layout_stack` 콜아웃 분배가 처리.
  인접 이질 재료는 서로 다른 색으로 구분(팔레트가 담당).

전체 규약이 길어지면 소형 모델 성능이 떨어지므로, **구조별 레시피는 `domain.py`
(아래)로 분리**하고 프롬프트에는 위 요약만 넣는다.

---

## 5. `backend/domain.py` (신규) — 지식/레시피 단일 소스

프롬프트·예제·템플릿(WP3)·린터(WP3)가 **같은 지식**을 참조하도록 구조 레시피를
파이썬 데이터로 1곳에 둔다. 문자열 중복/드리프트 방지.
```python
# backend/domain.py
STRUCTURES = {
  "fanout_info": {
    "aka": ["InFO", "FOWLP", "integrated fan-out"],
    "caption": "Integrated fan-out (InFO): die-first, RDL, no Si substrate",
    "recipe": [ ... bottom-to-top row dicts ... ],
    "must_label": ["RDL", "EMC / mold", "solder ball"],
    "rules": ["no substrate row", "die width_frac 0.4-0.6", "mold width_frac 1.0"],
  },
  "hybrid_bond_soic": { ... "recipe" uses a `bond` row ... },
  "hbm": { ... uses `diestack` ... },
  "cowos_l": { ... embeds LSI bridge ... },
  "backside_power": { ... },
  "glass_core_detailed": { ... },
  "qfn_wirebond": { ... },
  "pop": { ... },
  "oled": { ... },
  # + 기존 9개도 여기로 이관해 단일 소스화(examples.py는 domain에서 생성)
}
```
- `examples.py`는 `STRUCTURES[...]["recipe"]`로부터 프리셋 Deck을 생성(현재 하드코딩 대체).
- `prompts._example()`도 여기서 1개를 뽑아 few-shot으로.
- WP3 `templates.py`는 `STRUCTURES`를 파라메트릭 빌더로 노출.
- WP3 `lint.py`는 `must_label`/`rules`로 검증.

---

## 6. 수용 기준 (WP1)

1. `smoke_test.py`가 신규 프리셋 포함 전부 통과(SVG는 `<svg`로 시작, pptx는 `PK`+>5KB,
   Deck round-trip). 신규 프리셋을 `EXAMPLES`/`EXAMPLE_META`에 추가.
2. `BondRow`/`DieStackRow`가 SVG·pptx 양쪽에서 동일 geometry로 렌더(레이아웃 단일 소스 원칙).
3. HBM `diestack(count=8)`이 손으로 16행을 쓰지 않고 1행으로 8단 + TSV + µbump를 그린다.
4. 하이브리드 본드 예제가 balls가 아닌 얇은 bond 계면으로 렌더된다.
5. `palette` 신규 role이 전부 alias 맵에 등록되어 미지 role도 폴백된다(WP3 연계).
6. 프론트엔드 파일 diff = 0 (UI 불변).
7. 신규 구조는 `domain.py` 단일 소스에서 파생(examples/prompt/template/lint 중복 없음).

---

## 참고 출처 (리서치)

- Fan-out/RDL-first: [SemiEngineering — Fan-Out Packaging Gets Competitive](https://semiengineering.com/fan-out-packaging-gets-competitive/), [3D InCites — Role of RDL](https://www.3dincites.com/2025/07/the-role-of-redistribution-layers-rdl-in-advanced-packages/)
- 하이브리드 본딩: [SemiAnalysis — Hybrid Bonding Process Flow](https://semianalysis.com/2024/02/09/hybrid-bonding-process-flow-advanced/), [IEEE Spectrum — Hybrid Bonding](https://spectrum.ieee.org/hybrid-bonding)
- 백사이드 파워: [Wikipedia — Backside power delivery](https://en.wikipedia.org/wiki/Backside_power_delivery), [Tom's Hardware — Intel PowerVia](https://www.tomshardware.com/news/intel-details-powervia-backside-power-delivery-network)
- HBM: [Wevolver — HBM deep dive](https://www.wevolver.com/article/what-is-hbm-high-bandwidth-memory-deep-dive-into-architecture-packaging-and-applications), [Siemens — HBM3e/HBM4 design guide](https://blogs.sw.siemens.com/semiconductor-packaging/2026/04/24/hbm3e-hbm4-ic-design-guide/)
- CoWoS-L: [aminext — CoWoS-S/R/L](https://www.aminext.blog/en/post/tsmc-cowos-s-r-l-differences), [AnySilicon — CoWoS](https://anysilicon.com/cowos-package/)
- 글라스 코어/CoPoS: [3D InCites — Glass Core vs RDL Interposer](https://www.3dincites.com/2025/07/glass-core-vs-rdl-interposer-substrates-ready-for-prime-time/), [SemiEngineering — Glass Substrates Gain Momentum](https://semiengineering.com/glass-substrates-gain-momentum/)
- OLED 스택/TFE: [ScienceDirect — Organic materials in OLED](https://www.sciencedirect.com/science/article/pii/S2666950125000847)
- 작도 규약(단면/리더선/해칭): [McGill — Sectioning Technique](https://www.mcgill.ca/engineeringdesign/step-step-design-process/basics-graphics-communication/sectioning-technique), [WhatIsPiping — Types of Lines](https://whatispiping.com/types-of-lines-in-drawing/)
