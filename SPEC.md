# SPEC TÉCNICO - Bot WebScrapper ComprasTG

> Documento histórico do MVP v0.1. O estado implementado de 29/10/2026 está em docs/ARCHITECTURE.md, docs/SPEC-PRECO.md e docs/IMPLEMENTACAO-MELHORIAS.md. A estrutura e o limite de linhas abaixo não descrevem mais o código atual.

**Versão:** 0.1 | **Stack:** Python 3.11 + Telethon 1.40 + SQLite (opcional) | **SO:** Windows 11 (Notebook 24h)

---

## 1. Arquitetura

```
[ Telegram Cloud ]
       |
       | MTProto (Telethon Client, sua conta)
       v
[ bot.py - Event Loop asyncio ]
  -> 1. SessionManager (session.session)
  -> 2. ConfigLoader (.env, keywords.json, watched_groups.json)
  -> 3. GroupResolver (get_dialogs -> lista IDs)
  -> 4. MessageListener (events.NewMessage)
  -> 5. KeywordMatcher (regex \bkeyword\b, re.IGNORECASE)
  -> 6. Notifier (client.send_message('me', ...))
  -> 7. Logger (logs/bot.log)
```

**Decisão Arquitetural:** Telethon > Pyrogram. Telethon tem `get_dialogs()` mais estável para listar grupos e `events.NewMessage(chats=[])` nativo. Pyrogram exige tratamento manual.

## 2. Fluxo Detalhado

1. **Init:** `client = TelegramClient('session', API_ID, API_HASH)` -> `await client.start(phone)`
2. **Bootstrap Grupos (primeira vez):** `python bot.py --list-groups`
   - `dialogs = await client.get_dialogs()`
   - Filtra `dialog.is_group or dialog.is_channel`
   - Gera `watched_groups.json`:
     ```json
     [
       {"id": -100123456789, "name": "Grupo Compras SP", "selected": false},
       {"id": -100987654321, "name": "Achados A57", "selected": true}
     ]
     ```
   - Usuário edita `selected: true` manualmente (mais simples e confiável que UI terminal)
3. **Loop Principal:**
   ```python
   watched_ids = [g['id'] for g in config if g['selected']]
   keywords_pattern = re.compile(r'\b(' + '|'.join(map(re.escape, keywords)) + r')\b', re.IGNORECASE)

   @client.on(events.NewMessage(chats=watched_ids))
   async def handler(event):
       text = event.message.message or ""
       match = keywords_pattern.search(text)
       if match:
           keyword = match.group(1).upper() # normaliza
           # Deduplicação: dict cache { (chat_id, message_id): True }
           await client.send_message('me', format_alert(event, keyword))
           logger.info(f"ALERTA {keyword} em {event.chat_id}")
   ```
4. **Match Exato:** Regex com `\b` (word boundary).
   - `re.search(r'\bA57\b', 'vendo A57 hoje', re.I)` -> MATCH
   - `re.search(r'\bA57\b', 'vendo A570', re.I)` -> NO MATCH (correto)
   - Considerar pontuação: `\b` já lida com `A57,` `A57.` `A57!`

## 3. Modelo de Dados

### 3.1 `.env` (não commitado)
```
API_ID=123456
API_HASH=abc123hash
PHONE=+5511999999999
```

### 3.2 `keywords.json`
```json
["A57", "A58", "IPHONE 15"]
```

### 3.3 `watched_groups.json`
Gerado automaticamente, editado manualmente.

### 3.4 `alerts_log.json` (ou SQLite futuro)
Para deduplicação simples em memória + log em disco:
```json
[{"chat_id": -100123, "msg_id": 456, "keyword": "A57", "at": "2026-09-18T10:00:00Z"}]
```

## 4. Estrutura de Arquivos (MVP)

```
botWebScrapperComprasTG/
├── bot.py                 # < 250 linhas, entry point
├── config.py              # loader de .env + json
├── requirements.txt       # telethon, python-dotenv
├── .env.example           # template
├── .gitignore             # .env, session.session, __pycache__, logs/
├── keywords.json
├── watched_groups.json
├── session.session        # gerado após login
└── logs/
    └── bot.log
```

## 5. Requisitos de Sistema (Notebook 24h)

- **Windows:** Desativar hibernação: `Configurações > Sistema > Energia > Tela e suspensão > Nunca` quando conectado.
- **Auto-restart:** Criar `.bat` + `Task Scheduler` para iniciar com Windows: `python bot.py --watch`
- **Internet:** `client` com `connection_retries=5`, `auto_reconnect=True`

## 6. Tratamento de Erros

| Erro | Ação |
|---|---|
| `FloodWaitError (seconds=XX)` | `await asyncio.sleep(seconds)` + log |
| `SessionPasswordNeededError` | Pedir 2FA password no terminal |
| `ConnectionResetError` | Loop `while True: try: await client.run_until_disconnected()` |
| Mensagem editada (`MessageEdited`) | (Fora MVP) - futuro: escutar `events.MessageEdited` também |

## 7. Comandos CLI (MVP)

```bash
pip install -r requirements.txt

# 1. Primeira vez: lista grupos
python bot.py --list-groups

# 2. Editar watched_groups.json e keywords.json manualmente

# 3. Rodar monitor
python bot.py --watch

# 4. Testar sem enviar alerta real (dry-run)
python bot.py --watch --dry-run
```

## 8. Formato do Alerta (Mensagens Salvas)

```
🚨 A57 DETECTADO

📍 Grupo: Achados A57 (ID: -100123...)
👤 De: João Silva (@joao)
🕒 Em: 18/09/2026 10:15:23
💬 Mensagem: "Vendo A57 zerado 128gb 1500"

🔗 https://t.me/c/123456789/456
```

Link `t.me/c/` funciona para grupos privados (pega `chat_id` sem `-100`).

## 9. Testes (Validação Manual MVP)

1. Criar grupo privado de teste com 2 contas
2. Adicionar `A57` em `keywords.json`
3. Enviar `a57` (lowercase) -> deve alertar
4. Enviar `A570` -> NÃO deve alertar
5. Enviar `A57,` -> deve alertar (pontuação)
6. Medir tempo entre envio e alerta em Saved Messages (deve ser <60s)

## 10. Evolução Pós-MVP
- `events.MessageEdited` para pegar edições
- Filtro por mídia/foto com legenda
- Dashboard simples em `http://localhost:8000` para editar keywords sem editar JSON
- Docker para VPS

## 11. Próximo Passo Imediato
Gerar `bot.py` + `config.py` + `requirements.txt` + `.env.example` conforme este SPEC.
