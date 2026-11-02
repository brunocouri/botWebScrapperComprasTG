// Camada de apresentação da Atividade — pura, sem React.
// O store (events/rawLog) vive no App (montado durante toda a sessão);
// a página Atividade é só view. Navegar nunca limpa: ver activity.test.ts.
import type { BotEvent, DecisivePrice } from './ipc'
import { formatBRL } from './money'

export type EvKind = 'info' | 'ok' | 'warn' | 'error'
export type Ev = { ts: string; kind: EvKind; title: string; detail?: string; raw: string }

export { formatBRL }

function decisiveText(d: DecisivePrice): string {
  if (d.kind === 'parcela' && d.installments != null && d.installment_cents != null && d.total_cents != null) {
    return `${d.installments}x de R$ ${formatBRL(d.installment_cents)} (total R$ ${formatBRL(d.total_cents)})`
  }
  return `R$ ${formatBRL(d.cents)}${d.kind === 'vista' ? ' (à vista)' : ''}`
}

/** Protocolo -> view. Tipo desconhecido retorna null e nunca derruba o app. */
export function eventToEv(ev: BotEvent): Ev | null {
  const ts = new Date(ev.at ?? Date.now()).toLocaleTimeString('pt-BR', { hour12: false })
  const raw = JSON.stringify(ev)
  switch (ev.type) {
    case 'bot_started':
      return { ts, kind: 'ok', title: 'Bot iniciado', detail: `Monitorando ${ev.groups} grupos · ${ev.keywords.join(', ') || 'nenhuma keyword'}`, raw }
    case 'telegram_connecting':
      return { ts, kind: 'info', title: 'Conectando ao Telegram…', raw }
    case 'telegram_connected':
      return { ts, kind: 'ok', title: 'Telegram conectado', raw }
    case 'telegram_syncing':
      return { ts, kind: 'info', title: 'Sincronizando mensagens', raw }
    case 'session_authenticated':
      return { ts, kind: 'ok', title: 'Sessão validada', detail: `Conectado como ${ev.name}`, raw }
    case 'monitoring_started':
      return { ts, kind: 'info', title: 'Monitoramento ativo', detail: 'Aguardando mensagens…', raw }
    case 'keyword_matched':
      return {
        ts, kind: 'ok', title: `Oferta encontrada · ${ev.keyword.toUpperCase()}${ev.decisive ? ` · ${decisiveText(ev.decisive)}` : ''}`,
        detail: `${ev.group_title} — ${ev.preview}`, raw,
      }
    case 'alert_sent':
      return { ts, kind: 'ok', title: 'Alerta enviado para Mensagens Salvas', detail: `${ev.keyword.toUpperCase()} · ${ev.elapsed_ms}ms`, raw }
    case 'dry_run_detected':
      return { ts, kind: 'info', title: `Detectado · ${ev.keyword.toUpperCase()} (teste, não enviado)`, detail: ev.preview, raw }
    case 'rule_filtered': {
      if (ev.reason === 'ambiguous_price') return { ts, kind: 'info', title: `Preço ambíguo · ${ev.keyword.toUpperCase()}`, detail: 'Não foi possível associar o preço ao produto. Alerta não enviado.', raw }
      const price = ev.decisive ? decisiveText(ev.decisive) : null
      if (ev.reason === 'superseded') {
        return { ts, kind: 'info', title: `Ignorada · ${ev.keyword.toUpperCase()}`, detail: 'Outra regra de maior prioridade foi aplicada', raw }
      }
      if (ev.reason === 'no_price') {
        return { ts, kind: 'info', title: `Fora da faixa · ${ev.keyword.toUpperCase()}`, detail: 'Nenhum preço encontrado', raw }
      }
      const bound = ev.reason === 'above_max' && ev.bounds?.max_cents != null
        ? `máximo R$ ${formatBRL(ev.bounds.max_cents)}`
        : ev.reason === 'below_min' && ev.bounds?.min_cents != null
          ? `mínimo R$ ${formatBRL(ev.bounds.min_cents)}`
          : null
      return {
        ts, kind: 'info',
        title: `Fora da faixa · ${ev.keyword.toUpperCase()}`,
        detail: [price, bound ? `${ev.reason === 'below_min' ? '<' : '>'} ${bound}` : null].filter(Boolean).join(' ') || undefined,
        raw,
      }
    }
    case 'flood_wait':
      return { ts, kind: 'warn', title: `Telegram pediu espera${ev.seconds != null ? ` · ${ev.seconds}s` : ''}`, detail: 'Aguardando antes de reenviar', raw }
    case 'sync':
      return { ts, kind: 'info', title: ev.detail || 'Sincronizando…', raw }
    case 'stats':
      return { ts, kind: 'info', title: `Resumo · ${ev.messages} mensagens verificadas`, detail: ev.alerts != null ? `${ev.alerts} alertas` : undefined, raw }
    case 'error':
      return { ts, kind: 'error', title: 'Erro', detail: `${ev.code}: ${ev.message}`.slice(0, 200), raw }
    default:
      return null
  }
}

export const BUFFER_LIMIT = 800

/** Acrescenta sem mutar e sem depender de página/view — regressão do sumiço ao navegar. */
export function appendBounded<T>(list: T[], item: T, limit = BUFFER_LIMIT): T[] {
  return [...list.slice(-(limit - 1)), item]
}

