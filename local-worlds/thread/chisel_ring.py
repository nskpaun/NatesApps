"""Boxes -> ring of depth maps -> depth-guided pictures -> COLMAP-format dataset for the splat trainer.
  chisel_ring.py prep                 depth maps + cameras
  chisel_ring.py gen NAME "PROMPT"    pictures (model loaded once)
  chisel_ring.py colmap NAME          write chisel/NAME/{images,sparse/0}
"""
import sys, json, os, time
import numpy as np
from PIL import Image
sys.path.insert(0, "../spike")
import blockout as B

N, D = int(os.environ.get("WORLD_VIEWS", "16")), os.environ.get("WORLD_DIR", "chisel")
objs = json.load(open(f"{D}/boxes.json"))["objects"]
B.BOXES = [(tuple(b["min"]), tuple(b["max"])) for o in objs for b in o["boxes"]]
c = np.array([2.0, 0.0, 2.0])
B.CAMS = {}
for i in range(N):
    a = 2 * np.pi * i / N
    off = np.array([np.cos(a), 0, np.sin(a)])
    eye = c + off * 1.3 + [0, 1.5, 0]
    B.CAMS[str(i)] = (tuple(eye), tuple(c - off * 1.6 + [0, 0.8, 0]))

def prep():
    os.makedirs(f"{D}/depth", exist_ok=True)
    for k, cam in B.CAMS.items():
        t, P = B.trace(cam)
        inv = 1 / np.maximum(t, 0.3)
        img = (inv - inv.min()) / (inv.max() - inv.min())
        Image.fromarray((img * 255).astype(np.uint8)).convert("RGB").save(f"{D}/depth/{int(k):02d}.png")
        np.save(f"{D}/depth/{int(k):02d}.npy", P.astype(np.float32))
    print("depth maps", N)

def gen(name, prompt):
    from mflux.models.z_image.variants.controlnet.control_types import ControlSpec, ControlType
    from mflux.models.z_image.variants.controlnet.z_image_turbo_controlnet import ZImageTurboControlnet
    os.makedirs(f"{D}/{name}/images", exist_ok=True)
    model = ZImageTurboControlnet(quantize=8)
    for i in range(N):
        t = time.time()
        img = model.generate_image(seed=7, prompt=prompt, controlnet_strength=1.0, num_inference_steps=9, width=B.W, height=B.H,
                                   controls=[ControlSpec(type=ControlType.depth, image_path=f"{D}/depth/{i:02d}.png", strength=0.9)])
        img.save(f"{D}/{name}/images/{i:02d}.png")
        print(f"STAGE: painting view {i + 1} of {N}", flush=True)
        print(name, i, round(time.time() - t), "s", flush=True)

def colmap(name):
    S = np.diag([1.0, 1, -1])  # mirror z: the blockout world is left-handed
    out = f"{D}/{name}/sparse/0"; os.makedirs(out, exist_ok=True)
    f = B.W / 2 / np.tan(np.radians(B.FOV) / 2)
    open(f"{out}/cameras.txt", "w").write(f"1 PINHOLE {B.W} {B.H} {f} {f} {B.W/2} {B.H/2}\n")
    im, pts = [], []
    rng = np.random.default_rng(0)
    for i in range(N):
        eye, r, u, fw = B.basis(B.CAMS[str(i)])
        R = np.stack([S @ -r, S @ -u, S @ fw])
        assert np.linalg.det(R) > 0.99
        t = -R @ (S @ eye)
        from scipy.spatial.transform import Rotation
        qx, qy, qz, qw = Rotation.from_matrix(R).as_quat(); q = [qw, qx, qy, qz]
        im.append(f"{i+1} {' '.join(map(str, q))} {' '.join(map(str, t))} 1 {i:02d}.png\n\n")
        P = np.load(f"{D}/depth/{i:02d}.npy").reshape(-1, 3)
        C = np.asarray(Image.open(f"{D}/{name}/images/{i:02d}.png").convert("RGB")).reshape(-1, 3)
        idx = rng.choice(len(P), 3000, replace=False)
        pts += [(S @ P[j], C[j]) for j in idx]
    open(f"{out}/images.txt", "w").write("".join(im))
    open(f"{out}/points3D.txt", "w").write("".join(f"{k+1} {p[0]} {p[1]} {p[2]} {c[0]} {c[1]} {c[2]} 0.5\n" for k, (p, c) in enumerate(pts)))
    os.system(f"colmap model_converter --input_path {out} --output_path {out} --output_type BIN 2>&1 | tail -3")
    print("colmap dataset", name, len(pts), "points", os.listdir(out))

if __name__ == "__main__":
    {"prep": prep, "gen": gen, "colmap": colmap}[sys.argv[1]](*sys.argv[2:])
