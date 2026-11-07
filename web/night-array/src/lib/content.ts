import { fmtNum, fmtMm } from './format'
import {
  bbox,
  displayWidthMm,
  filesOf,
  footprint,
  materialLabel,
  mullionMm,
  num,
  nums,
  overallMm,
  portFromHingeMm,
  scene,
  span,
  stationMassG,
  text,
  type Scene,
} from './scene'
import type { Preset } from './types'

export type StorySpec = { label: string; value: string }
export type StoryStill = { name: string; caption: string }
export type Story = {
  id: string
  number: string
  kicker: string
  title: string
  line: string
  lede: string
  body: string[]
  specs: StorySpec[]
  stills: StoryStill[]
  preset: Preset
  liveLabel: string
}
export type ModeInfo = { id: 'work' | 'stow' | 'standalone'; title: string; sub: string; body: string; still: string; camera: Preset['camera'] }
export type Principle = { title: string; body: string }

export const MODES: ModeInfo[] = [
  {
    id: 'work',
    title: 'Work',
    sub: 'Active, open desk',
    body: "Keyboard and mouse come forward onto a felt mat, 15 cm clear of the base. The deck behind them stays empty and both panels sit at arm's length.",
    still: 'hero-work.jpg',
    camera: 'hero',
  },
  {
    id: 'stow',
    title: 'Stow & Charge',
    sub: 'Put away, power up',
    body: 'Slide both into their pockets and they start charging. Two amber marks on the pocket lips say so, and fade out when the batteries are full.',
    still: 'hero-stow.jpg',
    camera: 'trays',
  },
  {
    id: 'standalone',
    title: 'Standalone',
    sub: 'Compute stays in the base',
    body: 'Lift the laptop out and leave with it. The computer in the base takes over both panels with its own desktop.',
    still: 'hero-standalone.jpg',
    camera: 'hero',
  },
]

export const FINISHES = [
  ['titanium', 'Neutral Titanium'],
  ['graphite', 'Charcoal Graphite'],
  ['oxblood', 'Brushed Oxblood'],
] as const

export const STYLES = [
  ['studio', 'Studio'],
  ['cad', 'CAD'],
  ['xray', 'X-ray'],
  ['blueprint', 'Blueprint'],
] as const

export const MODE_TABS = [
  ['work', 'Work'],
  ['stow', 'Stow'],
  ['standalone', 'Standalone'],
] as const

export const CAMERAS = [
  ['hero', 'Hero'],
  ['front', 'Front'],
  ['display', 'Display'],
  ['dock', 'Dock'],
  ['trays', 'Trays'],
  ['top', 'Top'],
  ['side', 'Side'],
  ['back', 'Back'],
] as const

export const QUALITIES = [
  ['high', 'High'],
  ['balanced', 'Balanced'],
  ['battery', 'Battery'],
] as const

export const NIGHT_LINES = [
  'Two panels. One horizon.',
  'Compute stays in the base.',
  'Put it away. It powers up.',
  '5120 × 1440 · two 27-inch QHD.',
  'The seam is part of the deal.',
  'One cable leaves the back.',
  'Light only where it means something.',
  'Your hardware. Your OS.',
]

export const DOCK_STEPS = [
  ['align', 'Align', 'Guide it into the open cradle'],
  ['lower', 'Lower', 'Its own weight seats it on the USB-C'],
  ['lift', 'Lift out', 'Lift straight up — nothing to unlock'],
] as const

export const BOARD_NOTE =
  'The first board drew a single curved ultrawide. We kept the base, the trays, the dock, the light and the materials, and swapped the display for two mainstream 27-inch QHD panels in one titanium shroud: the same 5120 × 1440 pixels for a fraction of the price, and a dead panel is a cheap swap. The seam is the trade, so we made it a feature.'

