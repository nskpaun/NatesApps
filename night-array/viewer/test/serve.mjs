// Tiny static server that mirrors how the APK merges assets, so the viewer page resolves
// ../model/station.glb exactly like it does under https://appassets.androidplatform.net/assets/viewer/.
//   /assets/viewer/*   -> android/app/src/main/assets/viewer
//   /assets/renders/*  -> android/app/src/main/assets/renders
//   /assets/concept/*  -> android/app/src/main/assets/concept
//   /assets/model/*    -> cad/export/model
//   /assets/files/*    -> cad/export/files
//   /assets/drawings/* -> cad/export/drawings
// Run directly:  node test/serve.mjs [port]   (default 8787) then open http://127.0.0.1:8787/assets/viewer/index.html
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const appAssets = path.join(root, 'android/app/src/main/assets');
const cadExport = path.join(root, 'cad/export');

export const MOUNTS = {
  viewer: path.join(appAssets, 'viewer'),
  renders: path.join(appAssets, 'renders'),
  concept: path.join(appAssets, 'concept'),
  model: path.join(cadExport, 'model'),
  files: path.join(cadExport, 'files'),
  drawings: path.join(cadExport, 'drawings'),
};

const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json', '.glb': 'model/gltf-binary', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.png': 'image/png', '.svg': 'image/svg+xml', '.txt': 'text/plain; charset=utf-8', '.css': 'text/css',
  '.step': 'model/step', '.stl': 'model/stl', '.dxf': 'image/vnd.dxf',
};

function resolve(urlPath) {
  const m = /^\/assets\/([^/]+)\/(.+)$/.exec(urlPath);
  if (!m || !MOUNTS[m[1]]) return null;
  const base = MOUNTS[m[1]];
  const file = path.resolve(base, decodeURIComponent(m[2]));
  if (!file.startsWith(base + path.sep)) return null; // no traversal
  return file;
}

export function startServer(port = 0, { log = false } = {}) {
  const server = http.createServer((req, res) => {
    const urlPath = new URL(req.url, 'http://x').pathname;
    const file = resolve(urlPath);
    if (!file || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      if (log) console.log('404', urlPath);
      res.writeHead(404, { 'content-type': 'text/plain' }).end('not found');
      return;
    }
    const body = fs.readFileSync(file);
    res.writeHead(200, {
      'content-type': TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream',
      'content-length': body.length, 'cache-control': 'no-store',
    });
    res.end(req.method === 'HEAD' ? undefined : body);
    if (log) console.log('200', urlPath);
  });
  return new Promise((ok) => server.listen(port, '127.0.0.1', () => {
    const p = server.address().port;
    ok({ port: p, origin: `http://127.0.0.1:${p}`, viewerUrl: `http://127.0.0.1:${p}/assets/viewer/index.html`, close: () => new Promise((r) => server.close(r)) });
  }));
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const { viewerUrl } = await startServer(Number(process.argv[2] || 8787), { log: true });
  console.log(`serving ${viewerUrl}`);
}
