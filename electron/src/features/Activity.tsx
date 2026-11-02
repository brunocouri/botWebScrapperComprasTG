import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import type { RuntimeState } from '../lib/ipc'
import type { FeedStore } from '../lib/feed-store'

export function Activity({ store, status }: { store: FeedStore; status: RuntimeState }) {
  const data = useSyncExternalStore(store.subscribe, store.snapshot)
  const [filter, setFilter] = useState('all'), [query, setQuery] = useState(''), [technical, setTechnical] = useState(false)
  const [following, setFollowing] = useState(true), [copyMessage, setCopyMessage] = useState(''), [seen, setSeen] = useState(data.total)
  const list = useRef<HTMLDivElement>(null)
  const filtered = data.events.filter(e => (filter === 'all' || e.category === filter) && e.search.includes(query.trim().toLocaleLowerCase('pt-BR')))
  useEffect(() => { if (following && list.current) list.current.scrollTop = list.current.scrollHeight }, [data, following, technical, filter, query])
  const unread = following ? 0 : Math.max(0, data.total - seen)
  async function copy() {
    try {
      await navigator.clipboard.writeText(technical ? data.raw.join('\n') : filtered.map(e => `${e.ts} ${e.title}${e.detail ? ' — ' + e.detail : ''}`).join('\n'))
      setCopyMessage('Logs do buffer copiados.')
    } catch { setCopyMessage('Não foi possível copiar. Selecione o texto no modo técnico.') }
  }
  return <section className="activity"><div className="activity-tools"><label>Mostrar<select value={filter} onChange={e => setFilter(e.target.value)}><option value="all">Toda atividade</option><option value="offers">Ofertas</option><option value="sent">Enviados</option><option value="filtered">Filtrados</option><option value="errors">Erros</option></select></label><label>Buscar atividade<input value={query} onChange={e => setQuery(e.target.value)} placeholder="Termo ou grupo" /></label><label className="check"><input type="checkbox" checked={technical} onChange={e => setTechnical(e.target.checked)} />Modo técnico</label><button onClick={() => store.clear()}>Limpar buffer</button><button onClick={() => void copy()}>Copiar logs</button></div>
    <div className="activity-info"><span>Até 800 registros por modo nesta sessão</span><label className="check"><input type="checkbox" checked={following} onChange={e => { setSeen(data.total); setFollowing(e.target.checked) }} />Acompanhar novos eventos</label></div>
    {copyMessage && <p role="status">{copyMessage}</p>}
    <div ref={list} className={'feed ' + (technical ? 'technical' : '')} aria-label={technical ? 'Logs técnicos' : 'Eventos de atividade'} onScroll={e => {
      const node = e.currentTarget, bottom = node.scrollHeight - node.scrollTop - node.clientHeight < 32
      if (!bottom && following) { setSeen(data.total); setFollowing(false) }
      else if (bottom && !following) setFollowing(true)
    }}>
      {technical ? <pre>{data.raw.join('\n') || 'Sem logs técnicos neste buffer.'}</pre> : filtered.length ? filtered.map(e => <details className={'feed-row kind-' + e.kind} key={e.id}><summary><time>{e.ts}</time><span><strong>{e.title}</strong>{e.detail && <small>{e.detail}</small>}</span></summary><pre>{JSON.stringify(JSON.parse(e.raw), null, 2)}</pre></details>) : <div className="empty"><strong>{query || filter !== 'all' ? 'Nenhum evento corresponde ao filtro' : status === 'monitoring' ? 'Aguardando mensagens' : 'Sem atividade nesta sessão'}</strong><p>{status === 'monitoring' ? 'O monitor está ativo. Novos eventos aparecerão aqui.' : 'Inicie o monitor ou ajuste o filtro para acompanhar os eventos.'}</p></div>}
    </div>
    {!following && <button className="new-events" onClick={() => { setSeen(data.total); setFollowing(true) }}>{unread ? `${unread} novos eventos — ` : ''}Voltar ao final</button>}
  </section>
}
