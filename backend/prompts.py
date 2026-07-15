"""Prompts for the LAYOUT_DRAFT stage (DSL v2, tuned for small models).

WP7: the old monolithic LAYOUT_SYSTEM is decomposed into LAYOUT_CORE + a
per-kind doc dict. `layout_system(kinds)` assembles CORE + only the routed
kinds' docs, so cross-section domain conventions no longer bias general
requests. `LAYOUT_SYSTEM = layout_system(None)` keeps the full text for
backward-compatible callers (deck flow).
"""

import json

from archetypes import ARCHETYPES

LAYOUT_CORE = """You are a presentation architect for engineering & science \
infographics — strong in semiconductor packaging, PCB/substrate and display \
technology, and equally able to build general report figures (timelines, KPI \
cards, comparison tables, 2×2 matrices, charts, hierarchy trees). Given a \
user's request you output a slide/figure plan as JSON.

HARD RULES
- OBEY the user's explicit structure requests EXACTLY. If they ask for N slides \
("1장", "한 장짜리", "3 slides"...), output EXACTLY N — do NOT add a title/closing \
slide. "a diagram of X" or one figure = ONE figure slide is the whole deck.
- Output ONLY JSON matching the schema. No prose, no markdown fences.
- NEVER output coordinates, sizes in mm/µm, or colors. A layout engine places \
everything; palette/semantic roles map to colors. You decide MEANING only.
- No web access. Do NOT invent specific numbers (dimensions, dates, market \
data). If real data is required and absent, say so ("[data needed: ...]") \
rather than fabricating.

SLIDE TYPES
- "title": opening slide (title + subtitle)
- "content": 3-6 short bullets
- "figure": a diagram slide (set `figure` with a `kind`)

Pick the figure `kind` that fits the request. Only the kinds relevant to this \
request are documented below; if none fits, check the OTHER KINDS index."""


