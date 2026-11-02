# RULES.md — Regras Duras

> Quebrar uma regra = bug em produção (sessão revogada, log duplicado, freeze).

## 1. Telegram (MTProto)

- **1 client por session:** Sempre `SQLiteSession(str(BASE_DIR / "session"))` + lock do SO compartilhado por watch, listagem e autenticação. PID é metadado; não apagar bot.lock para forçar concorrência.
- **Conexão:** `TelegramClient(..., connection_retries=5, auto_reconnect=True)` + `await asyncio.wait_for(connect, 45s)` + `is_user_authorized 5s`.
- **`getDifference`:** Manter verificação do passado. Não ignorar histórico. Log amigável via `_FriendlyDifferenceFilter`:
  - Individual `1 canal` → `Sincronizando Nome (ID) - buscando mensagens perdidas...`
  - Lote `3+ em 2s` → `Sincronizando 25 canais - buscando mensagens perdidas (lote)...`
  - `Got difference for account` → `Sincronizando conta...`
  - `Got state`/`Getting difference` vazio → filtrado (`return False`).
- **IDs:** `watched_groups.json` usa `-100...` (supergroup). `Got difference` loga sem `-100` - mapear via `gid.endswith(cid)`.
- **Warnings:** `warnings.filterwarnings("ignore", UserWarning, module="telethon")` para `async sessions support is an experimental feature`.

## 2. Código & Concorrência

- **Logger:** `logging.getLogger("bot.compras")` com `if not handlers` + `propagate=False`. `telethon` em `INFO` com filtro, nunca `basicConfig` duplicado.
- **Lock:** `FileLock` exclusivo antes de abrir a sessão, com falha fechada. O arquivo permanece; o SO libera a trava inclusive após morte abrupta. Parada/encerramento aguardam close/error do filho.
- **UI:** Rede roda no processo Python. Electron usa IPC e checkboxes nativos; orientações antigas de Rich/Textual não se aplicam à interface React.
- **Deduplicação:** SeenStore SQLite, PRIMARY KEY(chat_id,msg_id), claim antes dos efeitos. Falha em seen impede envio; offers é best-effort. Não expirar seen automaticamente.

## 3. Logs (sem emoji, com cor)

- **Console:** `_ColorFormatter` - `INFO` azul `38;5;39`, `WARNING` laranja `214`, `ERROR` vermelho `196`, `RESET`. Arquivo `logs/bot.log` plain sem ANSI.
- **Prefixos obrigatórios:**
  - `[OK]` - iniciado, grupos resolvidos, alerta enviado
  - `[SESSAO]` - `Sessao valida (Clonador) — Nick (id)`
  - `[ALERTA]` - `MATCH 'A57' em [Grupo] por User — "preview"`
  - `[DRY]` - `Dry-run: detectado mas NAO enviado`
  - `[AGUARDE]` - `Telegram pediu espera Xs (FloodWait)`
  - `[ERRO]` - falhas
  - `[STATS]` - `X msgs escaneadas (Y/h) | Z alertas (A57:1) | uptime`
  - `[INFO]` - monitoramento iniciado, duplicado
  - `[AVISO]` - grupo não encontrado
- **Stats:** A cada `100 msgs` + `3600s` via `_stats_tick` com `cancel()` no `finally`.
- **Arquivo:** `logs/bot.log` com `FileHandler(encoding="utf-8")`, nunca `StreamHandler` duplicado.

## 4. Persistência & Pastas

- **Contracts:** `electron/src/lib/ipc.ts` é a fonte de verdade. shared/ipc.schema.json é legado sem autoridade. `backend` nunca importa `electron/`.
- **Repo:** Configuration/config_cli.py são a única camada operacional de mutação. Grupos preservam selected por ID; saves usam revisão e substituição atômica. Erro de leitura nunca vira lista vazia. Testes usam diretórios temporários, nunca arquivos reais.
- **Estrutura:**
  ```
  backend/app/{core,services,repository,api} + bot.py (CLI)
  electron/src/{main,preload,renderer/features/{groups,keywords,logs}}
  shared/ipc.schema.json
  docs/{PRD,SPEC,ARCHITECTURE}.md
  ```
- **.env:** Nunca commit. `session.session` ignorado. `API_ID`/`PHONE` via `load_dotenv`.

## 5. UX & Performance

- **Pattern:** `re.compile(r"\b(" + "|".join(map(re.escape, keywords)) + r")\b", re.IGNORECASE)` - sem `re` a cada mensagem.
- **chat_titles:** Lazy ou `asyncio.gather` - não 25x `get_entity` sequencial no startup (3.5s hoje é limite).
- **Electron:** Monitorando exige evento operacional; salvar é distinto de aplicar. Preservar rascunhos após falha. Seleção filtrada não altera grupos ocultos. Rolagem manual pausa acompanhamento. Labels/foco/contraste fazem parte do contrato.
- **Ctrl+C:** Mantém `SIGINT` para parar, `Ctrl+Shift+C` para copiar. Não interceptar.

## 6. Testes

- `python -m py_compile bot.py` + `pytest` sem rede (mock `TelegramClient`).
- `headless_watch.bat` + `headless_watch --dry-run` para validar `A57` vs `A570` sem enviar.
- Parada: `python bot.py --stop` solicita encerramento somente deste monitor. Nunca encerrar processos Python por nome nem apagar locks ativos.
- Spec Driven Development e TDD, com testes focados e sem Playwright. Este projeto não tem artisan; limpeza de config Laravel é inaplicável.
- Smoke compilado: em electron/, `npm run build` e `npm run smoke`, sem Telegram real.
