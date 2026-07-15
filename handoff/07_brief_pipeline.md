# WP8 — 점진적 구체화 파이프라인 (Brief IR + 컴파일)

> 대상: 단면도 스튜디오(`/`, dsessions) figure 1장 흐름. 문제: 지금은 `프롬프트 → kind
> 즉시 확정 → 구체 DSL`이라 **조기 확정**된 표현(예: photonic 그래프)에 갇혀, 사용자의
> 구조적 수정(솔더 실장·패드·매립 waveguide)이 **텍스트로만** 반영된다(세션4 리뷰).
>
> 해결: kind보다 상위의 **편집 가능한 중간표현 `Brief`를 노드마다 지속**시키고, 수정은
> Brief에 반영 → **매번 figure DSL로 재컴파일**. Brief는 어떤 단일 figure kind보다 풍부하므로
> "현재 뷰가 못 그리는 것"을 요청하면 컴파일러가 뷰를 확장/전환한다 — 갇히지 않는다.
>
> 확정된 설계 결정(사용자): ① Brief IR = 진실(single source), figure DSL은 그 투영.
> ② 하이브리드 UX(즉시 2안 + 편집 가능한 Brief 패널). ③ genre가 모호하면 그리기 전에
> 먼저 질문(genre 층위에서만 blocking).

## 0. 원칙 — 모호함에서 구체화로 (단계)

생성은 가장 추상적인 판단부터 좁혀간다. 각 단계는 **작고 지식-백업된 결정**만 LLM에 시키고,
결정론 코드(컴파일러 + 부품 지식)가 기하를 만든다(핸드오프 전역 철학과 일치).

```
0. genre        추상 인포그래픽 vs 물리 구조(부품 실장)?   ← 모호하면 먼저 질문
1. elements     어떤 부품/요소가 들어가나
2. state        실장 상태: 단순 스택 | 솔더 | 플립칩 | 와이어본드 | 하이브리드 | 매립, 패드(pitch/size/count)
3. attributes   기능→그래픽: waveguide=가늘고 긴 광경로(PIC면 기판 내부), laser=발광 …
4. arrangement  위치/배열 (마지막에 파생) + 렌더 강조(단면 emphasis vs 평면 emphasis)
```

핵심 명제: **처음부터 특정 구체화 단계로 착지하면 그 제약에 갇힌다.** Brief는 이 단계들을
필드로 담아 상위 층위에 머무르고, 구체 DSL은 매번 파생된다.

### 0.1 photonic/stack을 나누지 않는다 — "기판 위 부품 배치"로 통합 (사용자 지적)

photonic-그래프와 stack은 **같은 것의 두 렌더링**이다 — 둘 다 *기판 위에 부품이 배치되고 서로
연결되는 구조*. 그래서 genre를 photonic vs stack으로 나누지 않는다. 상위 분기는 **딱 둘**:

- **physical**(물리 구조) — 기판 + 부품 + 실장/연결. 단일 통합 스킴(§1).
- **infographic**(추상 데이터 도해) — timeline/table/… (WP7). 이건 물리 구조가 아니므로 별개.

physical 안에서 "단면 측면도"냐 "평면 네트워크"냐는 **렌더 강조(emphasis)** 일 뿐, 별도 genre가
아니다. 같은 scene을 `emphasis=section`이면 수직 빌드업+실장 디테일 중심으로, `emphasis=planar`면
측면 광/전기 토폴로지 중심으로 그린다. 필요하면 둘을 겹친다(단면 위 측면 광경로 화살표, §3).
→ 세션4가 photonic이냐 stack이냐를 고를 필요가 애초에 없어진다.

## 1. Brief IR 스키마 (`backend/brief_model.py`, 신규)

figure DSL과 **별개**. 실장/인터페이스/매립 같은 물성을 "어떻게 그릴지"와 독립적으로 담는다.
물리 구조는 photonic/stack 구분 없이 **하나의 통합 scene**(기판 + 부품 + 연결).