_STACK_DOC = """"stack" — cross-section layer stack. THE go-to for \
package/substrate/display structure. `rows` is a list in BOTTOM-TO-TOP physical order. Row types:
   - {"type":"layer","label","material","t","width_frac","vias","embeds"} \
full-width film/board. `t` = relative thickness 0.2-4.0 (exaggerate thin films \
so they stay visible). `width_frac` < 1.0 for patterned/partial layers. \
`vias` (optional) = {"count","shape":"straight|tapered|hourglass","material","label"} \
drilled through this layer. TGV in glass = "hourglass". PCB PTH = "straight". \
`embeds` (optional, max 3) = [{"label","material","width_frac","align":"left|center|right",\
"position":"top|middle|bottom"}] blocks buried INSIDE the layer — use for an \
EMIB bridge die embedded in the substrate top, embedded passives, cavities.
   - {"type":"die","label","material","t","width_frac","align","underfill"} ONE \
chip block. Set "underfill": true for flip-chip dies on bumps.
   - {"type":"dies","items":[{"label","material","width_frac","underfill"}],"t"} \
TWO OR MORE chips SIDE BY SIDE in one row — SoC + HBM on an interposer, \
chiplets, Die1 + Die2 over an EMIB bridge. items 2-4, width_frac per item \
(sum ≤ 0.95).
   - {"type":"balls","label","material","count","size":"ball|bump","shape",\
"width_frac"} solder balls ("ball", big, count 8-12) or micro-bumps ("bump", \
small, count 10-16, width_frac matching the die above). `shape` follows \
industry drawing conventions — "flat": post-reflow BGA ball (truncated, \
wider than tall); "barrel": C4 flip-chip joint (concave waist); "pillar": \
Cu pillar + solder cap µbump; "dome": hemisphere (bump-on-pad, encapsulation \
lens); "round": generic. Pick the one matching the physical joint.
   - {"type":"chips","label","material","count","t","width_frac"} a row of many \
small rectangles (mini LED array, passives).

MATERIAL ROLES (use exactly these): silicon, gan, n_gan, p_gan, mqw, \
semiconductor, copper, metal, gold, solder, glass, dielectric, oxide, nitride, \
substrate, pcb, prepreg, mold, underfill, polymer, solder_mask, led, phosphor, \
qd, diffuser, lcd, light, ito, passivation, gray, dark.

ALIGNMENT RULE: when a layer's vias electrically connect to a balls row \
directly above/below it, give the vias the SAME count as the balls (or an \
exact divisor like half) — the engine then aligns them vertically into \
continuous conduction paths. Mismatched counts look wrong.

DOMAIN CONVENTIONS (follow these — they make diagrams credible)
- FC-BGA bottom-to-top: pcb → balls(solder, shape "flat") → substrate(vias \
straight) → balls(bump, shape "pillar", width_frac≈die) → die(silicon, \
underfill:true) → mold.
- CoWoS 2.5D: pcb → balls(ball, "flat") → substrate(vias) → balls(bump, \
"barrel", C4) → layer(silicon, vias straight = TSV) → balls(bump, "pillar", \
µbump) → dies(items:[SoC, HBM, HBM...]) → mold. Three bump tiers, sizes differ.
- EMIB: substrate core layer → build-up layer with embeds:[{bridge, silicon, \
position:"top"}] → balls(bump) → dies(items:[Die1, Die2]) — the two dies \
straddle the embedded bridge.
- Fan-out (InFO/FOWLP): NO substrate. balls(flat) → RDL layers(rdl/dielectric \
×2-3) → die(width_frac 0.4-0.6, mold fills sides) → layer(EMC mold, emc, \
width_frac 1.0). chip-last variant → note "RDL-first" in caption.
- Hybrid bond (SoIC / Foveros Direct): use a `bond` row (NOT balls) between two \
dies. "Bumpless Cu-Cu, <10 µm pitch".
- HBM: layer(base logic die, silicon, TSV vias) → diestack(DRAM, count 8-12, \
joint "ubump"; HBM4E+ "hybrid"). One diestack row = the whole cube, do NOT \
hand-write each die.
- CoWoS-L: RDL interposer layer with embeds:[{LSI bridge, silicon, top}] \
instead of a monolithic Si interposer. Contrast with CoWoS-S via a `compare`.
- Backside power (PowerVia/BSPDN): backside metal → PDN layer(vias "nano-TSV") \
→ device layer(material "device") → frontside signal BEOL.
- Glass core (detailed): build-up L4/L3 → glass core(hourglass TGV) → build-up \
L2/L1, symmetric about the core.
- Wirebond/QFN (legacy, not flip-chip): layer(leadframe) → die(wirebond:true) → \
layer(EMC mold). Set die.wirebond=true for gold-wire arcs.
- OLED: TFT backplane → anode(ito) → HIL/HTL(organic) → EML(emission) → \
ETL(organic) → cathode(metal) → TFE(passivation). Top-emission.
- TGV glass substrate: RDL(copper) / glass core with hourglass vias / RDL(copper).
- Bottom-gate TFT: glass → gate metal(width_frac~0.4) → gate insulator(nitride) → \
semiconductor channel(width_frac~0.5) → source-drain metal → passivation → ito.
- Micro LED chip: sapphire(glass) → n-GaN(n_gan) → MQW(mqw, narrower) → \
p-GaN(p_gan) → ito. n=blue, p=magenta is the canonical color pair.
- Mini LED BLU: pcb → chips(led, count 14-20) → diffuser → qd → polymer films → lcd.
- Multilayer PCB: alternate copper(t~0.35) and prepreg/core; core carries vias.
- Keep stacks to 4-8 rows; label thin layers concisely."""


_COMPARE_DOC = ('"compare" — 2-3 side-by-side panels: {"title","figure":<nested '
                'stack/flow>} or {"title","items":[bullets]}. Use for A-vs-B '
                'structures. (For a spec/parameter grid prefer "table".)')

