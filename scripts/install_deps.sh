#!/usr/bin/env bash
set -euo pipefail


sudo apt update
sudo apt install -y python3-pip python3-venv \
libxcb-cursor0 libxkbcommon0 libinput10 libmtdev1 libudev1 \
libxcb-xinerama0 libxcb-xfixes0 libxcb-shape0


python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
pip install -e .


echo "OK: installed dependencies."
