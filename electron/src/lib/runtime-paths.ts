import path from 'node:path'

export function runtimePaths(input: { packaged: boolean; resources: string; source: string; userData: string; data?: string }) {
  const backend = input.packaged ? path.join(input.resources, 'backend') : input.source
  return {
    backend,
    python: input.packaged ? path.join(backend, 'python.exe') : 'python',
    data: input.data || (input.packaged ? path.join(input.userData, 'data') : input.source),
  }
}
