import { useCallback, useEffect, useRef, useState } from 'react'
import type { WatchedGroup } from '../lib/ipc'
import type { ArchivedMessage, CatalogRequest, CatalogStatus, Extraction, FieldDefinition, FieldMapping, FieldType, LinkSettings, MessageDetail, OfferRecord, Page, ReprocessPreview, Review, Source, Template, TemplateEntry, ValueFilter, WorkerStatus } from '../lib/catalog'
import { formatBRL } from '../lib/money'
import { numericBounds } from '../lib/catalog-filters'
import { StructuredAlerts } from './StructuredAlerts'
import { ReprocessHistory, ReviewExamples, SourceHistory } from './CatalogHistory'

const request = <T,>(payload: CatalogRequest) => window.api.catalog<T>(payload)
const reason: Record<string, string> = { unknown_format: 'Formato desconhecido', ambiguous_template: 'Modelos conflitantes', extraction_error: 'Campo obrigatório ausente ou inválido', ambiguous_field: 'Campo ambíguo', no_text: 'Mídia sem texto', done: 'Interpretada', ignored: 'Sem oferta', input_limit: 'Limite de processamento' }
const typeNames: Record<FieldType, string> = { text: 'Texto', money: 'Dinheiro (R$)', number: 'Número', condition: 'Condição', category: 'Categoria', link: 'Link', installments: 'Parcelamento' }
const date = (v: string) => new Date(v).toLocaleString('pt-BR')
const errorText = (e: unknown) => e instanceof Error ? e.message : String(e)
const emptyStatus: CatalogStatus = { messages: 0, revisions: 0, pending: 0, offers: 0, reviews: 0, runs: 0, bytes: 0, sources: [] }
type View = 'capture' | 'archive' | 'templates' | 'reviews' | 'offers' | 'stores' | 'alerts'
const viewNames: Record<View, string> = { capture: 'Coleta', archive: 'Acervo', templates: 'Modelos', reviews: 'Pendências', offers: 'Ofertas', stores: 'Lojas e links', alerts: 'Alertas estruturados' }

function Input({ label, value, change, multiline = false, required = false }: { label: string; value: string; change: (value: string) => void; multiline?: boolean; required?: boolean }) {
  return <label className="field">{label}{multiline ? <textarea value={value} required={required} onChange={e => change(e.target.value)} /> : <input value={value} required={required} onChange={e => change(e.target.value)} />}</label>
}
function Pager({ total, offset, change }: { total: number; offset: number; change: (n: number) => void }) {
  return <div className="actions catalog-pager"><span>{total ? `${offset + 1}–${Math.min(offset + 25, total)} de ${total}` : 'Nenhum resultado'}</span><button disabled={!offset} onClick={() => change(Math.max(0, offset - 25))}>Anterior</button><button disabled={offset + 25 >= total} onClick={() => change(offset + 25)}>Próxima</button></div>
}
function displayValue(value: unknown): string {
  if (Array.isArray(value)) return value.map(displayValue).join('; ')
  if (value === 'present') return 'Presente'
  if (value === 'absent') return 'Ausente'
  if (value && typeof value === 'object') {
    const item = value as Record<string, unknown>
    if (typeof item.url === 'string') return `${item.store ? String(item.store) + ' · ' : ''}${item.url}`
    if (typeof item.installments === 'number' && typeof item.installment_cents === 'number' && typeof item.total_cents === 'number') return `${item.installments} x R$ ${formatBRL(item.installment_cents)} · Total R$ ${formatBRL(item.total_cents)}`
  }
  return String(value ?? 'Não informado')
}
function Values({ offers }: { offers: Extraction['offers'] }) {
  return <>{offers.map(o => <dl key={o.block} className="offer-values">{Object.entries(o.values).map(([id, v]) => <div key={id}><dt>{v.name}{v.option ? ` · ${v.option}` : ''}</dt><dd>{v.value === null || v.value === 'unknown' ? 'Não informado' : v.type === 'money' && typeof v.value === 'number' ? `R$ ${formatBRL(v.value)}` : displayValue(v.value)}<details><summary>Evidência</summary><p>{v.raw || 'Sem trecho na mensagem'} · {v.origin === 'configuration' ? 'Constante configurada' : v.origin === 'absent' ? 'Não informado' : `Trecho da origem${v.start === null ? '' : `, posição ${v.start}`}`}</p></details></dd></div>)}</dl>)}</>
}

