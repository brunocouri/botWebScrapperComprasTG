import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from catalog_storage import Catalog
from extraction import extract


START = '2026-10-30T10:00:00+00:00'
NOW = '2026-10-30T11:00:00+00:00'


def template():
    return {'id': 'single', 'name': 'Oferta', 'source_id': -1001,
            'markers': ['Produto:', 'Pix:'], 'delimiter': '\n---\n', 'fields': [
                {'field_id': 'product', 'name': 'Produto', 'type': 'text', 'op': 'after', 'marker': 'Produto:', 'required': True},
                {'field_id': 'pix', 'name': 'Preço Pix', 'type': 'money', 'op': 'after', 'marker': 'Pix:', 'required': True},
                {'field_id': 'coupon', 'name': 'Cupom', 'type': 'text', 'op': 'after', 'marker': 'Cupom:'},
                {'field_id': 'app', 'name': 'Somente app', 'type': 'condition', 'op': 'presence', 'marker': 'no app'},
            ]}


def capture(db, text='Produto: A57\nPix: R$ 1.899,90', **kw):
    return db.capture(-1001, 1, NOW, text, **kw)


def test_capture_cutoff_idempotence_revisions_and_atomic_queue(tmp_path):
    with Catalog(tmp_path / 'catalog.db') as db:
        assert capture(db) is None
        db.set_source(-1001, 'Canal', True, now=START)
        assert db.capture(-1001, 2, '2020-01-01T00:00:00+00:00', 'antiga') is None
        first = capture(db)
        assert capture(db) == first
        assert len(db.messages()['items']) == 1
        assert db.status()['pending'] == 1
        second = capture(db, 'editada', edited_at='2026-10-30T12:00:00+00:00', is_edit=True)
        assert first != second
        assert db.message(first)['text'].startswith('Produto:')
        capture(db, 'fora de ordem', edited_at='2026-10-30T11:30:00+00:00', is_edit=True)
        assert db.messages()['items'][0]['text'] == 'editada'
        assert db.capture(-1001, 99, NOW, 'edição desconhecida', is_edit=True) is None


def test_pause_resume_needs_choice_preserves_cutoff(tmp_path):
    with Catalog(tmp_path / 'catalog.db') as db:
        db.set_source(-1001, 'Canal', True, now=START)
        db.set_source(-1001, 'Canal', False, now=NOW)
        with pytest.raises(ValueError):
            db.set_source(-1001, 'Canal', True)
        source = db.set_source(-1001, 'Canal', True, resume='recover')
        assert source['capture_started_at'] == START


def test_extraction_blocks_evidence_condition_and_no_coupon_math():
    result = extract('Produto: A57\nPix: R$ 1.899,90\nCupom: GALAXY100\n---\nProduto: Mouse\nPix: R$ 30', [template()])
    assert result['state'] == 'done'
    a, b = result['offers']
    assert a['values']['pix']['value'] == 189990
    assert a['values']['coupon']['value'] == 'GALAXY100'
    assert b['values']['coupon']['value'] is None
    assert b['values']['app']['value'] == 'unknown'
    assert a['values']['pix']['raw'] == 'R$ 1.899,90'
    assert a['values']['pix']['start'] >= 0


def test_template_conflict_missing_ambiguous_price_and_unknown():
    t = template()
    assert extract('nada', [t])['state'] == 'unknown_format'
    assert extract('Produto: A57\nPix: R$ 20', [t, {**t, 'id': 'other'}])['state'] == 'ambiguous_template'
    assert extract('Produto:\nPix: R$ 20', [t])['state'] == 'extraction_error'
    assert extract('Produto: A57\nPix: R$ 20 ou R$ 30', [t])['state'] == 'ambiguous_field'


def test_worker_publish_reprocess_preserves_history_and_search(tmp_path):
    with Catalog(tmp_path / 'catalog.db') as db:
        db.set_source(-1001, 'Canal', True, now=START)
        rid = capture(db)
        assert db.process_batch()['processed'] == 1
        assert db.reviews()['items'][0]['count'] == 1
        draft = db.save_draft(template(), expected=0)
        assert db.templates()[0]['published'] is None
        db.publish('single', expected=draft['revision'])
        db.process_batch()
        offers = db.search({'field_id': 'pix', 'max': 190000})
        assert offers['total'] == 1
        assert db.search({'field_id': 'pix', 'max': 100})['total'] == 0
        assert db.message(rid)['text'].startswith('Produto:')
        preview = db.reprocess_preview({'source_id': -1001})
        assert preview['count'] == 1
        db.reprocess_confirm(preview['token'])
        db.process_batch()
        assert db.search({})['total'] == 1
        assert db.status()['runs'] == 3


