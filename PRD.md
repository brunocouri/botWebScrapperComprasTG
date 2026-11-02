# PRD - Bot WebScrapper ComprasTG (Userbot Monitor de Keywords)

> Registro histórico do MVP v0.1. O escopo evoluiu para Electron, regras de preço, SQLite, simulador e autenticação desktop; consultar docs/IMPLEMENTACAO-MELHORIAS.md para o estado atual e limites da validação.

**Versão:** 0.1 | **Data:** 18/09/2026 | **Status:** Draft
**Autor:** Bruno | **Objetivo:** Alertar quando palavra-chave aparecer em grupos selecionados

---

## 1. Visão Geral
Criar um bot que roda com a CONTA PESSOAL do Telegram (Userbot via MTProto) para monitorar mensagens em tempo real. Ao detectar uma palavra-chave cadastrada (ex: `A57`), enviar alerta imediato em `Mensagens Salvas`.

**Motivação:** Celular quebrou, oportunidade de compra depende de ser o primeiro a ver `A57`.

**Restrição Crítica:** Não usar Bot API. Bot API só vê mensagens se for admin do grupo. Userbot vê tudo que sua conta vê.

## 2. Personas
- **Primary:** Bruno - precisa ser notificado em até 1 minuto após `A57` aparecer em qualquer grupo selecionado.

## 3. User Stories

| ID | História | Critério de Aceite |
|---|---|---|
| US01 | Como usuário quero cadastrar/editar/remover palavras-chave | CRUD via arquivo `keywords.json` ou comando `/add A57` no Saved Messages |
| US02 | Como usuário quero listar meus grupos e selecionar quais monitorar | Ao iniciar, bot lista todos os dialogs do tipo Group/Channel e salva `watched_groups.json` com IDs selecionados |
| US03 | Como usuário quero receber alerta em Mensagens Salvas | Formato: `🚨 ALERTA: A57\n📍 Grupo: [Nome] \n👤 Autor: @user\n💬 Msg: [conteúdo]\n🔗 Link: t.me/c/...` |
| US04 | Como usuário quero que o match seja EXATO e CASE-INSENSITIVE | `A57` alerta em `compro A57` e `a57`, mas NÃO em `A570`, `XA57`, `A57PRO` |
| US05 | Como usuário quero rodar 24h no notebook | Auto-reconnect, log em arquivo, reconexão após sleep/hibernação |

## 4. Requisitos Funcionais (MVP)

- **RF01 - Autenticação:** Login via `API_ID` + `API_HASH` (my.telegram.org) + `phone` + `code`. Gera `session.session` para não logar toda vez.
- **RF02 - Keywords:** `keywords.json` = `["A57", "A58"]`. Match exato com word boundary regex: `\bA57\b` com flag `re.IGNORECASE`.
- **RF03 - Seleção de Grupos:** Comando `python bot.py --list-groups` lista grupos com `ID | Nome | Members`. Usuário edita `watched_groups.json` marcando `true/false`. Alternativa: interativo no terminal.
- **RF04 - Listener:** `events.NewMessage(chats=watched_groups_ids)` - escuta apenas grupos selecionados.
- **RF05 - Notificação:** `client.send_message('me', alerta)` -> Mensagens Salvas. Com delay tolerado de até 60s.
- **RF06 - Deduplicação:** Não re-alertar mesma `message.id` do mesmo `chat_id`. Log em `alerts.db` ou memória.
- **RF07 - Logs:** `logs/bot.log` com timestamp de cada mensagem escaneada e alerta enviado.

## 5. Requisitos Não-Funcionais

- **RNF01 - Latência:** Até 60 segundos (relaxado, sem necessidade de <3s).
- **RNF02 - Disponibilidade:** Rodar contínuo no notebook Windows. Deve sobreviver a reconexão de internet e hibernação (loop com `auto_reconnect=True`).
- **RNF03 - Performance:** Suportar 20-50 grupos simultâneos sem CPU alta. Uso de `asyncio`.
- **RNF04 - Segurança:** `.env` nunca commitado. `session.session` ignorado no `.gitignore`.
- **RNF05 - Manutenibilidade:** Código único `bot.py` < 250 linhas no MVP.

## 6. Fora do Escopo (v1)
- Dashboard web
- Compra automática / resposta automática
- Múltiplas contas
- Filtro por preço, regex complexo, IA
- Notificação por e-mail/WhatsApp

## 7. Critérios de Sucesso (MVP Done)
1. Bot conecta com sua conta e lista seus grupos reais
2. Você marca 3 grupos para monitorar
3. Alguém digita `A57` em um deles -> em até 60s você recebe alerta em Mensagens Salvas com link correto
4. `A570` NÃO gera alerta (match exato validado)

## 8. Riscos
- **R01 - FloodWait / Ban:** Mitigação: apenas leitura + 1 msg por alerta, sem spam.
- **R02 - Notebook hiberna:** Mitigação: instruir `Power Options > Never Sleep when plugged in` + `pm2` ou `task scheduler`.
- **R03 - Sessão expirada:** Mitigação: documentar como re-gerar `session.session`.

## 9. Próximos Passos
PRD aprovado -> SPEC.md -> `bot.py` MVP
