from core.extras_3s_arm import (
    get_3sx_status,
    install_or_update_3sx,
    uninstall_3sx,
    upload_3sx_afs,
)

from core.extras_sonic_mania import (
    get_sonic_mania_status,
    install_or_update_sonic_mania,
    uninstall_sonic_mania,
    upload_sonic_mania_data_rsdk,
)

from core.extras_zaparoo_launcher import (
    get_zaparoo_launcher_status,
    install_or_update_zaparoo_launcher,
    enable_zaparoo_launcher_frontend,
    uninstall_zaparoo_launcher,
)

from core.extras_mms2_gb_core import (
    get_mms2_gb_core_status,
    install_or_update_mms2_gb_core,
    uninstall_mms2_gb_core,
)

from core.extras_paprium_megadrive import (
    get_paprium_megadrive_status,
    install_or_update_paprium_megadrive,
    uninstall_paprium_megadrive,
)


__all__ = [
    "get_3sx_status",
    "install_or_update_3sx",
    "uninstall_3sx",
    "upload_3sx_afs",

    "get_sonic_mania_status",
    "install_or_update_sonic_mania",
    "uninstall_sonic_mania",
    "upload_sonic_mania_data_rsdk",

    "get_zaparoo_launcher_status",
    "install_or_update_zaparoo_launcher",
    "enable_zaparoo_launcher_frontend",
    "uninstall_zaparoo_launcher",

    "get_mms2_gb_core_status",
    "install_or_update_mms2_gb_core",
    "uninstall_mms2_gb_core",

    "get_paprium_megadrive_status",
    "install_or_update_paprium_megadrive",
    "uninstall_paprium_megadrive",
]