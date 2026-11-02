import { describe, expect, it } from 'vitest'
import path from 'node:path'
import { runtimePaths } from './runtime-paths'

describe('runtime Windows distribuído', () => {
  const input = { packaged: true, resources: path.resolve('Program Files/ComprasTG/resources'), source: path.resolve('source'), userData: path.resolve('profile/ComprasTG') }

  it('usa Python e scripts externos ao ASAR e dados no perfil', () => {
    const result = runtimePaths(input)
    expect(result.backend).toBe(path.join(input.resources, 'backend'))
    expect(result.python).toBe(path.join(input.resources, 'backend', 'python.exe'))
    expect(result.data).toBe(path.join(input.userData, 'data'))
    expect(result.data.startsWith(input.resources)).toBe(false)
  })

  it('preserva o diretório explícito de dados', () => {
    expect(runtimePaths({ ...input, data: path.resolve('custom data') }).data).toBe(path.resolve('custom data'))
  })

  it('mantém desenvolvimento por PATH e dados na raiz', () => {
    expect(runtimePaths({ ...input, packaged: false })).toEqual({ backend: input.source, python: 'python', data: input.source })
  })
})
