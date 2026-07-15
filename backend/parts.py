"""WP8 — part-level knowledge (single source; the atomic layer below
domain.STRUCTURES and archetypes.ARCHETYPES).

Each part FUNCTION knows: its material role, default footprint width, whether it
is a base/substrate, its valid mounting interfaces, and semantic flags. Grounded
in the assembly-facts research (handoff/07b). compile_brief, understand and the
verify loop all consume this so facts live in one place.
"""
from __future__ import annotations

# function -> knowledge
PARTS: dict[str, dict] = {
    # ---- bases / carriers ----
    "pic":        {"base": True, "material": "silicon", "can_embed": ["waveguide"],
                   "aka": ["pic", "실리콘 포토닉", "photonic ic", "포토닉 ic"]},
    "substrate":  {"base": True, "material": "substrate", "aka": ["substrate", "기판"]},
    "interposer": {"base": True, "material": "silicon", "aka": ["interposer", "인터포저"]},
    "submount":   {"base": True, "material": "dielectric", "aka": ["submount", "서브마운트"]},
    "pcb":        {"base": True, "material": "pcb", "aka": ["pcb", "보드", "board"]},
    "leadframe":  {"base": True, "material": "leadframe", "aka": ["leadframe", "리드프레임"]},
    # ---- active dies ----
    "laser_gain": {"material": "gan", "width": 0.22, "emits": True, "has_pads": True,
                   "interfaces": ["solder", "flipchip", "wirebond", "edge_couple"],
                   "aka": ["laser", "레이저", "gain chip", "이득칩", "dfb"]},
    "photodiode": {"material": "device", "width": 0.18, "detects": True, "has_pads": True,
                   "interfaces": ["flipchip", "wirebond", "monolithic"],
                   "aka": ["photodiode", "포토다이오드", "pd", "수광"]},
    "logic_die":  {"material": "silicon", "width": 0.4, "has_pads": True,
                   "interfaces": ["flipchip", "wirebond", "hybrid_bond"],
                   "aka": ["logic", "die", "다이", "칩", "asic", "soc"]},
    "modulator":  {"material": "device", "width": 0.2, "aka": ["modulator", "변조기", "mzm"]},
    "hbm":        {"material": "silicon", "width": 0.26, "aka": ["hbm", "dram", "메모리"]},
    "mems":       {"material": "silicon", "width": 0.3, "cavity": True,
                   "aka": ["mems", "멤스", "센서", "membrane"]},
    # ---- electronics ----
    "driver_ic":  {"material": "metal", "width": 0.2, "electronic": True,
                   "aka": ["driver", "드라이버"]},
    "tia":        {"material": "metal", "width": 0.18, "electronic": True, "aka": ["tia"]},
    "eic":        {"material": "dark", "width": 0.34, "electronic": True, "aka": ["eic"]},
    # ---- optics / passives ----
    "waveguide":  {"material": "polymer", "width": 0.6, "buried": True,
                   "interfaces": ["monolithic", "edge_couple"],
                   "aka": ["waveguide", "도파로", "광도파로"]},
    "lens":       {"material": "glass", "width": 0.12, "glyph": "dome",
                   "aka": ["lens", "렌즈", "microlens"]},
    "fiber":      {"material": "gray", "width": 0.16, "aka": ["fiber", "파이버", "광섬유"]},
    "mlcc":       {"material": "metal", "width": 0.1, "aka": ["mlcc", "커패시터", "수동소자"]},
    "passive":    {"material": "metal", "width": 0.12, "aka": ["passive", "수동"]},
    # ---- package features (handled specially by the compiler) ----
    "mold":       {"feature": "mold", "aka": ["mold", "몰드", "emc", "encapsulation"]},
    "bga":        {"feature": "bottom_balls", "aka": ["bga", "solder ball", "패키지 볼", "lga"]},
    "generic":    {"material": "gray", "width": 0.24, "aka": []},
}


def get(func: str) -> dict:
    return PARTS.get((func or "").lower().strip(), PARTS["generic"])


def is_base(func: str) -> bool:
    return bool(get(func).get("base"))


def material(func: str) -> str:
    return get(func).get("material", "gray")


def width(func: str) -> float:
    return get(func).get("width", 0.24)


def feature(func: str) -> str | None:
    """'mold' | 'bottom_balls' | None — package-level features, not mounted boxes."""
    return get(func).get("feature")