export const PRINCIPLES: Principle[] = [
  { title: 'One object', body: 'Display, dock, chargers and computer are one piece of furniture, not a cluster of gadgets sharing a desk.' },
  { title: 'Put it away, power it up', body: 'Tidying and charging are the same motion.' },
  { title: 'Honest parts', body: 'Two off-the-shelf 27-inch panels, VESA 100, USB-C, Qi2. Anything that wears out is something you can buy.' },
  { title: 'Show the seam', body: "Where two things meet, say so. The titanium mullion is the station's centre line, not a flaw to paper over." },
  { title: 'Light means something', body: 'Amber appears only where it reports a state. It never blinks.' },
  { title: 'The slot does the aiming', body: "Chamfers, pockets and stops guide every move, so you don't have to look." },
  { title: 'Your hardware. Your OS.', body: 'Bring the laptop and the operating system you already use. Nothing here needs an app or an account.' },
]

const LAPTOP_CLEARANCE_MM = 2

export const STORIES: Story[] = [
  {
    id: 'dual',
    number: '01',
    kicker: 'Display',
    title: 'Two panels, one horizon',
    line: 'Two mainstream QHD panels in one titanium shroud',
    lede: 'Inside the shroud sit two ordinary 27-inch QHD monitors with their plastic housings taken off. Side by side they draw 5120 × 1440: the pixels of a 49-inch super-ultrawide, for the price of two good mainstream screens.',
    body: [
      'Each panel is a 2560 × 1440 IPS module, the size and resolution the industry builds by the million, which is exactly why it is cheap and why it is good. Together they give almost 1.2 m of active width at 109 pixels per inch: crisp text at arm\'s length.',
      'Each panel is toed in 10° about the seam, which brings its outer edge about 106 mm toward you. The far corners come about 8 cm closer and meet your eye less obliquely than on a flat pair, though at arm\'s length you will still turn your head toward the edges.',
      "Between the two active areas runs a 14 mm seam. We don't disguise it. A 4 mm titanium mullion covers the joint and becomes the station's centre line, and most work splits there anyway: code on the left, preview on the right; the call on one side, your notes on the other.",
      'Your OS already knows how to drive two displays. Snap a window to each half, or span one across both. And if a panel gives out in year five, the replacement is a standard 27-inch module on four VESA screws, not a service ticket.',
    ],
    specs: [],
    stills: [
      { name: 'display.jpg', caption: 'The honest seam: a 4 mm titanium mullion over the 14 mm joint.' },
      { name: 'hero-work.jpg', caption: 'One 5120 × 1440 canvas, split exactly where your OS splits it.' },
    ],
    preset: { mode: 'work', style: 'studio', camera: 'display', explode: 0 },
    liveLabel: 'See the panels live',
  },
  {
    id: 'work-stow',
    number: '02',
    kicker: 'Modes',
    title: 'Work & Stow',
    line: 'Two states, one footprint',
    lede: "Pull the keyboard and mouse forward to work. Push them back into the base when you're done, and the desk is clear.",
    body: [
      'In Work, the keyboard sits on a felt mat 15 cm in front of the base: close enough that the panels stay at arm\'s length, far enough that your wrists rest on the desk instead of the titanium.',
      'In Stow, both drop into pockets cut into the deck. The keyboard pocket is 376 × 136 mm and the mouse pocket 82 × 134 mm, with a few millimetres of play all round, so they go in without looking and come out with two fingers.',
      'There is no drawer and no cable to put away. Tidying up is the same motion as plugging in.',
    ],
    specs: [
      { label: 'Work offset', value: '150 mm in front of the base' },
      { label: 'Keyboard pocket', value: '376 × 136 mm' },
      { label: 'Mouse pocket', value: '82 × 134 mm' },
      { label: 'Pocket depth', value: '14 mm below the deck' },
      { label: 'Desk mat', value: '820 × 300 mm felt' },
    ],
    stills: [
      { name: 'hero-work.jpg', caption: 'Work: active, open desk.' },
      { name: 'hero-stow.jpg', caption: 'Stow & Charge: put away, power up.' },
    ],
    preset: { mode: 'stow', style: 'studio', camera: 'hero', explode: 0 },
    liveLabel: 'Switch modes live',
  },
  {
    id: 'dock',
    number: '03',
    kicker: 'Dock',
    title: 'The dock',
    line: 'A vertical cradle on the right wing',
    lede: 'Your laptop stands on its edge in the right wing, lid closed, connected by its own weight.',
    body: [
      "The cradle is a titanium wing with a 20 mm slot and chamfered lead-ins. Guide the laptop into the open cradle and let go: its own weight, about 1.3 kg, seats its USB-C port on a sprung, self-centring connector on the slot floor. The chamfers do the aiming, not your eyes.",
      "To leave, lift it straight out. The slot walls hold the laptop upright, so the plug only carries power and data and is never levered. USB-C's own grip, roughly 8–20 N, keeps it connected, and a gentle lift is all it takes to let go.",
      "The outer faces wear brushed oxblood: the station's one deep colour, on the side your hand reaches for. A slim amber line near the top of the front face, right under the laptop, glows while it is seated.",
    ],
    specs: [
      { label: 'Position', value: 'Right outer wing' },
      { label: 'Slot', value: '20 × 224 mm, 4 mm lead-in chamfers' },
      { label: 'Connector', value: 'Sprung, self-centring USB-C on the slot floor' },
      { label: 'Docking', value: 'Its own weight seats it; lift straight out' },
      { label: 'Seated light', value: '30 × 2 mm amber line on the front face' },
      { label: 'Laptop', value: 'Slim laptops up to 18 mm thick, with a USB-C port on the docking edge near the hinge' },
      { label: 'Footprint', value: '125 × 260 mm' },
    ],
    stills: [
      { name: 'dock-align.jpg', caption: '1 · Align: guide it into the open cradle.' },
      { name: 'dock-lower.jpg', caption: '2 · Lower: its own weight seats it on the USB-C.' },
      { name: 'dock-lift.jpg', caption: '3 · Lift out: straight up, and it lets go.' },
    ],
    preset: { mode: 'stow', style: 'studio', camera: 'dock', explode: 0, dock: 'play' },
    liveLabel: 'Play the sequence live',
  },
  {
    id: 'charge',
    number: '04',
    kicker: 'Charging',
    title: 'Charge in place',
    line: 'Qi2 coils under the pads',
    lede: 'Set it down where it lives and it charges. No cable, no puck, nothing to line up.',
    body: [
      'Under each soft-touch pad is a flat Qi2 coil on a ferrite shield: two under the keyboard, one under the mouse. The pocket walls place each device within a few millimetres of its coil, which is all inductive charging asks for.',
      'Titanium would block the field, so the pocket floors are cut with round non-metallic windows over every coil. A faint ring debossed in each pad marks the spot, though the walls already put you there.',
      'The receiver coils sit in the floors of the keyboard and mouse, directly over the transmitters when stowed, with 2 mm of pad between them.',
      "A thin amber mark on each pocket's front lip glows while charging and fades out when the battery is full.",
    ],
    specs: [
      { label: 'Standard', value: 'Qi2' },
      { label: 'Keyboard', value: '2 coils, 160 mm apart' },
      { label: 'Mouse', value: '1 coil' },
      { label: 'Shielding', value: 'Ferrite plate under every coil' },
      { label: 'Pad', value: '2 mm soft-touch graphite' },
      { label: 'Indicators', value: '30 mm and 16 mm amber marks' },
    ],
    stills: [
      { name: 'trays.jpg', caption: 'Both pockets, devices stowed.' },
      { name: 'xray.jpg', caption: 'X-ray: coils and ferrite under the pads.' },
    ],
    preset: { mode: 'stow', style: 'xray', camera: 'trays', explode: 0 },
    liveLabel: 'See it live',
  },
  {
    id: 'compute',
    number: '05',
    kicker: 'Compute',
    title: 'Compute stays in the base',
    line: 'A computer, not a monitor waiting for one',
    lede: 'The Array runs on its own. Dock a laptop and it takes the panels; lift it out and the base carries on.',
    body: [
      'A full mainboard with a vapor-chamber cooler and a slim blower lives under the left half of the 36 mm base. The power supply sits on the right, beside the mouse pocket. One mains cable feeds everything.',
      'Each 27-inch panel keeps its own scaler board, mounted on the steel spine behind it. To the computer they are simply two monitors on two standard display links: no custom display electronics, nothing proprietary to fail.',
      'Air comes in under the front edge and leaves through the rear cut-outs on the left, away from your hands.',
    ],
    specs: [
      { label: 'Mainboard', value: '300 × 230 mm, base left' },
      { label: 'Cooling', value: 'Vapor chamber + slim blower' },
      { label: 'Display links', value: '2, one per panel' },
      { label: 'Power', value: 'Internal PSU, one cable' },
      { label: 'I/O', value: 'Rear face, left side' },
      { label: 'Base height', value: '36 mm' },
    ],
    stills: [
      { name: 'hero-standalone.jpg', caption: 'Standalone: laptop gone, both panels still running.' },
      { name: 'section.jpg', caption: 'Section through the base.' },
      { name: 'exploded.jpg', caption: 'Exploded: every part, every layer.' },
    ],
    preset: { mode: 'standalone', style: 'xray', camera: 'hero', explode: 0.35 },
    liveLabel: 'See it live',
  },
  {
    id: 'amber',
    number: '06',
    kicker: 'Light',
    title: 'Light that informs',
    line: 'Amber only where it means something',
    lede: 'Five lights, five jobs. None of them blinks, none of them changes colour.',
    body: [
      'The under-glow along the front edge finds the desk in a dark room. The bar on the neck says the panels are awake. The marks on the pocket lips say charging. The line on the dock\'s front face says the laptop is seated. The tail light on the mouse tells you where you left it.',
      "One slider sets all five, from off to a low warm glow. The amber sits well below the screens' white, so it never competes with what you're reading.",
    ],
    specs: [
      { label: 'Under-glow', value: '1120 mm strip, front edge' },
      { label: 'Neck bar', value: '150 mm, panels awake' },
      { label: 'Pocket marks', value: 'Charging; fade when full' },
      { label: 'Dock light', value: 'Laptop seated' },
      { label: 'Mouse', value: 'Tail light' },
      { label: 'Colour', value: 'Amber #F2A04A, dims to off' },
    ],
    stills: [
      { name: 'hero-work.jpg', caption: 'Amber at 80 %.' },
      { name: 'amber-off.jpg', caption: 'Amber off.' },
    ],
    preset: { mode: 'stow', style: 'studio', amber: 1, camera: 'trays' },
    liveLabel: 'Set the light live',
  },
  {
    id: 'materials',
    number: '07',
    kicker: 'Materials',
    title: 'Materials & finishes',
    line: 'Titanium, graphite, oxblood',
    lede: 'Three materials, chosen to look better at night than in a showroom.',
    body: [
      "The base, cradle, shroud rim, seam mullion and neck lettering are titanium: stiff enough that a 1.3 m slab doesn't flex under your palms, warm enough in tone to sit beside wood.",
      "The surfaces you touch or look past most are charcoal graphite: the pads, the neck, the back of the shroud. The dock's outer panels are brushed oxblood.",
      'Pick the metal: Neutral Titanium, Charcoal Graphite or Brushed Oxblood. The rest of the palette holds still.',
    ],
    specs: [
      { label: 'Primary metal', value: 'Titanium, 4.43 g/cm³' },
      { label: 'Soft surfaces', value: 'Charcoal graphite: soft-touch pads, anodised neck and shroud' },
      { label: 'Accent', value: 'Brushed oxblood panels' },
      { label: 'Panel faces', value: 'Black glass' },
      { label: 'Finishes', value: 'Titanium · Graphite · Oxblood' },
    ],
    stills: [
      { name: 'finish-titanium.jpg', caption: 'Neutral Titanium.' },
      { name: 'finish-graphite.jpg', caption: 'Charcoal Graphite.' },
      { name: 'finish-oxblood.jpg', caption: 'Brushed Oxblood.' },
    ],
    preset: { mode: 'stow', style: 'studio', finish: 'graphite', camera: 'hero' },
    liveLabel: 'Try the finishes live',
  },
  {
    id: 'cablefree',
    number: '08',
    kicker: 'Desk',
    title: 'A cable-free desk',
    line: 'One cable leaves the back',
    lede: 'From your chair, nothing on the desk is plugged into anything.',
    body: [
      'Mains power enters at the rear and is shared inside the base by the two panels, the computer, the dock and both chargers. The ports are cut into the back face on the left, out of sight.',
      "The keyboard and mouse are wireless and charge in their pockets. The laptop connects through the floor of the cradle. The only cable you'll ever see runs from the back of the base to the wall.",
    ],
    specs: [
      { label: 'Cables on the desk', value: '1, power, at the rear' },
      { label: 'Ports', value: 'Rear face, left side' },
      { label: 'Peripherals', value: 'Wireless, charged in place' },
      { label: 'Laptop', value: 'Docks without a cable' },
    ],
    stills: [
      { name: 'blueprint.jpg', caption: 'Blueprint: every edge, nothing else.' },
      { name: 'cad.jpg', caption: 'CAD view of the assembly.' },
    ],
    preset: { mode: 'stow', style: 'blueprint', camera: 'back' },
    liveLabel: 'See it live',
  },
]

