# POS Local


POS minimal offline para Raspberry Pi OS Lite. UI fullscreen con PySide6/eglfs, SQLite local, Print ESC/POS y control cash.


## Requirements
- Raspberry Pi 3B+ o (64-bit Recomended)
- Raspberry Pi OS Lite (Debian-based)
- Termal Printer 80mm ESC/POS (USB)
- Automatic Cash RJ-11


## Installation
```bash
sudo apt update
sudo apt install -y git
git clone <TU_REPO_URL> pos-local
cd pos-local
bash scripts/install_deps.sh
