from __future__ import annotations

import html
import socket
from dataclasses import dataclass

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent, QMouseEvent, QPainter, QColor
from PyQt6.QtWidgets import QApplication, QAbstractScrollArea


_BASIC_COLORS = {
    0: "#000000", 1: "#cc0000", 2: "#4e9a06", 3: "#c4a000",
    4: "#3465a4", 5: "#75507b", 6: "#06989a", 7: "#d3d7cf",
    8: "#555753", 9: "#ef2929", 10: "#8ae234", 11: "#fce94f",
    12: "#729fcf", 13: "#ad7fa8", 14: "#34e2e2", 15: "#eeeeec",
}


def _xterm_color(index: int) -> str:
    index = max(0, min(255, int(index)))
    if index < 16:
        return _BASIC_COLORS[index]
    if index < 232:
        value = index - 16
        r, value = divmod(value, 36)
        g, b = divmod(value, 6)
        levels = [0, 95, 135, 175, 215, 255]
        return f"#{levels[r]:02x}{levels[g]:02x}{levels[b]:02x}"
    gray = 8 + (index - 232) * 10
    return f"#{gray:02x}{gray:02x}{gray:02x}"


@dataclass
class Cell:
    ch: str = " "
    fg: str | None = None
    bg: str | None = None
    bold: bool = False
    underline: bool = False
    inverse: bool = False

    def clone(self):
        return Cell(self.ch, self.fg, self.bg, self.bold, self.underline, self.inverse)


