# Night Array Kit: build contract

We're turning the concept into something you can build at home: buy real parts, print the shells on a **Bambu Lab printer (256 × 256 × 256 mm)**, and assemble it.
This file is the contract between everyone working on the kit. `../SPEC.md` still governs coordinates, file formats and the app ↔ viewer bridge.
Where they disagree, this file wins for anything about the physical build.

The raw sourcing research is in `research/parts-research.json`: five categories, each independently verified, with sources and prices as of 2026-11-07.

## Owner decisions (2026-11-07)

1. **Dock.** Latch-free: no switch, button or lock. The laptop's own weight seats it on a sprung USB-C plug, and you lift it straight out.
2. **Universal cradle.** Printable slot inserts and an adjustable plug carriage fit most 11–20 mm laptops, Mac and Windows. A script generates the insert from three measurements, and a printable gauge checks it.
3. **Printer.** Bambu Lab, 256 mm bed. Every printed part must fit **245 × 245 × 245 mm**, leaving 5 mm of margin.
4. **No computer in the base.** The laptop is the computer, so **Standalone mode is removed** everywhere: CAD poses, viewer, app copy and UI.
5. **Budget.** Balanced, about US$1,200, excluding the laptop, the printer and filament. Prices swing, so give a realistic total and a "budget swaps" list that reaches the target.

## Hard rules

- **No user mains wiring.** Mains stays inside certified products: the power strip, the monitors' internal PSUs, the dock brick and the GaN charger.
  - Only plug-in IEC or NEMA cords and low-voltage DC wiring are done by the builder.
  - One mains cord leaves the station.
- **No printed part carries monitor load.** Load path: monitors → steel wing bracket → 2× 2040 aluminium posts → steel spine/ballast plate → feet.
  - Printed shells locate, cover and light.
- **Qi keep-out.** Keep these at least 10 mm away from each charging-pad footprint: metal, magnets, LED PCBs and screws. Steel stays at least 20 mm away.
  - The pocket floor is solid plastic, 1.0 mm over the coil, printed in PETG at 100 % infill.
- **Heat.** The monitors have internal PSUs, so never seal their rear box. Keep at least 10 mm of air over it, with intakes underneath and exhausts on top.
  - PETG (or ASA on an enclosed printer) wherever a part is near heat. PLA only for small, cool accents.
- **Stability.** The station must pass a 10° tilt in every direction, with monitors fitted and the laptop either docked or not.
  - It must also resist a 50 N push at the top of the screen in any direction without tipping.
  - Check this in `verify.py`.

## Parts (primary picks; alternates in parentheses)

`kit/parts.json` is the single source of truth for the bill of materials. Fields per item: `id, category, role, product, mpn, qty, unit_usd, buy_url, spec_sources, dims_mm, notes, alternates[], verified (date, status)`.

