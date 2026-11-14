"""Real 3D shapes for the objects of an invented room, so they are not painted boxes.
  shapes.py plan "STYLE"   which kinds of object get a shape, and what each looks like   (.venv; asks the layout model)
  shapes.py pictures       one picture of each kind, alone on a plain blue backdrop      (../spike/.venv)
  shapes.py build          cut-out -> 3D mesh (Hunyuan3D) -> placed in the room          (.venv)
Environment: WORLD_DIR (the world's folder), WORLD_SHAPES (most kinds to shape, default 6), HY3D_DIR (the Hunyuan3D-Swift
folder, default ../ext/Hunyuan3D-Swift), WORLD_SHAPE_PX (picture size, default 512).
Files in WORLD_DIR/shapes: plan.json, KIND.png, KIND.rgba.png, KIND.glb, placed/NNN.npz (V, F in room coordinates; NNN is
the object's index in boxes.json), times.json, KIND.failed (why this kind has no shape; delete it to try again).
Every step skips what already exists, and nothing here may fail a world: an object whose shape cannot be made or placed
has no placed file and stays a box.
"""
import sys, os, re, json, math, time, subprocess, hashlib
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.environ.get("WORLD_DIR", "chisel")
S = f"{D}/shapes"
HY3D = os.environ.get("HY3D_DIR") or os.path.join(HERE, "../ext/Hunyuan3D-Swift")
THIN = 0.15          # metres: anything thinner (windows, rugs) is left as a box
MAX_FACES = 60000

NO_MODEL = f"The 3D shape model is not installed ({os.path.normpath(HY3D)}): objects stay boxes."

def limit():
    """Most kinds to shape. Anything that is not a number (off, no, false) switches shapes off, as 0 does."""
    try: return max(0, int(float(os.environ.get("WORLD_SHAPES", "6"))))
    except (ValueError, OverflowError): return 0

def have_model(): return os.path.exists(f"{HY3D}/.build/release/hy3d") and os.path.isdir(f"{HY3D}/weights/shape-small")

def stamp(world):
    """Changes when the layout does: a plan names objects by their position in it."""
    return hashlib.md5(json.dumps([world.get("room"), world.get("objects")], sort_keys=True).encode()).hexdigest()

def save_json(obj, path):
    json.dump(obj, open(path + ".tmp", "w"), indent=1); os.replace(path + ".tmp", path)

def times():
    try: t = json.load(open(f"{S}/times.json"))
    except (OSError, ValueError): t = {}
    return {k: v for k, v in t.items() if isinstance(v, dict)} if isinstance(t, dict) else {}

def note_time(kind, what, secs):
    try:        # only a note: it must never stop a step
        t = times(); t.setdefault(kind, {})[what] = round(float(t.get(kind, {}).get(what, 0)) + secs, 1); save_json(t, f"{S}/times.json")
    except Exception: pass

def give_up(kind, why):
    """This kind stays a box, now and on later runs (until KIND.failed is deleted): trying again costs minutes each time."""
    print(f"{kind} {why}: it stays a box", flush=True)
    try: open(f"{S}/{kind}.failed", "w").write(why + "\n")
    except OSError: pass

def read_plan(n_objs):
    """-> (plan, kinds) keeping only the kinds that are written as plan() writes them; ({}, {}) when there is no usable plan."""
    try: p = json.load(open(f"{S}/plan.json")); kinds = p["kinds"].items()
    except (OSError, ValueError, KeyError, TypeError, AttributeError): return {}, {}
    ok = lambda k, v: (re.fullmatch(r"[a-z0-9_]+", str(k)) and isinstance(v, dict) and isinstance(v.get("look"), str) and isinstance(v.get("objects"), list)
                       and all(type(i) is int and 0 <= i < n_objs for i in v["objects"]))
    return p, {k: v for k, v in kinds if ok(k, v)}

# ---------------------------------------------------------------- geometry of the layout