def test_link_host_boundary_hidden_links_and_buttons():
    t = {**template(), 'markers': ['Produto:'], 'fields': [
        {'field_id': 'url', 'name': 'Comprar', 'type': 'link', 'op': 'link'}]}
    rules = [{'host': 's.shopee.com.br', 'store': 'Shopee', 'subdomains': False}]
    r = extract('Produto: X', [t], links=[{'url': 'https://s.shopee.com.br/a', 'origin': 'button'}], link_rules=rules)
    assert r['offers'][0]['values']['url']['value']['store'] == 'Shopee'
    r = extract('Produto: https://s.shopee.com.br.evil.test', [t], link_rules=rules)
    assert r['offers'][0]['values']['url']['value']['store'] is None


def test_catalog_failure_does_not_block_legacy_alert(tmp_path):
    import bot
    from storage import SeenStore
    event = SimpleNamespace(chat_id=-1001, sender=None, message=SimpleNamespace(
        id=1, message='A57', date=datetime.now(timezone.utc)))
    broken = SimpleNamespace(capture_event=lambda *a, **kw: (_ for _ in ()).throw(OSError('disk')))
    client, received = SimpleNamespace(send_message=AsyncMock()), []
    with SeenStore(tmp_path / 'seen.db') as store:
        h = bot.create_handler(client, store, [{'id': 'a', 'term': 'A57', 'enabled': True}], {}, bot.new_stats(), received.append,
                               catalog=broken, alert_ids={-1001})
        asyncio.run(h(event))
    assert client.send_message.await_count == 1
    assert any(e.get('code') == 'catalog_failed' for e in received)


def test_replay_does_not_reprocess_completed_message_on_new_template(tmp_path):
    with Catalog(tmp_path / 'catalog.db') as db:
        db.set_source(-1001, 'Canal', True, now=START)
        d = db.save_draft(template(), 0)
        db.publish('single', d['revision'])
        capture(db)
        db.process_batch()
        t = template()
        t['fields'][1]['name'] = 'Pix anunciado'
        d = db.save_draft(t, 2)
        db.publish('single', d['revision'])
        capture(db)
        assert db.status()['pending'] == 0


def test_structured_alert_new_only_idempotent_and_not_reprocessing(tmp_path):
    with Catalog(tmp_path / 'catalog.db') as db:
        db.set_source(-1001, 'Canal', True, now=START)
        d = db.save_draft(template(), 0)
        db.publish('single', d['revision'])
        rules = [{'id': 'cheap', 'name': 'A57 Pix', 'enabled': True, 'source_id': -1001,
                  'filters': {'values': [{'field_id': 'pix', 'max': 190000}, {'field_id': 'product', 'text': 'A57'}]}}]
        db.save_alert_rules(rules, 0, now=START)
        capture(db, live=True)
        db.process_batch()
        ready = db.claim_alert()
        assert ready['rule_name'] == 'A57 Pix'
        assert db.claim_alert() is None
        db.finish_alert(ready['id'], 'sent')
        p = db.reprocess_preview({'source_id': -1001})
        db.reprocess_confirm(p['token'])
        db.process_batch()
        assert db.claim_alert() is None
        db.capture(-1001, 2, NOW, 'Produto: A57\nPix: R$ 10', live=False)
        db.process_batch()
        assert db.claim_alert() is None


def test_worker_transaction_rollback_resume(tmp_path, monkeypatch):
    import catalog_storage
    with Catalog(tmp_path / 'catalog.db') as db:
        db.set_source(-1001, 'Canal', True, now=START)
        capture(db)
        original = catalog_storage.extract
        monkeypatch.setattr(catalog_storage, 'extract', lambda *a: (_ for _ in ()).throw(RuntimeError('crash')))
        with pytest.raises(RuntimeError):
            db.process_batch()
        assert db.status()['pending'] == 1
        assert db.status()['runs'] == 0
        monkeypatch.setattr(catalog_storage, 'extract', original)
        assert db.process_batch()['processed'] == 1


def test_recovery_failure_keeps_checkpoint_and_respects_boundary(tmp_path):
    from catalog_runtime import CapturePipeline, recover_catalog
    path = tmp_path / 'catalog.db'
    with Catalog(path) as db:
        db.set_source(-1001, 'Canal', True, now=START)
        sources = db.sources()
    seen_kwargs = []
    async def iter_messages(cid, **kwargs):
        seen_kwargs.append(kwargs)
        yield SimpleNamespace(id=1, date=datetime.fromisoformat(NOW), message='Texto', entities=[], media=None)
        raise ConnectionError('rede')
    published = []
    client = SimpleNamespace(iter_messages=iter_messages)
    asyncio.run(recover_catalog(client, CapturePipeline(path), sources, published.append))
    assert seen_kwargs[0]['offset_date'] == datetime.fromisoformat(START)
    with Catalog(path) as db:
        assert db.sources()[0]['checkpoint'] == START
        assert db.sources()[0]['degraded'] == 'ConnectionError'
        assert db.status()['messages'] == 1
