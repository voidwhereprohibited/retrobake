"""Plain-English help when RetroArch or a core is missing. No terminal steps."""

from __future__ import annotations

from dataclasses import dataclass, field

from .cores import CORES
from .detect import RetroArchInstall

RETROARCH_DOWNLOAD = "https://www.retroarch.com/?page=platforms"
FLATHUB_PAGE = "https://flathub.org/apps/org.libretro.RetroArch"
STEAM_PAGE = "https://store.steampowered.com/app/1118310/RetroArch/"

SYSTEM_NAMES = {"nes": "NES", "snes": "Super NES"}


@dataclass(frozen=True)
class Action:
    label: str
    url: str | None = None  # open in the browser / software store


@dataclass(frozen=True)
class SetupAdvice:
    ok: bool
    title: str
    message: str
    steps: list[str] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)


def advise(installs: list[RetroArchInstall], system: str, os_name: str) -> SetupAdvice:
    sys_name = SYSTEM_NAMES.get(system, system.upper())
    if not installs:
        if os_name == "windows":
            return SetupAdvice(
                False,
                "RetroArch isn't installed yet",
                "RetroArch is the free app that plays your games. Install it once and "
                "RetroBake will find it by itself.",
                [
                    "Click “Get RetroArch” and download the Windows Installer (64-bit).",
                    "Open the file you downloaded and keep clicking Next.",
                    "Come back here and click “Check again”.",
                ],
                [
                    Action("Get RetroArch", RETROARCH_DOWNLOAD),
                    Action("Get it on Steam", STEAM_PAGE),
                ],
            )
        return SetupAdvice(
            False,
            "RetroArch isn't installed yet",
            "RetroArch is the free app that plays your games. Install it once and "
            "RetroBake will find it by itself.",
            [
                "Click “Get RetroArch”. Your software store (or the Flathub page) opens.",
                "Click Install.",
                "Come back here and click “Check again”.",
            ],
            [Action("Get RetroArch", FLATHUB_PAGE), Action("Get it on Steam", STEAM_PAGE)],
        )

    inst = installs[0]
    for candidate in installs:
        if candidate.find_core(system):
            return SetupAdvice(
                True, "Ready to play", f"{candidate.label} is ready to play {sys_name} games."
            )

    best = CORES[system][0]
    steps = [
        "Open RetroArch.",
        "Go to Main Menu → Online Updater → Core Downloader.",
        f"Pick “{best.downloader_name}” and wait for “Download complete”.",
        "Close RetroArch, come back here and click “Check again”.",
    ]
    if inst.kind == "linux-native":
        steps.append(
            "Don't see Core Downloader? Your RetroArch came from your Linux software store "
            "without it. Easiest fix: install the Flatpak version from Flathub instead."
        )
    actions = [Action("Check again")]
    if inst.kind == "linux-native":
        actions.append(Action("Get Flatpak RetroArch", FLATHUB_PAGE))
    return SetupAdvice(
        False,
        f"RetroArch needs one small add-on for {sys_name} games",
        f"RetroArch plays each console with an add-on called a “core”. "
        f"The {sys_name} one is free and takes a few seconds to add.",
        steps,
        actions,
    )
