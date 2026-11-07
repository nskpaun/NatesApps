import { cpSync, mkdirSync, rmSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const site = resolve(here, '..')
const assets = resolve(here, '../../../chain-theory/android/app/src/main/assets')
const dest = resolve(site, 'public/data')
const files = ['content.json', 'talk.json', 'alpha.json', 'comp.json', 'talk.pdf', 'alpha.pdf', 'comp.pdf']

rmSync(dest, { recursive: true, force: true })
mkdirSync(dest, { recursive: true })
for (const file of files) cpSync(resolve(assets, file), resolve(dest, file))
console.log(`copied ${files.length} Chain Theory assets → public/data`)
