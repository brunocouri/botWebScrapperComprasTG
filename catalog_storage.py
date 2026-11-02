"""Catálogo local opcional. Identidades e transações independentes de seen.db."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import uuid

from extraction import ENGINE_VERSION, extract, validate_template, validate_link_rules
from runtime_safety import FileLock


def utc(value=None):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        raise ValueError('Data precisa de fuso horário.')
    return dt.astimezone(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, enabled INTEGER NOT NULL,
 capture_started_at TEXT NOT NULL, checkpoint TEXT, revision INTEGER NOT NULL DEFAULT 1,
 degraded TEXT);
CREATE TABLE IF NOT EXISTS capture_intervals (
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id),
 started_at TEXT NOT NULL, ended_at TEXT);
CREATE TABLE IF NOT EXISTS source_events (id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL REFERENCES sources(id),
 at TEXT NOT NULL,kind TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS message_revisions (
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id), message_id INTEGER NOT NULL,
 published_at TEXT NOT NULL, revision_at TEXT NOT NULL, captured_at TEXT NOT NULL,
 text TEXT NOT NULL, metadata TEXT NOT NULL, hash TEXT NOT NULL,
 UNIQUE(source_id,message_id,revision_at,hash));
CREATE INDEX IF NOT EXISTS messages_origin_date ON message_revisions(source_id,published_at);
CREATE INDEX IF NOT EXISTS messages_identity ON message_revisions(source_id,message_id,revision_at DESC,id DESC);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL);
INSERT OR IGNORE INTO settings VALUES('links',0,'[]');
INSERT OR IGNORE INTO settings VALUES('alerts',0,'[]');
CREATE TABLE IF NOT EXISTS field_definitions (id TEXT PRIMARY KEY, name TEXT NOT NULL,type TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS templates (id TEXT PRIMARY KEY, source_id INTEGER NOT NULL,
 revision INTEGER NOT NULL, draft TEXT NOT NULL, published INTEGER, archived INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS template_versions (template_id TEXT NOT NULL, version INTEGER NOT NULL,
 payload TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(template_id,version));
CREATE TABLE IF NOT EXISTS configurations (hash TEXT PRIMARY KEY,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS processing_jobs (id INTEGER PRIMARY KEY, revision_id INTEGER NOT NULL REFERENCES message_revisions(id),
 config_hash TEXT NOT NULL REFERENCES configurations(hash), state TEXT NOT NULL DEFAULT 'pending',
 attempts INTEGER NOT NULL DEFAULT 0,error TEXT, allow_alerts INTEGER NOT NULL DEFAULT 0, UNIQUE(revision_id,config_hash));
CREATE INDEX IF NOT EXISTS jobs_state ON processing_jobs(state,id);
CREATE TABLE IF NOT EXISTS extraction_runs (id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL,
 revision_id INTEGER NOT NULL, config_hash TEXT NOT NULL, state TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS offer_records (id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL, message_id INTEGER NOT NULL,
 revision_id INTEGER NOT NULL,run_id INTEGER NOT NULL, block INTEGER NOT NULL,published_at TEXT NOT NULL,payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS offers_origin_date ON offer_records(source_id,published_at,id);
CREATE INDEX IF NOT EXISTS offers_message ON offer_records(source_id,message_id);
CREATE TABLE IF NOT EXISTS offer_values (offer_id INTEGER NOT NULL REFERENCES offer_records(id) ON DELETE CASCADE,
 field_id TEXT NOT NULL,option_id TEXT,value_text TEXT,value_number REAL,presence TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS values_numeric ON offer_values(field_id,value_number,offer_id);
CREATE INDEX IF NOT EXISTS values_text ON offer_values(field_id,value_text,offer_id);
CREATE INDEX IF NOT EXISTS values_offer_field ON offer_values(offer_id,field_id,option_id);
CREATE INDEX IF NOT EXISTS runs_revision ON extraction_runs(revision_id,id DESC);
CREATE TABLE IF NOT EXISTS review_items (revision_id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL,
 reason TEXT NOT NULL,signature TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS reviews_grouped ON review_items(source_id,reason,signature);
CREATE TABLE IF NOT EXISTS reprocess_requests (token TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'preview');
CREATE TABLE IF NOT EXISTS structured_deliveries (id INTEGER PRIMARY KEY, rule_id TEXT NOT NULL, rule_name TEXT NOT NULL,
 rule_hash TEXT NOT NULL, source_id INTEGER NOT NULL, message_id INTEGER NOT NULL,revision_id INTEGER NOT NULL,
 payload TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'ready',error TEXT,created_at TEXT NOT NULL,
 UNIQUE(rule_id,source_id,message_id));
"""


