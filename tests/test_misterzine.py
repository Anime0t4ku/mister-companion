"""Run with python -m unittest discover -s tests -v; no MiSTer required."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mister-companion"))
from core import extras_misterzine as mz


class MisterZineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.card = Path(self.temp.name)
        self.log = Mock()

    def write(self, path, data):
        target = self.card / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data.encode() if isinstance(data, str) else data)
        return target

    def installed(self):
        for name in ("misterzine/misterzine", "misterzine/maintenance.py", "Scripts/MisterZine-Setup.sh"):
            self.write(name, "fixture")

    def test_existing_dropin_keeps_one_registration_and_global_filter(self):
        self.write("downloader.ini", "[MiSTer]\nfilter = arcade\n")
        dropin = self.write("downloader_misterzine.ini", f"[misterzine]\ndb_url = {mz.DB_URL}\nfilter =\n")
        def download(root, db_id, log):
            self.assertEqual(db_id, "misterzine")
            self.assertIn("filter =\n", dropin.read_text())
            self.installed()
        with patch.object(mz.downloader, "run_named_database_local", side_effect=download):
            mz.install_or_update_misterzine_local(self.card, self.log)
        self.assertEqual((self.card / "downloader.ini").read_text(), "[MiSTer]\nfilter = arcade\n")
        self.assertEqual(dropin.read_text().count("[misterzine]"), 1)
        self.log.assert_any_call(mz.SETUP_NOTE + "\n")

    def test_download_failure_restores_existing_source(self):
        ini = self.write("downloader_misterzine.ini", "[misterzine]\ndb_url = https://example.org/dev.zip\nfilter = custom\n")
        before = ini.read_text()
        with patch.object(mz.downloader, "run_named_database_local", side_effect=RuntimeError("download failed")):
            with self.assertRaisesRegex(RuntimeError, "download failed"):
                mz.install_or_update_misterzine_local(self.card, self.log)
        self.assertEqual(ini.read_text(), before)

    def test_duplicate_registration_refuses_without_download(self):
        for name in ("downloader.ini", "downloader_misterzine.ini"):
            self.write(name, f"[misterzine]\ndb_url = {mz.DB_URL}\n")
        with patch.object(mz.downloader, "run_named_database_local") as run:
            with self.assertRaises(mz.downloader.DuplicateDatabaseSectionError):
                mz.install_or_update_misterzine_local(self.card, self.log)
        run.assert_not_called()

    def test_missing_files_after_download_are_not_success(self):
        with patch.object(mz.downloader, "run_named_database_local"):
            with self.assertRaisesRegex(RuntimeError, "missing"):
                mz.install_or_update_misterzine_local(self.card, self.log)

    def test_online_install_checks_exit_and_orders_setup_after_download(self):
        connection = Mock()
        with patch.object(mz.downloader, "ensure_database_source_online") as ensure, patch.object(mz.downloader, "_run_remote_streaming_result", return_value=("", 0)) as run:
            mz.install_or_update_misterzine(connection, self.log)
        ensure.assert_called_once_with(connection, "misterzine", mz.DB_URL, filter_value="")
        self.assertIn("--run-only misterzine", run.call_args_list[0].args[1])
        self.assertEqual(run.call_args_list[1].args[1], mz.BINARY + " launcher enable")

    def test_online_failed_downloader_does_not_run_setup(self):
        with patch.object(mz.downloader, "ensure_database_source_online", return_value="snapshot"), patch.object(mz.downloader, "restore_online") as restore, patch.object(mz.downloader, "_run_remote_streaming_result", return_value=("failed", 1)) as run:
            with self.assertRaisesRegex(RuntimeError, "exit 1"):
                mz.install_or_update_misterzine("connection", self.log)
        self.assertEqual(run.call_count, 1)
        restore.assert_called_once_with("connection", "snapshot")

    def test_online_setup_failure_keeps_registration_for_retry(self):
        with patch.object(mz.downloader, "ensure_database_source_online"), patch.object(mz.downloader, "restore_online") as restore, patch.object(mz.downloader, "_run_remote_streaming_result", side_effect=[("", 0), ("setup failed", 1)]):
            with self.assertRaisesRegex(RuntimeError, "setup failed"):
                mz.install_or_update_misterzine("connection", self.log)
        restore.assert_not_called()

    def test_status_of_uninstalled_registered_and_incomplete_cards(self):
        self.assertFalse(mz.get_misterzine_status_local(self.card)["installed"])
        self.write("downloader_misterzine.ini", f"[misterzine]\ndb_url = {mz.DB_URL}\nfilter =\n")
        status = mz.get_misterzine_status_local(self.card)
        self.assertTrue(status["install_enabled"])
        self.assertFalse(status["uninstall_enabled"])
        self.write("misterzine/misterzine", "fixture")
        status = mz.get_misterzine_status_local(self.card)
        self.assertEqual(status["install_label"], "Repair / Update")

    def test_offline_pending_setup_still_checks_updates(self):
        self.installed()
        self.write("downloader_misterzine.ini", f"[misterzine]\ndb_url = {mz.DB_URL}\nfilter =\n")
        with patch.object(mz.downloader, "check_named_database_local", return_value=True):
            status = mz.get_misterzine_status_local(self.card, check_latest=True)
        self.assertTrue(status["update_available"])
        self.assertTrue(status["install_enabled"])
        self.assertIn("MisterZine-Setup", status["status_text"])

    def test_update_failure_does_not_claim_up_to_date(self):
        self.installed()
        self.write("downloader.ini", f"[misterzine]\ndb_url = {mz.DB_URL}\n")
        with patch.object(mz.downloader, "check_named_database_local", side_effect=RuntimeError("network failed")):
            status = mz.get_misterzine_status_local(self.card, check_latest=True)
        self.assertIn("update check failed", status["status_text"])

    def test_offline_upgrade_preserves_boot_and_saved_data(self):
        self.installed()
        startup = self.write("linux/user-startup.sh", "#!/bin/sh\nother-service &\n# misterzine\n" + mz.STARTUP_LINE + "\n")
        before = startup.read_bytes()
        self.write("MisterZine.mgl", "launcher")
        saved = self.write("misterzine/favorites.json", '{"favorite":true}')
        with patch.object(mz.downloader, "run_named_database_local"):
            mz.install_or_update_misterzine_local(self.card, self.log)
        self.assertEqual(startup.read_bytes(), before)
        self.assertEqual(saved.read_text(), '{"favorite":true}')
        self.assertFalse(any(mz.SETUP_NOTE in call.args[0] for call in self.log.call_args_list))

    def test_uninstall_preserves_other_hooks_and_user_data(self):
        unrelated = b"#!/bin/sh\r\nother-service &\r\n# keep me\r\n"
        startup = self.write("linux/user-startup.sh", unrelated + b"# misterzine\r\n" + mz.STARTUP_LINE.encode() + b" # menu\r\n")
        self.write("MisterZine.mgl", "launcher")
        self.write("misterzine.mgl", "legacy")
        saved = self.write("misterzine/settings.json", "preferences")
        self.write("downloader_misterzine.ini", f"[misterzine]\ndb_url = {mz.DB_URL}\n")
        with patch.object(mz, "_require_native_uninstall"), patch.object(mz.downloader, "uninstall_named_database_local", return_value=True) as remove:
            mz.uninstall_misterzine_local(self.card, self.log, force=True)
        remove.assert_called_once_with(self.card, "misterzine", log=self.log, force=True)
        self.assertEqual(startup.read_bytes(), unrelated)
        self.assertFalse((self.card / "MisterZine.mgl").exists())
        self.assertFalse((self.card / "misterzine.mgl").exists())
        self.assertEqual(saved.read_text(), "preferences")
        self.assertFalse(mz.downloader.database_registered_local(self.card, "misterzine"))

    def test_old_downloader_leaves_menu_untouched(self):
        startup = self.write("linux/user-startup.sh", mz.STARTUP_LINE + "\n")
        with patch.object(mz.downloader, "get_downloader_version_local", return_value=mz.downloader.DownloaderVersion(2, 3, 0)):
            with self.assertRaisesRegex(RuntimeError, "2.4.3"):
                mz.uninstall_misterzine_local(self.card, self.log)
        self.assertEqual(startup.read_text(), mz.STARTUP_LINE + "\n")

    def test_failed_uninstall_keeps_source_and_explains_recovery(self):
        self.write("downloader_misterzine.ini", f"[misterzine]\ndb_url = {mz.DB_URL}\n")
        with patch.object(mz, "_require_native_uninstall"), patch.object(mz.downloader, "uninstall_named_database_local", side_effect=RuntimeError("missing drive")):
            with self.assertRaisesRegex(RuntimeError, "missing drive"):
                mz.uninstall_misterzine_local(self.card, self.log)
        self.assertTrue(mz.downloader.database_registered_local(self.card, "misterzine"))
        self.assertIn("restore", self.log.call_args.args[0])

    def test_online_busy_app_aborts_before_downloader_removal(self):
        with patch.object(mz, "_require_native_uninstall"), patch.object(mz, "_remote_checked", side_effect=RuntimeError("Quit MisterZine")), patch.object(mz.downloader, "uninstall_named_database_online") as remove:
            with self.assertRaisesRegex(RuntimeError, "Quit MisterZine"):
                mz.uninstall_misterzine("connection", self.log)
        remove.assert_not_called()

    def test_comment_is_not_enabled_hook(self):
        self.assertFalse(mz._enabled("# " + mz.STARTUP_LINE))
        self.assertTrue(mz._enabled(mz.STARTUP_LINE + " # enabled"))


if __name__ == "__main__":
    unittest.main()
