"""Description -> local LLM writes a rough layout -> code checks it and expands it into primitives.
  llm_boxes.py "DESCRIPTION" OUT.json
Output: {"request", "room": [width, height, depth], "objects": [{"name", "prims": [primitive, ...]}]}  (see ../spike/blockout.py)
An object placed against a wall or in a ring also has "yaw": its front faces (sin yaw, 0, cos yaw). "focus": [x, z] is what an audience watches, if anything.
Only when the layout has them (all in room metres): "setting": "outdoor" and "surround" (the room is then the patch of ground to walk
on); "motions": [{"i": object index, "type": sway|swing|spin|bob|path, ..., "phase": 0..1, "sound"}]; "effects": swarms of small things
the viewer draws (wander, drift); "wind": {"strength": 0..1, "from": degrees}; "mood": {"feel", "energy", "time"}. An "arch" object has "open": true.
"grounds": [{"name", "c": [x, z], "h": [half width, half depth], "yaw"}] are the flat stretches the layout names (a road, a pond, a rug):
not objects, only told to the painter. "rules": 2 marks a layout written since cameras keep clear of posts (see chisel_ring.py).
The layout model is asked up to three times while faults() finds its layout poor for the description; the best is kept.
Environment: WORLD_SETTING (indoor or outdoor) overrides the layout model's choice.
"""
import json, sys, os, math, re, urllib.request, urllib.error

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

FEELS = ("calm", "warm", "bright", "dreamy", "playful", "mysterious", "melancholy", "eerie")
SOUNDS = ("rustle", "buzz", "rumble", "creak", "chirp", "none")
SOUND_FOR = {"sway": "rustle", "swing": "creak", "path": "rumble", "wander": "buzz"}     # the sound a motion has when none is given
LIFTED = ("swing", "spin", "bob", "path")       # motions that take a piece off its spot; a swaying piece stays rooted
POST = 0.12                                     # metres: the thickness of an arch's posts and beam

