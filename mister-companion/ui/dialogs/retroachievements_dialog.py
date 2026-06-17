
import requests
from core.open_helpers import open_uri
from PyQt6.QtCore import QEvent, QPoint, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QComboBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.scaling import set_text_button_min_width
from core.config import save_config
from core.ra_image_cache import RAImageWorker, cache_path_for_url, get_cached_image_bytes
from core.retroachievements_api import get_game_set_options, get_user_summary


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


def make_game_icon_url(data, allow_boxart=False):
    if not isinstance(data, dict):
        return ""

    value = (
        data.get("ImageIcon")
        or data.get("imageIcon")
        or data.get("GameIcon")
        or data.get("gameIcon")
        or data.get("ImageTitle")
        or data.get("imageTitle")
        or ""
    )

    if not value and allow_boxart:
        value = data.get("ImageBoxArt") or data.get("imageBoxArt") or ""

    return normalize_ra_image_url(value)


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
    results = []
    offset = 0
    count = 500

    while True:
        params = {
            "u": username,
            "y": api_key,
            "c": count,
            "o": offset,
        }

        data = fetch_json(
            f"{RA_API_BASE}/API_GetUserCompletionProgress.php",
            params=params,
            timeout=25,
        )

        page_results = []
        total = 0

        if isinstance(data, dict):
            total = data.get("Total") or data.get("total") or 0
            raw_results = (
                data.get("Results")
                or data.get("results")
                or data.get("UserCompletionProgress")
                or data.get("userCompletionProgress")
                or []
            )

            if isinstance(raw_results, list):
                page_results = raw_results
            elif isinstance(raw_results, dict):
                page_results = list(raw_results.values())
        elif isinstance(data, list):
            page_results = data

        results.extend(page_results)

        if len(page_results) < count:
            break

        if total and len(results) >= int(total):
            break

        offset += count

    return results

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


def get_game_extended_info(api_key, game_id):
    params = {
        "y": api_key,
        "i": game_id,
    }

    data = fetch_json(
        f"{RA_API_BASE}/API_GetGameExtended.php",
        params=params,
        timeout=15,
    )

    if isinstance(data, dict):
        return data

    return {}


