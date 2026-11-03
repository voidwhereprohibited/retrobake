"""Describe -> Questions -> Cover & name -> Bake -> Finish, end to end, offscreen and offline."""

import os
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QComboBox

from retrobake import retroarch
from retrobake import spec as gamespec
from retrobake.ai.service import AIService, AISettings
from retrobake.ui import theme
from retrobake.ui.screens import default_steps
from retrobake.ui.session import Session, default_bake
from retrobake.ui.wizard import WizardWindow

KEYS = ["welcome", "system", "genre", "describe", "questions", "art_name", "bake", "finish"]


def wait(app, cond, timeout=60.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


def fake_bake(spec, work_dir: Path) -> Path:
    assert gamespec.validate(spec) == []
    work_dir.mkdir(parents=True, exist_ok=True)
    p = work_dir / "game.nes"
    p.write_bytes(b"NES\x1a" + bytes(100))
    return p


class FakeLauncher:
    def __init__(self):
        self.played = []

    def play(self, inst, rom, system):
        self.played.append((inst, rom, system))


@pytest.fixture
def make(app, tmp_path):
    made = []

    def _make(bake=fake_bake, detect=lambda: [], saves=None):
        theme.set_font_scale(app, 1.0)
        session = Session(
            ai=AIService(AISettings(online=False), cache_dir=False),
            work_dir=tmp_path / "games",
            bake=bake,
            detect=detect,
            launcher=FakeLauncher(),
            ask_save=lambda cap, name, flt: (saves or {}).get(cap),
        )
        win = WizardWindow(default_steps(session), app)
        win.show()
        made.append(win)
        return win, session

    yield _make
    for w in made:
        w.close()
        w.deleteLater()
    app.processEvents()


def step(win, key):
    return win.steps[KEYS.index(key)]


def walk_to_cover(app, win, description="a fox in glowing caves"):
    win.next_btn.click()  # welcome -> system
    win.next_btn.click()  # system -> genre
    win.next_btn.click()  # genre -> describe
    assert win.current.key == "describe"
    step(win, "describe").edit.setPlainText(description)
    win.next_btn.click()
    assert win.current.key == "questions"
    win.next_btn.click()
    assert win.current.key == "art_name"
    wait(app, lambda: not step(win, "art_name").busy)


def test_full_flow_bakes_and_finishes(app, make, tmp_path):
    win, session = make(
        saves={
            "Save your game": str(tmp_path / "out.nes"),
            "Save the cover": str(tmp_path / "cover.png"),
        }
    )
    walk_to_cover(app, win)
    art = step(win, "art_name")
    assert art.names.count() >= 1 and art.name_edit.text()  # first idea picked
    art.name_edit.setText("Cave Fox")
    assert win.next_btn.isEnabled()
    win.next_btn.click()
    assert win.current.key == "bake"
    wait(app, lambda: session.rom_path is not None)
    assert win.spec["title"] == "Cave Fox" and gamespec.validate(win.spec) == []
    assert session.cover_png.startswith(b"\x89PNG")
    win.next_btn.click()
    fin = step(win, "finish")
    assert all(b.isEnabled() for b in fin.actions)
    fin.save_rom()
    fin.save_cover()
    assert (tmp_path / "out.nes").read_bytes() == session.rom_path.read_bytes()
    assert (tmp_path / "cover.png").read_bytes() == session.cover_png


def test_description_is_cleaned_and_franchise_names_become_style(app, make):
    win, _ = make()
    for _ in range(3):
        win.next_btn.click()
    d = step(win, "describe")
    d.edit.setPlainText("like Zelda meets Mario\x00 with a dragon")
    assert d.notice.isVisible() or not d.notice.isHidden()
    win.next_btn.click()
    assert "zelda" not in win.spec["description"].lower()
    assert "\x00" not in win.spec["description"]
    assert gamespec.validate(win.spec) == []


def test_questions_follow_answers_and_apply(app, make):
    win, _ = make()
    for _ in range(4):
        win.next_btn.click()
    q = step(win, "questions")
    assert q.widgets and win.current.key == "questions"
    combo = next(w for w in q.widgets.values() if isinstance(w, QComboBox))
    combo.setCurrentIndex(combo.count() - 1)
    win.next_btn.click()
    assert gamespec.validate(win.spec) == []


def test_bad_name_blocks_next_with_plain_message(app, make):
    win, _ = make()
    walk_to_cover(app, win)
    art = step(win, "art_name")
    art.name_edit.setText("Zelda Quest")
    assert not win.next_btn.isEnabled()
    assert art.error.text()
    art.name_edit.setText("Moon Quest")
    assert win.next_btn.isEnabled()


def test_bake_failure_is_plain_english_and_retry_works(app, make):
    calls = []

    def flaky(spec, work_dir):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom internal detail")
        return fake_bake(spec, work_dir)

    win, session = make(bake=flaky)
    walk_to_cover(app, win)
    win.next_btn.click()
    bake = step(win, "bake")
    wait(app, lambda: not bake.busy)
    assert "boom" not in bake.status.text() and bake.retry.isVisibleTo(bake)
    assert not win.back_btn.isHidden() and not win.next_btn.isEnabled()
    bake.retry.click()
    wait(app, lambda: session.rom_path is not None)
    assert win.next_btn.isEnabled()


def test_play_and_library_without_retroarch_show_setup_help(app, make):
    win, session = make(detect=lambda: [])
    walk_to_cover(app, win)
    win.next_btn.click()
    wait(app, lambda: session.rom_path is not None)
    win.next_btn.click()
    fin = step(win, "finish")
    fin.actions[0].click()
    assert "RetroArch" in fin.message.text()
    assert session.launcher.played == []


def test_play_launches_retroarch_when_ready(app, make, monkeypatch):
    class Inst:
        def find_core(self, system):
            return Path("core.so"), object()

    win, session = make(detect=lambda: [Inst()])
    monkeypatch.setattr(retroarch, "pick", lambda installs, system: installs[0])
    monkeypatch.setattr("retrobake.ui.make_screens.retroarch.pick", lambda i, s: i[0])
    walk_to_cover(app, win)
    win.next_btn.click()
    wait(app, lambda: session.rom_path is not None)
    win.next_btn.click()
    step(win, "finish").actions[0].click()
    assert session.launcher.played and session.launcher.played[0][2] == "nes"


def test_make_another_game_restarts(app, make):
    win, session = make()
    walk_to_cover(app, win)
    win.next_btn.click()
    wait(app, lambda: session.rom_path is not None)
    win.next_btn.click()
    step(win, "finish").again.click()
    assert win.current.key == "system" and session.rom_path is None and not win.spec


@pytest.mark.skipif(
    not os.environ.get("RETROBAKE_CC65_DIR") and os.environ.get("RETROBAKE_REQUIRE_CC65") != "1",
    reason="cc65 not bundled here (CI provides it)",
)
@pytest.mark.parametrize("genre_index", [0, 1])
def test_real_nes_bake_through_the_ui(app, make, genre_index):
    win, session = make(bake=default_bake)
    win.next_btn.click()
    win.next_btn.click()  # genre
    g = step(win, "genre")
    g.primary.setCurrentIndex(min(genre_index, g.primary.count() - 1))
    win.next_btn.click()
    step(win, "describe").edit.setPlainText("a brave robot in a neon city")
    win.next_btn.click()
    win.next_btn.click()
    wait(app, lambda: not step(win, "art_name").busy)
    step(win, "art_name").name_edit.setText("Neon Bot")
    win.next_btn.click()
    wait(app, lambda: not step(win, "bake").busy, timeout=240)
    rom = session.rom_path.read_bytes()
    assert session.rom_path.suffix == ".nes" and rom[:4] == b"NES\x1a" and len(rom) > 16000
