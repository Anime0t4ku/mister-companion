from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.update_all_config import CUSTOM_SOURCE_SYNC_ID_KEY


class UpdateAllSourceSyncConflictsDialog(QDialog):
    def __init__(self, conflicts: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resolve Custom Source Sync")
        self.resize(860, 560)
        self._rows = []

        root = QVBoxLayout(self)
        intro = QLabel(
            "Companion found local and cloud Update_All custom sources with the same database ID "
            "but different details. Choose which version should be kept and synced to all devices."
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

            database_id = str(local.get("database_id") or cloud.get("database_id") or "")
            group_layout.addWidget(QLabel(f"Database ID: {database_id}"))

            compare = QHBoxLayout()
            local_form = QFormLayout()
            cloud_form = QFormLayout()

            local_form.addRow("Local name:", self._value_label(local.get("display_name")))
            local_form.addRow("Local URL:", self._value_label(local.get("db_url")))
            local_form.addRow("Local INI:", self._value_label(local.get("ini_block")))

            cloud_form.addRow("Cloud name:", self._value_label(cloud.get("display_name")))
            cloud_form.addRow("Cloud URL:", self._value_label(cloud.get("db_url")))
            cloud_form.addRow("Cloud INI:", self._value_label(cloud.get("ini_block")))

            compare.addLayout(local_form, 1)
            compare.addSpacing(18)
            compare.addLayout(cloud_form, 1)
            group_layout.addLayout(compare)

            action = QComboBox()
            action.addItem("Keep Local", "keep_local")
            action.addItem("Keep Cloud", "keep_cloud")
            group_layout.addWidget(action)

            hint = QLabel("The selected version becomes the shared custom source on all linked devices.")
            hint.setWordWrap(True)
            group_layout.addWidget(hint)

            self._rows.append({"conflict": conflict, "action": action})
            body_layout.addWidget(group)

        body_layout.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @staticmethod
    def _value_label(value) -> QLabel:
        text = str(value or "").strip() or "(none)"
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(label.textInteractionFlags())
        return label

    def resolutions(self) -> list[dict]:
        result = []
        for row in self._rows:
            local = row["conflict"].get("local") or {}
            result.append({
                "local_id": str(local.get(CUSTOM_SOURCE_SYNC_ID_KEY) or ""),
                "action": str(row["action"].currentData() or ""),
            })
        return result
