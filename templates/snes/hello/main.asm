; RetroBake SNES "hello" engine (M1). 32 KB LoROM, SlowROM, NTSC.
; Title screen: game title, "PRESS START", credit line, on a dark blue backdrop.
; Start -> "gameplay" (backdrop turns dark green). Publishes the qa boot signature
; "RB" v1 at WRAM $7E:1FFC-$1FFF (state 1 title, 2 gameplay).
;
; This file is a fixed template. The builder never writes code: it only drops in
;   text.bin  - text records: [len, vram_lo, vram_hi, tile...]..., ended by a 0 byte
;   font.bin  - 2bpp tiles (RetroBake's own original 5x7 font)
; User text reaches the ROM only as tile numbers inside text.bin (and, after linking,
; as the plain-ASCII internal header name the builder patches in with a new checksum).

.MEMORYMAP
    SLOTSIZE $8000
    DEFAULTSLOT 0
    SLOT 0 $8000
.ENDME

.ROMBANKSIZE $8000
.ROMBANKS 1

.SNESHEADER
    NAME "RETROBAKE GAME       "
    LOROM
    SLOWROM
    CARTRIDGETYPE $00
    ROMSIZE $05
    SRAMSIZE $00
    COUNTRY $01
    LICENSEECODE $00
    VERSION $00
.ENDSNES

.SNESNATIVEVECTOR
    COP Idle
    BRK Idle
    ABORT Idle
    NMI Idle
    IRQ Idle
.ENDNATIVEVECTOR

.SNESEMUVECTOR
    COP Idle
    ABORT Idle
    NMI Idle
    RESET Reset
    IRQBRK Idle
.ENDEMUVECTOR

.COMPUTESNESCHECKSUM

.DEFINE COUNT   $00          ; direct-page scratch byte
.DEFINE SIG     $1FFC        ; boot signature (qa contract rom-boot-signature)
.DEFINE STATE   $1FFF
.DEFINE MAP_VRAM $0400       ; BG1 tilemap word address (32x32)

.BANK 0 SLOT 0
.ORG 0
.SECTION "Engine" FORCE

Reset:
    sei
    clc
    xce                     ; native 65816 mode
    rep #$38                ; 16-bit A/X/Y, binary mode
.ACCU 16
.INDEX 16
    ldx #$1EFF              ; stack below the boot signature
    txs
    lda #$0000
    tcd                     ; direct page = $0000

    ldx #$0000              ; clear low WRAM $0000-$1FFF
ClearWram:
    stz $0000,x
    inx
    inx
    cpx #$2000
    bne ClearWram

    sep #$20
.ACCU 8
    phk
    plb                     ; data bank = program bank (0)
    lda #$80
    sta $2100               ; force blank
    stz $4200               ; NMI, IRQ, auto-read off

    ldx #$2101              ; zero PPU registers $2101-$210C
ClearPpu1:
    stz $0000,x
    inx
    cpx #$210D
    bne ClearPpu1
ClearScroll:                ; scroll registers $210D-$2114 take two writes each
    stz $0000,x
    stz $0000,x
    inx
    cpx #$2115
    bne ClearScroll
    ldx #$2123              ; windows, layers, colour math $2123-$2133
ClearPpu2:
    stz $0000,x
    inx
    cpx #$2134
    bne ClearPpu2
    lda #$30
    sta $2130               ; colour math off
    lda #$E0
    sta $2132               ; fixed colour = black
    lda #$FF
    sta $4201
    ldx #$4202              ; CPU I/O $4202-$420D
ClearCpu:
    stz $0000,x
    inx
    cpx #$420E
    bne ClearCpu

    ; clear all 64 KB of VRAM: DMA ch0, fixed source byte 0 -> $2118/$2119
    lda #$80
    sta $2115               ; VRAM +1 word after high byte
    ldx #$0000
    stx $2116
    lda #$09
    sta $4300
    lda #$18
    sta $4301
    ldx #ZeroByte
    stx $4302
    stz $4304
    ldx #$0000
    stx $4305               ; 0 = 65536 bytes
    lda #$01
    sta $420B

    ; font tiles -> VRAM word $0000
    ldx #$0000
    stx $2116
    lda #$01
    sta $4300               ; two registers, incrementing source
    ldx #FontData
    stx $4302
    stz $4304
    ldx #FontEnd-FontData
    stx $4305
    lda #$01
    sta $420B

    ; palette 0: backdrop, white, light grey, grey
    stz $2121
    ldx #$0000
LoadPalette:
    lda Palette,x
    sta $2122
    inx
    cpx #8
    bne LoadPalette

    ; text records -> BG1 tilemap
    ldx #$0000
NextRecord:
    lda TextData,x          ; length, 0 = end
    beq TextDone
    sta COUNT
    inx
    lda TextData,x
    sta $2116
    inx
    lda TextData,x
    sta $2117
    inx
PutTile:
    lda TextData,x
    sta $2118
    stz $2119               ; palette 0, no flip, low priority
    inx
    dec COUNT
    bne PutTile
    bra NextRecord
TextDone:

    ; mode 0, BG1 = text layer
    stz $2105               ; BG mode 0, 8x8 tiles
    lda #(MAP_VRAM >> 8)
    sta $2107               ; BG1 map at $0400, 32x32
    stz $210B               ; BG1/2 tiles at $0000
    lda #$01
    sta $212C               ; main screen: BG1

    ; boot signature "RB" v1, state 1 (title)
    lda #$52
    sta SIG
    lda #$42
    sta SIG+1
    lda #$01
    sta SIG+2
    sta STATE

    lda #$01
    sta $4200               ; joypad auto-read on (no NMI)
    lda #$0F
    sta $2100               ; screen on, full brightness

MainLoop:
WaitVblank:
    lda $4212
    bpl WaitVblank
WaitJoypad:
    lda $4212
    and #$01
    bne WaitJoypad
    lda $4219               ; JOY1 high byte: B Y Select Start Up Down Left Right
    and #$10
    beq EndFrame
    lda STATE
    cmp #$02
    beq EndFrame
    lda #$02
    sta STATE               ; Start pressed: title -> gameplay
    stz $2121
    lda GameplayColor
    sta $2122
    lda GameplayColor+1
    sta $2122
EndFrame:
    lda $4212
    bmi EndFrame            ; wait for vblank to end
    bra MainLoop

Idle:
    rti

ZeroByte:
    .DB $00
Palette:                    ; BGR555: dark blue, white, light grey, grey
    .DW $2C40, $7FFF, $5AD6, $3DEF
GameplayColor:
    .DW $0560               ; dark green
TextData:
    .INCBIN "text.bin"
FontData:
    .INCBIN "font.bin"
FontEnd:

.ENDS
