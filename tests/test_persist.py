"""Integração de persistência da configuração (auditoria item 3).
Arquivo temporário; nunca o keywords.json real. Simula exatamente o que
o Electron faz: JSON.stringify({version:2, rules}, null, 2)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from rules import load_rules_file, migrate_file


def write_ts_shape(path: Path, rules: list) -> None:
    """Replica byte a byte o que main.ts grava: JSON.stringify({version:2,rules},null,2)."""
    path.write_text(json.dumps({"version": 2, "rules": rules}, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def test_v1_migracao_edicao_ui_save_reload():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "keywords.json"
        p.write_text('["A57", "Galaxy"]', encoding="utf-8")

        # 1. startup Python migra
        migrated = migrate_file(p)
        ids = [r["id"] for r in migrated]
        assert len(set(ids)) == 2
        bak = Path(str(p) + ".bak")
        assert bak.read_text(encoding="utf-8") == '["A57", "Galaxy"]'

        # 2. edição equivalente à UI: rename + max, preservando id/ordem
        v, rules = load_rules_file(p)
        assert v == 2
        rules[0]["term"] = "A57 5G"
        rules[0]["max_cents"] = 190000
        write_ts_shape(p, rules)  # exatamente como keywords:save grava

        # 3. reload Python: tudo idêntico, nada normalizado por baixo
        v2, reloaded = load_rules_file(p)
        assert v2 == 2
        assert [r["id"] for r in reloaded] == ids
        assert [r["term"] for r in reloaded] == ["A57 5G", "Galaxy"]
        assert [r["enabled"] for r in reloaded] == [True, True]
        assert [r["max_cents"] for r in reloaded] == [190000, None]
        assert [r["min_cents"] for r in reloaded] == [None, None]
        # .bak intacto (conteúdo v1 original, sem sobrescrita)
        assert bak.read_text(encoding="utf-8") == '["A57", "Galaxy"]'


def test_bytes_do_electron_sao_legiveis_pelo_python():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "keywords.json"
        write_ts_shape(p, [
            {"id": "a57-ab12", "term": "A57", "enabled": False,
             "min_cents": 10000, "max_cents": 190000},
        ])
        v, rules = load_rules_file(p)
        assert v == 2 and rules[0]["enabled"] is False
        assert rules[0]["min_cents"] == 10000
