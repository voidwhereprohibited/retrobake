# RetroBake agent board (snapshot)

## Tasks
| id | agent | state | title | note |
|---|---|---|---|---|
| 1 | theme-art | done | 15 theme style contact sheets | 10 personal themes from Roger's own wallpapers built in ~/Pictures/RetroBake-Themes (<id>/wallpapers 4K+1920x1200+1920x1080, <id>/icons full XMB set from community packs: 16X, PS3, BAXY, sysdaite, retroarch-assets). Previews _previews/ALL.jpg. Personal only, not in repo. Next: Roger picks; retroarch task 2 installs. |
| 2 | retroarch | done | Themes: 'Use my own wallpapers' option | Superseded by tasks 3-5 (Theme Studio) |
| 3 | theme-art | done | Theme Studio engine: photo -> pack | Engine done per 11/01 handoff: src/retrobake/themes/studio.py (photo -> full pack, local analysis, no AI) |
| 4 | retroarch | todo | Theme installer + RetroArch auto-setup |  |
| 5 | wizard-ui | todo | Theme Studio screen |  |
| 6 | qa | todo | Test Theme Studio end to end |  |
| 7 | theme-art | blocked | Original retro-neon 4K dynamic wallpapers for every system + tab - NO AI | Paused by Roger 11/03: Rick and Morty personal pack took priority |
| 8 | release | todo | Publish wallpaper Releases + README previews |  |
| 9 | retroarch | doing | Install Roger's icon picks into RetroArch | Step 1: sent Roger OPTIONS sheets (rainbow-pad, wolverine, neon-chase, teal-arcade), waiting for his A-F pick per theme |
| 10 | icon-art | done | Rick and Morty XMB icons: research + 20 icons x 5 options | Icons done 11/03: ~/Pictures/RetroBake-Themes/_rick-morty/icons/final (zip + png + full-set.jpg); copied to ~/.config/retroarch/assets/xmb/custom (859 png). xmb_theme still 0 in retroarch.cfg. |
| 11 | theme-art | todo | Rick and Morty dynamic wallpapers from Roger's 5 folder pictures + install (pending Roger's yes) |  |

## Decisions
| topic | decision | by |
|---|---|---|
| theme art generator | Pollinations gen.pollinations.ai with a free account secret key (stored only in ~/.config/retrobake/pollinations.key, chmod 600, never committed), model tongyi-mai/z-image-turbo (free, 60 rpm) at 1920x1080, fixed seed per style; Real-ESRGAN ncnn-vulkan x4plus v0.2.5.0 (sha256 e5aa6eb1...0c96) to 4K. Keyless Classic API rejected: only 'sana' at 1024x576, 1 img/45s, forced watermark, muddy output - fails Roger's quality bar. | theme-art |
| theme styles | 15 preview styles in themes/styles.json: sunny-platformer, neon-arcade, dungeon-torchlight, space-shooter, underwater-reef, racing-sunset, rpg-overworld, snow-level, lava-castle, boxart-90s, haunted-mansion, candy-land, jungle-temple, sky-airships, crystal-cave | theme-art |
| Icon background keying | Sample each icon cell's border colour and flood-fill from the edges (tol 95) + tight global pass (tol 40) + 1px choke; Pollinations returns hot pink, not pure #FF00FF | theme-art |
| Theme icons come from open packs, not generated | Per Roger: no self-made icons. Use libretro/retroarch-assets XMB packs (CC-BY 4.0) recolored per wallpaper (tint/gradient/glow/outline/shadow) via tools/theme_art/build_themes.py; full XMB name coverage via primary+fallback pack | theme-art |
| RetroBake Theme Studio | App feature: user picks a prebuilt pack (GitHub releases of retroarch-dynamic-wallpapers-retrobake) OR uploads their own photo(s); engine builds a full XMB dynamic-wallpaper pack (every tab incl. Contentless Cores + every playlist name), styled lettering top-left, matching icon set chosen+recolored from bundled open packs; preview in XMB layout; one click installs and configures RetroArch (backup cfg, wallpapers, xmb custom icons, thumbnails, title header off) with Restore. User photos never leave their PC. | theme-art |
| No AI | Roger 11/01: drop AI entirely. Wallpaper art is drawn in code only (no Pollinations, no AI models). RetroBake cover art uses the offline pixel-art generator only. Supersedes the Pollinations decisions. | orchestrator |

## Contracts
| name | owner | spec |
|---|---|---|
| theme folder layout | theme-art | themes/<style-id>/wallpapers/{master_3840x2160,1920x1200,1920x1080}.png; themes/<style-id>/icons/<exact XMB name>.png 256x256 RGBA (names per docs/themes/xmb_icon_names.txt); previews themes/_previews/<style-id>.png 1920x1200. Generator: tools/theme_art/make_previews.py |