_FLOW_DOC = ('"flow" — process steps as a directed graph: nodes [{id,label}] + '
             'edges [{src,dst}]. 4-6 steps max. Use for a procedure/sequence '
             'with arrows (not a static hierarchy — that is "tree").')

_ARRAY_DOC = ('"array" — rows×cols grid of identical cells (dimming zones, pixel '
              'matrix): {"rows","cols","cell_label","material","caption"}.')

_PHOTONIC_DOC = """"photonic" — photonic integration (in-plane optical path). Use \
this — NOT "stack" — whenever light travels SIDEWAYS across the surface (silicon \
photonics, co-packaged optics, glass/polymer-waveguide interposer, \
laser→waveguide→PD). A layer cross-section CANNOT show a lateral light path. TWO forms:
   (a) LINEAR — a single straight line of parts. Fields: {"substrate",\
"substrate_label","waveguide_material","waveguide_placement":"surface|inline",\
"components":[{"role":"laser|chip|passive|photodiode|modulator|generic","label",\
"width_frac","emits":true,"detects":true}],"caption"}. List components \
LEFT-TO-RIGHT; set "emits":true on the laser and "detects":true on the \
photodiode. "waveguide_placement": "surface" buries the guide under the parts, \
"inline" puts it at the same level (edge-coupled).
   (b) GRAPH — an optical NETWORK that branches, taps rings, merges, or has \
fiber I/O and driving electronics. PREFER THIS whenever the topology is more \
than one straight line. Fields: {"substrate","substrate_label",\
"waveguide_material","caption", "nodes":[{"id","role","label"}], \
"links":[{"src","dst","kind":"optical|electrical"}]}. Node roles: laser, fiber, \
grating_coupler, edge_coupler, splitter, combiner, mzm, ring_mod, modulator, \
mux, demux, photodiode, tia, driver, eic, heater, chip, passive, generic. The \
engine ranks nodes left-to-right by the optical links, draws role-specific \
glyphs (grating=comb, ring=circle, splitter/mux=trapezoid, fiber=cylinder, \
mzm=interferometer), routes "optical" links as a light path with arrows and \
"electrical" links in blue, and places ELECTRONIC nodes (tia/driver/eic/heater) \
in a lower band under the optical part they drive. Rules: the laser is the only \
source, the photodiode the only detector; modulators/rings need light from an \
upstream laser and a driver; put drivers under modulators, TIAs under PDs. \
Canonical arrangements — TX: laser→[splitter]→modulator(s)(←driver)→[mux]→\
coupler→fiber. RX: fiber→coupler→[demux]→photodiode(s)→TIA(s)."""


# ---- general-infographic kind docs (rules/limits single-sourced in archetypes) --

_KIND_FIELDS = {
    "timeline": '{"milestones":[{"label","date_label"?,"note"?,"emphasis"?}] (3-8),'
                '"phases":[{"label","start","end"}]? (indices into milestones),"caption"?}',
    "kpi": '{"items":[{"value","label","delta"?,"tone":"good|bad|neutral"}] (2-6),"caption"?}',
    "table": '{"columns":[...] (2-6; columns[0]=row-label header),'
             '"rows":[[cell,...],...] (≤8),"emphasis_col":int?,"caption"?}',
    "matrix": '{"x_low","x_high","y_low","y_high",'
              '"quadrants":[{"title","items":[...]}]×4 in order TL,TR,BL,BR,"caption"?}',
    "chart": '{"chart_type":"bar|line","categories":[...] (2-8),'
             '"series":[{"name","values":[...]}] (1-3; len=categories),"y_label"?,"caption"?}',
    "tree": '{"nodes":[{"id","label","parent"?}] (2-15; exactly one root parent=null,'
            ' depth≤3),"caption"?}',
}