| Area | Primary | Alternate / budget swap |
|---|---|---|
| Monitors (×2) | Samsung ViewFinity S6 **S60UD 27" QHD** `LS27D606UANXGO`, about $330–370 each, about $300 on sale. 612.9 × 362.6 face, 41.6 deep, 3.6 kg, VESA 100 (M4) in a 120 × 120 × 8.2 mm pocket, about 31.4 mm behind the screen face. Internal PSU. Exact envelope in the research JSON. | ASUS ProArt **PA278CFRV** (about $190–330; 44.9 mm deep, 4.9 kg). The shroud is regenerated from a monitor profile. |
| Dock electronics | Plugable **UD-6950PDH** DisplayLink dock, about $180: any USB-C laptop including base M1/M2. 225 × 85 × 24.5 mm, 100 W to the laptop, external 130 W brick. | Plugable **TBT-6950PD**, about $300: Thunderbolt 4/USB4 laptops get native, uncompressed video with DisplayLink fallback. |
| Cradle plug | Newnex USB4 cable `U4T1C01CR5P010`. One side-exit right-angle head is the cradle plug; the other end goes to the dock. Never a male-to-female extension. | Plugable `TBT4-240W-80CMR` |
| Plug carriage springs | 4× McMaster `9657K614` (check in a browser before buying). Flat, smooth seat on the carriage. | 316 SS `8969T119`, or a printed PETG flexure carriage |
| Keyboard | Keychron **K3 Ultra 8K** (75 %, low profile, multi-device), 320.6 × 126 mm, 20/25.5 mm tall, plus a NILLKIN **Magic Tag Type-C Short** Qi receiver that sits under it | ZAGG Pro Keyboard 12 (native wireless charging) |
| Mouse | Lenovo **Multi-Device Wireless Mouse (X9 Edition)** `4Y51R29290`, native Qi, 59 × 101 × 34 mm, about $52 | Razer Cobra HyperSpeed + Razer Wireless Charging Puck |
| Qi transmitters (×2) | Anker **313 Wireless Charger (Pad)** `A2503`, fitted intact in printed cradles under each pocket. 100 × 100 × 11.2 mm, micro-USB 5 V/2 A. | Adafruit 2162 bare module |
| Power | Tripp Lite **PS2406RA08B** (6 right-angle outlets, 609.6 × 40.9 × 31.8 mm) inside the base. Right-angle C13 cords for the monitors. **GaN charger** for the low-voltage loads (pick and port-plan it per "Electrical" below). | Tripp Lite PS2404RA06B |
| Light | SuperLightingLED 12 V **1800 K slim COB** (3 mm), **QSG-0505** 5 × 5 mm channels with opal diffuser, **CONSC-DIM-03** knob dimmer | Super Bright LEDs 2200 K COB; RF remote dimmer |
| Seated light | **IR break-beam** across the slot (Adafruit 2167) switching the dock LED. No mechanical switch, no splice into the USB-C path. | Hall sensor + magnet on the carriage (Adafruit 158) |
| Structure | Custom laser-cut A36 steel from **SendCutSend**: 1/4" spine/ballast plate, 3/16" **wing bracket with bent return flanges** (the flat bracket was too flexible fore-aft), 1/4" front bar. We supply the DXF/STEP. Plus 2× ZYLtech 2040 posts, 2× 2020 × 1200 rails, M5 hammer nuts. | VIVO `MOUNT-VW02A` dual VESA adapter + Everbilt 0750 flat bar (no custom fabrication) |
| Hardware | ruthex heat-set insert kit (M3 5.7, M4 8.1, M5 9.5), ISO 7380 / 4762 screws, 6 × 3 mm N52 magnets, 3M Bumpon SJ5023, 3M VHB 5952, Panduit PLT1M-C0 + ABMM-AT-C0 | CNC Kitchen inserts |
| Filament (Bambu) | **PETG Basic Gray 30107** for titanium parts (filler primer, then Rust-Oleum 245220 Titanium Silver) or PETG Basic Dark Beige unpainted. **PETG-CF Titan Gray 31101** for graphite parts (needs a hardened nozzle). **PLA Basic Maroon Red 10205** for oxblood accents. **PETG Translucent Clear 32101** for light pipes and diffusers. | PETG Basic Black for graphite; ASA Gray on enclosed printers |
| Desk mat | Optional: Oakywood felt & cork 90 × 30 | any 800 × 300 felt mat |

Every price and part number above comes from the verified research. When a verifier corrected a value, use the corrected one.

## Geometry targets (app axes, mm: +Y up, +Z toward the user, x = 0 at the seam)

- **Display.**
  - Two S60UD housings, each toed in 10° about the vertical axis through the seam.
  - Seam: 16.16 mm of bezels plus about 0.8 mm gap, so **seam ≈ 17 mm**. The metal-look strip is about 4 mm wide and covers the joint.
  - A printed **front frame** wraps the outer bezels, notched for the power-LED nub. A printed **rear shroud** tiles the back with at least 10 mm of air gap and vents.
  - The rear joystick stays reachable through a finger opening or a printed plunger.
  - Ports face down from the rear box: route right-angle plugs and leave the shroud bottom open there.
