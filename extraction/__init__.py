"""Extração declarativa pura. Sem Telegram, filesystem, rede ou código de usuário."""
import re
import json
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from price_parser import extract_prices as parse_prices

ENGINE_VERSION = 1
TYPES = {'text', 'money', 'number', 'condition', 'category', 'link', 'installments'}
OPS = {'line', 'after', 'between', 'presence', 'constant', 'link'}


def validate_template(t):
    if not isinstance(t, dict) or not isinstance(t.get('id'), str) or not t['id'].strip():
        raise ValueError('Modelo precisa de identidade estável.')
    if not isinstance(t.get('name'), str) or not t['name'].strip() or type(t.get('source_id')) is not int:
        raise ValueError('Informe nome e grupo do modelo.')
    markers = t.get('markers')
    if not isinstance(markers, list) or not 1 <= len(markers) <= 20 or any(not isinstance(m, str) or not m.strip() or len(m) > 256 for m in markers):
        raise ValueError('Defina entre 1 e 20 marcadores de reconhecimento.')
    fields = t.get('fields')
    if t.get('kind', 'offer') not in ('offer', 'ignore'):
        raise ValueError('Classificação do modelo inválida.')
    if not isinstance(fields, list) or not (0 if t.get('kind') == 'ignore' else 1) <= len(fields) <= 100:
        raise ValueError('Defina entre 1 e 100 campos.')
    ids = set()
    for f in fields:
        if not isinstance(f, dict) or not isinstance(f.get('field_id'), str) or not f['field_id'] or f['field_id'] in ids:
            raise ValueError('Campos precisam de identidades únicas no modelo.')
        ids.add(f['field_id'])
        if f.get('type') not in TYPES or f.get('op') not in OPS or not isinstance(f.get('name'), str) or not f['name'].strip():
            raise ValueError('Campo com nome, tipo ou extrator inválido.')
        if f.get('scope', 'offer') not in ('message', 'offer', 'price'):
            raise ValueError('Escopo inválido.')
        if f.get('scope') == 'price' and not f.get('option'):
            raise ValueError('Informe a opção de preço do campo.')
        if f['op'] in ('after', 'between', 'presence') and (not isinstance(f.get('marker'), str) or not f['marker'] or len(f['marker']) > 256):
            raise ValueError('Informe o marcador do extrator.')
        if f['op'] == 'between' and (not isinstance(f.get('end'), str) or not f['end']):
            raise ValueError('Informe o marcador final.')
        if f['op'] == 'line' and (type(f.get('line')) is not int or not 1 <= f['line'] <= 1000):
            raise ValueError('Linha deve estar entre 1 e 1000.')
        if f.get('position') is not None and (type(f['position']) is not int or not 0 <= f['position'] < 100):
            raise ValueError('Posição de link inválida.')
        if f.get('host') is not None and not isinstance(f['host'], str):
            raise ValueError('Hostname de extrator inválido.')
        if f['op'] == 'constant' and (not isinstance(f.get('value'), str) or len(f['value']) > 4096):
            raise ValueError('Valor constante precisa ser texto de até 4096 caracteres.')
        if f['type'] == 'category' and (not isinstance(f.get('mapping'), dict) or len(f['mapping']) > 100 or any(not isinstance(k, str) or not isinstance(v, str) for k, v in f['mapping'].items())):
            raise ValueError('Defina até 100 mapeamentos de categoria.')
        if f.get('absence', 'unknown') not in ('unknown', 'absent'):
            raise ValueError('Estado de ausência inválido.')
        if f.get('many', False) not in (True, False) or f.get('required', False) not in (True, False):
            raise ValueError('Cardinalidade e obrigatoriedade inválidas.')
    if not isinstance(t.get('delimiter', ''), str) or len(t.get('delimiter', '')) > 256:
        raise ValueError('Separador de blocos inválido.')
    if not isinstance(t.get('block_marker', ''), str) or len(t.get('block_marker', '')) > 256:
        raise ValueError('Marcador de bloco inválido.')
    if len(str(t)) > 100000:
        raise ValueError('Modelo excede limite de tamanho.')
    return t


