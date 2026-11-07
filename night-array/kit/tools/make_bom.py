"""Generate kit/BOM.md, kit/bom.csv and the app copy (android assets kit/parts.json) from kit/parts.json.

    python3 night-array/kit/tools/make_bom.py
"""
import csv, json, pathlib, shutil

KIT = pathlib.Path(__file__).resolve().parents[1]
APP = KIT.parent / 'android/app/src/main/assets/kit/parts.json'
data = json.loads((KIT / 'parts.json').read_text())
items = data['items']

def line(i, swap=False):
    s = i.get('swap') if swap else None
    unit = s['unit_usd'] if s else i['unit_usd']
    return round(unit * i['qty'], 2)

core = [i for i in items if not i.get('excluded') and not i.get('optional')]
optional = [i for i in items if i.get('optional')]
excluded = [i for i in items if i.get('excluded')]
total = round(sum(line(i) for i in core), 2)
total_swaps = round(sum(line(i, True) for i in core), 2)
filament = round(sum(line(i) for i in excluded), 2)
fmt = lambda v: f"${v:,.2f}"

out = ["# Night Array kit: shopping list", "",
       f"Generated from [`parts.json`](parts.json) by `tools/make_bom.py`. Prices are typical US street prices checked on "
       f"{data['prices_checked']} and move often. Every primary pick was independently verified; sources are in "
       "[`research/parts-research.json`](research/parts-research.json).", "",
       "| | Total |", "|---|---|",
       f"| **Core build, primary picks** | **{fmt(total)}** |",
       f"| Core build with every budget swap below | {fmt(total_swaps)} |",
       f"| Optional (desk mat) | {fmt(sum(line(i) for i in optional))} |",
       f"| Filament (not in the budget) | {fmt(filament)} |", "",
       "The laptop, the printer and filament are not included. The monitors are most of the cost, and Samsung and ASUS run "
       "frequent sales, so watch for deals before you buy (Black Friday is 2026-11-27).", ""]
cats = []
for i in items:
    if i['category'] not in cats: cats.append(i['category'])
for c in cats:
    out += [f"## {c}", "", "| Part | Qty | Unit | Line | What it does |", "|---|---:|---:|---:|---|"]
    for i in [x for x in items if x['category'] == c]:
        name = f"[{i['product']}]({i['buy_url']})" if i.get('buy_url') else i['product']
        tag = ' *(optional)*' if i.get('optional') else ''
        out.append(f"| {name}<br>`{i['mpn']}`{tag} | {i['qty']} | {fmt(i['unit_usd'])} | {fmt(line(i))} | {i['role']}"
                   + (f". {i['price_note']}" if i.get('price_note') else '') + " |")
    out.append("")
out += ["## Budget swaps and upgrades", "",
        "| Instead of | Use | Unit | Saves / costs per unit | Note |", "|---|---|---:|---:|---|"]
for i in items:
    for key, label in (('swap', 'swap'), ('upgrade', 'upgrade')):
        s = i.get(key)
        if s:
            d = s['unit_usd'] - i['unit_usd']
            out.append(f"| {i['product']} | {s['product']} (`{s['mpn']}`) | {fmt(s['unit_usd'])} | "
                       f"{'+' if d > 0 else '−'}{fmt(abs(d))} | {label}{': ' + s['note'] if s.get('note') else ''} |")
out.append("")
(KIT / 'BOM.md').write_text('\n'.join(out))
with open(KIT / 'bom.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['id', 'category', 'product', 'mpn', 'qty', 'unit_usd', 'line_usd', 'optional', 'excluded_from_budget', 'role', 'buy_url'])
    for i in items:
        w.writerow([i['id'], i['category'], i['product'], i['mpn'], i['qty'], i['unit_usd'], line(i),
                    bool(i.get('optional')), bool(i.get('excluded')), i['role'], i.get('buy_url', '')])
APP.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(KIT / 'parts.json', APP)
print(f"core {fmt(total)} | with swaps {fmt(total_swaps)} | filament {fmt(filament)} | {len(items)} items")
