import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bot
from storage import SeenStore


def rules():
    return [{'id': 'a57', 'term': 'A57', 'enabled': True, 'min_cents': None, 'max_cents': None},
            {'id': 'galaxy', 'term': 'Galaxy', 'enabled': True, 'min_cents': None, 'max_cents': None}]


def message():
    return SimpleNamespace(chat_id=-100123, sender=None, message=SimpleNamespace(id=1, message='Galaxy A57'))


def test_grupo_basico_nao_recebe_link_privado_invalido():
    event = message()
    event.chat_id = -123
    assert 't.me/c/123/' not in bot.format_alert(event, 'A57', 'Grupo básico')


@pytest.mark.parametrize('failure', [None, RuntimeError('network wait is not FloodWait')])
def test_handler_real_envio_confirmado_e_falha_sem_promover(tmp_path, failure):
    client = SimpleNamespace(send_message=AsyncMock(side_effect=failure))
    received = []
    stats = bot.new_stats()
    with SeenStore(tmp_path / 'seen.db') as store:
        handler = bot.create_handler(client, store, rules(), {-100123: 'Grupo'}, stats, received.append)
        asyncio.run(handler(message()))
        assert client.send_message.await_count == 1
        assert stats['alerts'] == (0 if failure else 1)
        assert stats['failed'] == (1 if failure else 0)
        asyncio.run(handler(message()))
        assert client.send_message.await_count == 1
        assert stats['duplicates'] == 1
        assert store.count_seen() == 1
        offers = store.fetch_offers()
        assert len(offers) == 2
        if failure:
            assert any(o['delivery_status'] == 'failed' for o in offers)
    assert not any(e['type'] == 'flood_wait' for e in received)


def test_dry_run_marca_mas_nao_conta_envio(tmp_path):
    client = SimpleNamespace(send_message=AsyncMock())
    stats = bot.new_stats()
    with SeenStore(tmp_path / 'seen.db') as store:
        handler = bot.create_handler(client, store, rules(), {}, stats, lambda e: None, dry_run=True)
        asyncio.run(handler(message()))
        assert stats['alerts'] == 0
        assert stats['dry_runs'] == 1
        assert store.is_seen(-100123, 1)
    client.send_message.assert_not_called()


def test_floodwait_tipado_retry_unico_conta_um_envio(tmp_path):
    from telethon.errors import FloodWaitError
    client = SimpleNamespace(send_message=AsyncMock(side_effect=[FloodWaitError(None, capture=2), None]))
    sleep = AsyncMock()
    stats, received = bot.new_stats(), []
    with SeenStore(tmp_path / 'seen.db') as store:
        handler = bot.create_handler(client, store, rules(), {}, stats, received.append, sleep=sleep)
        asyncio.run(handler(message()))
    assert client.send_message.await_count == 2
    sleep.assert_awaited_once_with(3)
    assert stats['alerts'] == 1
    assert next(e for e in received if e['type'] == 'alert_sent')['elapsed_ms'] >= 0


def test_desktop_sem_sessao_nao_pede_input_e_desconecta(tmp_path, monkeypatch):
    client = SimpleNamespace(connect=AsyncMock(), is_user_authorized=AsyncMock(return_value=False),
                             disconnect=AsyncMock())
    received = []
    monkeypatch.setattr(bot, 'emit', received.append)
    with pytest.raises(bot.AuthenticationRequired):
        asyncio.run(bot.connect_authorized(client, desktop=True))
    assert any(e.get('code') == 'auth_required' for e in received)


def test_lista_grupos_config_corrompida_nao_sobrescreve(tmp_path, monkeypatch):
    path = tmp_path / 'watched_groups.json'
    path.write_text('{corrompido')
    monkeypatch.setattr(bot, 'BASE_DIR', tmp_path)
    monkeypatch.setattr(bot, 'WATCHED_FILE', path)
    client = SimpleNamespace(get_dialogs=AsyncMock(return_value=[]))
    with pytest.raises(ValueError):
        asyncio.run(bot.list_groups(client))
    assert path.read_text() == '{corrompido'


def test_runtime_desconecta_e_libera_lock_apos_autorizacao_ausente(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, 'BASE_DIR', tmp_path)
    monkeypatch.setattr(bot, 'LOCK_FILE', tmp_path / 'bot.lock')
    monkeypatch.setattr(bot, 'SEEN_DB', tmp_path / 'seen.db')
    (tmp_path / 'keywords.json').write_text('["A57"]')
    (tmp_path / 'watched_groups.json').write_text('[{"id":-100123,"name":"g","selected":true}]')
    client = SimpleNamespace(connect=AsyncMock(), is_user_authorized=AsyncMock(return_value=False),
                             disconnect=AsyncMock(), add_event_handler=lambda *args: None)
    monkeypatch.setattr(bot, 'TelegramClient', lambda *args, **kwargs: client)
    monkeypatch.setattr(bot, 'stdin_commands', asyncio.Queue)
    assert asyncio.run(bot.run_operation('watch', desktop=True)) == 1
    client.disconnect.assert_awaited_once()
    from runtime_safety import FileLock
    with FileLock(tmp_path / 'bot.lock'):
        assert (tmp_path / 'bot.lock').read_text() == ''


def test_cancelar_autenticacao_nao_tenta_signin(monkeypatch):
    client = SimpleNamespace(connect=AsyncMock(), is_user_authorized=AsyncMock(return_value=False),
                             send_code_request=AsyncMock(return_value=SimpleNamespace(phone_code_hash='fake')),
                             sign_in=AsyncMock())
    async def run():
        queue = asyncio.Queue()
        await queue.put({'command': 'stop'})
        await bot.authenticate(client, queue)
    asyncio.run(run())
    client.sign_in.assert_not_awaited()


def test_autenticacao_expirada_tem_diagnostico_especifico(tmp_path, monkeypatch):
    from telethon.errors import PhoneCodeExpiredError
    client = SimpleNamespace(connect=AsyncMock(), is_user_authorized=AsyncMock(return_value=False),
                             send_code_request=AsyncMock(return_value=SimpleNamespace(phone_code_hash='fake')),
                             sign_in=AsyncMock(side_effect=PhoneCodeExpiredError(None)), disconnect=AsyncMock())
    monkeypatch.setattr(bot, 'BASE_DIR', tmp_path)
    monkeypatch.setattr(bot, 'LOCK_FILE', tmp_path / 'bot.lock')
    monkeypatch.setattr(bot, 'TelegramClient', lambda *args, **kwargs: client)
    monkeypatch.setattr('telethon.sessions.SQLiteSession', lambda *args: None)
    queue = asyncio.Queue()
    queue.put_nowait({'command': 'auth', 'value': 'codigo-ficticio'})
    monkeypatch.setattr(bot, 'stdin_commands', lambda: queue)
    received = []
    monkeypatch.setattr(bot, 'emit', received.append)
    assert asyncio.run(bot.run_operation('authenticate', desktop=True)) == 1
    assert any(e.get('code') == 'auth_expired' for e in received)
    assert 'codigo-ficticio' not in str(received)
