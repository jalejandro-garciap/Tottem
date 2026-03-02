from __future__ import annotations
from typing import List, Optional, Dict, Any
from services.sales import (
    money_to_cents,
    list_products as _list_products_core,
    list_products_by_category,
    get_product as _get_product_core,
    upsert_product as _upsert_core,
    delete_product as _delete_core,
    get_categories as _get_categories_core,
)

def list_products(q: str = "", include_inactive: bool = True, category: Optional[str] = None) -> List[Dict[str, Any]]:
    if category is not None:
        return list_products_by_category(q=q, category=category, include_inactive=include_inactive)
    return _list_products_core(q=q, include_inactive=include_inactive)

def get_product(product_id: int) -> Optional[Dict[str, Any]]:
    return _get_product_core(product_id)

def create_product(*, name: str, price_money: str | float | int, unit: str,
                   allow_decimal: bool, active: bool, category: str, icon: str = "") -> int:
    price_cents = money_to_cents(price_money)
    return _upsert_core(
        product_id=None,
        name=name,
        price_cents=price_cents,
        unit=unit,
        allow_decimal=allow_decimal,
        active=active,
        category=category,
        icon=icon,
    )

def update_product(*, product_id: int, name: str, price_money: str | float | int, unit: str,
                   allow_decimal: bool, active: bool, category: str, icon: str = "") -> int:
    price_cents = money_to_cents(price_money)
    return _upsert_core(
        product_id=product_id,
        name=name,
        price_cents=price_cents,
        unit=unit,
        allow_decimal=allow_decimal,
        active=active,
        category=category,
        icon=icon,
    )

def set_active(product_id: int, active: bool) -> None:
    data = _get_product_core(product_id)
    if not data:
        return
    _upsert_core(
        product_id=product_id,
        name=data["name"],
        price_cents=int(data["price"]),
        unit=data.get("unit") or "pz",
        allow_decimal=bool(data.get("allow_decimal", 0)),
        active=active,
        category=data.get("category") or "General",
        icon=data.get("icon") or "",
    )

def delete_product(product_id: int) -> None:
    _delete_core(product_id)

def get_categories() -> List[str]:
    return _get_categories_core()