PROMPT = '''You design the rough 3D layout ("blockout") of a space, indoors or outdoors, from a description. Output JSON only.

{"setting": "indoor" or "outdoor",
 "room": {"width": metres (x), "depth": metres (z), "height": metres},
 "pieces": [ one object per thing or group of things ],
 "mood": {"feel": one of FEEL_NAMES, "energy": 0 (still) to 1 (lively), "time": "day" or "dusk" or "night"},
 "surround": outdoors only: at most 10 words for what is seen in the distance all around,
 "wind": outdoors only: {"strength": 0 (still air) to 1 (gale), "from": compass degrees},
 "effects": [ swarms of small moving things, see below; leave it out when there are none ]}

Each piece: {"label": short name, "shape": "box" or "cylinder" or "arch" or "ground" or a furniture name, "size": see below, "base": metres from the floor up to its underside (0 = on the floor), "place": one of the placements below, and only for a piece that moves: "motion" and "sound", see below}
- box size: [width, height, depth] in metres. cylinder size: [radius, height] in metres (cylinders stand upright).
- arch size: [width, height, depth] in metres: two posts with a beam across their tops and nothing between them (the frame of a swing, a gateway, a goal).
- ground size: [width, depth] in metres: a flat stretch of the ground or floor (a road, a path, a pond, a lawn, a rug). It takes up no space: other pieces stand on it or travel along it. Never use a box for these.
- furniture names, which need no size: FURNITURE_NAMES. Use these for ordinary rooms.
- "place": {"at": [u, v]}                     one piece; u and v are fractions 0..1 across the room's width and depth (0.5, 0.5 = centre; v = 1 is the back wall)
- "place": {"wall": "back"|"front"|"left"|"right", "along": 0..1}   one piece against a wall (along 0.5 = middle of that wall)
- "place": {"ring": {"centre": [u, v], "radius": metres, "count": n, "from": degrees, "to": degrees}}
      n copies evenly spaced on a circle or arc, each turned to face the centre. "size" is the size of ONE copy (a bench is about 2 m wide), not the whole row. Angle 0 points right (+x), 90 points to the back wall, 180 left, 270 to the front wall. 0 to 360 is a full circle; 200 to 340 is an arc on the front side of the centre, which is where an audience sits to watch something at the back.
- "place": {"on": label of another piece}     only for a moving piece that another piece holds up: it goes under an arch, or on the front of anything else
- "place": {"corners": true}                  FOUR copies, one near each corner. Only for things the description puts in every corner (pillars, lamps). A single thing "in the back left corner" is ONE piece: {"wall": "back", "along": 0} (back right: along 1; front left: {"wall": "front", "along": 0}; front right: along 1)

Rules: choose a room size that suits the space (a bedroom is about 4 x 4 x 2.6; a hall or theatre is 10 to 16 wide and 4 to 6 high). Use 3 to 12 pieces. Everything rests on the floor (base 0) unless it sits on top of another piece, or it hangs or floats and has a motion. A raised stage is a low, wide box or cylinder with base 0 and height 0.5 to 1. Curved rows of seating are rings that share one centre (the thing being watched) and have increasing radii, about 1.2 m apart, with more copies in the outer rows. A piece "by a window" goes on the same wall as the window, and you must also add the window. Leave the middle of the floor open unless the description puts something there. Do not include lights, torches, fabric, colours or materials: only large solid shapes. Pieces do not overlap or stand inside each other. Leave out nothing that the description names: each thing is a piece, a "ground" or an effect.

Outdoors: "room" is the patch of ground you can walk on, 10 to 16 m across; its "walls" are only the edges of that patch, and "height" is the height of the tallest thing. Put big things that bound the place (hedges, fences, house fronts, rows of trees) on the edges with "wall". Do not use "window".

Motion: most pieces stand still and have no "motion". Give one only to a thing the description says is moving, or that plainly would be (a tree on a windy day). One of:
- {"type": "sway", "amount": 0..1}     held at its base or along one edge and bending in the wind: trees, bushes, reeds, flags, hanging cloth
- {"type": "swing", "pivot": metres above the ground of the point it hangs from, "rope": metres of rope or chain between that point and the piece, "axis": "depth" or "width" (the piece's own direction it swings along), "angle": degrees to each side, 4 to 30}     hangs and rocks like a pendulum
- {"type": "spin", "axis": "up" or "width" or "depth", "period": seconds for one turn}     turns on the spot about its own centre. "axis" is the line it turns around: "up" for what turns flat like a carousel, a turntable or a ceiling fan; "depth" for what turns upright facing the front like a wheel, a clock hand or the sails of a windmill
- {"type": "bob", "height": metres, 0.02 to 0.3, "period": seconds}     rises and falls gently where it is
- {"type": "path", "points": [[u, v], [u, v]], "speed": metres per second (1 to 3: it takes 5 seconds or more to go by), "mode": "loop" or "back", "pause": seconds to wait between trips}     travels over the ground through 2 to 4 points (fractions like "at"). "loop": it leaves past the last point and comes in again at the first. "back": it goes there and back
For swing, spin and bob the part that moves is a piece of its own, apart from the still piece that holds it, and is placed "on" that piece: a swing is an "arch" (the frame, no motion) and a seat with the swing motion; a windmill is a tower (no motion) and thin upright sails that spin about "depth". A swing's "pivot" is the height of the beam it hangs from (indoors it may hang from the ceiling) and its "rope" is long when the piece hangs low: a seat hangs about 0.5 m above the ground. A spinning or bobbing piece off the ground has "base" above 0. Never add a piece for the ropes, chains, rods or mounts that hold a hanging thing.
A travelling piece has size [width, height, length], starts at its first point, and needs a clear strip along its points with no other piece on it. Several passing things (cars, carts, boats) are two or three such pieces, each with its own strip.
"sound", for a piece with a motion and for an effect: one of SOUND_NAMES (rustle: leaves and cloth; buzz: flies and bees; rumble: engines and wheels; creak: ropes and hinges; chirp: only birds; none: anything silent).

Effects: small or thin moving things (insects, birds, falling leaves, petals, snow, dust, sparks) are never pieces. Each kind is one entry in "effects":
- {"type": "wander", "label": short name, "at": [u, v], "radius": metres, "height": [lowest, highest] in metres, "count": 1 to 40, "size": metres across one of them, "speed": metres per second, "colours": ["#rrggbb", ...], "sound": ...}     things flying about one spot
- {"type": "drift", "label": short name, "at": [u, v], "radius": metres, "height": [lowest, highest] in metres, "count": 10 to 400, "size": metres across one of them, "fall": metres per second (0 = floating; below 0 = rising: sparks, bubbles, smoke), "colours": ["#rrggbb", ...], "sound": ...}     things falling or floating down through the air, carried by the wind
Either kind may have "glow": true for things that give off light (fireflies, sparks, embers), false for any that do not.

Example for "a small chapel with two rows of pews facing an altar at the back":
{"setting":"indoor","room":{"width":8,"depth":12,"height":5},"mood":{"feel":"calm","energy":0.2,"time":"day"},"pieces":[
 {"label":"altar","shape":"box","size":[2,1,0.8],"base":0,"place":{"wall":"back","along":0.5}},
 {"label":"pew","shape":"box","size":[2.6,0.9,0.5],"base":0,"place":{"at":[0.28,0.35]}},
 {"label":"pew","shape":"box","size":[2.6,0.9,0.5],"base":0,"place":{"at":[0.72,0.35]}},
 {"label":"pew","shape":"box","size":[2.6,0.9,0.5],"base":0,"place":{"at":[0.28,0.55]}},
 {"label":"pew","shape":"box","size":[2.6,0.9,0.5],"base":0,"place":{"at":[0.72,0.55]}},
 {"label":"column","shape":"cylinder","size":[0.25,5],"base":0,"place":{"corners":true}}]}

Example for "a round council chamber: speaker's platform in the middle, two curved rows of seats around the front half, pillars around the edge":
{"setting":"indoor","room":{"width":12,"depth":12,"height":5},"mood":{"feel":"mysterious","energy":0.4,"time":"day"},"pieces":[
 {"label":"platform","shape":"cylinder","size":[1.5,0.5],"base":0,"place":{"at":[0.5,0.5]}},
 {"label":"seat","shape":"box","size":[1.6,0.5,0.5],"base":0,"place":{"ring":{"centre":[0.5,0.5],"radius":3,"count":6,"from":200,"to":340}}},
 {"label":"seat","shape":"box","size":[1.6,0.5,0.5],"base":0,"place":{"ring":{"centre":[0.5,0.5],"radius":4.2,"count":8,"from":200,"to":340}}},
 {"label":"pillar","shape":"cylinder","size":[0.3,5],"base":0,"place":{"ring":{"centre":[0.5,0.5],"radius":5.4,"count":8,"from":0,"to":360}}}]}

Example for "a reading room: sofa on the back wall, armchair by the window on the left wall, coffee table in the middle":
{"setting":"indoor","room":{"width":4,"depth":4,"height":2.6},"mood":{"feel":"warm","energy":0.3,"time":"day"},"pieces":[
 {"label":"sofa","shape":"sofa","place":{"wall":"back","along":0.5}},
 {"label":"window","shape":"window","place":{"wall":"left","along":0.5}},
 {"label":"armchair","shape":"armchair","place":{"wall":"left","along":0.5}},
 {"label":"coffee table","shape":"coffee_table","place":{"at":[0.5,0.5]}}]}

Example for "a windy village green: a big oak at the back with leaves blowing off it, a hedge along the left, a child's swing in the middle, gnats over a flower tub on the right, and a lane along the front where a van goes by":
{"setting":"outdoor","room":{"width":14,"depth":12,"height":7},"mood":{"feel":"bright","energy":0.5,"time":"day"},
 "surround":"cottages and low hills beyond a hedge line","wind":{"strength":0.6,"from":250},"pieces":[
 {"label":"oak tree","shape":"cylinder","size":[1.8,7],"base":0,"place":{"wall":"back","along":0.5},"motion":{"type":"sway","amount":0.6},"sound":"rustle"},
 {"label":"hedge","shape":"box","size":[10,1.6,1],"base":0,"place":{"wall":"left","along":0.5},"motion":{"type":"sway","amount":0.3},"sound":"none"},
 {"label":"swing frame","shape":"arch","size":[2.2,2.4,0.3],"base":0,"place":{"at":[0.5,0.5]}},
 {"label":"swing seat","shape":"box","size":[0.5,0.1,0.25],"place":{"on":"swing frame"},"motion":{"type":"swing","pivot":2.3,"rope":1.7,"axis":"depth","angle":20},"sound":"creak"},
 {"label":"flower tub","shape":"cylinder","size":[0.5,0.6],"base":0,"place":{"at":[0.82,0.55]}},
 {"label":"lane","shape":"ground","size":[14,3],"place":{"wall":"front","along":0.5}},
 {"label":"van","shape":"box","size":[1.9,2.2,4.8],"base":0,"place":{"at":[0.08,0.12]},"motion":{"type":"path","points":[[0.08,0.12],[0.92,0.12]],"speed":2,"mode":"loop","pause":5},"sound":"rumble"}],
 "effects":[
 {"type":"wander","label":"gnats","at":[0.82,0.55],"radius":0.8,"height":[0.6,1.6],"count":14,"size":0.02,"speed":1,"colours":["#3a2a10","#6b5a2a"],"sound":"buzz"},
 {"type":"drift","label":"leaves","at":[0.5,0.8],"radius":4,"height":[0,6],"count":120,"size":0.05,"fall":0.6,"colours":["#c9682a","#8a9a3a"],"sound":"none"}]}

Example for "a mill yard at dusk: the mill at the back with its water wheel turning, a cart in the middle, a sign swinging in the gateway on the right":
{"setting":"outdoor","room":{"width":12,"depth":10,"height":6},"mood":{"feel":"calm","energy":0.3,"time":"dusk"},
 "surround":"dark woods along a stream","wind":{"strength":0.2,"from":200},"pieces":[
 {"label":"mill","shape":"box","size":[6,5,3],"base":0,"place":{"wall":"back","along":0.4}},
 {"label":"water wheel","shape":"box","size":[3,3,0.4],"base":0.4,"place":{"on":"mill"},"motion":{"type":"spin","axis":"depth","period":10},"sound":"creak"},
 {"label":"cart","shape":"box","size":[1.2,1,2],"base":0,"place":{"at":[0.5,0.45]}},
 {"label":"gateway","shape":"arch","size":[2.4,2.6,0.2],"base":0,"place":{"wall":"right","along":0.5}},
 {"label":"sign","shape":"box","size":[0.8,0.5,0.1],"place":{"on":"gateway"},"motion":{"type":"swing","pivot":2.5,"rope":0.2,"axis":"depth","angle":10},"sound":"creak"}]}

Description: '''.replace("FURNITURE_NAMES", ", ".join(FURNITURE)).replace("FEEL_NAMES", ", ".join(FEELS)).replace("SOUND_NAMES", ", ".join(SOUNDS))

