# Packaging

Owned by the release agent. Filled in at milestone M6.

- `windows/` - PyInstaller build + Inno Setup installer script (`RetroBake-Setup-<version>.exe`), bundled cc65 + PVSnesLib toolchains, no terminal window.
- `linux/` - PyInstaller build packed as an AppImage (`RetroBake-<version>-x86_64.AppImage`). Flatpak later.
- `build.py` - single entry point CI calls on both platforms.

Every release ships SHA-256 checksums and signatures, and the installer size is tracked per release to keep RetroBake lightweight.
