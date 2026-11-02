import { describe, it, expect } from 'vitest'
import { resolveCloseAction, shouldDelayQuit, SHUTDOWN_GRACE_MS } from './lifecycle'

describe('resolveCloseAction', () => {
  it('stop do usuário -> stopped (nunca crash)', () => {
    expect(resolveCloseAction({ quitting: false, stopRequested: true })).toBe('stopped')
  })
  it('morte inesperada -> crashed (nunca parada normal)', () => {
    expect(resolveCloseAction({ quitting: false, stopRequested: false })).toBe('crashed')
  })
  it('quit em andamento -> ignored-quit (sem IPC fantasma)', () => {
    expect(resolveCloseAction({ quitting: true, stopRequested: false })).toBe('ignored-quit')
    expect(resolveCloseAction({ quitting: true, stopRequested: true })).toBe('ignored-quit')
  })
})

describe('shouldDelayQuit', () => {
  it('segura o quit só com filho vivo e primeira tentativa', () => {
    expect(shouldDelayQuit({ hasChild: true, alreadyQuitting: false })).toBe(true)
    expect(shouldDelayQuit({ hasChild: false, alreadyQuitting: false })).toBe(false)
    expect(shouldDelayQuit({ hasChild: true, alreadyQuitting: true })).toBe(false)
  })
  it('timeout de segurança é finito e curto', () => {
    expect(SHUTDOWN_GRACE_MS).toBeGreaterThan(0)
    expect(SHUTDOWN_GRACE_MS).toBeLessThanOrEqual(10000)
  })
})
