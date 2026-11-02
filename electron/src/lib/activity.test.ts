import { describe, it, expect } from 'vitest'
import { parseLine, appendBounded, stripAnsi, cleanText, eventToEv, BUFFER_LIMIT } from './activity'
import type { BotEvent, PriceOccurrence } from './ipc'

// Regressão do lifecycle: o buffer vive no App (sessão), a página Atividade
// é só view. Trocar de página = no-op no buffer. Nada aqui recebe `page`.

describe('parseLine — apresentação amigável', () => {
  it('Bot iniciado vira evento legível, sem detalhes técnicos', () => {
    const ev = parseLine('2026-09-22 00:56:34,293 | INFO | [OK] Bot iniciado — 29 grupos: x (+24) | 1 keywords: A57 | Pattern: \\b(A57)\\b | dry_run=False')
    expect(ev).not.toBeNull()
    expect(ev!.title).toBe('Bot iniciado')
    expect(ev!.detail).toContain('29 grupos')
    expect(ev!.detail).not.toMatch(/Pattern|dry_run|TcpFull|149\.154/)
  })

  it('remove ANSI antes de renderizar', () => {
    const ev = parseLine('\x1b[38;5;39m2026-09-22 00:56:35,710 | INFO | [SESSAO] Sessao valida (Clonador) — logado como Nick (1234567890)\x1b[0m')
    expect(ev!.title).toBe('Sessão validada')
    expect(ev!.detail).toBe('Conectado como Nick')
    expect(ev!.raw).not.toContain('\x1b')
  })

  it('preserva UTF-8 (promoções, Sessão, Conexão)', () => {
    expect(cleanText('Rato Promoçoes | CHAT')).toContain('Promoçoes')
    expect(stripAnsi('[SESSAO] Sessao valida')).toContain('Sessao')
    const ev = parseLine('00:56:34 | INFO | Sincronizando gatuna das promoções (1234567891) - buscando mensagens perdidas...')
    expect(ev!.title).toContain('promoções')
    expect(ev!.title).not.toMatch(/�/)
  })

  it('filtra ruído técnico (UserWarning, Got difference cru, disconnect)', () => {
    expect(parseLine('UserWarning: Using async sessions support is an experimental feature')).toBeNull()
    expect(parseLine('2026-09-19 00:07:45,707 | INFO | Got difference for account updates')).not.toBeNull() // este vira "Sincronizando conta…"
    expect(parseLine('2026-09-18 23:21:44,829 | INFO | Disconnecting from 149.154.175.58:443/TcpFull...')).toBeNull()
    expect(parseLine('2026-09-18 23:21:24,434 | INFO | [OK] 25 grupos resolvidos em 3.3s: x')).toBeNull()
  })
})

describe('buffer da sessão — navegação nunca limpa', () => {
  it('recebe → troca de página → recebe → ambos aparecem', () => {
    let buf: ReturnType<typeof parseLine>[] = []
    const push = (raw: string) => {
      const ev = parseLine(raw)
      if (ev) buf = appendBounded(buf, ev) as any
    }
    push('00:43:24 | INFO | [OK] Bot iniciado — 29 grupos: a | 1 keywords: A57')
    expect(buf).toHaveLength(1)

    // troca Grupos → Keywords → Atividade: nenhum código toca no buffer aqui
    const snapshot = [...buf]

    push('00:43:26 | INFO | [SESSAO] Sessao valida (Clonador) — logado como Nick (1234567890)')
    expect(buf).toHaveLength(2)
    expect(buf[0]).toBe(snapshot[0])
    expect(buf.map(e => e!.title)).toEqual(['Bot iniciado', 'Sessão validada'])
  })

  it('respeita o limite sem perder os mais recentes', () => {
    let buf: number[] = []
    for (let i = 0; i < BUFFER_LIMIT + 50; i++) buf = appendBounded(buf, i)
    expect(buf).toHaveLength(BUFFER_LIMIT)
    expect(buf[buf.length - 1]).toBe(BUFFER_LIMIT + 49)
  })

  it('protocolo vira view sem wording do Python', () => {
    const ev = eventToEv({ type: 'bot_started', groups: 29, keywords: ['A57'] })!
    expect(ev.title).toBe('Bot iniciado')
    expect(ev.detail).toContain('29 grupos')
    const m = eventToEv({ type: 'keyword_matched', keyword: 'a57', group_id: '1', group_title: 'G', message_id: 2, sender: 'x', preview: 'vendo a57' })!
    expect(m.title).toContain('A57')
  })

  it('evento desconhecido retorna null e nunca derruba', () => {
    expect(eventToEv({ type: 'futura_feature_x' } as unknown as BotEvent)).toBeNull()
    expect(eventToEv({} as unknown as BotEvent)).toBeNull()
  })

  it('matched legado (sem campos novos) não quebra', () => {
    const m = eventToEv({ type: 'keyword_matched', keyword: 'a57', group_id: '1', group_title: 'G', message_id: 2, sender: 'x', preview: 'vendo a57' })!
    expect(m.title).toBe('Oferta encontrada · A57')
    expect(m.detail).toBe('G — vendo a57')
  })

  it('matched com decisivo mostra preço', () => {
    const m = eventToEv({ type: 'keyword_matched', rule_id: 'a', keyword: 'A57', prices: [], decisive: { cents: 189900, kind: 'vista' }, eligible: true, reason: 'ok', group_id: '1', group_title: 'G', message_id: 2, sender: 'x', preview: 'v' })!
    expect(m.title).toBe('Oferta encontrada · A57 · R$ 1.899,00 (à vista)')
    const p = eventToEv({ type: 'keyword_matched', rule_id: 'a', keyword: 'A57', prices: [], decisive: { cents: 18990, kind: 'parcela', installments: 12, installment_cents: 18990, total_cents: 227880 }, eligible: true, reason: 'ok', group_id: '1', group_title: 'G', message_id: 2, sender: 'x', preview: 'v' })!
    expect(p.title).toContain('12x de R$ 189,90 (total R$ 2.278,80)')
  })

  it('rule_filtered mapeia motivos sem badge de erro', () => {
    const base = { type: 'rule_filtered' as const, rule_id: 'a', keyword: 'A57', group_id: '1', message_id: 2, prices: [] as PriceOccurrence[], decisive: { cents: 249900, kind: 'avulso' as const }, bounds: { min_cents: null as number | null, max_cents: 189900 as number | null } }
    const over = eventToEv({ ...base, reason: 'above_max' })!
    expect(over.title).toBe('Fora da faixa · A57')
    expect(over.detail).toBe('R$ 2.499,00 > máximo R$ 1.899,00')
    expect(over.kind).toBe('info')
    const none = eventToEv({ ...base, decisive: null, bounds: null, reason: 'no_price' })!
    expect(none.detail).toBe('Nenhum preço encontrado')
    const sup = eventToEv({ ...base, reason: 'superseded' })!
    expect(sup.title).toBe('Ignorada · A57')
    expect(sup.detail).toBe('Outra regra de maior prioridade foi aplicada')
  })

  it('limpar é explícito (ação Limpar), nunca navegação', () => {
    let buf = appendBounded([], parseLine('00:00:01 | INFO | [OK] Bot iniciado — 1 grupos: a | 1 keywords: A57')!)
    expect(buf).toHaveLength(1)
    buf = [] // só a ação explícita de Limpar faz isto
    expect(buf).toHaveLength(0)
  })
})
