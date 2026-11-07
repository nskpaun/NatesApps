"""Night Array kit -- parts registry: every part from every module, in group order, with its kind, material,
filament / BOM id, plus the scene-level tables build.py writes into scene.json (materials, group text, poses,
explode vectors).  Modules own their PARTS lists; this file only aggregates (owner: CAD architect / integrator).
"""

from __future__ import annotations

from . import base, display, dock, electronics, neck, structure
from .common import LAYOUT, PartDef

MODULES = {"display": display, "neck": neck, "base": base, "dock": dock, "structure": structure,
           "electronics": electronics}

GROUP_ORDER = ["display", "stand", "base", "dock", "laptop", "keyboard", "mouse", "deskmat", "structure", "electronics"]

_ALL = []
for _m in MODULES.values():
    _ALL += _m.PARTS
PARTS: list[PartDef] = sorted(_ALL, key=lambda p: GROUP_ORDER.index(p.group))
BY_ID = {p.id: p for p in PARTS}
assert len(BY_ID) == len(PARTS), "duplicate part ids"
MODULE_OF = {p.id: name for name, m in MODULES.items() for p in m.PARTS}


def parts_of_module(name):
    return [p.id for p in MODULES[name].PARTS]


def build_parts(only=None, verbose=True):
    import time
    out = {}
    for p in PARTS:
        if only and p.id not in only:
            continue
        t = time.time()
        s = p.builder()
        if verbose:
            print(f"  {p.id:18s} {time.time() - t:6.2f}s  solids={len(s.Solids())} valid={s.isValid()}", flush=True)
        out[p.id] = s
    return out


# ----------------------------------------------------------------------------- materials
# key: label, sRGB, metallic, roughness, density g/cm3 (fallback when a part has no mass override), emissive, spec
MATERIALS = {
    "titanium":      ("Neutral Titanium", "#BDB2A4", 1.0, 0.32, 1.27, None,
                      "printed PETG, filler primer + Rust-Oleum 245220 Titanium Silver + satin clear"),
    "graphite":      ("Charcoal Graphite", "#3A3735", 0.55, 0.48, 1.25, None,
                      "printed PETG-CF Titan Gray (matte graphite); device bodies in their own finish"),
    "oxblood":       ("Brushed Oxblood", "#7A2E2A", 0.75, 0.36, 1.24, None, "printed PLA Maroon Red, sanded one way + satin clear"),
    "glass_black":   ("Black Glass", "#060606", 0.0, 0.06, 2.50, None, "black glass"),
    "screen":        ("Active Screen", "#08080A", 0.0, 0.12, 2.50, None, "IPS active area (2560 x 1440 each)"),
    "keycap":        ("PBT Keycap", "#1C1A19", 0.0, 0.62, 1.30, None, "double-shot PBT"),
    "rubber":        ("Rubber", "#141313", 0.0, 0.88, 1.20, None, "polyurethane / silicone"),
    "amber_led":     ("Amber Light", "#F2A04A", 0.0, 0.40, 1.20, "#F2A04A", "1800 K COB behind an opal / clear PETG diffuser"),
    "copper":        ("Copper", "#C9805A", 1.0, 0.33, 8.96, None, "copper"),
    "pcb":           ("PCB", "#1D2A22", 0.0, 0.55, 1.85, None, "FR-4 boards and modules"),
    "ferrite":       ("Ferrite", "#2A2828", 0.0, 0.80, 4.80, None, "MnZn ferrite"),
    "laptop_alu":    ("Laptop Aluminium", "#8C847B", 1.0, 0.38, 2.70, None, "aluminium unibody"),
    "felt":          ("Wool Felt", "#2B2724", 0.0, 0.96, 0.30, None, "merino felt on cork"),
    "steel":         ("Steel", "#5E6164", 1.0, 0.45, 7.85, None, "A36 / 1008 mild steel, painted or powder coated"),
    "aluminium":     ("Aluminium", "#A9ACAE", 1.0, 0.35, 2.70, None, "6063 extrusion / housing, clear anodised"),
    "plastic_black": ("Black Plastic", "#141414", 0.0, 0.70, 1.20, None, "matte black ABS / PC housing"),
}

