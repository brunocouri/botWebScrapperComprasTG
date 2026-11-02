import { describe, it, expect } from 'vitest'
import { formatBRL, parseBRL } from './money'

describe('formatBRL', () => {
  it('189900 <-> R$ 1.899,00', () => {
    expect(formatBRL(189900)).toBe('1.899,00')
  })
  it('zero, centavos e milhares', () => {
    expect(formatBRL(0)).toBe('0,00')
    expect(formatBRL(90)).toBe('0,90')
    expect(formatBRL(100)).toBe('1,00')
    expect(formatBRL(123456789)).toBe('1.234.567,89')
  })
})

describe('parseBRL', () => {
  it('null <-> vazio', () => {
    expect(parseBRL('')).toEqual({ value: null, error: null })
    expect(parseBRL('   ')).toEqual({ value: null, error: null })
  })
  it('R$ 1.899,00 -> 189900', () => {
    expect(parseBRL('R$ 1.899,00')).toEqual({ value: 189900, error: null })
    expect(parseBRL('1899')).toEqual({ value: 189900, error: null })
    expect(parseBRL('1,5')).toEqual({ value: 150, error: null })
    expect(parseBRL('0')).toEqual({ value: 0, error: null })
  })
  it('entrada inválida explica, nunca NaN', () => {
    // 'R$' sozinho vira vazio após strip -> null sem erro (equivale a sem limite)
    expect(parseBRL('R$')).toEqual({ value: null, error: null })
    for (const bad of ['abc', '1.89,00', '--5', '1,899,00']) {
      const r = parseBRL(bad)
      expect(r.error).toBeTruthy()
      expect(r.value).toBeNull()
      expect(Number.isNaN(r.value as unknown as number)).toBe(false)
    }
  })
  it('nunca float: só inteiros', () => {
    const r = parseBRL('R$ 10,10')
    expect(r.value).toBe(1010)
    expect(Number.isInteger(r.value)).toBe(true)
  })
})