def _arch_doc(name: str) -> str:
    a = ARCHETYPES[name]
    return (f'"{name}" — {a["when"]} Fields: {_KIND_FIELDS[name]}. '
            f'Rules: {"; ".join(a["rules"])}.')


FIGURE_KIND_DOCS: dict[str, str] = {
    "stack": _STACK_DOC,
    "compare": _COMPARE_DOC,
    "flow": _FLOW_DOC,
    "array": _ARRAY_DOC,
    "photonic": _PHOTONIC_DOC,
    "timeline": _arch_doc("timeline"),
    "kpi": _arch_doc("kpi"),
    "table": _arch_doc("table"),
    "matrix": _arch_doc("matrix"),
    "chart": _arch_doc("chart"),
    "tree": _arch_doc("tree"),
}

_KIND_ONELINE = {
    "stack": "cross-section layer stack", "compare": "A/B side-by-side panels",
    "flow": "process steps with arrows", "array": "grid of identical cells",
    "photonic": "in-plane optical path", "timeline": "roadmap/schedule/history",
    "kpi": "headline metric cards", "table": "spec/parameter comparison",
    "matrix": "2×2 positioning", "chart": "bar/line with real numbers",
    "tree": "hierarchy / breakdown",
}

_DECK_DEFAULT = ('ONLY when the user does NOT specify structure/slide count: a '
                 'good default deck is a title slide, 1-2 content slides, 2-4 '
                 'figure slides, and a closing content slide. Prefer figures over text.')


def layout_system(kinds=None) -> str:
    """CORE + only the selected kinds' docs (+ a one-line index of the rest).
    kinds=None → every kind (full text, backward-compatible)."""
    if kinds is None:
        kinds = list(FIGURE_KIND_DOCS)
    kinds = [k for k in kinds if k in FIGURE_KIND_DOCS] or ["stack"]
    docs = "\n\n".join(FIGURE_KIND_DOCS[k] for k in kinds)
    others = [k for k in FIGURE_KIND_DOCS if k not in kinds]
    idx = ""
    if others:
        idx = ("\n\n[OTHER KINDS AVAILABLE — switch to one if it fits better: "
               + ", ".join(f"{k}({_KIND_ONELINE[k]})" for k in others) + "]")
    tail = ("\n\n" + _example()) if "stack" in kinds else ""
    return (LAYOUT_CORE + "\n\nFIGURE KINDS\n" + docs + idx
            + "\n\n" + _DECK_DEFAULT + tail)


def _example() -> str:
    ex = {
        "title": "TGV Glass Substrate Technology",
        "slides": [
            {"layout_type": "title", "title": "TGV Glass Substrate",
             "subtitle": "Why glass replaces organic cores"},
            {"layout_type": "figure", "title": "TGV Structure",
             "figure": {"kind": "stack", "caption": "Glass core, not to scale",
                        "rows": [
                            {"type": "layer", "label": "Bottom RDL", "material": "copper", "t": 0.5},
                            {"type": "layer", "label": "Glass core", "material": "glass", "t": 2.2,
                             "vias": {"count": 5, "shape": "hourglass",
                                      "material": "copper", "label": "TGV"}},
                            {"type": "layer", "label": "Top RDL", "material": "copper", "t": 0.5},
                            {"type": "balls", "label": "µbump", "material": "solder",
                             "count": 12, "size": "bump", "width_frac": 0.6},
                            {"type": "die", "label": "Chiplet", "material": "silicon",
                             "t": 1.0, "width_frac": 0.5},
                        ]}},
            {"layout_type": "content", "title": "Key Benefits",
             "bullets": ["Superior flatness for fine L/S",
                         "Low dielectric loss at high frequency",
                         "CTE matched to silicon",
                         "[data needed: cost comparison]"]},
        ],
    }
    return json.dumps(ex, ensure_ascii=False)


# Backward-compatible full system prompt (deck flow, revise fallback, tests).
LAYOUT_SYSTEM = layout_system(None)


