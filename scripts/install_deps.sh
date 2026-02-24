#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# TOTTEM POS - Instalación de Dependencias
# ═══════════════════════════════════════════════════════════════════════════
# Este script instala todas las dependencias necesarias para ejecutar
# TOTTEM POS en Raspberry Pi OS Lite (sin escritorio).
#
# Uso: bash scripts/install_deps.sh
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
# 1. Verificar que estamos en el directorio correcto
# ─────────────────────────────────────────────────────────────────────────────

if [ ! -f "pyproject.toml" ]; then
    log_error "Este script debe ejecutarse desde el directorio raíz del proyecto."
    log_error "Uso: cd /ruta/a/Tottem && bash scripts/install_deps.sh"
    exit 1
fi

log_info "Iniciando instalación de TOTTEM POS..."
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 2. Actualizar sistema
# ─────────────────────────────────────────────────────────────────────────────

log_info "Actualizando lista de paquetes..."
sudo apt update

log_info "Actualizando paquetes existentes..."
sudo apt upgrade -y

# ─────────────────────────────────────────────────────────────────────────────
# 3. Instalar dependencias del sistema
# ─────────────────────────────────────────────────────────────────────────────

log_info "Instalando dependencias del sistema..."

# Python y herramientas de compilación
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    pkg-config

# Librerías para Qt6/PySide6 en framebuffer
# Nota: Algunos paquetes tienen sufijo t64 en Debian 13+ / RPi OS Bookworm
sudo apt install -y \
    libxcb-cursor0 \
    libxkbcommon0 \
    libinput10 || sudo apt install -y libinput-dev \
    libmtdev1t64 || sudo apt install -y libmtdev1 || true \
    libudev1 \
    libxcb-xinerama0 \
    libxcb-xfixes0 \
    libxcb-shape0 \
    libxcb-render0 \
    libxcb-render-util0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-shm0 \
    libxcb-sync1 \
    libxcb-xkb1 \
    libxkbcommon-x11-0 \
    libfontconfig1 \
    libfreetype6 \
    libdbus-1-3

# Librerías OpenGL/EGL (nombres actualizados para Debian 12+/Bookworm)
sudo apt install -y \
    libegl1 \
    libgles2 \
    libgl1 \
    libglx-mesa0 \
    libopengl0 \
    libglvnd0 \
    libdrm2 \
    libgbm1 || true

# Para acceso a USB (impresoras ESC/POS)
sudo apt install -y \
    libusb-1.0-0-dev \
    libudev-dev

# Herramientas de terminal y reproductor de video
sudo apt install -y \
    kbd \
    console-setup \
    mpv

log_success "Dependencias del sistema instaladas."

# ─────────────────────────────────────────────────────────────────────────────
# 4. Crear entorno virtual de Python
# ─────────────────────────────────────────────────────────────────────────────

log_info "Creando entorno virtual de Python..."

if [ -d ".venv" ]; then
    log_warning "Entorno virtual existente encontrado. Recreando..."
    rm -rf .venv
fi

python3 -m venv .venv

log_info "Actualizando pip..."
.venv/bin/pip install --upgrade pip wheel setuptools

log_success "Entorno virtual creado."

# ─────────────────────────────────────────────────────────────────────────────
# 5. Instalar dependencias de Python
# ─────────────────────────────────────────────────────────────────────────────

log_info "Instalando dependencias de Python..."

# Instalar el proyecto en modo editable
.venv/bin/pip install -e .

log_success "Dependencias de Python instaladas."

# ─────────────────────────────────────────────────────────────────────────────
# 6. Configurar permisos USB para impresora
# ─────────────────────────────────────────────────────────────────────────────

log_info "Configurando permisos USB..."

# Crear regla udev para impresoras térmicas comunes
sudo tee /etc/udev/rules.d/99-escpos.rules > /dev/null << 'EOF'
# Reglas para impresoras ESC/POS USB
# Epson TM series
SUBSYSTEM=="usb", ATTR{idVendor}=="04b8", MODE="0666"
# Star Micronics
SUBSYSTEM=="usb", ATTR{idVendor}=="0519", MODE="0666"
# Generic Chinese printers (común en impresoras económicas)
SUBSYSTEM=="usb", ATTR{idVendor}=="0416", MODE="0666"
SUBSYSTEM=="usb", ATTR{idVendor}=="0483", MODE="0666"
SUBSYSTEM=="usb", ATTR{idVendor}=="1fc9", MODE="0666"
SUBSYSTEM=="usb", ATTR{idVendor}=="1a86", MODE="0666"
# Permitir acceso general a dispositivos USB
SUBSYSTEM=="usb", MODE="0666"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger

