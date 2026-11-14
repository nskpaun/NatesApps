"""Description -> local LLM writes a rough layout -> code checks it and expands it into primitives.
  llm_boxes.py "DESCRIPTION" OUT.json
Output: {"request", "room": [width, height, depth], "objects": [{"name", "prims": [primitive, ...]}]}  (see ../spike/blockout.py)
"""
import json, sys, math, re, urllib.request

FURNITURE = {  # width along the wall, depth out from the wall; built from several boxes each
    "sofa": (2.0, 0.9), "armchair": (0.85, 0.85), "coffee_table": (1.0, 0.6), "bookshelf": (1.2, 0.35),
    "floor_lamp": (0.35, 0.35), "window": (1.6, 0.06), "desk": (1.4, 0.7), "side_table": (0.45, 0.45),
    "bed": (1.6, 2.0), "chair": (0.45, 0.5), "plant": (0.5, 0.5), "cabinet": (1.0, 0.45), "dining_table": (1.6, 0.9),
}

def furniture_boxes(kind, w, d):
    """Boxes in the piece's own frame: u across [0,w], y up, v from its back [0,d]."""
    if kind in ("sofa", "armchair"):
        return [((0, 0, 0), (w, 0.45, d)), ((0, 0.45, 0), (w, 0.95, 0.25)), ((0, 0, 0), (0.18, 0.65, d)), ((w - 0.18, 0, 0), (w, 0.65, d))]
    if kind == "bed": return [((0, 0, 0), (w, 0.5, d)), ((0, 0.5, 0), (w, 1.1, 0.12))]
    if kind == "chair": return [((0, 0, 0), (w, 0.45, d)), ((0, 0.45, 0), (w, 0.9, 0.08))]
    if kind == "plant": return [((0.1, 0, 0.1), (w - 0.1, 0.4, d - 0.1)), ((0, 0.4, 0), (w, 1.4, d))]
    if kind == "cabinet": return [((0, 0, 0), (w, 0.9, d))]
    if kind in ("coffee_table", "desk", "side_table", "dining_table"):
        h = {"coffee_table": 0.42, "desk": 0.75, "side_table": 0.55, "dining_table": 0.75}[kind]; L = 0.06
        return [((0, h - 0.06, 0), (w, h, d))] + [((u, 0, v), (u + L, h - 0.06, v + L)) for u in (0.02, w - L - 0.02) for v in (0.02, d - L - 0.02)]
    if kind == "bookshelf": return [((0, 0, 0), (w, 2.0, d))]
    if kind == "floor_lamp": return [((0.15, 0, 0.15), (0.2, 1.5, 0.2)), ((0, 1.5, 0), (w, 1.82, d))]
    if kind == "window": return [((0, 0.9, 0), (w, 2.1, d))]

