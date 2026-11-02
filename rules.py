"""Regras de monitoramento v2 + evaluate() multi-regra + política D6.
Puro: stdlib + price_parser. Sem Telegram, sem IO (exceto load/migrate
explícitos por path), sem Electron. SPEC-PREÇOS §2/§3 (F2).

bot.py importa daqui (build_pattern); o handler continua em bot.py (F3).
"""

from __future__ import annotations

import functools
import json
import re
import secrets
from pathlib import Path

from price_parser import extract_prices, decisive, comparison_cents

RULES_VERSION = 2


# ---------------------------------------------------------------- matcher ---
# Mesma semântica histórica do bot.py (F2 §6): exato + case-insensitive.

def build_pattern(keywords) -> re.Pattern | None:
    kws = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    if not kws:
        return None
    return re.compile(r"\b(" + "|".join(map(re.escape, kws)) + r")\b", re.IGNORECASE)


@functools.lru_cache(maxsize=256)
def _compile_term(term: str):
    return build_pattern([term])


def match_term(text: str | None, term: str | None) -> str | None:
    if not text or not term or not term.strip():
        return None
    m = _compile_term(term).search(text)
    return m.group(1) if m else None


# ---------------------------------------------------------------- modelo ----

def _slug(term: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")
    return s or "rule"


def generate_rule_id(term: str, existing: set) -> str:
    """slug legível + 4 hex. Colisão: regenera (limitado, depois erro explícito)."""
    base = _slug(term)
    for _ in range(100):
        rid = f"{base}-{secrets.token_hex(2)}"
        if rid not in existing:
            return rid
    raise ValueError("colisão de rule_id esgotada")


def _is_cents(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_rule(rule) -> list:
    """Estrito: lista problemas, não corrige. min/max ausentes = null (ok)."""
    errs = []
    if not isinstance(rule, dict):
        return ["rule deve ser objeto"]
    term = rule.get("term")
    if not isinstance(term, str) or not term.strip():
        errs.append("term vazio")
    elif len(term.strip()) > 120:
        errs.append("term deve ter até 120 caracteres")
    rid = rule.get("id")
    if not isinstance(rid, str) or not rid.strip():
        errs.append("id vazio")
    if not isinstance(rule.get("enabled"), bool):
        errs.append("enabled deve ser booleano")
    for f in ("min_cents", "max_cents"):
        v = rule.get(f)
        if v is not None and not _is_cents(v):
            errs.append(f"{f} deve ser int (centavos) ou null")
        elif _is_cents(v) and v < 0:
            errs.append(f"{f} >= 0")
        elif _is_cents(v) and v > 2**53 - 1:
            errs.append(f"{f} excede centavos seguros")
    mn, mx = rule.get("min_cents"), rule.get("max_cents")
    if _is_cents(mn) and _is_cents(mx) and mn > mx:
        errs.append("min_cents <= max_cents")
    return errs


def validate_rules(rules) -> list:
    if not isinstance(rules, list):
        return ["rules deve ser lista"]
    errs = []
    seen: dict = {}
    for i, r in enumerate(rules):
        for e in validate_rule(r):
            errs.append(f"rules[{i}]: {e}")
        if isinstance(r, dict) and isinstance(r.get("id"), str):
            if r["id"] in seen:
                errs.append(f"rules[{i}]: id duplicado '{r['id']}' (primeiro em rules[{seen[r['id']]}])")
            else:
                seen[r["id"]] = i
    return errs


# ------------------------------------------------------- leitura/migração ---

def _rule_from_legacy(term: str, existing: set) -> dict:
    t = str(term).strip()
    if not t:
        raise ValueError("term vazio no legado")
    rid = generate_rule_id(t, existing)
    existing.add(rid)
    return {"id": rid, "term": t, "enabled": True, "min_cents": None, "max_cents": None}


def _normalize_rule_dict(item: dict, existing: set) -> dict:
    errs = validate_rule(item)
    if errs:
        raise ValueError("; ".join(errs))
    if item["id"] in existing:
        raise ValueError(f"id duplicado '{item['id']}'")
    existing.add(item["id"])
    return {"id": item["id"], "term": item["term"].strip(), "enabled": item["enabled"],
            "min_cents": item.get("min_cents"), "max_cents": item.get("max_cents")}


def normalize_document(data) -> tuple:
    """Legado reconhecido -> (versão, rules). Corrompido -> ValueError explícito.
    Nunca retorna lista vazia silenciosa para formato inválido."""
    if isinstance(data, list):
        existing: set = set()
        rules = []
        for item in data:
            if isinstance(item, str):
                rules.append(_rule_from_legacy(item, existing))
            elif isinstance(item, dict):
                rules.append(_normalize_rule_dict(item, existing))
            else:
                raise ValueError(f"item inválido no legado: {item!r}")
        return (1, rules)
    if isinstance(data, dict) and isinstance(data.get("rules"), list):
        version = data.get("version", RULES_VERSION)
        existing = set()
        rules = []
        for item in data["rules"]:
            if isinstance(item, str):
                rules.append(_rule_from_legacy(item, existing))
            elif isinstance(item, dict):
                rules.append(_normalize_rule_dict(item, existing))
            else:
                raise ValueError(f"item inválido em rules: {item!r}")
        return (version, rules)
    raise ValueError(f"formato de keywords inválido: {type(data).__name__}")


def load_rules_file(path) -> tuple:
    """Lê sem escrever. Ausente/corrompido -> exceção explícita (nunca [] silencioso)."""
    raw = Path(path).read_text(encoding="utf-8")  # FileNotFoundError propaga
    return normalize_document(json.loads(raw))  # JSONDecodeError propaga


def migrate_file(path) -> list:
    """v1 -> escreve v2 + .bak (só cria .bak se ainda não existir). v2 válido:
    só valida e retorna, sem escrever nada. Nunca chamado pelo bot.py (F3 decide)."""
    # Mesmo lock e identidade usados pelo Electron. Paths de fixtures também
    # são aceitos; não há dependência do arquivo real.
    from configuration import Configuration
    from runtime_safety import atomic_write, FileLock
    p = Path(path)
    if p.name == 'keywords.json':
        return Configuration(p.parent).get_rules()['rules']
    with FileLock(p.parent / 'config.lock'):
        raw = p.read_text(encoding='utf-8')
        data = json.loads(raw)
        _, rules = normalize_document(data)
        if not (isinstance(data, dict) and data.get('version') == RULES_VERSION):
            bak = Path(str(p) + '.bak')
            if not bak.exists():
                atomic_write(bak, raw)
            atomic_write(p, json.dumps({'version': RULES_VERSION, 'rules': rules}, ensure_ascii=False, indent=2))
        return rules


# --------------------------------------------------------------- evaluate ---

def _bounds(rule: dict):
    mn, mx = rule.get("min_cents"), rule.get("max_cents")
    if isinstance(mn, bool):
        mn = None
    if isinstance(mx, bool):
        mx = None
    return mn, mx


def associated_prices(text, term, prices):
    """Associação conservadora, com evidência de linha; não é NLP/OCR.

    Preço na mesma linha é evidência direta. Linhas só de pagamento podem
    continuar a oferta. Outra descrição com preço não herda a keyword.
    Sem evidência direta, múltiplos valores avulsos são ambíguos.
    """
    lines = text.split('\n')
    matching = {i for i, line in enumerate(lines) if match_term(line, term)}
    direct = [p for p in prices if p.get('line', 0) in matching]

    def payment_only(index):
        line = lines[index]
        for price in prices:
            if price.get('line', 0) == index:
                line = line.replace(price['raw'], '')
        remainder = re.sub(r'\b(no|na|em|de|por|pix|boleto|vista|ou|total|frete|envio|sem|juros|com|cupom|preço|valor|à|a)\b', '', line, flags=re.I)
        return not re.sub(r'[\s\W_]+', '', remainder, flags=re.UNICODE)

    if direct:
        selected = list(direct)
        end = max(matching)
        for index in range(end + 1, len(lines)):
            if not lines[index].strip():
                break
            if payment_only(index):
                selected.extend(p for p in prices if p.get('line', 0) == index)
            else:
                break
    else:
        selected = prices
        product_lines = {p.get('line', 0) for p in prices if p['kind'] not in ('de', 'frete')}
        if any(not payment_only(i) and i not in matching for i in product_lines):
            return [], True
    amounts = {p['cents'] for p in selected if p['kind'] in ('avulso', 'vista', 'por')}
    # Texto livre como "ou"/"Pix" não comprova que dois valores pertençam
    # ao mesmo produto. Referência "de" e parcela não disputam esse vínculo.
    ambiguous = len(amounts) > 1
    return selected, ambiguous


def evaluate(text: str | None, rules) -> list:
    """Uma Evaluation por regra habilitada que casar, em ordem das rules.
    Extração de preços 1x por mensagem. Pura."""
    if not text:
        return []
    matching_rules = [r for r in rules or [] if r.get('enabled', True) and match_term(text, r.get('term', ''))]
    if not matching_rules:
        return []
    prices = extract_prices(text)
    out = []
    for r in matching_rules:
        term = r.get("term", "")
        kw = match_term(text, term)
        if kw is None:
            continue
        associated, ambiguous = associated_prices(text, term, prices)
        dec = None if ambiguous else decisive(associated)
        comp = comparison_cents(dec)
        mn, mx = _bounds(r)
        if mn is None and mx is None:
            eligible, reason = True, "ok"
        elif ambiguous:
            eligible, reason = False, 'ambiguous_price'
        elif comp is None:
            eligible, reason = False, "no_price"
        elif mn is not None and comp < mn:
            eligible, reason = False, "below_min"
        elif mx is not None and comp > mx:
            eligible, reason = False, "above_max"
        else:
            eligible, reason = True, "ok"
        out.append({"rule_id": r.get("id"), "keyword": term, "prices": prices,
                    "decisive": dec, "eligible": eligible, "reason": reason,
                    'association': {'ambiguous': ambiguous, 'lines': sorted({p.get('line', 0) + 1 for p in associated})}})
    return out


def select_winner(evaluations) -> tuple:
    """D6 first-eligible-only. Pura: (vencedora|None, demais).
    Elegível não-vencedora -> cópia com reason=superseded. Inelegível intacta.
    Não envia nada; falha futura de envio não promove ninguém (F3 respeita)."""
    evs = list(evaluations or [])
    winner = next((e for e in evs if e.get("eligible")), None)
    rest = []
    for e in evs:
        if winner is not None and e is winner:
            continue
        if e.get("eligible"):
            rest.append({**e, "reason": "superseded"})
        else:
            rest.append(e)
    return winner, rest


def plan_effects(evaluations, dry_run: bool = False) -> list:
    """D6 aplicada ao fluxo real: [(kind, evaluation)].
    kind ∈ {alert, dry, filtered}. Pura — o handler executa, sem Telegram.
    Ordem: filtradas primeiro, vencedora por último (determinístico)."""
    winner, rest = select_winner(evaluations)
    plan = [("filtered", e) for e in rest]
    if winner is not None:
        plan.append(("dry" if dry_run else "alert", winner))
    return plan


def format_brl(cents: int) -> str:
    """189900 -> '1.899,00'. Pura (apresentação, sem decisão)."""
    reais, cent = divmod(int(cents), 100)
    return f"{reais:,}".replace(",", ".") + f",{cent:02d}"


def decisive_to_json(dec) -> dict | None:
    """Serializa Decisive para o protocolo (objeto, nunca só cents). Pura."""
    if dec is None:
        return None
    d = {"cents": comparison_cents(dec), "kind": dec["kind"]}
    if dec["kind"] == "parcela":
        d.update({"installments": dec["installments"],
                  "installment_cents": dec["installment_cents"],
                  "total_cents": dec["total_cents"]})
    return d


class RulesConfigError(Exception):
    """Configuração de keywords inválida: erro explícito, nunca default silencioso."""


def default_rules() -> list:
    """Legado: arquivo ausente => regra A57 sem faixa, em memória, sem escrever."""
    return [{"id": f"a57-{secrets.token_hex(2)}", "term": "A57",
             "enabled": True, "min_cents": None, "max_cents": None}]


def load_rules_config(path) -> list:
    """Startup F3: migra v1->v2 se preciso, valida, retorna Rule[].
    Falha -> RulesConfigError (impede inicialização). Arquivo ausente ->
    default em memória (comportamento legado). Nunca escreve fora de migrate."""
    p = Path(path)
    if not p.exists():
        return default_rules()
    try:
        migrate_file(p)  # no-op em v2 válido
        _, rules = load_rules_file(p)
    except (ValueError, OSError) as e:
        raise RulesConfigError(str(e))
    errs = validate_rules(rules)
    if errs:
        raise RulesConfigError("; ".join(errs))
    if not rules:
        raise RulesConfigError("nenhuma regra configurada")
    return rules
