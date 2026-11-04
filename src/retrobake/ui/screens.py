"""The RetroBake wizard screens, in order: Welcome, System, Genre, Describe,
Questions, Cover & name, Bake, Finish.

Screens share one ``Session`` (see session.py). Each writes its answers there;
the Describe screen turns them into a real game-spec with ``new_spec``.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStandardPaths, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from retrobake.ai import AIService
from retrobake.security import InputRejected, check_title
from retrobake.spec import analyze, new_spec
from retrobake.spec.catalog import catalog
from retrobake.spec.questions import apply_answers, questions_for

from .session import Session
from .wizard import WizardStep

DISCLAIMER = (
    "You're responsible for what you make with RetroBake. Please keep your games "
    "original — RetroBake turns famous names into a style, never a copy."
)


def _text(layout: QVBoxLayout, text: str, role: str | None = None) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    if role:
        lbl.setProperty("role", role)
    layout.addWidget(lbl)
    return lbl


class WelcomeStep(WizardStep):
    key = "welcome"
    nav_label = "Welcome"
    title = "Make your own retro game"
    subtitle = "Answer a few easy questions and RetroBake builds a real game you can play."
    next_label = "Let's start"

    def build(self, layout: QVBoxLayout) -> None:
        _text(layout, "Here's how it works:")
        for line in (
            "1.  Pick a game system.",
            "2.  Pick one kind of game.",
            "3.  Tell us about your game in your own words.",
            "4.  Answer a few quick questions.",
            "5.  Pick a cover and a name.",
            "6.  We bake it. Then play it or save it.",
        ):
            _text(layout, line)
        _text(layout, "No coding. Nothing to set up.", "hint")
        self.disclaimer = _text(layout, DISCLAIMER, "hint")
        self.disclaimer.setAccessibleName("Please note")


class _SessionStep(WizardStep):
    """A screen that reads and writes the shared Session."""

    def __init__(self, session: Session) -> None:
        self.session = session
        super().__init__()


# --- System -----------------------------------------------------------------

SYSTEMS = (
    ("nes", "NES", True),
    ("snes", "SNES", False),
    ("n64", "N64", False),
    ("genesis", "Genesis", False),
    ("sms", "Master System", False),
    ("ps1_2d", "PS1 (2D)", False),
)


class SystemStep(_SessionStep):
    key = "system"
    nav_label = "System"
    title = "Which game system?"
    subtitle = "Pick the console your game is for."

    def build(self, layout: QVBoxLayout) -> None:
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QRadioButton] = {}
        for value, label, ready in SYSTEMS:
            btn = QRadioButton(label if ready else f"{label}  ·  coming soon")
            btn.setAccessibleName(label)
            btn.setEnabled(ready)
            self.group.addButton(btn)
            self.buttons[value] = btn
            layout.addWidget(btn)
        self.buttons[self.session.system].setChecked(True)

    def apply_to(self, spec: dict[str, Any]) -> None:
        self.session.system = next(k for k, b in self.buttons.items() if b.isChecked())


# --- Genre ------------------------------------------------------------------

MAX_INSPIRATIONS = 2


class GenreStep(_SessionStep):
    key = "genre"
    nav_label = "Kind of game"
    title = "What kind of game?"
    subtitle = "Pick one kind of game. You can also tick up to two others you like."

    def build(self, layout: QVBoxLayout) -> None:
        genres = catalog()["genres"]
        self.group = QButtonGroup(self)
        self.genre_buttons: dict[str, QRadioButton] = {}
        self.inspiration_boxes: dict[str, QCheckBox] = {}
        cols = QHBoxLayout()
        cols.setSpacing(32)
        left, right = QVBoxLayout(), QVBoxLayout()
        left.addWidget(QLabel("Your game is a…"))
        right.addWidget(QLabel("Inspired by (optional, up to 2)"))
        for gid, info in genres.items():
            label = info["label"] if info["available"] else f"{info['label']}  ·  coming soon"
            btn = QRadioButton(label)
            btn.setAccessibleName(info["label"])
            btn.setEnabled(info["available"])
            btn.toggled.connect(self._sync)
            self.group.addButton(btn)
            self.genre_buttons[gid] = btn
            left.addWidget(btn)
            box = QCheckBox(info["label"])
            box.setAccessibleName(f"Inspired by {info['label']}")
            box.toggled.connect(self._sync)
            self.inspiration_boxes[gid] = box
            right.addWidget(box)
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        layout.addLayout(cols)
        self.genre_buttons[self.session.genre].setChecked(True)

    @property
    def genre(self) -> str | None:
        return next((g for g, b in self.genre_buttons.items() if b.isChecked()), None)

    @property
    def inspirations(self) -> list[str]:
        return [g for g, b in self.inspiration_boxes.items() if b.isChecked()]

    def _sync(self) -> None:
        picked = self.inspirations
        for gid, box in self.inspiration_boxes.items():
            if gid == self.genre:
                box.setChecked(False)
            full = len(picked) >= MAX_INSPIRATIONS and not box.isChecked()
            box.setEnabled(gid != self.genre and not full)
        self.changed.emit()

    def is_complete(self) -> bool:
        return self.genre is not None and len(self.inspirations) <= MAX_INSPIRATIONS

    def apply_to(self, spec: dict[str, Any]) -> None:
        self.session.genre = self.genre or "platformer"
        self.session.inspirations = self.inspirations


# --- Describe ---------------------------------------------------------------


class DescribeStep(_SessionStep):
    key = "describe"
    nav_label = "Describe"
    title = "Tell us about your game"
    subtitle = "Write it like you'd tell a friend. A few sentences is plenty."

    def build(self, layout: QVBoxLayout) -> None:
        self.text = QPlainTextEdit()
        self.text.setAccessibleName("Your game idea")
        self.text.setPlaceholderText("Example: A fox explores a snowy forest and stomps on robots.")
        self.text.setMaximumHeight(160)
        self.text.textChanged.connect(self.changed.emit)
        layout.addWidget(self.text)
        self.read_btn = QPushButton("Read my idea")
        self.read_btn.setAccessibleName("Read my idea")
        self.read_btn.setAccessibleDescription("Show the plan RetroBake made from your words")
        self.read_btn.clicked.connect(self.show_plan)
        layout.addWidget(self.read_btn)
        self.summary = _text(layout, "", "hint")
        self.summary.setAccessibleName("Your plan")
        _text(
            layout,
            "Everything here is worked out on your computer. Nothing is sent online.",
            "hint",
        )

    def first_focus(self) -> QWidget | None:
        return self.text

    def show_plan(self) -> str:
        words = self.text.toPlainText().strip()
        plan = analyze(words, self.session.genre) if words else None
        self.summary.setText(plan.summary() if plan else "Write a sentence or two first.")
        return self.summary.text()

    def is_complete(self) -> bool:
        return bool(self.text.toPlainText().strip())

    def apply_to(self, spec: dict[str, Any]) -> None:
        s = self.session
        s.description = self.text.toPlainText().strip()
        s.spec, _ = new_spec(s.system, s.genre, s.description, inspirations=s.inspirations)
        self.show_plan()


# --- Questions --------------------------------------------------------------


class QuestionsStep(_SessionStep):
    key = "questions"
    nav_label = "Questions"
    title = "A few quick questions"
    subtitle = "We filled these in from your idea. Change anything you like."

    def build(self, layout: QVBoxLayout) -> None:
        self.form = QFormLayout()
        self.form.setVerticalSpacing(10)
        self.form.setHorizontalSpacing(24)
        layout.addLayout(self.form)
        self.fields: dict[str, tuple[dict[str, Any], Any]] = {}

    def on_enter(self, spec: dict[str, Any]) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        self.fields = {}
        if not self.session.spec:
            return
        for q in questions_for(self.session.spec):
            widget = self._widget(q)
            self.fields[q["id"]] = (q, widget)
            label = QLabel(q["prompt"])
            label.setWordWrap(True)
            self.form.addRow(label, widget)

    @staticmethod
    def _widget(q: dict[str, Any]) -> QWidget:
        kind, default = q["kind"], q["default"]
        if kind == "choice":
            w = QComboBox()
            for o in q["options"]:
                w.addItem(o["label"], o["value"])
            w.setCurrentIndex(max(0, w.findData(default)))
        elif kind == "number":
            w = QSpinBox()
            w.setRange(q["min"], q["max"])
            w.setValue(default or q["min"])
        elif kind == "multi":
            w = QWidget()
            row = QHBoxLayout(w)
            row.setContentsMargins(0, 0, 0, 0)
            w.boxes = []
            for o in q["options"]:
                box = QCheckBox(o["label"])
                box.setChecked(o["value"] in (default or []))
                box.value = o["value"]
                row.addWidget(box)
                w.boxes.append(box)
            row.addStretch(1)
        else:
            w = QLineEdit(default or "")
            w.setMaxLength(q.get("max_length", 120))
            w.setPlaceholderText(q.get("help", ""))
        w.setAccessibleName(q["prompt"])
        return w

    def answers(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for qid, (q, w) in self.fields.items():
            if q["kind"] == "choice":
                out[qid] = w.currentData()
            elif q["kind"] == "number":
                out[qid] = w.value()
            elif q["kind"] == "multi":
                out[qid] = [b.value for b in w.boxes if b.isChecked()]
            elif w.text().strip():
                out[qid] = w.text().strip()
        return out

    def apply_to(self, spec: dict[str, Any]) -> None:
        if self.session.spec:
            self.session.spec, _ = apply_answers(self.session.spec, self.answers())


# --- Cover & name -----------------------------------------------------------


class ArtNameStep(_SessionStep):
    key = "art_name"
    nav_label = "Cover & name"
    title = "Pick a cover and a name"
    subtitle = "Choose one of our ideas, or type your own name."

    def build(self, layout: QVBoxLayout) -> None:
        self.ai = AIService()
        self.variant = 0
        self._art = None
        row = QHBoxLayout()
        row.setSpacing(32)
        self.cover = QLabel()
        self.cover.setProperty("role", "cover")
        self.cover.setAccessibleName("Cover picture")
        self.cover.setFixedSize(256, 256)
        self.cover.setScaledContents(True)
        row.addWidget(self.cover)
        side = QVBoxLayout()
        side.addWidget(QLabel("Game name"))
        self.name = QComboBox()
        self.name.setEditable(True)
        self.name.setAccessibleName("Game name")
        self.name.lineEdit().setMaxLength(20)
        self.name.currentTextChanged.connect(self._name_changed)
        side.addWidget(self.name)
        self.problem = _text(side, "", "hint")
        self.another = QPushButton("Try another cover")
        self.another.setAccessibleName("Try another cover")
        self.another.clicked.connect(self.next_cover)
        side.addWidget(self.another)
        _text(side, "Covers are drawn on your computer. No internet needed.", "hint")
        side.addStretch(1)
        row.addLayout(side, 1)
        layout.addLayout(row)

    def on_enter(self, spec: dict[str, Any]) -> None:
        s = self.session.spec
        if not s:
            return
        ideas = [s["title"], *self.ai.suggest_names(s).names]
        self.name.blockSignals(True)
        self.name.clear()
        self.name.addItems(list(dict.fromkeys(ideas)))
        self.name.blockSignals(False)
        self._art = self.ai.make_art(s, variant=self.variant)
        self._name_changed(self.name.currentText())

    def next_cover(self) -> None:
        self.variant += 1
        self._art = self.ai.make_art(self.session.spec, variant=self.variant)
        self._name_changed(self.name.currentText())

    def title_problem(self) -> str:
        title = self.name.currentText().strip()
        if not title:
            return "Type a name for your game."
        try:
            check_title(title, field="title")
        except InputRejected as exc:
            return str(exc) or "Please pick a different name."
        return ""

    def _name_changed(self, _text_: str) -> None:
        problem = self.title_problem()
        self.problem.setText(problem)
        if not problem and self._art is not None:
            self.session.cover_png = self.ai.with_title(self._art, self.name.currentText().strip())
            pix = QPixmap()
            pix.loadFromData(self.session.cover_png)
            self.cover.setPixmap(pix)
        self.changed.emit()

    def is_complete(self) -> bool:
        return self._art is not None and not self.title_problem()

    def apply_to(self, spec: dict[str, Any]) -> None:
        self.session.spec["title"] = self.name.currentText().strip()


# --- Bake -------------------------------------------------------------------


class BakeStep(_SessionStep):
    key = "bake"
    nav_label = "Bake"
    title = "Bake your game"
    subtitle = "This usually takes a few seconds."
    next_label = "See my game"
    done = Signal(object)

    def build(self, layout: QVBoxLayout) -> None:
        self.bake_btn = QPushButton("Bake my game")
        self.bake_btn.setAccessibleName("Bake my game")
        self.bake_btn.setProperty("primary", True)
        self.bake_btn.clicked.connect(self.start)
        layout.addWidget(self.bake_btn)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1)
        self.bar.setTextVisible(False)
        self.bar.setAccessibleName("Baking progress")
        layout.addWidget(self.bar)
        self.status = _text(layout, "Press the button when you're ready.", "hint")
        self.done.connect(self._finished)

    def on_enter(self, spec: dict[str, Any]) -> None:
        if self.session.rom is None:
            self.status.setText("Press the button when you're ready.")

    def first_focus(self) -> QWidget | None:
        return self.bake_btn

    def start(self) -> None:
        self.session.rom = None
        self.bake_btn.setEnabled(False)
        self.bar.setRange(0, 0)  # busy
        self.status.setText("Building levels, drawing tiles and writing music…")
        self.changed.emit()
        spec = dict(self.session.spec)
        threading.Thread(target=self._work, args=(spec,), daemon=True).start()

    def _work(self, spec: dict[str, Any]) -> None:
        try:
            self.done.emit(self.session.baker(spec))
        except Exception as exc:  # shown to the user in plain English
            self.done.emit(exc)

    def _finished(self, result: object) -> None:
        self.bar.setRange(0, 1)
        self.bake_btn.setEnabled(True)
        if isinstance(result, Exception):
            self.bar.setValue(0)
            message = getattr(result, "message", "") or "Something went wrong while baking."
            self.status.setText(f"{message} You can press Bake to try again.")
        else:
            self.session.rom = result
            self.bar.setValue(1)
            self.status.setText("Done! Your game is baked.")
        self.changed.emit()

    def is_complete(self) -> bool:
        return self.session.rom is not None


# --- Finish -----------------------------------------------------------------


def games_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(base or Path.home() / ".retrobake") / "games"


def safe_filename(title: str) -> str:
    keep = "".join(c if c.isalnum() else "_" for c in title).strip("_")
    return keep or "game"


class FinishStep(_SessionStep):
    key = "finish"
    nav_label = "Done"
    title = "Your game is ready!"
    subtitle = "Play it now or save it anywhere you like."
    show_next = False

    def build(self, layout: QVBoxLayout) -> None:
        self.actions: list[QPushButton] = []
        for label, desc, slot in (
            ("Play in RetroArch", "Open your game in RetroArch", self.play),
            ("Save ROM…", "Choose where to save your game file", self.save_rom),
            ("Save cover…", "Choose where to save the cover picture", self.save_cover),
        ):
            btn = QPushButton(label)
            btn.setAccessibleName(label)
            btn.setAccessibleDescription(desc)
            btn.clicked.connect(slot)
            layout.addWidget(btn)
            self.actions.append(btn)
        self.status = _text(layout, "", "hint")
        self.launcher = None

    def on_enter(self, spec: dict[str, Any]) -> None:
        ready = self.session.rom is not None
        for btn in self.actions:
            btn.setEnabled(ready)
        self.status.setText("" if ready else "Bake your game first.")

    def _name(self) -> str:
        return safe_filename(self.session.spec.get("title", "game"))

    def write_rom(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.session.rom.rom)
        return path

    def play(self) -> None:
        from retrobake.retroarch import Launcher, LaunchError, detect, pick

        rom = self.write_rom(games_dir() / f"{self._name()}.nes")
        install = pick(detect(), "nes")
        if install is None:
            self.status.setText(f"RetroArch isn't installed. Your game is saved at {rom}.")
            return
        self.launcher = self.launcher or Launcher()
        try:
            self.launcher.relaunch(install, rom, "nes")
            self.status.setText("Starting RetroArch…")
        except LaunchError as exc:
            self.status.setText(str(exc))

    def _ask(self, caption: str, suffix: str, filt: str) -> Path | None:
        start = str(Path.home() / f"{self._name()}{suffix}")
        name, _ = QFileDialog.getSaveFileName(self, caption, start, filt)
        return Path(name) if name else None

    def save_rom(self) -> None:
        path = self._ask("Save your game", ".nes", "NES game (*.nes)")
        if path:
            self.status.setText(f"Saved to {self.write_rom(path)}")

    def save_cover(self) -> None:
        path = self._ask("Save the cover", ".png", "PNG picture (*.png)")
        if path:
            path.write_bytes(self.session.cover_png)
            self.status.setText(f"Saved to {path}")


def default_steps(session: Session | None = None) -> list[WizardStep]:
    session = session or Session()
    return [
        WelcomeStep(),
        SystemStep(session),
        GenreStep(session),
        DescribeStep(session),
        QuestionsStep(session),
        ArtNameStep(session),
        BakeStep(session),
        FinishStep(session),
    ]
