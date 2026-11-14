"""Blockout -> ring of depth maps -> depth-guided pictures.
  chisel_ring.py prep                depth maps + cameras
  chisel_ring.py gen NAME "STYLE"    pictures (model loaded once; already-painted views are skipped)
Environment: WORLD_DIR (the world's folder), WORLD_VIEWS (how many views), WORLD_PAINT (picture size, default 1024x768),
WORLD_CHAIN (0 to paint every view on its own; default 1: each view is given what earlier views already show of it).
"""
import sys, json, os, re, time, hashlib
import numpy as np
from PIL import Image, ImageFilter
sys.path.insert(0, "../spike")
import blockout as B

RING, D = int(os.environ.get("WORLD_VIEWS", "16")), os.environ.get("WORLD_DIR", "chisel")   # RING: views in the level ring
world = json.load(open(f"{D}/boxes.json"))
objs = world["objects"]
RW, RH, RD = world.get("room", [4.0, 2.6, 4.0])
B.ROOM = ((0, 0, 0), (RW, RH, RD))
# an object that has a generated shape (shapes/placed/NNN.npz: a mesh already in room coordinates) is that mesh, not its boxes
def bounds(prims):
    """Axis-aligned bounds of box and cylinder primitives."""
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for p in prims:
        if p["shape"] == "cyl": e = np.array([p["r"], p["hy"], p["r"]])
        else:
            h = np.array(p["h"], float); cs, sn = abs(np.cos(p.get("yaw", 0.0))), abs(np.sin(p.get("yaw", 0.0)))
            e = np.array([cs * h[0] + sn * h[2], h[1], sn * h[0] + cs * h[2]])
        lo, hi = np.minimum(lo, np.array(p["c"], float) - e), np.maximum(hi, np.array(p["c"], float) + e)
    return lo, hi
def shape_prim(oi):
    """The mesh primitive and file checksum for object oi's placed shape; None when there is none, or when it does not
    stand where the object does (a shape left over from an earlier layout of this world: the object stays boxes)."""
    f = f"{D}/shapes/placed/{oi:03d}.npz"
    if not os.path.exists(f): return None
    try:
        z = np.load(f); V, F = z["V"], z["F"]
        # checked here because the ray-caster reads outside the vertex list without complaint when a face index is wrong
        if V.ndim != 2 or V.shape[1] != 3 or F.ndim != 2 or F.shape[1] != 3 or not len(F) or not np.isfinite(V).all() or F.min() < 0 or F.max() >= len(V): raise ValueError
        lo, hi = V.min(0), V.max(0)
    except Exception: raise SystemExit(f"The shape file {f} cannot be used. Delete this world's shapes folder and build it again.")
    blo, bhi = bounds(objs[oi]["prims"]); mid = (lo + hi) / 2
    if not (blo[0] <= mid[0] <= bhi[0] and blo[2] <= mid[2] <= bhi[2]):
        print(f"shape {oi:03d} is not where {objs[oi]['name']} stands: ignored (delete this world's shapes folder to make new shapes)"); return None
    return {"shape": "mesh", "file": f, "c": mid.tolist(), "h": ((hi - lo) / 2).tolist(), "yaw": 0.0}, hashlib.md5(open(f, "rb").read()).hexdigest()
found = {oi: shape_prim(oi) for oi in range(len(objs))}
SHAPES = {oi: g[0]["file"] for oi, g in found.items() if g}
SHAPE_SUMS = {str(oi): g[1] for oi, g in found.items() if g}         # changes whenever the set of shapes or any mesh changes
OBJ_PRIMS = [[found[oi][0]] if found[oi] else o["prims"] for oi, o in enumerate(objs)]
B.PRIMS = [p for ps in OBJ_PRIMS for p in ps]
PRIM_OBJ = [oi for oi, ps in enumerate(OBJ_PRIMS) for _ in ps]       # which object each primitive belongs to
def tall(p, lo, hi):
    """Primitive p stretched up or down to span at least the heights lo..hi."""
    hy = p["hy"] if p["shape"] == "cyl" else p["h"][1]
    a, b = min(p["c"][1] - hy, lo), max(p["c"][1] + hy, hi)
    q = dict(p, c=[p["c"][0], (a + b) / 2, p["c"][2]])
    if p["shape"] == "cyl": q["hy"] = (b - a) / 2
    else: q["h"] = [p["h"][0], (b - a) / 2, p["h"][2]]
    return q
