"""Screens 4-8: Describe, Questions, Cover & name, Bake, Finish.

Text the user types always goes through ``retrobake.security`` before it reaches the spec.
Anything slow (AI art, names, baking) runs in a ``Task`` thread so the window never freezes.
"""

from __future__ import annotations

import copy
import html
import json
import shutil
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from retrobake import retroarch
from retrobake import spec as gamespec
from retrobake.security import DISCLAIMER_SHORT, InputRejected, check_title, sanitize

from .session import Session, Task, error_text
from .wizard import WizardStep

MAX_DESCRIPTION = 500


def _label(layout: QVBoxLayout, text: str, role: str | None = None) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    if role:
        lbl.setProperty("role", role)
    layout.addWidget(lbl)
    return lbl


def _spec_key(spec: dict[str, Any]) -> str:
    return json.dumps(spec, sort_keys=True, default=str)


# --------------------------------------------------------------------------- Describe
class DescribeStep(WizardStep):
    key = "describe"
    nav_label = "Describe"
    title = "Tell us about your game"
    subtitle = "Write it like you'd tell a friend. A few sentences is plenty."

    def __init__(self, session: Session | None = None) -> None:
        self.session = session or Session()
        super().__init__()

    def build(self, layout: QVBoxLayout) -> None:
        self.edit = QPlainTextEdit()
        self.edit.setAccessibleName("Describe your game")
        self.edit.setPlaceholderText(
            "A brave fox runs through glowing caves to rescue her friends…"
        )
        self.edit.setMinimumHeight(150)
        self.edit.textChanged.connect(self._on_text)
        layout.addWidget(self.edit)
        self.counter = _label(layout, f"0 / {MAX_DESCRIPTION}", "hint")
        self.notice = _label(layout, "", "hint")
        self.notice.setVisible(False)
        self.error = _label(layout, "")
        self.error.setVisible(False)
        self.error.setAccessibleName("Problem with your description")
        _label(
            layout,
            "Tip: you can say things like \"a spooky castle with a boss at the end\". "
            "Skipping this is fine too.",
            "hint",
        )

    def _on_text(self) -> None:
        text = self.edit.toPlainText()
        if len(text) > MAX_DESCRIPTION:
            self.edit.setPlainText(text[:MAX_DESCRIPTION])
            self.edit.moveCursor(self.edit.textCursor().MoveOperation.End)
            return
        self.counter.setText(f"{len(text)} / {MAX_DESCRIPTION}")
        self._clean()
        self.changed.emit()

    def _clean(self) -> str | None:
        try:
            clean = sanitize("description", self.edit.toPlainText())
        except InputRejected as exc:
            self.error.setText(exc.message)
            self.error.setVisible(True)
            return None
        self.error.setVisible(False)
        hints = gamespec.style_from_text(clean)
        self.notice.setVisible(bool(hints.matched))
        if hints.matched:
            self.notice.setText(
                "We spotted a name from another game. We'll use it as inspiration for the "
                "style only. Your game stays original."
            )
        return clean

    def is_complete(self) -> bool:
        return self._clean() is not None

    def apply_to(self, spec: dict[str, Any]) -> None:
        clean = self._clean()
        if clean is None:
            return
        new, _ = gamespec.new_spec(
            spec.get("system", "nes"),
            spec.get("genres") or ["platformer"],
            description=clean,
            title=spec.get("title", "My Game"),
            seed=spec.get("seed"),
        )
        spec.clear()
        spec.update(new)

    def on_enter(self, spec: dict[str, Any]) -> None:
        if spec.get("description") and not self.edit.toPlainText():
            self.edit.setPlainText(spec["description"])

    def first_focus(self) -> QWidget | None:
        return self.edit


