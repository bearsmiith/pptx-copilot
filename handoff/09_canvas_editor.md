# WP10 — 자유 캔버스 편집기 (단면도·슬라이드 탭) + 파생 연결 + WP8 잔여

> 사용자 확정: **자유 캔버스** — 생성된 인포그래픽/슬라이드를 웹 UI에서 PowerPoint처럼
> 직접 편집(드래그 이동·리사이즈·텍스트 수정·요소 추가/삭제)하고, 저장하면 **편집 시작
> 노드의 파생 노드**로 트리에 연결된다. 대상: 단면도 스튜디오(`index.html`, dsessions)와
> 슬라이드 탭(`slides.html`, slsessions). deck 탭은 후순위 백로그.
>
> **아키텍처 원칙과의 화해 — 오버라이드 레이어**: "JSON=진실, 좌표=엔진"을 버리지 않는다.
> 엔진이 계산한 베이스 geometry 위에 **사용자 편집을 diff(오버라이드)로 저장**하고,
> SVG 프리뷰와 pptx 내보내기가 **같은 오버라이드를 적용**한다. LLM은 오버라이드를 보지
> 않는다(스키마 오염 없음). 자유 캔버스 UX를 얻으면서 프리뷰=pptx 일치가 유지된다.
>
> 신규: `backend/overrides.py`. 변경: `layout.py`(eid 부여+적용), `render_svg.py`(data-eid,
> 오버라이드 인자), `export_pptx.py`(동일), `slide_render.py`(슬라이드 탭 동일 경로),
> `app.py`(+3 엔드포인트), `dsessions.py`/`slsessions.py`(노드 필드), **`frontend/index.html`·
> `slides.html`(편집기 — UI 제약 갱신, §7)**. WP8 잔여인 `/recompile`+Brief 편집도 여기서 흡수.

## 0. 데이터 모델 — 오버라이드는 노드에, DSL 밖에

```python
# dsession/slsession 노드에 추가 필드 (LLM 스키마 아님 — Slide/SlideLayout 모델 무변경)
node = {..., "slide": {...}, "brief": {...},
        "overrides": {                      # 없으면 기존과 동일 (하위호환)
          "v": 1,
          "items": {                        # eid -> 요소별 편집 (단위: inch, 엔진 좌표계)
            "r3":  {"dx": 0.3, "dy": -0.1},           # 이동
            "r7":  {"sw": 1.25, "sh": 1.0},           # 크기 배율 (Rect만)
            "t2":  {"text": "Laser gain chip"},        # 텍스트 교체
            "c1":  {"dx": 0, "dy": 0.4, "hidden": false},
            "r9":  {"role": "copper"},                 # 색(재질/semantic role) 교체
            "r4":  {"hidden": true},                   # 삭제 = 숨김
          },
          "added": [                        # 자유 추가 요소 (기존 프리미티브만)
            {"type": "text",  "x": 6.2, "y": 1.4, "w": 2.0, "text": "누설 경로", "size": 14},
            {"type": "arrow", "x1": 5.0, "y1": 2.0, "x2": 6.4, "y2": 2.6, "label": ""},
            {"type": "rect",  "x": 1.0, "y": 3.0, "w": 1.2, "h": 0.5, "role": "accent1",
             "label": "보강재"},
          ]}}
```

- 좌표 단위는 엔진과 같은 inch(px 변환은 프런트가 `PX=96`으로). 수치는 렌더 좌표이지
  물리 치수가 아님 — "LLM 출력에 좌표 금지" 원칙과 무관(LLM은 이 필드를 생성하지 않는다).
- `role`은 palette role만 허용(자유 hex 금지 — 팔레트 일관성 유지).

## 1. eid(stable element id) — `layout.py`

- `TextItem/RectShape/PolyShape/CircleShape/EdgeShape/Callout` dataclass에
  `eid: str | None = None` 필드 추가(기본 None — 기존 생성 코드 무변경).
