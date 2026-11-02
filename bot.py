"""
Bot WebScrapper ComprasTG - Userbot Monitor de Keywords
Stack: Telethon (MTProto) | Match exato case-insensitive | Alerta em Mensagens Salvas
SPEC: ./SPEC.md | PRD: ./PRD.md
"""
import asyncio
import json
import logging
import argparse
import sys
import warnings
from pathlib import Path
from datetime import datetime, timezone
import time
import threading
import subprocess
from logging.handlers import RotatingFileHandler
from runtime_safety import FileLock, LockBusy, atomic_write
from configuration import Configuration

# stdout em UTF-8 com replace: o protocolo JSONL pode conter emojis de nomes
# de grupos; sem isso o print quebraria em consoles cp1252 (headless).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def emit(event: dict) -> None:
    """Protocolo de aplicação: 1 objeto JSON por linha no STDOUT.
    STDERR continua com logs humanos. Sem ANSI, UTF-8 preservado."""
    try:
        event = {"at": datetime.now(timezone.utc).isoformat(), **event}
        print(json.dumps(event, ensure_ascii=False), flush=True)
    except (OSError, ValueError, TypeError) as exc:
        print("[ERRO] Falha no protocolo: " + type(exc).__name__, file=sys.stderr, flush=True)

# silencia UserWarning do telethon async sessions (experimental, inofensivo)
warnings.filterwarnings("ignore", category=UserWarning, module="telethon")

from dotenv import load_dotenv
import os
from telethon import TelegramClient, events
from telethon.errors import PhoneCodeExpiredError, FloodWaitError

# --- Setup ---
BASE_DIR = Path(os.environ.get("COMPRAS_DATA_DIR", Path(__file__).resolve().parent))
load_dotenv(BASE_DIR / ".env", override=True)

API_ID = os.getenv("API_ID", "0")
API_HASH = os.getenv("API_HASH", "")
PHONE = os.getenv("PHONE", "")

KEYWORDS_FILE = BASE_DIR / "keywords.json"
WATCHED_FILE = BASE_DIR / "watched_groups.json"
LOG_DIR = BASE_DIR / "logs"


# Logger com cores no console (sem emoji), arquivo limpo sem ANSI
class _ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\x1b[38;5;244m",  # cinza
        "INFO": "\x1b[38;5;39m",    # azul claro
        "WARNING": "\x1b[38;5;214m", # laranja
        "ERROR": "\x1b[38;5;196m",  # vermelho
        "CRITICAL": "\x1b[48;5;196m\x1b[38;5;231m",
    }
    RESET = "\x1b[0m"
    def format(self, record):
        # base sem cor para arquivo
        msg = super().format(record)
        # cor só no StreamHandler
        color = self.COLORS.get(record.levelname, "")
        if color:
            return f"{color}{msg}{self.RESET}"
        return msg

logger = logging.getLogger("bot.compras")
logger.setLevel(logging.INFO)
if not logger.handlers:
    plain_fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    color_fmt = _ColorFormatter("%(asctime)s | %(levelname)s | %(message)s")
    sh = logging.StreamHandler()
    sh.setFormatter(color_fmt)
    logger.addHandler(sh)
    logger.propagate = False

# Nomes carregados uma vez; o filtro nunca lê JSON no caminho de logs.
_chat_names = {}
_last_diff = {"ts": 0, "ids": set()}
class _FriendlyDifferenceFilter(logging.Filter):
    def filter(self, record):
        import re
        msg = record.getMessage()
        match = re.search(r"Got difference for channel (\d+)", msg)
        if match:
            now, cid = time.monotonic(), match[1]
            if now - _last_diff["ts"] >= 2:
                _last_diff.update(ts=now, ids=set())
            _last_diff["ids"].add(cid)
            count = len(_last_diff["ids"])
            if count > 1 and count != 3:
                return False
            name = _chat_names.get('-100' + cid, cid)
            detail = f"Sincronizando {count} canais (lote)…" if count >= 3 else f"Sincronizando {name}…"
            record.msg, record.args = detail, ()
            emit({"type": "sync", "detail": detail})
        elif "Got difference for account" in msg:
            record.msg, record.args = "Sincronizando conta…", ()
            emit({"type": "sync", "detail": record.msg})
        elif "Got state" in msg or "Getting difference" in msg:
            return False
        return True

