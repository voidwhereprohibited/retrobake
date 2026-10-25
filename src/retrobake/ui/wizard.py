"""Wizard frame: window, step bar, page stack, Back/Next, zoom shortcuts.

Each screen is a ``WizardStep``. The frame knows nothing about NES, genres or
art; screens own their content and write their answers into ``spec`` (a plain
dict that later validates against the game-design ``game-spec`` contract).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import theme

TITLE_FACTOR = 1.9
SUBTITLE_FACTOR = 1.1

# Fits a 1366x768 laptop with taskbar and window frame.
MIN_WIDTH, MIN_HEIGHT = 900, 600
DEFAULT_WIDTH, DEFAULT_HEIGHT = 1100, 700


class WizardStep(QWidget):
    """Base class for one wizard screen.

    Subclasses set ``key``, ``nav_label``, ``title``, ``subtitle`` and build
    their widgets in ``build(body_layout)``. Call ``self.changed.emit()``
    whenever ``is_complete()`` may have changed.
    """

    key: str = "step"
    nav_label: str = "Step"
    title: str = ""
    subtitle: str = ""
    next_label: str = "Next"
    show_back: bool = True
    show_next: bool = True

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName(self.title or self.nav_label)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self.title_label = QLabel(self.title)
        self.title_label.setProperty("role", "title")
        self.title_label.setWordWrap(True)
        self.title_label.setAccessibleName(self.title)
        outer.addWidget(self.title_label)

        self.subtitle_label = QLabel(self.subtitle)
        self.subtitle_label.setProperty("role", "subtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(self.subtitle))
        outer.addWidget(self.subtitle_label)

        card = QFrame()
        card.setObjectName("Card")
        body = QVBoxLayout(card)
        body.setContentsMargins(24, 20, 24, 20)
        body.setSpacing(12)
        self.build(body)
        body.addStretch(1)
        outer.addWidget(card, 1)

    # --- for subclasses -------------------------------------------------
    def build(self, layout: QVBoxLayout) -> None:  # pragma: no cover - overridden
        pass

    def is_complete(self) -> bool:
        return True

    def apply_to(self, spec: dict[str, Any]) -> None:
        """Write this step's answers into the shared spec."""

    def on_enter(self, spec: dict[str, Any]) -> None:
        """Called each time the step is shown."""

    def first_focus(self) -> QWidget | None:
        """Widget that should get keyboard focus when the step opens."""
        return None

    # --- used by the frame ---------------------------------------------
    def apply_fonts(self, base: QFont) -> None:
        tf = QFont(base)
        tf.setPointSizeF(base.pointSizeF() * TITLE_FACTOR)
        tf.setBold(True)
        self.title_label.setFont(tf)
        sf = QFont(base)
        sf.setPointSizeF(base.pointSizeF() * SUBTITLE_FACTOR)
        self.subtitle_label.setFont(sf)


