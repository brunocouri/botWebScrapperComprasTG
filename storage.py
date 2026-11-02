"""seen.db: deduplicação persistente + histórico best-effort. SPEC-PREÇOS F4.
Camada pequena e explícita (sem ORM/framework). Só stdlib (sqlite3).
F1/F2 não importam daqui; o fluxo externo (bot.py) coordena.
seen.db e session.session (Telethon) são bancos completamente independentes."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rules import decisive_to_json


class StorageError(Exception):
    """Falha de integridade do seen.db: explícita, nunca silenciosa."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    chat_id INTEGER NOT NULL,
    msg_id INTEGER NOT NULL,
    PRIMARY KEY (chat_id, msg_id)
);
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    msg_id INTEGER NOT NULL,
    rule_id TEXT,
    keyword TEXT,
    decisive_json TEXT,
    prices_json TEXT NOT NULL,
    sent INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL
);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SeenStore:
    """Uma conexão por processo, reutilizada. Métodos síncronos e curtos;
    nunca manter transação aberta durante IO de rede (Telegram)."""

    def __init__(self, path) -> None:
        self._path = Path(path)
        self._conn: sqlite3.Connection | None = None

    def open(self) -> "SeenStore":
        """Idempotente: CREATE TABLE IF NOT EXISTS. Erro -> StorageError."""
        try:
            self._conn = sqlite3.connect(str(self._path))
            self._conn.executescript(SCHEMA)
            columns = {row[1] for row in self._conn.execute('PRAGMA table_info(offers)')}
            if 'delivery_status' not in columns:
                self._conn.execute("ALTER TABLE offers ADD COLUMN delivery_status TEXT")
            if 'delivery_error' not in columns:
                self._conn.execute("ALTER TABLE offers ADD COLUMN delivery_error TEXT")
            self._conn.commit()
        except sqlite3.Error as e:
            self._conn = None
            raise StorageError(f"open {self._path}: {e}")
        return self

    def close(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                conn.commit()
            except sqlite3.Error:
                pass
            try:
                conn.close()
            except sqlite3.Error:
                pass

    def __enter__(self) -> "SeenStore":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise StorageError("store fechado")
        return self._conn

    def is_seen(self, chat_id: int, msg_id: int) -> bool:
        try:
            cur = self._db().execute(
                "SELECT 1 FROM seen WHERE chat_id = ? AND msg_id = ?", (chat_id, msg_id))
            return cur.fetchone() is not None
        except sqlite3.Error as e:
            raise StorageError(f"is_seen: {e}")

    def claim_message(self, chat_id: int, msg_id: int) -> bool:
        """Reivindicação atômica: só o INSERT decide (sem await no meio, sem
        intercalamento no event loop; concorrência real serializa na PRIMARY KEY).
        True = esta execução venceu; False = duplicata. Erro -> StorageError."""
        try:
            conn = self._db()
            cur = conn.execute(
                "INSERT OR IGNORE INTO seen (chat_id, msg_id) VALUES (?, ?)",
                (chat_id, msg_id))
            conn.commit()
            return cur.rowcount == 1
        except sqlite3.Error as e:
            raise StorageError(f"claim_message: {e}")

    def record_offer(self, chat_id: int, msg_id: int, rule_id, keyword: str,
                     decisive_json, prices_json: str, sent: int, reason,
                     delivery_status=None, delivery_error=None) -> None:
        try:
            conn = self._db()
            conn.execute(
                "INSERT INTO offers (chat_id, msg_id, rule_id, keyword, decisive_json,"
                " prices_json, sent, reason, created_at, delivery_status, delivery_error)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (chat_id, msg_id, rule_id, keyword, decisive_json, prices_json,
                 sent, reason, _utcnow(), delivery_status, delivery_error))
            conn.commit()
        except sqlite3.Error as e:
            raise StorageError(f"record_offer: {e}")

    def count_seen(self) -> int:
        try:
            cur = self._db().execute("SELECT COUNT(*) FROM seen")
            return cur.fetchone()[0]
        except sqlite3.Error as e:
            raise StorageError(f"count_seen: {e}")

    def fetch_offers(self) -> list:
        try:
            cur = self._db().execute(
                "SELECT chat_id, msg_id, rule_id, keyword, decisive_json, prices_json,"
                " sent, reason, created_at, delivery_status, delivery_error FROM offers ORDER BY id")
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        except sqlite3.Error as e:
            raise StorageError(f"fetch_offers: {e}")


def record_evaluation(store: SeenStore, chat_id: int, msg_id: int,
                      evaluation: dict, sent: bool, delivery_status=None, delivery_error=None) -> None:
    """Registra UMA avaliação no histórico. Best-effort: levanta StorageError
    e o chamador (handler) loga [AVISO] e segue — nunca bloqueia alerta."""
    dec = evaluation.get("decisive")
    store.record_offer(
        chat_id=chat_id, msg_id=msg_id,
        rule_id=evaluation.get("rule_id"), keyword=evaluation.get("keyword"),
        decisive_json=json.dumps(decisive_to_json(dec), ensure_ascii=False) if dec is not None else None,
        prices_json=json.dumps(evaluation.get("prices", []), ensure_ascii=False, sort_keys=True),
        sent=1 if sent else 0, reason=evaluation.get("reason"),
        delivery_status=delivery_status, delivery_error=delivery_error,
    )
