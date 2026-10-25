"""M1: the System + Genre screens produce a valid game-spec."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from retrobake import spec as gamespec
from retrobake.ui.screens import GenreStep, SystemStep


def _to(window, key):
    while window.current.key != key:
        window.next_btn.click()
    return window.current


@pytest.mark.parametrize("system", ["nes", "snes"])
def test_single_genre_spec_validates(window, system):
    step = _to(window, "system")
    step.buttons[system].setChecked(True)
    window.next_btn.click()
    genre = window.current
    assert isinstance(genre, GenreStep)
    for i in range(genre.primary.count()):
        genre.primary.setCurrentIndex(i)
        window.next_btn.click()
        spec = window.spec
        assert spec["system"] == system
        assert spec["genres"] == [genre.primary.itemData(i)]
        assert gamespec.validate(spec) == []
        window.back_btn.click()


def test_mashup_spec_validates_and_keeps_seed(window):
    _to(window, "genre")
    genre = window.current
    genre.primary.setCurrentIndex(genre.primary.findData("platformer"))
    assert not genre.secondary.isVisible()
    genre.mix.setChecked(True)
    assert genre.secondary.isVisible()
    second = [genre.secondary.itemData(i) for i in range(genre.secondary.count())]
    assert "platformer" not in second and second
    window.next_btn.click()
    spec = window.spec
    assert spec["genres"] == ["platformer", second[0]]
    assert gamespec.validate(spec) == []
    seed = spec["seed"]
    window.back_btn.click()
    window.next_btn.click()
    assert window.spec["seed"] == seed  # re-applying keeps the same game


def test_only_available_genres_offered():
    step = GenreStep()
    offered = [step.primary.itemData(i) for i in range(step.primary.count())]
    assert offered == gamespec.available_genres()


def test_back_restores_choices(window):
    sys_step = _to(window, "system")
    sys_step.buttons["snes"].setChecked(True)
    window.next_btn.click()
    genre = window.current
    genre.primary.setCurrentIndex(genre.primary.findData("topdown_adventure"))
    genre.mix.setChecked(True)
    window.next_btn.click()
    window.back_btn.click()
    window.back_btn.click()
    assert isinstance(window.current, SystemStep) and window.current.system == "snes"
    window.next_btn.click()
    assert window.current.genres == window.spec["genres"]


def test_system_keyboard_arrows_switch(window, app):
    step = _to(window, "system")
    window.activateWindow()
    QTest.qWaitForWindowActive(window)
    first = step.buttons["nes"]
    first.setChecked(True)
    first.setFocus()
    QTest.keyClick(first, Qt.Key.Key_Down)
    app.processEvents()
    assert step.system == "snes"


def test_franchise_free_labels():
    step = GenreStep()
    labels = [step.primary.itemText(i) for i in range(step.primary.count())]
    from retrobake.security import find_ip

    assert all(not find_ip(lbl) for lbl in labels)