export function storyById(id: string | undefined): Story | undefined {
  return STORIES.find((s) => s.id === id)
}

function mm(v: number | null, fallback: string): string {
  return v != null ? `${fmtNum(v)} mm` : fallback
}

export function storySpecs(s: Story, model: Scene = scene): StorySpec[] {
  if (s.id === 'dual') {
    const sc = model.screen
    return [
      { label: 'Panels', value: `${sc.panels} × ${fmtNum(sc.panelInch)}″ QHD IPS, off the shelf` },
      { label: 'Canvas', value: `${sc.canvasW} × ${sc.canvasH}` },
      { label: 'Each panel', value: `${sc.resEach[0]} × ${sc.resEach[1]}, ${fmtNum(sc.activeMm[0])} × ${fmtNum(sc.activeMm[1])} mm` },
      { label: 'Density', value: `${Math.round(sc.ppi)} ppi` },
      { label: 'Toe-in', value: `${fmtNum(sc.toeInDeg)}° per panel` },
      { label: 'Seam', value: `${fmtNum(sc.seamMm)} mm, 4 mm titanium mullion` },
      { label: 'Width', value: `≈ ${fmtMm(displayWidthMm(model))} mm across` },
      { label: 'Mount', value: 'VESA 100 per panel, steel spine' },
    ]
  }
  if (s.id === 'dock') {
    const slotW = span(model, 'dock.slot.x')
    const slotL = span(model, 'dock.slot.z')
    const lead = num(model, 'dock.slot.lead_in')
    const ledW = num(model, 'dock.led.w')
    const ledH = num(model, 'dock.led.h')
    const w = span(model, 'dock.x')
    const d = span(model, 'dock.z')
    return s.specs.map((r) => {
      if (r.label === 'Slot' && slotW != null && slotL != null) return { ...r, value: `${fmtNum(slotW)} × ${fmtNum(slotL)} mm, ${fmtNum(lead ?? 4)} mm lead-in chamfers` }
      if (r.label === 'Seated light' && ledW != null && ledH != null) return { ...r, value: `${fmtNum(ledW)} × ${fmtNum(ledH)} mm amber line on the front face` }
      if (r.label === 'Laptop' && slotW != null) return { ...r, value: `Slim laptops up to ${fmtNum(slotW - LAPTOP_CLEARANCE_MM)} mm thick, with a USB-C port on the docking edge near the hinge` }
      if (r.label === 'Footprint' && w != null && d != null) return { ...r, value: `${fmtNum(w)} × ${fmtNum(d)} mm` }
      return r
    })
  }
  if (s.id === 'work-stow') {
    const kb = nums(model, 'base.kb_pocket.size')
    const ms = nums(model, 'base.mouse_pocket.size')
    const deck = num(model, 'base.deck_y')
    const floor = num(model, 'base.kb_pocket.floor_y')
    const mat = nums(model, 'deskmat.size')
    const gap = footprint(model).workGapMm
    return s.specs.map((r) => {
      if (r.label === 'Work offset') return { ...r, value: `${fmtNum(gap)} mm in front of the base` }
      if (r.label === 'Keyboard pocket' && kb && kb.length >= 2) return { ...r, value: `${fmtNum(kb[0])} × ${fmtNum(kb[1])} mm` }
      if (r.label === 'Mouse pocket' && ms && ms.length >= 2) return { ...r, value: `${fmtNum(ms[0])} × ${fmtNum(ms[1])} mm` }
      if (r.label === 'Pocket depth' && deck != null && floor != null) return { ...r, value: `${fmtNum(deck - floor)} mm below the deck` }
      if (r.label === 'Desk mat' && mat && mat.length >= 3) return { ...r, value: `${fmtNum(mat[0])} × ${fmtNum(mat[2])} mm felt` }
      return r
    })
  }
  if (s.id === 'charge') {
    const kbx = nums(model, 'internals.qi_coils_kb_x')
    const win = num(model, 'base.coil_window_d')
    const pad = num(model, 'base.pad_t')
    return s.specs.map((r) => {
      if (r.label === 'Keyboard' && kbx && kbx.length >= 2) return { ...r, value: `${kbx.length} coils, ${fmtNum(Math.max(...kbx) - Math.min(...kbx))} mm apart` }
      if (r.label === 'Shielding' && win != null) return { ...r, value: `Ferrite under every coil; ${fmtNum(win)} mm windows in the titanium` }
      if (r.label === 'Pad' && pad != null) return { ...r, value: `${fmtNum(pad)} mm soft-touch graphite` }
      return r
    })
  }
  return s.specs
}

