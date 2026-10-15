"""
measure_tool_v2.py
------------------
Precision Image Measurement, Bead Contour & Polygon Tool (PyQt5)

TOOLS (left rail):
  Calibrate   two points of known distance -> px/mm scale
  Line        straight 2-point distance
  Bead        multi-point polyline (inner bead / curved contour) -> total arc length
  Polygon     labelme-style shape: click vertices, the cursor snaps to the first
              point to close it, then you name it. Shows area and perimeter.

LABELS (every measurement has one):
  drag to move it   |  double-click to rename  |  right-click for colour / order / delete
  the table on the right does the same: click the swatch for colour, double-click the
  name to edit it, Up / Down to reorder (numbers follow the order).

KEYS:
  Esc         cancel what you are drawing (or leave full screen)
  Enter       finish a bead path / close a polygon      Backspace  remove last point
  Wheel       zoom at cursor       Alt+Wheel / Shift+Wheel   scroll sideways
  Ctrl+Drag   pan (or middle mouse)  Ctrl+0 fit   Ctrl+1 1:1   Ctrl+Z undo   F11 full screen

OPTIONAL: put marker_snap.py next to this file to enable sub-pixel snapping of clicks
(calibration, line and bead points). Polygon vertices are never snapped.
"""

import math
import os
import sys

from PyQt5.QtCore import QByteArray, QPoint, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QBrush, QColor, QConicalGradient, QFontDatabase, QFontMetricsF, QIcon,
    QKeySequence, QPainter, QPainterPath, QPalette, QPen, QPixmap, QPolygonF,
    QRadialGradient,
)
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QAbstractItemView, QAction, QApplication, QButtonGroup, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGraphicsItem, QGraphicsObject, QGraphicsPixmapItem, QGraphicsScene,
    QGraphicsView, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QShortcut, QSlider,
    QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

try:  # optional companion module (sub-pixel click snapping)
    from marker_snap import snap_to_mark_centre, load_image_array
    HAVE_SNAP = True
except Exception:
    HAVE_SNAP = False


# ── THEME ─────────────────────────────────────────────────────────────────────
class Theme:
    """Colour tokens. Amber = calibration, green = line, orange = bead, cyan = drafting."""
    BG = "#14171A"
    BAR = "#101316"
    PANEL = "#181C21"
    CARD = "#1B1F24"
    FIELD = "#222830"
    BORDER = "#2A3038"
    TEXT = "#D5DBE1"
    MUTED = "#8F9AA6"
    ACCENT = "#F5A524"
    GREEN = "#3DDC84"
    CYAN = "#2EC4F1"
    ORANGE = "#FF7A3D"
    RED = "#FF6B6B"
    SANS = '"IBM Plex Sans", "Segoe UI", "Inter", "Helvetica Neue", sans-serif'
    MONO = '"IBM Plex Mono", "Consolas", "Menlo", "DejaVu Sans Mono", monospace'


PRESET_COLORS = ["#3DDC84", "#2EC4F1", "#F5A524", "#FF7A3D", "#FF5C5C", "#FF6FB5",
                 "#B388FF", "#7C8CFF", "#FFD54F", "#C6FF4D", "#FFFFFF", "#9AA4AF"]
POLY_COLORS = ["#B388FF", "#FF6FB5", "#4DD0E1", "#FFD54F", "#C6FF4D", "#7C8CFF"]
DEFAULT_COLOR = {"straight": Theme.GREEN, "bead": Theme.ORANGE}


def qc(hex_color: str, alpha: int = 255) -> QColor:
    color = QColor(hex_color)
    color.setAlpha(alpha)
    return color


_QSS = """
QWidget{background:@BG;color:@TEXT;font-family:@SANS;font-size:13px}
QLabel{background:transparent}
QMainWindow,QDialog{background:@BG}
QToolTip{background:@PANEL;color:@TEXT;border:1px solid @BORDER;padding:4px}

QMenuBar{background:@BAR;border-bottom:1px solid @BORDER;padding:0 6px}
QMenuBar::item{padding:6px 10px;background:transparent;color:#C4CBD3}
QMenuBar::item:selected{background:@FIELD}
QMenu{background:@PANEL;border:1px solid @BORDER;padding:4px}
QMenu::item{padding:6px 28px 6px 14px}
QMenu::item:selected{background:@FIELD}
QMenu::separator{height:1px;background:@BORDER;margin:4px 8px}

QFrame#Bar{background:@PANEL;border:0;border-bottom:1px solid @BORDER}
QFrame#RailBar{background:@PANEL;border:0;border-right:1px solid @BORDER}
QFrame#Sidebar{background:@PANEL;border:0;border-left:1px solid @BORDER}
QFrame#Sep{background:#2F3640;border:0}
QFrame#Rule{background:@BORDER;border:0}
QFrame#Card{background:@CARD;border:1px solid @BORDER;border-radius:6px}
QFrame#Card > QWidget{background:transparent}
QLabel#CardTitle{color:@MUTED;font-size:11px;font-weight:600}
QLabel#Key{color:@MUTED}
QLabel#Value{font-family:@MONO}
QLabel#Hint{color:#C4CBD3;padding:0 14px 12px 14px}
QLabel#Snap{color:@MUTED;font-size:11px}

QPushButton,QToolButton{background:@FIELD;border:1px solid #2F3640;border-radius:4px;
    padding:6px 12px;color:@TEXT;font-weight:500}
QPushButton:hover,QToolButton:hover{background:#2A313A}
QPushButton:pressed{background:#1A1F25}
QPushButton:disabled{color:#5B6570}
QPushButton#Primary{background:@ACCENT;border-color:@ACCENT;color:#14171A;font-weight:600;padding:10px}
QPushButton#Primary:hover{background:#FFB938}
QPushButton#Outline{background:transparent;border-color:@ACCENT;color:@ACCENT}
QPushButton#Outline:hover{background:#2A2418}
QPushButton#Small{padding:4px 10px;font-size:12px}
QPushButton#Seg{border:0;border-radius:0;border-right:1px solid #2F3640;font-family:@MONO;padding:6px 14px}
QPushButton#Seg:checked{background:@ACCENT;color:#14171A;font-weight:600}
QPushButton#Swatch{border:2px solid #2F3640;border-radius:4px;padding:0;
    min-width:24px;max-width:24px;min-height:24px;max-height:24px}
QPushButton#Swatch:hover{border-color:#FFFFFF}
QFrame#SegGroup{background:@FIELD;border:1px solid #2F3640;border-radius:4px}
QToolButton#Rail{background:transparent;border:0;border-left:2px solid transparent;border-radius:4px;padding:0}
QToolButton#Rail:hover{background:@FIELD}
QToolButton#Rail:checked{background:#2A2418;border-left:2px solid @ACCENT}

QTableWidget{background:transparent;border:0;gridline-color:transparent;font-family:@MONO;
    selection-background-color:#2A313A;selection-color:@TEXT}
QTableWidget::item{padding:4px 6px;border-bottom:1px solid #20262C}
QTableWidget QLineEdit{padding:2px 4px}
QHeaderView{background:transparent}
QHeaderView::section{background:transparent;color:@MUTED;border:0;padding:6px 6px;font-size:11px;font-weight:600}

QLineEdit,QDoubleSpinBox,QSpinBox,QComboBox{background:@FIELD;border:1px solid #2F3640;border-radius:4px;
    padding:5px 8px;font-family:@MONO;selection-background-color:@ACCENT;selection-color:#14171A}
QComboBox QAbstractItemView{background:@PANEL;selection-background-color:@FIELD;border:1px solid @BORDER}
QCheckBox{spacing:8px;background:transparent}
QCheckBox::indicator{width:16px;height:16px;border:1px solid #3A424B;border-radius:3px;background:@FIELD}
QCheckBox::indicator:checked{background:@ACCENT;border-color:@ACCENT}
QSlider::groove:horizontal{height:6px;background:@FIELD;border-radius:3px}
QSlider::handle:horizontal{background:@ACCENT;width:14px;margin:-5px 0;border-radius:7px}
QDialogButtonBox QPushButton{min-width:72px}

QGraphicsView{background:#0E1013;border:0}
QScrollArea{background:@PANEL;border:0;border-left:1px solid @BORDER}
QScrollBar:vertical{background:@BG;width:12px;margin:0}
QScrollBar:horizontal{background:@BG;height:12px;margin:0}
QScrollBar::handle:vertical{background:#2F3640;border-radius:5px;min-height:30px;margin:2px}
QScrollBar::handle:horizontal{background:#2F3640;border-radius:5px;min-width:30px;margin:2px}
QScrollBar::add-line,QScrollBar::sub-line{height:0;width:0}
QScrollBar::add-page,QScrollBar::sub-page{background:transparent}

QStatusBar{background:@BAR;border-top:1px solid @BORDER;color:#9AA4AF;font-family:@MONO;font-size:11px}
QStatusBar::item{border:0}
QStatusBar QLabel{font-family:@MONO;font-size:11px;padding:0 8px}
"""