- `layout_slide()`/`layout_slide_layout()` 마지막에 `assign_eids(items)` 후처리:
  결정적 순회 순서로 `r0,r1..`(shapes) `t0..`(texts) `e0..`(edges) `c0..`(callouts),
  FigureItem 내부는 접두사(`f0.r3`). 같은 JSON → 같은 eid 보장(순수 함수).
- `apply_overrides(items, ov) -> items` (신규 `backend/overrides.py`):
  이동/배율/텍스트/role/hidden 적용 + added를 프리미티브로 변환해 append.
  **SVG와 pptx가 같은 함수를 통과** → 편집 결과도 양쪽 일치가 구조적으로 보장.

## 2. 렌더 경로 — `render_svg.py`, `export_pptx.py`, `slide_render.py`

- `render_slide_svg(slide, overrides=None, editable=False)`:
  overrides 적용 후 렌더. `editable=True`면 각 요소에 `data-eid` 속성 추가(편집기 모드만 —
  일반 프리뷰 SVG는 기존과 byte 동일 유지).
- `build_pptx(deck, overrides_by_slide=None)` / `build_slide_pptx(layout, assets, overrides=None)`:
  같은 `apply_overrides` 경유. export 엔드포인트가 노드의 overrides를 전달.
- `_dsession_payload`/`_ssession_payload`: 노드 svg 렌더 시 overrides 반영(있으면).

## 3. API — `app.py` (+3)

```
POST /api/d/session/{n}/edit_node   {node_id, overrides}        → 파생 노드 생성
POST /api/s/session/{n}/edit_node   {node_id, overrides}        → 파생 노드 생성
POST /api/d/session/{n}/recompile   {node_id, brief}             → Brief 재컴파일 파생 (WP8 잔여)
GET  /api/d/session/{n}/node/{id}/editable_svg                   → data-eid 포함 SVG + 현재 overrides
```

- `edit_node`: 원본 노드의 slide(+brief)를 **복사**하고 overrides를 붙여
  `add_node(s, parent=node_id, instruction="(직접 편집)", ...)` — **파생 연결 요구가
  트리 구조로 공짜로 충족**. telemetry에 `action:"manual_edit"` 기록(WP5 학습 신호:
  직접 편집이 잦은 요소 = 첫 초안 약점).
- 검증: overrides 스키마(pydantic `Overrides` 모델, `overrides.py`), eid 존재 여부는
  관대(없는 eid는 무시 — LLM 수정 후 stale 가능), role은 palette 화이트리스트.
- `recompile`: body의 brief를 `compile_brief`로 재컴파일(모델 호출 없음, 즉시) →
  파생 노드(instruction "(Brief 편집)"). Brief 패널(WP8 §6)을 편집 가능하게 승격.

## 4. 편집기 UI — `index.html`·`slides.html` (vanilla JS, 빌드스텝 없음 유지)

노드 확대 모달에 **"✎ 편집" 버튼** → 편집기 모드 진입(같은 모달 확장):

- **선택**: editable_svg의 `data-eid` 요소 클릭 → 하이라이트(외곽선) + 우측 미니 패널
  (텍스트/role 드롭다운/숨김/z 없음 — 단순 유지).
- **이동**: 드래그 → 클라이언트에서 `transform=translate(dx,dy)` 즉시 반영(라이브),
  overrides.items[eid].dx/dy 갱신. **리사이즈**: Rect 선택 시 모서리 핸들 4개(sw/sh).
- **텍스트**: 더블클릭 → 해당 위치에 input 오버레이 → text 오버라이드.
- **추가**: 툴바 [텍스트|화살표|박스] → 클릭/드래그로 배치 → added에 push.
- **삭제**: 선택 후 Del → hidden:true. **실행취소/재실행**: 클라이언트 스택(overrides
  스냅샷 단위, 메모리만).
