from PyQt6.QtWidgets import QFileDialog, QMessageBox

from core.open_helpers import open_uri
from core.scripts_actions import (
    check_update_all_initialized,
    check_update_all_initialized_local,
    disable_ftp_save_sync_service,
    disable_ftp_save_sync_service_local,
    enable_ftp_save_sync_service,
    enable_ftp_save_sync_service_local,
    enable_zaparoo_service,
    enable_zaparoo_service_local,
    ensure_update_all_config_bootstrap,
    ensure_update_all_config_bootstrap_local,
    remove_cifs_config,
    remove_cifs_config_local,
    remove_dav_browser_config,
    remove_dav_browser_config_local,
    remove_ftp_save_sync_config,
    remove_ftp_save_sync_config_local,
    run_cifs_mount,
    run_cifs_umount,
    toggle_syncthing_start_on_boot,
    toggle_syncthing_start_on_boot_local,
)
from core.extras_3s_arm import upload_3sx_afs, upload_3sx_afs_local
from core.extras_sonic_mania import upload_sonic_mania_data_rsdk, upload_sonic_mania_data_rsdk_local
from core.extras_mister_quake import upload_mister_quake_paks, upload_mister_quake_paks_local
from core.extras_paprium_megadrive import open_paprium_game_folder_local, open_paprium_game_folder_on_host
from ui.dialogs.cifs_config_dialog import CifsConfigDialog
from ui.dialogs.dav_browser_config_dialog import DavBrowserConfigDialog
from ui.dialogs.ftp_save_sync_config_dialog import FtpSaveSyncConfigDialog
from ui.dialogs.ra_cores_config_dialog import RetroAchievementsConfigDialog
from ui.dialogs.ra_viewer_config_dialog import RAViewerConfigDialog
from ui.dialogs.update_all_config_dialog import UpdateAllConfigDialog


