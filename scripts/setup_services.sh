#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# TOTTEM POS - Configuración de Servicio Systemd
# ═══════════════════════════════════════════════════════════════════════════
# Este script configura TOTTEM POS como un servicio del sistema que
# arranca automáticamente al encender la Raspberry Pi.
#
# Uso: sudo bash scripts/setup_services.sh
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

# Verificar si somos root (compatible con sh y bash)
if [ "$(id -u)" -ne 0 ]; then
    log_error "Este script debe ejecutarse con sudo."
    log_error "Uso: sudo bash scripts/setup_services.sh"
    exit 1
fi

if [ ! -f "pyproject.toml" ]; then
    log_error "Este script debe ejecutarse desde el directorio raíz del proyecto."
    exit 1
fi

# Obtener el directorio actual y el usuario
APP_DIR="$(pwd)"
APP_USER="${SUDO_USER:-$USER}"
APP_GROUP="$(id -gn $APP_USER)"

log_info "Configurando servicio TOTTEM POS..."
log_info "Directorio: $APP_DIR"
log_info "Usuario: $APP_USER"

# ─────────────────────────────────────────────────────────────────────────────
# 1. Crear grupo de administración POS
# ─────────────────────────────────────────────────────────────────────────────

log_info "Configurando grupos..."

groupadd -f posadm || true
usermod -aG posadm "$APP_USER" || true

log_success "Grupos configurados."

# ─────────────────────────────────────────────────────────────────────────────
# 2. Generar archivo de servicio personalizado
# ─────────────────────────────────────────────────────────────────────────────

log_info "Generando archivo de servicio..."

cat > /etc/systemd/system/pos.service << EOF
[Unit]
Description=TOTTEM POS - Punto de Venta (linuxfb)
After=network.target local-fs.target
Wants=network.target
Conflicts=getty@tty1.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR
Environment=PYTHONUNBUFFERED=1
Environment=QT_QPA_PLATFORM=linuxfb
Environment=QT_QPA_FB_FORCE_FULLSCREEN=1
Environment=QT_QPA_FONTDIR=/usr/share/fonts
Environment=QT_LOGGING_RULES=*.debug=false

# Ejecutar en TTY1 para control del framebuffer
TTYPath=/dev/tty1
StandardInput=tty
StandardOutput=inherit
StandardError=inherit
TTYVHangup=yes
TTYVTDisallocate=yes

# Preparar la consola antes de iniciar
ExecStartPre=-/bin/systemctl stop tottem-splash.service
ExecStartPre=/bin/sh -lc 'echo 0 > /sys/class/graphics/fbcon/cursor_blink 2>/dev/null || true'
ExecStartPre=/bin/sh -lc "printf '\\033[?25l' > /dev/tty1 || true"
ExecStartPre=/bin/sh -lc 'chvt 1 && setterm -cursor off -blank 0 -powersave off -clear all </dev/tty1 2>/dev/null || true'

# Iniciar el kiosk
ExecStart=$APP_DIR/.venv/bin/pos run-kiosk

# Al detener: iniciar animación de apagado
ExecStopPost=-/bin/systemctl start tottem-splash-shutdown.service

# Restaurar la consola al salir
ExecStopPost=/bin/sh -lc "printf '\\033[?25h' > /dev/tty1 || true"
ExecStopPost=/bin/sh -lc 'echo 1 > /sys/class/graphics/fbcon/cursor_blink 2>/dev/null || true'
ExecStopPost=/bin/sh -lc 'setterm -cursor on </dev/tty1 2>/dev/null || true'

User=$APP_USER
Group=$APP_GROUP
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

log_success "Archivo de servicio generado."

# ─────────────────────────────────────────────────────────────────────────────
# 3. Configurar sudoers para operaciones de sistema
# ─────────────────────────────────────────────────────────────────────────────

log_info "Configurando permisos sudo..."

mkdir -p /etc/sudoers.d

cat > /etc/sudoers.d/pos << EOF
# Permisos para TOTTEM POS
# Permite al grupo posadm ejecutar comandos de sistema necesarios

