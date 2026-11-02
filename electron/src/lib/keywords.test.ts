import { describe, it, expect } from 'vitest'
import { draftFromRule, validateRuleDraft, applyDraft, rulesDirty, isDraftDirty, applyDrafts, validateAllDrafts, pruneDrafts } from './keywords'
import type { Rule } from './ipc'

const R = (over: Partial<Rule> = {}): Rule => ({
  id: 'a-1', term: 'A57', enabled: true, min_cents: null, max_cents: null, ...over,
})

describe('draftFromRule', () => {
  it('null vira vazio, centavos viram BRL', () => {
    const d = draftFromRule(R({ min_cents: null, max_cents: 189900 }), (c) => `F${c}`)
    expect(d).toEqual({ term: 'A57', enabled: true, minStr: '', maxStr: 'F189900' })
  })
})

describe('validateRuleDraft', () => {
  it('min = max válido; min < max válido', () => {
    expect(validateRuleDraft({ term: 'A', enabled: true, minStr: '10,00', maxStr: '10,00' })).toEqual({})
    expect(validateRuleDraft({ term: 'A', enabled: true, minStr: '', maxStr: '5,00' })).toEqual({})
  })
  it('min > max inválido com a mensagem da spec', () => {
    const e = validateRuleDraft({ term: 'A', enabled: true, minStr: 'R$ 2.000,00', maxStr: 'R$ 1.500,00' })
    expect(e.max).toBe('O preço mínimo não pode ser maior que o máximo.')
  })
  it('term vazio e valores inválidos', () => {
    const e = validateRuleDraft({ term: '  ', enabled: true, minStr: 'abc', maxStr: '-5' })
    expect(e.term).toBeTruthy()
    expect(e.min).toBeTruthy()
    expect(e.max).toBeTruthy()
  })
})

describe('applyDraft', () => {
  it('preserva id e resto, converte BRL', () => {
    const out = applyDraft(R({ id: 'keep-me', min_cents: 1 }), { term: ' A58 ', enabled: false, minStr: '', maxStr: 'R$ 5,00' })
    expect(out).toEqual({ id: 'keep-me', term: 'A58', enabled: false, min_cents: null, max_cents: 500 })
  })
})

describe('rulesDirty', () => {
  it('igual -> false; edição, ordem e tamanho -> true', () => {
    const a = [R(), R({ id: 'b', term: 'B' })]
    expect(rulesDirty(a, a.map((r) => ({ ...r })))).toBe(false)
    expect(rulesDirty(a, [{ ...a[0], term: 'X' }, a[1]])).toBe(true)
    expect(rulesDirty(a, [a[1], a[0]])).toBe(true)
    expect(rulesDirty(a, [a[0]])).toBe(true)
  })
  it('disabled não exclui: continua na lista', () => {
    const a = [R({ enabled: false })]
    expect(rulesDirty(a, [{ ...a[0] }])).toBe(false)
    expect(a).toHaveLength(1)
  })
})

describe('isDraftDirty', () => {
  it('formatos equivalentes não são dirty', () => {
    const r = R({ max_cents: 500 })
    expect(isDraftDirty(r, undefined)).toBe(false)
    expect(isDraftDirty(r, { term: 'A57', enabled: true, minStr: '', maxStr: 'R$ 5,00' })).toBe(false)
  })
  it('valor diferente, toggle e termo marcam dirty; inválido também', () => {
    const r = R()
    expect(isDraftDirty(r, { term: 'A57', enabled: false, minStr: '', maxStr: '' })).toBe(true)
    expect(isDraftDirty(r, { term: 'X', enabled: true, minStr: '', maxStr: '' })).toBe(true)
    expect(isDraftDirty(r, { term: 'A57', enabled: true, minStr: '', maxStr: 'abc' })).toBe(true)
    expect(isDraftDirty(r, { term: 'A57', enabled: true, minStr: '', maxStr: '' })).toBe(false)
  })
})

describe('applyDrafts', () => {
  it('aplica só ids presentes, preserva ordem e ids', () => {
    const rules = [R(), R({ id: 'b', term: 'B' })]
    const out = applyDrafts(rules, { b: { term: 'B2', enabled: false, minStr: '', maxStr: '10,00' } })
    expect(out.map((r) => r.id)).toEqual(['a-1', 'b'])
    expect(out[0].term).toBe('A57')
    expect(out[1]).toEqual({ id: 'b', term: 'B2', enabled: false, min_cents: null, max_cents: 1000 })
  })
  it('ignora drafts de ids inexistentes', () => {
    const rules = [R()]
    expect(applyDrafts(rules, { zzz: { term: 'Z', enabled: true, minStr: '', maxStr: '' } })).toEqual(rules)
  })
})

describe('validateAllDrafts', () => {
  it('ok quando vazio; aponta primeira regra com problema', () => {
    const rules = [R(), R({ id: 'b', term: 'B' })]
    expect(validateAllDrafts(rules, {})).toBeNull()
    const bad = validateAllDrafts(rules, { b: { term: '', enabled: true, minStr: '', maxStr: '' } })
    expect(bad).toEqual({ ruleId: 'b', field: 'term', message: expect.any(String) })
  })
})

describe('pruneDrafts', () => {
  it('remove drafts de rules excluídas, mantém o resto', () => {
    const drafts = { 'a-1': { term: 'A57', enabled: true, minStr: 'x', maxStr: '' }, zzz: { term: 'Z', enabled: true, minStr: '', maxStr: '' } }
    expect(pruneDrafts([R()], drafts)).toEqual({ 'a-1': drafts['a-1'] })
  })
})
