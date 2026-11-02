import { useEffect, useState } from 'react'
import type { Delivery, ReprocessJob, Review } from '../lib/catalog'

export function DeliveryHistory() {
  const [rows, setRows] = useState<Delivery[]>([]), [error, setError] = useState('')
  const load = () => { void window.api.catalog<Delivery[]>({ action: 'deliveries' }).then(setRows).catch(e => setError(String(e))) }
  const labels: Record<string, string> = { ready: 'Aguardando envio', claimed: 'Em envio ou sem confirmação após interrupção', sent: 'Enviado', failed: 'Falhou', dry_run: 'Simulado', suppressed: 'Suprimido por mudança de regra ou mensagem' }
  return <details className="catalog-reprocess"><summary onClick={load}>Histórico dos últimos 50 alertas estruturados</summary>{error && <p role="alert">{error}</p>}<button onClick={load}>Atualizar entregas</button>{rows.map(r => <p key={r.id}>{r.rule_name} · {labels[r.state] ?? r.state} · {new Date(r.created_at).toLocaleString('pt-BR')}{r.error ? ` · ${r.error}` : ''}</p>)}{!rows.length && <p>Nenhuma entrega registrada.</p>}</details>
}

export function ReprocessHistory({ refresh }: { refresh: number }) {
  const [rows, setRows] = useState<ReprocessJob[]>([]), [reload, setReload] = useState(0), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  useEffect(() => { let live = true; void window.api.catalog<ReprocessJob[]>({ action: 'reprocess:list' }).then(d => { if (live) setRows(d) }).catch(e => { if (live) setError(String(e)) }); return () => { live = false } }, [refresh, reload])
  return <section className="catalog-reprocess"><h3>Reprocessamentos recentes</h3><button onClick={() => setReload(n => n + 1)}>Atualizar progresso</button>{error && <p role="alert">{error}</p>}{rows.map(r => <div className="catalog-row" key={r.token}><p>{new Date(r.created_at).toLocaleString('pt-BR')} · {r.done} concluídas · {r.pending} pendentes · {r.cancelled} canceladas de {r.total}</p>{(r.pending > 0 || r.cancelled > 0) && <button disabled={busy} onClick={() => { setBusy(true); void window.api.catalog({ action: r.pending > 0 ? 'reprocess:cancel' : 'reprocess:resume', token: r.token }).then(() => setReload(n => n + 1)).catch(e => setError(String(e))).finally(() => setBusy(false)) }}>{r.pending > 0 ? 'Cancelar restante deste lote' : 'Retomar restante deste lote'}</button>}</div>)}</section>
}

export function ReviewExamples({ review, open, changed }: { review: Review; open: (n: number) => Promise<void>; changed: () => void }) {
  const [items, setItems] = useState<{ id: number; text: string; published_at: string }[]>([]), [error, setError] = useState('')
  return <details><summary onClick={() => { void window.api.catalog<typeof items>({ action: 'review:examples', source_id: review.source_id, reason: review.reason, signature: review.signature }).then(setItems).catch(e => setError(String(e))) }}>Ver até 25 exemplos deste agrupamento</summary>{error && <p role="alert">{error}</p>}{items.map(m => <div className="catalog-row" key={m.id}><p>{m.text.slice(0, 240)}</p><div className="actions"><button onClick={() => void open(m.id)}>Abrir esta mensagem</button><button onClick={() => { void window.api.catalog({ action: 'review:split', id: m.id }).then(changed).catch(e => setError(String(e))) }}>Separar esta mensagem do agrupamento</button></div></div>)}</details>
}

export function SourceHistory({ id }: { id: number }) {
  const [items, setItems] = useState<{ at: string; kind: string }[]>([]), [error, setError] = useState('')
  const labels: Record<string, string> = { start: 'Arquivamento habilitado', pause: 'Pausa', recover: 'Retomada com recuperação da pausa', now: 'Novo intervalo sem recuperar a pausa' }
  return <details><summary onClick={() => { void window.api.catalog<typeof items>({ action: 'source:history', id }).then(setItems).catch(e => setError(String(e))) }}>Histórico de coleta</summary>{error && <p role="alert">{error}</p>}{items.map((v, i) => <p key={i}>{new Date(v.at).toLocaleString('pt-BR')} · {labels[v.kind] ?? v.kind}</p>)}</details>
}
