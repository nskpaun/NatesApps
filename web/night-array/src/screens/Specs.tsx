import { useState } from 'react'
import { NavLink, useParams } from 'react-router-dom'
import { specSheet } from '../lib/content'
import { cm, fmt1, fmtMass, fmtUsd, fmtDelta } from '../lib/format'
import { categories, coreTotal, excludedTotal, isCore, kit, line, optionalTotal, type KitItem } from '../lib/kit'
import { fitOf, footprint, materialColor, materialLabel, partsOf, scene, stationMassG, type Footprint } from '../lib/scene'
import { Segmented, Swatch } from '../components/ui'

const TABS = [
  ['sheet', 'Sheet'],
  ['bom', 'BOM'],
  ['fit', 'Desk fit'],
  ['buy', 'Buy'],
] as const

export function Specs() {
  const { section } = useParams()
  const tab = TABS.some(([id]) => id === section) ? section : 'sheet'
  return (
    <article className="page specs">
      <header className="measure">
        <p className="kicker">Specs</p>
        <h1>The station, in numbers</h1>
        <nav className="spec-tabs" aria-label="Specification sections">
          {TABS.map(([id, label]) => (
            <NavLink key={id} to={id === 'sheet' ? '/specs' : `/specs/${id}`} end={id === 'sheet'} className={tab === id ? 'on' : ''}>
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      {tab === 'bom' ? <Bom /> : tab === 'fit' ? <DeskFit /> : tab === 'buy' ? <Buy /> : <Sheet />}
    </article>
  )
}

function Sheet() {
  const sections = specSheet(scene)
  return (
    <div className="measure spec-columns">
      {sections.map((sec) => (
        <section key={sec.title}>
          <h2>{sec.title}</h2>
          <p className="sub">{sec.sub}</p>
          <dl className="spec-list">
            {sec.rows.map((row) => (
              <div key={row.label}>
                <dt>{row.label}</dt>
                <dd>{row.value}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
      <p className="fine">
        Numbers come from the CAD export (model/scene.json). {scene.massNote || 'Masses are concept estimates from the CAD volumes and real densities.'}
      </p>
    </div>
  )
}

function Bom() {
  return (
    <div className="measure">
      <header className="split">
        <div>
          <p className="kicker">Bill of materials</p>
          <p>
            {scene.parts.length} parts in {scene.groups.length} groups
          </p>
        </div>
        <p className="price">
          {fmtMass(stationMassG(scene))}
          <small>Station</small>
        </p>
      </header>
      {scene.groups.map((g) => (
        <section key={g.id}>
          <h2>
            {g.name} <span>{fmtMass(g.massG)}</span>
          </h2>
          <ul className="part-lines">
            {partsOf(scene, g.id).map((p) => (
              <li key={p.id}>
                <Swatch material={p.material} />
                <span>
                  <strong>{p.name}</strong>
                  {p.internal ? <em> Internal</em> : null}
                  <small>{materialLabel(scene, p.material)}</small>
                </span>
                <b>{fmtMass(p.massG)}</b>
              </li>
            ))}
          </ul>
        </section>
      ))}
      <p className="fine">
        {scene.massNote || 'Masses use real densities and assume solid parts unless the model is hollow.'} “Station” excludes the laptop and the desk mat. Swatches use the CAD material colours.
      </p>
      <p className="sr-only">Material colours include titanium {materialColor(scene, 'titanium')}.</p>
    </div>
  )
}

const PRESETS = [
  [120, 60],
  [140, 70],
  [160, 80],
  [180, 90],
] as const

function DeskFit() {
  const fp = footprint(scene)
  const [w, setW] = useState(160)
  const [d, setD] = useState(80)
  const [mode, setMode] = useState<'work' | 'stow'>('work')
  const fit = fitOf(fp, w, d)
  return (
    <div className="measure fit">
      <p>Enter your desk and see the station on it, from above, with the {cm(fp.workGapMm)} cm work zone.</p>
      <div className="desk-fields">
        <CmField label="Desk width" value={w} onChange={setW} />
        <CmField label="Desk depth" value={d} onChange={setD} />
      </div>
      <div className="chips">
        {PRESETS.map(([pw, pd]) => (
          <button key={pw} type="button" className={w === pw && d === pd ? 'chip on' : 'chip'} aria-pressed={w === pw && d === pd} onClick={() => { setW(pw); setD(pd) }}>
            {pw} × {pd}
          </button>
        ))}
      </div>
      <Verdict fp={fp} fit={fit} w={w} d={d} />
      <div className="plan-head">
        <p className="micro">Plan view</p>
        <Segmented
          label="Plan mode"
          value={mode}
          options={[
            ['work', 'Work'],
            ['stow', 'Stow'],
          ]}
          onChange={setMode}
        />
      </div>
      <DeskPlan fp={fp} wcm={w} dcm={d} mode={mode} />
      <ul className="legend">
        <li><i className="swatch" style={{ background: '#BDB2A4' }} /> Station</li>
        <li><i className="swatch" style={{ background: '#F2A04A' }} /> Work zone</li>
        <li><i className="swatch" style={{ background: '#4A4541' }} /> Mat and devices</li>
      </ul>
    </div>
  )
}

function Verdict({ fp, fit, w, d }: { fp: Footprint; fit: ReturnType<typeof fitOf>; w: number; d: number }) {
  const title = fit === 'fits' ? 'It fits' : fit === 'stow' ? 'Fits stowed only' : "Doesn't fit"
  const spareW = (w * 10 - fp.widthMm) / 10
  let text = ''
  if (fit === 'fits') {
    text = `${fmt1(spareW / 2)} cm spare at each side and ${fmt1((d * 10 - fp.workDepthMm) / 10)} cm in front of the mat in Work. Stowed, the station needs only ${cm(fp.baseDepthMm)} cm of depth.`
  } else if (fit === 'stow') {
    text = `Stowed, it fits with ${fmt1(d - fp.baseDepthMm / 10)} cm to spare. Working needs ${cm(fp.workDepthMm)} cm: the base, the ${cm(fp.workGapMm)} cm work zone and the mat. You're ${fmt1(fp.workDepthMm / 10 - d)} cm short.`
  } else {
    const bits = []
    if (w * 10 < fp.widthMm) bits.push(`The station is ${cm(fp.widthMm)} cm wide including the dock; your desk is ${w} cm, ${fmt1(fp.widthMm / 10 - w)} cm short.`)
    if (d * 10 < fp.baseDepthMm) bits.push(`The base alone is ${cm(fp.baseDepthMm)} cm deep; your desk is ${d} cm.`)
    text = bits.join(' ')
  }
  return (
    <p className={`verdict ${fit}`} role="status">
      <strong>{title}</strong>
      {text}
    </p>
  )
}

function CmField({ label, value, onChange }: { label: string; value: number; onChange: (n: number) => void }) {
  return (
    <label className="cm">
      <span>{label} (cm)</span>
      <span>
        <button type="button" aria-label={`Decrease ${label}`} onClick={() => onChange(Math.max(30, value - 5))}>
          −
        </button>
        <input
          inputMode="numeric"
          value={value}
          aria-label={label}
          onChange={(e) => {
            const n = Number(e.target.value.replace(/\D/g, '').slice(0, 3))
            if (n >= 1 && n <= 999) onChange(n)
          }}
        />
        <button type="button" aria-label={`Increase ${label}`} onClick={() => onChange(Math.min(400, value + 5))}>
          +
        </button>
      </span>
    </label>
  )
}

function DeskPlan({ fp, wcm, dcm, mode }: { fp: Footprint; wcm: number; dcm: number; mode: 'work' | 'stow' }) {
  const deskW = wcm * 10
  const deskD = dcm * 10
  const work = mode === 'work'
  const needD = work ? fp.workDepthMm : fp.baseDepthMm
  const extW = Math.max(deskW, fp.widthMm)
  const extH = Math.max(deskD, needD)
  const padL = 30
  const padT = 46
  const padR = 70
  const padB = 36
  const shift = extW / 2 - (fp.xMin + fp.xMax) / 2
  const deskLeft = (extW - deskW) / 2
  const P = (x: number, z: number) => [padL + x + shift, padT + z + fp.baseDepthMm / 2]
  const rect = (x0: number, z0: number, x1: number, z1: number) => {
    const [ax, ay] = P(x0, z0)
    const [bx, by] = P(x1, z1)
    return { x: Math.min(ax, bx), y: Math.min(ay, by), width: Math.abs(bx - ax), height: Math.abs(by - ay) }
  }
  const base = rect(-640, -fp.baseDepthMm / 2, 650, fp.baseDepthMm / 2)
  const fit = fitOf(fp, wcm, dcm)
  const bad = fit === 'no' || (work && fit === 'stow')
  const [dx, dy] = [padL + deskLeft, padT]
  return (
    <svg className="plan" viewBox={`0 0 ${extW + padL + padR} ${extH + padT + padB}`} role="img" aria-label={`Plan of a ${wcm} by ${dcm} centimetre desk with the station ${fit === 'fits' ? 'fitting' : fit === 'stow' ? 'fitting only when stowed' : 'not fitting'}`}>
      <rect x={dx} y={dy} width={deskW} height={deskD} rx="8" fill="#231C17" stroke={bad ? '#E15B4A' : '#BDB2A4'} />
      {work ? <rect {...rect(fp.xMin + 40, fp.baseFront, fp.xMax - 140, fp.baseFront + fp.workGapMm)} fill="#F2A04A" opacity="0.18" /> : null}
      {work ? <rect {...rect(fp.matCx - fp.matW / 2, fp.matCz - fp.matD / 2, fp.matCx + fp.matW / 2, fp.matCz + fp.matD / 2)} rx="8" fill="#3A3532" /> : null}
      {work ? <rect {...rect(-270, 300, 90, 420)} rx="6" fill="#55504C" /> : null}
      {work ? <rect {...rect(257, 301, 323, 419)} rx="20" fill="#55504C" /> : null}
      <rect {...base} rx="28" fill="#BDB2A4" opacity="0.72" stroke="#BDB2A4" />
      <rect {...rect(-278, -6, 98, 130)} rx="6" fill="#26231F" />
      <rect {...rect(209, -5, 291, 129)} rx="8" fill="#26231F" />
      {!work ? <rect {...rect(-270, 2, 90, 122)} rx="6" fill="#55504C" /> : null}
      {!work ? <rect {...rect(217, 3, 283, 121)} rx="16" fill="#55504C" /> : null}
      <rect {...rect(-160, -140, 160, -70)} fill="#3A3735" />
      <rect {...rect(650, -130, 775, 130)} rx="10" fill="#BDB2A4" opacity="0.72" />
      <rect {...rect(772, -130, 775, 130)} fill="#7A2E2A" />
      <rect {...rect(714.5, -106, 729.5, 106)} fill="#B9B5AF" />
      <text x={dx} y={padT + Math.max(deskD, needD) + 22} fill="#A39A90" fontSize="14">
        Your desk · {wcm} × {dcm} cm
      </text>
      <text x={padL + shift + (fp.xMin + fp.xMax) / 2} y="22" textAnchor="middle" fill="#F2EAE1" fontSize="14">
        {cm(fp.widthMm)} cm wide
      </text>
    </svg>
  )
}

function Buy() {
  const [swaps, setSwaps] = useState(false)
  const core = coreTotal(kit, swaps)
  const saving = coreTotal(kit, false) - coreTotal(kit, true)
  if (!kit.items.length) {
    return (
      <p className="measure">The parts list isn't bundled in this build. It comes from kit/parts.json.</p>
    )
  }
  return (
    <div className="measure buy">
      <section className="card-body buy-total">
        <div className="split">
          <div>
            <p className="kicker">Shopping list</p>
            <p>{kit.items.filter(isCore).length} items to buy</p>
          </div>
          <p className="price">
            {fmtUsd(core)}
            <small>{swaps ? 'With budget swaps' : 'Core build'}</small>
          </p>
        </div>
        <p className="fine">
          These are the recorded US street prices in kit/parts.json{kit.pricesChecked ? `, checked ${kit.pricesChecked}` : ''}. They are not a live quote. A link opens the retailer page stored with that part. Budget swaps replace a line with its cheaper alternate. Upgrades are shown and are never added. Shipping, tax, the optional desk mat and filament stay outside the core total.
        </p>
        <label className="swap-toggle">
          <input type="checkbox" checked={swaps} onChange={(e) => setSwaps(e.target.checked)} />
          Budget swaps
          <small>{saving > 0.005 ? `Cheaper picks where there is one; saves ${fmtUsd(saving)}` : 'Cheaper picks where there is one'}</small>
        </label>
        <p>
          Not in the budget
          {optionalTotal(kit, swaps) > 0 ? <span> · Optional (desk mat) {fmtUsd(optionalTotal(kit, swaps))}</span> : null}
          {excludedTotal(kit, swaps) > 0 ? <span> · Filament {fmtUsd(excludedTotal(kit, swaps))}</span> : null}
        </p>
      </section>
      {categories(kit).map(([cat, items]) => (
        <section key={cat}>
          <h2>
            {cat} <span>{fmtUsd(items.reduce((s, item) => s + line(item, swaps), 0))}</span>
          </h2>
          <ul className="buy-list">
            {items.map((item) => (
              <BuyRow key={item.id} item={item} swaps={swaps} />
            ))}
          </ul>
        </section>
      ))}
      <p className="fine">Download the same list from the repository as night-array/kit/BOM.md. Prices move. Confirm each retailer page before buying.</p>
    </div>
  )
}

function BuyRow({ item, swaps }: { item: KitItem; swaps: boolean }) {
  const swapped = swaps && item.swap
  const host = (() => {
    try {
      return item.buyUrl ? new URL(item.buyUrl).host.replace(/^www\./, '') : ''
    } catch {
      return ''
    }
  })()
  return (
    <li className={item.optional ? 'optional' : item.excluded ? 'excluded' : ''}>
      <div className="split">
        <div>
          {item.buyUrl ? (
            <a href={item.buyUrl} target="_blank" rel="noreferrer">
              {item.product}
              <span className="sr-only"> (opens {host} in a new tab)</span>
            </a>
          ) : (
            <strong>{item.product}</strong>
          )}
          {item.mpn ? <code>{item.mpn}</code> : null}
          {host ? <small>Retailer link · {host}</small> : <small>No retailer link was recorded for this part.</small>}
        </div>
        <div className="money">
          <b className={swapped ? 'struck' : ''}>{fmtUsd(line(item, false))}</b>
          <small>
            {item.qty} × {fmtUsd(item.unitUsd)}
          </small>
        </div>
      </div>
      {item.role ? <p>{item.role}</p> : null}
      {item.priceNote ? <p className="fine">Recorded price note: {item.priceNote}</p> : null}
      {item.why ? <p className="fine">{item.why}</p> : null}
      {item.optional ? <p className="flag">Optional · not in the core total</p> : null}
      {item.excluded ? <p className="flag">Filament · not in the core total</p> : null}
      {item.swap && swaps ? <Alt kind="Swap" item={item} alt={item.swap} active /> : null}
      {item.upgrade ? <Alt kind="Upgrade" item={item} alt={item.upgrade} active={false} /> : null}
    </li>
  )
}

function Alt({ kind, item, alt, active }: { kind: string; item: KitItem; alt: NonNullable<KitItem['swap']>; active: boolean }) {
  const delta = (alt.unitUsd - item.unitUsd) * item.qty
  return (
    <div className={active ? 'alt on' : 'alt'}>
      <span>
        <small>{kind}{active ? ' · counted' : ' · not counted'}</small>
        <strong>{alt.product}</strong>
        {alt.mpn ? <code>{alt.mpn}</code> : null}
        {alt.note ? <em>{alt.note}</em> : null}
      </span>
      <span>
        {fmtUsd(alt.unitUsd * item.qty)}
        <small>{fmtDelta(delta)}</small>
      </span>
    </div>
  )
}
