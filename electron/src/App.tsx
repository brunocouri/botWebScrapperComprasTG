import { useEffect, useRef, useState, type FormEvent } from 'react'
import type { AppliedSnapshot, BotApi, ConfigState, Rule, RuntimeStatus, Simulation, WatchedGroup } from './lib/ipc'
import { applyDrafts, dirtyIds, draftFromRule, validateAllDrafts, type DraftErrors, type Drafts } from './lib/keywords'
import { formatBRL } from './lib/money'
import { Activity } from './features/Activity'
import { FeedStore } from './lib/feed-store'
import { Catalog } from './features/Catalog'
import type { Source } from './lib/catalog'

declare global { interface Window { api: BotApi } }
type Page = 'collected' | 'groups' | 'rules' | 'activity' | 'settings' | 'catalog'
const labels: Record<RuntimeStatus['state'], string> = {
  stopped: 'Parado', starting: 'Iniciando', connecting: 'Conectando', synchronizing: 'Sincronizando', monitoring: 'Monitorando',
  reconnecting: 'Reconectando', stopping: 'Parando', auth_required: 'Autorização necessária', authenticating: 'Autenticando', error: 'Erro',
}
const initial: RuntimeStatus = { state: 'stopped', busy: false, snapshot: null, error: null }
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error)
const timeLabel = (value?: string | null) => value ? new Date(value).toLocaleTimeString('pt-BR') : 'Ainda não registrado'