- **Base.**
  - Height **≤ 50 mm**. The keyboard's keycaps should sit within ±3 mm of the rim when stowed.
  - Depth ≤ 330 mm; width as the layout needs.
  - Split into tiles of 245 mm or less, for example a rear "spine" row and a front "pocket" row, on 2020 rails and the steel parts.
  - Joints: printed alignment keys or dowels, M3 inserts, and screws into rails through T-nuts. No visible screw heads on top or front faces.
  - Bays: power strip (rear, on edge, 30 mm plug zone), GaN charger, dock electronics (with at least 70 mm of cable space behind), LV hub (Wagos, dimmer, regulator), and a cable chase to the neck. Removable bottom hatches over the charging pads and the bays.
- **Pockets.**
  - Keyboard and mouse pockets with **per-device printed locator inserts**, the same idea as the laptop inserts, so each receiver lands over its coil within ±1–2 mm.
  - One Anker pad per pocket, in an adjustable printed carrier (slotted) under a 1.0 mm floor.
  - The K3 Ultra's Magic Tag folds round its left edge. The insert includes a relief for it.
- **Neck.** A printed trapezoid shroud, split as needed, around the 2× 2040 posts and cable chase. It keeps the light bar and the inlaid NIGHT ARRAY lettering.
- **Dock cradle.**
  - The printed cradle on the right wing, split so each piece fits the bed. Oxblood panels are separate prints.
  - The universal slot insert sets the width for laptop thickness plus clearance.
  - The **floating plug carriage** has ±1.5–2 mm self-centring float and is adjustable along the slot (port distance from the hinge end). The insert sets the plug's lateral offset (port height above the laptop's bottom face).
  - The overmold face sits 0.3–0.5 mm below the landing plane, so the laptop rests on the slot floor, never on the plug.
  - The break-beam emitter and receiver sit in the slot walls. Line the pockets with IR-opaque material.
- **Concept features that change in the build** must be listed honestly in `kit/README.md`, for example charge marks that light while a pad is powered rather than breathing.

## Deliverables

```
night-array/kit/
  KIT_SPEC.md            this contract
  README.md              overview: what it is, cost (realistic + budget swaps), time, difficulty, tools, what changed from the concept
  parts.json             BOM source of truth (generated docs come from it)
  BOM.md, bom.csv        generated from parts.json, with a running total
  PRINTING.md            per-part material, colour, orientation, supports, settings, grams, hours; plates; filament totals
  ASSEMBLY.md            numbered steps with renders, tools, time, cautions
  WIRING.md              wiring diagram (wiring/wiring.svg + .png), power budget, port plan, fusing, wire gauges, safety
  METAL.md               ordering the steel from SendCutSend (files, material, bends, finish, quoted cost) + the no-fabrication alternate
  LAPTOP-INSERT.md       how to measure your laptop and generate and test its insert
  print/<filament>/*.stl print-ready meshes (mm, Z-up, flat face down, at the origin), print/print-list.json
  metal/*.dxf, *.step    laser-cut and bend files
  insert/make_insert.py  insert + carriage-setting generator; presets.json; gauge STL
  assembly/steps.json    step id, title, text, parts[], tools[], minutes, cautions[], still
  research/parts-research.json
night-array/cad/         CAD source (refactor into per-subsystem modules), still building everything with one command
night-array/cad/export/  model/ (app assembly GLBs + scene.json), files/ (STEP/STL/drawings) and NEW kit/ (app-facing:
                         parts.json, print-list.json, steps.json, wiring.png, power-budget.json), all packaged into the APK
```

`scene.json` parts gain `kind: printed | purchased | metal | hardware`, plus:

- `bom` (parts.json id) for purchased and hardware parts;
- `print {file, filament, grams, minutes, plate}` for printed parts.

Groups may be added: `structure` (metal + rails + posts) and `electronics` (strip, charger, dock box, pads, LV hub). The `internals` group becomes those two.

The assembly in `station.glb` **is the buildable design** in the stow pose, keeping the concept's look. The app's renderer and Files tab show what you will actually build.
