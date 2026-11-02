// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Activity } from './Activity'
import { FeedStore } from '../lib/feed-store'

afterEach(() => { cleanup(); vi.useRealTimers() })
describe('buffer e acompanhamento', () => {
  it('agrupa rajadas, preserva ordem e limita memória', () => {
    vi.useFakeTimers()
    const store = new FeedStore(), changed = vi.fn()
    store.subscribe(changed)
    for (let i = 0; i < 1000; i++) store.receive({ kind: 'event', event: { type: 'sync', detail: String(i) } })
    expect(changed).not.toHaveBeenCalled()
    vi.advanceTimersByTime(50)
    expect(changed).toHaveBeenCalledOnce()
    expect(store.snapshot().events).toHaveLength(800)
    expect(store.snapshot().events[0].title).toBe('200')
    expect(store.snapshot().events.at(-1)?.title).toBe('999')
  })
  it('subir a lista pausa acompanhamento; novos eventos não roubam leitura', () => {
    const store = new FeedStore()
    render(<Activity store={store} status="monitoring" />)
    const feed = screen.getByLabelText('Eventos de atividade')
    Object.defineProperties(feed, { scrollHeight: { value: 1000, configurable: true }, clientHeight: { value: 100, configurable: true } })
    feed.scrollTop = 100
    fireEvent.scroll(feed)
    act(() => { store.receive({ kind: 'event', event: { type: 'sync', detail: 'Novo evento' } }); store.flush() })
    expect(feed.scrollTop).toBe(100)
    expect(screen.getByRole('button', { name: '1 novos eventos — Voltar ao final' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '1 novos eventos — Voltar ao final' }))
    expect(feed.scrollTop).toBe(1000)
  })
})
