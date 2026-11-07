# Night Array kit: shopping list

Generated from [`parts.json`](parts.json) by `tools/make_bom.py`. Prices are typical US street prices checked on 2026-11-07 and move often. Every primary pick was independently verified; sources are in [`research/parts-research.json`](research/parts-research.json).

| | Total |
|---|---|
| **Core build, primary picks** | **$1,730.46** |
| Core build with every budget swap below | $1,312.95 |
| Optional (desk mat) | $77.00 |
| Filament (not in the budget) | $196.90 |

The laptop, the printer and filament are not included. The monitors are most of the cost, and Samsung and ASUS run frequent sales, so watch for deals before you buy (Black Friday is 2026-11-27).

## Display

| Part | Qty | Unit | Line | What it does |
|---|---:|---:|---:|---|
| [Samsung ViewFinity S6 S60UD 27" QHD IPS, 100 Hz, USB-C 90 W](https://www.samsung.com/us/business/computing/monitors/uhd-and-wqhd/27-viewfinity-s6-s60d-qhd-hdr10-high-resolution-monitor-with-usb-c-and-daisy-chain-ls27d606uanxgo/)<br>`LS27D606UANXGO` | 2 | $349.99 | $699.98 | The two screens (identical pair; buy both from one retailer, same batch). $369.99 list at samsung.com/us; ~$300-330 on sale |

## Dock

| Part | Qty | Unit | Line | What it does |
|---|---:|---:|---:|---|
| [Plugable UD-6950PDH USB-C dual 4K DisplayLink dock (100 W charging)](https://plugable.com/products/ud-6950pdh)<br>`UD-6950PDH` | 1 | $179.95 | $179.95 | Drives both screens + charges the laptop from one USB-C |
| [Newnex USB4 cable, C-male straight to C-male 90-degree side-exit, 1 m, 240 W](https://www.newnex.com/)<br>`U4T1C01CR5P010` | 1 | $64.99 | $64.99 | The sprung USB-C plug in the cradle (one end of the dock's host cable; never a male-to-female extension) |
| [McMaster-Carr compression spring, music wire, 0.375 in long](https://www.mcmaster.com/9657K614/)<br>`9657K614` | 1 | $10.00 | $10.00 | Self-centring float for the plug carriage (4 used). pack; McMaster pages could not be checked automatically, confirm specs in a browser before ordering |

## Keyboard & mouse

| Part | Qty | Unit | Line | What it does |
|---|---:|---:|---:|---|
| [Keychron K3 Ultra 8K wireless mechanical keyboard](https://www.keychron.com/)<br>`K3U-H3 (or other switch options)` | 1 | $109.99 | $109.99 | 75% low-profile wireless keyboard (Bluetooth x3 + 2.4 GHz + USB-C) |
| [NILLKIN Magic Tag wireless charging receiver, Type-C (Short)](https://www.nillkin.com/)<br>`Magic Tag Type-C Short (6902048139886)` | 1 | $29.99 | $29.99 | Makes the keyboard charge wirelessly: thin Qi receiver plugged into its USB-C port, folded flat underneath |
| [Lenovo Multi-Device Wireless Mouse (X9 Edition)](https://www.cdw.com/)<br>`4Y51R29290` | 1 | $51.99 | $51.99 | Wireless mouse that charges natively on a Qi pad. $58.99 list |
| [Anker 313 Wireless Charger (Pad)](https://www.anker.com/products/a2503)<br>`A2503` | 2 | $23.99 | $47.98 | Wireless chargers fitted intact under the keyboard and mouse pockets |
| [Oakywood Felt & Cork Desk Mat 90 x 30, Anthracite](https://oakywood.shop/)<br>`1501FEAL` *(optional)* | 1 | $77.00 | $77.00 | Felt mat for work mode (optional) |

## Power

| Part | Qty | Unit | Line | What it does |
|---|---:|---:|---:|---|
| [Tripp Lite by Eaton 6-outlet power strip, right-angle outlets, 24 in, 8 ft cord](https://tripplite.eaton.com/)<br>`PS2406RA08B` | 1 | $33.00 | $33.00 | The only mains connection: lives inside the base, one cord to the wall |
| [Tripp Lite heavy-duty cord, right-angle NEMA 5-15P to C13, 2 ft](https://tripplite.eaton.com/)<br>`P007-002-15D` | 2 | $10.00 | $20.00 | Right-angle mains cords from the strip to each monitor (confirm the monitor inlet is C14 on arrival) |
| [Monoprice 100 W USB-C 4-port GaN desktop charger](https://www.monoprice.com/)<br>`46820` | 1 | $59.99 | $59.99 | Powers the low-voltage loads (charging pads, amber lights, sensors) |
| [Adafruit USB-C PD to 5.5/2.1 mm barrel adapter, 12 V](https://www.adafruit.com/product/6032)<br>`Adafruit 6032 (12V)` | 1 | $2.25 | $2.25 | USB-C PD trigger: 12 V for the amber lighting bus |

## Light

| Part | Qty | Unit | Line | What it does |
|---|---:|---:|---:|---|
| [SuperLightingLED 12 V super-slim amber 1800 K COB tape, 3 mm](https://www.superlightingled.com/)<br>`FSL-COB-1800K-SLIM (3 mm)` | 1 | $15.98 | $15.98 | Amber light: base under-glow, neck light bar, dock seated light |
| [SuperLightingLED ultra-slim recessed channel for 3 mm strip](https://www.superlightingled.com/)<br>`QSG-0505` | 2 | $4.98 | $9.96 | 5 x 5 mm aluminium channel with opal diffuser (2 x 1 m) |
| [SuperLightingLED rotary knob dimmer, DC connector](https://www.superlightingled.com/)<br>`CONSC-DIM-03` | 1 | $6.99 | $6.99 | One knob dims every amber light |
| [Adafruit IR break-beam sensor, 3 mm LEDs](https://www.adafruit.com/product/2167)<br>`Adafruit 2167` | 1 | $2.95 | $2.95 | Lights the dock's seated light with no switch: an IR beam across the slot is broken by the laptop |
| [Pololu 5 V 600 mA step-down regulator](https://www.pololu.com/product/3792)<br>`D36V6F5 (Pololu 3792)` | 1 | $6.95 | $6.95 | 5 V logic rail for the sensor |
| [Lite-On LTV-815 optocoupler, DIP-4](https://www.lcsc.com/)<br>`LTV-815` | 3 | $0.25 | $0.75 | Switches the seated light from the sensor (photo-Darlington opto) |
| [WAGO 221-412/413/415 + JST-SM 2-pin pairs + 2.1 mm jack-to-terminal](https://www.digikey.com/)<br>`221-41x, SMP-02V-BC/SMR-02V-B, Adafruit 368` | 1 | $18.00 | $18.00 | Low-voltage wiring: lever splices, disconnects at base-tile joints, jack-to-terminal |

## Structure

| Part | Qty | Unit | Line | What it does |
|---|---:|---:|---:|---|
| [Custom laser-cut + bent A36 steel from SendCutSend](https://sendcutsend.com/)<br>`NA-SPINE / NA-WING / NA-FRONTBAR` | 1 | $140.00 | $140.00 | Load path: spine/ballast plate (1/4"), monitor wing bracket with folded flanges (3/16"), front ballast bar (1/4"). estimate; instant quote needs our DXF upload (DXF export is part of the remaining CAD work). Optional powder coat ~$40. |
| [ZYLtech 2040 T-slot aluminium extrusion, 400 mm](https://www.zyltech.com/)<br>`EXT-2040-REG-400` | 2 | $10.14 | $20.28 | Neck posts (2 side by side inside the printed neck) |
| [ZYLtech 2020 T-slot aluminium extrusion, 1200 mm](https://www.zyltech.com/)<br>`EXT-2020-REG-1200` | 2 | $15.54 | $31.08 | Stiffening rails under the printed base tiles |
| [ZYLtech M5 hammer nuts for 2020](https://www.zyltech.com/)<br>`HW-M5-HAMMER-100PK` | 1 | $9.95 | $9.95 | M5 hammer nuts for the rails and posts (100 pack) |

## Hardware

| Part | Qty | Unit | Line | What it does |
|---|---:|---:|---:|---|
| [ruthex threaded insert assortment (M2/M3/M4/M5)](https://www.ruthex.de/)<br>`GE-KASTEN-001` | 1 | $33.00 | $33.00 | Brass heat-set inserts for every screwed printed joint |
| Metric socket/button-head screw kit (black oxide or A2)<br>`generic` | 1 | $25.00 | $25.00 | Screws: ISO 7380 M3/M4/M5 button heads, M6x20 8.8 post bolts, M4x22 VESA screws, washers |
| [K&J Magnetics 1/4 x 1/8 in N52 disc](https://www.kjmagnetics.com/)<br>`D42-N52` | 24 | $0.52 | $12.48 | Hold removable covers and hatches (keep 30 mm from the charging pads) |
| 3M Bumpon SJ5023, black (sheet of 36)<br>`SJ5023` | 1 | $6.00 | $6.00 | Non-slip feet under the spine plate and rail ends |
| 3M VHB 5952 + 3M urethane foam tape 4026<br>`5952 + 4026` | 1 | $20.00 | $20.00 | VHB for the seam strip, light pipes and inlays; foam pads for monitor tolerances |
| Panduit PLT1M-C0 ties + ABMM-AT-C0 adhesive mounts<br>`PLT1M-C0 + ABMM-AT-C0` | 1 | $15.00 | $15.00 | Cable management |

## Finishing

| Part | Qty | Unit | Line | What it does |
|---|---:|---:|---:|---|
| [Rust-Oleum Automotive filler primer, flat gray, 12 oz](https://www.homedepot.com/)<br>`249279` | 3 | $9.00 | $27.00 | Filler primer for the titanium-look parts |
| [Rust-Oleum Universal All Surface Metallic, Titanium Silver, 11 oz](https://www.homedepot.com/)<br>`245220` | 2 | $9.49 | $18.98 | Titanium-look topcoat |

## Filament (not in budget)

| Part | Qty | Unit | Line | What it does |
|---|---:|---:|---:|---|
| [Bambu Lab PETG Basic, Gray (refill 1 kg)](https://us.store.bambulab.com/)<br>`30107` | 5 | $13.99 | $69.95 | Titanium parts: base shell tiles, cradle, neck, front frame (painted) |
| [Bambu Lab PETG-CF, Titan Gray (refill 1 kg)](https://us.store.bambulab.com/)<br>`31101` | 3 | $31.99 | $95.97 | Graphite parts: rear shroud, deck, pocket inserts (needs a hardened nozzle) |
| [Bambu Lab PLA Basic, Maroon Red](https://us.store.bambulab.com/)<br>`10205` | 1 | $14.99 | $14.99 | Oxblood accent panels on the dock |
| [Bambu Lab PETG Translucent, Clear](https://us.store.bambulab.com/)<br>`32101` | 1 | $15.99 | $15.99 | Light pipes and diffusers |

## Budget swaps and upgrades

| Instead of | Use | Unit | Saves / costs per unit | Note |
|---|---|---:|---:|---|
| Samsung ViewFinity S6 S60UD 27" QHD IPS, 100 Hz, USB-C 90 W | ASUS ProArt PA278CFRV 27" QHD 100 Hz (`PA278CFRV`) | $229.00 | −$120.99 | swap: $190-330 depending on deals; 44.9 mm deep and 4.9 kg, so the shroud is regenerated for it |
| Plugable UD-6950PDH USB-C dual 4K DisplayLink dock (100 W charging) | Plugable TBT-6950PD Thunderbolt 4 + DisplayLink dock (`TBT-6950PD`) | $299.99 | +$120.04 | upgrade: Thunderbolt 4/USB4 laptops get native, uncompressed video; DisplayLink fallback for base M1/M2 |
| Newnex USB4 cable, C-male straight to C-male 90-degree side-exit, 1 m, 240 W | Plugable Thunderbolt 4 cable, right-angle, 0.8 m, 240 W (`TBT4-240W-80CMR`) | $34.95 | −$30.04 | swap |
| Keychron K3 Ultra 8K wireless mechanical keyboard | ZAGG Pro Keyboard 12 (charges wirelessly by itself, no receiver needed) (`103210887`) | $69.99 | −$40.00 | swap: also drop the NILLKIN receiver |
| NILLKIN Magic Tag wireless charging receiver, Type-C (Short) | not needed with the ZAGG keyboard (`-`) | $0.00 | −$29.99 | swap |
| Lenovo Multi-Device Wireless Mouse (X9 Edition) | Razer Cobra HyperSpeed + Razer Wireless Charging Puck (`RZ01-05570100-R3U1 + RC21-01990200-R3U1`) | $129.98 | +$77.99 | upgrade: puck often out of stock |
| Oakywood Felt & Cork Desk Mat 90 x 30, Anthracite | any 800 x 300 mm felt desk mat (`-`) | $20.00 | −$57.00 | swap |
| Custom laser-cut + bent A36 steel from SendCutSend | VIVO MOUNT-VW02A dual VESA adapter + Everbilt 0750 1/4 x 1-1/2 in flat steel bar (`MOUNT-VW02A + Everbilt 0750`) | $76.50 | −$63.50 | swap: no custom fabrication; less precise toe-in |
| ruthex threaded insert assortment (M2/M3/M4/M5) | CNC Kitchen M3x5.7 (100) + M4x8.1 (50) (`TC-M3x5.7 + TC-M4x8.1`) | $21.00 | −$12.00 | swap |
| Bambu Lab PETG-CF, Titan Gray (refill 1 kg) | Bambu Lab PETG Basic, Black (`30105`) | $13.99 | −$18.00 | swap |
