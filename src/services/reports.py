from __future__ import annotations
import io
import csv
from datetime import datetime
from typing import Optional, Tuple, List
from services.sales import connect, cents_to_money
from services.shifts import current_shift, shift_totals


def get_shift_tickets_detail(shift_id: int) -> List[dict]:
    """
    Obtiene el detalle completo de todos los tickets de un turno,
    incluyendo los productos de cada ticket.
    """
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, ts, total, COALESCE(payment_method, 'cash') as payment_method
        FROM ticket 
        WHERE shift_id = ? 
        ORDER BY ts ASC
    """, (int(shift_id),))
    tickets = cur.fetchall()
    
    result = []
    for ticket in tickets:
        ticket_id = ticket[0]
        
        cur.execute("""
            SELECT name, price, quantity, COALESCE(unit, 'pz') as unit
            FROM ticket_item
            WHERE ticket_id = ?
            ORDER BY id
        """, (ticket_id,))
        items = cur.fetchall()
        
        result.append({
            "id": ticket_id,
            "timestamp": ticket[1],
            "total": int(ticket[2]),
            "payment_method": ticket[3] or "cash",
            "items": [
                {
                    "name": item[0],
                    "price": int(item[1]),
                    "qty": float(item[2]),
                    "unit": item[3]
                }
                for item in items
            ]
        })
    
    return result


def render_shift_text(shift_id: int, detailed: bool = False) -> str:
    """Pretty text for a single shift, suitable for ESC/POS or email body."""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, opened_at, opened_by, closed_at, closed_by, opening_cash, closing_cash 
        FROM shift WHERE id=?
    """, (int(shift_id),))
    sh = cur.fetchone()
    if not sh:
        return "Turno no encontrado.\n"
    
    sums = shift_totals(shift_id)
    opening_cash = int(sh[5] or 0)
    closing_cash = int(sh[6] or 0) if sh[6] is not None else None

    out = []
    out.append("================================\n")
    out.append("       REPORTE DE TURNO\n")
    out.append("================================\n\n")
    
    out.append(f"Turno #: {sh[0]}\n")
    out.append(f"Apertura: {sh[1] or '-'}\n")
    if sh[2]:
        out.append(f"Abierto por: {sh[2]}\n")
    out.append(f"Cierre: {sh[3] or 'EN CURSO'}\n")
    if sh[4]:
        out.append(f"Cerrado por: {sh[4]}\n")
    out.append("\n")
    
    out.append("--------------------------------\n")
    out.append("         RESUMEN\n")
    out.append("--------------------------------\n")
    out.append(f"Tickets vendidos:  {sums['tickets']}\n")
    out.append(f"Articulos totales: {sums['items']}\n")
    out.append(f"Fondo inicial:     $ {cents_to_money(opening_cash)}\n")
    out.append(f"Total ventas:      $ {cents_to_money(sums['total'])}\n")
    if sums.get('total_card', 0) > 0:
        out.append(f"  Efectivo:        $ {cents_to_money(sums['total_cash'])}\n")
        out.append(f"  Tarjeta:         $ {cents_to_money(sums['total_card'])}\n")
    
    expected_cash = opening_cash + sums.get('total_cash', sums['total'])
    out.append(f"Efectivo esperado: $ {cents_to_money(expected_cash)}\n")
    
    if closing_cash is not None:
        out.append(f"Efectivo contado:  $ {cents_to_money(closing_cash)}\n")
        diff = closing_cash - expected_cash
        if diff > 0:
            out.append(f"Sobrante:          $ {cents_to_money(diff)}\n")
        elif diff < 0:
            out.append(f"Faltante:          $ {cents_to_money(abs(diff))}\n")
        else:
            out.append("Cuadre:            EXACTO\n")
    
    out.append("\n")
    
    if detailed:
        tickets_detail = get_shift_tickets_detail(shift_id)
        if tickets_detail:
            out.append("================================\n")
            out.append("     DETALLE DE VENTAS\n")
            out.append("================================\n\n")
            
            for idx, ticket in enumerate(tickets_detail, 1):
                try:
                    ts = ticket["timestamp"]
                    if "T" in ts:
                        hora = ts.split("T")[1][:5]
                    else:
                        hora = ts.split(" ")[1][:5] if " " in ts else ts
                except (KeyError, TypeError, ValueError, IndexError):
                    hora = ticket["timestamp"]
                
                out.append(f"#{ticket['id']} - {hora}\n")
                out.append("-" * 30 + "\n")
                
                for item in ticket["items"]:
                    qty_str = f"{item['qty']:.2f}".rstrip('0').rstrip('.')
                    subtotal = int(item["price"] * item["qty"])
                    name = item["name"][:20]  # Truncar nombre largo
                    out.append(f"  {qty_str} {item['unit']} {name}\n")
                    out.append(f"       $ {cents_to_money(subtotal)}\n")
                
                out.append(f"  TOTAL: $ {cents_to_money(ticket['total'])}\n")
                out.append("\n")
    else:
        cur.execute("SELECT id, ts, total FROM ticket WHERE shift_id=? ORDER BY id;", (int(shift_id),))
        tickets = cur.fetchall()
        if tickets:
            out.append("--------------------------------\n")
            out.append("      LISTA DE TICKETS\n")
            out.append("--------------------------------\n")
            for t in tickets:
                out.append(f"  #{t[0]}  {t[1][-8:]}  $ {cents_to_money(int(t[2]))}\n")
            out.append("\n")
    
    out.append("================================\n")
    
    return "".join(out)


