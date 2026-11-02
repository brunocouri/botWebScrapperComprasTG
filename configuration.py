"""Configuração compartilhada CLI/Electron. Erros de leitura nunca viram defaults."""
import hashlib
import io
import json
from pathlib import Path
import re

from dotenv import dotenv_values
from runtime_safety import FileLock, atomic_write
from rules import normalize_document, validate_rules


class ConfigConflict(ValueError):
    pass


def revision(raw):
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def validate_groups(groups):
    if not isinstance(groups, list) or len(groups) > 5000:
        raise ValueError('Formato de grupos inválido.')
    ids = set()
    for group in groups:
        if (not isinstance(group, dict) or type(group.get('id')) is not int
                or abs(group['id']) > 2**53 - 1 or group['id'] in ids
                or not isinstance(group.get('name'), str)
                or type(group.get('selected')) is not bool):
            raise ValueError('Grupo inválido ou ID duplicado.')
        ids.add(group['id'])
    return groups


class Configuration:
    def __init__(self, base):
        self.base = Path(base)

    def _lock(self):
        return FileLock(self.base / 'config.lock', timeout=5)

    def _read(self, name):
        try:
            return (self.base / name).read_text(encoding='utf-8')
        except FileNotFoundError:
            return ''

    def _check(self, raw, expected):
        if not isinstance(expected, str) or revision(raw) != expected:
            raise ConfigConflict('A configuração mudou. Recarregue antes de salvar; suas edições foram preservadas.')

    def _rules(self):
        raw = self._read('keywords.json')
        if not raw and not (self.base / 'keywords.json').exists():
            return [], raw
        data = json.loads(raw)
        _, rules = normalize_document(data)
        errors = validate_rules(rules)
        if errors:
            raise ValueError('; '.join(errors))
        if not (isinstance(data, dict) and data.get('version') == 2 and data.get('rules') == rules):
            backup = self.base / 'keywords.json.bak'
            if not backup.exists():
                atomic_write(backup, raw)
            raw = json.dumps({'version': 2, 'rules': rules}, ensure_ascii=False, indent=2)
            atomic_write(self.base / 'keywords.json', raw)
        return rules, raw

    def get_rules(self):
        with self._lock():
            rules, raw = self._rules()
            return {'rules': rules, 'revision': revision(raw)}

    def save_rules(self, rules, expected):
        errors = validate_rules(rules)
        if errors:
            raise ValueError('; '.join(errors))
        terms = [r['term'].strip().casefold() for r in rules]
        if len(set(terms)) != len(terms):
            raise ValueError('Palavra-chave duplicada.')
        with self._lock():
            _, raw = self._rules()
            self._check(raw, expected)
            raw = json.dumps({'version': 2, 'rules': rules}, ensure_ascii=False, indent=2)
            atomic_write(self.base / 'keywords.json', raw)
            return {'rules': rules, 'revision': revision(raw)}

    def add_rule(self, term, expected=None):
        if not isinstance(term, str) or not 1 <= len(term.strip()) <= 120:
            raise ValueError('Informe uma palavra-chave de até 120 caracteres.')
        from rules import generate_rule_id
        with self._lock():
            rules, raw = self._rules()
            if expected is not None:
                self._check(raw, expected)
            if any(r['term'].casefold() == term.strip().casefold() for r in rules):
                raise ValueError('Palavra-chave já cadastrada.')
            rules.append({'id': generate_rule_id(term, {r['id'] for r in rules}),
                          'term': term.strip(), 'enabled': True, 'min_cents': None, 'max_cents': None})
            raw = json.dumps({'version': 2, 'rules': rules}, ensure_ascii=False, indent=2)
            atomic_write(self.base / 'keywords.json', raw)
            return {'rules': rules, 'revision': revision(raw)}

    def _groups(self):
        raw = self._read('watched_groups.json')
        absent = not raw and not (self.base / 'watched_groups.json').exists()
        return ([] if absent else validate_groups(json.loads(raw))), raw

    def get_groups(self):
        with self._lock():
            groups, raw = self._groups()
            return {'groups': groups, 'revision': revision(raw)}

    def save_groups(self, groups, expected):
        validate_groups(groups)
        with self._lock():
            _, raw = self._groups()
            self._check(raw, expected)
            raw = json.dumps(groups, ensure_ascii=False, indent=2)
            atomic_write(self.base / 'watched_groups.json', raw)
            return {'groups': groups, 'revision': revision(raw)}

    def merge_groups(self, fetched):
        with self._lock():
            groups, _ = self._groups()
            selected = {g['id']: g['selected'] for g in groups}
            merged = [dict(id=g['id'], name=g['name'], selected=selected.get(g['id'], False)) for g in fetched]
            validate_groups(merged)
            atomic_write(self.base / 'watched_groups.json', json.dumps(merged, ensure_ascii=False, indent=2))
            return merged

    def get_config(self):
        with self._lock():
            raw = self._read('.env')
            env = dotenv_values(self.base / '.env')
            secret = env.get('API_HASH') or ''
            return {'apiId': env.get('API_ID') or '', 'phone': env.get('PHONE') or '',
                    'apiHashSet': bool(secret), 'apiHashPreview': '••••••••' + secret[-4:] if secret else '',
                    'revision': revision(raw)}

    def save_config(self, payload, expected):
        if not isinstance(payload, dict):
            raise ValueError('Configuração inválida.')
        values = {}
        for key, pattern, dest in [('apiId', r'\d{5,12}', 'API_ID'), ('apiHash', r'[a-fA-F0-9]{32}', 'API_HASH'),
                                   ('phone', r'\+\d{10,15}', 'PHONE')]:
            if key not in payload:
                continue
            value = str(payload[key]).strip()
            if key == 'apiHash' and not value:
                continue
            if not re.fullmatch(pattern, value):
                raise ValueError(f'Campo {key} inválido.')
            values[dest] = value
        with self._lock():
            raw = self._read('.env')
            self._check(raw, expected)
            lines, seen = [], set()
            for line in raw.splitlines():
                match = re.match(r'^\s*(API_ID|API_HASH|PHONE)\s*=', line)
                if match and match[1] in values:
                    key = match[1]
                    if key not in seen:
                        lines.append(key + '=' + values[key])
                        seen.add(key)
                else:
                    lines.append(line)
            lines.extend(k + '=' + v for k, v in values.items() if k not in seen)
            atomic_write(self.base / '.env', '\n'.join(lines) + '\n')
        return self.get_config()

    def snapshot(self):
        return self.runtime_config()['snapshot']

    def runtime_config(self):
        with self._lock():
            rules, _ = self._rules()
            groups, _ = self._groups()
            # Includes credentials in the digest only; no secret crosses IPC.
            env_raw = self._read('.env')
            # Apenas seleção de captura compõe o snapshot; jobs não exigem reinício.
            catalog_sources = []
            catalog_path = self.base / 'catalog.db'
            if catalog_path.exists():
                import sqlite3
                try:
                    with sqlite3.connect(catalog_path.as_uri() + '?mode=ro', uri=True, timeout=.2) as catalog:
                        catalog_sources = catalog.execute('SELECT id,enabled,revision FROM sources ORDER BY id').fetchall()
                except sqlite3.Error:
                    catalog_sources = 'unavailable'
            if isinstance(catalog_sources, list):
                # Defaults previstos antes da criação física: iniciar o catálogo
                # não deve produzir falsa divergência de configuração aplicada.
                known = {s[0] for s in catalog_sources}
                catalog_sources.extend((g['id'], 1, 1) for g in groups if g['selected'] and g['id'] not in known)
                catalog_sources.sort(key=lambda s: s[0])
            digest = revision(json.dumps({'rules': rules, 'groups': groups, 'capture': catalog_sources,
                                         'env': env_raw}, sort_keys=True, ensure_ascii=False))
            snapshot = {'revision': digest, 'groups': sum(g['selected'] for g in groups),
                        'rules': sum(r['enabled'] for r in rules), 'keywords': [r['term'] for r in rules if r['enabled']]}
            return {'snapshot': snapshot, 'rules': rules, 'groups': groups,
                    'credentials': dotenv_values(stream=io.StringIO(env_raw))}
