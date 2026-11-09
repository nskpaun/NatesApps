"""Assemble the browser version of the Night Array Studio into web/dist/.

    python3 night-array/web/build.py

studio.html is the page body (published through claude.ai Artifacts, which add the <html>/<head> skeleton).
It loads viewer.js directly (no iframe) and fetches model/*.glb, which the page decodes from base64 text
files because the artifact host does not serve .glb. dist/ holds the files to publish beside the page.
"""
import base64, pathlib, shutil

NA = pathlib.Path(__file__).resolve().parents[1]
dist = NA / 'web/dist'
shutil.rmtree(dist, ignore_errors=True)
(dist / 'model').mkdir(parents=True)
shutil.copyfile(NA / 'web/studio.html', dist / 'studio.html')
js = (NA / 'android/app/src/main/assets/viewer/viewer.js').read_text()
assert js.count('"../model/"') == 1, 'viewer.js model base path changed'
(dist / 'viewer.js').write_text(js.replace('"../model/"', '"model/"'))
for n in ('station', 'station-edges'):
    (dist / f'model/{n}.glb.txt').write_text(base64.b64encode((NA / f'cad/export/model/{n}.glb').read_bytes()).decode())
shutil.copyfile(NA / 'cad/export/model/scene.json', dist / 'model/scene.json')
shutil.copyfile(NA / 'kit/parts.json', dist / 'parts.json')
print('built', dist)
