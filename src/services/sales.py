from __future__ import annotations
import sqlite3
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data.db"

def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


@dataclass
class CartItem:
    product_id: Optional[int]
    name: str
    price: int   # cents
    qty: float
    unit: str    # 'pz', 'kg', etc.


def cents_to_money(cents: int) -> str:
    return f"{cents/100:.2f}"


def money_to_cents(text: str | float | int) -> int:
    """
    Robust converter: '12.34' -> 1234; 12 -> 1200; 0.5 -> 50; handles commas/spaces.
    """
    if isinstance(text, int):
        return text
    if isinstance(text, float):
        return int(round(text * 100))
    s = str(text or "").strip().replace(",", ".")
    try:
        val = float(s)
    except Exception:
        val = 0.0
    return int(round(val * 100))


# ---------- Products ----------
def get_active_products() -> List[Dict[str, Any]]:
    with connect() as c:
        rows = c.execute("""
            SELECT id, name, price, active,
                   COALESCE(unit,'pz') AS unit,
                   COALESCE(allow_decimal,0) AS allow_decimal,
                   COALESCE(category,'General') AS category,
                   COALESCE(icon,'') AS icon
            FROM product
            WHERE active = 1
            ORDER BY name COLLATE NOCASE
        """).fetchall()
    return [dict(r) for r in rows]


def list_products(q: str = "", include_inactive: bool = True) -> List[Dict[str, Any]]:
    sql = """
      SELECT id, name, price, active,
             COALESCE(unit,'pz') AS unit,
             COALESCE(allow_decimal,0) AS allow_decimal,
             COALESCE(category,'General') AS category,
             COALESCE(icon,'') AS icon
      FROM product
      WHERE 1=1
    """
    args: list[Any] = []
    if not include_inactive:
        sql += " AND active = 1"
    if q:
        sql += " AND name LIKE ?"
        args.append(f"%{q}%")
    sql += " ORDER BY active DESC, name COLLATE NOCASE"
    with connect() as c:
        rows = c.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def list_products_by_category(q: str = "", category: str | None = None, include_inactive: bool = True) -> List[Dict[str, Any]]:
    sql = """
      SELECT id, name, price, active,
             COALESCE(unit,'pz') AS unit,
             COALESCE(allow_decimal,0) AS allow_decimal,
             COALESCE(category,'General') AS category,
             COALESCE(icon,'') AS icon
      FROM product
      WHERE 1=1
    """
    args: list[Any] = []
    if not include_inactive:
        sql += " AND active = 1"
    if q:
        sql += " AND name LIKE ?"
        args.append(f"%{q}%")
    if category and category != "_ALL_":
        sql += " AND COALESCE(category,'General') = ?"
        args.append(category)
    sql += " ORDER BY active DESC, name COLLATE NOCASE"
    with connect() as c:
        rows = c.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def get_categories() -> List[str]:
    with connect() as c:
        rows = c.execute("SELECT DISTINCT COALESCE(category,'General') AS c FROM product").fetchall()
    cats = sorted([r["c"] for r in rows if r["c"]], key=str.lower)
    return cats or ["General"]


def upsert_product(*,
                   product_id: Optional[int],
                   name: str,
                   price_cents: int,
                   unit: str,
                   allow_decimal: bool,
                   active: bool,
                   category: str,
                   icon: str = "") -> int:
    unit = (unit or "pz").strip()
    category = (category or "General").strip()
    icon = (icon or "").strip()
    allow_decimal_i = 1 if allow_decimal else 0
    active_i = 1 if active else 0
    with connect() as c:
        if product_id:
            c.execute("""
                UPDATE product
                   SET name=?, price=?, unit=?, allow_decimal=?, active=?, category=?, icon=?
                 WHERE id=?
            """, (name, price_cents, unit, allow_decimal_i, active_i, category, icon, product_id))
            return int(product_id)
        cur = c.execute("""
            INSERT INTO product(name, price, unit, allow_decimal, active, category, icon)
            VALUES(?,?,?,?,?,?,?)
        """, (name, price_cents, unit, allow_decimal_i, active_i, category, icon))
        return int(cur.lastrowid)


