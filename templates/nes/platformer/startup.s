; RetroBake NES start-up code and neslib glue (original RetroBake file).
; Defines the hardware constants and zero-page variables the vendored nesdoug copy of neslib
; expects, includes neslib + nesdoug unchanged, maps neslib's music calls onto the FamiStudio
; engine, sets the machine up and jumps to the game.

.import _main, music_data
.import famistudio_init, famistudio_update, famistudio_music_play
.import famistudio_music_stop, famistudio_music_pause
.export popa, popax
.exportzp sp

; ---------------------------------------------------------------- hardware
PPU_CTRL     = $2000
PPU_MASK     = $2001
PPU_STATUS   = $2002
PPU_OAM_ADDR = $2003
PPU_OAM_DATA = $2004
PPU_SCROLL   = $2005
PPU_ADDR     = $2006
PPU_DATA     = $2007
PPU_OAM_DMA  = $4014
PPU_FRAMECNT = $4017
DMC_FREQ     = $4010
CTRL_PORT1   = $4016
CTRL_PORT2   = $4017

OAM_BUF      = $0200
PAL_BUF      = $01C0
VRAM_BUF     = $0700
CSTACK_TOP   = $0700

FT_SFX_ENABLE  = 0
FT_DPCM_ENABLE = 0

; ---------------------------------------------------------------- neslib variables
.segment "ZEROPAGE"
sp:              .res 2   ; software argument stack used by neslib's multi-argument calls
NTSC_MODE:       .res 1
FRAME_CNT1:      .res 1
FRAME_CNT2:      .res 1
VRAM_UPDATE:     .res 1
NAME_UPD_ADR:    .res 2
NAME_UPD_ENABLE: .res 1
PAL_UPDATE:      .res 1
PAL_BG_PTR:      .res 2
PAL_SPR_PTR:     .res 2
SCROLL_X:        .res 1
SCROLL_Y:        .res 1
SCROLL_X1:       .res 1
SCROLL_Y1:       .res 1
PAD_STATE:       .res 2
PAD_STATEP:      .res 2
PAD_STATET:      .res 2
PPU_CTRL_VAR:    .res 1
PPU_CTRL_VAR1:   .res 1
PPU_MASK_VAR:    .res 1
RAND_SEED:       .res 2
FT_TEMP:         .res 3
TEMP:            .res 11
SPRID:           .res 1
VRAM_INDEX:      .res 1
META_PTR:        .res 2
DATA_PTR:        .res 2

PAD_BUF  = TEMP+1
PTR      = TEMP
LEN      = TEMP+2
NEXTSPR  = TEMP+4
SCRX     = TEMP+5
SCRY     = TEMP+6
SRC      = TEMP+7
DST      = TEMP+9
RLE_LOW  = TEMP
RLE_HIGH = TEMP+1
RLE_TAG  = TEMP+2
RLE_BYTE = TEMP+3

.segment "BSS"
FT_SONG_SPEED:   .res 1   ; nesdoug's set_music_speed writes here; FamiStudio keeps its own speed

; ---------------------------------------------------------------- header
.segment "HEADER"
    .byte "NES", $1A
    .byte 2                  ; 2 x 16 KB PRG
    .byte 1                  ; 1 x 8 KB CHR
    .byte $01                ; mapper 0, vertical mirroring
    .byte $00
    .res 8, $00

; ---------------------------------------------------------------- code
.segment "CODE"

; neslib calls these FamiTone2 names; RetroBake plays music with FamiStudio instead.
FamiToneUpdate:     jmp famistudio_update
FamiToneMusicPlay:  jmp famistudio_music_play
FamiToneMusicStop:  jmp famistudio_music_stop
FamiToneMusicPause: jmp famistudio_music_pause

; Pop one byte / one 16-bit value (A = low, X = high) off the software argument stack.
popa:
    ldy #0
    lda (sp),y
    inc sp
    bne :+
    inc sp+1
:   rts

popax:
    ldy #1
    lda (sp),y
    tax
    dey
    lda (sp),y
    inc sp
    bne :+
    inc sp+1
:   inc sp
    bne :+
    inc sp+1
:   rts

.include "neslib.s"
.include "nesdoug.s"

reset:
    sei
    cld
    ldx #$40
    stx PPU_FRAMECNT         ; no APU frame IRQ
    ldx #$BF
    txs                      ; hardware stack stays below neslib's palette buffer
    lda #0
    sta PPU_CTRL
    sta PPU_MASK
    sta DMC_FREQ
    bit PPU_STATUS
@vblank1:
    bit PPU_STATUS
    bpl @vblank1

    lda #0                   ; clear all RAM
    tax
@clear_ram:
    sta $0000,x
    sta $0100,x
    sta $0200,x
    sta $0300,x
    sta $0400,x
    sta $0500,x
    sta $0600,x
    sta $0700,x
    inx
    bne @clear_ram

@vblank2:
    bit PPU_STATUS
    bpl @vblank2

    lda #$20                 ; clear both nametables
    sta PPU_ADDR
    lda #$00
    sta PPU_ADDR
    ldy #8
    tax
@clear_vram:
    sta PPU_DATA
    inx
    bne @clear_vram
    dey
    bne @clear_vram

    lda #4
    jsr _pal_bright          ; normal brightness: sets neslib's palette pointers
    jsr _pal_clear
    jsr _oam_clear

    lda #<CSTACK_TOP
    sta sp
    lda #>CSTACK_TOP
    sta sp+1

    ldx #<music_data
    ldy #>music_data
    lda #1                   ; NTSC
    jsr famistudio_init
    lda #0
    jsr famistudio_music_play

    lda #%10001000           ; NMI on, background $0000, sprites $1000
    sta <PPU_CTRL_VAR
    sta PPU_CTRL
    lda #%00000110
    sta <PPU_MASK_VAR
    jmp _main

.segment "VECTORS"
    .addr nmi, reset, irq

.segment "CHARS"
    .incbin "game.chr"       ; written by the builder (RetroBake placeholder art)
