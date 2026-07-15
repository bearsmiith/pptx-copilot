"""LLM output schema (Deck / figure DSL v2).

Design principle: the LLM produces *meaning only* — no coordinates, no colors.
A deterministic layout engine (layout.py) turns this into positioned geometry
consumed by both the SVG renderer and the pptx exporter, and palette.py maps
semantic `material` roles to colors.

Figure kinds:
  flow    — process steps as a chain of nodes + arrows
  stack   — cross-section layer stack, bottom-to-top row list (dies, bumps,
            balls, vias, chip arrays). The workhorse for packaging/substrate/
            display tech. Linear list = easy for a small LLM (no cross refs).
  compare — 2-3 side-by-side panels, each holding a nested stack/flow/bullets
  array   — simple rows x cols grid of cells (LED matrix etc)
"""
from __future__ import annotations

from typing import Literal, Optional, Union
from pydantic import BaseModel, Field


# ---------------- flow ----------------

class FlowNode(BaseModel):
    id: str = Field(description="short unique id, e.g. 'n1'")
    label: str = Field(description="text shown in the box")


class FlowEdge(BaseModel):
    src: str
    dst: str
    label: Optional[str] = None


class FlowFigure(BaseModel):
    kind: Literal["flow"] = "flow"
    caption: Optional[str] = None
    nodes: list[FlowNode] = Field(default_factory=list)
    edges: list[FlowEdge] = Field(default_factory=list)


# ---------------- stack ----------------

class Vias(BaseModel):
    """Vias drilled through the layer they are attached to."""
    count: int = Field(default=3, ge=1, le=12)
    shape: Literal["straight", "tapered", "hourglass"] = "straight"
    material: str = Field(default="copper")
    label: Optional[str] = None


class Embed(BaseModel):
    """A block buried INSIDE a layer (e.g. EMIB bridge die embedded in the
    substrate's top build-up, an embedded passive)."""
    label: str
    material: str = "silicon"
    width_frac: float = Field(default=0.25, ge=0.05, le=0.9,
                              description="fraction of the layer width")
    align: Literal["left", "center", "right"] = "center"
    position: Literal["top", "middle", "bottom"] = Field(
        default="top", description="vertical placement inside the layer")


class LayerRow(BaseModel):
    """A full-width horizontal layer (substrate, film, mold, glass core...)."""
    type: Literal["layer"] = "layer"
    label: str
    material: str = Field(description="semantic material role, e.g. silicon, copper, glass, dielectric, pcb, mold")
    t: float = Field(default=1.0, ge=0.2, le=4.0, description="relative thickness weight")
    width_frac: float = Field(default=1.0, ge=0.1, le=1.0, description="fraction of stack width (centered)")
    vias: Optional[Vias] = None
    embeds: Optional[list[Embed]] = Field(
        default=None, max_length=3,
        description="blocks embedded inside this layer (e.g. EMIB bridge)")


class DieRow(BaseModel):
    """A single die / chip block sitting on the stack."""
    type: Literal["die"] = "die"
    label: str
    material: str = "silicon"
    t: float = Field(default=1.2, ge=0.4, le=3.0)
    width_frac: float = Field(default=0.55, ge=0.15, le=0.95)
    align: Literal["left", "center", "right"] = "center"
    underfill: bool = Field(default=False, description="draw underfill fillets at the die edges")
    wirebond: bool = Field(default=False, description="draw wire-bond arcs from the die top to the row below (QFN/leadframe, legacy)")


class DieSpec(BaseModel):
    label: str
    material: str = "silicon"
    width_frac: float = Field(default=0.28, ge=0.05, le=0.9,
                              description="fraction of stack width")
    underfill: bool = False


class DiesRow(BaseModel):
    """Two or more dies SIDE BY SIDE in one row (SoC + HBM, chiplets,
    Die1 + Die2 over an EMIB bridge)."""
    type: Literal["dies"] = "dies"
    items: list[DieSpec] = Field(min_length=2, max_length=4)
    t: float = Field(default=1.2, ge=0.4, le=3.0)


class BallsRow(BaseModel):
    """A row of solder balls / bumps. `shape` follows industry drawing
    conventions: round(generic), flat(post-reflow BGA ball, truncated),
    barrel(C4 joint with concave waist), pillar(Cu pillar + solder cap),
    dome(hemisphere — bump-on-pad, encapsulation lens)."""
    type: Literal["balls"] = "balls"
    label: str
    material: str = "solder"
    count: int = Field(default=8, ge=2, le=24)
    size: Literal["ball", "bump"] = "ball"
    shape: Literal["round", "flat", "barrel", "pillar", "dome"] = "round"
    width_frac: float = Field(default=1.0, ge=0.1, le=1.0)


