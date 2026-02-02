from __future__ import annotations
import smtplib
from email.message import EmailMessage
from pathlib import Path
import yaml
from typing import List, Tuple, Optional

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "config.yaml"


def _load_cfg() -> dict:
    try:
        return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _save_cfg(cfg):
    """Save config.yaml dict back to disk."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def _create_html_email_report(date_from: str, date_to: str, stats: dict) -> str:
    """
    Crea un email HTML con diseño similar a Vista Previa del Turno.
    
    Args:
        date_from: Fecha inicio en formato YYYY-MM-DD
        date_to: Fecha fin en formato YYYY-MM-DD
        stats: Dict con estadísticas {total_cents, tickets, items}
    
    Returns:
        HTML string del reporte
    """
    # Formatear total
    total_formatted = f"{stats['total_cents'] / 100:,.2f}"
    
    # Formatear fechas para mostrar (DD/MM/YYYY)
    from datetime import datetime
    dt_from = datetime.strptime(date_from, "%Y-%m-%d")
    dt_to = datetime.strptime(date_to, "%Y-%m-%d")
    fecha_from = dt_from.strftime("%d/%m/%Y")
    fecha_to = dt_to.strftime("%d/%m/%Y")
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            margin: 0;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        }}
    </style>
</head>
<body>
    <div style="max-width: 600px; margin: 0 auto; background: #12121a; border-radius: 16px; padding: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
        
        <!-- Encabezado -->
        <h1 style="text-align: center; font-size: 11px; letter-spacing: 2.5px; color: #64748b; font-weight: 700; margin: 0 0 16px 0; text-transform: uppercase; line-height: 1.2;">
            REPORTE DE VENTAS
        </h1>
        
        <!-- Panel de información -->
        <div style="background: #16161e; padding: 16px; border-radius: 10px; margin: 12px 0;">
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="color: #94a3b8; padding: 6px 12px; font-weight: 600; font-size: 13px; border-bottom: 1px solid #1a1a26; line-height: 1.3;">
                        Período:
                    </td>
                    <td style="color: #f8fafc; padding: 6px 12px; font-size: 13px; border-bottom: 1px solid #1a1a26; line-height: 1.3;">
                        {fecha_from} - {fecha_to}
                    </td>
                </tr>
                <tr>
                    <td style="color: #94a3b8; padding: 6px 12px; font-weight: 600; font-size: 13px; border-bottom: 1px solid #1a1a26; line-height: 1.3;">
                        Tickets:
                    </td>
                    <td style="color: #f8fafc; padding: 6px 12px; font-size: 15px; font-weight: 700; border-bottom: 1px solid #1a1a26; line-height: 1.3;">
                        {stats['tickets']}
                    </td>
                </tr>
                <tr>
                    <td style="color: #94a3b8; padding: 6px 12px; font-weight: 600; font-size: 13px; border-bottom: 1px solid #1a1a26; line-height: 1.3;">
                        Artículos:
                    </td>
                    <td style="color: #f8fafc; padding: 6px 12px; font-size: 15px; font-weight: 700; border-bottom: 1px solid #1a1a26; line-height: 1.3;">
                        {stats['items']}
                    </td>
                </tr>
                <tr>
                    <td style="color: #94a3b8; padding: 6px 12px; font-weight: 600; font-size: 13px; line-height: 1.3;">
                        Total Ventas:
                    </td>
                    <td style="color: #10b981; padding: 6px 12px; font-size: 17px; font-weight: 700; line-height: 1.3;">
                        $ {total_formatted}
                    </td>
                </tr>
            </table>
        </div>
        
        <!-- Mensaje -->
        <p style="color: #94a3b8; text-align: center; font-size: 12px; margin: 16px 0 0 0; line-height: 1.4;">
            📊 Detalles completos en el archivo CSV adjunto
        </p>
        
    </div>
</body>
</html>
    """
    return html.strip()


def recent_emails() -> List[str]:
    cfg = _load_cfg()
    return list(cfg.get("notifications", {}).get("recent_emails", []) or [])


def add_recent_emails(emails: List[str], max_keep: int = 10) -> None:
    cfg = _load_cfg()
    notif = cfg.setdefault("notifications", {})
    cur = list(notif.get("recent_emails", []) or [])
    for e in emails:
        e = e.strip()
        if e and e not in cur:
            cur.insert(0, e)
    notif["recent_emails"] = cur[:max_keep]
    _save_cfg(cfg)


