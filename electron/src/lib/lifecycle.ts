// Menor máquina testável do lifecycle do bot (I-3). Sem Electron/React.
// O main.ts aplica; aqui só a tabela de decisão, coberta por lifecycle.test.ts.

export const SHUTDOWN_GRACE_MS = 5000

export type CloseOutcome = 'stopped' | 'crashed' | 'ignored-quit'

/** Decide o que um 'close' do Python significa.
 *  quitting (before-quit em andamento) -> ignora: o app está saindo mesmo.
 *  stopRequested (bot:stop do usuário) -> parada normal.
 *  Caso contrário -> crash: nunca fingir parada normal. */
export function resolveCloseAction(o: { quitting: boolean; stopRequested: boolean }): CloseOutcome {
  if (o.quitting) return 'ignored-quit'
  if (o.stopRequested) return 'stopped'
  return 'crashed'
}

/** before-quit deve segurar o quit somente se há filho vivo para colher. */
export function shouldDelayQuit(o: { hasChild: boolean; alreadyQuitting: boolean }): boolean {
  return o.hasChild && !o.alreadyQuitting
}
