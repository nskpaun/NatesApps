// Bundles src/ into ONE classic (IIFE) script and writes the viewer into the Android app's assets:
//   android/app/src/main/assets/viewer/{index.html, viewer.js, LICENSES.txt}
// Usage: node build.mjs            (minified production bundle)
//        node build.mjs --dev      (unminified, inline source map; never commit this one)
import { build } from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(here, '../android/app/src/main/assets/viewer');
const dev = process.argv.includes('--dev');
const MAX_BYTES = 1.5 * 1024 * 1024;

fs.mkdirSync(outDir, { recursive: true });

const threePkg = JSON.parse(fs.readFileSync(path.join(here, 'node_modules/three/package.json'), 'utf8'));
const pkg = JSON.parse(fs.readFileSync(path.join(here, 'package.json'), 'utf8'));

const result = await build({
  entryPoints: [path.join(here, 'src/main.js')],
  bundle: true,
  format: 'iife',
  platform: 'browser',
  target: ['chrome87', 'safari14'],
  minify: !dev,
  sourcemap: dev ? 'inline' : false,
  legalComments: 'none',
  charset: 'utf8',
  define: {
    __VIEWER_VERSION__: JSON.stringify(pkg.version),
    __THREE_VERSION__: JSON.stringify(threePkg.version),
  },
  banner: { js: `/* Night Array viewer ${pkg.version} - three.js r${threePkg.version.split('.')[1]} (MIT, see LICENSES.txt) */` },
  outfile: path.join(outDir, 'viewer.js'),
  metafile: true,
  logLevel: 'warning',
});

fs.copyFileSync(path.join(here, 'index.html'), path.join(outDir, 'index.html'));

const threeLicense = fs.readFileSync(path.join(here, 'node_modules/three/LICENSE'), 'utf8').trim();
fs.writeFileSync(path.join(outDir, 'LICENSES.txt'),
  `Night Array viewer (viewer.js) bundles the following third-party software.\n\n` +
  `three.js ${threePkg.version} - https://threejs.org/ - including the example modules\n` +
  `GLTFLoader, OrbitControls, RoomEnvironment, EffectComposer, RenderPass, UnrealBloomPass,\n` +
  `OutputPass, LineSegments2/LineMaterial and RoundedBoxGeometry from three/examples/jsm.\n\n` +
  `${threeLicense}\n`);

const bytes = fs.statSync(path.join(outDir, 'viewer.js')).size;
const kb = (bytes / 1024).toFixed(1);
console.log(`viewer.js ${kb} KiB${dev ? ' (dev)' : ''} -> ${path.relative(process.cwd(), outDir)}`);
if (!dev && bytes > MAX_BYTES) {
  console.error(`viewer.js is ${kb} KiB, over the ${(MAX_BYTES / 1024).toFixed(0)} KiB budget`);
  process.exit(1);
}
if (process.argv.includes('--meta')) {
  const inputs = Object.entries(result.metafile.outputs)[0][1].inputs;
  const rows = Object.entries(inputs).sort((a, b) => b[1].bytesInOutput - a[1].bytesInOutput).slice(0, 25);
  for (const [f, v] of rows) console.log(String(v.bytesInOutput).padStart(8), f);
}
