
import requests
from core.open_helpers import open_uri
from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.scaling import set_text_button_min_width
from core.config import save_config
from core.ra_image_cache import RAImageWorker, get_cached_image_bytes
from core.retroachievements_api import get_user_summary


CONFIG_RA_USERNAME = "retroachievements_username"
CONFIG_RA_API_KEY = "retroachievements_api_key"

RA_API_BASE = "https://retroachievements.org/API"
RA_SITE_BASE = "https://retroachievements.org"
RA_SETTINGS_URL = "https://retroachievements.org/settings"


def normalize_ra_image_url(value):
    value = str(value or "").strip()

    if not value:
        return ""

    if value.startswith("http://") or value.startswith("https://"):
        return value

    if value.startswith("/"):
        return f"{RA_SITE_BASE}{value}"

    return f"{RA_SITE_BASE}/{value}"


def make_badge_url(badge_name):
    badge_name = str(badge_name or "").strip()

    if not badge_name:
        return ""

    if badge_name.startswith("http://") or badge_name.startswith("https://"):
        return badge_name

    if badge_name.endswith(".png"):
        return normalize_ra_image_url(badge_name)

    return f"{RA_SITE_BASE}/Badge/{badge_name}.png"


def make_user_profile_image_url(summary):
    if not isinstance(summary, dict):
        return ""

    value = (
        summary.get("UserPic")
        or summary.get("userPic")
        or summary.get("UserPicUrl")
        or summary.get("userPicUrl")
        or summary.get("Avatar")
        or summary.get("avatar")
        or summary.get("AvatarUrl")
        or summary.get("avatarUrl")
        or summary.get("Image")
        or summary.get("image")
        or ""
    )

    value = str(value or "").strip()

    if value:
        return normalize_ra_image_url(value)

    username = (
        summary.get("User")
        or summary.get("user")
        or summary.get("Username")
        or summary.get("username")
        or ""
    )

    username = str(username or "").strip()

    if username and username != "—":
        return f"{RA_SITE_BASE}/UserPic/{username}.png"

    return ""


def make_pixmap_grayscale(pixmap):
    if pixmap is None or pixmap.isNull():
        return pixmap

    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)

    for y in range(image.height()):
        for x in range(image.width()):
            color = QColor(image.pixel(x, y))
            alpha = color.alpha()
            gray = int(
                (color.red() * 0.299)
                + (color.green() * 0.587)
                + (color.blue() * 0.114)
            )
            color.setRgb(gray, gray, gray, alpha)
            image.setPixelColor(x, y, color)

    return QPixmap.fromImage(image)


def fetch_json(url, params, timeout=20):
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()

    data = response.json()

    if isinstance(data, dict):
        error = data.get("Error") or data.get("error")
        if error:
            raise RuntimeError(str(error))

    return data


def get_user_completion_progress(username, api_key):
    params = {
        "u": username,
        "y": api_key,
    }

    data = fetch_json(
        f"{RA_API_BASE}/API_GetUserCompletionProgress.php",
        params=params,
        timeout=25,
    )

    if isinstance(data, dict):
        results = (
            data.get("Results")
            or data.get("results")
            or data.get("UserCompletionProgress")
            or data.get("userCompletionProgress")
            or []
        )

        if isinstance(results, list):
            return results

        if isinstance(results, dict):
            return list(results.values())

    if isinstance(data, list):
        return data

    return []


def get_game_info_and_user_progress(username, api_key, game_id):
    params = {
        "u": username,
        "y": api_key,
        "g": game_id,
    }

    data = fetch_json(
        f"{RA_API_BASE}/API_GetGameInfoAndUserProgress.php",
        params=params,
        timeout=25,
    )

    if isinstance(data, dict):
        return data

    return {}


def normalize_game_from_recent(game):
    game_id = (
        game.get("GameID")
        or game.get("gameId")
        or game.get("ID")
        or game.get("id")
        or ""
    )

    return {
        "id": str(game_id),
        "title": game.get("Title") or game.get("title") or "Unknown Game",
        "console": game.get("ConsoleName") or game.get("consoleName") or "",
        "image": normalize_ra_image_url(
            game.get("ImageBoxArt")
            or game.get("imageBoxArt")
            or game.get("ImageIcon")
            or game.get("imageIcon")
            or ""
        ),
        "source": "recent",
        "raw": game,
    }


