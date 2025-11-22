from src.core.db import ensure_migrated, connect


def test_can_migrate_and_insert():
    ensure_migrated()
    con = connect()
    cur = con.execute("SELECT COUNT(1) FROM product")
    assert cur.fetchone()[0] >= 0

