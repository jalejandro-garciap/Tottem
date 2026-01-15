# TOTTEM POS · Obsidian Design System

Sistema de diseño premium para interfaces táctiles de punto de venta.

## Filosofía de Diseño

**"Dark elegance meets functional minimalism"**

El diseño Obsidian Edition prioriza:
- **Contraste extremo** para legibilidad en cualquier condición de luz
- **Jerarquía visual clara** mediante tipografía y espaciado
- **Touch-first** con objetivos táctiles de mínimo 56px
- **Retroalimentación visual inmediata** en todas las interacciones

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

### Jerarquía
```
Hero Display    → 56px / 800 / -2px tracking
Section Title   → 24px / 700 / -0.5px tracking
Body Large      → 16px / 500
Body            → 15px / 500
Label           → 12px / 700 / 3px tracking / UPPERCASE
```

### Font Stack
```css
font-family: "SF Pro Display", "Inter", "Segoe UI", -apple-system, sans-serif;
```

---

## Espaciado

### Contenedores
- **Padding exterior**: 16-24px
- **Padding interior**: 20-32px
- **Gap entre elementos**: 12-16px
- **Border radius**: 16-28px

### Botones
- **Altura mínima**: 56px (controles), 72-80px (acciones principales)
- **Padding horizontal**: 20-28px
- **Border radius**: 16-20px

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

## Responsive Breakpoints

| Pantalla | Ancho | Columnas Grid | Cart Width |
|----------|-------|---------------|------------|
| 7" | ≤800px | 2-3 | 280px |
| 10" | ≤1024px | 3-4 | 340px |
| 12" | ≤1280px | 4-5 | 400px |
| 22"+ | >1280px | 5-8 | 460px |

---

## Iconografía

Uso de emojis Unicode para máxima compatibilidad:
```
🔐 Seguridad     🖨 Impresora     🏪 Tienda
📦 Productos     📊 Turnos        📈 Reportes
💻 Sistema       ⚙ Configuración  👤 Empleado
```

---

## Archivos del Sistema

- `src/ui/theme.qss` → Estilos globales QSS
- `src/ui/widgets/kiosk_window.py` → Interfaz de venta
- `src/ui/widgets/admin_window.py` → Panel de administración
- `src/ui/widgets/keypad.py` → Teclado numérico
- `src/ui/widgets/osk.py` → Teclado en pantalla
