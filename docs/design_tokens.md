# Tokens de diseño táctil

Este sistema de diseño unifica colores, tipografías y espaciamiento para las apps Qt (`admin_app.py` y `kiosk_app.py`) a través de `src/ui/theme.qss`. Los valores priorizan pantallas táctiles entre 7" y 12".

## Paleta
- **Fondo base:** `#f6f7fb`
- **Superficie:** `#ffffff`
- **Texto principal:** `#0f172a`
- **Texto secundario:** `#4b5563`
- **Borde neutro:** `#d6deeb`
- **Acento primario:** `#3f66d1`
- **Realce suave / hover:** `#e6ebff`
- **Feedback de peligro:** `#fef2f2` (borde `#f2b8b5`, texto `#b91c1c`)

## Tipografía
- Familia: `Inter`, fallback `Segoe UI`, sans-serif.
- Tamaño base: **18px** para texto y controles.
- Títulos: **20–26px**, peso **700**.
- Tracking: `0.1px` en labels para mejorar legibilidad en pantallas medianas.

## Espaciado y tamaños táctiles
- Paddings horizontales: **14–18px**.
- Paddings verticales: **12–16px**.
- Altura mínima de controles: **52px** (inputs 48px, keypad 68px) para asegurar objetivos táctiles de 44–48px.
- Separación entre elementos de lista: **2–4px** de margen.

## Radios y elevación
- Campos: **12px**.
- Botones: **14px**.
- Contenedores/cards: **16px** con sombra `0 10px 28px rgba(15, 23, 42, 0.10)` para jerarquía.

## Estados interactivos
- **Hover:** fondos neutros claros (`#eef1ff`/`#f9faff`) y bordes suavizados.
- **Focus:** borde `#3f66d1` con halo `rgba(63, 102, 209, 0.22)` de 3px.
- **Pressed:** sombras internas y refuerzo de borde/acento para sensación táctil.

## Componentes base
- **Botones (`QPushButton`):** peso 600, padding 14x18px, roles primario/ghost/danger definidos. Variantes usan solo el acento primario o el rojo de feedback.
- **Campos (`QLineEdit`, `QComboBox`, `QSpinBox`, `QTextEdit`, `QPlainTextEdit`):** padding 14x16px, altura 48px, borde neutro y halo de enfoque.
- **Tarjetas/paneles (`#CartPanel`, `#GridPanel`):** bordes neutros, radios 16px y sombra sutil.
- **Listas y tablas (`QListWidget`, `QTableWidget`, `QHeaderView`):** bordes 14px, selección en `#e2e7ff`, encabezados con peso 700.
- **Tabs (`QTabWidget`, `QTabBar`):** radios 12–14px, padding 12px, fondo neutro al seleccionar.
- **Scrollbar táctil:** tamaño 16px con mango redondeado y mayor contraste en hover.

## Puntos de entrada
Los estilos se cargan en las apps a través de `theme.qss`:
- `src/ui/admin_app.py` y `src/ui/kiosk_app.py` leen el archivo y aplican el stylesheet a la instancia global de `QApplication`.
- Cualquier widget nuevo debe seguir los tokens anteriores para mantener consistencia y objetivos táctiles.
