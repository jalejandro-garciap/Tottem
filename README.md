# TOTTEM POS

<div align="center">

![TOTTEM POS](https://img.shields.io/badge/TOTTEM-POS-3b82f6?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.9+-10b981?style=for-the-badge&logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-Qt6-1d4ed8?style=for-the-badge&logo=qt&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Local-f59e0b?style=for-the-badge&logo=sqlite&logoColor=white)

**Sistema de Punto de Venta minimalista y offline para Raspberry Pi**

</div>

---

## 📋 Descripción

TOTTEM POS es un sistema de punto de venta diseñado para funcionar completamente offline en Raspberry Pi OS Lite. Cuenta con una interfaz táctil fullscreen optimizada para operaciones de caja rápidas y eficientes.

### ✨ Características principales

- 🖥️ **UI Fullscreen** - Interfaz táctil minimalista con PySide6
- 📴 **100% Offline** - Base de datos SQLite local, sin dependencias de red
- 🖨️ **Impresión ESC/POS** - Soporte para impresoras térmicas de 80mm
- 💰 **Cash Drawer** - Control de caja automático RJ-11
- 📊 **Reportes** - Cortes de caja (X/Z) con detalle de transacciones
- 🔒 **Seguridad** - PIN de administrador con hash Argon2
- 🌐 **Multiidioma** - Español e Inglés

---

## 🔧 Requisitos de Hardware

| Componente | Especificación |
|------------|----------------|
| **SBC** | Raspberry Pi 3B+ o superior (64-bit recomendado) |
| **OS** | Raspberry Pi OS Lite (sin escritorio) |
| **Pantalla** | Monitor táctil HDMI (7" a 22") |
| **Impresora** | Térmica 80mm ESC/POS (USB) |
| **Caja** | Automática RJ-11 (conectada a impresora) |
| **Almacenamiento** | microSD 16GB+ (Class 10) |

---

## 🚀 Instalación

### 1. Preparar Raspberry Pi

```bash
# Descargar Raspberry Pi OS Lite (64-bit) desde:
# https://www.raspberrypi.org/software/operating-systems/

# Flashear imagen con Raspberry Pi Imager
# Habilitar SSH en la configuración avanzada
```

### 2. Clonar repositorio

```bash
# Conectarse por SSH a la Raspberry
ssh pi@raspberrypi.local

# Actualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar git
sudo apt install -y git

# Clonar repositorio
git clone https://github.com/tu-usuario/Tottem.git
cd Tottem
```

### 3. Ejecutar instalador

```bash
# Instalar dependencias del sistema y Python
bash scripts/install_deps.sh
```

### 4. Probar la aplicación

```bash
# Activar entorno virtual
source .venv/bin/activate

# Ejecutar kiosk (punto de venta)
pos run-kiosk

# O ejecutar panel de administración
pos run-admin
```

### 5. Configurar como servicio (arranque automático)

```bash
# Configurar servicio systemd
sudo bash scripts/setup_services.sh

# Reiniciar para aplicar cambios
sudo reboot
```

---

## 📁 Estructura del Proyecto

```
Tottem/
├── config/
│   ├── config.yaml          # Configuración principal
│   └── config.schema.yaml   # Esquema de validación
├── migrations/
│   └── *.sql                # Scripts de base de datos
├── scripts/
│   ├── install_deps.sh      # Instalador de dependencias
│   └── setup_services.sh    # Configurador de servicio
├── src/
│   ├── cli.py               # Comandos CLI
│   ├── core/
│   │   ├── db.py            # Conexión a base de datos
│   │   └── settings.py      # Gestión de configuración
│   ├── drivers/
│   │   ├── hw_detect.py     # Detección de hardware
│   │   └── printer_escpos.py # Driver de impresora
│   ├── services/
│   │   ├── auth.py          # Autenticación
│   │   ├── employees.py     # Gestión de empleados
│   │   ├── i18n.py          # Internacionalización
│   │   ├── products.py      # Catálogo de productos
│   │   ├── receipts.py      # Generación de tickets
│   │   ├── reports.py       # Reportes y cortes
│   │   ├── sales.py         # Lógica de ventas
│   │   └── shifts.py        # Control de turnos
│   └── ui/
│       ├── kiosk_app.py     # Aplicación kiosk
│       ├── admin_app.py     # Aplicación admin
│       ├── theme.qss        # Estilos visuales
│       └── widgets/
│           ├── kiosk_window.py  # Ventana principal POS
│           ├── admin_window.py  # Panel administración
│           ├── keypad.py        # Teclado numérico
│           └── osk.py           # Teclado en pantalla
├── system/
│   ├── pos.service          # Archivo de servicio systemd
│   └── sudoers.d/pos        # Permisos sudo
├── data.db                  # Base de datos SQLite
├── pyproject.toml           # Dependencias Python
└── README.md
```

---

## ⚙️ Configuración

### Archivo `config/config.yaml`

```yaml
store:
  name: "Mi Tienda"
  rfc: "XAXX010101000"
  ticket_header: "Mi Tienda\n\nRFC: XAXX010101000\n\n"
  ticket_footer: "Gracias por su compra\n\n"

hardware:
  printer:
    vendor_id: 0x0416    # ID del fabricante USB
    product_id: 0x5011   # ID del producto USB
    interface: 0
    out_ep: 0x03         # USB endpoint OUT
    in_ep: 0x82          # USB endpoint IN

ui:
  font_family: "Sans"
  kiosk_fullscreen: true
  categories_enabled: false

security:
  admin_pin_hash: "..."  # Hash Argon2 del PIN

notifications:
  recent_emails: []
```

### Encontrar IDs USB de la impresora

```bash
# Listar dispositivos USB
lsusb

# Ejemplo de salida:
# Bus 001 Device 004: ID 0416:5011 Some Printer
#                        ^^^^:^^^^
#                        vendor:product
```

---

## 💻 Comandos CLI

```bash
# Activar entorno virtual
source .venv/bin/activate

# Ejecutar kiosk (punto de venta)
pos run-kiosk

# Ejecutar panel de administración
pos run-admin

# Imprimir prueba de impresora
pos print-test

# Abrir caja registradora
pos drawer-open

# Reporte X (preview del turno actual)
pos x-report

# Reporte Z (cierre de turno)
pos z-report --closed-by "Juan" --closing-cash 150000
```

---

## 🖨️ Impresoras Compatibles

| Marca | Modelo | Status |
|-------|--------|--------|
| Epson | TM-T20/T88 | ✅ Probado |
| Star Micronics | TSP100/650 | ✅ Probado |
| Genérica China | 80mm USB | ✅ Probado |

---

## 📊 Cortes de Caja

### Reporte X (Preview)
- Muestra totales del turno actual sin cerrarlo
- Útil para verificar antes del cierre

### Reporte Z (Cierre)
- Cierra el turno actual
- Imprime reporte detallado con:
  - Resumen de ventas
  - Total de transacciones
  - Cuadre de caja (efectivo esperado vs contado)
  - Detalle de cada ticket y sus productos
- Se archiva el turno cerrado

---

## 🔒 Seguridad

- **PIN de administrador**: Acceso al panel de configuración
- **Hash Argon2**: Almacenamiento seguro de credenciales
- **Sin conexión a internet**: Datos 100% locales

### Cambiar PIN de administrador

1. Entrar al panel de administración
2. Ir a la pestaña "Seguridad"
3. Ingresar PIN actual y nuevo PIN
4. Guardar cambios

**PIN por defecto**: `123`

---

## 🐛 Solución de Problemas

### La pantalla parpadea o no se muestra

```bash
# Verificar que el servicio está corriendo
sudo systemctl status pos.service

# Ver logs
sudo journalctl -u pos.service -f
```

### La impresora no funciona

```bash
# Verificar conexión USB
lsusb

# Verificar permisos
ls -la /dev/usb*

# Probar impresión manual
pos print-test
```

### La base de datos está corrupta

```bash
# Hacer backup
cp data.db data.db.backup

# Recrear desde migraciones
rm data.db
for f in migrations/*.sql; do sqlite3 data.db < "$f"; done
```

### Reiniciar servicio

```bash
sudo systemctl restart pos.service
```

---

## 📄 Licencia

Este proyecto es software propietario. Todos los derechos reservados.

---

## 🤝 Soporte

Para soporte técnico, contactar al equipo de desarrollo.