export function Catalog({ groups, onSourcesChanged, onDirty, surface = 'catalog', visible = true, onConfigure }: { groups: WatchedGroup[]; onSourcesChanged: (sources: Source[]) => void; onDirty: (dirty: boolean) => void; surface?: 'catalog' | 'collected'; visible?: boolean; onConfigure?: () => void }) {
  const [view, setView] = useState<View>('capture')
  const activeView = surface === 'collected' ? 'archive' : view
  const [status, setStatus] = useState(emptyStatus)
  const [worker, setWorker] = useState<WorkerStatus>({ running: false, error: null })
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false)
  const [detail, setDetail] = useState<MessageDetail | null>(null)
  const detailRef = useRef<HTMLElement>(null)
  useEffect(() => {
    if (detail?.id) { detailRef.current?.focus({ preventScroll: true }); detailRef.current?.scrollIntoView?.({ block: 'start' }) }
  }, [detail?.id])
  const [editing, setEditing] = useState<TemplateEntry | null>(null)
  const [modelDirty, setModelDirty] = useState(false), [linksDirty, setLinksDirty] = useState(false)
  const [alertsDirty, setAlertsDirty] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [resume, setResume] = useState<Record<number, string>>({})
  const [groupQuery, setGroupQuery] = useState('')
  const loadStatus = useCallback(async () => {
    const [s, w] = await Promise.all([request<CatalogStatus>({ action: 'status' }), window.api.worker('status')])
    setStatus(s); setWorker(w)
  }, [])
  useEffect(() => {
    let alive = true, pending = false
    const tick = async () => {
      if (pending) return
      pending = true
      try { if (alive) await loadStatus() } catch (e) { if (alive) setError(errorText(e)) }
      finally { pending = false }
    }
    void tick()
    const timer = setInterval(() => void tick(), 5000)
    return () => { alive = false; clearInterval(timer) }
  }, [loadStatus])
  useEffect(() => { onDirty(modelDirty || linksDirty || alertsDirty) }, [modelDirty, linksDirty, alertsDirty, onDirty])
  const operate = async (fn: () => Promise<void>) => {
    if (busy) return
    setBusy(true); setError(''); setNotice('')
    try { await fn(); await loadStatus(); setRefresh(n => n + 1) }
    catch (e) { setError(errorText(e)) } finally { setBusy(false) }
  }
  const open = async (id: number) => { try { setDetail(await request<MessageDetail>({ action: 'message', id })) } catch (e) { setError(errorText(e)) } }
  const create = (sourceId?: number) => {
    if (modelDirty) { setError('Salve ou descarte o rascunho aberto antes de criar outro modelo.'); return }
    const source_id = sourceId ?? groups[0]?.id ?? status.sources[0]?.id
    if (source_id === undefined) { setError('Atualize os grupos primeiro.'); return }
    const draft: Template = { id: crypto.randomUUID(), name: '', source_id, markers: [], delimiter: '', fields: [] }
    setEditing({ id: draft.id, source_id, draft, revision: 0, published: null, archived: 0 }); setView('templates'); onConfigure?.()
  }
  const allGroups = [...groups, ...status.sources.filter(s => !groups.some(g => g.id === s.id)).map(s => ({ id: s.id, name: s.name, selected: false }))]
  return <section className="catalog" aria-label="Catálogo de ofertas">
    {surface === 'catalog' && <><div className="catalog-summary" role="status"><span>{status.messages} mensagens · {status.offers} ofertas · {status.pending} na fila · {status.reviews} pendentes de revisão</span><span>{(status.bytes / 1048576).toFixed(1)} MB · Processamento {worker.running ? 'ativo' : 'parado'}</span></div>
    <div className="actions"><button disabled={busy} onClick={() => void operate(async () => { setWorker(await window.api.worker(worker.running ? 'stop' : 'start')) })}>{worker.running ? 'Parar processamento' : 'Iniciar processamento'}</button><button disabled={busy || worker.running} onClick={() => void operate(async () => { await request({ action: 'process' }) })}>Processar próximo lote</button><button disabled={busy} onClick={() => void operate(async () => {})}>Atualizar catálogo</button></div>
    <p className="help">O monitor recebe as mensagens; o processamento interpreta o acervo salvo. Alertas por palavra-chave funcionam independentemente dessas etapas.</p></>}
    {worker.error && <p role="alert" className="message">{worker.error}</p>}{error && <p role="alert" className="message">{error}</p>}{notice && <p role="status">{notice}</p>}
    {surface === 'catalog' && <nav className="catalog-tabs" aria-label="Catálogo">{(Object.keys(viewNames) as View[]).map(v => <button key={v} aria-current={view === v ? 'page' : undefined} onClick={() => setView(v)}>{viewNames[v]}</button>)}</nav>}
    {activeView === 'capture' && <section><h2>Arquivamento por grupo</h2><p>Grupos selecionados na tela Grupos já vêm com arquivamento habilitado por padrão. Aqui você pode pausar a coleta ou incluir outras origens. Preferências já salvas são preservadas. Reinicie o monitor para aplicar mudanças de escuta.</p>
      <Input label="Buscar grupo para arquivar" value={groupQuery} change={setGroupQuery} />
      {allGroups.filter(g => g.name.toLocaleLowerCase('pt-BR').includes(groupQuery.toLocaleLowerCase('pt-BR'))).map(g => {
        const source = status.sources.find(s => s.id === g.id)
        return <div className="catalog-source" key={g.id}><label className="check"><input type="checkbox" aria-label={'Arquivar ' + g.name} checked={!!source?.enabled} disabled={busy} onChange={e => { const enabled = e.target.checked; void operate(async () => {
          await request({ action: 'source:save', id: g.id, name: g.name, enabled, revision: source?.revision ?? 0, resume: resume[g.id] })
          const sources = await request<Source[]>({ action: 'sources' }); onSourcesChanged(sources)
          setNotice('Arquivamento salvo. Reinicie o monitor para aplicar a seleção.')
        }) }} />{g.name}</label><span className="help">Alertas: {g.selected ? 'selecionado' : 'não selecionado'}{source ? ` · Início: ${date(source.capture_started_at)}` : ' · Nunca arquivado'}</span>
          {source && !source.enabled && <label className="field">Ao reativar<select value={resume[g.id] ?? ''} onChange={e => setResume({ ...resume, [g.id]: e.target.value })}><option value="">Escolha como retomar</option><option value="recover">Recuperar desde o checkpoint</option><option value="now">Iniciar novo intervalo agora</option></select></label>}
          {source && <SourceHistory id={g.id} />}
          {source?.degraded && <p role="alert">Coleta degradada ({source.degraded}). Recuperação pendente desde {source.checkpoint ? date(source.checkpoint) : date(source.capture_started_at)}.</p>}
        </div>
      })}{!allGroups.length && <p>Atualize a lista de grupos na tela Grupos para escolher origens.</p>}
    </section>}
    <div hidden={activeView !== 'archive'}><Archive groups={allGroups} active={visible && activeView === 'archive'} refresh={refresh} open={open} report={setError} /></div>
    <div hidden={activeView !== 'templates'}><Templates groups={allGroups} editing={editing} setEditing={setEditing} dirty={modelDirty} setDirty={setModelDirty} create={() => create()} sample={detail} refresh={refresh} report={setError} /></div>
    <div hidden={activeView !== 'reviews'}><Reviews refresh={refresh} open={open} create={id => create(id)} report={setError} /></div>
    <div hidden={activeView !== 'offers'}><Offers groups={allGroups} refresh={refresh} open={open} report={setError} /></div>
    <div hidden={activeView !== 'stores'}><Stores dirty={linksDirty} setDirty={setLinksDirty} report={setError} /></div>
    <div hidden={activeView !== 'alerts'}><StructuredAlerts groups={allGroups} onDirty={setAlertsDirty} report={setError} /></div>
    {detail && <section ref={detailRef} tabIndex={-1} className="catalog-detail" aria-label="Mensagem original"><div className="section-title"><h2>Mensagem original · {detail.source_name}</h2><button onClick={() => setDetail(null)}>Fechar mensagem</button></div><p>{date(detail.published_at)} · {reason[detail.state ?? ''] ?? 'Aguardando processamento'}{detail.metadata.media_type ? ` · ${detail.metadata.media_type}` : ''}</p><pre>{detail.text || 'Mensagem sem texto'}</pre><div className="actions"><button onClick={() => create(detail.source_id)}>Parametrizar esta mensagem</button>{String(detail.source_id).startsWith('-100') && <button onClick={() => { void window.api.openExternal(`https://t.me/c/${String(detail.source_id).slice(4)}/${detail.message_id}`).catch(e => setError(errorText(e))) }}>Abrir no Telegram</button>}{detail.revisions.map(r => <button key={r.id} disabled={r.id === detail.id} onClick={() => void open(r.id)}>Revisão {date(r.revision_at)}</button>)}</div><details><summary>Links e histórico de interpretação</summary>{detail.metadata.links.map((l, i) => <p key={i}>{l.url} ({l.origin})</p>)}{detail.run_history?.map(r => <button key={r.id} onClick={() => { void request<MessageDetail['runs'][number]>({ action: 'run', id: r.id }).then(run => setDetail({ ...detail, runs: [run] })).catch(e => setError(errorText(e))) }}>{reason[r.state] ?? r.state} · {date(r.created_at)}</button>)}{detail.runs.map(r => <details key={r.id}><summary>{reason[r.state] ?? r.state} · {date(r.created_at)}</summary><Values offers={(JSON.parse(r.result) as Extraction).offers ?? []} /></details>)}</details></section>}
  </section>
}

