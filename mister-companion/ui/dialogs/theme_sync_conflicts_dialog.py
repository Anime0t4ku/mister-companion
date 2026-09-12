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

from core.custom_themes import THEME_SYNC_ID_KEY, normalize_theme_id


class ThemeSyncConflictsDialog(QDialog):
    def __init__(self, conflicts: list[dict], reserved_theme_ids: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resolve Theme Sync")
        self.resize(820, 560)
        self._rows = []
        self._reserved_ids = {
            normalize_theme_id(value)
            for value in (reserved_theme_ids or [])
            if normalize_theme_id(value)
        }

        root = QVBoxLayout(self)
        intro = QLabel(
            "Companion found Theme Creator themes that were changed independently. "
            "Choose which version to keep, or keep both as separate themes."
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

            reason = QLabel(str(conflict.get("reason") or "Theme conflict"))
            reason.setWordWrap(True)
            group_layout.addWidget(reason)

            compare = QHBoxLayout()
            local_form = QFormLayout()
            cloud_form = QFormLayout()

            local_name = QLineEdit(str(local.get("name") or ""))
            cloud_name = QLineEdit(str(cloud.get("name") or ""))
            local_id = QLabel(normalize_theme_id(local.get("id")))
            cloud_id = QLabel(normalize_theme_id(cloud.get("id")))

            local_form.addRow("Local name:", local_name)
            local_form.addRow("Local ID:", local_id)
            local_form.addRow("Local author:", QLabel(str(local.get("author") or "Unknown")))
            local_form.addRow("Background:", QLabel(str(local.get("background") or "")))
            local_form.addRow("Surface:", QLabel(str(local.get("surface") or "")))
            local_form.addRow("Accent:", QLabel(str(local.get("accent") or "")))
            local_form.addRow("Text:", QLabel(str(local.get("text") or "")))

            cloud_form.addRow("Cloud name:", cloud_name)
            cloud_form.addRow("Cloud ID:", cloud_id)
            cloud_form.addRow("Cloud author:", QLabel(str(cloud.get("author") or "Unknown")))
            cloud_form.addRow("Background:", QLabel(str(cloud.get("background") or "")))
            cloud_form.addRow("Surface:", QLabel(str(cloud.get("surface") or "")))
            cloud_form.addRow("Accent:", QLabel(str(cloud.get("accent") or "")))
            cloud_form.addRow("Text:", QLabel(str(cloud.get("text") or "")))

            compare.addLayout(local_form, 1)
            compare.addSpacing(18)
            compare.addLayout(cloud_form, 1)
            group_layout.addLayout(compare)

            action = QComboBox()
            action.addItem("Use Local Theme", "use_local")
            action.addItem("Use Cloud Theme", "use_cloud")
            action.addItem("Keep Both Themes", "keep_both")
            group_layout.addWidget(action)

            hint = QLabel()
            hint.setWordWrap(True)
            group_layout.addWidget(hint)

            row = {
                "conflict": conflict,
                "action": action,
                "local_name": local_name,
                "cloud_name": cloud_name,
                "local_id": local_id,
                "cloud_id": cloud_id,
                "hint": hint,
            }
            self._rows.append(row)
            action.currentIndexChanged.connect(lambda _value, r=row: self._update_row(r))
            local_name.textChanged.connect(lambda _value, r=row: self._update_ids(r))
            cloud_name.textChanged.connect(lambda _value, r=row: self._update_ids(r))
            self._update_row(row)
            self._update_ids(row)
            body_layout.addWidget(group)

        body_layout.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _update_row(self, row: dict):
        action = str(row["action"].currentData() or "")
        keep_both = action == "keep_both"
        row["local_name"].setEnabled(keep_both)
        row["cloud_name"].setEnabled(keep_both)

        if keep_both:
            local_name = row["local_name"].text().strip()
            cloud_name = row["cloud_name"].text().strip()
            if local_name and normalize_theme_id(local_name) == normalize_theme_id(cloud_name):
                row["cloud_name"].setText(f"{cloud_name} Cloud")

        messages = {
            "use_local": "Keep the local version and make it the synced version everywhere.",
            "use_cloud": "Replace the local version with the cloud version.",
            "keep_both": "Keep both versions as separate Theme Creator themes. Their names must produce different Theme IDs.",
        }
        row["hint"].setText(messages.get(action, ""))
        self._update_ids(row)

    def _update_ids(self, row: dict):
        row["local_id"].setText(normalize_theme_id(row["local_name"].text()))
        row["cloud_id"].setText(normalize_theme_id(row["cloud_name"].text()))

    def resolutions(self) -> list[dict]:
        result = []
        for row in self._rows:
            conflict = row["conflict"]
            result.append({
                "local_id": str(conflict.get("local_id") or ""),
                "action": str(row["action"].currentData() or ""),
                "local_name": row["local_name"].text().strip(),
                "cloud_name": row["cloud_name"].text().strip(),
            })
        return result

    def _validate_and_accept(self):
        claimed = set(self._reserved_ids)

        for row in self._rows:
            action = str(row["action"].currentData() or "")
            if action != "keep_both":
                continue

            local_name = row["local_name"].text().strip()
            cloud_name = row["cloud_name"].text().strip()
            local_id = normalize_theme_id(local_name)
            cloud_id = normalize_theme_id(cloud_name)

            if not local_name or not cloud_name or not local_id or not cloud_id:
                QMessageBox.warning(self, "Resolve Theme Sync", "Both themes need valid names.")
                return
            if local_id == cloud_id:
                QMessageBox.warning(self, "Resolve Theme Sync", "Themes kept separately must use different Theme IDs.")
                return
            if local_id in claimed or cloud_id in claimed:
                QMessageBox.warning(
                    self,
                    "Resolve Theme Sync",
                    "One of the resolved Theme IDs is already used by another installed Theme Creator theme.",
                )
                return

            claimed.add(local_id)
            claimed.add(cloud_id)

        self.accept()