def host(url):
    try:
        parts = urlsplit(url)
        if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password:
            return None
        return parts.hostname.rstrip('.').encode('idna').decode('ascii').lower()
    except (ValueError, UnicodeError):
        return None


def validate_link_rules(rules):
    if not isinstance(rules, list) or len(rules) > 500:
        raise ValueError('Lista de regras de loja inválida.')
    seen = set()
    for r in rules:
        if not isinstance(r, dict) or not isinstance(r.get('host'), str) or not isinstance(r.get('store'), str) or not r['store'].strip():
            raise ValueError('Informe hostname e loja.')
        normalized = host('https://' + r['host'])
        if not normalized or normalized != r['host'].lower().rstrip('.') or '/' in r['host'] or ':' in r['host']:
            raise ValueError('Use apenas o hostname completo, sem caminho ou protocolo.')
        if normalized in seen or type(r.get('subdomains', False)) is not bool:
            raise ValueError('Hostname duplicado ou regra inválida.')
        seen.add(normalized)
    return rules


def all_links(text, links):
    result = []
    for m in re.finditer(r'https?://[^\s<>]+', text):
        result.append({'url': m.group().rstrip(').,;'), 'origin': 'text', 'start': m.start()})
    result.extend(links or [])
    unique = {}
    for link in result:
        if isinstance(link, dict) and isinstance(link.get('url'), str) and host(link['url']):
            unique.setdefault(link['url'], link)
    return list(unique.values())


def classified(link, rules):
    hostname = host(link['url'])
    matches = [r for r in rules if hostname == r['host'].lower().rstrip('.') or (
        r.get('subdomains') and hostname and hostname.endswith('.' + r['host'].lower().rstrip('.')))]
    # O host mais específico prevalece, nunca substring de domínio.
    rule = max(matches, key=lambda r: len(r['host']), default=None)
    return {**link, 'host': hostname, 'store': rule['store'] if rule else None}


class FieldError(ValueError):
    def __init__(self, state, field):
        self.state, self.field = state, field


def fragments(text, f, links):
    op = f['op']
    if op == 'constant':
        return [(str(f.get('value', '')), None, 'configuration')]
    if op == 'link':
        ls = all_links(text, links)
        if f.get('host'):
            ls = [l for l in ls if host(l['url']) == f['host']]
        if f.get('position') is not None:
            ls = ls[f['position']:f['position'] + 1]
        return [(l['url'], l.get('start'), l.get('origin', 'entity')) for l in ls]
    if op == 'presence':
        start = text.casefold().find(f['marker'].casefold())
        return [(text[start:start + len(f['marker'])], start, 'text')] if start >= 0 else []
    if op == 'line':
        lines = text.splitlines(keepends=True)
        n = f['line'] - 1
        return [(lines[n].strip(), sum(map(len, lines[:n])) + len(lines[n]) - len(lines[n].lstrip()), 'text')] if n < len(lines) else []
    found, offset = [], 0
    while True:
        at = text.find(f['marker'], offset)
        if at < 0:
            break
        start = at + len(f['marker'])
        end = text.find(f['end'], start) if op == 'between' else text.find('\n', start)
        if end < 0:
            if op == 'between':
                break
            end = len(text)
        raw = text[start:end]
        if raw.strip():
            found.append((raw.strip(), start + len(raw) - len(raw.lstrip()), 'text'))
        offset = max(start, end + (len(f['end']) if op == 'between' else 1))
        if len(found) > 100:
            raise FieldError('ambiguous_field', f['field_id'])
    return found


