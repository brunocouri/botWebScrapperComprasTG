import { expect, it } from 'vitest'
import { numericBounds } from './catalog-filters'

it('busca aceita reais brasileiros e rejeita limite inválido sem ignorar filtro', () => {
  expect(numericBounds('money', '1.200,50', '1.899,90')).toEqual({ min: 120050, max: 189990 })
  expect(() => numericBounds('money', '', 'barato')).toThrow()
  expect(() => numericBounds('money', '200', '100')).toThrow()
  expect(numericBounds('number', '1,5', '2,75')).toEqual({ min: 1.5, max: 2.75 })
})
