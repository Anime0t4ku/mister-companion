import json
import posixpath
import shlex
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ui.scaling import set_text_button_min_width


SMB_CONFIG_REMOTE = "/media/fat/Scripts/.config/MiSTerHiFi/smb.json"
SMB_CONFIG_RELATIVE = Path("Scripts") / ".config" / "MiSTerHiFi" / "smb.json"


def smb_config_exists(connection=None, sd_root=None):
    if sd_root:
        return (Path(sd_root) / SMB_CONFIG_RELATIVE).is_file()
    if connection is None or not connection.is_connected():
        return False
    try:
        sftp = connection.client.open_sftp()
        try:
            sftp.stat(SMB_CONFIG_REMOTE)
            return True
        finally:
            sftp.close()
    except Exception:
        return False


def _read_online(connection):
    sftp = connection.client.open_sftp()
    try:
        try:
            with sftp.file(SMB_CONFIG_REMOTE, "r") as handle:
                raw = handle.read()
        except FileNotFoundError:
            return {"shares": []}
    finally:
        sftp.close()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw or "{}")
    return data if isinstance(data, dict) else {"shares": []}


def _mkdirs_sftp(sftp, remote_dir):
    current = "/"
    for part in remote_dir.strip("/").split("/"):
        if not part:
            continue
        current = posixpath.join(current, part)
        try:
            sftp.stat(current)
        except Exception:
            sftp.mkdir(current)


def _write_online(connection, data):
    sftp = connection.client.open_sftp()
    try:
        _mkdirs_sftp(sftp, posixpath.dirname(SMB_CONFIG_REMOTE))
        payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        with sftp.file(SMB_CONFIG_REMOTE, "w") as handle:
            handle.write(payload)
    finally:
        sftp.close()


def _read_local(sd_root):
    path = Path(sd_root) / SMB_CONFIG_RELATIVE
    if not path.is_file():
        return {"shares": []}
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
    return data if isinstance(data, dict) else {"shares": []}