def frame(o):
    """An object's bounding box in its own turned frame -> (yaw, lo, hi) with lo/hi = (across u, up y, back-to-front v).
    The frame is the one llm_boxes.to_world turns into the room: the piece's front faces +v. The layout writes the turn
    on the object when it chose one (against a wall, in a ring); otherwise it is the first box's."""
    yaw = o["yaw"] if isinstance(o.get("yaw"), (int, float)) else next((p.get("yaw", 0.0) for p in o["prims"] if p["shape"] == "box"), 0.0)
    cs, sn = math.cos(yaw), math.sin(yaw); pts = []
    for p in o["prims"]:
        c = p["c"]; h = p["h"] if p["shape"] == "box" else [p["r"], p["hy"], p["r"]]
        a = p.get("yaw", 0.0) if p["shape"] == "box" else yaw; ca, sa = math.cos(a), math.sin(a)
        for du in (-h[0], h[0]):
            for dv in (-h[2], h[2]):
                x, z = c[0] + ca * du + sa * dv, c[2] - sa * du + ca * dv
                pts.append((cs * x - sn * z, c[1] - h[1], sn * x + cs * z)); pts.append((cs * x - sn * z, c[1] + h[1], sn * x + cs * z))
    pts = np.array(pts)
    return yaw, pts.min(0), pts.max(0)

def covers(p, x, z):
    """Is the floor point (x, z) under or inside primitive p?"""
    dx, dz = x - p["c"][0], z - p["c"][2]
    if p["shape"] != "box": return dx * dx + dz * dz <= p["r"] ** 2
    cs, sn = math.cos(p.get("yaw", 0.0)), math.sin(p.get("yaw", 0.0))
    return abs(cs * dx - sn * dz) <= p["h"][0] and abs(sn * dx + cs * dz) <= p["h"][2]