class ChipsRow(BaseModel):
    """A row of small rectangular chips (mini LED array, passives...)."""
    type: Literal["chips"] = "chips"
    label: str
    material: str = "led"
    count: int = Field(default=10, ge=2, le=40)
    t: float = Field(default=0.6, ge=0.2, le=1.5)
    width_frac: float = Field(default=1.0, ge=0.1, le=1.0)


class BondRow(BaseModel):
    """Bumpless Cu-Cu / fusion bond interface between two dies (SoIC, Foveros
    Direct). Rendered as a thin dielectric band with a bond line + fine Cu pad
    columns — NOT solder balls."""
    type: Literal["bond"] = "bond"
    label: str = "Hybrid bond (Cu-Cu)"
    style: Literal["hybrid", "fusion"] = "hybrid"
    material: str = "bond_oxide"       # SiCN/SiO interface
    pad_material: str = "copper"
    count: int = Field(default=10, ge=2, le=32, description="Cu pad columns")
    width_frac: float = Field(default=0.9, ge=0.1, le=1.0)


class DieStackRow(BaseModel):
    """N identical dies stacked vertically (HBM DRAM cube, 3D logic stack). The
    engine repeats the die band `count` times with the chosen joint between
    layers — one compact row instead of 2N hand-written rows (small-model safe)."""
    type: Literal["diestack"] = "diestack"
    label: str                         # e.g. "DRAM die"
    count: int = Field(default=8, ge=2, le=16)
    material: str = "silicon"
    joint: Literal["ubump", "hybrid", "none"] = "ubump"
    width_frac: float = Field(default=0.7, ge=0.15, le=0.95)
    tsv: bool = Field(default=True, description="draw TSV columns through the stack")
    t_each: float = Field(default=0.5, ge=0.2, le=1.5)


StackRow = Union[LayerRow, DieRow, DiesRow, BallsRow, ChipsRow, BondRow, DieStackRow]


class StackFigure(BaseModel):
    kind: Literal["stack"] = "stack"
    caption: Optional[str] = None
    rows: list[StackRow] = Field(
        description="cross-section rows in BOTTOM-TO-TOP order", min_length=1
    )


# ---------------- compare ----------------

class ComparePanel(BaseModel):
    title: str
    figure: Optional[Union[StackFigure, FlowFigure]] = None
    items: Optional[list[str]] = Field(default=None, description="bullet items if no figure")


class CompareFigure(BaseModel):
    kind: Literal["compare"] = "compare"
    caption: Optional[str] = None
    panels: list[ComparePanel] = Field(min_length=2, max_length=3)


# ---------------- array ----------------

class ArrayFigure(BaseModel):
    kind: Literal["array"] = "array"
    caption: Optional[str] = None
    rows: int = Field(default=3, ge=1, le=12)
    cols: int = Field(default=8, ge=2, le=24)
    cell_label: str = Field(description="what one cell is, e.g. 'Mini LED chip'")
    material: str = "led"


# ---------------- photonic (planar / in-plane optical path) ----------------

class PhotonicComponent(BaseModel):
    """A part mounted side-by-side on the substrate surface (left-to-right)."""
    role: Literal["laser", "chip", "passive", "photodiode",
                  "modulator", "generic"] = "generic"
    label: str
    width_frac: float = Field(default=1.0, gt=0, le=4,
                              description="relative footprint width")
    emits: bool = Field(default=False,
                        description="laser facet launches light into the waveguide")
    detects: bool = Field(default=False,
                         description="receives light from the waveguide (photodiode)")


# roles that are ELECTRONIC (placed in the lower band, driven electrically)
PhotonicRole = Literal[
    "laser", "fiber", "grating_coupler", "edge_coupler", "splitter",
    "combiner", "mzm", "ring_mod", "modulator", "mux", "demux",
    "photodiode", "tia", "driver", "eic", "heater", "chip", "passive", "generic",
]


class PhotonicNode(BaseModel):
    """One element in the optical/electronic network (graph form)."""
    id: str
    role: PhotonicRole = "generic"
    label: str


class PhotonicLink(BaseModel):
    """A connection between two nodes. 'optical' = a waveguide carrying light
    (drawn as a light rail with a direction arrow); 'electrical' = a wire/driver
    connection (drawn blue). Direction is src -> dst."""
    src: str
    dst: str
    kind: Literal["optical", "electrical"] = "optical"


