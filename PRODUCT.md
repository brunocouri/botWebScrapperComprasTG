# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Electron + Vite + React + TypeScript + Tailwind (renderer) + Python CLI + Telethon (processos locais). Sem servidor FastAPI operacional. Contrato IPC em electron/src/lib/ipc.ts.

## Users

**Primário:** pessoas que acompanham grupos de promoções e querem receber alertas por termos e faixas de preço, sem consultar cada grupo manualmente. O acesso usa a própria conta Telegram.

Outros audiences não confirmados.

## Product Purpose

Monitorar keywords exatas (case-insensitive, word-boundary) em grupos selecionados via Userbot MTProto (não Bot API) e alertar em Mensagens Salvas em até 60s. Transformar o Telegram pessoal em sistema de alerta programável. Sucesso = receber `A57` em Salvos antes de ver manualmente, sem FloodWait/ban e sem duplicar.

Framework: mecanismo reutilizável para qualquer keyword/canal, não só A57 — trocar `keywords.json`/`watched_groups.json` sem mudar código.

## Positioning

Userbot com **sua conta** (vê tudo que você vê, sem precisar ser admin) + match exato `\bA57\b` + deduplicação persistente + logs amigáveis com cor (`[OK]/[ALERTA]/[STATS]`) + trava `bot.lock` de instância única. Vizinho (Bot API) não consegue — só vê se for admin.

## Operating Context

- Notebook Windows 24h, `session.session` SQLite, `.env` com `API_ID`/`API_HASH`/`PHONE`
- Workflows: `headless_list_groups.bat` -> edita `watched_groups.json: selected` -> `headless_watch.bat` (`python bot.py --watch`); Electron implementado consome IPC/JSONL e config_cli.py, sem API HTTP
- 25 grupos monitorados, 2 keywords, `logs/bot.log` tail, `bot.lock` PID check, `headless_watch.sh` para Git Bash
- Telegram DC `149.154.175.58:443`, `getDifference` mantido (verificação do passado), `Sincronizando...` amigável (individual com nome, lote agregado)

## Capabilities and Constraints

**Capacidades confirmadas:**
- `ExactMatcher` `\b(A57|Galaxy)\b` RE.IGNORECASE; `A57` != `A570`
- `Notifier` para `me` (Salvos) com `t.me/c/...`, `FloodWait` com `[AGUARDE]` + retry 1x
- `Repo` json (`watched_groups.json` preserva `selected`) + `SeenStore` SQLite implementado
- CLI: `--list-groups`, `--watch`, `--watch --dry-run`, `--help`; `.bat` por comando

**Restrições:**
- Nunca 2 clients na mesma `session` (RULES.md#telegram)
- `session.session` + `bot.lock` obrigatório; `watched_groups.test.json` para testes
- Logs sem emoji, com cor só no console (`_ColorFormatter`), arquivo plain
- Latência até 60s, não <3s

**Estado atual:** SeenStore SQLite, nomes persistidos sem consultas sequenciais no startup, filtros de atividade, regras de preço, simulador e autorização desktop implementados. Validação real da conta/rede é separada dos testes isolados. Outras evidências históricas abaixo não devem ser tratadas como medição atual.

## Brand Commitments

- Nome: `botWebScrapperComprasTG` / `Clonador` (App title em my.telegram.org)
- Voice: logs com prefixos `[OK]` `[ALERTA]` `[STATS]` sem emoji, pt-BR
- Assets: `session.session`, `.env`, `PRD.md`/`SPEC.md`/`AGENTS.md`/`RULES.md`

## Evidence on Hand

- `bot.py` CLI headless rodando 25 grupos, 101 alertas GALAXY em 2 dias, 134 msgs/h (evidence em `logs/bot.log`)
- Listagem e seleção de grupos persistidas em `watched_groups.json`, mantido apenas no ambiente local.
- `keywords.json` `["A57", "Galaxy"]`
- `headless_*.bat` funcionais, `bot.lock` testado
- Sem DESIGN.md ainda — será criado em `new-work`

## Product Principles

1. **Uma sessão, uma verdade** — nunca duplicar `TelegramClient` na mesma `session`
2. **Exato sem ruído** — word-boundary > fuzzy; prefira perder `A570` a spammar `XA57`
3. **Observável sem poluir** — `Sincronizando` amigável (individual nome, lote agregado), `STATS` a cada 100/1h, resto silencioso
4. **CLI primeiro, UI depois** — `backend` roda headless sozinho; Electron consome API, não o contrário
5. **Framework, não script** — trocar keyword/canal não exige mudar `MatcherAgent`/`ListenerAgent`

## Accessibility & Inclusion

Electron deve preservar labels associados, foco visível, teclado, prefers-reduced-motion e contraste AA. Ver docs/IMPLEMENTACAO-MELHORIAS.md para evidências e limitações.
