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


def _save_cfg(data: dict) -> None:
    CONFIG_PATH.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


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


def send_mail(subject: str, body: str, recipients: List[str],
              attachments: Optional[List[Tuple[str, bytes]]] = None) -> Tuple[bool, str]:
    """
    Send simple email using SMTP settings stored in config.yaml:
      notifications:
        email:
          smtp_host: "smtp.example.com"
          smtp_port: 587
          use_tls: true
          username: "user"
          password: "pass"
          from_addr: "pos@example.com"
    attachments: list of (filename, bytes)
    """
    cfg = _load_cfg()
    email_cfg = (cfg.get("notifications", {}) or {}).get("email", {}) or {}
    host = email_cfg.get("smtp_host")
    port = int(email_cfg.get("smtp_port", 587))
    use_tls = bool(email_cfg.get("use_tls", True))
    user = email_cfg.get("username")
    pwd = email_cfg.get("password")
    from_addr = email_cfg.get("from_addr") or user

    if not host or not from_addr:
        return False, "SMTP no configurado (notifications.email en config.yaml)."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
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

