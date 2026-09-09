"""Legacy compatibility module.

MiSTer Companion now uses native operating-system window decorations for dialogs.
The old global frameless-dialog installer has been removed.
"""


def install_custom_dialogs(app) -> None:
    """Compatibility no-op for older imports."""
    return None