class VTScreen:
    def __init__(self, columns=100, rows=30, history_limit=2000):
        self.history_limit = history_limit
        self.history: list[list[Cell]] = []
        self.columns = max(20, columns)
        self.rows = max(5, rows)
        self.cursor_x = 0
        self.cursor_y = 0
        self.saved_cursor = (0, 0)
        self.cursor_visible = True
        self.current = Cell()
        self._state = "normal"
        self._csi = ""
        self._osc = ""
        self._private = False
        self._alternate = False
        self._main_snapshot = None
        self.buffer = [self._blank_row() for _ in range(self.rows)]

    def _blank_row(self):
        return [Cell() for _ in range(self.columns)]

    def reset(self):
        self.history.clear()
        self.buffer = [self._blank_row() for _ in range(self.rows)]
        self.cursor_x = self.cursor_y = 0
        self.current = Cell()

    def resize(self, columns, rows):
        columns = max(20, int(columns))
        rows = max(5, int(rows))
        if columns == self.columns and rows == self.rows:
            return
        old = self.buffer
        self.columns, self.rows = columns, rows
        new = [self._blank_row() for _ in range(rows)]
        for y in range(min(rows, len(old))):
            for x in range(min(columns, len(old[y]))):
                new[y][x] = old[y][x]
        self.buffer = new
        self.cursor_x = min(self.cursor_x, columns - 1)
        self.cursor_y = min(self.cursor_y, rows - 1)

    def _scroll(self):
        if not self._alternate:
            self.history.append([c.clone() for c in self.buffer[0]])
            if len(self.history) > self.history_limit:
                del self.history[: len(self.history) - self.history_limit]
        self.buffer.pop(0)
        self.buffer.append(self._blank_row())
        self.cursor_y = self.rows - 1

    def _newline(self):
        self.cursor_y += 1
        if self.cursor_y >= self.rows:
            self._scroll()

    def _put(self, ch):
        if self.cursor_x >= self.columns:
            self.cursor_x = 0
            self._newline()
        cell = self.current.clone()
        cell.ch = ch
        self.buffer[self.cursor_y][self.cursor_x] = cell
        self.cursor_x += 1

    def feed(self, text: str):
        for ch in text:
            if self._state == "osc":
                if ch == "\x07":
                    self._state = "normal"
                elif ch == "\x1b":
                    self._state = "osc_esc"
                continue
            if self._state == "osc_esc":
                self._state = "normal" if ch == "\\" else "osc"
                continue
            if self._state == "esc":
                if ch == "[":
                    self._state = "csi"
                    self._csi = ""
                    self._private = False
                elif ch == "]":
                    self._state = "osc"
                    self._osc = ""
                elif ch == "7":
                    self.saved_cursor = (self.cursor_x, self.cursor_y)
                    self._state = "normal"
                elif ch == "8":
                    self.cursor_x, self.cursor_y = self.saved_cursor
                    self._state = "normal"
                elif ch == "c":
                    self.reset()
                    self._state = "normal"
                elif ch == "M":
                    if self.cursor_y > 0:
                        self.cursor_y -= 1
                    self._state = "normal"
                else:
                    self._state = "normal"
                continue
            if self._state == "csi":
                if not self._csi and ch == "?":
                    self._private = True
                    continue
                if "@" <= ch <= "~":
                    self._handle_csi(ch, self._csi, self._private)
                    self._state = "normal"
                else:
                    self._csi += ch
                continue
            if ch == "\x1b":
                self._state = "esc"
            elif ch == "\r":
                self.cursor_x = 0
            elif ch == "\n":
                self._newline()
            elif ch == "\b":
                self.cursor_x = max(0, self.cursor_x - 1)
            elif ch == "\t":
                spaces = 8 - (self.cursor_x % 8)
                for _ in range(spaces):
                    self._put(" ")
            elif ch >= " ":
                self._put(ch)

    @staticmethod
    def _params(raw):
        if not raw:
            return [0]
        out = []
        for item in raw.split(";"):
            try:
                out.append(int(item) if item else 0)
            except ValueError:
                out.append(0)
        return out

    def _handle_csi(self, command, raw, private):
        p = self._params(raw)
        n = p[0] or 1
        if command == "A":
            self.cursor_y = max(0, self.cursor_y - n)
        elif command == "B":
            self.cursor_y = min(self.rows - 1, self.cursor_y + n)
        elif command == "C":
            self.cursor_x = min(self.columns - 1, self.cursor_x + n)
        elif command == "D":
            self.cursor_x = max(0, self.cursor_x - n)
        elif command == "E":
            self.cursor_y = min(self.rows - 1, self.cursor_y + n); self.cursor_x = 0
        elif command == "F":
            self.cursor_y = max(0, self.cursor_y - n); self.cursor_x = 0
        elif command in ("G", "`"):
            self.cursor_x = max(0, min(self.columns - 1, n - 1))
        elif command in ("H", "f"):
            row = (p[0] or 1) - 1
            col = (p[1] if len(p) > 1 and p[1] else 1) - 1
            self.cursor_y = max(0, min(self.rows - 1, row))
            self.cursor_x = max(0, min(self.columns - 1, col))
        elif command == "J":
            mode = p[0]
            if mode in (2, 3):
                self.buffer = [self._blank_row() for _ in range(self.rows)]
                if mode == 3:
                    self.history.clear()
                self.cursor_x = self.cursor_y = 0
            elif mode == 0:
                self._erase_line_from_cursor()
                for y in range(self.cursor_y + 1, self.rows):
                    self.buffer[y] = self._blank_row()
        elif command == "K":
            mode = p[0]
            if mode == 0:
                for x in range(self.cursor_x, self.columns): self.buffer[self.cursor_y][x] = Cell()
            elif mode == 1:
                for x in range(0, self.cursor_x + 1): self.buffer[self.cursor_y][x] = Cell()
            elif mode == 2:
                self.buffer[self.cursor_y] = self._blank_row()
        elif command == "m":
            self._sgr(p)
        elif command == "s":
            self.saved_cursor = (self.cursor_x, self.cursor_y)
        elif command == "u":
            self.cursor_x, self.cursor_y = self.saved_cursor
        elif command in ("h", "l") and private:
            enabled = command == "h"
            for mode in p:
                if mode == 25:
                    self.cursor_visible = enabled
                elif mode in (47, 1047, 1049):
                    self._set_alternate(enabled)
        elif command == "P":
            row = self.buffer[self.cursor_y]
            count = min(n, self.columns - self.cursor_x)
            del row[self.cursor_x:self.cursor_x + count]
            row.extend(Cell() for _ in range(count))
        elif command == "@":
            row = self.buffer[self.cursor_y]
            count = min(n, self.columns - self.cursor_x)
            row[self.cursor_x:self.cursor_x] = [Cell() for _ in range(count)]
            del row[self.columns:]
        elif command == "L":
            for _ in range(min(n, self.rows - self.cursor_y)):
                self.buffer.insert(self.cursor_y, self._blank_row()); self.buffer.pop()
        elif command == "M":
            for _ in range(min(n, self.rows - self.cursor_y)):
                self.buffer.pop(self.cursor_y); self.buffer.append(self._blank_row())

    def _erase_line_from_cursor(self):
        for x in range(self.cursor_x, self.columns):
            self.buffer[self.cursor_y][x] = Cell()

    def _set_alternate(self, enabled):
        if enabled and not self._alternate:
            self._main_snapshot = (self.buffer, self.cursor_x, self.cursor_y)
            self.buffer = [self._blank_row() for _ in range(self.rows)]
            self.cursor_x = self.cursor_y = 0
            self._alternate = True
        elif not enabled and self._alternate:
            if self._main_snapshot:
                self.buffer, self.cursor_x, self.cursor_y = self._main_snapshot
            self._main_snapshot = None
            self._alternate = False

    def _sgr(self, p):
        if not p:
            p = [0]
        i = 0
        while i < len(p):
            code = p[i]
            if code == 0:
                self.current = Cell()
            elif code == 1:
                self.current.bold = True
            elif code == 4:
                self.current.underline = True
            elif code == 7:
                self.current.inverse = True
            elif code == 22:
                self.current.bold = False
            elif code == 24:
                self.current.underline = False
            elif code == 27:
                self.current.inverse = False
            elif 30 <= code <= 37:
                self.current.fg = _BASIC_COLORS[code - 30]
            elif 90 <= code <= 97:
                self.current.fg = _BASIC_COLORS[8 + code - 90]
            elif code == 39:
                self.current.fg = None
            elif 40 <= code <= 47:
                self.current.bg = _BASIC_COLORS[code - 40]
            elif 100 <= code <= 107:
                self.current.bg = _BASIC_COLORS[8 + code - 100]
            elif code == 49:
                self.current.bg = None
            elif code in (38, 48) and i + 2 < len(p) and p[i + 1] == 5:
                color = _xterm_color(p[i + 2])
                if code == 38: self.current.fg = color
                else: self.current.bg = color
                i += 2
            elif code in (38, 48) and i + 4 < len(p) and p[i + 1] == 2:
                color = f"#{p[i+2]:02x}{p[i+3]:02x}{p[i+4]:02x}"
                if code == 38: self.current.fg = color
                else: self.current.bg = color
                i += 4
            i += 1

    def top_align_initial_content(self):
        """Top-align only the untouched initial shell output.

        Some MiSTer shells emit enough leading newlines/cursor movement to push
        blank rows into scrollback before drawing the first prompt.  Strip only
        those *leading blank* history rows, then move leading blank screen rows
        below the first visible content.  Once the user types, the caller stops
        invoking this normalization and normal terminal scrolling takes over.
        """
        if self._alternate:
            return

        def row_is_blank(row):
            return all(cell.ch == " " for cell in row)

        # Blank rows can already have been scrolled into history before the
        # first prompt appears.  They are not meaningful initial content.
        while self.history and row_is_blank(self.history[0]):
            del self.history[0]

        # If history now contains real content (for example a login banner),
        # it is already the first visible content and should remain untouched.
        if self.history:
            return

        first_used = None
        for y, row in enumerate(self.buffer):
            if not row_is_blank(row):
                first_used = y
                break

        if first_used is None or first_used == 0:
            return

        shift = first_used
        self.buffer = self.buffer[shift:] + [self._blank_row() for _ in range(shift)]
        self.cursor_y = max(0, self.cursor_y - shift)
        saved_x, saved_y = self.saved_cursor
        self.saved_cursor = (saved_x, max(0, saved_y - shift))

    def to_html(self):
        rows = self.buffer if self._alternate else (self.history + self.buffer)
        pieces = ["<pre style='margin:0; white-space:pre; font-family:monospace;'>"]
        base_fg, base_bg = "#d8d8d8", "#111111"
        for y, row in enumerate(rows):
            screen_y = y - (0 if self._alternate else len(self.history))
            runs = []
            last_style = None
            text = ""
            for x, cell in enumerate(row):
                fg, bg = cell.fg or base_fg, cell.bg or base_bg
                inverse = cell.inverse
                if inverse:
                    fg, bg = bg, fg
                style = (fg, bg, cell.bold, cell.underline)
                if style != last_style and text:
                    runs.append((last_style, text)); text = ""
                last_style = style
                text += cell.ch
            if text:
                runs.append((last_style, text))
            for style, run in runs:
                fg, bg, bold, underline = style
                css = [f"color:{fg}", f"background-color:{bg}"]
                if bold: css.append("font-weight:bold")
                if underline: css.append("text-decoration:underline")
                pieces.append(f"<span style='{';'.join(css)}'>{html.escape(run)}</span>")
            if y != len(rows) - 1:
                pieces.append("\n")
        pieces.append("</pre>")
        return "".join(pieces)


