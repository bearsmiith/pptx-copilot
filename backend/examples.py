"""Canonical example decks for the target domains.

Serve three purposes: (1) gallery presets in the UI so the user can test
without an LLM, (2) regression fixtures, (3) few-shot material for prompts.
All validated against the DSL at import time.
"""
from __future__ import annotations

from models import Deck

_RAW: dict[str, dict] = {
    "fcbga": {
        "title": "Flip-Chip BGA Package",
        "slides": [
            {
                "layout_type": "figure",
                "title": "FC-BGA Cross-Section",
                "figure": {
                    "kind": "stack",
                    "caption": "Flip-chip BGA: die on organic substrate, not to scale",
                    "rows": [
                        {"type": "layer", "label": "PCB (motherboard)", "material": "pcb", "t": 1.0},
                        {"type": "balls", "label": "BGA solder ball", "material": "solder",
                         "count": 11, "size": "ball", "shape": "flat"},
                        {"type": "layer", "label": "Package substrate", "material": "substrate",
                         "t": 1.1, "vias": {"count": 6, "shape": "straight",
                                            "material": "copper", "label": "Cu via (PTH)"}},
                        {"type": "balls", "label": "Cu pillar µbump", "material": "solder",
                         "count": 14, "size": "bump", "shape": "pillar", "width_frac": 0.55},
                        {"type": "die", "label": "Si Die", "material": "silicon",
                         "t": 1.3, "width_frac": 0.55, "underfill": True},
                        {"type": "layer", "label": "Mold / heat spreader", "material": "mold",
                         "t": 0.7, "width_frac": 0.8},
                    ],
                },
            },
        ],
    },
    "tgv": {
        "title": "TGV Glass Substrate",
        "slides": [
            {
                "layout_type": "figure",
                "title": "Through-Glass Via (TGV) Substrate",
                "figure": {
                    "kind": "stack",
                    "caption": "Glass core with hourglass TGV and RDL both sides",
                    "rows": [
                        {"type": "layer", "label": "Bottom RDL (Cu)", "material": "copper", "t": 0.5},
                        {"type": "layer", "label": "Glass core", "material": "glass", "t": 2.2,
                         "vias": {"count": 5, "shape": "hourglass", "material": "copper",
                                  "label": "TGV (hourglass)"}},
                        {"type": "layer", "label": "Top RDL (Cu)", "material": "copper", "t": 0.5},
                        {"type": "layer", "label": "Dielectric build-up", "material": "dielectric", "t": 0.5},
                        {"type": "balls", "label": "µbump", "material": "solder",
                         "count": 12, "size": "bump", "width_frac": 0.6},
                        {"type": "die", "label": "Chiplet", "material": "silicon",
                         "t": 1.0, "width_frac": 0.5},
                    ],
                },
            },
            {
                "layout_type": "figure",
                "title": "Organic vs Glass Substrate",
                "figure": {
                    "kind": "compare",
                    "panels": [
                        {"title": "Organic (ABF) substrate",
                         "figure": {"kind": "stack", "rows": [
                             {"type": "layer", "label": "Solder resist", "material": "solder_mask", "t": 0.4},
                             {"type": "layer", "label": "ABF build-up", "material": "dielectric", "t": 1.0},
                             {"type": "layer", "label": "Organic core", "material": "substrate", "t": 1.6,
                              "vias": {"count": 4, "shape": "straight", "material": "copper"}},
                             {"type": "layer", "label": "ABF build-up", "material": "dielectric", "t": 1.0},
                         ]}},
                        {"title": "Glass (TGV) substrate",
                         "figure": {"kind": "stack", "rows": [
                             {"type": "layer", "label": "RDL", "material": "copper", "t": 0.5},
                             {"type": "layer", "label": "Glass core", "material": "glass", "t": 2.0,
                              "vias": {"count": 4, "shape": "hourglass", "material": "copper"}},
                             {"type": "layer", "label": "RDL", "material": "copper", "t": 0.5},
                         ]}},
                    ],
                    "caption": "Glass: better flatness, lower loss, finer L/S",
                },
            },
        ],
    },
    "smt": {
        "title": "SMT Assembly",
        "slides": [
            {
                "layout_type": "figure",
                "title": "SMT Reflow Process",
                "figure": {
                    "kind": "flow",
                    "caption": "Surface-mount assembly line",
                    "nodes": [
                        {"id": "n1", "label": "Solder paste printing"},
                        {"id": "n2", "label": "SPI"},
                        {"id": "n3", "label": "Pick & place"},
                        {"id": "n4", "label": "Reflow"},
                        {"id": "n5", "label": "AOI"},
                    ],
                    "edges": [
                        {"src": "n1", "dst": "n2"}, {"src": "n2", "dst": "n3"},
                        {"src": "n3", "dst": "n4"}, {"src": "n4", "dst": "n5"},
                    ],
                },
            },
            {
                "layout_type": "figure",
                "title": "Chip Component Solder Joint",
                "figure": {
                    "kind": "stack",
                    "caption": "0402/0603 chip on PCB pad after reflow",
                    "rows": [
                        {"type": "layer", "label": "FR-4 PCB", "material": "pcb", "t": 1.4},
                        {"type": "layer", "label": "Cu pad + solder fillet", "material": "solder",
                         "t": 0.5, "width_frac": 0.75},
                        {"type": "die", "label": "Chip component (MLCC)", "material": "gray",
                         "t": 1.1, "width_frac": 0.5},
                    ],
                },
            },
        ],
    },
    "tft": {
        "title": "TFT Backplane",
        "slides": [
            {
                "layout_type": "figure",
                "title": "Bottom-Gate a-Si TFT Stack",
                "figure": {
                    "kind": "stack",
                    "caption": "Inverted-staggered TFT, layers not to scale",
                    "rows": [
                        {"type": "layer", "label": "Glass substrate", "material": "glass", "t": 1.6},
                        {"type": "layer", "label": "Gate metal (Mo/Al)", "material": "metal",
                         "t": 0.5, "width_frac": 0.4},
                        {"type": "layer", "label": "Gate insulator (SiNx)", "material": "nitride", "t": 0.6},
                        {"type": "layer", "label": "a-Si:H channel", "material": "semiconductor",
                         "t": 0.5, "width_frac": 0.5},
                        {"type": "layer", "label": "Source / Drain (Mo)", "material": "metal",
                         "t": 0.5, "width_frac": 0.8},
                        {"type": "layer", "label": "Passivation (SiNx)", "material": "passivation", "t": 0.55},
                        {"type": "layer", "label": "Pixel electrode (ITO)", "material": "ito",
                         "t": 0.4, "width_frac": 0.6},
                    ],
                },
            },
        ],
    },
    "microled": {
        "title": "Micro LED",
        "slides": [
            {
                "layout_type": "figure",
                "title": "Micro LED Chip Structure",
                "figure": {
                    "kind": "stack",
                    "caption": "GaN µLED on sapphire (before transfer), <50 µm chip",
                    "rows": [
                        {"type": "layer", "label": "Sapphire substrate", "material": "glass", "t": 1.6},
                        {"type": "layer", "label": "n-GaN", "material": "n_gan", "t": 1.0},
                        {"type": "layer", "label": "MQW active region", "material": "mqw",
                         "t": 0.45, "width_frac": 0.85},
                        {"type": "layer", "label": "p-GaN", "material": "p_gan",
                         "t": 0.6, "width_frac": 0.85},
                        {"type": "layer", "label": "p-electrode (ITO)", "material": "ito",
                         "t": 0.4, "width_frac": 0.6},
                    ],
                },
            },
            {
                "layout_type": "figure",
                "title": "Mass Transfer to Backplane",
                "figure": {
                    "kind": "flow",
                    "nodes": [
                        {"id": "n1", "label": "Epi growth on sapphire"},
                        {"id": "n2", "label": "Chip singulation"},
                        {"id": "n3", "label": "Laser lift-off"},
                        {"id": "n4", "label": "Mass transfer (stamp)"},
                        {"id": "n5", "label": "Bond to TFT backplane"},
                    ],
                    "edges": [
                        {"src": "n1", "dst": "n2"}, {"src": "n2", "dst": "n3"},
                        {"src": "n3", "dst": "n4"}, {"src": "n4", "dst": "n5"},
                    ],
                },
            },
        ],
    },
    "miniled": {
        "title": "Mini LED Backlight",
        "slides": [
            {
                "layout_type": "figure",
                "title": "Mini LED BLU + LCD Stack",
                "figure": {
                    "kind": "stack",
                    "caption": "Direct-lit mini LED backlight with QD film",
                    "rows": [
                        {"type": "layer", "label": "BLU PCB", "material": "pcb", "t": 0.9},
                        {"type": "chips", "label": "Mini LED (~200 µm)", "material": "led",
                         "count": 16, "t": 0.55},
                        {"type": "layer", "label": "Diffuser plate", "material": "diffuser", "t": 0.8},
                        {"type": "layer", "label": "QD film", "material": "qd", "t": 0.5},
                        {"type": "layer", "label": "Prism / BEF films", "material": "polymer", "t": 0.5},
                        {"type": "layer", "label": "LCD cell", "material": "lcd", "t": 0.9},
                    ],
                },
            },
            {
                "layout_type": "figure",
                "title": "Local Dimming Zones",
                "figure": {
                    "kind": "array",
                    "rows": 4, "cols": 10,
                    "cell_label": "Dimming zone (LED cluster)",
                    "material": "led",
                    "caption": "Thousands of zones enable HDR local dimming",
                },
            },
        ],
    },
    "cowos": {
        "title": "CoWoS 2.5D Packaging",
        "slides": [
            {
                "layout_type": "figure",
                "title": "CoWoS-S Cross-Section",
                "figure": {
                    "kind": "stack",
                    "caption": "SoC + HBM on silicon interposer, 3-tier interconnect (not to scale)",
                    "rows": [
                        {"type": "layer", "label": "Package substrate (ABF)", "material": "substrate",
                         "t": 1.2, "vias": {"count": 6, "shape": "straight",
                                            "material": "copper", "label": "Substrate via"}},
                        {"type": "balls", "label": "C4 bump (~130 µm)", "material": "solder",
                         "count": 12, "size": "ball", "shape": "barrel", "width_frac": 0.8},
                        {"type": "layer", "label": "Si interposer (~100 µm)", "material": "silicon",
                         "t": 0.8, "width_frac": 0.8,
                         "vias": {"count": 12, "shape": "straight",
                                  "material": "copper", "label": "TSV"}},
                        {"type": "balls", "label": "µbump (Cu pillar, ~45 µm)", "material": "solder",
                         "count": 18, "size": "bump", "shape": "pillar", "width_frac": 0.72},
                        {"type": "dies", "t": 1.2, "items": [
                            {"label": "HBM", "material": "silicon", "width_frac": 0.16},
                            {"label": "SoC (GPU)", "material": "silicon", "width_frac": 0.3},
                            {"label": "HBM", "material": "silicon", "width_frac": 0.16},
                        ]},
                        {"type": "layer", "label": "Mold + lid", "material": "mold",
                         "t": 0.6, "width_frac": 0.85},
                    ],
                },
            },
        ],
    },
    "emib": {
        "title": "Intel EMIB",
        "slides": [
            {
                "layout_type": "figure",
                "title": "EMIB: Embedded Bridge Interconnect",
                "figure": {
                    "kind": "stack",
                    "caption": "Silicon bridge embedded in substrate top build-up — no full interposer",
                    "rows": [
                        {"type": "layer", "label": "Substrate core", "material": "substrate",
                         "t": 1.3, "vias": {"count": 5, "shape": "straight",
                                            "material": "copper", "label": "PTH"}},
                        {"type": "layer", "label": "Top build-up layers", "material": "dielectric",
                         "t": 1.1, "embeds": [
                             {"label": "EMIB bridge (Si)", "material": "silicon",
                              "width_frac": 0.3, "align": "center", "position": "top"}]},
                        {"type": "balls", "label": "µbump / C4", "material": "solder",
                         "count": 16, "size": "bump", "width_frac": 0.85},
                        {"type": "dies", "t": 1.3, "items": [
                            {"label": "Die 1 (CPU)", "material": "silicon",
                             "width_frac": 0.34, "underfill": True},
                            {"label": "Die 2 (I/O)", "material": "silicon",
                             "width_frac": 0.34, "underfill": True},
                        ]},
                    ],
                },
            },
        ],
    },
    "pcb": {
        "title": "PCB Stackup",
        "slides": [
            {
                "layout_type": "figure",
                "title": "6-Layer PCB Stackup",
                "figure": {
                    "kind": "stack",
                    "caption": "Signal/plane alternation with through + blind vias",
                    "rows": [
                        {"type": "layer", "label": "L6 Cu (bottom)", "material": "copper", "t": 0.35},
                        {"type": "layer", "label": "Prepreg", "material": "prepreg", "t": 0.5},
                        {"type": "layer", "label": "L5 Cu (GND)", "material": "copper", "t": 0.35},
                        {"type": "layer", "label": "Core (FR-4)", "material": "pcb", "t": 0.9,
                         "vias": {"count": 3, "shape": "straight", "material": "copper",
                                  "label": "Buried via"}},
                        {"type": "layer", "label": "L2 Cu (PWR)", "material": "copper", "t": 0.35},
                        {"type": "layer", "label": "Prepreg", "material": "prepreg", "t": 0.5},
                        {"type": "layer", "label": "L1 Cu (top, signal)", "material": "copper", "t": 0.35},
                        {"type": "layer", "label": "Solder mask", "material": "solder_mask", "t": 0.25},
                    ],
                },
            },
        ],
    },
}