for _lname in ["telethon", "telethon.client.updates"]:
    _tl = logging.getLogger(_lname)
    _tl.setLevel(logging.INFO)
    _tl.addFilter(_FriendlyDifferenceFilter())
    _tl.propagate = False
    if not _tl.handlers:
        _tl.addHandler(logging.StreamHandler())

# trava de instância única (evita 2x bot.py --watch com mesma session)
LOCK_FILE = BASE_DIR / "bot.lock"

# seen.db (deduplicação persistente + histórico). Independente de session.session.
SEEN_DB = BASE_DIR / "seen.db"

# Domínio em rules.py (F2/F3). evaluate_message mantido por compatibilidade
# (testes); o handler operacional usa evaluate().
from rules import (
    build_pattern, evaluate, select_winner, plan_effects,
    load_rules_config, RulesConfigError, decisive_to_json, format_brl,
)
from storage import SeenStore, StorageError, record_evaluation


def decide_message(store, text, chat_id, msg_id, rules, dry_run: bool = False) -> dict:
    """Orquestra claim → evaluate → plan, sem Telegram (testável F4).
    Retorna {"status": "duplicate"|"no_match"|"decided", ...}.
    StorageError em falha de seen (explícito; at-most-once manda não enviar).
    dry_run não altera a seleção — só rotula o plano."""
    if store.is_seen(chat_id, msg_id):
        return {"status": "duplicate"}
    evaluations = evaluate(text, rules or [])
    if not evaluations:
        return {"status": "no_match"}
    if not store.claim_message(chat_id, msg_id):
        return {"status": "duplicate"}  # perdeu a corrida atômica
    winner, rest = select_winner(evaluations)
    return {"status": "decided", "evaluations": evaluations,
            "winner": winner, "rest": rest,
            "plan": plan_effects(evaluations, dry_run=dry_run)}


def _record(store, chat_id, msg_id, evaluation, sent: bool, status=None, error=None) -> None:
    """Histórico best-effort: falha vira [AVISO], nunca bloqueia alerta."""
    try:
        record_evaluation(store, chat_id, msg_id, evaluation, sent, status, error)
    except StorageError as e:
        logger.warning(f"[AVISO] Falha ao gravar histórico offers: {e} — alerta não afetado")

def evaluate_message(text: str | None, pattern) -> str | None:
    """Domínio puro: retorna a keyword casada ou None.
    Não conecta, não envia, não loga, não escreve arquivos. Testável sem Telegram."""
    if not text or pattern is None:
        return None
    m = pattern.search(text)
    return m.group(1) if m else None


def price_line(decisive) -> str:
    """Formatter: 1 linha de preço para o alerta. Só formata, não decide."""
    if decisive is None:
        return ""
    if decisive["kind"] == "parcela":
        return (f"\n💰 Preço: {decisive['installments']}x de R$ "
                f"{format_brl(decisive['installment_cents'])} "
                f"(total R$ {format_brl(decisive['total_cents'])})")
    suffix = " (à vista)" if decisive["kind"] == "vista" else ""
    return f"\n💰 Preço: R$ {format_brl(decisive['cents'])}{suffix}"


def matched_event(ev: dict, chat_id, message_id: int) -> dict:
    """Construtor puro do evento keyword_matched (testável sem Telegram)."""
    return {"type": "keyword_matched", "rule_id": ev["rule_id"], "keyword": ev["keyword"],
            "prices": ev["prices"], "decisive": decisive_to_json(ev["decisive"]),
            "eligible": ev["eligible"], "reason": ev["reason"],
            "group_id": str(chat_id), "message_id": message_id}


