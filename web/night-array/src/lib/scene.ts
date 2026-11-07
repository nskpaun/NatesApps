import rawScene from '../../../../night-array/cad/export/model/scene.json'
import { fmtNum } from './format'

export type Group = {
  id: string
  name: string
  summary: string
  description: string
  parts: string[]
  pivot: number[]
  bboxMm: number[]
  massG: number
  volumeCm3: number
  materials: string[]
}

export type Part = {
  id: string
  group: string
  name: string
  material: string
  internal: boolean
  bboxMm: number[]
  volumeCm3: number
  massG: number
  massNote: string
}

export type CadFile = {
  id: string
  group: string | null
  format: string
  label: string
  path: string
  bytes: number
}

export type DockStep = { step: string; title: string; caption: string }
export type Dim = { id: string; label: string; pose: string | null }

export type ScreenInfo = {
  layout: string
  panels: number
  panelInch: number
  activeMm: number[]
  resEach: number[]
  seamMm: number
  toeInDeg: number
  canvasW: number
  canvasH: number
  ppi: number
  activeY: number[] | null
}

export type MaterialInfo = { label: string; color: string; spec: string }

export type Scene = {
  name: string
  tagline: string
  massNote: string
  params: Record<string, unknown>
  boundsMin: number[]
  boundsMax: number[]
  materials: Record<string, MaterialInfo>
  groups: Group[]
  parts: Part[]
  files: CadFile[]
  drawings: Record<string, string>
  dims: Dim[]
  screen: ScreenInfo
  dockSteps: DockStep[]
  poses: Record<string, unknown>
  fromFile: boolean
}

const GROUP_ORDER = ['display', 'stand', 'base', 'dock', 'laptop', 'keyboard', 'mouse', 'deskmat', 'internals']

const MATERIAL_LABELS: Record<string, string> = {
  titanium: 'Neutral Titanium',
  graphite: 'Charcoal Graphite',
  oxblood: 'Brushed Oxblood',
  glass_black: 'Black cover glass',
  screen: 'Display panel',
  keycap: 'PBT keycaps',
  rubber: 'Rubber',
  amber_led: 'Amber LED',
  copper: 'Copper',
  pcb: 'Circuit board',
  ferrite: 'Ferrite',
  laptop_alu: 'Laptop aluminium',
  felt: 'Wool felt',
  steel: 'Steel',
}

const FALLBACK_COLORS: Record<string, string> = {
  titanium: '#BDB2A4',
  graphite: '#3A3735',
  oxblood: '#7A2E2A',
  glass_black: '#060606',
  screen: '#08080A',
  keycap: '#1C1A19',
  rubber: '#141313',
  amber_led: '#F2A04A',
  copper: '#B87333',
  pcb: '#245C32',
  ferrite: '#4A4744',
  laptop_alu: '#C5C2BA',
  felt: '#6E5A48',
  steel: '#8E9196',
}

type Rec = Record<string, unknown>

function rec(v: unknown): Rec | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Rec) : null
}

function str(o: Rec, k: string, def = ''): string {
  const v = o[k]
  return typeof v === 'string' ? v : def
}

