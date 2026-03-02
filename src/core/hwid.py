"""
TOTTEM POS · Hardware ID Binding
Prevents SD card cloning by binding the app to a specific Raspberry Pi's serial number.

On Linux (Raspberry Pi):
  Reads the unique CPU serial from /proc/cpuinfo.
  On first run, registers it in config/.hwid.
  On subsequent runs, verifies the current serial matches.

On non-Linux (development):
  Uses a fixed dev serial so development is unaffected.
"""

from __future__ import annotations

import hashlib
import hmac
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HWID_PATH = ROOT / "config" / ".hwid"

# Salt for key derivation — change this per-project for extra safety
_SALT = b"TOTTEM-POS-2026-anticlone"

# Fixed serial for development on non-Linux systems
_DEV_SERIAL = "DEV-0000000000000000"


def _read_pi_serial() -> str:
    """Read the CPU serial number from /proc/cpuinfo on Linux."""
    if platform.system() != "Linux":
        return _DEV_SERIAL
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text()
        for line in cpuinfo.splitlines():
            if line.strip().lower().startswith("serial"):
                parts = line.split(":")
                if len(parts) == 2:
                    return parts[1].strip()
    except (OSError, IOError):
        pass
    return _DEV_SERIAL


def _hash_serial(serial: str) -> str:
    """Create a SHA-256 hash of the serial + salt."""
    return hashlib.sha256(_SALT + serial.encode("utf-8")).hexdigest()


def get_serial() -> str:
    """Return the current device serial number."""
    return _read_pi_serial()


def register() -> str:
    """Register the current Pi's serial in config/.hwid.

    Called once during installation (setup_services.sh).
    Returns the registered serial hash.
    """
    serial = _read_pi_serial()
    serial_hash = _hash_serial(serial)

    HWID_PATH.parent.mkdir(parents=True, exist_ok=True)
    HWID_PATH.write_text(serial_hash, encoding="utf-8")

    # Make it read-only
    try:
        HWID_PATH.chmod(0o444)
    except OSError:
        pass

    return serial_hash


def verify() -> bool:
    """Verify the current Pi matches the registered hardware.

    Returns True if:
      - We're on a non-Linux dev system (always passes)
      - No .hwid file exists yet (first run, auto-registers)
      - The current serial matches the stored hash

    Returns False if the serial doesn't match (cloned SD).
    """
    serial = _read_pi_serial()

    # Development mode — always pass
    if serial == _DEV_SERIAL:
        return True

    # No HWID file yet — auto-register on first boot
    if not HWID_PATH.exists():
        register()
        return True

    # Compare current serial against stored hash
    stored_hash = HWID_PATH.read_text(encoding="utf-8").strip()
    current_hash = _hash_serial(serial)

    return hmac.compare_digest(stored_hash, current_hash)


def get_db_key() -> str:
    """Derive a deterministic encryption key from the Pi's serial.

    This key is used by SQLCipher to encrypt/decrypt the database.
    On dev systems, returns a fixed key so development works normally.
    """
    serial = _read_pi_serial()
    # Derive a 64-char hex key from serial + a different salt
    raw = hashlib.sha256(b"TOTTEM-DB-KEY-" + serial.encode("utf-8")).hexdigest()
    return raw
