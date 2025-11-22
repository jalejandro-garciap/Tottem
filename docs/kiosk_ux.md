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

- **CTA principal**: resaltar "Cobrar / Imprimir" (rol primario). Tamaño mínimo 56px de alto y ancho expandible en desktop táctil.
- **Acciones secundarias**: estilo "ghost" o bordes neutros para reimprimir, idioma, admin y limpiar carrito. Agrupar en barras horizontales con espacio amplio entre ellas.
- **Agrupación**: usar paneles con sombra suave para separar (a) catálogo, (b) carrito y (c) pagos. Títulos con `SectionTitle` para cada bloque.
- **Estados**: hover/pressed según `theme.qss`; feedback de error en rojo (`#fef2f2`) y éxito en acento primario.

## 3) Búsqueda y selección optimizada

- **Entrada táctil**: mostrar teclado numérico al editar cantidad o al elegir "Otro monto"; teclado QWERTY táctil opcional para búsqueda.
- **Filtros visibles**: chips o botones de categoría siempre visibles en la parte superior; si el catálogo es largo, añadir botón "Más filtros" que abra panel lateral.
- **Listas legibles**: truncar a dos líneas (`_elide_two_lines`) y mantener altura mínima de 96–132px en botones de producto.
- **Confirmaciones claras**: al agregar producto, animar o resaltar el carrito durante 800ms. Al vaciar/eliminar, diálogos modales con texto grande.

## 4) Reducción de pasos y feedback inmediato

- **Add-to-cart en un toque**: tapping en producto añade 1 unidad; mantener selección en la lista para edición directa.
- **Gestos directos**: botones +/− y "N" (cantidad exacta) junto a la lista del carrito para evitar abrir subpantallas.
- **Feedback de sistema**:
  - Loading: superponer `QMessageBox` no modal o banner con texto grande y spinner.
  - Éxito/error: banners en la parte superior del carrito con colores de feedback y textos cortos ("Ticket impreso", "Error de impresora").
- **Atajos de teclado táctil**: en el diálogo de pago, auto-aceptar cuando `recibido >= total` y mostrar cambio en vivo.

## 5) Recomendaciones de layout

- **Distribución**: 65% del ancho para catálogo, 35% para carrito/pago en pantallas ≥1024px; en pantallas menores, pila vertical con carrito abajo.
- **Tipografía**: títulos 22–26px, montos 24–28px en pago, texto de lista 18px. Siempre Inter/Segoe UI.
- **Padding**: usar 14–18px horizontal y 12–16px vertical en paneles y botones; bordes redondeados (12–16px) como en `design_tokens.md`.
- **Tamaño de toque**: mínimo 52px de alto en controles; keypad 68px de alto por tecla.

## 6) Checklist de validación UX

1) ¿El CTA "Cobrar" es el elemento más visible en el panel derecho?  
2) ¿Los filtros/búsqueda están siempre visibles sin abrir modales adicionales?  
3) ¿Cada acción crítica (vaciar, eliminar, cobrar) tiene confirmación clara y texto grande?  
4) ¿Se muestra feedback inmediato (loading, éxito, error) con mensajes legibles?  
5) ¿La navegación entre categorías/productos evita pasos redundantes (un toque para agregar, back persistente)?
