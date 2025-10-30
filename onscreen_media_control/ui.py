import asyncio
import sys
import os
import threading
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QSlider, QCheckBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QSize, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QFont, QIcon, QPainterPath, QRegion, QColor

from ctypes import POINTER, cast, windll, wintypes
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

from onscreen_media_control.media_backend import safe_get_current_media
from onscreen_media_control.utils import send_key, VK_MEDIA_PLAY_PAUSE, VK_MEDIA_NEXT_TRACK, VK_MEDIA_PREV_TRACK


def resource_path(relative_path: str) -> str:
    """Return absolute path to resource; works in dev and when bundled by PyInstaller."""
    if getattr(sys, "_MEIPASS", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base_path, relative_path)
    return path

# MarqueeLabel
class MarqueeLabel(QLabel):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None,
                 interval: int = 30, step: int = 2, gap: int = 60, pause_ms: int = 2000):
        super().__init__(parent)
        self._full_text = text or ""
        self._interval = interval
        self._step = step
        self._gap = gap
        self._pause_ms = pause_ms
        self._offset = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self.setWordWrap(False)
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def setText(self, text: str):
        self._full_text = text or "-"
        self._offset = 0
        self._update_scroll()
        self.update()

    def _update_scroll(self):
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self._full_text)
        if text_w > self.width():
            if not self._timer.isActive():
                self._timer.start(self._interval)
        else:
            self._timer.stop()
            self._offset = 0

    def _tick(self):
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self._full_text)
        self._offset += self._step
        if self._offset > text_w + self._gap:
            self._offset = 0
            QTimer.singleShot(self._pause_ms, self._resume_scroll)
        self.update()

    def _resume_scroll(self):
        if not self._timer.isActive():
            self._timer.start(self._interval)

    def paintEvent(self, event):
        if not self._full_text:
            return
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self._full_text)
        p = QPainter(self)
        p.setPen(QColor(220, 220, 220))
        baseline = int((self.height() + fm.ascent() - fm.descent()) / 2)
        if text_w <= self.width():
            p.drawText(0, baseline, self._full_text)
        else:
            x1 = -self._offset
            x2 = x1 + text_w + self._gap
            p.drawText(x1, baseline, self._full_text)
            p.drawText(x2, baseline, self._full_text)
        p.end()

