from __future__ import annotations
from pathlib import Path
import sqlite3
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data.db"
MIGRATIONS_DIR = ROOT / "migrations"

SCHEMA_TABLE = "schema_migrations"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def applied_migrations(conn: sqlite3.Connection) -> set[str]:
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {SCHEMA_TABLE}(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, applied_at TEXT NOT NULL)"
    )
    rows = conn.execute(f"SELECT name FROM {SCHEMA_TABLE}").fetchall()
    return {r[0] for r in rows}


def ensure_migrated():
    conn = connect()
    done = applied_migrations(conn)
    files = sorted(p for p in MIGRATIONS_DIR.glob("*.sql"))
    for p in files:
        name = p.name
        if name in done:
            continue
        sql = p.read_text(encoding="utf-8")
        with conn:
            conn.executescript(sql)
            conn.execute(
                f"INSERT INTO {SCHEMA_TABLE}(name, applied_at) VALUES(?, ?)",
                (name, datetime.utcnow().isoformat()),
            )
    conn.close()

