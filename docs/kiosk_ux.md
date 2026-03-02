# Flujo táctil del kiosko

Este resumen mapea las pantallas clave del kiosko (PySide6) y define reglas de jerarquía visual, búsqueda y confirmaciones para simplificar ventas rápidas.

## 1) Mapa de pantallas

- **Inicio / venta rápida**
  - Se muestra el catálogo en cuadrícula (por categorías si están activadas) y un carrito compacto a la derecha.
  - Acciones rápidas: agregar producto, aumentar/disminuir cantidad, vaciar carrito, alternar idioma y reimprimir último ticket.
- **Selección de productos**
  - Vista de categorías ➝ lista de categorías en tarjetas grandes. CTA secundario: "Atrás" para regresar al catálogo general.
  - Vista de productos ➝ botones grandes con nombre, precio y unidad; tapping agrega al carrito. Si un producto permite decimales, abrir keypad numérico.
  - Búsqueda/filtros: teclado táctil persistente o filtros visibles (categoría, precio, disponibilidad) colocados arriba de la cuadrícula.
- **Checkout y pagos**
  - Resumen de carrito con total grande y editable.
  - Botón principal "Cobrar" abre el diálogo de pago.
  - Diálogo de pago: montos rápidos ($20–$1000), opción "Exacto" y "Otro monto" con keypad; mostrar recibido y cambio en tipografía grande.
  - Confirmación final: ticket impreso, mensaje de éxito y botón "Nueva venta" (reinicia carrito).

## 2) Jerarquía visual

- **CTA principal**: resaltar "Cobrar / Imprimir" (rol primario). Tamaño mínimo `s(56)`px de alto y ancho expandible en desktop táctil.
- **Acciones secundarias**: estilo "ghost" o bordes neutros para reimprimir, idioma, admin y limpiar carrito. Agrupar en barras horizontales con espacio amplio entre ellas.
- **Agrupación**: usar paneles con sombra suave para separar (a) catálogo, (b) carrito y (c) pagos. Títulos con `SectionTitle` para cada bloque.
- **Estados**: hover/pressed según `theme.qss`; feedback de error en rojo y éxito en acento primario.

## 3) Búsqueda y selección optimizada

- **Entrada táctil**: mostrar teclado numérico al editar cantidad o al elegir "Otro monto"; teclado QWERTY táctil opcional para búsqueda.
- **Filtros visibles**: chips o botones de categoría siempre visibles en la parte superior; si el catálogo es largo, añadir botón "Más filtros" que abra panel lateral.
- **Listas legibles**: truncar a dos líneas (`_elide_two_lines`) y mantener altura mínima de 96–132px en botones de producto.
- **Confirmaciones claras**: al agregar producto, animar o resaltar el carrito durante 800ms. Al vaciar/eliminar, diálogos modales con texto grande.

## 4) Reducción de pasos y feedback inmediato

- **Add-to-cart en un toque**: tapping en producto añade 1 unidad; mantener selección en la lista para edición directa.
- **Gestos directos**: botones +/− y "N" (cantidad exacta) junto a la lista del carrito para evitar abrir subpantallas.
- **Feedback de sistema**:
  - Loading: superponer overlay no modal con spinner y texto grande.
  - Éxito/error: toasts en la parte superior con colores de feedback y textos cortos ("Ticket impreso", "Error de impresora").
- **Atajos de teclado táctil**: en el diálogo de pago, auto-aceptar cuando `recibido >= total` y mostrar cambio en vivo.

## 5) Recomendaciones de layout

- **Distribución**: 65% del ancho para catálogo, 35% para carrito/pago en pantallas ≥1024px; en pantallas menores, el carrito se comprime proporcionalmente.
- **Tipografía**: títulos `s(22)`–`s(26)`px, montos `s(24)`–`s(28)`px en pago, texto de lista `s(18)`px. Siempre Inter/Segoe UI.
- **Padding**: usar `s(14)`–`s(18)`px horizontal y `s(12)`–`s(16)`px vertical en paneles y botones; bordes redondeados `s(12)`–`s(16)`px como en `design_tokens.md`.
- **Tamaño de toque**: mínimo `s(52)`px de alto en controles; keypad `s(68)`px de alto por tecla.

## 6) Adaptación responsive

Todos los valores de tamaño usan el helper `s()` de `ui/responsive.py` que adapta automáticamente las dimensiones según la resolución de la pantalla:

| Pantalla | Resolución | Factor | Botón CTA | Keypad Key |
|----------|-----------|--------|-----------|------------|
| 12" | 1366×768 | 0.71 | ~57px | ~57px |
| 14" | 1600×900 | 0.83 | ~66px | ~66px |
| 22" | 1920×1080 | 1.00 | 80px | 80px |

## 7) Cursor dinámico

El sistema detecta automáticamente la presencia de un ratón USB:

- **Sin ratón**: El cursor es invisible. La interfaz es 100% táctil.
- **Con ratón**: Se muestra el cursor estándar, permitiendo operación con mouse.
- **Transición**: Automática al conectar/desconectar. No requiere reinicio.

Esto permite usar el kiosk como dispositivo táctil puro, pero habilita el uso de ratón como respaldo en caso de fallo de la pantalla táctil.

## 8) Checklist de validación UX

1) ¿El CTA "Cobrar" es el elemento más visible en el panel derecho?  
2) ¿Los filtros/búsqueda están siempre visibles sin abrir modales adicionales?  
3) ¿Cada acción crítica (vaciar, eliminar, cobrar) tiene confirmación clara y texto grande?  
4) ¿Se muestra feedback inmediato (loading, éxito, error) con mensajes legibles?  
5) ¿La navegación entre categorías/productos evita pasos redundantes (un toque para agregar, back persistente)?
6) ¿Los tamaños de toque son adecuados para la resolución de pantalla actual?
7) ¿El cursor aparece/desaparece correctamente al conectar/desconectar un ratón USB?