class InstallCenterActions:
    """Actions shared by Install Center and Device without hidden legacy tabs."""

    def __init__(self, main_window, install_center_tab):
        self.main_window = main_window
        self.tab = install_center_tab

    @property
    def connection(self):
        return self.main_window.connection

    def is_offline_mode(self):
        return bool(self.main_window.is_offline_mode())

    def sd_root(self):
        return self.main_window.get_offline_sd_root()

    def refresh(self):
        self.tab.refresh_existing_tabs()
        self.tab.refresh_status()

    def _require_sd(self):
        root = self.sd_root()
        if not root:
            QMessageBox.critical(self.tab, "Error", "Select an Offline SD Card first.")
            return None
        return root

    def _require_online(self):
        if not self.connection.is_connected():
            QMessageBox.critical(self.tab, "Error", "Connect to a MiSTer first.")
            return False
        return True

    def configure_update_all(self, installed=True):
        if not installed:
            QMessageBox.critical(self.tab, "update_all not installed", "Install update_all first before opening the configurator.")
            return
        try:
            if self.is_offline_mode():
                root = self._require_sd()
                if not root:
                    return
                ensure_update_all_config_bootstrap_local(root)
                check_update_all_initialized_local(root)
                dialog = UpdateAllConfigDialog(parent=self.tab, sd_root=root)
            else:
                if not self._require_online():
                    return
                ensure_update_all_config_bootstrap(self.connection)
                check_update_all_initialized(self.connection)
                dialog = UpdateAllConfigDialog(connection=self.connection, parent=self.tab)
        except Exception as exc:
            QMessageBox.critical(self.tab, "update_all configuration error", f"Could not prepare update_all configuration files.\n\n{exc}")
            return
        if dialog.exec():
            self.refresh()

    def configure_cifs(self):
        if self.is_offline_mode():
            root = self._require_sd()
            if not root: return
            dialog = CifsConfigDialog(parent=self.tab, sd_root=root)
        else:
            if not self._require_online(): return
            dialog = CifsConfigDialog(connection=self.connection, parent=self.tab)
        if dialog.exec(): self.refresh()

    def configure_dav_browser(self):
        if self.is_offline_mode():
            root = self._require_sd()
            if not root: return
            dialog = DavBrowserConfigDialog(parent=self.tab, sd_root=root)
        else:
            if not self._require_online(): return
            dialog = DavBrowserConfigDialog(connection=self.connection, parent=self.tab)
        if dialog.exec(): self.refresh()

    def configure_ftp_save_sync(self):
        if self.is_offline_mode():
            root = self._require_sd()
            if not root: return
            dialog = FtpSaveSyncConfigDialog(main_window=self.main_window, parent=self.tab, sd_root=root)
        else:
            if not self._require_online(): return
            dialog = FtpSaveSyncConfigDialog(connection=self.connection, main_window=self.main_window, parent=self.tab)
        if dialog.exec(): self.refresh()

    def edit_ra_viewer_config(self):
        if self.is_offline_mode():
            root = self._require_sd()
            if not root: return
            dialog = RAViewerConfigDialog(parent=self.tab, sd_root=root)
        else:
            if not self._require_online(): return
            dialog = RAViewerConfigDialog(connection=self.connection, parent=self.tab)
        if dialog.exec(): self.refresh()

    def edit_ra_cores_config(self):
        if self.is_offline_mode():
            root = self._require_sd()
            if not root: return
            dialog = RetroAchievementsConfigDialog(self.tab, connection=None, sd_root=root)
        else:
            if not self._require_online(): return
            dialog = RetroAchievementsConfigDialog(self.tab, self.connection)
        if dialog.exec() == dialog.DialogCode.Accepted: self.refresh()

    def enable_zaparoo_service(self):
        offline = self.is_offline_mode()
        root = self._require_sd() if offline else None
        if offline and not root: return
        if not offline and not self._require_online(): return
        text = "This will add the Zaparoo service entry to the selected SD card so it starts automatically when that MiSTer boots.\n\nContinue?" if offline else "This will enable the Zaparoo service so it starts automatically on boot.\n\nContinue?"
        if QMessageBox.question(self.tab, "Enable Zaparoo Service", text) != QMessageBox.StandardButton.Yes: return
        try:
            enable_zaparoo_service_local(root) if offline else enable_zaparoo_service(self.connection)
            message = "Zaparoo service enabled on the selected SD card." if offline else "Zaparoo service enabled.\n\nPlease reboot your MiSTer."
            QMessageBox.information(self.tab, "Zaparoo Enabled", message)
            self.refresh()
        except Exception as exc: QMessageBox.critical(self.tab, "Error", str(exc))


    def disable_zaparoo_frontend(self):
        offline = self.is_offline_mode()
        root = self._require_sd() if offline else None
        if offline and not root: return
        if not offline and not self._require_online(): return
        try:
            disable_zaparoo_launcher_frontend_local(root) if offline else disable_zaparoo_launcher_frontend(self.connection)
            QMessageBox.information(self.tab, "Zaparoo Frontend", "Zaparoo Frontend has been disabled.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self.tab, "Error", str(exc))

    def open_zaparoo_web_interface(self):
        if self.is_offline_mode() or not self._require_online(): return
        host = self.connection.host
        if host: open_uri(f"http://{host}:7497/app/")

    def run_cifs_mount(self):
        if self.is_offline_mode() or not self._require_online(): return
        QMessageBox.information(self.tab, "Mount", run_cifs_mount(self.connection) or "Mount command sent.")

    def run_cifs_umount(self):
        if self.is_offline_mode() or not self._require_online(): return
        QMessageBox.information(self.tab, "Unmount", run_cifs_umount(self.connection) or "Unmount command sent.")

    def _remove_config(self, title, offline_fn, online_fn):
        if self.is_offline_mode():
            root = self._require_sd()
            if not root: return
            target = " from the selected SD card"
        else:
            if not self._require_online(): return
            root = None; target = ""
        if QMessageBox.question(self.tab, "Remove Config", f"Delete {title} configuration{target}?") != QMessageBox.StandardButton.Yes: return
        offline_fn(root) if root else online_fn(self.connection)
        self.refresh()

    def remove_cifs_config(self): self._remove_config("CIFS", remove_cifs_config_local, remove_cifs_config)
    def remove_dav_browser_config(self): self._remove_config("DAV Browser", remove_dav_browser_config_local, remove_dav_browser_config)
    def remove_ftp_save_sync_config(self): self._remove_config("ftp_save_sync", remove_ftp_save_sync_config_local, remove_ftp_save_sync_config)

    def _set_ftp_service(self, enable):
        offline = self.is_offline_mode(); root = self._require_sd() if offline else None
        if offline and not root: return
        if not offline and not self._require_online(): return
        verb = "Enable" if enable else "Disable"
        if QMessageBox.question(self.tab, f"{verb} ftp_save_sync Service", f"This will {'add' if enable else 'remove'} the ftp_save_sync startup entry{' on the selected SD card' if offline else ''}.\n\nContinue?") != QMessageBox.StandardButton.Yes: return
        try:
            fn = enable_ftp_save_sync_service_local if enable and offline else disable_ftp_save_sync_service_local if offline else enable_ftp_save_sync_service if enable else disable_ftp_save_sync_service
            fn(root if offline else self.connection)
            QMessageBox.information(self.tab, f"ftp_save_sync {verb}d", f"ftp_save_sync service {verb.lower()}d{' on the selected SD card' if offline else ''}.")
            self.refresh()
        except Exception as exc: QMessageBox.critical(self.tab, "Error", str(exc))

    def enable_ftp_save_sync_service(self): self._set_ftp_service(True)
    def disable_ftp_save_sync_service(self): self._set_ftp_service(False)

    def toggle_syncthing_start_on_boot(self, enabling):
        offline = self.is_offline_mode(); root = self._require_sd() if offline else None
        if offline and not root: return
        if not offline and not self._require_online(): return
        verb = "Enable" if enabling else "Disable"
        if QMessageBox.question(self.tab, f"{verb} Syncthing Start on Boot", f"This will {'add' if enabling else 'remove'} the Syncthing startup entry{' to the selected SD card' if offline else ''}.\n\nContinue?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes) != QMessageBox.StandardButton.Yes: return
        try:
            toggle_syncthing_start_on_boot_local(root) if offline else toggle_syncthing_start_on_boot(self.connection)
            QMessageBox.information(self.tab, f"Syncthing {verb}d", f"Syncthing start on boot has been {verb.lower()}d{' on the selected SD card' if offline else ''}.")
            self.refresh()
        except Exception as exc: QMessageBox.critical(self.tab, "Error", str(exc))

    def open_syncthing_web_config(self):
        if self.is_offline_mode() or not self._require_online(): return
        if self.connection.host: open_uri(f"http://{self.connection.host}:8384")

    def upload_sf33rd_afs(self, output_widget=None):
        self._upload_file("Select SF33RD.AFS", "AFS Files (SF33RD.AFS *.afs *.AFS);;All Files (*)", upload_3sx_afs_local, upload_3sx_afs, "SF33RD.AFS copied.", "SF33RD.AFS uploaded.", output_widget)

    def upload_sonic_mania_data_rsdk(self, output_widget=None):
        self._upload_file("Select Data.rsdk", "Sonic Mania Data File (Data.rsdk *.rsdk *.RSDK);;All Files (*)", upload_sonic_mania_data_rsdk_local, upload_sonic_mania_data_rsdk, "Data.rsdk copied.", "Data.rsdk uploaded.", output_widget)

    def upload_mister_quake_paks(self, output_widget=None):
        if self.is_offline_mode():
            root = self._require_sd()
            if not root: return
        else:
            if not self._require_online(): return
            root = None
        paths, _ = QFileDialog.getOpenFileNames(self.tab, "Select Quake PAK Files", "", "Quake PAK Files (PAK0.PAK PAK1.PAK *.pak *.PAK);;All Files (*)")
        if not paths: return
        def task(log):
            log("Selected files:\n" + "\n".join(paths) + "\n")
            return upload_mister_quake_paks_local(root, paths, log) if root else upload_mister_quake_paks(self.connection, paths, log)
        self.tab.start_task("Uploading Quake PAK files...", task, "Quake PAK files copied." if root else "Quake PAK files uploaded.", output_widget=output_widget)

    def _upload_file(self, title, file_filter, local_fn, remote_fn, local_message, remote_message, output_widget):
        if self.is_offline_mode():
            root = self._require_sd()
            if not root: return
        else:
            if not self._require_online(): return
            root = None
        path, _ = QFileDialog.getOpenFileName(self.tab, title, "", file_filter)
        if not path: return
        def task(log):
            log(f"Selected file: {path}")
            return local_fn(root, path, log) if root else remote_fn(self.connection, path, log)
        self.tab.start_task(f"{title.replace('Select ', 'Uploading ')}...", task, local_message if root else remote_message, output_widget=output_widget)

    def open_paprium_game_folder(self):
        try:
            if self.is_offline_mode():
                root = self._require_sd()
                if root: open_paprium_game_folder_local(root)
            elif self._require_online():
                open_paprium_game_folder_on_host(self.connection.host)
        except Exception as exc: QMessageBox.critical(self.tab, "Paprium MegaDrive", str(exc))