class Catalog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=3, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.create_function('casefold', 1, lambda v: str(v).casefold() if v is not None else '', deterministic=True)
        try:
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.execute('PRAGMA journal_mode=WAL')
            if self.db.execute('PRAGMA user_version').fetchone()[0] != 4:
                with FileLock(self.path.with_suffix('.schema.lock'), timeout=3):
                    self._initialize()
        except BaseException:
            self.db.close()
            raise

    def _initialize(self):
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > 4:
            raise ValueError('Catálogo criado por versão mais recente. Atualize o app.')
        if version == 4:
            return
        if version in (1, 2, 3):
            self.backup(str(self.path) + '.before-v4.bak')
        migration = 'ALTER TABLE processing_jobs ADD COLUMN allow_alerts INTEGER NOT NULL DEFAULT 0;\n' if version == 1 else ''
        self.db.executescript('BEGIN IMMEDIATE;\n' + migration + SCHEMA + '\nPRAGMA user_version=4;\nCOMMIT;')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
        except BaseException:
            self.db.rollback()
            raise
        else:
            self.db.commit()

    def sources(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM sources ORDER BY name,id')]

    def ensure_selected(self, groups):
        """Padrão inicial; nunca substitui uma preferência de coleta existente."""
        now = utc()
        with self.transaction():
            for group in groups:
                if not group['selected']:
                    continue
                created = self.db.execute('INSERT OR IGNORE INTO sources(id,name,enabled,capture_started_at,checkpoint) VALUES(?,?,1,?,?)',
                                          (group['id'], group['name'], now, now))
                if created.rowcount:
                    self.db.execute('INSERT INTO capture_intervals(source_id,started_at) VALUES(?,?)', (group['id'], now))
                    self.db.execute("INSERT INTO source_events(source_id,at,kind) VALUES(?,?,'start')", (group['id'], now))
        return self.sources()

    def set_source(self, source_id, name, enabled, *, now=None, resume=None, expected=None):
        if type(source_id) is not int or type(enabled) is not bool or not isinstance(name, str) or not name.strip():
            raise ValueError('Grupo ou seleção de arquivamento inválidos.')
        now = utc(now)
        with self.transaction():
            old = self.db.execute('SELECT * FROM sources WHERE id=?', (source_id,)).fetchone()
            if expected is not None and expected != (old['revision'] if old else 0):
                raise ValueError('Origem alterada em outra janela. Atualize antes de salvar.')
            if not old:
                self.db.execute('INSERT INTO sources(id,name,enabled,capture_started_at,checkpoint) VALUES(?,?,?,?,?)',
                                (source_id, name, enabled, now, now))
                if enabled:
                    self.db.execute('INSERT INTO capture_intervals(source_id,started_at) VALUES(?,?)', (source_id, now))
                    self.db.execute("INSERT INTO source_events(source_id,at,kind) VALUES(?,?,'start')", (source_id, now))
            else:
                if enabled and not old['enabled']:
                    if resume not in ('recover', 'now'):
                        raise ValueError('Escolha recuperar a pausa ou iniciar novo intervalo agora.')
                    self.db.execute('INSERT INTO source_events(source_id,at,kind) VALUES(?,?,?)', (source_id, now, resume))
                    if resume == 'recover':
                        interval = self.db.execute('SELECT id FROM capture_intervals WHERE source_id=? ORDER BY id DESC LIMIT 1', (source_id,)).fetchone()
                        if interval:
                            self.db.execute('UPDATE capture_intervals SET ended_at=NULL WHERE id=?', (interval['id'],))
                        else:
                            self.db.execute('INSERT INTO capture_intervals(source_id,started_at) VALUES(?,?)', (source_id, now))
                    else:
                        self.db.execute('INSERT INTO capture_intervals(source_id,started_at) VALUES(?,?)', (source_id, now))
                        self.db.execute('UPDATE sources SET checkpoint=? WHERE id=?', (now, source_id))
                if not enabled and old['enabled']:
                    self.db.execute('UPDATE capture_intervals SET ended_at=? WHERE source_id=? AND ended_at IS NULL', (now, source_id))
                    self.db.execute("INSERT INTO source_events(source_id,at,kind) VALUES(?,?,'pause')", (source_id, now))
                self.db.execute('UPDATE sources SET name=?,enabled=?,revision=revision+1 WHERE id=?', (name, enabled, source_id))
        return next(s for s in self.sources() if s['id'] == source_id)

    def _bundle(self, source_id):
        templates = [json.loads(r['payload']) for r in self.db.execute('''SELECT v.payload FROM templates t
            JOIN template_versions v ON v.template_id=t.id AND v.version=t.published
            WHERE t.source_id=? AND t.archived=0 ORDER BY t.id''', (source_id,))]
        links = self.db.execute("SELECT * FROM settings WHERE key='links'").fetchone()
        alerts = self.db.execute("SELECT * FROM settings WHERE key='alerts'").fetchone()
        return {'engine': ENGINE_VERSION, 'templates': templates, 'link_rules': json.loads(links['payload']), 'link_version': links['revision'],
                'alerts': json.loads(alerts['payload']), 'alert_version': alerts['revision']}

    def _enqueue(self, revision_id, bundle, allow_alerts=False):
        h = digest(bundle)
        self.db.execute('INSERT OR IGNORE INTO configurations VALUES(?,?)', (h, encode(bundle)))
        self.db.execute('INSERT OR IGNORE INTO processing_jobs(revision_id,config_hash,allow_alerts) VALUES(?,?,?)', (revision_id, h, allow_alerts))

    def capture(self, source_id, message_id, published_at, text, *, metadata=None, edited_at=None, is_edit=False, live=False):
        published_at, revision_at = utc(published_at), utc(edited_at or published_at)
        if not isinstance(text, str):
            raise ValueError('Texto inválido.')
        metadata = metadata or {}
        h = digest({'text': text, 'metadata': metadata})
        with self.transaction():
            source = self.db.execute('SELECT * FROM sources WHERE id=? AND enabled=1', (source_id,)).fetchone()
            if not source or published_at < source['capture_started_at']:
                return None
            allowed = self.db.execute('SELECT 1 FROM capture_intervals WHERE source_id=? AND started_at<=? AND (ended_at IS NULL OR ended_at>=?)',
                                      (source_id, published_at, published_at)).fetchone()
            if not allowed:
                return None
            if is_edit and not self.db.execute('SELECT 1 FROM message_revisions WHERE source_id=? AND message_id=?', (source_id, message_id)).fetchone():
                return None
            inserted = self.db.execute('''INSERT OR IGNORE INTO message_revisions(source_id,message_id,published_at,revision_at,captured_at,text,metadata,hash)
                VALUES(?,?,?,?,?,?,?,?)''', (source_id, message_id, published_at, revision_at, utc(), text, encode(metadata), h))
            row = self.db.execute('SELECT id FROM message_revisions WHERE source_id=? AND message_id=? AND revision_at=? AND hash=?',
                                  (source_id, message_id, revision_at, h)).fetchone()
            if inserted.rowcount:
                self._enqueue(row['id'], self._bundle(source_id), allow_alerts=live and not is_edit)
            return row['id']

    def capture_event(self, event, is_edit=False, live=True):
        m = event.message
        text = m.message or ''
        entities, links, buttons = [], [], []
        for entity in (getattr(m, 'entities', None) or []):
            item = {'type': type(entity).__name__, 'offset': entity.offset, 'length': entity.length}
            # Telegram offsets são unidades UTF-16, não índices Python.
            encoded = text.encode('utf-16-le')
            start = len(encoded[:entity.offset * 2].decode('utf-16-le', errors='replace'))
            visible = encoded[entity.offset * 2:(entity.offset + entity.length) * 2].decode('utf-16-le', errors='replace')
            url = getattr(entity, 'url', None)
            if url or type(entity).__name__ == 'MessageEntityUrl':
                url = url or visible
                item['url'] = url
                links.append({'url': url, 'start': start, 'origin': 'entity'})
            entities.append(item)
        markup = getattr(m, 'reply_markup', None)
        for row in (getattr(markup, 'rows', None) or []):
            for button in row.buttons:
                url = getattr(button, 'url', None)
                if url:
                    buttons.append({'text': getattr(button, 'text', ''), 'url': url})
                    links.append({'url': url, 'origin': 'button'})
        media = getattr(m, 'media', None)
        metadata = {'entities': entities, 'links': links, 'buttons': buttons, 'media_type': type(media).__name__ if media else None}
        return self.capture(event.chat_id, m.id, m.date, text, metadata=metadata,
                            edited_at=getattr(m, 'edit_date', None), is_edit=is_edit, live=live)

    def mark_degraded(self, source_id, error):
        self.db.execute('UPDATE sources SET degraded=? WHERE id=?', (error, source_id))

    def checkpoint(self, source_id, completed_until):
        self.db.execute('UPDATE sources SET checkpoint=MAX(COALESCE(checkpoint,capture_started_at),?),degraded=NULL WHERE id=?',
                        (utc(completed_until), source_id))

    def templates(self):
        return [{**dict(r), 'draft': json.loads(r['draft'])} for r in self.db.execute('SELECT * FROM templates ORDER BY id')]

    def fields(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM field_definitions ORDER BY name,id')]

    def save_draft(self, template, expected):
        validate_template(template)
        with self.transaction():
            old = self.db.execute('SELECT * FROM templates WHERE id=?', (template['id'],)).fetchone()
            if expected != (old['revision'] if old else 0):
                raise ValueError('Modelo alterado em outra janela. Atualize antes de salvar.')
            if old and old['source_id'] != template['source_id']:
                raise ValueError('Grupo do modelo é imutável. Crie outro modelo.')
            count = self.db.execute('SELECT COUNT(*) FROM templates WHERE source_id=?', (template['source_id'],)).fetchone()[0]
            if not old and count >= 50:
                raise ValueError('Limite de 50 modelos por grupo.')
            rev = expected + 1
            self.db.execute('''INSERT INTO templates(id,source_id,revision,draft) VALUES(?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,draft=excluded.draft''',
                (template['id'], template['source_id'], rev, encode(template)))
        return {'id': template['id'], 'revision': rev}

    def publish(self, template_id, expected):
        with self.transaction():
            row = self.db.execute('SELECT * FROM templates WHERE id=?', (template_id,)).fetchone()
            if not row or row['revision'] != expected:
                raise ValueError('Modelo alterado. Atualize antes de publicar.')
            t = json.loads(row['draft'])
            validate_template(t)
            version = self.db.execute('SELECT COALESCE(MAX(version),0)+1 FROM template_versions WHERE template_id=?', (template_id,)).fetchone()[0]
            t['version'] = version
            for f in t['fields']:
                old = self.db.execute('SELECT * FROM field_definitions WHERE id=?', (f['field_id'],)).fetchone()
                if old and old['type'] != f['type']:
                    raise ValueError('Tipo de campo existente é imutável. Crie outro campo.')
                self.db.execute('INSERT INTO field_definitions VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',
                                (f['field_id'], f['name'], f['type']))
            self.db.execute('INSERT INTO template_versions VALUES(?,?,?,?)', (template_id, version, encode(t), utc()))
            self.db.execute('UPDATE templates SET published=?,revision=revision+1,archived=0 WHERE id=?', (version, template_id))
            bundle = self._bundle(row['source_id'])
            # Publicação só agenda pendências; resultados concluídos exigem reprocessamento.
            for r in self.db.execute('SELECT revision_id FROM review_items WHERE source_id=?', (row['source_id'],)).fetchall():
                self._enqueue(r['revision_id'], bundle)
        return {'version': version, 'revision': expected + 1}

    def links(self):
        r = self.db.execute("SELECT * FROM settings WHERE key='links'").fetchone()
        return {'rules': json.loads(r['payload']), 'revision': r['revision']}

    def save_links(self, rules, expected):
        validate_link_rules(rules)
        with self.transaction():
            cur = self.db.execute("UPDATE settings SET payload=?,revision=revision+1 WHERE key='links' AND revision=?", (encode(rules), expected))
            if not cur.rowcount:
                raise ValueError('Regras de lojas alteradas. Atualize antes de salvar.')
        return self.links()

    @staticmethod
    def _latest(alias='m'):
        return f'''NOT EXISTS(SELECT 1 FROM message_revisions newer WHERE newer.source_id={alias}.source_id
            AND newer.message_id={alias}.message_id AND (newer.revision_at>{alias}.revision_at
            OR (newer.revision_at={alias}.revision_at AND newer.id>{alias}.id)))'''

    def message(self, revision_id):
        row = self.db.execute('SELECT m.*,s.name AS source_name FROM message_revisions m JOIN sources s ON s.id=m.source_id WHERE m.id=?', (revision_id,)).fetchone()
        if not row:
            raise ValueError('Mensagem não encontrada.')
        result = dict(row)
        result['metadata'] = json.loads(result['metadata'])
        result['revisions'] = [dict(r) for r in self.db.execute('SELECT id,revision_at FROM message_revisions WHERE source_id=? AND message_id=? ORDER BY revision_at DESC,id DESC LIMIT 50', (row['source_id'], row['message_id']))]
        # Detalhes completos de uma execução por consulta evitam payload crescente.
        result['runs'] = [dict(r) for r in self.db.execute('SELECT id,state,created_at,result FROM extraction_runs WHERE revision_id=? ORDER BY id DESC LIMIT 1', (revision_id,))]
        result['run_history'] = [dict(r) for r in self.db.execute('SELECT id,state,created_at FROM extraction_runs WHERE revision_id=? ORDER BY id DESC LIMIT 50', (revision_id,))]
        return result

    def messages(self, source_id=None, offset=0, limit=25):
        offset, limit = max(0, int(offset)), min(100, max(1, int(limit)))
        where, args = self._latest(), []
        if source_id is not None:
            where += ' AND m.source_id=?'
            args.append(source_id)
        total = self.db.execute('SELECT COUNT(*) FROM message_revisions m WHERE ' + where, args).fetchone()[0]
        rows = self.db.execute('''SELECT m.id,m.source_id,m.message_id,m.published_at,m.revision_at,m.text,s.name AS source_name,
            (SELECT state FROM extraction_runs WHERE revision_id=m.id ORDER BY id DESC LIMIT 1) AS state
            FROM message_revisions m JOIN sources s ON s.id=m.source_id WHERE ''' + where + ' ORDER BY m.published_at DESC,m.id DESC LIMIT ? OFFSET ?', args + [limit, offset])
        return {'items': [dict(r) for r in rows], 'total': total, 'offset': offset, 'limit': limit}

    def reviews(self, offset=0, limit=25):
        groups = self.db.execute('''SELECT r.source_id,s.name AS source_name,r.reason,r.signature,COUNT(*) AS count,
            MIN(r.created_at) AS first_at,MAX(r.created_at) AS last_at,MIN(r.revision_id) AS example_id
            FROM review_items r JOIN sources s ON s.id=r.source_id
            GROUP BY r.source_id,r.reason,r.signature ORDER BY last_at DESC,r.source_id,r.signature''').fetchall()
        return {'items': [dict(r) for r in groups[max(0, int(offset)):max(0, int(offset)) + min(100, max(1, int(limit)))]], 'total': len(groups)}

    def process_batch(self, limit=25):
        processed = 0
        with FileLock(self.path.with_suffix('.worker.lock')):
            for _ in range(min(25, max(1, int(limit)))):
                # Mantém claim e projeção na mesma transação. Crash faz rollback.
                with self.transaction():
                    job = self.db.execute('SELECT * FROM processing_jobs WHERE state=\'pending\' ORDER BY id LIMIT 1').fetchone()
                    if not job:
                        break
                    m = self.db.execute('SELECT * FROM message_revisions WHERE id=?', (job['revision_id'],)).fetchone()
                    bundle = json.loads(self.db.execute('SELECT payload FROM configurations WHERE hash=?', (job['config_hash'],)).fetchone()[0])
                    result = extract(m['text'], bundle['templates'], json.loads(m['metadata']).get('links'), bundle['link_rules'])
                    run_id = self.db.execute('INSERT INTO extraction_runs(job_id,revision_id,config_hash,state,result,created_at) VALUES(?,?,?,?,?,?)',
                        (job['id'], m['id'], job['config_hash'], result['state'], encode(result), utc())).lastrowid
                    latest = self.db.execute('SELECT id FROM message_revisions m WHERE id=? AND ' + self._latest(), (m['id'],)).fetchone()
                    # Trabalho de configuração antiga não substitui projeção mais nova.
                    newer_job = self.db.execute('SELECT 1 FROM processing_jobs WHERE revision_id=? AND id>?', (m['id'], job['id'])).fetchone()
                    if latest and not newer_job:
                        self.db.execute('DELETE FROM offer_records WHERE source_id=? AND message_id=?', (m['source_id'], m['message_id']))
                        self.db.execute('DELETE FROM review_items WHERE revision_id IN (SELECT id FROM message_revisions WHERE source_id=? AND message_id=?)', (m['source_id'], m['message_id']))
                        for offer in result['offers']:
                            oid = self.db.execute('INSERT INTO offer_records(source_id,message_id,revision_id,run_id,block,published_at,payload) VALUES(?,?,?,?,?,?,?)',
                                (m['source_id'], m['message_id'], m['id'], run_id, offer['block'], m['published_at'], encode(offer))).lastrowid
                            for fid, val in offer['values'].items():
                                values = val['value'] if isinstance(val['value'], list) else [val['value']]
                                for value in values:
                                    numeric = value if val['type'] in ('money', 'number') and isinstance(value, (int, float)) else None
                                    self.db.execute('INSERT INTO offer_values VALUES(?,?,?,?,?,?)',
                                        (oid, fid, val.get('option'), encode(value) if isinstance(value, dict) else value, numeric, val['presence']))
                        if result['state'] == 'done' and job['allow_alerts']:
                            for rule in bundle.get('alerts', []):
                                if not rule['enabled'] or rule['source_id'] != m['source_id'] or m['published_at'] < rule['activated_at']:
                                    continue
                                matched = self.search({**rule['filters'], 'source_id': m['source_id'], 'revision_id': m['id']}, limit=1)
                                if matched['total']:
                                    self.db.execute('''INSERT OR IGNORE INTO structured_deliveries(rule_id,rule_name,rule_hash,source_id,message_id,revision_id,payload,created_at)
                                        VALUES(?,?,?,?,?,?,?,?)''', (rule['id'], rule['name'], digest(rule), m['source_id'], m['message_id'], m['id'], encode(matched['items'][0]['payload']), utc()))
                        if result['state'] not in ('done', 'no_text', 'ignored'):
                            structure = re.sub(r'https?://\S+|\d+[\d.,]*', '#', m['text'].casefold())
                            structure = '\n'.join(line.split(':')[0] if ':' in line else '#' for line in structure.splitlines())
                            self.db.execute('INSERT INTO review_items VALUES(?,?,?,?,?)', (m['id'], m['source_id'], result['state'], digest(structure), utc()))
                    self.db.execute("UPDATE processing_jobs SET state='done',attempts=attempts+1,error=NULL WHERE id=?", (job['id'],))
                    processed += 1
        return {'processed': processed, **self.status()}

    def search(self, filters=None, offset=0, limit=25):
        f, args, conditions = filters or {}, [], []
        if f.get('revision_id') is not None:
            conditions.append('o.revision_id=?')
            args.append(f['revision_id'])
        for key, column in [('source_id', 'o.source_id'), ('from', 'o.published_at'), ('to', 'o.published_at')]:
            if f.get(key) not in (None, ''):
                conditions.append(column + ('>=?' if key == 'from' else '<=?' if key == 'to' else '=?'))
                args.append(f[key])
        # Cada filtro usa o mesmo offer_id e, opcionalmente, a mesma opção explícita.
        value_filters = f.get('values', [])
        if f.get('field_id'):
            value_filters = [*value_filters, f]
        if len(value_filters) > 20:
            raise ValueError('Limite de 20 filtros.')
        for v in value_filters:
            clause, params = ['v.field_id=?'], [v['field_id']]
            for key, operator in [('min', '>='), ('max', '<=')]:
                if v.get(key) not in (None, ''):
                    clause.append('v.value_number' + operator + '?')
                    params.append(float(v[key]))
            if v.get('text'):
                clause.append("casefold(v.value_text) LIKE casefold(?) ESCAPE '\\'")
                params.append('%' + str(v['text']).replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
            for key, column in [('presence', 'v.presence'), ('option', 'v.option_id')]:
                if v.get(key):
                    clause.append(column + '=?')
                    params.append(v[key])
            conditions.append('o.id IN (SELECT v.offer_id FROM offer_values v WHERE ' + ' AND '.join(clause) + ')')
            args.extend(params)
        if f.get('query'):
            conditions.append("o.id IN (SELECT v.offer_id FROM offer_values v WHERE instr(casefold(v.value_text),casefold(?))>0)")
            args.append(f['query'])
        if f.get('store'):
            conditions.append("o.id IN (SELECT v.offer_id FROM offer_values v WHERE CASE WHEN json_valid(v.value_text) THEN json_extract(v.value_text,'$.store') END=?)")
            args.append(f['store'])
        where = ' AND '.join(conditions) or '1'
        total = self.db.execute('SELECT COUNT(*) FROM offer_records o WHERE ' + where, args).fetchone()[0]
        offset, limit = max(0, int(offset)), min(100, max(1, int(limit)))
        rows = self.db.execute('SELECT o.*,s.name AS source_name FROM offer_records o JOIN sources s ON s.id=o.source_id WHERE ' + where + ' ORDER BY o.published_at DESC,o.id DESC LIMIT ? OFFSET ?', args + [limit, offset])
        definitions = {f['id']: f['name'] for f in self.fields()}
        items = []
        for r in rows:
            payload = json.loads(r['payload'])
            for fid, value in payload['values'].items():
                value['name'] = definitions.get(fid, value['name'])
            items.append({**dict(r), 'payload': payload})
        return {'items': items, 'total': total, 'offset': offset, 'limit': limit}

    def reprocess_preview(self, scope):
        if not isinstance(scope, dict) or type(scope.get('source_id')) is not int:
            raise ValueError('Escolha um grupo para reprocessar.')
        where, args = ['m.source_id=?', self._latest()], [scope['source_id']]
        for key, op in [('from', '>='), ('to', '<=')]:
            if scope.get(key):
                where.append('m.published_at' + op + '?')
                args.append(utc(scope[key]))
        ids = [r[0] for r in self.db.execute('SELECT id FROM message_revisions m WHERE ' + ' AND '.join(where), args)]
        bundle = self._bundle(scope['source_id'])
        token = str(uuid.uuid4())
        self.db.execute('INSERT INTO reprocess_requests(token,payload,created_at) VALUES(?,?,?)', (token, encode({'ids': ids, 'bundle': bundle}), utc()))
        return {'token': token, 'count': len(ids), 'scope': scope}

    def reprocess_confirm(self, token):
        with self.transaction():
            r = self.db.execute("SELECT * FROM reprocess_requests WHERE token=? AND state='preview'", (token,)).fetchone()
            if not r:
                raise ValueError('Prévia inexistente ou já confirmada.')
            data = json.loads(r['payload'])
            for rid in data['ids']:
                self._enqueue(rid, data['bundle'])
                self.db.execute("UPDATE processing_jobs SET state='pending',allow_alerts=0 WHERE revision_id=? AND config_hash=?", (rid, digest(data['bundle'])))
            self.db.execute("UPDATE reprocess_requests SET state='queued' WHERE token=?", (token,))
        return {'queued': len(data['ids'])}

    def status(self):
        counts = {key: self.db.execute(sql).fetchone()[0] for key, sql in {
            'messages': 'SELECT COUNT(*) FROM message_revisions m WHERE ' + self._latest(),
            'revisions': 'SELECT COUNT(*) FROM message_revisions', 'pending': "SELECT COUNT(*) FROM processing_jobs WHERE state='pending'",
            'runs': 'SELECT COUNT(*) FROM extraction_runs', 'offers': 'SELECT COUNT(*) FROM offer_records',
            'reviews': 'SELECT COUNT(*) FROM review_items',
            'delivery_failed': "SELECT COUNT(*) FROM structured_deliveries WHERE state='failed'",
            'delivery_uncertain': "SELECT COUNT(*) FROM structured_deliveries WHERE state='claimed'"}.items()}
        return {**counts, 'bytes': sum(p.stat().st_size for p in [self.path, Path(str(self.path) + '-wal')] if p.exists()), 'sources': self.sources()}

    def backup(self, destination):
        with sqlite3.connect(destination) as target:
            self.db.backup(target)

    def alert_rules(self):
        r = self.db.execute("SELECT * FROM settings WHERE key='alerts'").fetchone()
        return {'rules': json.loads(r['payload']), 'revision': r['revision']}

    def save_alert_rules(self, rules, expected, now=None):
        now = utc(now)
        if not isinstance(rules, list) or len(rules) > 100:
            raise ValueError('Lista de alertas estruturados inválida.')
        fields = {f['id']: f for f in self.fields()}
        ids, clean = set(), []
        with self.transaction():
            old = self.alert_rules()
            if old['revision'] != expected:
                raise ValueError('Alertas alterados. Atualize antes de salvar.')
            for r in rules:
                if not isinstance(r, dict) or not isinstance(r.get('id'), str) or not r['id'] or r['id'] in ids:
                    raise ValueError('Identidade de alerta inválida ou duplicada.')
                if not isinstance(r.get('name'), str) or not r['name'].strip() or type(r.get('enabled')) is not bool or type(r.get('source_id')) is not int:
                    raise ValueError('Informe nome, grupo e estado do alerta.')
                ids.add(r['id'])
                filters = r.get('filters')
                if not isinstance(filters, dict) or not isinstance(filters.get('values'), list) or not 1 <= len(filters['values']) <= 20:
                    raise ValueError('Alerta precisa de 1 a 20 filtros de campos.')
                for f in filters['values']:
                    if not isinstance(f, dict) or f.get('field_id') not in fields:
                        raise ValueError('Filtro referencia campo inexistente. Publique um modelo primeiro.')
                    for key in ('min', 'max'):
                        value = f.get(key)
                        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or fields[f['field_id']]['type'] not in ('money', 'number')):
                            raise ValueError('Limite numérico incompatível com campo.')
                    if f.get('min') is not None and f.get('max') is not None and f['min'] > f['max']:
                        raise ValueError('Mínimo não pode exceder máximo.')
                    if not any(f.get(k) not in (None, '') for k in ('min', 'max', 'text', 'presence')):
                        raise ValueError('Informe ao menos uma condição para cada filtro.')
                value = {k: r[k] for k in ('id', 'name', 'enabled', 'source_id', 'filters')}
                previous = next((p for p in old['rules'] if p['id'] == r['id']), None)
                same = previous and all(previous[k] == v for k, v in value.items())
                value['activated_at'] = previous['activated_at'] if same else now
                clean.append(value)
            self.db.execute("UPDATE settings SET revision=revision+1,payload=? WHERE key='alerts'", (encode(clean),))
        return self.alert_rules()

    def claim_alert(self, source_ids=None):
        with self.transaction():
            current = {r['id']: r for r in self.alert_rules()['rules'] if r['enabled']}
            for row in self.db.execute("SELECT * FROM structured_deliveries WHERE state='ready' ORDER BY id").fetchall():
                if source_ids is not None and row['source_id'] not in source_ids:
                    continue
                rule = current.get(row['rule_id'])
                latest = self.db.execute('SELECT 1 FROM message_revisions m WHERE m.id=? AND ' + self._latest(), (row['revision_id'],)).fetchone()
                source = self.db.execute('SELECT enabled FROM sources WHERE id=?', (row['source_id'],)).fetchone()
                if not source or not source['enabled'] or not latest or not rule or digest(rule) != row['rule_hash']:
                    self.db.execute("UPDATE structured_deliveries SET state='suppressed' WHERE id=?", (row['id'],))
                    continue
                self.db.execute("UPDATE structured_deliveries SET state='claimed' WHERE id=?", (row['id'],))
                return {**dict(row), 'payload': json.loads(row['payload'])}
        return None

    def finish_alert(self, delivery_id, state, error=None):
        if state not in ('sent', 'failed', 'dry_run'):
            raise ValueError('Desfecho inválido.')
        self.db.execute("UPDATE structured_deliveries SET state=?,error=? WHERE id=? AND state='claimed'", (state, error, delivery_id))
