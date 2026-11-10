"""Build the explorer's data file from scratch: night-array/kit/poc/build/ (assembled meshes + scene.json, written by
pocket_section.py) + print/print-list.json  ->  <out>/parts-<version>.json

    python3 night-array/kit/poc/explorer/make_data.py <out dir> <version>
"""
import base64, json, pathlib, sys

POC = pathlib.Path(__file__).resolve().parents[1]
out_dir, version = pathlib.Path(sys.argv[1]), sys.argv[2]
scene = json.loads((POC / 'build/scene.json').read_text())
plist = {p['file'].split('/')[-1]: p for p in json.loads((POC / 'print/print-list.json').read_text())['parts']}

NAMES = {
    'kb_block': ('Keyboard floor block', 'kb_floor_block.stl', 'Carries the 1.0 mm charging floor under the keyboard. Drops into its tapered seat from below; keep supports off its top face.'),
    'mouse_block': ('Mouse floor block', 'mouse_floor_block.stl', 'Carries the 1.0 mm charging floor under the mouse.'),
    'kb_carrier': ('Keyboard pad carrier', 'pad_carrier.stl', 'Holds the Anker pad on foam so it presses up against the floor. Slides ±15 mm both ways; one M3 screw locks it.'),
    'mouse_carrier': ('Mouse pad carrier', 'pad_carrier.stl', 'Same carrier, under the mouse pocket.'),
    'kb_hatch': ('Keyboard hatch', 'kb_hatch.stl', 'Closes the underside and bridges the front/back seam. Finger window, 5 mm tick scale and a sight slot for the pad light.'),
    'mouse_hatch': ('Mouse hatch', 'mouse_hatch.stl', 'Closes the underside under the mouse pocket.'),
    'kb_pad': ('Anker 313 pad (keyboard)', None, 'Bought part. Qi charger, 100 × 100 × 11.2 mm, micro-USB in.'),
    'mouse_pad': ('Anker 313 pad (mouse)', None, 'Bought part. Qi charger, 100 × 100 × 11.2 mm, micro-USB in.'),
    'kb_plug': ('Micro-USB plug', None, 'The pad cable; runs along the underside groove to the back edge.'),
    'mouse_plug': ('Micro-USB plug', None, 'The pad cable; runs along the underside groove to the back edge.'),
    'kb_foam': ('Foam squares', None, 'Four 20 × 20 mm squares of 3 mm EVA push the pad against the floor.'),
    'mouse_foam': ('Foam squares', None, 'Four 20 × 20 mm squares of 3 mm EVA under the mouse pad.'),
    'keyboard': ('Keychron K3 Ultra', None, 'Bought part. Sits in its pocket with 2.5 mm per side.'),
    'magic_tag': ('NILLKIN Magic Tag', None, 'Bought part. Qi receiver plugged into the keyboard and folded flat underneath.'),
    'mouse': ('Lenovo X9 mouse', None, 'Bought part. Charges natively on the pad below.'),
}
parts = []
for p in scene['parts']:
    pid = p['file'][:-4]
    if pid.startswith('tray_'):
        words = pid.split('_')[1:]
        name = 'Tray, ' + ' '.join(words)
        pf, desc = pid + '.stl', 'One of the six tray pieces. Hollowed from underneath; glued to its neighbours along the seams with printed dowel pins for alignment.'
    else:
        name, pf, desc = NAMES[pid]
    meta = plist.get(pf) if pf else None
    parts.append(dict(id=pid, name=name, desc=desc, color=p['color'], explode=p['explode'], group=p['group'],
                      print=dict(file=pf, qty=meta['qty'], ml=meta['resin_ml_each'], size=meta['size_mm'],
                                 material=meta['material'], orient=meta['orientation']) if meta else None,
                      stl=base64.b64encode((POC / 'build' / p['file']).read_bytes()).decode()))
extra = [p for f, p in plist.items() if f == 'dowel_pin.stl']
data = dict(version=version, bounds=scene['bounds'], parts=parts,
            total_ml=json.loads((POC / 'print/print-list.json').read_text())['total_resin_ml'],
            extra=[dict(name='Dowel pins', qty=e['qty'], ml=e['resin_ml_each']) for e in extra])
out = out_dir / f'parts-{version}.json'
out.write_text(json.dumps(data))
print(out, len(parts), 'parts')
