# AGENTS.md — botWebScrapperComprasTG

> Framework CLI + Electron para monitoramento de keywords no Telegram via Userbot MTProto.

## Visão Geral
5 agentes especializados, cada um dono de uma pasta e um contrato. Comunicação via Electron IPC (`electron/electron/main.ts`) + eventos JSONL no stdout do processo Python.

> Estado atual: `bot.py` (CLI/runtime), `rules.py`, `price_parser.py`, `storage.py`, `configuration.py`, `config_cli.py` e `runtime_safety.py` na raiz. `backend/app/*` e FastAPI são layout planejado, NÃO implementado. Os nomes Agent abaixo representam responsabilidades, não classes existentes.

Desenvolvimento por TDD e Spec Driven Development. Testes focados, sem Playwright, sempre com dados temporários. Este workspace não tem artisan; a instrução de limpar config Laravel é inaplicável aqui. Não autenticar nem enviar ao Telegram real como parte de testes automatizados.

```
Renderer (Electron) --IPC invoke--> main --spawn--> bot.py --Observer--> Telegram (MTProto)
                    <--bot:event (JSONL stdout)--
```

---

## 1. BotAgent — `bot.py` / `runtime_safety.py`

**Papel:** Dono exclusivo do `TelegramClient`.

**Responsabilidades:**
- Carregar `.env` (`API_ID`, `API_HASH`, `PHONE`) e `session.session` (`SQLiteSession`).
- Garantir exclusividade via FileLock do SO antes de abrir a sessão em watch, listagem e autenticação. PID é metadado; o arquivo permanece no disco e não deve ser apagado para forçar concorrência.
- Conexão/autorização com limites; desktop tem código/2FA explícitos, sem input invisível no terminal. Preservar sessão se PHONE for de outra conta.
- Logar `[SESSAO] Sessao valida (Clonador) — Nick (1234567890)`.

**Entrada:** `.env` | **Saída:** `TelegramClient` autorizado.

**Regras:**
- Nunca 2 clients na mesma `session` (ver `RULES.md#telegram`).
- Usar `SQLiteSession(str(BASE_DIR / "session"))` + `auto_reconnect=True` + `connection_retries=5`.
- Timeout `connect 45s`, `is_user_authorized 5s`.

---

## 2. ListenerAgent — `bot.py`

**Papel:** Escutar `events.NewMessage(chats=watched_ids)`.

**Responsabilidades:**
- Resolver `watched_ids` via `RepoAgent`.
- Manter verificação do passado (`getDifference`) — não ignorar histórico.
- Publicar `event.message` para `MatcherAgent`.
- Usar nomes persistidos; não consultar todas as entidades sequencialmente no startup. Registrar handler antes da recuperação/catch_up e deduplicar replay.

**Entrada:** `List[int] watched_ids` + `Pattern` | **Saída:** `telethon.events.NewMessage.Event`.

**Regras:**
- Não bloquear UI: rede no processo Python, com eventos operacionais por JSONL.
- `Got difference` individual → `Sincronizando Nome (ID)`, lote 3+ em 2s → `Sincronizando 25 canais (lote)` (filtro `_FriendlyDifferenceFilter`).

---

## 3. MatcherAgent — `rules.py` / `price_parser.py`

**Papel:** Decidir se mensagem casa com keyword.

**Responsabilidades:**
- Matching puro por regex exata/case-insensitive, com termos escapados e compilação cacheada.
- Detectar regras correspondentes antes de extrair preços. BRL em centavos, limites inclusivos, IDs estáveis e primeira regra elegível por mensagem.
- Associação conservadora de produto/preço; com faixa e ambiguidade, filtrar e mostrar ambiguous_price. Domínio sem Telegram/Electron; simulador sem efeitos.

**Entrada:** `str text` | **Saída:** `keyword | None`.

**Regras:**
- `A57` == `a57`, `A57,` == `A57`, `A570` != `A57`, `XA57` != `A57`.
- Testável com `pytest` sem Telegram (mock).

---

## 4. NotifierAgent — `bot.py` / `storage.py`

**Papel:** Alertar em `Mensagens Salvas` e logar.

**Responsabilidades:**
- Deduplicar por `(chat_id, message_id)` via SeenStore SQLite, com claim antes dos efeitos. Falha em seen impede envio; offers é best-effort e registra desfecho separado de elegibilidade.
- `client.send_message("me", alert, link_preview=False)` com `t.me/c/{id}/{msg}`.
- Tratar FloodWait tipado pelo campo seconds, com retry 1x após sleep(seconds+1). Não procurar a palavra wait em qualquer erro.
- Estatísticas distinguem recebido, duplicado, filtrado, simulado, falho e enviado. Contar envio somente após sucesso. Logar STATS a cada 100 msgs e 1h.

