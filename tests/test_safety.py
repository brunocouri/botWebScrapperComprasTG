import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_lock_exclui_segundo_processo_e_recupera_apos_morte(tmp_path):
    from runtime_safety import FileLock, LockBusy
    path = tmp_path / 'session.lock'
    code = ('from runtime_safety import FileLock; import sys; '
            'lock=FileLock(sys.argv[1]).acquire(); print("ready",flush=True); sys.stdin.read()')
    proc = subprocess.Popen([sys.executable, '-c', code, str(path)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == 'ready'
        with pytest.raises(LockBusy):
            FileLock(path).acquire()
    finally:
        proc.kill()
        proc.wait(timeout=5)
        proc.stdin.close()
        proc.stdout.close()
    with FileLock(path):
        assert path.exists()


def test_lock_falha_fechado_e_nao_remove_arquivo(tmp_path):
    from runtime_safety import FileLock
    with pytest.raises(OSError):
        FileLock(tmp_path / 'ausente' / 'bot.lock').acquire()
    path = tmp_path / 'bot.lock'
    with FileLock(path):
        inode = path.stat().st_ino
    assert path.stat().st_ino == inode


def test_metadados_do_lock_podem_ser_lidos_por_parada(tmp_path):
    from runtime_safety import FileLock
    path = tmp_path / 'bot.lock'
    with FileLock(path) as lock:
        lock.set_owner()
        assert json.loads(path.read_text())['pid'] == os.getpid()


def test_atomic_write_preserva_original_em_falha(tmp_path, monkeypatch):
    from runtime_safety import atomic_write
    path = tmp_path / 'keywords.json'
    path.write_text('original', encoding='utf-8')
    def fail(*args):
        raise PermissionError('bloqueado')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(PermissionError):
        atomic_write(path, 'novo')
    assert path.read_text() == 'original'
    assert list(tmp_path.iterdir()) == [path]


def test_config_corrompida_nao_e_sobrescrita(tmp_path):
    from configuration import Configuration
    path = tmp_path / 'keywords.json'
    path.write_text('{truncado', encoding='utf-8')
    repo = Configuration(tmp_path)
    with pytest.raises(ValueError):
        repo.add_rule('A57')
    assert path.read_text() == '{truncado'


def test_migracao_tem_ids_estaveis_backup_e_conflito(tmp_path):
    from configuration import Configuration, ConfigConflict
    path = tmp_path / 'keywords.json'
    path.write_text('["A57"]', encoding='utf-8')
    repo = Configuration(tmp_path)
    first = repo.get_rules()
    second = repo.get_rules()
    assert first == second
    assert Path(str(path) + '.bak').read_text() == '["A57"]'
    repo.add_rule('Galaxy')
    with pytest.raises(ConfigConflict):
        repo.save_rules(first['rules'], first['revision'])
    assert len(repo.get_rules()['rules']) == 2


def test_groups_invalidos_nao_perdem_selected(tmp_path):
    from configuration import Configuration
    path = tmp_path / 'watched_groups.json'
    path.write_text('[{"id": 1, "name": "g", "selected": "sim"}]', encoding='utf-8')
    repo = Configuration(tmp_path)
    with pytest.raises(ValueError):
        repo.merge_groups([{'id': 1, 'name': 'renomeado'}])
    assert json.loads(path.read_text())[0]['selected'] == 'sim'


def test_env_preserva_chaves_e_mascara_segredo(tmp_path):
    from configuration import Configuration
    path = tmp_path / '.env'
    path.write_text('OUTRA=preservar\nAPI_HASH=' + 'a' * 32 + '\n', encoding='utf-8')
    repo = Configuration(tmp_path)
    cfg = repo.get_config()
    assert 'a' * 32 not in json.dumps(cfg)
    repo.save_config({'apiId': '123456', 'phone': '+5511999999999', 'apiHash': ''}, cfg['revision'])
    assert 'OUTRA=preservar' in path.read_text()
    assert 'API_HASH=' + 'a' * 32 in path.read_text()


def test_simulador_cli_nao_toca_dados(tmp_path):
    root = Path(__file__).resolve().parents[1]
    payload = {'operation': 'simulate', 'text': 'A57 R$ 1.899', 'rules': [
        {'id': 'a57', 'term': 'A57', 'enabled': True, 'min_cents': None, 'max_cents': 190000}]}
    result = subprocess.run([sys.executable, str(root / 'config_cli.py')], input=json.dumps(payload),
                            capture_output=True, text=True, cwd=tmp_path, timeout=5)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['winner']['rule_id'] == 'a57'
    assert list(tmp_path.iterdir()) == []