GROUP_TEXT = {
    "display": dict(name="Dual 27″ display",
                    summary="Two Samsung S60UD 27″ QHD monitors, toed in 10°, in one printed frame and shroud with an honest 17 mm seam.",
                    description=("Two complete Samsung ViewFinity S6 S60UD monitors (their own housings and internal power "
                                 "supplies, nothing stripped) hang on a steel wing bracket by their VESA 100 mounts. Each is "
                                 "toed in 10° about the seam, so the outer edges come 106 mm toward you. A printed titanium "
                                 "front frame wraps the outer bezels and a 4 mm strip covers the joint; a printed graphite "
                                 "shroud and keel cover the backs with 10 mm of air over each monitor's rear box, intakes "
                                 "underneath and exhausts on top.")),
    "stand": dict(name="Neck & light bar",
                  summary="Printed trapezoid neck around the two aluminium posts and the cable chase, with the amber light bar.",
                  description=("A printed graphite trapezoid shroud (320 mm at the foot, 180 at the top) covers the two "
                               "2040 aluminium posts that carry the monitors and the cables that climb to them. NIGHT ARRAY "
                               "is inlaid on its front face and an 1800 K COB strip in an aluminium channel glows just "
                               "below the display. The neck carries no load.")),
    "base": dict(name="Base & charging pockets",
                 summary="1.29 m printed titanium base on a steel frame, with Qi charging pockets for the keyboard and mouse.",
                 description=("Fourteen printed PETG tiles (painted titanium) bolt to a steel spine plate, a front bar and "
                              "two 2020 rails. Under the deck are the power strip, the GaN charger, the dock electronics "
                              "and the low-voltage hub, each in its own bay behind a bottom hatch. The keyboard and mouse "
                              "pockets have per-device locator inserts and an Anker 313 pad under a 1.0 mm solid floor.")),
    "dock": dict(name="Laptop dock",
                 summary="Latch-free right-wing cradle: guide the laptop in, its own weight seats it on a floating USB-C, lift it out.",
                 description=("The printed cradle rises 120 mm at the back and sweeps down to a 60 mm front, wrapped in "
                              "oxblood panels. A universal slot insert sets the width for any 11-20 mm laptop; the laptop's "
                              "own weight seats its port on a Newnex USB4 side-exit plug held in a floating, sprung carriage "
                              "0.4 mm below the landing plane, and you lift it straight out. An IR break-beam lights the "
                              "amber seated light.")),
    "laptop": dict(name="Laptop",
                   summary="Your laptop (11-20 mm thick) stands closed in the dock: it is the computer.",
                   description=("A generic 14-inch laptop (304 × 212 × 15 mm) stands closed on its side, hinge toward the "
                                "back. Docked, it drives both monitors through the Plugable dock and charges at up to 100 W. "
                                "There is no computer in the base.")),
    "keyboard": dict(name="Keyboard",
                     summary="Keychron K3 Ultra 8K with a NILLKIN Magic Tag: charges on its Qi pad when stowed.",
                     description=("A 75 % low-profile Keychron K3 Ultra 8K (320.6 × 126 mm). A NILLKIN Magic Tag plugged "
                                  "into its left USB-C folds under the left-rear corner and lands over the pocket's Anker 313 "
                                  "pad; the printed locator insert holds it to within 1 mm. Stowed, its keycaps sit within "
                                  "3 mm of the rim.")),
    "mouse": dict(name="Mouse",
                  summary="Lenovo Multi-Device Wireless Mouse X9, native Qi, in its own locator pocket.",
                  description=("A 59 × 101 × 34 mm Lenovo X9 mouse with native Qi charging, held over its pad by a printed "
                               "insert. In work mode it sits on the mat beside the keyboard.")),
    "deskmat": dict(name="Desk mat",
                    summary="Oakywood 90 × 30 felt and cork mat for work mode.",
                    description="A 3 mm merino felt mat on cork in front of the base; shown in work mode only."),
    "structure": dict(name="Steel frame & posts",
                      summary="The load path: steel wing bracket, two 2040 posts, a steel spine plate and front bar on rubber feet.",
                      description=("Laser-cut A36 steel from SendCutSend: a 3/16 in centre bracket with 10° ears and two "
                                   "3/16 in wing channels with return flanges carry the monitors; two 2040 aluminium posts "
                                   "take them down to a 1/4 in U-shaped spine plate, tied to a 1/4 in front bar, on six 3M "
                                   "Bumpon feet. Two 2020 rails carry the printed tiles. No printed part carries monitor load.")),
    "electronics": dict(name="Power & electronics",
                        summary="Power strip, GaN charger, Plugable dock and its brick, two Qi pads and the 12 V lighting hub.",
                        description=("One mains cord enters the station, at a Tripp Lite right-angle strip on edge under the "
                                     "rear plinth. It feeds both monitors, the dock's 130 W brick and a 100 W GaN charger, which "
                                     "powers the Qi pads and, through PD triggers, the 12 V amber lighting and its dimmer. "
                                     "All mains stays inside certified products.")),
}

