#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# TOTTEM POS - Desinstalación de Dependencias del Sistema
# ═══════════════════════════════════════════════════════════════════════════
# Revierte los cambios realizados por install_deps.sh:
#   - Elimina reglas udev de impresoras ESC/POS
#   - Elimina entorno virtual de Python
#   - Restaura configuración de suspensión del sistema
#
# NOTA: NO elimina paquetes del sistema (python3, librerías, etc.)
#       porque podrían ser usados por otros programas.
#
# Uso: sudo bash scripts/uninstall_deps.sh
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ─────────────────────────────────────────────────────────────────────────────
# Verificaciones iniciales
# ─────────────────────────────────────────────────────────────────────────────

if [ "$(id -u)" -ne 0 ]; then
    log_error "Este script debe ejecutarse con sudo."
    log_error "Uso: sudo bash scripts/uninstall_deps.sh"
    exit 1
fi

if [ ! -f "pyproject.toml" ]; then
    log_error "Este script debe ejecutarse desde el directorio raíz del proyecto."
    exit 1
fi

log_info "Desinstalando componentes de TOTTEM POS..."
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 1. Eliminar reglas udev para impresoras ESC/POS
# ─────────────────────────────────────────────────────────────────────────────

log_info "Eliminando reglas udev de impresoras..."

if [ -f /etc/udev/rules.d/99-escpos.rules ]; then
    rm -f /etc/udev/rules.d/99-escpos.rules
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger 2>/dev/null || true
    log_success "Reglas udev eliminadas."
else
    log_warning "No se encontraron reglas udev de ESC/POS."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 2. Eliminar entorno virtual de Python
# ─────────────────────────────────────────────────────────────────────────────

log_info "Eliminando entorno virtual..."

if [ -d ".venv" ]; then
    rm -rf .venv
    log_success "Entorno virtual eliminado."
else
    log_warning "No se encontró entorno virtual."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 3. Restaurar suspensión / hibernación del sistema
# ─────────────────────────────────────────────────────────────────────────────

log_info "Restaurando configuración de suspensión..."

# Unmask targets de suspensión
systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true

# Restaurar logind.conf desde respaldo
LOGIND_CONF="/etc/systemd/logind.conf"
if [ -f "${LOGIND_CONF}.bak.tottem" ]; then
    cp "${LOGIND_CONF}.bak.tottem" "$LOGIND_CONF"
    rm -f "${LOGIND_CONF}.bak.tottem"
    systemctl restart systemd-logind 2>/dev/null || true
    log_success "Configuración de logind restaurada desde respaldo."
else
    log_warning "No se encontró respaldo de logind.conf. Configuración no modificada."
fi

log_success "Configuración de suspensión restaurada."

# ─────────────────────────────────────────────────────────────────────────────
# 4. Nota sobre paquetes del sistema
# ─────────────────────────────────────────────────────────────────────────────

log_warning "Los paquetes del sistema (python3, librerías Qt, etc.) NO fueron eliminados"
log_warning "porque podrían ser usados por otros programas."
log_warning "Si desea eliminarlos manualmente, revise install_deps.sh para la lista completa."

# ─────────────────────────────────────────────────────────────────────────────
# Resumen final
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo -e "${GREEN}DESINSTALACIÓN DE DEPENDENCIAS COMPLETADA${NC}"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "Componentes eliminados:"
echo "  ✓ Reglas udev (impresoras ESC/POS)"
echo "  ✓ Entorno virtual de Python (.venv)"
echo "  ✓ Prevención de suspensión (restaurada)"
echo ""
echo "Para desinstalar el servicio del sistema:"
echo "  sudo bash scripts/uninstall_services.sh"
echo ""
