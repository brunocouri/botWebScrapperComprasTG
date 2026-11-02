import { eventToEv, stripAnsi, type Ev } from './activity'
import type { BotInbound } from './ipc'

type FeedEvent = Ev & { id: number; category: string; search: string }
type Snapshot = { events: FeedEvent[]; raw: string[]; total: number }
export class FeedStore {
  private value: Snapshot = { events: [], raw: [], total: 0 }
  private pending: BotInbound[] = []
  private listeners = new Set<() => void>()
  private timer: ReturnType<typeof setTimeout> | null = null
  private id = 0
  subscribe = (cb: () => void) => { this.listeners.add(cb); return () => { this.listeners.delete(cb) } }
  snapshot = () => this.value
  receive(message: BotInbound) {
    this.pending.push(message)
    if (this.pending.length > 1600) this.flush()
    else if (!this.timer) this.timer = setTimeout(() => this.flush(), 50)
  }
  flush() {
    if (this.timer) clearTimeout(this.timer)
    this.timer = null
    const events = [...this.value.events], raw = [...this.value.raw]
    let total = this.value.total
    for (const message of this.pending.splice(0)) {
      if (message.kind === 'raw') { raw.push(stripAnsi(message.line)); total++; continue }
      const ev = eventToEv(message.event)
      if (!ev) continue
      const category = message.event.type === 'keyword_matched' ? 'offers' : message.event.type === 'alert_sent' ? 'sent' : message.event.type === 'rule_filtered' ? 'filtered' : ev.kind === 'error' ? 'errors' : 'other'
      events.push({ ...ev, id: ++this.id, category, search: JSON.stringify(message.event).toLocaleLowerCase('pt-BR') }); total++
    }
    this.value = { events: events.slice(-800), raw: raw.slice(-800), total }
    for (const listener of this.listeners) listener()
  }
  clear() { this.cancelPending(); this.pending = []; this.value = { events: [], raw: [], total: 0 }; for (const cb of this.listeners) cb() }
  cancelPending() { if (this.timer) clearTimeout(this.timer); this.timer = null }
}
