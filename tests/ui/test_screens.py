"""The real wizard screens, driven headlessly."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QFileDialog

from retrobake.builders import nes
from retrobake.spec import validate
from retrobake.ui import screens
from retrobake.ui.session import Session

IDEA = "A brave fox explores a spooky haunted castle and stomps on ghosts."


@pytest.fixture
def steps(app):
    made = {s.key: s for s in screens.default_steps(Session())}
    yield made
    for s in made.values():
        s.deleteLater()


def _describe(steps, text=IDEA):
    for key in ("system", "genre"):
        steps[key].apply_to({})
    steps["describe"].text.setPlainText(text)
    steps["describe"].apply_to({})
    return steps["describe"].session


def test_system_order_and_only_nes_ready(steps):
    s = steps["system"]
    assert [label for _, label, _ in screens.SYSTEMS] == [
        "NES",
        "SNES",
        "N64",
        "Genesis",
        "Master System",
        "PS1 (2D)",
    ]
    assert [b.isEnabled() for b in s.buttons.values()] == [True] + [False] * 5
    assert all("coming soon" in b.text() for b in list(s.buttons.values())[1:])
    assert s.buttons["nes"].isChecked()


def test_genre_is_one_choice_with_up_to_two_inspirations(steps):
    g = steps["genre"]
    assert g.genre == "platformer" and g.is_complete()
    g.genre_buttons["topdown_adventure"].setChecked(True)
    assert g.genre == "topdown_adventure"
    assert not g.genre_buttons["platformer"].isChecked()
    assert not g.inspiration_boxes["topdown_adventure"].isEnabled()
    g.inspiration_boxes["platformer"].setChecked(True)
    g.inspiration_boxes["rpg"].setChecked(True)
    assert not g.inspiration_boxes["shooter"].isEnabled()  # two is the limit
    g.apply_to({})
    assert g.session.genre == "topdown_adventure"
    assert g.session.inspirations == ["platformer", "rpg"]


def test_unavailable_genres_say_coming_soon(steps):
    for gid, btn in steps["genre"].genre_buttons.items():
        assert btn.isEnabled() == ("coming soon" not in btn.text()), gid


def test_describe_runs_helper_and_shows_summary(steps):
    d = steps["describe"]
    assert not d.is_complete()
    d.text.setPlainText(IDEA)
    assert d.is_complete()
    summary = d.show_plan()
    assert "haunted" in summary and "Working title" in summary
    session = _describe(steps)
    assert validate(session.spec) == []
    assert session.spec["world"]["setting"] == "haunted"


def test_questions_are_prefilled_from_helper(steps):
    session = _describe(steps)
    q = steps["questions"]
    q.on_enter({})
    _, setting = q.fields["setting"]
    assert setting.currentData() == "haunted"
    assert q.answers()["hero_archetype"] == session.spec["hero"]["archetype"]
    setting.setCurrentIndex(setting.findData("ice"))
    q.apply_to({})
    assert session.spec["world"]["setting"] == "ice"
    assert validate(session.spec) == []


def test_cover_and_name(steps):
    session = _describe(steps)
    a = steps["art_name"]
    a.on_enter({})
    assert a.name.currentText() == session.spec["title"]
    assert a.name.count() > 1 and a.is_complete()
    first = session.cover_png
    assert first.startswith(b"\x89PNG")
    a.next_cover()
    assert session.cover_png != first
    a.name.setEditText("Super Mario Quest")
    assert not a.is_complete() and a.problem.text()
    a.name.setEditText("Lantern Keep")
    assert a.is_complete()
    a.apply_to({})
    assert session.spec["title"] == "Lantern Keep"


def test_bake_reports_errors_plainly(steps, wait_until):
    session = _describe(steps)

    def broken(spec):
        raise nes.NesBuildError("The baking tools are missing.")

    session.baker = broken
    b = steps["bake"]
    b.start()
    assert wait_until(lambda: b.bake_btn.isEnabled())
    assert not b.is_complete()
    assert "baking tools are missing" in b.status.text()


def _has_cc65() -> bool:
    try:
        nes.find_cc65()
    except nes.NesBuildError:
        return False
    return True


@pytest.mark.skipif(not _has_cc65(), reason="cc65 not installed")
def test_bake_then_save_rom_and_cover(steps, wait_until, tmp_path, monkeypatch):
    _describe(steps)
    a = steps["art_name"]
    a.on_enter({})
    a.apply_to({})
    b = steps["bake"]
    b.start()
    assert wait_until(b.is_complete, 60000), b.status.text()
    f = steps["finish"]
    f.on_enter({})
    assert all(btn.isEnabled() for btn in f.actions)
    target = tmp_path / "game.nes"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    f.save_rom()
    assert target.read_bytes()[:4] == b"NES\x1a"
    cover = tmp_path / "cover.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(cover), ""))
    f.save_cover()
    assert cover.read_bytes().startswith(b"\x89PNG")


def test_finish_buttons_wait_for_a_bake(steps):
    f = steps["finish"]
    f.on_enter({})
    assert not any(btn.isEnabled() for btn in f.actions)


def test_safe_filename():
    assert screens.safe_filename("Lantern Keep!") == "Lantern_Keep"
    assert screens.safe_filename("../..") == "game"
    assert isinstance(screens.games_dir(), Path)


def test_every_screen_fits_1366x768(window, app):
    window.resize(1366, 768)
    for i in range(len(window.steps)):
        window.go_to(i)
        app.processEvents()
        hint = window.minimumSizeHint()
        assert hint.width() <= 1366 and hint.height() <= 768, window.current.key