def normalize_game_from_completion(game):
    game_id = (
        game.get("GameID")
        or game.get("gameId")
        or game.get("ID")
        or game.get("id")
        or ""
    )

    title = (
        game.get("Title")
        or game.get("title")
        or game.get("GameTitle")
        or game.get("gameTitle")
        or "Unknown Game"
    )

    console = (
        game.get("ConsoleName")
        or game.get("consoleName")
        or game.get("Console")
        or game.get("console")
        or ""
    )

    achieved = (
        game.get("NumAwardedToUserHardcore")
        or game.get("numAwardedToUserHardcore")
        or game.get("NumAwardedToUser")
        or game.get("numAwardedToUser")
        or game.get("NumAchieved")
        or game.get("numAchieved")
        or 0
    )

    total = (
        game.get("MaxPossible")
        or game.get("maxPossible")
        or game.get("NumPossibleAchievements")
        or game.get("numPossibleAchievements")
        or game.get("NumAchievements")
        or game.get("numAchievements")
        or 0
    )

    return {
        "id": str(game_id),
        "title": title,
        "console": console,
        "image": normalize_ra_image_url(
            game.get("ImageIcon")
            or game.get("imageIcon")
            or game.get("ImageBoxArt")
            or game.get("imageBoxArt")
            or ""
        ),
        "achieved": achieved,
        "total": total,
        "source": "all",
        "raw": game,
    }


def normalize_achievement(game_id, game_title, console, achievement_id, achievement):
    badge_name = (
        achievement.get("BadgeName")
        or achievement.get("badgeName")
        or achievement.get("Badge")
        or achievement.get("badge")
        or ""
    )

    date_awarded = (
        achievement.get("DateEarnedHardcore")
        or achievement.get("dateEarnedHardcore")
        or achievement.get("DateEarned")
        or achievement.get("dateEarned")
        or achievement.get("DateAwarded")
        or achievement.get("dateAwarded")
        or ""
    )

    unlocked = bool(date_awarded)

    return {
        "id": str(
            achievement.get("ID")
            or achievement.get("id")
            or achievement_id
            or ""
        ),
        "game_id": str(game_id or ""),
        "game_title": game_title or "Unknown Game",
        "console": console or "",
        "title": achievement.get("Title") or achievement.get("title") or "Unknown Achievement",
        "description": achievement.get("Description") or achievement.get("description") or "",
        "points": achievement.get("Points") or achievement.get("points") or 0,
        "true_ratio": achievement.get("TrueRatio") or achievement.get("trueRatio") or "",
        "date_awarded": date_awarded,
        "unlocked": unlocked,
        "badge_name": badge_name,
        "badge_url": make_badge_url(badge_name),
        "raw": achievement,
    }


class RetroAchievementsWorker(QThread):
    result = pyqtSignal(str, object)
    error = pyqtSignal(str)

    def __init__(self, task, username, api_key, game_id=None):
        super().__init__()
        self.task = task
        self.username = username
        self.api_key = api_key
        self.game_id = game_id

    def run(self):
        try:
            if self.task == "dashboard":
                summary = get_user_summary(
                    self.username,
                    self.api_key,
                    recent_games=10,
                    recent_achievements=10,
                )

                completion = get_user_completion_progress(
                    self.username,
                    self.api_key,
                )

                self.result.emit(
                    self.task,
                    {
                        "summary": summary,
                        "completion": completion,
                    },
                )
                return

            if self.task == "game":
                game = get_game_info_and_user_progress(
                    self.username,
                    self.api_key,
                    self.game_id,
                )
                self.result.emit(self.task, game)
                return

            raise RuntimeError("Unknown RetroAchievements task.")

        except Exception as e:
            self.error.emit(str(e))