PROMPT = '''You design the rough 3D layout ("blockout") of an indoor space from a description. Output JSON only.

{"room": {"width": metres (x), "depth": metres (z), "height": metres},
 "pieces": [ one object per thing or group of things ]}

Each piece: {"label": short name, "shape": "box" or "cylinder" or a furniture name, "size": see below, "base": metres above the floor (0 = on the floor), "place": one of the placements below}
- box size: [width, height, depth] in metres. cylinder size: [radius, height] in metres (cylinders stand upright).
- furniture names, which need no size: FURNITURE_NAMES. Use these for ordinary rooms.
- "place": {"at": [u, v]}                     one piece; u and v are fractions 0..1 across the room's width and depth (0.5, 0.5 = centre; v = 1 is the back wall)
- "place": {"wall": "back"|"front"|"left"|"right", "along": 0..1}   one piece against a wall (along 0.5 = middle of that wall)
- "place": {"ring": {"centre": [u, v], "radius": metres, "count": n, "from": degrees, "to": degrees}}
      n copies evenly spaced on a circle or arc, each turned to face the centre. "size" is the size of ONE copy (a bench is about 2 m wide), not the whole row. Angle 0 points right (+x), 90 points to the back wall, 180 left, 270 to the front wall. 0 to 360 is a full circle; 200 to 340 is an arc on the front side of the centre, which is where an audience sits to watch something at the back.
- "place": {"corners": true}                  four copies, one near each corner

Rules: choose a room size that suits the space (a bedroom is about 4 x 4 x 2.6; a hall or theatre is 10 to 16 wide and 4 to 6 high). Use 3 to 12 pieces. Everything rests on the floor (base 0) unless it sits on top of another piece. A raised stage is a low, wide box or cylinder with base 0 and height 0.5 to 1. Curved rows of seating are rings that share one centre (the thing being watched) and have increasing radii, about 1.2 m apart, with more copies in the outer rows. A piece "by a window" goes on the same wall as the window, and you must also add the window. Leave the middle of the floor open unless the description puts something there. Do not include lights, torches, fabric, colours or materials: only large solid shapes.

Example for "a small chapel with two rows of pews facing an altar at the back":
{"room":{"width":8,"depth":12,"height":5},"pieces":[
 {"label":"altar","shape":"box","size":[2,1,0.8],"base":0,"place":{"wall":"back","along":0.5}},
 {"label":"pew","shape":"box","size":[2.6,0.9,0.5],"base":0,"place":{"at":[0.28,0.35]}},
 {"label":"pew","shape":"box","size":[2.6,0.9,0.5],"base":0,"place":{"at":[0.72,0.35]}},
 {"label":"pew","shape":"box","size":[2.6,0.9,0.5],"base":0,"place":{"at":[0.28,0.55]}},
 {"label":"pew","shape":"box","size":[2.6,0.9,0.5],"base":0,"place":{"at":[0.72,0.55]}},
 {"label":"column","shape":"cylinder","size":[0.25,5],"base":0,"place":{"corners":true}}]}

Example for "a round council chamber: speaker's platform in the middle, two curved rows of seats around the front half, pillars around the edge":
{"room":{"width":12,"depth":12,"height":5},"pieces":[
 {"label":"platform","shape":"cylinder","size":[1.5,0.5],"base":0,"place":{"at":[0.5,0.5]}},
 {"label":"seat","shape":"box","size":[1.6,0.5,0.5],"base":0,"place":{"ring":{"centre":[0.5,0.5],"radius":3,"count":6,"from":200,"to":340}}},
 {"label":"seat","shape":"box","size":[1.6,0.5,0.5],"base":0,"place":{"ring":{"centre":[0.5,0.5],"radius":4.2,"count":8,"from":200,"to":340}}},
 {"label":"pillar","shape":"cylinder","size":[0.3,5],"base":0,"place":{"ring":{"centre":[0.5,0.5],"radius":5.4,"count":8,"from":0,"to":360}}}]}

Example for "a reading room: sofa on the back wall, armchair by the window on the left wall, coffee table in the middle":
{"room":{"width":4,"depth":4,"height":2.6},"pieces":[
 {"label":"sofa","shape":"sofa","place":{"wall":"back","along":0.5}},
 {"label":"window","shape":"window","place":{"wall":"left","along":0.5}},
 {"label":"armchair","shape":"armchair","place":{"wall":"left","along":0.5}},
 {"label":"coffee table","shape":"coffee_table","place":{"at":[0.5,0.5]}}]}

Description: '''.replace("FURNITURE_NAMES", ", ".join(FURNITURE))

clamp = lambda v, lo, hi: max(lo, min(hi, v))
num = lambda v, d: float(v) if isinstance(v, (int, float)) else d
FOCUS = re.compile(r"stage|altar|platform|podium|screen|throne|pulpit|dais", re.I)
TINY = re.compile(r"torch|candle|light|lantern|flame|cloth|tent|fabric|curtain", re.I)

def placements(place, room, foot, focus):
    """-> list of (x, z, yaw) for one piece. foot = (width, depth) of its footprint."""
    W, _, D = room; fw, fd = foot
    if "wall" in place:
        a = clamp(num(place.get("along"), 0.5), 0, 1); wall = place["wall"]
        if wall in ("back", "front"):
            x = clamp(a * W, fw / 2 + 0.05, W - fw / 2 - 0.05)
            return [(x, D - fd / 2, math.pi)] if wall == "back" else [(x, fd / 2, 0.0)]
        z = clamp(a * D, fw / 2 + 0.05, D - fw / 2 - 0.05)
        return [(fd / 2, z, math.pi / 2)] if wall == "left" else [(W - fd / 2, z, -math.pi / 2)]
    if place.get("corners"):
        m = max(fw, fd) / 2 + 0.3
        return [(m, m, 0.0), (W - m, m, 0.0), (m, D - m, 0.0), (W - m, D - m, 0.0)]
    if "ring" in place:
        r = place["ring"]; cu, cv = (r.get("centre") or [0.5, 0.5])[:2]; cx, cz = clamp(cu, 0, 1) * W, clamp(cv, 0, 1) * D
        n = int(clamp(num(r.get("count"), 6), 1, 40)); a0, a1 = num(r.get("from"), 0), num(r.get("to"), 360)
        if a1 <= a0: a1 += 360
        span = min(a1 - a0, 360); full = span >= 359
        # keep the ring inside the room
        rad = clamp(num(r.get("radius"), 2), 0.5, min(cx, W - cx, cz, D - cz) - max(fw, fd) / 2 - 0.1) if min(cx, W - cx, cz, D - cz) > 1 else 0.5
        if not full and focus and math.hypot(focus[0] - cx, focus[1] - cz) > 0.5:
            mid = math.degrees(math.atan2(cz - focus[1], cx - focus[0]))     # an audience sits on the far side from what it watches
            a0 = mid - span / 2
        # copies must not overlap: shrink the count if the arc is too short for them
        n = max(1, min(n, int(math.radians(span) * rad / (fw * 1.08)) + (0 if full else 1)))
        out = []
        for i in range(n):
            th = math.radians(a0 + span * ((i + 0.0) / n if full else (i / (n - 1) if n > 1 else 0.5)))
            out.append((cx + rad * math.cos(th), cz + rad * math.sin(th), math.atan2(-math.cos(th), -math.sin(th))))
        return out
    u, v = (place.get("at") or [0.5, 0.5])[:2]
    return [(clamp(num(u, 0.5), 0, 1) * W, clamp(num(v, 0.5), 0, 1) * D, 0.0)]

