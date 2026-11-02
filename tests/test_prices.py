"""F1: PriceParser puro (SPEC-PREÇOS §1+§7). Sem Telegram, sem IO."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from price_parser import extract_prices, decisive, comparison_cents, to_cents


def cents_of(entries, kind=None):
    xs = [e for e in entries if kind is None or e["kind"] == kind]
    return sorted(e["cents"] for e in xs)


def test_formatos_basicos():
    assert cents_of(extract_prices("R$ 1.899,00")) == [189900]
    assert cents_of(extract_prices("R$1899,99")) == [189999]
    assert cents_of(extract_prices("RS 1.899")) == [189900]
    assert cents_of(extract_prices("R$ 1899")) == [189900]
    assert cents_of(extract_prices("$ 1.899,00")) == [189900]
    assert cents_of(extract_prices("1899 reais")) == [189900]


def test_to_cents():
    assert to_cents("1.899,00") == 189900
    assert to_cents("189,90") == 18990
    assert to_cents("1.899") == 189900
    assert to_cents("18,9") == 1890


def test_parcela_com_e_sem_ancora():
    a = extract_prices("12x R$ 189,90")[0]
    assert (a["kind"], a["cents"], a["installments"], a["total_cents"]) == ("parcela", 18990, 12, 227880)
    b = extract_prices("12x 189,90")[0]  # Nx ancora (D1)
    assert (b["kind"], b["installments"], b["total_cents"]) == ("parcela", 12, 227880)
    assert b["installment_cents"] == 18990


def test_parcela_com_de_opcional():
    # "de" entre Nx e valor é opcional (I-1); whitespace/case variam
    for txt in ["12x de R$ 189,90", "12X DE R$ 189,90", "12 x de R$ 189,90", "12 x R$ 189,90"]:
        es = extract_prices(f"A57 {txt}")
        assert len(es) == 1, txt
        p = es[0]
        assert p["kind"] == "parcela", txt
        assert (p["installments"], p["installment_cents"], p["total_cents"]) == (12, 18990, 227880), txt
    d = decisive(extract_prices("A57 12x de R$ 189,90"))
    assert d is not None and comparison_cents(d) == 227880


def test_frete_preservado_mas_nunca_decisivo():
    es = extract_prices("A57 R$ 1.899 + frete R$ 39,90")
    assert cents_of(es, "frete") == [3990]
    d = decisive(es)
    assert d["kind"] in ("vista", "avulso") and d["cents"] == 189900


def test_frete_variantes_contexto_local():
    assert cents_of(extract_prices("A57 por R$ 1.899 + frete R$ 39,90"), "frete") == [3990]
    assert cents_of(extract_prices("A57 R$ 1.899\nFrete: R$ 39,90"), "frete") == [3990]
    assert cents_of(extract_prices("envio R$ 39,90"), "frete") == [3990]
    assert cents_of(extract_prices("R$ 39,90 de frete"), "frete") == [3990]
    # frete grátis não contamina preço posterior
    es = extract_prices("Frete grátis\nA57 R$ 1.899")
    assert cents_of(es, "frete") == []
    assert decisive(es)["cents"] == 189900


def test_frete_sozinho_decisive_null():
    es = extract_prices("frete R$ 39,90")
    assert cents_of(es, "frete") == [3990]
    assert decisive(es) is None


def test_combinado_pix_parcela_frete():
    es = extract_prices("A57 R$ 1.999 no Pix + 12x de R$ 189,90 + frete R$ 30")
    kinds = {p["kind"] for p in es}
    assert {"vista", "parcela", "frete"} <= kinds
    d = decisive(es)
    assert d["kind"] == "vista" and d["cents"] == 199900  # prioridade intacta
    assert cents_of(es, "frete") == [3000]


def test_frete_primeiro_nao_vence():
    es = extract_prices("+ frete R$ 39,90, produto R$ 1.899")
    assert decisive(es)["cents"] == 189900


def test_propagacao_trio_de_por():
    for txt in ["de R$ 2.499 por 1.899", "R$ 2.499 por 1.899", "de 2.499 por R$ 1.899"]:
        es = extract_prices(txt)
        assert cents_of(es, "de") == [249900], txt
        assert cents_of(es, "por") == [189900], txt
        d = decisive(es)
        assert d["kind"] == "por" and d["cents"] == 189900, txt
        assert comparison_cents(d) == 189900


def test_por_sozinho_sem_par_sem_ancora_nao_e_preco():
    assert extract_prices("por 1.899") == []
    assert extract_prices("vendo por 1899 barato") == []


def test_isolado_sem_ancora_nao_e_preco():
    assert extract_prices("A57 1899") == []
    assert extract_prices("128GB 5G") == []
    assert extract_prices("vendo moto 2023") == []


def test_moeda_estrangeira_ignorada():
    assert extract_prices("US$ 100") == []
    assert extract_prices("100 dólares") == []


def test_so_de_decisive_null():
    es = extract_prices("só de 2.499")
    assert cents_of(es, "de") == [249900]
    assert decisive(es) is None
    assert comparison_cents(None) is None


def test_vazio():
    assert extract_prices("") == []
    assert extract_prices(None) == []
    assert decisive([]) is None


def test_vista_contexto():
    es = extract_prices("no pix R$ 1.899")
    assert es[0]["kind"] == "vista"
    es2 = extract_prices("R$ 1.899")
    assert es2[0]["kind"] == "avulso"


def test_prioridade_por_sobre_vista_e_parcela():
    es = extract_prices("de R$ 2.499 por 1.899 no pix")
    assert decisive(es)["kind"] == "por"
    es2 = extract_prices("R$ 1.899 à vista ou 12x R$ 189,90")
    d2 = decisive(es2)
    assert d2["kind"] == "vista" and d2["cents"] == 189900
    es3 = extract_prices("somente 12x R$ 189,90")
    d3 = decisive(es3)
    assert d3["kind"] == "parcela" and comparison_cents(d3) == 227880


def test_empate_mesma_prioridade_menor_vence():
    es = extract_prices("R$ 1.999 ou R$ 1.899")
    assert decisive(es)["cents"] == 189900


def test_nao_casa_dentro_de_modelo():
    # "57" de A57 não pode virar preço nem com Nx por perto sem número próprio
    assert extract_prices("A57") == []


def test_robustez_nunca_lanca():
    for txt in ["R$", "por", "12x", "de por", "R$ ,,,", "R$ 1.2.3,4", "\x00 R$ \n 1.899"]:
        assert isinstance(extract_prices(txt), list)
