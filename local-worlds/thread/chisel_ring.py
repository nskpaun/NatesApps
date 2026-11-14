"""Blockout -> ring of depth maps -> depth-guided pictures.
  chisel_ring.py prep                depth maps + cameras
  chisel_ring.py gen NAME "STYLE"    pictures (model loaded once; already-painted views are skipped)
Environment: WORLD_DIR (the world's folder), WORLD_VIEWS (how many views), WORLD_PAINT (picture size, default 1024x768).
"""
import sys, json, os, re, time
import numpy as np
from PIL import Image
sys.path.insert(0, "../spike")
import blockout as B

N, D = int(os.environ.get("WORLD_VIEWS", "16")), os.environ.get("WORLD_DIR", "chisel")
world = json.load(open(f"{D}/boxes.json"))
objs = world["objects"]
RW, RH, RD = world.get("room", [4.0, 2.6, 4.0])
B.ROOM = ((0, 0, 0), (RW, RH, RD))
B.PRIMS = [p for o in objs for p in o["prims"]]
PRIM_OBJ = [oi for oi, o in enumerate(objs) for _ in o["prims"]]     # which object each primitive belongs to
c = np.array([RW / 2, 0.0, RD / 2])
EYE = 1.5 if RH < 3.2 else 1.7

def free(eye, margin=0.25):
    """A camera position that is not inside (or right against) any shape: the given spot, else the nearest free spot
    found by sliding towards or away from the room's centre. None if there is none."""
    eye = np.array(eye, float)
    clear = lambda e: not any(B.inside(e, p, margin) for p in B.PRIMS)
    inside_room = lambda e: 0.3 < e[0] < RW - 0.3 and 0.3 < e[2] < RD - 0.3
    for k in (1.0, 0.9, 1.1, 0.8, 1.2, 0.7, 1.3, 0.6, 0.5, 0.4, 0.3):
        e = eye.copy(); e[[0, 2]] = c[[0, 2]] + (eye[[0, 2]] - c[[0, 2]]) * k
        if inside_room(e) and clear(e): return e
    return None

B.CAMS = {}
for i in range(N):
    a = 2 * np.pi * i / N
    off = np.array([np.cos(a) * RW, 0, np.sin(a) * RD])               # an ellipse that follows the room's shape
    want = c + off * 0.325 + [0, EYE, 0]
    eye = free(want)
    if eye is None: eye = free(want, 0.0)
    if eye is None: eye = want                                        # a painted view must exist for every index
    B.CAMS[str(i)] = (tuple(eye), tuple(c - off * 0.4 + [0, 0.8, 0]))

def prep():
    os.makedirs(f"{D}/depth", exist_ok=True)
    for k, cam in B.CAMS.items():
        t, P = B.trace(cam)
        inv = 1 / np.maximum(t, 0.3)
        # robust contrast: a few very near pixels must not flatten the rest of the map, and far walls need visible steps
        lo, hi = np.percentile(inv, [1, 99])
        img = np.clip((inv - lo) / max(hi - lo, 1e-6), 0, 1) ** 0.6
        Image.fromarray((img * 255).astype(np.uint8)).convert("RGB").save(f"{D}/depth/{int(k):02d}.png")
        np.save(f"{D}/depth/{int(k):02d}.npy", P.astype(np.float32))
    print("depth maps", N)

def view_prompt(i, style):
    """Name only what this view's blockout actually contains, so the painter does not add furniture that is elsewhere."""
    _, _, sid = B.trace(B.CAMS[str(i)], PRIM_OBJ)
    share = np.bincount(sid.ravel(), minlength=6 + len(objs)) / sid.size
    seen = {}
    for oi, o in enumerate(objs):
        if share[6 + oi] > 0.005:
            name = re.sub(r"[_\d]+", " ", o["name"]).strip()
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

def gen(name, style):
    from mflux.models.z_image.variants.controlnet.control_types import ControlSpec, ControlType
    from mflux.models.z_image.variants.controlnet.z_image_turbo_controlnet import ZImageTurboControlnet
    out = f"{D}/{name}/images"; os.makedirs(out, exist_ok=True)
    pw, ph = (int(v) for v in os.environ.get("WORLD_PAINT", f"{B.W}x{B.H}").split("x"))
    meta_path, meta = f"{D}/{name}/views.json", {"views": N, "room": [RW, RH, RD], "paint": [pw, ph], "style": style}
    if not os.path.exists(meta_path) or json.load(open(meta_path)) != meta:   # anything painted for another setup is stale
        for f in os.listdir(out): os.remove(f"{out}/{f}")
    json.dump(meta, open(meta_path, "w"))
    todo = [i for i in range(N) if not os.path.exists(f"{out}/{i:02d}.png")]
    if not todo: return print("all views already painted")
    speed_patches()
    model = ZImageTurboControlnet(quantize=8)
    for i in todo:
        t = time.time()
        print(f"STAGE: painting view {i + 1} of {N}", flush=True)
        img = model.generate_image(seed=7, prompt=view_prompt(i, style), controlnet_strength=1.0, num_inference_steps=9, width=pw, height=ph,
                                   controls=[ControlSpec(type=ControlType.depth, image_path=f"{D}/depth/{i:02d}.png", strength=0.9)])
        img.save(f"{out}/{i:02d}.tmp.png"); os.replace(f"{out}/{i:02d}.tmp.png", f"{out}/{i:02d}.png")   # never leave a half-written picture
        print(name, i, round(time.time() - t), "s", flush=True)

if __name__ == "__main__":
    {"prep": prep, "gen": gen}[sys.argv[1]](*sys.argv[2:])