def build_stylesheet() -> str:
    """Return the app stylesheet with @TOKENS replaced by Theme values."""
    tokens = [(n, v) for n, v in vars(Theme).items() if n.isupper()]
    css = _QSS
    for name, value in sorted(tokens, key=lambda t: -len(t[0])):
        css = css.replace(f"@{name}", value)
    return css


def apply_dark_palette(app: QApplication) -> None:
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(Theme.BG))
    pal.setColor(QPalette.WindowText, QColor(Theme.TEXT))
    pal.setColor(QPalette.Base, QColor(Theme.BAR))
    pal.setColor(QPalette.AlternateBase, QColor(Theme.PANEL))
    pal.setColor(QPalette.Text, QColor(Theme.TEXT))
    pal.setColor(QPalette.Button, QColor(Theme.FIELD))
    pal.setColor(QPalette.ButtonText, QColor(Theme.TEXT))
    pal.setColor(QPalette.ToolTipBase, QColor(Theme.PANEL))
    pal.setColor(QPalette.ToolTipText, QColor(Theme.TEXT))
    pal.setColor(QPalette.Highlight, QColor(Theme.ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("#14171A"))
    app.setPalette(pal)


# ── SMALL WIDGET HELPERS ──────────────────────────────────────────────────────
_SVG = {
    "calibrate": '<rect x="2" y="8" width="20" height="8" rx="1"/><path d="M6 8v3M10 8v4M14 8v3M18 8v4"/>',
    "straight": '<circle cx="5" cy="19" r="2"/><circle cx="19" cy="5" r="2"/><path d="M6.5 17.5l11-11"/>',
    "bead": '<path d="M3 18c4-10 14-10 18 0"/><circle cx="3" cy="18" r="1.6"/><circle cx="12" cy="9.5" r="1.6"/><circle cx="21" cy="18" r="1.6"/>',
    "polygon": '<path d="M12 3l8.5 6.2-3.2 10H6.7L3.5 9.2z"/>',
    "loupe": '<circle cx="10" cy="10" r="6"/><path d="M15 15l6 6M10 7v6M7 10h6"/>',
}


def make_icon(name: str, size: int = 20) -> QIcon:
    """Stroke icon from inline SVG: muted when off, amber when checked."""
    icon = QIcon()
    for color, state in ((Theme.MUTED, QIcon.Off), (Theme.ACCENT, QIcon.On)):
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
               f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" '
               f'stroke-linejoin="round">{_SVG[name]}</svg>')
        pix = QPixmap(size * 2, size * 2)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        QSvgRenderer(QByteArray(svg.encode())).render(painter)
        painter.end()
        icon.addPixmap(pix, QIcon.Normal, state)
    return icon


def swatch_icon(hex_color: str, size: int = 14) -> QIcon:
    """Rounded colour square for the table's colour column."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(hex_color))
    p.setPen(QPen(QColor("#FFFFFF"), 1))
    p.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), 3, 3)
    p.end()
    return QIcon(pix)


def make_separator() -> QFrame:
    sep = QFrame()
    sep.setObjectName("Sep")
    sep.setFixedSize(1, 24)
    return sep


def make_card(title: str, body: QWidget, right: QWidget = None) -> QFrame:
    """Titled card: small caps title, optional widget on the right, hairline, body."""
    card = QFrame()
    card.setObjectName("Card")
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    head = QWidget()
    row = QHBoxLayout(head)
    row.setContentsMargins(14, 10, 14, 10)
    lbl = QLabel(title.upper())
    lbl.setObjectName("CardTitle")
    row.addWidget(lbl)
    row.addStretch()
    if right is not None:
        row.addWidget(right)

    rule = QFrame()
    rule.setObjectName("Rule")
    rule.setFixedHeight(1)
    outer.addWidget(head)
    outer.addWidget(rule)
    outer.addWidget(body, 1)
    return card


def make_row(key: str, value_label: QLabel) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(14, 8, 14, 8)
    k = QLabel(key)
    k.setObjectName("Key")
    value_label.setObjectName("Value")
    value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    lay.addWidget(k)
    lay.addStretch()
    lay.addWidget(value_label)
    return row


# ── UNITS / GEOMETRY HELPERS ──────────────────────────────────────────────────
UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}
DISPLAY_UNITS = ("mm", "cm", "in", "px")


def format_distance(mm_val, target_unit="mm"):
    if target_unit == "cm":
        return f"{mm_val / 10.0:.2f} cm"
    elif target_unit == "in":
        return f"{mm_val / 25.4:.3f} in"
    elif target_unit == "m":
        return f"{mm_val / 1000.0:.4f} m"
    return f"{mm_val:.2f} mm"


def format_area(mm2_val, target_unit="mm"):
    if target_unit == "cm":
        return f"{mm2_val / 100.0:.2f} cm²"
    elif target_unit == "in":
        return f"{mm2_val / 645.16:.3f} in²"
    elif target_unit == "m":
        return f"{mm2_val / 1e6:.6f} m²"
    return f"{mm2_val:,.1f} mm²"


def path_length(pts, closed=False) -> float:
    total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
    if closed and len(pts) > 2:
        total += math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1])
    return total


def polygon_area_centroid(pts):
    """Shoelace area and centroid (falls back to the vertex mean for degenerate shapes)."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-9:
        return 0.0, (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    return abs(a), (cx / (6 * a), cy / (6 * a))


# ── MOVABLE LABEL ─────────────────────────────────────────────────────────────
class LabelItem(QGraphicsObject):
    """Label pill that can be dragged. Stores its offset in the measurement dict."""
    is_label = True
    edit_requested = pyqtSignal(object)
    menu_requested = pyqtSignal(object, QPoint)

    def __init__(self, m, text, color, anchor, home, k):
        super().__init__()
        self.m, self.text, self.k = m, text, k
        self.color = QColor(color)
        self.anchor = QPointF(*anchor)
        self.home = QPointF(*home)
        self._font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self._font.setBold(True)
        self._font.setPixelSize(int(13 * k))
        r = QFontMetricsF(self._font).boundingRect(QRectF(0, 0, 10000, 10000), Qt.AlignLeft, text)
        pad = 6 * k
        self._rect = QRectF(-r.width() / 2 - pad, -r.height() / 2 - pad / 2,
                            r.width() + 2 * pad, r.height() + pad)
        off = m.get("label_off")
        self._leader_on = off is not None
        self.setPos(self.home + (QPointF(*off) if off else QPointF(0, 0)))
        self.setZValue(20)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setCursor(Qt.SizeAllCursor)
        self.setToolTip("Drag to move  |  double-click to rename  |  right-click for options")
        self._press_pos = self.pos()

    def boundingRect(self):
        rect = QRectF(self._rect)
        if self._leader_on:
            a = self.anchor - self.pos()
            rect = rect.united(QRectF(QPointF(0, 0), a).normalized())
        m = 6 * self.k
        return rect.adjusted(-m, -m, m, m)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            self.prepareGeometryChange()
        return super().itemChange(change, value)

    def paint(self, p, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        k = self.k
        if self._leader_on:
            a = self.anchor - self.pos()
            p.setPen(QPen(qc(self.color.name(), 200), 1.2 * k, Qt.DashLine))
            p.drawLine(QPointF(0, 0), a)
            p.setBrush(self.color)
            p.setPen(Qt.NoPen)
            p.drawEllipse(a, 3 * k, 3 * k)
        p.setPen(QPen(self.color, 1.2 * k))
        p.setBrush(qc(Theme.BAR, 225))
        p.drawRoundedRect(self._rect, 3 * k, 3 * k)
        p.setFont(self._font)
        p.setPen(QColor("white"))
        p.drawText(self._rect, Qt.AlignCenter, self.text)

    def mousePressEvent(self, event):
        self._press_pos = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.commit_move()

    def commit_move(self):
        """Remember where the label was dropped (offset from its default spot)."""
        if self.pos() != self._press_pos:
            d = self.pos() - self.home
            self.m["label_off"] = (d.x(), d.y())
            self._leader_on = True
            self._press_pos = self.pos()
            self.update()

    def mouseDoubleClickEvent(self, event):
        self.edit_requested.emit(self.m)
        event.accept()


# ── GRAPHICS VIEW WITH ZOOM & PAN ─────────────────────────────────────────────
class ZoomPanGraphicsView(QGraphicsView):
    mouse_moved = pyqtSignal(QPointF)
    clicked_image = pyqtSignal(QPointF)
    double_clicked_image = pyqtSignal(QPointF)
    right_clicked_image = pyqtSignal(QPointF)
    view_changed = pyqtSignal()

    MIN_ZOOM, MAX_ZOOM = 0.02, 80.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFrameShape(QFrame.NoFrame)
        self._is_panning = False
        self._pan_start = QPointF()
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().setCursor(Qt.CrossCursor)

    def _label_at(self, pos):
        item = self.itemAt(pos)
        return item if getattr(item, "is_label", False) else None

    def wheelEvent(self, event):
        # Qt on some platforms swaps the wheel axis while Alt is held, so read both
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta == 0:
            return
        if event.modifiers() & (Qt.AltModifier | Qt.ShiftModifier):   # sideways scroll
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - delta)
            event.accept()
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        if self.MIN_ZOOM <= self.transform().m11() * factor <= self.MAX_ZOOM:
            self.scale(factor, factor)
            self.view_changed.emit()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self.view_changed.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.view_changed.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton or (
                event.button() == Qt.LeftButton and event.modifiers() & Qt.ControlModifier):
            self._is_panning = True
            self._pan_start = QPointF(event.pos())
            self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        label = self._label_at(event.pos())
        if label is not None:                      # labels handle their own clicks
            if event.button() == Qt.RightButton:
                label.menu_requested.emit(label.m, event.globalPos())
                event.accept()
            else:
                super().mousePressEvent(event)
            return
        if event.button() == Qt.RightButton:
            self.right_clicked_image.emit(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.clicked_image.emit(self.mapToScene(event.pos()))

    def mouseDoubleClickEvent(self, event):
        if self._label_at(event.pos()) is not None:
            super().mouseDoubleClickEvent(event)
        elif event.button() == Qt.LeftButton:
            self.double_clicked_image.emit(self.mapToScene(event.pos()))
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_panning:
            delta = QPointF(event.pos()) - self._pan_start
            self._pan_start = QPointF(event.pos())
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - delta.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)
        grabber = self.scene().mouseGrabberItem() if self.scene() else None
        if getattr(grabber, "is_label", False):    # dragging a label: no drafting updates
            return
        self.mouse_moved.emit(self.mapToScene(event.pos()))

    def mouseReleaseEvent(self, event):
        if self._is_panning:
            self._is_panning = False
            self.viewport().setCursor(Qt.CrossCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


# ── RULER ─────────────────────────────────────────────────────────────────────
class Ruler(QWidget):
    """Ruler in image pixels. Redraws from the view's transform, so it tracks zoom/pan."""
    THICK = 22

    def __init__(self, view: QGraphicsView, horizontal: bool):
        super().__init__()
        self.view = view
        self.horizontal = horizontal
        self.cursor_scene = None
        if horizontal:
            self.setFixedHeight(self.THICK)
        else:
            self.setFixedWidth(self.THICK)

    def set_cursor(self, scene_pos):
        self.cursor_scene = scene_pos
        self.update()

    @staticmethod
    def nice_step(min_step: float) -> float:
        if min_step <= 1:
            return 1.0
        mag = 10 ** math.floor(math.log10(min_step))
        for m in (1, 2, 5, 10):
            if m * mag >= min_step:
                return float(m * mag)
        return float(10 * mag)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), qc(Theme.BAR))
        scale = self.view.transform().m11()
        if scale <= 0:
            return
        length = self.width() if self.horizontal else self.height()
        origin = self.view.mapToScene(0, 0)
        start = origin.x() if self.horizontal else origin.y()
        step = self.nice_step(70.0 / scale)
        minor = step / 5.0

        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        font.setPixelSize(9)
        p.setFont(font)

        first = int(math.floor(start / minor))
        last = int(math.floor((start + length / scale) / minor)) + 1
        for i in range(first, last + 1):
            value = i * minor
            pos = (value - start) * scale
            is_major = i % 5 == 0
            p.setPen(qc("#5A646F" if is_major else "#38404A"))
            tick = 10 if is_major else 4
            if self.horizontal:
                p.drawLine(int(pos), self.THICK - tick, int(pos), self.THICK)
            else:
                p.drawLine(self.THICK - tick, int(pos), self.THICK, int(pos))
            if is_major and value >= 0:
                p.setPen(qc(Theme.MUTED))
                text = f"{value:g}"
                if self.horizontal:
                    p.drawText(int(pos) + 3, 10, text)
                else:
                    p.save()
                    p.translate(2, int(pos) + 3)
                    p.rotate(90)
                    p.drawText(0, 0, text)
                    p.restore()

        if self.cursor_scene is not None:
            c = self.cursor_scene.x() if self.horizontal else self.cursor_scene.y()
            pos = int((c - start) * scale)
            p.setPen(QPen(qc(Theme.ACCENT), 1))
            if self.horizontal:
                p.drawLine(pos, 0, pos, self.THICK)
            else:
                p.drawLine(0, pos, self.THICK, pos)

        p.setPen(qc(Theme.BORDER))
        if self.horizontal:
            p.drawLine(0, self.THICK - 1, self.width(), self.THICK - 1)
        else:
            p.drawLine(self.THICK - 1, 0, self.THICK - 1, self.height())


