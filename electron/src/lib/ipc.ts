// Contratos IPC main <-> renderer + protocolo bot:event.
// Fonte de verdade (AGENTS.md). Sem runtime: só tipos. Não importar React/Electron aqui.
import type { CatalogRequest, WorkerStatus } from './catalog'

export interface WatchedGroup {
  id: number
  name: string
  selected: boolean
}

/** Ocorrência de preço (SPEC-PREÇOS §1.2). `frete` = custo acessório, nunca decisivo. */
export interface PriceOccurrence {
  line?: number
  cents: number
  kind: 'por' | 'vista' | 'parcela' | 'de' | 'avulso' | 'frete'
  raw: string
  installments?: number
  installment_cents?: number
  total_cents?: number
}

/** Preço decisivo com origem preservada (nunca só cents). */
export interface DecisivePrice {
  cents: number
  kind: PriceOccurrence['kind']
  installments?: number
  installment_cents?: number
  total_cents?: number
}

export type FilterReason = 'above_max' | 'below_min' | 'no_price' | 'superseded' | 'ambiguous_price'

export interface AppliedSnapshot { revision: string; groups: number; rules: number; keywords: string[] }
export type RuntimeState = 'stopped' | 'starting' | 'connecting' | 'synchronizing' | 'monitoring' | 'reconnecting' | 'stopping' | 'auth_required' | 'authenticating' | 'error'
export interface RuntimeStatus { state: RuntimeState; busy: boolean; snapshot: AppliedSnapshot | null; error: string | null }

/** Eventos JSONL (stdout do bot.py). stderr = logs humanos, nunca protocolo. */
export type BotEvent = (
  | { type: 'bot_started'; groups: number; keywords: string[] }
  | { type: 'telegram_connecting' }
  | { type: 'telegram_connected' }
  | { type: 'telegram_syncing' }
  | { type: 'session_authenticated'; name: string; user_id: number }
  | { type: 'monitoring_started'; snapshot?: AppliedSnapshot }
  | { type: 'connection_state'; connected: boolean }
  | { type: 'auth_step'; step: 'code' | 'password' | 'checking' | 'authorized'; message?: string }
  | { type: 'operation_completed'; operation: 'watch' | 'list' | 'authenticate' }
  | { type: 'groups_loaded'; count: number }
  | { type: 'keyword_matched'; rule_id?: string; keyword: string; prices?: PriceOccurrence[]; decisive?: DecisivePrice | null; eligible?: boolean; reason?: string; group_id: string; group_title: string; message_id: number; sender: string; preview: string }
  | { type: 'alert_sent'; rule_id?: string; keyword: string; group_id: string; message_id: number; decisive?: DecisivePrice | null; elapsed_ms: number }
  | { type: 'dry_run_detected'; rule_id?: string; keyword: string; group_id: string; message_id: number; decisive?: DecisivePrice | null; preview: string }
  | { type: 'rule_filtered'; rule_id: string; keyword: string; group_id: string; message_id: number; prices: PriceOccurrence[]; decisive: DecisivePrice | null; bounds: { min_cents: number | null; max_cents: number | null } | null; reason: FilterReason | string }
  | { type: 'flood_wait'; seconds: number | null }
  | { type: 'sync'; detail: string }
  | { type: 'stats'; messages: number; alerts?: number; by_keyword?: Record<string, number>; uptime_s?: number; last_message?: string | null; last_alert?: string | null; duplicates?: number; matches?: number; filtered?: number; dry_runs?: number; failed?: number }
  | { type: 'error'; code: string; message: string }
) & { at?: string }

/** O que o main encaminha ao renderer por 'bot:event'. */
export type BotInbound =
  | { kind: 'event'; event: BotEvent }
  | { kind: 'raw'; line: string }

export interface CrashInfo {
  code: number | null
  signal: string | null
}

/** Regra de monitoramento (SPEC-PREÇOS §2). Dinheiro sempre em centavos inteiros. */
export interface Rule {
  id: string
  term: string
  enabled: boolean
  min_cents: number | null
  max_cents: number | null
}

export interface ConfigState {
  revision: string
  apiId: string
  apiHashSet: boolean
  apiHashPreview: string
  phone: string
}

export interface ConfigErrors {
  apiId?: string
  apiHash?: string
  phone?: string
  _form?: string
}

export type ConfigSaveResult = { ok: true } | { ok: false; errors: ConfigErrors }

export type StartResult = { ok: true } | { ok: false; error: string }

export interface BotApi {
  catalog<T>(request: CatalogRequest): Promise<T>
  worker(action: 'start' | 'stop' | 'status'): Promise<WorkerStatus>
  listGroups(): Promise<{ groups: WatchedGroup[]; revision: string }>
  reloadGroups(): Promise<{ ok: true; out: string }>
  saveGroups(g: WatchedGroup[], revision: string): Promise<{ groups: WatchedGroup[]; revision: string }>
  getKeywords(): Promise<{ rules: Rule[]; revision: string }>
  saveKeywords(rules: Rule[], revision: string): Promise<{ rules: Rule[]; revision: string }>
  addKeyword(term: string, revision: string): Promise<{ rules: Rule[]; revision: string }>
  startBot(): Promise<StartResult>
  stopBot(): Promise<{ ok: true }>
  isRunning(): Promise<{ running: boolean }>
  getStatus(): Promise<RuntimeStatus>
  getSnapshot(): Promise<AppliedSnapshot>
  authenticate(): Promise<StartResult>
  submitAuth(value: string): Promise<void>
  simulate(text: string, rules: Rule[]): Promise<Simulation>
  onStatus(cb: (status: RuntimeStatus) => void): () => void
  setDirty(dirty: boolean): Promise<void>
  onBotEvent(cb: (msg: BotInbound) => void): () => void
  onBotStopped(cb: () => void): () => void
  onBotCrashed(cb: (info: CrashInfo) => void): () => void
  getConfig(): Promise<ConfigState>
  saveConfig(p: { apiId?: string; apiHash?: string; phone?: string }, revision: string): Promise<ConfigState>
  openExternal(url: string): Promise<{ ok: boolean }>
}

export interface Evaluation {
  rule_id: string; keyword: string; prices: PriceOccurrence[]; decisive: PriceOccurrence | null
  eligible: boolean; reason: string; association?: { ambiguous: boolean; lines: number[] }
}
export interface Simulation { evaluations: Evaluation[]; winner: Evaluation | null; others: Evaluation[] }