# Agregar usuario al grupo dialout para acceso serial
sudo usermod -aG dialout ${SUDO_USER:-$USER} || true
sudo usermod -aG plugdev ${SUDO_USER:-$USER} || true

log_success "Permisos USB configurados."

# ─────────────────────────────────────────────────────────────────────────────
# 7. Crear base de datos inicial
# ─────────────────────────────────────────────────────────────────────────────

log_info "Inicializando base de datos..."

# Instalar sqlite3 si no está disponible
if ! command -v sqlite3 &> /dev/null; then
    log_info "Instalando sqlite3..."
    sudo apt install -y sqlite3
fi

# Ejecutar migraciones SQL en orden
if [ -d "migrations" ]; then
    for sql_file in $(ls migrations/*.sql 2>/dev/null | sort); do
        if [ -f "$sql_file" ]; then
            log_info "Aplicando: $(basename $sql_file)"
            sqlite3 data.db < "$sql_file" || log_warning "Migración ya aplicada o error: $(basename $sql_file)"
        fi
    done
else
    log_warning "Directorio migrations/ no encontrado"
fi

# Verificar que las tablas existen
TABLES=$(sqlite3 data.db ".tables" 2>/dev/null || echo "")
if echo "$TABLES" | grep -q "product"; then
    log_success "Base de datos inicializada correctamente."
    log_info "Tablas: $TABLES"
else
    log_error "ERROR: Las tablas no se crearon correctamente."
    log_error "Ejecuta manualmente: for f in migrations/*.sql; do sqlite3 data.db < \"\$f\"; done"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 8. Crear directorios necesarios
# ─────────────────────────────────────────────────────────────────────────────

log_info "Creando directorios..."

mkdir -p config
mkdir -p logs

# Crear config.yaml si no existe
if [ ! -f "config/config.yaml" ]; then
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
  admin_pin_hash: "$argon2id$v=19$m=65536,t=3,p=4$JFE4XiXJTD9iEGWnQdnmuw$G9953rMEA4eGchNqHDFj6FhJZqTf2AlWlk38juIO7/w"

settings:
  categories_enabled: false
  language: "es"
EOF
    log_success "Archivo de configuración creado."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 10. Prevenir suspensión / hibernación del equipo
# ─────────────────────────────────────────────────────────────────────────────

log_info "Deshabilitando suspensión e hibernación..."

# Mask targets de suspensión para que nunca se activen
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true

# Configurar logind para ignorar cierre de tapa e inactividad
LOGIND_CONF="/etc/systemd/logind.conf"
if [ -f "$LOGIND_CONF" ]; then
    # Respaldar el original si no existe respaldo
    if [ ! -f "${LOGIND_CONF}.bak.tottem" ]; then
        sudo cp "$LOGIND_CONF" "${LOGIND_CONF}.bak.tottem"
    fi

    # Asegurar que las opciones existan con los valores correctos
    for opt in "HandleLidSwitch=ignore" "HandleLidSwitchExternalPower=ignore" "HandleLidSwitchDocked=ignore" "IdleAction=ignore"; do
        key="${opt%%=*}"
        if sudo grep -q "^${key}=" "$LOGIND_CONF" 2>/dev/null; then
            sudo sed -i "s/^${key}=.*/${opt}/" "$LOGIND_CONF"
        elif sudo grep -q "^#${key}=" "$LOGIND_CONF" 2>/dev/null; then
            sudo sed -i "s/^#${key}=.*/${opt}/" "$LOGIND_CONF"
        else
            echo "$opt" | sudo tee -a "$LOGIND_CONF" > /dev/null
        fi
    done

    # Reiniciar logind para aplicar cambios
    sudo systemctl restart systemd-logind 2>/dev/null || true
fi

log_success "Suspensión e hibernación deshabilitadas."
# ─────────────────────────────────────────────────────────────────────────────
# 9. Resumen final
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo -e "${GREEN}INSTALACIÓN COMPLETADA${NC}"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "Para probar la aplicación:"
echo "  1. Activar entorno virtual: source .venv/bin/activate"
echo "  2. Ejecutar kiosk:          pos run-kiosk"
echo "  3. Ejecutar admin:          pos run-admin"
echo ""
echo "Para instalar como servicio del sistema:"
echo "  bash scripts/setup_services.sh"
echo ""
echo "PIN de administrador por defecto: 1234"
echo "(Cámbielo desde el panel de administración)"
echo ""
log_warning "IMPORTANTE: Reinicie la sesión para aplicar permisos USB."
echo ""
