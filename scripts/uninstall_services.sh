#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# TOTTEM POS - Desinstalación de Servicios del Sistema
# ═══════════════════════════════════════════════════════════════════════════
# Revierte los cambios realizados por setup_services.sh:
#   - Detiene y deshabilita el servicio pos.service y splash services
#   - Elimina archivo de servicio, sudoers, autologin, screen blanking
#   - Restaura configuración de suspensión del sistema
#   - Restaura texto de arranque del kernel
#   - Elimina grupo posadm
#
# Uso: sudo bash scripts/uninstall_services.sh
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
    log_error "Uso: sudo bash scripts/uninstall_services.sh"
    exit 1
fi

log_info "Desinstalando servicios de TOTTEM POS..."
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 1. Detener y deshabilitar servicio pos.service
# ─────────────────────────────────────────────────────────────────────────────

log_info "Deteniendo servicio pos.service..."

if systemctl is-active --quiet pos.service 2>/dev/null; then
    systemctl stop pos.service
    log_success "Servicio detenido."
else
    log_warning "El servicio no estaba activo."
fi

if systemctl is-enabled --quiet pos.service 2>/dev/null; then
    systemctl disable pos.service
    log_success "Servicio deshabilitado."
else
    log_warning "El servicio no estaba habilitado."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 2. Eliminar archivo de servicio
# ─────────────────────────────────────────────────────────────────────────────

log_info "Eliminando archivo de servicio..."

if [ -f /etc/systemd/system/pos.service ]; then
    rm -f /etc/systemd/system/pos.service
    log_success "Archivo de servicio POS eliminado."
else
    log_warning "No se encontró el archivo de servicio POS."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 2b. Eliminar servicios de splash
# ─────────────────────────────────────────────────────────────────────────────

log_info "Eliminando servicios de splash..."

for svc in tottem-splash.service tottem-splash-shutdown.service; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        systemctl stop "$svc" 2>/dev/null || true
    fi
    if systemctl is-enabled --quiet "$svc" 2>/dev/null; then
        systemctl disable "$svc" 2>/dev/null || true
    fi
    if [ -f "/etc/systemd/system/$svc" ]; then
        rm -f "/etc/systemd/system/$svc"
        log_success "$svc eliminado."
    fi
done

systemctl daemon-reload

# ─────────────────────────────────────────────────────────────────────────────
# 3. Eliminar configuración de sudoers
# ─────────────────────────────────────────────────────────────────────────────

log_info "Eliminando configuración de sudoers..."

if [ -f /etc/sudoers.d/pos ]; then
    rm -f /etc/sudoers.d/pos
    log_success "Archivo sudoers eliminado."
else
    log_warning "No se encontró archivo sudoers de POS."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 4. Eliminar configuración de autologin
# ─────────────────────────────────────────────────────────────────────────────

log_info "Eliminando configuración de autologin..."

AUTOLOGIN_DIR="/etc/systemd/system/getty@tty1.service.d"
if [ -f "${AUTOLOGIN_DIR}/autologin.conf" ]; then
    rm -f "${AUTOLOGIN_DIR}/autologin.conf"
    # Eliminar directorio si quedó vacío
    rmdir "${AUTOLOGIN_DIR}" 2>/dev/null || true
    log_success "Autologin eliminado."
else
    log_warning "No se encontró configuración de autologin."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 5. Eliminar screen blanking profile
# ─────────────────────────────────────────────────────────────────────────────

log_info "Eliminando perfil de screen blanking..."

if [ -f /etc/profile.d/pos-console.sh ]; then
    rm -f /etc/profile.d/pos-console.sh
    log_success "Perfil de screen blanking eliminado."
else
    log_warning "No se encontró perfil de screen blanking."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 6. Restaurar suspensión / hibernación
# ─────────────────────────────────────────────────────────────────────────────

log_info "Restaurando configuración de suspensión..."

systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true

LOGIND_CONF="/etc/systemd/logind.conf"
if [ -f "${LOGIND_CONF}.bak.tottem" ]; then
    cp "${LOGIND_CONF}.bak.tottem" "$LOGIND_CONF"
    rm -f "${LOGIND_CONF}.bak.tottem"
    systemctl restart systemd-logind 2>/dev/null || true
    log_success "Configuración de logind restaurada."
else
    log_warning "No se encontró respaldo de logind.conf."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 7. Eliminar grupo posadm (opcional)
# ─────────────────────────────────────────────────────────────────────────────

log_info "Eliminando grupo posadm..."

if getent group posadm > /dev/null 2>&1; then
    groupdel posadm 2>/dev/null || log_warning "No se pudo eliminar grupo posadm (puede tener usuarios asignados)."
    log_success "Grupo posadm eliminado."
else
    log_warning "Grupo posadm no existía."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 8. Restaurar texto de arranque del kernel y config.txt
# ─────────────────────────────────────────────────────────────────────────────

log_info "Restaurando parámetros de arranque del kernel..."

# Restaurar cmdline.txt desde respaldo
for path in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
    if [ -f "${path}.bak.tottem" ]; then
        cp "${path}.bak.tottem" "$path"
        rm -f "${path}.bak.tottem"
        log_success "cmdline.txt restaurado desde respaldo."
        break
    fi
done

# Eliminar disable_splash de config.txt
for path in /boot/firmware/config.txt /boot/config.txt; do
    if [ -f "$path" ]; then
        if grep -q "disable_splash=1" "$path" 2>/dev/null; then
            sed -i '/^disable_splash=1$/d' "$path"
            log_success "Splash arcoíris de RPi restaurado."
        fi
        break
    fi
done

# ─────────────────────────────────────────────────────────────────────────────
# Resumen final
# ─────────────────────────────────────────────────────────────────────────────

systemctl daemon-reload

echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo -e "${GREEN}DESINSTALACIÓN DE SERVICIOS COMPLETADA${NC}"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "Componentes eliminados:"
echo "  ✓ Servicio pos.service (detenido, deshabilitado, eliminado)"
echo "  ✓ Configuración sudoers (/etc/sudoers.d/pos)"
echo "  ✓ Autologin en TTY1"
echo "  ✓ Perfil de screen blanking"
echo "  ✓ Prevención de suspensión (restaurada)"
echo "  ✓ Grupo posadm"
echo "  ✓ Servicios de splash (arranque/apagado)"
echo "  ✓ Parámetros de kernel (texto de arranque restaurado)"
echo ""
echo "Para desinstalar dependencias del sistema:"
echo "  sudo bash scripts/uninstall_deps.sh"
echo ""
log_warning "IMPORTANTE: Reinicie el sistema para aplicar todos los cambios:"
echo "  sudo reboot"
echo ""
