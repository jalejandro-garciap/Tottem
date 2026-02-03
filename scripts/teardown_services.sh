#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# TOTTEM POS - Desinstalar Servicio Systemd
# ═══════════════════════════════════════════════════════════════════════════
# Uso: sudo bash scripts/teardown_services.sh
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

if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}[ERROR]${NC} Este script debe ejecutarse con sudo."
    exit 1
fi

if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}[ERROR]${NC} Este script debe ejecutarse desde el directorio raíz del proyecto."
    exit 1
fi

log_warning "Se desactivará el servicio pos.service y se eliminarán archivos de systemd."
read -r -p "¿Deseas continuar? (escribe SI para confirmar): " confirm
if [ "${confirm}" != "SI" ]; then
    log_info "Operación cancelada."
    exit 0
fi

log_info "Deteniendo servicio..."
systemctl stop pos.service || true
systemctl disable pos.service || true

log_info "Eliminando archivos de servicio..."
rm -f /etc/systemd/system/pos.service
rm -f /etc/sudoers.d/pos
rm -rf /etc/systemd/system/getty@tty1.service.d
rm -f /etc/profile.d/pos-console.sh

systemctl daemon-reload

log_success "Servicio desinstalado."
