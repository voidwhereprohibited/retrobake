; RetroBake NES "hello" engine (M1). NROM-128: 16 KB PRG + 8 KB CHR, vertical mirroring.
; Shows the game title and a credit line on a plain background, then idles.
;
; This file is a fixed template. The builder never writes code: it only drops in
;   text.bin  - text records: [addr_hi, addr_lo, len, tile...]..., ended by a 0 byte
;   font.chr  - 8 KB pattern table (RetroBake's own original 5x7 font)
; User text reaches the ROM only as tile numbers inside text.bin.

PPUCTRL   = $2000
PPUMASK   = $2001
PPUSTATUS = $2002
PPUSCROLL = $2005
PPUADDR   = $2006
PPUDATA   = $2007
DMC_FREQ  = $4010
APU_FRAME = $4017

.segment "HEADER"
    .byte "NES", $1A
    .byte 1             ; 1 x 16 KB PRG-ROM
    .byte 1             ; 1 x 8 KB CHR-ROM
    .byte $01           ; mapper 0 (NROM), vertical mirroring
    .byte $00
    .res 8, $00

.segment "ZEROPAGE"
ptr: .res 2

.segment "CODE"

.proc reset
    sei
    cld
    ldx #$40
    stx APU_FRAME       ; no APU frame IRQ
    ldx #$FF
    txs
    inx                 ; X = 0
    stx PPUCTRL         ; no NMI
    stx PPUMASK         ; rendering off
    stx DMC_FREQ        ; no DMC IRQ
    bit PPUSTATUS
vblank1:
    bit PPUSTATUS
    bpl vblank1

    txa                 ; A = 0, clear all 2 KB of RAM
clear_ram:
    sta $0000,x
    sta $0100,x
    sta $0200,x
    sta $0300,x
    sta $0400,x
    sta $0500,x
    sta $0600,x
    sta $0700,x
    inx
    bne clear_ram

vblank2:
    bit PPUSTATUS
    bpl vblank2

    ; palettes ($3F00-$3F1F)
    lda #$3F
    sta PPUADDR
    lda #$00
    sta PPUADDR
    ldx #0
load_palette:
    lda palette,x
    sta PPUDATA
    inx
    cpx #32
    bne load_palette

    ; blank nametable 0 and its attributes ($2000-$23FF)
    lda #$20
    sta PPUADDR
    lda #$00
    sta PPUADDR
    ldy #4
    ldx #0
clear_nt:
    sta PPUDATA
    inx
    bne clear_nt
    dey
    bne clear_nt

    ; draw text records
    lda #<text_data
    sta ptr
    lda #>text_data
    sta ptr+1
next_record:
    ldy #0
    lda (ptr),y         ; address high byte, 0 = end
    beq text_done
    sta PPUADDR
    iny
    lda (ptr),y
    sta PPUADDR
    iny
    lda (ptr),y         ; length (1-32)
    tax
    iny
put_tile:
    lda (ptr),y
    sta PPUDATA
    iny
    dex
    bne put_tile
    tya                 ; move ptr past this record
    clc
    adc ptr
    sta ptr
    bcc next_record
    inc ptr+1
    jmp next_record
text_done:

    ; turn the screen on at the start of a frame
vblank3:
    bit PPUSTATUS
    bpl vblank3
    lda #$00
    sta PPUSCROLL
    sta PPUSCROLL
    sta PPUCTRL         ; background tiles from $0000
    lda #%00001010      ; show background, including the left 8 pixels
    sta PPUMASK
forever:
    jmp forever
.endproc

.proc nmi
    rti
.endproc

.proc irq
    rti
.endproc

.segment "RODATA"
palette:
    .byte $0F,$30,$10,$00, $0F,$30,$10,$00, $0F,$30,$10,$00, $0F,$30,$10,$00
    .byte $0F,$30,$10,$00, $0F,$30,$10,$00, $0F,$30,$10,$00, $0F,$30,$10,$00
text_data:
    .incbin "text.bin"

.segment "VECTORS"
    .addr nmi, reset, irq

.segment "CHARS"
    .incbin "font.chr"
