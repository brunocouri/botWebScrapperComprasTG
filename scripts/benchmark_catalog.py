"""Medição sintética isolada; nunca abre catalog.db do workspace."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog_storage import Catalog


def benchmark(count):
    started = datetime.now(timezone.utc) - timedelta(days=1)
    writes, queries = [], []
    with tempfile.TemporaryDirectory(prefix='comprastg-benchmark-') as directory:
        with Catalog(Path(directory) / 'catalog.db') as db:
            db.set_source(-1001, 'Origem sintética', True, now=started.isoformat())
            template = {'id': 'synthetic', 'name': 'Sintético', 'source_id': -1001, 'markers': ['Produto:', 'Pix:'], 'fields': [
                {'field_id': 'product', 'name': 'Produto', 'type': 'text', 'op': 'after', 'marker': 'Produto:'},
                {'field_id': 'pix', 'name': 'Pix', 'type': 'money', 'op': 'after', 'marker': 'Pix:'}]}
            d = db.save_draft(template, 0)
            db.publish(template['id'], d['revision'])
            for n in range(count):
                before = time.perf_counter()
                db.capture(-1001, n + 1, (started + timedelta(seconds=n + 1)).isoformat(), f'Produto: Item {n % 200}\nPix: R$ {n % 3000 + 10},90')
                writes.append((time.perf_counter() - before) * 1000)
            before = time.perf_counter()
            while db.process_batch()['processed']:
                pass
            processing_seconds = time.perf_counter() - before
            for _ in range(10):
                before = time.perf_counter()
                result = db.search({'source_id': -1001, 'values': [{'field_id': 'pix', 'max': 100000}]}, offset=25)
                queries.append((time.perf_counter() - before) * 1000)
            plan = [r['detail'] for r in db.db.execute('EXPLAIN QUERY PLAN SELECT offer_id FROM offer_values WHERE field_id=? AND value_number<=?', ('pix', 100000))]
            return {'messages': count, 'offers': db.status()['offers'], 'database_bytes': db.status()['bytes'],
                    'capture_median_ms': statistics.median(writes), 'capture_p95_ms': sorted(writes)[int(len(writes) * .95)],
                    'processing_seconds': processing_seconds, 'search_median_ms': statistics.median(queries),
                    'search_max_ms': max(queries), 'search_results': result['total'], 'numeric_index_plan': plan,
                    'note': 'Dados sintéticos temporários; não representa SLA ou latência de rede Telegram.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=10000)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not 100 <= args.count <= 100000:
        parser.error('count precisa estar entre 100 e 100000')
    result = benchmark(args.count)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
