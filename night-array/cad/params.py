"""Night Array -- every dimension of the station, in millimetres.

Single source of truth for model.py / build.py and copied verbatim into
export/model/scene.json ("params").

Axes (same as the app, see SPEC.md section 1):
  +X right, +Y up, +Z toward the user.  Desk surface y = 0, x = 0 is the centre
  of the main base slab, z = 0 is the front-to-back centre of the base.
The exported assembly is in the STOW pose (laptop docked, keyboard and mouse in
their charging pockets).
"""

import math

TOE_IN_DEG = 10.0
_C = math.cos(math.radians(TOE_IN_DEG))
_S = math.sin(math.radians(TOE_IN_DEG))

P = {
    "units": "mm",
    "axes": "+X right, +Y up, +Z toward the user; desk y=0; x=0 centre of base slab; z=0 base depth centre",
    "pose": "stow",

    # ------------------------------------------------------------------ base
    "base": {
        "x": [-640.0, 650.0],
        "z": [-150.0, 150.0],
        "height": 36.0,              # rim top
        "corner_r": 40.0,            # plan corner radius
        "top_fillet": 6.0,           # soft outer top edge
        "bottom_fillet": 1.5,
        "rim_w": 16.0,               # perimeter rim width at y = 36
        "rim_inner_fillet": 2.5,
        "deck_y": 30.0,              # recessed inner deck
        "deck_fillet": 3.0,          # concave fillet deck -> rim wall
        "wall": 4.0,                 # side walls of the hollow shell
        "floor_t": 2.5,              # bottom plate
        "deck_t": 2.5,               # deck plate (cavity top at deck_y - deck_t)
        "liner_t": 1.0,              # graphite deck liner inlaid flush with the deck
        "liner_reveal": 1.2,         # titanium reveal around the liner
        "pocket_wall": 2.0,          # pocket floors / walls
        "kb_pocket": {"c": [-90.0, 62.0], "size": [376.0, 136.0], "floor_y": 16.0, "r": 12.0},
        "mouse_pocket": {"c": [250.0, 62.0], "size": [82.0, 134.0], "floor_y": 16.0, "r": 12.0},
        "pocket_edge_fillet": 1.5,
        "pad_t": 2.0,                # soft-touch pads, y 16..18
        "pad_clear": 0.5,
        "pad_ring_d": 58.0,          # debossed charge-zone ring on the pads
        "coil_window_d": 54.0,       # non-metallic windows in the Ti pocket floor
        "plinth": {"z_front": -58.0, "half_w_front": 172.0, "half_w_back": 196.0, "r": 12.0},
        "cable_chase": {"x": [-50.0, 50.0], "z": [-122.0, -96.0]},
        "undercut": {"x": [-575.0, 575.0], "y": [0.0, 6.0], "depth": 4.0},
        "glow": {"x": [-560.0, 560.0], "y": [2.0, 5.0], "z": [146.0, 149.0]},
        "kb_led": {"x": -90.0, "w": 30.0, "d": 2.0, "z": 140.0, "depth": 1.0},
        "mouse_led": {"x": 250.0, "w": 16.0, "d": 2.0, "z": 140.0, "depth": 1.0},
        "feet": {"x": [-600.0, 610.0], "z": [-122.0, 122.0], "w": 12.0, "depth": 1.5},
        "io_bay": {"x": [-602.0, -478.0], "y": [6.0, 27.0], "depth": 1.5},
        "exhaust": {"x": [-468.0, -322.0], "y": [9.0, 25.0], "slot_w": 4.0, "pitch": 9.0},
        "ac_inlet": {"x": 400.0, "y": 14.0},
    },

    # ------------------------------------------------------------------ stand
    "neck": {
        "y": [36.0, 156.0],
        "bottom_w": 320.0,
        "top_w": 180.0,
        "z_bottom": [-130.0, -70.0],
        "z_top": [-140.0, -80.0],     # slight rearward lean (4.8 deg)
        "edge_fillet": 8.0,
        "wall": 4.0,
        "light": {"w": 150.0, "h": 5.0, "depth": 3.0, "y": [126.0, 131.0]},   # clear of the display overhang, seen from the seat
        "badge": {"text": "NIGHT ARRAY", "size": 8.5, "tracking": 0.42, "y": 104.0, "depth": 0.5,
                  "font": "Inter", "kind": "regular"},
    },

    # ------------------------------------------------------------------ display
    "display": {
        "panel_inch": 27,
        "panels": 2,
        "resolution_each": [2560, 1440],
        "active": [596.7, 335.7],
        "toe_in_deg": TOE_IN_DEG,
        "seam_axis_xz": [0.0, -62.0],          # vertical fold axis, front surface of the glass
        "seam_mm": 14.0,                       # 7 mm each side of x = 0, measured along the facets
        "inner_border": 7.0,
        "outer_border": 9.0,
        "chin": 16.0,
        "top_border": 9.0,
        "glass_y": [156.0, 516.7],
        "active_y": [172.0, 507.7],
        "glass_t": 2.0,
        "module_t": 10.0,                      # stripped LCD module (cell, backlight, steel tray) behind the black front
        "module_inset": 1.5,                   # module body stops short of the glass's outer edge
        "screen_proud": 0.3,
        "glass_corner_r": 4.0,
        "frame_w": 3.0,
        "frame_proud": 1.0,
        "frame_depth": 5.0,                    # frame band runs w = -5 .. +1 (w = facet normal)
        "frame_corner_r": 7.0,
        "mullion_w": 4.0,
        "mullion_front_z": -60.6,
        "shroud_thin": 16.0,                   # thin edge zone behind the faces (inner wall 1.5 mm behind the modules)
        "shroud_depth": 45.0,                  # behind the panel faces
        "shroud_wall": 2.5,
        "bump_front": {"u_max": 545.0, "y": [172.0, 458.0]},   # at w = -shroud_thin
        "bump_back": {"u_max": 440.0, "y": [200.0, 405.0]},    # at w = -45
        "keel": {"bottom_w": 200.0, "top_w": 116.0, "y_top": 440.0, "z_back_bottom": -143.0,
                 "z_back_top": -110.0, "chamfer": 14.0, "wall": 3.0},
        "vesa_hub": {"d": 104.0, "proud": 3.0, "y": 262.0, "pattern": 100.0},
        "vents": {"count": 34, "pitch": 12.5, "u0": 70.0, "w": 3.2, "len": 26.0},
        "plate": {"u": [200.0, 420.0], "y": [255.0, 425.0], "t": 2.0},   # bolted to the module backs
        "spine_arm": {"u_max": 236.0, "y": [330.0, 352.0], "w": [-23.5, -14.0]},
        "spine_post": {"x": 18.0, "y": [160.0, 352.0], "z": [-114.0, -76.0], "wall": 3.0},   # 36 x 38 RHS
        "spine_foot": {"x": 88.0, "y": [156.0, 160.0], "z": [-137.0, -83.0]},
        "board": {"u": [220.0, 410.0], "y": [262.0, 348.0], "w_pcb": [-25.6, -24.0]},
    },

    # ------------------------------------------------------------------ dock
    "dock": {
        "x": [650.0, 775.0],
        "z": [-130.0, 130.0],
        "h_back": 120.0,
        "h_front": 60.0,
        "profile_pts": [[-130.0, 120.0], [-96.0, 120.0], [-58.0, 104.0], [-12.0, 80.0], [40.0, 64.5], [78.0, 60.0], [130.0, 60.0]],
        "plan_r": 12.0,
        "edge_fillet": 4.0,
        "slot": {"x": [712.0, 732.0], "z": [-112.0, 112.0], "floor_y": 24.0, "r": 3.0, "lead_in": 4.0},
        "wall": 3.0,
        "cavity_y": [2.5, 21.0],
        "panel_t": 2.0,
        "panel_inset": 7.0,
        # latch-free: the laptop's own weight seats it on the sprung USB-C, you lift it straight out.  The front face
        # (flat x 650 .. 763 up to the R12 plan corner, 60 tall) carries one oxblood panel with the side panel's 7 mm
        # margins, so the two read as one wrap round the corner, and a slim amber seated light inlaid near its top
        # edge on the slot axis, right under the laptop it reports on.
        "front_panel": {"x": [657.0, 756.0], "y": [7.0, 53.0]},
        "led": {"x": 722.0, "w": 30.0, "h": 2.0, "y": 46.0, "depth": 1.0},   # x = slot axis, y = bottom edge
        "connector": {"z": -60.0, "boot": [7.0, 6.0, 14.0], "plug": [2.5, 6.5, 8.3], "boot_y": [18.0, 24.0]},
    },

    # ------------------------------------------------------------------ laptop
    "laptop": {
        "x": [714.5, 729.5], "y": [24.0, 328.0], "z": [-106.0, 106.0],
        "corner_r": 6.0, "edge_r": 2.5, "lid_t": 5.0, "seam_groove": 0.6,
        "port_z": -60.0, "port": [3.2, 7.5, 8.9],
    },

    # ------------------------------------------------------------------ keyboard
    "keyboard": {
        "size": [360.0, 120.0], "h_front": 9.0, "h_back": 13.0, "corner_r": 8.0,
        "stow_c": [-90.0, 62.0], "stow_y": 18.0,
        "unit": 18.5, "cap_gap": 2.0, "cap_h": 2.6, "cap_r": 2.2, "cap_taper": 12.0,
        "well_depth": 1.0, "well_margin": 2.5,
        "coil_x": [-80.0, 80.0], "coil_d": [40.0, 14.0], "coil_t": 1.0,
        "layout": "75% (84 keys, 16u x 6 rows)",
    },

    # ------------------------------------------------------------------ mouse
    "mouse": {
        "size": [66.0, 118.0, 38.0], "stow_c": [250.0, 62.0], "stow_y": 18.0,
        "wheel_d": 18.0, "wheel_w": 6.5, "wheel_z": -32.0, "wheel_cy": 27.0,
        "coil_d": [38.0, 12.0], "coil_t": 1.0,
    },

    # ------------------------------------------------------------------ desk mat
    "deskmat": {"size": [820.0, 3.0, 300.0], "c": [60.0, 385.0], "corner_r": 12.0},

    # ------------------------------------------------------------------ internals
    "internals": {
        "board": {"x": [-600.0, -300.0], "z": [-120.0, 110.0], "y": [4.0, 5.6]},
        "vapor_chamber": {"x": [-470.0, -322.0], "z": [-118.0, -22.0], "y": [5.6, 8.0]},
        "fins": {"x": [-466.0, -326.0], "z": [-116.0, -24.0], "y": [8.0, 22.0], "t": 0.8, "pitch": 2.8},
        "fan": {"x": [-440.0, -352.0], "z": [-20.0, 64.0], "y": [5.6, 19.6]},
        "psu": {"x": [330.0, 470.0], "z": [-138.0, 20.0], "y": [4.0, 24.0]},
        "qi_coils_kb_x": [-170.0, -10.0], "qi_z": 62.0, "qi_coil_mouse_x": 250.0,
        "qi_coil": {"d": [50.0, 20.0], "y": [12.0, 15.0]},
        "ferrite": {"size": 60.0, "y": [10.0, 12.0]},
        "dock_board": {"x": [662.0, 762.0], "z": [-112.0, 118.0], "y": [4.0, 5.6]},
    },

    # ------------------------------------------------------------------ poses (deltas, mm)
    "poses_mm": {
        "work_keyboard": [0.0, -15.0, 298.0],
        "work_mouse": [40.0, -15.0, 298.0],
        "work_lift": 30.0,           # stow <-> work path: lift clear of the 36 mm rim ...
        "work_clear_z": 200.0,       # ... slide forward until the back edge is past the base front, then set down
        "dock_align_lift": 70.0,     # laptop part-way into the cradle lead-in, above the 60 mm front lip
        "dock_lift_out": 160.0,
    },
}


def facet_point(side, u, y, w=0.0):
    """World point on the display facet frame.

    side = +1 right panel, -1 left panel.  u = distance along the facet from the
    seam axis, w = distance along the facet's front normal (toward the user).
    """
    sx, sz = P["display"]["seam_axis_xz"]
    x = side * (u * _C - w * _S)
    z = sz + u * _S + w * _C
    return (x, y, z)


COS_T, SIN_T = _C, _S