clamp = lambda v, lo, hi: max(lo, min(hi, v))
num = lambda v, d: float(v) if isinstance(v, (int, float)) and math.isfinite(v) else d   # the model's numbers can be missing, text or NaN
pair = lambda v: (list(v) + [None, None])[:2] if isinstance(v, (list, tuple)) else [None, None]
WALLS = ("back", "front", "left", "right")
FOCUS = re.compile(r"stage|altar|platform|podium|screen|throne|pulpit|dais", re.I)
TINY = re.compile(r"torch|candle|light|lantern|flame|cloth|tent|fabric|curtain", re.I)

def placements(place, room, foot, focus):
    """-> list of (x, z, yaw) for one piece. foot = (width, depth) of its footprint."""
    W, _, D = room; fw, fd = foot
    if "wall" in place:
        a = clamp(num(place.get("along"), 0.5), 0, 1); wall = place["wall"]
        if not isinstance(wall, str) or wall not in WALLS: return []        # an unknown wall name used to mean the right wall
        if wall in ("back", "front"):
            x = clamp(a * W, fw / 2 + 0.05, W - fw / 2 - 0.05)
            return [(x, D - fd / 2, math.pi)] if wall == "back" else [(x, fd / 2, 0.0)]
        z = clamp(a * D, fw / 2 + 0.05, D - fw / 2 - 0.05)
        return [(fd / 2, z, math.pi / 2)] if wall == "left" else [(W - fd / 2, z, -math.pi / 2)]
    if place.get("corners"):
        m = max(fw, fd) / 2 + 0.3
        return [(m, m, 0.0), (W - m, m, 0.0), (m, D - m, 0.0), (W - m, D - m, 0.0)]
    if "ring" in place:
        r = place["ring"]
        if not isinstance(r, dict): return []
        cu, cv = pair(r.get("centre")); cx, cz = clamp(num(cu, 0.5), 0, 1) * W, clamp(num(cv, 0.5), 0, 1) * D
        n = int(clamp(num(r.get("count"), 6), 1, 40)); a0, a1 = num(r.get("from"), 0), num(r.get("to"), 360)
        if a1 <= a0: a1 = a0 + ((a1 - a0) % 360 or 360)
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
    u, v = pair(place.get("at"))
    return [(clamp(num(u, 0.5), 0, 1) * W, clamp(num(v, 0.5), 0, 1) * D, 0.0)]

def to_world(local, x, z, yaw):   # local (u, y, v) offset from the footprint centre -> world
    cs, sn = math.cos(yaw), math.sin(yaw)
    return [x + cs * local[0] + sn * local[2], local[1], z - sn * local[0] + cs * local[2]]

def fit(prims, room, shrink):
    """Move one placed piece (all its primitives together) so its yaw-rotated extent lies inside the room.
    A single box or cylinder that is larger than the room is shrunk first; anything else too large is centred."""
    def ext(p):
        if p["shape"] == "cyl": return p["r"], p["r"]
        cs, sn = abs(math.cos(p["yaw"])), abs(math.sin(p["yaw"]))
        return cs * p["h"][0] + sn * p["h"][2], sn * p["h"][0] + cs * p["h"][2]
    if shrink and len(prims) == 1:
        p = prims[0]; hx, hz = ext(p); k = min(1.0, room[0] / (2 * hx), room[2] / (2 * hz))
        if k < 1:
            if p["shape"] == "cyl": p["r"] *= k
            else: p["h"][0] *= k; p["h"][2] *= k
    for ax, L in ((0, room[0]), (2, room[2])):
        lo = min(p["c"][ax] - ext(p)[ax // 2] for p in prims); hi = max(p["c"][ax] + ext(p)[ax // 2] for p in prims)
        move = (L - lo - hi) / 2 if hi - lo >= L else clamp(lo, 0, L - (hi - lo)) - lo
        for p in prims: p["c"][ax] += move

def sound(v, kind): return v if isinstance(v, str) and v in SOUNDS else SOUND_FOR.get(kind, "none")

def motion(p):
    """A piece's motion as the layout model wrote it -> its checked numbers, or None. What depends on where the piece
    ends up (a path's points, a swing's pivot, period and angle) is settled by route() and hang()."""
    m = p.get("motion"); m = {"type": m} if isinstance(m, str) else m
    t = m.get("type") if isinstance(m, dict) else None
    if t == "sway": q = {"amount": clamp(num(m.get("amount"), 0.6), 0, 1), "stiff": clamp(num(m.get("stiff"), 0.35), 0, 0.8)}
    elif t == "swing": q = {"pivot": num(m.get("pivot"), None), "axis": "width" if m.get("axis") == "width" else "depth", "angle": clamp(num(m.get("angle"), 20), 4, 30), "period": num(m.get("period"), None), "rope": num(m.get("rope"), None)}
    elif t == "spin": q = {"axis": m["axis"] if m.get("axis") in ("up", "width", "depth") else "up", "period": clamp(num(m.get("period"), 8), 1, 60)}
    elif t == "bob": q = {"height": clamp(num(m.get("height"), 0.1), 0.02, 0.3), "period": clamp(num(m.get("period"), 3), 1.5, 8)}
    elif t == "path":
        pts = [pair(q) for q in m["points"]][:4] if isinstance(m.get("points"), list) else []
        q = {"points": [[clamp(u, 0, 1), clamp(v, 0, 1)] for u, v in pts if num(u, None) is not None and num(v, None) is not None],
             "speed": clamp(num(m.get("speed"), 2), 0.2, 4), "mode": m["mode"] if m.get("mode") in ("loop", "back") else None, "pause": clamp(num(m.get("pause"), 4), 0, 30)}
    else: return None
    s = p.get("sound") if isinstance(p.get("sound"), str) and p["sound"] in SOUNDS else m.get("sound")
    return {"type": t, **q, "sound": sound(s, t)}

def route(pts, foot, room):
    """A travelling piece's points (fractions of the room) -> (points in metres, yaw), or None when they make no path of
    at least 1 m. The piece's length (its depth) lies along the first leg and its front faces the way it goes; the points
    are kept far enough from the edges that the piece is inside the room all the way: by its extent along a straight path,
    by its half-diagonal on one that bends, since it turns as it goes."""
    W, _, D = room; fw, fd = foot
    pts = [[u * W, v * D] for u, v in pts]
    for _ in range(6):
        pts = [q for k, q in enumerate(pts) if not k or math.dist(q, pts[k - 1]) > 0.05]
        if len(pts) < 2: return None
        yaw = math.atan2(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]); cs, sn = abs(math.cos(yaw)), abs(math.sin(yaw))
        bent = any(abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) > 1e-6 for a, b, c in zip(pts, pts[1:], pts[2:]))
        ex, ez = (math.hypot(fw, fd) / 2,) * 2 if bent else ((cs * fw + sn * fd) / 2, (sn * fw + cs * fd) / 2)
        ex, ez = min(ex, W / 2), min(ez, D / 2)
        new = [[clamp(x, ex, W - ex), clamp(z, ez, D - ez)] for x, z in pts]
        if new == pts: return (pts, yaw) if sum(math.dist(a, b) for a, b in zip(pts, pts[1:])) >= 1 else None
        pts = new
    return None

def aside(pts, fw, lanes):
    """How far sideways (dx, dz) a straight two-point path of this width must move to have a strip of its own beside an
    earlier one that runs the same or the opposite way; (0, 0) when it already has."""
    (x0, z0), (x1, z1) = pts; L = math.dist(*pts); dx, dz = (x1 - x0) / L, (z1 - z0) / L
    for (a, b), w in lanes:
        if math.dist(a, b) < 1e-6: continue
        if abs(dx * (b[1] - a[1]) - dz * (b[0] - a[0])) > 0.2 * math.dist(a, b): continue      # it crosses: not checked
        s = (a[0] - x0) * dz - (a[1] - z0) * dx; gap = (fw + w) / 2 + 0.3                      # s: how far to the right the earlier one runs
        if abs(s) < gap - 1e-6: k = (gap + 0.01 - abs(s)) * (-1 if s >= 0 else 1); return dz * k, -dx * k
    return 0, 0

