import { describe, expect, it } from 'vitest'
import { storyById, storySpecs, specSheet, STORIES } from './content'
import { assetUrl, downloadName, fmtUsd } from './format'
import { categories, coreTotal, excludedTotal, isCore, kit, line, optionalTotal, parseKit } from './kit'
import { displayWidthMm, filesOf, fitOf, footprint, groupOf, scene, stationMassG } from './scene'
import { presetPatch, stillsFor } from './stills'
import { DEFAULT_STATE } from './types'

describe('scene.json', () => {
  it('loads the committed CAD scene', () => {
    expect(scene.fromFile).toBe(true)
    expect(scene.name).toContain('Night Array')
    expect(scene.groups.map((g) => g.id)).toEqual([
      'display',
      'stand',
      'base',
      'dock',
      'laptop',
      'keyboard',
      'mouse',
      'deskmat',
      'internals',
    ])
    expect(scene.parts).toHaveLength(40)
    expect(scene.files).toHaveLength(38)
    expect(scene.screen.canvasW).toBe(5120)
    expect(scene.screen.canvasH).toBe(1440)
    expect(scene.dockSteps.map((s) => s.step)).toEqual(['align', 'lower', 'lift'])
    const assembly = scene.files.find((f) => f.id === 'assembly-step')
    expect(assembly?.path).toBe('files/night-array-assembly.step')
    expect(assembly?.bytes).toBe(5849273)
    expect(scene.files.every((f) => f.bytes > 0)).toBe(true)
    expect(groupOf(scene, 'base')?.parts).toContain('base_shell')
    expect(stationMassG(scene)).toBeGreaterThan(1000)
    expect(displayWidthMm(scene)).toBeGreaterThan(1100)
  })

  it('points every group at a real download set', () => {
    for (const g of scene.groups) {
      const files = filesOf(scene, g.id)
      expect(files.map((f) => f.format).sort()).toEqual(['DXF', 'STEP', 'STL', 'SVG'])
      for (const f of files) {
        expect(f.path.startsWith('files/')).toBe(true)
        expect(assetUrl(f.path).startsWith('/files/')).toBe(true)
        expect(downloadName(f.path).startsWith('night-array-')).toBe(true)
      }
      expect(scene.drawings[g.id]).toBe(`drawings/${g.id}.png`)
    }
    expect(downloadName('files/night-array-assembly.step')).toBe('night-array-assembly.step')
  })
})

describe('desk fit', () => {
  const fp = footprint(scene)

  it('uses the CAD envelope', () => {
    expect(fp.widthMm).toBeCloseTo(1415, 0)
    expect(fp.baseDepthMm).toBeCloseTo(300, 0)
    expect(fp.workGapMm).toBeCloseTo(150, 0)
    expect(fp.workDepthMm).toBeGreaterThan(fp.baseDepthMm)
  })

  it('classifies the preset desks', () => {
    expect(fitOf(fp, 160, 80)).toBe('fits')
    expect(fitOf(fp, 180, 90)).toBe('fits')
    expect(fitOf(fp, 160, 60)).toBe('stow')
    expect(fitOf(fp, 120, 80)).toBe('no')
    expect(fitOf(fp, 100, 40)).toBe('no')
  })
})

