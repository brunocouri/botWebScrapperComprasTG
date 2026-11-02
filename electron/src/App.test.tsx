// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { BotApi, Rule, RuntimeStatus } from './lib/ipc'

const rules: Rule[] = [{ id: 'a', term: 'A57', enabled: true, min_cents: null, max_cents: null },
  { id: 'b', term: 'Galaxy', enabled: true, min_cents: null, max_cents: 200000 }]
let api: BotApi
let onStatus: (s: RuntimeStatus) => void
const status: RuntimeStatus = { state: 'stopped', busy: false, error: null, snapshot: null }

beforeEach(() => {
  api = {
    catalog: vi.fn().mockResolvedValue([]), worker: vi.fn(),
    listGroups: vi.fn().mockResolvedValue({ groups: [{ id: 1, name: 'Celulares', selected: false }, { id: 2, name: 'Hardware', selected: false }], revision: 'g' }),
    saveGroups: vi.fn().mockImplementation(async (groups) => ({ groups, revision: 'g2' })),
    reloadGroups: vi.fn().mockResolvedValue({ ok: true, out: '' }),
    getKeywords: vi.fn().mockResolvedValue({ rules: structuredClone(rules), revision: 'r' }),
    saveKeywords: vi.fn().mockImplementation(async rules => ({ rules, revision: 'r2' })),
    addKeyword: vi.fn().mockRejectedValue(new Error('Disco indisponível')),
    getConfig: vi.fn().mockResolvedValue({ apiId: '123456', apiHashSet: true, apiHashPreview: '••••1234', phone: '+5511999999999', revision: 'c' }),
    saveConfig: vi.fn(), startBot: vi.fn().mockResolvedValue({ ok: true }), stopBot: vi.fn().mockResolvedValue({ ok: true }),
    isRunning: vi.fn().mockResolvedValue({ running: false }), getStatus: vi.fn().mockResolvedValue(status),
    getSnapshot: vi.fn().mockResolvedValue({ revision: 's', groups: 0, rules: 2, keywords: ['A57', 'Galaxy'] }),
    authenticate: vi.fn(), submitAuth: vi.fn(), simulate: vi.fn().mockResolvedValue({ evaluations: [], winner: null, others: [] }),
    setDirty: vi.fn().mockResolvedValue(undefined), openExternal: vi.fn(),
    onBotEvent: vi.fn().mockReturnValue(() => {}), onBotStopped: vi.fn().mockReturnValue(() => {}), onBotCrashed: vi.fn().mockReturnValue(() => {}),
    onStatus: vi.fn().mockImplementation(cb => { onStatus = cb; return () => {} }),
  }
  window.api = api
})
afterEach(cleanup)

