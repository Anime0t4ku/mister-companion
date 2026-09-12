from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.device_profiles import PROFILE_SYNC_ID_KEY


class ProfileSyncConflictsDialog(QDialog):
    def __init__(self, conflicts: list[dict], reserved_names: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resolve Profile Sync")
        self.resize(820, 560)
        self._rows = []
        self._reserved_names = {str(name).strip().casefold() for name in (reserved_names or []) if str(name).strip()}

        root = QVBoxLayout(self)
        intro = QLabel(
            "Companion found profiles that may refer to the same MiSTer. "
            "Choose how each conflict should be resolved. If a local profile is renamed, "
            "its MiSTer Settings and SaveManager folders are migrated with it."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(4, 4, 4, 4)
        body_layout.setSpacing(12)

        for index, conflict in enumerate(conflicts, start=1):
            local = conflict.get("local") if isinstance(conflict, dict) else {}
            cloud = conflict.get("cloud") if isinstance(conflict, dict) else {}
            group = QGroupBox(f"Conflict {index}")
            group_layout = QVBoxLayout(group)

            reason = QLabel(str(conflict.get("reason") or "Profile conflict"))
            reason.setWordWrap(True)
            group_layout.addWidget(reason)

            compare = QHBoxLayout()
            local_form = QFormLayout()
            cloud_form = QFormLayout()

            local_form.addRow("Local IP:", QLabel(str(local.get("ip") or "")))
            local_form.addRow("Local user:", QLabel(str(local.get("username") or "root")))
            local_name = QLineEdit(str(local.get("name") or ""))
            local_form.addRow("Local name:", local_name)

            cloud_form.addRow("Cloud IP:", QLabel(str(cloud.get("ip") or "")))
            cloud_form.addRow("Cloud user:", QLabel(str(cloud.get("username") or "root")))
            cloud_name = QLineEdit(str(cloud.get("name") or ""))
            cloud_form.addRow("Cloud name:", cloud_name)

            compare.addLayout(local_form, 1)
            compare.addSpacing(18)
            compare.addLayout(cloud_form, 1)
            group_layout.addLayout(compare)

            action = QComboBox()
            action.addItem("Use Local Profile", "use_local")
            action.addItem("Use Cloud Profile", "use_cloud")
            action.addItem("Keep Both Profiles", "keep_both")
            group_layout.addWidget(action)

            hint = QLabel()
            hint.setWordWrap(True)
            group_layout.addWidget(hint)

            row = {
                "conflict": conflict,
                "action": action,
                "local_name": local_name,
                "cloud_name": cloud_name,
                "hint": hint,
            }
            self._rows.append(row)
            action.currentIndexChanged.connect(lambda _value, r=row: self._update_row(r))
            self._update_row(row)
            body_layout.addWidget(group)

        body_layout.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _update_row(self, row: dict):
        action = row["action"].currentData()
        row["local_name"].setEnabled(action in {"use_local", "keep_both"})
        row["cloud_name"].setEnabled(action in {"use_cloud", "keep_both"})
        messages = {
            "use_local": "The local profile is kept and becomes the synced cloud profile.",
            "use_cloud": "The cloud profile replaces the local profile. Local backup folders follow the selected cloud name.",
            "keep_both": "Both profiles are kept. Their final profile names must be different.",
        }
        row["hint"].setText(messages.get(action, ""))

    def resolutions(self) -> list[dict]:
        result = []
        for row in self._rows:
            conflict = row["conflict"]
            local = conflict.get("local") or {}
            result.append({
                "local_id": str(local.get(PROFILE_SYNC_ID_KEY) or ""),
                "action": str(row["action"].currentData() or ""),
                "local_name": row["local_name"].text().strip(),
                "cloud_name": row["cloud_name"].text().strip(),
            })
        return result

    def _validate_and_accept(self):
        final_names = []
        for row in self._rows:
            action = row["action"].currentData()
            local_name = row["local_name"].text().strip()
            cloud_name = row["cloud_name"].text().strip()

            if action in {"use_local", "keep_both"} and not local_name:
                QMessageBox.warning(self, "Resolve Profile Sync", "Every kept local profile needs a name.")
                return
            if action in {"use_cloud", "keep_both"} and not cloud_name:
                QMessageBox.warning(self, "Resolve Profile Sync", "Every kept cloud profile needs a name.")
                return
            if action == "keep_both" and local_name.casefold() == cloud_name.casefold():
                QMessageBox.warning(self, "Resolve Profile Sync", "Profiles kept separately must use different names.")
                return

            if action == "use_local":
                final_names.append(local_name.casefold())
            elif action == "use_cloud":
                final_names.append(cloud_name.casefold())
            else:
                final_names.extend([local_name.casefold(), cloud_name.casefold()])

        if len(final_names) != len(set(final_names)):
            QMessageBox.warning(self, "Resolve Profile Sync", "The resolved profiles must use unique names.")
            return
        if any(name in self._reserved_names for name in final_names):
            QMessageBox.warning(
                self,
                "Resolve Profile Sync",
                "A resolved profile name is already used by another local or cloud profile.",
            )
            return

        self.accept()
