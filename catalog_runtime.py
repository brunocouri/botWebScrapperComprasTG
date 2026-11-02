"""Fronteira entre recepção MTProto e catálogo. Não possui TelegramClient."""
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sqlite3

from catalog_storage import Catalog


CATALOG_ERRORS = (OSError, sqlite3.Error, ValueError)


class CapturePipeline:
    def __init__(self, path):
        self.path = Path(path)
        import threading
        self._capture_lock = threading.Lock()

    def capture_event(self, event, is_edit=False, live=True):
        with self._capture_lock:
            with Catalog(self.path) as db:
                return db.capture_event(event, is_edit, live)


def capture_sources(path):
    if not Path(path).exists():
        return []
    with Catalog(path) as db:
        return [s for s in db.sources() if s['enabled']]


def ensure_selected_sources(path, groups):
    if not Path(path).exists() and not any(g['selected'] for g in groups):
        return []
    with Catalog(path) as db:
        return db.ensure_selected(groups)


async def recover_catalog(client, pipeline, sources, publish):
    """Cursor temporal de lote, nunca avançado pela recepção ao vivo."""
    until = datetime.now(timezone.utc)
    for source in sources:
        try:
            # Datas Telegram têm precisão de segundos; sobreposição evita perder
            # mensagens no segundo do checkpoint. Capture é idempotente.
            start = datetime.fromisoformat(source['capture_started_at'])
            after = max(start, datetime.fromisoformat(source['checkpoint'] or source['capture_started_at']) - timedelta(seconds=1))
            async for message in client.iter_messages(source['id'], offset_date=after, reverse=True):
                if message.date > until:
                    break
                event = type('CapturedEvent', (), {'chat_id': source['id'], 'message': message})()
                await asyncio.to_thread(pipeline.capture_event, event, False, False)
            with Catalog(pipeline.path) as db:
                db.checkpoint(source['id'], until)
        except Exception as exc:
            # Fronteira de recuperação: rede/catálogo falhos não encerram alertas.
            code = type(exc).__name__
            try:
                with Catalog(pipeline.path) as db:
                    db.mark_degraded(source['id'], code)
            except CATALOG_ERRORS:
                pass
            publish({'type': 'error', 'code': 'catalog_failed', 'message': f'Coleta degradada em {source["name"]} ({code}); alertas legados continuam.'})


async def deliver_structured(client, path, source_ids, publish, stats, dry_run=False):
    from telethon.errors import FloodWaitError
    import time

    def claim():
        with Catalog(path) as db:
            return db.claim_alert(source_ids)

    def finish(delivery_id, state, error=None):
        with Catalog(path) as db:
            db.finish_alert(delivery_id, state, error)

    while True:
        try:
            item = await asyncio.to_thread(claim)
            if not item:
                await asyncio.sleep(1)
                continue
            values = '\n'.join(f'{v["name"]}: {v["raw"] or "não informado"}' for v in item['payload']['values'].values())
            # Mantém margem para nomes/links, sem ultrapassar o limite do Telegram.
            alert = f'[ALERTA] {item["rule_name"]}\n{values[:3000]}'
            if str(item['source_id']).startswith('-100'):
                alert += f'\nhttps://t.me/c/{str(item["source_id"])[4:]}/{item["message_id"]}'
            if dry_run:
                await asyncio.to_thread(finish, item['id'], 'dry_run')
                stats['dry_runs'] += 1
                continue
            started = time.monotonic()
            try:
                try:
                    await client.send_message('me', alert, link_preview=False, parse_mode=None)
                except FloodWaitError as exc:
                    publish({'type': 'flood_wait', 'seconds': exc.seconds})
                    await asyncio.sleep(exc.seconds + 1)
                    await client.send_message('me', alert, link_preview=False, parse_mode=None)
            except Exception as exc:
                stats['failed'] += 1
                await asyncio.to_thread(finish, item['id'], 'failed', type(exc).__name__)
                publish({'type': 'error', 'code': 'catalog_failed', 'message': f'Alerta estruturado falhou ({type(exc).__name__}). Veja o histórico de entregas.'})
            else:
                await asyncio.to_thread(finish, item['id'], 'sent')
                stats['alerts'] += 1
                stats['last_alert'] = datetime.now(timezone.utc).isoformat()
                publish({'type': 'alert_sent', 'rule_id': item['rule_id'], 'keyword': item['rule_name'],
                         'group_id': str(item['source_id']), 'message_id': item['message_id'], 'elapsed_ms': int((time.monotonic() - started) * 1000)})
        except CATALOG_ERRORS as exc:
            publish({'type': 'error', 'code': 'catalog_failed', 'message': f'Alertas estruturados indisponíveis ({type(exc).__name__}). Alertas legados continuam.'})
            await asyncio.sleep(5)
