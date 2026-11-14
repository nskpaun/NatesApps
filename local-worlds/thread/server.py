"""Local server for the viewer: static files plus a small job API. Binds to 127.0.0.1 only.
  server.py PORT
  GET  /api/status                      current or last job
  POST /api/upload?job=ID&name=FILE     raw photo bytes (call once per photo, before starting a photos job)
  POST /api/jobs                        JSON {type:"photos", id, name} or {type:"prompt", name, layout, style, views}
  POST /api/cancel
  POST /api/stitch                      JSON {name, parts:[{ref, x, z, rot}]}: save several worlds placed side by side as one
One job runs at a time, so only one large model is in memory at once. A cancelled job stays busy ("cancelling": true in
/api/status, with "state" still "running" so older viewers keep polling) until its processes have really gone.
"""
import sys, os, json, re, time, threading, subprocess, signal, secrets
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
HERE = os.path.dirname(os.path.abspath(__file__))
WORLDS = os.path.join(HERE, "worlds")
job = {"state": "idle"}; proc = None; lock = threading.Lock()
slug = lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "world"

def kill(p, sig=signal.SIGTERM):
    try: os.killpg(p.pid, sig)
    except (ProcessLookupError, PermissionError): pass

def halt(p, rec):
    """Ask a job's process group to stop, and force it after 8 s if the run has still not finished. The test is the run's
    record, not the leader: pipeline.py dies at once on SIGTERM, but a child that ignores it keeps the run (and its memory) alive."""
    kill(p); t = threading.Timer(8, lambda: rec["state"] == "cancelling" and kill(p, signal.SIGKILL)); t.daemon = True; t.start()