class SSHChannelReader(QThread):
    data_received = pyqtSignal(str)
    closed = pyqtSignal(str)

    def __init__(self, channel, parent=None):
        super().__init__(parent)
        self.channel = channel
        self._stop_requested = False
        self._pending_resize = None

    def request_resize(self, columns, rows):
        self._pending_resize = (int(columns), int(rows))

    def stop(self):
        self._stop_requested = True
        try:
            self.channel.close()
        except Exception:
            pass

    def run(self):
        reason = ""
        try:
            while not self._stop_requested and not self.channel.closed:
                resize = self._pending_resize
                if resize is not None:
                    self._pending_resize = None
                    try:
                        self.channel.resize_pty(width=resize[0], height=resize[1])
                    except Exception:
                        pass

                received = False
                try:
                    # Poll readiness rather than blocking in recv(). Paramiko's
                    # interactive channels buffer data internally, so this keeps
                    # the reader responsive while still draining login banners
                    # and prompts immediately when they arrive.
                    while self.channel.recv_ready():
                        data = self.channel.recv(8192)
                        if not data:
                            break
                        received = True
                        self.data_received.emit(data.decode("utf-8", errors="replace"))

                    while self.channel.recv_stderr_ready():
                        data = self.channel.recv_stderr(8192)
                        if not data:
                            break
                        received = True
                        self.data_received.emit(data.decode("utf-8", errors="replace"))
                except Exception as exc:
                    if not self._stop_requested:
                        reason = str(exc)
                    break

                if not received:
                    self.msleep(15)
        finally:
            self.closed.emit(reason)


