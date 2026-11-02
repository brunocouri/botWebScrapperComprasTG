"""F3: pipeline handler (via plan_effects), dry-run, protocolo, migração integrada.
Sem Telegram: efeitos externos (send) não executados, só planejados."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))
import bot
from bot import (
    matched_event, filtered_event, alert_event, dry_event,
    price_line, format_alert, format_brl,
)
from rules import (
    evaluate, plan_effects, load_rules_config, load_rules_file, RulesConfigError,
    migrate_file, format_brl as fmt,
)


def R(term, enabled=True, mn=None, mx=None, rid=None):
    return {"id": rid or f"t-{term.lower()}", "term": term, "enabled": enabled,
            "min_cents": mn, "max_cents": mx}


def kinds(plan):
    return [k for k, _ in plan]


def fake_event(text, chat_id=-1001, msg_id=42):
    return SimpleNamespace(
        chat_id=chat_id,
        message=SimpleNamespace(message=text, id=msg_id),
        sender=SimpleNamespace(first_name="Joao", last_name=None, username="joao"),
    )


# ------------------------------------------------------------- pipeline ----
def test_uma_elegivel_um_envio():
    plan = plan_effects(evaluate("vendo A57", [R("A57")]))
    assert kinds(plan) == ["alert"] and plan[0][1]["rule_id"] == "t-a57"


def test_duas_elegiveis_apenas_primeira_envia():
    plan = plan_effects(evaluate("Galaxy A57 por R$ 1.899", [R("Galaxy"), R("A57")]))
    assert kinds(plan) == ["filtered", "alert"]
    assert plan[0][1]["reason"] == "superseded"
    assert plan[1][1]["rule_id"] == "t-galaxy"


def test_primeira_inelegivel_segunda_envia():
    plan = plan_effects(evaluate("Galaxy A57 por R$ 5.000", [R("Galaxy", mx=100), R("A57")]))
    assert kinds(plan) == ["filtered", "alert"]
    assert plan[0][1]["reason"] == "above_max"
    assert plan[1][1]["rule_id"] == "t-a57"


def test_todas_inelegiveis_zero_envios():
    plan = plan_effects(evaluate("A57 por R$ 5.000", [R("A57", mx=100)]))
    assert kinds(plan) == ["filtered"]


def test_sem_faixa_sem_preco_preserva_alerta():
    plan = plan_effects(evaluate("vendo A57 zerado", [R("A57")]))
    assert kinds(plan) == ["alert"]


def test_disabled_nao_participa():
    assert plan_effects(evaluate("vendo A57", [R("A57", enabled=False)])) == []


def test_multi_match_um_efeito_externo():
    plan = plan_effects(evaluate("Galaxy A57 256GB por R$ 1.899", [R("Galaxy"), R("A57"), R("256GB")]))
    assert kinds(plan).count("alert") == 1
    assert sum(1 for k in kinds(plan) if k in ("alert", "dry")) == 1


def test_falha_nao_promove():
    evs = evaluate("Galaxy A57", [R("Galaxy"), R("A57")])
    assert [k for k, _ in plan_effects(evs)] == ["filtered", "alert"]
    assert [k for k, _ in plan_effects(evs)] == ["filtered", "alert"]  # determinístico


# -------------------------------------------------------------- dry-run ----
def test_dry_run_mesma_vencedora_sem_envio():
    evs = evaluate("Galaxy A57 por R$ 1.899", [R("Galaxy"), R("A57")])
    plan = plan_effects(evs, dry_run=True)
    assert kinds(plan) == ["filtered", "dry"]
    assert plan[1][1]["rule_id"] == "t-galaxy"
    assert "alert" not in kinds(plan)


def test_dry_run_nao_promove():
    evs = evaluate("Galaxy A57 por R$ 5.000", [R("Galaxy", mx=100), R("A57")])
    plan = plan_effects(evs, dry_run=True)
    assert kinds(plan) == ["filtered", "dry"]
    assert plan[1][1]["rule_id"] == "t-a57"


# ------------------------------------------------------------- protocolo ----
def test_matched_serializa_preco_e_regra():
    ev = evaluate("A57 12x R$ 189,90", [R("A57")])[0]
    m = matched_event(ev, -1001, 7)
    assert m["type"] == "keyword_matched" and m["rule_id"] == "t-a57"
    assert m["eligible"] is True and m["reason"] == "ok"
    assert m["group_id"] == "-1001" and m["message_id"] == 7
    assert m["decisive"]["kind"] == "parcela" and m["decisive"]["total_cents"] == 227880
    assert len(m["prices"]) >= 1
    json.dumps(m, ensure_ascii=False)  # stdout JSONL válido


def test_filtered_above_below_noprice_superseded():
    e1 = evaluate("A57 por R$ 5.000", [R("A57", mx=100)])[0]
    f1 = filtered_event(e1, -1, 1, {"min_cents": None, "max_cents": 100})
    assert (f1["type"], f1["reason"]) == ("rule_filtered", "above_max")
    assert f1["bounds"] == {"min_cents": None, "max_cents": 100}
    e2 = evaluate("A57 por R$ 10,00", [R("A57", mn=5000)])[0]
    assert filtered_event(e2, -1, 1, None)["reason"] == "below_min"
    e3 = evaluate("vendo A57", [R("A57", mx=100)])[0]
    f3 = filtered_event(e3, -1, 1, None)
    assert (f3["reason"], f3["decisive"]) == ("no_price", None)
    evs = evaluate("Galaxy A57", [R("Galaxy"), R("A57")])
    _, rest = __import__("rules").select_winner(evs)
    assert filtered_event(rest[0], -1, 1, None)["reason"] == "superseded"
    for f in (f1, f3):
        json.dumps(f, ensure_ascii=False)


def test_alert_inclui_decisive():
    ev = evaluate("A57 R$ 1.899,00", [R("A57", mx=200000)])[0]
    a = alert_event(ev, -1001, 9, 87)
    assert a["decisive"] == {"cents": 189900, "kind": "avulso"}
    assert (a["elapsed_ms"], a["message_id"]) == (87, 9)
    json.dumps(a, ensure_ascii=False)


def test_dry_event_identifica_regra_preco():
    ev = evaluate("A57 R$ 1.899,00", [R("A57")])[0]
    d = dry_event(ev, -1001, 9, "prev")
    assert (d["rule_id"], d["keyword"], d["decisive"]["cents"]) == ("t-a57", "A57", 189900)


# ----------------------------------------------------- alerta formatado ----
def test_format_brl():
    assert fmt(189900) == "1.899,00" and fmt(18990) == "189,90"
    assert fmt(100) == "1,00" and fmt(0) == "0,00"
    assert bot.format_brl is fmt


def test_price_line():
    assert bot.price_line(None) == ""
    assert bot.price_line({"kind": "vista", "cents": 189900}) == "\n💰 Preço: R$ 1.899,00 (à vista)"
    assert bot.price_line({"kind": "avulso", "cents": 189900}) == "\n💰 Preço: R$ 1.899,00"
    assert bot.price_line({"kind": "parcela", "cents": 18990, "installments": 12,
                           "installment_cents": 18990, "total_cents": 227880}) == \
        "\n💰 Preço: 12x de R$ 189,90 (total R$ 2.278,80)"


def test_format_alert_com_e_sem_preco():
    ev_text = "vendo A57"
    e = fake_event(ev_text)
    sem = format_alert(e, "A57", "Grupo X")
    assert "Preço:" not in sem and "t.me/c/1/42" in sem  # comportamento atual (-100 removido)
    dec = {"kind": "vista", "cents": 189900}
    com = format_alert(e, "A57", "Grupo X", dec)
    assert "💰 Preço: R$ 1.899,00 (à vista)" in com


# -------------------------------------------------------------- migração ----
def test_v1_startup_migra_e_bot_usa_rules(tmp_path):
    p = tmp_path / "keywords.json"
    p.write_text('["A57", "Galaxy"]', encoding="utf-8")
    rules = load_rules_config(p)  # mesmo caminho do startup F3
    assert [r["term"] for r in rules] == ["A57", "Galaxy"]
    assert (tmp_path / "keywords.json.bak").exists()
    v, reloaded = load_rules_file(p)
    assert v == 2 and [r["id"] for r in reloaded] == [r["id"] for r in rules]
    assert evaluate("A57 R$ 10", rules)[0]["eligible"] is True


def test_config_invalida_erro_explicito(tmp_path):
    p = tmp_path / "keywords.json"
    p.write_text('[{"id": "a", "term": "", "enabled": true}]', encoding="utf-8")
    try:
        load_rules_config(p)
        assert False, "deveria falhar"
    except RulesConfigError as e:
        assert "term" in str(e)
    p.write_text('[]', encoding="utf-8")
    try:
        load_rules_config(p)
        assert False
    except RulesConfigError as e:
        assert "nenhuma regra" in str(e)


def test_arquivo_ausente_default_sem_escrever(tmp_path):
    p = tmp_path / "keywords.json"
    rules = load_rules_config(p)
    assert [r["term"] for r in rules] == ["A57"] and rules[0]["enabled"] is True
    assert not p.exists()
