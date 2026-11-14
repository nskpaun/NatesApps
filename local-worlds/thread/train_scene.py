"""COLMAP-format dataset -> splat PLY + scene.json (poses, up, start view).  train_scene.py DATASET OUT_PREFIX ITERS [UP_FROM_Y]"""
import sys, json, numpy as np, msplat
from PIL import Image
src, out, iters = sys.argv[1], sys.argv[2], int(sys.argv[3])
ds = msplat.load_dataset(src)
cfg = msplat.TrainingConfig(); cfg.iterations = iters
tr = msplat.GaussianTrainer(ds, cfg); tr.train(lambda s: None, iters)
tr.export_ply(out + ".ply")
n = ds.num_train
poses = np.array([np.array(ds.camera_pose(i), np.float32).reshape(4, 4) for i in range(n)])
up = poses[:, :3, 1].mean(0); up /= np.linalg.norm(up)
json.dump({"up": up.tolist(), "center": poses[:, :3, 3].mean(0).tolist(), "poses": poses.tolist(),
           "eye": poses[0, :3, 3].tolist(), "forward": (-poses[0, :3, 2]).tolist(), "splats": tr.splat_count}, open(out + "_scene.json", "w"))
for j in (0, n // 2):
    A, B = poses[j], poses[(j + 1) % n]; M = A.copy(); M[:3, 3] = (A[:3, 3] + B[:3, 3]) / 2
    Image.fromarray((np.clip(tr.render_from_pose(M, j), 0, 1) * 255).astype(np.uint8)).save(f"{out}_novel{j}.jpg")
print("splats", tr.splat_count)
