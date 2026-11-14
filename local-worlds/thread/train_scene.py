"""COLMAP-format dataset -> splat PLY + scene.json (poses, up, start view, training focal and width).
train_scene.py DATASET OUT_PREFIX ITERS [--downscales N] [--res-schedule N] [--sh N] [--eval-every N]
Flags left out keep msplat's defaults (2 downscales, 3000 steps each, SH degree 3), i.e. the behaviour before the flags existed.
--eval-every N holds out every Nth photo and prints psnr/ssim/l1. MEASUREMENT ONLY: scene.json then has fewer poses than
the dataset, which breaks mesh_photos.py's camera-count match, so point OUT_PREFIX at a scratch folder."""
import sys, os, json, struct, time, argparse, numpy as np

def parse(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("src"); p.add_argument("out"); p.add_argument("iters", type=int)
    p.add_argument("legacy", nargs="?", help=argparse.SUPPRESS)  # the old docstring's UP_FROM_Y, never read
    p.add_argument("--downscales", type=int, help="TrainingConfig.num_downscales")
    p.add_argument("--res-schedule", type=int, help="TrainingConfig.resolution_schedule (steps per downscale level)")
    p.add_argument("--sh", type=int, choices=(0, 1, 2, 3), help="TrainingConfig.sh_degree")
    p.add_argument("--eval-every", type=int, default=0, help="hold out every Nth photo and print the score (measurement only)")
    return p.parse_args(argv)

def camera_use(d):
    """{camera_id: number of photos using it} from COLMAP images.bin (else images.txt) in folder d; {} if unreadable."""
    use = {}
    try:
        b, t = (os.path.join(d, "images" + e) for e in (".bin", ".txt"))
        if os.path.exists(b):
            buf = open(b, "rb").read(); o = 8
            for _ in range(struct.unpack_from("<Q", buf, 0)[0]):  # int32 id, 7 doubles, int32 camera_id, name NUL, uint64 n, n*24 bytes
                c = struct.unpack_from("<i", buf, o + 60)[0]; o = buf.index(b"\0", o + 64) + 1
                o += 8 + 24 * struct.unpack_from("<Q", buf, o)[0]; use[c] = use.get(c, 0) + 1
        elif os.path.exists(t):
            rows = [l for l in open(t) if not l.startswith("#")]
            for l in rows[::2]:  # image lines alternate with (possibly empty) 2D point lines
                s = l.split()
                if len(s) > 8: use[int(s[8])] = use.get(int(s[8]), 0) + 1
    except Exception: pass  # truncated or odd file: whatever was counted so far
    return use

def intrinsics(src):
    """(focal px, image width px) from the dataset's COLMAP cameras file, or None. msplat's Dataset exposes poses only.
    With several cameras (photo sets usually have one odd photo with its own), the camera most photos use wins; the
    median-focal one only if the images file is missing. fx is params[0] in every COLMAP camera model."""
    for d in ("sparse/0", "sparse", "."):  # .bin first: COLMAP readers prefer it when both exist
        cams = {}; b, t = (os.path.join(src, d, "cameras" + e) for e in (".bin", ".txt"))
        if os.path.exists(b):
            NP = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12, 7: 5, 8: 4, 9: 5, 10: 12}  # params per model id
            f = open(b, "rb")
            for _ in range(struct.unpack("<Q", f.read(8))[0]):
                cid, model, w, _ = struct.unpack("<iiQQ", f.read(24))
                if model not in NP: break  # newer COLMAP model: param count unknown, so the rest cannot be read
                cams[cid] = (struct.unpack(f"<{NP[model]}d", f.read(8 * NP[model]))[0], int(w))
        elif os.path.exists(t):
            for l in open(t):
                s = l.split()
                if len(s) > 4 and not l.startswith("#"): cams[int(s[0])] = (float(s[4]), int(s[2]))
        if cams:
            use = {c: k for c, k in camera_use(os.path.join(src, d)).items() if c in cams}
            return cams[max(use, key=lambda c: (use[c], -c))] if use else sorted(cams.values())[len(cams) // 2]
    return None

def final_downscale(cfg, iters):
    """msplat's image downscale at the last step (model.cpp getDownscaleFactor); 1 unless the run ends before full resolution."""
    return 1 << max(cfg.num_downscales - (iters - 1) // max(cfg.resolution_schedule, 1), 0)

def main(a):
    import msplat
    from PIL import Image
    src, out, iters = a.src, a.out, a.iters
    ds = msplat.load_dataset(src, eval_mode=True, test_every=a.eval_every) if a.eval_every > 0 else msplat.load_dataset(src)
    cfg = msplat.TrainingConfig(); cfg.iterations = iters
    if a.downscales is not None: cfg.num_downscales = a.downscales
    if a.res_schedule is not None: cfg.resolution_schedule = a.res_schedule
    if a.sh is not None: cfg.sh_degree = a.sh
    print("config", {k: getattr(cfg, k) for k in ("iterations", "num_downscales", "resolution_schedule", "sh_degree")}, flush=True)
    t0 = time.time()
    tr = msplat.GaussianTrainer(ds, cfg); tr.train(lambda s: None, iters)  # 2nd arg is callback_every, not a step count
    secs = time.time() - t0
    tr.export_ply(out + ".ply")
    n = ds.num_train
    poses = np.array([np.array(ds.camera_pose(i), np.float32).reshape(4, 4) for i in range(n)])
    up = poses[:, :3, 1].mean(0); up /= np.linalg.norm(up)
    # start in the middle of where the photos were taken: the first photo can be an outlier (shot from a doorway, say)
    start = int(np.argmin(np.linalg.norm(poses[:, :3, 3] - np.median(poses[:, :3, 3], axis=0), axis=1)))
    scene = {"up": up.tolist(), "center": poses[:, :3, 3].mean(0).tolist(), "poses": poses.tolist(),
             "eye": poses[start, :3, 3].tolist(), "forward": (-poses[start, :3, 2]).tolist(), "splats": tr.splat_count}
    try: fw = intrinsics(src)
    except Exception: fw = None  # optional fields must never cost a finished training run its scene.json
    if fw:  # optional fields: the viewer falls back when they are missing
        k = final_downscale(cfg, iters); scene["focal"], scene["width"] = fw[0] / k, fw[1] // k
    json.dump(scene, open(out + "_scene.json", "w"))
    for j in (0, n // 2):
        A, B = poses[j], poses[(j + 1) % n]; M = A.copy(); M[:3, 3] = (A[:3, 3] + B[:3, 3]) / 2
        Image.fromarray((np.clip(tr.render_from_pose(M, j), 0, 1) * 255).astype(np.uint8)).save(f"{out}_novel{j}.jpg")
    print("splats", tr.splat_count)
    if a.eval_every > 0:
        e = tr.evaluate()
        print("eval", json.dumps({"psnr": round(float(e["psnr"]), 3), "ssim": round(float(e["ssim"]), 4), "l1": round(float(e["l1"]), 5),
              "train_s": round(secs, 1), "splats": tr.splat_count, "ply_mb": round(os.path.getsize(out + ".ply") / 1e6, 1),
              "held_out": ds.num_test, "trained_on": n}))

if __name__ == "__main__": main(parse(sys.argv[1:]))
