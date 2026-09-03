import json
import posixpath
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
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


RADIO_CONFIG_REMOTE = "/media/fat/Scripts/.config/MiSTerHiFi/radio.json"
RADIO_CONFIG_RELATIVE = Path("Scripts") / ".config" / "MiSTerHiFi" / "radio.json"


def _read_online(connection):
    sftp = connection.client.open_sftp()
    try:
        try:
            with sftp.file(RADIO_CONFIG_REMOTE, "r") as handle:
                raw = handle.read()
        except FileNotFoundError:
            return {"stations": []}
    finally:
        sftp.close()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw or "{}")
    return data if isinstance(data, dict) else {"stations": []}


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
        _mkdirs_sftp(sftp, posixpath.dirname(RADIO_CONFIG_REMOTE))
        payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        with sftp.file(RADIO_CONFIG_REMOTE, "w") as handle:
            handle.write(payload)
    finally:
        sftp.close()


def _read_local(sd_root):
    path = Path(sd_root) / RADIO_CONFIG_RELATIVE
    if not path.is_file():
        return {"stations": []}
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
    return data if isinstance(data, dict) else {"stations": []}


def _write_local(sd_root, data):
    path = Path(sd_root) / RADIO_CONFIG_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class RadioStationEditorDialog(QDialog):
    def __init__(self, station=None, parent=None):
        super().__init__(parent)
        self.result_station = None
        self.original = dict(station or {})

        self.setWindowTitle("Edit Radio Station" if station else "Add Radio Station")
        self.setMinimumWidth(520)
        self._build_ui()
        self._load_station()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        info = QLabel(
            "Add a radio station for MiSTer Hi-Fi. Use a direct audio stream URL, "
            "not the station's website address."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Station name")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/live.mp3")
        self.genre_edit = QLineEdit()
        self.genre_edit.setPlaceholderText("Optional genre")

        form.addRow("Name", self.name_edit)
        form.addRow("Stream URL", self.url_edit)
        form.addRow("Genre", self.genre_edit)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")
        set_text_button_min_width(self.save_button, 90)
        set_text_button_min_width(self.cancel_button, 90)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)

    def _load_station(self):
        self.name_edit.setText(str(self.original.get("name", "") or ""))
        self.url_edit.setText(str(self.original.get("url", "") or ""))
        self.genre_edit.setText(str(self.original.get("genre", "") or ""))

    def _save(self):
        name = self.name_edit.text().strip()
        url = self.url_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Radio Station", "Name is required.")
            return
        if not url:
            QMessageBox.warning(self, "Radio Station", "Stream URL is required.")
            return
        if not url.lower().startswith(("http://", "https://")):
            QMessageBox.warning(self, "Radio Station", "Stream URL must start with http:// or https://.")
            return

        station = dict(self.original)
        station.update({
            "name": name,
            "url": url,
            "genre": self.genre_edit.text().strip(),
        })
        self.result_station = station
        self.accept()


class MisterHiFiRadioDialog(QDialog):
    def __init__(self, connection=None, parent=None, sd_root=None):
        super().__init__(parent)
        self.connection = connection
        self.sd_root = sd_root
        self.offline = bool(sd_root)
        self.data = {"stations": []}
        self.stations = []

        self.setWindowTitle("MiSTer Hi-Fi - Radio Stations")
        self.setMinimumSize(620, 420)
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        info = QLabel(
            "Add or manage internet radio stations used by MiSTer Hi-Fi. "
            "Stations must use direct, supported audio stream URLs."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._edit_selected())
        layout.addWidget(self.list_widget, 1)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Add Radio Station")
        self.edit_button = QPushButton("Edit")
        self.delete_button = QPushButton("Delete")
        set_text_button_min_width(self.add_button, 160)
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

        self.add_button.clicked.connect(self._add_station)
        self.edit_button.clicked.connect(self._edit_selected)
        self.delete_button.clicked.connect(self._delete_selected)
        self.close_button.clicked.connect(self.accept)
        self.list_widget.itemSelectionChanged.connect(self._update_buttons)

    def _load(self):
        try:
            self.data = _read_local(self.sd_root) if self.offline else _read_online(self.connection)
        except Exception as exc:
            QMessageBox.critical(self, "MiSTer Hi-Fi", f"Unable to load radio.json:\n\n{exc}")
            self.reject()
            return
        stations = self.data.get("stations", [])
        self.stations = [dict(item) for item in stations if isinstance(item, dict)] if isinstance(stations, list) else []
        self._refresh()

    def _refresh(self):
        self.list_widget.clear()
        for index, station in enumerate(self.stations):
            name = str(station.get("name", "") or "").strip() or "Unnamed Station"
            url = str(station.get("url", "") or "").strip()
            genre = str(station.get("genre", "") or "").strip()
            subtitle = genre or "No genre"
            if url:
                subtitle += f"  •  {url}"
            item = QListWidgetItem(f"{name}\n{subtitle}")
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

    def _add_station(self):
        dialog = RadioStationEditorDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_station is None:
            return
        self.stations.append(dialog.result_station)
        if self._save():
            self._refresh()
            self.list_widget.setCurrentRow(len(self.stations) - 1)

    def _edit_selected(self):
        index = self._selected_index()
        if index is None or index < 0 or index >= len(self.stations):
            return
        dialog = RadioStationEditorDialog(station=self.stations[index], parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_station is None:
            return
        self.stations[index] = dialog.result_station
        if self._save():
            self._refresh()
            self.list_widget.setCurrentRow(index)

    def _delete_selected(self):
        index = self._selected_index()
        if index is None or index < 0 or index >= len(self.stations):
            return
        station = self.stations[index]
        label = str(station.get("name", "") or "").strip() or "this station"
        answer = QMessageBox.question(
            self,
            "Delete Radio Station",
            f"Remove '{label}' from MiSTer Hi-Fi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed = self.stations.pop(index)
        if not self._save():
            self.stations.insert(index, removed)
            return
        self._refresh()

    def _save(self):
        payload = dict(self.data)
        payload["stations"] = self.stations
        try:
            if self.offline:
                _write_local(self.sd_root, payload)
            else:
                _write_online(self.connection, payload)
            self.data = payload
            return True
        except Exception as exc:
            QMessageBox.critical(self, "MiSTer Hi-Fi", f"Unable to save radio.json:\n\n{exc}")
            return False
