"""RetroArch integration tests. Everything uses fake folders and a fake launcher:
nothing touches a real RetroArch install or starts a real program."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from retrobake.retroarch import (
    PLAYLIST_FILE,
    Launcher,
    LaunchError,
    PlaylistError,
    add_game,
    advise,
    clean_label,
    detect,
    pick,
    plan_launch,
    remove_game,
    thumbnail_name,
)
from retrobake.retroarch.config import read_cfg, resolve_dir

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def touch(p: Path, data: bytes = b"x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def no_which(_name: str):
    return None


# ------------------------------------------------------------------ config


def test_read_cfg_and_resolve(tmp_path):
    cfg = touch(
        tmp_path / "retroarch.cfg",
        b'# comment\nlibretro_directory = "~/cores"\nplaylist_directory = "default"\n'
        b'thumbnails_directory = ":\\thumbs"\n',
    )
    vals = read_cfg(cfg)
    assert vals["libretro_directory"] == "~/cores"
    assert (
        resolve_dir(vals["libretro_directory"], home=tmp_path, exe_dir=None) == tmp_path / "cores"
    )
    assert resolve_dir(vals["playlist_directory"], home=tmp_path, exe_dir=None) is None
    assert resolve_dir(vals["thumbnails_directory"], home=tmp_path, exe_dir=tmp_path) == (
        tmp_path / "thumbs"
    )
    assert read_cfg(tmp_path / "missing.cfg") == {}


# ------------------------------------------------------------------ Linux detection


def test_linux_flatpak(tmp_path):
    home = tmp_path
    touch(home / ".local/share/flatpak/exports/bin/org.libretro.RetroArch")
    core = touch(home / ".var/app/org.libretro.RetroArch/config/retroarch/cores/mesen_libretro.so")
    found = detect(
        os_name="linux",
        home=home,
        env={},
        which=lambda n: "/usr/bin/flatpak" if n == "flatpak" else None,
    )
    assert [i.kind for i in found] == ["linux-flatpak"]
    inst = found[0]
    assert inst.launch == ("/usr/bin/flatpak", "run", "org.libretro.RetroArch")
    assert inst.find_core("nes")[0] == core
    assert inst.find_core("snes") is None
    assert inst.playlists_dir == home / ".var/app/org.libretro.RetroArch/config/retroarch/playlists"


def test_linux_native_reads_cfg_dirs(tmp_path):
    home = tmp_path
    cfg_dir = home / ".config/retroarch"
    touch(
        cfg_dir / "retroarch.cfg",
        b'libretro_directory = "~/mycores"\nplaylist_directory = "~/lists"\n'
        b'thumbnails_directory = "~/thumbs"\n',
    )
    core = touch(home / "mycores/snes9x_libretro.so")
    found = detect(
        os_name="linux",
        home=home,
        env={},
        which=lambda n: "/usr/bin/retroarch" if n == "retroarch" else None,
    )
    inst = found[0]
    assert inst.kind == "linux-native"
    assert inst.find_core("snes")[0] == core
    assert inst.playlists_dir == home / "lists"
    assert inst.thumbnails_dir == home / "thumbs"


def test_linux_xdg_config_home(tmp_path):
    xdg = tmp_path / "xdg"
    core = touch(xdg / "retroarch/cores/fceumm_libretro.so")
    found = detect(
        os_name="linux",
        home=tmp_path,
        env={"XDG_CONFIG_HOME": str(xdg)},
        which=lambda n: "/usr/bin/retroarch" if n == "retroarch" else None,
    )
    assert found[0].find_core("nes")[0] == core


def test_linux_appimage_portable_home(tmp_path):
    app = touch(tmp_path / "Applications/RetroArch-Linux-x86_64.AppImage")
    core = touch(
        tmp_path / "Applications/RetroArch-Linux-x86_64.AppImage.home/.config/retroarch/cores/"
        "nestopia_libretro.so"
    )
    found = detect(os_name="linux", home=tmp_path, env={}, which=no_which)
    assert found[0].kind == "linux-appimage"
    assert found[0].launch == (str(app),)
    assert found[0].find_core("nes")[0] == core


def test_linux_steam_with_extra_library(tmp_path):
    lib2 = tmp_path / "games"
    vdf = f'"libraryfolders"\n{{\n "0"\n {{\n  "path"  "{lib2}"\n }}\n}}\n'
    touch(tmp_path / ".local/share/Steam/steamapps/libraryfolders.vdf", vdf.encode())
    exe = touch(lib2 / "steamapps/common/RetroArch/retroarch")
    core = touch(lib2 / "steamapps/common/RetroArch/cores/bsnes_libretro.so")
    found = detect(os_name="linux", home=tmp_path, env={}, which=no_which)
    assert found[0].kind == "linux-steam"
    assert found[0].launch == (str(exe),)
    assert found[0].find_core("snes")[0] == core


def test_linux_nothing_installed(tmp_path):
    assert detect(os_name="linux", home=tmp_path, env={}, which=no_which) == []


# ------------------------------------------------------------------ Windows detection


def test_windows_installer_and_steam(tmp_path):
    drive = tmp_path / "C"
    appdata = tmp_path / "AppData/Roaming"
    env = {
        "SystemDrive": str(drive),
        "APPDATA": str(appdata),
        "ProgramFiles(x86)": str(drive / "Program Files (x86)"),
        "ProgramFiles": str(drive / "Program Files"),
    }
    ra = drive / "RetroArch-Win64"
    touch(ra / "retroarch.exe")
    touch(ra / "retroarch.cfg", b'libretro_directory = ":\\cores"\n')
    core = touch(ra / "cores/mesen_libretro.dll")
    steam_ra = drive / "Program Files (x86)/Steam/steamapps/common/RetroArch"
    touch(steam_ra / "retroarch.exe")
    found = detect(os_name="windows", home=tmp_path / "user", env=env, which=no_which)
    kinds = [i.kind for i in found]
    assert kinds == ["windows-installer", "windows-steam"]
    assert found[0].config_dir == ra
    assert found[0].find_core("nes")[0] == core
    assert found[1].config_dir == appdata  # no cfg beside exe -> %APPDATA%
    assert pick(found, "nes") is found[0]
    assert pick(found, "snes") is found[0]  # nobody has snes: first one


def test_extra_folder_portable(tmp_path):
    folder = tmp_path / "MyRA"
    touch(folder / "retroarch")
    core = touch(folder / "cores/snes9x_libretro.so")
    found = detect(os_name="linux", home=tmp_path, env={}, which=no_which, extra_folders=[folder])
    assert found[0].find_core("snes")[0] == core


def test_core_preference_order(tmp_path):
    folder = tmp_path / "RA"
    touch(folder / "retroarch")
    touch(folder / "cores/nestopia_libretro.so")
    touch(folder / "cores/fceumm_libretro.so")
    inst = detect(os_name="linux", home=tmp_path, env={}, which=no_which, extra_folders=[folder])[0]
    assert inst.find_core("nes")[1].file_stem == "fceumm_libretro"
    touch(folder / "cores/mesen_libretro.so")
    assert inst.find_core("nes")[1].file_stem == "mesen_libretro"


# ------------------------------------------------------------------ launching


@pytest.fixture
def inst(tmp_path):
    folder = tmp_path / "RA"
    touch(folder / "retroarch")
    touch(folder / "cores/mesen_libretro.so")
    touch(folder / "cores/snes9x_libretro.so")
    return detect(os_name="linux", home=tmp_path, env={}, which=no_which, extra_folders=[folder])[0]


class FakeProc:
    def __init__(self, argv, **kw):
        self.argv = argv
        self.kw = kw
        self.alive = True
        self.terminated = False

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.terminated = True
        self.alive = False

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.alive = False


def test_plan_launch_argv(inst, tmp_path):
    rom = touch(tmp_path / "out/My Game.nes")
    plan = plan_launch(inst, rom, "nes")
    assert plan.argv[-3] == "-L"
    assert plan.argv[-2].endswith("mesen_libretro.so")
    assert plan.argv[-1] == str(rom.resolve())  # spaces stay one argument


def test_plan_launch_rejects_bad_input(inst, tmp_path):
    with pytest.raises(LaunchError):
        plan_launch(inst, touch(tmp_path / "evil.sh"), "nes")
    with pytest.raises(LaunchError):
        plan_launch(inst, tmp_path / "missing.nes", "nes")
    with pytest.raises(LaunchError):
        plan_launch(inst, touch(tmp_path / "g.nes"), "n64")
    inst.cores_dirs = [tmp_path / "empty"]
    with pytest.raises(LaunchError):
        plan_launch(inst, touch(tmp_path / "g.nes"), "nes")


def test_launcher_play_and_relaunch(inst, tmp_path):
    procs = []

    def fake_popen(argv, **kw):
        p = FakeProc(argv, **kw)
        procs.append(p)
        return p

    launcher = Launcher(popen=fake_popen)
    rom1 = touch(tmp_path / "a.sfc")
    launcher.play(inst, rom1, "snes")
    assert launcher.running
    assert isinstance(procs[0].argv, list)  # list argv, never a shell string
    assert "shell" not in procs[0].kw
    rom2 = touch(tmp_path / "b.sfc")
    launcher.relaunch(inst, rom2, "snes")
    assert procs[0].terminated
    assert procs[1].argv[-1] == str(rom2.resolve())
    # a bad new ROM must not close the running game
    with pytest.raises(LaunchError):
        launcher.relaunch(inst, tmp_path / "nope.sfc", "snes")
    assert not procs[1].terminated


def test_launcher_start_failure(inst, tmp_path):
    def boom(argv, **kw):
        raise FileNotFoundError

    with pytest.raises(LaunchError):
        Launcher(popen=boom).play(inst, touch(tmp_path / "a.nes"), "nes")


# ------------------------------------------------------------------ playlist + thumbnails


def test_thumbnail_rules():
    assert thumbnail_name('Q*bert: "Cubes" & <You>?') == "Q_bert_ _Cubes_ _ _You__.png"
    assert thumbnail_name("A/B\\C|D`E") == "A_B_C_D_E.png"


def test_clean_label():
    assert clean_label("  Hero\x00\x1b[31m  Quest\n ") == "Hero[31m Quest"
    assert clean_label("") == "My RetroBake Game"
    assert len(clean_label("x" * 500)) == 64


def test_add_update_remove_game(inst, tmp_path):
    rom = touch(tmp_path / "out/sky.nes")
    core_path, core = inst.find_core("nes")
    lpl = add_game(inst, rom, "Sky: Rising", core_path, core, cover_png=PNG)
    assert lpl == inst.playlists_dir / PLAYLIST_FILE
    data = json.loads(lpl.read_text())
    assert data["version"] == "1.5"
    assert data["items"] == [
        {
            "path": str(rom.resolve()),
            "label": "Sky: Rising",
            "core_path": str(core_path),
            "core_name": core.display_name,
            "crc32": "DETECT",
            "db_name": "RetroBake.lpl",
        }
    ]
    thumb = inst.thumbnails_dir / "RetroBake/Named_Boxarts/Sky_ Rising.png"
    assert thumb.read_bytes() == PNG
    # re-adding the same ROM updates, doesn't duplicate
    add_game(inst, rom, "Sky Rising 2", core_path, core)
    data = json.loads(lpl.read_text())
    assert [i["label"] for i in data["items"]] == ["Sky Rising 2"]
    other = touch(tmp_path / "out/sea.nes")
    add_game(inst, other, "Sea", core_path, core)
    remove_game(inst, rom)
    data = json.loads(lpl.read_text())
    assert [i["label"] for i in data["items"]] == ["Sea"]
    # no temp files left behind
    assert not list(inst.playlists_dir.glob(".retrobake-*"))


def test_corrupt_playlist_is_replaced(inst, tmp_path):
    lpl = touch(inst.playlists_dir / PLAYLIST_FILE, b"{not json")
    core_path, core = inst.find_core("nes")
    add_game(inst, touch(tmp_path / "a.nes"), "A", core_path, core)
    assert len(json.loads(lpl.read_text())["items"]) == 1


def test_cover_validation(inst, tmp_path):
    core_path, core = inst.find_core("nes")
    rom = touch(tmp_path / "a.nes")
    with pytest.raises(PlaylistError):
        add_game(inst, rom, "A", core_path, core, cover_png=b"GIF89a....")
    with pytest.raises(PlaylistError):
        add_game(inst, rom, "A", core_path, core, cover_png=PNG + b"\x00" * (5 * 1024 * 1024))


def test_never_touches_retroarch_cfg(inst, tmp_path):
    cfg = touch(inst.config_dir / "retroarch.cfg", b'video_driver = "gl"\n')
    before = cfg.read_bytes()
    core_path, core = inst.find_core("nes")
    add_game(inst, touch(tmp_path / "a.nes"), "A", core_path, core, cover_png=PNG)
    assert cfg.read_bytes() == before


# ------------------------------------------------------------------ setup helper


def test_advise_missing_retroarch():
    for os_name in ("windows", "linux"):
        a = advise([], "nes", os_name)
        assert not a.ok
        assert a.actions[0].url.startswith("https://")
        assert not any("sudo" in s or "terminal" in s.lower() for s in a.steps)


def test_advise_missing_core_and_ready(inst, tmp_path):
    inst.cores_dirs = [tmp_path / "none"]
    a = advise([inst], "snes", "linux")
    assert not a.ok and "Core Downloader" in " ".join(a.steps)
    inst.cores_dirs = [tmp_path / "RA/cores"]
    assert advise([inst], "snes", "linux").ok
