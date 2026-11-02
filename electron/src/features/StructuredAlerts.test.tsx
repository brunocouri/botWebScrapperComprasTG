// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { StructuredAlerts } from './StructuredAlerts'
import type { BotApi } from '../lib/ipc'

afterEach(cleanup)
it('salva filtro monetário em centavos e exige ativação explícita', async () => {
  const catalog = vi.fn(async (r: { action: string; rules?: unknown[] }) => {
    if (r.action === 'fields') return [{ id: 'pix', name: 'Preço Pix', type: 'money' }]
    if (r.action === 'alerts:save') return { rules: r.rules, revision: 1 }
    return { rules: [], revision: 0 }
  })
  window.api = { catalog } as unknown as BotApi
  render(<StructuredAlerts groups={[{ id: -1001, name: 'Canal', selected: false }]} onDirty={vi.fn()} report={vi.fn()} />)
  await waitFor(() => expect((screen.getByRole('button', { name: 'Criar alerta estruturado' }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Criar alerta estruturado' }))
  fireEvent.change(screen.getByLabelText('Nome do alerta'), { target: { value: 'Preço baixo' } })
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar condição' }))
  fireEvent.change(screen.getByLabelText('Campo'), { target: { value: 'pix' } })
  fireEvent.change(screen.getByLabelText('Máximo (R$)'), { target: { value: '1899.90' } })
  fireEvent.submit(screen.getByLabelText('Nome do alerta').closest('form')!)
  await waitFor(() => expect(catalog).toHaveBeenCalledWith(expect.objectContaining({ action: 'alerts:save', rules: [expect.objectContaining({ enabled: false, filters: { values: [{ field_id: 'pix', max: 189990 }] } })] })))
})
