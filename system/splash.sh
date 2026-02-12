#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# TOTTEM POS - Splash Screen Player
# ═══════════════════════════════════════════════════════════════════════════
# Reproduce el video de arranque o apagado en pantalla completa.
# Uso: splash.sh boot | shutdown
# ═══════════════════════════════════════════════════════════════════════════

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VIDEO_BOOT="${APP_DIR}/system/tottem_turn_on.mp4"
VIDEO_SHUTDOWN="${APP_DIR}/system/tottem_turn_off.mp4"

case "$1" in
    boot)
        VIDEO="$VIDEO_BOOT"
        EXTRA_ARGS="--loop=inf"
        ;;
    shutdown)
        VIDEO="$VIDEO_SHUTDOWN"
        EXTRA_ARGS=""
        ;;
    *)
        echo "Uso: $0 {boot|shutdown}"
        exit 1
        ;;
esac

# Salir si el video no existe
if [ ! -f "$VIDEO" ]; then
    exit 0
fi

# Ocultar cursor de consola
printf '\033[?25l' > /dev/tty1 2>/dev/null || true
echo 0 > /sys/class/graphics/fbcon/cursor_blink 2>/dev/null || true

# Limpiar pantalla
printf '\033[2J\033[H' > /dev/tty1 2>/dev/null || true

# Reproducir video con mpv en modo DRM (renderizado directo sin escritorio)
exec /usr/bin/mpv \
    --vo=drm \
    --no-audio \
    --really-quiet \
    --no-terminal \
    --hwdec=auto \
    $EXTRA_ARGS \
    "$VIDEO"
