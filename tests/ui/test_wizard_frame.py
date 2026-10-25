from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton, QVBoxLayout

from retrobake.ui import WizardStep, WizardWindow, theme
from retrobake.ui.screens import default_steps

EXPECTED = ["welcome", "system", "genre", "describe", "questions", "art_name", "bake", "finish"]


def test_steps_in_plan_order(window):
    assert [s.key for s in window.steps] == EXPECTED
    assert window.index == 0
    assert not window.back_btn.isVisible()
    assert window.next_btn.text() == "Let's start"


def test_next_and_back_walk_every_step(window):
    for i in range(1, len(EXPECTED)):
        window.next_btn.click()
        assert window.index == i
    assert not window.next_btn.isVisible()  # finish screen has its own buttons
    for i in range(len(EXPECTED) - 2, -1, -1):
        window.back_btn.click()
        assert window.index == i


def test_keyboard_enter_and_shortcuts(window, app):
    window.activateWindow()
    QTest.qWaitForWindowActive(window)
    QTest.keyClick(window, Qt.Key.Key_Return)
    app.processEvents()
    assert window.index == 1
    QTest.keyClick(window, Qt.Key.Key_N, Qt.KeyboardModifier.AltModifier)
    app.processEvents()
    assert window.index == 2
    QTest.keyClick(window, Qt.Key.Key_B, Qt.KeyboardModifier.AltModifier)
    app.processEvents()
    assert window.index == 1
    QTest.keyClick(window, Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)
    app.processEvents()
    assert window.index == 2


class _Gate(WizardStep):
    key = "gate"
    nav_label = "Gate"
    title = "Gate"
    ok = False

    def is_complete(self):
        return self.ok

    def apply_to(self, spec):
        spec["gate"] = True


def test_next_blocked_until_step_complete(app):
    gate = _Gate()
    win = WizardWindow([gate, _Gate()], app)
    assert not win.next_btn.isEnabled()
    win.go_next()
    assert win.index == 0 and "gate" not in win.spec
    gate.ok = True
    gate.changed.emit()
    assert win.next_btn.isEnabled()
    win.go_next()
    assert win.index == 1 and win.spec == {"gate": True}
    win.deleteLater()


def test_zoom_scales_fonts_in_points_and_clamps(window, app):
    base = app.font().pointSizeF()
    title = window.current.title_label.font().pointSizeF()
    window.zoom_in()
    assert app.font().pointSizeF() > base
    assert window.current.title_label.font().pointSizeF() > title
    assert window.next_btn.font().pointSizeF() == app.font().pointSizeF()
    for _ in range(50):
        window.zoom_in()
    assert window.scale == theme.MAX_SCALE
    window.zoom_reset()
    assert app.font().pointSizeF() == theme.BASE_POINT_SIZE
    assert app.font().pixelSize() == -1  # never pixel-sized


def test_fits_small_laptop_even_at_max_zoom(window, app):
    assert window.minimumWidth() <= 1366 and window.minimumHeight() <= 768
    window.set_scale(theme.MAX_SCALE)
    window.resize(1366, 700)
    app.processEvents()
    hint = window.minimumSizeHint()
    assert hint.width() <= 1366 and hint.height() <= 768


def test_every_button_has_accessible_name(window):
    for b in window.findChildren(QPushButton):
        assert b.accessibleName(), b.text()
    for s in window.steps:
        assert s.accessibleName()


def test_tab_reaches_next_button(window, app):
    window.go_to(len(EXPECTED) - 1)  # finish: has several buttons
    window.go_to(0)
    assert window.next_btn.hasFocus() or window.focusWidget() is not None
    assert window.next_btn.focusPolicy() & Qt.FocusPolicy.TabFocus


def test_theme_contrast_meets_wcag_aa():
    for c in (theme.LIGHT, theme.DARK):
        assert theme.contrast_ratio(c.text, c.window) >= 7
        assert theme.contrast_ratio(c.text, c.surface) >= 7
        assert theme.contrast_ratio(c.muted, c.surface) >= 4.5
        assert theme.contrast_ratio(c.muted, c.window) >= 4.5
        assert theme.contrast_ratio(c.accent_text, c.accent) >= 4.5
        assert theme.contrast_ratio(c.focus, c.surface) >= 3  # focus ring, non-text


def test_both_themes_apply(app):
    assert theme.apply_theme(app, dark=True) is theme.DARK
    assert theme.apply_theme(app, dark=False) is theme.LIGHT


def test_finish_step_has_four_actions():
    steps = default_steps()
    finish = steps[-1]
    assert [b.text() for b in finish.actions] == [
        "Play now in RetroArch",
        "Save game to…",
        "Save cover art…",
        "Add to RetroArch library",
    ]
    assert isinstance(finish.layout(), QVBoxLayout)


def test_progress_label_tracks_step(window):
    assert window.progress_label.text() == "Step 1 of 8 · Welcome"
    window.next_btn.click()
    assert window.progress_label.text() == "Step 2 of 8 · System"
    assert window.progress.value() == 2


def test_enter_on_focused_button_clicks_that_button(window, app):
    window.next_btn.click()
    window.back_btn.setFocus()
    QTest.keyClick(window.back_btn, Qt.Key.Key_Return)
    app.processEvents()
    assert window.index == 0


def test_button_text_never_clipped_at_any_zoom(window, app):
    for scale in (1.0, theme.MAX_SCALE):
        window.set_scale(scale)
        for i in range(len(EXPECTED)):
            window.go_to(i)
            app.processEvents()
            for b in (window.next_btn, window.back_btn):
                if b.isVisible():
                    need = b.fontMetrics().horizontalAdvance(b.text())
                    assert b.width() > need, (scale, i, b.text())
