"""
TOTTEM POS · Presentations & Pricing Service (v1.3)

Manages product presentations (variants) and price resolution logic.
Each product has at least one presentation ("Única" by default).

Pricing rules per presentation (mutually exclusive):
  - Wholesale: activated when qty >= wholesale_min_qty
  - Discount:  auto-applied when discount_pct is set and wholesale doesn't apply
  - Normal:    base price when neither applies
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any, Tuple
from services.sales import connect


def list_presentations(product_id: int, include_inactive: bool = False) -> List[Dict[str, Any]]:
    """List all presentations for a product."""
    sql = """
        SELECT id, product_id, name, price, wholesale_price, wholesale_min_qty,
               discount_pct, active, sort_order
        FROM presentation
        WHERE product_id = ?
    """
    if not include_inactive:
        sql += " AND active = 1"
    sql += " ORDER BY sort_order, id"
    with connect() as c:
        rows = c.execute(sql, (int(product_id),)).fetchall()
    return [dict(r) for r in rows]


def get_presentation(presentation_id: int) -> Optional[Dict[str, Any]]:
    """Get a single presentation by ID."""
    with connect() as c:
        r = c.execute("""
            SELECT id, product_id, name, price, wholesale_price, wholesale_min_qty,
                   discount_pct, active, sort_order
            FROM presentation WHERE id = ?
        """, (int(presentation_id),)).fetchone()
    return dict(r) if r else None


def upsert_presentation(
    *,
    presentation_id: Optional[int] = None,
    product_id: int,
    name: str,
    price_cents: int,
    wholesale_price_cents: Optional[int] = None,
    wholesale_min_qty: Optional[float] = None,
    discount_pct: Optional[int] = None,
    active: bool = True,
    sort_order: int = 0,
) -> int:
    """Create or update a presentation."""
    name = (name or "Única").strip()
    active_i = 1 if active else 0
    # Normalize: if wholesale is set, ignore discount
    if wholesale_price_cents is not None and wholesale_min_qty is not None:
        discount_pct = None
    with connect() as c:
        if presentation_id:
            c.execute("""
                UPDATE presentation
                SET product_id=?, name=?, price=?, wholesale_price=?,
                    wholesale_min_qty=?, discount_pct=?, active=?, sort_order=?
                WHERE id=?
            """, (int(product_id), name, int(price_cents),
                  wholesale_price_cents, wholesale_min_qty,
                  discount_pct, active_i, int(sort_order),
                  int(presentation_id)))
            return int(presentation_id)
        cur = c.execute("""
            INSERT INTO presentation(product_id, name, price, wholesale_price,
                                     wholesale_min_qty, discount_pct, active, sort_order)
            VALUES(?,?,?,?,?,?,?,?)
        """, (int(product_id), name, int(price_cents),
              wholesale_price_cents, wholesale_min_qty,
              discount_pct, active_i, int(sort_order)))
        return int(cur.lastrowid)


def delete_presentation(presentation_id: int) -> None:
    """Delete a presentation."""
    with connect() as c:
        c.execute("DELETE FROM presentation WHERE id=?", (int(presentation_id),))


def ensure_default_presentation(product_id: int, price_cents: int) -> int:
    """Ensure a product has at least one 'Única' presentation.

    If the product already has presentations, does nothing.
    Returns the presentation ID of the default.
    """
    with connect() as c:
        existing = c.execute(
            "SELECT id FROM presentation WHERE product_id=? LIMIT 1",
            (int(product_id),)
        ).fetchone()
        if existing:
            return int(existing[0])
        cur = c.execute("""
            INSERT INTO presentation(product_id, name, price, active, sort_order)
            VALUES(?, 'Única', ?, 1, 0)
        """, (int(product_id), int(price_cents)))
        return int(cur.lastrowid)


def sync_default_price(product_id: int, price_cents: int) -> None:
    """Update the default 'Única' presentation price when the base product price changes.

    Only updates if the product has exactly one presentation named 'Única'.
    """
    with connect() as c:
        rows = c.execute(
            "SELECT id, name FROM presentation WHERE product_id=?",
            (int(product_id),)
        ).fetchall()
        if len(rows) == 1 and rows[0][1] == 'Única':
            c.execute(
                "UPDATE presentation SET price=? WHERE id=?",
                (int(price_cents), int(rows[0][0]))
            )


def count_presentations(product_id: int) -> int:
    """Count active presentations for a product."""
    with connect() as c:
        row = c.execute(
            "SELECT COUNT(*) FROM presentation WHERE product_id=? AND active=1",
            (int(product_id),)
        ).fetchone()
    return int(row[0]) if row else 0


def resolve_price(presentation_id: int, qty: float) -> Tuple[int, str]:
    """Calculate the effective price for a given presentation and quantity.

    Returns:
        (price_cents, price_type) where price_type is 'normal', 'wholesale', or 'discount'

    Rules (mutually exclusive, wholesale takes priority):
        1. If qty >= wholesale_min_qty and wholesale_price is set → wholesale
        2. If discount_pct is set (and wholesale doesn't apply) → discount
        3. Otherwise → normal price
    """
    pres = get_presentation(presentation_id)
    if not pres:
        return (0, 'normal')

    base_price = int(pres['price'])
    wholesale_price = pres.get('wholesale_price')
    wholesale_min = pres.get('wholesale_min_qty')
    discount = pres.get('discount_pct')

    # Rule 1: Wholesale
    if (wholesale_price is not None and wholesale_min is not None
            and qty >= wholesale_min):
        return (int(wholesale_price), 'wholesale')

    # Rule 2: Discount (auto-applied)
    if discount is not None and discount > 0:
        discounted = int(round(base_price * (1 - discount / 100.0)))
        return (discounted, 'discount')

    # Rule 3: Normal
    return (base_price, 'normal')


def resolve_price_from_data(
    price: int,
    wholesale_price: Optional[int],
    wholesale_min_qty: Optional[float],
    discount_pct: Optional[int],
    qty: float,
) -> Tuple[int, str]:
    """Calculate effective price from raw data (no DB lookup).

    Same rules as resolve_price() but works with in-memory data.
    """
    # Rule 1: Wholesale
    if (wholesale_price is not None and wholesale_min_qty is not None
            and qty >= wholesale_min_qty):
        return (int(wholesale_price), 'wholesale')

    # Rule 2: Discount
    if discount_pct is not None and discount_pct > 0:
        discounted = int(round(price * (1 - discount_pct / 100.0)))
        return (discounted, 'discount')

    # Rule 3: Normal
    return (int(price), 'normal')
