/** Formatting shared with the Android app (Data.kt). */

export function fmtNum(d: number): string {
  if (!Number.isFinite(d)) return '—'
  if (Math.abs(d - Math.trunc(d)) < 1e-6) return String(Math.trunc(d))
  return d.toFixed(1)
}

export function fmtMm(mm: number): string {
  const n = Math.round(mm)
  const s = String(Math.abs(n))
  const body = n >= 1000 || n <= -1000 ? `${s.slice(0, -3)}\u2009${s.slice(-3)}` : s
  return n < 0 ? `−${body}` : body
}

export function fmtBox(b: number[]): string {
  if (b.length < 3 || b.every((v) => v <= 0)) return '—'
  return `${fmtMm(b[0])} × ${fmtMm(b[1])} × ${fmtMm(b[2])} mm`
}

export function fmtMass(g: number): string {
  if (g <= 0) return '—'
  if (g < 1) return '< 1 g'
  if (g < 1000) return `${Math.round(g)} g`
  if (g < 10_000) return `${(g / 1000).toFixed(2)} kg`
  return `${(g / 1000).toFixed(1)} kg`
}

export function fmtBytes(b: number): string {
  if (b < 0) return '—'
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${Math.round(b / 1024)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

export function fmtUsd(v: number): string {
  return v.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

export function fmtDelta(v: number): string {
  return `${v < 0 ? '−' : '+'}${fmtUsd(Math.abs(v))}`
}

export function cm(mm: number): string {
  const c = mm / 10
  return Math.abs(c - Math.trunc(c)) < 1e-6 ? String(Math.trunc(c)) : c.toFixed(1)
}

export function fmt1(d: number): string {
  return Math.abs(d - Math.trunc(d)) < 1e-6 ? String(Math.trunc(d)) : d.toFixed(1)
}

export const FORMAT_NOTES: Record<string, string> = {
  STEP: 'B-rep solids for any CAD tool',
  STL: 'Mesh in mm, ready to slice',
  GLB: 'glTF binary, one node per part',
  SVG: 'Drawing sheet, 3 views + iso',
  DXF: '2D top-view outline',
}

export function downloadName(path: string): string {
  const base = path.substring(path.lastIndexOf('/') + 1)
  return base.startsWith('night-array') ? base : `night-array-${base}`
}

export function assetUrl(assetPath: string): string {
  return `/${assetPath.replace(/^\/+/, '')}`
}
