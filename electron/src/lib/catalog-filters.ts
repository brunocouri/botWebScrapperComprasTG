import { parseBRL } from './money'
import type { FieldType } from './catalog'

export function numericBounds(type: FieldType | undefined, min: string, max: string): { min?: number; max?: number } {
  const parse = (value: string) => {
    if (!value.trim()) return undefined
    if (type === 'money') {
      const result = parseBRL(value)
      if (result.error) throw new Error(result.error)
      return result.value ?? undefined
    }
    const result = Number(value.replace(',', '.'))
    if (!Number.isFinite(result)) throw new Error('Limite numérico inválido.')
    return result
  }
  const result = { min: parse(min), max: parse(max) }
  if (result.min !== undefined && result.max !== undefined && result.min > result.max) throw new Error('O mínimo não pode exceder o máximo.')
  return result
}
