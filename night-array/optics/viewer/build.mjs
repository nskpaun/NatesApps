// Bundles src/main.js with three.js and writes ONE self-contained page: ribbon-3d.html
// (the model and textures are embedded, so it opens from a file or anywhere it is hosted).
// Usage: npm install && node build.mjs
import { build } from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const r = await build({
  entryPoints: [path.join(here, 'src/main.js')], bundle: true, format: 'iife', platform: 'browser',
  target: ['chrome90', 'safari15'], minify: true, legalComments: 'none', charset: 'utf8', write: false, logLevel: 'warning',
});
const js = r.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');
const b64 = f => fs.readFileSync(path.join(here, 'assets', f)).toString('base64');
const assets = {
  glb: b64('station-ribbon.glb'),
  screen: 'data:image/jpeg;base64,' + b64('screen.jpg'),
  band: 'data:image/png;base64,' + b64('band.png'),
  info: JSON.parse(fs.readFileSync(path.join(here, 'assets', 'station-ribbon.json'), 'utf8')),
};
const html = fs.readFileSync(path.join(here, 'page.html'), 'utf8')
  .replace('/*__ASSETS__*/null', () => JSON.stringify(assets))
  .replace('/*__BUNDLE__*/', () => `/* three.js r170 (MIT) + viewer */\n${js}`);
fs.writeFileSync(path.join(here, 'ribbon-3d.html'), html);
console.log(`wrote ribbon-3d.html, ${(html.length / 1048576).toFixed(1)} MB (bundle ${(js.length / 1024).toFixed(0)} KB)`);
