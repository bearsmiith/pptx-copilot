"""WP8 — Brief IR: the editable, kind-agnostic understanding of a request.

Richer than any figure DSL: it carries genre, parts, mounting interfaces and
relations independent of HOW it will be drawn. `compile_brief` projects it to a
concrete figure; revisions edit the Brief and recompile (so structural changes —
solder pads, chip-on-chip — reach the geometry, not just labels).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# interface.kind — how a part joins what is beneath it (07b research)
InterfaceKind = Literal[
    "none", "stack", "die_attach", "solder", "c4", "cu_pillar", "flipchip",
    "wirebond", "hybrid_bond", "edge_couple", "monolithic", "epoxy", "eutectic",
]


class Interface(BaseModel):
    kind: InterfaceKind = "stack"
    pad_count: Optional[int] = None
    pad_pitch: Optional[str] = None      # display string "100 µm" (never fabricate)
    pad_size: Optional[str] = None
    underfill: bool = False


class Part(BaseModel):
    id: str
    name: str
    function: str = "generic"            # parts.py key: laser_gain, waveguide, pic,
                                         #   photodiode, logic_die, submount, mlcc ...
    on: Optional[str] = None             # mounted on this part id (None = base)
    interface: Optional[Interface] = None
    attributes: dict = Field(default_factory=dict)   # {buried,emits,detects,cavity,...}


class Relation(BaseModel):
    type: Literal["optical", "electrical", "mechanical"] = "optical"
    src: str
    dst: str
    via: Optional[str] = None
    label: Optional[str] = None


class Brief(BaseModel):
    genre: Literal["physical", "infographic"] = "physical"
    genre_confidence: float = 1.0
    emphasis: Literal["section", "planar", "auto"] = "auto"
    infographic_kind: Optional[str] = None
    title: str
    caption: Optional[str] = None
    base: Optional[str] = None            # substrate/base part id
    parts: list[Part] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
