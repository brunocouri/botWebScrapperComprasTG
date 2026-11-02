// Integração do EXE distribuído usando CDP, sem Playwright ou Telegram real.
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import net from 'node:net'
import { spawn, spawnSync } from 'node:child_process'
import { once } from 'node:events'

const exe = path.resolve(process.argv[2] || '../artifacts/windows/win-unpacked/ComprasTG.exe')
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'comprastg-packaged-'))
const defaultData = process.argv.includes('--default-data')
const data = defaultData ? path.join(temp, 'profile', 'data') : path.join(temp, 'dados com espaços')
fs.mkdirSync(data, { recursive: true })
fs.writeFileSync(path.join(data, 'keywords.json'), '["A57"]')
fs.writeFileSync(path.join(data, 'watched_groups.json'), '[{"id":-100123,"name":"Grupo fictício","selected":true}]')
const env = { ...process.env, PATH: path.join(process.env.SystemRoot || 'C:\\Windows', 'System32'),
  COMPRAS_DATA_DIR: data, COMPRAS_SMOKE: '1', PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' }
delete env.ELECTRON_RUN_AS_NODE
delete env.PYTHONHOME
delete env.PYTHONPATH
if (defaultData) delete env.COMPRAS_DATA_DIR
const server = net.createServer()
server.listen(0, '127.0.0.1')
await once(server, 'listening')
const port = server.address().port
await new Promise(resolve => server.close(resolve))
const child = spawn(exe, [`--remote-debugging-port=${port}`, `--user-data-dir=${path.join(temp, 'profile')}`],
  { env, windowsHide: true, cwd: temp, stdio: ['ignore', 'ignore', 'pipe'] })
let log = '', closed = false, spawnError
child.stderr.on('data', chunk => { log = (log + chunk).slice(-8000) })
child.on('error', error => { spawnError = error })
const exited = new Promise(resolve => child.once('close', code => { closed = true; resolve(code) }))
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
const sockets = []
async function cdp(url) {
  const socket = new WebSocket(url)
  sockets.push(socket)
  await once(socket, 'open')
  let sequence = 0
  const pending = new Map()
  socket.addEventListener('close', () => {
    for (const request of pending.values()) {
      clearTimeout(request.timer)
      request.reject(new Error('CDP encerrado.'))
    }
    pending.clear()
  })
  socket.addEventListener('message', ({ data }) => {
    const value = JSON.parse(data)
    const request = pending.get(value.id)
    if (!request) return
    pending.delete(value.id)
    clearTimeout(request.timer)
    if (value.error) request.reject(new Error(value.error.message))
    else request.resolve(value.result)
  })
  return (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)) }, 20000)
    pending.set(id, { resolve, reject, timer })
    socket.send(JSON.stringify({ id, method, params }))
  })
}