def filtered_event(ev: dict, chat_id, message_id: int, bounds) -> dict:
    """Construtor puro do evento rule_filtered (testável sem Telegram)."""
    return {"type": "rule_filtered", "rule_id": ev["rule_id"], "keyword": ev["keyword"],
            "group_id": str(chat_id), "message_id": message_id,
            "prices": ev["prices"], "decisive": decisive_to_json(ev["decisive"]),
            "bounds": bounds, "reason": ev["reason"]}


def alert_event(ev: dict, chat_id, message_id: int, elapsed_ms: int) -> dict:
    """Construtor puro do evento alert_sent (testável sem Telegram)."""
    return {"type": "alert_sent", "rule_id": ev["rule_id"], "keyword": ev["keyword"],
            "group_id": str(chat_id), "message_id": message_id,
            "decisive": decisive_to_json(ev["decisive"]), "elapsed_ms": elapsed_ms}


def dry_event(ev: dict, chat_id, message_id: int, preview: str) -> dict:
    """Construtor puro do evento dry_run_detected (testável sem Telegram)."""
    return {"type": "dry_run_detected", "rule_id": ev["rule_id"], "keyword": ev["keyword"],
            "group_id": str(chat_id), "message_id": message_id,
            "decisive": decisive_to_json(ev["decisive"]), "preview": preview}

