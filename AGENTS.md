# pptx-copilot — agent guide

Short, imperative rules for any agent (opencode / Claude Code) working here.

## Run & test (verify in this order)

```bash
# app (deterministic mock provider — no model needed)
MOCK=1 uvicorn app:app --app-dir backend --port 8000

# smoke test — MUST print "ALL PASSED" (includes router golden 30/30 + golden-SVG)
cd backend && MOCK=1 python smoke_test.py

# model-quality eval (needs a configured provider) / bench
python eval_llm.py            # golden cases
# or the 벤치 tab / POST /api/bench/run  {"endpoints":["mock"]}
```

If you change rendering intentionally, the golden-SVG check will flag a hash
diff — regenerate `tests/golden_svg.json` (delete it, run smoke once) and commit.

## Invariants (do not break)

- **Geometry only in `backend/layout.py`.** `render_svg.py` / `export_pptx.py`
  consume `DrawItem` primitives; never put coordinates in the renderers.
- **No coordinates/colors/physical dimensions in the LLM schema** (`models.py`).
  A new figure = a `kind` Literal-tagged model + one `_layout_*` function.
  Renderers stay primitive-only. `pad_pitch` etc. are display strings, not math.
- **Single knowledge sources — no string duplication:** structures →
  `domain.py`, archetypes → `archetypes.py`, parts → `parts.py`, assembly
  recipes → `assemblies.py`, prose grounding → `data/kb/*.jsonl`.
- **User edits are an override diff** (`overrides.py`), applied by BOTH SVG and
  pptx — never mutate the LLM `Slide`/`SlideLayout` schema for edits.
- **Frontend is vanilla (no build step).** `data/` (except `data/kb/`) is local
  and gitignored — never commit sessions/config/bench runs.
- **Backward compatible:** with no new env / no overrides, behavior is identical.

## Common task recipes

- **Add a figure kind:** `models.py` model → `layout.py` `_layout_*` +
  dispatch → `archetypes.py`/`examples.py` preset → `lint.py` limits →
  `tests/routing_testset.jsonl` case → smoke.
- **Add a part:** `parts.py` (function → material/glyph/interfaces) → glyph in
  `layout.py` if needed → `assemblies.py` recipe → a `data/kb/*.jsonl` card →
  a `tests/bench_set.jsonl` case.
- **Change generation routing:** `router.py` (keywords / genre) → confirm with
  `tests/routing_testset.jsonl` (smoke gate ≥ 90%).
- **Compare models:** 벤치 tab or `POST /api/bench/run`; tune an endpoint's
  `profile` in `data/config.json`, re-run, compare deltas.

## Layout of the pipeline

`prompt → understand.py (Brief IR) → compile_brief.py → layout.py → render_svg /
export_pptx`. For canonical structures, `templates.match_structure` +
`assemblies.build_assembly` provide a deterministic template-first path (safest
for small models).
