// Copies the committed CAD export, stills, concept board, kit list and the
// Android viewer's bundle into public/ so the site is same-origin and the
// Vite build output is self-contained. Does not modify night-array sources.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const webRoot = path.resolve(here, '..')
const repo = path.resolve(webRoot, '../..')
const night = path.join(repo, 'night-array')
const pub = path.join(webRoot, 'public')

function copyDir(from, to) {
  if (!fs.existsSync(from)) throw new Error(`missing source directory: ${from}`)
  fs.rmSync(to, { recursive: true, force: true })
  fs.cpSync(from, to, { recursive: true })
}

copyDir(path.join(night, 'cad/export/model'), path.join(pub, 'model'))
copyDir(path.join(night, 'cad/export/files'), path.join(pub, 'files'))
copyDir(path.join(night, 'cad/export/drawings'), path.join(pub, 'drawings'))
copyDir(path.join(night, 'android/app/src/main/assets/renders'), path.join(pub, 'renders'))
copyDir(path.join(night, 'android/app/src/main/assets/concept'), path.join(pub, 'concept'))
fs.mkdirSync(path.join(pub, 'kit'), { recursive: true })
fs.copyFileSync(path.join(night, 'kit/parts.json'), path.join(pub, 'kit/parts.json'))

const viewerOut = path.join(pub, 'viewer')
fs.mkdirSync(viewerOut, { recursive: true })
const assetViewer = path.join(night, 'android/app/src/main/assets/viewer')
fs.copyFileSync(path.join(assetViewer, 'viewer.js'), path.join(viewerOut, 'viewer.js'))
fs.copyFileSync(path.join(assetViewer, 'LICENSES.txt'), path.join(viewerOut, 'LICENSES.txt'))
fs.copyFileSync(path.join(webRoot, 'viewer-shell/host-bridge.js'), path.join(viewerOut, 'host-bridge.js'))

const htmlPath = path.join(assetViewer, 'index.html')
let html = fs.readFileSync(htmlPath, 'utf8')
const needle = '<script src="viewer.js"></script>'
if (!html.includes(needle)) throw new Error('viewer index.html has no viewer.js script tag to hook')
html = html.replace(needle, '<script src="host-bridge.js"></script>\n<script src="viewer.js"></script>')
fs.writeFileSync(path.join(viewerOut, 'index.html'), html)

const required = [
  'model/scene.json',
  'model/station.glb',
  'model/station-edges.glb',
  'files/night-array-assembly.step',
  'files/parts/base.step',
  'files/parts/base.stl',
  'files/drawings/base.svg',
  'files/drawings/base-top.dxf',
  'drawings/base.png',
  'renders/hero-work.jpg',
  'renders/hero-stow.jpg',
  'renders/hero-standalone.jpg',
  'renders/part-internals.jpg',
  'renders/night.jpg',
  'concept/board.jpg',
  'kit/parts.json',
  'viewer/viewer.js',
  'viewer/index.html',
  'viewer/host-bridge.js',
  'viewer/LICENSES.txt',
]
for (const rel of required) {
  const file = path.join(pub, rel)
  if (!fs.existsSync(file) || fs.statSync(file).size < 32) throw new Error(`asset missing or empty: public/${rel}`)
}
const viewerJs = fs.readFileSync(path.join(pub, 'viewer/viewer.js'), 'utf8')
if (!viewerJs.includes('Night Array')) throw new Error('viewer.js does not look like the Night Array bundle')
console.log('copied Night Array CAD, stills, kit list and viewer into web/night-array/public')
