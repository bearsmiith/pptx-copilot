"""Material color palette for technical cross-section infographics.

The LLM never picks colors — it assigns a semantic `material` role and the
palette decides appearance. Curated for professional look on white slides
(semiconductor/display industry conventions: copper=warm orange-brown,
solder=cool gray, silicon=blue-gray, glass=translucent blue, etc).
"""
from __future__ import annotations

# role -> (fill, stroke)
MATERIALS: dict[str, tuple[str, str]] = {
    # dies / semiconductors (industry-canonical hues, see research notes)
    "silicon":     ("#6e7b8b", "#4d5866"),   # die = dark blue-gray
    "gan":         ("#b7a4d6", "#8a74ad"),   # generic GaN / III-V epi
    "n_gan":       ("#5b8fd0", "#33639f"),   # n-GaN = blue (canonical)
    "p_gan":       ("#c968ab", "#9c3f7f"),   # p-GaN = magenta (canonical pair)
    "mqw":         ("#f2c94c", "#d49b2e"),   # active region = warm yellow band
    "semiconductor": ("#a9b8d6", "#7889ad"),
    # metals
    "copper":      ("#e8983a", "#b87333"),
    "metal":       ("#8c96a5", "#5f6873"),   # gate/SD metal = dark slate
    "gold":        ("#d4af37", "#a8862a"),
    "solder":      ("#c0c7ce", "#8a9199"),
    # insulators / structural
    "glass":       ("#cde8f5", "#8fbfd9"),
    "dielectric":  ("#d9c58f", "#b09a5e"),   # ABF/organic build-up = tan
    "oxide":       ("#bfd9e8", "#8db4cb"),
    "nitride":     ("#bee0c2", "#8dba93"),
    "substrate":   ("#d9c9a8", "#b5a077"),   # organic package substrate
    "pcb":         ("#3a7d44", "#285a30"),   # FR4 green (darker, credible)
    "prepreg":     ("#8fbc8f", "#659a65"),   # lighter shade of core
    "mold":        ("#3b3f45", "#26292e"),   # black epoxy mold
    "underfill":   ("#5b8bc9", "#3a659c"),   # blue is the classic underfill
    "polymer":     ("#e7d3c0", "#c2a889"),
    "solder_mask": ("#3f7d4e", "#2c5837"),
    # display / optics
    "led":         ("#7ec8e3", "#4b9dbd"),
    "phosphor":    ("#f7d774", "#d4ae3a"),
    "qd":          ("#f0a35e", "#c97c33"),   # quantum dot film
    "diffuser":    ("#e8eef4", "#b9c6d4"),
    "lcd":         ("#c3d5e8", "#8fa9c7"),
    "light":       ("#fff3b8", "#e8cf5e"),
    "ito":         ("#bfe0dc", "#84b8b1"),
    "passivation": ("#dce8dd", "#a8c4ab"),
    # generic
    "accent":      ("#e8f0fe", "#2f6fed"),
    "gray":        ("#e3e6ea", "#aab0b8"),
    "white":       ("#ffffff", "#9aa2ac"),
    "dark":        ("#4a4f57", "#33373d"),
    # advanced packaging / display (WP1)
    "emission":   ("#8be0c0", "#4fae8c"),   # OLED emission layer (EML)
    "organic":    ("#e9dcc8", "#c7b48f"),   # HIL/HTL/ETL organic thin films
    "device":     ("#9aa7c4", "#6b7aa0"),   # transistor / nanosheet device layer
    "rdl":        ("#e8983a", "#b87333"),   # RDL (same tone as copper)
    "emc":        ("#4a4741", "#2f2d29"),   # fan-out EMC mold (warm near-black)
    "bond_oxide": ("#d5dbe0", "#9aa6b0"),   # hybrid-bond dielectric interface
    "leadframe":  ("#c9ccd1", "#9aa0a8"),   # leadframe (bright silver metal)
    "optical":    ("#e5484d", "#c0353a"),   # in-plane light path (laser beam / λ)

    # WP7 general-infographic semantic roles (NOT materials — role, not color)
    "accent1": ("#dbe7fd", "#2f6fed"), "accent2": ("#dff3e7", "#2e9e5b"),
    "accent3": ("#fdeeda", "#d97917"), "accent4": ("#f3e3f5", "#a24bb8"),
    "accent5": ("#e8eef4", "#5b6472"), "accent6": ("#fde3e4", "#d64550"),
    "good": ("#dff3e7", "#2e9e5b"), "bad": ("#fde3e4", "#d64550"),
    "warn": ("#fdeeda", "#d97917"), "neutral": ("#eef1f6", "#8a93a0"),
    "ink": ("#1f2a44", "#1f2a44"), "grid": ("#eef1f6", "#d7dbe3"),
    "track": ("#e3e6ea", "#c3c9d1"),         # timeline axis / gantt track
}

DEFAULT = ("#dfe4ea", "#9aa2ac")


def material_colors(role: str | None) -> tuple[str, str]:
    if not role:
        return DEFAULT
    return MATERIALS.get(role.lower().strip(), DEFAULT)


# roles whose fill is dark enough to need light text
DARK_ROLES = {"mold", "dark", "solder_mask", "pcb", "silicon", "emc", "device", "ink"}
