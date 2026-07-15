# pptx-copilot (thin vertical slice)

Conversational, multi-stage PowerPoint builder. This slice covers one stage
end-to-end: **chat → LAYOUT_DRAFT → live SVG preview → editable Deck JSON →
.pptx export → LibreOffice fidelity render**.

## Design principles baked in
- **JSON is the source of truth.** The LLM emits a semantic `Deck` (models.py);
  everything renders from it. Raw pptx XML is never edited.
- **LLM does meaning, code does geometry.** The model never outputs
  coordinates. `layout.py` is the single geometry source shared by the SVG
  renderer and the pptx exporter, so preview and export match by construction.
- **Figures = high-level DSL + auto-layout.** A `flow` figure is just
  nodes+edges; `layout.py` computes positions. Easy for a small model.
- **Hybrid preview.** Fast browser SVG for iteration; LibreOffice "true render"
  for fidelity.

## Run
```bash
cd pptx-copilot
. .venv/bin/activate            # deps already installed here
export MOCK=1                    # run without a model
uvicorn app:app --app-dir backend --reload --port 8000
# open http://localhost:8000
```

## Point it at a real model (vLLM / Qwen3)
```bash
export OPENAI_BASE_URL=http://your-vllm-host:8000/v1
export OPENAI_API_KEY=EMPTY
export LLM_MODEL=qwen3
export LLM_JSON_MODE=guided_json   # vLLM: schema-constrained decoding
unset MOCK
```
`LLM_JSON_MODE` ∈ `json_schema` (default) | `guided_json` (vLLM) | `json_object`.

## True render needs (optional)
`libreoffice` + `pdftoppm` (poppler-utils). Missing → the UI just reports it.

## Files
| file | role |
|------|------|
| `backend/models.py` | LLM output schema (`Deck`) |
| `backend/prompts.py` | LAYOUT_DRAFT prompt |
| `backend/layout.py` | geometry engine (inches) — shared truth |
| `backend/render_svg.py` | Deck → SVG (browser preview) |
| `backend/export_pptx.py` | Deck → .pptx (python-pptx) |
| `backend/llm.py` | OpenAI-compatible client + MOCK + repair loop |
| `backend/truerender.py` | pptx → PNG via LibreOffice |
| `backend/app.py` | FastAPI endpoints |
| `frontend/index.html` | single-page UI (no build step) |

## Not in this slice (next)
Figure draft→final iteration loop, per-figure editing, ASSEMBLY stage,
`needs_input` interrupts, persistence/DB, WYSIWYG drag editing, more figure
kinds (comparison/timeline/matrix).
