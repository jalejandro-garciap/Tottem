# -*- coding: utf-8 -*-
# services/osctl.py — System control helpers (nmcli, reboot, poweroff).
# UI strings in Spanish are supplied by callers; comments here are in English.

import subprocess


def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    """
    Run a command and return (exit_code, stdout, stderr), all text.
    Timeout prevents UI from hanging if the command blocks.
    """
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = p.communicate(timeout=timeout)
        return p.returncode, (out or "").strip(), (err or "").strip()
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        return 1, "", "Tiempo de espera agotado."
    except Exception as e:
        return 1, "", str(e)


def wifi_list() -> list[dict]:
    """
    List available Wi-Fi networks via nmcli.
    Returns: [{'ssid': str, 'security': str, 'signal': str}, ...]
    """
    code, out, err = _run(["nmcli", "-t", "-f", "SSID,SECURITY,SIGNAL", "dev", "wifi", "list"], timeout=15)
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
    Connect to a Wi-Fi SSID. If password is provided, pass it to nmcli.
    Returns: (ok, message)
    """
    if not ssid:
        return False, "SSID vacío."

    # Try simple connect first
    cmd = ["nmcli", "dev", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]
    code, out, err = _run(cmd, timeout=30)

    if code == 0:
        return True, out or "Conectado."

    # Fallback: if key-mgmt error, use explicit connection profile
    combined = f"{out} {err}"
    if "key-mgmt" in combined or "802-11-wireless-security" in combined:
        # Delete existing connection profile if any
        _run(["nmcli", "connection", "delete", ssid], timeout=10)

        # Create connection with explicit security settings
        cmd2 = [
            "nmcli", "connection", "add",
            "type", "wifi",
            "con-name", ssid,
            "ssid", ssid,
        ]
        if password:
            cmd2 += [
                "wifi-sec.key-mgmt", "wpa-psk",
                "wifi-sec.psk", password,
            ]
        code2, out2, err2 = _run(cmd2, timeout=15)
        if code2 != 0:
            return False, out2 or err2 or "Error al crear perfil de conexión."

        # Activate the connection
        code3, out3, err3 = _run(["nmcli", "connection", "up", ssid], timeout=30)
        return (code3 == 0, out3 or err3 or "Sin salida.")

    return (False, out or err or "Sin salida.")


def wifi_status() -> str:
    """
    Get a compact Wi-Fi status. Adjust interface if not wlan0 in your device.
    """
    code, out, err = _run(["nmcli", "-t", "-f", "GENERAL.STATE,IP4.ADDRESS", "dev", "show", "wlan0"])
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

