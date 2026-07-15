# Offline training / rule-mining (WP5 tiers 2–3)

These run **outside the app**, on a GPU host, and never touch the request path.
The app improves online via tier-1 (retrieval + profile, already wired in
`backend/retrieve.py` / `backend/profile.py`). Tiers 2–3 kick in once enough
accepted data has accumulated.

Data flow: `backend/corpus.py` → `data/learning/{sft_generate,sft_revise,dpo}.jsonl`.

- `build_corpus.py` — wraps `backend.corpus.build()` (regenerate datasets).
- `train_lora.py`  — SFT LoRA on qwen3.6-27b / 3.5-122b from sft_* (stub).
- `run_dpo.py`     — DPO preference alignment from dpo.jsonl (stub).
- `promote_adapter.py` — gate: only swap the served adapter if `eval_llm.py`
  shows a first-draft-acceptance / lint-pass improvement over current.
- `mine_rules.py`  — tier-3: mine repeated corrections → proposed diffs for
  `backend/repair.MATERIAL_ALIAS` / `templates` defaults (human-reviewed).

haiku (claude_cli) is not fine-tunable → improves via tiers 1 & 3 only.
All data stays on-prem (governance: `handoff/04_learning_loop.md` §7).
