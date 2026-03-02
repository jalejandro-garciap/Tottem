# FontAwesome 6 Free Icons for Tottem POS

## Installation

This directory contains FontAwesome 6 Free Solid font for offline icon rendering in Raspbian Lite.

### Required Font File

Download **fa-solid-900.ttf** from FontAwesome 6 Free and place it in:
```
src/ui/assets/fonts/fa-solid-900.ttf
```

**Download Link**: https://fontawesome.com/download
- Select "Free For Web" or "Free For Desktop"
- Extract the archive
- Copy `webfonts/fa-solid-900.ttf` to this directory

### Verification

After placing the font file, verify the structure:
```
src/ui/assets/
├── fonts/
│   └── fa-solid-900.ttf
└── README.md
```

### Usage in Code

Icons are loaded automatically at application startup via `icon_helper.py`:

```python
from ui.icon_helper import IconHelper, get_icon_char

# Get icon character
icon = get_icon_char("coffee")  # Returns Unicode char

# Use in labels/buttons
btn.setText(f"{get_icon_char('pizza-slice')}  Pizza")
```

### Available Icons

See `icon_helper.py` for the complete `ICON_MAP` dictionary with all available icon names.

Common icons:
- Products: `utensils`, `coffee`, `pizza-slice`, `burger`, `ice-cream`
- Actions: `print`, `gear`, `lock`, `check`, `arrow-right`
- Money: `dollar-sign`, `coins`, `cash-register`

### License

FontAwesome 6 Free is licensed under:
- Font: SIL OFL 1.1 License
- Icons: CC BY 4.0 License

See: https://fontawesome.com/license/free