function Archive({ groups, refresh, open, report, active }: { groups: WatchedGroup[]; refresh: number; open: (id: number) => Promise<void>; report: (s: string) => void; active: boolean }) {
  const [source, setSource] = useState(''), [offset, setOffset] = useState(0), [data, setData] = useState<Page<ArchivedMessage>>({ items: [], total: 0 })
  const [reload, setReload] = useState(0), [loading, setLoading] = useState(false), [loaded, setLoaded] = useState(false)
  useEffect(() => {
    if (!active) return
    let alive = true, pending = false
    const load = async () => {
      if (pending) return
      pending = true; setLoading(true)
      try {
        const result = await request<Page<ArchivedMessage>>({ action: 'messages', source_id: source ? Number(source) : undefined, offset })
        if (alive) { setData(result); setLoaded(true) }
      } catch (e) { if (alive) report(errorText(e)) }
      finally { pending = false; if (alive) setLoading(false) }
    }
    void load()
    const timer = setInterval(() => void load(), 5000)
    return () => { alive = false; clearInterval(timer) }
  }, [source, offset, refresh, reload, report, active])
  return <section aria-busy={loading}><div className="section-title"><h2>Mensagens coletadas</h2><button disabled={loading} onClick={() => setReload(n => n + 1)}>Atualizar mensagens</button></div><p>Postagens originais salvas, inclusive sem palavra-chave ou modelo. A lista é atualizada a cada 5 segundos enquanto esta tela está aberta.</p><label className="field">Grupo de origem<select value={source} onChange={e => { setSource(e.target.value); setOffset(0) }}><option value="">Todos os grupos</option>{groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select></label>{loading && !loaded && <p role="status">Carregando mensagens…</p>}{data.items.map(m => <article className="catalog-row" key={m.id}><button onClick={() => void open(m.id)}>{m.source_name} · {date(m.published_at)}</button><p>{m.text.slice(0, 240) || 'Mensagem sem texto'}</p><small>{reason[m.state ?? ''] ?? 'Aguardando processamento'}</small></article>)}{loaded && !data.total && <p>Nenhuma mensagem coletada nesta seleção. Selecione grupos e inicie o monitor; as novas postagens aparecerão aqui.</p>}<Pager total={data.total} offset={offset} change={setOffset} /></section>
}

function Templates({ groups, editing, setEditing, dirty, setDirty, create, sample, refresh, report }: { groups: WatchedGroup[]; editing: TemplateEntry | null; setEditing: (entry: TemplateEntry | null) => void; dirty: boolean; setDirty: (v: boolean) => void; create: () => void; sample: MessageDetail | null; refresh: number; report: (s: string) => void }) {
  const [entries, setEntries] = useState<TemplateEntry[]>([]), [fields, setFields] = useState<FieldDefinition[]>([])
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let alive = true
    Promise.all([request<TemplateEntry[]>({ action: 'templates' }), request<FieldDefinition[]>({ action: 'fields' })]).then(([t, f]) => { if (alive) { setEntries(t); setFields(f) } }).catch(e => { if (alive) report(errorText(e)) })
    return () => { alive = false }
  }, [refresh, reload, report])
  return <section><div className="section-title"><h2>Modelos por grupo</h2><button onClick={create}>Criar modelo</button></div><p>Defina os marcadores fixos e os campos variáveis. Publicar afeta mensagens futuras e pendências; resultados concluídos exigem reprocessamento.</p>{entries.map(e => <div className="catalog-row" key={e.id}><button onClick={() => { if (dirty) { report('Salve ou descarte o rascunho aberto antes de trocar de modelo.'); return } setEditing(e) }}>{e.draft.name}</button><span> · {e.archived ? 'Arquivado' : e.published ? `Publicado v${e.published}` : 'Rascunho'}</span></div>)}{!entries.length && <p>Nenhum modelo salvo. A coleta funciona mesmo sem modelos.</p>}{editing && <TemplateEditor key={editing.id} entry={editing} groups={groups} fields={fields} sample={sample} dirty={dirty} onDirty={setDirty} saved={e => { setEditing(e); setReload(n => n + 1) }} report={report} />}</section>
}