export type SpecSection = { title: string; sub: string; rows: StorySpec[] }

export function specSheet(model: Scene = scene): SpecSection[] {
  const sc = model.screen
  const fp = footprint(model)
  const base = bbox(model, 'base')
  const dock = bbox(model, 'dock')
  const o = overallMm(model)
  const boardW = span(model, 'internals.board.x')
  const boardD = span(model, 'internals.board.z')
  const coilsKb = nums(model, 'internals.qi_coils_kb_x')
  const slotW = span(model, 'dock.slot.x')
  const slotL = span(model, 'dock.slot.z')
  const activeY = sc.activeY ?? nums(model, 'display.active_y')
  const box = (b: number[] | null, fallback: string) => (b ? `${fmtMm(b[0])} × ${fmtMm(b[1])} × ${fmtMm(b[2])} mm` : fallback)
  const mm2 = (v: number[] | null, fallback: string) => (v && v.length >= 2 ? `${fmtNum(v[0])} × ${fmtNum(v[1])} mm` : fallback)
  return [
    {
      title: 'Display',
      sub: 'Two mainstream panels, one shroud',
      rows: [
        { label: 'Panels', value: `${sc.panels} × ${fmtNum(sc.panelInch)}″ QHD IPS, off the shelf` },
        { label: 'Canvas', value: `${sc.canvasW} × ${sc.canvasH}, as ${sc.panels} displays of ${sc.resEach[0]} × ${sc.resEach[1]}` },
        { label: 'Active area', value: `${sc.panels} × ${fmtNum(sc.activeMm[0])} × ${fmtNum(sc.activeMm[1])} mm` },
        { label: 'Density', value: `${Math.round(sc.ppi)} ppi` },
        { label: 'Toe-in', value: `${fmtNum(sc.toeInDeg)}° per panel, about the seam` },
        { label: 'Seam', value: `${fmtNum(sc.seamMm)} mm between active areas; ${mullionMm(model)} titanium mullion` },
        { label: 'Width', value: `≈ ${fmtMm(displayWidthMm(model))} mm across both panels` },
        { label: 'Screen height', value: activeY ? `Active area ${fmtNum(activeY[0])}–${fmtNum(activeY[1])} mm above the desk` : 'Active area 172–508 mm above the desk' },
        { label: 'Mount', value: `VESA 100 per panel on a steel spine; ${mm(num(model, 'display.shroud_depth'), '45 mm')} shroud; own scaler boards kept` },
      ],
    },
    {
      title: 'Dock',
      sub: 'Right outer wing',
      rows: [
        { label: 'Cradle', value: `${box(dock, '125 × 120 × 260 mm')}, titanium + brushed oxblood` },
        { label: 'Slot', value: `${fmtNum(slotW ?? 20)} × ${fmtNum(slotL ?? 224)} mm, ${mm(num(model, 'dock.slot.lead_in'), '4 mm')} chamfered lead-ins` },
        { label: 'Connector', value: 'Sprung, self-centring USB-C on the slot floor' },
        { label: 'Docking', value: 'Guide it in and its own weight seats it on the plug; lift straight out to leave' },
        { label: 'Hold', value: "USB-C's own retention, roughly 8–20 N; the slot walls keep the laptop upright" },
        {
          label: 'Laptops',
          value: `Up to ${mm(slotW != null ? slotW - LAPTOP_CLEARANCE_MM : null, '18 mm')} thick and ${mm(slotL, '224 mm')} deep, standing closed on edge; USB-C port about ${mm(portFromHingeMm(model), '46 mm')} from the hinge end`,
        },
      ],
    },
    {
      title: 'Charging',
      sub: 'Qi2, in place',
      rows: [
        { label: 'Keyboard pocket', value: `${mm2(nums(model, 'base.kb_pocket.size'), '376 × 136 mm')}, ${coilsKb?.length ?? 2} Qi2 coils` },
        { label: 'Mouse pocket', value: `${mm2(nums(model, 'base.mouse_pocket.size'), '82 × 134 mm')}, 1 Qi2 coil` },
        {
          label: 'Coils',
          value: coilsKb && coilsKb.length >= 2 ? `Two under the keyboard, ${fmtNum(Math.max(...coilsKb) - Math.min(...coilsKb))} mm apart; one under the mouse` : 'Two under the keyboard, one under the mouse',
        },
        { label: 'Shielding', value: 'Ferrite plate under every coil' },
        { label: 'Pads', value: `${mm(num(model, 'base.pad_t'), '2 mm')} soft-touch graphite` },
        { label: 'Indicators', value: 'Amber marks on the pocket lips' },
      ],
    },
    {
      title: 'Compute',
      sub: 'Stays in the base',
      rows: [
        { label: 'Mainboard', value: `${boardW != null && boardD != null ? `${fmtNum(boardW)} × ${fmtNum(boardD)} mm` : '300 × 230 mm'}, under the left deck` },
        { label: 'Cooling', value: 'Vapor chamber, fin stack, slim blower' },
        { label: 'Power', value: 'Internal PSU beside the mouse pocket, one mains cable' },
        { label: 'Displays', value: 'One link per panel' },
        { label: 'I/O', value: 'Rear face, left side' },
      ],
    },
    {
      title: 'Peripherals',
      sub: 'Wireless, charged where they live',
      rows: [
        { label: 'Keyboard', value: `${text(model, 'keyboard.layout') ?? '75 %'}, ${mm2(nums(model, 'keyboard.size'), '360 × 120 mm')}` },
        { label: 'Keyboard height', value: `${mm(num(model, 'keyboard.h_front'), '9 mm')} front, ${mm(num(model, 'keyboard.h_back'), '13 mm')} back` },
        {
          label: 'Mouse',
          value: (() => {
            const m = nums(model, 'mouse.size')
            return m && m.length === 3 ? `${fmtNum(m[0])} × ${fmtNum(m[1])} × ${fmtNum(m[2])} mm, ambidextrous` : '66 × 118 × 38 mm, ambidextrous'
          })(),
        },
        { label: 'Desk mat', value: `Wool felt, ${mm2(nums(model, 'deskmat.size')?.length ? [nums(model, 'deskmat.size')![0], nums(model, 'deskmat.size')!.at(-1)!] : null, '820 × 300 mm')}` },
      ],
    },
    {
      title: 'Lighting',
      sub: 'Amber #F2A04A, dims to off',
      rows: [
        { label: 'Under-glow', value: '1120 mm strip along the front edge' },
        { label: 'Neck bar', value: `${mm(num(model, 'neck.light.w'), '150 mm')}, panels awake` },
        { label: 'Pocket marks', value: '30 mm and 16 mm, charging' },
        { label: 'Dock light', value: `${mm(num(model, 'dock.led.w'), '30 mm')} on the cradle's front face, laptop seated` },
        { label: 'Mouse', value: 'Tail light' },
      ],
    },
    {
      title: 'Materials',
      sub: 'Three finishes for the metal',
      rows: [
        ...['titanium', 'graphite', 'oxblood', 'glass_black', 'felt'].map((k) => ({
          label: materialLabel(model, k),
          value:
            model.materials[k]?.spec
              ? model.materials[k].spec.charAt(0).toUpperCase() + model.materials[k].spec.slice(1)
              : k === 'titanium'
                ? 'Grade 5 titanium, 4.43 g/cm³'
                : k === 'graphite'
                  ? 'Charcoal graphite finish'
                  : k === 'oxblood'
                    ? 'Brushed oxblood finish'
                    : k === 'glass_black'
                      ? 'Black cover glass'
                      : 'Pressed wool felt',
        })),
        { label: 'Finish choice', value: FINISHES.map(([, label]) => label).join(' · ') },
      ],
    },
    {
      title: 'Dimensions',
      sub: 'Stow pose, millimetres',
      rows: [
        { label: 'Overall', value: `${fmtMm(fp.widthMm)} × ${fmtMm(o[1])} × ${fmtMm(fp.baseDepthMm)} mm (W × H × D)` },
        { label: 'Base slab', value: box(base, '1 290 × 36 × 300 mm') },
        { label: 'Display top', value: `${fmtMm(o[1])} mm above the desk` },
        { label: 'Work zone', value: `${fmtMm(fp.workGapMm)} mm clear in front of the base` },
        { label: 'Desk needed', value: `${cmLabel(fp.widthMm)} × ${cmLabel(fp.workDepthMm)} cm to work, ${cmLabel(fp.widthMm)} × ${cmLabel(fp.baseDepthMm)} cm stowed` },
        { label: 'Mass', value: stationMassG(model) > 0 ? `${massLabel(stationMassG(model))} without laptop and mat (concept estimate)` : '—' },
      ],
    },
  ]
}

function cmLabel(mm: number): string {
  const c = mm / 10
  return Math.abs(c - Math.floor(c)) < 1e-6 ? String(Math.floor(c)) : c.toFixed(1)
}

function massLabel(g: number): string {
  if (g < 1000) return `${Math.round(g)} g`
  if (g < 10_000) return `${(g / 1000).toFixed(2)} kg`
  return `${(g / 1000).toFixed(1)} kg`
}

export function dockUi(model: Scene = scene) {
  return DOCK_STEPS.map(([id, title, caption], i) => {
    const st = model.dockSteps.find((s) => s.step === id)
    return { n: i + 1, id, title: st?.title || title, caption: st?.caption || caption, still: `dock-${id}.jpg` }
  })
}

export function assemblyFiles(model: Scene = scene) {
  return filesOf(model, null)
}