def run_job(args, rec, env):
    """rec is this run's own record: a later job replaces the global `job`, and must not be written to from here."""
    global proc
    log = os.path.join(WORLDS, rec["id"], "job.log"); os.makedirs(os.path.dirname(log), exist_ok=True)
    rec.update(stage="starting", started=time.time(), error=None, log=[])
    code, last, p = 1, "", None
    try:
        with open(log, "w") as lf:
            with lock:
                p = proc = subprocess.Popen([sys.executable, "-u", "pipeline.py", *args], cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
                if rec["state"] == "cancelling": halt(p, rec)     # Cancel arrived before the process existed
            for line in p.stdout:
                lf.write(line); line = line.strip()
                if line.startswith("STAGE: "): rec["stage"] = line[7:]
                elif line and "%|" not in line and not line.startswith("Step failed"): last = line; rec["log"] = (rec["log"] + [line])[-6:]
            code = p.wait()
    except Exception as e: last = last or f"{type(e).__name__}: {e}"
    with lock:
        rec["finished"] = time.time()
        if rec["state"] == "cancelling": rec["state"] = "cancelled"
        elif code == 0: rec["state"] = "done"
        else: rec.update(state="failed", error=last or f"exit code {code}")
        if proc is p: proc = None

class H(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm", ".glb": "model/gltf-binary"}
    def __init__(self, *a, **k): super().__init__(*a, directory=HERE, **k)
    def log_message(self, *a): pass
    def end_headers(self):
        if self.path.split("?")[0].endswith((".json", ".html", ".js")): self.send_header("Cache-Control", "no-store")
        super().end_headers()
    def send_json(self, obj, code=200):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith("/api/status"):
            j = dict(job)
            if j["state"] == "cancelling": j.update(state="running", stage="cancelling", cancelling=True)
            return self.send_json({**j, "elapsed": round((j.get("finished") or time.time()) - j["started"]) if "started" in j else 0})
        if any(part.startswith(".") for part in urlparse(self.path).path.split("/")): return self.send_error(404)
        super().do_GET()
    def do_POST(self):
        try: self.post()
        except Exception as e:      # a bad request must get an answer the page can show, not a dropped connection
            bad = isinstance(e, (KeyError, ValueError, TypeError, AttributeError, IndexError))
            try: self.send_json({"error": f"Bad request ({type(e).__name__}: {e})" if bad else f"{type(e).__name__}: {e}"}, 400 if bad else 500)
            except Exception: pass
    def post(self):
        global job
        u = urlparse(self.path); q = parse_qs(u.query); n = int(self.headers.get("Content-Length", 0))
        if u.path == "/api/upload":
            jid, name = slug(q["job"][0]), re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(q["name"][0]))
            if n > 80e6: return self.send_json({"error": "file too large"}, 413)
            d = os.path.join(WORLDS, jid, "raw"); os.makedirs(d, exist_ok=True)
            data = self.rfile.read(n)
            if len(data) != n: return self.send_json({"error": "upload was cut short"}, 400)
            with lock:      # a counter in front keeps two photos with the same (or same-looking) name apart, and keeps upload order
                k = len(os.listdir(d))
                while any(f.startswith(f"{k:04d}_") for f in os.listdir(d)): k += 1
                with open(os.path.join(d, f"{k:04d}_{name}"), "wb") as f: f.write(data)
            return self.send_json({"ok": True, "count": len(os.listdir(d))})
        if u.path == "/api/cancel":
            with lock:
                p = proc
                if job["state"] == "running":
                    job["state"] = "cancelling"
                    if p: halt(p, job)
            return self.send_json({"ok": True})
        if u.path == "/api/stitch":
            body = json.loads(self.rfile.read(n) or b"{}"); path = os.path.join(HERE, "scenes.json")
            with lock:
                scenes = json.load(open(path)); single = {s["name"] for s in scenes if "parts" not in s}
                parts = [{"ref": p["ref"], "x": float(p["x"]), "z": float(p["z"]), "rot": float(p["rot"])} for p in body.get("parts", []) if p.get("ref") in single]
                if len(parts) < 2: return self.send_json({"error": "Pick at least two worlds to stitch"}, 400)
                name = (body.get("name") or "").strip()[:60] or "Stitched world"; base, k = name, 2
                while name in {s["name"] for s in scenes}: name, k = f"{base} {k}", k + 1
                scenes.append({"name": name, "kind": "stitched", "parts": parts, "note": f"{len(parts)} worlds stitched"})
                json.dump(scenes, open(path + ".tmp", "w"), indent=1); os.replace(path + ".tmp", path)
            return self.send_json({"ok": True, "name": name})
        if u.path == "/api/jobs":
            body = json.loads(self.rfile.read(n) or b"{}")
            with lock:
                if job["state"] == "cancelling": return self.send_json({"error": "The last world is still stopping. Try again in a moment."}, 409)
                if job["state"] == "running" or proc: return self.send_json({"error": "A world is already being built"}, 409)
                name = (body.get("name") or "").strip()[:60] or "Untitled world"
                existing = {s["name"] for s in json.load(open(os.path.join(HERE, "scenes.json")))}
                base, k = name, 2
                while name in existing: name, k = f"{base} {k}", k + 1
                env = dict(os.environ)
                if body.get("type") == "photos":
                    jid = slug(body["id"]); args = ["photos", os.path.join(WORLDS, jid), name]
                elif body.get("type") == "prompt":
                    if not body.get("layout", "").strip() or not body.get("style", "").strip(): return self.send_json({"error": "Describe both the layout and the style"}, 400)
                    jid = f"{slug(name)}-{secrets.token_hex(3)}"; args = ["prompt", os.path.join(WORLDS, jid), name, body["layout"].strip()[:600], body["style"].strip()[:600]]
                    env["WORLD_VIEWS"] = str(max(8, min(16, int(body.get("views", 12)))))
                else: return self.send_json({"error": "unknown job type"}, 400)
                job = {"state": "running", "id": jid, "name": name, "type": body["type"]}      # a fresh record per run
                threading.Thread(target=run_job, args=(args, job, env), daemon=True).start()
            return self.send_json({"ok": True, "id": jid, "name": name})
        self.send_error(404)

if __name__ == "__main__":
    if not os.path.exists(os.path.join(HERE, "scenes.json")): json.dump([], open(os.path.join(HERE, "scenes.json"), "w"))
    srv = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H)
    def stop(*_):
        if proc: kill(proc)
        os._exit(0)
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    print("serving on http://127.0.0.1:" + sys.argv[1], flush=True); srv.serve_forever()
