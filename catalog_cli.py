"""Operações do catálogo expostas ao IPC; nenhuma importação de Telethon."""
from extraction import extract, validate_template
from catalog_storage import Catalog


def dispatch_catalog(payload, base):
    op = payload.get('action')
    allowed = {'status', 'sources', 'source:save', 'messages', 'message', 'templates', 'template:save',
               'template:publish', 'template:archive', 'preview', 'fields', 'links', 'links:save', 'reviews',
               'review:ignore', 'review:examples', 'review:split', 'search', 'process', 'reprocess:preview', 'reprocess:confirm', 'reprocess:cancel', 'reprocess:resume', 'reprocess:list', 'alerts', 'alerts:save', 'deliveries', 'source:history', 'run'}
    if op not in allowed:
        raise ValueError('Operação de catálogo desconhecida.')
    if op in ('sources', 'status'):
        from configuration import Configuration
        from catalog_runtime import ensure_selected_sources
        sources = ensure_selected_sources(base / 'catalog.db', Configuration(base).get_groups()['groups'])
        if op == 'sources':
            return sources
    if op == 'preview':
        t = payload.get('template')
        validate_template(t)
        peers = []
        if (base / 'catalog.db').exists():
            with Catalog(base / 'catalog.db') as db:
                peers = [p for p in db._bundle(t['source_id'])['templates'] if p['id'] != t['id']]
        return extract(payload.get('text', ''), peers + [t], payload.get('links', []), payload.get('link_rules', []))
    with Catalog(base / 'catalog.db') as db:
        if op == 'status':
            return db.status()
        if op == 'alerts':
            return db.alert_rules()
        if op == 'alerts:save':
            return db.save_alert_rules(payload.get('rules'), payload.get('revision'))
        if op == 'deliveries':
            return [dict(r) for r in db.db.execute('SELECT id,rule_name,source_id,message_id,state,error,created_at FROM structured_deliveries ORDER BY id DESC LIMIT 50')]
        if op == 'sources':
            return db.sources()
        if op == 'source:history':
            return [dict(r) for r in db.db.execute('SELECT at,kind FROM source_events WHERE source_id=? ORDER BY id DESC', (payload.get('id'),))]
        if op == 'source:save':
            return db.set_source(payload.get('id'), payload.get('name'), payload.get('enabled'),
                                 resume=payload.get('resume'), expected=payload.get('revision'))
        if op == 'messages':
            return db.messages(payload.get('source_id'), payload.get('offset', 0), payload.get('limit', 25))
        if op == 'message':
            return db.message(payload.get('id'))
        if op == 'run':
            row = db.db.execute('SELECT id,state,created_at,result FROM extraction_runs WHERE id=?', (payload.get('id'),)).fetchone()
            if not row:
                raise ValueError('Execução não encontrada.')
            return dict(row)
        if op == 'templates':
            return db.templates()
        if op == 'template:save':
            return db.save_draft(payload.get('template'), payload.get('revision'))
        if op == 'template:publish':
            return db.publish(payload.get('id'), payload.get('revision'))
        if op == 'template:archive':
            with db.transaction():
                cur = db.db.execute('UPDATE templates SET archived=1,revision=revision+1 WHERE id=? AND revision=?', (payload.get('id'), payload.get('revision')))
                if not cur.rowcount:
                    raise ValueError('Modelo alterado. Atualize antes de arquivar.')
            return {'ok': True}
        if op == 'fields':
            return db.fields()
        if op == 'links':
            return db.links()
        if op == 'links:save':
            return db.save_links(payload.get('rules'), payload.get('revision'))
        if op == 'reviews':
            return db.reviews(payload.get('offset', 0), payload.get('limit', 25))
        if op == 'review:examples':
            return [dict(r) for r in db.db.execute('''SELECT m.id,m.text,m.published_at FROM review_items r
                JOIN message_revisions m ON m.id=r.revision_id WHERE r.source_id=? AND r.reason=? AND r.signature=? ORDER BY m.id DESC LIMIT 25''',
                (payload.get('source_id'), payload.get('reason'), payload.get('signature')))]
        if op == 'review:split':
            import uuid
            db.db.execute('UPDATE review_items SET signature=? WHERE revision_id=?', (str(uuid.uuid4()), payload.get('id')))
            return {'ok': True}
        if op == 'review:ignore':
            # Por mensagem: não confiar na assinatura aproximada como classificação.
            with db.transaction():
                revision_id = payload.get('id')
                if not db.db.execute('SELECT 1 FROM review_items WHERE revision_id=?', (revision_id,)).fetchone():
                    raise ValueError('Pendência não encontrada.')
                db.db.execute("INSERT INTO extraction_runs(job_id,revision_id,config_hash,state,result,created_at) VALUES(0,?,'manual','ignored',?,datetime('now'))", (revision_id, '{"state":"ignored","offers":[]}'))
                db.db.execute('DELETE FROM review_items WHERE revision_id=?', (revision_id,))
            return {'ok': True}
        if op == 'search':
            return db.search(payload.get('filters', {}), payload.get('offset', 0), payload.get('limit', 25))
        if op == 'process':
            return db.process_batch()
        if op == 'reprocess:preview':
            return db.reprocess_preview(payload.get('scope'))
        if op == 'reprocess:list':
            import json
            from catalog_storage import digest
            result = []
            for row in db.db.execute("SELECT * FROM reprocess_requests WHERE state!='preview' ORDER BY created_at DESC LIMIT 20").fetchall():
                data = json.loads(row['payload'])
                counts = {'pending': 0, 'done': 0, 'cancelled': 0}
                for state in db.db.execute('SELECT state,COUNT(*) FROM processing_jobs WHERE config_hash=? AND revision_id IN (SELECT value FROM json_each(?)) GROUP BY state', (digest(data['bundle']), json.dumps(data['ids']))):
                    counts[state[0]] = state[1]
                result.append({'token': row['token'], 'created_at': row['created_at'], 'state': row['state'], 'total': len(data['ids']), **counts})
            return result
        if op == 'reprocess:confirm':
            return db.reprocess_confirm(payload.get('token'))
        if op == 'reprocess:resume':
            import json
            from catalog_storage import digest
            with db.transaction():
                row = db.db.execute("SELECT payload FROM reprocess_requests WHERE token=? AND state='cancelled'", (payload.get('token'),)).fetchone()
                if not row:
                    raise ValueError('Lote cancelado não encontrado.')
                data = json.loads(row[0])
                db.db.execute("UPDATE processing_jobs SET state='pending',allow_alerts=0 WHERE config_hash=? AND revision_id IN (SELECT value FROM json_each(?)) AND state='cancelled'", (digest(data['bundle']), json.dumps(data['ids'])))
                db.db.execute("UPDATE reprocess_requests SET state='queued' WHERE token=?", (payload.get('token'),))
            return {'ok': True}
        if op == 'reprocess:cancel':
            with db.transaction():
                row = db.db.execute("SELECT payload FROM reprocess_requests WHERE token=? AND state='queued'", (payload.get('token'),)).fetchone()
                if row:
                    import json
                    from catalog_storage import digest
                    data = json.loads(row[0])
                    for rid in data['ids']:
                        db.db.execute("UPDATE processing_jobs SET state='cancelled' WHERE revision_id=? AND config_hash=? AND state='pending'", (rid, digest(data['bundle'])))
                    db.db.execute("UPDATE reprocess_requests SET state='cancelled' WHERE token=?", (payload.get('token'),))
            return {'ok': True}
