"""SQLite helpers: schema, connections and small query utilities.

The database stores:
  - datasets: metadata + the actual table data (as CSV text) + column type roles
  - history : an analysis/cleaning activity log
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "datalab.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    description    TEXT DEFAULT '',
    rows           INTEGER DEFAULT 0,
    cols           INTEGER DEFAULT 0,
    data           TEXT DEFAULT '',
    original_data  TEXT DEFAULT '',
    column_roles   TEXT DEFAULT '{}',
    original_roles TEXT DEFAULT '{}',
    created_at     TEXT,
    updated_at     TEXT
);

CREATE TABLE IF NOT EXISTS history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id   INTEGER,
    dataset_name TEXT DEFAULT '',
    action       TEXT NOT NULL,
    detail       TEXT DEFAULT '',
    created_at   TEXT NOT NULL
);

-- CleanFlow (DataLab 2.0) ------------------------------------------------

CREATE TABLE IF NOT EXISTS undo_stack (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL,
    data       TEXT NOT NULL,
    roles      TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipelines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT DEFAULT '',
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    steps       TEXT NOT NULL,
    created_at  TEXT,
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_id   INTEGER,
    pipeline_name TEXT DEFAULT '',
    dataset_id    INTEGER,
    dataset_name  TEXT DEFAULT '',
    result_id     INTEGER,
    result_name   TEXT DEFAULT '',
    status        TEXT DEFAULT 'ok',
    steps_total   INTEGER DEFAULT 0,
    steps_ok      INTEGER DEFAULT 0,
    rows_in       INTEGER DEFAULT 0,
    rows_out      INTEGER DEFAULT 0,
    detail        TEXT DEFAULT '',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cleanflow_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT DEFAULT '',
    dataset_id   INTEGER,
    dataset_name TEXT DEFAULT '',
    action       TEXT NOT NULL,
    ops          TEXT DEFAULT '[]',
    score_before REAL,
    score_after  REAL,
    rows_before  INTEGER,
    rows_after   INTEGER,
    summary      TEXT DEFAULT '',
    created_at   TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def get_conn():
    """Open a connection, commit on success, always close."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Additive migration (DataLab 2.0): optional session isolation column.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(datasets)").fetchall()}
        if "session_id" not in cols:
            conn.execute("ALTER TABLE datasets ADD COLUMN session_id TEXT DEFAULT ''")


def add_history(conn, dataset_id, dataset_name, action, detail="") -> None:
    conn.execute(
        "INSERT INTO history (dataset_id, dataset_name, action, detail, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (dataset_id, dataset_name or "", action, detail or "", now_iso()),
    )


def query_all(sql, params=()):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def query_one(sql, params=()):
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None