%posadm ALL=(ALL) NOPASSWD: /sbin/reboot
%posadm ALL=(ALL) NOPASSWD: /sbin/poweroff
%posadm ALL=(ALL) NOPASSWD: /sbin/shutdown
%posadm ALL=(ALL) NOPASSWD: /usr/bin/nmcli
%posadm ALL=(ALL) NOPASSWD: /bin/systemctl restart pos.service
%posadm ALL=(ALL) NOPASSWD: /bin/systemctl stop pos.service
%posadm ALL=(ALL) NOPASSWD: /bin/systemctl start pos.service
EOF

chmod 440 /etc/sudoers.d/pos

log_success "Permisos sudo configurados."

# ─────────────────────────────────────────────────────────────────────────────
# 4. Configurar autologin en TTY1 (opcional pero recomendado)
# ─────────────────────────────────────────────────────────────────────────────

log_info "Configurando autologin..."

mkdir -p /etc/systemd/system/getty@tty1.service.d

cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $APP_USER --noclear %I \$TERM
EOF

log_success "Autologin configurado."

# ─────────────────────────────────────────────────────────────────────────────
# 5. Habilitar y arrancar el servicio
# ─────────────────────────────────────────────────────────────────────────────

log_info "Habilitando servicio..."

systemctl daemon-reload
systemctl enable pos.service

log_success "Servicio POS habilitado."

# ─────────────────────────────────────────────────────────────────────────────
# 5b. Configurar splash de arranque y apagado
# ─────────────────────────────────────────────────────────────────────────────

log_info "Configurando animaciones de arranque y apagado..."

# Hacer splash.sh ejecutable
chmod +x "$APP_DIR/system/splash.sh"

# --- Servicio de boot splash ---
cat > /etc/systemd/system/tottem-splash.service << EOF
[Unit]
Description=TOTTEM POS - Animación de Arranque
DefaultDependencies=no
After=local-fs.target
Before=pos.service
ConditionPathExists=$APP_DIR/system/tottem_turn_on.mp4

[Service]
Type=simple
ExecStart=$APP_DIR/system/splash.sh boot
TTYPath=/dev/tty1
StandardInput=tty
StandardOutput=null
StandardError=null

[Install]
WantedBy=sysinit.target
EOF

# --- Servicio de shutdown splash ---
cat > /etc/systemd/system/tottem-splash-shutdown.service << EOF
[Unit]
Description=TOTTEM POS - Animación de Apagado
DefaultDependencies=no
Before=systemd-reboot.service systemd-poweroff.service systemd-halt.service
Before=umount.target
ConditionPathExists=$APP_DIR/system/tottem_turn_off.mp4

[Service]
Type=simple
ExecStart=$APP_DIR/system/splash.sh shutdown
TTYPath=/dev/tty1
StandardInput=tty
StandardOutput=null
StandardError=null
TimeoutStartSec=30
TimeoutStopSec=5

[Install]
WantedBy=reboot.target poweroff.target halt.target
EOF

systemctl daemon-reload
systemctl enable tottem-splash.service
systemctl enable tottem-splash-shutdown.service

log_success "Animaciones de arranque y apagado configuradas."

# ─────────────────────────────────────────────────────────────────────────────
# 6. Configuraciones adicionales del sistema
# ─────────────────────────────────────────────────────────────────────────────

log_info "Aplicando configuraciones adicionales..."

# Desactivar screen blanking
cat > /etc/profile.d/pos-console.sh << 'EOF'
# Desactivar screen blanking para POS
setterm -blank 0 -powersave off 2>/dev/null || true
EOF

# Prevenir suspensión e hibernación
log_info "Deshabilitando suspensión e hibernación..."
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true

