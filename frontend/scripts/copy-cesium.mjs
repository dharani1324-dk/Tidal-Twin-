// Copies Cesium's runtime static assets (Workers/Assets/ThirdParty/Widgets)
// into the Vite public folder so the browser can fetch them from /cesium/.
import { cpSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const src = join(root, 'node_modules', 'cesium', 'Build', 'Cesium')
const dest = join(root, 'public', 'cesium')

for (const folder of ['Assets', 'ThirdParty', 'Workers', 'Widgets']) {
  const from = join(src, folder)
  if (!existsSync(from)) throw new Error(`Missing Cesium build folder: ${from}`)
  cpSync(from, join(dest, folder), { recursive: true })
}

console.log('Cesium runtime assets copied to frontend/public/cesium')