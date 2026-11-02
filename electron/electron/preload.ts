import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'
import type { BotApi } from '../src/lib/ipc'

function listen<T>(channel: string, callback: (value: T) => void) {
  const handler = (_event: IpcRendererEvent, value: T) => callback(value)
  ipcRenderer.on(channel, handler)
  return () => ipcRenderer.removeListener(channel, handler)
}
const api: BotApi = {
  catalog: request => ipcRenderer.invoke('catalog:request', request),
  worker: action => ipcRenderer.invoke('catalog:worker', action),
  listGroups: () => ipcRenderer.invoke('groups:list'),
  reloadGroups: () => ipcRenderer.invoke('groups:reload'),
  saveGroups: (groups, revision) => ipcRenderer.invoke('groups:save', groups, revision),
  getKeywords: () => ipcRenderer.invoke('keywords:get'),
  saveKeywords: (rules, revision) => ipcRenderer.invoke('keywords:save', rules, revision),
  addKeyword: (term, revision) => ipcRenderer.invoke('keywords:add', term, revision),
  startBot: () => ipcRenderer.invoke('bot:start'),
  stopBot: () => ipcRenderer.invoke('bot:stop'),
  isRunning: () => ipcRenderer.invoke('bot:isRunning'),
  getStatus: () => ipcRenderer.invoke('bot:status'),
  getSnapshot: () => ipcRenderer.invoke('config:snapshot'),
  authenticate: () => ipcRenderer.invoke('bot:authenticate'),
  submitAuth: value => ipcRenderer.invoke('bot:authInput', value),
  simulate: (text, rules) => ipcRenderer.invoke('rules:simulate', text, rules),
  setDirty: dirty => ipcRenderer.invoke('window:dirty', dirty),
  getConfig: () => ipcRenderer.invoke('config:get'),
  saveConfig: (payload, revision) => ipcRenderer.invoke('config:save', payload, revision),
  openExternal: url => ipcRenderer.invoke('shell:openExternal', url),
  onStatus: callback => listen('bot:status', callback),
  onBotEvent: callback => listen('bot:event', callback),
  onBotStopped: callback => listen('bot:stopped', callback),
  onBotCrashed: callback => listen('bot:crashed', callback),
}
contextBridge.exposeInMainWorld('api', api)