```python
class Interface(BaseModel):           # 이 부품이 아래(기판/하부 부품)와 접합되는 방식
    kind: Literal["none","stack","solder","c4","cu_pillar","flipchip",
                  "wirebond","hybrid_bond","edge_couple","monolithic",
                  "epoxy","eutectic"] = "stack"
    pad_count: Optional[int] = None   # 접합 패드/범프 개수
    pad_pitch: Optional[str] = None   # 표기 문자열 "100 µm" (수치 창작 금지)
    pad_size: Optional[str] = None
    underfill: bool = False

class Part(BaseModel):
    id: str
    name: str                         # 표시 라벨
    function: str                     # parts.py 키: laser_gain, waveguide, photodiode,
                                      #   pic, logic_die, hbm, submount, mlcc, mems, lens ...
    on: Optional[str] = None          # 무엇 위에 실장되나 — 기판이든 **다른 부품(chip-on-chip)**이든
    interface: Optional[Interface] = None    # 하부와의 접합(패드/범프/와이어/에지결합/매립)
    internal: Optional["Brief"] = None       # 부품 자체가 미니 구조(예: HBM=DRAM 스택)면 재귀
    attributes: dict = {}             # 기능별: {"buried":true}(기판 내부 waveguide),
                                      #   {"emits":true}(laser), {"cavity":true}(MEMS) ...

class Relation(BaseModel):
    type: Literal["optical","electrical","mechanical"]
    src: str; dst: str
    via: Optional[str] = None         # 예: waveguide part id
    label: Optional[str] = None

class Brief(BaseModel):
    genre: Literal["physical","infographic"]   # 상위 분기는 딱 둘 (§0.1)
    genre_confidence: float = 1.0
    emphasis: Literal["section","planar","auto"] = "auto"  # physical 렌더 강조(genre 아님)
    infographic_kind: Optional[str] = None     # genre=infographic일 때 timeline/table/...
    title: str
    caption: Optional[str] = None
    base: Optional[str] = None        # substrate/interposer 부품 id (최하단 기준)
    parts: list[Part] = []            # 기판 포함 모든 부품
    relations: list[Relation] = []
    open_questions: list[str] = []    # 아직 모호한 것 → intake(§4)
    requirements: list[str] = []      # 요청이 반드시 담아야 할 것 → 검증(§4b)
```

Brief는 dsession 노드에 `slide`와 **함께** 저장된다(§6). 수정은 Brief를 바꾼다.
`Part.on`이 다른 부품을 가리킬 수 있어 **chip-on-chip**(laser를 PIC 위에)·submount·**재귀 구조**가
자연히 표현된다 — 세션4에서 부족했던 "laser gain chip을 PIC 위에 솔더로" 가 여기서 나온다.

## 2. 컴파일러 — Brief → figure DSL (`backend/compile_brief.py`, 신규)

`compile_brief(brief) -> Slide`. 기존 렌더 엔진을 **재사용**하고, Brief가 그 중 무엇을
쓸지 고른다. 통합 scene(기판+부품+연결)이 하나이므로 photonic/stack 분기가 사라지고, **emphasis가
같은 scene을 어떻게 그릴지**를 정한다.

- **genre == "physical"** → 통합 scene을 렌더:
  - **emphasis section** (수직 빌드업 + 실장 디테일 중심) → StackFigure 계열로 컴파일:
    - `base`부터 `on` 체인으로 바닥→위 정렬. 각 부품 → die/layer 행(부품이 `internal` 구조면 재귀 전개).
    - `interface`로 **하부에 접합 행 삽입**: solder/c4 → `balls`(bump, count=pad_count);
      cu_pillar → `balls`("pillar"); flipchip → `balls`("barrel")+underfill; wirebond → die.wirebond=true;
      hybrid_bond → `bond` 행; monolithic/stack → 접합 행 없음. **chip-on-chip**은 접합 행을
      기판이 아니라 하부 부품 위에 삽입.
    - waveguide 부품: `attributes.buried` → 기판 layer의 `embeds`(가늘고 긴 채널); 아니면 표면 얇은 layer.
    - optical relation → **측면 광경로 화살표 오버레이**(§3).
  - **emphasis planar** (측면 토폴로지 중심) → 기존 `_layout_photonic_graph`로 렌더(같은 부품/연결을
    노드/링크로). 
  - **emphasis auto** → §4b 판정: 실장/수직 디테일이 중요하면 section, 광/신호 흐름이 중요하면 planar.