class PhotonicFigure(BaseModel):
    """Planar photonic integration. Use this — not `stack` — when the story is a
    horizontal optical path, not a vertical layer build-up. TWO forms:

    - LINEAR (`components`): parts in a row joined by one straight waveguide
      (laser -> waveguide -> photodiode). Simplest case.
    - GRAPH (`nodes` + `links`): an optical NETWORK that branches, taps rings,
      merges, or has fiber I/O and driving electronics — silicon-photonics
      transceivers, WDM (de)mux trees, ring-modulator buses, co-packaged optics.
      Prefer this whenever the topology is more than a single straight line.
    """
    kind: Literal["photonic"] = "photonic"
    caption: Optional[str] = None
    substrate: str = "glass"
    substrate_label: str = "Glass substrate (Cu routing & pads)"
    routing: bool = Field(default=True,
                          description="draw a Cu routing/pad skin on the substrate top")
    waveguide_material: str = "polymer"
    waveguide_label: str = "Polymer waveguide"
    waveguide_placement: Literal["surface", "inline"] = Field(
        default="surface",
        description="LINEAR form only. 'surface' = waveguide is a buried strip "
                    "UNDER the parts; 'inline' = at the SAME level as the parts")
    components: list[PhotonicComponent] = Field(
        default_factory=list, description="LINEAR form: mounted parts, left-to-right")
    nodes: list[PhotonicNode] = Field(
        default_factory=list, description="GRAPH form: optical/electronic elements")
    links: list[PhotonicLink] = Field(
        default_factory=list, description="GRAPH form: connections between nodes")
    optical_label: Optional[str] = "optical path (λ)"


# ================ general infographic kinds (WP7) ================
# Engineering-report figures. No coordinates/colors/physical dimensions —
# geometry is owned by layout.py, colors by semantic roles in palette.py.

# ---------------- timeline (roadmap / history / schedule) ----------------

class Milestone(BaseModel):
    label: str
    date_label: Optional[str] = None      # "2026 Q3" — display string, not a number
    note: Optional[str] = None
    emphasis: bool = False


class TimelinePhase(BaseModel):           # gantt-lite: a bar spanning milestones
    label: str
    start: int = Field(ge=0, description="milestone index")
    end: int = Field(ge=0, description="milestone index")


class TimelineFigure(BaseModel):
    kind: Literal["timeline"] = "timeline"
    caption: Optional[str] = None
    milestones: list[Milestone] = Field(min_length=3, max_length=8)
    phases: list[TimelinePhase] = Field(default_factory=list, max_length=4)


# ---------------- kpi (metric cards) ----------------

class KpiItem(BaseModel):
    value: str                            # "99.2%", "1.2 TB/s" — string w/ unit
    label: str
    delta: Optional[str] = None           # "+0.8%p"
    tone: Literal["good", "bad", "neutral"] = "neutral"


class KpiFigure(BaseModel):
    kind: Literal["kpi"] = "kpi"
    caption: Optional[str] = None
    items: list[KpiItem] = Field(min_length=2, max_length=6)


# ---------------- table (spec / parameter comparison) ----------------

class TableFigure(BaseModel):
    kind: Literal["table"] = "table"
    caption: Optional[str] = None
    columns: list[str] = Field(min_length=2, max_length=6)   # first = row-label header
    rows: list[list[str]] = Field(min_length=1, max_length=8)
    emphasis_col: Optional[int] = None    # highlighted column (e.g. our/recommended)


# ---------------- matrix (2x2 positioning) ----------------

class Quadrant(BaseModel):
    title: str
    items: list[str] = Field(default_factory=list, max_length=4)


class MatrixFigure(BaseModel):
    kind: Literal["matrix"] = "matrix"
    caption: Optional[str] = None
    x_low: str
    x_high: str
    y_low: str
    y_high: str
    # fixed order: [top_left, top_right, bottom_left, bottom_right]
    quadrants: list[Quadrant] = Field(min_length=4, max_length=4)


# ---------------- chart (bar / line, only with real data) ----------------

class ChartSeries(BaseModel):
    name: str
    values: list[float] = Field(min_length=2, max_length=8)


class ChartFigure(BaseModel):
    kind: Literal["chart"] = "chart"
    chart_type: Literal["bar", "line"] = "bar"
    caption: Optional[str] = None
    categories: list[str] = Field(min_length=2, max_length=8)
    series: list[ChartSeries] = Field(min_length=1, max_length=3)
    y_label: Optional[str] = None


# ---------------- tree (system decomposition / org / BOM) ----------------

class TreeNode(BaseModel):
    id: str
    label: str
    parent: Optional[str] = None          # None = root (exactly 1); depth <= 3


class TreeFigure(BaseModel):
    kind: Literal["tree"] = "tree"
    caption: Optional[str] = None
    nodes: list[TreeNode] = Field(min_length=2, max_length=15)


