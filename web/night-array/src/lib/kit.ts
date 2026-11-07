import rawKit from '../../../../night-array/kit/parts.json'

export type KitAlt = { product: string; mpn: string; unitUsd: number; note: string }

export type KitItem = {
  id: string
  category: string
  role: string
  product: string
  mpn: string
  qty: number
  unitUsd: number
  priceNote: string
  buyUrl: string
  why: string
  optional: boolean
  excluded: boolean
  swap: KitAlt | null
  upgrade: KitAlt | null
}

export type Kit = {
  currency: string
  pricesChecked: string
  note: string
  items: KitItem[]
}

type Rec = Record<string, unknown>

function rec(v: unknown): Rec | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Rec) : null
}

function s(o: Rec, k: string): string {
  const v = o[k]
  return typeof v === 'string' ? v.trim() : ''
}

function money(o: Rec, k: string): number {
  const v = o[k]
  return typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : 0
}

function alt(v: unknown): KitAlt | null {
  const o = rec(v)
  if (!o) return null
  const product = s(o, 'product')
  if (!product || !('unit_usd' in o)) return null
  return { product, mpn: s(o, 'mpn'), unitUsd: money(o, 'unit_usd'), note: s(o, 'note') }
}

export function parseKit(raw: unknown): Kit {
  const o = rec(raw)
  if (!o) return { currency: 'USD', pricesChecked: '', note: '', items: [] }
  const items: KitItem[] = []
  const arr = Array.isArray(o.items) ? o.items : []
  arr.forEach((value, i) => {
    const it = rec(value)
    if (!it) return
    const product = s(it, 'product')
    if (!product) return
    const qty = typeof it.qty === 'number' && it.qty >= 1 ? Math.floor(it.qty) : 1
    items.push({
      id: s(it, 'id') || `item${i}`,
      category: s(it, 'category') || 'Other',
      role: s(it, 'role'),
      product,
      mpn: s(it, 'mpn'),
      qty,
      unitUsd: money(it, 'unit_usd'),
      priceNote: s(it, 'price_note'),
      buyUrl: s(it, 'buy_url'),
      why: s(it, 'why'),
      optional: it.optional === true,
      excluded: it.excluded === true,
      swap: alt(it.swap),
      upgrade: alt(it.upgrade),
    })
  })
  return {
    currency: s(o, 'currency') || 'USD',
    pricesChecked: s(o, 'prices_checked'),
    note: s(o, 'note'),
    items,
  }
}

export const kit = parseKit(rawKit)

export function isCore(item: KitItem): boolean {
  return !item.optional && !item.excluded
}

export function unit(item: KitItem, swaps: boolean): number {
  return swaps && item.swap ? item.swap.unitUsd : item.unitUsd
}

export function line(item: KitItem, swaps: boolean): number {
  return unit(item, swaps) * item.qty
}

export function coreTotal(kit: Kit, swaps: boolean): number {
  return kit.items.filter(isCore).reduce((s, item) => s + line(item, swaps), 0)
}

export function optionalTotal(kit: Kit, swaps: boolean): number {
  return kit.items.filter((item) => item.optional && !item.excluded).reduce((s, item) => s + line(item, swaps), 0)
}

export function excludedTotal(kit: Kit, swaps: boolean): number {
  return kit.items.filter((item) => item.excluded).reduce((s, item) => s + line(item, swaps), 0)
}

export function categories(kit: Kit): [string, KitItem[]][] {
  const order: string[] = []
  const map = new Map<string, KitItem[]>()
  for (const item of kit.items) {
    if (!map.has(item.category)) {
      map.set(item.category, [])
      order.push(item.category)
    }
    map.get(item.category)!.push(item)
  }
  return order.map((name) => [name, map.get(name)!])
}
