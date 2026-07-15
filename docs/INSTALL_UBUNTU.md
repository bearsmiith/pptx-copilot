# Install — Ubuntu 24.04 + local Qwen (vLLM) + opencode

Every step is written so a **local LLM agent (opencode) can execute it directly**:
① a copy-paste command, ② a verification command with expected output, ③ a
failure hint. Version-sensitive items (vLLM flags, opencode config, model HF IDs)
are marked **[verify at setup]** — check the current vLLM / Qwen / opencode docs
and pin the versions you used at the bottom.

---

## 0. Requirements

- Ubuntu 24.04, Python 3.12 (default), `git`.
- To serve a model: NVIDIA driver + CUDA. VRAM guidance **[verify at setup]**:
  - Qwen3.6-27B: bf16 ≈ 60 GB (2×A6000 / 1×H100); AWQ/GPTQ 4-bit ≈ 20 GB (1×3090/4090).
  - Qwen3.5-122B (A10B MoE): bf16 = multi-GPU/server; 4-bit ≈ 70 GB+.
- Verify: `python3 --version` → `Python 3.12.x`; `nvidia-smi` lists your GPU.
- Fail: no `python3.12` → `sudo apt install python3.12 python3.12-venv`; no
  `nvidia-smi` → install the NVIDIA driver (you can still run the app in MOCK mode).

## 1. Install the app

```bash
git clone https://github.com/bearsmiith/pptx-copilot && cd pptx-copilot
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

- Verify: `MOCK=1 uvicorn app:app --app-dir backend --port 8000 &` then
  `curl -s localhost:8000/api/config | head -c 60` → JSON starting `{"active"`.
- Fail: `ModuleNotFoundError` → re-activate the venv and re-run `pip install`.

## 2. Smoke test (no model)

```bash
cd backend && MOCK=1 python smoke_test.py ; cd ..
```

- Verify: last line is `ALL PASSED`.
- Fail: a `[!!]` line names the broken preset — file an issue with that line.

## 3. (Optional) true-fidelity pptx render

```bash
sudo apt install -y libreoffice poppler-utils
```

- Verify: `soffice --version` prints a LibreOffice version.
- Fail: not installed → the UI still works; only the LibreOffice fidelity
  preview is disabled (a warning, not an error).

## 4. Serve a model with vLLM  **[verify at setup]**

```bash
# separate env recommended
python3 -m venv .vllm && . .vllm/bin/activate && pip install vllm

# serve (flags/model-id are version-sensitive — confirm against vLLM + Qwen docs)
vllm serve <HF_MODEL_ID_or_local_path> \
  --port 8001 --max-model-len 32768 \
  --guided-decoding-backend xgrammar \
  [--tensor-parallel-size N] [--quantization awq]
```

- Verify: `curl -s localhost:8001/v1/models` lists the served model id.
- Fail: OOM → use `--quantization awq` / a 4-bit checkpoint / the 27B model;
  `guided-decoding` unsupported on your version → drop the flag and use
  `json_mode=json_object` in step 5.

## 5. Connect the app to the model

- In the **설정** tab: set the `qwen27b` (or `qwen122b`) endpoint —
  `base_url=http://<host>:8001/v1`, `model=<served id>`,
  `json_mode=guided_json` — then click **테스트** (expect `ok`).
- Headless equivalent:

```bash
curl -s -X POST localhost:8000/api/config -H 'Content-Type: application/json' \
  -d '{"active":"qwen27b","endpoints":{"qwen27b":{"base_url":"http://localhost:8001/v1","model":"<served id>","json_mode":"guided_json"}}}'
```

- Verify: `curl -s -X POST localhost:8000/api/config/test -H 'Content-Type: application/json' -d '{"endpoint":"qwen27b"}'` → `{"ok":true...}`.
- Fail: connection refused → check the vLLM port/firewall; keys are stored in
  `data/config.json` (gitignored — never commit).

## 6. Verify generation quality

```bash
python eval_llm.py            # golden pass rate
```

- Verify: prints a summary line with a pass count.
- Also: the **벤치** tab → pick the endpoint + a small category → **실행 ▶** →
  a model × category heatmap. 27B: keep its `template_first` profile on.

## 7. opencode + local Qwen  **[verify at setup]**

```bash
# install opencode (use the current official installer / npm — verify)
# then register the local vLLM as an OpenAI-compatible provider:
#   base_url = http://localhost:8001/v1 , model = <served id>
```

- Verify: `AGENTS.md` loads automatically; give it a task —
  *"run the smoke test in backend and fix any failure"* — it runs
  `MOCK=1 python smoke_test.py` and reports `ALL PASSED`.
- Fail: provider not found → recheck the opencode config schema for your version.

## 8. Troubleshooting

- `guided_json` unsupported → `json_mode=json_object` (looser, still works).
- VRAM too low → 4-bit quantization or the 27B model.
- CORS / firewall between app and vLLM host → open the port, use the host IP.
- 27B vs 122B: **27B** = single-GPU + `template_first` profile, practical;
  **122B** = higher quality + multimodal (attached images). Compare in the 벤치 tab.

---

**Verified versions (fill in at setup):** vllm==`X.Y`, opencode==`Z`,
model=`<HF id>`, GPU=`<name/count>`.
