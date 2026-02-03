#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# TOTTEM POS - Desinstalar Dependencias
# ═══════════════════════════════════════════════════════════════════════════
# Elimina dependencias y archivos instalados por install_deps.sh.
#
# Uso: bash scripts/uninstall_deps.sh
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

log_warning "Se eliminará el entorno virtual, reglas udev y paquetes instalados."
read -r -p "¿Deseas continuar? (escribe SI para confirmar): " confirm
if [ "${confirm}" != "SI" ]; then
    log_info "Operación cancelada."
    exit 0
fi

log_info "Eliminando entorno virtual..."
rm -rf .venv || true

log_info "Eliminando reglas udev..."
sudo rm -f /etc/udev/rules.d/99-escpos.rules || true
sudo udevadm control --reload-rules || true
sudo udevadm trigger || true

log_info "Quitando usuario de grupos..."
sudo gpasswd -d "${SUDO_USER:-$USER}" dialout || true
sudo gpasswd -d "${SUDO_USER:-$USER}" plugdev || true

log_info "Desinstalando paquetes del sistema..."
sudo apt remove -y \
    python3-venv \
    python3-dev \
    build-essential \
    pkg-config \
    libusb-1.0-0-dev \
    libudev-dev \
    kbd \
    console-setup || true

sudo apt autoremove -y || true

log_success "Desinstalación completada."
