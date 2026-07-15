"""WP6 — LLM tool registry (thin pure functions).

Exposes deterministic helpers the pipeline applies post-generation (default,
all providers) or that a tool-calling model may invoke directly (optional).
The LLM's job shrinks to *choosing/using* tools, not free generation.
"""
from __future__ import annotations


def search_knowledge(query: str, kinds: list[str] | None = None, k: int = 4) -> list[dict]:
    import kb
    return kb.retrieve(query, kinds, k=k)


def list_templates() -> list[dict]:
    from templates import list_templates as _lt
    return _lt()


def instantiate_template(name: str, params: dict | None = None):
    from templates import instantiate
    return instantiate(name, params or {})


def choose_layout(intent: str, n_images: int = 0) -> str:
    """Deterministic template recommendation for a single slide (sd-018).
    intent ∈ describe|compare|sequence|highlight|grid|text."""
    it = (intent or "").lower()
    if n_images >= 3 or "grid" in it or "그리드" in it:
        return "image_grid"
    if "compare" in it or "비교" in it or n_images == 2:
        return "two_images"
    if "sequence" in it or "flow" in it or "공정" in it or "순서" in it:
        return "flow"
    if "highlight" in it or "강조" in it or (n_images == 1 and "hero" in it):
        return "hero_title"
    if n_images == 1 or "describe" in it or "설명" in it:
        return "image_left_text_right"
    return "text_only"


def choose_figure_kind(intent: str) -> dict:
    """WP7 — recommend the figure kind(s) for a request (ranked + reasons).
    Thin wrapper over the deterministic router; tool-calling models may call it
    directly, otherwise the backend injects the routed kinds automatically."""
    import router
    h = router.classify(intent)
    return {
        "ranked": [{"kind": k, "score": s, "why": why} for k, s, why in h.ranked[:4]],
        "needs": h.needs,
        "has_series_data": h.has_series_data,
    }


def lint_slide(slide_json: dict) -> list[dict]:
    from models import Slide
    import lint as _lint
    import slidewrite
    s = Slide.model_validate(slide_json)
    return [f.as_dict() for f in (_lint.lint_slide(s) + slidewrite.lint_slide(s))]


def check_figure(slide_json: dict) -> list[dict]:
    from models import Slide
    from geomcheck import check_layout
    return [f.as_dict() for f in check_layout(Slide.model_validate(slide_json))]


REGISTRY = {
    "search_knowledge": search_knowledge,
    "list_templates": list_templates,
    "instantiate_template": instantiate_template,
    "choose_layout": choose_layout,
    "choose_figure_kind": choose_figure_kind,
    "lint_slide": lint_slide,
    "check_figure": check_figure,
}
