// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { Catalog } from './Catalog'
import type { BotApi } from '../lib/ipc'

afterEach(cleanup)
const groups = [{ id: -1001, name: 'Celulares', selected: true }]
let rejectSave = false
const call = vi.fn(async (r: { action: string }) => {
  if (r.action === 'template:save' && rejectSave) throw new Error('Falha ao salvar')
  if (r.action === 'status') return { messages: 0, revisions: 0, pending: 0, offers: 0, reviews: 0, bytes: 0, sources: [{ id: -1001, name: 'Celulares', enabled: 1, capture_started_at: '2026-10-30T10:00:00Z', checkpoint: null, revision: 1, degraded: null }] }
  if (['templates', 'fields', 'reprocess:list', 'deliveries'].includes(r.action)) return []
  if (r.action === 'links' || r.action === 'alerts') return { rules: [], revision: 0 }
  return { items: [], total: 0 }
})
function setup() {
  call.mockClear()
  rejectSave = false
  window.api = { catalog: call, worker: vi.fn().mockResolvedValue({ running: false, error: null }) } as unknown as BotApi
  render(<Catalog groups={groups} onSourcesChanged={vi.fn()} onDirty={vi.fn()} />)
}
it('grupo selecionado já aparece arquivado e permite pausar separadamente', async () => {
  setup()
  await screen.findByRole('checkbox', { name: 'Arquivar Celulares' })
  await waitFor(() => expect((screen.getByRole('checkbox', { name: 'Arquivar Celulares' }) as HTMLInputElement).checked).toBe(true))
  expect(call.mock.calls.some(([r]) => r.action === 'source:save')).toBe(false)
  fireEvent.click(screen.getByRole('checkbox', { name: 'Arquivar Celulares' }))
  await waitFor(() => expect(call).toHaveBeenCalledWith(expect.objectContaining({ action: 'source:save', id: -1001, enabled: false, revision: 1 })))
})
it('oferece editor guiado sem exigir JSON e preserva entrada após falha', async () => {
  setup()
  fireEvent.click(screen.getByRole('button', { name: 'Modelos' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Criar modelo' }))
  fireEvent.change(screen.getByLabelText('Nome do modelo'), { target: { value: 'Celular Pix' } })
  fireEvent.change(screen.getByLabelText('Marcadores de reconhecimento (um por linha)'), { target: { value: 'Produto:' } })
  rejectSave = true
  fireEvent.click(screen.getByRole('button', { name: 'Salvar rascunho' }))
  await screen.findByRole('alert')
  expect((screen.getByLabelText('Nome do modelo') as HTMLInputElement).value).toBe('Celular Pix')
  fireEvent.click(screen.getByRole('button', { name: 'Coleta' }))
  fireEvent.click(screen.getByRole('button', { name: 'Modelos' }))
  expect((screen.getByLabelText('Nome do modelo') as HTMLInputElement).value).toBe('Celular Pix')
})
