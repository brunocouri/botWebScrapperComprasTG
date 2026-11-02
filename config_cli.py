"""Operações sem Telegram. stdin/stdout JSON, sem importar bot.py ou abrir sessão."""
import json
import os
from pathlib import Path
import sys
import sqlite3

from configuration import Configuration
from rules import evaluate, select_winner, validate_rules


def dispatch(payload, base):
    if not isinstance(payload, dict):
        raise ValueError('Pedido inválido.')
    operation = payload.get('operation')
    if operation == 'catalog':
        from catalog_cli import dispatch_catalog
        return dispatch_catalog(payload, base)
    if operation == 'simulate':
        rules, text = payload.get('rules'), payload.get('text')
        errors = validate_rules(rules)
        if errors or not isinstance(text, str) or len(text) > 65536:
            raise ValueError('Texto ou regras inválidos para simulação.')
        evaluations = evaluate(text, rules)
        winner, rest = select_winner(evaluations)
        return {'evaluations': evaluations, 'winner': winner, 'others': rest}
    repo = Configuration(base)
    if operation == 'groups:get':
        return repo.get_groups()
    if operation == 'groups:save':
        return repo.save_groups(payload.get('groups'), payload.get('revision'))
    if operation == 'rules:get':
        return repo.get_rules()
    if operation == 'rules:save':
        return repo.save_rules(payload.get('rules'), payload.get('revision'))
    if operation == 'rules:add':
        return repo.add_rule(payload.get('term'), payload.get('revision'))
    if operation == 'config:get':
        return repo.get_config()
    if operation == 'config:save':
        return repo.save_config(payload.get('payload'), payload.get('revision'))
    if operation == 'snapshot':
        return repo.snapshot()
    raise ValueError('Operação desconhecida.')


if __name__ == '__main__':
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        data = sys.stdin.read(1_000_001)
        if len(data) > 1_000_000:
            raise ValueError('Pedido muito grande.')
        result = dispatch(json.loads(data), Path(os.environ.get('COMPRAS_DATA_DIR', Path(__file__).resolve().parent)))
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, TypeError, sqlite3.Error) as exc:
        # Não ecoar JSON fornecido, credenciais ou códigos de login.
        message = 'Arquivo JSON inválido. Preserve o original e restaure uma cópia válida.' if isinstance(exc, json.JSONDecodeError) else str(exc)
        print(json.dumps({'error': message}, ensure_ascii=False))
        sys.exit(1)
