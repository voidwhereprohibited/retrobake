#!/usr/bin/env bash
# Build the cc65 assembler + linker (ca65, ld65) that RetroBake bundles.
# Runs on Linux (CI or a clean VM). Builds native Linux tools and, with mingw-w64
# installed, Windows .exe tools too. Pinned to one cc65 commit for repeatable builds.
#
#   tools/build_cc65.sh [out_dir]     (default: toolchains/cc65)
#   -> out_dir/linux/bin/{ca65,ld65}   out_dir/windows/bin/{ca65,ld65}.exe   out_dir/LICENSE
set -euo pipefail

CC65_REPO="https://github.com/cc65/cc65.git"
CC65_COMMIT="5725066bfb86cdb52c8f4afb94b6401cb320cb21"   # master, 2026-10-25
OUT="$(realpath -m "${1:-toolchains/cc65}")"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git -C "$WORK" init -q src
git -C "$WORK/src" fetch -q --depth 1 "$CC65_REPO" "$CC65_COMMIT"
git -C "$WORK/src" checkout -q FETCH_HEAD
test "$(git -C "$WORK/src" rev-parse HEAD)" = "$CC65_COMMIT"

copy_tools() {  # $1 = platform folder, $2 = exe suffix
    mkdir -p "$OUT/$1/bin"
    for t in ca65 ld65; do
        f="$WORK/src/bin/$t$2"
        [ -f "$f" ] || f="$WORK/src/bin/$t"
        cp "$f" "$OUT/$1/bin/$t$2"
    done
}

make -C "$WORK/src/src" -j"$(nproc)" ca65 ld65 >/dev/null
strip "$WORK/src/bin/ca65" "$WORK/src/bin/ld65"
copy_tools linux ""

if command -v x86_64-w64-mingw32-gcc >/dev/null; then
    make -C "$WORK/src/src" clean >/dev/null
    rm -f "$WORK/src/bin/"*
    make -C "$WORK/src/src" -j"$(nproc)" ca65 ld65 CROSS_COMPILE=x86_64-w64-mingw32- \
        USER_LDFLAGS=-static >/dev/null
    x86_64-w64-mingw32-strip "$WORK/src/bin/"*
    copy_tools windows ".exe"
fi

cp "$WORK/src/LICENSE" "$OUT/LICENSE"
echo "$CC65_COMMIT" > "$OUT/COMMIT"
ls -l "$OUT"/*/bin