def delete_product(product_id: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM product WHERE id=?", (product_id,))


def get_product(product_id: int) -> Optional[Dict[str, Any]]:
    with connect() as c:
        r = c.execute("""
          SELECT id, name, price, active,
                 COALESCE(unit,'pz') AS unit,
                 COALESCE(allow_decimal,0) AS allow_decimal,
                 COALESCE(category,'General') AS category,
                 COALESCE(icon,'') AS icon
            FROM product WHERE id=?
        """, (product_id,)).fetchone()
    return dict(r) if r else None


# ---------- Tickets ----------
def save_ticket(
    items: List[CartItem], 
    shift_id: int | None = None,
    paid_cents: int = 0,
    change_cents: int = 0
) -> int:
    """Guardar ticket asociado a un turno.
    
    Args:
        items: Items del carrito
        shift_id: ID del turno activo. Si es None, intenta obtener turno actual.
        paid_cents: Cantidad pagada en centavos
        change_cents: Cambio devuelto en centavos
    
    Returns:
        ticket_id generado
    """
    if not items:
        raise ValueError("No hay items para guardar en el ticket")
    
    # Obtener shift_id si no se proporcionó
    if shift_id is None:
        from services.shifts import current_shift
        sh = current_shift()
        shift_id = sh["id"] if sh else None
    total_cents = int(round(sum(round(i.price * i.qty) for i in items)))
    with connect() as c:
        # CRÍTICO: Incluir shift_id para asociar venta con turno, y paid/change
        cur = c.execute("""
            INSERT INTO ticket(ts, total, shift_id, paid, change_amount) 
            VALUES(datetime('now'), ?, ?, ?, ?)
        """, (total_cents, shift_id, paid_cents, change_cents))
        tid = int(cur.lastrowid)
        for it in items:
            c.execute("""
                INSERT INTO ticket_item(ticket_id, product_id, name, price, quantity)
                VALUES(?,?,?,?,?)
            """, (tid, it.product_id, it.name, it.price, it.qty))
    return tid


def get_last_ticket_id() -> Optional[int]:
    with connect() as c:
        row = c.execute("SELECT id FROM ticket ORDER BY id DESC LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def get_ticket_items(ticket_id: int) -> List[CartItem]:
    with connect() as c:
        rows = c.execute("""
          SELECT product_id, name, price, quantity
            FROM ticket_item
           WHERE ticket_id=?
        """, (ticket_id,)).fetchall()
    items: List[CartItem] = []
    for r in rows:
        items.append(CartItem(
            product_id=r["product_id"],
            name=r["name"],
            price=r["price"],
            qty=float(r["quantity"]),
            unit="pz"  # ticket_item no guarda unidad; legacy
        ))
    return items


def list_tickets(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Lista paginada de tickets ordenados por fecha descendente.
    
    Args:
        limit: Número máximo de tickets a retornar
        offset: Offset para paginación
        
    Returns:
        Lista de diccionarios con información de tickets
    """
    with connect() as c:
        rows = c.execute("""
            SELECT 
                t.id,
                t.ts,
                t.total,
                t.shift_id,
                COALESCE(e.full_name, s.opened_by, '') as served_by
            FROM ticket t
            LEFT JOIN shift s ON t.shift_id = s.id
            LEFT JOIN employee e ON s.opened_by = e.emp_no
            ORDER BY t.id DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
    
    tickets = []
    for r in rows:
        tickets.append({
            "id": r["id"],
            "ts": r["ts"],
            "total": r["total"],
            "shift_id": r["shift_id"],
            "served_by": r["served_by"] or ""
        })
    return tickets


def search_tickets_by_id(ticket_id: int) -> Optional[Dict[str, Any]]:
    """Buscar ticket específico por ID.
    
    Args:
        ticket_id: ID del ticket a buscar
        
    Returns:
        Diccionario con información del ticket o None si no existe
    """
    with connect() as c:
        row = c.execute("""
            SELECT 
                t.id,
                t.ts,
                t.total,
                t.shift_id,
                COALESCE(t.paid, 0) as paid,
                COALESCE(t.change_amount, 0) as change_amount,
                COALESCE(e.full_name, s.opened_by, '') as served_by
            FROM ticket t
            LEFT JOIN shift s ON t.shift_id = s.id
            LEFT JOIN employee e ON s.opened_by = e.emp_no
            WHERE t.id = ?
        """, (ticket_id,)).fetchone()
    
    if not row:
        return None
    
    return {
        "id": row["id"],
        "ts": row["ts"],
        "total": row["total"],
        "shift_id": row["shift_id"],
        "paid": row["paid"],
        "change_amount": row["change_amount"],
        "served_by": row["served_by"] or ""
    }


def get_ticket_details(ticket_id: int) -> Optional[Dict[str, Any]]:
    """Obtener detalles completos de un ticket incluyendo items.
    
    Args:
        ticket_id: ID del ticket
        
    Returns:
        Diccionario con ticket completo (info + items) o None si no existe
    """
    ticket_info = search_tickets_by_id(ticket_id)
    if not ticket_info:
        return None
    
    items = get_ticket_items(ticket_id)
    
    return {
        "id": ticket_info["id"],
        "ts": ticket_info["ts"],
        "total": ticket_info["total"],
        "shift_id": ticket_info["shift_id"],
        "paid": ticket_info["paid"],
        "change_amount": ticket_info["change_amount"],
        "served_by": ticket_info["served_by"],
        "items": items
    }

