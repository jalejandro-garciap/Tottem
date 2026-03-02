from __future__ import annotations
from core.db import sqlite3
from typing import Optional, Dict, Any, List
from services.sales import connect


def current_shift(conn: sqlite3.Connection | None = None) -> Optional[Dict[str, Any]]:
    own = False
    if conn is None:
        conn = connect()
        own = True
    cur = conn.cursor()
    cur.execute("""SELECT id, opened_at, opened_by, opening_cash, closed_at, closed_by, closing_cash
                   FROM shift WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1;""")
    row = cur.fetchone()
    if own:
        conn.close()
    if not row:
        return None
    return {
        "id": int(row[0]),
        "opened_at": row[1],
        "opened_by": row[2],
        "opening_cash": int(row[3] or 0),
        "closed_at": row[4],
        "closed_by": row[5],
        "closing_cash": int(row[6] or 0) if row[6] is not None else None,
    }


def open_shift(opened_by: str | None = None, opening_cash: int = 0) -> None:
    conn = connect()
    conn.execute("PRAGMA busy_timeout=5000")
    with conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM shift WHERE closed_at IS NULL LIMIT 1;")
        row = cur.fetchone()
        if row:
            return
        cur.execute(
            "INSERT INTO shift(opened_at, opened_by, opening_cash) "
            "VALUES(datetime('now'), ?, ?);",
            (opened_by or "", int(opening_cash)),
        )

def close_shift(closed_by: str | None = None, closing_cash: int = 0) -> None:
    conn = connect()
    conn.execute("PRAGMA busy_timeout=5000")
    with conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM shift WHERE closed_at IS NULL ORDER BY opened_at LIMIT 1;"
        )
        row = cur.fetchone()
        if not row:
            return
        sid = row["id"]
        cur.execute(
            "UPDATE shift "
            "SET closed_at = datetime('now'), closed_by = ?, closing_cash = ? "
            "WHERE id = ?;",
            (closed_by or "", int(closing_cash), sid),
        )

def close_current_shift() -> dict | None:
    conn = connect()
    conn.execute("PRAGMA busy_timeout=5000")
    with conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM shift WHERE closed_at IS NULL ORDER BY opened_at LIMIT 1;"
        )
        row = cur.fetchone()
        if not row:
            return None
        sid = row["id"]
        cur.execute(
            "UPDATE shift SET closed_at = datetime('now') WHERE id = ?;",
            (sid,),
        )
        cur.execute("SELECT * FROM shift WHERE id = ?;", (sid,))
        return dict(cur.fetchone())

def shift_totals(shift_id: int) -> dict:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), COALESCE(SUM(total),0) FROM ticket WHERE shift_id=?;", (int(shift_id),))
    row = cur.fetchone() or (0, 0)
    tickets = int(row[0] or 0)
    total = int(row[1] or 0)
    cur.execute("SELECT COUNT(*) FROM ticket_item WHERE ticket_id IN (SELECT id FROM ticket WHERE shift_id=?);",
                (int(shift_id),))
    items = int((cur.fetchone() or (0,))[0] or 0)
    # Desglose por método de pago
    cur.execute("""
        SELECT
            COALESCE(payment_method, 'cash') as pm,
            COUNT(*) as cnt,
            COALESCE(SUM(total), 0) as tot
        FROM ticket WHERE shift_id=?
        GROUP BY pm;
    """, (int(shift_id),))
    tickets_cash = 0
    tickets_card = 0
    total_cash = 0
    total_card = 0
    for r in cur.fetchall():
        pm = r[0] or "cash"
        if pm == "card":
            tickets_card = int(r[1] or 0)
            total_card = int(r[2] or 0)
        else:
            tickets_cash = int(r[1] or 0)
            total_cash = int(r[2] or 0)
    return {
        "tickets": tickets, "total": total, "items": items,
        "tickets_cash": tickets_cash, "total_cash": total_cash,
        "tickets_card": tickets_card, "total_card": total_card,
    }


def list_shifts(limit: int = 50) -> List[dict]:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, opened_at, closed_at FROM shift ORDER BY id DESC LIMIT ?;", (int(limit),))
    out = []
    for r in cur.fetchall():
        out.append({"id": int(r[0]), "opened_at": r[1], "closed_at": r[2]})
    return out


def list_shifts_since(days: int = 7) -> List[dict]:
    """Shifts opened in the last `days` days."""
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, opened_at, closed_at FROM shift WHERE date(opened_at) >= date('now', ?) ORDER BY id DESC;",
        (f"-{int(days)} days",),
    )
    out = []
    for r in cur.fetchall():
        out.append({"id": int(r[0]), "opened_at": r[1], "closed_at": r[2]})
    return out

