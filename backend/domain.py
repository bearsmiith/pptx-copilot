"""Single source of structure knowledge (WP1 §5).

Cross-section recipes as plain Python data so prompts, examples, templates
(WP3) and the linter (WP3) all reference the SAME knowledge — no string
duplication or drift. Each recipe is bottom-to-top `rows` (StackFigure DSL),
plus metadata (aka names, caption, must_label, rules) used by search/lint.
"""
from __future__ import annotations

from models import Deck, Slide, StackFigure, PhotonicFigure


STRUCTURES: dict[str, dict] = {
    # ---- advanced packaging (new) ----
    "fanout_info": {
        "aka": ["InFO", "FOWLP", "integrated fan-out", "fan-out", "팬아웃"],
        "title": "Integrated Fan-Out (InFO)",
        "caption": "Integrated fan-out (InFO): die-first, RDL, no Si substrate",
        "must_label": ["RDL", "EMC", "solder ball"],
        "rules": ["no substrate row", "die width_frac 0.4-0.6", "mold width_frac 1.0"],
        "rows": [
            {"type": "balls", "label": "Solder ball", "material": "solder",
             "count": 10, "size": "ball", "shape": "flat"},
            {"type": "layer", "label": "RDL L2 (Cu)", "material": "rdl", "t": 0.35},
            {"type": "layer", "label": "RDL dielectric", "material": "dielectric", "t": 0.4},
            {"type": "layer", "label": "RDL L1 (Cu)", "material": "rdl", "t": 0.35},
            {"type": "die", "label": "Die (face-down)", "material": "silicon",
             "t": 1.2, "width_frac": 0.5},
            {"type": "layer", "label": "EMC mold", "material": "emc", "t": 0.6,
             "width_frac": 1.0},
        ],
    },
    "hybrid_bond_soic": {
        "aka": ["SoIC", "Foveros Direct", "hybrid bond", "Cu-Cu", "bumpless", "하이브리드 본딩"],
        "title": "Hybrid Bonding (SoIC)",
        "caption": "Bumpless Cu-Cu hybrid bond, <10 µm pitch",
        "must_label": ["hybrid bond"],
        "rules": ["use bond row not balls between dies"],
        "rows": [
            {"type": "die", "label": "Bottom die (logic)", "material": "silicon",
             "t": 1.3, "width_frac": 0.7},
            {"type": "bond", "label": "Hybrid bond (Cu-Cu)", "style": "hybrid",
             "count": 12, "width_frac": 0.7},
            {"type": "die", "label": "Top die (cache/SRAM)", "material": "silicon",
             "t": 1.3, "width_frac": 0.7},
        ],
    },
    "hbm": {
        "aka": ["HBM", "high bandwidth memory", "DRAM stack", "8-Hi", "12-Hi"],
        "title": "HBM Stack",
        "caption": "8-Hi HBM: base logic die + DRAM via TSV / µbump",
        "must_label": ["base logic", "DRAM", "TSV"],
        "rules": ["base logic die at bottom with TSV", "use diestack for DRAM"],
        "rows": [
            {"type": "layer", "label": "Base logic die (PHY)", "material": "silicon",
             "t": 1.1, "vias": {"count": 6, "shape": "straight", "material": "copper",
                                "label": "TSV"}},
            {"type": "diestack", "label": "DRAM die", "count": 8, "joint": "ubump",
             "width_frac": 0.72, "tsv": True, "t_each": 0.5},
            {"type": "layer", "label": "EMC", "material": "emc", "t": 0.4,
             "width_frac": 0.85},
        ],
    },
    "backside_power": {
        "aka": ["backside power", "BSPDN", "PowerVia", "super power rail", "백사이드 파워"],
        "title": "Backside Power Delivery",
        "caption": "Backside power delivery: power on back, signal on front",
        "must_label": ["nano-TSV", "device", "signal"],
        "rules": ["backside metal at bottom", "device layer in middle"],
        "rows": [
            {"type": "layer", "label": "Backside power metal", "material": "copper", "t": 0.5},
            {"type": "layer", "label": "Backside PDN + nano-TSV", "material": "dielectric",
             "t": 0.6, "vias": {"count": 5, "shape": "straight", "material": "copper",
                                "label": "nano-TSV"}},
            {"type": "layer", "label": "Transistor / nanosheet device", "material": "device",
             "t": 0.7, "width_frac": 0.9},
            {"type": "layer", "label": "Frontside signal M1-M2", "material": "metal", "t": 0.4},
            {"type": "layer", "label": "Frontside signal BEOL", "material": "dielectric", "t": 0.5},
        ],
    },
    "glass_core_detailed": {
        "aka": ["glass core", "glass substrate", "TGV detailed", "글라스 코어"],
        "title": "Glass Core Substrate (TGV)",
        "caption": "Glass-core substrate with symmetric build-up + hourglass TGV (not to scale)",
        "must_label": ["Glass core", "TGV", "Build-up"],
        "rules": ["symmetric build-up around glass core", "hourglass TGV"],
        "rows": [
            {"type": "layer", "label": "Build-up L4 RDL", "material": "copper", "t": 0.35},
            {"type": "layer", "label": "Build-up L3 dielectric", "material": "dielectric", "t": 0.4},
            {"type": "layer", "label": "Glass core", "material": "glass", "t": 2.2,
             "vias": {"count": 5, "shape": "hourglass", "material": "copper", "label": "TGV ~40µm"}},
            {"type": "layer", "label": "Build-up L2 dielectric", "material": "dielectric", "t": 0.4},
            {"type": "layer", "label": "Build-up L1 RDL", "material": "copper", "t": 0.35},
        ],
    },
    "qfn_wirebond": {
        "aka": ["QFN", "wirebond", "wire bond", "leadframe", "와이어본드"],
        "title": "Wire-Bond QFN Package",
        "caption": "Wire-bond QFN: die on leadframe pad, gold wires to leads",
        "must_label": ["Leadframe", "Wire bond", "EMC"],
        "rules": ["leadframe at bottom", "die wirebond:true", "not flip-chip"],
        "rows": [
            {"type": "layer", "label": "Leadframe / die pad", "material": "leadframe", "t": 0.5},
            {"type": "die", "label": "Silicon die", "material": "silicon",
             "t": 1.2, "width_frac": 0.55, "wirebond": True},
            {"type": "layer", "label": "EMC mold", "material": "emc", "t": 0.7,
             "width_frac": 0.95},
        ],
    },
    "pop": {
        "aka": ["PoP", "package-on-package", "패키지 온 패키지"],
        "title": "Package-on-Package (PoP)",
        "caption": "Bottom logic package + top memory package (PoP)",
        "must_label": ["logic", "memory", "PoP"],
        "rules": ["two stacked packages joined by PoP solder"],
        "rows": [
            {"type": "layer", "label": "PCB", "material": "pcb", "t": 0.9},
            {"type": "balls", "label": "BGA ball", "material": "solder", "count": 11,
             "size": "ball", "shape": "flat"},
            {"type": "layer", "label": "Bottom substrate", "material": "substrate", "t": 0.7,
             "vias": {"count": 5, "shape": "straight", "material": "copper"}},
            {"type": "die", "label": "Logic die (flip-chip)", "material": "silicon",
             "t": 1.0, "width_frac": 0.55, "underfill": True},
            {"type": "balls", "label": "PoP solder", "material": "solder", "count": 9,
             "size": "ball", "shape": "round", "width_frac": 0.9},
            {"type": "layer", "label": "Top substrate", "material": "substrate", "t": 0.6},
            {"type": "die", "label": "Memory die", "material": "silicon",
             "t": 0.9, "width_frac": 0.7},
            {"type": "layer", "label": "Top mold", "material": "mold", "t": 0.5,
             "width_frac": 0.85},
        ],
    },
    "oled": {
        "aka": ["OLED", "organic LED", "유기 발광", "top emission"],
        "title": "OLED Display Stack",
        "caption": "Top-emission OLED + thin-film encapsulation (TFE)",
        "must_label": ["Emission", "Cathode", "Anode", "TFE"],
        "rules": ["emission layer between HTL and ETL"],
        "rows": [
            {"type": "layer", "label": "TFT backplane", "material": "device", "t": 0.7},
            {"type": "layer", "label": "Anode (ITO)", "material": "ito", "t": 0.35, "width_frac": 0.6},
            {"type": "layer", "label": "HIL / HTL", "material": "organic", "t": 0.3},
            {"type": "layer", "label": "Emission layer (EML)", "material": "emission",
             "t": 0.4, "width_frac": 0.55},
            {"type": "layer", "label": "ETL / EIL", "material": "organic", "t": 0.3},
            {"type": "layer", "label": "Cathode (Mg:Ag)", "material": "metal", "t": 0.3},
            {"type": "layer", "label": "Thin-film encapsulation (TFE)", "material": "passivation", "t": 0.4},
        ],
    },
}


