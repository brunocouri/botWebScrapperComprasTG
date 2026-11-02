"""Regressão B1: --list-groups nunca destrói selected. Merge por ID, nunca por nome."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import bot


def test_preserva_selected_existente():
    prev = {"-1001": True, "-1002": False}
    fetched = [{"id": -1001, "name": "A"}, {"id": -1002, "name": "B"}]
    out = bot.merge_watched(prev, fetched)
    assert out == [
        {"id": -1001, "name": "A", "selected": True},
        {"id": -1002, "name": "B", "selected": False},
    ]


def test_grupo_novo_vem_desmarcado():
    out = bot.merge_watched({"-1001": True}, [{"id": -1001, "name": "A"}, {"id": -1009, "name": "Novo"}])
    assert out[1] == {"id": -1009, "name": "Novo", "selected": False}


def test_grupo_removido_sai_da_lista():
    out = bot.merge_watched({"-1001": True, "-1000": True}, [{"id": -1001, "name": "A"}])
    assert [g["id"] for g in out] == [-1001]


def test_identidade_por_id_nao_por_nome():
    # mesmo nome, id diferente => NÃO herda selected
    out = bot.merge_watched({"-1001": True}, [{"id": -1002, "name": "A"}])
    assert out == [{"id": -1002, "name": "A", "selected": False}]


def test_prev_vazio_ou_ausente():
    assert bot.merge_watched({}, [{"id": -1001, "name": "A"}])[0]["selected"] is False