# ── MAGNIFIER LOUPE WIDGET ────────────────────────────────────────────────────
class MagnifierWidget(QWidget):
    def __init__(self, parent=None, size=150, zoom_factor=3.0):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.zoom_factor = zoom_factor
        self.pixmap = None
        self.center_pos = QPointF(0, 0)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint)
        self.hide()

    def set_source_pixmap(self, pixmap):
        self.pixmap = pixmap

    def set_target(self, img_pos):
        self.center_pos = img_pos
        self.update()

    def paintEvent(self, event):
        if self.pixmap is None or self.pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        path = QPainterPath()
        path.addEllipse(0, 0, self.width(), self.height())
        painter.setClipPath(path)
        painter.fillRect(self.rect(), qc(Theme.BAR))
        src_w = self.width() / self.zoom_factor
        src_h = self.height() / self.zoom_factor
        src_rect = QRectF(self.center_pos.x() - src_w / 2.0,
                          self.center_pos.y() - src_h / 2.0, src_w, src_h)
        painter.drawPixmap(QRectF(0, 0, self.width(), self.height()), self.pixmap, src_rect)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        painter.setPen(QPen(qc(Theme.GREEN), 1.5))
        painter.drawLine(int(cx - 12), int(cy), int(cx + 12), int(cy))
        painter.drawLine(int(cx), int(cy - 12), int(cx), int(cy + 12))
        painter.setClipping(False)
        painter.setPen(QPen(qc(Theme.CYAN), 3))
        painter.drawEllipse(1, 1, self.width() - 2, self.height() - 2)