describe('fluxos operacionais', () => {
  it('mostra Coletados acima de Grupos e abre originais sem exigir modelo', async () => {
    api.worker = vi.fn().mockResolvedValue({ running: false, error: null })
    api.catalog = vi.fn().mockImplementation(async request => {
      if (request.action === 'sources') return []
      if (request.action === 'status') return { messages: 1, revisions: 1, offers: 0, pending: 1, reviews: 0, bytes: 0, sources: [] }
      if (request.action === 'links' || request.action === 'alerts') return { rules: [], revision: 0 }
      if (request.action === 'reviews' || request.action === 'search') return { items: [], total: 0 }
      if (request.action === 'messages') return { total: 1, items: [{ id: 10, source_id: 1, message_id: 123, published_at: '2026-10-30T12:00:00Z', source_name: 'Celulares', text: 'Postagem coletada sem modelo', state: null }] }
      if (request.action === 'message') return { id: 10, source_id: 1, message_id: 123, published_at: '2026-10-30T12:00:00Z', source_name: 'Celulares', text: 'Postagem original completa', metadata: { links: [], media_type: null }, revisions: [], runs: [], run_history: [] }
      return []
    })
    render(<App />)
    const navigation = screen.getByRole('navigation', { name: 'Principal' })
    expect(within(navigation).getAllByRole('button').slice(0, 2).map(b => b.textContent)).toEqual(['Coletados', 'Grupos'])
    fireEvent.click(within(navigation).getByRole('button', { name: 'Coletados' }))
    await screen.findByRole('heading', { name: 'Coletados', level: 1 })
    await screen.findByText('Postagem coletada sem modelo')
    fireEvent.click(screen.getByRole('button', { name: /Celulares ·/ }))
    await screen.findByText('Postagem original completa')
    fireEvent.click(screen.getByRole('button', { name: 'Parametrizar esta mensagem' }))
    await screen.findByRole('heading', { name: 'Catálogo', level: 1 })
    expect(screen.getByLabelText('Texto para testar')).toBeTruthy()
  })
  it('editar a mensagem invalida o resultado anterior da simulação', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Palavras-chave' }))
    await screen.findByRole('button', { name: 'Editar A57' })
    const input = screen.getByLabelText('Texto da oferta')
    fireEvent.change(input, { target: { value: 'A57 R$ 1.899' } })
    fireEvent.click(screen.getByRole('button', { name: 'Simular regras' }))
    await screen.findByText('Nenhum alerta seria enviado')
    fireEvent.change(input, { target: { value: 'Outro produto' } })
    expect(screen.queryByText('Nenhum alerta seria enviado')).toBeNull()
  })
  it('snapshot de status atrasado não sobrescreve evento mais recente', async () => {
    let resolve!: (value: RuntimeStatus) => void
    api.getStatus = vi.fn().mockReturnValue(new Promise<RuntimeStatus>(done => { resolve = done }))
    render(<App />)
    await screen.findByText('Celulares')
    onStatus({ state: 'monitoring', busy: true, snapshot: null, error: null })
    await screen.findByText('Monitorando')
    resolve(status)
    await new Promise(done => setTimeout(done, 0))
    expect(screen.getByText('Monitorando')).toBeTruthy()
  })
  it('seleciona somente os resultados da busca', async () => {
    render(<App />)
    await screen.findByText('Celulares')
    fireEvent.change(screen.getByLabelText('Buscar grupos'), { target: { value: 'Celulares' } })
    fireEvent.click(screen.getByLabelText('Selecionar resultados (1)'))
    await waitFor(() => expect(api.saveGroups).toHaveBeenCalledWith([
      { id: 1, name: 'Celulares', selected: true }, { id: 2, name: 'Hardware', selected: false },
    ], 'g'))
  })
  it('aceitação de spawn não mostra monitoramento ativo', async () => {
    render(<App />)
    await screen.findByText('Celulares')
    fireEvent.click(screen.getByRole('checkbox', { name: /Celulares/ }))
    await waitFor(() => expect(api.saveGroups).toHaveBeenCalledOnce())
    await waitFor(() => expect((screen.getByRole('button', { name: 'Iniciar monitor' }) as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(screen.getByRole('button', { name: 'Iniciar monitor' }))
    await waitFor(() => expect(api.startBot).toHaveBeenCalledOnce())
    expect(screen.queryByText('Monitorando')).toBeNull()
    onStatus({ state: 'monitoring', busy: true, error: null, snapshot: { revision: 's', groups: 1, rules: 2, keywords: [] } })
    await screen.findByText('Monitorando')
  })
  it('salva rascunho de outra regra mesmo com editor atual sem alterações', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Palavras-chave' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Editar A57' }))
    fireEvent.change(screen.getByLabelText('Palavra-chave'), { target: { value: 'A58' } })
    fireEvent.click(screen.getByRole('button', { name: 'Editar Galaxy' }))
    fireEvent.click(screen.getByRole('button', { name: 'Salvar 1 alteração' }))
    await waitFor(() => expect(api.saveKeywords).toHaveBeenCalledWith([
      { ...rules[0], term: 'A58' }, rules[1],
    ], 'r'))
  })
  it('preserva termo ao falhar adição', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Palavras-chave' }))
    await screen.findByRole('button', { name: 'Editar A57' })
    const input = screen.getByLabelText('Nova palavra-chave')
    fireEvent.change(input, { target: { value: 'iPhone' } })
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
    await screen.findByText('Disco indisponível')
    expect((input as HTMLInputElement).value).toBe('iPhone')
  })
})