function Icon({ name }: { name: Page | 'menu' }) {
  const paths = { groups: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M16 3a4 4 0 0 1 0 8 M22 21v-2a4 4 0 0 0-3-3.87',
    rules: 'M20 12l-8 8L2 10V2h8z M7 7h.01', activity: 'M2 12h4l3-9 6 18 3-9h4',
    settings: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2',
    collected: 'M3 4h18v5H3z M5 9v11h14V9 M9 13h6', catalog: 'M4 3h16v18H4z M8 7h8 M8 12h8 M8 17h5', menu: 'M4 6h16 M4 12h16 M4 18h16' }
  return <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name]} />{name === 'groups' && <circle cx="9" cy="7" r="4" />}</svg>
}
function Message({ children }: { children: React.ReactNode }) { return <div className="message" role="alert">{children}</div> }
function Empty({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="empty"><strong>{title}</strong><p>{children}</p></div>
}

export default function App() {
  if (!window.api) return <main className="empty"><h1>ComprasTG</h1><p>Abra o aplicativo pelo Electron para acessar seus dados.</p></main>
  return <DesktopApp />
}

function DesktopApp() {
  const [page, setPage] = useState<Page>('groups')
  const [catalogVisited, setCatalogVisited] = useState(false)
  const [catalogDirty, setCatalogDirty] = useState(false)
  const [captureSources, setCaptureSources] = useState<Source[]>([])
  const [collapsed, setCollapsed] = useState(false)
  const [status, setStatus] = useState(initial)
  const [snapshot, setSnapshot] = useState<AppliedSnapshot | null>(null)
  const [groups, setGroups] = useState<WatchedGroup[]>([])
  const [groupRevision, setGroupRevision] = useState('')
  const [groupsLoaded, setGroupsLoaded] = useState(false)
  const [groupError, setGroupError] = useState('')
  const [rules, setRules] = useState<Rule[]>([])
  const [ruleRevision, setRuleRevision] = useState('')
  const [rulesLoaded, setRulesLoaded] = useState(false)
  const [drafts, setDrafts] = useState<Drafts>({})
  const [editing, setEditing] = useState<string | null>(null)
  const [draftErrors, setDraftErrors] = useState<DraftErrors>({})
  const [ruleError, setRuleError] = useState('')
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)
  const [config, setConfig] = useState<ConfigState | null>(null)
  const [configDraft, setConfigDraft] = useState({ apiId: '', apiHash: '', phone: '' })
  const [configNotice, setConfigNotice] = useState('')
  const [configErrors, setConfigErrors] = useState<Record<string, string>>({})
  const [authStep, setAuthStep] = useState<'code' | 'password' | 'checking' | 'authorized' | null>(null)
  const [authMessage, setAuthMessage] = useState('')
  const [stats, setStats] = useState<{ messages: number; alerts?: number; last_message?: string | null; last_alert?: string | null } | null>(null)
  const [feed] = useState(() => new FeedStore())
  const busyRef = useRef(false)
  const snapshotRequest = useRef(0)
  const pendingDrafts = dirtyIds(rules, drafts)
  const configDirty = !!config && (configDraft.apiId !== config.apiId || configDraft.phone !== config.phone || configDraft.apiHash !== '')
  const appliedDiffers = !!status.snapshot && !!snapshot && status.snapshot.revision !== snapshot.revision

  const refreshSnapshot = async () => {
    const request = ++snapshotRequest.current
    try { const result = await window.api.getSnapshot(); if (request === snapshotRequest.current) setSnapshot(result) }
    catch (e) { if (request === snapshotRequest.current) setError(errorText(e)) }
  }
  const loadGroups = async () => {
    try { const data = await window.api.listGroups(); setGroups(data.groups); setGroupRevision(data.revision); setGroupError(''); setGroupsLoaded(true) }
    catch (e) { setGroupError(errorText(e)); setGroupsLoaded(false) }
  }
  const loadRules = async () => {
    try { const data = await window.api.getKeywords(); setRules(data.rules); setRuleRevision(data.revision); setRuleError(''); setRulesLoaded(true) }
    catch (e) { setRuleError(errorText(e)); setRulesLoaded(false) }
  }
  useEffect(() => {
    let live = true
    let receivedStatus = false
    const off = window.api.onBotEvent(message => {
      feed.receive(message)
      if (message.kind !== 'event') return
      const event = message.event
      if (event.type === 'stats') setStats(event)
      if (event.type === 'auth_step') { setAuthStep(event.step); setAuthMessage(event.message || '') }
    })
    const offStatus = window.api.onStatus(value => { receivedStatus = true; setStatus(value) })
    void window.api.getStatus().then(value => { if (live && !receivedStatus) setStatus(value) }).catch(e => { if (live) setError(errorText(e)) })
    // IPC assíncrono; não há atualização síncrona de estado no efeito.
    void Promise.resolve().then(() => { if (live) {
      void loadGroups(); void loadRules(); void refreshSnapshot()
      void window.api.catalog<Source[]>({ action: 'sources' }).then(s => { if (live) { setCaptureSources(s); void refreshSnapshot() } }).catch(() => {})
    } })
    void window.api.getConfig().then(c => { if (live) { setConfig(c); setConfigDraft({ apiId: c.apiId, apiHash: '', phone: c.phone }) } }).catch(e => { if (live) setError(errorText(e)) })
    const timer = setInterval(() => { if (live && !busyRef.current) void refreshSnapshot() }, 5000)
    return () => { live = false; off(); offStatus(); clearInterval(timer); feed.cancelPending() }
  }, [feed])
  useEffect(() => { void window.api.setDirty(pendingDrafts.length > 0 || configDirty || catalogDirty).catch(() => {}) }, [pendingDrafts.length, configDirty, catalogDirty])

  async function operation(action: () => Promise<void>) {
    if (busyRef.current) return
    busyRef.current = true; setWorking(true); setError('')
    try { await action(); await refreshSnapshot() }
    catch (e) { setError(errorText(e)) }
    finally { busyRef.current = false; setWorking(false) }
  }
  async function start() {
    await operation(async () => {
      setStats(null)
      const result = await window.api.startBot()
      if (!result.ok) throw new Error(result.error)
    })
  }
  async function saveGroups(next: WatchedGroup[]) {
    await operation(async () => { const data = await window.api.saveGroups(next, groupRevision); setGroups(data.groups); setGroupRevision(data.revision) })
  }
  async function persistRules(next: Rule[]) {
    const data = await window.api.saveKeywords(next, ruleRevision)
    setRules(data.rules); setRuleRevision(data.revision)
  }
  async function saveAll() {
    const problem = validateAllDrafts(rules, drafts)
    if (problem) { setEditing(problem.ruleId); setDraftErrors({ [problem.field]: problem.message }); return }
    await operation(async () => { await persistRules(applyDrafts(rules, drafts)); setDrafts({}); setEditing(null); setDraftErrors({}) })
  }
  async function reorder(index: number, delta: number) {
    const next = [...rules]; [next[index], next[index + delta]] = [next[index + delta], next[index]]
    await operation(() => persistRules(next))
  }
  const activeRule = rules.find(r => r.id === editing)
  const draft = activeRule ? drafts[activeRule.id] ?? draftFromRule(activeRule, formatBRL) : null
  function patchDraft(patch: Partial<NonNullable<typeof draft>>) {
    if (!activeRule || !draft) return
    setDrafts(value => ({ ...value, [activeRule.id]: { ...draft, ...patch } })); setDraftErrors({})
  }
  function closeEditor() {
    const previous = editing
    setEditing(null)
    requestAnimationFrame(() => { if (previous) document.getElementById('rule-button-' + previous)?.focus() })
  }
  useEffect(() => { if (editing) document.getElementById('rule-term')?.focus() }, [editing])
  async function saveConfiguration(e: FormEvent) {
    e.preventDefault()
    if (!config || working) return
    const errors: Record<string, string> = {}
    if (!/^\d{5,12}$/.test(configDraft.apiId.trim())) errors.apiId = 'Informe de 5 a 12 dígitos.'
    if ((!config.apiHashSet || configDraft.apiHash.trim()) && !/^[a-fA-F0-9]{32}$/.test(configDraft.apiHash.trim())) errors.apiHash = 'Informe os 32 caracteres hexadecimais do API Hash.'
    const phone = configDraft.phone.trim().replace(/[\s-]/g, '')
    if (!/^\+\d{10,15}$/.test(phone)) errors.phone = 'Use o formato internacional: +5511999999999.'
    setConfigErrors(errors)
    if (Object.keys(errors).length) { document.getElementById(errors.apiId ? 'api-id' : errors.apiHash ? 'api-hash' : 'phone')?.focus(); return }
    await operation(async () => {
      const c = await window.api.saveConfig({ ...configDraft, phone }, config.revision)
      setConfig(c); setConfigDraft({ apiId: c.apiId, apiHash: '', phone: c.phone })
      setConfigNotice('Configurações salvas. Reinicie o monitor para aplicar.')
    })
  }
  const headings = { collected: ['Coletados', 'Veja as mensagens originais salvas dos grupos acompanhados.'], groups: ['Grupos', 'Escolha onde procurar suas oportunidades.'], rules: ['Palavras-chave', 'Controle termos, preços e a prioridade de cada regra.'], activity: ['Atividade', 'Entenda o que foi encontrado, enviado ou filtrado.'], settings: ['Configurações', 'Credenciais e autorização da sua conta do Telegram.'], catalog: ['Catálogo', 'Guarde postagens, configure formatos e pesquise ofertas anunciadas.'] }

  return <div className={'app-shell' + (collapsed ? ' collapsed' : '')}>
    <aside className="sidebar">
      <div className="brand"><strong>ComprasTG</strong><button aria-label={collapsed ? 'Expandir navegação' : 'Recolher navegação'} onClick={() => setCollapsed(!collapsed)}><Icon name="menu" /></button></div>
      <nav aria-label="Principal">{(['collected', 'groups', 'rules', 'catalog', 'activity', 'settings'] as const).map(item => <button key={item} title={headings[item][0]} aria-label={headings[item][0]} aria-current={page === item ? 'page' : undefined} onClick={() => { setPage(item); if (item === 'catalog' || item === 'collected') setCatalogVisited(true) }}><Icon name={item} /><span>{headings[item][0]}</span></button>)}</nav>
      <div className="sidebar-foot">Fechar o app encerra o monitor.</div>
    </aside>
    <div className="workspace">
      <header className="app-header"><div><h1>{headings[page][0]}</h1><p>{headings[page][1]}</p></div><div className="actions">
        <span role="status" className={'status status-' + status.state}><i />{labels[status.state]}</span>
        {status.busy ? <button disabled={working || status.state === 'stopping'} onClick={() => void operation(async () => { await window.api.stopBot() })}>{status.state === 'stopping' ? 'Parando…' : 'Parar operação'}</button>
          : <button className="primary" disabled={working || !groupsLoaded || !rulesLoaded || (!(groups.some(g => g.selected) && rules.some(r => r.enabled)) && !captureSources.some(s => s.enabled))} onClick={() => void start()}>Iniciar monitor</button>}
      </div></header>
      <div className="runtime-summary"><span>{status.snapshot ? `${status.snapshot.groups} grupos · ${status.snapshot.rules} regras aplicadas` : 'Monitor ainda não iniciado nesta sessão'}</span><span>Última mensagem: {timeLabel(stats?.last_message)}</span><span>Último envio: {timeLabel(stats?.last_alert)}</span>{stats && <span>{stats.messages} mensagens · {stats.alerts ?? 0} envios</span>}</div>
      {appliedDiffers && <div className="notice">Configuração salva diferente da aplicada. Reinicie o monitor para aplicar.<button disabled={working} onClick={() => void operation(async () => { await window.api.stopBot(); const result = await window.api.startBot(); if (!result.ok) throw new Error(result.error) })}>Reiniciar e aplicar</button></div>}
      {(error || status.error) && <div className="global-error"><Message>{error || status.error}{status.state === 'auth_required' && <button onClick={() => setPage('settings')}>Autorizar conta</button>}</Message>{error && <button onClick={() => setError('')} aria-label="Dispensar mensagem">Fechar</button>}</div>}
      <main className={'page ' + (page === 'activity' ? 'activity-page' : '')}>
        {page === 'groups' && <Groups groups={groups} loaded={groupsLoaded} error={groupError} disabled={working} busy={status.busy} save={saveGroups} retry={loadGroups} reload={() => operation(async () => { await window.api.reloadGroups(); await loadGroups() })} />}
        {page === 'rules' && <>
          <section className="section"><div className="section-title"><h2>Regras de monitoramento</h2><span>{rules.filter(r => r.enabled).length} ativas de {rules.length}</span></div>
            <AddRule disabled={working || !rulesLoaded} add={async term => {
              if (busyRef.current) throw new Error('Aguarde a gravação atual.')
              busyRef.current = true; setWorking(true)
              try { const data = await window.api.addKeyword(term, ruleRevision); setRules(data.rules); setRuleRevision(data.revision); setRuleError(''); await refreshSnapshot() }
              finally { busyRef.current = false; setWorking(false) }
            }} report={setRuleError} />
            {ruleError && <Message>{ruleError}<button onClick={() => void loadRules()}>Recarregar regras</button></Message>}
            {!rulesLoaded && !ruleError && <p>Carregando regras…</p>}
            {rulesLoaded && !rules.length && <Empty title="Nenhuma palavra-chave cadastrada">Adicione um termo e selecione grupos para iniciar.</Empty>}
            <ol className="rule-list">{rules.map((rule, index) => <li key={rule.id} className={editing === rule.id ? 'selected' : ''}>
              <span className="priority" title="Prioridade">{index + 1}</span><button className="rule-main" id={'rule-button-' + rule.id} aria-label={'Editar ' + rule.term} aria-expanded={editing === rule.id} onClick={() => { setEditing(editing === rule.id ? null : rule.id); setDraftErrors({}) }}><strong>{rule.term}{pendingDrafts.includes(rule.id) && <span className="dirty-dot"> · edição pendente</span>}</strong><span>{rule.enabled ? 'Ativa' : 'Desativada'} · {rule.min_cents !== null ? `De R$ ${formatBRL(rule.min_cents)}` : 'Sem mínimo'} · {rule.max_cents !== null ? `Até R$ ${formatBRL(rule.max_cents)}` : 'Sem máximo'}</span></button>
              <div className="actions"><button disabled={working || index === 0} aria-label={'Aumentar prioridade de ' + rule.term} onClick={() => void reorder(index, -1)}>Subir</button><button disabled={working || index === rules.length - 1} aria-label={'Diminuir prioridade de ' + rule.term} onClick={() => void reorder(index, 1)}>Descer</button></div>
            </li>)}</ol>
            <p className="help">Match exato, sem diferenciar maiúsculas. A primeira regra elegível tem prioridade; cada mensagem gera no máximo um alerta.</p>
            {activeRule && draft && <section className="editor" aria-label={'Editor de ' + activeRule.term} onKeyDown={e => { if (e.key === 'Escape') closeEditor() }}>
              <div className="section-title"><h3>Editar {activeRule.term}</h3><button onClick={closeEditor}>Fechar editor</button></div>
              <label className="check"><input type="checkbox" checked={draft.enabled} disabled={working} onChange={e => patchDraft({ enabled: e.target.checked })} />Regra ativa</label>
              <Field disabled={working} id="rule-term" label="Palavra-chave" value={draft.term} error={draftErrors.term} onChange={v => patchDraft({ term: v })} />
              <div className="field-pair"><Field disabled={working} id="rule-min" label="Preço mínimo (R$)" value={draft.minStr} error={draftErrors.min} placeholder="Sem limite" onChange={v => patchDraft({ minStr: v })} /><Field disabled={working} id="rule-max" label="Preço máximo (R$)" value={draft.maxStr} error={draftErrors.max} placeholder="Sem limite" onChange={v => patchDraft({ maxStr: v })} /></div>
              <p className="help">Limites inclusivos. Deixe vazio para não limitar. Preço ambíguo é filtrado quando há limite.</p>
              <DeleteRule key={activeRule.id} disabled={working} term={activeRule.term} remove={() => operation(async () => { await persistRules(rules.filter(r => r.id !== activeRule.id)); setDrafts(current => { const next = { ...current }; delete next[activeRule.id]; return next }); setEditing(null) })} />
            </section>}
            {pendingDrafts.length > 0 && <div className="save-bar" role="status"><span>{pendingDrafts.length} {pendingDrafts.length === 1 ? 'regra alterada' : 'regras alteradas'}</span><button disabled={working} onClick={() => { setDrafts({}); setDraftErrors({}) }}>Descartar alterações</button><button className="primary" disabled={working} onClick={() => void saveAll()}>Salvar {pendingDrafts.length} {pendingDrafts.length === 1 ? 'alteração' : 'alterações'}</button></div>}
          </section>
          <Simulator rules={rules} drafts={drafts} pending={pendingDrafts.length > 0} />
        </>}
        {page === 'activity' && <Activity store={feed} status={status.state} />}
        {catalogVisited && <div hidden={page !== 'catalog' && page !== 'collected'}><Catalog groups={groups} surface={page === 'collected' ? 'collected' : 'catalog'} visible={page === 'collected' || page === 'catalog'} onConfigure={() => setPage('catalog')} onDirty={setCatalogDirty} onSourcesChanged={sources => { setCaptureSources(sources); void refreshSnapshot() }} /></div>}
        {page === 'settings' && <section className="section settings"><h2>Conta do Telegram</h2><p>Configure as credenciais antes de autorizar a sessão.</p>
          {!config ? <p>Configurações indisponíveis. Confira a mensagem de erro e tente abrir o app novamente.</p> : <form onSubmit={e => void saveConfiguration(e)}>
            <Field disabled={working} error={configErrors.apiId} id="api-id" label="API ID" value={configDraft.apiId} onChange={v => setConfigDraft({ ...configDraft, apiId: v })} />
            <SecretField disabled={working} error={configErrors.apiHash} value={configDraft.apiHash} onChange={v => setConfigDraft({ ...configDraft, apiHash: v })} />
            <p className="help">{config.apiHashSet ? `Hash configurado (${config.apiHashPreview}). Deixe vazio para manter.` : 'Informe o API Hash de sua aplicação.'}</p>
            <Field disabled={working} error={configErrors.phone} id="phone" label="Telefone" value={configDraft.phone} placeholder="+5511999999999" onChange={v => setConfigDraft({ ...configDraft, phone: v })} />
            <div className="actions"><button type="button" disabled={working || !configDirty} onClick={() => setConfigDraft({ apiId: config.apiId, apiHash: '', phone: config.phone })}>Descartar alterações</button><button type="submit" className="primary" disabled={working || !configDirty}>Salvar configurações</button></div>
          </form>}
          {configNotice && <p role="status">{configNotice}</p>}
          <details className="help-block"><summary>Como obter as credenciais?</summary><p>Acesse my.telegram.org, entre com sua conta e abra API development tools. Copie App api_id e App api_hash.</p><button onClick={() => void window.api.openExternal('https://my.telegram.org').catch(e => setError(errorText(e)))}>Abrir portal oficial do Telegram</button></details>
          <section className="editor"><h3>Autorizar sessão</h3><p>O monitor deve estar parado. Alterar o telefone não substitui uma sessão de outra conta.</p><button disabled={working || status.busy || configDirty || !config?.apiHashSet} onClick={() => void operation(async () => { setAuthStep(null); setAuthMessage(''); const result = await window.api.authenticate(); if (!result.ok) throw new Error(result.error) })}>Autorizar conta</button>
            {(authStep === 'code' || authStep === 'password') && status.busy && <AuthInput step={authStep} submit={value => window.api.submitAuth(value)} />}
            {authStep === 'checking' && status.busy && <p role="status">Conferindo resposta com o Telegram…</p>}
            {authMessage && <Message>{authMessage}</Message>}{authStep === 'authorized' && <p role="status">Sessão autorizada. O monitor pode ser iniciado.</p>}
          </section>
        </section>}
      </main>
    </div>
  </div>
}

