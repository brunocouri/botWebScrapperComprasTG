import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from catalog_cli import dispatch_catalog
from catalog_storage import Catalog, SCHEMA
from extraction import extract, validate_template
from runtime_safety import FileLock, LockBusy
from test_catalog import START, NOW, template


def configured(tmp_path):
    db = Catalog(tmp_path / 'catalog.db')
    db.set_source(-1001, 'Canal', True, now=START)
    draft = db.save_draft(template(), 0)
    db.publish('single', draft['revision'])
    return db


def test_hidden_entity_utf16_and_button_preserved_without_download(tmp_path):
    from telethon.tl.types import MessageEntityTextUrl
    text = '\U0001f4f1 Comprar'
    event = SimpleNamespace(chat_id=-1001, message=SimpleNamespace(
        id=1, message=text, date=datetime.fromisoformat(NOW), edit_date=None, media=SimpleNamespace(),
        entities=[MessageEntityTextUrl(offset=3, length=7, url='https://s.shopee.com.br/x')],
        reply_markup=SimpleNamespace(rows=[SimpleNamespace(buttons=[SimpleNamespace(text='Loja', url='https://example.org')])])))
    with configured(tmp_path) as db:
        rid = db.capture_event(event)
        metadata = db.message(rid)['metadata']
        assert metadata['links'][0]['start'] == 2
        assert metadata['links'][0]['url'] == 'https://s.shopee.com.br/x'
        assert metadata['buttons'][0]['url'] == 'https://example.org'


def test_rollback_capture_and_job_is_one_transaction(tmp_path, monkeypatch):
    with configured(tmp_path) as db:
        monkeypatch.setattr(db, '_enqueue', lambda *a, **kw: (_ for _ in ()).throw(sqlite3.OperationalError('disk')))
        with pytest.raises(sqlite3.OperationalError):
            db.capture(-1001, 1, NOW, 'texto')
        assert db.status()['messages'] == 0
        assert db.sources()[0]['checkpoint'] == START


def test_old_revision_worker_does_not_replace_newer_result_and_reversal_is_revision(tmp_path):
    with configured(tmp_path) as db:
        a = db.capture(-1001, 1, NOW, 'Produto: A57\nPix: R$ 10')
        b = db.capture(-1001, 1, NOW, 'Produto: A57\nPix: R$ 20', edited_at='2026-10-30T13:00:00+00:00', is_edit=True)
        db.capture(-1001, 1, NOW, 'Produto: A57\nPix: R$ 5', edited_at='2026-10-30T12:00:00+00:00', is_edit=True)
        db.process_batch()
        assert db.search({})['items'][0]['revision_id'] == b
        c = db.capture(-1001, 1, NOW, 'Produto: A57\nPix: R$ 10', edited_at='2026-10-30T14:00:00+00:00', is_edit=True)
        assert c != a
        db.process_batch()
        assert db.search({})['items'][0]['revision_id'] == c
        assert db.status()['runs'] == 4


def test_pause_new_interval_excludes_gap(tmp_path):
    with Catalog(tmp_path / 'catalog.db') as db:
        db.set_source(-1001, 'Canal', True, now=START)
        db.set_source(-1001, 'Canal', False, now=NOW)
        db.set_source(-1001, 'Canal', True, resume='now', now='2026-10-30T13:00:00+00:00')
        assert db.capture(-1001, 1, '2026-10-30T12:00:00+00:00', 'gap') is None
        assert db.capture(-1001, 2, '2026-10-30T14:00:00+00:00', 'nova') is not None


def test_template_type_conflict_revision_check_and_published_immutable(tmp_path):
    with configured(tmp_path) as db:
        with pytest.raises(ValueError, match='outra janela'):
            db.save_draft(template(), 0)
        changed = template()
        changed['fields'][1]['type'] = 'text'
        d = db.save_draft(changed, 2)
        with pytest.raises(ValueError, match='imutável'):
            db.publish('single', d['revision'])
        original = json.loads(db.db.execute('SELECT payload FROM template_versions WHERE version=1').fetchone()[0])
        assert original['fields'][1]['type'] == 'money'


def test_preview_detects_existing_template_conflicts(tmp_path):
    with configured(tmp_path):
        pass
    t = {**template(), 'id': 'second'}
    result = dispatch_catalog({'action': 'preview', 'template': t, 'text': 'Produto: A57\nPix: R$ 10'}, tmp_path)
    assert result['state'] == 'ambiguous_template'


def test_explicit_scope_prevents_coupon_inheritance_and_unknown_link_contamination():
    t = template()
    t['fields'].append({'field_id': 'url', 'name': 'Link', 'type': 'link', 'op': 'link'})
    text = 'Produto: A\nPix: R$ 10\n---\nProduto: B\nPix: R$ 20'
    result = extract(text, [t], links=[{'url': 'https://example.org', 'origin': 'button'}])
    assert all(o['values']['url']['value'] is None for o in result['offers'])


def test_explicit_header_coupon_scope_and_installments():
    t = template()
    t['block_marker'] = 'Produto:'
    t['fields'][2]['scope'] = 'message'
    t['fields'].append({'field_id': 'card', 'name': 'Cartão', 'type': 'installments', 'op': 'after', 'marker': 'Cartão:', 'scope': 'price', 'option': 'Cartão'})
    result = extract('Cupom: APP10\n---\nProduto: A\nPix: R$ 10\nCartão: 2x R$ 6\n---\nProduto: B\nPix: R$ 20\nCartão: 2x R$ 12', [t])
    assert result['state'] == 'done'
    assert len(result['offers']) == 2
    assert all(o['values']['coupon']['value'] == 'APP10' for o in result['offers'])
    assert result['offers'][0]['values']['card']['value']['total_cents'] == 1200


