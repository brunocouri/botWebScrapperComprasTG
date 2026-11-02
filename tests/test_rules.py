"""F2: regras v2, migração, evaluate() multi-regra, política D6. Sem Telegram/IO real."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import bot
import rules
from rules import (
    evaluate, select_winner, validate_rule, validate_rules,
    normalize_document, load_rules_file, migrate_file, generate_rule_id,
)


def R(term, enabled=True, mn=None, mx=None, rid=None):
    return {"id": rid or f"t-{term.lower()}", "term": term, "enabled": enabled,
            "min_cents": mn, "max_cents": mx}


# ---------------------------------------------------------- fonte única ----
def test_build_pattern_compartilhado_com_bot():
    assert bot.build_pattern is rules.build_pattern
    assert bot.evaluate_message("a57,", bot.build_pattern(["A57"])) == "a57"


# -------------------------------------------------------------- migração ----
def test_v1_lista_simples_migra(tmp_path):
    p = tmp_path / "keywords.json"
    p.write_text('["A57"]', encoding="utf-8")
    out = migrate_file(p)
    assert len(out) == 1 and out[0]["term"] == "A57" and out[0]["enabled"] is True
    assert out[0]["min_cents"] is None and out[0]["max_cents"] is None
    assert out[0]["id"].startswith("a57-") and len(out[0]["id"]) == len("a57-") + 4


def test_ordem_preservada_e_ids_diferentes(tmp_path):
    p = tmp_path / "keywords.json"
    p.write_text('["Galaxy", "A57", "256GB"]', encoding="utf-8")
    out = migrate_file(p)
    assert [r["term"] for r in out] == ["Galaxy", "A57", "256GB"]
    assert len({r["id"] for r in out}) == 3


def test_segunda_leitura_nao_regenera(tmp_path):
    p = tmp_path / "keywords.json"
    p.write_text('["A57"]', encoding="utf-8")
    first = migrate_file(p)
    v, again = load_rules_file(p)
    assert v == 2 and again[0]["id"] == first[0]["id"]
    # migrar de novo: sem escrita, sem .bak novo, mesmos ids
    assert migrate_file(p)[0]["id"] == first[0]["id"]


def test_backup_criado_e_nunca_sobrescrito(tmp_path):
    p = tmp_path / "keywords.json"
    p.write_text('["A57"]', encoding="utf-8")
    migrate_file(p)
    bak = Path(str(p) + ".bak")
    assert bak.read_text(encoding="utf-8") == '["A57"]'
    bak.write_text("SENTINELA", encoding="utf-8")
    p.write_text('["Galaxy"]', encoding="utf-8")  # simula edição manual pós-migração
    migrate_file(p)
    assert bak.read_text(encoding="utf-8") == "SENTINELA"


def test_v2_valido_nao_migra(tmp_path):
    p = tmp_path / "keywords.json"
    original = '{"version": 2, "rules": [{"id": "a57-aaaa", "term": "A57", "enabled": true, "min_cents": null, "max_cents": null}]}'
    p.write_text(original, encoding="utf-8")
    out = migrate_file(p)
    assert out[0]["id"] == "a57-aaaa"
    assert p.read_text(encoding="utf-8") == original
    assert not Path(str(p) + ".bak").exists()


def test_editar_term_preserva_id(tmp_path):
    p = tmp_path / "keywords.json"
    p.write_text('["A57"]', encoding="utf-8")
    rid = migrate_file(p)[0]["id"]
    v, rules = load_rules_file(p)
    rules[0]["term"] = "A57 5G"
    assert validate_rules(rules) == []
    assert rules[0]["id"] == rid


def test_arquivo_invalido_erro_explicito(tmp_path):
    p = tmp_path / "keywords.json"
    for bad in ["{corrompido", "123", "null", '{"foo": 1}', "[123]", '[{"term": "A57"}]']:
        p.write_text(bad, encoding="utf-8")
        with pytest.raises(ValueError):
            load_rules_file(p)
    p.unlink()
    with pytest.raises(FileNotFoundError):
        load_rules_file(p)


def test_colisao_id_unica_e_slug():
    seen = set()
    for _ in range(30):
        seen.add(generate_rule_id("A57!!! ", seen))
    assert len(seen) == 30
    assert all(i.startswith("a57-") and len(i) == 8 for i in seen)
    assert generate_rule_id("!!!", set()).startswith("rule-")


# ------------------------------------------------------------ validação ----
def test_validate_ok_e_falhas():
    good = {"id": "a-1", "term": "A57", "enabled": True, "min_cents": None, "max_cents": 10}
    assert validate_rule(good) == []
    assert any("term" in e for e in validate_rule({**good, "term": "  "}))
    assert any("id" in e for e in validate_rule({**good, "id": ""}))
    assert any("enabled" in e for e in validate_rule({**good, "enabled": "yes"}))
    assert any("min_cents" in e for e in validate_rule({**good, "min_cents": 1.5}))
    assert any("min_cents" in e for e in validate_rule({**good, "min_cents": True}))
    assert any("min_cents" in e for e in validate_rule({**good, "min_cents": -1}))
    assert any("min_cents <=" in e for e in validate_rule({**good, "min_cents": 5, "max_cents": 4}))
    assert any("duplicado" in e for e in validate_rules([good, {**good, "term": "B"}]))


# --------------------------------------------------------- elegibilidade ----
def test_sem_faixa_sempre_eligible():
    assert evaluate("sem preço aqui", [R("A57")]) == []  # sem match
    ev = evaluate("vendo A57 zerado", [R("A57")])[0]
    assert (ev["eligible"], ev["reason"]) == (True, "ok")
    ev2 = evaluate("A57 R$ 9.999,00", [R("A57")])[0]
    assert (ev2["eligible"], ev2["reason"]) == (True, "ok")


def test_somente_maximo():
    assert evaluate("A57 R$ 1.899,00", [R("A57", mx=189900)])[0]["reason"] == "ok"
    assert evaluate("A57 R$ 1.899,01", [R("A57", mx=189900)])[0]["reason"] == "above_max"


def test_somente_minimo():
    assert evaluate("A57 R$ 500,00", [R("A57", mn=50000)])[0]["reason"] == "ok"
    assert evaluate("A57 R$ 499,99", [R("A57", mn=50000)])[0]["reason"] == "below_min"


def test_min_max_faixa():
    r = R("A57", mn=100000, mx=200000)
    assert evaluate("A57 R$ 1.500,00", [r])[0]["eligible"] is True
    assert evaluate("A57 R$ 500,00", [r])[0]["reason"] == "below_min"
    assert evaluate("A57 R$ 2.500,00", [r])[0]["reason"] == "above_max"


def test_faixa_sem_preco_no_price():
    ev = evaluate("vendo A57 zerado", [R("A57", mx=189900)])[0]
    assert (ev["eligible"], ev["reason"]) == (False, "no_price")
    ev2 = evaluate("só de 2.499 e A57", [R("A57", mx=999900)])[0]
    assert (ev2["eligible"], ev2["reason"]) == (False, "no_price")


def test_frete_so_com_faixa_no_price():
    # Só há custo acessório: sem decisivo do produto (B-1)
    ev = evaluate("A57 frete R$ 39,90", [R("A57", mx=999900)])[0]
    assert (ev["eligible"], ev["reason"]) == (False, "no_price")
    assert ev["decisive"] is None
    assert [p["kind"] for p in ev["prices"]] == ["frete"]


def test_frete_nao_muda_elegibilidade_produto():
    ev = evaluate("A57 R$ 1.899 + frete R$ 39,90", [R("A57", mx=190000)])[0]
    assert (ev["eligible"], ev["reason"]) == (True, "ok")
    assert ev["decisive"]["cents"] == 189900


def test_disabled_sem_avaliacao():
    assert evaluate("vendo A57", [R("A57", enabled=False)]) == []


def test_decisive_preserva_origem():
    ev = evaluate("A57 12x R$ 189,90", [R("A57")])[0]
    assert ev["decisive"]["kind"] == "parcela"
    assert ev["decisive"]["total_cents"] == 227880
    assert ev["prices"] and ev["rule_id"] == "t-a57" and ev["keyword"] == "A57"


# ------------------------------------------------------------ multi-regra ----
def test_duas_regras_duas_avaliacoes_em_ordem():
    evs = evaluate("Galaxy A57 256GB por R$ 1.899", [R("Galaxy"), R("A57"), R("256GB")])
    assert [e["rule_id"] for e in evs] == ["t-galaxy", "t-a57", "t-256gb"]
    assert all(e["eligible"] for e in evs)


def test_elegivel_mais_inelegivel():
    evs = evaluate("Galaxy A57 por R$ 5.000", [R("Galaxy"), R("A57", mx=189900)])
    assert [(e["rule_id"], e["eligible"], e["reason"]) for e in evs] == [
        ("t-galaxy", True, "ok"), ("t-a57", False, "above_max")]


def test_disabled_no_meio_nao_participa():
    evs = evaluate("Galaxy A57", [R("Galaxy"), R("X", enabled=False), R("A57")])
    assert [e["rule_id"] for e in evs] == ["t-galaxy", "t-a57"]


def test_extracao_unica_por_mensagem(monkeypatch):
    import rules as rules_mod
    calls = []
    orig = rules_mod.extract_prices
    monkeypatch.setattr(rules_mod, "extract_prices", lambda t: (calls.append(t), orig(t))[1])
    evaluate("Galaxy A57 por R$ 1.899", [R("Galaxy"), R("A57")])
    assert calls == ["Galaxy A57 por R$ 1.899"]


# ------------------------------------------------------------------ D6 ----
def test_uma_elegivel_vence():
    evs = evaluate("vendo A57", [R("A57")])
    w, rest = select_winner(evs)
    assert w["rule_id"] == "t-a57" and rest == []


def test_duas_elegiveis_primeira_vence():
    evs = evaluate("Galaxy A57 por R$ 1.899", [R("Galaxy"), R("A57")])
    w, rest = select_winner(evs)
    assert w["rule_id"] == "t-galaxy"
    assert [(e["rule_id"], e["reason"]) for e in rest] == [("t-a57", "superseded")]


def test_primeira_inelegivel_segunda_vence():
    evs = evaluate("Galaxy A57 por R$ 5.000", [R("Galaxy", mx=100), R("A57")])
    w, rest = select_winner(evs)
    assert w["rule_id"] == "t-a57"
    assert [(e["rule_id"], e["reason"]) for e in rest] == [("t-galaxy", "above_max")]


def test_todas_inelegiveis_sem_vencedora():
    evs = evaluate("Galaxy A57 por R$ 5.000", [R("Galaxy", mx=100), R("A57", mx=100)])
    w, rest = select_winner(evs)
    assert w is None and len(rest) == 2
    assert all(e["reason"] == "above_max" for e in rest)


def test_ordem_muda_vencedora():
    a = evaluate("Galaxy A57", [R("Galaxy"), R("A57")])
    b = evaluate("Galaxy A57", [R("A57"), R("Galaxy")])
    assert select_winner(a)[0]["rule_id"] == "t-galaxy"
    assert select_winner(b)[0]["rule_id"] == "t-a57"


def test_inelegivel_nunca_vira_superseded():
    evs = evaluate("Galaxy A57 por R$ 5.000", [R("Galaxy"), R("A57", mx=100)])
    _, rest = select_winner(evs)
    assert "superseded" not in [e["reason"] for e in rest]


def test_sem_fallback_apos_escolha():
    evs = evaluate("Galaxy A57", [R("Galaxy"), R("A57")])
    w1, _ = select_winner(evs)
    w2, _ = select_winner(evs)  # determinístico: mesma entrada, mesma vencedora
    assert w1["rule_id"] == w2["rule_id"] == "t-galaxy"
    assert select_winner([]) == (None, [])
