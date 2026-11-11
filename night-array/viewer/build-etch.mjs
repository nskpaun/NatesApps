// Builds the deck etch concept page into ../web/dist/ (next to the Studio page that web/build.py assembles):
//   deck-etch.html   the page body (published through claude.ai Artifacts, which add the <html>/<head> skeleton)
//   deck-etch.js     src/etch/main.js bundled with three.js into one classic script
//   model/           scene.json and station.glb as base64 text (the artifact host does not serve .glb)
// Usage: node build-etch.mjs            (minified)
//        node build-etch.mjs --dev      (unminified, inline source map)
import { build } from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const na = path.resolve(here, '..');
const dist = path.join(na, 'web/dist');
const dev = process.argv.includes('--dev');
fs.mkdirSync(path.join(dist, 'model'), { recursive: true });

const three = JSON.parse(fs.readFileSync(path.join(here, 'node_modules/three/package.json'), 'utf8')).version;
await build({
  entryPoints: [path.join(here, 'src/etch/main.js')],
  bundle: true,
  format: 'iife',
  platform: 'browser',
  target: ['chrome87', 'safari15'],
  minify: !dev,
  sourcemap: dev ? 'inline' : false,
  legalComments: 'none',
  charset: 'utf8',
  banner: { js: `/* Night Array deck etch concept - three.js r${three.split('.')[1]} (MIT, https://threejs.org/) */` },
  outfile: path.join(dist, 'deck-etch.js'),
  logLevel: 'warning',
});
fs.copyFileSync(path.join(na, 'web/deck-etch.html'), path.join(dist, 'deck-etch.html'));
fs.copyFileSync(path.join(na, 'cad/export/model/scene.json'), path.join(dist, 'model/scene.json'));
fs.writeFileSync(path.join(dist, 'model/station.glb.txt'), fs.readFileSync(path.join(na, 'cad/export/model/station.glb')).toString('base64'));
console.log(`deck-etch.js ${(fs.statSync(path.join(dist, 'deck-etch.js')).size / 1024).toFixed(1)} KiB${dev ? ' (dev)' : ''} -> ${path.relative(process.cwd(), dist)}`);
