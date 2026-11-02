// Helpers puros da página Keywords: draft do editor, validação e dirty.
// Sem React. O App conecta ao IPC; aqui só decisão testável.
import type { Rule } from './ipc'
import { parseBRL } from './money'

export interface RuleDraft {
  term: string
  enabled: boolean
  minStr: string
  maxStr: string
}

export function draftFromRule(r: Rule, format: (cents: number) => string): RuleDraft {
  return {
    term: r.term,
    enabled: r.enabled,
    minStr: r.min_cents !== null ? format(r.min_cents) : '',
    maxStr: r.max_cents !== null ? format(r.max_cents) : '',
  }
}

export type DraftErrors = Partial<Record<'term' | 'min' | 'max', string>>

export function validateRuleDraft(d: RuleDraft): DraftErrors {
  const errs: DraftErrors = {}
  if (d.term.trim() === '') errs.term = 'Informe a palavra-chave.'
  const mn = parseBRL(d.minStr)
  const mx = parseBRL(d.maxStr)
  if (mn.error) errs.min = mn.error
  if (mx.error) errs.max = mx.error
  if (!mn.error && !mx.error && mn.value !== null && mx.value !== null && mn.value > mx.value) {
    errs.max = 'O preço mínimo não pode ser maior que o máximo.'
  }
  return errs
}

/** Aplica draft validado sobre a regra (preserva id e posição — chamador decide onde). */
export function applyDraft(rule: Rule, d: RuleDraft): Rule {
  return {
    ...rule,
    term: d.term.trim(),
    enabled: d.enabled,
    min_cents: parseBRL(d.minStr).value,
    max_cents: parseBRL(d.maxStr).value,
  }
}

function canonical(r: Rule): string {
  return JSON.stringify({ id: r.id, term: r.term, enabled: r.enabled, min_cents: r.min_cents, max_cents: r.max_cents })
}

/** Dirty = persistido difere do editado (ordem incluída, nunca reordenada aqui). */
export function rulesDirty(persisted: Rule[], edited: Rule[]): boolean {
  if (persisted.length !== edited.length) return true
  return persisted.some((r, i) => canonical(r) !== canonical(edited[i]))
}

export type Drafts = Record<string, RuleDraft>

/** Um draft difere da regra? Compara por VALOR (parse), não por string:
 *  "R$ 5,00" vs "5,00" não é dirty. Inválido conta como diferente (bloqueia save). */
export function isDraftDirty(rule: Rule, draft: RuleDraft | undefined): boolean {
  if (!draft) return false
  if (draft.term.trim() !== rule.term || draft.enabled !== rule.enabled) return true
  const mn = parseBRL(draft.minStr)
  const mx = parseBRL(draft.maxStr)
  if (mn.error || mx.error) return true
  return (mn.value ?? null) !== rule.min_cents || (mx.value ?? null) !== rule.max_cents
}

/** Ids com edição pendente (só rules ainda existentes). */
export function dirtyIds(rules: Rule[], drafts: Drafts): string[] {
  return rules.filter((r) => isDraftDirty(r, drafts[r.id])).map((r) => r.id)
}

/** Aplica todos os drafts válidos sobre as rules (ordem e ids preservados).
 *  Chamar somente após validar cada draft (validateRuleDraft). */
export function applyDrafts(rules: Rule[], drafts: Drafts): Rule[] {
  return rules.map((r) => {
    const d = drafts[r.id]
    return d ? applyDraft(r, d) : r
  })
}

/** Valida todos os drafts pendentes; retorna o primeiro problema achado. */
export function validateAllDrafts(
  rules: Rule[],
  drafts: Drafts,
): { ruleId: string; field: keyof DraftErrors; message: string } | null {
  for (const r of rules) {
    const d = drafts[r.id]
    if (!d) continue
    const errs = validateRuleDraft(d)
    const field = (Object.keys(errs) as Array<keyof DraftErrors>)[0]
    if (field && errs[field]) return { ruleId: r.id, field, message: errs[field] as string }
  }
  return null
}

/** Remove drafts de rules que não existem mais (pós-delete). */
export function pruneDrafts(rules: Rule[], drafts: Drafts): Drafts {
  const ids = new Set(rules.map((r) => r.id))
  return Object.fromEntries(Object.entries(drafts).filter(([id]) => ids.has(id)))
}
