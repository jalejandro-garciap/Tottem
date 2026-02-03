#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# TOTTEM POS - Restauración de Fábrica
# ═══════════════════════════════════════════════════════════════════════════
# Limpia configuración, base de datos y logs, y regenera archivos mínimos.
#
# Uso: bash scripts/factory_reset.sh
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }

if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}[ERROR]${NC} Este script debe ejecutarse desde el directorio raíz del proyecto."
    exit 1
fi

log_warning "Esto eliminará config/config.yaml y data.db."
read -r -p "¿Deseas continuar? (escribe SI para confirmar): " confirm
if [ "${confirm}" != "SI" ]; then
    log_info "Operación cancelada."
    exit 0
fi

log_info "Eliminando base de datos..."
rm -f data.db data.db-shm data.db-wal || true

log_info "Eliminando logs..."
rm -rf logs || true

log_info "Eliminando configuración..."
rm -f config/config.yaml || true
mkdir -p config

log_info "Regenerando config.yaml..."
cat > config/config.yaml << 'EOF'
# TOTTEM POS - Configuración
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
EOF

log_info "Regenerando base de datos..."
if ! command -v sqlite3 &> /dev/null; then
    log_warning "sqlite3 no está instalado. Instálalo para aplicar migraciones."
else
    if [ -d "migrations" ]; then
        for sql_file in $(ls migrations/*.sql 2>/dev/null | sort); do
            if [ -f "$sql_file" ]; then
                log_info "Aplicando: $(basename "$sql_file")"
                sqlite3 data.db < "$sql_file" || true
            fi
        done
    fi
fi

log_success "Restauración de fábrica completada."