- **genre == "infographic"** → archetype kind(WP7; `infographic_kind`).

즉 컴파일러는 (section-stack / planar-graph / archetype) 렌더러의 **디스패처 + 부품 배치기**이고,
**앞의 둘은 이제 같은 physical scene의 두 렌더**다. 세션4는 genre=physical·emphasis=section으로
컴파일 → 솔더 접합 행 + 매립 waveguide로 **기하가 바뀐다**.

## 3. DSL/스키마 변경 — 커버리지 갭 기반 (근거: 07b_coverage_research.md)

리서치 감사 결과, 최소 변경으로는 부족하고 **구조적 갭 2개**가 근본이다. 우선순위(07b §갭):

1. **부품별 본드패드+실장 모델(최우선)** — 다이/부품에 `mount ∈ {wirebond, flipchip, cu_pillar,
   c4, hybrid, die_attach, edge_couple, grating_couple}` + 패드 위치(top-peripheral/bottom-array/edge).
   엔진이 손-작성 balls 행 없이 올바른 인터커넥트를 **자동 생성**. `DieSpec`에 `wirebond` 추가.
   → "laser diode가 패드를 갖고 wirebond인지 flip-chip인지"를 시스템이 알게 됨.
2. **chip-on-chip / 위치지정 실장(구조적 핵심)** — 작은 부품을 더 넓은 다이 **위 특정 x-위치**에
   얹고 그 다이는 옆으로 계속 뻗음(laser-on-PIC). 현행 stack의 "모든 행 풀-폭·중앙·바닥→위" 가정을
   완화. **통합 scene(§0.1)이 부품을 (x-위치, level)에 배치**하므로 여기서 자연히 풀림 — 평면 photonic
   레이아웃이 이미 x-배치를 하고, 수직 스택은 "같은 x에 쌓임"의 특수경우. `Part.on`이 다른 부품이면
   그 부품 위에 국소 접합.
3. **수직 단면 위 in-plane 광빔** — `_h_arrow_poly`를 section 렌더에 도입. 다이가 facet/발광점을
   선언 → 올바른 높이로 edge coupler까지 수평 빔. `StackFigure.optical_paths` 또는 통합 scene의 relation.
4. **캐비티/보이드(MEMS)** — 밀봉 빈 영역 + 씰 링(PolyShape 재사용, DSL 행).
5. **진짜 매립 waveguide 채널**(코어+클래딩) — 현행 surface/inline strip과 구분(embed 확장).
6. **센서 광학 행** — 마이크로렌즈 어레이/컬러필터(Bayer)/글라스 리드(CIS·VCSEL).
7. **V-groove + 파이버-in-groove**. 8. **다이 방향(face-up/down)** + 1급 flip-chip 범프배열 속성.

렌더러(`render_svg`/`export_pptx`) diff ≈ 0(신규 기하는 기존 Poly/화살표/dome 프리미티브 조합).
palette: 광경로 role `optical` 재사용. P1은 갭 1·2를, P2는 3·4·5를, 이후 6·7·8.

## 4. 이해(understand) 단계 + genre 질문 (`backend/understand.py`, 신규)

`understand(prompt, prior_brief=None) -> Brief` — Brief를 채우는 **단계-스코프** LLM 호출.
프롬프트는 부품 지식(parts.py, §5)을 주입해 좁은 선택만 시킨다: (a) view 판정 + 확신도,
(b) 부품 목록 + function, (c) 명백한 곳의 mount/interface, (d) 모호한 것은 `open_questions`에.

- **genre 게이트(blocking, 사용자 결정 ③)**: `view_confidence`가 낮거나 신호가 상충하면
  `open_questions=["genre: 개념 인포그래픽 vs 부품 실장 단면도 vs 광 네트워크?"]`를 채우고
  **컴파일 보류** → app이 먼저 질문(§6). 명확하면 바로 컴파일.
- **수정**: `understand(instruction, prior_brief)` → 갱신된 Brief → 재컴파일. "솔더 패드 추가"는
  해당 part.interface.kind=solder/pad_count 설정 → 컴파일러가 bump 행 삽입 → **기하 변경**.
