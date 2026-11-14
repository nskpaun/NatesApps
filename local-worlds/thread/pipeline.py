"""End-to-end pipelines, run from this folder.
  pipeline.py photos WORLD_DIR "Name"                    WORLD_DIR/raw/* photos -> splat + mesh + collider
  pipeline.py prompt WORLD_DIR "Name" "LAYOUT" "STYLE"   sentence + style -> blockout -> pictures -> splat
Each step prints a 'STAGE: ...' line. On success the world is added to scenes.json.
"""
import sys, os, json, subprocess, shutil, glob, socket, time
HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, ".venv/bin/python")                 # splat training, meshing
PY_IMG = os.path.join(HERE, "../spike/.venv/bin/python")    # image and depth models (mflux)

def stage(t): print("STAGE: " + t, flush=True)
def run(cmd, env=None, quiet=False):
    r = subprocess.run(cmd, cwd=HERE, env={**os.environ, **(env or {})}, stdout=subprocess.DEVNULL if quiet else None, stderr=subprocess.STDOUT if not quiet else subprocess.DEVNULL)
    if r.returncode: raise SystemExit(f"Step failed: {' '.join(map(str, cmd[:3]))}")

def register(entry):
    path = os.path.join(HERE, "scenes.json")
    scenes = [s for s in json.load(open(path)) if s["name"] != entry["name"]] + [entry]
    json.dump(scenes, open(path + ".tmp", "w"), indent=1); os.replace(path + ".tmp", path)

def photos(d, name):
    rel = "/" + os.path.relpath(d, HERE)
    raw = sorted(glob.glob(f"{d}/raw/*"))
    if len(raw) < 8: raise SystemExit(f"Need at least 8 photos, got {len(raw)}")
    stage(f"converting {len(raw)} photos")
    os.makedirs(f"{d}/images", exist_ok=True)
    for i, f in enumerate(raw):
        run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "92", "-Z", "1920", f, "--out", f"{d}/images/{i:03d}.jpg"], quiet=True)
    stage("solving camera positions")
    for p in ("db.db", "sparse", "dense", "txt"):
        shutil.rmtree(f"{d}/{p}", ignore_errors=True) if os.path.isdir(f"{d}/{p}") else (os.path.exists(f"{d}/{p}") and os.remove(f"{d}/{p}"))
    run(["colmap", "feature_extractor", "--database_path", f"{d}/db.db", "--image_path", f"{d}/images", "--ImageReader.single_camera", "0", "--ImageReader.camera_model", "SIMPLE_RADIAL"], quiet=True)
    run(["colmap", "exhaustive_matcher", "--database_path", f"{d}/db.db"], quiet=True)
    os.makedirs(f"{d}/sparse"); run(["colmap", "mapper", "--database_path", f"{d}/db.db", "--image_path", f"{d}/images", "--output_path", f"{d}/sparse"], quiet=True)
    models = glob.glob(f"{d}/sparse/*/")
    if not models: raise SystemExit("Could not solve camera positions: the photos need more overlap")
    best = max(models, key=lambda m: os.path.getsize(m + "images.bin"))
    run(["colmap", "image_undistorter", "--image_path", f"{d}/images", "--input_path", best, "--output_path", f"{d}/dense", "--output_type", "COLMAP"], quiet=True)
    os.makedirs(f"{d}/dense/sparse/0")
    for b in glob.glob(f"{d}/dense/sparse/*.bin"): shutil.move(b, f"{d}/dense/sparse/0/")
    os.makedirs(f"{d}/txt"); run(["colmap", "model_converter", "--input_path", f"{d}/dense/sparse/0", "--output_path", f"{d}/txt", "--output_type", "TXT"], quiet=True)
    n_reg = len([l for l in open(f"{d}/txt/images.txt") if l[0] != "#"]) // 2
    print(f"registered {n_reg} of {len(raw)} photos", flush=True)
    if n_reg < 5: raise SystemExit(f"Only {n_reg} photos could be placed: the photos need more overlap")
    stage(f"training the splat ({n_reg} photos placed)")
    run([PY, "train_scene.py", f"{d}/dense", f"{d}/scene", "7000"])
    shutil.copy(f"{d}/scene_scene.json", f"{d}/scene.json")
    stage("estimating depth for each photo")
    run([PY_IMG, "photo_depth.py", f"{d}/dense/images", f"{d}/mono"])
    stage("building the mesh and collider")
    run([PY, "mesh_photos.py", d, f"{d}/mesh"])
    s = json.load(open(f"{d}/scene.json"))
    register({"name": name, "ply": f"{rel}/scene.ply", "mesh": f"{rel}/mesh.glb", "collider": f"{rel}/mesh_collider.glb", "up": s["up"], "center": s["center"],
              "eye": s["eye"], "forward": s["forward"], "note": f"{n_reg} photos, {s['splats'] // 1000}k splats", "kind": "photos"})
    stage("done")

def port_open(p):
    with socket.socket() as k:
        k.settimeout(0.3); return k.connect_ex(("127.0.0.1", p)) == 0

def prompt(d, name, layout, style):
    rel = "/" + os.path.relpath(d, HERE)
    os.makedirs(d, exist_ok=True)
    env = {"WORLD_DIR": os.path.relpath(d, HERE), "WORLD_VIEWS": os.environ.get("WORLD_VIEWS", "12")}
    n_views = int(env["WORLD_VIEWS"])
    painted = os.path.exists(f"{d}/boxes.json") and len(glob.glob(f"{d}/gen/images/*.png")) >= n_views
    if not painted:                                     # a re-run of the same world reuses its painted views
        stage("planning the layout")
        started = None
        if not port_open(11434):
            started = subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(60):
                if port_open(11434): break
                time.sleep(0.25)
        try:
            run([PY, "llm_boxes.py", layout, f"{d}/boxes.json"])
        finally:
            if started: started.terminate()            # one model in memory at a time
        pieces = ", ".join(dict.fromkeys(o["name"].replace("_", " ") for o in json.load(open(f"{d}/boxes.json"))["objects"]))
        stage("rendering the blockout")
        run([PY, "chisel_ring.py", "prep"], env)
        stage("painting views")
        run([PY_IMG, "chisel_ring.py", "gen", "gen", f"interior photo, {style}, with {pieces}"], env)
    pieces = ", ".join(dict.fromkeys(o["name"].replace("_", " ") for o in json.load(open(f"{d}/boxes.json"))["objects"]))
    stage("making the views agree")
    run([PY, "consistent.py", "gen"], env)
    stage("training the splat")
    run([PY, "train_scene.py", f"{d}/gen_c", f"{d}/gen_c/gen_c", "10000"])
    stage("building the mesh and collider")
    run([PY, "blockout_mesh.py", "gen_c"], env)
    s = json.load(open(f"{d}/gen_c/gen_c_scene.json"))
    register({"name": name, "ply": f"{rel}/gen_c/gen_c.ply", "mesh": f"{rel}/gen_c/gen_c_mesh.glb", "collider": f"{rel}/gen_c/gen_c_mesh_collider.glb", "up": s["up"], "center": s["center"],
              "eye": s["eye"], "forward": s["forward"], "metre": json.load(open(f"{d}/gen_c/gen_c_metre.json"))["metre"], "flat": True, "lamp": 5,
              "note": f"invented: {layout[:60]}", "kind": "prompt"})
    stage("done")

if __name__ == "__main__":
    {"photos": photos, "prompt": prompt}[sys.argv[1]](os.path.abspath(sys.argv[2]), *sys.argv[3:])