function Field({ id, label, value, onChange, error, placeholder, disabled, type = 'text' }: { id: string; label: string; value: string; onChange: (value: string) => void; error?: string; placeholder?: string; type?: string; disabled?: boolean }) {
  return <div className="field"><label htmlFor={id}>{label}</label><input id={id} disabled={disabled} type={type} value={value} placeholder={placeholder} spellCheck={false} aria-invalid={!!error} aria-describedby={error ? id + '-error' : undefined} onChange={e => onChange(e.target.value)} />{error && <p id={id + '-error'} className="field-error">{error}</p>}</div>
}
function SecretField({ value, onChange, disabled, error }: { value: string; onChange: (value: string) => void; disabled: boolean; error?: string }) {
  const [visible, setVisible] = useState(false)
  return <div className="secret-field"><Field disabled={disabled} error={error} id="api-hash" label="API Hash" type={visible ? 'text' : 'password'} value={value} onChange={onChange} /><button type="button" aria-pressed={visible} onClick={() => setVisible(!visible)}>{visible ? 'Ocultar hash' : 'Mostrar hash'}</button></div>
}
function AuthInput({ step, submit }: { step: 'code' | 'password'; submit: (value: string) => Promise<void> }) {
  const [value, setValue] = useState(''), [pending, setPending] = useState(false), [error, setError] = useState('')
  return <form onSubmit={e => { e.preventDefault(); if (!value || pending) return; setPending(true); void submit(value).then(() => setValue('')).catch(e => setError(errorText(e))).finally(() => setPending(false)) }}>
    <Field id="auth-value" label={step === 'code' ? 'Código recebido no Telegram' : 'Senha de verificação em duas etapas'} type={step === 'password' ? 'password' : 'text'} value={value} onChange={setValue} />
    {error && <Message>{error}</Message>}<button className="primary" disabled={!value || pending}>Enviar {step === 'code' ? 'código' : 'senha'}</button><p className="help">A autorização expira após 3 minutos sem resposta. Use Parar operação para cancelar.</p>
  </form>
}
function AddRule({ disabled, add, report }: { disabled: boolean; add: (term: string) => Promise<void>; report: (error: string) => void }) {
  const [term, setTerm] = useState('')
  async function submit(e: FormEvent) {
    e.preventDefault(); if (!term.trim()) return
    try { await add(term.trim()); setTerm('') } catch (error) { report(errorText(error)); return }
  }
  return <form className="add-rule" onSubmit={e => void submit(e)}><Field id="new-rule" label="Nova palavra-chave" value={term} onChange={setTerm} /><button disabled={disabled || !term.trim()} type="submit">Adicionar</button></form>
}
function DeleteRule({ disabled, term, remove }: { disabled: boolean; term: string; remove: () => Promise<void> }) {
  const [confirm, setConfirm] = useState(false)
  return <div className="actions">{confirm ? <><span>Excluir {term}?</span><button disabled={disabled} className="danger" onClick={() => void remove()}>Confirmar exclusão</button><button onClick={() => setConfirm(false)}>Cancelar</button></> : <button className="danger" disabled={disabled} onClick={() => setConfirm(true)}>Excluir palavra-chave</button>}</div>
}
function Groups({ groups, loaded, error, disabled, busy, save, retry, reload }: { groups: WatchedGroup[]; loaded: boolean; error: string; disabled: boolean; busy: boolean; save: (groups: WatchedGroup[]) => Promise<void>; retry: () => Promise<void>; reload: () => Promise<void> }) {
  const [query, setQuery] = useState(''), [onlySelected, setOnlySelected] = useState(false)
  const q = query.trim().toLocaleLowerCase('pt-BR')
  const filtered = groups.filter(g => (!onlySelected || g.selected) && (!q || g.name.toLocaleLowerCase('pt-BR').includes(q) || String(g.id).includes(q)))
  const all = filtered.length > 0 && filtered.every(g => g.selected)
  const mixed = !all && filtered.some(g => g.selected)
  const bulk = useRef<HTMLInputElement>(null)
  useEffect(() => { if (bulk.current) bulk.current.indeterminate = mixed }, [mixed])
  return <section className="section"><div className="toolbar"><Field id="groups-search" label="Buscar grupos" value={query} onChange={setQuery} placeholder="Nome ou ID" /><label className="check"><input type="checkbox" checked={onlySelected} onChange={e => setOnlySelected(e.target.checked)} />Só selecionados</label><button disabled={disabled || busy} onClick={() => void reload()}>Atualizar do Telegram</button></div>
    {busy && <p className="help">Pare a operação atual antes de atualizar a lista do Telegram.</p>}
    {error && <Message>{error}<button onClick={() => void retry()}>Tentar ler novamente</button></Message>}
    {!loaded && !error && <p>Carregando grupos…</p>}
    {loaded && <><div className="selection-toolbar"><label className="check"><input ref={bulk} type="checkbox" aria-label={`Selecionar resultados (${filtered.length})`} checked={all} disabled={disabled || !filtered.length} onChange={() => { const ids = new Set(filtered.map(g => g.id)); void save(groups.map(g => ids.has(g.id) ? { ...g, selected: !all } : g)) }} />Selecionar resultados ({filtered.length})</label><span>{groups.filter(g => g.selected).length} selecionados de {groups.length}</span><button disabled={disabled || !groups.length} onClick={() => void save(groups.map(g => ({ ...g, selected: !groups.every(x => x.selected) })))}>{groups.length && groups.every(g => g.selected) ? 'Desmarcar todos os grupos' : `Selecionar todos os grupos (${groups.length})`}</button></div>
      {!groups.length ? <Empty title="Nenhum grupo carregado">Autorize sua conta e use Atualizar do Telegram.</Empty> : !filtered.length ? <Empty title="Nenhum resultado para este filtro">Tente outro nome ou limpe o filtro de selecionados.</Empty> : <div className="group-list">{filtered.map(g => <label className={'group-row' + (g.selected ? ' checked' : '')} key={g.id}><input type="checkbox" checked={g.selected} disabled={disabled} onChange={() => void save(groups.map(item => item.id === g.id ? { ...item, selected: !item.selected } : item))} /><span>{g.name}</span><code>{g.id}</code></label>)}</div>}
      {!!groups.length && !groups.some(g => g.selected) && <p className="help">Selecione pelo menos um grupo para habilitar o monitor.</p>}
    </>}
  </section>
}
function Simulator({ rules, drafts, pending }: { rules: Rule[]; drafts: Drafts; pending: boolean }) {
  const [text, setText] = useState(''), [result, setResult] = useState<Simulation | null>(null), [error, setError] = useState(''), [working, setWorking] = useState(false)
  const signature = JSON.stringify([text, rules, drafts])
  const [resultSignature, setResultSignature] = useState('')
  async function simulate(e: FormEvent) {
    e.preventDefault(); const problem = validateAllDrafts(rules, drafts)
    if (problem) { setError('Corrija as edições antes de simular: ' + problem.message); return }
    setWorking(true); setError(''); setResult(null)
    try { setResult(await window.api.simulate(text, applyDrafts(rules, drafts))); setResultSignature(signature) } catch (e) { setError(errorText(e)) } finally { setWorking(false) }
  }
  return <section className="section simulator"><h2>Testar uma mensagem</h2><p>Cole uma oferta para entender quais regras correspondem. Não conecta ao Telegram, não envia e não marca mensagens como vistas.</p>{pending && <p className="notice">A simulação usa suas edições ainda não salvas.</p>}
    <form onSubmit={e => void simulate(e)}><label htmlFor="simulation-text">Texto da oferta</label><textarea id="simulation-text" value={text} maxLength={65536} rows={5} onChange={e => setText(e.target.value)} /><button disabled={working || !text.trim() || !rules.length}>{working ? 'Analisando…' : 'Simular regras'}</button></form>
    {error && <Message>{error}</Message>}{result && resultSignature === signature && <div role="status"><h3>{result.winner ? `Alerta pela regra ${result.winner.keyword}` : 'Nenhum alerta seria enviado'}</h3>{!result.evaluations.length && <p>Nenhuma palavra-chave correspondeu.</p>}{result.evaluations.map(ev => <details key={ev.rule_id}><summary>{ev.keyword} · {ev.reason === 'ambiguous_price' ? 'Preço ambíguo' : ev.eligible ? 'Elegível' : ev.reason}</summary><p>{result.winner?.rule_id === ev.rule_id ? 'Regra vencedora.' : ev.eligible ? 'Outra regra tem prioridade.' : 'Oferta filtrada.'} {ev.association?.lines.length ? `Preço associado às linhas ${ev.association.lines.join(', ')}.` : ''}</p><pre>{JSON.stringify({ prices: ev.prices, decisive: ev.decisive, reason: ev.reason }, null, 2)}</pre></details>)}</div>}
  </section>
}
