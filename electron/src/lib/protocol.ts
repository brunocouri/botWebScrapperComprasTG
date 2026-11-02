import { StringDecoder } from 'node:string_decoder'
import type { BotEvent } from './ipc'

/** Incremental UTF-8, com descarte da linha inteira após exceder o limite. */
export class LineDecoder {
  private decoder = new StringDecoder('utf8')
  private buffer = ''
  private discarding = false
  private line: (line: string) => void
  private error: (message: string) => void
  private limit: number
  constructor(line: (line: string) => void, error: (message: string) => void = () => {}, limit = 262144) {
    this.line = line; this.error = error; this.limit = limit
  }
  write(chunk: Buffer) { this.consume(this.decoder.write(chunk)) }
  end() { this.consume(this.decoder.end() + '\n') }
  private consume(text: string) {
    for (const part of text.match(/[^\n]*\n|[^\n]+$/g) ?? []) {
      const complete = part.endsWith('\n')
      if (!this.discarding) {
        this.buffer += complete ? part.slice(0, -1) : part
        if (this.buffer.length > this.limit) {
          this.buffer = ''; this.discarding = true; this.error('Linha de protocolo excedeu o limite.')
        }
      }
      if (complete) {
        if (!this.discarding && this.buffer.trim()) this.line(this.buffer.replace(/\r$/, ''))
        this.buffer = ''; this.discarding = false
      }
    }
  }
}

const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const numeric = (v: unknown) => typeof v === 'number' && Number.isFinite(v)
const text = (v: unknown) => typeof v === 'string'
const price = (v: unknown) => v == null || (object(v) && numeric(v.cents) &&
  ['por', 'vista', 'parcela', 'de', 'avulso', 'frete'].includes(String(v.kind)) &&
  (v.kind !== 'parcela' || (numeric(v.installments) && numeric(v.installment_cents) && numeric(v.total_cents))))

/** Dados do subprocesso são unknown; tipos TypeScript não validam JSON. */
export function parseBotEvent(value: unknown): BotEvent | null {
  if (!object(value)) return null
  const v = value
  if (v.at !== undefined && (typeof v.at !== 'string' || !Number.isFinite(Date.parse(v.at)))) return null
  let valid = false
  switch (v.type) {
    case 'telegram_connecting': case 'telegram_connected': case 'telegram_syncing': valid = true; break
    case 'monitoring_started': valid = !v.snapshot || (object(v.snapshot) && text(v.snapshot.revision) && numeric(v.snapshot.groups) && numeric(v.snapshot.rules)); break
    case 'bot_started': valid = numeric(v.groups) && Array.isArray(v.keywords) && v.keywords.every(text); break
    case 'session_authenticated': valid = text(v.name) && numeric(v.user_id); break
    case 'keyword_matched': valid = text(v.keyword) && text(v.group_id) && numeric(v.message_id) && text(v.group_title) && text(v.preview) && price(v.decisive); break
    case 'alert_sent': valid = text(v.keyword) && text(v.group_id) && numeric(v.message_id) && numeric(v.elapsed_ms) && price(v.decisive); break
    case 'dry_run_detected': valid = text(v.keyword) && text(v.preview) && text(v.group_id) && numeric(v.message_id) && price(v.decisive); break
    case 'rule_filtered': valid = text(v.rule_id) && text(v.keyword) && text(v.reason) && text(v.group_id) && numeric(v.message_id) && Array.isArray(v.prices) && v.prices.every(price) && price(v.decisive) && (v.bounds == null || (object(v.bounds) && (v.bounds.min_cents == null || numeric(v.bounds.min_cents)) && (v.bounds.max_cents == null || numeric(v.bounds.max_cents)))); break
    case 'stats': valid = numeric(v.messages) && (v.alerts === undefined || numeric(v.alerts)); break
    case 'sync': valid = text(v.detail); break
    case 'error': valid = text(v.code) && text(v.message); break
    case 'flood_wait': valid = v.seconds === null || numeric(v.seconds); break
    case 'connection_state': valid = typeof v.connected === 'boolean'; break
    case 'auth_step': valid = ['code', 'password', 'checking', 'authorized'].includes(String(v.step)); break
    case 'operation_completed': valid = ['watch', 'list', 'authenticate'].includes(String(v.operation)); break
    case 'groups_loaded': valid = numeric(v.count); break
  }
  return valid ? v as unknown as BotEvent : null
}
