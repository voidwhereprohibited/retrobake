"""Tiny headless libretro frontend for RetroBake's ROM boot tests (stdlib only).

It loads one libretro core (the same cores players use in RetroArch), boots one ROM,
runs it for a fixed number of frames, presses Start, and prints one JSON result line.
run_smoke.py calls this in a child process, so an emulator crash or hang can never
take the test runner down with it.

Usage: python libretro_harness.py --core <core.so|dll> --rom <rom> --system nes|snes
"""

from __future__ import annotations

import argparse
import ctypes as C
import json
import sys
import tempfile
from pathlib import Path

# libretro.h constants we need
ENV_GET_CAN_DUPE = 3
ENV_SET_PERFORMANCE_LEVEL = 8
ENV_GET_SYSTEM_DIRECTORY = 9
ENV_SET_PIXEL_FORMAT = 10
ENV_GET_VARIABLE_UPDATE = 17
ENV_GET_CORE_ASSETS_DIRECTORY = 30
ENV_GET_SAVE_DIRECTORY = 31
DIR_QUERIES = (ENV_GET_SYSTEM_DIRECTORY, ENV_GET_CORE_ASSETS_DIRECTORY, ENV_GET_SAVE_DIRECTORY)
DEVICE_JOYPAD = 1
JOYPAD_START = 3
JOYPAD_MASK = 256
MEMORY_SYSTEM_RAM = 2

# Boot signature contract (see tests/TEST_PLAN.md): 4 bytes in system RAM.
# NES CPU $07FC-$07FF, SNES WRAM $7E:1FFC-$1FFF -> "R" "B" <version=1> <state>.
SIGNATURE_OFFSET = {"nes": 0x07FC, "snes": 0x1FFC}

ENV_CB = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO_CB = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO_CB = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDIO_BATCH_CB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL_CB = C.CFUNCTYPE(None)
STATE_CB = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


class SystemInfo(C.Structure):
    _fields_ = [
        ("library_name", C.c_char_p),
        ("library_version", C.c_char_p),
        ("valid_extensions", C.c_char_p),
        ("need_fullpath", C.c_bool),
        ("block_extract", C.c_bool),
    ]


class GameInfo(C.Structure):
    _fields_ = [
        ("path", C.c_char_p),
        ("data", C.c_void_p),
        ("size", C.c_size_t),
        ("meta", C.c_char_p),
    ]


class Geometry(C.Structure):
    _fields_ = [
        ("base_width", C.c_uint),
        ("base_height", C.c_uint),
        ("max_width", C.c_uint),
        ("max_height", C.c_uint),
        ("aspect_ratio", C.c_float),
    ]


class Timing(C.Structure):
    _fields_ = [("fps", C.c_double), ("sample_rate", C.c_double)]


class AVInfo(C.Structure):
    _fields_ = [("geometry", Geometry), ("timing", Timing)]


