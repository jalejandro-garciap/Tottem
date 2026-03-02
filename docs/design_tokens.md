# TOTTEM POS · Obsidian Design System

Sistema de diseño premium para interfaces táctiles de punto de venta.

## Filosofía de Diseño

**"Dark elegance meets functional minimalism"**

El diseño Obsidian Edition prioriza:
- **Contraste extremo** para legibilidad en cualquier condición de luz
- **Jerarquía visual clara** mediante tipografía y espaciado
- **Touch-first** con objetivos táctiles de mínimo 56px (escalados)
- **Retroalimentación visual inmediata** en todas las interacciones
- **Adaptabilidad** para pantallas de 12" a 22"

---

## Paleta de Colores

### Fondos
| Token | Valor | Uso |
|-------|-------|-----|
| Background Deep | `#0a0a0f` | Fondo principal (Obsidian) |
| Background Mid | `#12121a` | Paneles y contenedores (Onyx) |
| Surface | `#1a1a24` | Tarjetas y elementos elevados (Slate) |
| Surface Elevated | `#22222e` | Hover states y elementos activos |

### Texto
| Token | Valor | Uso |
|-------|-------|-----|
| Text Primary | `#f8fafc` | Títulos y texto principal (Snow) |
| Text Secondary | `#94a3b8` | Texto secundario (Mist) |
| Text Muted | `#64748b` | Labels y hints (Fog) |

### Acentos
| Token | Valor | Uso |
|-------|-------|-----|
| Accent Primary | `#6366f1` | Botones primarios, links (Indigo) |
| Accent Glow | `#818cf8` | Hover states, highlights |
| Success | `#10b981` | Confirmaciones, totales positivos (Emerald) |
| Warning | `#f59e0b` | Alertas, estados pendientes (Amber) |
| Danger | `#ef4444` | Errores, acciones destructivas (Rose) |

---

## Tipografía

### Jerarquía (valores base @1920×1080)
```
Hero Display    → 56px / 800 / -2px tracking
Section Title   → 24px / 700 / -0.5px tracking
Body Large      → 16px / 500
Body            → 15px / 500
Label           → 12px / 700 / 3px tracking / UPPERCASE
```

> **Nota**: Todos los valores se escalan dinámicamente con `s(px)` según la resolución de pantalla. Ver sección "Sistema Responsive" más abajo.

### Font Stack
```css
font-family: "SF Pro Display", "Inter", "Segoe UI", -apple-system, sans-serif;
```

---

## Espaciado

### Contenedores (valores base)
- **Padding exterior**: 16–24px
- **Padding interior**: 20–32px
- **Gap entre elementos**: 12–16px
- **Border radius**: 16–28px

### Botones
- **Altura mínima**: 56px (controles), 72–80px (acciones principales)
- **Padding horizontal**: 20–28px
- **Border radius**: 16–20px

---

## Sistema Responsive

### Módulo `ui/responsive.py`

El sistema calcula un factor de escala único al arrancar la aplicación:

```
scale = min(screen_width / 1920, screen_height / 1080)
piso  = 0.55  (≈ pantallas 12" @ 1366×768)
techo = 1.0   (pantallas 22" @ 1920×1080 o mayor)
```

### Función `s(px)`

Convierte cualquier valor en píxeles al tamaño adaptado:

```python
from ui.responsive import s

widget.setMinimumHeight(s(56))   # → 56px en 22", 31px en 12"
widget.setContentsMargins(s(24), s(24), s(24), s(24))
```

### Tabla de Escalado

| Pantalla | Resolución | Factor | Botón 56px → | Título 24px → |
|----------|-----------|--------|-------------|---------------|
| 12" | 1366×768 | 0.71 | 40px | 17px |
| 14" | 1600×900 | 0.83 | 47px | 20px |
| 15.6" | 1920×1080 | 1.00 | 56px | 24px |
| 22" | 1920×1080 | 1.00 | 56px | 24px |

### Integración

- **Código Python**: Todos los `setMinimumHeight`, `setContentsMargins`, `setSpacing` y `setStyleSheet` con `font-size` usan `s()`.
- **QSS generado**: La función `generate_qss()` en `themes.py` usa `_s()` para escalar todos los tamaños en el stylesheet dinámico.
- **QSS estático** (`theme.qss`): Sirve como fallback; los tamaños definidos en código Python tienen prioridad.

---

## Responsive Breakpoints

| Pantalla | Ancho | Columnas Grid | Cart Width |
|----------|-------|---------------|------------|
| 12" | ≤1280px | 3–4 | ~280px |
| 14" | ≤1600px | 4–5 | ~340px |
| 15.6" | ≤1920px | 5–6 | ~400px |
| 22"+ | >1920px | 5–8 | ~460px |

---

## Componentes

### Botones
```
Primary   → Gradiente Indigo, texto blanco, sin borde
Success   → Gradiente Emerald, texto blanco
Danger    → Fondo transparente con tinte rojo, borde sutil
Ghost     → Completamente transparente, hover revela fondo
```

### Inputs
```
Default   → Borde #2a2a3a, fondo #12121a
Focus     → Borde #6366f1 (Indigo)
Error     → Borde #ef4444, fondo con tinte rojo
Success   → Borde #10b981, fondo con tinte verde
```

### Listas
```
Item      → Fondo #16161e, border-radius 14px
Selected  → Gradiente lateral Indigo, borde izquierdo 4px
Hover     → Fondo #1e1e2a
```

---

## Animaciones

Qt no soporta transiciones CSS nativas, pero los estados visuales simulan fluidez:
- **Pressed**: Desplazamiento de padding (efecto de presión)
- **Hover**: Cambio de color de fondo/borde
- **Focus**: Borde de acento visible

---

## Cursor Dinámico

El cursor del ratón se gestiona dinámicamente por `ui/mouse_manager.py`:

- **Sin ratón USB**: Cursor completamente oculto (`Qt.BlankCursor`). Ideal para operación táctil exclusiva.
- **Con ratón USB**: Cursor estándar (`Qt.ArrowCursor`) visible automáticamente.
- **Detección**: Polling cada 2 segundos de `/sys/class/input/event*/device/capabilities/rel`.
- **Transición**: Al conectar/desconectar un ratón, el cambio es automático sin reiniciar la app.

---

## Iconografía

Se usa Font Awesome 6 Free (Solid) con fallback a emojis Unicode:
```
🔐 Seguridad     🖨 Impresora     🏪 Tienda
📦 Productos     📊 Turnos        📈 Reportes
💻 Sistema       ⚙ Configuración  👤 Empleado
```

---

## Archivos del Sistema

| Archivo | Responsabilidad |
|---------|----------------|
| `src/ui/responsive.py` | Factor de escala y helpers `s()`, `font_css()` |
| `src/ui/mouse_manager.py` | Detección de ratón USB y gestión de cursor |
| `src/services/themes.py` | Generación de QSS escalado (`generate_qss()`) |
| `src/ui/theme.qss` | Estilos QSS estáticos (fallback) |
| `src/ui/widgets/kiosk_window.py` | Interfaz de venta |
| `src/ui/widgets/admin_window.py` | Panel de administración |
| `src/ui/widgets/keypad.py` | Teclado numérico |
| `src/ui/widgets/osk.py` | Teclado en pantalla |
