from __future__ import annotations
from core.db import sqlite3, connect as _db_connect
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data.db"

def connect() -> sqlite3.Connection:
    conn = _db_connect()  # handles PRAGMA key for SQLCipher
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


@dataclass
class CartItem:
    product_id: Optional[int]
    name: str
    price: int   # cents (effective/final price)
    qty: float
    unit: str    # 'pz', 'kg', etc.
    price_type: str = "normal"           # 'normal', 'wholesale', 'discount'
    original_price: Optional[int] = None  # base price before rule (cents)


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
                   COALESCE(icon,'') AS icon,
                   COALESCE(card_color,'') AS card_color
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
             COALESCE(icon,'') AS icon,
             COALESCE(card_color,'') AS card_color
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
             COALESCE(icon,'') AS icon,
             COALESCE(card_color,'') AS card_color
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
                   icon: str = "",
                   card_color: str = "") -> int:
    unit = (unit or "pz").strip()
    category = (category or "General").strip()
    icon = (icon or "").strip()
    card_color = (card_color or "").strip() or None  # Store NULL if empty
    allow_decimal_i = 1 if allow_decimal else 0
    active_i = 1 if active else 0
    with connect() as c:
        if product_id:
            c.execute("""
                UPDATE product
                   SET name=?, price=?, unit=?, allow_decimal=?, active=?, category=?, icon=?, card_color=?
                 WHERE id=?
            """, (name, price_cents, unit, allow_decimal_i, active_i, category, icon, card_color, product_id))
            return int(product_id)
        cur = c.execute("""
            INSERT INTO product(name, price, unit, allow_decimal, active, category, icon, card_color)
            VALUES(?,?,?,?,?,?,?,?)
        """, (name, price_cents, unit, allow_decimal_i, active_i, category, icon, card_color))
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
                 COALESCE(icon,'') AS icon,
                 COALESCE(card_color,'') AS card_color
            FROM product WHERE id=?
        """, (product_id,)).fetchone()
    return dict(r) if r else None


# ---------- Tickets ----------
def save_ticket(
    items: List[CartItem], 
    shift_id: int | None = None,
    paid_cents: int = 0,
    change_cents: int = 0,
    payment_method: str = "cash"
) -> int:
    """Guardar ticket asociado a un turno.
    
    Args:
        items: Items del carrito
        shift_id: ID del turno activo. Si es None, intenta obtener turno actual.
        paid_cents: Cantidad pagada en centavos
        change_cents: Cambio devuelto en centavos
        payment_method: Metodo de pago ('cash' o 'card')
    
    Returns:
        ticket_id generado
    """
    if not items:
        raise ValueError("No hay items para guardar en el ticket")
    
    if shift_id is None:
        from services.shifts import current_shift
        sh = current_shift()
        shift_id = sh["id"] if sh else None
    total_cents = int(round(sum(round(i.price * i.qty) for i in items)))
    with connect() as c:
        cur = c.execute("""
            INSERT INTO ticket(ts, total, shift_id, paid, change_amount, payment_method) 
            VALUES(datetime('now'), ?, ?, ?, ?, ?)
        """, (total_cents, shift_id, paid_cents, change_cents, payment_method))
        tid = int(cur.lastrowid)
        for it in items:
            c.execute("""
                INSERT INTO ticket_item(ticket_id, product_id, name, price, quantity, price_type, original_price)
                VALUES(?,?,?,?,?,?,?)
            """, (tid, it.product_id, it.name, it.price, it.qty,
                  it.price_type or "normal", it.original_price))
    return tid


def get_last_ticket_id() -> Optional[int]:
    with connect() as c:
        row = c.execute("SELECT id FROM ticket ORDER BY id DESC LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def get_ticket_items(ticket_id: int) -> List[CartItem]:
    with connect() as c:
        rows = c.execute("""
          SELECT product_id, name, price, quantity,
                 COALESCE(price_type, 'normal') AS price_type,
                 original_price
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
            unit="pz",  # ticket_item no guarda unidad; legacy
            price_type=r["price_type"] or "normal",
            original_price=int(r["original_price"]) if r["original_price"] is not None else None,
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
                COALESCE(e.full_name, s.opened_by, '') as served_by,
                COALESCE(t.payment_method, 'cash') as payment_method
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
            "served_by": r["served_by"] or "",
            "payment_method": r["payment_method"] or "cash"
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
                COALESCE(e.full_name, s.opened_by, '') as served_by,
                COALESCE(t.payment_method, 'cash') as payment_method
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
        "served_by": row["served_by"] or "",
        "payment_method": row["payment_method"] or "cash"
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
        "payment_method": ticket_info.get("payment_method", "cash"),
        "items": items
    }

