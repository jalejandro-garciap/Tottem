from __future__ import annotations

import sqlite3
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "config.yaml"
DB_PATH = ROOT / "data.db"
MIGRATIONS_DIR = ROOT / "migrations"
LOGS_DIR = ROOT / "logs"

DEFAULT_CONFIG = """# TOTTEM POS - Configuración
# ═══════════════════════════════════════════════════════════════════════════

store:
  name: "Mi Tienda"
  ticket_header: |
    MI TIENDA
    Dirección de ejemplo
    Tel: (123) 456-7890
  ticket_footer: |
    ¡Gracias por su compra!
    Vuelva pronto

hardware:
  printer:
    vendor_id: 0x0416
    product_id: 0x5011
    interface: 0
    out_endpoint: 0x03
    in_endpoint: 0x82

security:
  # PIN por defecto: 1234 (cambiar en producción)
  admin_pin_hash: "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$RdescudvJCsgt3ub+b+dWRWJTmaaJObG"

ui:
  theme: "dark"
  categories_enabled: false

notifications:
  email:
    gmail_user: "tottem.reports@gmail.com"
    gmail_pass: "mfexwikphlncahve"

settings:
  language: "es"
"""


def factory_reset() -> tuple[bool, str]:
    try:
        for suffix in ("", "-shm", "-wal"):
            db_file = DB_PATH.with_name(DB_PATH.name + suffix)
            if db_file.exists():
                db_file.unlink()

        if LOGS_DIR.exists():
            shutil.rmtree(LOGS_DIR)

        if CONFIG_PATH.exists():
            CONFIG_PATH.unlink()

        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(DEFAULT_CONFIG, encoding="utf-8")

        if MIGRATIONS_DIR.exists():
            conn = sqlite3.connect(DB_PATH)
            try:
                for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
                    conn.executescript(sql_file.read_text(encoding="utf-8"))
                conn.commit()
            finally:
                conn.close()
        return True, "Restauración completada. Reinicia la aplicación."
    except Exception as exc:
        return False, f"No se pudo restaurar: {exc}"
