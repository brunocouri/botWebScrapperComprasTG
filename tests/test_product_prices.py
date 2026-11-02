import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rules import evaluate


def rule(term='A57', maximum=190000):
    return {'id': term, 'term': term, 'enabled': True, 'min_cents': None, 'max_cents': maximum}


def test_sem_keyword_nao_extrai_preco():
    with patch('rules.extract_prices', side_effect=AssertionError('extração desnecessária')):
        assert evaluate('Outro produto R$ 10', [rule()]) == []


def test_preco_de_outro_produto_nao_aprova_a57():
    ev = evaluate('A57 R$ 2.500\nCapa R$ 20', [rule()])[0]
    assert not ev['eligible']
    assert ev['reason'] == 'above_max'
    assert ev['decisive']['cents'] == 250000


def test_multiplos_produtos_sem_vinculo_claro_sao_ambiguos():
    ev = evaluate('Galaxy A57\nLista de produtos\nR$ 2.500\nR$ 20', [rule()])[0]
    assert not ev['eligible']
    assert ev['reason'] == 'ambiguous_price'


def test_sem_faixa_mantem_match_mas_nao_inventa_preco():
    ev = evaluate('Galaxy A57\nLista de produtos\nR$ 2.500\nR$ 20', [rule(maximum=None)])[0]
    assert ev['eligible']
    assert ev['decisive'] is None


def test_produto_em_bloco_unico_preserva_pix_parcela():
    ev = evaluate('Galaxy A57\n128GB 5G\nR$ 1.899 no Pix\n12x R$ 200', [rule()])[0]
    assert ev['eligible']
    assert ev['decisive']['cents'] == 189900


def test_ou_e_pix_nao_liberam_precos_de_dois_produtos():
    for text in ['A57 R$ 2.500 ou Capa R$ 20', 'A57 R$ 2.500 e Capa R$ 20 no Pix']:
        ev = evaluate(text, [rule()])[0]
        assert ev['reason'] == 'ambiguous_price'
        assert not ev['eligible']