# ---- photonic structures (GRAPH form: optical network, not a layer stack) ----

PHOTONIC_STRUCTURES: dict[str, dict] = {
    "silicon_photonics_tx": {
        "aka": ["silicon photonics", "실리콘 포토닉스", "siph", "photonic transmitter",
                "optical transmitter", "wdm transmitter", "co-packaged optics",
                "cpo", "포토닉스 송신", "광 송신"],
        "title": "Silicon Photonics WDM Transmitter",
        "caption": "Laser split into per-λ MZM modulators (driven by the EIC), "
                   "recombined by a WDM MUX, coupled to fiber via a grating coupler.",
        "substrate": "silicon",
        "substrate_label": "Silicon photonics chip (Si/SiN waveguides)",
        "waveguide_material": "optical",
        "must_label": ["laser", "modulator", "MUX", "grating coupler", "fiber"],
        "rules": ["laser is the optical source", "modulators driven by driver/EIC"],
        "nodes": [
            {"id": "laser", "role": "laser", "label": "DFB Laser"},
            {"id": "split", "role": "splitter", "label": "1×2 Splitter"},
            {"id": "mzm1", "role": "mzm", "label": "MZM λ1"},
            {"id": "mzm2", "role": "mzm", "label": "MZM λ2"},
            {"id": "mux", "role": "mux", "label": "WDM MUX"},
            {"id": "gc", "role": "grating_coupler", "label": "Grating coupler"},
            {"id": "fiber", "role": "fiber", "label": "SMF fiber"},
            {"id": "drv1", "role": "driver", "label": "Driver λ1"},
            {"id": "drv2", "role": "driver", "label": "Driver λ2"},
        ],
        "links": [
            {"src": "laser", "dst": "split"}, {"src": "split", "dst": "mzm1"},
            {"src": "split", "dst": "mzm2"}, {"src": "mzm1", "dst": "mux"},
            {"src": "mzm2", "dst": "mux"}, {"src": "mux", "dst": "gc"},
            {"src": "gc", "dst": "fiber"},
            {"src": "drv1", "dst": "mzm1", "kind": "electrical"},
            {"src": "drv2", "dst": "mzm2", "kind": "electrical"},
        ],
    },
    "silicon_photonics_rx": {
        "aka": ["photonic receiver", "optical receiver", "wdm receiver",
                "포토닉스 수신", "광 수신", "ring receiver", "포토닉 수신기"],
        "title": "Silicon Photonics WDM Receiver",
        "caption": "Fiber light is demultiplexed to per-λ Ge photodiodes; "
                   "TIAs amplify the photocurrent.",
        "substrate": "silicon",
        "substrate_label": "Silicon photonics receiver die",
        "must_label": ["grating coupler", "DEMUX", "photodiode", "TIA"],
        "rules": ["photodiode detects light", "TIA amplifies PD current"],
        "nodes": [
            {"id": "fiber", "role": "fiber", "label": "SMF fiber"},
            {"id": "gc", "role": "grating_coupler", "label": "Grating coupler"},
            {"id": "demux", "role": "demux", "label": "WDM DEMUX"},
            {"id": "pd1", "role": "photodiode", "label": "Ge PD λ1"},
            {"id": "pd2", "role": "photodiode", "label": "Ge PD λ2"},
            {"id": "tia1", "role": "tia", "label": "TIA λ1"},
            {"id": "tia2", "role": "tia", "label": "TIA λ2"},
        ],
        "links": [
            {"src": "fiber", "dst": "gc"}, {"src": "gc", "dst": "demux"},
            {"src": "demux", "dst": "pd1"}, {"src": "demux", "dst": "pd2"},
            {"src": "pd1", "dst": "tia1", "kind": "electrical"},
            {"src": "pd2", "dst": "tia2", "kind": "electrical"},
        ],
    },
    "glass_photonic_pic": {
        "aka": ["photonic ic", "photonic glass", "glass photonic", "포토닉 ic",
                "포토닉", "polymer waveguide", "폴리머 도파로", "optical interposer",
                "glass waveguide", "photonic integrated", "포토닉스"],
        "title": "Glass-Substrate Photonic IC",
        "caption": "Laser edge-couples into a polymer waveguide on a glass "
                   "substrate and is received by a photodiode; electronics via Cu RDL.",
        "substrate": "glass",
        "substrate_label": "Glass substrate (Cu RDL & pads)",
        "waveguide_material": "polymer",
        "must_label": ["laser", "waveguide", "photodiode"],
        "rules": ["laser emits into the waveguide", "photodiode receives"],
        "nodes": [
            {"id": "laser", "role": "laser", "label": "Laser diode"},
            {"id": "mod", "role": "modulator", "label": "Modulator"},
            {"id": "pd", "role": "photodiode", "label": "Photodiode"},
            {"id": "drv", "role": "driver", "label": "Laser driver"},
            {"id": "tia", "role": "tia", "label": "TIA"},
        ],
        "links": [
            {"src": "laser", "dst": "mod"}, {"src": "mod", "dst": "pd"},
            {"src": "drv", "dst": "laser", "kind": "electrical"},
            {"src": "pd", "dst": "tia", "kind": "electrical"},
        ],
    },
}


def build_deck(name: str) -> Deck:
    """Deterministically build a single-figure Deck from a structure recipe."""
    if name in PHOTONIC_STRUCTURES:
        slide = build_photonic(name)
        return Deck(title=slide.title, slides=[slide])
    s = STRUCTURES[name]
    fig = StackFigure(kind="stack", caption=s.get("caption"), rows=s["rows"])
    slide = Slide(layout_type="figure", title=s["title"], figure=fig)
    return Deck(title=s["title"], slides=[slide])


def build_photonic(name: str) -> Slide:
    """Build a validated photonic (graph-form) figure slide from a preset."""
    s = PHOTONIC_STRUCTURES[name]
    fig = PhotonicFigure(
        caption=s.get("caption"),
        substrate=s.get("substrate", "glass"),
        substrate_label=s.get("substrate_label", "Substrate"),
        waveguide_material=s.get("waveguide_material", "polymer"),
        nodes=s["nodes"], links=s["links"])
    return Slide(layout_type="figure", title=s["title"], figure=fig)


def all_names() -> list[str]:
    return list(STRUCTURES) + list(PHOTONIC_STRUCTURES)