def _write_local(sd_root, data):
    path = Path(sd_root) / SMB_CONFIG_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class SMBShareEditorDialog(QDialog):
    def __init__(self, share=None, connection=None, offline=False, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.offline = offline
        self.result_share = None
        self.original = dict(share or {})

        self.setWindowTitle("Edit SMB Share" if share else "Add SMB Share")
        self.setMinimumWidth(480)
        self._build_ui()
        self._load_share()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        info = QLabel(
            "Configure an SMB music source for MiSTer Hi-Fi. "
            "Server and Share are required."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Optional display name")
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText("192.168.1.100 or hostname")
        self.share_edit = QLineEdit()
        self.share_edit.setPlaceholderText("Music")
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Optional subfolder")
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.guest_check = QCheckBox("Guest access")

        form.addRow("Name", self.name_edit)
        form.addRow("Server", self.server_edit)
        form.addRow("Share", self.share_edit)

        path_box = QVBoxLayout()
        path_box.setContentsMargins(0, 0, 0, 0)
        path_box.setSpacing(3)
        path_box.addWidget(self.path_edit)
        path_help = QLabel("Optional. Leave blank to use the root of the share.")
        path_help.setWordWrap(True)
        path_box.addWidget(path_help)
        form.addRow("Path (optional)", path_box)

        form.addRow("", self.guest_check)
        form.addRow("Username", self.username_edit)
        form.addRow("Password", self.password_edit)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.test_button = QPushButton("Test Connection")
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")
        set_text_button_min_width(self.test_button, 140)
        set_text_button_min_width(self.save_button, 90)
        set_text_button_min_width(self.cancel_button, 90)
        buttons.addWidget(self.test_button)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.guest_check.toggled.connect(self._update_auth_state)
        self.test_button.clicked.connect(self._test_connection)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)

        if self.offline:
            self.test_button.setEnabled(False)
            self.test_button.setToolTip("Test Connection is only available in Online / SSH Mode.")

    def _load_share(self):
        share = self.original
        self.name_edit.setText(str(share.get("name", "") or ""))
        self.server_edit.setText(str(share.get("server", "") or ""))
        self.share_edit.setText(str(share.get("share", "") or ""))
        self.path_edit.setText(str(share.get("path", "") or ""))
        self.username_edit.setText(str(share.get("username", "") or ""))
        self.password_edit.setText(str(share.get("password", "") or ""))
        self.guest_check.setChecked(bool(share.get("guest", False)))
        self._update_auth_state()

    def _update_auth_state(self):
        enabled = not self.guest_check.isChecked()
        self.username_edit.setEnabled(enabled)
        self.password_edit.setEnabled(enabled)

    def _values(self):
        server = self.server_edit.text().strip()
        share = self.share_edit.text().strip().strip("/")
        if not server:
            raise ValueError("Server is required.")
        if not share:
            raise ValueError("Share is required.")
        guest = self.guest_check.isChecked()
        return {
            "name": self.name_edit.text().strip(),
            "server": server,
            "share": share,
            "path": self.path_edit.text().strip().strip("/"),
            "username": "" if guest else self.username_edit.text().strip(),
            "password": "" if guest else self.password_edit.text(),
            "guest": guest,
        }

    def _test_connection(self):
        if self.offline or self.connection is None or not self.connection.is_connected():
            QMessageBox.information(self, "Test Connection", "Testing requires Online / SSH Mode.")
            return
        try:
            share = self._values()
        except ValueError as exc:
            QMessageBox.warning(self, "SMB Share", str(exc))
            return

        server = share["server"]
        share_name = share["share"]
        src = f"//{server}/{share_name}"
        mount_point = "/tmp/mistercompanion-smb-test"
        opts = ["ro", "guest"] if share["guest"] else [
            "ro",
            f"username={share['username']}",
            f"password={share['password']}",
        ]
        attempts = ["vers=3.0", "vers=2.1", "vers=2.0", "", "vers=1.0"]
        commands = [f"mkdir -p {shlex.quote(mount_point)}", f"umount {shlex.quote(mount_point)} >/dev/null 2>&1 || true"]
        tests = []
        for version in attempts:
            all_opts = list(opts)
            if version:
                all_opts.append(version)
            opt_value = ",".join(all_opts)
            tests.append(
                f"mount -t cifs {shlex.quote(src)} {shlex.quote(mount_point)} -o {shlex.quote(opt_value)} >/dev/null 2>&1"
            )
        commands.append("(" + " || ".join(tests) + ")")
        if share["path"]:
            target = posixpath.join(mount_point, share["path"])
            commands.append(f"test -d {shlex.quote(target)}")
        commands.append("rc=$?")
        commands.append(f"umount {shlex.quote(mount_point)} >/dev/null 2>&1 || true")
        commands.append(f"rmdir {shlex.quote(mount_point)} >/dev/null 2>&1 || true")
        commands.append("echo $rc")
        try:
            output = self.connection.run_command("; ".join(commands)).strip().splitlines()
            ok = bool(output and output[-1].strip() == "0")
        except Exception as exc:
            QMessageBox.critical(self, "Test Connection", f"SMB connection test failed:\n\n{exc}")
            return
        if ok:
            QMessageBox.information(self, "Test Connection", "Connection successful.")
        else:
            QMessageBox.warning(self, "Test Connection", "Unable to connect to the SMB share with these settings.")

    def _save(self):
        try:
            self.result_share = self._values()
        except ValueError as exc:
            QMessageBox.warning(self, "SMB Share", str(exc))
            return
        self.accept()


class MisterHiFiSMBDialog(QDialog):
    def __init__(self, connection=None, parent=None, sd_root=None):
        super().__init__(parent)
        self.connection = connection
        self.sd_root = sd_root
        self.offline = bool(sd_root)
        self.data = {"shares": []}
        self.shares = []

        self.setWindowTitle("MiSTer Hi-Fi - SMB Shares")
        self.setMinimumSize(620, 420)
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        info = QLabel(
            "Add or manage SMB music sources used by MiSTer Hi-Fi. "
            "Multiple shares are supported."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._edit_selected())
        layout.addWidget(self.list_widget, 1)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Add SMB Share")
        self.edit_button = QPushButton("Edit")
        self.delete_button = QPushButton("Delete")
        set_text_button_min_width(self.add_button, 140)
        set_text_button_min_width(self.edit_button, 90)
        set_text_button_min_width(self.delete_button, 90)
        actions.addWidget(self.add_button)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.delete_button)
        actions.addStretch()
        self.close_button = QPushButton("Close")
        set_text_button_min_width(self.close_button, 90)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

        self.add_button.clicked.connect(self._add_share)
        self.edit_button.clicked.connect(self._edit_selected)
        self.delete_button.clicked.connect(self._delete_selected)
        self.close_button.clicked.connect(self.accept)
        self.list_widget.itemSelectionChanged.connect(self._update_buttons)

    def _load(self):
        try:
            self.data = _read_local(self.sd_root) if self.offline else _read_online(self.connection)
        except Exception as exc:
            QMessageBox.critical(self, "MiSTer Hi-Fi", f"Unable to load smb.json:\n\n{exc}")
            self.reject()
            return
        shares = self.data.get("shares", [])
        self.shares = [dict(item) for item in shares if isinstance(item, dict)] if isinstance(shares, list) else []
        self._refresh()

    def _refresh(self):
        self.list_widget.clear()
        for index, share in enumerate(self.shares):
            name = str(share.get("name", "") or "").strip()
            server = str(share.get("server", "") or "").strip()
            share_name = str(share.get("share", "") or "").strip()
            path = str(share.get("path", "") or "").strip()
            title = name or f"{server}/{share_name}"
            subtitle = f"{server} / {share_name}"
            if path:
                subtitle += f" / {path}"
            if bool(share.get("guest", False)):
                subtitle += "  •  Guest"
            item = QListWidgetItem(f"{title}\n{subtitle}")
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setSizeHint(item.sizeHint())
            self.list_widget.addItem(item)
        self._update_buttons()

    def _update_buttons(self):
        selected = self.list_widget.currentItem() is not None
        self.edit_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)

    def _selected_index(self):
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def _add_share(self):
        dialog = SMBShareEditorDialog(connection=self.connection, offline=self.offline, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_share is None:
            return
        self.shares.append(dialog.result_share)
        if self._save():
            self._refresh()
            self.list_widget.setCurrentRow(len(self.shares) - 1)

    def _edit_selected(self):
        index = self._selected_index()
        if index is None or index < 0 or index >= len(self.shares):
            return
        dialog = SMBShareEditorDialog(
            share=self.shares[index],
            connection=self.connection,
            offline=self.offline,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_share is None:
            return
        self.shares[index] = dialog.result_share
        if self._save():
            self._refresh()
            self.list_widget.setCurrentRow(index)

    def _delete_selected(self):
        index = self._selected_index()
        if index is None or index < 0 or index >= len(self.shares):
            return
        share = self.shares[index]
        label = str(share.get("name", "") or "").strip() or f"{share.get('server', '')}/{share.get('share', '')}"
        answer = QMessageBox.question(
            self,
            "Delete SMB Share",
            f"Remove '{label}' from MiSTer Hi-Fi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed = self.shares.pop(index)
        if not self._save():
            self.shares.insert(index, removed)
            return
        self._refresh()

    def _save(self):
        payload = dict(self.data)
        payload["shares"] = self.shares
        try:
            if self.offline:
                _write_local(self.sd_root, payload)
            else:
                _write_online(self.connection, payload)
            self.data = payload
            return True
        except Exception as exc:
            QMessageBox.critical(self, "MiSTer Hi-Fi", f"Unable to save smb.json:\n\n{exc}")
            return False