function TemplateEditor({ entry, groups, fields, sample, dirty, onDirty, saved, report }: { entry: TemplateEntry; groups: WatchedGroup[]; fields: FieldDefinition[]; sample: MessageDetail | null; dirty: boolean; onDirty: (v: boolean) => void; saved: (e: TemplateEntry) => void; report: (s: string) => void }) {
  const [draft, setDraft] = useState(entry.draft), [text, setText] = useState(sample?.source_id === entry.source_id ? sample.text : '')
  const [result, setResult] = useState<Extraction | null>(null), [signature, setSignature] = useState(''), [busy, setBusy] = useState(false)
  const sampleRef = useRef<HTMLTextAreaElement>(null)
  const current = JSON.stringify({ draft, text })
  const patch = (p: Partial<Template>) => { setDraft(d => ({ ...d, ...p })); onDirty(true) }
  const changeField = (i: number, p: Partial<FieldMapping>) => patch({ fields: draft.fields.map((f, n) => n === i ? { ...f, ...p } : f) })
  const act = async (fn: () => Promise<void>) => { setBusy(true); try { await fn() } catch (e) { report(errorText(e)) } finally { setBusy(false) } }
  const addField = (selection = false) => {
    const input = sampleRef.current
    const before = input ? text.slice(0, input.selectionStart) : ''
    const prefix = before.slice(before.lastIndexOf('\n') + 1)
    const f: FieldMapping = { field_id: crypto.randomUUID(), name: '', type: 'text', op: selection && !prefix ? 'line' : 'after', marker: selection ? prefix : '', line: before.split('\n').length, scope: 'offer' }
    patch({ fields: [...draft.fields, f] })
  }
  return <section className="catalog-editor" aria-label="Editor de modelo"><h3>{draft.name || 'Novo modelo'}</h3><p>Os valores extraídos representam o anúncio. Uma única amostra não garante cobertura do padrão; teste outras mensagens antes de publicar.</p><fieldset disabled={busy}><legend>Reconhecimento</legend><label className="check"><input type="checkbox" checked={draft.kind === 'ignore'} onChange={e => patch({ kind: e.target.checked ? 'ignore' : 'offer' })} />Este formato é conteúdo sem oferta</label><Input label="Nome do modelo" value={draft.name} change={name => patch({ name })} required /><label className="field">Grupo do modelo<select disabled={entry.revision > 0} value={draft.source_id} onChange={e => patch({ source_id: Number(e.target.value) })}>{groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select></label><Input label="Marcadores de reconhecimento (um por linha)" value={draft.markers.join('\n')} change={v => patch({ markers: v.split('\n') })} multiline /><Input label="Separador literal entre ofertas (opcional)" value={draft.delimiter} change={delimiter => patch({ delimiter })} multiline /><Input label="Marcador obrigatório do bloco de oferta (opcional)" value={draft.block_marker ?? ''} change={block_marker => patch({ block_marker })} /></fieldset>
    <div className="catalog-editor-columns"><section><h3>Exemplo da postagem</h3><label className="field">Texto para testar<textarea ref={sampleRef} value={text} maxLength={65536} onChange={e => setText(e.target.value)} /></label><div className="actions"><button onClick={() => addField(true)} disabled={busy || !text}>Criar campo a partir da seleção</button>{sample && <button disabled={busy} onClick={() => setText(sample.text)}>Usar mensagem aberta</button>}</div><p className="help">Selecione o valor variável para sugerir o marcador que vem antes dele. Revise a regra e teste outro exemplo.</p><button disabled={busy} onClick={() => void act(async () => {
      const links = await request<LinkSettings>({ action: 'links' })
      const r = await request<Extraction>({ action: 'preview', template: draft, text, links: sample?.text === text ? sample.metadata.links : [], link_rules: links.rules })
      setResult(r); setSignature(current)
    })}>Testar extração</button>{result && signature !== current && <p>Exemplo ou modelo alterado. Teste novamente para atualizar a prévia.</p>}{result && signature === current && <div role="status"><p>{reason[result.state] ?? result.state}{result.field_id ? ` · campo ${draft.fields.find(f => f.field_id === result.field_id)?.name ?? ''}` : ''}</p><Values offers={result.offers} /></div>}</section>
    <section><h3>Campos variáveis</h3>{draft.fields.map((f, i) => <fieldset key={i} disabled={busy}><legend>{f.name || `Campo ${i + 1}`}</legend><label className="field">Campo reutilizável<select value={fields.some(d => d.id === f.field_id) ? f.field_id : ''} onChange={e => { const known = fields.find(d => d.id === e.target.value); changeField(i, known ? { field_id: known.id, name: known.name, type: known.type } : { field_id: crypto.randomUUID() }) }}><option value="">Novo campo</option>{fields.map(d => <option key={d.id} value={d.id}>{d.name} ({typeNames[d.type]})</option>)}</select></label><Input label="Nome do campo" value={f.name} change={name => changeField(i, { name })} /><label className="field">Tipo<select value={f.type} onChange={e => changeField(i, { type: e.target.value as FieldType })}>{Object.entries(typeNames).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label><label className="field">Extrair usando<select value={f.op} onChange={e => changeField(i, { op: e.target.value as FieldMapping['op'] })}><option value="after">Texto após marcador, até o fim da linha</option><option value="between">Texto entre marcadores</option><option value="line">Número da linha</option><option value="presence">Presença de expressão</option><option value="constant">Valor constante configurado</option><option value="link">URL da postagem</option></select></label>{['after', 'between', 'presence'].includes(f.op) && <Input label="Marcador inicial" value={f.marker ?? ''} change={marker => changeField(i, { marker })} />}{f.op === 'between' && <Input label="Marcador final" value={f.end ?? ''} change={end => changeField(i, { end })} />}{f.op === 'line' && <label className="field">Número da linha<input type="number" min={1} max={1000} value={f.line ?? 1} onChange={e => changeField(i, { line: Number(e.target.value) })} /></label>}{f.op === 'constant' && <Input label="Valor constante" value={f.value ?? ''} change={value => changeField(i, { value })} />}{f.op === 'link' && <><Input label="Hostname do link (opcional)" value={f.host ?? ''} change={host => changeField(i, { host: host || undefined })} /><label className="field">Posição do link (opcional, começando em 1)<input type="number" min={1} max={100} value={f.position === undefined ? '' : f.position + 1} onChange={e => changeField(i, { position: e.target.value ? Number(e.target.value) - 1 : undefined })} /></label></>}{f.type === 'condition' && <label className="check"><input type="checkbox" checked={f.absence === 'absent'} onChange={e => changeField(i, { absence: e.target.checked ? 'absent' : 'unknown' })} />Expressão não encontrada significa condição ausente (por padrão, é desconhecida)</label>}{f.type === 'category' && <Input label="Mapeamentos (origem=destino por linha)" multiline value={Object.entries(f.mapping ?? {}).map(([k, v]) => `${k}=${v}`).join('\n')} change={v => changeField(i, { mapping: Object.fromEntries(v.split('\n').map(l => { const at = l.indexOf('='); return at < 0 ? [l, ''] : [l.slice(0, at), l.slice(at + 1)] })) })} />}
      <label className="field">Escopo<select value={f.scope ?? 'offer'} onChange={e => changeField(i, { scope: e.target.value as FieldMapping['scope'] })}><option value="offer">Apenas este bloco de oferta</option><option value="message">Toda a mensagem (herdar para ofertas)</option><option value="price">Opção de preço deste bloco</option></select></label>{f.scope === 'price' && <Input label="Nome da opção de preço (ex.: Pix)" value={f.option ?? ''} change={option => changeField(i, { option })} />}<label className="check"><input type="checkbox" checked={!!f.required} onChange={e => changeField(i, { required: e.target.checked })} />Obrigatório</label><label className="check"><input type="checkbox" checked={!!f.many} onChange={e => changeField(i, { many: e.target.checked })} />Aceitar vários valores</label><button className="danger" onClick={() => patch({ fields: draft.fields.filter((_, n) => n !== i) })}>Remover campo</button></fieldset>)}<button disabled={busy} onClick={() => addField()}>Adicionar campo</button></section></div>
    <div className="save-bar"><span>{dirty ? 'Alterações não salvas' : entry.published ? `Publicado v${entry.published}` : 'Rascunho'}</span><button disabled={busy || !dirty} onClick={() => { setDraft(entry.draft); onDirty(false) }}>Descartar alterações</button><button disabled={busy} onClick={() => void act(async () => { const r = await request<{ revision: number }>({ action: 'template:save', template: draft, revision: entry.revision }); saved({ ...entry, draft, revision: r.revision }); onDirty(false) })}>Salvar rascunho</button><button className="primary" disabled={busy || dirty || !entry.revision || signature !== current || !['done', 'ignored'].includes(result?.state ?? '')} onClick={() => void act(async () => { const r = await request<{ revision: number; version: number }>({ action: 'template:publish', id: entry.id, revision: entry.revision }); saved({ ...entry, draft, revision: r.revision, published: r.version }); onDirty(false) })}>Publicar modelo e processar pendências</button>{entry.published && <button disabled={busy || dirty} onClick={() => void act(async () => { await request({ action: 'template:archive', id: entry.id, revision: entry.revision }); saved({ ...entry, revision: entry.revision + 1, archived: 1 }) })}>Arquivar modelo</button>}</div>
  </section>
}

function Reviews({ refresh, open, create, report }: { refresh: number; open: (n: number) => Promise<void>; create: (n: number) => void; report: (s: string) => void }) {
  const [data, setData] = useState<Page<Review>>({ items: [], total: 0 }), [offset, setOffset] = useState(0), [reload, setReload] = useState(0)
  useEffect(() => { let alive = true; request<Page<Review>>({ action: 'reviews', offset }).then(d => { if (alive) setData(d) }).catch(e => { if (alive) report(errorText(e)) }); return () => { alive = false } }, [refresh, offset, reload, report])
  return <section><h2>Pendências por formato</h2><p>Os agrupamentos ajudam a revisar exemplos; cada mensagem continua sendo interpretada individualmente.</p>{data.items.map(r => <article className="catalog-row" key={`${r.source_id}-${r.reason}-${r.signature}`}><h3>{r.source_name} · {reason[r.reason] ?? r.reason}</h3><p>{r.count} mensagens · de {date(r.first_at)} a {date(r.last_at)}</p><div className="actions"><button onClick={() => void open(r.example_id)}>Abrir exemplo</button><button onClick={() => { void open(r.example_id).then(() => create(r.source_id)) }}>Criar modelo para este formato</button><button onClick={() => { void request({ action: 'review:ignore', id: r.example_id }).then(() => setReload(n => n + 1)).catch(e => report(errorText(e))) }}>Marcar somente este exemplo como sem oferta</button></div><ReviewExamples review={r} open={open} changed={() => setReload(n => n + 1)} /></article>)}{!data.total && <p>Nenhuma pendência de interpretação.</p>}<Pager total={data.total} offset={offset} change={setOffset} /></section>
}

function Offers({ groups, refresh, open, report }: { groups: WatchedGroup[]; refresh: number; open: (n: number) => Promise<void>; report: (s: string) => void }) {
  const [query, setQuery] = useState(''), [source, setSource] = useState(''), [field, setField] = useState(''), [max, setMax] = useState(''), [min, setMin] = useState(''), [valueText, setValueText] = useState(''), [option, setOption] = useState(''), [store, setStore] = useState(''), [from, setFrom] = useState(''), [to, setTo] = useState('')
  const [fields, setFields] = useState<FieldDefinition[]>([]), [filters, setFilters] = useState<Record<string, unknown>>({}), [offset, setOffset] = useState(0), [data, setData] = useState<Page<OfferRecord>>({ items: [], total: 0 })
  const [preview, setPreview] = useState<ReprocessPreview | null>(null), [jobToken, setJobToken] = useState(''), [busy, setBusy] = useState(false)
  useEffect(() => { request<FieldDefinition[]>({ action: 'fields' }).then(setFields).catch(e => report(errorText(e))) }, [refresh, report])
  useEffect(() => { let alive = true; request<Page<OfferRecord>>({ action: 'search', filters, offset }).then(d => { if (alive) setData(d) }).catch(e => { if (alive) report(errorText(e)) }); return () => { alive = false } }, [filters, offset, refresh, report])
  const range = () => ({ source_id: source ? Number(source) : undefined, from: from ? new Date(`${from}T00:00:00`).toISOString() : undefined, to: to ? new Date(`${to}T23:59:59.999`).toISOString() : undefined })
  const selectedField = fields.find(f => f.id === field)
  const [extra, setExtra] = useState<ValueFilter[]>([])
  const valueFilter = () => ({ field_id: field, ...numericBounds(selectedField?.type, min, max), text: valueText || undefined, option: option || undefined })

  return <section><h2>Buscar ofertas anunciadas</h2><form onSubmit={e => { e.preventDefault(); try { setFilters({ query, ...range(), values: [...extra, ...(field ? [valueFilter()] : [])], store: store || undefined }); setOffset(0) } catch (error) { report(errorText(error)) } }}><Input label="Produto, cupom ou texto extraído" value={query} change={setQuery} /><details className="catalog-filters"><summary>Filtrar por origem, loja, período e campo</summary><div className="field-pair"><label className="field">Origem<select value={source} onChange={e => { setSource(e.target.value); setPreview(null) }}><option value="">Todos os grupos</option>{groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select></label><Input label="Loja" value={store} change={setStore} /><label className="field">De<input type="date" value={from} onChange={e => { setFrom(e.target.value); setPreview(null) }} /></label><label className="field">Até<input type="date" value={to} onChange={e => { setTo(e.target.value); setPreview(null) }} /></label><label className="field">Campo para filtrar<select value={field} onChange={e => { setField(e.target.value); setMin(''); setMax(''); setValueText('') }}><option value="">Sem filtro por campo</option>{fields.map(f => <option key={f.id} value={f.id}>{f.name} ({typeNames[f.type]})</option>)}</select></label>{field && (selectedField?.type === 'condition' ? <label className="field">Estado da condição<select value={valueText} onChange={e => setValueText(e.target.value)}><option value="">Qualquer estado</option><option value="present">Presente</option><option value="absent">Ausente por regra explícita</option><option value="unknown">Não informada</option></select></label> : <Input label="Valor deve conter" value={valueText} change={setValueText} />)}{selectedField && ['money', 'number'].includes(selectedField.type) && <><Input label={selectedField.type === 'money' ? 'Mínimo (R$)' : 'Mínimo'} value={min} change={setMin} /><Input label={selectedField.type === 'money' ? 'Máximo (R$)' : 'Máximo'} value={max} change={setMax} /></>}{field && <Input label="Opção de preço (opcional)" value={option} change={setOption} />}</div><button type="button" disabled={!field} onClick={() => { try { setExtra([...extra, valueFilter()]); setField(''); setMin(''); setMax(''); setValueText(''); setOption('') } catch (error) { report(errorText(error)) } }}>Adicionar condição à busca</button>{extra.map((f, i) => <p key={i}>{fields.find(d => d.id === f.field_id)?.name} · {f.text || (f.max !== undefined ? `até ${f.max}` : f.min !== undefined ? `a partir de ${f.min}` : 'campo presente')}<button type="button" onClick={() => setExtra(extra.filter((_, n) => n !== i))}>Remover condição da busca</button></p>)}</details><button type="submit">Buscar no catálogo</button></form>
    {data.items.map(o => <article className="catalog-row" key={o.id}><div className="section-title"><h3>{o.source_name} · {date(o.published_at)}</h3><button onClick={() => void open(o.revision_id)}>Ver mensagem e evidências</button></div><Values offers={[o.payload]} /></article>)}{!data.total && <p>Nenhuma oferta corresponde aos filtros. Mensagens sem modelo ficam no Acervo e nas Pendências.</p>}<Pager total={data.total} offset={offset} change={setOffset} />
    <details className="catalog-reprocess"><summary>Reprocessar acervo local</summary><p>Selecione uma origem e, se desejar, um período acima. A prévia fixa as mensagens e versões atuais. Reprocessar não envia alertas.</p><button disabled={busy || !source} onClick={() => { setBusy(true); void request<ReprocessPreview>({ action: 'reprocess:preview', scope: range() }).then(setPreview).catch(e => report(errorText(e))).finally(() => setBusy(false)) }}>Ver impacto do reprocessamento</button>{preview && <div><p>{preview.count} mensagens serão reprocessadas com os modelos publicados. Execuções anteriores serão preservadas.</p><button disabled={busy} onClick={() => { setBusy(true); void request({ action: 'reprocess:confirm', token: preview.token }).then(() => { setJobToken(preview.token); setPreview(null) }).catch(e => report(errorText(e))).finally(() => setBusy(false)) }}>Confirmar reprocessamento de {preview.count} mensagens</button></div>}{jobToken && <p>Trabalho enfileirado. Inicie o processamento para executar ou retomar.<button disabled={busy} onClick={() => { setBusy(true); void request({ action: 'reprocess:cancel', token: jobToken }).then(() => setJobToken('')).catch(e => report(errorText(e))).finally(() => setBusy(false)) }}>Cancelar mensagens ainda pendentes</button></p>}</details><ReprocessHistory refresh={refresh} />
  </section>
}

function Stores({ dirty, setDirty, report }: { dirty: boolean; setDirty: (v: boolean) => void; report: (s: string) => void }) {
  const [saved, setSaved] = useState<LinkSettings>({ rules: [], revision: 0 }), [draft, setDraft] = useState<LinkSettings['rules']>([]), [loaded, setLoaded] = useState(false), [busy, setBusy] = useState(false)
  useEffect(() => { let alive = true; request<LinkSettings>({ action: 'links' }).then(d => { if (alive) { setSaved(d); setDraft(d.rules); setLoaded(true) } }).catch(e => { if (alive) report(errorText(e)) }); return () => { alive = false } }, [report])
  return <section><h2>Lojas e domínios</h2><p>Associe o hostname real à loja. Exemplo: s.shopee.com.br. Links desconhecidos continuam preservados. O app não abre encurtadores para descobrir o destino.</p>{draft.map((r, i) => <fieldset key={i} disabled={busy}><legend>Regra de loja {i + 1}</legend><div className="field-pair"><Input label="Hostname completo" value={r.host} change={host => { setDraft(draft.map((v, n) => n === i ? { ...v, host } : v)); setDirty(true) }} /><Input label="Nome da loja" value={r.store} change={store => { setDraft(draft.map((v, n) => n === i ? { ...v, store } : v)); setDirty(true) }} /></div><label className="check"><input type="checkbox" checked={r.subdomains} onChange={e => { setDraft(draft.map((v, n) => n === i ? { ...v, subdomains: e.target.checked } : v)); setDirty(true) }} />Incluir subdomínios deste hostname</label><button className="danger" onClick={() => { setDraft(draft.filter((_, n) => n !== i)); setDirty(true) }}>Remover regra de loja</button></fieldset>)}<div className="actions"><button disabled={!loaded || busy} onClick={() => { setDraft([...draft, { host: '', store: '', subdomains: false }]); setDirty(true) }}>Adicionar loja</button><button disabled={!dirty || busy} onClick={() => { setDraft(saved.rules); setDirty(false) }}>Descartar regras</button><button className="primary" disabled={!dirty || busy} onClick={() => { setBusy(true); void request<LinkSettings>({ action: 'links:save', rules: draft, revision: saved.revision }).then(r => { setSaved(r); setDirty(false) }).catch(e => report(errorText(e))).finally(() => setBusy(false)) }}>Salvar regras de lojas</button></div><p className="help">Mudanças classificam mensagens futuras. Para atualizar resultados existentes, use a prévia de reprocessamento em Ofertas.</p></section>
}