def to_world(local, x, z, yaw):   # local (u, y, v) offset from the footprint centre -> world
    cs, sn = math.cos(yaw), math.sin(yaw)
    return [x + cs * local[0] + sn * local[2], local[1], z - sn * local[0] + cs * local[2]]

def expand(layout):
    r = layout.get("room") or {}
    room = [clamp(num(r.get("width"), 4), 3, 24), clamp(num(r.get("height"), 2.6), 2.4, 9), clamp(num(r.get("depth"), 4), 3, 24)]
    pieces = [p for p in layout.get("pieces", []) if isinstance(p, dict) and isinstance(p.get("place"), dict)]
    def foot(p):
        s = p.get("shape"); z = p.get("size") or []
        if s in FURNITURE: return FURNITURE[s]
        if s == "cylinder": rr = clamp(num(z[0] if z else None, 0.3), 0.08, 6); return (2 * rr, 2 * rr)
        return (clamp(num(z[0] if z else None, 1), 0.1, room[0]), clamp(num(z[2] if len(z) > 2 else None, 1), 0.1, room[2]))
    focus = None
    for p in pieces:
        if FOCUS.search(str(p.get("label", ""))) and "ring" not in p["place"]:
            x, z, _ = placements(p["place"], room, foot(p), None)[0]; focus = (x, z); break
    objs = []
    for p in pieces:
        label, s, z = str(p.get("label") or p.get("shape") or "piece")[:30], p.get("shape"), p.get("size") or []
        fw, fd = foot(p)
        if s not in FURNITURE and s not in ("box", "cylinder"): continue
        if s not in FURNITURE and (TINY.search(label) or min(fw, fd) < 0.12): continue      # lights and fabric are for the painter, not the blockout
        for x, zc, yaw in placements(p["place"], room, (fw, fd), focus):
            x, zc = clamp(x, min(fw, fd) / 2, room[0] - min(fw, fd) / 2), clamp(zc, min(fw, fd) / 2, room[2] - min(fw, fd) / 2)
            if s in FURNITURE:
                gap = 0.25 if s in ("armchair", "chair", "sofa", "desk") and any(q.get("shape") == "window" and q["place"].get("wall") == p["place"].get("wall") for q in pieces) and "wall" in p["place"] else 0
                prims = []
                for lo, hi in furniture_boxes(s, fw, fd):
                    c = [(lo[0] + hi[0]) / 2 - fw / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2 - fd / 2 + gap]
                    prims.append({"shape": "box", "c": to_world(c, x, zc, yaw), "h": [(hi[0] - lo[0]) / 2, (hi[1] - lo[1]) / 2, (hi[2] - lo[2]) / 2], "yaw": yaw})
            else:
                hgt = clamp(num(z[1] if len(z) > 1 else None, 1), 0.1, room[1]); base = 0.0   # everything settles onto the floor
                if s == "cylinder": prims = [{"shape": "cyl", "c": [x, base + hgt / 2, zc], "r": fw / 2, "hy": hgt / 2}]
                else: prims = [{"shape": "box", "c": [x, base + hgt / 2, zc], "h": [fw / 2, hgt / 2, fd / 2], "yaw": yaw}]
            objs.append({"name": label, "prims": prims})
    return room, objs[:80]

def ask(req, model="qwen3.5:9b"):
    body = json.dumps({"model": model, "stream": False, "think": False, "keep_alive": 0, "options": {"temperature": 0.1, "num_ctx": 6144}, "prompt": PROMPT + req}).encode()
    r = json.load(urllib.request.urlopen(urllib.request.Request("http://localhost:11434/api/generate", body), timeout=300))
    txt = r["response"]
    return json.loads(txt[txt.index("{"):txt.rindex("}") + 1]), r["total_duration"] / 1e9

if __name__ == "__main__":
    req, path = sys.argv[1], sys.argv[2]
    try:
        layout, secs = ask(req)
    except (ValueError, KeyError) as e:
        raise SystemExit("The layout model did not return a usable plan. Try describing the space more simply.")
    room, objs = expand(layout)
    if not objs: raise SystemExit("The layout model's plan had nothing solid in it. Try naming the main things in the space.")
    json.dump({"request": req, "room": room, "objects": objs}, open(path, "w"), indent=1)
    names = {}
    for o in objs: names[o["name"]] = names.get(o["name"], 0) + 1
    print(f"room {room[0]:g} x {room[2]:g} m, {room[1]:g} m high;", ", ".join(f"{n} x {k}" if n > 1 else k for k, n in names.items()))
    print("secs", round(secs, 1))
