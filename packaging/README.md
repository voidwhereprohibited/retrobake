# Packaging

`packaging/build.py` is the single entry point (CI's `package` job runs it on both systems):

```sh
pip install --require-hashes -r requirements/runtime.txt && pip install --no-deps --no-build-isolation -e . && pip install --require-hashes -r packaging/requirements.txt
bash tools/build_cc65.sh toolchains/cc65        # bundled ca65 + ld65 (zlib license)
python packaging/build.py                       # -> dist/ + dist/SHA256SUMS
```

- **Windows:** PyInstaller folder (no console window) -> Inno Setup 6 installer,
  `RetroBake-Setup-<version>.exe` (`windows/retrobake.iss`, per-user, no admin prompt).
- **Linux:** the same PyInstaller folder in an AppDir -> `RetroBake-<version>-x86_64.AppImage`.
  appimagetool 1.9.1 and the type2 runtime are downloaded from fixed releases and checked
  against pinned SHA-256s.
- The bundle carries `templates/`, `third_party/` (with its notices), the GPL `LICENSE` and
  `toolchains/cc65/{bin,LICENSE}`.
- `RetroBake --self-test` bakes a sample NES game with the bundled tools and exits.

SNES bundling (wla-dx) and code signing aren't done yet.
