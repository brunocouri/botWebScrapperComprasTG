"""F4: seen.db, deduplicação persistente, histórico best-effort. Sem Telegram.
Banco sempre temporário (tmp_path) — nunca o seen.db real."""
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import bot
from bot import decide_message
from storage import SeenStore, StorageError, record_evaluation


def R(term, enabled=True, mn=None, mx=None, rid=None):
    return {"id": rid or f"t-{term.lower()}", "term": term, "enabled": enabled,
            "min_cents": mn, "max_cents": mx}


def store_at(tmp_path):
    return SeenStore(tmp_path / "seen.db").open()


# ---------------------------------------------------------------- storage ---
def test_schema_idempotente(tmp_path):
    s = store_at(tmp_path)
    s.close()
    s2 = SeenStore(tmp_path / "seen.db").open()  # reabre sem erro
    assert s2.count_seen() == 0
    s2.close()


def test_claim_primeira_ok_segunda_rejeitada(tmp_path):
    s = store_at(tmp_path)
    assert s.is_seen(-1001, 7) is False
    assert s.claim_message(-1001, 7) is True
    assert s.is_seen(-1001, 7) is True
    assert s.claim_message(-1001, 7) is False
    s.close()


def test_sem_colisao_entre_chats_e_msgs(tmp_path):
    s = store_at(tmp_path)
    assert s.claim_message(-1001, 7) is True
    assert s.claim_message(-1002, 7) is True   # mesmo msg, outro chat
    assert s.claim_message(-1001, 8) is True   # mesmo chat, outra msg
    assert s.count_seen() == 3
    s.close()


def test_persiste_entre_reaberturas(tmp_path):
    p = tmp_path / "seen.db"
    SeenStore(p).open().claim_message(-1001, 7)
    SeenStore(p).open().close()  # fecha sem with
    s = SeenStore(p).open()
    assert s.is_seen(-1001, 7) is True
    s.close()


def test_concorrencia_um_vencedor(tmp_path):
    p = tmp_path / "seen.db"
    SeenStore(p).open().close()  # cria schema
    results = []

    def worker():
        s = SeenStore(p).open()
        try:
            results.append(s.claim_message(-1001, 7))
        finally:
            s.close()

    ts = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in ts]
    [t.join(timeout=10) for t in ts]
    assert sorted(results) == [False, True]  # PRIMARY KEY decide, não SELECT+INSERT


# ----------------------------------------------------------------- decide ---
def test_no_match_nao_marca(tmp_path):
    s = store_at(tmp_path)
    out = decide_message(s, "nada aqui", -1001, 7, [R("A57")])
    assert out["status"] == "no_match"
    assert s.is_seen(-1001, 7) is False  # sem match => sem claim (spec §5)
    s.close()


def test_multi_regra_uma_entrada_seen(tmp_path):
    s = store_at(tmp_path)
    out = decide_message(s, "Galaxy A57 por R$ 1.899", -1001, 7, [R("Galaxy"), R("A57")])
    assert out["status"] == "decided" and len(out["evaluations"]) == 2
    assert s.count_seen() == 1
    out2 = decide_message(s, "Galaxy A57 por R$ 1.899", -1001, 7, [R("Galaxy"), R("A57")])
    assert out2["status"] == "duplicate"
    s.close()


def test_dry_run_marca_seen(tmp_path):
    s = store_at(tmp_path)
    out = decide_message(s, "vendo A57", -1001, 7, [R("A57")], dry_run=True)
    assert out["status"] == "decided"
    assert s.is_seen(-1001, 7) is True
    s.close()


def test_filtrada_marca_seen(tmp_path):
    s = store_at(tmp_path)
    out = decide_message(s, "A57 por R$ 5.000", -1001, 7, [R("A57", mx=100)])
    assert out["status"] == "decided" and out["winner"] is None
    assert s.is_seen(-1001, 7) is True
    s.close()


def test_dry_mesma_selecao_que_normal(tmp_path):
    s = store_at(tmp_path)
    rules = [R("Galaxy"), R("A57")]
    a = decide_message(s, "Galaxy A57", -1001, 7, rules, dry_run=False)
    assert [k for k, _ in a["plan"]] == ["filtered", "alert"]
    assert a["winner"]["rule_id"] == "t-galaxy"
    # dry_run não altera seleção: mesmo plano, só o kind final muda
    from rules import evaluate, select_winner
    evs = evaluate("Galaxy A57", rules)
    w, _ = select_winner(evs)
    assert w["rule_id"] == "t-galaxy"
    s.close()


def test_seen_fechado_erro_explicito(tmp_path):
    s = store_at(tmp_path)
    s.close()
    with pytest.raises(StorageError):
        decide_message(s, "vendo A57", -1001, 7, [R("A57")])


def test_decide_nao_toca_offers_prova_best_effort(tmp_path):
    # offers quebrada NÃO afeta a decisão (best-effort estrutural)
    s = store_at(tmp_path)
    s._conn.execute("DROP TABLE offers")
    s._conn.commit()
    out = decide_message(s, "vendo A57", -1001, 7, [R("A57")])
    assert out["status"] == "decided" and out["winner"]["rule_id"] == "t-a57"
    s.close()


# --------------------------------------------------------------- histórico ---
def test_historico_todos_reasons(tmp_path):
    s = store_at(tmp_path)
    cases = [
        (evaluate_text("vendo A57", [R("A57")]), True),                       # ok
        (evaluate_text("A57 por R$ 5.000", [R("A57", mx=100)]), False),       # above_max
        (evaluate_text("A57 por R$ 10,00", [R("A57", mn=5000)]), False),      # below_min
        (evaluate_text("vendo A57", [R("A57", mx=100)]), False),              # no_price
    ]
    for i, (evs, sent) in enumerate(cases):
        bot_record(s, -1001, 100 + i, evs[0], sent)
    rows = s.fetch_offers()
    assert [r["reason"] for r in rows] == ["ok", "above_max", "below_min", "no_price"]
    assert [r["sent"] for r in rows] == [1, 0, 0, 0]
    parsed = json.loads(rows[0]["prices_json"])  # JSON estável e recuperável
    assert isinstance(parsed, list)
    assert rows[3]["decisive_json"] is None  # no_price => NULL
    s.close()


def evaluate_text(text, rules):
    from rules import evaluate
    return evaluate(text, rules)


def bot_record(s, chat, msg, ev, sent):
    record_evaluation(s, chat, msg, ev, sent)


def test_superseded_persistido(tmp_path):
    from rules import evaluate, select_winner
    s = store_at(tmp_path)
    evs = evaluate("Galaxy A57", [R("Galaxy"), R("A57")])
    _, rest = select_winner(evs)
    record_evaluation(s, -1001, 7, rest[0], False)
    rows = s.fetch_offers()
    assert len(rows) == 1 and rows[0]["reason"] == "superseded" and rows[0]["sent"] == 0
    s.close()


def test_offers_falha_explicita_nao_silenciosa(tmp_path):
    s = store_at(tmp_path)
    s._conn.execute("DROP TABLE offers")
    s._conn.commit()
    from rules import evaluate
    ev = evaluate("vendo A57", [R("A57")])[0]
    with pytest.raises(StorageError):
        record_evaluation(s, -1001, 7, ev, True)
    s.close()