# ================ assembly (WP8 — unified physical scene) ================
# Parts placed on a substrate at (level, x): a cross-section where a small part
# can sit at a position ON TOP of a wider die that continues past it
# (chip-on-chip, laser-on-PIC), with an explicit mounting interface per part.
# The vertical layer stack is the special case where parts share the same x.

MountKind = Literal["none", "stack", "die_attach", "solder", "c4", "cu_pillar",
                    "flipchip", "wirebond", "hybrid", "edge_couple"]


class AssemblyPart(BaseModel):
    id: str
    label: str
    material: str = "silicon"
    level: int = Field(default=1, ge=0, le=4,
                       description="0 = base/substrate; 1 = mounted on base; 2 = on a level-1 part")
    side: Literal["top", "bottom"] = Field(
        default="top", description="'bottom' hangs the part under the substrate (double-sided)")
    on: Optional[str] = Field(default=None,
                              description="parent part id it is mounted on (None = base)")
    x_frac: float = Field(default=0.5, ge=0.0, le=1.0,
                          description="center x as a fraction of the BASE width")
    width_frac: float = Field(default=0.3, gt=0.0, le=1.0,
                              description="width as a fraction of the BASE width")
    t: float = Field(default=1.0, gt=0.0, le=4.0, description="relative height")
    mount: MountKind = "stack"
    pad_count: int = Field(default=6, ge=1, le=24)
    emits: bool = False        # optical source facet (laser)
    detects: bool = False      # optical receiver (photodiode)
    buried: bool = False       # drawn as a channel INSIDE the base (waveguide-in-substrate)


class AssemblyBeam(BaseModel):
    """In-plane optical path drawn as a horizontal beam at the source's height."""
    src: str
    dst: str
    label: Optional[str] = None


class AssemblyBaseLayer(BaseModel):
    """One internal layer of a multilayer substrate (bottom-to-top)."""
    label: str
    material: str = "dielectric"
    t: float = Field(default=1.0, gt=0.0, le=4.0)
    vias: int = Field(default=0, ge=0, le=16, description="through-vias in this layer")


class AssemblyFigure(BaseModel):
    kind: Literal["assembly"] = "assembly"
    caption: Optional[str] = None
    base_label: str = "Substrate"
    base_material: str = "substrate"
    base_layers: list[AssemblyBaseLayer] = Field(
        default_factory=list, description="multilayer substrate build-up (bottom-to-top); "
                                          "empty = a solid slab")
    parts: list[AssemblyPart] = Field(min_length=1)
    beams: list[AssemblyBeam] = Field(default_factory=list)
    mold: bool = Field(default=False, description="encapsulate the top parts in EMC")
    mold_label: str = "Mold (EMC)"
    bottom_balls: Optional[int] = Field(
        default=None, description="row of package balls (BGA/LGA) UNDER the substrate")
    bottom_ball_label: Optional[str] = None


Figure = Union[
    FlowFigure, StackFigure, CompareFigure, ArrayFigure, PhotonicFigure,
    TimelineFigure, KpiFigure, TableFigure, MatrixFigure, ChartFigure, TreeFigure,
    AssemblyFigure,
]


# ---------------- deck ----------------

class Slide(BaseModel):
    layout_type: Literal["title", "content", "figure"]
    title: str
    subtitle: Optional[str] = Field(default=None, description="only for layout_type='title'")
    bullets: Optional[list[str]] = Field(default=None, description="for layout_type='content'")
    figure: Optional[Figure] = Field(default=None, description="required for layout_type='figure'")


class Deck(BaseModel):
    title: str
    slides: list[Slide]


# ---------------- staged workflow: plan ----------------

class PlanSlide(BaseModel):
    layout_type: Literal["title", "content", "figure"]
    title: str
    subtitle: Optional[str] = None
    bullets: Optional[list[str]] = None
    figure_plan: Optional[str] = Field(
        default=None,
        description="figure slides: prose description of what the diagram will show")


class DeckPlan(BaseModel):
    title: str
    slides: list[PlanSlide]
    questions: list[str] = Field(default_factory=list,
                                 description="clarifying questions to the user")


# ---------------- single-slide image+text layout ----------------

class SlideImage(BaseModel):
    ref: int = Field(description="0-based index into the attached images")
    caption: Optional[str] = None


class SlideLayout(BaseModel):
    """A single slide composing attached images + text. The LLM picks a
    template and fills slots; the engine computes all geometry."""
    template: Literal[
        "image_left_text_right",
        "image_right_text_left",
        "image_top_text_bottom",
        "text_top_image_bottom",
        "two_images",
        "hero_title",
        "image_grid",
        "text_only",
    ]
    title: str
    subtitle: Optional[str] = None
    bullets: Optional[list[str]] = None
    images: list[SlideImage] = Field(default_factory=list)
    caption: Optional[str] = None