# ── COLOUR PICKER (presets + hue/saturation wheel + brightness) ───────────────
class ColorWheel(QWidget):
    """Hue (angle) / saturation (radius) disc. Brightness comes from the slider."""
    changed = pyqtSignal(float, float)       # hue 0-1, saturation 0-1

    def __init__(self, size=190):
        super().__init__()
        self.setFixedSize(size, size)
        self.h, self.s, self.v = 0.0, 0.0, 1.0
        self.setCursor(Qt.CrossCursor)

    def set_hsv(self, h, s, v):
        self.h, self.s, self.v = h, s, v
        self.update()

    def _geom(self):
        c = QPointF(self.width() / 2.0, self.height() / 2.0)
        return c, self.width() / 2.0 - 4

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c, r = self._geom()
        clip = QPainterPath()
        clip.addEllipse(c, r, r)
        p.setClipPath(clip)
        hue = QConicalGradient(c, 0)
        for i in range(7):
            hue.setColorAt(i / 6.0, QColor.fromHsv((i * 60) % 360, 255, 255))
        p.fillRect(self.rect(), QBrush(hue))
        sat = QRadialGradient(c, r)
        sat.setColorAt(0, QColor(255, 255, 255, 255))
        sat.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(self.rect(), QBrush(sat))
        p.fillRect(self.rect(), QColor(0, 0, 0, int(255 * (1 - self.v))))
        p.setClipping(False)
        p.setPen(QPen(qc(Theme.BORDER), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, r, r)
        ang = self.h * 2 * math.pi
        m = QPointF(c.x() + self.s * r * math.cos(ang), c.y() - self.s * r * math.sin(ang))
        p.setPen(QPen(QColor("black"), 3))
        p.drawEllipse(m, 7, 7)
        p.setPen(QPen(QColor("white"), 1.5))
        p.drawEllipse(m, 7, 7)

    def _pick(self, pos):
        c, r = self._geom()
        dx, dy = pos.x() - c.x(), c.y() - pos.y()
        s = min(1.0, math.hypot(dx, dy) / r)
        h = (math.atan2(dy, dx) % (2 * math.pi)) / (2 * math.pi)
        self.changed.emit(h, s)

    def mousePressEvent(self, e):
        self._pick(e.pos())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._pick(e.pos())


class ColorPickerDialog(QDialog):
    """Presets, your recent custom colours, and a colour wheel for anything else."""

    def __init__(self, initial, custom, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Label colour")
        self.setFixedWidth(340)
        h, s, v, _ = QColor(initial).getHsvF()
        self.h, self.s, self.v = max(0.0, h), s, v
        self.result_hex = QColor(initial).name().upper()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        top = QHBoxLayout()
        self.wheel = ColorWheel(190)
        top.addWidget(self.wheel)
        side = QVBoxLayout()
        self.preview = QFrame()
        self.preview.setFixedSize(96, 56)
        self.hex_edit = QLineEdit()
        self.hex_edit.setMaxLength(7)
        side.addWidget(self.preview)
        side.addWidget(self.hex_edit)
        side.addStretch()
        top.addLayout(side)
        lay.addLayout(top)

        cap = QLabel("BRIGHTNESS")
        cap.setObjectName("CardTitle")
        lay.addWidget(cap)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        lay.addWidget(self.slider)

        lay.addLayout(self._swatch_grid("PRESETS", PRESET_COLORS))
        if custom:
            lay.addLayout(self._swatch_grid("YOUR COLOURS", custom))

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self.wheel.changed.connect(self._on_wheel)
        self.slider.valueChanged.connect(self._on_slider)
        self.hex_edit.editingFinished.connect(lambda: self._set_hex(self.hex_edit.text()))
        self._sync()

    def _swatch_grid(self, title, colors):
        box = QVBoxLayout()
        box.setSpacing(6)
        cap = QLabel(title)
        cap.setObjectName("CardTitle")
        box.addWidget(cap)
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, hex_color in enumerate(colors):
            b = QPushButton()
            b.setObjectName("Swatch")
            b.setStyleSheet(f"background:{hex_color}")
            b.setToolTip(hex_color)
            b.clicked.connect(lambda _=False, c=hex_color: self._set_hex(c))
            grid.addWidget(b, i // 12, i % 12)
        grid.setColumnStretch(12, 1)
        box.addLayout(grid)
        return box

    def _on_wheel(self, h, s):
        self.h, self.s = h, s
        self._sync("wheel")

    def _on_slider(self, value):
        self.v = value / 100.0
        self._sync("slider")

    def _set_hex(self, text):
        c = QColor(text)
        if not c.isValid():
            self._sync()
            return
        h, s, v, _ = c.getHsvF()
        self.h, self.s, self.v = (h if h >= 0 else self.h), s, v
        self._sync()

    def _sync(self, source=None):
        c = QColor.fromHsvF(min(1.0, self.h), self.s, self.v)
        self.result_hex = c.name().upper()
        self.wheel.set_hsv(self.h, self.s, self.v)
        if source != "slider":
            self.slider.blockSignals(True)
            self.slider.setValue(round(self.v * 100))
            self.slider.blockSignals(False)
        self.hex_edit.setText(self.result_hex)
        self.preview.setStyleSheet(
            f"background:{self.result_hex};border:1px solid #2F3640;border-radius:4px")

    @staticmethod
    def pick(initial, custom, parent=None):
        dlg = ColorPickerDialog(initial, custom, parent)
        return dlg.result_hex if dlg.exec_() == QDialog.Accepted else None


# ── CALIBRATION DIALOG ────────────────────────────────────────────────────────
class CalibrationDialog(QDialog):
    def __init__(self, pixel_distance, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Reference Calibration")
        self.setFixedWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        info = QLabel(f"Measured span: <b>{pixel_distance:.2f} px</b><br>"
                      "Enter the real distance between the two marks.")
        info.setWordWrap(True)
        layout.addWidget(info)
        form = QFormLayout()
        form.setSpacing(10)
        self.dist_spin = QDoubleSpinBox()
        self.dist_spin.setRange(0.0001, 100000.0)
        self.dist_spin.setDecimals(3)
        self.dist_spin.setValue(15.0)
        form.addRow("Actual distance", self.dist_spin)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["cm", "mm", "in", "m"])
        form.addRow("Unit", self.unit_combo)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_values(self):
        return self.dist_spin.value(), self.unit_combo.currentText()


# ── MAIN APPLICATION WINDOW ───────────────────────────────────────────────────
TOOL_NAMES = {"straight": "LINE", "bead": "BEAD CONTOUR", "polygon": "POLYGON"}


class MeasurementApp(QMainWindow):
    SNAP_RADIUS_PX = 12            # screen pixels: how close counts as "on the first point"

    def __init__(self, image_path=None):
        super().__init__()
        self.setWindowTitle("Tire Measure")
        self.setMinimumSize(980, 620)
        self.fit_window_to_screen()

        self.image_path = image_path
        self.raw_pixmap = None
        self.pixmap_item = None
        self.img_np_array = None
        self.px_per_mm = None
        self.current_unit = "mm"
        self.k = 1.0                     # overlay size factor (grows with image resolution)

        self.mode = "calibrate"          # "calibrate" or "measure"
        self.tool_type = "straight"      # "straight", "bead" or "polygon"
        self.cal_pts, self.meas_pts, self.bead_pts, self.poly_pts = [], [], [], []
        self.measurements = []           # dicts: type, pts, dist_px, name, color, label_off, ...
        self.selected_m = None
        self.custom_colors = []
        self.snap_history = []
        self.hover_pos = None
        self.poly_snap = False           # cursor is snapped onto the polygon's first point
        self._populating = False
        self._static, self._preview, self._bucket = [], [], []
        self._was_maximized = False

        self.init_ui()
        self.setup_shortcuts()

        if self.image_path and os.path.isfile(self.image_path):
            self.load_image(self.image_path)
        else:
            QTimer.singleShot(0, self.prompt_open_image)

    # ── WINDOW SIZE / FULL SCREEN ─────────────────────────────────────────────
    def fit_window_to_screen(self):
        """Size the window from the usable screen area (taskbar excluded), not a fixed size."""
        screen = self.screen() if hasattr(self, "screen") and self.screen() else QApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.resize(min(1440, int(geo.width() * 0.96)), min(900, int(geo.height() * 0.92)))
        frame = self.frameGeometry()
        frame.moveCenter(geo.center())
        self.move(frame.topLeft())

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized() if self._was_maximized else self.showNormal()
        else:
            self._was_maximized = self.isMaximized()
            self.showFullScreen()
        self.act_fullscreen.setChecked(self.isFullScreen())
        self.update_shortcuts()

    # ── UI CONSTRUCTION ───────────────────────────────────────────────────────
    def init_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_lay = QVBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        self.build_menu()
        root_lay.addWidget(self.build_toolbar())
        body = QHBoxLayout()
        body.setSpacing(0)
        body.addWidget(self.build_tool_rail())
        body.addWidget(self.build_canvas(), 1)
        body.addWidget(self.build_sidebar())
        root_lay.addLayout(body, 1)
        self.build_status_bar()
        self.set_calibration_ui(None)
        self.sync_mode_ui()

    def build_menu(self):
        bar = self.menuBar()

        def add(menu, text, slot, shortcut=None, checkable=False):
            act = QAction(text, self)
            if shortcut:
                act.setShortcut(shortcut)
            act.setCheckable(checkable)
            act.triggered.connect(slot)
            menu.addAction(act)
            return act

        m = bar.addMenu("&File")
        add(m, "Open Image...", self.prompt_open_image, "Ctrl+O")
        add(m, "Export Annotated Image...", self.export_annotated_image, "Ctrl+E")
        m.addSeparator()
        add(m, "Quit", self.close, "Ctrl+Q")

        m = bar.addMenu("&Edit")
        add(m, "Undo Last Measurement", self.undo_last_measurement, "Ctrl+Z")
        add(m, "Clear All Measurements", self.clear_all_measurements)

        m = bar.addMenu("&View")
        add(m, "Fit to Window", self.fit_image_to_view, "Ctrl+0")
        add(m, "Actual Size (1:1)", self.reset_zoom, "Ctrl+1")
        self.act_loupe = add(m, "Magnifier Loupe", self.on_loupe_menu, "L", True)
        self.act_loupe.setChecked(True)
        self.act_fullscreen = add(m, "Full Screen", self.toggle_fullscreen, "F11", True)

        m = bar.addMenu("&Tools")
        add(m, "Calibrate Reference...", self.start_calibration_mode, "Ctrl+K")
        add(m, "Line", lambda: self.set_tool("straight"))
        add(m, "Bead Contour", lambda: self.set_tool("bead"))
        add(m, "Polygon", lambda: self.set_tool("polygon"))

        m = bar.addMenu("&Help")
        add(m, "Controls", self.show_controls)

    def build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Bar")
        bar.setFixedHeight(48)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(6)

        def button(text, slot):
            b = QPushButton(text)
            b.clicked.connect(slot)
            lay.addWidget(b)

        button("Open", self.prompt_open_image)
        button("Export PNG", self.export_annotated_image)
        lay.addWidget(make_separator())
        button("Undo Last", self.undo_last_measurement)
        button("Clear All", self.clear_all_measurements)
        lay.addWidget(make_separator())
        button("Fit", self.fit_image_to_view)
        button("1:1", self.reset_zoom)
        lay.addStretch()

        cap = QLabel("DISPLAY UNIT")
        cap.setObjectName("CardTitle")
        lay.addWidget(cap)
        seg = QFrame()
        seg.setObjectName("SegGroup")
        seg_lay = QHBoxLayout(seg)
        seg_lay.setContentsMargins(0, 0, 0, 0)
        seg_lay.setSpacing(0)
        self.unit_group = QButtonGroup(self)
        self.unit_buttons = {}
        for unit in DISPLAY_UNITS:
            b = QPushButton(unit)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setChecked(unit == self.current_unit)
            self.unit_group.addButton(b)
            self.unit_buttons[unit] = b
            seg_lay.addWidget(b)
        self.unit_group.buttonClicked.connect(lambda b: self.on_unit_changed(b.text()))
        lay.addWidget(seg)
        return bar

    def build_tool_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("RailBar")
        rail.setFixedWidth(52)
        lay = QVBoxLayout(rail)
        lay.setContentsMargins(6, 8, 6, 8)
        lay.setSpacing(4)
        self.rail_buttons = {}

        def tool(key, icon, tip, slot):
            b = QToolButton()
            b.setObjectName("Rail")
            b.setIcon(make_icon(icon))
            b.setIconSize(QSize(20, 20))
            b.setFixedSize(40, 40)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            lay.addWidget(b)
            self.rail_buttons[key] = b
            return b

        tool("calibrate", "calibrate", "Calibrate reference (Ctrl+K)", self.start_calibration_mode)
        tool("straight", "straight", "Line: two-point distance", lambda: self.set_tool("straight"))
        tool("bead", "bead", "Bead contour: multi-point curve length", lambda: self.set_tool("bead"))
        tool("polygon", "polygon", "Polygon: labelled shape with area", lambda: self.set_tool("polygon"))
        lay.addSpacing(8)
        self.btn_tool_loupe = tool("loupe", "loupe", "Magnifier loupe (L)", self.on_loupe_button)
        self.btn_tool_loupe.setChecked(True)
        lay.addStretch()
        return rail

    def build_canvas(self) -> QWidget:
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        self.scene = QGraphicsScene(self)
        self.view = ZoomPanGraphicsView(self.scene)
        self.view.clicked_image.connect(self.on_canvas_click)
        self.view.double_clicked_image.connect(self.on_canvas_double_click)
        self.view.right_clicked_image.connect(self.on_canvas_right_click)
        self.view.mouse_moved.connect(self.on_canvas_mouse_move)
        self.view.view_changed.connect(self.on_view_changed)

        self.ruler_h = Ruler(self.view, horizontal=True)
        self.ruler_v = Ruler(self.view, horizontal=False)
        corner = QFrame()
        corner.setFixedSize(Ruler.THICK, Ruler.THICK)
        corner.setObjectName("Bar")
        grid.addWidget(corner, 0, 0)
        grid.addWidget(self.ruler_h, 0, 1)
        grid.addWidget(self.ruler_v, 1, 0)
        grid.addWidget(self.view, 1, 1)
        self.magnifier = MagnifierWidget(self.view, size=160, zoom_factor=3.5)
        return holder

    def build_sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("Sidebar")
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        scroll = QScrollArea()                 # scrolls instead of squashing cards on small screens
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(352)
        scroll.setWidget(side)

        # Calibration
        self.lbl_cal_status = QLabel()
        self.lbl_scale = QLabel()
        self.lbl_ref = QLabel()
        btn_recal = QPushButton("Recalibrate")
        btn_recal.setObjectName("Outline")
        btn_recal.clicked.connect(self.start_calibration_mode)
        body = QWidget()
        b = QVBoxLayout(body)
        b.setContentsMargins(0, 0, 0, 12)
        b.setSpacing(0)
        b.addWidget(make_row("Scale", self.lbl_scale))
        b.addWidget(make_row("Reference", self.lbl_ref))
        wrap = QHBoxLayout()
        wrap.setContentsMargins(14, 4, 14, 0)
        wrap.addWidget(btn_recal)
        b.addLayout(wrap)
        lay.addWidget(make_card("Calibration", body, self.lbl_cal_status))

        # Sub-pixel snap
        self.chk_auto_snap = QCheckBox("Auto-snap to mark centre")
        self.chk_auto_snap.setChecked(HAVE_SNAP)
        self.chk_auto_snap.setEnabled(HAVE_SNAP)
        if not HAVE_SNAP:
            self.chk_auto_snap.setToolTip("Put marker_snap.py next to this script to enable")
        self.spin_marker_width = QSpinBox()
        self.spin_marker_width.setRange(1, 15)
        self.spin_marker_width.setFixedWidth(76)
        self.spin_marker_width.setValue(3)
        self.spin_marker_width.setToolTip("Expected width of a printed graduation line in pixels")
        self.lbl_snap_feedback = QLabel("marker_snap.py found" if HAVE_SNAP else "marker_snap.py not found")
        self.lbl_snap_feedback.setObjectName("Snap")
        body = QWidget()
        b = QVBoxLayout(body)
        b.setContentsMargins(14, 10, 14, 10)
        b.setSpacing(6)
        b.addWidget(self.chk_auto_snap)
        row = QHBoxLayout()
        k = QLabel("Mark width (px)")
        k.setObjectName("Key")
        row.addWidget(k)
        row.addStretch()
        row.addWidget(self.spin_marker_width)
        b.addLayout(row)
        b.addWidget(self.lbl_snap_feedback)
        lay.addWidget(make_card("Sub-pixel snap", body))

        # Next step
        self.lbl_guide = QLabel()
        self.lbl_guide.setObjectName("Hint")
        self.lbl_guide.setWordWrap(True)
        self.lbl_guide.setMinimumHeight(64)
        self.lbl_guide.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.addWidget(make_card("Next step", self.lbl_guide))

        # Measurements
        self.lbl_count = QLabel("0")
        self.lbl_count.setObjectName("Value")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "#", "NAME", "VALUE"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        hdr = self.table.horizontalHeader()
        hdr.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(0, 34)
        self.table.setColumnWidth(1, 34)
        self.table.cellClicked.connect(self.on_table_cell_clicked)
        self.table.itemChanged.connect(self.on_table_item_changed)
        self.table.itemSelectionChanged.connect(self.on_table_selection_changed)

        body = QWidget()
        b = QVBoxLayout(body)
        b.setContentsMargins(0, 0, 0, 10)
        b.setSpacing(8)
        b.addWidget(self.table, 1)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(10, 0, 10, 0)
        btn_row.setSpacing(6)
        for text, slot in (("Up", lambda: self.move_selected(-1)),
                           ("Down", lambda: self.move_selected(1)),
                           ("Colour", self.color_selected),
                           ("Delete", self.delete_selected)):
            btn = QPushButton(text)
            btn.setObjectName("Small")
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        b.addLayout(btn_row)
        card = make_card("Measurements", body, self.lbl_count)
        card.setMinimumHeight(220)
        lay.addWidget(card, 1)

        btn_export = QPushButton("Export Annotated Image")
        btn_export.setObjectName("Primary")
        btn_export.clicked.connect(self.export_annotated_image)
        lay.addWidget(btn_export)
        return scroll

    def build_status_bar(self):
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        self.lbl_mode = QLabel()
        self.lbl_mode.setStyleSheet(f"color:{Theme.ACCENT};font-weight:600")
        self.lbl_hint = QLabel()
        self.lbl_xy = QLabel("—")
        self.lbl_zoom = QLabel("—")
        self.lbl_size = QLabel("no image")
        sb.addWidget(self.lbl_mode)
        sb.addWidget(self.lbl_hint, 1)
        for w in (self.lbl_xy, self.lbl_zoom, self.lbl_size):
            sb.addPermanentWidget(w)
        sb.addPermanentWidget(QLabel("Esc cancel   Alt+wheel scroll"))

    def setup_shortcuts(self):
        self.sc_esc = QShortcut(QKeySequence(Qt.Key_Escape), self, self.cancel_current)
        self.sc_enter = QShortcut(QKeySequence(Qt.Key_Return), self, self.finish_current)
        self.sc_enter2 = QShortcut(QKeySequence(Qt.Key_Enter), self, self.finish_current)
        self.sc_back = QShortcut(QKeySequence(Qt.Key_Backspace), self, self.undo_last_point)
        self.update_shortcuts()

    def update_shortcuts(self):
        """Keys are only live when they mean something, so they never steal typing in the table."""
        if not hasattr(self, "sc_esc"):
            return
        self.sc_esc.setEnabled(self.has_draft() or self.isFullScreen())
        self.sc_back.setEnabled(self.has_draft())
        can_finish = self.mode == "measure" and (
            (self.tool_type == "bead" and len(self.bead_pts) >= 2)
            or (self.tool_type == "polygon" and len(self.poly_pts) >= 3))
        self.sc_enter.setEnabled(can_finish)
        self.sc_enter2.setEnabled(can_finish)

    # ── DRAFT STATE ───────────────────────────────────────────────────────────
    def has_draft(self) -> bool:
        return bool(self.cal_pts or self.meas_pts or self.bead_pts or self.poly_pts)

    def clear_drafts(self):
        self.cal_pts, self.meas_pts, self.bead_pts, self.poly_pts = [], [], [], []
        self.poly_snap = False

    def cancel_current(self):
        """Esc: drop whatever is being drawn; if nothing is, leave full screen."""
        if self.has_draft():
            self.clear_drafts()
            self.update_guide_text()
            self.rebuild_preview()
            self.statusBar().showMessage("Cancelled", 2000)
        elif self.isFullScreen():
            self.toggle_fullscreen()

    def undo_last_point(self):
        """Backspace: remove the last placed point of the current draft."""
        draft = (self.cal_pts if self.mode == "calibrate" else
                 {"straight": self.meas_pts, "bead": self.bead_pts, "polygon": self.poly_pts}[self.tool_type])
        if draft:
            draft.pop()
            self.update_guide_text()
            self.rebuild_preview()

    def finish_current(self):
        if self.mode != "measure":
            return
        if self.tool_type == "bead":
            self.finish_bead_path()
        elif self.tool_type == "polygon":
            self.finish_polygon()

    # ── MODE / UI SYNC ────────────────────────────────────────────────────────
    def sync_mode_ui(self):
        for key, btn in self.rail_buttons.items():
            if key == "loupe":
                continue
            btn.setChecked(key == ("calibrate" if self.mode == "calibrate" else self.tool_type))
        self.lbl_mode.setText("TOOL: " + ("CALIBRATE" if self.mode == "calibrate"
                                          else TOOL_NAMES[self.tool_type]))
        self.update_guide_text()

    def set_tool(self, tool):
        if tool != "polygon" and not self.px_per_mm:
            QMessageBox.warning(self, "Not Calibrated", "Please calibrate the ruler scale first!")
            self.start_calibration_mode()
            return
        self.mode, self.tool_type = "measure", tool
        self.clear_drafts()
        self.sync_mode_ui()
        self.rebuild_preview()

    def set_calibration_ui(self, info):
        if info is None:
            self.lbl_cal_status.setText(f'<span style="color:{Theme.RED}">&#9679;</span> Not calibrated')
            self.lbl_scale.setText("—")
            self.lbl_ref.setText("—")
            return
        px_dist, dist_val, unit = info
        self.lbl_cal_status.setText(f'<span style="color:{Theme.GREEN}">&#9679;</span> '
                                    f'<span style="color:{Theme.GREEN}">Calibrated</span>')
        self.lbl_scale.setText(f"{self.px_per_mm:.3f} px/mm")
        self.lbl_ref.setText(f"{px_dist:.1f} px = {dist_val:g} {unit}")

    def update_guide_text(self):
        if self.mode == "calibrate":
            n = len(self.cal_pts)
            msg = ["Click the <b>first mark</b> on your ruler or reference scale.",
                   "Click the <b>second mark</b> to finish the span.",
                   "Enter the real distance in the dialog."][min(n, 2)]
        elif self.tool_type == "straight":
            n = len(self.meas_pts)
            msg = ["Click <b>point A</b> on the object.",
                   "Click <b>point B</b> to finish the line.",
                   "Saved. Click to start a new line."][min(n, 2)]
        elif self.tool_type == "bead":
            n = len(self.bead_pts)
            msg = ("Click the <b>start point</b> on the inner edge." if n == 0 else
                   f"{n} pt{'s' if n > 1 else ''}. Keep clicking along the curve. "
                   "<b>Enter</b>, double-click or right-click finishes. <b>Esc</b> cancels.")
        else:
            n = len(self.poly_pts)
            msg = ("Click to place the <b>first vertex</b>." if n == 0 else
                   f"{n} vertices. Keep clicking." if n < 3 else
                   f"{n} vertices. Click the <b>first point</b> (it snaps) or press "
                   "<b>Enter</b> to close. <b>Backspace</b> removes the last vertex.")
        self.lbl_guide.setText(msg)
        self.lbl_hint.setText(msg.replace("<b>", "").replace("</b>", ""))
        self.update_shortcuts()

    def show_controls(self):
        QMessageBox.information(
            self, "Controls",
            "Click: place a point      Esc: cancel current drawing\n"
            "Enter / double-click / right-click: finish bead path or close polygon\n"
            "Backspace: remove last point\n\n"
            "Labels: drag to move, double-click to rename, right-click for options\n\n"
            "Wheel: zoom at cursor      Alt+wheel or Shift+wheel: scroll sideways\n"
            "Ctrl+drag or middle-drag: pan\n"
            "Ctrl+0 fit   Ctrl+1 1:1   Ctrl+Z undo   Ctrl+K recalibrate\n"
            "L: loupe      F11: full screen")

    # ── LOUPE TOGGLES ─────────────────────────────────────────────────────────
    def loupe_enabled(self) -> bool:
        return self.btn_tool_loupe.isChecked()

    def on_loupe_button(self):
        self.act_loupe.setChecked(self.loupe_enabled())
        if not self.loupe_enabled():
            self.magnifier.hide()

    def on_loupe_menu(self):
        self.btn_tool_loupe.setChecked(self.act_loupe.isChecked())
        self.on_loupe_button()

    # ── IMAGE LOADING / VIEW ──────────────────────────────────────────────────
    def prompt_open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image to Measure", "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;All Files (*)")
        if path:
            self.load_image(path)

    def load_image(self, path):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            QMessageBox.critical(self, "Error", f"Failed to load image:\n{path}")
            return
        self.image_path = path
        self.raw_pixmap = pixmap
        try:
            self.img_np_array = load_image_array(path) if HAVE_SNAP else None
        except Exception:
            self.img_np_array = None

        self.scene.clear()
        self._static, self._preview = [], []
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.magnifier.set_source_pixmap(pixmap)

        self.px_per_mm = None                    # new image = new scale
        self.measurements, self.selected_m = [], None
        self.k = max(1.0, pixmap.width() / 900.0)
        self.set_calibration_ui(None)
        self.update_history_list()
        self.start_calibration_mode()
        self.fit_image_to_view()
        self.setWindowTitle(f"Tire Measure — {os.path.basename(path)}")
        self.lbl_size.setText(f"{pixmap.width()} x {pixmap.height()} px")

    def fit_image_to_view(self):
        if self.raw_pixmap:
            self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
            self.on_view_changed()

    def reset_zoom(self):
        self.view.resetTransform()
        self.on_view_changed()

    def on_view_changed(self):
        self.ruler_h.update()
        self.ruler_v.update()
        self.lbl_zoom.setText(f"{self.view.transform().m11() * 100:.0f}%")

    # ── CALIBRATION ───────────────────────────────────────────────────────────
    def start_calibration_mode(self):
        self.mode = "calibrate"
        self.clear_drafts()
        self.snap_history = []
        self.sync_mode_ui()
        self.redraw_overlays()

    def finish_calibration(self):
        p1, p2 = self.cal_pts
        px_dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if px_dist < 2.0:
            QMessageBox.warning(self, "Invalid Calibration",
                                "Calibration points are too close. Please try again.")
            self.cal_pts = []
            self.update_guide_text()
            return
        dlg = CalibrationDialog(px_dist, self)
        if dlg.exec_() == QDialog.Accepted:
            dist_val, unit = dlg.get_values()
            self.px_per_mm = px_dist / (dist_val * UNIT_TO_MM[unit])
            self.set_calibration_ui((px_dist, dist_val, unit))
            self.set_unit(unit)
            self.mode = "measure"
            self.clear_drafts()
            self.sync_mode_ui()
            self.refresh_measurements()
        else:
            self.cal_pts = []
            self.update_guide_text()

    # ── UNITS / TEXT ──────────────────────────────────────────────────────────
    def set_unit(self, unit):
        if unit not in self.unit_buttons:
            unit = "mm"
        self.unit_buttons[unit].setChecked(True)
        self.on_unit_changed(unit)

    def on_unit_changed(self, new_unit):
        self.current_unit = new_unit
        self.refresh_measurements()

    def length_text(self, px_val):
        """Lengths are stored in pixels and converted on display, so recalibrating updates them."""
        if self.current_unit == "px" or not self.px_per_mm:
            return f"{px_val:.1f} px"
        return format_distance(px_val / self.px_per_mm, self.current_unit)

    def area_text(self, area_px):
        if self.current_unit == "px" or not self.px_per_mm:
            return f"{area_px:,.0f} px²"
        return format_area(area_px / self.px_per_mm ** 2, self.current_unit)

    def value_text(self, m):
        return self.area_text(m["area_px"]) if m["type"] == "polygon" else self.length_text(m["dist_px"])

    def label_text(self, m, idx):
        head = f"#{idx}" + (f"  {m['name']}" if m["name"] else "")
        if m["type"] == "polygon":
            return f"{head}\nA {self.area_text(m['area_px'])}   P {self.length_text(m['dist_px'])}"
        return f"{head}  {self.length_text(m['dist_px'])}"

    # ── MEASUREMENT LIST (table) ──────────────────────────────────────────────
    def add_measurement(self, mtype, pts, dist_px, **extra):
        poly_count = sum(1 for m in self.measurements if m["type"] == "polygon")
        color = DEFAULT_COLOR.get(mtype) or POLY_COLORS[poly_count % len(POLY_COLORS)]
        m = {"type": mtype, "pts": list(pts), "dist_px": dist_px, "name": "",
             "color": color, "label_off": None}
        m.update(extra)
        self.measurements.append(m)
        self.refresh_measurements()

    def refresh_measurements(self):
        self.update_history_list()
        self.rebuild_static()

    def update_history_list(self):
        self._populating = True
        self.table.setRowCount(len(self.measurements))
        for row, m in enumerate(self.measurements):
            sw = QTableWidgetItem()
            sw.setIcon(swatch_icon(m["color"]))
            sw.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            sw.setToolTip("Click to change colour")
            num = QTableWidgetItem(str(row + 1))
            num.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            num.setForeground(QBrush(qc(Theme.MUTED)))
            name = QTableWidgetItem(m["name"])
            name.setToolTip("Double-click to rename")
            val = QTableWidgetItem(self.value_text(m))
            val.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if m["type"] == "polygon":
                val.setToolTip(f"Perimeter {self.length_text(m['dist_px'])}")
            for col, item in enumerate((sw, num, name, val)):
                self.table.setItem(row, col, item)
        if self.selected_m in self.measurements:
            self.table.selectRow(self.measurements.index(self.selected_m))
        else:
            self.selected_m = None
            self.table.clearSelection()
        self._populating = False
        self.lbl_count.setText(str(len(self.measurements)))

    def on_table_selection_changed(self):
        if self._populating:
            return
        row = self.table.currentRow()
        selected = self.table.selectionModel().selectedRows()
        self.selected_m = (self.measurements[row] if selected and 0 <= row < len(self.measurements)
                           else None)
        self.rebuild_static()

    def on_table_cell_clicked(self, row, col):
        if col == 0 and 0 <= row < len(self.measurements):
            self.change_color(self.measurements[row])

    def on_table_item_changed(self, item):
        if self._populating or item.column() != 2 or item.row() >= len(self.measurements):
            return
        self.measurements[item.row()]["name"] = item.text().strip()
        self.rebuild_static()

    def need_selection(self):
        if self.selected_m is None:
            self.statusBar().showMessage("Select a measurement in the list first", 2500)
        return self.selected_m

    def move_selected(self, delta):
        if self.need_selection():
            self.move_measurement(self.selected_m, delta)

    def move_measurement(self, m, delta):
        i = self.measurements.index(m)
        j = i + delta
        if 0 <= j < len(self.measurements):
            self.measurements[i], self.measurements[j] = self.measurements[j], self.measurements[i]
            self.selected_m = m
            self.refresh_measurements()

    def delete_selected(self):
        if self.need_selection():
            self.delete_measurement(self.selected_m)

    def delete_measurement(self, m):
        if m in self.measurements:
            self.measurements.remove(m)
            if self.selected_m is m:
                self.selected_m = None
            self.refresh_measurements()

    def color_selected(self):
        if self.need_selection():
            self.change_color(self.selected_m)

    def change_color(self, m):
        picked = ColorPickerDialog.pick(m["color"], self.custom_colors, self)
        if picked:
            m["color"] = picked
            if picked not in PRESET_COLORS and picked not in self.custom_colors:
                self.custom_colors = ([picked] + self.custom_colors)[:12]
            self.refresh_measurements()

    def edit_name(self, m):
        text, ok = QInputDialog.getText(self, "Label name", "Name:", QLineEdit.Normal, m["name"])
        if ok:
            m["name"] = text.strip()
            self.refresh_measurements()

    def show_label_menu(self, m, global_pos):
        menu = QMenu(self)
        actions = {
            menu.addAction("Rename..."): lambda: self.edit_name(m),
            menu.addAction("Change colour..."): lambda: self.change_color(m),
            menu.addAction("Reset label position"): lambda: (m.update(label_off=None), self.rebuild_static()),
        }
        menu.addSeparator()
        actions[menu.addAction("Move up in list")] = lambda: self.move_measurement(m, -1)
        actions[menu.addAction("Move down in list")] = lambda: self.move_measurement(m, 1)
        menu.addSeparator()
        actions[menu.addAction("Delete")] = lambda: self.delete_measurement(m)
        chosen = menu.exec_(global_pos)
        if chosen in actions:
            actions[chosen]()

    def undo_last_measurement(self):
        if self.measurements:
            self.delete_measurement(self.measurements[-1])

    def clear_all_measurements(self):
        self.measurements.clear()
        self.selected_m = None
        self.clear_drafts()
        self.snap_history.clear()
        self.update_guide_text()
        self.refresh_measurements()
        self.rebuild_preview()

    # ── MOUSE INPUT ───────────────────────────────────────────────────────────
    def clamp_to_image(self, scene_pos):
        return (max(0, min(scene_pos.x(), self.raw_pixmap.width())),
                max(0, min(scene_pos.y(), self.raw_pixmap.height())))

    def near_first(self, x, y) -> bool:
        if len(self.poly_pts) < 3:
            return False
        radius = self.SNAP_RADIUS_PX / max(self.view.transform().m11(), 1e-6)
        return math.hypot(x - self.poly_pts[0][0], y - self.poly_pts[0][1]) <= radius

    def apply_snap(self, x, y):
        if HAVE_SNAP and self.chk_auto_snap.isChecked() and self.img_np_array is not None:
            res = snap_to_mark_centre(self.img_np_array, x, y,
                                      marker_width_px=self.spin_marker_width.value())
            self.snap_history.append(res)
            self.lbl_snap_feedback.setText(
                f"shifted {res.offset_px:.1f} px (confidence {res.confidence:.2f})")
            return res.snapped_x, res.snapped_y
        return x, y

    def on_canvas_mouse_move(self, scene_pos):
        if not self.raw_pixmap:
            return
        x, y = self.clamp_to_image(scene_pos)
        self.poly_snap = self.mode == "measure" and self.tool_type == "polygon" and self.near_first(x, y)
        if self.poly_snap:                        # labelme-style: jump onto the first point
            x, y = self.poly_pts[0]
        self.hover_pos = QPointF(x, y)
        self.lbl_xy.setText(f"{x:.0f}, {y:.0f} px")
        self.ruler_h.set_cursor(self.hover_pos)
        self.ruler_v.set_cursor(self.hover_pos)

        if self.loupe_enabled():
            view_pos = self.view.mapFromScene(self.hover_pos)
            loupe_x = view_pos.x() + 20
            loupe_y = view_pos.y() - 180
            if loupe_x + self.magnifier.width() > self.view.width():
                loupe_x = view_pos.x() - self.magnifier.width() - 20
            if loupe_y < 10:
                loupe_y = view_pos.y() + 20
            self.magnifier.move(int(max(10, loupe_x)), int(max(10, loupe_y)))
            self.magnifier.set_target(self.hover_pos)
            self.magnifier.show()
        else:
            self.magnifier.hide()
        if self.has_draft():
            self.rebuild_preview()

    def on_canvas_click(self, scene_pos):
        if not self.raw_pixmap:
            return
        x, y = self.clamp_to_image(scene_pos)

        if self.mode == "measure" and self.tool_type == "polygon":
            if self.near_first(x, y):
                self.finish_polygon()
                return
            self.poly_pts.append((x, y))
            self.update_guide_text()
            self.rebuild_preview()
            return

        pt = self.apply_snap(x, y)
        if self.mode == "calibrate":
            if len(self.cal_pts) < 2:
                self.cal_pts.append(pt)
                self.update_guide_text()
                if len(self.cal_pts) == 2:
                    self.finish_calibration()
        elif self.mode == "measure":
            if not self.px_per_mm:
                QMessageBox.warning(self, "Not Calibrated", "Please calibrate the ruler scale first!")
                self.start_calibration_mode()
                return
            if self.tool_type == "straight":
                self.meas_pts.append(pt)
                if len(self.meas_pts) == 2:
                    p1, p2 = self.meas_pts
                    self.add_measurement("straight", [p1, p2], math.hypot(p2[0] - p1[0], p2[1] - p1[1]))
                    self.meas_pts = []
            else:
                self.bead_pts.append(pt)
            self.update_guide_text()
        self.rebuild_preview()

    def on_canvas_double_click(self, scene_pos):
        self.finish_current()

    def on_canvas_right_click(self, scene_pos):
        self.finish_current()

    @staticmethod
    def drop_duplicate_tail(pts):
        """A double-click places the same point twice; drop the repeat."""
        if len(pts) >= 2 and math.hypot(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]) < 2.0:
            pts.pop()
        return pts

    def finish_bead_path(self):
        pts = self.drop_duplicate_tail(list(self.bead_pts))
        if len(pts) < 2 or not self.px_per_mm:
            return
        self.add_measurement("bead", pts, path_length(pts))
        self.bead_pts = []
        self.update_guide_text()
        self.rebuild_preview()

    def finish_polygon(self):
        pts = self.drop_duplicate_tail(list(self.poly_pts))
        if len(pts) < 3:
            return
        used = sorted({m["name"] for m in self.measurements if m["name"]})
        if used:
            name, ok = QInputDialog.getItem(self, "Polygon label", "Label name:", used, 0, True)
        else:
            name, ok = QInputDialog.getText(self, "Polygon label", "Label name:")
        if not ok:                                # cancelled: keep drawing, nothing is lost
            return
        area_px, _ = polygon_area_centroid(pts)
        self.add_measurement("polygon", pts, path_length(pts, closed=True),
                             area_px=area_px, name=name.strip())
        self.poly_pts = []
        self.poly_snap = False
        self.update_guide_text()
        self.rebuild_preview()

    # ── DRAWING ───────────────────────────────────────────────────────────────
    # Sizes scale with self.k so overlays stay readable on high-resolution photos
    # and in the exported image. Finished shapes live in _static, drafts in _preview,
    # so moving the mouse only redraws the draft and never disturbs a label you drag.
    def track(self, item):
        self._bucket.append(item)
        return item

    def clear_items(self, bucket):
        for item in bucket:
            if item.scene() is not None:
                self.scene.removeItem(item)
        bucket.clear()

    def redraw_overlays(self):
        self.rebuild_static()
        self.rebuild_preview()

    def rebuild_static(self):
        if not self.raw_pixmap:
            return
        self.clear_items(self._static)
        self._bucket = self._static
        k = self.k
        for idx, m in enumerate(self.measurements, 1):
            color = qc(m["color"])
            wide = 1.7 if m is self.selected_m else 1.0
            pts = m["pts"]
            if m["type"] == "polygon":
                fill = QColor(color)
                fill.setAlpha(60)
                poly = self.track(self.scene.addPolygon(
                    QPolygonF([QPointF(x, y) for x, y in pts]), QPen(color, 2 * k * wide), QBrush(fill)))
                poly.setZValue(5)
                for p in pts:
                    self.draw_dot(p, color, 4.5 * k)
                _, centre = polygon_area_centroid(pts)
                anchor, home = centre, centre
            else:
                pen = QPen(color, (3 if m["type"] == "bead" else 2) * k * wide)
                pen.setJoinStyle(Qt.RoundJoin)
                pen.setCapStyle(Qt.RoundCap)
                for a, b in zip(pts, pts[1:]):
                    self.track(self.scene.addLine(a[0], a[1], b[0], b[1], pen)).setZValue(8)
                for p in (pts if m["type"] == "bead" else (pts[0], pts[-1])):
                    self.draw_dot(p, color, 5 * k if m["type"] == "bead" else 6 * k)
                if m["type"] == "straight":
                    anchor = ((pts[0][0] + pts[1][0]) / 2.0, (pts[0][1] + pts[1][1]) / 2.0)
                else:
                    anchor = pts[len(pts) // 2]
                home = (anchor[0], anchor[1] - 22 * k)
            label = LabelItem(m, self.label_text(m, idx), m["color"], anchor, home, k)
            label.edit_requested.connect(lambda mm: QTimer.singleShot(0, lambda: self.edit_name(mm)))
            label.menu_requested.connect(
                lambda mm, pos: QTimer.singleShot(0, lambda: self.show_label_menu(mm, pos)))
            self.scene.addItem(label)
            self.track(label)

    def rebuild_preview(self):
        if not self.raw_pixmap:
            return
        self.clear_items(self._preview)
        self._bucket = self._preview
        amber, cyan, orange = qc(Theme.ACCENT), qc(Theme.CYAN), qc(Theme.ORANGE)
        hover = (self.hover_pos.x(), self.hover_pos.y()) if self.hover_pos else None

        if self.mode == "calibrate":
            if len(self.cal_pts) >= 1:
                self.draw_point(self.cal_pts[0], amber, "Mark 1")
            if len(self.cal_pts) == 1 and hover:
                self.draw_dashed_line(self.cal_pts[0], hover, amber)
            if len(self.cal_pts) == 2:
                self.draw_point(self.cal_pts[1], amber, "Mark 2")
                self.draw_dashed_line(self.cal_pts[0], self.cal_pts[1], amber)
            return

        if self.tool_type == "straight" and len(self.meas_pts) == 1:
            p1 = self.meas_pts[0]
            self.draw_point(p1, cyan, "A")
            if hover:
                px = math.hypot(hover[0] - p1[0], hover[1] - p1[1])
                self.draw_dashed_line(p1, hover, cyan)
                self.draw_label(self.length_text(px), (p1[0] + hover[0]) / 2.0,
                                (p1[1] + hover[1]) / 2.0 - 22 * self.k, cyan, centered=True)

        elif self.tool_type == "bead" and self.bead_pts:
            pts = self.bead_pts
            pen = QPen(orange, 2 * self.k)
            for a, b in zip(pts, pts[1:]):
                self.track(self.scene.addLine(a[0], a[1], b[0], b[1], pen)).setZValue(8)
            for i, p in enumerate(pts, 1):
                self.draw_point(p, orange, str(i))
            if hover:
                self.draw_dashed_line(pts[-1], hover, qc("#FFC08A"))
                total = path_length(pts) + math.hypot(hover[0] - pts[-1][0], hover[1] - pts[-1][1])
                self.draw_label(f"Bead: {self.length_text(total)}", hover[0] + 12 * self.k,
                                hover[1] - 30 * self.k, orange)

        elif self.tool_type == "polygon" and self.poly_pts:
            pts = self.poly_pts
            pen = QPen(cyan, 2 * self.k)
            for a, b in zip(pts, pts[1:]):
                self.track(self.scene.addLine(a[0], a[1], b[0], b[1], pen)).setZValue(8)
            for p in pts:
                self.draw_dot(p, cyan, 4.5 * self.k)
            if hover:
                self.draw_dashed_line(pts[-1], hover, cyan)
            if self.poly_snap:                    # highlight the closing target
                r = 10 * self.k
                ring = self.track(self.scene.addEllipse(pts[0][0] - r, pts[0][1] - r, 2 * r, 2 * r,
                                                        QPen(amber, 2.5 * self.k), QBrush(Qt.NoBrush)))
                ring.setZValue(12)
                self.draw_label("Close", pts[0][0] + 14 * self.k, pts[0][1] - 30 * self.k, amber)

    def draw_dot(self, pt, color, r):
        fill = QColor(color)
        fill.setAlpha(170)
        dot = self.track(self.scene.addEllipse(pt[0] - r, pt[1] - r, 2 * r, 2 * r,
                                               QPen(color, 1.6 * self.k), QBrush(fill)))
        dot.setZValue(9)

    def draw_point(self, pt, color, label_text=""):
        self.draw_dot(pt, color, 6 * self.k)
        if label_text:
            self.draw_label(label_text, pt[0] + 12 * self.k, pt[1] - 26 * self.k, color)

    def draw_dashed_line(self, p1, p2, color):
        pen = QPen(color, 2 * self.k, Qt.DashLine)
        self.track(self.scene.addLine(p1[0], p1[1], p2[0], p2[1], pen)).setZValue(8)

    def draw_label(self, text, x, y, color, centered=False):
        """Fixed (non-movable) pill used for drafts and calibration marks."""
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        font.setBold(True)
        font.setPixelSize(int(13 * self.k))
        txt = self.track(self.scene.addSimpleText(text, font))
        txt.setBrush(QBrush(Qt.white))
        rect = txt.boundingRect()
        if centered:
            x -= rect.width() / 2.0
            y -= rect.height() / 2.0
        txt.setPos(x, y)
        pad = 6 * self.k
        path = QPainterPath()
        path.addRoundedRect(x - pad, y - pad / 2, rect.width() + 2 * pad,
                            rect.height() + pad, 3 * self.k, 3 * self.k)
        bg = self.track(self.scene.addPath(path, QPen(color, 1.2 * self.k), QBrush(qc(Theme.BAR, 225))))
        bg.setZValue(10)
        txt.setZValue(11)

    # ── EXPORT ANNOTATED IMAGE ────────────────────────────────────────────────
    def export_annotated_image(self):
        if not self.raw_pixmap:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Annotated Measurement Image", "measured_output.png",
            "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)")
        if not save_path:
            return
        self.clear_items(self._preview)           # no half-drawn drafts in the export
        out_pixmap = QPixmap(self.raw_pixmap.size())
        painter = QPainter(out_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        self.scene.render(painter, QRectF(out_pixmap.rect()), QRectF(self.raw_pixmap.rect()))
        painter.end()
        self.rebuild_preview()
        if out_pixmap.save(save_path):
            QMessageBox.information(self, "Success", f"Annotated image saved:\n{save_path}")
        else:
            QMessageBox.critical(self, "Error", f"Failed to save image to:\n{save_path}")


# ── APPLICATION ENTRYPOINT ────────────────────────────────────────────────────
def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)   # correct sizes on scaled Windows displays
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_dark_palette(app)
    app.setStyleSheet(build_stylesheet())
    window = MeasurementApp(sys.argv[1] if len(sys.argv) > 1 else None)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
