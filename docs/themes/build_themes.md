# Build a RetroArch theme from your own wallpapers

`tools/theme_art/build_themes.py` turns pictures the user already has into full XMB themes.
It never draws icons: it takes the open XMB icon packs from libretro/retroarch-assets
(CC-BY 4.0) and recolors them to match each wallpaper. This is the engine behind the
"Use my own pictures" option (retroarch task 2).

## Input: themes.json
```json
{
  "icon_root": "_src/ra/xmb",
  "themes": [
    {"id": "synthwave", "name": "Synthwave Drive", "wallpaper": "~/Downloads/x.jpg",
     "pack": "automatic", "fallback": "monochrome",
     "fx": {"tint": ["#ffb13b", "#ff2fa0"], "glow": "#ff3d7f"}}
  ]
}
```
- `pack` / `fallback`: retroarch-assets XMB pack names. Every icon name in either pack is produced, primary first.
- `fx`: `tint` (1 color, or 2 for a top-to-bottom gradient; recolors white/mono icons), `glow` (+ `glow_strength`),
  `outline` (+ `outline_px`), `shadow`.

## Output (next to themes.json)
- `<id>/wallpapers/master_3840x2160.png`, `1920x1200.png`, `1920x1080.png` (Real-ESRGAN x4 when the source is under 4K)
- `<id>/icons/<XMB name>.png` 256x256 RGBA
- `_previews/<id>.png` 1920x1200 contact sheet

## Rules
- User-supplied wallpapers stay on the user's machine. RetroBake never bundles or downloads third-party wallpapers.
- Keep a CREDITS file with the theme: the icon packs are CC-BY 4.0 and require attribution.