# explode vectors (metres at explode = 1): parts leave their seats along their assembly direction
EXPLODE = {
    "display_screen": [0.0, 0.42, 0.22], "monitor_housings": [0.0, 0.42, 0.16], "display_frame": [0.0, 0.42, 0.30],
    "display_seam": [0.0, 0.42, 0.34], "display_back": [0.0, 0.42, -0.22],
    "neck": [0.0, 0.20, 0.0], "neck_light": [0.0, 0.20, 0.06], "neck_badge": [0.0, 0.20, 0.09],
    "base_shell": [0.0, 0.10, 0.0], "deck_liner": [0.0, 0.14, 0.0], "kb_insert": [0.0, 0.16, 0.0],
    "mouse_insert": [0.0, 0.16, 0.0], "base_hatches": [0.0, -0.05, 0.0], "base_glow": [0.0, 0.10, 0.06],
    "kb_charge_led": [0.0, 0.13, 0.0], "mouse_charge_led": [0.0, 0.13, 0.0],
    "dock_cradle": [0.20, 0.10, 0.0], "dock_panels": [0.28, 0.10, 0.04], "dock_led": [0.28, 0.10, 0.08],
    "dock_connector": [0.20, 0.03, 0.0], "dock_carriage": [0.20, 0.0, 0.0], "dock_insert": [0.20, 0.22, 0.0],
    "ir_beam": [0.20, 0.10, 0.0], "laptop_body": [0.20, 0.50, 0.0],
    "keyboard_body": [0.0, 0.25, 0.05], "keyboard_keys": [0.0, 0.29, 0.05], "keyboard_tag": [0.0, 0.21, 0.05],
    "mouse_shell": [0.0, 0.25, 0.05], "mouse_wheel": [0.0, 0.29, 0.05], "deskmat": [0.0, 0.0, 0.08],
    "spine_plate": [0.0, 0.0, 0.0], "front_bar": [0.0, 0.03, 0.0], "posts": [0.0, 0.05, 0.0],
    "rail_front": [0.0, 0.06, 0.0], "rail_mid": [0.0, 0.06, 0.0], "bracket_centre": [0.0, 0.42, -0.05],
    "wings": [0.0, 0.42, -0.10], "vesa_spacers": [0.0, 0.42, -0.02], "feet": [0.0, -0.03, 0.0],
    "fasteners": [0.0, 0.0, 0.0],
    "power_strip": [0.0, 0.02, 0.0], "gan_charger": [0.0, 0.02, 0.0], "dock_box": [0.0, 0.02, 0.0],
    "dock_brick": [0.0, 0.02, 0.0], "qi_pads": [0.0, 0.0, 0.0], "lv_hub": [0.0, 0.02, 0.0],
}

# poses: per-group deltas (mm) from stow.  Work: keyboard and mouse to the mat via a lift and a slide.
POSES_MM = {
    "work_keyboard": [0.0, 3.0 - LAYOUT["qi"]["kb_floor_y"], 315.0],
    "work_mouse": [40.0, 3.0 - LAYOUT["qi"]["mouse_floor_y"], 328.0],
    "work_lift": 35.0,
    "work_clear_z": 178.0,
    "dock_align_lift": 70.0,
    "dock_lift_out": 160.0,
}
ANIMATED_GROUPS = {"laptop", "keyboard", "mouse"}


def part_mass(pid, shape):
    """(grams, density g/cm3, note) -- the ONE mass model (build.py, stability.py, scene.json all use it).
    Purchased parts: research / manufacturer weight.  Printed: shell + infill model.  Metal / hardware: volume x
    density of the material."""
    from .common import FILAMENT, print_mass_g
    p = BY_ID[pid]
    vol = shape.Volume()
    if p.mass_g is not None:
        g = p.mass_g
        return g, (g / (vol / 1000.0) if vol > 0 else 0.0), p.mass_note or "manufacturer / research weight"
    if p.kind == "printed":
        g = print_mass_g(vol, shape.Area(), p.print)
        return g, g / (vol / 1000.0), (f"printed {FILAMENT[p.print.filament][2]}, {int(p.print.infill * 100)} % infill, "
                                       f"{p.print.walls} walls (shell + infill model)")
    dens = MATERIALS[p.material][4]
    return vol / 1000.0 * dens, dens, None
