// Lógica pura de normalização/validação do keywords.json para o main.
// O main faz fs/IO; aqui só decisão testável. Sem React/Electron.
import type { Rule } from './ipc'

export type IdGen = (term: string, existing: Set<string>) => string

export function defaultIdGen(term: string, existing: Set<string>): string {
  const base = term.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'rule'
  for (let i = 0; i < 100; i++) {
    const id = `${base}-${Math.floor(Math.random() * 0xffff).toString(16).padStart(4, '0')}`
    if (!existing.has(id)) return id
  }
  throw new Error('colisão de rule_id esgotada')
}

function isCents(v: unknown): v is number {
  return typeof v === 'number' && Number.isInteger(v) && v >= 0
}

/** v1 (string[]) ou v2 ({rules}) -> Rule[]. Lança Error explícito se inválido. */
export function toRules(data: unknown, genId: IdGen = defaultIdGen): Rule[] {
  const existing = new Set<string>()
  const fromLegacy = (term: unknown): Rule => {
    if (typeof term !== 'string' || term.trim() === '') throw new Error('term vazio no legado')
    const id = genId(term.trim(), existing)
    existing.add(id)
    return { id, term: term.trim(), enabled: true, min_cents: null, max_cents: null }
  }
  const fromDict = (item: unknown): Rule => {
    if (typeof item !== 'object' || item === null) throw new Error('regra deve ser objeto')
    const r = item as Record<string, unknown>
    if (typeof r.term !== 'string' || r.term.trim() === '') throw new Error('term vazio')
    if (typeof r.id !== 'string' || r.id.trim() === '') throw new Error('id vazio')
    if (existing.has(r.id)) throw new Error(`id duplicado '${r.id}'`)
    existing.add(r.id)
    if (typeof r.enabled !== 'boolean') throw new Error('enabled deve ser booleano')
    if (r.min_cents !== null && r.min_cents !== undefined && !isCents(r.min_cents)) throw new Error('min_cents deve ser int >= 0 ou null')
    if (r.max_cents !== null && r.max_cents !== undefined && !isCents(r.max_cents)) throw new Error('max_cents deve ser int >= 0 ou null')
    const mn = (r.min_cents ?? null) as number | null
    const mx = (r.max_cents ?? null) as number | null
    if (mn !== null && mx !== null && mn > mx) throw new Error('min_cents <= max_cents')
    return { id: r.id, term: r.term.trim(), enabled: r.enabled, min_cents: mn, max_cents: mx }
  }
  if (Array.isArray(data)) {
    return (data as unknown[]).map((item) => (typeof item === 'string' ? fromLegacy(item) : fromDict(item)))
  }
  if (data && typeof data === 'object' && Array.isArray((data as Record<string, unknown>).rules)) {
    return ((data as Record<string, unknown>).rules as unknown[]).map(
      (item) => (typeof item === 'string' ? fromLegacy(item) : fromDict(item)),
    )
  }
  throw new Error('formato de keywords inválido')
}

/** Valida payload de save. Retorna mensagem de erro ou null. */
export function validateRulesPayload(rules: unknown): string | null {
  if (!Array.isArray(rules)) return 'Formato de regras inválido.'
  try {
    const ids = new Set<string>()
    for (const r of rules) {
      if (typeof r !== 'object' || r === null) return 'Regra deve ser objeto.'
      const o = r as Record<string, unknown>
      if (typeof o.id !== 'string' || o.id.trim() === '') return 'Toda regra precisa de id.'
      if (ids.has(o.id)) return `ID duplicado: ${o.id}`
      ids.add(o.id)
      if (typeof o.term !== 'string' || o.term.trim() === '') return 'Toda regra precisa de palavra-chave.'
      if (typeof o.enabled !== 'boolean') return 'enabled deve ser booleano.'
      const mn = (o.min_cents ?? null) as number | null
      const mx = (o.max_cents ?? null) as number | null
      if (mn !== null && !isCents(mn)) return 'Preço mínimo inválido.'
      if (mx !== null && !isCents(mx)) return 'Preço máximo inválido.'
      if (mn !== null && mx !== null && mn > mx) return 'O preço mínimo não pode ser maior que o máximo.'
    }
    return null
  } catch {
    return 'Formato de regras inválido.'
  }
}

export function isV2Document(data: unknown): boolean {
  return !!data && typeof data === 'object' && !Array.isArray(data)
    && (data as Record<string, unknown>).version === 2
    && Array.isArray((data as Record<string, unknown>).rules)
}