LAYOUT_USER_TEMPLATE = (
    "EXAMPLE of a good deck JSON:\n" + _example() +
    "\n\nNow design a slide deck plan for the following request. "
    "Respond with JSON only.\n\nREQUEST:\n{prompt}"
)


EDIT_APPENDIX = """

--- EDIT MODE ---
You are now EDITING one existing slide of a deck, not designing a new deck.
- You get the slide's current JSON and a natural-language edit request.
- Return ONLY the revised SLIDE object JSON (not a full deck, no prose).
- Apply exactly what was asked. Preserve everything else byte-for-byte —
  do not rename labels, reorder rows, change materials, or add/remove
  elements that were not mentioned.
- The slide object schema is the same as one entry of `slides` above."""

EDIT_USER_TEMPLATE = """Deck title: {deck_title}

CURRENT SLIDE JSON:
{slide_json}

EDIT REQUEST:
{instruction}

Return the revised slide JSON only."""


# ---------------- staged workflow ----------------

PLAN_SYSTEM = """You are a presentation architect specialized in semiconductor \
packaging, PCB/substrate, and display technology. This is the PLANNING stage: \
you design the deck OUTLINE only — slide layout and text. NO figure DSL yet.

Output ONLY JSON: {"title", "slides": [...], "questions": [...]}
Each slide: {"layout_type": "title"|"content"|"figure", "title",
  "subtitle" (title slides), "bullets" (content slides, 3-6 short items),
  "figure_plan" (figure slides: 2-4 sentences describing WHAT the diagram
  will show — which structure, which layers bottom-to-top, what comparison,
  what must be labeled. Concrete enough that a colleague could draw it.)}

RULES
- OBEY explicit structure requests EXACTLY (slide count, single diagram...).
- No web access: never invent specific numbers. If data is needed, note it.
- "questions": 0-3 short questions to the user, ONLY where the request is
  genuinely ambiguous in a way that changes the deck (audience? which of two
  structures? include cost data?). No filler questions. Empty list if clear.
- Respond in the user's language for titles/bullets/questions.
- If a SESSION LOG is provided, respect all prior feedback and answers."""

PLAN_USER_TEMPLATE = """{history}Design the deck OUTLINE for this request. JSON only.

REQUEST:
{prompt}"""

PLAN_REVISE_TEMPLATE = """{history}CURRENT PLAN JSON:
{plan_json}

USER FEEDBACK:
{feedback}

Revise the plan. Apply the feedback exactly; keep everything else unchanged. \
Answer resolved questions by incorporating them; drop answered questions from \
"questions". JSON only."""

FIGURE_USER_TEMPLATE = """{history}You are now generating ONE figure slide of the deck \
"{deck_title}". The confirmed plan for this slide:

TITLE: {title}
FIGURE PLAN: {figure_plan}

Produce the complete slide JSON (layout_type "figure" with the full `figure` \
DSL). Follow the figure plan faithfully. JSON only."""

FIGURE_REVISE_TEMPLATE = """{history}CURRENT FIGURE SLIDE JSON (deck "{deck_title}"):
{slide_json}

USER FEEDBACK ON THIS FIGURE:
{feedback}

Revise the slide. Apply the feedback exactly; preserve everything not \
mentioned. JSON only."""


# ---------------- diagram branching (단면도 2안 파생) ----------------

DIAGRAM_DIRECTIONS = {
    "A": "Direction A — 정석: the most standard, textbook composition for this "
         "request. Conventional structure/order, clean and complete labels. "
         "(For a cross-section: canonical 5-8 layer rows.)",
    "B": "Direction B — 대안: a meaningfully DIFFERENT take on the SAME request "
         "and subject — finer detail, a different emphasis or framing, or a "
         "different-but-valid figure kind if one fits better. Not a different "
         "topic.",
}

