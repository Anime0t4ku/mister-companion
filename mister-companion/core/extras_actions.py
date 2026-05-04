from core.extras_3s_arm import (
    get_3sx_status,
    install_or_update_3sx,
    uninstall_3sx,
    upload_3sx_afs,
)

from core.extras_pico8 import (
    get_pico8_status,
    install_or_update_pico8,
    uninstall_pico8,
)

from core.extras_openbor_4086 import (
    get_openbor_4086_status,
    install_or_update_openbor_4086,
    uninstall_openbor_4086,
)

from core.extras_openbor_7533 import (
    get_openbor_7533_status,
    install_or_update_openbor_7533,
    uninstall_openbor_7533,
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
    uninstall_zaparoo_launcher,
)


__all__ = [
    "get_3sx_status",
    "install_or_update_3sx",
    "uninstall_3sx",
    "upload_3sx_afs",

    "get_pico8_status",
    "install_or_update_pico8",
    "uninstall_pico8",

    "get_openbor_4086_status",
    "install_or_update_openbor_4086",
    "uninstall_openbor_4086",

    "get_openbor_7533_status",
    "install_or_update_openbor_7533",
    "uninstall_openbor_7533",

    "get_sonic_mania_status",
    "install_or_update_sonic_mania",
    "uninstall_sonic_mania",
    "upload_sonic_mania_data_rsdk",

    "get_zaparoo_launcher_status",
    "install_or_update_zaparoo_launcher",
    "uninstall_zaparoo_launcher",
]