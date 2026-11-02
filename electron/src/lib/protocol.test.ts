import { describe, expect, it } from 'vitest'
import { LineDecoder, parseBotEvent } from './protocol'

describe('fronteira JSONL', () => {
  it('remonta UTF-8 e linhas em chunks diferentes', () => {
    const lines: string[] = []
    const decoder = new LineDecoder(s => lines.push(s))
    const bytes = Buffer.from('{"type":"sync","detail":"Sessão"}\n')
    const index = bytes.indexOf(Buffer.from('ã')) + 1
    decoder.write(bytes.subarray(0, index))
    decoder.write(bytes.subarray(index))
    decoder.end()
    expect(lines).toEqual(['{"type":"sync","detail":"Sessão"}'])
  })
  it('rejeita shape malformado e tipo desconhecido', () => {
    expect(parseBotEvent({ type: 'bot_started', groups: 1 })).toBeNull()
    expect(parseBotEvent({ type: 'novo' })).toBeNull()
    expect(parseBotEvent({ type: 'stats', messages: 'oops' })).toBeNull()
    expect(parseBotEvent({ type: 'sync', detail: 'ok' })?.type).toBe('sync')
  })
  it('limita linha sem deixar fragmento virar um evento', () => {
    const lines: string[] = [], errors: string[] = []
    const decoder = new LineDecoder(s => lines.push(s), s => errors.push(s), 20)
    decoder.write(Buffer.from('x'.repeat(30)))
    decoder.write(Buffer.from('resto\nvalida\n'))
    expect(lines).toEqual(['valida'])
    expect(errors).toHaveLength(1)
  })
})
