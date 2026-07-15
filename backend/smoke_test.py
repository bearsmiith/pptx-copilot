"""End-to-end smoke test (no LLM): examples -> svg + pptx + json round-trip."""
import os
os.environ["LLM_PROVIDER"] = "mock"

from examples import EXAMPLES
from render_svg import render_slide_svg
from export_pptx import build_pptx
from models import Deck
from llm import generate_deck

for name, deck in EXAMPLES.items():
    svgs = [render_slide_svg(s) for s in deck.slides]
    assert all(s.startswith("<svg") for s in svgs), name
    pptx = build_pptx(deck)
    assert pptx[:2] == b"PK" and len(pptx) > 5000, name
    Deck.model_validate(deck.model_dump())  # round-trip
    print(f"[ok] {name}: {len(svgs)} slides, pptx {len(pptx)//1024}KB")

deck = generate_deck("smoke")
assert len(deck.slides) >= 1
print("[ok] mock provider works")

# WP6: KB load/retrieve, text linter, RAG doesn't change figure render
import kb, slidewrite
st = kb.index_stats()
assert st["design"] > 0 and st["domain"] > 0, st
assert kb.retrieve("CoWoS-L 비교", ["domain"]), "kb retrieve empty"
print(f"[ok] KB: {st['design']} design + {st['domain']} domain cards, retrieve works")

_fw = slidewrite.lint_slide(EXAMPLES["hbm"].slides[0])   # figure → only caption check
assert all(f.code in ("CAPTION_SCALE",) or f.level != "error" for f in _fw)
# figure render identical regardless of RAG (WP6 touches text layer only)
before = render_slide_svg(EXAMPLES["cowos"].slides[0])
os.environ["RAG_KB"] = "0"
after = render_slide_svg(EXAMPLES["cowos"].slides[0])
assert before == after, "RAG must not change figure geometry"
os.environ.pop("RAG_KB", None)
print("[ok] slidewrite linter + figure render invariant under RAG")

# WP7: router golden (deterministic, no model) + general-kind lint clean
import json as _json
import router as _router
from archetypes import ARCHETYPES as _ARCH, build_archetype as _ba
from lint import lint_slide as _ls
from geomcheck import check_layout as _cl

_rt = os.path.join(os.path.dirname(__file__), "..", "tests", "routing_testset.jsonl")
_cases = [_json.loads(l) for l in open(_rt, encoding="utf-8") if l.strip()]
_hit = 0
for c in _cases:
    top = _router.classify(c["prompt"]).ranked[0][0]
    if top in c["expect"]:
        _hit += 1
    else:
        print(f"  route miss: {c['prompt'][:36]!r} -> {top} (want {c['expect']})")
_rate = _hit / len(_cases)
assert _rate >= 0.9, f"routing accuracy {_rate:.0%} < 90%"
print(f"[ok] router golden: {_hit}/{len(_cases)} = {_rate:.0%}")

for _name in _ARCH:
    _sl = _ba(_name)
    _errs = [f for f in (_ls(_sl) + _cl(_sl)) if f.level == "error"]
    assert not _errs, f"{_name} lint errors: {_errs}"
print(f"[ok] all {len(_ARCH)} archetype presets lint-clean")

print("\nALL PASSED")
