"""Worker local opcional, sem TelegramClient. python etl_worker.py [--once]."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading

from catalog_storage import Catalog
from runtime_safety import FileLock, LockBusy


def run(base, once=False, desktop=False):
    stop = threading.Event()
    if desktop:
        def commands():
            for line in sys.stdin:
                try:
                    if json.loads(line).get('command') == 'stop':
                        break
                except (ValueError, AttributeError):
                    continue
            stop.set()
        threading.Thread(target=commands, daemon=True).start()
    # Lifecycle exclusivo além do lock de cada lote (consultas UI podem processar lote).
    with FileLock(base / 'etl.lifecycle.lock'):
        while not stop.is_set():
            try:
                with Catalog(base / 'catalog.db') as db:
                    result = db.process_batch()
                print(json.dumps({'state': 'running', **result}, ensure_ascii=False), flush=True)
            except LockBusy:
                pass
            except (OSError, sqlite3.Error, ValueError) as exc:
                print(json.dumps({'state': 'error', 'error': f'Falha no worker ({type(exc).__name__}).'}), flush=True)
                if once:
                    return 1
            if once:
                break
            stop.wait(1)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--desktop', action='store_true')
    args = parser.parse_args()
    base = Path(os.environ.get('COMPRAS_DATA_DIR', Path(__file__).resolve().parent))
    base.mkdir(parents=True, exist_ok=True)
    try:
        sys.exit(run(base, args.once, args.desktop))
    except LockBusy:
        print(json.dumps({'state': 'error', 'error': 'Já existe um worker ativo.'}), flush=True)
        sys.exit(1)
