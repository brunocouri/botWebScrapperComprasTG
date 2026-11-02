import fs from 'node:fs'
import path from 'node:path'
const root = path.resolve('dist-electron')
fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify({ type: 'commonjs' }))
for (const entry of ['main', 'preload']) fs.renameSync(path.join(root, 'electron', entry + '.js'), path.join(root, 'electron', entry + '.cjs'))