def safe_int_value(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_game_from_recent(game, awarded=None):
    game_id = (
        game.get("GameID")
        or game.get("gameId")
        or game.get("ID")
        or game.get("id")
        or ""
    )

    award_info = {}
    if isinstance(awarded, dict):
        game_id_text = str(game_id or "")
        award_info = awarded.get(game_id_text) or {}
        if not award_info and game_id_text.isdigit():
            award_info = awarded.get(int(game_id_text)) or {}
        if not isinstance(award_info, dict):
            award_info = {}

    achieved = (
        game.get("NumAwarded")
        or game.get("numAwarded")
        or game.get("NumAchieved")
        or game.get("numAchieved")
        or game.get("NumAwardedToUser")
        or game.get("numAwardedToUser")
        or award_info.get("NumAwarded")
        or award_info.get("numAwarded")
        or award_info.get("NumAchieved")
        or award_info.get("numAchieved")
        or award_info.get("NumAwardedToUser")
        or award_info.get("numAwardedToUser")
        or 0
    )

    hardcore_achieved = (
        game.get("NumAwardedHardcore")
        or game.get("numAwardedHardcore")
        or game.get("NumAchievedHardcore")
        or game.get("numAchievedHardcore")
        or game.get("NumAwardedToUserHardcore")
        or game.get("numAwardedToUserHardcore")
        or award_info.get("NumAwardedHardcore")
        or award_info.get("numAwardedHardcore")
        or award_info.get("NumAchievedHardcore")
        or award_info.get("numAchievedHardcore")
        or award_info.get("NumAwardedToUserHardcore")
        or award_info.get("numAwardedToUserHardcore")
        or 0
    )

    total = (
        game.get("MaxPossible")
        or game.get("maxPossible")
        or game.get("NumPossibleAchievements")
        or game.get("numPossibleAchievements")
        or game.get("NumAchievements")
        or game.get("numAchievements")
        or award_info.get("MaxPossible")
        or award_info.get("maxPossible")
        or award_info.get("NumPossibleAchievements")
        or award_info.get("numPossibleAchievements")
        or award_info.get("NumAchievements")
        or award_info.get("numAchievements")
        or 0
    )

    achieved = safe_int_value(achieved)
    hardcore_achieved = safe_int_value(hardcore_achieved)
    general_achieved = max(achieved, hardcore_achieved)

    return {
        "id": str(game_id),
        "title": game.get("Title") or game.get("title") or "Unknown Game",
        "console": game.get("ConsoleName") or game.get("consoleName") or "",
        "image": make_game_icon_url(game, allow_boxart=False),
        "achieved": general_achieved,
        "softcore_achieved": general_achieved,
        "hardcore_achieved": hardcore_achieved,
        "total": total,
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
        game.get("NumAwarded")
        or game.get("numAwarded")
        or game.get("NumAwardedToUser")
        or game.get("numAwardedToUser")
        or game.get("NumAchieved")
        or game.get("numAchieved")
        or 0
    )

    hardcore_achieved = (
        game.get("NumAwardedHardcore")
        or game.get("numAwardedHardcore")
        or game.get("NumAwardedToUserHardcore")
        or game.get("numAwardedToUserHardcore")
        or game.get("NumAchievedHardcore")
        or game.get("numAchievedHardcore")
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

    achieved = safe_int_value(achieved)
    hardcore_achieved = safe_int_value(hardcore_achieved)
    general_achieved = max(achieved, hardcore_achieved)

    return {
        "id": str(game_id),
        "title": title,
        "console": console,
        "image": make_game_icon_url(game, allow_boxart=True),
        "achieved": general_achieved,
        "softcore_achieved": general_achieved,
        "hardcore_achieved": hardcore_achieved,
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

    date_awarded_hardcore = (
        achievement.get("DateEarnedHardcore")
        or achievement.get("dateEarnedHardcore")
        or ""
    )

    date_awarded_softcore = (
        achievement.get("DateEarned")
        or achievement.get("dateEarned")
        or achievement.get("DateAwarded")
        or achievement.get("dateAwarded")
        or ""
    )

    date_awarded = date_awarded_hardcore or date_awarded_softcore
    hardcore_unlocked = bool(date_awarded_hardcore)
    softcore_unlocked = bool(date_awarded_softcore) or hardcore_unlocked
    unlocked = softcore_unlocked or hardcore_unlocked

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
        "date_awarded_hardcore": date_awarded_hardcore,
        "date_awarded_softcore": date_awarded_softcore,
        "unlocked": unlocked,
        "hardcore_unlocked": hardcore_unlocked,
        "softcore_unlocked": softcore_unlocked,
        "badge_name": badge_name,
        "badge_url": make_badge_url(badge_name),
        "raw": achievement,
    }


class GameIconResolverWorker(QThread):
    icon_found = pyqtSignal(str, str)

    def __init__(self, username, api_key, game_ids):
        super().__init__()
        self.username = username
        self.api_key = api_key
        self.game_ids = list(game_ids or [])

    def run(self):
        seen = set()

        for game_id in self.game_ids:
            game_id = str(game_id or "").strip()

            if not game_id or game_id in seen:
                continue

            seen.add(game_id)
            image_url = ""

            try:
                data = get_game_extended_info(self.api_key, game_id)
                image_url = make_game_icon_url(data, allow_boxart=False)
            except Exception:
                image_url = ""

            if not image_url:
                try:
                    data = get_game_info_and_user_progress(self.username, self.api_key, game_id)
                    image_url = make_game_icon_url(data, allow_boxart=False)
                except Exception:
                    image_url = ""

            if image_url:
                self.icon_found.emit(game_id, image_url)


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
                sets = get_game_set_options(self.api_key, game)
                self.result.emit(
                    self.task,
                    {
                        "game": game,
                        "sets": sets,
                    },
                )
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
        if achievement.get("hardcore_unlocked"):
            self.icon_label.setStyleSheet("border: 2px solid #d4af37; border-radius: 4px;")
        else:
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

        if achievement.get("hardcore_unlocked"):
            status = "Hardcore"
        elif achievement.get("softcore_unlocked"):
            status = "Softcore"
        elif achievement.get("unlocked"):
            status = "Unlocked"
        else:
            status = "Locked"
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
        self.current_sets = []
        self.current_set_id = ""
        self.updating_set_selector = False
        self.pending_auto_select_first_game = False
        self.resize_margin = 8
        self.resizing_window = False
        self.resize_edges = set()
        self.resize_start_pos = QPoint()
        self.resize_start_geometry = None

        self.image_workers = []
        self.image_targets = {}
        self.image_queue = []
        self.active_image_workers = 0
        self.max_image_workers = 6
        self.game_icon_worker = None
        self.game_icon_lookup_attempted = set()
        self.game_list_icon_labels = {}

        self.setWindowTitle("RetroAchievements")
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.MSWindowsFixedSizeDialogHint
        flags |= Qt.WindowType.Window
        flags |= Qt.WindowType.WindowMinimizeButtonHint
        flags |= Qt.WindowType.WindowMaximizeButtonHint
        flags |= Qt.WindowType.WindowCloseButtonHint
        self.setWindowFlags(flags)
        self.setSizeGripEnabled(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.resize(980, 760)
        self.setMinimumSize(820, 560)
        self.setMaximumSize(16777215, 16777215)

        self.build_ui()
        self.install_resize_filters()
        self.load_config_values()

        if self.has_saved_credentials():
            self.login_group.hide()
            self.toggle_login_button.setText("Settings")
            self.refresh_data()
        else:
            self.login_group.show()
            self.toggle_login_button.setText("Hide Settings")
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

        self.refresh_button = QPushButton("Refresh")
        set_text_button_min_width(self.refresh_button, 90)
        self.toggle_login_button = QPushButton("Settings")
        set_text_button_min_width(self.toggle_login_button, 90)
        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(self.refresh_button)
        header_row.addWidget(self.toggle_login_button)

        layout.addLayout(header_row)

        self.login_group = QGroupBox("RetroAchievements Settings")
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

        config_layout.addWidget(QLabel("Username:"), 0, 0)
        config_layout.addWidget(self.username_input, 0, 1, 1, 3)

        config_layout.addWidget(QLabel("API Key:"), 1, 0)
        config_layout.addWidget(self.api_key_input, 1, 1)
        config_layout.addWidget(self.show_key_button, 1, 2)
        config_layout.addWidget(self.get_api_key_button, 1, 3)

        login_buttons_row = QHBoxLayout()
        login_buttons_row.addStretch()
        login_buttons_row.addWidget(self.save_login_button)
        login_buttons_row.addStretch()

        config_layout.addLayout(login_buttons_row, 2, 0, 1, 4)

        layout.addWidget(self.login_group)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

        self.summary_group = QGroupBox("Profile")
        summary_outer_layout = QHBoxLayout(self.summary_group)
        summary_outer_layout.setContentsMargins(10, 12, 10, 10)
        summary_outer_layout.setSpacing(12)

        self.profile_picture_label = QLabel()
        self.profile_picture_label.setFixedSize(72, 72)
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

        game_filter_row = QHBoxLayout()
        game_filter_row.setSpacing(8)
        game_filter_row.addWidget(QLabel("Show:"))
        self.game_filter_combo = QComboBox()
        self.game_filter_combo.addItem("All", "all")
        self.game_filter_combo.addItem("Softcore", "softcore")
        self.game_filter_combo.addItem("Hardcore", "hardcore")
        game_filter_row.addWidget(self.game_filter_combo, stretch=1)
        left_layout.addLayout(game_filter_row)

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

        game_header = QFrame()
        game_header.setFrameShape(QFrame.Shape.StyledPanel)
        game_header_layout = QHBoxLayout(game_header)
        game_header_layout.setContentsMargins(8, 8, 8, 8)
        game_header_layout.setSpacing(10)

        self.selected_game_icon_label = QLabel()
        self.selected_game_icon_label.setFixedSize(72, 72)
        self.selected_game_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.selected_game_icon_label.setStyleSheet("border: 1px solid palette(mid);")
        self.selected_game_icon_label.setText("No\nGame")
        game_header_layout.addWidget(self.selected_game_icon_label)

        game_header_text = QVBoxLayout()
        game_header_text.setContentsMargins(0, 0, 0, 0)
        game_header_text.setSpacing(4)

        self.game_title_label = QLabel("Select a game")
        self.game_title_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        self.game_title_label.setWordWrap(True)

        self.game_info_label = QLabel("Choose a game from Recent or All Games to view achievements.")
        self.game_info_label.setWordWrap(True)
        self.game_info_label.setStyleSheet("color: gray;")

        self.game_points_label = QLabel("Points will appear after selecting a game.")
        self.game_points_label.setWordWrap(True)
        self.game_points_label.setStyleSheet("color: gray;")

        self.selected_game_progress = QProgressBar()
        self.selected_game_progress.setRange(0, 100)
        self.selected_game_progress.setValue(0)
        self.selected_game_progress.setTextVisible(True)
        self.selected_game_progress.setFixedHeight(16)

        game_header_text.addWidget(self.game_title_label)
        game_header_text.addWidget(self.game_info_label)
        game_header_text.addWidget(self.game_points_label)
        game_header_text.addWidget(self.selected_game_progress)
        game_header_layout.addLayout(game_header_text, stretch=1)

        achievements_group_layout.addWidget(game_header)

        self.game_detail_tabs = QTabWidget()

        self.achievements_tab = QWidget()
        achievements_tab_layout = QVBoxLayout(self.achievements_tab)
        achievements_tab_layout.setContentsMargins(0, 0, 0, 0)
        achievements_tab_layout.setSpacing(8)

        filters_row = QHBoxLayout()
        filters_row.setSpacing(8)

        self.set_selector_label = QLabel("Set:")
        self.set_selector_combo = QComboBox()
        self.set_selector_icon = QLabel()
        self.set_selector_icon.setFixedSize(32, 32)
        self.set_selector_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_selector_icon.setStyleSheet("border: 1px solid palette(mid);")

        filters_row.addWidget(self.set_selector_label)
        filters_row.addWidget(self.set_selector_icon)
        filters_row.addWidget(self.set_selector_combo, stretch=2)
        filters_row.addWidget(QLabel("Show:"))

        self.achievement_filter_combo = QComboBox()
        self.achievement_filter_combo.addItem("All", "all")
        self.achievement_filter_combo.addItem("Locked", "locked")
        self.achievement_filter_combo.addItem("Softcore", "softcore")
        self.achievement_filter_combo.addItem("Hardcore", "hardcore")
        filters_row.addWidget(self.achievement_filter_combo, stretch=1)

        achievements_tab_layout.addLayout(filters_row)

        self.set_selector_label.hide()
        self.set_selector_combo.hide()
        self.set_selector_icon.hide()
        self.achievement_filter_combo.setEnabled(False)

        self.achievements_scroll = QScrollArea()
        self.achievements_scroll.setWidgetResizable(True)

        self.achievements_container = QWidget()
        self.achievements_layout = QVBoxLayout(self.achievements_container)
        self.achievements_layout.setContentsMargins(6, 6, 6, 6)
        self.achievements_layout.setSpacing(8)
        self.achievements_layout.addStretch()

        self.achievements_scroll.setWidget(self.achievements_container)
        achievements_tab_layout.addWidget(self.achievements_scroll, stretch=1)

        self.stats_tab = QWidget()
        stats_layout = QGridLayout(self.stats_tab)
        stats_layout.setContentsMargins(12, 12, 12, 12)
        stats_layout.setHorizontalSpacing(10)
        stats_layout.setVerticalSpacing(8)
        self.stats_total_label = QLabel("—")
        self.stats_unlocked_label = QLabel("—")
        self.stats_softcore_label = QLabel("—")
        self.stats_hardcore_label = QLabel("—")
        self.stats_locked_label = QLabel("—")
        self.stats_points_label = QLabel("—")
        self.stats_hardcore_points_label = QLabel("—")
        stats_layout.addWidget(QLabel("Total achievements:"), 0, 0)
        stats_layout.addWidget(self.stats_total_label, 0, 1)
        stats_layout.addWidget(QLabel("Unlocked:"), 1, 0)
        stats_layout.addWidget(self.stats_unlocked_label, 1, 1)
        stats_layout.addWidget(QLabel("Softcore:"), 2, 0)
        stats_layout.addWidget(self.stats_softcore_label, 2, 1)
        stats_layout.addWidget(QLabel("Hardcore:"), 3, 0)
        stats_layout.addWidget(self.stats_hardcore_label, 3, 1)
        stats_layout.addWidget(QLabel("Locked:"), 4, 0)
        stats_layout.addWidget(self.stats_locked_label, 4, 1)
        stats_layout.addWidget(QLabel("Points:"), 5, 0)
        stats_layout.addWidget(self.stats_points_label, 5, 1)
        stats_layout.addWidget(QLabel("Hardcore points:"), 6, 0)
        stats_layout.addWidget(self.stats_hardcore_points_label, 6, 1)
        stats_layout.setRowStretch(7, 1)
        stats_layout.setColumnStretch(1, 1)

        self.game_detail_tabs.addTab(self.achievements_tab, "Achievements")
        self.game_detail_tabs.addTab(self.stats_tab, "Stats")
        achievements_group_layout.addWidget(self.game_detail_tabs, stretch=1)
        right_layout.addWidget(self.achievements_group, stretch=1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter, stretch=1)

        self.toggle_login_button.clicked.connect(self.toggle_login_panel)
        self.show_key_button.clicked.connect(self.toggle_api_key_visible)
        self.get_api_key_button.clicked.connect(self.open_api_key_page)
        self.save_login_button.clicked.connect(self.save_login_and_refresh)
        self.refresh_button.clicked.connect(self.refresh_data)

        self.search_input.textChanged.connect(self.refresh_game_lists)
        self.game_filter_combo.currentIndexChanged.connect(self.refresh_game_lists)
        self.achievement_filter_combo.currentIndexChanged.connect(self.render_current_achievements)
        self.set_selector_combo.currentIndexChanged.connect(self.on_set_selector_changed)
        self.recent_games_list.itemClicked.connect(self.on_game_item_clicked)
        self.all_games_list.itemClicked.connect(self.on_game_item_clicked)

    def install_resize_filters(self):
        self.setMouseTracking(True)
        self.installEventFilter(self)
        for widget in self.findChildren(QWidget):
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        event_type = event.type()

        if event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            global_pos = event.globalPosition().toPoint()
            edges = self.resize_edges_at(self.mapFromGlobal(global_pos))
            if edges:
                self.resizing_window = True
                self.resize_edges = edges
                self.resize_start_pos = global_pos
                self.resize_start_geometry = self.geometry()
                event.accept()
                return True

        if event_type == QEvent.Type.MouseMove:
            global_pos = event.globalPosition().toPoint()
            if self.resizing_window:
                self.resize_to_global_pos(global_pos)
                event.accept()
                return True

            edges = self.resize_edges_at(self.mapFromGlobal(global_pos))
            self.setCursor(self.cursor_for_edges(edges) if edges else Qt.CursorShape.ArrowCursor)

        if event_type == QEvent.Type.MouseButtonRelease and self.resizing_window:
            self.resizing_window = False
            self.resize_edges = set()
            self.resize_start_geometry = None
            event.accept()
            return True

        return super().eventFilter(obj, event)

    def resize_edges_at(self, pos):
        rect = self.rect()
        margin = self.resize_margin
        edges = set()

        if pos.x() <= margin:
            edges.add("left")
        elif pos.x() >= rect.width() - margin:
            edges.add("right")

        if pos.y() <= margin:
            edges.add("top")
        elif pos.y() >= rect.height() - margin:
            edges.add("bottom")

        return edges

    def cursor_for_edges(self, edges):
        if {"top", "left"}.issubset(edges) or {"bottom", "right"}.issubset(edges):
            return Qt.CursorShape.SizeFDiagCursor
        if {"top", "right"}.issubset(edges) or {"bottom", "left"}.issubset(edges):
            return Qt.CursorShape.SizeBDiagCursor
        if "left" in edges or "right" in edges:
            return Qt.CursorShape.SizeHorCursor
        if "top" in edges or "bottom" in edges:
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def resize_to_global_pos(self, global_pos):
        if self.resize_start_geometry is None:
            return

        geometry = self.resize_start_geometry
        delta = global_pos - self.resize_start_pos
        new_geometry = geometry.adjusted(0, 0, 0, 0)
        min_width = self.minimumWidth()
        min_height = self.minimumHeight()

        if "left" in self.resize_edges:
            new_left = geometry.left() + delta.x()
            max_left = geometry.right() - min_width + 1
            new_geometry.setLeft(min(new_left, max_left))

        if "right" in self.resize_edges:
            new_right = geometry.right() + delta.x()
            min_right = geometry.left() + min_width - 1
            new_geometry.setRight(max(new_right, min_right))

        if "top" in self.resize_edges:
            new_top = geometry.top() + delta.y()
            max_top = geometry.bottom() - min_height + 1
            new_geometry.setTop(min(new_top, max_top))

        if "bottom" in self.resize_edges:
            new_bottom = geometry.bottom() + delta.y()
            min_bottom = geometry.top() + min_height - 1
            new_geometry.setBottom(max(new_bottom, min_bottom))

        self.setGeometry(new_geometry)

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
        self.toggle_login_button.setText("Settings")
        self.refresh_data()

    def toggle_login_panel(self):
        if self.login_group.isVisible():
            self.login_group.hide()
            self.toggle_login_button.setText("Settings")
        else:
            self.login_group.show()
            self.toggle_login_button.setText("Hide Settings")

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
            self.toggle_login_button.setText("Hide Settings")
            QMessageBox.warning(self, "RetroAchievements", "Username is required.")
            return

        if not api_key:
            self.login_group.show()
            self.toggle_login_button.setText("Hide Settings")
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
        self.game_points_label.setText("Loading points...")
        self.selected_game_progress.setValue(0)
        self.queue_image_for_label(
            self.selected_game_icon_label,
            game.get("image", ""),
            72,
            fallback_text="No\nGame",
        )

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
            game_data = data.get("game", {}) if isinstance(data, dict) else {}
            set_options = data.get("sets", []) if isinstance(data, dict) else []
            self.populate_game_details(game_data, set_options)
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
        self.game_filter_combo.setEnabled(not busy)
        self.set_selector_combo.setEnabled(not busy and bool(self.current_sets))
        self.achievement_filter_combo.setEnabled(not busy and bool(self.current_achievements))
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
            72,
            fallback_text="No\nImage",
        )

    def populate_game_lists(self, summary, completion):
        self.clear_achievements()

        recent_games_raw = summary.get("RecentlyPlayed") or summary.get("recentlyPlayed") or []
        if not isinstance(recent_games_raw, list):
            recent_games_raw = []

        awarded = summary.get("Awarded") or summary.get("awarded") or {}
        self.recent_games = [
            normalize_game_from_recent(game, awarded)
            for game in recent_games_raw
            if isinstance(game, dict)
        ]

        self.all_games = [
            normalize_game_from_completion(game)
            for game in completion
            if isinstance(game, dict)
        ]

        self.all_games.sort(key=lambda item: item.get("title", "").lower())
        self.game_icon_lookup_attempted.clear()
        self.merge_known_game_images()

        self.refresh_game_lists()
        QTimer.singleShot(0, self.ensure_displayed_game_icons)

        self.current_sets = []
        self.current_set_id = ""
        self.set_selector_combo.clear()
        self.set_selector_label.hide()
        self.set_selector_combo.hide()
        self.set_selector_icon.hide()
        self.achievement_filter_combo.setCurrentIndex(0)
        self.achievement_filter_combo.setEnabled(False)

        self.game_title_label.setText("Select a game")
        self.game_info_label.setText("Choose a game from Recent or All Games to view achievements.")
        self.game_points_label.setText("Points will appear after selecting a game.")
        self.selected_game_progress.setValue(0)
        self.selected_game_icon_label.setText("No\nGame")

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

    def merge_known_game_images(self):
        images_by_id = {}

        for game in self.all_games:
            if not isinstance(game, dict):
                continue

            game_id = str(game.get("id") or "").strip()
            image_url = str(game.get("image") or "").strip()

            if game_id and image_url:
                images_by_id[game_id] = image_url

        for game in self.recent_games:
            if not isinstance(game, dict):
                continue

            if game.get("image"):
                continue

            game_id = str(game.get("id") or "").strip()
            image_url = images_by_id.get(game_id, "")

            if image_url:
                game["image"] = image_url

    def list_widget_game_ids(self, list_widget):
        game_ids = []
        seen = set()

        for row in range(list_widget.count()):
            item = list_widget.item(row)
            game = item.data(Qt.ItemDataRole.UserRole)

            if not isinstance(game, dict):
                continue

            game_id = str(game.get("id") or "").strip()

            if not game_id or game_id in seen:
                continue

            seen.add(game_id)
            game_ids.append(game_id)

        return game_ids

    def prioritized_missing_game_icon_ids(self):
        game_ids = []
        seen = set()

        ordered_ids = []
        ordered_ids.extend(self.list_widget_game_ids(self.recent_games_list))
        ordered_ids.extend(self.list_widget_game_ids(self.all_games_list))

        for collection in (self.recent_games, self.all_games):
            for game in collection:
                if isinstance(game, dict):
                    ordered_ids.append(str(game.get("id") or "").strip())

        games_by_id = {}
        for collection in (self.recent_games, self.all_games):
            for game in collection:
                if isinstance(game, dict):
                    game_id = str(game.get("id") or "").strip()
                    if game_id:
                        games_by_id[game_id] = game

        for game_id in ordered_ids:
            if not game_id or game_id in seen or game_id in self.game_icon_lookup_attempted:
                continue

            game = games_by_id.get(game_id, {})
            if game.get("image"):
                continue

            seen.add(game_id)
            game_ids.append(game_id)

            if len(game_ids) >= 20:
                break

        return game_ids

    def ensure_displayed_game_icons(self):
        self.apply_known_game_images_to_visible_rows()
        self.start_missing_game_icon_lookup()

    def apply_known_game_images_to_visible_rows(self):
        for list_widget in (self.recent_games_list, self.all_games_list):
            for row in range(list_widget.count()):
                item = list_widget.item(row)
                game = item.data(Qt.ItemDataRole.UserRole)

                if not isinstance(game, dict):
                    continue

                image_url = str(game.get("image") or "").strip()
                if not image_url:
                    continue

                row_widget = list_widget.itemWidget(item)
                if row_widget is None:
                    continue

                icon_label = row_widget.findChild(QLabel, "GameIconLabel")
                if icon_label is None:
                    continue

                if icon_label.property("ra_game_image_loaded_url") == image_url:
                    continue

                self.queue_image_for_label(
                    icon_label,
                    image_url,
                    42,
                    fallback_text="—",
                )

    def start_missing_game_icon_lookup(self):
        username = self.username_input.text().strip()
        api_key = self.api_key_input.text().strip()

        if not username or not api_key:
            return

        if self.game_icon_worker is not None and self.game_icon_worker.isRunning():
            return

        game_ids = self.prioritized_missing_game_icon_ids()

        if not game_ids:
            return

        self.game_icon_lookup_attempted.update(game_ids)
        self.game_icon_worker = GameIconResolverWorker(username, api_key, game_ids)
        self.game_icon_worker.icon_found.connect(self.update_game_image)
        self.game_icon_worker.finished.connect(self.on_game_icon_worker_finished)
        self.game_icon_worker.start()

    def on_game_icon_worker_finished(self):
        self.game_icon_worker = None
        if self.prioritized_missing_game_icon_ids():
            QTimer.singleShot(100, self.start_missing_game_icon_lookup)

    def refresh_game_lists(self):
        search_text = self.search_input.text().strip().lower()

        self.game_list_icon_labels.clear()
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

        QTimer.singleShot(0, self.ensure_displayed_game_icons)

    def filtered_games(self, games, search_text):
        results = []
        filter_mode = self.game_filter_combo.currentData() if hasattr(self, "game_filter_combo") else "all"

        for game in games:
            title = str(game.get("title") or "").lower()
            console = str(game.get("console") or "").lower()
            display_name = self.game_display_name(game).lower()

            if search_text and not (
                search_text in title
                or search_text in console
                or search_text in display_name
            ):
                continue

            softcore_achieved = self.safe_int(game.get("softcore_achieved") or game.get("achieved") or 0)
            hardcore_achieved = self.safe_int(game.get("hardcore_achieved") or 0)

            if filter_mode == "softcore" and softcore_achieved <= 0:
                continue

            if filter_mode == "hardcore" and hardcore_achieved <= 0:
                continue

            results.append(game)

        return results

    def safe_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0


    def game_progress_values(self, game):
        achieved = self.safe_int(game.get("achieved") or game.get("softcore_achieved") or 0)
        hardcore_achieved = self.safe_int(game.get("hardcore_achieved") or 0)
        total = self.safe_int(game.get("total") or 0)
        percent = int(round((achieved / total) * 100)) if total else 0
        percent = max(0, min(100, percent))
        return achieved, hardcore_achieved, total, percent

    def game_display_name(self, game):
        title = str(game.get("title") or "Unknown Game").strip()
        console = str(game.get("console") or "").strip()

        if console:
            return f"{title} ({console})"

        return title

    def add_game_item(self, list_widget, game):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, game)

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(6, 6, 6, 6)
        row_layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setObjectName("GameIconLabel")
        icon_label.setFixedSize(42, 42)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("border: 1px solid palette(mid);")
        icon_label.setText("—")
        game_id = str(game.get("id") or "").strip()
        icon_label.setProperty("ra_game_id", game_id)
        row_layout.addWidget(icon_label)

        if game_id:
            self.game_list_icon_labels.setdefault(game_id, []).append(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)

        title_label = QLabel(str(game.get("title") or "Unknown Game"))
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-weight: bold;")
        text_layout.addWidget(title_label)

        achieved, hardcore_achieved, total, percent = self.game_progress_values(game)
        console = str(game.get("console") or "").strip()
        info_parts = []
        if console:
            info_parts.append(console)
        if total:
            info_parts.append(f"{achieved} / {total} • {percent}%")
        if hardcore_achieved:
            info_parts.append(f"HC {hardcore_achieved}")

        info_label = QLabel(" • ".join(info_parts) if info_parts else "No progress data")
        info_label.setStyleSheet("color: gray;")
        info_label.setWordWrap(True)
        text_layout.addWidget(info_label)

        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(percent)
        progress_bar.setTextVisible(False)
        progress_bar.setFixedHeight(8)
        text_layout.addWidget(progress_bar)

        row_layout.addLayout(text_layout, stretch=1)

        item.setSizeHint(row_widget.sizeHint())
        list_widget.addItem(item)
        list_widget.setItemWidget(item, row_widget)

        self.queue_image_for_label(
            icon_label,
            game.get("image", ""),
            42,
            fallback_text="—",
        )

    def update_game_image(self, game_id, image_url):
        game_id = str(game_id or "").strip()
        image_url = str(image_url or "").strip()

        if not game_id or not image_url:
            return

        for collection in (self.recent_games, self.all_games):
            for game in collection:
                if isinstance(game, dict) and str(game.get("id") or "") == game_id:
                    game["image"] = image_url

        labels = list(self.game_list_icon_labels.get(game_id, []))

        for label in labels:
            if label is None:
                continue

            try:
                if label.property("ra_game_id") != game_id:
                    continue

                self.queue_image_for_label(
                    label,
                    image_url,
                    42,
                    fallback_text="—",
                )
            except RuntimeError:
                continue

        for list_widget in (self.recent_games_list, self.all_games_list):
            for row in range(list_widget.count()):
                item = list_widget.item(row)
                game = item.data(Qt.ItemDataRole.UserRole)

                if not isinstance(game, dict) or str(game.get("id") or "") != game_id:
                    continue

                game["image"] = image_url
                item.setData(Qt.ItemDataRole.UserRole, game)

    def on_game_item_clicked(self, item):
        game = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(game, dict):
            return

        self.pending_auto_select_first_game = False
        self.load_game_details(game)

    def populate_game_details(self, data, set_options=None):
        if not isinstance(data, dict):
            data = {}

        game_id = (
            data.get("ID")
            or data.get("id")
            or data.get("GameID")
            or data.get("gameId")
            or self.current_game.get("id", "")
        )
        game_id = str(game_id or "").strip()

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

        selected_game_image = make_game_icon_url(data, allow_boxart=False) or self.current_game.get("image") or ""

        if selected_game_image:
            self.current_game["image"] = selected_game_image
            self.update_game_image(game_id, selected_game_image)
            self.queue_image_for_label(
                self.selected_game_icon_label,
                selected_game_image,
                72,
                fallback_text="No\nGame",
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
                self.safe_int(item.get("raw", {}).get("DisplayOrder") or item.get("raw", {}).get("displayOrder") or 999999),
                str(item.get("title", "")).lower(),
            )
        )

        self.current_achievements = achievements
        self.current_set_id = game_id

        effective_set_options = set_options or []
        if len(effective_set_options) <= 1 and self.current_sets:
            for item in self.current_sets:
                if str(item.get("id") or "") == str(game_id or ""):
                    effective_set_options = self.current_sets
                    break

        self.update_set_selector(effective_set_options, game_id)

        if console:
            self.game_title_label.setText(f"{game_title} ({console})")
        else:
            self.game_title_label.setText(game_title)

        self.render_current_achievements()

    def update_set_selector(self, set_options, current_game_id):
        normalized = []
        seen = set()

        for item in set_options:
            if not isinstance(item, dict):
                continue

            item_id = str(item.get("id") or "").strip()
            if not item_id or item_id in seen:
                continue

            seen.add(item_id)
            normalized.append(item)

        if current_game_id and current_game_id not in seen:
            normalized.insert(
                0,
                {
                    "id": current_game_id,
                    "title": "Base Set",
                    "type": "Base",
                    "image": "",
                },
            )

        self.current_sets = normalized
        self.updating_set_selector = True
        self.set_selector_combo.clear()

        for item in normalized:
            label = str(item.get("title") or "Set").strip()
            set_type = str(item.get("type") or "").strip()
            if set_type and set_type.lower() not in label.lower():
                label = f"{set_type}: {label}"
            self.set_selector_combo.addItem(label, item)

        current_index = 0
        for index, item in enumerate(normalized):
            if str(item.get("id") or "") == str(current_game_id or ""):
                current_index = index
                break

        show_sets = len(normalized) > 1

        if normalized:
            self.set_selector_combo.setCurrentIndex(current_index)
            self.update_set_icon(normalized[current_index])

        self.set_selector_label.setVisible(show_sets)
        self.set_selector_combo.setVisible(show_sets)
        self.set_selector_icon.setVisible(show_sets)
        self.set_selector_combo.setEnabled(show_sets)

        self.updating_set_selector = False

    def update_set_icon(self, set_item):
        image_url = ""
        if isinstance(set_item, dict):
            image_url = set_item.get("image") or ""

        self.queue_image_for_label(
            self.set_selector_icon,
            image_url,
            32,
            fallback_text="—",
        )

    def on_set_selector_changed(self):
        if self.updating_set_selector:
            return

        item = self.set_selector_combo.currentData()
        if not isinstance(item, dict):
            return

        self.update_set_icon(item)
        selected_id = str(item.get("id") or "").strip()

        if not selected_id or selected_id == str(self.current_set_id or ""):
            return

        set_game = {
            "id": selected_id,
            "title": item.get("title") or "Achievement Set",
            "console": self.current_game.get("console") or "",
            "image": item.get("image") or "",
            "source": "set",
            "raw": item,
        }
        self.load_game_details(set_game)

    def filtered_achievements(self):
        mode = self.achievement_filter_combo.currentData() if hasattr(self, "achievement_filter_combo") else "all"
        achievements = []

        for achievement in self.current_achievements:
            unlocked = bool(achievement.get("unlocked"))
            hardcore = bool(achievement.get("hardcore_unlocked"))
            softcore = bool(achievement.get("softcore_unlocked"))

            if mode == "locked" and unlocked:
                continue
            if mode == "softcore" and not softcore:
                continue
            if mode == "hardcore" and not hardcore:
                continue

            achievements.append(achievement)

        return achievements

    def render_current_achievements(self):
        achievements = self.filtered_achievements()
        total = len(self.current_achievements)
        unlocked = sum(1 for achievement in self.current_achievements if achievement.get("unlocked"))
        hardcore = sum(1 for achievement in self.current_achievements if achievement.get("hardcore_unlocked"))
        softcore = sum(1 for achievement in self.current_achievements if achievement.get("softcore_unlocked"))
        locked = max(0, total - unlocked)
        points_total = sum(self.safe_int(achievement.get("points") or 0) for achievement in self.current_achievements)
        points_earned = sum(self.safe_int(achievement.get("points") or 0) for achievement in self.current_achievements if achievement.get("unlocked"))
        hardcore_points = sum(self.safe_int(achievement.get("points") or 0) for achievement in self.current_achievements if achievement.get("hardcore_unlocked"))
        percent = int(round((unlocked / total) * 100)) if total else 0
        percent = max(0, min(100, percent))

        info = f"{unlocked} / {total} achievements  •  Softcore {softcore}  •  Hardcore {hardcore}"
        self.game_info_label.setText(info)
        self.game_points_label.setText(f"Points: {points_earned} / {points_total}  •  Hardcore points: {hardcore_points} / {points_total}")
        self.selected_game_progress.setValue(percent)

        self.stats_total_label.setText(str(total))
        self.stats_unlocked_label.setText(f"{unlocked} ({percent}%)")
        self.stats_softcore_label.setText(str(softcore))
        self.stats_hardcore_label.setText(str(hardcore))
        self.stats_locked_label.setText(str(locked))
        self.stats_points_label.setText(f"{points_earned} / {points_total}")
        self.stats_hardcore_points_label.setText(f"{hardcore_points} / {points_total}")

        self.clear_achievements()
        self.achievement_filter_combo.setEnabled(bool(self.current_achievements))

        if not self.current_achievements:
            empty_label = QLabel("No achievements found for this game.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: gray;")
            self.achievements_layout.addWidget(empty_label)
            self.achievements_layout.addStretch()
            return

        if not achievements:
            empty_label = QLabel("No achievements match the selected filter.")
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
            if label in (self.profile_picture_label, self.set_selector_icon, self.selected_game_icon_label):
                continue
            if getattr(label, "objectName", lambda: "")() == "GameIconLabel":
                continue
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
        hardcore_unlocked = achievement.get("hardcore_unlocked", False)
        softcore_unlocked = achievement.get("softcore_unlocked", False)

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
        if hardcore_unlocked:
            icon_label.setStyleSheet("border: 2px solid #d4af37; border-radius: 3px;")
        else:
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

        if hardcore_unlocked:
            status_text = f"Hardcore • {points} pts"
            if date_awarded:
                status_text += f" • {date_awarded}"
            status_color = "#d4af37"
        elif softcore_unlocked:
            status_text = f"Softcore • {points} pts"
            if date_awarded:
                status_text += f" • {date_awarded}"
            status_color = "#2ecc71"
        elif unlocked:
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

        if label.property("ra_game_image_loaded_url") == url and label.pixmap() is not None:
            return

        label.clear()
        label.setText(fallback_text)

        if not url:
            if label.objectName() == "GameIconLabel":
                label.setProperty("ra_game_image_url", "")
                label.setProperty("ra_game_image_loaded_url", "")
            return

        token = f"{id(label)}:{url}:{size}:{int(bool(grayscale))}"
        label.setProperty("ra_image_token", token)
        if label.objectName() == "GameIconLabel":
            label.setProperty("ra_game_image_url", url)
        self.image_targets[token] = (label, size, fallback_text, bool(grayscale))

        cached_data = self.get_cached_image_data_if_available(url)
        if cached_data:
            self.apply_image_data_to_label(token, cached_data)
            return

        self.image_queue.append((token, url))
        self.start_next_image_workers()

    def get_cached_image_data_if_available(self, url):
        try:
            path = cache_path_for_url(url)
            if path.exists() and path.is_file():
                return path.read_bytes()
        except Exception:
            return b""

        return b""

    def start_next_image_workers(self):
        while self.image_queue and self.active_image_workers < self.max_image_workers:
            token, url = self.image_queue.pop(0)

            if token not in self.image_targets:
                continue

            worker = RAImageWorker(token, url)
            worker.loaded.connect(self.on_image_loaded)
            worker.finished.connect(lambda worker=worker: self.cleanup_image_worker(worker))

            self.image_workers.append(worker)
            self.active_image_workers += 1
            worker.start()

    def on_image_loaded(self, token, data):
        self.apply_image_data_to_label(token, data)

    def apply_image_data_to_label(self, token, data):
        target = self.image_targets.pop(token, None)

        if not target:
            return

        label, size, fallback_text, grayscale = target

        if label.property("ra_image_token") != token:
            return

        if not data:
            label.setText(fallback_text)
            if label.objectName() == "GameIconLabel":
                label.setProperty("ra_game_image_loaded_url", "")
            return

        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            label.setText(fallback_text)
            if label.objectName() == "GameIconLabel":
                label.setProperty("ra_game_image_loaded_url", "")
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
        if label.objectName() == "GameIconLabel":
            label.setProperty("ra_game_image_loaded_url", str(label.property("ra_game_image_url") or ""))

    def cleanup_image_worker(self, worker):
        try:
            if worker in self.image_workers:
                self.image_workers.remove(worker)
        except Exception:
            pass

        self.active_image_workers = max(0, self.active_image_workers - 1)
        self.start_next_image_workers()

    def open_achievement_details(self, achievement):
        dialog = AchievementDetailsDialog(achievement, self)
        dialog.exec()

    def closeEvent(self, event):
        self.pending_auto_select_first_game = False

        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(1500)

        if self.game_icon_worker is not None and self.game_icon_worker.isRunning():
            self.game_icon_worker.wait(1500)

        for worker in list(self.image_workers):
            try:
                if worker.isRunning():
                    worker.wait(1000)
            except Exception:
                pass

        self.image_workers.clear()
        self.image_targets.clear()
        self.image_queue.clear()
        self.active_image_workers = 0

        super().closeEvent(event)