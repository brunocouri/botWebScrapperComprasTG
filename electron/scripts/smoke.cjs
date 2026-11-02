// Integração do build real: renderer -> preload -> IPC -> Python, sem Telegram.
const { app, BrowserWindow } = require('electron')
const { spawnSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'comprastg-smoke-'))
process.env.COMPRAS_DATA_DIR = tempRoot
process.env.COMPRAS_RENDERER_FILE = '1'
process.env.COMPRAS_SMOKE = '1'
fs.writeFileSync(path.join(tempRoot, 'keywords.json'), '["A57"]')
fs.writeFileSync(path.join(tempRoot, 'watched_groups.json'), '[{"id":-100123,"name":"Grupo fictício","selected":true}]')
let finished = false
const timeout = setTimeout(() => finish(1, 'Tempo esgotado no smoke do Electron.'), 45000)
function finish(code, message) {
  if (finished) return
  finished = true
  clearTimeout(timeout)
  process.stdout.write(message + '\n')
  // Alvo absoluto criado por este script, validado dentro de os.tmpdir().
  const resolved = path.resolve(tempRoot)
  if (path.dirname(resolved) === path.resolve(os.tmpdir()) && path.basename(resolved).startsWith('comprastg-smoke-')) fs.rmSync(resolved, { recursive: true, force: true })
  app.exit(code)
}
app.on('web-contents-created', (_event, contents) => {
  contents.once('did-fail-load', () => finish(1, 'Falha ao carregar renderer compilado.'))
  contents.once('did-finish-load', async () => {
    try {
      const result = await contents.executeJavaScript(`(async () => {
        if (!window.api) throw new Error('Preload indisponível')
        const groups = await window.api.listGroups()
        const config = await window.api.getKeywords()
        const simulation = await window.api.simulate('A57 R$ 1.899', config.rules)
        const status = await window.api.getStatus()
        return { groupCount: groups.groups.length, ruleCount: config.rules.length, winner: simulation.winner?.keyword, state: status.state, heading: document.querySelector('h1')?.textContent }
      })()`)
      if (result.groupCount !== 1 || result.ruleCount !== 1 || result.winner !== 'A57' || result.state !== 'stopped' || result.heading !== 'Grupos') throw new Error('Resultado inesperado: ' + JSON.stringify(result))
      const defaults = await contents.executeJavaScript(`window.api.catalog({action:'sources'})`)
      if (!defaults.some(source => source.id === -100123 && source.enabled === 1)) throw new Error('Grupo selecionado não veio com arquivamento padrão.')
      const fixture = spawnSync('python', ['-c', `import os; from pathlib import Path; from catalog_storage import Catalog,utc\nwith Catalog(Path(os.environ['COMPRAS_DATA_DIR'])/'catalog.db') as db:\n db.capture(-100123,1,utc(),'Produto: Galaxy A57\\nPix: R$ 1.899,90\\nCupom: GALAXY100')`], { cwd: path.resolve(__dirname, '../..'), env: { ...process.env, PYTHONUTF8: '1' }, encoding: 'utf8', windowsHide: true })
      if (fixture.status !== 0) throw new Error('Fixture do catálogo falhou: ' + fixture.stderr)
      const catalog = await contents.executeJavaScript(`(async()=>{
        const template={id:'smoke',name:'Celular Pix',source_id:-100123,markers:['Produto:','Pix:'],delimiter:'',fields:[
          {field_id:'product',name:'Produto',type:'text',op:'after',marker:'Produto:',required:true},
          {field_id:'pix',name:'Preço Pix',type:'money',op:'after',marker:'Pix:',required:true}]}
        const draft=await window.api.catalog({action:'template:save',template,revision:0})
        await window.api.catalog({action:'template:publish',id:'smoke',revision:draft.revision})
        const preview=await window.api.catalog({action:'reprocess:preview',scope:{source_id:-100123}})
        await window.api.catalog({action:'reprocess:confirm',token:preview.token})
        await window.api.catalog({action:'process'})
        const search=await window.api.catalog({action:'search',filters:{field_id:'pix',max:190000}})
        await window.api.worker('start')
        await window.api.worker('stop')
        document.querySelector('button[aria-label="Catálogo"]').click()
        return {total:search.total,cents:search.items[0]?.payload.values.pix.value}
      })()`)
      if (catalog.total !== 1 || catalog.cents !== 189990) throw new Error('Catálogo IPC não corresponde à fixture: ' + JSON.stringify(catalog))
      await new Promise(resolve => setTimeout(resolve, 600))
      await contents.executeJavaScript(`Array.from(document.querySelectorAll('.catalog-tabs button')).find(b=>b.textContent==='Ofertas').click()`)
      const qaDir = path.resolve(__dirname, '../../docs/qa')
      fs.mkdirSync(qaDir, { recursive: true })
      const window = BrowserWindow.fromWebContents(contents)
      window.setContentSize(1100, 760)
      await new Promise(resolve => setTimeout(resolve, 200))
      fs.writeFileSync(path.join(qaDir, 'catalog-desktop.png'), (await contents.capturePage()).toPNG())
      window.setContentSize(760, 680)
      await new Promise(resolve => setTimeout(resolve, 200))
      const geometry = await contents.executeJavaScript(`({width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth||document.querySelector('.page').scrollWidth>document.querySelector('.page').clientWidth})`)
      if (geometry.overflow) throw new Error('Catálogo tem overflow horizontal em ' + geometry.width)
      fs.writeFileSync(path.join(qaDir, 'catalog-narrow.png'), (await contents.capturePage()).toPNG())
      const collected = await contents.executeJavaScript(`(async()=>{
        document.querySelector('button[aria-label="Coletados"]').click()
        for(let n=0;n<30;n++) {
          await new Promise(resolve=>setTimeout(resolve,100))
          const archive=document.querySelector('.catalog section[aria-busy]')
          if(document.querySelector('h1')?.textContent==='Coletados' && archive?.textContent.includes('Produto: Galaxy A57')) {
            return {ok:true,first:document.querySelector('nav[aria-label="Principal"] button')?.textContent}
          }
        }
        return {ok:false}
      })()`)
      if (!collected.ok || collected.first !== 'Coletados') throw new Error('Coletados não abriu o acervo salvo ou está fora de ordem.')
      fs.writeFileSync(path.join(qaDir, 'collected-narrow.png'), (await contents.capturePage()).toPNG())
      window.setContentSize(1100, 760)
      await new Promise(resolve => setTimeout(resolve, 200))
      fs.writeFileSync(path.join(qaDir, 'collected-desktop.png'), (await contents.capturePage()).toPNG())
      if (fs.existsSync(path.join(tempRoot, 'session.session')) || fs.existsSync(path.join(tempRoot, 'seen.db'))) throw new Error('Smoke abriu dados operacionais')
      finish(0, 'SMOKE_OK: renderer, preload, IPC, catálogo, Coletados, extração, busca, worker e layout 760px; sem sessão ou seen.db.')
    } catch (error) { finish(1, error.message) }
  })
})
require('../dist-electron/electron/main.cjs')
