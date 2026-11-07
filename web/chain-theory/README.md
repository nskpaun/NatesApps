# Chain Theory Explorer (web)

A browser port of the Chain Theory Android app: the same explainers, refresher, compendium map, quizzes, flashcards, α calculator, library, PDF pages, and full-text search. Progress stays in this browser (`localStorage`). Nothing here calls a third-party API.

Content and PDFs are copied at build time from `chain-theory/android/app/src/main/assets`, so this site and the Android app stay on the same text.

```bash
cd web/chain-theory
npm install
npm test
npm run build
npm run dev      # http://localhost:5173
```

`npm run build` needs Node.js 20 or newer. It does not need environment variables. The original PDFs are copyright their author and are bundled for personal reading, the same way the Android app bundles them.

## Deploy this site on Vercel

Create one Vercel project for this repository and set:

| Setting | Value |
| --- | --- |
| Root directory | `web/chain-theory` |
| Framework preset | Vite |
| Install command | `npm install` |
| Build command | `npm run build` |
| Output directory | `dist` |
| Node.js version | 22.x |

Environment variables: none.

The root directory has to be `web/chain-theory` inside this repository. The build reaches up to `chain-theory/android/app/src/main/assets` for the guide, the extracted text, and the PDFs. `vercel.json` in this folder sets the install command, build command, output directory, and the rewrite that sends client routes such as `/reader/comp/46` to `index.html`.