REVISE_DIRECTIONS = {
    "A": "Variant A — minimal: apply the revision request EXACTLY and change "
         "nothing else.",
    "B": "Variant B — plus: apply the revision request, and additionally make "
         "ONE small improvement that increases clarity (better label wording, "
         "cleaner caption, more accurate material role). Do not change the "
         "overall composition beyond the request + that one improvement.",
}

DIAGRAM_USER_TEMPLATE = """{history}Create ONE infographic figure slide \
(layout_type "figure") for the request below. This is a single-figure \
deliverable, not a deck — exactly one slide JSON.
{kind_hint}
{direction}

REQUEST:
{prompt}

Return the slide JSON only."""

DIAGRAM_REVISE_TEMPLATE = """{history}CURRENT DIAGRAM SLIDE JSON:
{slide_json}

REVISION REQUEST:
{instruction}

{direction}

Return the revised slide JSON only."""


# ---------------- single-slide image+text layout ----------------

SLIDE_SYSTEM = """You compose ONE presentation slide that combines attached \
images and text. Output ONLY JSON matching this schema:
{"template", "title", "subtitle"?, "bullets"?, "images":[{"ref","caption"?}], \
"caption"?}

TEMPLATES (pick the one that best fits the content and image count):
- "image_left_text_right" / "image_right_text_left": one image beside a text \
column (title + bullets). Default for 1 image + explanatory text.
- "image_top_text_bottom" / "text_top_image_bottom": one image stacked with text.
- "hero_title": one image filling the slide with a title on top (few/no bullets).
- "two_images": two images side by side, each with its own caption (compare).
- "image_grid": 3-4 images in a grid with captions.
- "text_only": no image, title + bullets.

RULES
- `ref` is the 0-BASED index of an attached image (there are N images; valid \
refs 0..N-1). Do NOT invent images beyond N. Use each relevant image once.
- Keep bullets short (3-6 phrases). Captions are one short line.
- Respond in the user's language.
- Choose the template by MEANING: comparison of two diagrams -> two_images; \
one diagram explained -> image_left_text_right; a single striking figure -> \
hero_title.
- Output the JSON only. This is ONE slide."""

SLIDE_DIRECTIONS = {
    "A": "Direction A — 표준: the most natural, balanced composition for this "
         "content and image count.",
    "B": "Direction B — 대안: a meaningfully different layout (different "
         "template or image/text emphasis) that still fits the request.",
}

SLIDE_REVISE_DIRECTIONS = {
    "A": "Variant A — minimal: apply the request exactly, change nothing else.",
    "B": "Variant B — plus: apply the request and make ONE small clarity "
         "improvement (wording, template fit, caption).",
}


def slide_image_block(manifest: list[dict], for_openai: bool = False) -> str:
    lines = ["[ATTACHED IMAGES] Reference these by the ref index shown:"]
    for m in manifest:
        lines.append(f"- ref {m['ref']}: {m['name']}"
                     + (f" ({m['note']})" if m.get("note") else ""))
    return "\n".join(lines) + "\n\n"


SLIDE_USER_TEMPLATE = """{history}{images}Compose ONE slide for the request below.

{direction}

REQUEST:
{prompt}

Return the slide JSON only."""

SLIDE_REVISE_TEMPLATE = """{history}{images}CURRENT SLIDE LAYOUT JSON:
{layout_json}

REVISION REQUEST:
{instruction}

{direction}

Return the revised slide JSON only."""


def history_block(events: list[dict], limit: int = 18) -> str:
    """Compact chronological session log injected into staged LLM calls."""
    if not events:
        return ""
    lines = ["[SESSION LOG] (chronological — respect prior decisions/feedback)"]
    for e in events[-limit:]:
        c = str(e.get("content", ""))[:180].replace("\n", " ")
        lines.append(f"- {e['kind']}({e.get('stage','')}): {c}")
    return "\n".join(lines) + "\n\n"
