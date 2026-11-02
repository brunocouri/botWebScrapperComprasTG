// Dinheiro em centavos inteiros — nunca float.
// parseBRL: texto do input -> { value } | { error }. vazio -> null (sem limite).
// formatBRL: centavos -> "1.899,00".

export interface ParsedBRL {
  value: number | null
  error: string | null
}

export function formatBRL(cents: number): string {
  const reais = Math.floor(cents / 100)
  const cent = cents % 100
  return `${reais.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${cent.toString().padStart(2, '0')}`
}

export function parseBRL(s: string): ParsedBRL {
  const t = s.trim().replace(/^R\$\s?/i, '').replace(/\s/g, '')
  if (t === '') return { value: null, error: null }
  const okShape = /^\d{1,3}(\.\d{3})*(,\d{1,2})?$/.test(t) || /^\d+(,\d{1,2})?$/.test(t)
  if (!okShape) return { value: null, error: 'Valor inválido. Ex: R$ 1.899,00' }
  const [intPart, decPart = ''] = t.split(',')
  const cents = parseInt(intPart.replace(/\./g, ''), 10) * 100 + parseInt((decPart + '00').slice(0, 2), 10)
  if (!Number.isSafeInteger(cents)) return { value: null, error: 'Valor muito grande' }
  return { value: cents, error: null }
}
