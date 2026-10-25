"""The RetroBake wizard screens.

M1-prep: Welcome is real; the rest are placeholders that show the flow and
plain-English wording. Later tasks replace each stub with the real screen
(System + Genre in M1, the rest as their contracts land).
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout

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


class SystemStep(_Placeholder):
    key = "system"
    nav_label = "System"
    title = "Which game system?"
    subtitle = "Pick the console your game is for."
    placeholder = "You'll choose NES or SNES here."


class GenreStep(_Placeholder):
    key = "genre"
    nav_label = "Kind of game"
    title = "What kind of game?"
    subtitle = "Pick one kind, or mix two for something new."
    placeholder = "You'll pick from a list here, with an optional second pick to mix."


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