class Frontend:
    def __init__(self, core_path: Path, workdir: Path) -> None:
        self.lib = C.CDLL(str(core_path))
        self.pixel_format = 0  # libretro default: 0RGB1555
        self.frame: tuple[bytes, int, int, int] | None = None
        self.frames_drawn = 0
        self.start_down = False
        self._dirbuf = C.create_string_buffer(str(workdir).encode())
        self._keep: list = []
        self._cbs = (
            ENV_CB(self._env),
            VIDEO_CB(self._video),
            AUDIO_CB(lambda left, right: None),
            AUDIO_BATCH_CB(lambda data, frames: frames),
            POLL_CB(lambda: None),
            STATE_CB(self._state),
        )
        lib = self.lib
        lib.retro_api_version.restype = C.c_uint
        lib.retro_load_game.restype = C.c_bool
        lib.retro_get_memory_data.restype = C.c_void_p
        lib.retro_get_memory_data.argtypes = [C.c_uint]
        lib.retro_get_memory_size.restype = C.c_size_t
        lib.retro_get_memory_size.argtypes = [C.c_uint]
        lib.retro_set_controller_port_device.argtypes = [C.c_uint, C.c_uint]

    # --- callbacks -------------------------------------------------------------
    def _env(self, cmd: int, data: int | None) -> bool:
        if not data:
            return False
        if cmd == ENV_GET_CAN_DUPE:
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        if cmd == ENV_SET_PIXEL_FORMAT:
            fmt = C.cast(data, C.POINTER(C.c_int))[0]
            if fmt in (0, 1, 2):
                self.pixel_format = fmt
                return True
            return False
        if cmd in DIR_QUERIES:
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.addressof(self._dirbuf)
            return True
        if cmd == ENV_GET_VARIABLE_UPDATE:
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        return cmd == ENV_SET_PERFORMANCE_LEVEL

    def _video(self, data: int | None, width: int, height: int, pitch: int) -> None:
        self.frames_drawn += 1
        if data:
            self.frame = (C.string_at(data, pitch * height), width, height, pitch)

    def _state(self, port: int, device: int, index: int, button: int) -> int:
        if port != 0 or (device & 0xFF) != DEVICE_JOYPAD:
            return 0
        if button == JOYPAD_MASK:
            return (1 << JOYPAD_START) if self.start_down else 0
        return 1 if (button == JOYPAD_START and self.start_down) else 0

    # --- driving the core ------------------------------------------------------
    def load(self, rom: Path) -> dict:
        lib = self.lib
        if lib.retro_api_version() != 1:
            raise RuntimeError("core is not libretro API v1")
        env, video, audio, batch, poll, state = self._cbs
        lib.retro_set_environment(env)
        lib.retro_set_video_refresh(video)
        lib.retro_set_audio_sample(audio)
        lib.retro_set_audio_sample_batch(batch)
        lib.retro_set_input_poll(poll)
        lib.retro_set_input_state(state)
        lib.retro_init()
        info = SystemInfo()
        lib.retro_get_system_info(C.byref(info))
        data = rom.read_bytes()
        rombuf = C.create_string_buffer(data, len(data))
        path = str(rom).encode()
        self._keep += [rombuf, path]
        game = GameInfo(path, C.cast(rombuf, C.c_void_p), len(data), None)
        loaded = bool(lib.retro_load_game(C.byref(game)))
        if loaded:
            av = AVInfo()
            lib.retro_get_system_av_info(C.byref(av))
            lib.retro_set_controller_port_device(0, DEVICE_JOYPAD)
        return {
            "loaded": loaded,
            "core": (info.library_name or b"?").decode(errors="replace"),
            "core_version": (info.library_version or b"?").decode(errors="replace"),
        }

    def run(self, frames: int) -> None:
        for _ in range(frames):
            self.lib.retro_run()

    def signature(self, system: str) -> list[int] | None:
        ptr = self.lib.retro_get_memory_data(MEMORY_SYSTEM_RAM)
        size = self.lib.retro_get_memory_size(MEMORY_SYSTEM_RAM)
        off = SIGNATURE_OFFSET[system]
        if not ptr or size < off + 4:
            return None
        return list(C.string_at(ptr + off, 4))

    def close(self) -> None:
        self.lib.retro_unload_game()
        self.lib.retro_deinit()


def frame_stats(frame: tuple[bytes, int, int, int] | None, fmt: int) -> dict:
    if not frame:
        return {"width": 0, "height": 0, "colors": 0, "nonblack": 0.0}
    buf, width, height, pitch = frame
    bpp, code, mask = (4, "I", 0xFFFFFF) if fmt == 1 else (2, "H", 0x7FFF if fmt == 0 else 0xFFFF)
    colors: set[int] = set()
    nonblack = 0
    for y in range(height):
        row = memoryview(buf[y * pitch : y * pitch + width * bpp]).cast(code)
        for px in row:
            px &= mask
            colors.add(px)
            nonblack += px != 0
    total = max(1, width * height)
    return {"width": width, "height": height, "colors": len(colors), "nonblack": nonblack / total}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", type=Path, required=True)
    ap.add_argument("--rom", type=Path, required=True)
    ap.add_argument("--system", choices=sorted(SIGNATURE_OFFSET), required=True)
    ap.add_argument("--boot-frames", type=int, default=180)
    ap.add_argument("--press-frames", type=int, default=10)
    ap.add_argument("--after-frames", type=int, default=180)
    args = ap.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="rb-harness-", ignore_cleanup_errors=True) as work:
        fe = Frontend(args.core.resolve(), Path(work))
        result = fe.load(args.rom.resolve())
        if result["loaded"]:
            fe.run(args.boot_frames)
            result["sig_boot"] = fe.signature(args.system)
            fe.start_down = True
            fe.run(args.press_frames)
            fe.start_down = False
            fe.run(args.after_frames)
            result["sig_after_start"] = fe.signature(args.system)
            result["frames_drawn"] = fe.frames_drawn
            result["frame"] = frame_stats(fe.frame, fe.pixel_format)
            fe.close()
    print("RESULT " + json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