def along(pts, fw, strips):
    """A straight two-point path that runs along a long stretch of ground (within about 15 degrees, starting on it or
    within 0.5 m of its side) but partly off it -> the same path moved sideways onto it and made parallel to it, in
    metres. None when it follows no stretch, or is on one already."""
    L = math.dist(*pts)
    for gx, gz, ux, uz, half, wide in strips:
        a0, a1 = ((x - gx) * ux + (z - gz) * uz for x, z in pts); s0, s1 = ((x - gx) * uz - (z - gz) * ux for x, z in pts)
        if abs(a1 - a0) < 0.96 * L or abs(a0) > half + 1 or abs(s0) > wide / 2 + 0.5: continue
        lim = max(0.0, (wide - fw) / 2)
        if abs(s0) <= lim + 1e-9 and abs(s1) <= lim + 1e-9: return None
        s = clamp(s0, -lim, lim)
        return [[gx + ux * a + uz * s, gz + uz * a - ux * s] for a in (a0, a1)]
    return None

def blocked(pts, w, top, objs, skip):
    """Whether a piece w wide and top high, travelling through pts, runs into an object (other than those in skip).
    What it passes under, like the beam of an arch, does not count; nor does what it meets after its last point, on
    its way out of an outdoor place."""
    line = pts
    for i, o in enumerate(objs):
        for p in ([] if i in skip else o["prims"]):
            cyl = p["shape"] == "cyl"; cs, sn = (1, 0) if cyl else (abs(math.cos(p["yaw"])), abs(math.sin(p["yaw"])))
            if p["c"][1] - (p["hy"] if cyl else p["h"][1]) >= top: continue
            ex, ez = (p["r"], p["r"]) if cyl else (cs * p["h"][0] + sn * p["h"][2], sn * p["h"][0] + cs * p["h"][2])
            for a, b in zip(line, line[1:]):
                n = max(1, int(math.dist(a, b) / 0.2))
                if any(abs(a[0] + (b[0] - a[0]) * k / n - p["c"][0]) < ex + w / 2 - 0.05 and abs(a[1] + (b[1] - a[1]) * k / n - p["c"][2]) < ez + w / 2 - 0.05 for k in range(n + 1)): return True
    return False

def hang(q, base, hgt, half, top):
    """Settle a swing whose piece spans base..base + hgt and reaches `half` to each side along its swing: the pivot is at
    or above the piece (and no higher than top), the period is a pendulum's of that length, and the angle is shrunk until
    the arc stays 0.1 m clear of the ground. -> False if it cannot be."""
    pivot = clamp(q["pivot"] if q["pivot"] is not None else base + hgt + 1.5, base + hgt, max(top, base + hgt))
    d = pivot - base; worst = math.atan2(half, d)        # the turn at which a lower corner is lowest
    low = lambda deg: pivot - (d * math.cos(min(math.radians(deg), worst)) + half * math.sin(min(math.radians(deg), worst)))
    angle = q["angle"]
    while angle > 4 and low(angle) < 0.1: angle = max(4, angle - 1)
    if low(angle) < 0.1: return False
    q.update(pivot=pivot, angle=angle, period=clamp(q["period"] or 2 * math.pi * math.sqrt((pivot - base - hgt / 2) / 9.8), 1.5, 6))
    return True

def lift(q, hgt, fw, fd, top):
    """The lowest and highest base at which a spinning or bobbing piece of this size clears the ground by 0.1 m (a bob: by
    nothing) and stays under top; lowest > highest when it cannot."""
    if q["type"] == "bob": return q["height"], top - hgt - q["height"]
    if q["type"] == "spin" and q["axis"] != "up":
        r = math.hypot((fd if q["axis"] == "width" else fw) / 2, hgt / 2)        # it tumbles: its corners sweep a circle about its centre
        return r + 0.1 - hgt / 2, top - r - hgt / 2
    return 0, top - hgt

def reach(q, a, b, lo, hgt):
    """How far a swinging or spinning piece gets from its centre along its own width and depth; a, b are its half-sizes."""
    if q["type"] == "spin":
        if q["axis"] == "up": return (math.hypot(a, b),) * 2
        return (a, math.hypot(b, hgt / 2)) if q["axis"] == "width" else (math.hypot(a, hgt / 2), b)
    d = q["pivot"] - lo; half = a if q["axis"] == "width" else b
    th = min(math.radians(q["angle"]), math.atan2(d, half)); far = d * math.sin(th) + half * math.cos(th)
    return (far, b) if q["axis"] == "width" else (a, far)

def effect(e, room):
    """One swarm of small things the viewer draws -> checked, in room metres; None if it is not one."""
    if not isinstance(e, dict) or not isinstance(e.get("type"), str) or e["type"] not in ("wander", "drift"): return None
    W, H, D = room; t = e["type"]; fly = t == "wander"
    u, v = pair(e.get("at")); lo, hi = pair(e.get("height"))
    lo = clamp(num(lo, 0.3 if fly else 0), 0, H); hi = clamp(num(hi, 1.5 if fly else H), lo + 0.1, max(H, lo + 0.1))
    cols = [c.lower() for c in e["colours"] if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c)][:4] if isinstance(e.get("colours"), list) else []
    return {"type": t, "label": str(e.get("label") or t)[:30], "at": [clamp(num(u, 0.5), 0, 1) * W, clamp(num(v, 0.5), 0, 1) * D],
            "radius": clamp(num(e.get("radius"), 1.2 if fly else 3), 0.3, 6 if fly else 12), "height": [lo, hi],
            "count": int(clamp(num(e.get("count"), 12 if fly else 100), 1 if fly else 10, 40 if fly else 400)),
            "size": clamp(num(e.get("size"), 0.03 if fly else 0.05), 0.01, 0.3 if fly else 0.15),
            **({"speed": clamp(num(e.get("speed"), 1), 0.2, 4)} if fly else {"fall": -abs(clamp(num(e.get("fall"), 0.5), -2, 2)) if e.get("rise") is True else clamp(num(e.get("fall"), 0.5), -2, 2)}),
            **({"glow": e["glow"]} if isinstance(e.get("glow"), bool) else {}), **({"opacity": clamp(num(e.get("opacity"), 0.95), 0.05, 1)} if "opacity" in e else {}),
            "colours": cols or ["#777777"], "sound": sound(e.get("sound"), t)}

