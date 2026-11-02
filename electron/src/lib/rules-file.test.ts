import { describe, it, expect } from 'vitest'
import { toRules, validateRulesPayload, isV2Document } from './rules-file'

const gen = (() => {
  let n = 0
  return () => `test-${++n}`
})()

describe('toRules', () => {
  it('v1 vira Rule[] com ids gerados uma vez', () => {
    const out = toRules(['A57', 'Galaxy'], gen)
    expect(out).toEqual([
      { id: 'test-1', term: 'A57', enabled: true, min_cents: null, max_cents: null },
      { id: 'test-2', term: 'Galaxy', enabled: true, min_cents: null, max_cents: null },
    ])
  })
  it('v2 passa com bounds/enabled/id preservados e ordem intacta', () => {
    const v2 = { version: 2, rules: [
      { id: 'b', term: 'B', enabled: false, min_cents: 100, max_cents: 200 },
      { id: 'a', term: 'A', enabled: true, min_cents: null, max_cents: null },
    ] }
    expect(toRules(v2, gen)).toEqual(v2.rules)
  })
  it('renomear term preserva id (round-trip)', () => {
    const rules = toRules([{ id: 'x-1', term: 'A57', enabled: true, min_cents: null, max_cents: null }], gen)
    const renamed = rules.map((r) => ({ ...r, term: 'A57 5G' }))
    expect(renamed[0].id).toBe('x-1')
    expect(validateRulesPayload(renamed)).toBeNull()
  })
  it('payload inválido é rejeitado, nunca silencioso', () => {
    expect(() => toRules(['  '], gen)).toThrow()
    expect(() => toRules(123, gen)).toThrow()
    expect(() => toRules({ foo: 1 }, gen)).toThrow()
    expect(() => toRules([{ id: 'a', term: 'A', enabled: true, min_cents: 5, max_cents: 4 }], gen)).toThrow()
    expect(() => toRules([{ id: 'a', term: 'A', enabled: true }, { id: 'a', term: 'B', enabled: true }], gen)).toThrow()
    expect(() => toRules([{ id: 'a', term: 'A', enabled: true, min_cents: 1.5 }], gen)).toThrow()
  })
})

describe('validateRulesPayload', () => {
  it('aceita Rule[] válido e rejeita o resto', () => {
    expect(validateRulesPayload([])).toBeNull()
    expect(validateRulesPayload([{ id: 'a', term: 'A', enabled: true, min_cents: null, max_cents: null }])).toBeNull()
    expect(validateRulesPayload('x')).not.toBeNull()
    expect(validateRulesPayload([{ id: '', term: 'A', enabled: true }])).not.toBeNull()
    expect(validateRulesPayload([{ id: 'a', term: '  ', enabled: true }])).not.toBeNull()
    expect(validateRulesPayload([
      { id: 'a', term: 'A', enabled: true },
      { id: 'a', term: 'B', enabled: true },
    ])).toMatch(/duplicado/i)
    expect(validateRulesPayload([{ id: 'a', term: 'A', enabled: true, min_cents: 10, max_cents: 5 }])).toMatch(/maior/)
  })
})

describe('isV2Document', () => {
  it('só v2 com rules', () => {
    expect(isV2Document({ version: 2, rules: [] })).toBe(true)
    expect(isV2Document(['A57'])).toBe(false)
    expect(isV2Document({ version: 1, rules: [] })).toBe(false)
    expect(isV2Document(null)).toBe(false)
  })
})
