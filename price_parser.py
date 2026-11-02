"""PriceParser puro: texto -> list[PriceEntry]. Sem Telegram, sem IO, sem logs.
SPEC-PREÇOS §1 (F1). Gramática sempre BR (`.` milhar, `,` decimal)."""

import re

# Número BR: 1.899,00 | 1899,99 | 1.899 | 1899 | 189,90
# (alternativa única longest-first: "1899,99" não pode casar só "189")
_NUM = r"\d+(?:\.\d{3})*(?:,\d{1,2})?"
# Número sem âncora para propagação/Nx: não pode grudar em letra/dígito (A57, 128GB)
_BARE = r"(?<![A-Za-z0-9])(\d[\d.]*(?:,\d{1,2})?)(?![A-Za-z0-9])"
# $ sozinho exige não ser US$ (lookbehind de letra)
_ANCHOR = r"(?:R\$\s?|RS\s?|(?<![A-Za-z])\$\s?)"

_NX_RE = re.compile(rf"(\d{{1,2}})\s*x\s*(?:\bde\b\s+)?(?:{_ANCHOR})?({_NUM})", re.IGNORECASE)
# Par de/por: cada lado ancorado ou bare; exige >=1 âncora (verificado no código)
_PAIR_RE = re.compile(
    rf"(?:\bde\b\s+)?(?:{_ANCHOR}(?P<a_num>{_NUM})|(?P<a_bare>{_BARE}))"
    rf"\s+\bpor\b\s+"
    rf"(?:{_ANCHOR}(?P<b_num>{_NUM})|(?P<b_bare>{_BARE}))",
    re.IGNORECASE,
)
_ANCHORED_RE = re.compile(rf"{_ANCHOR}({_NUM})", re.IGNORECASE)
_REAIS_RE = re.compile(rf"({_NUM})\s+reais?\b", re.IGNORECASE)
# "de" solitário + número com cara de preço (exige . ou ,): "só de 2.499".
# Bare sem separador ("de 2023") NÃO entra — evita ano virar preço.
_LONE_DE_RE = re.compile(rf"\bde\b\s+({_BARE})", re.IGNORECASE)
_DE_PREFIX_RE = re.compile(r"\bde\b\s+$", re.IGNORECASE)
_VISTA_RE = re.compile(r"pix|à\s*vista|a\s+vista|boleto", re.IGNORECASE)
# Frete/envio: custo acessório, nunca decisivo. Contexto LOCAL à ocorrência
# (antes: "frete R$", "frete: R$", "+ frete R$"; depois: "R$ X de frete").
# "frete grátis · A57 R$ 1.899" NÃO contamina o R$ 1.899 (sem adjacência).
_FRETE_BEFORE_RE = re.compile(r"(?:^|[\s+])(frete|envio)\s*:?\s*$", re.IGNORECASE)
_FRETE_AFTER_RE = re.compile(r"^\s*(?:de\s+)?(frete|envio)\b", re.IGNORECASE)


def _is_frete(line: str, start: int, end: int) -> bool:
    before = line[max(0, start - 16):start]
    after = line[end:end + 16]
    return bool(_FRETE_BEFORE_RE.search(before) or _FRETE_AFTER_RE.match(after))


def to_cents(num: str) -> int:
    """'1.899,00' -> 189900. Pura."""
    s = num.strip()
    if "," in s:
        inteiro, frac = s.rsplit(",", 1)
        frac = (frac + "00")[:2]
    else:
        inteiro, frac = s, "00"
    inteiro = inteiro.replace(".", "")
    if not inteiro.isdigit() or not frac.isdigit():
        raise ValueError(f"numero invalido: {num!r}")
    return int(inteiro) * 100 + int(frac)


def _spans_overlap(a, b) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def extract_prices(text: str | None) -> list:
    """Extrai PriceEntry dicts. Nunca lança exceção para entrada estranha."""
    if not text:
        return []
    entries: list = []
    try:
        for line_number, line in enumerate(text.split("\n")):
            entries.extend({**entry, 'line': line_number} for entry in _extract_line(line))
    except Exception:
        pass
    return entries