export const stripAnsi = (s: string) =>
  // eslint-disable-next-line no-control-regex -- remoção intencional de escapes ANSI
  s.replace(/\x1b\[[0-9;]*m/g, '').replace(/\x1b\[[0-9;]*[A-Za-z]/g, '')

export const cleanText = (s: string) =>
  stripAnsi(s)
    .replace(/�/g, '')
    .replace(/\s+/g, ' ')
    .trim()

export function parseLine(m: string): Ev | null {
  const c = cleanText(m)
  if (!c) return null
  if (/UserWarning|warnings\.warn|async sessions support is an experimental/i.test(c)) return null
  const tm = c.match(/(\d{2}:\d{2}:\d{2})/)
  const ts = tm ? tm[1] : new Date().toTimeString().slice(0, 8)
  const body = c.replace(/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[,.]\d+\s*\|\s*\w+\s*\|\s*/, '').trim()

  if (/Connecting to/i.test(body) && !/complete/i.test(body)) return { ts, kind: 'info', title: 'Conectando ao Telegram…', raw: c }
  if (/Connection to .* complete/i.test(body)) return { ts, kind: 'ok', title: 'Telegram conectado', raw: c }
  if (/Disconnecting|Disconnection|Not disconnecting/i.test(body)) return null
  if (/\[SESSAO\]|Sess[aã]o v[aá]lida/i.test(body)) {
    const who = body.match(/como\s+([^(]+)\s*\(?(\d+)?/)
    return { ts, kind: 'ok', title: 'Sessão validada', detail: who ? `Conectado como ${who[1].trim()}` : undefined, raw: c }
  }
  if (/\[OK\] Bot iniciado/i.test(body)) {
    const g = body.match(/(\d+)\s+grupos?/)
    const k = body.match(/(\d+)\s+keywords?:\s*([^|]+)/i)
    return { ts, kind: 'ok', title: 'Bot iniciado', detail: `Monitorando ${g ? g[1] : '?'} grupos · ${k ? k[2].trim() : ''}`, raw: c }
  }
  if (/grupos resolvidos/i.test(body)) return null
  if (/Monitoramento iniciado/i.test(body)) return { ts, kind: 'info', title: 'Monitoramento ativo', detail: 'Aguardando mensagens…', raw: c }
  if (/Sincronizando/i.test(body)) {
    const lote = /lote|canais/i.test(body)
    const nm = body.match(/Sincronizando\s+(.+?)\s*\(/)
    return { ts, kind: 'info', title: lote ? 'Sincronizando canais…' : nm ? `Sincronizando ${nm[1].trim()}…` : 'Sincronizando…', raw: c }
  }
  if (/Got difference for account/i.test(body)) return { ts, kind: 'info', title: 'Sincronizando conta…', raw: c }
  if (/Got difference/i.test(body)) return null
  if (/\[ALERTA\].*MATCH/i.test(body)) {
    const kwm = body.match(/MATCH\s+'([^']+)'/i)
    const gr = body.match(/em\s+\[([^\]]+)\]/)
    const preview = body.match(/"([^"]{1,140})/)
    return { ts, kind: 'ok', title: `Oferta encontrada${kwm ? ` · ${kwm[1].toUpperCase()}` : ''}`, detail: `${gr ? gr[1] : ''}${preview ? ` — ${preview[1]}` : ''}`, raw: c }
  }
  if (/Alerta enviado/i.test(body)) {
    const d = body.match(/em\s+(\d+)ms\s*[—-]\s*(.*)/)
    return { ts, kind: 'ok', title: 'Alerta enviado para Mensagens Salvas', detail: d ? d[2].trim() : undefined, raw: c }
  }
  if (/\[DRY\]|DRY-RUN|Dry-run/i.test(body)) {
    const kwm = body.match(/'([^']+)'/)
    return { ts, kind: 'info', title: `Detectado${kwm ? ` · ${kwm[1].toUpperCase()}` : ''} (teste, não enviado)`, raw: c }
  }
  if (/\[AGUARDE\]|FloodWait|Telegram pediu espera/i.test(body)) {
    const s = body.match(/(\d+)\s*s/)
    return { ts, kind: 'warn', title: `Telegram pediu espera${s ? ` · ${s[1]}s` : ''}`, detail: 'Aguardando antes de reenviar', raw: c }
  }
  if (/\[STATS\]/i.test(body)) {
    const mg = body.match(/(\d+)\s+msgs?/)
    const al = body.match(/(\d+)\s+alertas?/)
    return { ts, kind: 'info', title: `Resumo · ${mg ? mg[1] : '?'} mensagens verificadas`, detail: al ? `${al[1]} alertas` : undefined, raw: c }
  }
  if (/Duplicado ignorado/i.test(body)) return null
  if (/\[ERRO\]|Falha|Traceback|Error/i.test(body)) return { ts, kind: 'error', title: 'Erro', detail: body.slice(0, 160), raw: c }
  if (/\[AVISO\]|Parado pelo usuario/i.test(body)) return { ts, kind: 'warn', title: body.slice(0, 90), raw: c }
  if (/Recarregar|Gerado .* grupos/i.test(body)) return null
  return { ts, kind: 'info', title: body.slice(0, 110), raw: c }
}