describe('stills', () => {
  it('picks the same fallback order as the Android host', () => {
    expect(stillsFor({ ...DEFAULT_STATE, mode: 'work' }, 'hero', null).at(-2)).toBe('hero-work.jpg')
    expect(stillsFor({ ...DEFAULT_STATE, isolate: 'keyboard' }, 'hero', null)[0]).toBe('part-keyboard.jpg')
    expect(stillsFor({ ...DEFAULT_STATE, cinematic: true }, 'hero', null)).toContain('night.jpg')
    expect(stillsFor({ ...DEFAULT_STATE, style: 'cad' }, 'hero', null)).toContain('cad.jpg')
    expect(stillsFor({ ...DEFAULT_STATE, style: 'xray' }, 'trays', null)).toContain('xray.jpg')
    expect(stillsFor({ ...DEFAULT_STATE, explode: 0.6 }, 'hero', null)).toContain('exploded.jpg')
    expect(stillsFor({ ...DEFAULT_STATE, section: { axis: 'x', t: 0.4 } }, 'hero', null)).toContain('section.jpg')
    expect(stillsFor({ ...DEFAULT_STATE, finish: 'oxblood' }, 'hero', null)).toContain('finish-oxblood.jpg')
    expect(stillsFor({ ...DEFAULT_STATE, amber: 0 }, 'hero', null)).toContain('amber-off.jpg')
    expect(stillsFor(DEFAULT_STATE, 'display', null)).toContain('display.jpg')
    expect(stillsFor(DEFAULT_STATE, 'dock', 'align')).toContain('dock-align.jpg')
    expect(stillsFor(DEFAULT_STATE, 'dock', 'align')).not.toContain('dock-lower.jpg')
    expect(stillsFor(DEFAULT_STATE, 'dock', null)).toContain('dock-lower.jpg')
  })

  it('clears an isolate when a story preset does not set one', () => {
    const patch = presetPatch({ ...DEFAULT_STATE, isolate: 'dock', section: { axis: 'z', t: 0.2 } }, { mode: 'stow', camera: 'hero' })
    expect(patch.isolate).toBeNull()
    expect(patch.section).toBeNull()
    expect(patch.mode).toBe('stow')
  })
})

describe('stories and spec sheet', () => {
  it('keeps eight stories and fills the dual specs from the CAD screen block', () => {
    expect(STORIES).toHaveLength(8)
    const dual = storyById('dual')
    expect(dual).toBeTruthy()
    const rows = storySpecs(dual!)
    expect(rows.find((r) => r.label === 'Canvas')?.value).toBe('5120 × 1440')
    expect(rows.find((r) => r.label === 'Seam')?.value).toContain('14 mm')
    const sheet = specSheet(scene)
    expect(sheet.map((s) => s.title)).toContain('Display')
    expect(sheet.map((s) => s.title)).toContain('Dimensions')
    const mass = sheet.find((s) => s.title === 'Dimensions')?.rows.find((r) => r.label === 'Mass')?.value
    expect(mass).toContain('concept')
  })
})

describe('parts.json shopping list', () => {
  it('preserves recorded prices, links and the budget split', () => {
    expect(kit.pricesChecked).toBe('2026-11-07')
    expect(kit.currency).toBe('USD')
    expect(kit.items.length).toBe(36)
    expect(kit.items.filter(isCore)).toHaveLength(31)
    expect(coreTotal(kit, false)).toBeCloseTo(1730.46, 2)
    expect(coreTotal(kit, true)).toBeCloseTo(1312.95, 2)
    expect(optionalTotal(kit, false)).toBeCloseTo(77, 2)
    expect(excludedTotal(kit, false)).toBeCloseTo(196.9, 2)
    expect(fmtUsd(coreTotal(kit, false))).toBe('$1,730.46')
    const monitor = kit.items.find((i) => i.id === 'monitor')
    expect(monitor?.qty).toBe(2)
    expect(monitor?.unitUsd).toBe(349.99)
    expect(monitor?.mpn).toBe('LS27D606UANXGO')
    expect(monitor?.buyUrl).toContain('samsung.com')
    expect(monitor?.swap?.unitUsd).toBe(229)
    expect(line(monitor!, true)).toBeCloseTo(458, 2)
    expect(kit.items.find((i) => i.id === 'dock')?.upgrade?.unitUsd).toBe(299.99)
    expect(categories(kit)[0][0]).toBe('Display')
    expect(parseKit(null).items).toEqual([])
    expect(parseKit({ items: [{ id: 'blank' }] }).items).toEqual([])
  })
})
