import json

import pytest

from catalog_runtime import ensure_selected_sources
from catalog_storage import Catalog
from config_cli import dispatch


GROUPS = [{'id': -1001, 'name': 'Selecionado', 'selected': True},
          {'id': -1002, 'name': 'Outro', 'selected': False}]


def test_defaults_only_selected_and_keeps_cutoff_and_pause(tmp_path):
    path = tmp_path / 'catalog.db'
    ensure_selected_sources(path, GROUPS)
    with Catalog(path) as db:
        assert len(db.sources()) == 1
        source = db.sources()[0]
        assert source['id'] == -1001
        assert source['enabled'] == 1
        db.set_source(-1001, source['name'], False)
    ensure_selected_sources(path, GROUPS)
    with Catalog(path) as db:
        assert db.sources()[0]['capture_started_at'] == source['capture_started_at']
        assert db.sources()[0]['enabled'] == 0


@pytest.mark.parametrize('action', ['sources', 'status'])
def test_ipc_defaults_existing_selected_without_telegram(tmp_path, action):
    (tmp_path / 'watched_groups.json').write_text(json.dumps(GROUPS), encoding='utf-8')
    result = dispatch({'operation': 'catalog', 'action': action}, tmp_path)
    sources = result if action == 'sources' else result['sources']
    assert sources[0]['id'] == -1001
    assert sources[0]['enabled'] == 1
    assert not (tmp_path / 'session.session').exists()
    assert not (tmp_path / 'seen.db').exists()


def test_no_database_created_if_no_selected_or_existing_catalog(tmp_path):
    assert ensure_selected_sources(tmp_path / 'catalog.db', [GROUPS[1]]) == []
    assert not (tmp_path / 'catalog.db').exists()


def test_newly_selected_group_gets_default_without_changing_existing_sources(tmp_path):
    path = tmp_path / 'catalog.db'
    ensure_selected_sources(path, GROUPS)
    ensure_selected_sources(path, [GROUPS[0], {**GROUPS[1], 'selected': True}])
    with Catalog(path) as db:
        assert {s['id'] for s in db.sources() if s['enabled']} == {-1001, -1002}


def test_default_initialization_does_not_change_applied_snapshot(tmp_path):
    from configuration import Configuration
    (tmp_path / 'watched_groups.json').write_text(json.dumps(GROUPS), encoding='utf-8')
    before = Configuration(tmp_path).snapshot()
    ensure_selected_sources(tmp_path / 'catalog.db', GROUPS)
    assert Configuration(tmp_path).snapshot() == before
