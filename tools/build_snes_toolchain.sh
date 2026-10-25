#!/usr/bin/env bash
# Build the SNES assembler + linker (wla-65816, wlalink) that RetroBake bundles.
# Uses the exact WLA-DX commit that PVSnesLib 4.6.0 pins as its compiler/wla-dx submodule,
# so RetroBake's SNES tools match the PVSnesLib toolchain. Runs on Linux (CI or a clean VM).
# Builds native Linux tools and, with mingw-w64 installed, static Windows .exe tools too.
#
#   tools/build_snes_toolchain.sh [out_dir]     (default: toolchains/pvsneslib)
#   -> out_dir/linux/bin/{wla-65816,wlalink}  out_dir/windows/bin/{wla-65816,wlalink}.exe
#      out_dir/LICENSE (WLA-DX, GPL-2.0-or-later)  out_dir/COMMIT
set -euo pipefail

PVSNESLIB_TAG="4.6.0"                                       # alekmaul/pvsneslib release
WLA_REPO="https://github.com/vhelin/wla-dx.git"
WLA_COMMIT="6fa1f673f010e4fa4571c40929019cd7e67d1bbd"       # pvsneslib 4.6.0 compiler/wla-dx
OUT="$(realpath -m "${1:-toolchains/pvsneslib}")"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git -C "$WORK" init -q src
git -C "$WORK/src" fetch -q --depth 1 "$WLA_REPO" "$WLA_COMMIT"
git -C "$WORK/src" checkout -q FETCH_HEAD
test "$(git -C "$WORK/src" rev-parse HEAD)" = "$WLA_COMMIT"

TARGETS=(wla-65816 wlalink)

cmake -S "$WORK/src" -B "$WORK/linux" -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build "$WORK/linux" -j"$(nproc)" --target "${TARGETS[@]}" gen-65816 >/dev/null
mkdir -p "$OUT/linux/bin"
for t in "${TARGETS[@]}"; do
    install -m 755 "$WORK/linux/binaries/$t" "$OUT/linux/bin/$t"
    strip "$OUT/linux/bin/$t"
done

if command -v x86_64-w64-mingw32-gcc >/dev/null; then
    # Cross build reuses the native instruction-table generators from the Linux build.
    cmake -S "$WORK/src" -B "$WORK/windows" -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_SYSTEM_NAME=Windows -DCMAKE_C_COMPILER=x86_64-w64-mingw32-gcc \
        -DCMAKE_EXE_LINKER_FLAGS=-static \
        -DIMPORT_GENERATORS="$WORK/linux/ImportGenerators.cmake" >/dev/null
    cmake --build "$WORK/windows" -j"$(nproc)" --target "${TARGETS[@]}" >/dev/null
    mkdir -p "$OUT/windows/bin"
    for t in "${TARGETS[@]}"; do
        cp "$WORK/windows/binaries/$t.exe" "$OUT/windows/bin/$t.exe"
        x86_64-w64-mingw32-strip "$OUT/windows/bin/$t.exe"
    done
fi

cp "$WORK/src/LICENSE" "$OUT/LICENSE"
printf 'wla-dx %s (pvsneslib %s)\n' "$WLA_COMMIT" "$PVSNESLIB_TAG" > "$OUT/COMMIT"
ls -l "$OUT"/*/bin