- 소형모델 안전장치: understand는 자유 DSL이 아니라 **제한된 Brief 필드**만 채운다. router(WP7)를
  view 1차 추정에 재사용하고, parts.py가 function/interface 후보를 좁힌다.

## 4b. 검증 → 적응/대체 루프 (사용자 지적 3)

컴파일 후 **요청을 충족하는지 판정**하고, 지금 요소/도구로 부족하면 **형태가 비슷한 다른 요소로
대체**해서 적용한다(갇히지 않기의 프리미티브 레벨판). 3단계:

1. **requirements 추출** — understand가 Brief.requirements에 "요청이 반드시 담아야 할 것"을 남긴다
   (예: "laser가 솔더 패드로 PIC에 접합", "waveguide는 기판 내부", "빛은 laser→PD로 측면 전파").
2. **critic(결정론 우선 + 필요시 LLM)** — 컴파일된 figure가 각 requirement를 실제로 표현하는지 대조.
   미충족 목록(unmet)을 만든다. 결정론 체크로 잡히는 것(접합 행 존재? 광경로 화살표 존재? buried
   embed 존재?)은 코드로, 애매한 것만 소형 LLM 1회.
3. **adapter — 형태 유사 대체** — unmet 원소를 표현할 전용 도구가 없으면, **가장 형태가 비슷한
   기존 프리미티브로 치환 + 재라벨**하고 근사를 caption에 명시. 유사도 레지스트리(`substitute.py`):
   - 인포그래픽: 형태 유사하면 텍스트만 바꿔 재사용(예: 요청은 "퍼널"인데 미지원 → 역삼각 계층은
     tree/matrix로 근사, 라벨 교체).
   - 물리: 전용 글리프 없음 → 가까운 것으로. 예) microlens 없음 → dome poly; MEMS comb 없음 →
     패턴 chips 행 재라벨; V-groove 없음 → 사다리꼴(taper) 재라벨. "≈ 근사 표현" 주석.
   - 그래도 핵심 requirement가 대체 불가면 → open_questions/《미지원》으로 정직하게 표기(라벨로
     숨기지 않음).

이 루프가 있어야 "요소·도구 부족"이 **조용한 누락**이 아니라 **의식적 대체 또는 명시적 한계**가 된다.

## 5. 부품 지식베이스 (`backend/parts.py`, 신규 — domain/archetypes와 대칭) — **리서치 필요**

지금 지식은 통짜 구조(domain.py)·인포그래픽 kind(archetypes.py)뿐, **원자 단위(부품)**가 없다.
부품 단위 function→glyph→interface→실장 사실을 단일 소스로. **이 내용은 실제 소자 조립 사실에
대한 조사가 선행되어야 한다**(사용자 지적 2: "laser diode도 접합 패드가 있는지, wire bonding인지
flip-chip인지 알고 있는가"). 별도 리서치 결과(부품별 실장 사실 + 실제 단면도 카탈로그 + 현행 DSL
커버리지 갭)를 이 표의 근거로 삼는다.

```python
PARTS = {
  "waveguide": {"aka":["waveguide","도파로"], "shape":"thin_long",
                "interfaces":["monolithic","edge_couple"],
                "attributes":{"buried":"PIC/monolithic이면 기판 내부 채널"}},
  "laser_gain": {"aka":["laser","레이저","gain chip"], "emits":True, "glyph":"die",
                 # 실제 사실(리서치 근거): 본드 패드 있음(anode/cathode).
                 # 실장: epi-up이면 wirebond, epi-down이면 flip-chip/solder(에지결합 정렬↑),
                 # 보통 submount 위에 먼저.
                 "interfaces":["solder","flipchip","wirebond","edge_couple"],
                 "has_pads":True, "submount":True},
  "photodiode": {"detects":True, "glyph":"die", "has_pads":True,
                 "interfaces":["flipchip","wirebond","monolithic"]},
  "pic": {"aka":["pic","실리콘 포토닉","photonic ic"], "is_base":True,
          "can_embed":["waveguide"]},
  "logic_die": {"interfaces":["flipchip","wirebond","hybrid_bond"], "has_pads":True},
  "submount": {"is_base":True, "aka":["submount","서브마운트"]},
  "mlcc": {"passive":True}, "mems": {"attributes":{"cavity":True}},
  "lens": {"glyph":"dome"}, "fiber": {"glyph":"cylinder", "interfaces":["v_groove"]},
  ...
}
```

