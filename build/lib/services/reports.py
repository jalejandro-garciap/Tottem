from __future__ import annotations
import io
import csv
from typing import Optional, Tuple, List
from services.sales import connect, cents_to_money
from services.shifts import current_shift, shift_totals


def render_shift_text(shift_id: int) -> str:
    """Pretty text for a single shift, suitable for ESC/POS or email body."""
    conn = connect(); cur = conn.cursor()
    cur.execute("SELECT id, opened_at, opened_by, closed_at, closed_by, opening_cash, closing_cash FROM shift WHERE id=?;", (int(shift_id),))
    sh = cur.fetchone()
    if not sh:
        return "Turno no encontrado.\n"
    cur.execute("SELECT id, ts, total FROM ticket WHERE shift_id=? ORDER BY id;", (int(shift_id),))
    tickets = cur.fetchall()
    sums = shift_totals(shift_id)

    out = []
    out.append("REPORTE DE TURNO\n")
    out.append("----------------\n")
    out.append(f"Turno: #{sh[0]}\n")
    out.append(f"Inicio: {sh[1]}  •  Abre: {sh[2] or '-'}\n")
    out.append(f"Cierre: {sh[3] or '-'}  •  Cierra: {sh[4] or '-'}\n")
    out.append("\n")
    out.append(f"Tickets: {sums['tickets']}\n")
    out.append(f"Artículos: {sums['items']}\n")
    out.append(f"Total: $ {cents_to_money(sums['total'])}\n")
    out.append("\n")
    out.append("Detalle de tickets:\n")
    for t in tickets:
        out.append(f"  #{t[0]}  {t[1]}  $ {cents_to_money(int(t[2]))}\n")
    return "".join(out)


def render_range_text(date_from: str, date_to: str) -> str:
    """Pretty text for a date range summary."""
    conn = connect(); cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*), COALESCE(SUM(total),0) FROM ticket WHERE DATE(ts) BETWEEN DATE(?) AND DATE(?);",
        (date_from, date_to),
    )
    row = cur.fetchone() or (0, 0)
    tickets = int(row[0] or 0); total = int(row[1] or 0)
    out = []
    out.append("REPORTE POR RANGO DE FECHAS\n")
    out.append("---------------------------\n")
    out.append(f"Desde: {date_from}\nHasta: {date_to}\n\n")
    out.append(f"Tickets: {tickets}\n")
    out.append(f"Total: $ {cents_to_money(total)}\n")
    return "".join(out)


def csv_tickets_bytes(date_from: str, date_to: str) -> bytes:
    """CSV content for tickets in range, as bytes."""
    conn = connect(); cur = conn.cursor()
    cur.execute(
        "SELECT id, ts, shift_id, total FROM ticket WHERE DATE(ts) BETWEEN DATE(?) AND DATE(?) ORDER BY ts;",
        (date_from, date_to),
    )
    rows = cur.fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ticket_id", "timestamp", "shift_id", "total_cents"])
    for r in rows:
        w.writerow([r[0], r[1], r[2], r[3]])
    return buf.getvalue().encode("utf-8")


def csv_items_bytes(date_from: str, date_to: str) -> bytes:
    """CSV content for items in range, as bytes."""
    conn = connect(); cur = conn.cursor()
    cur.execute(
        """
        SELECT ti.ticket_id, t.ts, ti.product_id, ti.name, ti.price, ti.quantity, ti.unit
        FROM ticket_item ti
        JOIN ticket t ON t.id = ti.ticket_id
        WHERE DATE(t.ts) BETWEEN DATE(?) AND DATE(?)
        ORDER BY t.ts, ti.id;
        """,
        (date_from, date_to),
    )
    rows = cur.fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ticket_id", "timestamp", "product_id", "name", "price_cents", "quantity", "unit"])
    for r in rows:
        w.writerow(list(r))
    return buf.getvalue().encode("utf-8")


def report_x() -> Tuple[str, Optional[int]]:
    """Preview current shift (not closing)."""
    sh = current_shift()
    if not sh:
        return "No hay turno abierto.\n", None
    text = render_shift_text(sh["id"])
    return text, sh["id"]


def report_z(closed_by: str = "", closing_cash: int = 0) -> str:
    """Close current shift and return final text."""
    from services.shifts import close_shift
    sh = current_shift()
    if not sh:
        return "No hay turno abierto.\n"
    text = render_shift_text(sh["id"])
    close_shift(closed_by=closed_by, closing_cash=int(closing_cash))
    text += "\nEstado: CERRADO\n"
    return text

