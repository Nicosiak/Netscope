"""SQLite session storage — thread-safe via a dedicated write-queue thread."""

from __future__ import annotations

import json
import os
import queue
import sqlite3
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from core.session import Session

_DB_PATH = os.path.join(os.path.expanduser("~"), ".netscope", "sessions.db")


def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)


_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    customer_name TEXT,
    customer_address TEXT,
    notes TEXT,
    tags TEXT,
    started_at REAL,
    ended_at REAL
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    kind TEXT,
    ts REAL,
    data TEXT
);
"""


class SessionStorage:
    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db_path = db_path
        self._q: "queue.Queue[Optional[Callable[[sqlite3.Connection], None]]]" = queue.Queue()
        self._ready = threading.Event()
        self._conn: Optional[sqlite3.Connection] = None
        self._closed = False
        self._t = threading.Thread(target=self._worker, daemon=True)
        self._t.start()
        self._ready.wait(timeout=5.0)

    def _worker(self) -> None:
        _ensure_dir()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=30.0)
        self._conn.executescript(_DDL)
        # WAL + NORMAL sync: fewer fsyncs during dev session logging; safe for local desktop use.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.commit()
        self._ready.set()
        try:
            while True:
                try:
                    fn = self._q.get(timeout=1.0)
                    if fn is None:
                        break
                    fn(self._conn)
                    self._conn.commit()
                except queue.Empty:
                    pass
                except Exception as e:
                    print(f"[storage] write error: {e}", file=sys.stderr)
        finally:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def _write(self, fn: Callable[[sqlite3.Connection], None]) -> None:
        self._q.put(fn)

    def save_session(self, session: Session) -> None:
        d = session.to_dict()

        def _w(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?)",
                (
                    d["id"],
                    d["customer_name"],
                    d["customer_address"],
                    d["notes"],
                    d["tags"],
                    d["started_at"],
                    d["ended_at"],
                ),
            )

        self._write(_w)

    def end_session(self, session_id: str) -> None:
        now = time.time()
        self._write(lambda conn: conn.execute("UPDATE sessions SET ended_at=? WHERE id=?", (now, session_id)))

    def update_notes(self, session_id: str, notes: str) -> None:
        self._write(lambda conn: conn.execute("UPDATE sessions SET notes=? WHERE id=?", (notes, session_id)))

    def update_tags(self, session_id: str, tags: List[str]) -> None:
        self._write(lambda conn: conn.execute("UPDATE sessions SET tags=? WHERE id=?", (",".join(tags), session_id)))

    def list_sessions(self) -> List[Session]:
        if not self._conn:
            return []
        cur = self._conn.execute(
            "SELECT id,customer_name,customer_address,notes,tags,started_at,ended_at "
            "FROM sessions ORDER BY started_at DESC LIMIT 100"
        )
        rows = cur.fetchall()
        keys = ["id", "customer_name", "customer_address", "notes", "tags", "started_at", "ended_at"]
        return [Session.from_dict(dict(zip(keys, r))) for r in rows]

    def save_snapshot(self, session_id: str, kind: str, data: Dict[str, Any]) -> None:
        ts = time.time()
        blob = json.dumps(data, default=str)
        # Guard local DB from accidental multi‑MB blobs (e.g. future UI changes).
        if len(blob) > 1_000_000:
            print("[storage] snapshot skipped: serialized payload exceeds 1MB", file=sys.stderr)
            return
        self._write(
            lambda conn: conn.execute(
                "INSERT INTO snapshots (session_id,kind,ts,data) VALUES (?,?,?,?)",
                (session_id, kind, ts, blob),
            )
        )

    def get_snapshots(self, session_id: str, kind: str) -> List[Dict[str, Any]]:
        if not self._conn:
            return []
        cur = self._conn.execute(
            "SELECT ts,data FROM snapshots WHERE session_id=? AND kind=? ORDER BY ts",
            (session_id, kind),
        )
        out: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            row_ts, blob = row[0], row[1]
            try:
                parsed = json.loads(blob) if isinstance(blob, str) else {}
            except json.JSONDecodeError:
                parsed = {}
            entry: Dict[str, Any] = {"ts": row_ts}
            entry.update(parsed)
            out.append(entry)
        return out

    def close(self) -> None:
        """Stop the writer thread and close the DB (idempotent)."""
        if self._closed:
            return
        self._closed = True
        self._q.put(None)
        if self._t.is_alive():
            self._t.join(timeout=30.0)


storage = SessionStorage()