# MediaController
class MediaController(QWidget):
    RESIZE_MARGIN = 6
    media_data_signal = pyqtSignal(str, str, bool)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self._corner_radius = 15
        self.setStyleSheet("background: transparent; color: #ddd;")
        self.setMinimumSize(400, 150)
        self.resize(400, 150)
        self._drag_pos: Optional[QPoint] = None
        self._resizing: Optional[str] = None

        self._build_ui()
        self.setMouseTracking(True)
        for child in self.findChildren(QWidget):
            child.setMouseTracking(True)

        self._setup_audio()
        self._connect_signals()
        self.topmost_chk.setChecked(bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))

        # background asyncio loop
        self._async_loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._start_async_loop, daemon=True)
        self._loop_thread.start()
        self.media_data_signal.connect(self._on_media_data)
        self._pending_future = None

        # media update timer
        self._update_interval_ms = 100
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update_media_info)
        self._timer.start(self._update_interval_ms)
        self.update_media_info()

    # UI
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        info_layout = QGridLayout()
        info_layout.setColumnStretch(0, 0)
        info_layout.setColumnStretch(1, 1)

        self.lbl_title_static = QLabel("Title:")
        self.lbl_title_static.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBaseline)
        self.lbl_title_static.setStyleSheet("color: #ddd;")
        self.title_value = MarqueeLabel("", self)
        self.title_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBaseline)
        self.title_value.setMinimumHeight(28)

        self.lbl_artist_static = QLabel("Artist:")
        self.lbl_artist_static.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBaseline)
        self.lbl_artist_static.setStyleSheet("color: #ddd;")
        self.artist_value = MarqueeLabel("", self)
        self.artist_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBaseline)
        self.artist_value.setMinimumHeight(28)

        info_layout.addWidget(self.lbl_title_static, 0, 0)
        info_layout.addWidget(self.title_value, 0, 1)
        info_layout.addWidget(self.lbl_artist_static, 1, 0)
        info_layout.addWidget(self.artist_value, 1, 1)
        layout.addLayout(info_layout)

        controls = QHBoxLayout()
        self.prev_btn = QPushButton()
        self.prev_btn.setIcon(QIcon(resource_path("assets/prev.png")))
        self.play_btn = QPushButton()
        self.play_btn.setIcon(QIcon(resource_path("assets/play.png")))
        self.next_btn = QPushButton()
        self.next_btn.setIcon(QIcon(resource_path("assets/next.png")))

        for btn in (self.prev_btn, self.play_btn, self.next_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                }
                QPushButton:hover {
                    background-color: rgba(255,255,255,0.06);
                    border-radius: 10px;
                }
            """)

        controls.addStretch(1)
        controls.addWidget(self.prev_btn)
        controls.addSpacing(60)
        controls.addWidget(self.play_btn)
        controls.addSpacing(60)
        controls.addWidget(self.next_btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        bottom = QHBoxLayout()
        vol_lbl = QLabel("Vol")
        vol_lbl.setStyleSheet("color: #ddd;")
        trans_lbl = QLabel("Trans")
        trans_lbl.setStyleSheet("color: #ddd;")

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(30, 100)
        self.alpha_slider.setValue(100)
        self.alpha_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.topmost_chk = QCheckBox("Always on top")
        self.topmost_chk.setStyleSheet("color: #ddd;")

        bottom.addWidget(vol_lbl)
        bottom.addWidget(self.volume_slider, 1)
        bottom.addWidget(trans_lbl)
        bottom.addWidget(self.alpha_slider, 1)
        bottom.addWidget(self.topmost_chk)
        layout.addLayout(bottom)

        # Close button
        self.close_btn = QPushButton("✕", self)
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #ddd;
                border: none;
                font-weight: bold;
                font-size: 14pt;
            }
            QPushButton:hover { color: red; }
        """)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.move(self.width() - 30, 5)
        self.close_btn.raise_()

    # Signals
    def _connect_signals(self):
        self.prev_btn.clicked.connect(lambda: self._send_media_key(VK_MEDIA_PREV_TRACK))
        self.play_btn.clicked.connect(lambda: self._send_media_key(VK_MEDIA_PLAY_PAUSE))
        self.next_btn.clicked.connect(lambda: self._send_media_key(VK_MEDIA_NEXT_TRACK))
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.alpha_slider.valueChanged.connect(self._on_alpha_changed)
        self.topmost_chk.stateChanged.connect(self._on_topmost_changed)

    # Drag & Resize
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            gpos = event.globalPosition().toPoint()
            self._resizing = self._detect_edge(event.position().toPoint())
            if not self._resizing:
                self._drag_pos = gpos - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        gpos = event.globalPosition().toPoint()
        if event.buttons() & Qt.MouseButton.LeftButton:
            if self._resizing:
                self._perform_resize(gpos)
            elif self._drag_pos:
                self.move(gpos - self._drag_pos)
        else:
            self._update_cursor(event.position().toPoint())

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resizing = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _update_cursor(self, pos):
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        m = self.RESIZE_MARGIN
        cursor = Qt.CursorShape.ArrowCursor

        if x < m and y < m:
            cursor = Qt.CursorShape.SizeFDiagCursor
        elif x > w - m and y < m:
            cursor = Qt.CursorShape.SizeBDiagCursor
        elif x < m and y > h - m:
            cursor = Qt.CursorShape.SizeBDiagCursor
        elif x > w - m and y > h - m:
            cursor = Qt.CursorShape.SizeFDiagCursor
        elif x < m or x > w - m:
            cursor = Qt.CursorShape.SizeHorCursor
        elif y < m or y > h - m:
            cursor = Qt.CursorShape.SizeVerCursor

        self.setCursor(cursor)

    def _detect_edge(self, pos):
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        m = self.RESIZE_MARGIN

        if x < m and y < m: return "top-left"
        if x > w - m and y < m: return "top-right"
        if x < m and y > h - m: return "bottom-left"
        if x > w - m and y > h - m: return "bottom-right"
        if x < m: return "left"
        if x > w - m: return "right"
        if y < m: return "top"
        if y > h - m: return "bottom"
        return None

    def _perform_resize(self, global_pos):
        geom = self.geometry()
        x, y, w, h = geom.x(), geom.y(), geom.width(), geom.height()
        min_w, min_h = self.minimumWidth(), self.minimumHeight()
        mx, my = global_pos.x(), global_pos.y()

        if "left" in self._resizing:
            new_x = min(mx, x + w - min_w)
            new_w = w + (x - new_x)
            x = new_x
            w = new_w
        if "right" in self._resizing:
            new_w = max(mx - x, min_w)
            w = new_w
        if "top" in self._resizing:
            new_y = min(my, y + h - min_h)
            new_h = h + (y - new_y)
            y = new_y
            h = new_h
        if "bottom" in self._resizing:
            new_h = max(my - y, min_h)
            h = new_h

        self.setGeometry(x, y, w, h)

    # Audio
    def _setup_audio(self):
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self._vol_iface = cast(interface, POINTER(IAudioEndpointVolume))
            current = int(self._vol_iface.GetMasterVolumeLevelScalar() * 100)
            self.volume_slider.setValue(current)
        except Exception as e:
            print(f"[WARN] pycaw init failed: {e}")
            self._vol_iface = None
            self.volume_slider.setEnabled(False)

    # Handlers
    def _on_volume_changed(self, value: int):
        if getattr(self, "_vol_iface", None):
            self._vol_iface.SetMasterVolumeLevelScalar(value / 100.0, None)

    def _on_alpha_changed(self, value: int):
        self.setWindowOpacity(value / 100.0)

    def _set_native_topmost(self, on: bool):
        try:
            hwnd = int(self.winId())
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            flags = SWP_NOMOVE | SWP_NOSIZE
            TOPMOST = -1
            NOTOPMOST = -2
            windll.user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(TOPMOST if on else NOTOPMOST), 0, 0, 0, 0, flags)
        except Exception as e:
            print(f"[WARN] native topmost failed: {e}")

    def _on_topmost_changed(self, state):
        try:
            checked = (state == Qt.CheckState.Checked) or (state == Qt.Checked) or bool(int(state))
        except Exception:
            checked = bool(state)

        try:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
            self.show()
            self.raise_()
            try:
                self.activateWindow()
            except Exception:
                pass
        except Exception as e:
            print(f"[WARN] setWindowFlag failed: {e}")

        try:
            self._set_native_topmost(checked)
        except Exception as e:
            print(f"[WARN] native topmost call failed: {e}")

    def _send_media_key(self, vk_code: int):
        send_key(vk_code)

    # Async
    def _start_async_loop(self):
        """Thread target: run the background asyncio loop forever."""
        asyncio.set_event_loop(self._async_loop)
        self._async_loop.run_forever()

    def update_media_info(self):
        """Schedule safe_get_current_media on the background loop; do not block GUI."""
        # If a previous query is still pending, skip starting a new one.
        if self._pending_future is not None and not self._pending_future.done():
            return

        if not hasattr(self, "_async_loop"):
            return

        try:
            fut = asyncio.run_coroutine_threadsafe(safe_get_current_media(), self._async_loop)
            self._pending_future = fut
            fut.add_done_callback(self._media_future_done)
        except Exception as e:
            print(f"[ERROR] scheduling media query: {e}")

    def _media_future_done(self, fut):
        """Callback running in background thread when the coroutine completes."""
        try:
            title, artist, status, is_playing = fut.result()
            self.media_data_signal.emit(title or "-", artist or "-", bool(is_playing))
        except Exception as e:
            print(f"[ERROR] media future failed: {e}")
            try:
                self.media_data_signal.emit("-", "-", False)
            except Exception:
                pass
        finally:
            if getattr(self, "_pending_future", None) is fut:
                self._pending_future = None

    def _on_media_data(self, title: str, artist: str, is_playing: bool):
        """Slot on main thread to apply media info to widgets."""
        if title != getattr(self.title_value, "_full_text", None):
            self.title_value.setText(title or "-")
        if artist != getattr(self.artist_value, "_full_text", None):
            self.artist_value.setText(artist or "-")
        icon_path = resource_path("assets/pause.png") if is_playing else resource_path("assets/play.png")
        self.play_btn.setIcon(QIcon(icon_path))

    # Close
    def closeEvent(self, event):
        """Stop timer and background loop cleanly on window close."""
        try:
            if hasattr(self, "_timer"):
                self._timer.stop()
            if getattr(self, "_pending_future", None) is not None:
                try:
                    self._pending_future.cancel()
                except Exception:
                    pass
            if hasattr(self, "_async_loop"):
                self._async_loop.call_soon_threadsafe(self._async_loop.stop)
            if hasattr(self, "_loop_thread") and self._loop_thread.is_alive():
                self._loop_thread.join(timeout=1.0)
        except Exception as e:
            print(f"[WARN] error stopping async loop: {e}")
        super().closeEvent(event)

    # Resize
    def resizeEvent(self, event):
        super().resizeEvent(event)
        path = QPainterPath()
        rect = QRectF(0.0, 0.0, float(self.width()), float(self.height()))
        path.addRoundedRect(rect, float(self._corner_radius), float(self._corner_radius))
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)
        self.close_btn.move(self.width() - self.close_btn.width() - 5, 5)
        base_size = max(12, self.width() // 25)
        font = QFont("Segoe UI", base_size)
        bold_font = QFont("Segoe UI", base_size, QFont.Weight.Bold)
        self.lbl_title_static.setFont(bold_font)
        self.lbl_artist_static.setFont(bold_font)
        self.title_value.setFont(font)
        self.artist_value.setFont(font)
        btn_size = max(32, self.width() // 15)
        for btn in (self.prev_btn, self.play_btn, self.next_btn):
            btn.setFixedSize(max(40, btn_size), max(40, btn_size))
            btn.setIconSize(QSize(max(30, btn_size - 4), max(30, btn_size - 4)))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        radius = float(self._corner_radius)
        painter.setBrush(QColor(30, 30, 30))
        painter.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.drawPath(path)
        border_color = QColor(80, 80, 80)
        border_width = 2.0
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(border_color)
        inner_rect = rect.adjusted(border_width / 2, border_width / 2, -border_width / 2, -border_width / 2)
        border_path = QPainterPath()
        border_path.addRoundedRect(inner_rect, radius - 1, radius - 1)
        painter.drawPath(border_path)
        painter.end()
        super().paintEvent(event)