# ------------------------------------------------------------------------- Questions
class QuestionsStep(WizardStep):
    key = "questions"
    nav_label = "Questions"
    title = "A few quick questions"
    subtitle = "These shape the levels, the hero and the look. Every answer has a good default."

    def __init__(self, session: Session | None = None) -> None:
        self.session = session or Session()
        self.answers: dict[str, Any] = {}
        self.fixes: list[Any] = []
        self.base: dict[str, Any] = {}
        self._shape: list[Any] = []
        self._sig: Any = None
        self._bad: set[str] = set()
        self.widgets: dict[str, QWidget] = {}
        super().__init__()

    def build(self, layout: QVBoxLayout) -> None:
        self.host = QWidget()
        self.form = QVBoxLayout(self.host)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setSpacing(10)
        layout.addWidget(self.host)
        self.fix_label = _label(layout, "", "hint")
        self.fix_label.setVisible(False)
        self.reset_btn = QPushButton("Use the suggested answers")
        self.reset_btn.setAccessibleName("Use the suggested answers")
        self.reset_btn.setAccessibleDescription("Clear your answers and use the defaults")
        self.reset_btn.setAutoDefault(False)
        self.reset_btn.clicked.connect(self._reset)
        layout.addWidget(self.reset_btn)

    def _reset(self) -> None:
        self.answers.clear()
        self._bad.clear()
        self._render(force=True)

    def _current(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        spec, self.fixes = gamespec.apply_answers(self.base, self.answers)
        return spec, gamespec.questions_for(spec)

    def on_enter(self, spec: dict[str, Any]) -> None:
        self.base = copy.deepcopy(spec)
        sig = (spec.get("system"), tuple(spec.get("genres", [])))
        if sig != self._sig:
            self.answers.clear()
            self._bad.clear()
            self._sig = sig
        self._render(force=True)

    def _render(self, force: bool = False) -> None:
        if not self.base:
            return
        _, qs = self._current()
        shape = [(q["id"], json.dumps(q.get("options"), default=str), q.get("max")) for q in qs]
        self._show_fixes()
        if not force and shape == self._shape:
            return
        self._shape = shape
        while self.form.count():
            item = self.form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.widgets = {}
        for q in qs:
            self._add_question(q)

    def _show_fixes(self) -> None:
        msgs = [f.message for f in self.fixes]
        self.fix_label.setText("We adjusted a few things so they work together:\n- " + "\n- ".join(msgs) if msgs else "")
        self.fix_label.setVisible(bool(msgs))

    def _add_question(self, q: dict[str, Any]) -> None:
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        prompt = _label(col, q["prompt"])
        prompt.setProperty("role", "subtitle")
        if q.get("help"):
            _label(col, q["help"], "hint")
        qid, value = q["id"], self.answers.get(q["id"], q["default"])
        kind = q["kind"]
        w: QWidget
        if kind == "choice":
            w = QComboBox()
            for o in q["options"]:
                w.addItem(o["label"], o["value"])
            w.setCurrentIndex(max(w.findData(value), 0))
            w.currentIndexChanged.connect(lambda _i, w=w, qid=qid: self._set(qid, w.currentData()))
        elif kind == "multi":
            w = QWidget()
            wl = QVBoxLayout(w)
            wl.setContentsMargins(0, 0, 0, 0)
            boxes: list[QCheckBox] = []
            cap = q.get("max_choices")
            chosen = set(value or [])
            for o in q["options"]:
                cb = QCheckBox(o["label"])
                cb.setProperty("value", o["value"])
                cb.setChecked(o["value"] in chosen)
                wl.addWidget(cb)
                boxes.append(cb)
            w.setProperty("boxes", boxes)

            def changed(*_: object, boxes=boxes, cap=cap, qid=qid) -> None:
                picked = [b.property("value") for b in boxes if b.isChecked()]
                if cap:
                    for b in boxes:
                        b.setEnabled(b.isChecked() or len(picked) < cap)
                self._set(qid, picked)

            for cb in boxes:
                cb.toggled.connect(changed)
            if cap:
                picked = [b for b in boxes if b.isChecked()]
                for b in boxes:
                    b.setEnabled(b.isChecked() or len(picked) < cap)
        elif kind == "number":
            w = QSpinBox()
            w.setRange(int(q.get("min", 0)), int(q.get("max", 99)))
            w.setValue(int(value))
            w.valueChanged.connect(lambda v, qid=qid: self._set(qid, v))
        else:  # text
            w = QLineEdit(str(value or ""))
            w.setMaxLength(int(q.get("max_length") or 120))
            w.textChanged.connect(lambda t, qid=qid: self._set_text(qid, t))
        w.setAccessibleName(q["prompt"])
        col.addWidget(w)
        self.widgets[qid] = w
        self.form.addWidget(box)

    def _set(self, qid: str, value: Any) -> None:
        self.answers[qid] = value
        self._render()
        self.changed.emit()

    def _set_text(self, qid: str, text: str) -> None:
        field = "hero_description" if qid == "hero_description" else "answer"
        try:
            self.answers[qid] = sanitize(field, text)
            self._bad.discard(qid)
        except InputRejected:
            self._bad.add(qid)
        self.changed.emit()

    def is_complete(self) -> bool:
        return not self._bad

    def apply_to(self, spec: dict[str, Any]) -> None:
        new, self.fixes = gamespec.apply_answers(self.base, self.answers)
        spec.clear()
        spec.update(new)

    def first_focus(self) -> QWidget | None:
        return next(iter(self.widgets.values()), None)


# ------------------------------------------------------------------------ Cover & name
class ArtNameStep(WizardStep):
    key = "art_name"
    nav_label = "Cover & name"
    title = "Pick a cover and a name"
    subtitle = "Choose one of our ideas, or type your own name."

    def __init__(self, session: Session | None = None) -> None:
        self.session = session or Session()
        self.spec: dict[str, Any] = {}
        self.art = None
        self.busy = False
        self.variant = 0
        self.task: Task | None = None
        self._key = ""
        self._error = ""
        super().__init__()

    def build(self, layout: QVBoxLayout) -> None:
        self.cover = QLabel("Making your cover…")
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setMinimumHeight(200)
        self.cover.setAccessibleName("Cover art preview")
        layout.addWidget(self.cover)
        self.status = _label(layout, "", "hint")
        self.status.setAccessibleName("Status")
        _label(layout, "Name ideas")
        self.names = QListWidget()
        self.names.setAccessibleName("Name ideas")
        self.names.setMaximumHeight(150)
        self.names.currentTextChanged.connect(self._pick)
        layout.addWidget(self.names)
        _label(layout, "Or type your own name")
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(24)
        self.name_edit.setAccessibleName("Your game's name")
        self.name_edit.textChanged.connect(self._on_name)
        layout.addWidget(self.name_edit)
        self.error = _label(layout, "")
        self.error.setAccessibleName("Problem with the name")
        self.error.setVisible(False)
        self.more = QPushButton("Show me more ideas")
        self.more.setAccessibleName("Show me more ideas")
        self.more.setAutoDefault(False)
        self.more.clicked.connect(self._more)
        layout.addWidget(self.more)
        self.online = QCheckBox("Use online AI for pictures and names (otherwise made on this computer)")
        self.online.setChecked(self.session.ai.settings.online)
        self.online.toggled.connect(self._set_online)
        layout.addWidget(self.online)

    # --- loading -----------------------------------------------------------
    def on_enter(self, spec: dict[str, Any]) -> None:
        self.spec = copy.deepcopy(spec)
        key = _spec_key({k: v for k, v in spec.items() if k != "title"})
        if key != self._key or self.art is None:
            self._key = key
            self.variant = 0
            self._load()

    def _set_online(self, on: bool) -> None:
        self.session.ai.settings.online = on
        self.variant = 0
        self._load()

    def _more(self) -> None:
        self.variant += 1
        self._load()

    def _load(self) -> None:
        if not self.spec:
            return
        spec, v, ai = copy.deepcopy(self.spec), self.variant, self.session.ai
        self.busy = True
        self.status.setText("Drawing your cover and thinking up names…")
        self.more.setEnabled(False)
        self.task = Task(lambda: (ai.make_art(spec, variant=v), ai.suggest_names(spec, 6, variant=v)), self)
        self.task.done.connect(self._loaded)
        self.task.finished.connect(self.task.deleteLater)
        self.task.start()
        self.changed.emit()

    def _loaded(self, result: Any, err: Any) -> None:
        if self.sender() is not self.task:
            return  # an older request that was replaced
        self.busy = False
        self.more.setEnabled(True)
        if err is not None:
            self.status.setText(error_text(err))
        else:
            self.art, ideas = result
            pix = QPixmap()
            pix.loadFromData(self.art.png)
            self.cover.setPixmap(pix.scaledToHeight(240, Qt.TransformationMode.FastTransformation))
            self.names.clear()
            self.names.addItems(ideas.names)
            note = " ".join(m for m in (self.art.message, ideas.message) if m)
            self.status.setText(note or "Here are some ideas. Pick one or type your own.")
            if not self.name_edit.text() and ideas.names:
                self.names.setCurrentRow(0)
        self.changed.emit()

    # --- naming --------------------------------------------------------------
    def _pick(self, text: str) -> None:
        if text:
            self.name_edit.setText(text)

    def _on_name(self, _text: str) -> None:
        self._validate()
        self.changed.emit()

    def _validate(self) -> str | None:
        text = self.name_edit.text()
        self._error = ""
        try:
            name = check_title(sanitize("title", text), field="title")
        except InputRejected as exc:
            if text.strip():
                self._error = exc.message
            name = None
        self.error.setText(self._error)
        self.error.setVisible(bool(self._error))
        return name

    @property
    def chosen_title(self) -> str | None:
        return self._validate()

    def is_complete(self) -> bool:
        return not self.busy and self.art is not None and self.chosen_title is not None

    def apply_to(self, spec: dict[str, Any]) -> None:
        title = self.chosen_title
        if title is None or self.art is None:
            return
        spec["title"] = title
        self.session.art = self.art
        self.session.cover_png = self.session.ai.with_title(self.art, title)

    def can_leave(self) -> bool:
        return not self.busy

    def first_focus(self) -> QWidget | None:
        return self.name_edit


# ------------------------------------------------------------------------------ Bake
class BakeStep(WizardStep):
    key = "bake"
    nav_label = "Bake"
    title = "Baking your game"
    subtitle = "This usually takes under a minute."
    next_label = "See my game"

    def __init__(self, session: Session | None = None) -> None:
        self.session = session or Session()
        self.task: Task | None = None
        self.busy = False
        self.spec: dict[str, Any] = {}
        super().__init__()

    def build(self, layout: QVBoxLayout) -> None:
        self.status = _label(layout, "Getting ready…")
        self.status.setAccessibleName("Baking status")
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.setAccessibleName("Baking progress")
        layout.addWidget(self.bar)
        self.retry = QPushButton("Try again")
        self.retry.setAccessibleName("Try again")
        self.retry.setAutoDefault(False)
        self.retry.setVisible(False)
        self.retry.clicked.connect(self._start)
        layout.addWidget(self.retry)

    def on_enter(self, spec: dict[str, Any]) -> None:
        self.spec = copy.deepcopy(spec)
        key = _spec_key(spec)
        if self.session.rom_path and self.session.baked_key == key and not self.busy:
            self._show_done()
        elif not self.busy:
            self._start()

    def _start(self) -> None:
        self.busy = True
        self.session.rom_path = None
        self.retry.setVisible(False)
        self.bar.setRange(0, 0)
        self.status.setText("Baking your game… the oven is warming up.")
        spec, work, bake = copy.deepcopy(self.spec), self.session.work_dir, self.session.bake
        self.task = Task(lambda: bake(spec, work), self)
        self.task.done.connect(self._finished)
        self.task.finished.connect(self.task.deleteLater)
        self.task.start()
        self.changed.emit()

    def _finished(self, path: Any, err: Any) -> None:
        self.busy = False
        if err is not None:
            self.bar.setRange(0, 1)
            self.bar.setValue(0)
            text = error_text(err) if hasattr(err, "message") else (
                "We couldn't bake this game: " + str(err) if isinstance(err, ValueError)
                else "Something went wrong while baking. Please try again."
            )
            self.status.setText(text + "\nYou can go Back to change something, or try again.")
            self.retry.setVisible(True)
        else:
            self.session.rom_path = Path(path)
            self.session.baked_key = _spec_key(self.spec)
            self._show_done()
        self.changed.emit()

    def _show_done(self) -> None:
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        self.retry.setVisible(False)
        self.status.setText(f"Done! \"{self.spec.get('title', 'Your game')}\" is baked and ready.")

    def is_complete(self) -> bool:
        return not self.busy and self.session.rom_path is not None

    def can_leave(self) -> bool:
        return not self.busy


# ---------------------------------------------------------------------------- Finish
class FinishStep(WizardStep):
    key = "finish"
    nav_label = "Done"
    title = "Your game is ready!"
    subtitle = "Play it now or save it anywhere you like."
    show_next = False

    restart_requested = Signal()

    def __init__(self, session: Session | None = None) -> None:
        self.session = session or Session()
        self.spec: dict[str, Any] = {}
        super().__init__()

    def build(self, layout: QVBoxLayout) -> None:
        handlers = (
            ("Play now in RetroArch", "Open your game in RetroArch", self.play),
            ("Save game to…", "Choose a folder to save your game file", self.save_rom),
            ("Save cover art…", "Save the cover picture", self.save_cover),
            ("Add to RetroArch library", "Show this game in your RetroArch list", self.add_library),
        )
        self.actions: list[QPushButton] = []
        for label, desc, fn in handlers:
            btn = QPushButton(label)
            btn.setAccessibleName(label)
            btn.setAccessibleDescription(desc)
            btn.setEnabled(False)
            btn.setAutoDefault(False)
            btn.clicked.connect(fn)
            layout.addWidget(btn)
            self.actions.append(btn)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.RichText)
        self.message.setOpenExternalLinks(False)
        self.message.linkActivated.connect(self._open_link)
        self.message.setAccessibleName("Result")
        layout.addWidget(self.message)
        self.again = QPushButton("Make another game")
        self.again.setAccessibleName("Make another game")
        self.again.setAutoDefault(False)
        self.again.clicked.connect(self.restart_requested.emit)
        layout.addWidget(self.again)
        _label(layout, DISCLAIMER_SHORT, "hint")

    def on_enter(self, spec: dict[str, Any]) -> None:
        self.spec = copy.deepcopy(spec)
        ready = self.session.rom_path is not None
        for b in self.actions:
            b.setEnabled(ready)
        self.actions[2].setEnabled(self.session.cover_png is not None)
        self.say("")

    def first_focus(self) -> QWidget | None:
        return self.actions[0]

    def reset(self) -> None:
        self.session.reset()

    # --- helpers ---------------------------------------------------------------
    def say(self, text: str, html_extra: str = "") -> None:
        self.message.setText(html.escape(text).replace("\n", "<br>") + html_extra)

    @staticmethod
    def _open_link(url: str) -> None:
        if url.startswith("https://"):
            QDesktopServices.openUrl(QUrl(url))

    @property
    def system(self) -> str:
        return self.spec.get("system", "nes")

    @property
    def title_text(self) -> str:
        return self.spec.get("title", "My Game")

    def _install(self):
        """(install, None) when RetroArch plus a core is ready, else (None, advice shown)."""
        installs = self.session.detect()
        inst = retroarch.pick(installs, self.system)
        if inst is not None and inst.find_core(self.system):
            return inst
        advice = retroarch.advise(installs, self.system, retroarch.current_os())
        steps = "".join(f"<li>{html.escape(s)}</li>" for s in advice.steps)
        links = "".join(
            f'<br><a href="{html.escape(a.url)}">{html.escape(a.label)}</a>' for a in advice.actions
        )
        self.message.setText(
            f"<b>{html.escape(advice.title)}</b><br>{html.escape(advice.message)}"
            f"<ol>{steps}</ol>{links}"
        )
        return None

    # --- actions ---------------------------------------------------------------
    def play(self) -> None:
        inst = self._install()
        if inst is None:
            return
        try:
            self.session.launcher.play(inst, self.session.rom_path, self.system)
        except retroarch.LaunchError as exc:
            self.say(error_text(exc) if hasattr(exc, "message") else str(exc))
            return
        self.say("RetroArch is starting your game. Have fun!")

    def save_rom(self) -> None:
        rom = self.session.rom_path
        ext = rom.suffix if rom else ".nes"
        dest = self.session.ask_save("Save your game", rom.name if rom else "game" + ext, f"Game (*{ext})")
        if not dest:
            return
        dest_path = Path(dest)
        if dest_path.suffix.lower() != ext:
            dest_path = dest_path.with_name(dest_path.name + ext)
        try:
            shutil.copyfile(rom, dest_path)
        except OSError:
            self.say("We couldn't save there. Please pick another folder.")
            return
        self.say(f"Saved to {dest_path}")

    def save_cover(self) -> None:
        png = self.session.cover_png
        if png is None:
            return
        dest = self.session.ask_save("Save the cover", "cover.png", "Picture (*.png)")
        if not dest:
            return
        dest_path = Path(dest)
        if dest_path.suffix.lower() != ".png":
            dest_path = dest_path.with_name(dest_path.name + ".png")
        try:
            dest_path.write_bytes(png)
        except OSError:
            self.say("We couldn't save there. Please pick another folder.")
            return
        self.say(f"Saved to {dest_path}")

    def add_library(self) -> None:
        inst = self._install()
        if inst is None:
            return
        core_path, core = inst.find_core(self.system)
        try:
            retroarch.add_game(
                inst, self.session.rom_path, self.title_text, core_path, core,
                self.session.cover_png,
            )
        except (retroarch.PlaylistError, OSError) as exc:
            self.say(error_text(exc) if hasattr(exc, "message") else "We couldn't add it to RetroArch.")
            return
        self.say("Added! Look for \"RetroBake\" in RetroArch's playlists.")
