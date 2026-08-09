import threading

from PyQt6.QtWidgets import QInputDialog, QLineEdit, QMessageBox

from core.zaparoo_crypto import ZaparooCryptoError, pair_with_pin
from core.zapscripts import ZaparooPairingRequired


_PROMPT_GUARD = threading.Lock()
_PROMPTING_HOSTS: set[str] = set()


def prompt_for_zaparoo_pairing(parent, connection) -> bool:
    host = getattr(connection, "host", "").strip()
    if not host:
        QMessageBox.warning(parent, "Not connected", "Please connect to your MiSTer first.")
        return False

    with _PROMPT_GUARD:
        if host.lower() in _PROMPTING_HOSTS:
            return False
        _PROMPTING_HOSTS.add(host.lower())

    try:
        return _prompt_for_zaparoo_pairing_locked(parent, host)
    finally:
        with _PROMPT_GUARD:
            _PROMPTING_HOSTS.discard(host.lower())


def _prompt_for_zaparoo_pairing_locked(parent, host: str) -> bool:
    pin, accepted = QInputDialog.getText(
        parent,
        "Zaparoo Pairing Required",
        "Start pairing on the Zaparoo device, then enter the 6-digit PIN shown there:",
        QLineEdit.EchoMode.Password,
    )
    if not accepted:
        return False

    pin = pin.strip()
    if len(pin) != 6 or not pin.isdigit():
        QMessageBox.warning(
            parent,
            "Invalid Zaparoo PIN",
            "The Zaparoo pairing PIN must contain exactly 6 digits.",
        )
        return False

    try:
        pair_with_pin(host, pin)
    except ZaparooCryptoError as exc:
        QMessageBox.critical(parent, "Zaparoo Pairing Failed", str(exc))
        return False

    QMessageBox.information(
        parent,
        "Zaparoo Paired",
        "MiSTer Companion is now paired with Zaparoo. The pairing credential has been saved; the 6-digit PIN is not stored.",
    )
    return True


def run_with_zaparoo_pairing(parent, connection, action):
    try:
        return action()
    except ZaparooPairingRequired:
        if not prompt_for_zaparoo_pairing(parent, connection):
            return None
        return action()