try {
  let page
  for (let n = 0; n < 100; n++) {
    if (spawnError) throw spawnError
    if (closed) throw new Error(`EXE encerrou antes do renderer: ${log}`)
    try {
      const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()
      page = pages.find(page => page.type === 'page' && page.url.startsWith('file:'))
      if (page) break
    } catch { /* aguardar servidor CDP local */ }
    await delay(200)
  }
  if (!page) throw new Error('Renderer empacotado não abriu.')
  const call = await cdp(page.webSocketDebuggerUrl)
  const evaluate = async expression => {
    const result = await call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text)
    return result.result.value
  }
  for (let n = 0; n < 100; n++) {
    if (await evaluate('Boolean(window.api && document.querySelector("h1"))')) break
    await delay(100)
  }
  const basic = await evaluate(`(async()=>{
    const groups=await window.api.listGroups(), rules=await window.api.getKeywords()
    const config=await window.api.getConfig()
    const result=await window.api.simulate('A57 R$ 1.899',rules.rules)
    const sources=await window.api.catalog({action:'sources'})
    return {groups:groups.groups.length,winner:result.winner?.keyword,apiHashSet:config.apiHashSet,
      source:sources.some(s=>s.id===-100123&&s.enabled===1),heading:document.querySelector('h1').textContent}
  })()`)
  if (basic.groups !== 1 || basic.winner !== 'A57' || basic.apiHashSet || !basic.source || basic.heading !== 'Grupos') {
    throw new Error('Configuração/simulador: ' + JSON.stringify(basic))
  }
  const backend = path.join(path.dirname(exe), 'resources', 'backend')
  const python = path.join(backend, 'python.exe')
  const fixture = spawnSync(python, ['-c', `import os; from pathlib import Path; from catalog_storage import Catalog,utc\nwith Catalog(Path(os.environ['COMPRAS_DATA_DIR'])/'catalog.db') as db:\n db.capture(-100123,1,utc(),'Produto: Galaxy A57\\nPix: R$ 1.899,90')`],
    { env: { ...env, COMPRAS_DATA_DIR: data }, cwd: temp, encoding: 'utf8', windowsHide: true })
  if (fixture.status !== 0) throw new Error('Python embutido: ' + fixture.stderr)
  const catalog = await evaluate(`(async()=>{
    const template={id:'smoke',name:'Celular Pix',source_id:-100123,markers:['Produto:','Pix:'],delimiter:'',fields:[
      {field_id:'product',name:'Produto',type:'text',op:'after',marker:'Produto:',required:true},
      {field_id:'pix',name:'Preço Pix',type:'money',op:'after',marker:'Pix:',required:true}]}
    const draft=await window.api.catalog({action:'template:save',template,revision:0})
    await window.api.catalog({action:'template:publish',id:'smoke',revision:draft.revision})
    const preview=await window.api.catalog({action:'reprocess:preview',scope:{source_id:-100123}})
    await window.api.catalog({action:'reprocess:confirm',token:preview.token})
    await window.api.catalog({action:'process'})
    const offers=await window.api.catalog({action:'search',filters:{field_id:'pix',max:190000}})
    await window.api.worker('start')
    await new Promise(resolve=>setTimeout(resolve,700))
    const worker=await window.api.worker('status')
    await window.api.worker('stop')
    return {total:offers.total,cents:offers.items[0]?.payload.values.pix.value,worker}
  })()`)
  if (catalog.total !== 1 || catalog.cents !== 189990 || !catalog.worker.running || catalog.worker.error) {
    throw new Error('Catálogo/worker: ' + JSON.stringify(catalog))
  }
  if (fs.existsSync(path.join(data, 'session.session')) || fs.existsSync(path.join(data, 'seen.db'))) throw new Error('Smoke abriu dados Telegram.')
  const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json()
  const browser = await cdp(version.webSocketDebuggerUrl)
  void browser('Browser.close').catch(() => {})
  const exitCode = await Promise.race([exited, delay(10000).then(() => 'timeout')])
  if (exitCode !== 0) throw new Error('EXE não encerrou normalmente: ' + exitCode)
  console.log('PACKAGED_SMOKE_OK: EXE, renderer, preload, IPC, Python embutido, catálogo e worker; PATH sem Python/Node; sem sessão ou seen.db; dados ' + (defaultData ? 'no perfil padrão.' : 'em diretório explícito.'))
} catch (error) {
  console.error(error.message)
  if (log) console.error(log)
  process.exitCode = 1
} finally {
  if (!closed) {
    try {
      const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json()
      const browser = await cdp(version.webSocketDebuggerUrl)
      void browser('Browser.close').catch(() => {})
      await Promise.race([exited, delay(5000)])
    } catch { /* o processo pode ter encerrado durante a limpeza */ }
  }
  for (const socket of sockets) socket.close()
  if (!closed) { child.kill(); await exited }
  // Somente a pasta temporária criada aqui; validar alvo antes da exclusão recursiva.
  if (path.dirname(path.resolve(temp)) === path.resolve(os.tmpdir()) && path.basename(temp).startsWith('comprastg-packaged-')) {
    try { await fs.promises.rm(temp, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 }) }
    catch (error) {
      console.error('Falha ao limpar pasta temporária: ' + temp + ' (' + error.code + ')')
      process.exitCode = 1
    }
  }
}