class WizardWindow(QMainWindow):
    """Main RetroBake window hosting the steps in order."""

    step_changed = Signal(int)

    def __init__(self, steps: list[WizardStep], app: QApplication | None = None) -> None:
        super().__init__()
        if not steps:
            raise ValueError("wizard needs at least one step")
        self._app = app or QApplication.instance()
        self.scale = 1.0
        self.spec: dict[str, Any] = {}
        self.steps = steps

        self.setWindowTitle("RetroBake")
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self.resize(DEFAULT_WIDTH, DEFAULT_HEIGHT)

        root = QWidget()
        root.setObjectName("WizardRoot")
        self.setCentralWidget(root)
        col = QVBoxLayout(root)
        col.setContentsMargins(32, 20, 32, 20)
        col.setSpacing(16)

        # Progress: "Step 2 of 8 · System" + bar. Compact so it fits at any zoom.
        self.progress_label = QLabel()
        self.progress_label.setProperty("role", "subtitle")
        self.progress = QProgressBar()
        self.progress.setRange(0, len(steps))
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(8)
        col.addWidget(self.progress_label)
        col.addWidget(self.progress)

        # Pages (scrollable, so big fonts never cut content off)
        self.stack = QStackedWidget()
        for s in steps:
            s.changed.connect(self._refresh_buttons)
            self.stack.addWidget(s)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.stack)
        col.addWidget(scroll, 1)

        # Footer
        foot = QHBoxLayout()
        self.zoom_hint = QLabel("Text size: Ctrl + and Ctrl −")
        self.zoom_hint.setProperty("role", "hint")
        foot.addWidget(self.zoom_hint)
        foot.addStretch(1)
        self.back_btn = QPushButton("Back")
        self.back_btn.setAccessibleName("Back")
        self.back_btn.setAccessibleDescription("Go to the previous step")
        self.back_btn.setAutoDefault(False)
        self.back_btn.clicked.connect(self.go_back)
        self.next_btn = QPushButton("Next")
        self.next_btn.setAccessibleName("Next")
        self.next_btn.setAccessibleDescription("Go to the next step")
        self.next_btn.setProperty("primary", True)
        self.next_btn.setDefault(True)
        self.next_btn.clicked.connect(self.go_next)
        for b in (self.back_btn, self.next_btn):
            b.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            b.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        foot.addWidget(self.back_btn)
        foot.addWidget(self.next_btn)
        col.addLayout(foot)

        # Keyboard. Fixed shortcuts (not & mnemonics) so changing button text
        # like "Bake my game" can never clash with Back.
        self.back_btn.setToolTip("Back (Alt+B or Alt+Left)")
        self.next_btn.setToolTip("Next (Enter, Alt+N or Alt+Right)")
        for seq, fn in (
            ("Alt+N", self.go_next),
            ("Alt+Right", self.go_next),
            ("Alt+B", self.go_back),
            ("Alt+Left", self.go_back),
            (QKeySequence.StandardKey.ZoomIn, self.zoom_in),
            ("Ctrl+=", self.zoom_in),
            (QKeySequence.StandardKey.ZoomOut, self.zoom_out),
            ("Ctrl+0", self.zoom_reset),
        ):
            QShortcut(QKeySequence(seq), self, activated=fn)

        self._apply_fonts()
        self.go_to(0)

    # --- navigation ------------------------------------------------------
    @property
    def index(self) -> int:
        return self.stack.currentIndex()

    @property
    def current(self) -> WizardStep:
        return self.steps[self.index]

    def go_to(self, i: int) -> None:
        i = max(0, min(len(self.steps) - 1, i))
        self.stack.setCurrentIndex(i)
        step = self.steps[i]
        step.on_enter(self.spec)
        text = f"Step {i + 1} of {len(self.steps)} · {step.nav_label}"
        self.progress_label.setText(text)
        self.progress_label.setAccessibleName(text)
        self.progress.setValue(i + 1)
        self.progress.setAccessibleName(text)
        self.setWindowTitle(f"RetroBake — {step.nav_label}")
        self._refresh_buttons()
        target = step.first_focus() or (self.next_btn if self.next_btn.isEnabled() else step)
        target.setFocus(Qt.FocusReason.OtherFocusReason)
        self.step_changed.emit(i)

    def go_next(self) -> None:
        step = self.current
        if not step.show_next or not step.is_complete():
            return
        step.apply_to(self.spec)
        if self.index < len(self.steps) - 1:
            self.go_to(self.index + 1)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt name)
        # Enter = press the focused button, otherwise "Next". Multi-line text
        # boxes keep Enter for new lines because they accept the key first.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focused = QApplication.focusWidget()
            if isinstance(focused, QPushButton) and focused.isEnabled():
                focused.click()
            elif self.next_btn.isVisible() and self.next_btn.isEnabled():
                self.go_next()
            event.accept()
            return
        super().keyPressEvent(event)

    def go_back(self) -> None:
        if self.back_btn.isVisible() and self.index > 0:
            self.go_to(self.index - 1)

    def _refresh_buttons(self) -> None:
        step = self.current
        self.back_btn.setVisible(step.show_back and self.index > 0)
        last = self.index == len(self.steps) - 1
        self.next_btn.setVisible(step.show_next and not last)
        label = step.next_label
        self.next_btn.setText(label)
        self.next_btn.setAccessibleName(label)
        self.next_btn.setEnabled(step.is_complete())

    # --- text size -------------------------------------------------------
    def set_scale(self, scale: float) -> None:
        if self._app is None:
            return
        self.scale = theme.set_font_scale(self._app, scale)
        self._apply_fonts()

    def zoom_in(self) -> None:
        self.set_scale(self.scale + theme.SCALE_STEP)

    def zoom_out(self) -> None:
        self.set_scale(self.scale - theme.SCALE_STEP)

    def zoom_reset(self) -> None:
        self.set_scale(1.0)

    def _apply_fonts(self) -> None:
        base = QFont(self._app.font()) if self._app else QFont()
        for w in self.findChildren(QWidget):
            if not isinstance(w, QLabel) or w.property("role") != "title":
                w.setFont(base)
        bold = QFont(base)
        bold.setBold(True)  # via QFont, not CSS, so the button's size hint includes it
        self.next_btn.setFont(bold)
        for s in self.steps:
            s.apply_fonts(base)
