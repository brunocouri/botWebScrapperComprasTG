import { app, BrowserWindow, ipcMain, shell, dialog } from 'electron'
import { spawn } from 'node:child_process'
import path from 'node:path'
import fs from 'node:fs'
import { pathToFileURL } from 'node:url'
import { stripAnsi } from '../src/lib/activity'
import { LineDecoder, parseBotEvent } from '../src/lib/protocol'
import { ProcessController, type Operation } from '../src/lib/process'
import { runtimePaths } from '../src/lib/runtime-paths'
import type { BotEvent, RuntimeStatus, Rule, WatchedGroup } from '../src/lib/ipc'

const runtime = runtimePaths({ packaged: app.isPackaged, resources: process.resourcesPath,
  source: path.resolve(__dirname, '../../..'), userData: app.getPath('userData'), data: process.env.COMPRAS_DATA_DIR })
const BACKEND_DIR = runtime.backend
const PYTHON = runtime.python
const FILE_RENDERER = app.isPackaged || process.env.COMPRAS_RENDERER_FILE === '1'
const DATA_DIR = runtime.data
const RENDERER = path.resolve(__dirname, '../../dist/index.html')
let win: BrowserWindow | null = null
let quitting = false
let dirty = false
let authInputExpected = false
let status: RuntimeStatus = { state: 'stopped', busy: false, snapshot: null, error: null }
const send = (channel: string, data?: unknown) => { if (win && !win.isDestroyed()) win.webContents.send(channel, data) }
function update(patch: Partial<RuntimeStatus>) {
  status = { ...status, ...patch, busy: controller.busy }
  send('bot:status', status)
}
function onEvent(event: BotEvent) {
  send('bot:event', { kind: 'event', event })
  switch (event.type) {
    case 'telegram_connecting': update({ state: 'connecting' }); break
    case 'telegram_syncing': update({ state: 'synchronizing' }); break
    case 'monitoring_started': update({ state: 'monitoring', snapshot: event.snapshot ?? null, error: null }); break
    case 'connection_state': update({ state: event.connected ? 'monitoring' : 'reconnecting' }); break
    case 'auth_step':
      authInputExpected = event.step === 'code' || event.step === 'password'
      update({ state: event.step === 'authorized' ? 'stopped' : 'authenticating' }); break
    case 'error':
      if (event.code !== 'catalog_failed') update({ state: event.code === 'auth_required' ? 'auth_required' : 'error', error: event.message })
      break
    case 'operation_completed': controller.completed = true; break
  }
}
const controller = new ProcessController((operation: Operation) => {
  const args = ['bot.py', operation === 'watch' ? '--watch' : operation === 'list' ? '--list-groups' : '--authenticate', '--desktop']
  const child = spawn(PYTHON, args, { cwd: BACKEND_DIR, windowsHide: true,
    env: { ...process.env, COMPRAS_DATA_DIR: DATA_DIR, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' } })
  const failure = (message: string) => onEvent({ type: 'error', code: 'protocol_invalid', message })
  const stdout = new LineDecoder(line => {
    try {
      const event = parseBotEvent(JSON.parse(line))
      if (event) onEvent(event)
      else failure('Evento inválido recebido do Python.')
    } catch { failure('JSON inválido recebido do Python.') }
  }, failure)
  const stderr = new LineDecoder(line => send('bot:event', { kind: 'raw', line: stripAnsi(line) }), failure)
  child.stdout.on('data', chunk => stdout.write(chunk))
  child.stderr.on('data', chunk => stderr.write(chunk))
  child.stdin.on('error', () => { /* close/error do processo resolve o lifecycle */ })
  child.once('close', () => { stdout.end(); stderr.end() })
  return child
}, (kind, info) => {
  if (kind === 'crashed') {
    if (status.state !== 'auth_required') update({ state: 'error', error: status.error || 'O processo terminou inesperadamente. Verifique os diagnósticos.' })
    else update({})
    send('bot:crashed', info)
  } else {
    update({ state: 'stopped', error: null })
    send('bot:stopped')
  }
})

function config<T>(payload: Record<string, unknown>): Promise<T> {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON, ['config_cli.py'], { cwd: BACKEND_DIR, windowsHide: true,
      env: { ...process.env, COMPRAS_DATA_DIR: DATA_DIR, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' } })
    let output = '', size = 0, settled = false
    const fail = (message: string) => { if (!settled) { settled = true; reject(new Error(message)) } }
    const timer = setTimeout(() => { child.kill(); fail('Tempo esgotado ao acessar configuração. Tente novamente.') }, 15000)
    child.stdout.setEncoding('utf8')
    child.stdout.on('data', chunk => {
      size += chunk.length
      if (size > 2_000_000) { child.kill(); fail('Resposta de configuração excedeu o limite.') }
      else output += chunk
    })
    child.stderr.resume() // nunca reenviar entrada/segredos em exceções de SDK
    child.stdin.on('error', () => {})
    child.once('error', () => { clearTimeout(timer); fail(app.isPackaged
      ? 'Runtime do aplicativo indisponível. Extraia o ZIP completo ou reinstale o ComprasTG.'
      : 'Python não disponível. Instale as dependências e confira o PATH.') })
    child.once('close', code => {
      clearTimeout(timer)
      if (settled) return
      try {
        const value = JSON.parse(output)
        if (code !== 0 || value.error) fail(typeof value.error === 'string' ? value.error : 'Falha ao acessar configuração.')
        else { settled = true; resolve(value as T) }
      } catch { fail('Resposta inválida da configuração.') }
    })
    child.stdin.end(JSON.stringify(payload))
  })
}

let workerError: string | null = null
const workerController = new ProcessController(() => {
  const child = spawn(PYTHON, ['etl_worker.py', '--desktop'], { cwd: BACKEND_DIR, windowsHide: true,
    env: { ...process.env, COMPRAS_DATA_DIR: DATA_DIR, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' } })
  const decoder = new LineDecoder(line => {
    try {
      const value: unknown = JSON.parse(line)
      if (value && typeof value === 'object' && 'state' in value) {
        workerError = 'error' in value && typeof value.error === 'string' ? value.error : null
      } else workerError = 'Resposta inválida do worker.'
    } catch { workerError = 'Resposta inválida do worker.' }
  }, message => { workerError = message })
  child.stdout.on('data', chunk => decoder.write(chunk))
  child.stderr.resume()
  child.stdin.on('error', () => {})
  child.once('close', () => decoder.end())
  return child
}, kind => { if (kind === 'crashed') workerError ||= 'Worker encerrado inesperadamente. Reinicie para retomar a fila.' })

function handle<A extends unknown[]>(channel: string, fn: (...args: A) => unknown) {
  ipcMain.handle(channel, (event, ...args: A) => {
    const url = event.senderFrame?.url || ''
    const allowed = FILE_RENDERER ? url === pathToFileURL(RENDERER).href : new URL(url).origin === 'http://localhost:5173'
    if (!win || event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame || !allowed) throw new Error('Origem IPC não permitida.')
    return fn(...args)
  })
}
function begin(operation: Operation) {
  if (!controller.start(operation)) return { ok: false, error: 'Aguarde a operação atual encerrar.' }
  update({ state: operation === 'authenticate' ? 'authenticating' : 'starting', error: null, snapshot: operation === 'watch' ? null : status.snapshot })
  return { ok: true }
}
handle('groups:list', () => config({ operation: 'groups:get' }))
handle('groups:save', (groups: WatchedGroup[], revision: string) => config({ operation: 'groups:save', groups, revision }))
handle('groups:reload', async () => {
  const started = begin('list')
  if (!started.ok) throw new Error(started.error)
  const info = await controller.wait()
  if (info.code !== 0 || status.state === 'error' || status.state === 'auth_required') throw new Error(status.error || 'Não foi possível atualizar grupos.')
  return { ok: true, out: '' }
})
handle('keywords:get', () => config({ operation: 'rules:get' }))
handle('keywords:save', (rules: Rule[], revision: string) => config({ operation: 'rules:save', rules, revision }))
handle('keywords:add', (term: string, revision: string) => config({ operation: 'rules:add', term, revision }))
handle('config:get', () => config({ operation: 'config:get' }))
handle('config:save', (payload: unknown, revision: string) => config({ operation: 'config:save', payload, revision }))
handle('config:snapshot', () => config({ operation: 'snapshot' }))
handle('rules:simulate', (text: string, rules: Rule[]) => config({ operation: 'simulate', text, rules }))
handle('catalog:request', (request: unknown) => {
  if (!request || typeof request !== 'object' || Array.isArray(request) || JSON.stringify(request).length > 900000) throw new Error('Pedido de catálogo inválido.')
  return config({ ...request, operation: 'catalog' })
})
handle('catalog:worker', async (action: unknown) => {
  if (action === 'start') { workerError = null; workerController.start('watch') }
  else if (action === 'stop') await workerController.stop()
  else if (action !== 'status') throw new Error('Comando de worker inválido.')
  return { running: workerController.busy, error: workerError }
})
handle('bot:start', () => begin('watch'))
handle('bot:stop', async () => { if (controller.busy) update({ state: 'stopping' }); await controller.stop(); return { ok: true } })
handle('bot:isRunning', () => ({ running: controller.busy }))
handle('bot:status', () => status)
handle('bot:authenticate', () => begin('authenticate'))
handle('bot:authInput', (value: unknown) => {
  if (status.state !== 'authenticating' || !authInputExpected || typeof value !== 'string' || value.length > 1024) throw new Error('Autenticação indisponível. Aguarde a resposta atual.')
  controller.send({ command: 'auth', value })
  onEvent({ type: 'auth_step', step: 'checking' })
})
handle('window:dirty', (value: unknown) => { dirty = value === true })
handle('shell:openExternal', async (url: unknown) => {
  if (typeof url !== 'string' || (url !== 'https://my.telegram.org' && url !== 'https://my.telegram.org/apps' && !/^https:\/\/t\.me\/c\/\d+\/\d+$/.test(url))) return { ok: false }
  await shell.openExternal(url); return { ok: true }
})

function createWindow() {
  win = new BrowserWindow({ width: 1100, height: 760, minWidth: 640, minHeight: 480,
    show: !(process.env.COMPRAS_SMOKE === '1' && (process.env.COMPRAS_DATA_DIR || app.commandLine.hasSwitch('user-data-dir'))), backgroundColor: '#0B0B0F', title: 'ComprasTG',
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true } })
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  win.webContents.on('will-navigate', event => event.preventDefault())
  win.on('close', event => {
    if (quitting) return
    if (dirty || controller.busy || workerController.busy) {
      const choice = dialog.showMessageBoxSync(win!, { type: 'question', buttons: ['Continuar no app', 'Fechar e parar'], defaultId: 0, cancelId: 0,
        message: dirty ? 'Há alterações não salvas. Fechar descarta essas edições e encerra o monitor.' : 'Fechar o app encerra o monitor. Deseja continuar?' })
      if (choice === 0) { event.preventDefault(); return }
    }
    quitting = true
  })
  if (FILE_RENDERER) void win.loadFile(RENDERER)
  else void win.loadURL('http://localhost:5173')
}
app.whenReady().then(() => {
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true })
    if (app.isPackaged && !fs.existsSync(PYTHON)) throw new Error('Runtime ausente')
  } catch {
    dialog.showErrorBox('Não foi possível abrir o ComprasTG', 'Confira a permissão da pasta de dados e extraia o ZIP completo ou reinstale o aplicativo.')
    app.exit(1)
    return
  }
  createWindow()
})
app.on('window-all-closed', () => app.quit())
app.on('before-quit', event => {
  if (!controller.busy && !workerController.busy) return
  event.preventDefault()
  if (quitting && status.state === 'stopping') return
  quitting = true
  update({ state: 'stopping' })
  const timer = setTimeout(() => { controller.child?.kill(); workerController.child?.kill(); app.exit(1) }, 12000)
  void Promise.all([controller.stop(), workerController.stop()]).then(() => { clearTimeout(timer); app.quit() })
})
