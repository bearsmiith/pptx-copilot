"""WP8 — the UNDERSTAND stage: request -> Brief IR (kind-agnostic).

Decides genre, lists parts + mounting interfaces + relations, marks open
questions. Revisions pass the prior Brief and apply the change (so structural
edits reach the Brief, not just labels). Deterministic mock for model-free tests.
"""
from __future__ import annotations

import json

from brief_model import Brief

UNDERSTAND_SYSTEM = """You extract a structured BRIEF (an understanding) of a \
request for a technical figure. You DECIDE the genre and list the parts — you do \
NOT draw, and you NEVER emit coordinates, colors, or physical dimensions.

Output ONLY JSON matching this schema:
{"genre":"physical"|"infographic","genre_confidence":0..1,
 "emphasis":"section"|"planar"|"auto","title":str,"caption":str?,
 "base":str? (id of the substrate part),
 "parts":[{"id":str,"name":str,"function":str,
           "on":str? (id of the part it is mounted ON; omit = on the base),
           "interface":{"kind":str,"pad_count":int?,"pad_pitch":str?,"underfill":bool?}?,
           "attributes":{"emits":bool?,"detects":bool?,"buried":bool?,"cavity":bool?}?}],
 "relations":[{"type":"optical"|"electrical"|"mechanical","src":str,"dst":str,"label":str?}],
 "open_questions":[str],"requirements":[str]}

EMPHASIS (physical only): "section" = a vertical cross-section showing mounting/\
build-up (default). "planar" = a top/network view showing the signal topology \
(nodes + links). Set "planar" only when the user asks for a network / block / \
topology / 평면 / 네트워크 view; otherwise "section".

GENRE. "physical" = a real physical structure / cross-section / parts mounted on a \
substrate (packaging, silicon photonics, MEMS, display, sensor). "infographic" = an \
abstract data figure (timeline, table, chart, kpi, matrix, tree). If genuinely \
ambiguous, set a LOW genre_confidence and put a genre question in open_questions.

FIELDS: "id" = a short unique handle ("pic","laser","pd"). "name" = the display \
label ("Laser gain chip"). "function" = EXACTLY ONE of the function keys below — \
NOT a description sentence.

PARTS & MOUNTING (physical) — use REAL assembly facts:
- ALWAYS include the substrate/base itself as a part (the 기판 / PIC / package \
substrate) and set the top-level "base" to its id. Everything else mounts on it.
- function keys — bases: pic, substrate, interposer, submount, pcb, leadframe. \
parts: laser_gain, photodiode, logic_die, modulator, driver_ic, tia, eic, hbm, \
mems, mlcc, passive, waveguide, lens, fiber, generic. mobile/watch: ap_pop, \
dram_pkg, nand, pmic, rf_fem, shield_can, btb_conn, flex_pcb, passive_01005, \
crystal, sip_module. photonic/sensor: fiber_vgroove, microlens_arr, color_filter, \
glass_lid. package features: mold, bga.
- A shield_can sets attributes.covers = [ids of parts it encloses]. PoP = a memory \
package (dram_pkg) mounted ON the AP (on:"ap"). A bottom-side part sets \
attributes.side="bottom". Chip-on-chip stacks (pixel on logic, filter on pixel) \
chain via `on`.
- A part mounted on the base or on another part sets "on". Chip-on-chip is normal \
(a laser gain chip mounted ON a PIC → on:"pic").
- interface.kind = HOW it is joined: "wirebond" (face-up die, pads on top, gold \
arcs), "flipchip"/"c4"/"cu_pillar" (face-down die, bump array UNDER it — set \
underfill), "solder" (solder pads/bumps), "hybrid_bond" (bumpless Cu-Cu), \
"edge_couple" (optical butt-coupling at the edge), "monolithic" (formed IN the \
substrate), "die_attach" (epoxy/eutectic), "stack"/"none".
- PACKAGE-LEVEL features: the encapsulation/overmold → a part with function "mold" \
(or "emc"); the package's bottom-side balls (BGA/LGA) that join to the board → a \
part with function "bga" and interface.pad_count. A component on the UNDERSIDE of \
the substrate → attributes {"side":"bottom"}. These render around/under the substrate.
- A laser gain chip HAS bond pads; it is edge-emitting and usually solder/flip-chip \
mounted so its facet aligns to an edge coupler — set attributes.emits. A photodiode \
sets attributes.detects. A waveguide in a PIC is usually BURIED \
(attributes.buried) — a channel inside the substrate, not a surface box.
- An optical light path → a relation {"type":"optical","src":<source part>,\
"dst":<final receiver part>,"via":<waveguide id>?}. Connect the SOURCE (laser) \
to the RECEIVER (photodiode), not to the waveguide — the waveguide is the `via`. \
This is what draws the beam.

RULES:
- Keep parts MINIMAL — only what the request implies. Do NOT add a full \
transceiver (modulator/MUX/driver/TIA) if only a laser + waveguide + photodiode \
are asked for.
- REQUIREMENTS: list what the figure MUST show (e.g. "laser solder-mounted on \
PIC", "waveguide buried in PIC", "optical beam laser->photodiode") so a later \
check can verify it.
- Do not invent precise numbers; pad_pitch/size are display strings only if given."""