def expand(layout, info=None, setting=None):
    """-> (room, objects). info, if given, receives "focus": the floor point an audience faces; and, only when the layout
    has them, "setting" and "surround" (outdoors), "motions", "effects", "wind" and "mood".
    setting: "indoor" or "outdoor" to overrule the layout (default: the environment's WORLD_SETTING, if it is one of those)."""
    if not isinstance(layout, dict): layout = {}
    if setting is None: setting = os.environ.get("WORLD_SETTING")
    out = (setting if setting in ("indoor", "outdoor") else layout.get("setting")) == "outdoor"
    r = layout.get("room") if isinstance(layout.get("room"), dict) else {}
    room = [clamp(num(r.get("width"), 4), 3, 24), clamp(num(r.get("height"), 2.6), 2.4, 9), clamp(num(r.get("depth"), 4), 3, 24)]
    if out: room[1] = clamp(num(r.get("height"), 6), 3, 12)      # the tallest thing, not a ceiling
    pieces = layout.get("pieces") if isinstance(layout.get("pieces"), list) else []
    pieces = [{**p, "place": {}} if isinstance(p, dict) and isinstance(p.get("motion"), dict) and not isinstance(p.get("place"), dict) else p for p in pieces]   # a moving piece may give only its points
    pieces = [p for p in pieces if isinstance(p, dict) and isinstance(p.get("place"), dict) and isinstance(p.get("shape"), str)]
    def size(p):     # a bare number is taken as the width or radius; anything else that is not a list is ignored
        z = p.get("size"); return list(z) if isinstance(z, (list, tuple)) else [z] if isinstance(z, (int, float)) else []
    def foot(p):
        s = p.get("shape"); z = size(p)
        if s in FURNITURE: return FURNITURE[s]
        if s == "cylinder": rr = clamp(num(z[0] if z else None, 0.3), 0.08, min(6, room[0] / 2, room[2] / 2)); return (2 * rr, 2 * rr)
        side = p["place"].get("wall") in ("left", "right")              # on a side wall the width runs along the room's depth
        if s == "arch": return (clamp(num(z[0] if z else None, 2), 0.5, room[2] if side else room[0]), clamp(num(z[2] if len(z) > 2 else None, POST), POST, room[0] if side else room[2]))
        return (clamp(num(z[0] if z else None, 1), 0.1, room[2] if side else room[0]), clamp(num(z[2] if len(z) > 2 else None, 1), 0.1, room[0] if side else room[2]))
    focus = None
    for p in pieces:
        if FOCUS.search(str(p.get("label", ""))) and "ring" not in p["place"]:
            at = placements(p["place"], room, foot(p), None)
            if at: focus = at[0][:2]; break
    if info is not None and focus: info["focus"] = [float(focus[0]), float(focus[1])]
    objs, motions, lanes, held, strips, travel, walled, grounds = [], [], {}, {}, [], {}, [], []      # lanes: the strip each travelling object uses; held: label -> where its first copy stands; strips: long stretches of ground
    for p in pieces:      # a road, a path, a rug: nothing is built, but the painter is told where it lies, and a long one is somewhere to travel along
        if p.get("shape") != "ground": continue
        try:
            z = size(p); gw, gd = (clamp(num(z[k] if len(z) > k else None, 2), 0.5, 24) for k in (0, 1))
            at = placements(p["place"], room, (gw, gd), focus)
            for x, zc, yaw in at[:1] if max(gw, gd) >= 2 * min(gw, gd) else []:
                strips.append((x, zc, *((math.cos(yaw), -math.sin(yaw)) if gw >= gd else (math.sin(yaw), math.cos(yaw))), max(gw, gd) / 2, min(gw, gd)))
            grounds += [{"name": str(p.get("label") or "ground")[:30], "c": [float(x), float(zc)], "h": [gw / 2, gd / 2], "yaw": float(yaw)} for x, zc, yaw in at]
        except Exception as e: print("skipped a stretch of ground the layout model wrote badly:", type(e).__name__, e, file=sys.stderr)
    for p in pieces:
      try:
        label, s, z = str(p.get("label") or p.get("shape") or "piece")[:30], p.get("shape"), size(p)
        fw, fd = foot(p)
        if s not in FURNITURE and s not in ("box", "cylinder", "arch"): continue
        if out and s == "window": continue
        try: mo = motion(p) if "motion" in p else None
        except Exception: mo = None      # a motion written badly is dropped and the piece kept
        frail = s not in FURNITURE and bool(TINY.search(label) or min(fw, fd) < 0.12)      # lights and fabric are for the painter, not the blockout,
        if frail and not mo: continue                                                       # unless they move: then they are kept, but only while they do
        if s == "box" and "wall" in p["place"] and mo and mo["type"] == "sway" and fw < min(fd / 3, 0.31): fw, fd = fd, fw       # a thin sheet waving on a wall lies flat against it
        at = placements(p["place"], room, (fw, fd), focus)
        edge = out and "wall" in p["place"] and len(at) == 1
        for _ in range(2 if edge else 0):      # outdoors an edge can be taken already, by a house front or a hedge: this piece stands in front of that
            for bx, bz, ex, ez in walled:
                x, zc, yaw = at[0]; n = (math.sin(yaw), math.cos(yaw))
                if abs(x - bx) < ex and abs(zc - bz) < ez: at = [(bx + n[0] * (ex + fd / 2), zc, yaw) if abs(n[0]) > 0.5 else (x, bz + n[1] * (ez + fd / 2), yaw)]
        on = held.get(p["place"]["on"].strip().lower()) if isinstance(p["place"].get("on"), str) else None
        if on:      # held up by another piece: inside an open one (an arch), on the front of any other
            off = 0 if on[4] else (on[3] + fd) / 2
            at = [(on[0] + math.sin(on[2]) * off, on[1] + math.cos(on[2]) * off, on[2])]
        full = lambda: len(motions) >= 40 or (mo["type"] in LIFTED and sum(m["type"] in LIFTED for m in motions) >= 12)
        if mo and (len(objs) >= 80 or full()): mo = None
        if mo and mo["type"] == "path":      # a travelling piece stands at its first point, facing the way it goes
            got = route(mo["points"], (fw, fd), room)
            onto = along(got[0], fw, strips) if got and len(got[0]) == 2 else None      # it runs along a road but partly off it: onto the road
            if onto: got = route([[x / room[0], zz / room[2]] for x, zz in onto], (fw, fd), room) or got
            if got and len(got[0]) == 2 and any(aside(got[0], fw, lanes.values())):      # another piece already travels this strip: go beside it
                dx, dz = aside(got[0], fw, lanes.values())
                got = route([[(x + dx) / room[0], (zz + dz) / room[2]] for x, zz in got[0]], (fw, fd), room)
                if not got or len(got[0]) != 2 or any(aside(got[0], fw, lanes.values())): continue      # no room beside it: one of them is enough
            if got: mo["points"] = got[0]; mo["mode"] = (mo["mode"] or "loop") if out else "back"; at = [(*got[0][0], got[1])]; lanes[len(objs)] = (got[0][:2], fw)
            else: mo = None
        if frail and not mo: continue
        for x, zc, yaw in at:
            still = False
            if s in FURNITURE:
                gap = 0.25 if s in ("armchair", "chair", "sofa", "desk") and any(q.get("shape") == "window" and q["place"].get("wall") == p["place"].get("wall") for q in pieces) and "wall" in p["place"] else 0
                prims = []
                for lo, hi in furniture_boxes(s, fw, fd):
                    c = [(lo[0] + hi[0]) / 2 - fw / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2 - fd / 2 + gap]
                    prims.append({"shape": "box", "c": to_world(c, x, zc, yaw), "h": [(hi[0] - lo[0]) / 2, (hi[1] - lo[1]) / 2, (hi[2] - lo[2]) / 2], "yaw": yaw})
            elif s == "arch":
                hgt = clamp(num(z[1] if len(z) > 1 else None, 2.4), 0.5, room[1])
                prims = [{"shape": "box", "c": to_world([u, (hgt - POST) / 2, 0], x, zc, yaw), "h": [POST / 2, (hgt - POST) / 2, fd / 2], "yaw": yaw} for u in (POST / 2 - fw / 2, fw / 2 - POST / 2)]
                prims.append({"shape": "box", "c": to_world([0, hgt - POST / 2, 0], x, zc, yaw), "h": [fw / 2, POST / 2, fd / 2], "yaw": yaw})
            else:
                hgt = clamp(num(z[1] if len(z) > 1 else None, 1), 0.1, room[1]); base = 0.0   # everything settles onto the floor
                if mo:      # but what hangs or floats, and moves; it is raised if it would dip into the ground
                    b0, b1 = lift(mo, hgt, fw, fd, 12 if out else room[1]); b1 = min(b1, max(b0, room[1] - hgt))
                    if on: b1 = min(b1, max(b0, on[5] - hgt))      # what a piece holds up is no higher than itself
                    roped = mo["type"] == "swing" and mo["rope"] is not None and mo["pivot"] is not None      # a rope's length says how low it hangs
                    if mo["type"] == "path": pass
                    elif b0 > b1: still = True
                    else: base = clamp(max(0.3, mo["pivot"] - max(mo["rope"], 0) - hgt) if roped else num(p.get("base"), 0), b0, b1)
                if s == "cylinder": prims = [{"shape": "cyl", "c": [x, base + hgt / 2, zc], "r": fw / 2, "hy": hgt / 2}]
                else: prims = [{"shape": "box", "c": [x, base + hgt / 2, zc], "h": [fw / 2, hgt / 2, fd / 2], "yaw": yaw}]
            was = prims[0]["c"][::2]
            fit(prims, room, s not in FURNITURE)        # nothing may poke through a wall: the depth maps would slice it
            if edge and len(prims) == 1:
                cs, sn = abs(math.cos(yaw)), abs(math.sin(yaw)); q = prims[0]; e = (q["r"], q["r"]) if q["shape"] == "cyl" else (q["h"][0], q["h"][2])
                walled.append((q["c"][0], q["c"][2], cs * e[0] + sn * e[1], sn * e[0] + cs * e[1]))
            held.setdefault(label.strip().lower(), (x + prims[0]["c"][0] - was[0], zc + prims[0]["c"][2] - was[1], yaw, fd, s == "arch", max(q["c"][1] + (q["hy"] if q["shape"] == "cyl" else q["h"][1]) for q in prims)))
            faces = "wall" in p["place"] or "ring" in p["place"] or bool(on)       # elsewhere the turn is 0 and means nothing: shapes.py chooses a facing
            one = dict(mo) if mo and not still and len(objs) < 80 and not full() else None        # each copy moves on its own
            try:
                lo, hi = min(q["c"][1] - (q["hy"] if q["shape"] == "cyl" else q["h"][1]) for q in prims), max(q["c"][1] + (q["hy"] if q["shape"] == "cyl" else q["h"][1]) for q in prims)
                a, b = (prims[0]["r"],) * 2 if prims[0]["shape"] == "cyl" else prims[0]["h"][::2] if len(prims) == 1 else (fw / 2, fd / 2)
                if one and one["type"] == "sway" and hi - lo < 2 * min(a, b): one = None      # only what stands taller than it is thick can bend: a low, wide thing is rigid
                if one and s not in ("box", "cylinder") and one["type"] in ("spin", "bob") and lift(one, hi, 2 * a, 2 * b, hi + 99)[0] > 0: one = None    # furniture and arches stand on the floor
                if one and one["type"] == "path":
                    faces = True
                    if math.dist(prims[0]["c"][::2], was) > 1e-6: one = None      # it had to be moved to fit, off its path: it stays where it is
                if one and one["type"] == "swing":
                    if not hang(one, lo, hi - lo, a if one["axis"] == "width" else b, room[1]): one = None
                if one and not out and one["type"] in ("swing", "spin"):      # indoors it must also miss the walls: it is pulled in by its reach
                    ra, rb = reach(one, a, b, lo, hi - lo); cs, sn = abs(math.cos(yaw)), abs(math.sin(yaw))
                    cx, cz = x + prims[0]["c"][0] - was[0], zc + prims[0]["c"][2] - was[1]
                    for ax, c, e, L in ((0, cx, cs * ra + sn * rb, room[0]), (2, cz, sn * ra + cs * rb, room[2])):
                        if e > L / 2: one = None; break
                    else:
                        for ax, c, e, L in ((0, cx, cs * ra + sn * rb, room[0]), (2, cz, sn * ra + cs * rb, room[2])):
                            for q in prims: q["c"][ax] += clamp(c, e, L - e) - c
            except Exception: one = None
            if frail and not one: continue
            if one and one["type"] == "path": travel[len(objs)] = (fw, fd, hi)
            if one: motions.append({"i": len(objs), "type": one.pop("type"), **{k: v for k, v in one.items() if k not in ("sound", "rope")}, "phase": round(len(motions) * 0.6180339887 % 1, 3), "sound": one["sound"]})
            objs.append({"name": label, "prims": prims, **({"open": True} if s == "arch" else {}), **({"yaw": yaw} if faces else {})})
      except Exception as e:      # one malformed piece must not fail the whole world
        print("skipped a piece the layout model wrote badly:", type(e).__name__, e, file=sys.stderr)
    for m in [m for m in motions if m["type"] == "path"]:      # a travelling piece must not run into the others
        i = m["i"]; fw, fd, top = travel[i]; o = objs[i]; others = [v for k, v in lanes.items() if k != i]
        skip = {q["i"] for q in motions if q["type"] == "path"}
        ok = lambda pts: not blocked(pts, fw, top, objs, skip) and (len(pts) != 2 or not any(aside(pts, fw, others)))
        if ok(m["points"]): continue
        (x0, z0), (x1, z1) = m["points"][:2]; L = math.dist(*m["points"][:2]); tries = []
        for gx, gz, ux, uz, half, wide in strips:      # it starts on a long stretch of ground: it follows that
            if abs((x0 - gx) * ux + (z0 - gz) * uz) < half + 1 and abs((x0 - gx) * uz - (z0 - gz) * ux) < wide / 2 + 1:
                k = half if (x1 - x0) * ux + (z1 - z0) * uz >= 0 else -half
                tries.append([[gx - ux * k, gz - uz * k], [gx + ux * k, gz + uz * k]])
        tries += [[[x + (z1 - z0) / L * k, z - (x1 - x0) / L * k] for x, z in m["points"]] for d in (0.5, 1, 1.5, 2, 2.5, 3) for k in (d, -d)]      # or a clear strip beside it
        for pts in tries if len(o["prims"]) == 1 else []:
            got = route([[x / room[0], z / room[2]] for x, z in pts], (fw, fd), room)
            if got and ok(got[0]):
                m["points"] = got[0]; lanes[i] = (got[0][:2], fw); o["yaw"] = got[1]; o["prims"][0]["c"][0], o["prims"][0]["c"][2] = got[0][0]
                if "yaw" in o["prims"][0]: o["prims"][0]["yaw"] = got[1]
                break
        else: motions.remove(m); lanes.pop(i, None)      # nowhere to go: it stays where it is
    for m in motions:      # a travelling thing takes at least 5 s over its route: any faster and it is gone before it is seen
        if m["type"] == "path": m["speed"] = min(m["speed"], max(0.2, sum(math.dist(a, b) for a, b in zip(m["points"], m["points"][1:])) / 5))
    if info is not None:
        effects = [e for e in (effect(e, room) for e in (layout.get("effects") if isinstance(layout.get("effects"), list) else [])) if e][:4]
        if out:
            info["setting"] = "outdoor"
            info["surround"] = re.sub(r"\s+", " ", layout["surround"]).strip()[:120] if isinstance(layout.get("surround"), str) else ""
        w = layout.get("wind") if isinstance(layout.get("wind"), dict) else {}
        if out or any(m["type"] == "sway" for m in motions) or any(e["type"] == "drift" for e in effects):     # only where something answers to it
            info["wind"] = {"strength": clamp(num(w.get("strength"), 0.4 if out else 0.2), 0, 1), "from": num(w.get("from"), 270) % 360}
        m = layout.get("mood")
        if isinstance(m, dict):
            info["mood"] = {**({"feel": m["feel"]} if isinstance(m.get("feel"), str) and m["feel"] in FEELS else {}), "energy": clamp(num(m.get("energy"), 0.5), 0, 1),
                            **({"time": m["time"]} if isinstance(m.get("time"), str) and m["time"] in ("day", "dusk", "night") else {})}
        if motions: info["motions"] = motions
        if effects: info["effects"] = effects
        if grounds: info["grounds"] = grounds[:8]
    return room, objs[:80]