# where cameras may not stand. A shape keeps its boxes' footprint for this (its own bounding box ignores how it is turned,
# and cameras should not move when shapes appear), stretched to the shape's height: a shape resting on something can rise
# above its boxes
KEEP_OUT = [tall(p, g[0]["c"][1] - g[0]["h"][1], g[0]["c"][1] + g[0]["h"][1]) if g else p for oi, o in enumerate(objs) for g in [found[oi]] for p in o["prims"]]
LOOKS = {}                                                           # object index -> planned look; without one an object goes by its label
try:
    for k, v in json.load(open(f"{D}/shapes/plan.json"))["objects"].items():   # one bad entry must not lose the others
        if str(k).isdigit() and int(k) in SHAPES and isinstance(v, dict) and isinstance(v.get("look"), str) and v["look"].strip(): LOOKS[int(k)] = v["look"].strip()
except (OSError, ValueError, KeyError, TypeError, AttributeError): pass
c = np.array([RW / 2, 0.0, RD / 2])
EYE = 1.5 if RH < 3.2 else 1.7

def free(eye, margin=0.25):
    """A camera position that is not inside (or right against) any shape: the given spot, else the nearest free spot
    found by sliding towards or away from the room's centre. None if there is none."""
    eye = np.array(eye, float)
    clear = lambda e: not any(B.inside(e, p, margin) for p in KEEP_OUT)
    inside_room = lambda e: 0.3 < e[0] < RW - 0.3 and 0.3 < e[2] < RD - 0.3
    for k in (1.0, 0.9, 1.1, 0.8, 1.2, 0.7, 1.3, 0.6, 0.5, 0.4, 0.3):
        e = eye.copy(); e[[0, 2]] = c[[0, 2]] + (eye[[0, 2]] - c[[0, 2]]) * k
        if inside_room(e) and clear(e): return e
    return None

B.CAMS = {}
for i in range(RING):
    a = 2 * np.pi * i / RING
    off = np.array([np.cos(a) * RW, 0, np.sin(a) * RD])               # an ellipse that follows the room's shape
    want = c + off * 0.325 + [0, EYE, 0]
    eye = free(want)
    if eye is None: eye = free(want, 0.0)
    if eye is None: eye = want                                        # a painted view must exist for every index
    B.CAMS[str(i)] = (tuple(eye), tuple(c - off * 0.4 + [0, 0.8, 0]))
# a few views from higher up looking down, painted after the ring: the ring looks across the room, so it never sees the
# middle of the floor or the tops and far sides of low furniture
n_extra = 4 if RW * RD < 60 else 6
for i in range(n_extra):
    a = 2 * np.pi * (i + 0.5) / n_extra; off = np.array([np.cos(a) * RW, 0, np.sin(a) * RD])
    eye = free(c + off * 0.3 + [0, min(RH - 0.3, EYE + 0.6), 0])
    if eye is not None: B.CAMS[str(len(B.CAMS))] = (tuple(eye), tuple(c - off * 0.08))
N = len(B.CAMS)                                                       # every painted view: the ring, then the downward ones