def remove_recent_email(email: str) -> None:
    """Elimina un email de la lista de recientes."""
    cfg = _load_cfg()
    notif = cfg.get("notifications", {})
    cur = list(notif.get("recent_emails", []) or [])
    
    if email in cur:
        cur.remove(email)
        notif["recent_emails"] = cur
        cfg["notifications"] = notif
        _save_cfg(cfg)


def send_mail(subject: str, body: str, recipients: List[str],
              attachments: Optional[List[Tuple[str, bytes]]] = None,
              html_body: Optional[str] = None) -> Tuple[bool, str]:
    """
    Send simple email using Gmail (yagmail) or SMTP settings stored in config.yaml:
      notifications:
        email:
          gmail_user: "user@gmail.com"      # Para Gmail con yagmail
          gmail_pass: "app_password"         # Contraseña de aplicación
          
          # O configuración SMTP tradicional:
          smtp_host: "smtp.example.com"
          smtp_port: 587
          use_tls: true
          username: "user"
          password: "pass"
          from_addr: "pos@example.com"
    attachments: list of (filename, bytes)
    html_body: optional HTML version of the email body
    """
    cfg = _load_cfg()
    email_cfg = (cfg.get("notifications", {}) or {}).get("email", {}) or {}
    
    # Intentar usar Gmail/yagmail primero
    gmail_user = email_cfg.get("gmail_user", "").strip()
    gmail_pass = email_cfg.get("gmail_pass", "").strip()
    
    if gmail_user and gmail_pass:
        # Usar yagmail para Gmail
        try:
            import yagmail
        except ImportError:
            return False, "yagmail no está instalado. Instala con: pip install yagmail"
        
        try:
            yag = yagmail.SMTP(gmail_user, gmail_pass)
            
            # yagmail usa HTML automáticamente si detecta tags HTML
            email_contents = html_body if html_body else body
            
            # Preparar adjuntos para yagmail
            attachments_yagmail = []
            if attachments:
                # yagmail necesita archivos temporales para adjuntos desde bytes
                import tempfile
                import os
                temp_files = []
                for fname, data in attachments:
                    # Crear archivo temporal
                    fd, path = tempfile.mkstemp(suffix=f"_{fname}")
                    os.write(fd, data)
                    os.close(fd)
                    temp_files.append(path)
                    attachments_yagmail.append(path)
                
                # Enviar email
                yag.send(to=recipients, subject=subject, contents=email_contents, attachments=attachments_yagmail)
                
                # Limpiar archivos temporales
                for path in temp_files:
                    try:
                        os.remove(path)
                    except:
                        pass
            else:
                yag.send(to=recipients, subject=subject, contents=email_contents)
            
            add_recent_emails(recipients)
            return True, "OK"
        except Exception as e:
            return False, f"Error con Gmail/yagmail: {str(e)}"
    
    # Fallback a SMTP tradicional
    host = email_cfg.get("smtp_host")
    port = int(email_cfg.get("smtp_port", 587))
    use_tls = bool(email_cfg.get("use_tls", True))
    user = email_cfg.get("username")
    pwd = email_cfg.get("password")
    from_addr = email_cfg.get("from_addr") or user

    if not host or not from_addr:
        return False, "Email no configurado. Configura Gmail en el tab Sistema o SMTP en config.yaml."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    
    # Si hay HTML, configurar contenido multipart
    if html_body:
        msg.set_content(body)  # Texto plano como fallback
        msg.add_alternative(html_body, subtype='html')  # HTML como alternativa
    else:
        msg.set_content(body)

    if attachments:
        for fname, data in attachments:
            msg.add_attachment(data, maintype="text", subtype="csv", filename=fname)

    try:
        if use_tls and port in (465,):
            with smtplib.SMTP_SSL(host, port) as s:
                if user and pwd:
                    s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.ehlo()
                if use_tls:
                    s.starttls()
                    s.ehlo()
                if user and pwd:
                    s.login(user, pwd)
                s.send_message(msg)
        add_recent_emails(recipients)
        return True, "OK"
    except Exception as e:
        return False, str(e)