class SSHTerminalWidget(QAbstractScrollArea):
    session_closed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setMouseTracking(True)
        self.viewport().setStyleSheet("background: #111111; border: none;")
        self.setStyleSheet("QAbstractScrollArea { background: #111111; border: 1px solid palette(button); border-radius: 6px; }")

        font = QFont("monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        font.setPointSize(10)
        self.setFont(font)

        self.screen = VTScreen()
        self.channel = None
        self.reader = None
        self._pending_output: list[str] = []
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(30)
        self._flush_timer.timeout.connect(self._flush_output)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(50)
        self._resize_timer.timeout.connect(self._apply_pending_resize)
        self._pending_size = None
        self._received_output = False
        self._initial_normalized = False
        self._follow_bottom = True

        self._prompt_nudge_timer = QTimer(self)
        self._prompt_nudge_timer.setSingleShot(True)
        self._prompt_nudge_timer.timeout.connect(self._nudge_prompt_if_blank)

        self._cursor_phase = True
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(500)
        self._cursor_timer.timeout.connect(self._toggle_cursor_phase)
        self._cursor_timer.start()

        self._selection_anchor = None
        self._selection_end = None
        self._drag_selecting = False

        self.verticalScrollBar().valueChanged.connect(lambda _v: self.viewport().update())
        self._update_metrics()
        self._update_scrollbar(force_bottom=True)

    def _update_metrics(self):
        metrics = self.fontMetrics()
        self._char_width = max(1, metrics.horizontalAdvance("M"))
        self._line_height = max(1, metrics.height())
        self._ascent = metrics.ascent()
        self._left_pad = 8
        self._top_pad = 6

    def is_session_active(self):
        return bool(self.channel is not None and not self.channel.closed)

    def attach_channel(self, channel):
        self.disconnect_session(emit_signal=False)
        self.channel = channel
        self._received_output = False
        self._initial_normalized = False
        self._follow_bottom = True
        self._selection_anchor = self._selection_end = None
        self.reader = SSHChannelReader(channel, self)
        self.reader.data_received.connect(self._on_data)
        self.reader.closed.connect(self._on_closed)
        self.reader.start()
        self._prompt_nudge_timer.start(300)
        self._resize_pty()
        self.setFocus()
        self.viewport().update()

    def disconnect_session(self, emit_signal=True):
        self._prompt_nudge_timer.stop()
        self._flush_timer.stop()
        self._pending_output.clear()
        reader = self.reader
        self.reader = None
        channel = self.channel
        self.channel = None
        if reader is not None:
            try:
                reader.closed.disconnect(self._on_closed)
            except Exception:
                pass
            reader.stop()
        elif channel is not None:
            try:
                channel.close()
            except Exception:
                pass
        self.screen.reset()
        self._initial_normalized = False
        self._selection_anchor = self._selection_end = None
        self._update_scrollbar(force_bottom=True)
        self.viewport().update()
        if emit_signal:
            self.session_closed.emit("")

    def clear_terminal(self):
        self.screen.reset()
        self._initial_normalized = True
        self._selection_anchor = self._selection_end = None
        self._update_scrollbar(force_bottom=True)
        self.viewport().update()

    def _on_data(self, text):
        self._received_output = True
        self._prompt_nudge_timer.stop()
        self._pending_output.append(text)
        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def _nudge_prompt_if_blank(self):
        if self.is_session_active() and not self._received_output:
            self._send("\r")

    def _flush_output(self):
        text = "".join(self._pending_output)
        self._pending_output.clear()
        if text:
            self.screen.feed(text)
            if not self._initial_normalized and not self.screen._alternate:
                self.screen.top_align_initial_content()
                rows = self.screen.history + self.screen.buffer
                self._initial_normalized = any(any(cell.ch != " " for cell in row) for row in rows)
        self._update_scrollbar(force_bottom=self._follow_bottom)
        self.viewport().update()
        if not self._pending_output:
            self._flush_timer.stop()

    def _on_closed(self, reason):
        self._prompt_nudge_timer.stop()
        self._flush_output()
        self._flush_timer.stop()
        self.channel = None
        self.reader = None
        self.viewport().update()
        self.session_closed.emit(reason)

    def _all_rows(self):
        return self.screen.buffer if self.screen._alternate else (self.screen.history + self.screen.buffer)

    def _update_scrollbar(self, force_bottom=False):
        if self.screen._alternate:
            max_value = 0
        else:
            max_value = len(self.screen.history)
        bar = self.verticalScrollBar()
        was_bottom = bar.value() >= bar.maximum()
        bar.setPageStep(max(1, self.screen.rows))
        bar.setRange(0, max_value)
        if force_bottom or was_bottom:
            bar.setValue(max_value)

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.fillRect(self.viewport().rect(), QColor("#111111"))
        painter.setFont(self.font())

        rows = self._all_rows()
        start = 0 if self.screen._alternate else self.verticalScrollBar().value()
        visible = rows[start:start + self.screen.rows]
        selection = self._selection_range()

        base_fg = QColor("#d8d8d8")
        base_bg = QColor("#111111")
        sel_bg = self.palette().highlight().color()
        sel_fg = self.palette().highlightedText().color()

        for row_index, row in enumerate(visible):
            y = self._top_pad + row_index * self._line_height
            abs_row = start + row_index
            for x, cell in enumerate(row):
                px = self._left_pad + x * self._char_width
                fg = QColor(cell.fg) if cell.fg else base_fg
                bg = QColor(cell.bg) if cell.bg else base_bg
                if cell.inverse:
                    fg, bg = bg, fg
                selected = selection and self._cell_in_selection(abs_row, x, selection)
                if selected:
                    bg, fg = sel_bg, sel_fg
                if bg != base_bg:
                    painter.fillRect(px, y, self._char_width, self._line_height, bg)
                if cell.ch != " ":
                    f = QFont(self.font())
                    f.setBold(cell.bold)
                    f.setUnderline(cell.underline)
                    painter.setFont(f)
                    painter.setPen(fg)
                    painter.drawText(px, y + self._ascent, cell.ch)

        # Paint the terminal caret only when the live screen is visible.
        if (self.is_session_active() and self._cursor_phase and self.screen.cursor_visible
                and self.hasFocus() and self.verticalScrollBar().value() == self.verticalScrollBar().maximum()):
            cy = self.screen.cursor_y
            cx = min(self.screen.cursor_x, self.screen.columns - 1)
            if 0 <= cy < self.screen.rows:
                px = self._left_pad + cx * self._char_width
                py = self._top_pad + cy * self._line_height
                painter.fillRect(px, py, 2, self._line_height, base_fg)

    def _toggle_cursor_phase(self):
        if self.isVisible():
            self._cursor_phase = not self._cursor_phase
            self.viewport().update()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._cursor_phase = True
        self.viewport().update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_metrics()
        columns = max(20, (self.viewport().width() - self._left_pad * 2) // self._char_width)
        rows = max(5, (self.viewport().height() - self._top_pad * 2) // self._line_height)
        if columns != self.screen.columns or rows != self.screen.rows:
            self._pending_size = (columns, rows)
            self._resize_timer.start()

    def _apply_pending_resize(self):
        size = self._pending_size
        self._pending_size = None
        if size is None:
            return
        columns, rows = size
        if columns == self.screen.columns and rows == self.screen.rows:
            return
        self.screen.resize(columns, rows)
        self._update_scrollbar(force_bottom=self._follow_bottom)
        self._resize_pty()
        self.viewport().update()

    def _resize_pty(self):
        if self.reader is not None and self.is_session_active():
            self.reader.request_resize(self.screen.columns, self.screen.rows)

    def _send(self, data):
        if not self.is_session_active():
            return
        try:
            self.channel.sendall(data.encode("utf-8") if isinstance(data, str) else data)
        except Exception as exc:
            self.session_closed.emit(str(exc))

    def paste_clipboard(self):
        text = QApplication.clipboard().text()
        if text:
            self._follow_bottom = True
            self._update_scrollbar(force_bottom=True)
            self._send(text)

    def copy(self):
        selection = self._selection_range()
        if not selection:
            return
        (r1, c1), (r2, c2) = selection
        rows = self._all_rows()
        lines = []
        for r in range(r1, min(r2 + 1, len(rows))):
            start = c1 if r == r1 else 0
            end = c2 if r == r2 else self.screen.columns - 1
            text = "".join(cell.ch for cell in rows[r][start:end + 1]).rstrip()
            lines.append(text)
        QApplication.clipboard().setText("\n".join(lines))

    def _selection_range(self):
        if self._selection_anchor is None or self._selection_end is None:
            return None
        a, b = self._selection_anchor, self._selection_end
        return (a, b) if a <= b else (b, a)

    @staticmethod
    def _cell_in_selection(row, col, selection):
        (r1, c1), (r2, c2) = selection
        if row < r1 or row > r2:
            return False
        if r1 == r2:
            return c1 <= col <= c2
        if row == r1:
            return col >= c1
        if row == r2:
            return col <= c2
        return True

    def _mouse_cell(self, pos):
        col = max(0, min(self.screen.columns - 1, (int(pos.x()) - self._left_pad) // self._char_width))
        view_row = max(0, min(self.screen.rows - 1, (int(pos.y()) - self._top_pad) // self._line_height))
        base = 0 if self.screen._alternate else self.verticalScrollBar().value()
        return (base + view_row, col)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self._selection_anchor = self._mouse_cell(event.position())
            self._selection_end = self._selection_anchor
            self._drag_selecting = True
            self.viewport().update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_selecting:
            self._selection_end = self._mouse_cell(event.position())
            self.viewport().update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_selecting:
            self._drag_selecting = False
            self._selection_end = self._mouse_cell(event.position())
            self.viewport().update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        bar = self.verticalScrollBar()
        delta = event.angleDelta().y()
        steps = -int(delta / 120) * 3
        bar.setValue(max(bar.minimum(), min(bar.maximum(), bar.value() + steps)))
        self._follow_bottom = bar.value() == bar.maximum()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent):
        self._cursor_phase = True
        self._follow_bottom = True
        self._selection_anchor = self._selection_end = None
        self._update_scrollbar(force_bottom=True)
        self.viewport().update()
        mods = event.modifiers()
        key = event.key()

        if mods & Qt.KeyboardModifier.ControlModifier and mods & Qt.KeyboardModifier.ShiftModifier:
            if key == Qt.Key.Key_C:
                self.copy(); return
            if key == Qt.Key.Key_V:
                self.paste_clipboard(); return

        special = {
            Qt.Key.Key_Up: "\x1b[A", Qt.Key.Key_Down: "\x1b[B",
            Qt.Key.Key_Right: "\x1b[C", Qt.Key.Key_Left: "\x1b[D",
            Qt.Key.Key_Home: "\x1b[H", Qt.Key.Key_End: "\x1b[F",
            Qt.Key.Key_PageUp: "\x1b[5~", Qt.Key.Key_PageDown: "\x1b[6~",
            Qt.Key.Key_Insert: "\x1b[2~", Qt.Key.Key_Delete: "\x1b[3~",
            Qt.Key.Key_Backspace: "\x7f", Qt.Key.Key_Tab: "\t",
            Qt.Key.Key_Backtab: "\x1b[Z", Qt.Key.Key_Return: "\r",
            Qt.Key.Key_Enter: "\r", Qt.Key.Key_Escape: "\x1b",
        }
        if key in special:
            self._send(special[key]); return
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F4:
            self._send(f"\x1bO{chr(ord('P') + key - Qt.Key.Key_F1.value)}"); return
        if Qt.Key.Key_F5 <= key <= Qt.Key.Key_F12:
            codes = [15, 17, 18, 19, 20, 21, 23, 24]
            self._send(f"\x1b[{codes[key - Qt.Key.Key_F5.value]}~"); return
        if mods & Qt.KeyboardModifier.ControlModifier:
            if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
                self._send(chr(key - Qt.Key.Key_A.value + 1)); return
            if key == Qt.Key.Key_BracketLeft:
                self._send("\x1b"); return
        text = event.text()
        if text:
            if mods & Qt.KeyboardModifier.AltModifier:
                text = "\x1b" + text
            self._send(text)