- **저장**: `edit_node` POST → 트리 갱신, 새 노드에 `✎` 배지. **취소**: 폐기.
- 슬라이드 탭도 동일 컴포넌트(공용 JS를 두 파일에 복제하지 말고 `frontend/editor.js`
  1개를 `<script src>`로 — 신규 파일은 UI 제약 위반이 아니라 명시적 승인 범위, §7).
- Brief 패널(단면도 탭): 필드를 input으로 승격 + "이 Brief로 다시 그리기" → recompile.

## 5. LLM 수정과 오버라이드의 공존 (승계 규칙)

편집된 노드에서 자연어 수정(branch)하면:
- LLM에는 **DSL(slide/brief)만** 전달(오버라이드 불투명 유지). 결과 슬라이드에
  `assign_eids` 후, **기존 오버라이드 중 eid가 여전히 존재하고 요소 타입이 같은 것만
  승계**, 나머지는 드롭하고 이벤트 로그에 `"오버라이드 n건 유지 / m건 폐기"` 기록.
- added 요소는 항상 승계(엔진 요소와 독립).
- 이 규칙은 `overrides.carry_forward(old_ov, old_items, new_items)`로 순수 함수화(테스트 용이).

## 6. pptx 내보내기·진실성

- export는 항상 오버라이드 적용본 — 화면에서 본 것과 같은 pptx(요구의 "pptx 편집"의 실체).
- truerender(LibreOffice)도 적용본 경유(같은 build_pptx 경로라 자동).
- 원본 DSL은 노드에 그대로 남으므로 "오버라이드 제거" = 편집 전 부모 노드로 회귀(트리가 이력).

## 7. UI 제약 갱신 (00_HANDOFF 전역 제약 개정)

- 기존: "UI 불변 + WP7 최소 예외" → **개정: `index.html`·`slides.html`·신규 `editor.js`에
  편집기 기능 추가 승인**(이번 사용자 요구가 곧 승인). `deck.html`·`settings.html`은 불변 유지.
- 단, 편집기 외 기존 흐름(생성/branch/confirm/export)의 동작·마크업은 보존(회귀 금지).
- "geometry는 layout.py 독점" 원칙은 **베이스 geometry**에 대해 유지되고, 오버라이드는
  베이스 위 diff로 명문화(이 문서가 근거).

## 8. 착수 순서

```
1. overrides.py(모델+apply+carry_forward, 순수 함수) + layout eid + 단위테스트
2. render_svg/export_pptx/slide_render 오버라이드 경유 + editable SVG (mock로 왕복 검증)
3. app.py 엔드포인트 3종 + 노드 저장/페이로드 + telemetry
4. editor.js + index.html 편집기 (이동/텍스트/저장 먼저 → 리사이즈/추가/undo)
5. slides.html에 동일 편집기 장착
6. recompile + Brief 패널 편집 승격 (WP8 잔여 마감)
7. 승계 규칙 연결(branch 경로) + smoke/골든 확장
```

## 9. 수용 기준

1. 단면도 노드에서 편집 → 라벨 이동·텍스트 수정·화살표 추가 → 저장 → **부모에 연결된
   파생 노드** 생성, 트리에 ✎ 배지. 그 노드의 SVG와 export pptx가 편집 내용을 동일하게
   보여준다(픽셀 위치 오차 ≤ 1px 상당).
2. 슬라이드 탭에서도 동일 시나리오 통과(이미지 캡션 이동/수정 포함).
3. 편집 노드에서 자연어 branch → 유지 가능한 오버라이드는 승계, 드롭 수가 로그에 남음.
4. Brief 패널에서 mount를 wirebond→flipchip으로 바꿔 "다시 그리기" → 모델 호출 없이
   즉시 파생 노드, 접합 기하가 바뀜(WP8 수용 기준 2 재확인).
5. overrides 없는 기존 세션/노드는 렌더·export byte 동일(하위호환), smoke ALL PASSED.
6. `Slide`/`SlideLayout` pydantic 스키마 diff = 0 (LLM 스키마 오염 없음 — guided_json 불변).
