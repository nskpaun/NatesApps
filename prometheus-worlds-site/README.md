# Prometheus Worlds

Marketing site for the local world-building app at [nskpaun/prometheus-worlds](https://github.com/nskpaun/prometheus-worlds).

The page is one screen of the real product: photos or a prompt become a world you can orbit, relight, and drop balls into, on your own Mac. Living scenes with motion and music are marked as coming soon. Screenshots are captures from the app, exported smaller as WebP. The sparks, the slow drift, and the bars on the living-scenes panel are drawn for this page. They are not a picture of a feature in the app.

The New world dialog capture in `local-worlds/docs/new-world.jpg` is not used here. Its detail estimate does not match the current app (Quick about 14 minutes, Standard about 20, Full about 40).

```bash
cd prometheus-worlds-site
npm install
npm run dev      # http://localhost:5173
npm run build
npm run preview
```

`npm run build` needs Node.js 20 or newer. It does not need environment variables.

## Deploy this site on Vercel

Create one Vercel project for this repository and set:

| Setting | Value |
| --- | --- |
| Root directory | `prometheus-worlds-site` |
| Framework preset | Vite |
| Install command | `npm install` |
| Build command | `npm run build` |
| Output directory | `dist` |
| Node.js version | 22.x |

Environment variables: none.

`vercel.json` in this folder sets the install command, build command, output directory, and the Vite framework. The site is a single page, so it does not rewrite routes.