# ---------------------------------------------------------------- is a layout any good for its description?
# No model is asked: only what can be read off the words. Parts of speech, not kinds of object.
COUNTS = {"a": 1, "an": 1, "one": 1, "some": 1, "several": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
STOPS = set("on in at by with and or to from along around across over under behind beside near where that which who is are has have against between into through above below next for as while but then so it its each every the".split())
VAGUE = set("back front left right middle centre center side sides corner corners edge edges end ends top bottom half wall walls floor ceiling row rows day night dusk dawn morning evening afternoon noon sunset sunrise breeze wind way view distance background foreground light shade few lot bit kind sort number".split())   # places, times and amounts: never things to build
UNITS = set("m cm mm metre metres meter meters ft foot feet inch inches x by storey storeys story stories".split())
POOR = 2        # a layout with faults weighing this much is asked for again

def stem(w):
    """A word without its plural or possessive ending, near enough to compare a description with labels."""
    w = re.sub(r"'s$", "", w.lower())
    for end, new in (("ies", "y"), ("ches", "ch"), ("shes", "sh"), ("sses", "ss"), ("xes", "x")):
        if w.endswith(end) and len(w) > len(end) + 1: return w[:-len(end)] + new
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")) else w
like = lambda w: re.sub(r"(?<=.[a-z])ve$|(?<=.[a-z])fe$", "f", w)      # leaf, leave(s)
def same(a, b):      # the same word (leaf, leave(s)), or one ends a compound of the other (shelf, bookshelf)
    a, b = sorted((re.sub(r"(?<=.[a-z])ve$|(?<=.[a-z])fe$", "f", w) for w in (a, b)), key=len); return a == b or (len(a) >= 4 and b.endswith(a))
stems = lambda t: [stem(w) for w in re.findall(r"[a-z]+", t.lower())] if isinstance(t, str) else []
PLACES = {stem(w) for w in VAGUE}

def named(req):
    """The things a description brings in with "a", "an", "some" or a number: [(how many, head noun, words, as written)],
    head (the word that is counted) and words as stems. "two rows of pews" has the head "row" and the words "pew" (rows
    are VAGUE); a verb that follows ("a car drives past") stays among the words, where it does no harm. Left out: what
    comes before a colon, or else the first of them at the start (the place itself); what follows "in" (in a circle, in
    a corner); measures (3 m)."""
    t = re.findall(r"[a-z]+(?:'s)?|\d+|[^\sa-z\d]", req.lower()) if isinstance(req, str) else []
    first = t.index(":") + 1 if ":" in t else 0; out = []
    for i in range(first, len(t)):
        n = COUNTS.get(t[i]) or (int(t[i]) if t[i].isdigit() and 0 < int(t[i]) <= 40 and t[i + 1:i + 2] and t[i + 1] not in UNITS else 0)
        if not n or (i and t[i - 1] == "in") or (not first and not i): continue
        j = i + 1
        if t[j:j + 2] in (["pair", "of"], ["couple", "of"]): n, j = 2, j + 2
        segs = [[]]
        for w in t[j:j + 6]:
            if w == "of" and segs[-1]: segs.append([]); continue
            if not w[0].isalpha() or w in STOPS or w in COUNTS: break
            segs[-1].append(w)
        if not segs[0] or (segs[0][-1] in VAGUE and not segs[1:]): continue
        words = [stem(w) for g in segs for w in g if w not in VAGUE]
        head = next((w for w in segs[0] if stem(w) != w and not w.endswith("'s")), segs[0][-1])      # the first plural: "boats" in "three fishing boats bobbing"
        if words: out.append((n, stem(head), words, " of ".join(" ".join(g) for g in segs)))
    return out

def faults(layout, req, known=()):
    """What is plainly wrong with a layout for its description: [(weight, a line that tells the layout model)].
    - a counted thing ("two trees") made as fewer pieces (3: the two were merged into one) or as more (1);
    - nothing made for a thing the description brings in, or for one that another try made of the description's words
      (`known`: that try's labels) (2 each);
    - small flying things made a piece (it sounds like a swarm, or travels above the ground) (3); a piece that was to
      swing, spin, bob or travel but cannot where it was put (2); a piece placed on a piece that is not there (1);
    - two pieces standing inside each other (2 each, at most two); nothing solid at all (10)."""
    info = {}
    try: room, objs = expand(layout, info)
    except Exception: objs = []
    if not objs: return [(10, "the layout had nothing solid in it")]
    pieces = [p for p in layout["pieces"] if isinstance(p, dict) and isinstance(p.get("label"), str) and isinstance(p.get("shape"), str)]
    eff = [stems(e.get("label")) for e in (layout.get("effects") if isinstance(layout.get("effects"), list) else []) if isinstance(e, dict)]
    def copies(p):
        pl = p.get("place") if isinstance(p.get("place"), dict) else {}; r = pl.get("ring")
        return int(clamp(num(r.get("count"), 6), 1, 40)) if isinstance(r, dict) else 4 if pl.get("corners") else 1
    lab = [(stems(p["label"]) + (stems(p["shape"]) if p.get("shape") in FURNITURE else []), copies(p)) for p in pieces]
    # what a piece is: the last word of its label that is not a place ("coffee table", "tree left"), or of its furniture shape
    is_a = [{like(w) for w in ([w for w in stems(p["label"]) if w not in PLACES][-1:] + (stems(p["shape"])[-1:] if p.get("shape") in FURNITURE else []))} for p in pieces]
    def count(head, text):      # pieces that are a `head`; only those with all the words as written, if any have them ("two side tables" beside a coffee table)
        ks = [k for k in range(len(lab)) if like(head) in is_a[k]]; full = {like(w) for w in stems(text)} - {"of"}
        return sum(lab[k][1] for k in ([k for k in ks if full <= {like(w) for w in lab[k][0]}] or ks))
    have = {w for ws, _ in lab for w in ws} | {w for ws in eff for w in ws} | set(stems(layout.get("surround")))
    hit = lambda w, ws: any(same(w, v) for v in ws)
    out, gone = [], set()
    for n, head, words, text in named(req):
        made = count(head, text)
        if n > 1 and made and made != n and not any(hit(head, ws) for ws in eff):
            out.append((3, f'the description has {n} "{text}" but only {made} of them {"is a piece" if made == 1 else "are pieces"}: each one is a piece of its own') if made < n else (1, f'the description has {n} "{text}" but {made} were made'))
        elif not any(hit(w, have) for w in words): out.append((2, f'nothing was made for "{text}"')); gone |= set(words)
    said = set(stems(req)) - {stem(w) for w in VAGUE | STOPS | set(COUNTS)}
    for label in known:
        ws = [w for w in stems(label) if w in said]
        if ws and not any(hit(w, have) or hit(w, gone) for w in ws): out.append((2, f'nothing was made for "{label}"'))
    moves = {(objs[m["i"]]["name"], m["type"]) for m in info.get("motions", [])}; labels = {p["label"].strip().lower() for p in pieces}
    pairs = set()      # a piece and the piece that holds it up may touch
    for p in pieces:
        label = p["label"]; m = p.get("motion") if isinstance(p.get("motion"), dict) else {}; t = m.get("type") if isinstance(m.get("type"), str) else None
        on = p["place"].get("on") if isinstance(p.get("place"), dict) else None
        if p.get("shape") == "ground": continue
        if any(v in ("buzz", "chirp") for v in (p.get("sound"), m.get("sound")) if isinstance(v, str)): out.append((3, f'"{label}" is a swarm of small things: it is an entry in "effects", never a piece'))
        elif t == "path" and num(p.get("base"), 0) > 0.3: out.append((3, f'"{label}" travels through the air, which no piece can: small flying things are an entry in "effects"'))
        elif t in LIFTED and (label[:30], t) not in moves: out.append((2, f'"{label}" cannot {"travel" if t == "path" else t} where it was put: give it room'))
        if isinstance(on, str):
            pairs.add(frozenset((label[:30].strip().lower(), on[:30].strip().lower())))
            if on.strip().lower() not in labels: out.append((1, f'"{label}" is placed on "{on}", which is not a piece'))
    def boxes(o):      # each primitive's axis-aligned bounds; a cylinder counts as the square inside it (a tree's crown is not solid to its corners)
        for p in o["prims"]:
            cs, sn = (1, 0) if p["shape"] == "cyl" else (abs(math.cos(p["yaw"])), abs(math.sin(p["yaw"])))
            e = (p["r"] * 0.71, p["hy"], p["r"] * 0.71) if p["shape"] == "cyl" else (cs * p["h"][0] + sn * p["h"][2], p["h"][1], sn * p["h"][0] + cs * p["h"][2])
            yield [(p["c"][k] - e[k], p["c"][k] + e[k]) for k in range(3)]
    bx = [list(boxes(o)) for o in objs]; vol = [sum(math.prod(hi - lo for lo, hi in b) for b in bs) for bs in bx]; inside = []
    top = [max(b[1][1] for b in bs) for bs in bx]; base = {p["label"][:30].strip().lower(): num(p.get("base"), 0) for p in pieces}
    crown = [max((2 * p["hy"] for p in o["prims"] if p["shape"] == "cyl"), default=0) for o in objs]      # a tall cylinder is a tree's crown down to the ground: things stand under it
    def meant(i, j):      # i was put on top of j (its base at j's top: on a stage), or stands low under j's crown
        return (top[j] > 0.2 and base.get(objs[i]["name"].strip().lower(), 0) >= top[j] - 0.1) or (crown[j] > 3 and top[i] < crown[j] / 2)
    flat = [min(max(b[k][1] for b in bs) - min(b[k][0] for b in bs) for k in range(3)) < 0.15 for bs in bx]      # windows, cloth, signs: they lie against things
    for i in range(len(objs)):
        for j in range(i + 1, len(objs)):
            if frozenset((objs[i]["name"].strip().lower(), objs[j]["name"].strip().lower())) in pairs or flat[i] or flat[j] or meant(i, j) or meant(j, i): continue
            v = sum(math.prod(max(0.0, min(a[k][1], b[k][1]) - max(a[k][0], b[k][0])) for k in range(3)) for a in bx[i] for b in bx[j])
            if v > 0.25 * min(vol[i], vol[j]): inside.append((2, f'"{objs[i]["name"]}" and "{objs[j]["name"]}" stand inside each other: move them apart'))
    out += inside[:2]
    return [f for k, f in enumerate(out) if f not in out[:k]]

def judge(layout, req, known=()):      # faults(), which must never be what stops a build: a layout it cannot read has none
    try: return faults(layout, req, known)
    except Exception: return []

def choose(req, tries=3, ask=None):
    """Ask for a layout, and again (up to `tries` times in all, saying what was wrong) while its faults weigh POOR or
    more. -> (the layout with the lightest faults, the earliest of equals; seconds spent; its faults; which try; tries made)."""
    ask = ask or globals()["ask"]; got, secs, note, err = [], 0.0, "", None
    weight = lambda fs: sum(w for w, _ in fs)
    for k in range(tries):
        try: layout, s = ask(req + note)
        except OSError:
            if not got: raise
            break                                   # the model went away: what there is must do
        except Exception as e: err = e; continue    # an answer that is not JSON: ask again
        got.append(layout); secs += s; fs = judge(layout, req)
        if weight(fs) < POOR: break
        print(f"layout try {k + 1} of {tries}:", "; ".join(t for _, t in fs), flush=True)
        note = "\n\nAn earlier layout for this description had these faults. Do not repeat them: " + "; ".join(t for _, t in fs[:5]) + "."
    if not got: raise err or ValueError("no layout")
    labels = [[p["label"] for p in (l.get("pieces") if isinstance(l, dict) and isinstance(l.get("pieces"), list) else []) if isinstance(p, dict) and isinstance(p.get("label"), str)] for l in got]
    fss = [judge(l, req, [v for j, vs in enumerate(labels) if j != k for v in vs]) for k, l in enumerate(got)]      # what another try made of the description and this one did not
    k = min(range(len(got)), key=lambda k: (weight(fss[k]), k))
    return got[k], secs, fss[k], k + 1, len(got)

def ask(req, model="qwen3.5:9b"):
    body = json.dumps({"model": model, "stream": False, "think": False, "keep_alive": 0, "options": {"temperature": 0.1, "num_ctx": 8192}, "prompt": PROMPT + req}).encode()
    r = json.load(urllib.request.urlopen(urllib.request.Request("http://localhost:11434/api/generate", body), timeout=300))
    txt = r["response"]
    return json.loads(txt[txt.index("{"):txt.rindex("}") + 1]), r["total_duration"] / 1e9

if __name__ == "__main__":
    req, path = sys.argv[1], sys.argv[2]
    try:
        layout, secs, wrong, k, n = choose(req); info = {}
        room, objs = expand(layout, info)
    except OSError as e:      # most specific first: HTTPError and TimeoutError are both OSErrors, and a connect timeout hides in URLError.reason
        if isinstance(e, urllib.error.HTTPError):
            if e.code == 404: raise SystemExit("The layout model has not been downloaded. Run: ollama pull qwen3.5:9b")
            raise SystemExit(f"Ollama could not run the layout model (HTTP {e.code}). It may be out of memory; try again in a moment.")
        if isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError):
            raise SystemExit("The layout model took too long to answer. Try again, or describe the space more simply.")
        raise SystemExit("Could not reach the layout model. Check that Ollama is running.")
    except Exception:
        raise SystemExit("The layout model did not return a usable plan. Try describing the space more simply.")
    if not objs: raise SystemExit("The layout model's plan had nothing solid in it. Try naming the main things in the space.")
    json.dump({"request": req, "room": room, "objects": objs, **info, "rules": 2}, open(path, "w"), indent=1)
    if n > 1: print(f"kept layout try {k} of {n}" + (": " + "; ".join(t for _, t in wrong) if wrong else ""))
    names = {}
    for o in objs: names[o["name"]] = names.get(o["name"], 0) + 1
    print(f"room {room[0]:g} x {room[2]:g} m, {room[1]:g} m high;", ", ".join(f"{n} x {k}" if n > 1 else k for k, n in names.items()))
    if info.get("setting") or info.get("motions") or info.get("effects"):
        print(info.get("setting", "indoor") + ";", ", ".join(f"{objs[m['i']]['name']} ({m['type']})" for m in info.get("motions", [])) or "nothing moves",
              *(["and " + ", ".join(e["label"] for e in info["effects"])] if info.get("effects") else []))
    print("secs", round(secs, 1))
