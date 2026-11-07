# Night Array kit: build it yourself

Night Array as a real desk station you build at home: buy off-the-shelf parts, 3D-print the shells (Bambu Lab, 256 mm bed), and assemble.

- **[BOM.md](BOM.md)**: the shopping list, with prices, part numbers, links and budget swaps. Also as [bom.csv](bom.csv), generated from [parts.json](parts.json).
- **[KIT_SPEC.md](KIT_SPEC.md)**: the design rules and decisions.
- **[research/parts-research.json](research/parts-research.json)**: the sourcing research behind every pick, with sources. Five categories, each checked by an independent verifier on 2026-11-07.

## Status

| | |
|---|---|
| **Parts selected and verified** | Done. Every primary part is a real, currently sold product with a confirmed part number, a plausible price and checked dimensions. Wrong, discontinued or out-of-stock picks were replaced. |
| **Shopping list** | Done: [BOM.md](BOM.md), also in the app (Specs → Buy). |
| **Printable shells (STLs), steel cut files, laptop-insert generator, wiring diagram, assembly guide** | **On hold** (owner's call, 2026-11-07). A first CAD layout with the real parts is on the development branch, not on `main`: real monitor, keyboard, mouse, pad, dock, strip and charger envelopes; the steel structure; a tip-over check that passes, tipping only past 32° with a 1.3–1.4× margin on a push; and zero part collisions. Picking up from there is the next step. |

## What it costs

| | |
|---|---|
| Core build, primary picks | **about $1,730** |
| With every budget swap in [BOM.md](BOM.md) | **about $1,310** |
| Filament (not in the budget) | about $200 |

The two monitors are about 40 % of the cost. You reach the ~$1,200 target in two ways:

- **Monitors:** the swap uses the ASUS PA278CFRV at about $229 each, and it has sold for about $190 at times. Catching that deal brings the total close to $1,200.
- **Your own keyboard and mouse:** keeping ones you already own also gets you there. Each one needs a Qi receiver, or it simply won't charge in its pocket.

## How it fits together

- **Structure.** Neither the monitors' weight nor the laptop's rests on printed plastic. The path is: two Samsung S60UD monitors, each turned 10° toward you, VESA-mounted to a laser-cut steel wing bracket with folded flanges. The bracket sits on two 2040 aluminium posts inside the printed neck, which stand on a 1/4" steel spine plate that is also the ballast.
  - The printed base tiles sit on two 2020 rails and a steel front bar.
  - The printed shroud, frame, neck and cradle shells cover, locate and light.
- **Mains power.** One cord leaves the station. It goes into a certified Tripp Lite strip inside the base, which feeds both monitors (each has an internal PSU), the dock's power brick and a USB-C GaN charger. You never wire mains yourself: everything plugs in.
- **Video and charging.** The laptop stands closed in the cradle. Its own weight seats its USB-C port on a sprung, self-centring plug, which is one end of the dock's host cable. Lift it straight out to undock: no latch, switch or lock.
  - The Plugable DisplayLink dock drives both screens and charges the laptop at up to 100 W, from any USB-C laptop, Mac or Windows.
  - Thunderbolt laptops can use the TBT-6950PD upgrade for native, uncompressed video.
- **Wireless charging.** An Anker 313 Qi pad sits intact under each pocket, under a 1 mm solid PETG floor.
  - The Lenovo X9 mouse charges natively.
  - The Keychron K3 Ultra gets a thin NILLKIN Magic Tag receiver that plugs into its USB-C port and folds flat underneath.
  - Printed locator inserts put each receiver over its coil.
- **Light.** The amber accents are one 12 V reel of 1800 K slim COB strip in 5 mm aluminium channels, with one dimmer knob.
  - The dock's seated light is switched by an IR beam across the slot, so there's no mechanical switch.
  - The charge marks light while a pad is powered. That replaces the concept's "breathing while charging", which a sealed off-the-shelf pad doesn't report.

## Before you buy

- **Monitors:** buy both from one retailer at the same time, so they share the same panel batch, tint and firmware. An honest seam makes mismatches obvious.
- **Monitor mains inlet:** on arrival, check that the S60UD's inlet is C14, and check the VESA depth, bezels and joystick position. The shroud is designed from Samsung's published model, which is accurate to about ±1–2 mm.
- **Gravity seating:** check that your laptop seats under its own weight. Lighter laptops with stiff USB-C ports may need a gentle press, so test with the cable before printing the cradle. The laptop must rest on the cradle floor, never on the plug.
- **Mouse puck:** the Razer puck (mouse upgrade) is often out of stock.
- **Metal-detection blink:** if the Anker pad blinks for metal under the keyboard, add a thin ferrite sheet between the receiver and the keyboard.
- **Filament and printer:** PETG-CF needs a hardened-steel nozzle, and ASA needs an enclosed printer, so use PETG on an A1. Bambu's PETG HF colours were out of stock on 2026-11-07, which is why the picks are PETG Basic.
- **Springs:** check the McMaster springs' specs in a browser before ordering. Their pages couldn't be checked automatically.
- **Prices:** prices and stock move. `parts.json` records the date they were checked, and `tools/make_bom.py` regenerates the list after you edit it.