def prep():
    os.makedirs(f"{D}/depth", exist_ok=True)
    for k, cam in B.CAMS.items():
        t, P, sid, nrm = B.trace(cam, PRIM_OBJ, True)
        inv = 1 / np.maximum(t, 0.3)
        # robust contrast: a few very near pixels must not flatten the rest of the map, and far walls need visible steps
        lo, hi = np.percentile(inv, [1, 99])
        img = np.clip((inv - lo) / max(hi - lo, 1e-6), 0, 1) ** 0.6
        Image.fromarray((img * 255).astype(np.uint8)).convert("RGB").save(f"{D}/depth/{int(k):02d}.png")
        np.save(f"{D}/depth/{int(k):02d}.npy", P.astype(np.float32))
        np.savez_compressed(f"{D}/depth/{int(k):02d}.npz", t=t, sid=sid.astype(np.int16), n=np.round(nrm * 127).astype(np.int8), shapes=json.dumps(SHAPE_SUMS))   # for surfaces()
    print("depth maps", N)

GRAZE = 0.3   # a shape's surface counts as seen side-on below this cosine between its normal and the direction to the camera

HALO = 33      # px, odd: a band 16 px wide around every shape's outline (at the working size)

def halo(sid):
    """Pixels just outside a generated shape's outline. The painter rarely keeps a shape exactly inside its outline, so
    the band around it often holds the shape's own paint: it must not be taken as the wall or floor behind."""
    on = np.isin(sid, [6 + oi for oi in SHAPES])
    if not on.any(): return np.zeros(sid.shape, bool)
    return (np.asarray(Image.fromarray((on * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(HALO))) > 127) & ~on

def surfaces(i):
    """Depth, surface id and shape normal (zero off shapes) per pixel of painted view i, as saved by prep: the painting
    environment cannot ray-cast meshes."""
    f = f"{D}/depth/{i:02d}.npz"
    if os.path.exists(f):
        z = np.load(f)
        if "shapes" not in z or str(z["shapes"]) != json.dumps(SHAPE_SUMS):   # rendered before the shapes changed
            raise SystemExit(f"The saved depth of view {i + 1} does not match this world's shapes. Render the blockout again (chisel_ring.py prep).")
        return z["t"].astype(float), z["sid"].astype(int), z["n"] / 127.0
    if SHAPES: raise SystemExit(f"View {i + 1} has no saved depth ({f}). Render the blockout again (chisel_ring.py prep).")
    t, _, sid = B.trace(B.CAMS[str(i)], PRIM_OBJ)                     # a world prepared before these files were saved
    return t, sid, np.zeros((B.H, B.W, 3))

def view_prompt(i, style):
    """Name only what this view's blockout actually contains, so the painter does not add furniture that is elsewhere.
    An object whose look was planned (shapes/plan.json) goes by that look instead of its label."""
    sid = surfaces(i)[1]
    share = np.bincount(sid.ravel(), minlength=6 + len(objs)) / sid.size
    seen = {}
    for oi, o in enumerate(objs):
        if share[6 + oi] > 0.005:
            name = LOOKS.get(oi) or re.sub(r"[_\d]+", " ", o["name"]).strip()
            seen[name] = seen.get(name, 0) + share[6 + oi]
    names = [n for n, _ in sorted(seen.items(), key=lambda kv: -kv[1])][:6]
    what = ("In view: " + ", ".join(names) + ".") if names else "A bare stretch of wall and floor."
    return f"interior photo, {style}. {what}"

def speed_patches():
    """mflux is patched in memory, not on disk. Measured on this Mac at 1024x768: a step drops from about 15.3 s to
    12.2 s and the slow first step on later views (up to 33 s) goes away."""
    import dataclasses, mlx.core as mx
    from mflux.models.z_image.variants.controlnet.controlnet_util import ZImageControlnetUtil
    from mflux.models.z_image.model.z_image_text_encoder.prompt_encoder import PromptEncoder
    enc = ZImageControlnetUtil.encode_controls
    def encode_controls(*a, **k):      # keep the transformer in bfloat16: float32 control latents drag every layer to float32
        r = enc(*a, **k)
        return dataclasses.replace(r, control_latents=[x.astype(mx.bfloat16) for x in r.control_latents])
    ZImageControlnetUtil.encode_controls = staticmethod(encode_controls)
    # the blockout depth map is used as it is; by default mflux would run Depth Pro on it and use that estimate instead
    ZImageControlnetUtil._depth = staticmethod(lambda img: img.convert("RGB"))
    encode, cache = PromptEncoder.encode_prompt, {}
    def encode_prompt(*a, **k):        # each distinct prompt is encoded once
        key = k.get("prompt")
        if key not in cache:
            cache[key] = encode(*a, **k); mx.eval(cache[key])
        return cache[key]
    PromptEncoder.encode_prompt = staticmethod(encode_prompt)

CN_FILE = "Z-Image-Turbo-Fun-Controlnet-Union-2.1-2601-8steps.safetensors"   # distilled for 8 steps: far more detail than the base file
KEEP = {}   # set per view: {"ref": picture, "mask": L image, white = already decided}

def painter_patches():
    """Load the distilled ControlNet file, and feed its inpaint channels. The ControlNet takes 33 channels: 16 for the
    depth map, 1 mask (1 = keep) and 16 for a picture of the pixels to keep. mflux fills the last 17 with zeros."""
    import dataclasses, mlx.core as mx
    from mflux.models.z_image.z_image_initializer import ZImageInitializer
    from mflux.models.z_image.weights.z_image_controlnet_weight_definition import ZImageControlnetWeightDefinition
    from mflux.models.z_image.variants.controlnet.controlnet_util import ZImageControlnetUtil
    from mflux.models.z_image.latent_creator import ZImageLatentCreator
    from mflux.utils.image_util import ImageUtil
    ZImageInitializer._controlnet_file_pattern = staticmethod(lambda repo_id: CN_FILE)
    comp = ZImageControlnetWeightDefinition.get_controlnet_component
    # weight_files is required: without it every .safetensors in the folder is loaded and the base file overwrites this one
    ZImageControlnetWeightDefinition.get_controlnet_component = staticmethod(lambda: dataclasses.replace(comp(), weight_files=[CN_FILE]))
    enc = ZImageControlnetUtil.encode_controls
    def encode_controls(*a, **k):
        r = enc(*a, **k)
        if not KEEP: return r
        vae, w, h = k["vae"], k["width"], k["height"]
        lat = r.control_latents[0]
        keep = np.asarray(KEEP["mask"].convert("L").resize((w, h), Image.NEAREST), np.float32) / 255 > 0.5
        ref = ImageUtil.to_array(KEEP["ref"].convert("RGB").resize((w, h))) * mx.array(keep.astype(np.float32))[None, None]
        inp = ZImageLatentCreator.pack_latents(vae.encode(ref), height=h, width=w)
        m = np.asarray(Image.fromarray((keep * 255).astype(np.uint8)).resize((lat.shape[-1], lat.shape[-2]), Image.NEAREST), np.float32) / 255
        new = mx.concatenate([lat[:16], mx.array(m)[None, None].astype(lat.dtype), inp.astype(lat.dtype)], axis=0)
        return dataclasses.replace(r, control_latents=[new])
    ZImageControlnetUtil.encode_controls = staticmethod(encode_controls)

def carry_over(i, done):
    """What earlier pictures already show of view i: (picture, keep mask) at the working size, or None.
    A pixel is carried over when an earlier view sees the same surface at the same place; the first view to do so wins,
    so every surface keeps the look it was first given."""
    t, sid, nrm = surfaces(i)
    eye, d = B.rays(B.CAMS[str(i)]); P = eye + d * t[..., None]
    shape = np.abs(nrm).sum(-1) > 0
    col = np.zeros((B.H, B.W, 3), np.float32); have = np.zeros((B.H, B.W), bool)
    for v, (img, t_v, sid_v, halo_v) in done.items():
        px, py, dist, z = B.project(B.CAMS[str(v)], P)
        xi, yi = np.round(px).astype(int), np.round(py).astype(int)
        ok = (z > 0.05) & (xi >= 1) & (xi < B.W - 1) & (yi >= 1) & (yi < B.H - 1)
        xi, yi = np.clip(xi, 0, B.W - 1), np.clip(yi, 0, B.H - 1)
        ok &= (sid_v[yi, xi] == sid) & (np.abs(t_v[yi, xi] - dist) < np.maximum(0.05, 0.01 * dist)) & ~have & ~halo_v[yi, xi]
        if shape.any():                 # what an earlier view saw of a shape side-on is a smear: paint it afresh instead
            to = np.array(B.CAMS[str(v)][0]) - P
            ok &= ~shape | ((to * nrm).sum(-1) >= GRAZE * np.linalg.norm(to, axis=-1))
        col[ok] = img[yi[ok], xi[ok]]; have |= ok
    # stay clear of silhouettes, where reprojection is least reliable (a 13 px minimum filter shrinks the mask by 6 px)
    have = np.asarray(Image.fromarray((have * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(13))) > 127
    if have.mean() < 0.03: return None
    return Image.fromarray(col.astype(np.uint8)), Image.fromarray((have * 255).astype(np.uint8))

def gen(name, style):
    from mflux.models.z_image.variants.controlnet.control_types import ControlSpec, ControlType
    from mflux.models.z_image.variants.controlnet.z_image_turbo_controlnet import ZImageTurboControlnet
    out = f"{D}/{name}/images"; os.makedirs(out, exist_ok=True)
    pw, ph = (int(v) for v in os.environ.get("WORLD_PAINT", f"{B.W}x{B.H}").split("x"))
    chain = os.environ.get("WORLD_CHAIN", "1") != "0"
    steps = 6 if RING <= 8 else 8                                  # the quick level trades a little detail for time
    meta_path, meta = f"{D}/{name}/views.json", {"views": RING, "painted": N, "room": [RW, RH, RD], "paint": [pw, ph], "style": style, "chain": chain, "file": CN_FILE}
    # views painted against boxes, or against other shapes, are stale; a world without shapes keeps the meta it always had
    if SHAPES: meta["shapes"] = {"meshes": SHAPE_SUMS, "looks": {str(oi): l for oi, l in LOOKS.items()}}
    if not os.path.exists(meta_path) or json.load(open(meta_path)) != meta:   # anything painted for another setup is stale
        for f in os.listdir(out): os.remove(f"{out}/{f}")
    json.dump(meta, open(meta_path, "w"))
    todo = [i for i in range(N) if not os.path.exists(f"{out}/{i:02d}.png")]
    if not todo: return print("all views already painted")
    speed_patches(); painter_patches()
    model = ZImageTurboControlnet(quantize=8)
    done = {}                                                   # view -> (picture at working size, depth, surface ids)
    def remember(i):
        t, sid, _ = surfaces(i)
        done[i] = (np.asarray(Image.open(f"{out}/{i:02d}.png").convert("RGB").resize((B.W, B.H), Image.LANCZOS), np.float32), t, sid, halo(sid))
    if chain:
        for i in range(N):
            if i not in todo: remember(i)
    for i in todo:
        t = time.time()
        print(f"STAGE: painting view {i + 1} of {N}", flush=True)
        KEEP.clear()
        got = carry_over(i, done) if chain and done else None
        if got: KEEP.update(ref=got[0], mask=got[1])
        img = model.generate_image(seed=7, prompt=view_prompt(i, style), controlnet_strength=1.0, num_inference_steps=steps, width=pw, height=ph,
                                   controls=[ControlSpec(type=ControlType.depth, image_path=f"{D}/depth/{i:02d}.png", strength=0.9)])
        img.save(f"{out}/{i:02d}.tmp.png"); os.replace(f"{out}/{i:02d}.tmp.png", f"{out}/{i:02d}.png")   # never leave a half-written picture
        if chain: remember(i)
        kept = 100 * np.asarray(got[1]).mean() / 255 if got else 0
        print(name, i, round(time.time() - t), "s", "carried over %.0f%%" % kept, flush=True)

if __name__ == "__main__":
    {"prep": prep, "gen": gen}[sys.argv[1]](*sys.argv[2:])
