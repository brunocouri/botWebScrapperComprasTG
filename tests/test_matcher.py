"""Preserva o comportamento atual de matching (B3). Sem Telegram, sem IO."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import bot


def pat(kws=None):
    return bot.build_pattern(kws or ["A57", "Galaxy"])


def test_encontra_keyword():
    assert bot.evaluate_message("vendo A57 zerado", pat()) == "A57"


def test_ausente_retorna_none():
    assert bot.evaluate_message("vendo moto zerada", pat()) is None


def test_case_insensitive():
    assert bot.evaluate_message("compro a57 hoje", pat()) == "a57"
    assert bot.evaluate_message("GALAXY barato", pat()) == "GALAXY"


def test_boundary_pontuacao_casa():
    assert bot.evaluate_message("A57, zerado", pat()) == "A57"
    assert bot.evaluate_message("(A57)", pat()) == "A57"


def test_boundary_nao_casa_sufixo_prefixo():
    assert bot.evaluate_message("vendo A570", pat()) is None
    assert bot.evaluate_message("XA57 aqui", pat()) is None
    assert bot.evaluate_message("A57PRO", pat()) is None


def test_multiplas_keywords():
    assert bot.evaluate_message("Galaxy S25", pat()) == "Galaxy"
    assert bot.evaluate_message("nada aqui", pat(["IPHONE 15"])) is None
    assert bot.evaluate_message("iphone 15 barato", pat(["IPHONE 15"])) is not None


def test_vazia_none_pattern_none():
    assert bot.evaluate_message("", pat()) is None
    assert bot.evaluate_message(None, pat()) is None
    assert bot.evaluate_message("A57", None) is None
    assert bot.evaluate_message("   ", pat()) is None


def test_build_pattern_vazio():
    assert bot.build_pattern([]) is None
    assert bot.evaluate_message("A57", bot.build_pattern([])) is None
