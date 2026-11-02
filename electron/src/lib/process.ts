import type { ChildProcessWithoutNullStreams } from 'node:child_process'

export type Operation = 'watch' | 'list' | 'authenticate'
export type Outcome = { code: number | null; signal: string | null; operation: Operation }

/** O processo continua pertencendo à instância até close/error. */
export class ProcessController {
  child: ChildProcessWithoutNullStreams | null = null
  completed = false
  private stopping = false
  private timer: ReturnType<typeof setTimeout> | null = null
  private done: Promise<Outcome> = Promise.resolve({ code: 0, signal: null, operation: 'watch' })
  private spawn: (operation: Operation) => ChildProcessWithoutNullStreams
  private report: (kind: 'stopped' | 'crashed' | 'completed', info: Outcome) => void
  private grace: number
  constructor(spawn: (operation: Operation) => ChildProcessWithoutNullStreams,
    report: (kind: 'stopped' | 'crashed' | 'completed', info: Outcome) => void, grace = 5000) {
    this.spawn = spawn; this.report = report; this.grace = grace
  }
  get busy() { return this.child !== null }
  start(operation: Operation) {
    if (this.busy) return false
    this.stopping = false; this.completed = false
    const proc = this.spawn(operation)
    this.child = proc
    this.done = new Promise(resolve => {
      let finished = false
      const finish = (code: number | null, signal: string | null) => {
        if (finished || this.child !== proc) return
        finished = true
        if (this.timer) clearTimeout(this.timer)
        this.timer = null
        const outcome = { code, signal, operation }
        const kind = this.stopping ? 'stopped' : this.completed && code === 0 ? 'completed' : 'crashed'
        this.child = null
        this.report(kind, outcome)
        resolve(outcome)
      }
      proc.once('error', () => finish(null, 'spawn-error'))
      proc.once('close', (code, signal) => finish(code, signal))
    })
    return true
  }
  send(payload: unknown) {
    if (!this.child || this.stopping) throw new Error('Nenhuma operação disponível.')
    this.child.stdin.write(JSON.stringify(payload) + '\n')
  }
  async wait() { return this.done }
  async stop() {
    if (!this.child) return
    if (!this.stopping) {
      this.stopping = true
      const proc = this.child
      if (proc.stdin.writable) proc.stdin.write('{"command":"stop"}\n')
      this.timer = setTimeout(() => { if (this.child === proc) proc.kill() }, this.grace)
    }
    // Nunca liberar referência por timeout; só close/error autoriza reinício.
    await this.done
  }
}