def understand(prompt: str, prior_brief: dict | None = None,
               events: list[dict] | None = None) -> Brief:
    from llm import _use_mock, _validated
    if _use_mock():
        return _mock_brief(prompt, prior_brief)
    if prior_brief:
        user = ("CURRENT BRIEF JSON:\n" + json.dumps(prior_brief, ensure_ascii=False)
                + "\n\nAPPLY this change and return the FULL updated brief JSON:\n"
                + prompt + "\n\nReturn JSON only.")
    else:
        user = ("Build the brief for this request. Return JSON only.\n\nREQUEST:\n"
                + prompt)
    messages = [{"role": "system", "content": UNDERSTAND_SYSTEM},
                {"role": "user", "content": user}]
    return _validated(Brief, messages, stage="figure")


# ---- deterministic mock (no model) ----

def _mock_brief(prompt: str, prior: dict | None) -> Brief:
    if prior:
        b = Brief.model_validate(prior)
        b.caption = (b.caption or "") + " [수정 반영(mock)]"
        return b
    t = (prompt or "").lower()
    infographic = any(k in t for k in ("로드맵", "타임라인", "차트", "그래프", "표",
                                       "비교표", "매트릭스", "지표", "kpi", "구성도"))
    if infographic:
        return Brief(genre="infographic", genre_confidence=0.8,
                     title=prompt[:40] or "Infographic", parts=[])
    from brief_model import Part, Interface, Relation
    parts = [Part(id="sub", name="Substrate", function="substrate")]
    rels = []
    if "laser" in t or "레이저" in t:
        parts.append(Part(id="laser", name="Laser", function="laser_gain", on="sub",
                          interface=Interface(kind="solder", pad_count=5),
                          attributes={"emits": True}))
    if "waveguide" in t or "도파로" in t:
        parts.append(Part(id="wg", name="Waveguide", function="waveguide", on="sub",
                          attributes={"buried": True}))
    if "photodiode" in t or "포토다이오드" in t or "수광" in t:
        parts.append(Part(id="pd", name="Photodiode", function="photodiode", on="sub",
                          interface=Interface(kind="flipchip", pad_count=4),
                          attributes={"detects": True}))
    if any(p.id == "laser" for p in parts) and any(p.id == "pd" for p in parts):
        rels.append(Relation(type="optical", src="laser", dst="pd", label="optical path"))
    if len(parts) == 1:                          # nothing recognized → a generic die
        parts.append(Part(id="die", name="Die", function="logic_die", on="sub",
                          interface=Interface(kind="flipchip", pad_count=6)))
    return Brief(genre="physical", genre_confidence=0.9, title=prompt[:40] or "Structure",
                 base="sub", parts=parts, relations=rels)