def render_shift_closure_report(shift_id: int, closing_cash: int = 0, closed_by: str = "") -> str:
    """
    Genera un reporte completo de cierre de turno con:
    - Resumen del turno
    - Total de ventas
    - Efectivo esperado vs contado
    - Detalle de todas las transacciones
    """
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, opened_at, opened_by, closed_at, closed_by, opening_cash, closing_cash 
        FROM shift WHERE id=?
    """, (int(shift_id),))
    sh = cur.fetchone()
    if not sh:
        return "Turno no encontrado.\n"
    
    sums = shift_totals(shift_id)
    opening_cash_cents = int(sh[5] or 0)
    
    out = []
    
    # Header
    out.append("\n")
    out.append("================================\n")
    out.append("      CORTE DE CAJA - Z         \n")
    out.append("================================\n")
    out.append("\n")
    
    now = datetime.now()
    out.append(f"Fecha: {now.strftime('%d/%m/%Y')}\n")
    out.append(f"Hora:  {now.strftime('%H:%M:%S')}\n")
    out.append(f"Turno: #{sh[0]}\n")
    if closed_by:
        out.append(f"Cajero: {closed_by}\n")
    out.append("\n")
    
    # Tiempos
    out.append("--------------------------------\n")
    out.append("PERIODO DEL TURNO\n")
    out.append("--------------------------------\n")
    out.append(f"Apertura: {sh[1] or '-'}\n")
    out.append(f"Cierre:   {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
    out.append("\n")
    
    out.append("--------------------------------\n")
    out.append("RESUMEN DE VENTAS\n")
    out.append("--------------------------------\n")
    out.append(f"Transacciones:     {sums['tickets']:>10}\n")
    out.append(f"Articulos vendidos:{sums['items']:>10}\n")
    out.append(f"Total en ventas:   ${cents_to_money(sums['total']):>9}\n")
    if sums.get('total_card', 0) > 0:
        out.append(f"  Efectivo:        ${cents_to_money(sums['total_cash']):>9}\n")
        out.append(f"  Tarjeta:         ${cents_to_money(sums['total_card']):>9}\n")
    out.append("\n")
    
    out.append("--------------------------------\n")
    out.append("CUADRE DE CAJA\n")
    out.append("--------------------------------\n")
    out.append(f"Fondo inicial:     ${cents_to_money(opening_cash_cents):>9}\n")
    out.append(f"(+) Ventas efvo:   ${cents_to_money(sums.get('total_cash', sums['total'])):>9}\n")
    expected = opening_cash_cents + sums.get('total_cash', sums['total'])
    out.append(f"(=) Esperado:      ${cents_to_money(expected):>9}\n")
    out.append(f"Efectivo contado:  ${cents_to_money(closing_cash):>9}\n")
    
    diff = closing_cash - expected
    out.append("--------------------------------\n")
    if diff > 0:
        out.append(f"SOBRANTE:          ${cents_to_money(diff):>9}\n")
    elif diff < 0:
        out.append(f"*** FALTANTE:      ${cents_to_money(abs(diff)):>9}\n")
    else:
        out.append("CUADRE:              EXACTO ✓\n")
    out.append("\n")
    
    tickets_detail = get_shift_tickets_detail(shift_id)
    if tickets_detail:
        out.append("================================\n")
        out.append("DETALLE DE TRANSACCIONES\n")
        out.append("================================\n\n")
        
        for ticket in tickets_detail:
            try:
                ts = ticket["timestamp"]
                if " " in ts:
                    hora = ts.split(" ")[1][:5]
                elif "T" in ts:
                    hora = ts.split("T")[1][:5]
                else:
                    hora = ts
            except (KeyError, TypeError, ValueError, IndexError):
                hora = "??:??"
            
            out.append(f"Ticket #{ticket['id']} [{hora}]\n")
            
            for item in ticket["items"]:
                qty = item["qty"]
                qty_str = f"{qty:.2f}".rstrip('0').rstrip('.') if qty != int(qty) else str(int(qty))
                subtotal = int(item["price"] * qty)
                name = item["name"][:18]
                out.append(f"  {qty_str}x {name}\n")
                out.append(f"               ${cents_to_money(subtotal):>6}\n")
            
            out.append("--------------------------------\n")
            out.append(f"  SUBTOTAL:    ${cents_to_money(ticket['total']):>6}\n")
            out.append("\n")
    
    # Footer
    out.append("================================\n")
    out.append("       FIN DEL REPORTE\n")
    out.append("================================\n")
    out.append("\n\n\n")  # Espacio para corte
    
    return "".join(out)


def render_range_text(date_from: str, date_to: str) -> str:
    """Pretty text for a date range summary."""
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*), COALESCE(SUM(total),0) FROM ticket WHERE DATE(ts) BETWEEN DATE(?) AND DATE(?);",
        (date_from, date_to),
    )
    row = cur.fetchone() or (0, 0)
    tickets = int(row[0] or 0)
    total = int(row[1] or 0)
    out = []
    out.append("================================\n")
    out.append("  REPORTE POR RANGO DE FECHAS\n")
    out.append("================================\n\n")
    out.append(f"Desde: {date_from}\n")
    out.append(f"Hasta: {date_to}\n\n")
    out.append(f"Tickets: {tickets}\n")
    out.append(f"Total:   $ {cents_to_money(total)}\n")
    out.append("\n================================\n")
    return "".join(out)


def csv_tickets_bytes(date_from: str, date_to: str) -> bytes:
    """CSV content for tickets in range, as bytes."""
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, ts, shift_id, total, COALESCE(payment_method, 'cash') as payment_method FROM ticket WHERE DATE(ts) BETWEEN DATE(?) AND DATE(?) ORDER BY ts;",
        (date_from, date_to),
    )
    rows = cur.fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ticket_id", "timestamp", "shift_id", "total_cents", "metodo_pago"])
    _pm_es = {"cash": "efectivo", "card": "tarjeta"}
    for r in rows:
        pm_raw = r[4] if len(r) > 4 else "cash"
        w.writerow([r[0], r[1], r[2], r[3], _pm_es.get(pm_raw, pm_raw)])
    return buf.getvalue().encode("utf-8")


def csv_items_bytes(date_from: str, date_to: str) -> bytes:
    """CSV content for items in range, as bytes."""
    conn = connect()
    cur = conn.cursor()
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


def csv_sales_detailed_bytes(date_from: str, date_to: str) -> bytes:
    """
    Genera CSV detallado de ventas con información completa para análisis de demanda.
    
    Columnas:
    - ticket: ID del ticket
    - fecha: Fecha de la venta (YYYY-MM-DD)
    - hora: Hora de la venta (HH:MM:SS)
    - turno: ID del turno
    - producto_nombre: Nombre del producto
    - categoria: Categoría del producto
    - precio_unitario: Precio por unidad en formato decimal
    - cantidad: Cantidad vendida
    - unidad: Unidad de medida
    - subtotal: Precio total de la línea
    - total_ticket: Total del ticket
    """
    conn = connect()
    cur = conn.cursor()
    
    cur.execute(
        """
        SELECT 
            t.id as ticket_id,
            DATE(t.ts) as fecha,
            TIME(t.ts) as hora,
            t.shift_id,
            ti.name as producto_nombre,
            COALESCE(p.category, 'General') as categoria,
            ti.price as precio_cents,
            ti.quantity,
            COALESCE(ti.unit, 'pz') as unidad,
            t.total as total_ticket_cents,
            COALESCE(t.payment_method, 'cash') as metodo_pago
        FROM ticket t
        JOIN ticket_item ti ON ti.ticket_id = t.id
        LEFT JOIN product p ON p.id = ti.product_id
        WHERE DATE(t.ts) BETWEEN DATE(?) AND DATE(?)
        ORDER BY t.ts, t.id, ti.id;
        """,
        (date_from, date_to),
    )
    rows = cur.fetchall()
    
    buf = io.StringIO()
    w = csv.writer(buf)
    
    w.writerow([
        "ticket",
        "fecha",
        "hora",
        "turno",
        "producto_nombre",
        "categoria",
        "precio_unitario",
        "cantidad",
        "unidad",
        "subtotal",
        "total_ticket",
        "metodo_pago"
    ])
    
    for r in rows:
        ticket_id = r[0]
        fecha = r[1]
        hora = r[2]
        shift_id = r[3] or ""
        producto_nombre = r[4]
        categoria = r[5]
        precio_cents = int(r[6])
        cantidad = float(r[7])
        unidad = r[8]
        total_ticket_cents = int(r[9])
        
        # Calcular subtotal
        subtotal_cents = int(precio_cents * cantidad)
        
        # Convertir centavos a formato decimal
        precio_unitario = f"{precio_cents / 100:.2f}"
        subtotal = f"{subtotal_cents / 100:.2f}"
        total_ticket = f"{total_ticket_cents / 100:.2f}"
        metodo_pago_raw = r[10] or "cash"
        metodo_pago = {"cash": "efectivo", "card": "tarjeta"}.get(metodo_pago_raw, metodo_pago_raw)
        
        w.writerow([
            ticket_id,
            fecha,
            hora,
            shift_id,
            producto_nombre,
            categoria,
            precio_unitario,
            cantidad,
            unidad,
            subtotal,
            total_ticket,
            metodo_pago
        ])
    
    return buf.getvalue().encode("utf-8")


def report_x() -> Tuple[str, Optional[int]]:
    """Preview current shift (not closing)."""
    sh = current_shift()
    if not sh:
        return "No hay turno abierto.\n", None
    text = render_shift_text(sh["id"], detailed=True)
    return text, sh["id"]


def report_z(closed_by: str = "", closing_cash: int = 0) -> str:
    """Close current shift and return final detailed report."""
    from services.shifts import close_shift
    sh = current_shift()
    if not sh:
        return "No hay turno abierto.\n"
    
    text = render_shift_closure_report(sh["id"], closing_cash=closing_cash, closed_by=closed_by)
    
    close_shift(closed_by=closed_by, closing_cash=int(closing_cash))
    
    return text

