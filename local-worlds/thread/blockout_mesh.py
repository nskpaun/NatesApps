"""Blockout boxes -> mesh + collider GLB, placed in the trained splat's coordinate frame.  blockout_mesh.py NAME
Also writes NAME_metre.json: where the room lies in that frame and, when the world has them, its setting, sky, wind, mood,
effects and the things that move (movers). An object the splat was trained without (NAME/lifted.json) is left out here."""
import sys, json, numpy as np, trimesh
sys.argv, name = [sys.argv[0], "prep"], sys.argv[1]
import chisel_ring as C
from movers import S, fit, from_room, to_file, paint, prim_mesh, obox
B = C.B
s, R, t = fit(name)
def saved(f, default):
    try: return json.load(open(f"{C.D}/{name}/{f}"))
    except (OSError, ValueError): return default
gone = {i for i in saved("lifted.json", []) if type(i) is int}           # objects the splat in this folder was trained without
split = {m["i"]: m for m in saved("movers.json", [])}                   # those of them that got a splat of their own
if C.OUT:       # outdoors there are no walls or ceiling: a slab of ground, the play area plus 6 m, its top at y = 0
    room = trimesh.creation.box(extents=[C.RW + 12, 0.2, C.RD + 12]); room.apply_translation([C.RW / 2, -0.1, C.RD / 2])
else:
    lo, hi = np.array(B.ROOM[0], float), np.array(B.ROOM[1], float)
    room = trimesh.creation.box(extents=hi - lo); room.apply_translation((lo + hi) / 2); room.invert()
# the shown mesh keeps a shape's detail; the collider only needs its rough form
for suffix, faces in (("mesh", 20000), ("mesh_collider", 3000)):
    m = trimesh.util.concatenate([paint(room.copy(), (120, 120, 125))] + [prim_mesh(p, faces) for p, oi in zip(B.PRIMS, C.PRIM_OBJ) if oi not in gone])
    to_file(m, s, R, t).export(f"{C.D}/{name}/{name}_{suffix}.glb")
mid = s * R @ (S @ [C.RW / 2, 0, C.RD / 2]) + t     # middle of the room's floor in the trained frame, so the viewer need not guess it from the mesh
meta = {"metre": float(s), "room": [C.RW, C.RH, C.RD], "centre": [float(mid[0]), float(mid[2])], "floor": float(mid[1]), "fromRoom": from_room(s, R, t)}
meta["up"] = [float(v) for v in R @ S @ [0, 1, 0]]     # the room's own up: the trainer's guess (the cameras' mean) tilts the room by half a degree
start = saved("../depth/start.json", None)              # the painted view to start in, clear of posts (chisel_ring.py prep)
try:
    e, l = np.array(start["eye"], float), np.array(start["look"], float); f = R @ (S @ (l - e))
    if np.isfinite([*e, *f]).all() and np.linalg.norm(f) > 1e-6: meta.update(eye=[float(v) for v in s * R @ (S @ e) + t], forward=[float(v) for v in f / np.linalg.norm(f)])
except (TypeError, KeyError, ValueError): pass
w = C.world
if C.OUT:
    meta.update(setting="outdoor", surround=C.SURROUND)
    sky = saved("sky.json", None)
    if sky: meta["sky"] = sky
meta.update({k: w[k] for k, kind in (("wind", dict), ("mood", dict), ("effects", list)) if isinstance(w.get(k), kind) and w[k]})
movers = []
for mo in w.get("motions") if isinstance(w.get("motions"), list) else []:
    i, kind = (mo.get("i"), mo.get("type")) if isinstance(mo, dict) else (None, None)
    if type(i) is not int or not 0 <= i < len(C.objs): continue
    # what sways stays in the room's splat and is bent there; what moves away is shown only if it got a splat of its own
    if kind == "sway" and i not in gone: e = {"render": "skin"}
    elif i in gone and i in split: e = {"render": "splat", **{k: split[i][k] for k in ("ply", "mesh", "collider", "fromRoom", "splats")}}
    else: continue
    box = obox(i)
    e = {"i": i, "name": C.objs[i]["name"], "type": kind, "render": e.pop("render"), "box": box, **{k: v for k, v in mo.items() if k not in ("i", "type")}, **e}
    if kind == "swing":     # the layout gives the pivot's height; the viewer gets the point, above the piece's middle
        up = mo.get("pivot"); e["pivot"] = [box["c"][0], float(up) if isinstance(up, (int, float)) else box["c"][1] + box["h"][1], box["c"][2]]
    movers.append(e)
if movers: meta["movers"] = movers
json.dump(meta, open(f"{C.D}/{name}/{name}_metre.json", "w"))
print("collider tris", len(m.faces))
