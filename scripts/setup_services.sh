#!/usr/bin/env bash
set -euo pipefail


sudo groupadd -f posadm || true
sudo usermod -aG posadm ${SUDO_USER:-$USER} || true


sudo install -Dm644 system/pos.service /etc/systemd/system/pos.service
sudo mkdir -p /etc/sudoers.d
sudo install -Dm440 system/sudoers.d/pos /etc/sudoers.d/pos


sudo systemctl daemon-reload
sudo systemctl enable pos.service


echo "OK: installed service. Use 'sudo systemctl start pos.service' to start."
