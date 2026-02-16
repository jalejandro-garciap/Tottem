# -*- coding: utf-8 -*-
# services/osctl.py — System control helpers (nmcli, reboot, poweroff).
# UI strings in Spanish are supplied by callers; comments here are in English.

import subprocess


def _run(cmd: list[str]) -> tuple[int, str, str]:
    """
    Run a command and return (exit_code, stdout, stderr), all text.
    """
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate()
    return p.returncode, (out or "").strip(), (err or "").strip()


def wifi_list() -> list[dict]:
    """
    List available Wi-Fi networks via nmcli.
    Returns: [{'ssid': str, 'security': str, 'signal': str}, ...]
    """
    code, out, err = _run(["sudo", "nmcli", "-t", "-f", "SSID,SECURITY,SIGNAL", "dev", "wifi", "list", "--rescan", "yes"])
    if code != 0:
        return []
    nets: list[dict] = []
    for line in out.splitlines():
        parts = line.split(":")
        ssid = parts[0] if len(parts) > 0 else ""
        sec = parts[1] if len(parts) > 1 else ""
        sig = parts[2] if len(parts) > 2 else ""
        if ssid:  # ignore blank SSIDs
            nets.append({"ssid": ssid, "security": sec, "signal": sig})
    return nets


def wifi_connect(ssid: str, password: str = "") -> tuple[bool, str]:
    """
    Connect to a Wi-Fi SSID via nmcli.
    With the regulatory domain properly set (MX), nmcli auto-detects
    the security type so no extra wifi-sec arguments are needed.
    Returns: (ok, message)
    """
    if not ssid:
        return False, "SSID vacío."
    cmd = ["sudo", "nmcli", "dev", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]
    code, out, err = _run(cmd)
    return (code == 0, out or err or "Sin salida.")


def wifi_status() -> str:
    """
    Get a compact Wi-Fi status. Adjust interface if not wlan0 in your device.
    """
    code, out, err = _run(["sudo", "nmcli", "-t", "-f", "GENERAL.STATE,IP4.ADDRESS", "dev", "show", "wlan0"])
    return out or err or ""


def reboot() -> tuple[int, str, str]:
    """
    Reboot the system (requires sudo NOPASSWD for /usr/sbin/reboot).
    """
    return _run(["sudo", "/usr/sbin/reboot"])


def poweroff() -> tuple[int, str, str]:
    """
    Power off the system (requires sudo NOPASSWD for /usr/sbin/poweroff).
    """
    return _run(["sudo", "/usr/sbin/poweroff"])

