"""The RetroBake wizard screens.

M1: Welcome, System and Genre are real; the rest are placeholders that show the flow and
plain-English wording. Later tasks replace each stub with the real screen
(System + Genre in M1, the rest as their contracts land).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from retrobake import spec as gamespec
from retrobake.security import clean_choice

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
            "2.  Pick a kind of game — or mix two together.",
            "3.  Tell us about your game in your own words.",
            "4.  Answer a few quick questions.",
            "5.  Pick a cover and a name.",
            "6.  We bake it. Then play it or save it.",
        ):
            _text(layout, line)
        _text(layout, "No coding. Nothing to set up.", "hint")
        self.disclaimer = _text(layout, DISCLAIMER, "hint")
        self.disclaimer.setAccessibleName("Please note")


class _Placeholder(WizardStep):
    """Stub screen until the real one is built."""

    placeholder = "Coming soon."

    def build(self, layout: QVBoxLayout) -> None:
        note = _text(layout, self.placeholder, "hint")
        note.setAccessibleName(f"{self.nav_label}: {self.placeholder}")


SYSTEM_BLURBS = {
    "nes": "Classic 8-bit look. Simple, bold graphics and chiptune music.",
    "snes": "16-bit look. More colors, bigger worlds and room for more extras.",
}


class SystemStep(WizardStep):
    key = "system"
    nav_label = "System"
    title = "Which game system?"
    subtitle = "Pick the console your game is for. You can come back and change it."

    def build(self, layout: QVBoxLayout) -> None:
        systems = gamespec.catalog()["systems"]
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QRadioButton] = {}
        for sid, info in systems.items():
            btn = QRadioButton(info["label"])
            btn.setProperty("system", sid)
            blurb = SYSTEM_BLURBS.get(sid, "")
            btn.setAccessibleName(info["label"])
            btn.setAccessibleDescription(blurb)
            self.group.addButton(btn)
            layout.addWidget(btn)
            if blurb:
                _text(layout, blurb, "hint").setIndent(28)
            self.buttons[sid] = btn
        self.buttons[next(iter(self.buttons))].setChecked(True)
        self.group.buttonToggled.connect(lambda *_: self.changed.emit())
        _text(layout, "Both play in RetroArch on Windows and Linux.", "hint")

    @property
    def system(self) -> str | None:
        btn = self.group.checkedButton()
        return btn.property("system") if btn else None

    def is_complete(self) -> bool:
        return self.system is not None

    def apply_to(self, spec: dict[str, Any]) -> None:
        spec["system"] = clean_choice(self.system, list(self.buttons))

    def on_enter(self, spec: dict[str, Any]) -> None:
        if spec.get("system") in self.buttons:
            self.buttons[spec["system"]].setChecked(True)

    def first_focus(self) -> QWidget | None:
        return self.group.checkedButton()


class GenreStep(WizardStep):
    key = "genre"
    nav_label = "Kind of game"
    title = "What kind of game?"
    subtitle = "Pick one kind, or mix two for something new."

    def build(self, layout: QVBoxLayout) -> None:
        cat = gamespec.catalog()["genres"]
        self.available = gamespec.available_genres()
        _text(layout, "Kind of game")
        self.primary = QComboBox()
        self.primary.setAccessibleName("Kind of game")
        for g in self.available:
            self.primary.addItem(cat[g]["label"], g)
        layout.addWidget(self.primary)

        self.mix = QCheckBox("Mix in a second kind of game")
        self.mix.setAccessibleDescription("Combine two kinds of game into one")
        layout.addWidget(self.mix)
        self.secondary = QComboBox()
        self.secondary.setAccessibleName("Second kind of game")
        layout.addWidget(self.secondary)
        self.mix_hint = _text(
            layout,
            "The first kind decides how your hero moves and fights. "
            "The second brings its world and extras.",
            "hint",
        )
        soon = [cat[g]["label"] for g in cat if not cat[g]["available"]]
        if soon:
            _text(layout, "Coming soon: " + ", ".join(soon) + ".", "hint")

        self.fixes: list[gamespec.Fix] = []
        self.primary.currentIndexChanged.connect(self._sync)
        self.secondary.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self.mix.toggled.connect(self._sync)
        self._sync()

    def _sync(self, *_: object) -> None:
        first = self.primary.currentData()
        keep = self.secondary.currentData()
        cat = gamespec.catalog()["genres"]
        self.secondary.blockSignals(True)
        self.secondary.clear()
        for g in self.available:
            if g != first:
                self.secondary.addItem(cat[g]["label"], g)
        i = self.secondary.findData(keep)
        self.secondary.setCurrentIndex(max(i, 0))
        self.secondary.blockSignals(False)
        can_mix = self.secondary.count() > 0
        self.mix.setEnabled(can_mix)
        on = self.mix.isChecked() and can_mix
        self.secondary.setVisible(on)
        self.mix_hint.setVisible(on)
        self.changed.emit()

    @property
    def genres(self) -> list[str]:
        out = [self.primary.currentData()]
        if self.mix.isChecked() and self.secondary.count():
            out.append(self.secondary.currentData())
        return [g for g in out if g]

    def is_complete(self) -> bool:
        g = self.genres
        return bool(g) and len(set(g)) == len(g)

    def apply_to(self, spec: dict[str, Any]) -> None:
        genres = [clean_choice(g, self.available) for g in self.genres]
        system = spec.get("system", "nes")
        new, self.fixes = gamespec.new_spec(
            system,
            genres,
            description=spec.get("description", ""),
            title=spec.get("title", "My Game"),
            seed=spec.get("seed"),
        )
        spec.clear()
        spec.update(new)

    def on_enter(self, spec: dict[str, Any]) -> None:
        g = spec.get("genres") or []
        if g and g[0] in self.available:
            self.primary.setCurrentIndex(self.primary.findData(g[0]))
            self.mix.setChecked(len(g) > 1)
            if len(g) > 1:
                self.secondary.setCurrentIndex(max(self.secondary.findData(g[1]), 0))

    def first_focus(self) -> QWidget | None:
        return self.primary


class DescribeStep(_Placeholder):
    key = "describe"
    nav_label = "Describe"
    title = "Tell us about your game"
    subtitle = "Write it like you'd tell a friend. A few sentences is plenty."
    placeholder = "A big text box goes here."


class QuestionsStep(_Placeholder):
    key = "questions"
    nav_label = "Questions"
    title = "A few quick questions"
    subtitle = "These help us shape the levels, the hero and the look."
    placeholder = "Questions for your kind of game show up here."


class ArtNameStep(_Placeholder):
    key = "art_name"
    nav_label = "Cover & name"
    title = "Pick a cover and a name"
    subtitle = "Choose one of our ideas, or type your own name."
    placeholder = "Cover art and name ideas show up here."


class BakeStep(_Placeholder):
    key = "bake"
    nav_label = "Bake"
    title = "Baking your game"
    subtitle = "This usually takes under a minute."
    next_label = "Bake my game"
    placeholder = "A progress bar shows here while your game is built."


class FinishStep(WizardStep):
    key = "finish"
    nav_label = "Done"
    title = "Your game is ready!"
    subtitle = "Play it now or save it anywhere you like."
    show_next = False

    def build(self, layout: QVBoxLayout) -> None:
        self.actions: list[QPushButton] = []
        for label, desc in (
            ("Play now in RetroArch", "Open your game in RetroArch"),
            ("Save game to…", "Choose a folder to save your game file"),
            ("Save cover art…", "Save the cover picture"),
            ("Add to RetroArch library", "Show this game in your RetroArch list"),
        ):
            btn = QPushButton(label)
            btn.setAccessibleName(label)
            btn.setAccessibleDescription(desc)
            btn.setEnabled(False)  # wired up once the bake step is real
            btn.setToolTip("Available after your game is baked.")
            layout.addWidget(btn)
            self.actions.append(btn)


def default_steps() -> list[WizardStep]:
    return [
        WelcomeStep(),
        SystemStep(),
        GenreStep(),
        DescribeStep(),
        QuestionsStep(),
        ArtNameStep(),
        BakeStep(),
        FinishStep(),
    ]
