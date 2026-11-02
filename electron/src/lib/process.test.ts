import { EventEmitter } from 'node:events'
import { PassThrough } from 'node:stream'
import { describe, it, expect, vi } from 'vitest'
import { ProcessController } from './process'

function child() {
  return Object.assign(new EventEmitter(), { stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(), kill: vi.fn(), exitCode: null })
}
describe('processo exclusivo', () => {
  it('parada espera close e recusa start até colher o filho', async () => {
    const proc = child(), report = vi.fn()
    const controller = new ProcessController(() => proc as never, report, 100)
    expect(controller.start('watch')).toBe(true)
    const stopped = controller.stop()
    expect(controller.busy).toBe(true)
    expect(controller.start('watch')).toBe(false)
    proc.emit('close', 0, null)
    await stopped
    expect(controller.busy).toBe(false)
    expect(report).toHaveBeenCalledWith('stopped', expect.anything())
  })
  it('erro no spawn resolve parada sem falso processo vivo', async () => {
    const proc = child(), report = vi.fn()
    const controller = new ProcessController(() => proc as never, report, 100)
    controller.start('watch')
    proc.emit('error', new Error('python ausente'))
    expect(controller.busy).toBe(false)
    expect(report).toHaveBeenCalledWith('crashed', expect.anything())
  })
})