def _extract_line(line: str) -> list:
    out: list = []
    used: list = []

    def take(m, entry: dict):
        span = (m.start(), m.end())
        if any(_spans_overlap(span, u) for u in used):
            return
        used.append(span)
        out.append(entry)

    # 1. Parcelas Nx (o Nx ancora, número pode ou não ter âncora)
    for m in _NX_RE.finditer(line):
        try:
            n = int(m.group(1))
            cents = to_cents(m.group(2))
        except (ValueError, IndexError):
            continue
        if not 1 <= n <= 99:
            continue
        take(m, {"cents": cents, "kind": "parcela", "raw": m.group(0).strip(),
                 "installments": n, "installment_cents": cents, "total_cents": n * cents})

    # 2. Pares de/por (pelo menos um lado ancorado)
    for m in _PAIR_RE.finditer(line):
        a = m.group("a_num") or m.group("a_bare")
        b = b_num = m.group("b_num") or m.group("b_bare")
        anchored = bool(m.group("a_num") or b_num)
        if not anchored or a is None or b is None:
            continue
        try:
            a_cents, b_cents = to_cents(a), to_cents(b)
        except ValueError:
            continue
        # lado esquerdo (com ou sem "de") = referência; lado B = por
        span = (m.start(), m.end())
        if any(_spans_overlap(span, u) for u in used):
            continue
        used.append(span)
        raw = m.group(0).strip()
        out.append({"cents": a_cents, "kind": "de", "raw": raw})
        out.append({"cents": b_cents, "kind": "por", "raw": raw})

    # 2.5 "de" solitário + número com separador (referência sem par)
    for m in _LONE_DE_RE.finditer(line):
        try:
            num = m.group(1)
            if "." not in num and "," not in num:
                continue
            cents = to_cents(num)
        except (ValueError, IndexError):
            continue
        take(m, {"cents": cents, "kind": "de", "raw": m.group(0).strip()})

    # 3. Avulsos ancorados (frete verificado antes de de/vista)
    vista = bool(_VISTA_RE.search(line))
    for m in _ANCHORED_RE.finditer(line):
        try:
            cents = to_cents(m.group(1))
        except ValueError:
            continue
        if _is_frete(line, m.start(), m.end()):
            kind = "frete"
        elif _DE_PREFIX_RE.search(line[:m.start()][-8:]):
            kind = "de"
        else:
            kind = "vista" if vista else "avulso"
        take(m, {"cents": cents, "kind": kind, "raw": m.group(0).strip()})
    for m in _REAIS_RE.finditer(line):
        try:
            cents = to_cents(m.group(1))
        except ValueError:
            continue
        if _is_frete(line, m.start(), m.end()):
            kind = "frete"
        else:
            kind = "vista" if vista else "avulso"
        take(m, {"cents": cents, "kind": kind, "raw": m.group(0).strip()})

    return out


def decisive(prices: list) -> dict | None:
    """A entrada vencedora (origem/kind preservados) ou None. Pura.
    Frete é custo acessório: preservado nas ocorrências, excluído da disputa."""
    cands = [p for p in (prices or []) if p["kind"] != "frete"]
    if not cands:
        return None
    pors = [p for p in cands if p["kind"] == "por"]
    if pors:
        return min(pors, key=lambda p: p["cents"])
    va = [p for p in cands if p["kind"] in ("vista", "avulso")]
    if va:
        return min(va, key=lambda p: p["cents"])
    pars = [p for p in cands if p["kind"] == "parcela"]
    if pars:
        return min(pars, key=lambda p: p["total_cents"])
    return None  # só-de, só-frete ou vazio


def comparison_cents(entry: dict | None) -> int | None:
    """Valor usado contra min/max: total se parcela."""
    if entry is None:
        return None
    if entry["kind"] == "parcela":
        return entry["total_cents"]
    return entry["cents"]