# Configurar logind para ignorar cierre de tapa e inactividad
LOGIND_CONF="/etc/systemd/logind.conf"
if [ -f "$LOGIND_CONF" ]; then
    if [ ! -f "${LOGIND_CONF}.bak.tottem" ]; then
        cp "$LOGIND_CONF" "${LOGIND_CONF}.bak.tottem"
    fi
    for opt in "HandleLidSwitch=ignore" "HandleLidSwitchExternalPower=ignore" "HandleLidSwitchDocked=ignore" "IdleAction=ignore"; do
        key="${opt%%=*}"
        if grep -q "^${key}=" "$LOGIND_CONF" 2>/dev/null; then
            sed -i "s/^${key}=.*/${opt}/" "$LOGIND_CONF"
        elif grep -q "^#${key}=" "$LOGIND_CONF" 2>/dev/null; then
            sed -i "s/^#${key}=.*/${opt}/" "$LOGIND_CONF"
        else
            echo "$opt" >> "$LOGIND_CONF"
        fi
    done
    systemctl restart systemd-logind 2>/dev/null || true
fi
log_success "Suspensión e hibernación deshabilitadas."

# Configurar resolución de pantalla si es necesario (para monitores comunes)
# Detectar ubicación de config.txt (Bookworm vs versiones anteriores)
BOOT_CONFIG=""
if [ -f /boot/firmware/config.txt ]; then
    BOOT_CONFIG="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    BOOT_CONFIG="/boot/config.txt"
fi

if [ -n "$BOOT_CONFIG" ]; then
    if ! grep -q "disable_overscan=1" "$BOOT_CONFIG"; then
        echo "" >> "$BOOT_CONFIG"
        echo "# TOTTEM POS - Configuración de pantalla" >> "$BOOT_CONFIG"
        echo "disable_overscan=1" >> "$BOOT_CONFIG"
        echo "hdmi_force_hotplug=1" >> "$BOOT_CONFIG"
        log_success "Configuración de pantalla actualizada."
    fi

    # Desactivar el splash arcoíris de Raspberry Pi
    if ! grep -q "disable_splash=1" "$BOOT_CONFIG"; then
        echo "disable_splash=1" >> "$BOOT_CONFIG"
        log_success "Splash arcoíris de RPi deshabilitado."
    fi
fi

# Ocultar texto de arranque del kernel
# Detectar ubicación de cmdline.txt
CMDLINE=""
if [ -f /boot/firmware/cmdline.txt ]; then
    CMDLINE="/boot/firmware/cmdline.txt"
elif [ -f /boot/cmdline.txt ]; then
    CMDLINE="/boot/cmdline.txt"
fi

if [ -n "$CMDLINE" ]; then
    # Respaldar cmdline original
    if [ ! -f "${CMDLINE}.bak.tottem" ]; then
        cp "$CMDLINE" "${CMDLINE}.bak.tottem"
    fi

    # Agregar parámetros para ocultar texto de arranque
    CURRENT=$(cat "$CMDLINE")
    MODIFIED="$CURRENT"

    for param in "quiet" "loglevel=0" "logo.nologo" "vt.global_cursor_default=0"; do
        if ! echo "$MODIFIED" | grep -q "$param"; then
            MODIFIED="$MODIFIED $param"
        fi
    done

    if [ "$CURRENT" != "$MODIFIED" ]; then
        echo "$MODIFIED" > "$CMDLINE"
        log_success "Parámetros de kernel actualizados para ocultar texto de arranque."
    fi
fi

log_success "Configuraciones adicionales aplicadas."

# ─────────────────────────────────────────────────────────────────────────────
# Resumen final
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo -e "${GREEN}SERVICIO CONFIGURADO${NC}"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "Comandos útiles:"
echo "  Iniciar servicio:    sudo systemctl start pos.service"
echo "  Detener servicio:    sudo systemctl stop pos.service"
echo "  Reiniciar servicio:  sudo systemctl restart pos.service"
echo "  Ver estado:          sudo systemctl status pos.service"
echo "  Ver logs:            sudo journalctl -u pos.service -f"
echo ""
echo "El servicio se iniciará automáticamente al arrancar el sistema."
echo ""
log_warning "IMPORTANTE: Reinicie el sistema para aplicar todos los cambios:"
echo "  sudo reboot"
echo ""
