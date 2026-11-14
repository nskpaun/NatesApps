import sys, os, json, numpy as np
from PIL import Image
sys.path.insert(0, os.getcwd())
import chisel_ring as C
B = C.B
D, out = C.D, sys.argv[1]
ids = C.PRIM_OBJ
rows = []
for k, cam in B.CAMS.items():
    t, P, sid = B.trace(cam, ids)
    for oi, o in enumerate(C.objs):
        m = sid == 6 + oi
        if m.sum() < 500: continue
        ys, xs = np.nonzero(m)
        edge = xs.min() == 0 or ys.min() == 0 or xs.max() == B.W - 1 or ys.max() == B.H - 1
        rows.append((o["name"], int(k), int(m.sum()), edge, xs.min(), xs.max(), ys.min(), ys.max()))
for r in sorted(rows): print(*r)
best = {}
for r in rows:
    if r[0].startswith("car") and not r[3] and r[2] > best.get(r[0], (0, 0, 0))[2]: best[r[0]] = r
for name, r in best.items():
    k = r[1]
    img = Image.open(f"{D}/gen/images/{k:02d}.png").convert("RGB")
    t, P, sid = B.trace(B.CAMS[str(k)], ids)
    m = Image.fromarray(((sid == 6 + [o["name"] for o in C.objs].index(name)) * 255).astype(np.uint8)).resize(img.size, Image.NEAREST)
    sx = img.size[0] / B.W
    box = [int(r[4] * sx) - 8, int(r[6] * sx) - 8, int(r[5] * sx) + 8, int(r[7] * sx) + 8]
    rgba = img.copy(); rgba.putalpha(m)
    rgba.crop(box).save(f"{out}/{name}_v{k}_masked.png")
    img.crop(box).save(f"{out}/{name}_v{k}_plain.png")
    print("saved", name, k, box)