EXAMPLES: dict[str, Deck] = {k: Deck.model_validate(v) for k, v in _RAW.items()}

# WP1: new advanced-packaging/display structures are single-sourced in domain.py
from domain import build_deck as _build_deck, STRUCTURES as _STRUCTURES  # noqa: E402

_DOMAIN_PRESETS = [
    ("fanout_info", "Fan-Out (InFO)"),
    ("hybrid_bond_soic", "하이브리드 본딩 (SoIC)"),
    ("hbm", "HBM 적층 (diestack)"),
    ("backside_power", "백사이드 파워 (PowerVia)"),
    ("glass_core_detailed", "글라스 코어 (상세 TGV)"),
    ("qfn_wirebond", "와이어본드 QFN"),
    ("pop", "PoP 패키지"),
    ("oled", "OLED 디스플레이 스택"),
]
for _name, _ in _DOMAIN_PRESETS:
    EXAMPLES[_name] = _build_deck(_name)

# WP7: general-infographic archetypes single-sourced in archetypes.py
from archetypes import ARCHETYPES as _ARCH, build_archetype as _build_arch  # noqa: E402
from models import Deck as _Deck  # noqa: E402

_ARCH_PRESETS = [
    ("timeline", "타임라인 / 로드맵"),
    ("kpi", "KPI 지표 카드"),
    ("table", "비교표 / 사양표"),
    ("matrix", "2×2 매트릭스"),
    ("chart", "막대/라인 차트"),
    ("tree", "계층 구성도"),
]
for _name, _ in _ARCH_PRESETS:
    _sl = _build_arch(_name)
    EXAMPLES[_name] = _Deck(title=_sl.title, slides=[_sl])

EXAMPLE_META = [
    ("fcbga", "FC-BGA 패키지 단면"),
    ("tgv", "TGV 글라스 기판 (+비교)"),
    ("smt", "SMT 공정 + 솔더 조인트"),
    ("tft", "TFT 레이어 스택"),
    ("microled", "Micro LED 구조 + 전사"),
    ("miniled", "Mini LED BLU + 디밍 어레이"),
    ("cowos", "CoWoS 2.5D (병렬 다이)"),
    ("emib", "EMIB (임베디드 브리지)"),
    ("pcb", "6층 PCB 스택업"),
] + _DOMAIN_PRESETS + _ARCH_PRESETS
