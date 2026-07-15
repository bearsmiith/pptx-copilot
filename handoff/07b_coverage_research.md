# WP8 부속 — 부품 실장 사실 + 단면도 커버리지 감사 (리서치 결과)

> 07_brief_pipeline.md의 근거 자료. 실제 소자 조립 사실 + 현행 DSL 커버리지 갭.
> 리서치 에이전트 산출(2026-07-10). 스키마/프리미티브 우선순위의 근거.

## 접합(pad/contact) 핵심 논리 — 스키마가 알아야 할 사실

| 접합 방식 | 패드 위치 | 그려야 할 기하 |
|---|---|---|
| Wire bond | 다이 **윗면**(주변부), face-up | 패드→리드로 **위로 솟는 아치** |
| Flip-chip (C4/pillar/µbump) | 다이 **아랫면**(면 배열), face-down | 다이 아래 **범프 배열 + 언더필** |
| Hybrid bond | 다이 면, 초미세 | 얇은 Cu/oxide **경계선** |
| Edge coupling (광) | 다이 **가장자리 facet** | waveguide 높이의 **수평 빔** |
| Grating coupling (광) | 다이 **윗면** | 위쪽 파이버로 near-수직 빔 |
| MLCC/2-terminal | **양 끝** | 양 끝 솔더 필렛 |

## Laser diode (사용자 질문에 대한 직접 답)

- **본드 패드: 있음.** 윗면 p-contact 패드, 아랫면(기판측) n-contact.
- **실장 방식(방향이 결정적):**
  - **epi-up**: n-side down으로 submount에 붙이고, 윗면 p-패드를 **wire-bond**. 발광 stripe가 윗면 근처.
  - **epi-down(flip-chip)**: 뒤집어 active를 submount 쪽으로 → 방열↑, p-패드를 **솔더로 직접 접합**(에지결합 정렬 유리).
- **발광은 가장자리 facet(수직 절단면)에서 수평 빔**, active stripe 높이(마운트면 위 1–5µm). PIC/파이버
  결합 시 **빔 높이 = 대상 waveguide 높이** 정렬이 핵심(edge coupling의 본질).
- 함의 그래픽: submount(AlN/SiC), AuSn 다이어태치, 와이어 아치, 수평 facet 빔, 스팟사이즈 변환기/렌즈.
- **laser-on-PIC**: laser를 PIC 표면에 솔더-범프/플립칩, facet을 PIC edge coupler에 정렬, 매립 waveguide.

(그 외 부품별 사실 — photodiode(표면조사 vs 도파로결합 Ge-on-Si), PIC(flip-chip/2.5D/3D 하이브리드본드,
grating vs edge, 매립 Si 코어), flip-chip/wirebond die(면배열 vs 주변부, face 방향 반대), HBM(base die+TSV+
µbump/hybrid), MEMS(밀봉 캐비티+막+본드링+포트), CIS(마이크로렌즈+컬러필터+BSI+하이브리드본드 로직),
MLCC(양끝 필렛/매립), submount/interposer(중첩 실장, TSV, 2개 범프 피치), V-groove 파이버, 렌즈,
TSV, RDL, 접합종류(C4/Cu pillar/BGA/wirebond/hybrid/µbump/underfill/EMC) — 07b 상세는 전부 반영됨.)

## 실제 단면도 카탈로그 (지원 목표 ~22종, 요약)

wirebond QFN · FCBGA(언더필) · 2.5D CoWoS · fan-out InFO · PoP · HBM 스택 · 3D 하이브리드본드(SoIC) ·
글라스코어 TGV · 백사이드파워 · **에지발광 laser flip-chip on Si PIC(에지결합)** · SiPh TX/RX · CPO ·
V-groove 파이버어태치 · laser-on-submount(버터플라이) · **CIS(마이크로렌즈+Bayer+BSI+하이브리드본드)** ·
**MEMS 마이크/압력(캐비티+막+포트)** · MLCC(온보드/매립) · EMIB · micro-LED 전사 · OLED 스택 · VCSEL+마이크로렌즈.

## 커버리지 갭 (현행 DSL 대조) — 우선순위

현행이 잘 하는 것: 수직 레이어 스택, vias(straight/tapered/hourglass/TGV), EMIB embed, 볼 형상 5종,
Cu-Cu bond 행, HBM diestack, wirebond 아치, 언더필, side-by-side dies, fan-out RDL, OLED, **평면 photonic
네트워크**(laser/mod/mux/PD/TIA, grating&edge 글리프, fiber, optical/electrical 링크). 여기는 견고.

**우선순위 갭(추가할 것):**
1. **부품별 본드패드+실장 모델 (최우선)** — 다이/부품에 명시적 접합 스펙: `mount ∈ {wirebond, flipchip,
   hybrid, die_attach, edge_couple, grating_couple}` + 패드 위치(top-peripheral/bottom-array/edge). laser
   diode 질문에 직접 답하고, 엔진이 손-작성 행 없이 올바른 인터커넥트를 자동 그림. `DieSpec`에 `wirebond` 추가.
2. **chip-on-chip / 위치 지정 실장 (구조적 핵심)** — 작은 부품을 더 넓은 다이 **위 특정 x-위치**에 얹고,
   그 다이는 옆으로 계속 뻗음(laser-on-PIC, chip-on-submount, EMIB 중첩). 현행 stack의 "모든 행은
   풀-폭·중앙·바닥→위" 가정을 완화해야 함 — `on_top:[{part, x_frac, mount}]` 또는 오프셋 앵커 서브스택.
   **→ 세션4 대표 예제가 여기서 막혔음. 통합 scene(§07 0.1)의 "부품을 (x,level)에 배치"가 이걸 해결.**
3. **수직 단면 위 in-plane 광빔 오버레이** — `_h_arrow_poly`를 `_layout_stack`에 도입. 다이가 facet/발광점을
   선언하면 올바른 높이로 edge coupler/인접 부품까지 수평 빔. → 대표 도해(laser flip-chip on PIC) 해금.
4. **캐비티/보이드 (MEMS)** — 밀봉 빈 영역 + 씰/본드 링(+막/포트). PolyShape 재사용, DSL 행 필요.
5. **진짜 매립 waveguide 채널**(코어+클래딩 in substrate) + 광 의미 — 현행 surface/inline strip과 구분.
6. **센서 광학 행** — 시맨틱 마이크로렌즈 어레이 행 + 컬러필터(Bayer) 행 + 글라스 리드 (CIS, VCSEL 완성).
7. **V-groove + 파이버-in-groove** 단면 프리미티브.
8. **다이 방향 플래그(face-up/down)** + 다이의 1급 flip-chip 범프배열 속성(언더필+수동 balls 행 대신).

**통합 스키마 관점의 결론**: 갭 2가 근본이다. 현행 stack이 "풀-폭 수직 스택"에 갇힌 반면, **평면 photonic
레이아웃은 이미 "부품을 x-위치로 기판에 배치"** 한다 — 후자가 더 일반적 모델이고 수직 스택은 그 특수경우
(부품들이 같은 x에 쌓인 것). 통합 physical scene은 **부품을 (x-위치, level)에 배치 + 실장 인터페이스 +
내부 구조**로 두고, 단면 측면도와 평면도는 둘 다 (x, level) 배치의 렌더다. chip-on-chip = `on`이 다른 부품.