def test_condition_absent_requires_explicit_configuration():
    t = template()
    t['fields'][3]['absence'] = 'absent'
    result = extract('Produto: A\nPix: R$ 10', [t])
    assert result['offers'][0]['values']['app']['value'] == 'absent'


def test_non_offer_template_classifies_without_fields():
    t = {**template(), 'markers': ['Bom dia'], 'fields': [], 'kind': 'ignore'}
    assert extract('Bom dia, boas compras', [t])['state'] == 'ignored'


def test_resume_cancelled_batch_and_progress_survive_new_process(tmp_path):
    with configured(tmp_path) as db:
        db.capture(-1001, 1, NOW, 'Produto: A57\nPix: R$ 10')
        db.process_batch()
        p = db.reprocess_preview({'source_id': -1001})
        db.reprocess_confirm(p['token'])
    dispatch_catalog({'action': 'reprocess:cancel', 'token': p['token']}, tmp_path)
    assert dispatch_catalog({'action': 'reprocess:list'}, tmp_path)[0]['cancelled'] == 1
    dispatch_catalog({'action': 'reprocess:resume', 'token': p['token']}, tmp_path)
    with Catalog(tmp_path / 'catalog.db') as db:
        assert db.process_batch()['processed'] == 1
    assert dispatch_catalog({'action': 'reprocess:list'}, tmp_path)[0]['done'] == 1


def test_search_filters_same_offer_not_two_different_products(tmp_path):
    with configured(tmp_path) as db:
        db.capture(-1001, 1, NOW, 'Produto: A57\nPix: R$ 200\n---\nProduto: Mouse\nPix: R$ 10')
        db.process_batch()
        assert db.search({'values': [{'field_id': 'product', 'text': 'A57'}, {'field_id': 'pix', 'max': 1000}]})['total'] == 0
        assert db.search({'query': "' OR 1=1 --"})['total'] == 0
        assert db.search({'store': 'Shopee'})['total'] == 0


def test_worker_exclusion_and_subprocess_no_telegram(tmp_path):
    with configured(tmp_path) as db:
        db.capture(-1001, 1, NOW, 'Produto: A57\nPix: R$ 10')
        with FileLock((tmp_path / 'catalog.db').with_suffix('.worker.lock')):
            with pytest.raises(LockBusy):
                db.process_batch()
    run = subprocess.run([sys.executable, 'etl_worker.py', '--once'], cwd=Path(__file__).resolve().parents[1],
                         env={**os.environ, 'COMPRAS_DATA_DIR': str(tmp_path)}, capture_output=True, text=True, timeout=10)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)['processed'] == 1
    assert not (tmp_path / 'session.session').exists()
    assert not (tmp_path / 'seen.db').exists()


def test_additive_migration_has_consistent_backup(tmp_path):
    path = tmp_path / 'catalog.db'
    with sqlite3.connect(path) as old:
        old.executescript(SCHEMA.replace(' allow_alerts INTEGER NOT NULL DEFAULT 0,', ''))
        old.execute('PRAGMA user_version=1')
    with Catalog(path) as db:
        assert db.db.execute('PRAGMA user_version').fetchone()[0] == 4
        assert 'allow_alerts' in [r['name'] for r in db.db.execute('PRAGMA table_info(processing_jobs)')]
    assert Path(str(path) + '.before-v4.bak').exists()


def test_consistent_backup_includes_committed_wal(tmp_path):
    with configured(tmp_path) as db:
        db.capture(-1001, 1, NOW, 'mensagem')
        target = tmp_path / 'backup.db'
        db.backup(target)
    with Catalog(target) as restored:
        assert restored.status()['messages'] == 1


def test_cancel_reprocess_does_not_erase_results(tmp_path):
    with configured(tmp_path) as db:
        db.capture(-1001, 1, NOW, 'Produto: A57\nPix: R$ 10')
        db.process_batch()
        p = db.reprocess_preview({'source_id': -1001})
        db.reprocess_confirm(p['token'])
    dispatch_catalog({'action': 'reprocess:cancel', 'token': p['token']}, tmp_path)
    with Catalog(tmp_path / 'catalog.db') as db:
        assert db.status()['pending'] == 0
        assert db.search({})['total'] == 1


def test_archive_only_monitor_does_not_open_seen(tmp_path):
    import bot
    event = SimpleNamespace(chat_id=-1001, sender=None, message=SimpleNamespace(
        id=1, message='Produto: A57\nPix: R$ 10', date=datetime.fromisoformat(NOW)))
    from catalog_runtime import CapturePipeline
    with configured(tmp_path):
        pass
    client = SimpleNamespace(send_message=AsyncMock())
    handler = bot.create_handler(client, None, [], {}, bot.new_stats(), lambda e: None,
                                 catalog=CapturePipeline(tmp_path / 'catalog.db'), alert_ids=set())
    asyncio.run(handler(event))
    with Catalog(tmp_path / 'catalog.db') as db:
        assert db.status()['messages'] == 1
    client.send_message.assert_not_called()
    assert not (tmp_path / 'seen.db').exists()


@pytest.mark.parametrize('op', ['eval', 'regex', 'python'])
def test_arbitrary_code_is_rejected(op):
    t = template()
    t['fields'][0]['op'] = op
    with pytest.raises(ValueError):
        validate_template(t)