**Entrada:** `MATCH` | **Saída:** `Salvos` + `bot.log`.

**Regras:**
- Prefixos sem emoji: `[OK]`, `[ALERTA]`, `[DRY]`, `[AGUARDE]`, `[ERRO]`, `[STATS]`.
- Cores só no console (`_ColorFormatter`), arquivo `bot.log` plain.

---

## 5. RepoAgent — `configuration.py` / `config_cli.py` / `storage.py`

**Papel:** Abstrair persistência.

**Implementações:**
- Configuration é a camada única de mutação para CLI/Electron; preserva selected por ID, backups e IDs estáveis na migração.
- Saves exigem revisão e substituição atômica. Erro de leitura nunca vira lista vazia. Não sobrescrever conflito silenciosamente.
- SeenStore para seen.db (PRIMARY KEY chat_id,msg_id). Não expirar deduplicação nem excluir histórico automaticamente.
- Testes usam diretórios temporários, nunca sobrescrevem dados reais.

**Entrada:** `selected: true/false` | **Saída:** `List[WatchedGroup]`.

---

## 6. UIAgents — `electron/src/App.tsx` / `electron/src/features/Activity.tsx`

**GroupsAgent — App.tsx**
- Checkboxes nativos e estado misto. Selecionar resultados não altera grupos ocultos pelo filtro.
- Atualização do Telegram é exclusiva e preserva selected; reload não pode disputar a sessão.

**KeywordsAgent — App.tsx / lib/keywords.ts**
- Linhas com prioridade, estado e faixa; edição preserva ID. Salvar N alterações considera todos os rascunhos, inclusive de editores fechados.
- Navegação não descarta rascunhos. Falha preserva entradas. Simulador usa o mesmo domínio Python sem sessão, migração ou bancos.

**LogsAgent — features/Activity.tsx / lib/feed-store.ts**
- Buffer de sessão limitado e atualizado em lotes. Filtros estruturados e detalhes; navegar não limpa eventos.
- Rolagem manual pausa acompanhamento também no modo técnico. Virtualizar só se a medição justificar.

**MainAgent — `electron/electron/main.ts`**
- Processo Python exclusivo, mantido até close/error; parada cooperativa por stdin, fallback somente no filho.
- Monitorando exige evento operacional, não spawn aceito. Mostrar divergência entre configuração salva/aplicada e reinício explícito.
- Validar origem/frame IPC, JSONL runtime e UTF-8 incremental. Renderer sem Node, com contextIsolation e sandbox. Código/2FA não entram em argv, eventos ou arquivos.
- Fechar o app encerra seu monitor; prevenir perda de rascunhos. Labels/foco/contraste são parte do contrato.
- Tray, auto-start: planejado, não implementado.

---

## Contratos

- `electron/src/lib/ipc.ts`: tipos dos canais IPC + eventos `bot:event` (fonte de verdade do contrato).
- `shared/ipc.schema.json`: rascunho REST/WebSocket antigo — desatualizado, não usar até ser reescrito.
- `backend` nunca importa `electron/`.

## Catálogo ETL opcional

- `catalog_storage.py`: catalog.db, fontes, revisões, modelos, fila e projeções.
- `extraction/`: motor declarativo puro; não executar regex/scripts do usuário.
- `catalog_runtime.py`: captura/recuperação e entrega estruturada usando o cliente
  recebido; não criar outro TelegramClient. Falhas do catálogo não bloqueiam alertas legados.
- `catalog_cli.py` / `etl_worker.py`: operações locais sem sessão Telegram; worker exclusivo,
  retomável e sem alertas retroativos de preview/reprocessamento/recuperação.
- `electron/src/lib/catalog.ts`: contrato de catálogo complementar a ipc.ts.
- `electron/src/features/Catalog*.tsx` / `StructuredAlerts.tsx`: coleta, acervo,
  modelos, revisão, busca, reprocessamento e alertas estruturados opcionais.
- Grupos selected recebem Arquivar habilitado por padrão na inicialização do
  catálogo/monitor; não reativar pausas existentes nem reconstruir o passado.
  A coleta pode ser pausada separadamente dos alertas. Não importar antes do marco
  UTC nem apagar dados/locks automaticamente. Specs em docs/SPEC-ETL.md.
