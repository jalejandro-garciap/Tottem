# -*- coding: utf-8 -*-
"""
TOTTEM POS · Pricing Rules Service
Resolves wholesale and discount pricing per product.
"""
from __future__ import annotations
from typing import Dict, Optional, Any, Tuple
from services.sales import connect


# ─── CRUD ────────────────────────────────────────────────────────────────────

def get_pricing_rule(product_id: int) -> Optional[Dict[str, Any]]:
    """Get the pricing rule for a product, or None."""
    with connect() as c:
        row = c.execute("""
            SELECT id, product_id, wholesale_price, wholesale_min_qty,
                   discount_pct, active, created_at, updated_at
            FROM pricing_rule
            WHERE product_id = ?
        """, (product_id,)).fetchone()
    if not row:
        return None
    return dict(row)


def upsert_pricing_rule(
    product_id: int,
    *,
    wholesale_price: int = 0,
    wholesale_min_qty: float = 0,
    discount_pct: float = 0,
    active: bool = True,
) -> int:
    """Create or update a pricing rule for a product.

    Enforces mutual exclusion: wholesale and discount cannot both be set.
    Returns the rule id.
    """
    # Mutual exclusion guard
    has_wholesale = wholesale_price > 0 and wholesale_min_qty > 0
    has_discount = discount_pct > 0
    if has_wholesale and has_discount:
        raise ValueError("Cannot have wholesale and discount active simultaneously")

    active_i = 1 if active else 0
    with connect() as c:
        existing = c.execute(
            "SELECT id FROM pricing_rule WHERE product_id = ?", (product_id,)
        ).fetchone()

        if existing:
            c.execute("""
                UPDATE pricing_rule
                SET wholesale_price = ?, wholesale_min_qty = ?,
                    discount_pct = ?, active = ?,
                    updated_at = datetime('now')
                WHERE product_id = ?
            """, (wholesale_price, wholesale_min_qty, discount_pct,
                  active_i, product_id))
            return int(existing["id"])
        else:
            cur = c.execute("""
                INSERT INTO pricing_rule
                    (product_id, wholesale_price, wholesale_min_qty,
                     discount_pct, active)
                VALUES (?, ?, ?, ?, ?)
            """, (product_id, wholesale_price, wholesale_min_qty,
                  discount_pct, active_i))
            return int(cur.lastrowid)


def delete_pricing_rule(product_id: int) -> None:
    """Remove the pricing rule for a product."""
    with connect() as c:
        c.execute("DELETE FROM pricing_rule WHERE product_id = ?", (product_id,))


# ─── Bulk load (for kiosk cache) ─────────────────────────────────────────────

def get_all_active_rules() -> Dict[int, Dict[str, Any]]:
    """Load all active pricing rules, keyed by product_id.

    Used by the kiosk to avoid per-product queries.
    """
    with connect() as c:
        rows = c.execute("""
            SELECT product_id, wholesale_price, wholesale_min_qty,
                   discount_pct
            FROM pricing_rule
            WHERE active = 1
        """).fetchall()
    result: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        result[int(r["product_id"])] = {
            "wholesale_price": int(r["wholesale_price"] or 0),
            "wholesale_min_qty": float(r["wholesale_min_qty"] or 0),
            "discount_pct": float(r["discount_pct"] or 0),
        }
    return result


# ─── Price resolution ─────────────────────────────────────────────────────────

def resolve_price(
    base_price_cents: int,
    qty: float,
    rule: Optional[Dict[str, Any]] = None,
) -> Tuple[int, str, Optional[int]]:
    """Determine the effective price for a product given its rule and quantity.

    Args:
        base_price_cents: The product's base price in cents.
        qty: Current quantity in the cart.
        rule: Active pricing rule dict (from get_all_active_rules),
              or None if no rule.

    Returns:
        (final_price_cents, price_type, original_price_cents)
        price_type is one of: "normal", "wholesale", "discount"
        original_price_cents is set only when price differs from base.
    """
    if not rule:
        return (base_price_cents, "normal", None)

    discount_pct = float(rule.get("discount_pct", 0) or 0)
    wholesale_price = int(rule.get("wholesale_price", 0) or 0)
    wholesale_min_qty = float(rule.get("wholesale_min_qty", 0) or 0)

    # Discount takes priority (auto-applied)
    if discount_pct > 0:
        discount_amt = round(base_price_cents * discount_pct / 100.0)
        final = max(0, base_price_cents - discount_amt)
        return (final, "discount", base_price_cents)

    # Wholesale: only if qty meets minimum
    if wholesale_price > 0 and wholesale_min_qty > 0:
        if qty >= wholesale_min_qty:
            return (wholesale_price, "wholesale", base_price_cents)

    return (base_price_cents, "normal", None)
