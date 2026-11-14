"""Local server for the viewer: static files plus a small job API. Binds to 127.0.0.1 only.
  server.py PORT
  GET  /api/status                      current or last job
  POST /api/upload?job=ID&name=FILE     raw photo bytes (call once per photo, before starting a photos job)
  POST /api/jobs                        JSON {type:"photos", id, name} or {type:"prompt", name, layout, style, views}
  POST /api/cancel
One job runs at a time, so only one large model is in memory at once.
"""
import sys, os, json, re, time, threading, subprocess, signal, secrets
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
HERE = os.path.dirname(os.path.abspath(__file__))
WORLDS = os.path.join(HERE, "worlds")
job = {"state": "idle"}; proc = None; lock = threading.Lock()
slug = lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "world"

def run_job(args, meta):
    global proc
    log = os.path.join(WORLDS, meta["id"], "job.log"); os.makedirs(os.path.dirname(log), exist_ok=True)
    job.update(meta, state="running", stage="starting", started=time.time(), error=None, log=[])
    with open(log, "w") as lf:
        proc = subprocess.Popen([sys.executable, "-u", "pipeline.py", *args], cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        last = ""
        for line in proc.stdout:
            lf.write(line); line = line.strip()
            if line.startswith("STAGE: "): job["stage"] = line[7:]
            elif line and "%|" not in line: last = line; job["log"] = (job["log"] + [line])[-6:]
        code = proc.wait()
    job["finished"] = time.time()
    if job["state"] == "cancelled": pass
    elif code == 0: job["state"] = "done"
    else: job.update(state="failed", error=last or f"exit code {code}")
    proc = None

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
            return self.send_json({**job, "elapsed": round((job.get("finished") or time.time()) - job["started"]) if "started" in job else 0})
        if any(part.startswith(".") for part in urlparse(self.path).path.split("/")): return self.send_error(404)
        super().do_GET()
    def do_POST(self):
        u = urlparse(self.path); q = parse_qs(u.query); n = int(self.headers.get("Content-Length", 0))
        if u.path == "/api/upload":
            jid, name = slug(q["job"][0]), re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(q["name"][0]))
            if n > 80e6: return self.send_json({"error": "file too large"}, 413)
            d = os.path.join(WORLDS, jid, "raw"); os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, name), "wb") as f: f.write(self.rfile.read(n))
            return self.send_json({"ok": True, "count": len(os.listdir(d))})
        if u.path == "/api/cancel":
            if proc: job["state"] = "cancelled"; os.killpg(proc.pid, signal.SIGTERM)
            return self.send_json({"ok": True})
        if u.path == "/api/jobs":
            body = json.loads(self.rfile.read(n) or b"{}")
            with lock:
                if job["state"] == "running": return self.send_json({"error": "A world is already being built"}, 409)
                name = (body.get("name") or "").strip()[:60] or "Untitled world"
                existing = {s["name"] for s in json.load(open(os.path.join(HERE, "scenes.json")))}
                base, k = name, 2
                while name in existing: name, k = f"{base} {k}", k + 1
                if body.get("type") == "photos":
                    jid = slug(body["id"]); args = ["photos", os.path.join(WORLDS, jid), name]
                elif body.get("type") == "prompt":
                    if not body.get("layout", "").strip() or not body.get("style", "").strip(): return self.send_json({"error": "Describe both the layout and the style"}, 400)
                    jid = f"{slug(name)}-{secrets.token_hex(3)}"; args = ["prompt", os.path.join(WORLDS, jid), name, body["layout"].strip()[:600], body["style"].strip()[:600]]
                    os.environ["WORLD_VIEWS"] = str(max(8, min(16, int(body.get("views", 12)))))
                else: return self.send_json({"error": "unknown job type"}, 400)
                job.clear(); job.update(state="running")
                threading.Thread(target=run_job, args=(args, {"id": jid, "name": name, "type": body["type"]}), daemon=True).start()
            return self.send_json({"ok": True, "id": jid, "name": name})
        self.send_error(404)

if __name__ == "__main__":
    if not os.path.exists(os.path.join(HERE, "scenes.json")): json.dump([], open(os.path.join(HERE, "scenes.json"), "w"))
    srv = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H)
    def stop(*_):
        if proc: os.killpg(proc.pid, signal.SIGTERM)
        os._exit(0)
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    print("serving on http://127.0.0.1:" + sys.argv[1], flush=True); srv.serve_forever()
