"""Mensagens promocionais reais/sujas contra a spec (auditoria item 7).
Regras ilustrativas: Galaxy sem faixa, A57 max R$ 1.900 (190000).
xfail estrito = gap de spec conhecido (frete, '12x de'); quando corrigidos,
o XPASS falha alto e obriga remover o marcador."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from rules import evaluate
from price_parser import comparison_cents


def R(term, enabled=True, mn=None, mx=None, rid=None):
    return {"id": rid or f"t-{term.lower()}", "term": term, "enabled": enabled,
            "min_cents": mn, "max_cents": mx}


RULES = [R("Galaxy"), R("A57", mx=190000)]


def by_id(evs, rid):
    return next(e for e in evs if e["rule_id"] == rid)


def test_par_simples_duas_regras_elegiveis():
    evs = evaluate("Galaxy A57 por R$ 1.899,00", RULES)
    assert [(e["rule_id"], e["eligible"], e["reason"]) for e in evs] == [
        ("t-galaxy", True, "ok"), ("t-a57", True, "ok")]
    assert comparison_cents(by_id(evs, "t-a57")["decisive"]) == 189900


def test_multilinha_de_por_com_pix():
    evs = evaluate("GALAXY A57\nDE R$ 2.499\nPOR R$ 1.899 NO PIX", RULES)
    a57 = by_id(evs, "t-a57")
    assert a57["eligible"] is True
    assert a57["decisive"]["kind"] == "vista"
    assert comparison_cents(a57["decisive"]) == 189900
    assert ("de", 249900) in [(p["kind"], p["cents"]) for p in a57["prices"]]


def test_specs_tecnicas_nao_viram_preco():
    evs = evaluate("A57 256GB 5G\nR$1899", RULES)
    assert len(evs) == 1  # Galaxy não casa; só A57 avalia
    a57 = by_id(evs, "t-a57")
    assert comparison_cents(a57["decisive"]) == 189900


def test_vista_ou_parcela_prioridade_vista():
    evs = evaluate("A57 R$ 1.999 ou 12x R$ 189,90", RULES)
    a57 = by_id(evs, "t-a57")
    assert a57["decisive"]["kind"] in ("vista", "avulso")
    assert a57["reason"] == "above_max"  # 199900 > 190000


def test_trio_de_por_propaga():
    for txt in ["A57 de R$ 2.499 por 1.899", "A57\nde 2.499 por R$ 1.899"]:
        a57 = by_id(evaluate(txt, RULES), "t-a57")
        assert a57["decisive"]["kind"] == "por"
        assert comparison_cents(a57["decisive"]) == 189900
        assert a57["eligible"] is True


def test_por_sozinho_sem_ancora_nada():
    evs = evaluate("A57 por 1899", RULES)
    assert len(evs) == 1 and evs[0]["reason"] == "no_price"


def test_sem_preco_nenhum():
    evs = evaluate("A57 128GB 8GB 5G", RULES)
    assert len(evs) == 1 and evs[0]["reason"] == "no_price"
    assert evs[0]["prices"] == []


def test_frete_nao_sequestra_decisivo():
    a57 = by_id(evaluate("A57 R$ 1.899 + frete R$ 39,90", RULES), "t-a57")
    assert comparison_cents(a57["decisive"]) == 189900


def test_12x_de_mantem_parcela():
    a57 = by_id(evaluate("A57\n12x de R$ 189,90", RULES), "t-a57")
    assert a57["decisive"] is not None
    assert a57["decisive"]["kind"] == "parcela"
    assert a57["decisive"]["total_cents"] == 227880
