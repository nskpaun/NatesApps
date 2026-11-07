# Night Array: Work & Stow (web)

A browser port of the Night Array concept explorer: Explore, Studio, Files, Specs and Buy. The live view is the same three.js CAD renderer the Android app embeds. Browser controls replace the Android bridge. Nothing on this site controls a desk or any other device.

CAD files, stills, the concept board and `kit/parts.json` are copied at build time from `night-array/`, so the site and the app stay on the same model, drawings and recorded prices.

```bash
cd web/night-array
npm install
npm test
npm run build
npm run dev      # http://localhost:5173
```

`npm run build` needs Node.js 22 or newer. It does not need environment variables.

## Deploy this site on Vercel

Create one Vercel project for this repository and set:

| Setting | Value |
| --- | --- |
| Root directory | `web/night-array` |
| Framework preset | Vite |
| Install command | `npm install` |
| Build command | `npm run build` |
| Output directory | `dist` |
| Node.js version | 22.x |

Environment variables: none.

The build reaches up to `night-array/cad/export`, `night-array/kit/parts.json` and `night-array/android/app/src/main/assets` for the model, engineering files, stills and the viewer bundle. `vercel.json` sets the install command, build command, output directory, and the rewrite that sends client routes such as `/studio` and `/specs/buy` to `index.html`. Existing files (GLB, STEP, STL, SVG, DXF, JPEG) are served as themselves.

Prices on Buy are the recorded `unit_usd` values from `kit/parts.json` (checked 2026-11-07), not a live quote. Each part link is the `buy_url` stored with that part.
