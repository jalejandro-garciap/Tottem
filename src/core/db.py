"""
TOTTEM POS · Database Layer
Supports SQLCipher (encrypted) with fallback to plain sqlite3 for development.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime

# ─── Conditional import: prefer sqlcipher3, fall back to sqlite3 ─────────────
try:
    import sqlcipher3 as sqlite3  # type: ignore[import-untyped]
    _HAS_SQLCIPHER = True
except ImportError:
    try:
        from pysqlcipher3 import dbapi2 as sqlite3  # type: ignore[no-redef]
        _HAS_SQLCIPHER = True
    except ImportError:
        import sqlite3  # type: ignore[no-redef]
        _HAS_SQLCIPHER = False

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data.db"
MIGRATIONS_DIR = ROOT / "migrations"

SCHEMA_TABLE = "schema_migrations"


def _apply_key(conn) -> None:
    """Apply the encryption key derived from the Pi's hardware serial."""
    if not _HAS_SQLCIPHER:
        return
    try:
        from core.hwid import get_db_key
        key = get_db_key()
        conn.execute(f"PRAGMA key = '{key}'")
    except Exception as exc:
        print(f"[db] Warning: Could not apply DB key: {exc}")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    _apply_key(conn)
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


def migrate_plain_to_encrypted() -> bool:
    """Migrate an existing plain-text DB to an encrypted one.

    This is a one-time operation run during the first boot after
    enabling SQLCipher. It:
      1. Reads all data from the existing plain DB
      2. Creates a new encrypted DB
      3. Replaces the old file

    Returns True if migration was performed, False if skipped/unnecessary.
    """
    if not _HAS_SQLCIPHER:
        return False

    if not DB_PATH.exists():
        return False

    # Check if the DB is already encrypted by trying to open it with the key
    try:
        conn = sqlite3.connect(str(DB_PATH))
        _apply_key(conn)
        conn.execute("SELECT count(*) FROM sqlite_master")
        conn.close()
        # Already encrypted or key works — no migration needed
        return False
    except Exception:
        pass

    # The DB exists but can't be read with the key — it's likely plain-text
    print("[db] Migrating plain database to encrypted...")

    plain_path = DB_PATH
    encrypted_path = DB_PATH.with_suffix(".db.enc")

    try:
        from core.hwid import get_db_key
        key = get_db_key()

        # Open the plain DB without encryption
        import sqlite3 as plain_sqlite3
        plain_conn = plain_sqlite3.connect(str(plain_path))

        # Create the encrypted DB
        enc_conn = sqlite3.connect(str(encrypted_path))
        enc_conn.execute(f"PRAGMA key = '{key}'")

        # Copy all data using the iterdump approach
        for line in plain_conn.iterdump():
            enc_conn.execute(line)

        enc_conn.commit()
        enc_conn.close()
        plain_conn.close()

        # Replace the old DB with the encrypted one
        backup_path = plain_path.with_suffix(".db.plain.bak")
        plain_path.rename(backup_path)
        encrypted_path.rename(plain_path)

        # Remove WAL/SHM files from old DB
        for suffix in ("-wal", "-shm"):
            p = Path(str(plain_path) + suffix)
            if p.exists():
                p.unlink()

        print("[db] Migration complete. Plain backup saved as data.db.plain.bak")
        return True

    except Exception as exc:
        print(f"[db] Migration failed: {exc}")
        # Clean up partial encrypted file
        if encrypted_path.exists():
            encrypted_path.unlink()
        return False


def factory_reset() -> bool:
    """Delete the database file and recreate it from migrations.

    Returns True on success, False on error.
    """
    try:
        # Remove existing database files (WAL, SHM, main, backup)
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(DB_PATH) + suffix)
            if p.exists():
                p.unlink()

        # Recreate from migrations
        ensure_migrated()
        return True
    except Exception as exc:
        print(f"[factory_reset] Error: {exc}")
        return False
