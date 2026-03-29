# -*- coding: utf-8 -*-

from __future__ import annotations
from typing import Iterable, Optional
from pathlib import Path
import yaml
from services.sales import CartItem, cents_to_money

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "config.yaml"


def _load_cfg() -> dict:
    try:
        raw = CONFIG_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        return yaml.safe_load(raw) or {}
    except Exception:
        return {}


def render_ticket(
    items: Iterable[CartItem], 
    *, 
    paid_cents: Optional[int] = None, 
    change_cents: Optional[int] = None,
    ticket_number: Optional[int] = None,
    timestamp: Optional[str] = None,
    served_by: Optional[str] = None,
    payment_method: Optional[str] = None
) -> str:
    """
    Devuelve un bloque de texto listo para imprimir en ESC/POS.
    Si se incluyen paid_cents y change_cents, los muestra al final.
    Si se incluyen ticket_number, timestamp, served_by, los muestra al inicio.
    """
    cfg = _load_cfg()
    store = cfg.get("store", {}) or {}
    head = (store.get("ticket_header") or "").strip()
    foot = (store.get("ticket_footer") or "").strip()

    out = []
    if head:
        out.append(head.rstrip() + "\n")
    else:
        out.append("Mi Tienda\n")

    if ticket_number is not None:
        out.append(f"\nTicket: {ticket_number}\n")
    if served_by:
        out.append(f"Cajero: {served_by}\n")
    if timestamp:
        out.append(f"Fecha: {timestamp}\n")
    
    out.append("------------------------------\n")
    total = 0
    for it in items:
        # Build name with presentation
        line_name = f"{it.name}".strip()
        pres_name = getattr(it, 'presentation_name', None)
        if pres_name and pres_name != 'Única':
            line_name = f"{it.name} ({pres_name})"

        qty_str = f"x{it.qty}"

        # Use applied_price if available, otherwise base price
        eff_price = getattr(it, 'applied_price', None)
        if eff_price is None:
            eff_price = it.price
        price_str = f"$ {cents_to_money(eff_price)}"

        # Pricing type indicator
        price_type = getattr(it, 'price_type', 'normal') or 'normal'
        tag = ""
        if price_type == 'wholesale':
            tag = " MAYOREO"
        elif price_type == 'discount':
            tag = " DTO"

        out.append(f"{qty_str} {line_name}{tag}\n   {price_str}\n")
        total += eff_price * it.qty

    out.append("------------------------------\n")
    out.append(f"TOTAL: $ {cents_to_money(total)}\n")

    if payment_method == "card":
        out.append("Metodo: Tarjeta\n")
    else:
        if paid_cents is not None and paid_cents > 0:
            out.append(f"Pago:  $ {cents_to_money(int(paid_cents))}\n")
        if change_cents is not None and change_cents > 0:
            out.append(f"Cambio:$ {cents_to_money(int(change_cents))}\n")

    if foot:
        out.append("\n" + foot.rstrip() + "\n")

    return "".join(out)