def support(objs, i):
    """-> (height the object rests at, index of the object it stands on or None). The layout settles every piece onto the
    floor, so a thing on a platform overlaps it. The platform is a lower object with a primitive that stands where this
    object's foot would be and lies under ALL of its footprint: a neighbour that merely overlaps (a lamp beside a sofa's arm)
    or a top with room underneath (a chair pushed under a table) is not one."""
    yaw, lo, hi = frame(objs[i]); cs, sn = math.cos(yaw), math.sin(yaw); m = 0.02
    foot = [(cs * u + sn * v, -sn * u + cs * v) for u, v in (((lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2), (lo[0] + m, lo[2] + m), (hi[0] - m, lo[2] + m), (lo[0] + m, hi[2] - m), (hi[0] - m, hi[2] - m))]
    best = (float(lo[1]), None)
    for j, o in enumerate(objs):
        if j == i or frame(o)[2][1] >= hi[1]: continue
        for p in o["prims"]:
            hy = p["h"][1] if p["shape"] == "box" else p["hy"]; top = p["c"][1] + hy
            if top > best[0] and p["c"][1] - hy <= lo[1] + 0.05 and all(covers(p, x, z) for x, z in foot): best = (float(top), j)
    return best

# ---------------------------------------------------------------- plan

# words that say where a thing stands, not what it is: "car_corner_fl" and "car_center" are both a car
WHERE = set("left right front back rear middle centre center central corner inner outer upper lower north south east west near far row".split())

def kinds_of(objs):
    """Group objects that can share one shape: the same thing (labels equal once numbers and words of position are
    dropped) with the same proportions (within 12%). -> [{"name", "objects": [indices], "size": (across, up, deep), "words"}]"""
    groups = []
    for i, o in enumerate(objs):
        _, lo, hi = frame(o); size = hi - lo
        all_words = re.findall(r"[a-z]+", str(o["name"]).lower())
        words = [w for w in all_words if len(w) > 2 and w not in WHERE] or all_words
        for g in groups:
            if g["words"] == words and g["prims"] == len(o["prims"]) and np.all(np.abs(size / g["size"] - 1) < 0.12): g["objects"].append(i); break
        else: groups.append({"objects": [i], "size": size, "words": words, "prims": len(o["prims"])})
    used = set()
    for g in groups:
        base = "_".join(g["words"])[:24].strip("_") or "thing"
        name, n = base, 2
        while name in used: name, n = f"{base}_{n}", n + 1
        used.add(name); g["name"] = name
    return groups

def proportions(size):
    """Plain words for a box that is much wider than deep, for the description and the picture: without them a 2 m sofa
    comes back as a corner sofa and fills half its box. Other proportions are left alone; words like "tall" did more harm than good."""
    w, h, d = size; a, b = max(w, d), min(w, d)
    if a <= 1.8 * b: return ""
    return "taller than it is wide and much wider than it is deep" if h > a else "much wider than it is deep, in one straight piece"

ASK = '''You help build a 3D scene. Below is a numbered list of the things in it, with their sizes in metres. For each thing decide whether it needs a sculpted 3D shape of its own, and say what it looks like.

Scene: "REQUEST"
Style: "STYLE"

Things:
THINGS

Answer with JSON only: {"things": [{"id": number, "shaped": true or false, "look": "..."}]} with one entry per thing.
- "shaped": true for things with a characteristic shape of their own: vehicles, furniture to sit or lie on, tables, shelves, statues, machines, instruments, plants, lamps. false for plain slabs and blocks that a box or a cylinder already describes well: platforms, stages, steps, counters, rugs, partitions, walls, windows, plain pillars and columns.
- "look": one short phrase of at most 12 words naming ONE such thing as it would be photographed on its own: what it is, with its material, colour and period, in keeping with the scene and the style. Example: "a cream 1930s antique car". Describe a single thing even when the scene has several, and one whose proportions match its size and the words in brackets: a thing 2 wide and 0.9 deep is a straight sofa, never a corner or sectional one; a thing 1.2 wide and 2 high is a wide bookcase, never a narrow one. Name the thing alone: not what it stands on, not what stands on it, not the room, other things or people.
'''

def ask(prompt, model="qwen3.5:9b"):
    import urllib.request
    body = json.dumps({"model": model, "stream": False, "think": False, "keep_alive": 0, "options": {"temperature": 0.1, "num_ctx": 4096}, "prompt": prompt}).encode()
    r = json.load(urllib.request.urlopen(urllib.request.Request("http://localhost:11434/api/generate", body), timeout=300))
    txt = r["response"]
    return json.loads(txt[txt.index("{"):txt.rindex("}") + 1])      # the MLX runner rejects "format": "json", so cut the JSON out of the text

def plan(style):
    world = json.load(open(f"{D}/boxes.json")); objs, room = world["objects"], world.get("room", [4.0, 2.6, 4.0])
    path = f"{S}/plan.json"
    try:
        p = json.load(open(path))
        if p.get("style") == style and p.get("layout") == stamp(world): return print("shapes already planned")
    except (OSError, ValueError, AttributeError): pass
    if os.path.isdir(S):                      # shapes made for another style or another layout no longer suit the room
        for root, _, files in os.walk(S):
            for f in files: os.remove(os.path.join(root, f))
    if not limit(): return
    if not have_model(): return print(NO_MODEL)
    os.makedirs(S, exist_ok=True)
    carriers = {support(objs, i)[1] for i in range(len(objs))}
    cands = []
    for g in kinds_of(objs):
        w, h, d = g["size"]
        if min(w, h, d) < THIN: continue                         # too thin to be worth a mesh
        g["objects"] = [i for i in g["objects"] if i not in carriers]     # what something stands on must keep its flat top
        if not g["objects"]: continue
        g["score"] = len(g["objects"]) * (w * h + d * h + w * d)
        cands.append(g)
    cands = sorted(cands, key=lambda g: -g["score"])[:16]        # keeps the question short
    head = {"style": style, "layout": stamp(world)}
    if not cands: save_json({**head, "kinds": {}, "objects": {}}, path); return print("no objects need a shape")
    words = lambda g: " ".join(g["words"]) or "object"
    things = "\n".join(f'{n + 1}. "{words(g)}"' +      # no counts: with them the model describes "five chairs"
                       f", {g['size'][0]:.1f} wide, {g['size'][1]:.1f} high, {g['size'][2]:.1f} deep" + (f" ({proportions(g['size'])})" if proportions(g["size"]) else "") for n, g in enumerate(cands))
    fill = {"REQUEST": str(world.get("request", ""))[:600], "STYLE": style[:300], "THINGS": things}
    answer = {}
    try:
        t = time.time()
        got = ask(re.sub("REQUEST|STYLE|THINGS", lambda m: fill[m.group()], ASK))     # in one pass: the request may itself say STYLE
        got = got.get("things") if isinstance(got, dict) else got
        got = [a for a in got if isinstance(a, dict)] if isinstance(got, list) else []
        def number(a):       # the id may come back as 2, 2.0 or "2"
            try: n = int(float(str(a.get("id")).strip()))
            except (ValueError, OverflowError): return None
            return n - 1 if 1 <= n <= len(cands) else None
        ids = [number(a) for a in got]
        if all(n is None for n in ids) and len(got) == len(cands): ids = list(range(len(cands)))      # no usable ids: take the answers in order
        for n, a in zip(ids, got):
            if n is not None: answer.setdefault(n, a)
        print("secs", round(time.time() - t, 1))
    except OSError as e:     # the model could not be reached: no plan is written, so the next build asks again
        return print("The layout model could not be asked about shapes this time: objects stay boxes.", type(e).__name__)
    except Exception as e:
        print("the layout model gave no usable answer about shapes, deciding by size instead:", type(e).__name__, file=sys.stderr)
    chosen = []
    for n, g in enumerate(cands):
        a = answer.get(n); w, h, d = g["size"]
        if a is None:      # no answer for this one: slabs lower than a third of their width, and things reaching the ceiling, stay boxes
            shaped = h >= 0.3 * max(w, d) and h < 0.85 * room[1]
        else:
            shaped = a.get("shaped") is True or str(a.get("shaped")).strip().lower() in ("true", "yes", "1")
        look = a.get("look") if a and isinstance(a.get("look"), str) else ""
        look = re.sub(r"\s+", " ", re.sub(r'["\n\r{}\[\]]', " ", look)).strip(" .")[:120]
        if len(look) < 3: look = f"a {words(g)}, {style}"[:120]
        print(f"{g['name']}: {'shape' if shaped else 'box'}, {len(g['objects'])} x {w:.2f} x {h:.2f} x {d:.2f} m, {look}")
        if shaped: chosen.append((g, look))
    chosen = chosen[:limit()]                                     # already ordered by size x count
    save_json({**head, "kinds": {g["name"]: {"look": look, "objects": g["objects"]} for g, look in chosen},
               "objects": {str(i): {"kind": g["name"], "look": look} for g, look in chosen for i in g["objects"]}}, path)

# ---------------------------------------------------------------- pictures

# Blue is the backdrop because the picture's colours do not matter (only its outline and shading reach the shape model)
# and a strongly coloured backdrop separates white, black and chrome objects alike; a shadow is darker blue, so it goes too.
# An object that is itself blue or green is tried on a green backdrop too. These are colour words, not kinds of object.
BLUISH = re.compile(r"\b(blue|bluish|navy|teal|cyan|azure|turquoise|indigo|cobalt|sapphire|aqua|aquamarine)\b", re.I)
GREENISH = re.compile(r"\b(green|greenish|emerald|olive|lime|mint|jade|sage|verdigris)\b", re.I)

def backdrop(im):
    """-> (how unlike the backdrop each pixel is, how bright it is relative to the backdrop). im: float RGB 0..1.
    The backdrop colour is read from the picture's rim; a pixel is compared with the nearest darker or lighter shade of it."""
    h, w = im.shape[:2]; m = max(4, h // 25)
    b = np.median(np.concatenate([im[:m].reshape(-1, 3), im[-m:].reshape(-1, 3), im[:, :m].reshape(-1, 3), im[:, -m:].reshape(-1, 3)]), 0)
    k = np.clip(im @ b / max(float(b @ b), 1e-6), 0.45, 1.3)
    return np.linalg.norm(im - k[..., None] * b, axis=-1), k

def framing(im):
    """-> (share of the picture that is object, share of the rim that is). A usable picture shows one object, not cut off
    by the frame, on a clean backdrop: its rim is almost all backdrop."""
    res, _ = backdrop(im); fg = res > 0.16; m = max(4, fg.shape[0] // 25)
    rim = np.concatenate([fg[:m].ravel(), fg[-m:].ravel(), fg[:, :m].ravel(), fg[:, -m:].ravel()])
    return float(fg.mean()), float(rim.mean())

def pictures():
    objs = json.load(open(f"{D}/boxes.json"))["objects"]
    _, kinds = read_plan(len(objs))
    todo = [k for k in kinds if kinds[k]["objects"] and not os.path.exists(f"{S}/{k}.png") and not os.path.exists(f"{S}/{k}.failed")]
    if not todo: return
    if not have_model(): return print(NO_MODEL)       # no use painting pictures nothing can turn into shapes
    from mflux.models.z_image import ZImageTurbo
    px = int(os.environ.get("WORLD_SHAPE_PX", "512"))
    model = ZImageTurbo(quantize=8)
    for n, k in enumerate(todo):
        print(f"STAGE: picturing object {n + 1} of {len(todo)}", flush=True)
        try:
            t = time.time(); look = kinds[k]["look"]
            # a thing described as blue or green is pictured on both backdrops, and the picture that keeps more of it wins:
            # the wrong backdrop eats the part of its own colour (a fern in a blue pot loses the pot or the fern)
            coloured = bool(BLUISH.search(look) or GREENISH.search(look))
            tries = ((7, "bright blue"), (7, "bright green")) if coloured else ((7, "bright blue"), (8, "bright blue"))    # else: one more try if the first is cropped
            _, lo, hi = frame(objs[kinds[k]["objects"][0]]); prop = proportions(hi - lo)
            best = None
            for seed, colour in tries:
                prompt = (f"Product photo of {look}{', ' + prop if prop else ''}. One single whole object, centred, entirely in frame with a margin around it, seen from the front "
                          f"three-quarter view, slightly from above, isolated on a plain flat solid {colour} background, no shadow, no floor, even soft lighting.")
                img = model.generate_image(seed=seed, prompt=prompt, num_inference_steps=8, width=px, height=px)
                fg, rim = framing(np.asarray(img.image.convert("RGB"), np.float32) / 255)
                score = (rim < 0.03, fg if coloured else -rim)         # first a clean rim (nothing cut off by the frame)
                if 0.02 < fg < 0.8 and rim <= 0.10 and (best is None or score > best[0]): best = (score, img)
                if best and best[0][0] and not coloured: break
            if not best: give_up(k, "could not be pictured whole on a plain backdrop"); continue   # cropped: its mesh would be cut flat
            best[1].save(f"{S}/{k}.tmp.png"); os.replace(f"{S}/{k}.tmp.png", f"{S}/{k}.png")
            note_time(k, "picture", time.time() - t)
            print(k, "picture", round(time.time() - t), "s", flush=True)
        except Exception as e: print(k, "could not be pictured this time: it stays a box;", type(e).__name__, e, flush=True)

# ---------------------------------------------------------------- cut-out and mesh

def cut_out(src, out):
    """Picture on a plain backdrop -> RGBA cut-out. False if no usable object was found."""
    from scipy import ndimage as ndi
    im = np.asarray(Image.open(src).convert("RGB"), np.float32) / 255
    h, w = im.shape[:2]; res, k = backdrop(im)
    back = res < 0.16
    lab, _ = ndi.label(back)
    rim = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    outer = np.isin(lab, rim[rim > 0])
    # backdrop seen through the object (between legs or slats) is as bright and as pure as the backdrop itself;
    # its reflection in metal or glass is not, and stays part of the object
    gap = back & ~outer & (res < 0.07) & (np.abs(k - 1) < 0.2)
    gl, gn = ndi.label(gap)
    if gn: gap = np.isin(gl, 1 + np.nonzero(ndi.sum(gap, gl, range(1, gn + 1)) > h * w * 2e-4)[0])
    fg = ndi.binary_opening(~(outer | gap))
    fl, fn = ndi.label(fg)
    if not fn: return False
    size = ndi.sum(fg, fl, range(1, fn + 1)); fg = np.isin(fl, 1 + np.nonzero(size > size.max() * 0.02)[0])   # drop specks
    if not 0.02 < fg.mean() < 0.8: return False
    a = ndi.gaussian_filter(ndi.binary_erosion(fg).astype(np.float32), 0.7)       # one pixel in: no backdrop-coloured fringe
    Image.fromarray(np.dstack([im * 255, a[..., None] * 255]).astype(np.uint8), "RGBA").save(out)
    return True

def mesh(kind):
    """Cut-out -> KIND.glb with the Hunyuan3D shape model; -> "" or why not. 15 steps give the same shape as the default 30 in half the time."""
    exe, weights = f"{HY3D}/.build/release/hy3d", f"{HY3D}/weights/shape-small"
    tmp = f"{S}/{kind}.tmp.glb"
    try:
        r = subprocess.run([exe, "shape", f"{S}/{kind}.rgba.png", "-o", tmp, "--weights", weights, "--steps", "15", "--octree", "256", "--seed", "0"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace", timeout=600)
    except subprocess.TimeoutExpired: return "took the shape model more than ten minutes"
    if r.returncode or not os.path.exists(tmp):
        said = [l.strip() for l in (r.stderr or "").splitlines() if l.strip()]
        return "could not be turned into a shape" + (f" ({said[-1][:200]})" if said else "")
    os.replace(tmp, f"{S}/{kind}.glb"); return ""

# ---------------------------------------------------------------- placing

def load(kind):
    """KIND.glb -> (V, F): centred, at most MAX_FACES faces, upright with its front on +z.
    The shape model always returns the object upright, squared up with the axes and facing +z, whatever angle the
    picture was taken from (checked on cars, seats, tables, shelves, lamps, statues and plants)."""
    import trimesh, open3d as o3d
    m = trimesh.load(f"{S}/{kind}.glb", force="mesh")
    V, F = np.asarray(m.vertices, float), np.asarray(m.faces)
    if len(F) > MAX_FACES:
        o = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(V), o3d.utility.Vector3iVector(F)).simplify_quadric_decimation(MAX_FACES)
        V, F = np.asarray(o.vertices), np.asarray(o.triangles)
    if not len(F) or not np.isfinite(V).all(): raise ValueError("empty mesh")
    # loose scraps on the ground (a bit of shadow turned into a slab) would enlarge the bounding box and so shrink the object
    parts = trimesh.graph.connected_components(trimesh.Trimesh(V, F, process=False).face_adjacency, nodes=np.arange(len(F)))
    if len(parts) > 1:
        big = max(len(c) for c in parts); low = V[:, 1].min() + 0.05 * (V[:, 1].max() - V[:, 1].min())
        F = F[np.sort(np.concatenate([c for c in parts if len(c) >= 0.05 * big or V[F[c]][..., 1].max() > low]))]
    used = np.unique(F); V = V[used]; F = np.searchsorted(used, F)
    return V - (V.min(0) + V.max(0)) / 2, F

QUARTER = ((1, 0), (0, 1), (-1, 0), (0, -1))      # (cos, sin) of 0, 1, 2, 3 quarter turns; the front then points along (sin, cos) in (u, v)

def place(V, F, objs, i, room, aim=None, same=()):
    """One mesh into the room in place of object i -> (V, F) in room coordinates. aim: the floor point (x, z) that things
    with no facing of their own turn to. same: the objects that get this same mesh."""
    o = objs[i]; yaw, lo, hi = frame(o); box = hi - lo; bu, bh, bv = box
    cs, sn = math.cos(yaw), math.sin(yaw); cu, cv = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    room_xz = lambda u, v: (cs * u + sn * v, -sn * u + cs * v)
    outside = lambda u, v: not (0 <= room_xz(u, v)[0] <= room[0] and 0 <= room_xz(u, v)[1] <= room[2])
    wall_behind, wall_ahead = outside(cu, lo[2] - 0.35), outside(cu, hi[2] + 0.35)       # only the walls its back or front is against
    eu, _, ev = V.max(0) - V.min(0)
    long_obj, long_box = max(eu, ev) / max(min(eu, ev), 1e-6) > 1.25, max(bu, bv) / max(min(bu, bv), 1e-6) > 1.25
    # The mesh's front (+z) may be turned by quarter turns: 0 = to the piece's front (+v), 1 = +u, 2 = its back, 3 = -u.
    # A long object in a long box lies along it, even if that turns its front sideways (a car in a wide, shallow box).
    if long_obj and long_box: turns = (1, 3) if (eu > ev) != (bu > bv) else (0, 2)
    else: turns = (0, 2) if long_box else (0, 1, 2, 3)
    # The layout gives a facing to pieces on a wall or in a ring (worlds made before it wrote that down: a turned box, or
    # a back against a wall). Those keep it if they can. All else turns its front to what the room is about, or to the
    # room's middle; a thing standing there faces the front wall, where a visitor starts.
    faces = isinstance(o.get("yaw"), (int, float)) or abs(math.remainder(yaw, 2 * math.pi)) > 1e-6 or wall_behind
    if faces and 0 in turns: k = 0
    else:
        x, z = room_xz(cu, cv); ax, az = aim if aim else (room[0] / 2, room[2] / 2); dx, dz = ax - x, az - z
        if math.hypot(dx, dz) < 0.5: dx, dz = 0.0, -1.0
        du, dv = cs * dx - sn * dz, sn * dx + cs * dz
        fu, fv = sn, -cs                          # towards the front wall, which settles a tie
        k = max(turns, key=lambda t: round(QUARTER[t][1] * (du + 1e-3 * fu) + QUARTER[t][0] * (dv + 1e-3 * fv), 6))
    # mesh (x, y, z) -> the piece's frame (u, y, v). x is mirrored, because the room is drawn mirrored (blockout.rays):
    # this way the object looks on screen as it does in its picture.
    ca, sa = QUARTER[k]
    P = np.stack([ca * -V[:, 0] + sa * V[:, 2], V[:, 1], -sa * -V[:, 0] + ca * V[:, 2]], 1)
    ext = P.max(0) - P.min(0)
    base, _ = support(objs, i)
    # one scale for all axes, so the shape is not stretched. It fits the box; but when the object's largest side could
    # still grow (a floor lamp whose shade is wider than its box), it may, until a smaller side sticks out by a third
    fit = box / ext
    lim = [fit[int(np.argmax(ext))], 1.35 * fit.min(), (room[1] - 0.05 - base) / ext[1],
           room[0] / (abs(cs) * ext[0] + abs(sn) * ext[2]), room[2] / (abs(sn) * ext[0] + abs(cs) * ext[2])]       # never wider than the room
    for j in same:           # nor into the next copy of itself: rings and rows are packed with little room to spare
        if j == i: continue
        yj, lj, hj = frame(objs[j]); cj, sj = math.cos(yj), math.sin(yj); uj, vj = (lj[0] + hj[0]) / 2, (lj[2] + hj[2]) / 2
        x, z = cj * uj + sj * vj - room_xz(cu, cv)[0], -sj * uj + cj * vj - room_xz(cu, cv)[1]
        d = (abs(cs * x - sn * z), 0, abs(sn * x + cs * z)); n = 0 if d[0] >= d[2] else 2
        lim.append(max(box[n], 0.98 * d[n]) / ext[n])
    P = P * min(lim); mn, mx = P.min(0), P.max(0)
    # against a wall the piece stays on the wall side of its box; elsewhere it sits in the middle of its box
    off_v = lo[2] - mn[2] if wall_behind else hi[2] - mx[2] if wall_ahead else cv - (mn[2] + mx[2]) / 2
    P = P + [cu - (mn[0] + mx[0]) / 2, base - mn[1], off_v]
    W = np.stack([cs * P[:, 0] + sn * P[:, 2], P[:, 1], -sn * P[:, 0] + cs * P[:, 2]], 1)
    for n, L in ((0, room[0]), (2, room[2])):            # nothing may poke through a wall
        W[:, n] += max(0.0, -W[:, n].min()) - max(0.0, W[:, n].max() - L)
    return W.astype(np.float32), F[:, ::-1].astype(np.int32)     # mirrored, so the triangles are wound the other way

def build():
    world = json.load(open(f"{D}/boxes.json")); objs, room = world["objects"], world.get("room", [4.0, 2.6, 4.0])
    p, kinds = read_plan(len(objs))
    if not kinds: return
    if p.get("layout") not in (None, stamp(world)): return print("The shapes were planned for another layout: objects stay boxes until they are planned again.")
    aim = world.get("focus"); aim = aim if isinstance(aim, list) and len(aim) == 2 and all(isinstance(v, (int, float)) for v in aim) else None
    os.makedirs(f"{S}/placed", exist_ok=True)
    todo = [k for k in kinds if os.path.exists(f"{S}/{k}.png") and not os.path.exists(f"{S}/{k}.glb") and not os.path.exists(f"{S}/{k}.failed")]
    if todo and not have_model(): print(NO_MODEL); todo = []
    for n, k in enumerate(todo):
        print(f"STAGE: shaping object {n + 1} of {len(todo)}", flush=True)
        t = time.time()
        try:
            if not cut_out(f"{S}/{k}.png", f"{S}/{k}.rgba.png"): give_up(k, "could not be cut out of its picture"); continue
            why = mesh(k)
            if why: give_up(k, why); continue
        except Exception as e: print(k, "could not be turned into a shape this time: it stays a box;", type(e).__name__, e); continue
        note_time(k, "mesh", time.time() - t)
        print(k, "mesh", round(time.time() - t), "s", flush=True)
    for k, kind in kinds.items():
        want = [i for i in kind["objects"] if not os.path.exists(f"{S}/placed/{i:03d}.npz")]
        if not want or not os.path.exists(f"{S}/{k}.glb"): continue
        t = time.time()
        try: V, F = load(k)
        except Exception as e: print(k, "has an unusable shape: it stays a box;", type(e).__name__, e); continue
        for i in want:
            try:
                W, G = place(V, F, objs, i, room, aim, kind["objects"])
                if not np.isfinite(W).all(): raise ValueError("bad placement")
                np.savez(f"{S}/placed/{i:03d}.tmp.npz", V=W, F=G); os.replace(f"{S}/placed/{i:03d}.tmp.npz", f"{S}/placed/{i:03d}.npz")
            except Exception as e: print(f"object {i} ({objs[i]['name']}) could not be placed: it stays a box;", type(e).__name__, e)
        note_time(k, "place", time.time() - t)
        print(k, "placed", len(want), "in", round(time.time() - t, 1), "s", flush=True)
    # the plan's object list names exactly the objects that are now meshes
    p["objects"] = {str(i): {"kind": k, "look": kind["look"]} for k, kind in kinds.items() for i in kind["objects"] if os.path.exists(f"{S}/placed/{i:03d}.npz")}
    save_json(p, f"{S}/plan.json")
    spent = times()
    for k, kind in kinds.items():
        n = sum(os.path.exists(f"{S}/placed/{i:03d}.npz") for i in kind["objects"]); t = spent.get(k, {})
        print(f"shape {k}: {n} of {len(kind['objects'])} objects, picture {t.get('picture', 0):g} s, mesh {t.get('mesh', 0):g} s, placing {t.get('place', 0):g} s")

if __name__ == "__main__":
    {"plan": plan, "pictures": pictures, "build": build}[sys.argv[1]](*sys.argv[2:])
