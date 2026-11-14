"""Depth Pro on every undistorted photo -> raw float depth maps (run in the mflux environment).  photo_depth.py IMAGES_DIR OUT_DIR"""
import sys, os, time, numpy as np, mlx.core as mx
from mflux.models.depth_pro.model.depth_pro import DepthPro
src, out = sys.argv[1:3]; os.makedirs(out, exist_ok=True)
dp = DepthPro()
for f in sorted(os.listdir(src)):
    t = time.time()
    arr, h, w = DepthPro._pre_process(os.path.join(src, f))
    d = dp._depth_pro_model(*DepthPro._create_patches(arr))
    d = np.asarray(d.astype(mx.float32)).squeeze()
    np.save(os.path.join(out, os.path.splitext(f)[0] + ".npy"), d.astype(np.float32))
    print(f, d.shape, "range", float(d.min()), float(d.max()), round(time.time() - t, 1), "s", flush=True)
print("peak GB", mx.get_peak_memory() / 1e9)