function numOf(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

function numList(v: unknown, n = 0): number[] {
  const list = Array.isArray(v) ? v.map((x) => (typeof x === 'number' && Number.isFinite(x) ? x : 0)) : []
  if (n > 0) return [...list, ...Array(n).fill(0)].slice(0, n)
  return list
}

function strList(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string' && x.length > 0) : []
}

function prettyId(id: string): string {
  const s = id.replaceAll('_', ' ').replaceAll('-', ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function parseScene(raw: unknown): Scene {
  const o = rec(raw) ?? {}
  const params = rec(o.params) ?? {}
  const bounds = rec(o.bounds)
  const boundsMin = numList(bounds?.min, 3)
  const boundsMax = numList(bounds?.max, 3)

  const materials: Record<string, MaterialInfo> = {}
  const mats = rec(o.materials)
  if (mats) {
    for (const [k, value] of Object.entries(mats)) {
      const m = rec(value)
      materials[k] = {
        label: m ? str(m, 'label') || MATERIAL_LABELS[k] || k : MATERIAL_LABELS[k] || k,
        color: (m && str(m, 'color')) || FALLBACK_COLORS[k] || '#A39A90',
        spec: m ? str(m, 'spec') : '',
      }
    }
  }

  const parts: Part[] = []
  for (const value of Array.isArray(o.parts) ? o.parts : []) {
    const p = rec(value)
    if (!p) continue
    const id = str(p, 'id')
    if (!id) continue
    parts.push({
      id,
      group: str(p, 'group'),
      name: str(p, 'name') || prettyId(id),
      material: str(p, 'material', 'titanium'),
      internal: p.internal === true,
      bboxMm: numList(p.bbox_mm, 3),
      volumeCm3: numOf(p.volume_cm3) ?? 0,
      massG: numOf(p.mass_g) ?? 0,
      massNote: str(p, 'mass_note'),
    })
  }

  const groups: Group[] = []
  for (const value of Array.isArray(o.groups) ? o.groups : []) {
    const g = rec(value)
    if (!g) continue
    const id = str(g, 'id')
    if (!id) continue
    const ids = strList(g.parts)
    const memberIds = ids.length ? ids : parts.filter((p) => p.group === id).map((p) => p.id)
    const members = parts.filter((p) => memberIds.includes(p.id))
    const mass = numOf(g.mass_g)
    const volume = numOf(g.volume_cm3)
    groups.push({
      id,
      name: str(g, 'name') || prettyId(id),
      summary: str(g, 'summary'),
      description: str(g, 'description'),
      parts: memberIds,
      pivot: numList(g.pivot, 3),
      bboxMm: numList(g.bbox_mm, 3),
      massG: mass != null && mass > 0 ? mass : members.reduce((s, p) => s + p.massG, 0),
      volumeCm3: volume != null && volume > 0 ? volume : members.reduce((s, p) => s + p.volumeCm3, 0),
      materials: strList(g.materials).length ? strList(g.materials) : [...new Set(members.map((p) => p.material))],
    })
  }
  groups.sort((a, b) => {
    const ia = GROUP_ORDER.indexOf(a.id)
    const ib = GROUP_ORDER.indexOf(b.id)
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)
  })

  const files: CadFile[] = []
  for (const value of Array.isArray(o.files) ? o.files : []) {
    const f = rec(value)
    if (!f) continue
    const filePath = str(f, 'path')
    if (!filePath) continue
    const format = (str(f, 'format') || filePath.split('.').pop() || '').toUpperCase()
    files.push({
      id: str(f, 'id') || filePath,
      group: str(f, 'group') || null,
      format,
      label: str(f, 'label'),
      path: filePath,
      bytes: Math.max(0, numOf(f.bytes) ?? 0),
    })
  }

  const drawings: Record<string, string> = {}
  const drawingRec = rec(o.drawings)
  if (drawingRec) {
    for (const [k, v] of Object.entries(drawingRec)) if (typeof v === 'string' && v) drawings[k] = v
  }

  const dims: Dim[] = []
  for (const value of Array.isArray(o.dims) ? o.dims : []) {
    const d = rec(value)
    if (!d) continue
    dims.push({ id: str(d, 'id'), label: str(d, 'label'), pose: str(d, 'pose') || null })
  }

  const scr = rec(o.screen)
  const active = numList(scr?.panel_active_mm).slice(0, 2)
  const res = numList(scr?.resolution_each).slice(0, 2).map((n) => Math.round(n))
  const activeMm = active.length >= 2 && active[0] > 0 && active[1] > 0 ? active : [596.7, 335.7]
  const resEach = res.length >= 2 && res[0] > 0 && res[1] > 0 ? res : [2560, 1440]
  const panels = numOf(scr?.panels) ?? 2
  const panelInch = numOf(scr?.panel_inch) ?? 27
  const seamMm = numOf(scr?.seam_mm) ?? 14
  const toeInDeg = numOf(scr?.toe_in_deg) ?? 10
  const canvas = numList(scr?.canvas).map((n) => Math.round(n))
  const activeY = numList(scr?.active_y_mm)
  const screen: ScreenInfo = {
    layout: scr ? str(scr, 'layout', 'dual') : 'dual',
    panels: panels >= 1 && panels <= 8 ? panels : 2,
    panelInch: panelInch > 0 ? panelInch : 27,
    activeMm,
    resEach,
    seamMm: seamMm >= 0 ? seamMm : 14,
    toeInDeg: toeInDeg >= 0 && toeInDeg <= 45 ? toeInDeg : 10,
    canvasW: canvas.length >= 2 && canvas[0] > 0 ? canvas[0] : resEach[0] * (panels >= 1 && panels <= 8 ? panels : 2),
    canvasH: canvas.length >= 2 && canvas[1] > 0 ? canvas[1] : resEach[1],
    ppi: resEach[0] / (activeMm[0] / 25.4),
    activeY: activeY.length >= 2 ? activeY.slice(0, 2) : null,
  }

  const dockSteps: DockStep[] = []
  for (const value of Array.isArray(o.dock_sequence) ? o.dock_sequence : []) {
    const s = rec(value)
    if (!s || !str(s, 'step')) continue
    dockSteps.push({ step: str(s, 'step'), title: str(s, 'title'), caption: str(s, 'caption') })
  }

  return {
    name: str(o, 'name') || 'Night Array — Work & Stow',
    tagline: str(o, 'tagline') || 'Your hardware. Your OS.',
    massNote: str(o, 'mass_note'),
    params,
    boundsMin: boundsMin.length ? boundsMin : [-0.64, 0, -0.15],
    boundsMax: boundsMax.length ? boundsMax : [0.775, 0.52, 0.15],
    materials,
    groups,
    parts,
    files,
    drawings,
    dims,
    screen,
    dockSteps,
    poses: rec(o.poses) ?? {},
    fromFile: true,
  }
}

export const scene: Scene = parseScene(rawScene)

export function param(scene: Scene, path: string): unknown {
  let cur: unknown = scene.params
  for (const key of path.split('.')) {
    const o = rec(cur)
    if (!o || !(key in o)) return undefined
    cur = o[key]
  }
  return cur
}

export function num(scene: Scene, path: string): number | null {
  return numOf(param(scene, path))
}

export function nums(scene: Scene, path: string): number[] | null {
  const v = param(scene, path)
  if (!Array.isArray(v) || v.length === 0) return null
  const list = v.map((x) => (typeof x === 'number' && Number.isFinite(x) ? x : Number.NaN))
  if (list.some((n) => Number.isNaN(n))) return null
  return list
}

export function text(scene: Scene, path: string): string | null {
  const v = param(scene, path)
  return typeof v === 'string' && v.trim() ? v : null
}

export function span(scene: Scene, path: string): number | null {
  const v = nums(scene, path)
  return v && v.length === 2 ? v[1] - v[0] : null
}

export function groupOf(scene: Scene, id: string | null | undefined): Group | undefined {
  return scene.groups.find((g) => g.id === id)
}

export function partsOf(scene: Scene, groupId: string): Part[] {
  return scene.parts.filter((p) => p.group === groupId)
}

export function filesOf(scene: Scene, groupId: string | null): CadFile[] {
  return scene.files.filter((f) => f.group === groupId)
}

export function materialLabel(scene: Scene, key: string): string {
  return scene.materials[key]?.label || MATERIAL_LABELS[key] || prettyId(key)
}

export function materialColor(scene: Scene, key: string): string {
  return scene.materials[key]?.color || FALLBACK_COLORS[key] || '#A39A90'
}

export function bbox(scene: Scene, groupId: string): number[] | null {
  const b = groupOf(scene, groupId)?.bboxMm
  return b && b.length === 3 && b.every((v) => v > 0) ? b : null
}

export function overallMm(scene: Scene): number[] {
  return [0, 1, 2].map((i) => (scene.boundsMax[i] - scene.boundsMin[i]) * 1000)
}

export function poseT(scene: Scene, pose: string, group: string): number[] {
  const poses = rec(scene.poses)
  const g = rec(rec(poses?.[pose])?.[group])
  const t = g?.t
  return numList(t, 3)
}

export function stationMassG(scene: Scene): number {
  return scene.groups.filter((g) => g.id !== 'laptop' && g.id !== 'deskmat').reduce((s, g) => s + g.massG, 0)
}

export function chordFromScreen(sc: ScreenInfo): number {
  const facet = sc.seamMm / 2 + sc.activeMm[0] + 9 + 3
  return 2 * facet * Math.cos((sc.toeInDeg * Math.PI) / 180)
}

export function displayWidthMm(scene: Scene): number {
  const w = groupOf(scene, 'display')?.bboxMm?.[0]
  return w != null && w > 100 ? w : chordFromScreen(scene.screen)
}

export function mullionMm(scene: Scene): string {
  const w = num(scene, 'display.mullion_w')
  return w != null ? `${fmtNum(w)} mm` : '4 mm'
}

export type Footprint = {
  xMin: number
  xMax: number
  baseDepthMm: number
  workGapMm: number
  matCz: number
  matW: number
  matD: number
  matCx: number
  widthMm: number
  baseFront: number
  workDepthMm: number
}

export type Fit = 'fits' | 'stow' | 'no'

/** Plan footprint in millimetres, the same derivation the Android desk-fit screen uses. */
export function footprint(model: Scene): Footprint {
  let x0 = model.boundsMin[0] * 1000
  let x1 = model.boundsMax[0] * 1000
  if (x1 - x0 < 500) {
    x0 = -640
    x1 = 775
  }
  const baseD = bbox(model, 'base')?.[2]
  const baseDepthMm = baseD != null && baseD >= 150 && baseD <= 600 ? baseD : 300
  const mat = bbox(model, 'deskmat')
  const matD = mat && mat[2] >= 100 && mat[2] <= 800 ? mat[2] : 300
  const matW = mat && mat[0] >= 200 && mat[0] <= 2000 ? mat[0] : 820
  const pv = groupOf(model, 'deskmat')?.pivot
  const mc = nums(model, 'deskmat.c')
  const matFromCenter = mc != null && mc.length === 2 && mc[1] > baseDepthMm / 2
  const pivotForward = pv != null && pv[2] * 1000 > baseDepthMm / 2
  const matCz = matFromCenter ? mc![1] : pivotForward ? pv![2] * 1000 : 385
  const matCx = matFromCenter ? mc![0] : pivotForward ? pv![0] * 1000 : 60
  const kbZ = nums(model, 'keyboard.stow_c')?.[1] ?? 62
  const kbD = nums(model, 'keyboard.size')?.[1] ?? 120
  const workT = poseT(model, 'work', 'keyboard')[2] * 1000
  const gap = kbZ + workT - kbD / 2 - baseDepthMm / 2
  const workGapMm = workT > 0 && gap >= 50 && gap <= 400 ? gap : 150
  return {
    xMin: x0,
    xMax: x1,
    baseDepthMm,
    workGapMm,
    matCz,
    matW,
    matD,
    matCx,
    widthMm: x1 - x0,
    baseFront: baseDepthMm / 2,
    workDepthMm: baseDepthMm / 2 + matCz + matD / 2,
  }
}

export function fitOf(fp: Footprint, deskWcm: number, deskDcm: number): Fit {
  const w = deskWcm * 10
  const d = deskDcm * 10
  if (w + 0.5 < fp.widthMm || d + 0.5 < fp.baseDepthMm) return 'no'
  if (d + 0.5 < fp.workDepthMm) return 'stow'
  return 'fits'
}

/** USB-C plug position measured from the hinge end of a docked laptop, millimetres. */
export function portFromHingeMm(model: Scene): number | null {
  const plug = num(model, 'dock.connector.z') ?? num(model, 'laptop.port_z')
  const hingeEnd = nums(model, 'laptop.z')?.[0]
  if (plug == null || hingeEnd == null) return null
  const d = plug - hingeEnd
  return d >= 5 && d <= 200 ? d : null
}