understand 프롬프트(무엇을 물을지)와 컴파일러(어떻게 그릴지)와 critic(무엇을 검증할지)이 공유.
장기적으로 domain.py 구조는 부품 조합으로 재표현 가능(통일) — 후순위.

## 6. 지속 + 하이브리드 UI (사용자 결정 ②)

- `dsessions` 노드에 `brief`를 `slide`와 함께 저장. `add_node`가 brief를 받도록 확장.
- `_dsession_payload`에 노드별 `brief` 포함(없으면 빈 값 — 하위호환).
- 생성/수정 잡: `understand → (genre 질문이면 보류) → compile_brief → slide`. 즉시 2안 유지.
- `frontend/index.html`(WP7 승인 예외 범위 내): 확대 카드 옆에 **편집 가능한 Brief 요약 패널**
  (view·부품 리스트·mount). "이 Brief로 다시 그리기" 버튼(→ brief-edit 재컴파일 엔드포인트) +
  기존 자연어 수정 둘 다. genre 질문은 §WP7 배너 재사용.
- 신규 엔드포인트 `POST /api/d/session/{n}/recompile`(node_id + edited_brief) → compile만(모델 불필요, 빠름).

## 7. 착수 순서

```
P0  리서치/감사(코드 아님): 부품별 실장 사실 + 실제 단면도 카탈로그 + 현행 DSL 커버리지 갭
      └ P1~P2의 스키마/프리미티브 우선순위를 이 갭 리스트가 결정. (진행 중)
P1  brief_model + compile_brief(physical/section=stack 재사용) + understand(genre/parts)
      + 노드 brief 저장. └ 세션4류가 physical/section으로 컴파일, chip-on-chip 솔더 접합 행이
      기하로 나타남. mock 검증.
P2  StackFigure.optical_paths 오버레이 + 매립 waveguide(embeds) + interface→접합행 매핑 정교화
      + P0 갭 중 우선순위 프리미티브(예: 부품 자체 패드, chip-on-chip 접합) 보강.
P3  parts.py 지식(P0 근거) + understand 단계 프롬프트 + genre blocking 질문(open_questions)
P4  검증→적응 루프(critic + substitute.py) — requirements 대조, 형태 유사 대체, 명시적 한계
P5  하이브리드 UI(brief 패널) + /recompile + brief 수정 흐름
P6  planar emphasis(그래프 렌더) 통합 + infographic도 같은 Brief 경유 + 라우팅/골든/린트 확장
```

각 단계 mock로 전 경로 검증. P0(갭 파악)이 스키마 결정을 좌우하고, P1이 백본(조기확정 제거).

## 8. 수용 기준 (세션4 재현으로 검증)

1. "photonic IC 기판에 laser gain chip 실장, waveguide로 전파" → Brief.view=cross_section
   (photonic-graph 아님), parts=[substrate_pic, laser_gain(on substrate), waveguide(buried), photodiode].
2. 수정 "솔더로 실장, 패드 접합" → laser_gain.interface.kind=solder → 컴파일 결과에 **솔더 bump 행**이
   실제로 생김(라벨만이 아니라 기하 변경). 두 번째 수정도 기하에 반영.
3. genre 모호 프롬프트 → open_questions에 genre 질문, blocking 후 답에 따라 뷰 확정.
4. 기존 세션(brief 없는 노드) 렌더·수정 하위호환 유지. smoke ALL PASSED.
5. 렌더러 diff는 optical overlay 재사용분뿐. LLM 출력에 좌표/색/치수 없음(Brief도 물성만, 수치는 표기 문자열).

## 9. 참고 (재사용 근거)
- stack 프리미티브: `layout._layout_stack`(die/balls/bond/embeds), `_h_arrow_poly`(측면 화살표).
- 뷰 3종 엔진: stack / `_layout_photonic_graph` / archetype 레이아웃(WP7).
- 라우터/intake/부분렌더: WP7 `router`, `_dsession_payload.questions`, `JOBS.partial`.
- 지식 단일 소스 패턴: `domain.STRUCTURES`, `archetypes.ARCHETYPES` → `parts.PARTS`.