class AchievementDetailsDialog(QDialog):
    def __init__(self, achievement, parent=None):
        super().__init__(parent)

        self.achievement = achievement

        self.setWindowTitle("Achievement Details")
        self.resize(520, 420)
        self.setMinimumSize(440, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel(achievement.get("title", "Achievement"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        layout.addWidget(title)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(96, 96)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("border: 1px solid palette(mid);")

        pixmap = self.load_pixmap_from_cache(
            achievement.get("badge_url", ""),
            96,
            grayscale=not achievement.get("unlocked", False),
        )
        if pixmap is not None:
            self.icon_label.setPixmap(pixmap)
        else:
            self.icon_label.setText("No Icon")

        top_row.addWidget(self.icon_label)

        info_layout = QGridLayout()
        info_layout.setHorizontalSpacing(8)
        info_layout.setVerticalSpacing(6)

        game_title = str(achievement.get("game_title", "Unknown Game"))
        console = str(achievement.get("console", "") or "").strip()
        if console:
            game_title = f"{game_title} ({console})"

        info_layout.addWidget(QLabel("Game:"), 0, 0)
        game_value_label = QLabel(game_title)
        game_value_label.setWordWrap(True)
        info_layout.addWidget(game_value_label, 0, 1)

        info_layout.addWidget(QLabel("Points:"), 1, 0)
        info_layout.addWidget(QLabel(str(achievement.get("points", 0))), 1, 1)

        info_layout.addWidget(QLabel("True Ratio:"), 2, 0)
        info_layout.addWidget(QLabel(str(achievement.get("true_ratio", "") or "—")), 2, 1)

        status = "Unlocked" if achievement.get("unlocked") else "Locked"
        info_layout.addWidget(QLabel("Status:"), 3, 0)
        info_layout.addWidget(QLabel(status), 3, 1)

        date_awarded = achievement.get("date_awarded") or "—"
        info_layout.addWidget(QLabel("Unlocked:"), 4, 0)
        info_layout.addWidget(QLabel(str(date_awarded)), 4, 1)

        top_row.addLayout(info_layout, stretch=1)
        layout.addLayout(top_row)

        description_label = QLabel(achievement.get("description", "") or "No description.")
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(description_label, stretch=1)

        button_row = QHBoxLayout()
        button_row.addStretch()

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)

        button_row.addStretch()
        layout.addLayout(button_row)

    def load_pixmap_from_cache(self, url, size, grayscale=False):
        url = str(url or "").strip()

        if not url:
            return None

        try:
            data = get_cached_image_bytes(url)
            if not data:
                return None

            pixmap = QPixmap()
            if not pixmap.loadFromData(data):
                return None

            pixmap = pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            if grayscale:
                pixmap = make_pixmap_grayscale(pixmap)

            return pixmap
        except Exception:
            return None


class RetroAchievementsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.main_window = parent
        self.worker = None
        self.summary_data = {}
        self.completion_data = []
        self.recent_games = []
        self.all_games = []
        self.current_game = {}
        self.current_achievements = []
        self.pending_auto_select_first_game = False

        self.image_workers = []
        self.image_targets = {}

        self.setWindowTitle("RetroAchievements")
        self.resize(980, 760)
        self.setMinimumSize(820, 560)

        self.build_ui()
        self.load_config_values()

        if self.has_saved_credentials():
            self.login_group.hide()
            self.toggle_login_button.setText("Show Login")
            self.refresh_data()
        else:
            self.login_group.show()
            self.toggle_login_button.setText("Hide Login")
            self.status_label.setText("Enter your RetroAchievements username and Web API key to continue.")
            self.status_label.setStyleSheet("color: gray;")

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        title = QLabel("RetroAchievements")
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.toggle_login_button = QPushButton("Show Login")
        set_text_button_min_width(self.toggle_login_button, 100)
        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(self.toggle_login_button)

        layout.addLayout(header_row)

        self.login_group = QGroupBox("Account")
        config_layout = QGridLayout(self.login_group)
        config_layout.setContentsMargins(10, 12, 10, 10)
        config_layout.setHorizontalSpacing(8)
        config_layout.setVerticalSpacing(8)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("RetroAchievements username")

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("RetroAchievements Web API key")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.show_key_button = QPushButton("Show")
        set_text_button_min_width(self.show_key_button, 70)
        self.get_api_key_button = QPushButton("Get API Key")
        set_text_button_min_width(self.get_api_key_button, 110)
        self.save_login_button = QPushButton("Save / Login")
        self.refresh_button = QPushButton("Refresh")
        self.close_button = QPushButton("Close")

        config_layout.addWidget(QLabel("Username:"), 0, 0)
        config_layout.addWidget(self.username_input, 0, 1, 1, 3)

        config_layout.addWidget(QLabel("API Key:"), 1, 0)
        config_layout.addWidget(self.api_key_input, 1, 1)
        config_layout.addWidget(self.show_key_button, 1, 2)
        config_layout.addWidget(self.get_api_key_button, 1, 3)

        login_buttons_row = QHBoxLayout()
        login_buttons_row.addStretch()
        login_buttons_row.addWidget(self.save_login_button)
        login_buttons_row.addWidget(self.refresh_button)
        login_buttons_row.addStretch()

        config_layout.addLayout(login_buttons_row, 2, 0, 1, 4)

        layout.addWidget(self.login_group)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

        self.summary_group = QGroupBox("Summary")
        summary_outer_layout = QHBoxLayout(self.summary_group)
        summary_outer_layout.setContentsMargins(10, 12, 10, 10)
        summary_outer_layout.setSpacing(12)

        self.profile_picture_label = QLabel()
        self.profile_picture_label.setFixedSize(96, 96)
        self.profile_picture_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.profile_picture_label.setStyleSheet("border: 1px solid palette(mid);")
        self.profile_picture_label.setText("No\nImage")

        summary_outer_layout.addWidget(self.profile_picture_label)

        summary_details_widget = QWidget()
        summary_layout = QGridLayout(summary_details_widget)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setHorizontalSpacing(12)
        summary_layout.setVerticalSpacing(6)

        self.user_value_label = QLabel("—")
        self.points_value_label = QLabel("—")
        self.true_points_value_label = QLabel("—")
        self.rank_value_label = QLabel("—")
        self.status_value_label = QLabel("—")
        self.last_game_value_label = QLabel("—")

        summary_layout.addWidget(QLabel("User:"), 0, 0)
        summary_layout.addWidget(self.user_value_label, 0, 1)

        summary_layout.addWidget(QLabel("Points:"), 0, 2)
        summary_layout.addWidget(self.points_value_label, 0, 3)

        summary_layout.addWidget(QLabel("True Points:"), 1, 0)
        summary_layout.addWidget(self.true_points_value_label, 1, 1)

        summary_layout.addWidget(QLabel("Rank:"), 1, 2)
        summary_layout.addWidget(self.rank_value_label, 1, 3)

        summary_layout.addWidget(QLabel("Status:"), 2, 0)
        summary_layout.addWidget(self.status_value_label, 2, 1)

        summary_layout.addWidget(QLabel("Last Game:"), 2, 2)
        summary_layout.addWidget(self.last_game_value_label, 2, 3)

        summary_layout.setColumnStretch(1, 1)
        summary_layout.setColumnStretch(3, 1)

        summary_outer_layout.addWidget(summary_details_widget, stretch=1)

        layout.addWidget(self.summary_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search games...")
        left_layout.addWidget(self.search_input)

        self.games_tabs = QTabWidget()

        self.recent_games_list = QListWidget()
        self.recent_games_list.setAlternatingRowColors(False)

        self.all_games_list = QListWidget()
        self.all_games_list.setAlternatingRowColors(False)

        self.games_tabs.addTab(self.recent_games_list, "Recent")
        self.games_tabs.addTab(self.all_games_list, "All Games")

        left_layout.addWidget(self.games_tabs)

        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.achievements_group = QFrame()
        self.achievements_group.setFrameShape(QFrame.Shape.StyledPanel)
        self.achievements_group.setObjectName("AchievementsFrame")
        self.achievements_group.setStyleSheet(
            """
            QFrame#AchievementsFrame {
                border: 1px solid palette(mid);
                border-radius: 4px;
            }
            """
        )

        achievements_group_layout = QVBoxLayout(self.achievements_group)
        achievements_group_layout.setContentsMargins(10, 10, 10, 10)
        achievements_group_layout.setSpacing(8)

        self.game_title_label = QLabel("Select a game")
        self.game_title_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        self.game_title_label.setWordWrap(True)

        self.game_info_label = QLabel("Achievements will appear here.")
        self.game_info_label.setWordWrap(True)
        self.game_info_label.setStyleSheet("color: gray;")

        achievements_group_layout.addWidget(self.game_title_label)
        achievements_group_layout.addWidget(self.game_info_label)

        self.achievements_scroll = QScrollArea()
        self.achievements_scroll.setWidgetResizable(True)

        self.achievements_container = QWidget()
        self.achievements_layout = QVBoxLayout(self.achievements_container)
        self.achievements_layout.setContentsMargins(6, 6, 6, 6)
        self.achievements_layout.setSpacing(8)
        self.achievements_layout.addStretch()

        self.achievements_scroll.setWidget(self.achievements_container)

        achievements_group_layout.addWidget(self.achievements_scroll, stretch=1)
        right_layout.addWidget(self.achievements_group, stretch=1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter, stretch=1)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        bottom_row.addWidget(self.close_button)
        bottom_row.addStretch()
        layout.addLayout(bottom_row)

        self.toggle_login_button.clicked.connect(self.toggle_login_panel)
        self.show_key_button.clicked.connect(self.toggle_api_key_visible)
        self.get_api_key_button.clicked.connect(self.open_api_key_page)
        self.save_login_button.clicked.connect(self.save_login_and_refresh)
        self.refresh_button.clicked.connect(self.refresh_data)
        self.close_button.clicked.connect(self.accept)

        self.search_input.textChanged.connect(self.refresh_game_lists)
        self.recent_games_list.itemClicked.connect(self.on_game_item_clicked)
        self.all_games_list.itemClicked.connect(self.on_game_item_clicked)

    def has_saved_credentials(self):
        return bool(self.username_input.text().strip() and self.api_key_input.text().strip())

    def load_config_values(self):
        config = getattr(self.main_window, "config_data", {}) or {}

        self.username_input.setText(config.get(CONFIG_RA_USERNAME, "") or "")
        self.api_key_input.setText(config.get(CONFIG_RA_API_KEY, "") or "")

    def save_config_values(self):
        if not hasattr(self.main_window, "config_data"):
            return

        self.main_window.config_data[CONFIG_RA_USERNAME] = self.username_input.text().strip()
        self.main_window.config_data[CONFIG_RA_API_KEY] = self.api_key_input.text().strip()
        save_config(self.main_window.config_data)

    def save_login_and_refresh(self):
        username = self.username_input.text().strip()
        api_key = self.api_key_input.text().strip()

        if not username:
            QMessageBox.warning(self, "RetroAchievements", "Username is required.")
            return

        if not api_key:
            QMessageBox.warning(self, "RetroAchievements", "Web API key is required.")
            return

        self.save_config_values()
        self.login_group.hide()
        self.toggle_login_button.setText("Show Login")
        self.refresh_data()

    def toggle_login_panel(self):
        if self.login_group.isVisible():
            self.login_group.hide()
            self.toggle_login_button.setText("Show Login")
        else:
            self.login_group.show()
            self.toggle_login_button.setText("Hide Login")

    def toggle_api_key_visible(self):
        if self.api_key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_key_button.setText("Hide")
        else:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_key_button.setText("Show")

    def open_api_key_page(self):
        open_uri(RA_SETTINGS_URL)

    def refresh_data(self):
        username = self.username_input.text().strip()
        api_key = self.api_key_input.text().strip()

        if not username:
            self.login_group.show()
            self.toggle_login_button.setText("Hide Login")
            QMessageBox.warning(self, "RetroAchievements", "Username is required.")
            return

        if not api_key:
            self.login_group.show()
            self.toggle_login_button.setText("Hide Login")
            QMessageBox.warning(self, "RetroAchievements", "Web API key is required.")
            return

        self.save_config_values()

        if self.worker is not None and self.worker.isRunning():
            return

        self.pending_auto_select_first_game = False
        self.set_busy(True)
        self.status_label.setText("Loading RetroAchievements data...")
        self.status_label.setStyleSheet("color: #f39c12; font-weight: bold;")

        self.worker = RetroAchievementsWorker("dashboard", username, api_key)
        self.worker.result.connect(self.on_worker_result)
        self.worker.error.connect(self.on_worker_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def load_game_details(self, game):
        game_id = str(game.get("id") or "").strip()

        if not game_id:
            return

        username = self.username_input.text().strip()
        api_key = self.api_key_input.text().strip()

        if not username or not api_key:
            return

        if self.worker is not None and self.worker.isRunning():
            return

        self.current_game = game
        self.clear_achievements()

        self.game_title_label.setText(self.game_display_name(game))
        self.game_info_label.setText("Loading achievements...")

        self.set_busy(True)

        self.worker = RetroAchievementsWorker("game", username, api_key, game_id=game_id)
        self.worker.result.connect(self.on_worker_result)
        self.worker.error.connect(self.on_worker_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_worker_result(self, task, data):
        if task == "dashboard":
            self.summary_data = data.get("summary", {}) or {}
            self.completion_data = data.get("completion", []) or []

            self.populate_game_lists(self.summary_data, self.completion_data)
            self.populate_summary(self.summary_data)
            self.pending_auto_select_first_game = True

            self.status_label.setText("RetroAchievements data loaded.")
            self.status_label.setStyleSheet("color: #2ecc71; font-weight: bold;")
            return

        if task == "game":
            self.populate_game_details(data)
            self.status_label.setText("Game achievements loaded.")
            self.status_label.setStyleSheet("color: #2ecc71; font-weight: bold;")

    def on_worker_error(self, message):
        self.pending_auto_select_first_game = False
        self.status_label.setText("Failed to load RetroAchievements data.")
        self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        QMessageBox.warning(self, "RetroAchievements", message)

    def on_worker_finished(self):
        finished_task = getattr(self.worker, "task", "")
        self.set_busy(False)
        self.worker = None

        if finished_task == "dashboard" and self.pending_auto_select_first_game:
            self.pending_auto_select_first_game = False
            QTimer.singleShot(0, self.select_first_available_game)

    def set_busy(self, busy):
        self.refresh_button.setEnabled(not busy)
        self.save_login_button.setEnabled(not busy)
        self.toggle_login_button.setEnabled(not busy)
        self.search_input.setEnabled(not busy)
        self.recent_games_list.setEnabled(not busy)
        self.all_games_list.setEnabled(not busy)

    def populate_summary(self, summary):
        user = summary.get("User") or summary.get("user") or "—"
        points = summary.get("TotalPoints") or summary.get("totalPoints") or 0
        true_points = summary.get("TotalTruePoints") or summary.get("totalTruePoints") or 0
        rank = summary.get("Rank") or summary.get("rank") or "—"
        status = summary.get("Status") or summary.get("status") or "—"

        last_game = summary.get("LastGame") or summary.get("lastGame") or {}
        if isinstance(last_game, dict):
            last_game_title = last_game.get("Title") or last_game.get("title") or "—"
            last_game_console = last_game.get("ConsoleName") or last_game.get("consoleName") or ""
            if last_game_console and last_game_title != "—":
                last_game_text = f"{last_game_title} ({last_game_console})"
            else:
                last_game_text = last_game_title
        else:
            last_game_text = "—"

        self.user_value_label.setText(str(user))
        self.points_value_label.setText(str(points))
        self.true_points_value_label.setText(str(true_points))
        self.rank_value_label.setText(str(rank))
        self.status_value_label.setText(str(status))
        self.last_game_value_label.setText(str(last_game_text))

        profile_image_url = make_user_profile_image_url(summary)
        self.queue_image_for_label(
            self.profile_picture_label,
            profile_image_url,
            96,
            fallback_text="No\nImage",
        )

    def populate_game_lists(self, summary, completion):
        self.clear_achievements()

        recent_games_raw = summary.get("RecentlyPlayed") or summary.get("recentlyPlayed") or []
        if not isinstance(recent_games_raw, list):
            recent_games_raw = []

        self.recent_games = [
            normalize_game_from_recent(game)
            for game in recent_games_raw
            if isinstance(game, dict)
        ]

        self.all_games = [
            normalize_game_from_completion(game)
            for game in completion
            if isinstance(game, dict)
        ]

        self.all_games.sort(key=lambda item: item.get("title", "").lower())

        self.refresh_game_lists()

        self.game_title_label.setText("Select a game")
        self.game_info_label.setText("Choose a game from Recent or All Games to view achievements.")

    def select_first_available_game(self):
        if self.worker is not None and self.worker.isRunning():
            return False

        list_widgets = [
            self.recent_games_list,
            self.all_games_list,
        ]

        for list_widget in list_widgets:
            for row in range(list_widget.count()):
                item = list_widget.item(row)
                game = item.data(Qt.ItemDataRole.UserRole)

                if isinstance(game, dict):
                    self.games_tabs.setCurrentWidget(list_widget)
                    list_widget.setCurrentItem(item)
                    self.load_game_details(game)
                    return True

        return False

    def refresh_game_lists(self):
        search_text = self.search_input.text().strip().lower()

        self.recent_games_list.clear()
        self.all_games_list.clear()

        recent_games = self.filtered_games(self.recent_games, search_text)
        all_games = self.filtered_games(self.all_games, search_text)

        if recent_games:
            for game in recent_games:
                self.add_game_item(self.recent_games_list, game)
        else:
            item = QListWidgetItem("No recent games found.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_games_list.addItem(item)

        if all_games:
            for game in all_games:
                self.add_game_item(self.all_games_list, game)
        else:
            item = QListWidgetItem("No games found.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.all_games_list.addItem(item)

    def filtered_games(self, games, search_text):
        if not search_text:
            return list(games)

        results = []

        for game in games:
            title = str(game.get("title") or "").lower()
            console = str(game.get("console") or "").lower()
            display_name = self.game_display_name(game).lower()

            if (
                search_text in title
                or search_text in console
                or search_text in display_name
            ):
                results.append(game)

        return results

    def game_display_name(self, game):
        title = str(game.get("title") or "Unknown Game").strip()
        console = str(game.get("console") or "").strip()

        if console:
            return f"{title} ({console})"

        return title

    def add_game_item(self, list_widget, game):
        text = self.game_display_name(game)

        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, game)
        list_widget.addItem(item)

    def on_game_item_clicked(self, item):
        game = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(game, dict):
            return

        self.pending_auto_select_first_game = False
        self.load_game_details(game)

    def populate_game_details(self, data):
        if not isinstance(data, dict):
            data = {}

        game_id = (
            data.get("ID")
            or data.get("id")
            or data.get("GameID")
            or data.get("gameId")
            or self.current_game.get("id", "")
        )

        game_title = (
            data.get("Title")
            or data.get("title")
            or self.current_game.get("title")
            or "Unknown Game"
        )

        console = (
            data.get("ConsoleName")
            or data.get("consoleName")
            or self.current_game.get("console")
            or ""
        )

        achievements_raw = data.get("Achievements") or data.get("achievements") or {}

        achievements = []

        if isinstance(achievements_raw, dict):
            for achievement_id, achievement in achievements_raw.items():
                if isinstance(achievement, dict):
                    achievements.append(
                        normalize_achievement(
                            game_id,
                            game_title,
                            console,
                            achievement_id,
                            achievement,
                        )
                    )

        achievements.sort(
            key=lambda item: (
                not item.get("unlocked", False),
                str(item.get("title", "")).lower(),
            )
        )

        self.current_achievements = achievements

        total = len(achievements)
        unlocked = sum(1 for achievement in achievements if achievement.get("unlocked"))

        if console:
            self.game_title_label.setText(f"{game_title} ({console})")
        else:
            self.game_title_label.setText(game_title)

        info = f"{unlocked} / {total} achievements"
        self.game_info_label.setText(info)

        self.clear_achievements()

        if not achievements:
            empty_label = QLabel("No achievements found for this game.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: gray;")
            self.achievements_layout.addWidget(empty_label)
            self.achievements_layout.addStretch()
            return

        for achievement in achievements:
            self.add_achievement_widget(achievement)

        self.achievements_layout.addStretch()

    def clear_achievements(self):
        keys_to_remove = []

        for token, target in self.image_targets.items():
            label = target[0]
            if label is not self.profile_picture_label:
                keys_to_remove.append(token)

        for token in keys_to_remove:
            self.image_targets.pop(token, None)

        while self.achievements_layout.count():
            item = self.achievements_layout.takeAt(0)

            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def add_achievement_widget(self, achievement):
        unlocked = achievement.get("unlocked", False)

        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setCursor(Qt.CursorShape.PointingHandCursor)

        if unlocked:
            frame.setStyleSheet("")
        else:
            frame.setStyleSheet("color: gray;")

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setFixedSize(48, 48)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("border: 1px solid palette(mid);")

        self.queue_image_for_label(
            icon_label,
            achievement.get("badge_url", ""),
            48,
            fallback_text="—",
            grayscale=not unlocked,
        )

        layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)

        title = QLabel(achievement.get("title", "Unknown Achievement"))
        title.setWordWrap(True)

        if unlocked:
            title.setStyleSheet("font-weight: bold;")
        else:
            title.setStyleSheet("font-weight: bold; color: gray;")

        description = QLabel(achievement.get("description", ""))
        description.setWordWrap(True)
        description.setStyleSheet("color: gray;")

        points = achievement.get("points", 0)
        date_awarded = achievement.get("date_awarded") or ""

        if unlocked:
            status_text = f"Unlocked • {points} pts"
            if date_awarded:
                status_text += f" • {date_awarded}"
            status_color = "#2ecc71"
        else:
            status_text = f"Locked • {points} pts"
            status_color = "gray"

        status = QLabel(status_text)
        status.setStyleSheet(f"color: {status_color}; font-weight: bold;")

        text_layout.addWidget(title)
        if achievement.get("description"):
            text_layout.addWidget(description)
        text_layout.addWidget(status)

        layout.addLayout(text_layout, stretch=1)

        frame.mousePressEvent = lambda event, item=achievement: self.open_achievement_details(item)

        self.achievements_layout.addWidget(frame)

    def queue_image_for_label(self, label, url, size, fallback_text="—", grayscale=False):
        url = str(url or "").strip()

        label.clear()
        label.setText(fallback_text)

        if not url:
            return

        token = f"{id(label)}:{url}:{size}:{int(bool(grayscale))}"
        label.setProperty("ra_image_token", token)
        self.image_targets[token] = (label, size, fallback_text, bool(grayscale))

        worker = RAImageWorker(token, url)
        worker.loaded.connect(self.on_image_loaded)
        worker.finished.connect(lambda worker=worker: self.cleanup_image_worker(worker))

        self.image_workers.append(worker)
        worker.start()

    def on_image_loaded(self, token, data):
        target = self.image_targets.pop(token, None)

        if not target:
            return

        label, size, fallback_text, grayscale = target

        if label.property("ra_image_token") != token:
            return

        if not data:
            label.setText(fallback_text)
            return

        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            label.setText(fallback_text)
            return

        pixmap = pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        if grayscale:
            pixmap = make_pixmap_grayscale(pixmap)

        label.setPixmap(pixmap)

    def cleanup_image_worker(self, worker):
        try:
            if worker in self.image_workers:
                self.image_workers.remove(worker)
        except Exception:
            pass

    def open_achievement_details(self, achievement):
        dialog = AchievementDetailsDialog(achievement, self)
        dialog.exec()

    def closeEvent(self, event):
        self.pending_auto_select_first_game = False

        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(1500)

        for worker in list(self.image_workers):
            try:
                if worker.isRunning():
                    worker.wait(1000)
            except Exception:
                pass

        self.image_workers.clear()
        self.image_targets.clear()

        super().closeEvent(event)