def convert(raw, f, rules):
    kind = f['type']
    if kind in ('money', 'installments'):
        prices = parse_prices(raw if re.search(r'R\$|RS|\$|\bx\b|\d\s*x', raw, re.I) else 'R$ ' + raw)
        if len(prices) != 1:
            raise FieldError('ambiguous_field' if len(prices) > 1 else 'extraction_error', f['field_id'])
        if kind == 'installments':
            p = prices[0]
            if p.get('kind') != 'parcela':
                raise FieldError('extraction_error', f['field_id'])
            return {k: p[k] for k in ('installments', 'installment_cents', 'total_cents')}
        return prices[0]['cents']
    if kind == 'number':
        try:
            number = Decimal(raw.replace('.', '').replace(',', '.'))
            if not number.is_finite():
                raise InvalidOperation
            return float(number)
        except InvalidOperation:
            raise FieldError('extraction_error', f['field_id']) from None
    if kind == 'condition':
        return 'present'
    if kind == 'category':
        mapping = f.get('mapping', {})
        if raw not in mapping:
            raise FieldError('extraction_error', f['field_id'])
        return mapping[raw]
    if kind == 'link':
        if not host(raw):
            raise FieldError('extraction_error', f['field_id'])
        return classified({'url': raw}, rules)
    return raw


def extract(text, templates, links=None, link_rules=None):
    if not isinstance(text, str) or len(text) > 65536:
        return {'state': 'input_limit', 'offers': []}
    if not text.strip():
        return {'state': 'no_text', 'offers': []}
    matched = [t for t in templates if all(m.casefold() in text.casefold() for m in t['markers'])]
    if len(matched) != 1:
        return {'state': 'unknown_format' if not matched else 'ambiguous_template', 'offers': []}
    t = matched[0]
    validate_template(t)
    if t.get('kind') == 'ignore':
        return {'state': 'ignored', 'template_id': t['id'], 'version': t.get('version'), 'offers': []}
    blocks = text.split(t['delimiter']) if t.get('delimiter') else [text]
    if len(blocks) > 100:
        return {'state': 'input_limit', 'offers': []}
    result, offset = [], 0
    try:
        for block_index, block in enumerate(blocks):
            if not block.strip() or (t.get('block_marker') and t['block_marker'].casefold() not in block.casefold()):
                offset += len(block) + len(t.get('delimiter', ''))
                continue
            values = {}
            for f in t['fields']:
                scope = f.get('scope', 'offer')
                source = text if scope == 'message' else block
                # Só herdar links de botões/entidades ao escopo correto.
                scoped_links = links if scope == 'message' or len(blocks) == 1 else [
                    {**l, 'start': l['start'] - offset} for l in (links or [])
                    if isinstance(l.get('start'), int) and offset <= l['start'] < offset + len(block)]
                parts = fragments(source, f, scoped_links)
                if len(parts) > 1 and not f.get('many'):
                    raise FieldError('ambiguous_field', f['field_id'])
                if not parts and f.get('required'):
                    raise FieldError('extraction_error', f['field_id'])
                evidence = []
                for raw, start, origin in parts:
                    evidence.append({'raw': raw, 'value': convert(raw, f, link_rules or []),
                                     'start': None if start is None else start + (0 if scope == 'message' else offset),
                                     'origin': origin})
                absent = f.get('absence', 'unknown') if f['type'] == 'condition' else None
                values[f['field_id']] = {**(evidence[0] if evidence else {'raw': '', 'start': None, 'origin': 'absent', 'value': absent}),
                    'type': f['type'], 'name': f['name'], 'scope': scope, 'option': f.get('option'),
                    'value': [e['value'] for e in evidence] if f.get('many') else (evidence[0]['value'] if evidence else absent),
                    'evidence': evidence, 'presence': 'present' if evidence else 'unknown'}
            result.append({'block': block_index, 'values': values})
            if len(json.dumps(result, ensure_ascii=False)) > 60000:
                return {'state': 'input_limit', 'offers': []}
            offset += len(block) + len(t.get('delimiter', ''))
    except FieldError as exc:
        return {'state': exc.state, 'field_id': exc.field, 'offers': []}
    return {'state': 'done' if result else 'extraction_error', 'template_id': t['id'], 'version': t.get('version'), 'offers': result}
