; RetroBake settings for the vendored FamiStudio sound engine (original RetroBake file).
; The engine source (famistudio_ca65.s) is used unchanged, under its own notice.

FAMISTUDIO_CFG_EXTERNAL          = 1
.define FAMISTUDIO_CA65_ZP_SEGMENT   ZEROPAGE
.define FAMISTUDIO_CA65_RAM_SEGMENT  BSS
.define FAMISTUDIO_CA65_CODE_SEGMENT CODE

FAMISTUDIO_CFG_NTSC_SUPPORT      = 1
FAMISTUDIO_USE_FAMITRACKER_TEMPO = 1

.include "famistudio_ca65.s"