def load_watched_ids() -> list[int]:
    if not WATCHED_FILE.exists():
        return []
    with open(WATCHED_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return [int(g["id"]) for g in data if g.get("selected")]

def format_alert(event, keyword: str, chat_title: str, decisive=None) -> str:
    sender = event.sender
    sender_name = getattr(sender, 'first_name', 'Desconhecido') or 'Desconhecido'
    if getattr(sender, 'last_name', None):
        sender_name += f" {sender.last_name}"
    username = f"@{sender.username}" if getattr(sender, 'username', None) else "sem username"

    # Link t.me/c/ para grupos privados: remove -100 do chat_id
    chat_id = event.chat_id
    msg_id = event.message.id
    # event.chat_id já vem como int positivo ou negativo? Telethon usa -100... para supergroups
    # Para link, precisa do ID sem -100
    raw_id = str(chat_id)
    username_chat = getattr(getattr(event, 'chat', None), 'username', None)
    if raw_id.startswith("-100"):
        link = f"https://t.me/c/{raw_id[4:]}/{msg_id}"
    else:
        link = 'Link direto indisponível para este tipo de grupo.'
    if username_chat:
        link = f'https://t.me/{username_chat}/{msg_id}'

    text = event.message.message or "[mídia sem texto]"
    # Trunca se muito grande
    if len(text) > 800:
        text = text[:800] + "..."

    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return (
        f"🚨 {keyword.upper()} DETECTADO\n\n"
        f"📍 Grupo: {chat_title}\n"
        f"👤 De: {sender_name} ({username})\n"
        f"🕒 Em: {now}\n"
        f"💬 Mensagem: {text}"
        f"{price_line(decisive)}"
        f"\n\n🔗 {link}"
    )

def merge_watched(prev_selected: dict, fetched: list) -> list:
    """Merge por ID (nunca por nome): preserva selected existente, novo=False.
    Grupos que não vieram mais do Telegram saem da lista. Pura e testável."""
    return [
        {"id": g["id"], "name": g["name"], "selected": bool(prev_selected.get(str(g["id"]), False))}
        for g in fetched
    ]

def load_prev_selected() -> dict:
    groups = Configuration(WATCHED_FILE.parent).get_groups()['groups']
    return {str(g['id']): g['selected'] for g in groups}


async def list_groups(client):
    repo = Configuration(WATCHED_FILE.parent)
    repo.get_groups()  # valida antes da operação de rede; nunca perde selected
    dialogs = await asyncio.wait_for(client.get_dialogs(), 45)
    fetched = [{'id': d.id, 'name': d.name or str(d.id)} for d in dialogs if d.is_group or d.is_channel]
    merged = repo.merge_groups(fetched)
    emit({'type': 'groups_loaded', 'count': len(merged)})
    return merged


_session_lock = None


def _acquire_lock():
    global _session_lock
    try:
        lock = FileLock(LOCK_FILE).acquire()
        # Compatibilidade com instância antiga que só escrevia PID.
        try:
            old_pid = int(LOCK_FILE.read_text(encoding='ascii').strip())
        except (ValueError, UnicodeError):
            old_pid = 0
        if old_pid and old_pid != os.getpid():
            if os.name == 'nt':
                result = subprocess.run(['tasklist', '/FI', f'PID eq {old_pid}', '/FO', 'CSV', '/NH'],
                                        capture_output=True, encoding='utf-8', errors='replace', timeout=5)
                if result.returncode != 0:
                    raise OSError('Não foi possível verificar o proprietário da sessão.')
                import csv
                alive = any(len(row) > 1 and row[1] == str(old_pid) for row in csv.reader(result.stdout.splitlines()))
            else:
                try:
                    os.kill(old_pid, 0)
                    alive = True
                except ProcessLookupError:
                    alive = False
            if alive:
                lock.close()
                raise LockBusy('Outra instância já usa a sessão. Pare-a antes de continuar.')
        lock.set_owner()
        _session_lock = lock
        return True
    except OSError:
        if 'lock' in locals():
            lock.close()
        raise


def _release_lock():
    global _session_lock
    if _session_lock is not None:
        lock, _session_lock = _session_lock, None
        # Limpa o proprietário sob o lock, mantendo o mesmo arquivo.
        try:
            lock.file.seek(0)
            lock.file.truncate()
            lock.file.flush()
        finally:
            lock.close()


class AuthenticationRequired(Exception):
    pass


async def connect_authorized(client, desktop=False):
    emit({'type': 'telegram_connecting'})
    await asyncio.wait_for(client.connect(), 45)
    authorized = await asyncio.wait_for(client.is_user_authorized(), 5)
    if not authorized:
        if desktop:
            emit({'type': 'error', 'code': 'auth_required', 'message': 'Autorize a sessão em Configurações.'})
            raise AuthenticationRequired()
        await client.start(phone=PHONE)
    me = await asyncio.wait_for(client.get_me(), 10)
    # Alterar PHONE não substitui uma sessão já autenticada.
    if PHONE and getattr(me, 'phone', None) and PHONE.lstrip('+') != me.phone:
        raise ValueError('A sessão pertence a outro telefone. Preserve-a e configure a conta correta.')
    emit({'type': 'telegram_connected'})
    emit({'type': 'session_authenticated', 'name': me.first_name or '?', 'user_id': me.id})
    return me


def new_stats():
    return dict(msgs=0, alerts=0, duplicates=0, matches=0, filtered=0, dry_runs=0,
                failed=0, by_kw={}, start=time.monotonic(), last_message=None, last_alert=None)


def create_handler(client, store, rules, chat_titles, stats, publish=emit, dry_run=False, sleep=asyncio.sleep, *, catalog=None, alert_ids=None):
    from telethon.errors import FloodWaitError
    bounds = {r['id']: {'min_cents': r.get('min_cents'), 'max_cents': r.get('max_cents')} for r in rules}

    async def handler(event):
        stats['msgs'] += 1
        if stats['msgs'] % 100 == 0:
            logger.info('[STATS] %s mensagens | %s envios | %s falhas', stats['msgs'], stats['alerts'], stats['failed'])
        stats['last_message'] = datetime.now(timezone.utc).isoformat()
        text, cid, mid = event.message.message or '', event.chat_id, event.message.id
        if catalog is not None:
            from catalog_runtime import CATALOG_ERRORS
            try:
                await asyncio.to_thread(catalog.capture_event, event)
            except CATALOG_ERRORS:
                publish({'type': 'error', 'code': 'catalog_failed', 'message': 'Falha no arquivamento. Alertas legados continuam; recuperação pendente.'})
        if alert_ids is not None and cid not in alert_ids:
            return
        try:
            outcome = decide_message(store, text, cid, mid, rules, dry_run)
        except StorageError:
            publish({'type': 'error', 'code': 'storage_failed', 'message': 'Falha de integridade em seen.db. Mensagem não enviada.'})
            return
        if outcome['status'] == 'duplicate':
            stats['duplicates'] += 1
            return
        if outcome['status'] == 'no_match':
            return
        title = chat_titles.get(cid, str(cid))
        preview = text[:70].replace('\n', ' ')
        stats['matches'] += len(outcome['evaluations'])
        for kind, ev in outcome['plan']:
            if kind == 'filtered':
                stats['filtered'] += 1
                logger.info('[INFO] Regra %s filtrada: %s', ev['keyword'], ev['reason'])
                publish({**filtered_event(ev, cid, mid, bounds.get(ev['rule_id'])), 'group_title': title, 'preview': preview})
                _record(store, cid, mid, ev, False, 'filtered')
                continue
            publish({**matched_event(ev, cid, mid), 'group_title': title,
                     'sender': getattr(event.sender, 'first_name', '?') or '?', 'preview': preview})
            logger.info('[ALERTA] MATCH %s em %s', ev['keyword'], title)
            if kind == 'dry':
                stats['dry_runs'] += 1
                logger.info('[DRY] Detectado %s; não enviado.', ev['keyword'])
                publish(dry_event(ev, cid, mid, preview))
                _record(store, cid, mid, ev, False, 'dry_run')
                continue
            alert = format_alert(event, ev['keyword'], title, ev['decisive'])
            started = time.monotonic()
            try:
                try:
                    await client.send_message('me', alert, link_preview=False, parse_mode=None)
                except FloodWaitError as exc:
                    publish({'type': 'flood_wait', 'seconds': exc.seconds})
                    logger.warning('[AGUARDE] Telegram pediu espera %ss', exc.seconds)
                    await sleep(exc.seconds + 1)
                    await client.send_message('me', alert, link_preview=False, parse_mode=None)
            except Exception as exc:
                # Fronteira de envio: erro diagnosticado, sem promover outra regra.
                stats['failed'] += 1
                code = type(exc).__name__
                publish({'type': 'error', 'code': 'send_failed', 'message': f'Falha ao enviar ({code}).',
                         'rule_id': ev['rule_id'], 'group_id': str(cid), 'message_id': mid})
                _record(store, cid, mid, ev, False, 'failed', code)
            else:
                stats['alerts'] += 1
                key = ev['keyword'].upper()
                stats['by_kw'][key] = stats['by_kw'].get(key, 0) + 1
                stats['last_alert'] = datetime.now(timezone.utc).isoformat()
                publish(alert_event(ev, cid, mid, int((time.monotonic() - started) * 1000)))
                logger.info('[OK] Alerta enviado: %s / %s', title, key)
                _record(store, cid, mid, ev, True, 'sent')
    return handler


def stdin_commands():
    """Thread daemon: readline não bloqueia o loop nem impede saída no Windows."""
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    def reader():
        for line in sys.stdin:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if not isinstance(item, dict):
                continue
            try:
                loop.call_soon_threadsafe(queue.put_nowait, item)
            except RuntimeError:
                return
        try:
            loop.call_soon_threadsafe(queue.put_nowait, {'command': 'stop'})
        except RuntimeError:
            return
    threading.Thread(target=reader, daemon=True).start()
    return queue


async def authenticate(client, queue):
    from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PasswordHashInvalidError
    await asyncio.wait_for(client.connect(), 45)
    if await asyncio.wait_for(client.is_user_authorized(), 5):
        await connect_authorized(client, desktop=True)
        emit({'type': 'auth_step', 'step': 'authorized'})
        return
    sent = await asyncio.wait_for(client.send_code_request(PHONE), 45)
    step = 'code'
    emit({'type': 'auth_step', 'step': step})
    while True:
        command = await asyncio.wait_for(queue.get(), 180)
        if command.get('command') == 'stop':
            return
        if command.get('command') != 'auth':
            continue
        value = command.get('value')
        if not isinstance(value, str) or not 1 <= len(value) <= 1024:
            continue
        try:
            if step == 'code':
                await asyncio.wait_for(client.sign_in(phone=PHONE, code=value, phone_code_hash=sent.phone_code_hash), 45)
            else:
                await asyncio.wait_for(client.sign_in(password=value), 45)
        except SessionPasswordNeededError:
            step = 'password'
            emit({'type': 'auth_step', 'step': step})
        except (PhoneCodeInvalidError, PasswordHashInvalidError):
            emit({'type': 'auth_step', 'step': step, 'message': 'Código ou senha inválidos. Tente novamente.'})
        else:
            emit({'type': 'auth_step', 'step': 'authorized'})
            return
        finally:
            command.clear()
            value = None


async def watch_connected(client, dry_run, desktop, queue, config=None):
    from contextlib import nullcontext
    from catalog_runtime import CapturePipeline, capture_sources, ensure_selected_sources, recover_catalog, deliver_structured, CATALOG_ERRORS
    repo = Configuration(BASE_DIR)
    config = config or repo.runtime_config()
    rules, groups = config['rules'], config['groups']
    alert_ids = {g['id'] for g in groups if g['selected']}
    catalog_path = BASE_DIR / 'catalog.db'
    catalog = None
    sources = []
    try:
        sources = [s for s in ensure_selected_sources(catalog_path, groups) if s['enabled']]
        if sources:
            catalog = CapturePipeline(catalog_path)
    except CATALOG_ERRORS:
        emit({'type': 'error', 'code': 'catalog_failed', 'message': 'Catálogo indisponível. Alertas legados continuam.'})
    watched_ids = sorted(alert_ids | {s['id'] for s in sources})
    if not any(r['enabled'] for r in rules) and not sources:
        raise ValueError('Ative uma regra ou habilite arquivamento de um grupo.')
    if not watched_ids:
        raise ValueError('Selecione pelo menos um grupo.')
    snapshot = config['snapshot']
    chat_titles = {g['id']: g['name'] for g in groups}
    chat_titles.update({s['id']: s['name'] for s in sources})
    _chat_names.update({str(k): v for k, v in chat_titles.items()})
    with (SeenStore(SEEN_DB) if alert_ids and any(r['enabled'] for r in rules) else nullcontext(None)) as store:
        stats = new_stats()
        active_alerts = alert_ids if store is not None else set()
        handler = create_handler(client, store, rules, chat_titles, stats, emit, dry_run, catalog=catalog, alert_ids=active_alerts)
        client.add_event_handler(handler, events.NewMessage(chats=watched_ids))
        if catalog:
            async def edited(event):
                try:
                    await asyncio.to_thread(catalog.capture_event, event, True)
                except CATALOG_ERRORS:
                    emit({'type': 'error', 'code': 'catalog_failed', 'message': 'Não foi possível arquivar uma edição observada.'})
            client.add_event_handler(edited, events.MessageEdited(chats=[s['id'] for s in sources]))
        await connect_authorized(client, desktop)
        emit({'type': 'bot_started', 'groups': len(watched_ids), 'keywords': snapshot['keywords']})
        # catch_up após registrar handler: replay passa pela deduplicação.
        emit({'type': 'telegram_syncing'})
        await client.catch_up()
        emit({'type': 'monitoring_started', 'snapshot': snapshot})
        disconnected = asyncio.create_task(client.run_until_disconnected())
        recovery = asyncio.create_task(recover_catalog(client, catalog, sources, emit)) if catalog else None
        structured = asyncio.create_task(deliver_structured(client, catalog_path, {s['id'] for s in sources}, emit, stats, dry_run)) if catalog else None
        last_recovery = time.monotonic()
        last_stats = 0
        last_log = time.monotonic()
        connected = True
        try:
            while True:
                if desktop:
                    try:
                        command = await asyncio.wait_for(queue.get(), .5)
                    except asyncio.TimeoutError:
                        command = {}
                    if command.get('command') == 'stop':
                        return
                else:
                    await asyncio.sleep(.5)
                    stop_file = BASE_DIR / 'bot.stop'
                    if stop_file.exists() and stop_file.read_text().strip() == str(os.getpid()):
                        stop_file.unlink(missing_ok=True)
                        return
                now_connected = client.is_connected()
                if now_connected != connected:
                    connected = now_connected
                    emit({'type': 'connection_state', 'connected': connected})
                if disconnected.done():
                    await disconnected  # preserva erro de atualização do Telethon
                    raise ConnectionError('Conexão com Telegram encerrada.')
                now = time.monotonic()
                if catalog and now - last_recovery >= 60 and recovery is not None and recovery.done():
                    await recovery
                    try:
                        current_sources = capture_sources(catalog_path)
                        # A lista aplicada muda só no reinício explícito.
                        current_sources = [s for s in current_sources if s['id'] in watched_ids]
                        recovery = asyncio.create_task(recover_catalog(client, catalog, current_sources, emit))
                    except CATALOG_ERRORS:
                        emit({'type': 'error', 'code': 'catalog_failed', 'message': 'Recuperação do acervo indisponível.'})
                    last_recovery = now
                if now - last_stats >= 5:
                    last_stats = now
                    emit({'type': 'stats', 'messages': stats['msgs'], 'alerts': stats['alerts'],
                          'duplicates': stats['duplicates'], 'matches': stats['matches'], 'filtered': stats['filtered'],
                          'dry_runs': stats['dry_runs'], 'failed': stats['failed'], 'by_keyword': stats['by_kw'],
                          'uptime_s': int(now - stats['start']), 'last_message': stats['last_message'], 'last_alert': stats['last_alert']})
                if now - last_log >= 3600:
                    last_log = now
                    logger.info('[STATS] %s mensagens | %s envios | %s falhas', stats['msgs'], stats['alerts'], stats['failed'])
        finally:
            if structured is not None:
                structured.cancel()
                try:
                    await structured
                except asyncio.CancelledError:
                    pass
            if recovery is not None:
                recovery.cancel()
                try:
                    await recovery
                except asyncio.CancelledError:
                    pass
            disconnected.cancel()
            try:
                await disconnected
            except asyncio.CancelledError:
                pass


async def run_operation(operation, desktop=False, dry_run=False):
    global API_ID, API_HASH, PHONE
    from telethon.sessions import SQLiteSession
    client = None
    acquired = False
    try:
        _acquire_lock()
        acquired = True
        config = Configuration(BASE_DIR).runtime_config() if operation == 'watch' else None
        if config:
            credentials = config['credentials']
            # Snapshot e credenciais aplicadas pertencem à mesma leitura.
            API_ID = credentials.get('API_ID') or API_ID
            API_HASH = credentials.get('API_HASH') or API_HASH
            PHONE = credentials.get('PHONE') or PHONE
        queue = stdin_commands() if desktop else None
        client = TelegramClient(SQLiteSession(str(BASE_DIR / 'session')), int(API_ID), API_HASH,
                                connection_retries=5, auto_reconnect=True, flood_sleep_threshold=0)
        if operation == 'authenticate':
            if desktop:
                await authenticate(client, queue)
            else:
                await connect_authorized(client)
        elif operation == 'list':
            await connect_authorized(client, desktop)
            await list_groups(client)
        else:
            await watch_connected(client, dry_run, desktop, queue, config)
        emit({'type': 'operation_completed', 'operation': operation})
        return 0
    except LockBusy:
        emit({'type': 'error', 'code': 'session_busy', 'message': 'Outra operação usa a sessão. Pare o monitor antes de continuar.'})
    except AuthenticationRequired:
        pass
    except PhoneCodeExpiredError:
        emit({'type': 'error', 'code': 'auth_expired', 'message': 'Código expirado. Inicie a autorização novamente para receber outro código.'})
    except FloodWaitError as exc:
        emit({'type': 'flood_wait', 'seconds': exc.seconds})
        emit({'type': 'error', 'code': 'rate_limited', 'message': f'Telegram pediu espera de {exc.seconds}s. Aguarde antes de tentar novamente.'})
    except asyncio.TimeoutError:
        emit({'type': 'error', 'code': 'timeout', 'message': 'Tempo esgotado. Verifique a conexão e tente novamente.'})
    except (ValueError, RulesConfigError):
        emit({'type': 'error', 'code': 'config_invalid', 'message': 'Configuração inválida. Revise grupos, regras e credenciais.'})
    except StorageError:
        emit({'type': 'error', 'code': 'storage_failed', 'message': 'Falha ao abrir a deduplicação. Monitoramento não iniciado.'})
    except OSError as exc:
        emit({'type': 'error', 'code': 'connection_or_io', 'message': f'Falha de conexão ou arquivo ({type(exc).__name__}).'})
    except Exception as exc:
        # Fronteira do processo: reportar tipo sem expor credenciais em texto do SDK.
        emit({'type': 'error', 'code': 'operation_failed', 'message': f'Operação falhou ({type(exc).__name__}).'})
    finally:
        if client is not None:
            try:
                await asyncio.wait_for(client.disconnect(), 10)
            except (OSError, asyncio.TimeoutError):
                logger.warning('[AVISO] Falha ao desconectar dentro do prazo.')
        if acquired:
            _release_lock()
    return 1


async def watch_loop(dry_run=False):
    return await run_operation('watch', dry_run=dry_run)


def main():
    parser = argparse.ArgumentParser(description='ComprasTG — monitor de oportunidades no Telegram')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--watch', action='store_true', help='Monitora os grupos selecionados')
    group.add_argument('--list-groups', action='store_true', help='Atualiza grupos preservando seleção')
    group.add_argument('--authenticate', action='store_true', help='Autentica pela interface desktop')
    group.add_argument('--stop', action='store_true', help='Solicita parada somente deste monitor headless')
    parser.add_argument('--dry-run', action='store_true', help='Não envia; marca mensagens em seen.db')
    parser.add_argument('--desktop', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.stop:
        if not LOCK_FILE.exists() or not LOCK_FILE.read_text().strip():
            print('[INFO] Nenhum monitor identificado.')
            return 0
        try:
            owner = json.loads(LOCK_FILE.read_text())
            pid = owner['pid'] if isinstance(owner, dict) and owner.get('version') == 2 else None
        except (ValueError, KeyError):
            pid = None
        if type(pid) is not int:
            print('[AVISO] Instância antiga: pare pelo terminal que a iniciou.')
            return 1
        atomic_write(BASE_DIR / 'bot.stop', str(pid))
        print('[INFO] Parada solicitada. Aguardando o monitor encerrar.')
        return 0
    if not (args.watch or args.list_groups or args.authenticate):
        parser.print_help()
        return 0
    if not API_ID.isdigit() or not int(API_ID) or not API_HASH or not PHONE:
        emit({'type': 'error', 'code': 'config_invalid', 'message': 'Preencha API ID, API Hash e telefone em Configurações.'})
        return 1
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(LOG_DIR / 'bot.log', maxBytes=5 * 1024 * 1024, backupCount=4, encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
    logger.addHandler(fh)
    try:
        return asyncio.run(run_operation('authenticate' if args.authenticate else 'list' if args.list_groups else 'watch',
                                         args.desktop, args.dry_run))
    except KeyboardInterrupt:
        logger.info('[INFO] Parado pelo usuário.')
        return 0
    finally:
        logger.removeHandler(fh)
        fh.close()


if __name__ == '__main__':
    sys.exit(main())
