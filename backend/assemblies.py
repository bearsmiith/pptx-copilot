"""WP9 — physical assembly recipes (single source, mirrors domain/archetypes).

Each recipe is a Brief-shaped dict (genre=physical). understand uses them as
few-shot exemplars, templates.match_structure routes to them (template-first =
safest for small models), examples exposes them in the gallery, and eval golden
references them. PoP is expressed as chip-on-chip (dram on ap); watch SiP as a
single overmold + LGA — no special recursion needed, the assembly scene already
covers it.
"""
from __future__ import annotations

from brief_model import Brief
from compile_brief import compile_brief
from models import Slide


def _p(id, name, function, **kw):
    d = {"id": id, "name": name, "function": function}
    d.update(kw)
    return d


ASSEMBLIES: dict[str, dict] = {
    "smartphone_mainboard": {
        "aka": ["스마트폰 메인보드", "휴대폰 기판", "mobile 실장", "logic board",
                "slp", "메인보드 실장", "스마트폰 기판 단면", "폰 메인보드"],
        "title": "Smartphone Main Board (SLP)",
        "must_label": ["PoP", "shield can", "SLP"],
        "brief": {
            "genre": "physical", "emphasis": "section", "base": "slp",
            "caption": "Smartphone main board (not to scale): double-sided SMT, "
                       "PoP AP + memory under an EMI shield can.",
            "parts": [
                _p("slp", "SLP main board", "pcb"),
                _p("ap", "AP", "ap_pop", on="slp",
                   interface={"kind": "solder", "pad_count": 10}),
                _p("dram", "LPDDR (PoP)", "dram_pkg", on="ap",
                   interface={"kind": "solder", "pad_count": 8}),
                _p("nand", "UFS NAND", "nand", on="slp",
                   interface={"kind": "solder", "pad_count": 8}),
                _p("pass", "01005 passives", "passive_01005", on="slp"),
                _p("btb", "BTB connector", "btb_conn", on="slp",
                   interface={"kind": "solder"}),
                _p("pmic", "PMIC", "pmic", on="slp", attributes={"side": "bottom"}),
                _p("rf", "RF FEM", "rf_fem", on="slp", attributes={"side": "bottom"}),
                _p("can", "Shield can", "shield_can", on="slp",
                   attributes={"covers": ["ap", "dram", "nand"]}),
            ],
            "requirements": ["양면 실장", "PoP 2단 볼", "쉴드캔이 AP·NAND를 덮음"],
        },
    },
    "watch_sip": {
        "aka": ["워치 sip", "watch sip", "스마트워치 실장", "s-sip",
                "워치 실장 단면", "애플워치 sip"],
        "title": "Smartwatch SiP Module",
        "must_label": ["SiP", "mold", "LGA"],
        "brief": {
            "genre": "physical", "emphasis": "section", "base": "sip_sub",
            "caption": "Watch SiP: dozens of bare dies + passives on one substrate, "
                       "single overmold, LGA to the board.",
            "parts": [
                _p("sip_sub", "SiP substrate", "substrate"),
                _p("ap", "SoC (flip-chip)", "logic_die", on="sip_sub",
                   interface={"kind": "flipchip", "pad_count": 10}),
                _p("mem", "Memory (wire-bond)", "hbm", on="sip_sub",
                   interface={"kind": "wirebond"}),
                _p("pmic", "PMIC", "pmic", on="sip_sub",
                   interface={"kind": "flipchip"}),
                _p("pass", "01005 passives", "passive_01005", on="sip_sub"),
                _p("mold", "Overmold (EMC)", "mold"),
                _p("lga", "LGA pads", "bga", attributes={},
                   interface={"kind": "solder", "pad_count": 12}),
            ],
            "requirements": ["단일 오버몰드", "베어다이 WB+FC 혼재", "외부 LGA"],
        },
    },
    "pop_package": {
        "aka": ["pop 패키지", "package on package", "패키지 온 패키지", "pop 단면", "tmv"],
        "title": "Package-on-Package (PoP)",
        "must_label": ["PoP", "TMV"],
        "brief": {
            "genre": "physical", "emphasis": "section", "base": "substrate",
            "caption": "PoP: bottom logic (fan-out/FC, molded with through-mold "
                       "vias) + top memory package stacked by PoP solder balls.",
            "parts": [
                _p("substrate", "Bottom substrate", "substrate"),
                _p("logic", "Logic die", "logic_die", on="substrate",
                   interface={"kind": "flipchip", "pad_count": 10}),
                _p("mem", "Memory package (PoP)", "dram_pkg", on="logic",
                   interface={"kind": "solder", "pad_count": 8}),
                _p("mold", "Mold (TMV)", "mold"),
                _p("bga", "BGA", "bga", interface={"kind": "solder", "pad_count": 11}),
            ],
            "requirements": ["볼 2단(PoP)", "TMV", "하단 BGA"],
        },
    },
    "butterfly_laser": {
        "aka": ["버터플라이 레이저", "butterfly laser", "laser 모듈", "레이저 서브마운트",
                "tosa", "laser submount"],
        "title": "Butterfly Laser Module",
        "must_label": ["submount", "laser", "fiber"],
        "brief": {
            "genre": "physical", "emphasis": "section", "base": "submount",
            "caption": "Edge-emitting laser on an AlN submount, lens-coupled to fiber; "
                       "monitor photodiode behind.",
            "parts": [
                _p("submount", "AlN submount (on TEC)", "submount"),
                _p("laser", "Laser diode", "laser_gain", on="submount",
                   interface={"kind": "solder", "pad_count": 3}, attributes={"emits": True}),
                _p("lens", "Lens", "lens", on="submount"),
                _p("fiber", "Fiber", "fiber", on="submount", attributes={"detects": True}),
            ],
            "relations": [{"type": "optical", "src": "laser", "dst": "fiber",
                           "label": "beam"}],
            "requirements": ["laser 솔더 실장", "빔 laser→fiber", "submount"],
        },
    },
    "cis_module": {
        "aka": ["cis 센서", "이미지센서", "cmos image sensor", "bsi 센서",
                "카메라 센서 적층", "이미지 센서 단면"],
        "title": "CMOS Image Sensor (BSI, stacked)",
        "must_label": ["microlens", "color filter", "hybrid bond"],
        "brief": {
            "genre": "physical", "emphasis": "section", "base": "substrate",
            "caption": "Stacked BSI CIS: pixel wafer hybrid-bonded to logic; color "
                       "filter + microlens on top under a glass lid.",
            "parts": [
                _p("substrate", "Package substrate", "substrate"),
                _p("logic", "Logic die", "logic_die", on="substrate",
                   interface={"kind": "flipchip", "pad_count": 8}),
                _p("pixel", "Pixel die (BSI)", "logic_die", on="logic",
                   interface={"kind": "hybrid_bond"}),
                _p("cf", "Color filter (Bayer)", "color_filter", on="pixel"),
                _p("mla", "Microlens array", "microlens_arr", on="cf"),
                _p("lid", "Glass lid", "glass_lid", on="substrate",
                   attributes={"side": "top"}),
            ],
            "requirements": ["마이크로렌즈 어레이", "컬러필터", "픽셀-로직 하이브리드본드"],
        },
    },
    "fiber_attach": {
        "aka": ["파이버 어태치", "v-groove 파이버", "fiber array", "fau", "파이버 정렬",
                "파이버 결합", "edge coupling 파이버"],
        "title": "Fiber Attach to PIC (V-groove)",
        "must_label": ["V-groove", "waveguide", "edge couple"],
        "brief": {
            "genre": "physical", "emphasis": "section", "base": "pic",
            "caption": "Fiber array held in etched V-grooves, edge-butt-coupled to "
                       "the PIC's buried waveguide.",
            "parts": [
                _p("pic", "Silicon PIC", "pic"),
                _p("wg", "Waveguide", "waveguide", on="pic", attributes={"buried": True}),
                _p("fau", "Fiber (V-groove)", "fiber_vgroove", on="pic",
                   attributes={"detects": True}),
                _p("laser", "Laser", "laser_gain", on="pic",
                   interface={"kind": "edge_couple"}, attributes={"emits": True}),
            ],
            "relations": [{"type": "optical", "src": "laser", "dst": "fau",
                           "label": "λ"}],
            "requirements": ["V-groove 파이버", "매립 waveguide", "edge coupling"],
        },
    },
}


def all_names() -> list[str]:
    return list(ASSEMBLIES)


def build_assembly(name: str) -> Slide:
    """Compile an assembly recipe into a validated figure Slide."""
    a = ASSEMBLIES[name]
    brief = Brief.model_validate({"title": a["title"], **a["brief"]})
    slide = compile_brief(brief)
    slide.title = a["title"]
    return slide
