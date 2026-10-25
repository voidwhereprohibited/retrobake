; RetroBake SNES platformer engine (M2). 128 KB LoROM, SlowROM, NTSC, no SRAM.
;
; This file is a fixed template: the builder never writes code. It only drops in data files
; made from the game-spec (see docs/snes-builder.md):
;   text.bin      title screen text records [len, off_lo, off_hi, tile...]... 0  (BG3 offsets)
;   config.bin    16 bytes: combat, extras flags, start lives, start hearts, ...
;   ascii.bin     128 bytes ASCII -> font tile (for this engine's own fixed messages)
;   levels.bin    the "RBLV" level pack from retrobake.spec.platformer (contract level-data)
;   objtiles.bin  objpal.bin  hudtiles.bin  hudpal.bin  bg2map.bin  settings.bin  (art)
; User text reaches the ROM only as tile numbers inside text.bin.
;
; Mode 1: BG1 = level (16x16 tiles, 4bpp), BG2 = parallax backdrop (16x16, 4bpp),
;         BG3 = HUD + messages (8x8, 2bpp, high priority). HDMA paints the sky gradient.
; qa boot signature "RB" v1 at WRAM $7E:1FFC (state 1 title, 2 gameplay).
; Debug probe for tests at WRAM $7E:1FF0-$1FFB (see docs/snes-builder.md).

.MEMORYMAP
    SLOTSIZE $8000
    DEFAULTSLOT 0
    SLOT 0 $8000
.ENDME

.ROMBANKSIZE $8000
.ROMBANKS 4

.SNESHEADER
    NAME "RETROBAKE GAME       "
    LOROM
    SLOWROM
    CARTRIDGETYPE $00
    ROMSIZE $07
    SRAMSIZE $00
    COUNTRY $01
    LICENSEECODE $00
    VERSION $00
.ENDSNES

.SNESNATIVEVECTOR
    COP Idle
    BRK Idle
    ABORT Idle
    NMI NmiHandler
    IRQ Idle
.ENDNATIVEVECTOR

.SNESEMUVECTOR
    COP Idle
    ABORT Idle
    NMI Idle
    RESET Reset
    IRQBRK Idle
.ENDEMUVECTOR


; ------------------------------------------------------------------ constants
.DEFINE BG1MAP   $1000
.DEFINE BG2MAP   $1400
.DEFINE BG3MAP   $1800
.DEFINE BG3CHR   $2000
.DEFINE OBJCHR   $4000
.DEFINE MAPRAM   $7E2000        ; level map: index = column*16 + row (4 KB)

.DEFINE OAM      $0200          ; 544 bytes
.DEFINE BG3BUF   $0500          ; 32x32 words = 2 KB ($0500-$0CFF)
.DEFINE OBJKIND  $0D00          ; 96 bytes each
.DEFINE OBJX     $0D60
.DEFINE OBJY     $0DC0
.DEFINE OBJST    $0E20          ; 0 dormant, 1 active, 2 gone
.DEFINE COLBUF   $0E80          ; 12 words
.DEFINE COLTMP   $0EA0          ; 16 bytes
.DEFINE E_KIND   $0F00          ; entity slots: 12 words each, index X = slot*2
.DEFINE E_SRC    $0F18
.DEFINE E_X      $0F30
.DEFINE E_Y      $0F48
.DEFINE E_VX     $0F60
.DEFINE E_VY     $0F78
.DEFINE E_TIMER  $0F90
.DEFINE E_DIR    $0FA8
.DEFINE E_HP     $0FC0
.DEFINE E_HURT   $0FD8
.DEFINE E_BASEY  $0FF0
.DEFINE E_GND    $1008
.DEFINE PROBE    $1FF0
.DEFINE SIG      $1FFC

.DEFINE LEVELPACK $018000
.DEFINE OBJGFX    $028000

.DEFINE NSLOTS   12
.DEFINE NOBJSLOT 10             ; slots 0-9 level objects, 10-11 shots/effects

; object kinds (level-data contract) + engine-only kinds
.DEFINE K_WALKER 1
.DEFINE K_HOPPER 2
.DEFINE K_FLYER  3
.DEFINE K_COIN   4
.DEFINE K_HEART  5
.DEFINE K_LIFE   6
.DEFINE K_KEY    7
.DEFINE K_BOSS   8
.DEFINE K_SHOP   9
.DEFINE K_SHOT   10
.DEFINE K_POOF   11

; config.bin flags
.DEFINE F_HEARTS 1
.DEFINE F_LIVES  2
.DEFINE F_COINS  4
.DEFINE F_SCORE  8
.DEFINE F_TIMER  16
.DEFINE F_SHOP   32

.DEFINE C_STOMP  0
.DEFINE C_MELEE  1
.DEFINE C_SHOOT  2
.DEFINE C_NONE   3

; joypad bits ($4218 as a word)
.DEFINE J_B      $8000
.DEFINE J_Y      $4000
.DEFINE J_START  $1000
.DEFINE J_UP     $0800
.DEFINE J_DOWN   $0400
.DEFINE J_LEFT   $0200
.DEFINE J_RIGHT  $0100
.DEFINE J_A      $0080
.DEFINE J_X      $0040
.DEFINE J_JUMP   $8080
.DEFINE J_ACT    $4040

; physics, in 1/16 pixel units
.DEFINE WALK     28
.DEFINE RUN      40
.DEFINE ACCEL    2
.DEFINE FRICTION 3
.DEFINE JUMPV    78
.DEFINE GRAVHOLD 3
.DEFINE GRAV     8
.DEFINE MAXFALL  96
.DEFINE BOUNCE   64

; game states
.DEFINE S_TITLE  0
.DEFINE S_INTRO  1
.DEFINE S_PLAY   2
.DEFINE S_DYING  3
.DEFINE S_CLEAR  4
.DEFINE S_OVER   5
.DEFINE S_WIN    6

; font tiles (CHARSET " A-Z0-9.,!?'&:-" then icons)
.DEFINE T_ZERO   27
.DEFINE T_HEART  45
.DEFINE T_HEARTE 46
.DEFINE T_GEM    47
.DEFINE T_LIFE   48
.DEFINE T_KEY    49
.DEFINE T_TIMES  50

.ENUM $00
tmp0      DW
tmp1      DW
tmp2      DW
tmp3      DW
tmp4      DW
tmp5      DW
tmp6      DW
tmp7      DW
ptr       DS 3
ptr2      DS 3
nmiReady  DB
nmiDone   DB
frame     DW
joy       DW
joyPrev   DW
joyNew    DW
gstate    DB
gtimer    DW
heroX     DW
heroY     DW
heroVX    DW
heroVY    DW
heroGnd   DB
heroFace  DB
heroInv   DB
heroAtk   DB
coyote    DB
jumpBuf   DB
camX      DW
leftCol   DW
colPend   DW
redrawCol DW
redrawN   DB
lvl       DB
lvlCount  DB
lvlWidth  DW
lvlCols   DW
setting   DB
objCount  DB
lives     DB
hearts    DB
coins     DB
score     DS 3
timeBCD   DW
timeFr    DB
hasKey    DB
bossDead  DB
bossLvl   DB
goalX     DW
goalY     DW
startX    DW
startY    DW
hudDirty  DB
txtDirty  DB
oamIdx    DW
combat    DB
flags     DB
startLives DB
startHearts DB
paused    DB
spikeHit  DB
px        DW
py        DW
slot      DW
ex        DW
ey        DW
ew        DW
oldFeet   DW
shopHint  DB
hscroll2  DW
.ENDE

.MACRO A8
    sep #$20
.ACCU 8
.ENDM
.MACRO A16
    rep #$20
.ACCU 16
.ENDM

.BANK 0 SLOT 0
.ORG 0
.SECTION "Engine" FORCE

.ACCU 8
.INDEX 16

; ================================================================== reset / init
Reset:
    sei
    clc
    xce
    rep #$38
.ACCU 16
.INDEX 16
    ldx #$1EFF
    txs
    lda #$0000
    tcd
    ldx #$0000
@clr:
    stz $0000,x
    inx
    inx
    cpx #$2000
    bne @clr
    A8
    phk
    plb
    lda #$80
    sta $2100
    stz $4200
    ldx #$2101
@ppu1:
    stz $0000,x
    inx
    cpx #$210D
    bne @ppu1
@scr:
    stz $0000,x
    stz $0000,x
    inx
    cpx #$2115
    bne @scr
    ldx #$2123
@ppu2:
    stz $0000,x
    inx
    cpx #$2134
    bne @ppu2
    lda #$30
    sta $2130
    lda #$E0
    sta $2132
    lda #$FF
    sta $4201
    ldx #$4202
@cpu:
    stz $0000,x
    inx
    cpx #$420E
    bne @cpu

    ; clear 64 KB VRAM
    lda #$80
    sta $2115
    ldx #$0000
    stx $2116
    lda #$09
    sta $4300
    lda #$18
    sta $4301
    ldx #ZeroWord
    stx $4302
    stz $4304
    ldx #$0000
    stx $4305
    lda #$01
    sta $420B
    ; clear CGRAM
    stz $2121
    lda #$0A
    sta $4300
    lda #$22
    sta $4301
    ldx #ZeroWord
    stx $4302
    stz $4304
    ldx #512
    stx $4305
    lda #$01
    sta $420B

    ; config
    ldx #$0000
@cfg:
    lda ConfigData,x
    sta combat,x
    inx
    cpx #4
    bne @cfg

    jsr LoadCommonGfx
    jsr SetupPpu

    ; boot signature "RB" v1
    lda #$52
    sta SIG
    lda #$42
    sta SIG+1
    lda #$01
    sta SIG+2
    stz SIG+3

    ldx #$FFFF
    stx colPend
    lda #$81
    sta $4200               ; NMI + joypad auto-read
    jmp GoTitle

Idle:
    rti

; ------------------------------------------------------------------ DMA helpers (A8)
; DmaVram: tmp0 = VRAM word address, ptr = 24-bit source, tmp1 = byte count
DmaVram:
    lda #$80
    sta $2115
    ldx tmp0
    stx $2116
    lda #$01
    sta $4300
    lda #$18
    sta $4301
    ldx ptr
    stx $4302
    lda ptr+2
    sta $4304
    ldx tmp1
    stx $4305
    lda #$01
    sta $420B
    rts

; DmaCgram: A = first colour, ptr = source, tmp1 = byte count
DmaCgram:
    sta $2121
    stz $4300
    lda #$22
    sta $4301
    ldx ptr
    stx $4302
    lda ptr+2
    sta $4304
    ldx tmp1
    stx $4305
    lda #$01
    sta $420B
    rts

LoadCommonGfx:
    ldx #OBJCHR
    stx tmp0
    ldx #ObjTiles
    stx ptr
    lda.b #:ObjTiles
    sta ptr+2
    ldx #8192
    stx tmp1
    jsr DmaVram
    ldx #BG3CHR
    stx tmp0
    ldx #HudTiles
    stx ptr
    lda.b #:HudTiles
    sta ptr+2
    ldx #HudTilesEnd-HudTiles
    stx tmp1
    jsr DmaVram
    ldx #HudPal
    stx ptr
    lda.b #:HudPal
    sta ptr+2
    ldx #64
    stx tmp1
    lda #0
    jsr DmaCgram
    ldx #ObjPal
    stx ptr
    lda.b #:ObjPal
    sta ptr+2
    ldx #256
    stx tmp1
    lda #128
    jsr DmaCgram
    rts

SetupPpu:
    lda #$62
    sta $2101               ; OBJ 16x16 / 32x32, tiles at $4000
    lda #$39
    sta $2105               ; mode 1, BG3 priority, BG1+BG2 16x16 tiles
    lda.b #(BG1MAP >> 8)
    sta $2107
    lda.b #(BG2MAP >> 8)
    sta $2108
    lda.b #(BG3MAP >> 8)
    sta $2109
    stz $210B               ; BG1/BG2 tiles at $0000
    lda.b #(BG3CHR >> 12)
    sta $210C
    lda #$FF                ; vertical scroll -1 so map line 0 is screen line 0
    sta $210E
    sta $210E
    sta $2110
    sta $2110
    sta $2112
    sta $2112
    lda #$17
    sta $212C               ; main screen: BG1 BG2 BG3 OBJ
    ; HDMA ch1: CGRAM colour 0 (sky), mode 3 -> $2121,$2121,$2122,$2122
    lda #$03
    sta $4310
    lda #$21
    sta $4311
    rts

; setting tiles/palettes for `setting` (forced blank)
LoadSetting:
    A16
    lda setting
    and #$000F
    cmp #12
    bcc @ok
    lda #0
@ok:
    asl
    tax
    lda SettingAddr,x
    sta ptr2
    A8
    lda #$03
    sta ptr2+2
    sta ptr+2
    ldx ptr2
    stx ptr
    ldx #$0000
    stx tmp0
    ldx #2048
    stx tmp1
    jsr DmaVram
    A16
    lda ptr2
    clc
    adc #2048
    sta ptr
    A8
    ldx #32
    stx tmp1
    lda #32
    jsr DmaCgram
    A16
    lda ptr2
    clc
    adc #2080
    sta ptr
    A8
    ldx #32
    stx tmp1
    lda #64
    jsr DmaCgram
    A16
    lda ptr2
    clc
    adc #2112
    sta $4312
    A8
    lda #$03
    sta $4314
    ; backdrop map variant (record byte 2240) -> BG2 map
    ldy #2240
    lda [ptr2],y
    and #$03
    A16
    and #$0003
    xba
    asl
    asl
    asl                     ; * 2048
    clc
    adc #Bg2Map
    sta ptr
    A8
    lda.b #:Bg2Map
    sta ptr+2
    ldx #BG2MAP
    stx tmp0
    ldx #2048
    stx tmp1
    jsr DmaVram
    rts

; ------------------------------------------------------------------ screen control
ScreenOff:
    jsr WaitFrame
    lda #$80
    sta $2100
    stz $420C
    rts

ScreenOn:
    jsr WaitFrame
    lda #$02
    sta $420C
    lda #$0F
    sta $2100
    rts

; ------------------------------------------------------------------ NMI + frame sync
NmiHandler:
    rep #$30
    pha
    phx
    phy
    phb
    phd
    lda #$0000
    tcd
    A8
    phk
    plb
    lda $4210
    lda nmiReady
    bne @go
    jmp @skip
@go:
    ; OAM
    stz $2102
    stz $2103
    stz $4300
    lda #$04
    sta $4301
    ldx #OAM
    stx $4302
    stz $4304
    ldx #544
    stx $4305
    lda #$01
    sta $420B
    ; one level column
    ldx colPend
    cpx #$FFFF
    beq @nocol
    jsr UploadColumn
    ldx #$FFFF
    stx colPend
@nocol:
    lda txtDirty
    beq @hud
    ldx #BG3MAP
    stx $2116
    ldx #2048
    bra @bg3
@hud:
    lda hudDirty
    beq @scroll
    ldx #BG3MAP
    stx $2116
    ldx #256
@bg3:
    stx $4305
    lda #$80
    sta $2115
    lda #$01
    sta $4300
    lda #$18
    sta $4301
    ldx #BG3BUF
    stx $4302
    stz $4304
    lda #$01
    sta $420B
    stz txtDirty
    stz hudDirty
@scroll:
    lda camX
    sta $210D
    lda camX+1
    sta $210D
    lda hscroll2
    sta $210F
    lda hscroll2+1
    sta $210F
    stz nmiReady
    lda #$01
    sta nmiDone
@skip:
    rep #$30
    pld
    plb
    ply
    plx
    pla
    rti

.ACCU 8
; UploadColumn: COLBUF -> BG1 map column (X = level column). A8.
UploadColumn:
    lda #$81
    sta $2115
    A16
    txa
    and #$001F
    clc
    adc #(BG1MAP + 64)
    sta $2116
    A8
    lda #$01
    sta $4300
    lda #$18
    sta $4301
    ldx #COLBUF
    stx $4302
    stz $4304
    ldx #24
    stx $4305
    lda #$01
    sta $420B
    lda #$80
    sta $2115
    rts

WaitFrame:
    stz nmiDone
    lda #$01
    sta nmiReady
@w:
    lda nmiDone
    beq @w
@joy:
    lda $4212
    and #$01
    bne @joy
    A16
    lda joy
    sta joyPrev
    lda $4218
    sta joy
    eor joyPrev
    and joy
    sta joyNew
    inc frame
    A8
    rts

; ------------------------------------------------------------------ BG helpers
ClearBg1Map:
    lda #$80
    sta $2115
    ldx #BG1MAP
    stx $2116
    lda #$09
    sta $4300
    lda #$18
    sta $4301
    ldx #ZeroWord
    stx $4302
    stz $4304
    ldx #2048
    stx $4305
    lda #$01
    sta $420B
    rts

ClearBg3Buf:
    A16
    ldx #$0000
    lda #$0000
@c:
    sta BG3BUF,x
    inx
    inx
    cpx #2048
    bne @c
    A8
    rts

; ClearRows: clear BG3BUF rows tmp0..tmp0+tmp1-1 (A16 inside)
ClearMsg:
    A16
    ldx #(10*64)
    lda #$0000
@c:
    sta BG3BUF,x
    inx
    inx
    cpx #(17*64)
    bne @c
    A8
    lda #$01
    sta txtDirty
    rts

; UploadBg3Now (forced blank)
UploadBg3Now:
    ldx #BG3MAP
    stx tmp0
    ldx #BG3BUF
    stx ptr
    stz ptr+2
    ldx #2048
    stx tmp1
    jsr DmaVram
    rts

; PrintStr: X = BG3 cell (row*32+col), Y = address of 0-terminated ASCII in bank 0.
; tmp7 = attribute word (palette/priority). A8 in/out.
PrintStr:
    A16
    txa
    asl
    tax
@n:
    lda $0000,y
    and #$00FF
    beq @done
    phx
    tax
    lda AsciiTable,x
    plx
    and #$00FF
    ora tmp7
    sta BG3BUF,x
    inx
    inx
    iny
    bra @n
@done:
    A8
    lda #$01
    sta txtDirty
    rts

; PutTile: X = byte offset in BG3BUF, A16 = tile|attr. Advances X.
; PutBCD: A8 = BCD byte, X = byte offset. Writes 2 digits, advances X by 4.
PutBCD:
    pha
    lsr
    lsr
    lsr
    lsr
    jsr PutDigit
    pla
    and #$0F
    jsr PutDigit
    rts
PutDigit:
    A16
    and #$000F
    clc
    adc #(T_ZERO | $2000)
    sta BG3BUF,x
    inx
    inx
    A8
    rts

; ================================================================== title screen
GoTitle:
    jsr ScreenOff
    lda #S_TITLE
    sta gstate
    lda #$01
    sta SIG+3
    stz lvl
    jsr ReadLevelHeader     ; setting of stage 1 for the title backdrop
    jsr LoadSetting
    jsr ClearBg1Map
    ; ground strip on BG1 rows 12-13
    lda #$80
    sta $2115
    ldx #(BG1MAP + 12*32)
    stx $2116
    ldy #32
@g1:
    ldx #$0802
    stx $2118
    dey
    bne @g1
    ldy #32
@g2:
    ldx #$0804
    stx $2118
    dey
    bne @g2
    jsr ClearBg3Buf
    ; title text records from the builder: [len, off_lo, off_hi, tile...]
    ldx #$0000
@rec:
    lda TextData,x
    beq @recdone
    sta tmp2
    stz tmp2+1
    inx
    A16
    lda TextData,x
    and #$03FF
    asl
    tay
    A8
    inx
    inx
@put:
    lda TextData,x
    sta BG3BUF,y
    lda #$30                ; palette 4 (gold), priority
    cpy #(16*64)
    bcc @gold
    lda #$20                ; lower lines: palette 0 (white)
@gold:
    sta BG3BUF+1,y
    iny
    iny
    inx
    dec tmp2
    bne @put
    bra @rec
@recdone:
    jsr UploadBg3Now
    A16
    stz camX
    stz hscroll2
    lda #(24*16)
    sta heroX
    lda #(10*16*16)
    sta heroY
    stz heroVX
    A8
    stz heroFace
    lda #$01
    sta heroGnd
    stz heroInv
    stz heroAtk
    stz bossLvl
    ldx #$4000
    stx goalX
    jsr ClearEntities
    jsr DrawSprites
    jsr ScreenOn
@loop:
    jsr WaitFrame
    jsr WriteProbe
    A16
    lda joyNew
    and #J_START
    A8
    beq @loop
    jmp NewGame

; ================================================================== game flow
NewGame:
    lda #$02
    sta SIG+3
    stz lvl
    lda startLives
    sta lives
    stz coins
    stz score
    stz score+1
    stz score+2
    stz paused
    jmp StartLevel

StartLevel:
    jsr ScreenOff
    jsr LoadLevel
    jsr LoadSetting
    jsr ClearBg1Map
    jsr ClearEntities
    A16
    lda startX
    sta heroX
    lda startY
    sta heroY
    stz heroVX
    stz heroVY
    A8
    stz heroFace
    stz heroInv
    stz heroAtk
    stz heroGnd
    stz hasKey
    stz bossDead
    stz paused
    stz shopHint
    stz redrawN
    lda startHearts
    sta hearts
    stz timeFr
    jsr CameraSnap
    ; draw the 17 visible columns now
    A16
    lda leftCol
    beq @c0
    dec a
@c0:
    sta tmp6
@cols:
    lda tmp6
    cmp lvlCols
    bcs @colsdone
    jsr BuildColumn
    A8
    ldx tmp6
    jsr UploadColumn
    A16
    inc tmp6
    lda tmp6
    sec
    sbc leftCol
    cmp #19
    bcc @cols
@colsdone:
    A8
    ldx #$FFFF
    stx colPend
    jsr ClearBg3Buf
    jsr DrawHud
    ; "STAGE nn" message
    lda #$20
    sta tmp7+1
    stz tmp7
    ldx #(12*32 + 12)
    ldy #MsgStage
    jsr PrintStr
    lda lvl
    inc a
    jsr ToBCD
    ldx #((12*32 + 18) * 2)
    jsr PutBCD
    jsr UploadBg3Now
    jsr SpawnObjects
    jsr DrawSprites
    lda #S_INTRO
    sta gstate
    ldx #80
    stx gtimer
    jsr ScreenOn
    jmp GameLoop

GameLoop:
    jsr WaitFrame
    A16
    lda gstate
    and #$00FF
    asl
    tax
    A8
    jmp (StateTable,x)

StateTable:
    .DW GameLoop, DoIntro, DoPlay, DoDying, DoClear, DoOver, DoWin

DoIntro:
    jsr DrawSprites
    jsr WriteProbe
    ldx gtimer
    dex
    stx gtimer
    bne @w
    jsr ClearMsg
    lda #S_PLAY
    sta gstate
@w:
    jmp GameLoop

DoPlay:
    A16
    lda joyNew
    and #J_START
    A8
    beq @nopause
    lda paused
    eor #$01
    sta paused
    beq @unpause
    lda #$20
    sta tmp7+1
    stz tmp7
    ldx #(12*32 + 13)
    ldy #MsgPaused
    jsr PrintStr
    jmp GameLoop
@unpause:
    jsr ClearMsg
@nopause:
    lda paused
    beq @run
    jmp GameLoop
@run:
    jsr HeroUpdate
    jsr CameraUpdate
    jsr SpawnObjects
    jsr UpdateEntities
    jsr CheckGoal
    jsr UpdateTimer
    jsr DrawSprites
    jsr WriteProbe
    jmp GameLoop

DoDying:
    A16
    lda heroVY
    clc
    adc #GRAV
    cmp #MAXFALL
    bmi @v
    lda #MAXFALL
@v:
    sta heroVY
    clc
    adc heroY
    sta heroY
    A8
    jsr DrawSprites
    jsr WriteProbe
    ldx gtimer
    dex
    stx gtimer
    bne @w
    lda flags
    and #F_LIVES
    beq @retry
    sed
    lda lives
    sec
    sbc #$01
    sta lives
    cld
    beq @over
@retry:
    jmp StartLevel
@over:
    lda #S_OVER
    sta gstate
    ldx #300
    stx gtimer
    jsr ClearMsg
    lda #$20
    sta tmp7+1
    stz tmp7
    ldx #(12*32 + 11)
    ldy #MsgOver
    jsr PrintStr
@w:
    jmp GameLoop

DoClear:
    jsr DrawSprites
    jsr WriteProbe
    ldx gtimer
    dex
    stx gtimer
    bne @w
    inc lvl
    lda lvl
    cmp lvlCount
    bcs @win
    jmp StartLevel
@win:
    lda #S_WIN
    sta gstate
    ldx #120
    stx gtimer
    jsr ClearMsg
    lda #$30
    sta tmp7+1
    stz tmp7
    ldx #(11*32 + 11)
    ldy #MsgWin
    jsr PrintStr
    lda #$20
    sta tmp7+1
    ldx #(14*32 + 7)
    ldy #MsgThanks
    jsr PrintStr
@w:
    jmp GameLoop

DoOver:
    jsr WriteProbe
    ldx gtimer
    dex
    stx gtimer
    beq @title
    cpx #240
    bcs @w
    A16
    lda joyNew
    and #J_START
    A8
    beq @w
@title:
    jmp GoTitle
@w:
    jmp GameLoop

DoWin:
    jsr DrawSprites
    jsr WriteProbe
    ldx gtimer
    beq @wait
    dex
    stx gtimer
    jmp GameLoop
@wait:
    A16
    lda joyNew
    and #J_START
    A8
    beq @w
    jmp GoTitle
@w:
    jmp GameLoop

; ================================================================== level loading
; ReadLevelHeader: ptr -> level record of `lvl`; reads screens/flags/time/start/goal/setting.
ReadLevelHeader:
    lda LEVELPACK+6
    sta lvlCount
    lda lvl
    cmp lvlCount
    bcc @ok
    stz lvl
@ok:
    A16
    lda lvl
    and #$00FF
    asl
    tax
    lda.l LEVELPACK+7,x
    clc
    adc #$8000
    sta ptr
    A8
    lda #$01
    sta ptr+2
    ldy #8
    lda [ptr],y
    sta setting
    rts

LoadLevel:
    jsr ReadLevelHeader
    ldy #0
    lda [ptr],y             ; screens
    beq @one
    cmp #17
    bcc @scr
@one:
    lda #1
@scr:
    A16
    and #$00FF
    xba                     ; *256 px
    sta lvlWidth
    lsr
    lsr
    lsr
    lsr
    sta lvlCols
    A8
    ldy #1
    lda [ptr],y
    and #$01
    sta bossLvl
    ; time limit (binary seconds) -> BCD
    A16
    ldy #2
    lda [ptr],y
    sta tmp0
    A8
    jsr TimeToBCD
    ; start (tile) -> 1/16 px
    ldy #4
    lda [ptr],y
    xba
    lda #0
    A16
    and #$FF00
    sta startX
    A8
    ldy #5
    lda [ptr],y
    xba
    lda #0
    A16
    and #$FF00
    sta startY
    A8
    ; goal (tile) -> px
    ldy #6
    lda [ptr],y
    A16
    and #$00FF
    asl
    asl
    asl
    asl
    sta goalX
    A8
    ldy #7
    lda [ptr],y
    A16
    and #$00FF
    asl
    asl
    asl
    asl
    sta goalY
    A8
    ; objects
    ldy #9
    lda [ptr],y
    cmp #97
    bcc @cnt
    lda #96
@cnt:
    sta objCount
    ldy #10
    ldx #$0000
@obj:
    cpx #96
    bcs @objdone
    txa
    cmp objCount
    bcs @objclr
    lda [ptr],y
    sta OBJKIND,x
    iny
    lda [ptr],y
    sta OBJX,x
    iny
    lda [ptr],y
    sta OBJY,x
    iny
    stz OBJST,x
    inx
    bra @obj
@objclr:
    lda #2
    sta OBJST,x
    stz OBJKIND,x
    inx
    bra @obj
@objdone:
    ; clear the map
    lda #$00
    ldx #$0000
@mc:
    sta.l MAPRAM,x
    inx
    cpx #$1000
    bne @mc
    ; decode columns: y = data offset, x = map index
    ldx #$0000
    stx tmp1                ; columns done
@col:
    A16
    lda tmp1
    cmp lvlCols
    A8
    bcc @more
    rts
@more:
    lda [ptr],y             ; header: (repeat-1)<<4 | runs
    iny
    sta tmp2
    and #$0F
    sta tmp3                ; runs
    lda tmp2
    lsr
    lsr
    lsr
    lsr
    inc a
    sta tmp4                ; repeat
    stz tmp5                ; row
    ; clear COLTMP
    phx
    ldx #$0000
@ct:
    stz COLTMP,x
    inx
    cpx #16
    bne @ct
    plx
@run:
    lda tmp3
    beq @runsdone
    dec tmp3
    lda [ptr],y
    iny
    sta tmp2
    and #$0F
    inc a
    sta tmp6                ; length
    lda tmp2
    lsr
    lsr
    lsr
    lsr
    sta tmp2                ; tile
@fill:
    lda tmp5
    cmp #12
    bcs @skipcell
    phx
    A16
    and #$00FF
    tax
    A8
    lda tmp2
    sta COLTMP,x
    plx
@skipcell:
    inc tmp5
    dec tmp6
    bne @fill
    bra @run
@runsdone:
    ; write `repeat` copies of COLTMP
@rep:
    A16
    lda tmp1
    cmp lvlCols
    A8
    bcs @col
    phy
    ldy #$0000
@cp:
    lda COLTMP,y
    sta.l MAPRAM,x
    inx
    iny
    cpy #16
    bne @cp
    ply
    A16
    inc tmp1
    A8
    dec tmp4
    bne @rep
    jmp @col

; TimeToBCD: tmp0 = seconds (binary, capped at 999) -> timeBCD (3 BCD digits)
TimeToBCD:
    A16
    lda tmp0
    cmp #1000
    bcc @ok
    lda #999
@ok:
    sta tmp0
    stz timeBCD
    A8
    stz tmp1                ; hundreds
@h:
    A16
    lda tmp0
    cmp #100
    bcc @hd
    sbc #100
    sta tmp0
    A8
    inc tmp1
    bra @h
@hd:
    A8
    lda tmp1
    sta timeBCD+1
    stz tmp1
@t:
    lda tmp0
    cmp #10
    bcc @td
    sbc #10
    sta tmp0
    inc tmp1
    bra @t
@td:
    lda tmp1
    asl
    asl
    asl
    asl
    ora tmp0
    sta timeBCD
    rts

; ToBCD: A8 binary (0-99) -> A8 BCD
ToBCD:
    sta tmp0
    stz tmp1
@t:
    lda tmp0
    cmp #10
    bcc @d
    sbc #10
    sta tmp0
    inc tmp1
    bra @t
@d:
    lda tmp1
    asl
    asl
    asl
    asl
    ora tmp0
    rts

; BuildColumn: A16 = column -> COLBUF (12 map entries). Returns A16.
.ACCU 16
BuildColumn:
    asl
    asl
    asl
    asl
    tax
    ldy #$0000
@r:
    lda.l MAPRAM,x
    and #$000F
    asl
    ora #$0800              ; BG palette 2
    sta COLBUF,y
    inx
    iny
    iny
    cpy #24
    bne @r
    rts
.ACCU 8

; OpenDoors: every door tile becomes empty, then redraw the visible columns
OpenDoors:
    ldx #$0000
@d:
    lda.l MAPRAM,x
    cmp #6
    bne @n
    lda #0
    sta.l MAPRAM,x
@n:
    inx
    cpx #$1000
    bne @d
    ldx leftCol
    stx redrawCol
    lda #18
    sta redrawN
    rts

; ================================================================== camera
CameraSnap:
    jsr CameraCalc
    A16
    lda camX
    lsr
    lsr
    lsr
    lsr
    sta leftCol
    A8
    rts

CameraCalc:
    A16
    lda heroX
    lsr
    lsr
    lsr
    lsr
    sec
    sbc #120
    bpl @p
    lda #0
@p:
    sta tmp0
    lda lvlWidth
    sec
    sbc #256
    cmp tmp0
    bcs @ok
    sta tmp0
@ok:
    lda tmp0
    sta camX
    lsr
    sta hscroll2
    A8
    rts

CameraUpdate:
    jsr CameraCalc
    A16
    lda camX
    lsr
    lsr
    lsr
    lsr
    cmp leftCol
    beq @redraw
    sta tmp6
    sec
    sbc leftCol
    clc
    adc #1
    cmp #3
    lda tmp6
    bcc @step
    ; big jump (respawn/teleport): redraw every visible column over the next frames
    sta leftCol
    dec a
    bpl @rc
    lda #0
@rc:
    sta redrawCol
    A8
    lda #19
    sta redrawN
    rts
.ACCU 16
@step:
    cmp leftCol
    bcc @left
    sta leftCol
    clc
    adc #17
    cmp lvlCols
    bcs @done
    bra @build
@left:
    sta leftCol
    dec a
    bmi @done
@build:
    sta tmp6
    jsr BuildColumn
    lda tmp6
    sta colPend
@done:
    A8
    rts
@redraw:
    A8
    lda redrawN
    beq @done2
    dec redrawN
    A16
    lda redrawCol
    cmp lvlCols
    bcs @skip
    sta tmp6
    jsr BuildColumn
    lda tmp6
    sta colPend
@skip:
    inc redrawCol
    A8
@done2:
    rts

; ================================================================== collision
; TileAt: px, py (pixels, signed) -> A16 = tile id. Uses X.
.ACCU 16
TileAt:
    lda py
    bmi @empty
    cmp #192
    bcs @empty
    lda px
    bmi @wall
    cmp lvlWidth
    bcs @wall
    and #$FFF0
    sta tmp5
    lda py
    lsr
    lsr
    lsr
    lsr
    ora tmp5
    tax
    lda.l MAPRAM,x
    and #$000F
    rts
@empty:
    lda #0
    rts
@wall:
    lda #3
    rts

; HeroSolid: tile at px,py solid for the hero? A16 = 0/1, records spikes.
HeroSolid:
    jsr TileAt
    cmp #5
    bne @s
    pha
    A8
    lda #1
    sta spikeHit
    A16
    pla
@s:
    tax
    lda SolidTable,x
    and #$00FF
    rts

; SupportAt: A16 nonzero if tile at px,py can be stood on (solid or platform).
SupportAt:
    jsr TileAt
    tax
    lda SupportTable,x
    and #$00FF
    rts

; ArithShift4: A16 signed >> 4
Asr4:
    cmp #$8000
    ror
    cmp #$8000
    ror
    cmp #$8000
    ror
    cmp #$8000
    ror
    rts
.ACCU 8

; ================================================================== hero
HeroUpdate:
    stz spikeHit
    lda heroInv
    beq @ni
    dec heroInv
@ni:
    lda heroAtk
    beq @na
    dec heroAtk
@na:
    ; ---- horizontal input
    A16
    lda #WALK
    sta tmp2
    lda combat
    and #$00FF
    cmp #C_STOMP
    beq @canrun
    cmp #C_NONE
    bne @norun
@canrun:
    lda joy
    and #J_ACT
    beq @norun
    lda #RUN
    sta tmp2
@norun:
    lda joy
    and #J_RIGHT
    beq @notr
    A8
    stz heroFace
    A16
    lda heroVX
    bpl @r1
    clc
    adc #ACCEL*2
@r1:
    clc
    adc #ACCEL
    bmi @rs
    cmp tmp2
    bcc @rs
    lda tmp2
@rs:
    sta heroVX
    bra @hdone
@notr:
    lda joy
    and #J_LEFT
    beq @notl
    A8
    lda #1
    sta heroFace
    A16
    lda heroVX
    bmi @l1
    sec
    sbc #ACCEL*2
@l1:
    sec
    sbc #ACCEL
    bpl @ls
    sta tmp3
    lda tmp2
    eor #$FFFF
    inc a
    cmp tmp3
    bcs @ls2
    lda tmp3
@ls2:
    bra @lst
@ls:
@lst:
    sta heroVX
    bra @hdone
@notl:
    lda heroVX
    beq @hdone
    bmi @fneg
    sec
    sbc #FRICTION
    bpl @fst
    lda #0
    bra @fst
@fneg:
    clc
    adc #FRICTION
    bmi @fst
    lda #0
@fst:
    sta heroVX
@hdone:
    ; ---- jump (buffered, with coyote time)
    A8
    lda heroGnd
    beq @air
    lda #6
    sta coyote
    bra @cy
@air:
    lda coyote
    beq @cy
    dec coyote
@cy:
    A16
    lda joyNew
    and #J_JUMP
    A8
    beq @nobuf
    lda #6
    sta jumpBuf
    bra @jb
@nobuf:
    lda jumpBuf
    beq @jb
    dec jumpBuf
@jb:
    lda jumpBuf
    beq @nojump
    lda coyote
    beq @nojump
    stz jumpBuf
    stz coyote
    stz heroGnd
    A16
    lda #-JUMPV
    sta heroVY
    A8
@nojump:
    ; ---- gravity
    A16
    lda #GRAV
    sta tmp2
    lda heroVY
    bpl @g
    lda joy
    and #J_JUMP
    beq @g
    lda #GRAVHOLD
    sta tmp2
@g:
    lda heroVY
    clc
    adc tmp2
    bmi @gs
    cmp #MAXFALL
    bcc @gs
    lda #MAXFALL
@gs:
    sta heroVY
    A8
    ; ---- attack
    lda combat
    cmp #C_MELEE
    beq @atk
    cmp #C_SHOOT
    bne @noatk
@atk:
    A16
    lda joyNew
    and #J_ACT
    A8
    beq @noatk
    lda heroAtk
    bne @noatk
    lda #16
    sta heroAtk
    lda combat
    cmp #C_SHOOT
    bne @noatk
    jsr FireShot
@noatk:
    jsr HeroMoveX
    jsr HeroMoveY
    ; pits
    A16
    lda heroY
    bmi @np
    cmp #(208*16)
    bcc @np
    A8
    jmp KillHero
@np:
    A8
    lda spikeHit
    beq @ns
    jsr HurtHero
@ns:
    rts

HeroMoveX:
    A16
    lda heroVX
    beq @done
    bmi @neg
    clc
    adc heroX
    bcc @st
    lda #$FF00
    bra @st
@neg:
    clc
    adc heroX
    bcs @st
    lda #0
@st:
    sta heroX
    ; clamp to level
    lda lvlWidth
    sec
    sbc #16
    asl
    asl
    asl
    asl
    cmp heroX
    bcs @in
    sta heroX
    stz heroVX
@in:
    lda heroX
    lsr
    lsr
    lsr
    lsr
    sta tmp0                ; hx
    lda heroY
    jsr Asr4
    sta tmp1                ; hy
    lda heroVX
    bmi @left
    ; right edge
    lda tmp0
    clc
    adc #12
    sta px
    jsr SideHit
    beq @done
    lda px
    and #$FFF0
    sec
    sbc #13
    bra @push
@left:
    lda tmp0
    clc
    adc #3
    sta px
    jsr SideHit
    beq @done
    lda px
    and #$FFF0
    clc
    adc #13
@push:
    asl
    asl
    asl
    asl
    sta heroX
    stz heroVX
@done:
    A8
    rts

; SideHit: px set; checks hy+2, hy+8, hy+15. A16 nonzero if solid.
.ACCU 16
SideHit:
    lda tmp1
    clc
    adc #2
    sta py
    jsr HeroSolid
    bne @hit
    lda tmp1
    clc
    adc #8
    sta py
    jsr HeroSolid
    bne @hit
    lda tmp1
    clc
    adc #15
    sta py
    jsr HeroSolid
@hit:
    rts
.ACCU 8

HeroMoveY:
    A16
    lda heroY
    jsr Asr4
    clc
    adc #16
    sta oldFeet
    lda heroY
    clc
    adc heroVY
    sta heroY
    lda heroX
    lsr
    lsr
    lsr
    lsr
    sta tmp0
    lda heroY
    jsr Asr4
    sta tmp1
    lda heroVY
    bmi @up
    ; falling / standing: feet at hy+16
    lda tmp1
    clc
    adc #16
    sta py
    lda tmp0
    clc
    adc #3
    sta px
    jsr FeetHit
    bne @land
    lda tmp0
    clc
    adc #12
    sta px
    jsr FeetHit
    bne @land
    A8
    stz heroGnd
    rts
.ACCU 16
@land:
    lda py
    and #$FFF0
    sec
    sbc #16
    asl
    asl
    asl
    asl
    sta heroY
    stz heroVY
    A8
    lda #1
    sta heroGnd
    rts
.ACCU 16
@up:
    A8
    stz heroGnd
    A16
    lda tmp1
    clc
    adc #2
    sta py
    lda tmp0
    clc
    adc #3
    sta px
    jsr HeroSolid
    bne @bump
    lda tmp0
    clc
    adc #12
    sta px
    jsr HeroSolid
    beq @free
@bump:
    lda py
    and #$FFF0
    clc
    adc #14
    asl
    asl
    asl
    asl
    sta heroY
    stz heroVY
@free:
    A8
    rts

; FeetHit: tile at px,py (feet) supports a falling hero? A16 nonzero = land.
.ACCU 16
FeetHit:
    jsr TileAt
    cmp #4
    beq @plat
    cmp #5
    bne @solid
    pha
    A8
    lda #1
    sta spikeHit
    A16
    pla
@solid:
    tax
    lda SolidTable,x
    and #$00FF
    rts
@plat:
    ; one-way platform: only if the feet were at or above its top last frame
    lda py
    and #$FFF0
    cmp oldFeet
    bcc @no
    lda #1
    rts
@no:
    lda #0
    rts
.ACCU 8

HurtHero:
    lda heroInv
    bne @r
    lda gstate
    cmp #S_PLAY
    bne @r
    lda flags
    and #F_HEARTS
    beq KillHero
    dec hearts
    beq KillHero
    bmi KillHero
    lda #90
    sta heroInv
    A16
    lda #-40
    sta heroVY
    A8
    lda #1
    sta hudDirty
    jsr DrawHud
@r:
    rts

KillHero:
    lda gstate
    cmp #S_PLAY
    bne @r
    lda #S_DYING
    sta gstate
    ldx #110
    stx gtimer
    stz hearts
    A16
    lda #-72
    sta heroVY
    stz heroVX
    A8
    jsr DrawHud
@r:
    rts

FireShot:
    ; free shot slot (10 or 11)
    ldx #(10*2)
    lda E_KIND,x
    beq @f
    ldx #(11*2)
    lda E_KIND,x
    beq @f
    rts
@f:
    lda #K_SHOT
    sta E_KIND,x
    A16
    lda heroX
    sta E_X,x
    lda heroY
    clc
    adc #(2*16)
    sta E_Y,x
    A8
    lda heroFace
    A16
    beq @rt
    lda #-64
    bra @st
@rt:
    lda #64
@st:
    sta E_VX,x
    lda #36
    sta E_TIMER,x
    A8
    lda heroFace
    sta E_DIR,x
    rts

; ================================================================== objects
ClearEntities:
    ldx #$0000
@c:
    stz E_KIND,x
    stz E_KIND+1,x
    inx
    inx
    cpx #(NSLOTS*2)
    bne @c
    rts

; SpawnObjects: wake dormant objects that come into view
SpawnObjects:
    A16
    lda camX
    sec
    sbc #32
    bpl @lo
    lda #0
@lo:
    lsr
    lsr
    lsr
    lsr
    sta tmp2                ; lo tile
    lda camX
    clc
    adc #288
    lsr
    lsr
    lsr
    lsr
    cmp #256
    bcc @hi
    lda #255
@hi:
    sta tmp3                ; hi tile
    A8
    ldy #$0000
@o:
    tya
    cmp objCount
    bcc @chk
    rts
@chk:
    lda OBJST,y
    bne @next
    lda OBJX,y
    cmp tmp2
    bcc @next
    cmp tmp3
    beq @in
    bcs @next
@in:
    jsr FreeSlot
    bcs @full
    jsr SpawnOne
@next:
    iny
    bra @o
@full:
    rts

; FreeSlot: X = free object slot*2, carry clear; carry set if none
FreeSlot:
    ldx #$0000
@f:
    lda E_KIND,x
    beq @ok
    inx
    inx
    cpx #(NOBJSLOT*2)
    bne @f
    sec
    rts
@ok:
    clc
    rts

; SpawnOne: object Y -> slot X
SpawnOne:
    lda #1
    sta OBJST,y
    lda OBJKIND,y
    sta E_KIND,x
    stz E_KIND+1,x
    A16
    tya
    sta E_SRC,x
    lda OBJX,y
    and #$00FF
    xba
    sta E_X,x
    lda OBJY,y
    and #$00FF
    xba
    sta E_Y,x
    sta E_BASEY,x
    stz E_VX,x
    stz E_VY,x
    stz E_TIMER,x
    stz E_HURT,x
    lda #1
    sta E_DIR,x
    sta E_HP,x
    stz E_GND,x
    A8
    lda E_KIND,x
    cmp #K_WALKER
    bne @nw
    A16
    lda #-8
    sta E_VX,x
    A8
    rts
@nw:
    cmp #K_HOPPER
    bne @nh
    A16
    lda #40
    sta E_TIMER,x
    A8
    rts
@nh:
    cmp #K_BOSS
    bne @nb
    A16
    lda E_Y,x
    sec
    sbc #$0100              ; (x, y) is the bottom-left of a 2x2 boss
    sta E_Y,x
    lda #-12
    sta E_VX,x
    lda #3
    sta E_HP,x
    lda #90
    sta E_TIMER,x
    A8
@nb:
    rts

; UpdateEntities
UpdateEntities:
    ldx #$0000
@e:
    stx slot
    lda E_KIND,x
    beq @next
    A16
    and #$00FF
    asl
    tax
    A8
    jsr (KindTable,x)
@next:
    ldx slot
    inx
    inx
    cpx #(NSLOTS*2)
    bne @e
    rts

KindTable:
    .DW KNone, KWalker, KHopper, KFlyer, KItem, KItem, KItem, KItem, KBoss, KShop, KShot, KPoof

KNone:
    rts

; Despawn: if slot is off-camera, return its object to dormant. Carry set = removed.
Despawn:
    ldx slot
    A16
    lda E_X,x
    lsr
    lsr
    lsr
    lsr
    clc
    adc #64
    sec
    sbc camX
    bmi @out
    cmp #(256+64+64)
    bcs @out
    A8
    clc
    rts
.ACCU 16
@out:
    lda E_SRC,x
    tay
    A8
    lda #0
    sta OBJST,y
    stz E_KIND,x
    sec
    rts

; Remove: slot gone for good (killed / collected)
RemoveGone:
    ldx slot
    A16
    lda E_SRC,x
    tay
    A8
    lda #2
    sta OBJST,y
    stz E_KIND,x
    rts

; EnemyBox: ex, ey, ew (pixels) for slot
EnemyBox:
    ldx slot
    A16
    lda E_X,x
    lsr
    lsr
    lsr
    lsr
    sta ex
    lda E_Y,x
    jsr Asr4
    sta ey
    lda #16
    sta ew
    A8
    lda E_KIND,x
    cmp #K_BOSS
    bne @r
    A16
    lda #32
    sta ew
    A8
@r:
    rts

; HeroTouch: does the hero box overlap the box (ex, ey, ew x ew, inset 2)? carry set = yes
HeroTouch:
    A16
    lda heroX
    lsr
    lsr
    lsr
    lsr
    sta tmp0
    lda heroY
    jsr Asr4
    sta tmp1
    ; hero x range [hx+3, hx+12], enemy [ex+2, ex+ew-3]
    lda tmp0
    clc
    adc #12
    sec
    sbc ex
    sec
    sbc #2
    bmi @no
    lda ex
    clc
    adc ew
    sec
    sbc #3
    sec
    sbc tmp0
    sec
    sbc #3
    bmi @no
    ; y: hero [hy+2, hy+15], enemy [ey+3, ey+ew-1]
    lda tmp1
    clc
    adc #15
    sec
    sbc ey
    sec
    sbc #3
    bmi @no
    lda ey
    clc
    adc ew
    sec
    sbc #1
    sec
    sbc tmp1
    sec
    sbc #2
    bmi @no
    A8
    sec
    rts
.ACCU 16
@no:
    A8
    clc
    rts

; EnemyVsHero: stomp / sword / hurt
EnemyVsHero:
    jsr EnemyBox
    lda gstate
    cmp #S_PLAY
    bne @r
    ; sword
    lda combat
    cmp #C_MELEE
    bne @nosw
    lda heroAtk
    cmp #4
    bcc @nosw
    jsr SwordTouch
    bcc @nosw
    jmp DamageEnemy
@nosw:
    jsr HeroTouch
    bcc @r
    ; stomp? (always allowed on the boss; on others only in stomp mode)
    ldx slot
    lda E_KIND,x
    cmp #K_BOSS
    beq @canstomp
    lda combat
    cmp #C_STOMP
    bne @hurt
@canstomp:
    A16
    lda heroVY
    bmi @hurt16
    beq @hurt16
    lda tmp1
    clc
    adc #15
    sec
    sbc ey
    cmp #10
    bcs @hurt16
    lda #-BOUNCE
    sta heroVY
    lda joy
    and #J_JUMP
    beq @b
    lda #-(BOUNCE+24)
    sta heroVY
@b:
    A8
    jmp DamageEnemy
.ACCU 16
@hurt16:
    A8
@hurt:
    ldx slot
    lda E_HURT,x
    bne @r
    jsr HurtHero
@r:
    rts

; SwordTouch: sword box in front of the hero overlaps (ex,ey,ew)? carry set = yes
SwordTouch:
    A16
    lda heroX
    lsr
    lsr
    lsr
    lsr
    sta tmp0
    lda heroY
    jsr Asr4
    sta tmp1
    A8
    lda heroFace
    A16
    php
    lda tmp0
    clc
    adc #12
    plp
    beq @r
    sec
    sbc #26
@r:
    sta tmp2                ; sword left
    ; overlap x: [tmp2, tmp2+15] vs [ex, ex+ew-1]
    clc
    adc #15
    sec
    sbc ex
    bmi @no
    lda ex
    clc
    adc ew
    sec
    sbc tmp2
    bmi @no
    beq @no
    lda tmp1
    clc
    adc #14
    sec
    sbc ey
    bmi @no
    lda ey
    clc
    adc ew
    sec
    sbc tmp1
    sec
    sbc #2
    bmi @no
    A8
    sec
    rts
.ACCU 16
@no:
    A8
    clc
    rts

; DamageEnemy: slot takes one hit
DamageEnemy:
    ldx slot
    lda E_HURT,x
    bne @r
    dec E_HP,x
    beq @dead
    bmi @dead
    lda #40
    sta E_HURT,x
    rts
@dead:
    lda E_KIND,x
    cmp #K_BOSS
    bne @small
    lda #1
    sta bossDead
    A16
    lda #$1000
    jsr AddScore
    A8
    bra @gone
@small:
    A16
    lda #$0100
    jsr AddScore
    A8
@gone:
    ldx slot
    A16
    lda E_SRC,x
    tay
    A8
    lda #2
    sta OBJST,y
    lda #K_POOF
    sta E_KIND,x
    lda #16
    sta E_TIMER,x
@r:
    rts

; AddScore: A16 = BCD amount (low 4 digits)
.ACCU 16
AddScore:
    sed
    clc
    adc score
    sta score
    A8
    lda score+2
    adc #0
    sta score+2
    cld
    lda #1
    sta hudDirty
    jsr DrawHud
    A16
    rts
.ACCU 8

; EnemyPhysics: gravity + walls (+ ledges if tmp7=1) + floor, for walkers/hoppers/boss
EnemyPhysics:
    ldx slot
    A16
    lda E_VY,x
    clc
    adc #6
    bmi @v
    cmp #MAXFALL
    bcc @v
    lda #MAXFALL
@v:
    sta E_VY,x
    ; horizontal
    lda E_X,x
    clc
    adc E_VX,x
    sta E_X,x
    jsr EnemyBoxNoA8
    ; front point
    ldx slot
    lda E_VX,x
    beq @nowall
    bmi @fl
    lda ex
    clc
    adc ew
    sec
    sbc #2
    bra @fp
@fl:
    lda ex
    inc a
@fp:
    sta px
    lda ey
    clc
    adc ew
    sec
    sbc #8
    sta py
    jsr TileAt
    tax
    lda SolidTable,x
    and #$00FF
    bne @turn
    ; ledge check while walking on the ground
    ldx slot
    lda E_GND,x
    beq @nowall
    lda tmp7
    beq @nowall
    lda ey
    clc
    adc ew
    clc
    adc #2
    sta py
    jsr SupportAt
    bne @nowall
@turn:
    ldx slot
    lda E_X,x
    sec
    sbc E_VX,x
    sta E_X,x
    lda E_VX,x
    eor #$FFFF
    inc a
    sta E_VX,x
@nowall:
    ; vertical
    ldx slot
    lda E_Y,x
    clc
    adc E_VY,x
    sta E_Y,x
    lda E_VY,x
    bmi @air
    jsr EnemyBoxNoA8
    lda ex
    lsr ew
    clc
    adc ew
    asl ew
    sta px
    lda ey
    clc
    adc ew
    sta py
    jsr SupportAt
    beq @air
    ldx slot
    lda py
    and #$FFF0
    sec
    sbc ew
    asl
    asl
    asl
    asl
    sta E_Y,x
    stz E_VY,x
    lda #1
    sta E_GND,x
    bra @fallchk
@air:
    ldx slot
    stz E_GND,x
@fallchk:
    lda E_Y,x
    bmi @ok
    cmp #(200*16)
    bcc @ok
    A8
    jmp RemoveGone
.ACCU 16
@ok:
    A8
    rts

.ACCU 16
EnemyBoxNoA8:
    ldx slot
    lda E_X,x
    lsr
    lsr
    lsr
    lsr
    sta ex
    lda E_Y,x
    jsr Asr4
    sta ey
    lda E_KIND,x
    and #$00FF
    cmp #K_BOSS
    beq @b
    lda #16
    sta ew
    rts
@b:
    lda #32
    sta ew
    rts
.ACCU 8

HurtTick:
    ldx slot
    lda E_HURT,x
    beq @r
    dec E_HURT,x
@r:
    rts

KWalker:
    jsr Despawn
    bcs @r
    jsr HurtTick
    A16
    lda #1
    sta tmp7
    A8
    jsr EnemyPhysics
    ldx slot
    lda E_KIND,x
    beq @r
    jsr EnemyVsHero
@r:
    rts

KHopper:
    jsr Despawn
    bcs @r
    jsr HurtTick
    ldx slot
    lda E_GND,x
    beq @phys
    A16
    stz E_VX,x
    dec E_TIMER,x
    bne @phys16
    lda #50
    sta E_TIMER,x
    lda #-56
    sta E_VY,x
    stz E_GND,x
    ; hop toward the hero
    lda heroX
    cmp E_X,x
    lda #12
    bcs @dir
    lda #-12
@dir:
    sta E_VX,x
@phys16:
    A8
@phys:
    A16
    stz tmp7
    A8
    jsr EnemyPhysics
    ldx slot
    lda E_KIND,x
    beq @r
    jsr EnemyVsHero
@r:
    rts

KFlyer:
    jsr Despawn
    bcs @r
    jsr HurtTick
    ldx slot
    A16
    inc E_TIMER,x
    lda E_TIMER,x
    and #$003F
    asl
    tay
    lda SineTable,y
    clc
    adc E_BASEY,x
    sta E_Y,x
    ; slow drift, turning every 128 frames
    lda E_TIMER,x
    and #$007F
    bne @d
    lda E_DIR,x
    eor #1
    sta E_DIR,x
@d:
    lda #4
    ldy E_DIR,x
    beq @dr
    lda #-4
@dr:
    clc
    adc E_X,x
    sta E_X,x
    A8
    jsr EnemyVsHero
@r:
    rts

KBoss:
    jsr HurtTick
    ldx slot
    A16
    dec E_TIMER,x
    bne @nohop
    lda #120
    sta E_TIMER,x
    lda E_GND,x
    beq @nohop
    lda #-60
    sta E_VY,x
@nohop:
    ; keep inside the arena: turn if it walks more than 5 tiles from its start
    lda E_VX,x
    bne @mv
    lda #-12
    sta E_VX,x
@mv:
    A8
    A16
    stz tmp7
    A8
    jsr EnemyPhysics
    ldx slot
    lda E_KIND,x
    beq @r
    jsr EnemyVsHero
@r:
    rts

KItem:
    jsr Despawn
    bcs @r
    jsr EnemyBox
    jsr HeroTouch
    bcc @r
    ldx slot
    lda E_KIND,x
    cmp #K_COIN
    bne @nc
    sed
    lda coins
    clc
    adc #$01
    sta coins
    cld
    bne @c1
    lda flags
    and #F_LIVES
    beq @c1
    jsr AddLife
@c1:
    A16
    lda #$0010
    jsr AddScore
    A8
    bra @got
@nc:
    cmp #K_HEART
    bne @nh
    lda hearts
    cmp #5
    bcs @h1
    inc hearts
@h1:
    A16
    lda #$0050
    jsr AddScore
    A8
    bra @got
@nh:
    cmp #K_LIFE
    bne @nl
    jsr AddLife
    bra @got
@nl:
    ; key
    lda #1
    sta hasKey
    jsr OpenDoors
    A16
    lda #$0100
    jsr AddScore
    A8
@got:
    jsr DrawHud
    jsr RemoveGone
@r:
    rts

AddLife:
    lda flags
    and #F_LIVES
    beq @r
    lda lives
    cmp #$99
    bcs @r
    sed
    clc
    adc #$01
    sta lives
    cld
@r:
    rts

KShop:
    jsr Despawn
    bcs @r
    jsr EnemyBox
    jsr HeroTouch
    bcc @far
    lda shopHint
    bne @shown
    lda #1
    sta shopHint
    lda #$20
    sta tmp7+1
    stz tmp7
    ldx #(3*32 + 1)
    ldy #MsgShop
    jsr PrintStr
@shown:
    A16
    lda joyNew
    and #J_UP
    A8
    beq @r
    lda coins
    cmp #$10
    bcc @r
    sed
    sec
    sbc #$10
    sta coins
    cld
    lda flags
    and #F_HEARTS
    beq @life
    lda hearts
    cmp #5
    bcs @life
    inc hearts
    bra @paid
@life:
    jsr AddLife
@paid:
    jsr DrawHud
    rts
@far:
    lda shopHint
    beq @r
    stz shopHint
    A16
    ldx #(3*64)
    lda #0
@cl:
    sta BG3BUF,x
    inx
    inx
    cpx #(4*64)
    bne @cl
    A8
    lda #1
    sta txtDirty
@r:
    rts

KShot:
    ldx slot
    A16
    lda E_X,x
    clc
    adc E_VX,x
    sta E_X,x
    dec E_TIMER,x
    bne @alive
    A8
    jmp @kill
.ACCU 16
@alive:
    ; wall?
    lsr
    lsr
    lsr
    lsr
    clc
    adc #8
    sta px
    lda E_Y,x
    jsr Asr4
    clc
    adc #8
    sta py
    jsr TileAt
    tax
    lda SolidTable,x
    and #$00FF
    beq @nowall
    A8
    jmp @kill
@nowall:
    A8
    ; hit an enemy?
    ldx slot
    A16
    lda E_X,x
    lsr
    lsr
    lsr
    lsr
    sta tmp3                ; shot px
    lda E_Y,x
    jsr Asr4
    sta tmp4
    A8
    ldx #$0000
@t:
    lda E_KIND,x
    cmp #K_WALKER
    bcc @nt
    cmp.b #(K_FLYER+1)
    bcc @hit
    cmp #K_BOSS
    bne @nt
@hit:
    A16
    lda E_X,x
    lsr
    lsr
    lsr
    lsr
    sec
    sbc tmp3
    clc
    adc #12
    cmp #24
    bcs @nt16
    lda E_Y,x
    jsr Asr4
    sec
    sbc tmp4
    clc
    adc #12
    cmp #24
    bcs @nt16
    ; damage slot X
    A8
    lda slot
    pha
    stx slot
    jsr DamageEnemy
    pla
    sta slot
    stz slot+1
    bra @kill
.ACCU 16
@nt16:
    A8
@nt:
    inx
    inx
    cpx #(NOBJSLOT*2)
    bne @t
    rts
@kill:
    ldx slot
    stz E_KIND,x
    rts

KPoof:
    ldx slot
    dec E_TIMER,x
    bne @r
    stz E_KIND,x
@r:
    rts

CheckGoal:
    lda bossLvl
    beq @open
    lda bossDead
    beq @r
@open:
    A16
    lda goalX
    sta ex
    lda goalY
    sec
    sbc #8
    sta ey
    lda #24
    sta ew
    A8
    jsr HeroTouch
    bcc @r
    lda #S_CLEAR
    sta gstate
    ldx #150
    stx gtimer
    A16
    lda #$0500
    jsr AddScore
    A8
    lda #$30
    sta tmp7+1
    stz tmp7
    ldx #(12*32 + 10)
    ldy #MsgClear
    jsr PrintStr
@r:
    rts

UpdateTimer:
    lda flags
    and #F_TIMER
    beq @r
    A16
    lda timeBCD
    A8
    beq @r
    inc timeFr
    lda timeFr
    cmp #60
    bcc @r
    stz timeFr
    sed
    A16
    lda timeBCD
    sec
    sbc #$0001
    sta timeBCD
    A8
    cld
    jsr DrawHud
    A16
    lda timeBCD
    A8
    bne @r
    jmp KillHero
@r:
    rts

; ================================================================== HUD
; row 1: [life]x99  hearts  [gem]x99  key  TIME 999 ; row 2: SCORE 000000   STAGE 01
DrawHud:
    A16
    ldx #64
    lda #0
@c:
    sta BG3BUF,x
    inx
    inx
    cpx #192
    bne @c
    A8
    lda flags
    and #F_LIVES
    beq @nolives
    A16
    lda #(T_LIFE | $2C00)
    sta BG3BUF+64+2
    lda #(T_TIMES | $2000)
    sta BG3BUF+64+4
    A8
    ldx #(64+6)
    lda lives
    jsr PutBCD
@nolives:
    lda flags
    and #F_HEARTS
    beq @nohearts
    ldx #(64+20)
    ldy #0
@h:
    A16
    lda #(T_HEARTE | $2400)
    sta tmp0
    tya
    A8
    cmp hearts
    bcs @he
    A16
    lda #(T_HEART | $2400)
    sta tmp0
    A8
@he:
    A16
    lda tmp0
    sta BG3BUF,x
    A8
    inx
    inx
    iny
    cpy #5
    beq @nohearts
    tya
    cmp #3
    bcc @h
    cmp hearts
    bcc @h
@nohearts:
    lda flags
    and #F_COINS
    beq @nocoins
    A16
    lda #(T_GEM | $2800)
    sta BG3BUF+64+34
    lda #(T_TIMES | $2000)
    sta BG3BUF+64+36
    A8
    ldx #(64+38)
    lda coins
    jsr PutBCD
@nocoins:
    lda hasKey
    beq @nokey
    A16
    lda #(T_KEY | $2400)
    sta BG3BUF+64+44
    A8
@nokey:
    lda flags
    and #F_TIMER
    beq @notime
    A16
    lda timeBCD
    A8
    ora timeBCD+1
    beq @notime
    lda #$20
    sta tmp7+1
    stz tmp7
    ldx #(32 + 24)
    ldy #MsgTime
    jsr PrintStr
    ldx #(64+58)
    lda timeBCD+1
    jsr PutDigit
    lda timeBCD
    jsr PutBCD
@notime:
    lda flags
    and #F_SCORE
    beq @noscore
    lda #$20
    sta tmp7+1
    stz tmp7
    ldx #(64 + 1)
    ldy #MsgScore
    jsr PrintStr
    ldx #(128+14)
    lda score+2
    jsr PutBCD
    lda score+1
    jsr PutBCD
    lda score
    jsr PutBCD
@noscore:
    lda #$20
    sta tmp7+1
    stz tmp7
    ldx #(64 + 20)
    ldy #MsgStageHud
    jsr PrintStr
    lda lvl
    inc a
    jsr ToBCD
    ldx #(128+52)
    jsr PutBCD
    lda #1
    sta hudDirty
    rts

; ================================================================== sprites
; DrawSprite: tmp0 = screen x (signed), tmp1 = screen y (signed), tmp2 = tile, tmp3 = attr,
; tmp4 = 1 for a large (32x32) sprite
DrawSprite:
    A16
    lda oamIdx
    cmp #128
    bcs @r16
    lda tmp0
    clc
    adc #32
    cmp #(256+32)
    bcs @r16
    lda tmp1
    clc
    adc #32
    cmp #(224+32)
    bcs @r16
    lda oamIdx
    asl
    asl
    tax
    A8
    lda tmp0
    sta OAM,x
    lda tmp1
    sta OAM+1,x
    lda tmp2
    sta OAM+2,x
    lda tmp2+1
    and #$01
    ora tmp3
    sta OAM+3,x
    ; high table
    A16
    lda oamIdx
    lsr
    lsr
    tax
    lda oamIdx
    and #$0003
    tay
    A8
    lda tmp0+1
    and #$01
    beq @nx
    lda HiXBit,y
    ora OAM+512,x
    sta OAM+512,x
@nx:
    lda tmp4
    beq @ns
    lda HiSizeBit,y
    ora OAM+512,x
    sta OAM+512,x
@ns:
    A16
    inc oamIdx
@r16:
    A8
    rts

HiXBit:
    .DB $01, $04, $10, $40
HiSizeBit:
    .DB $02, $08, $20, $80

; ToScreen: A16 = world px x in tmp0, y in tmp1 -> screen coordinates (in place)
.ACCU 16
ToScreen:
    lda tmp0
    sec
    sbc camX
    sta tmp0
    lda tmp1
    clc
    adc #31
    sta tmp1
    rts
.ACCU 8

DrawSprites:
    ; hide all
    ldx #$0000
    lda #$F0
@h:
    sta OAM+1,x
    inx
    inx
    inx
    inx
    cpx #512
    bne @h
    ldx #$0000
@hz:
    stz OAM+512,x
    inx
    cpx #32
    bne @hz
    ldx #$0000
    stx oamIdx
    stz tmp4
    stz tmp4+1
    ; hero
    lda heroInv
    and #$04
    beq @drawhero
    jmp @nohero
@drawhero:
    A16
    lda heroX
    lsr
    lsr
    lsr
    lsr
    sta tmp0
    lda heroY
    jsr Asr4
    sta tmp1
    jsr ToScreen
    ; frame: jump / walk / stand
    A8
    lda heroGnd
    A16
    bne @onground
    lda #3
    bra @hf
@onground:
    lda heroVX
    beq @stand
    lda frame
    lsr
    lsr
    lsr
    and #$0001
    inc a
    bra @hf
@stand:
    lda #0
@hf:
    asl
    sta tmp2
    A8
    lda heroFace
    beq @hr0
    lda #$70
    bra @hr
@hr0:
    lda #$30
@hr:
    sta tmp3
    lda gstate
    cmp #S_DYING
    bne @alive
    lda #$B0                ; flipped upside down
    sta tmp3
@alive:
    jsr DrawSprite
    ; sword
    lda combat
    cmp #C_MELEE
    beq @melee
    jmp @nohero
@melee:
    lda heroAtk
    cmp #4
    bcs @swing
    jmp @nohero
@swing:
    A16
    lda heroFace
    and #$00FF
    beq @swr
    lda tmp0
    sec
    sbc #26
    bra @sws
@swr:
    lda tmp0
    clc
    adc #12
@sws:
    sta tmp0
    lda #((19 & 7)*2 + (19 >> 3)*32)
    sta tmp2
    A8
    lda heroFace
    beq @swa0
    lda #$74
    bra @swa
@swa0:
    lda #$34
@swa:
    sta tmp3
    jsr DrawSprite
@nohero:
    ; goal flag
    A16
    lda goalX
    sta tmp0
    lda goalY
    sec
    sbc #16
    sta tmp1
    jsr ToScreen
    lda #((16 & 7)*2 + (16 >> 3)*32)
    sta tmp2
    A8
    lda bossLvl
    beq @gopen
    lda bossDead
    bne @gopen
    lda #$3A                ; grey until the boss is beaten
    bra @gc
@gopen:
    lda #$34                ; items palette
@gc:
    sta tmp3
    jsr DrawSprite
    A16
    lda tmp1
    clc
    adc #16
    sta tmp1
    lda #((17 & 7)*2 + (17 >> 3)*32)
    sta tmp2
    A8
    jsr DrawSprite
    ; entities
    ldx #$0000
@e:
    stx slot
    lda E_KIND,x
    beq @en
    jsr DrawEntity
@en:
    ldx slot
    inx
    inx
    cpx #(NSLOTS*2)
    bne @e
    rts

; entity look-up: sprite id frame 0, frame 1, palette attr
EntSprite:
    .DB 0, 0, $30           ; 0 none
    .DB 4, 5, $32           ; walker
    .DB 6, 7, $32           ; hopper
    .DB 8, 9, $32           ; flyer
    .DB 10, 11, $34         ; coin (gem)
    .DB 12, 12, $34         ; heart
    .DB 13, 13, $34         ; life
    .DB 14, 14, $34         ; key
    .DB 0, 0, $36           ; boss (large)
    .DB 15, 15, $34         ; shop
    .DB 18, 18, $34         ; shot
    .DB 20, 20, $34         ; poof

DrawEntity:
    ldx slot
    A16
    lda E_X,x
    lsr
    lsr
    lsr
    lsr
    sta tmp0
    lda E_Y,x
    jsr Asr4
    sta tmp1
    jsr ToScreen
    lda E_KIND,x
    and #$00FF
    sta tmp5
    asl
    clc
    adc tmp5
    tay                     ; y = kind*3
    A8
    stz tmp4
    lda tmp5
    cmp #K_BOSS
    bne @small
    lda #1
    sta tmp4
    A16
    lda frame
    and #$0010
    beq @bf
    lda #132
    bra @bt
@bf:
    lda #128
@bt:
    sta tmp2
    A8
    lda #$36
    bra @attr
@small:
    ; frame toggles every 8 frames (hopper: airborne frame)
    lda tmp5
    cmp #K_HOPPER
    bne @anim
    lda E_GND,x
    beq @f1
    bra @f0
@anim:
    lda frame
    and #$08
    beq @f0
@f1:
    lda EntSprite+1,y
    bra @sid
@f0:
    lda EntSprite,y
@sid:
    A16
    and #$00FF
    sta tmp2
    and #$0007
    asl
    sta tmp3
    lda tmp2
    lsr
    lsr
    lsr
    xba
    lsr
    lsr
    lsr                     ; (id >> 3) * 32
    clc
    adc tmp3
    sta tmp2
    A8
    lda EntSprite+2,y
@attr:
    sta tmp3
    ; face: walker/hopper/boss face their movement; others don't flip
    A16
    lda E_VX,x
    A8
    bmi @nf0
    bne @face
@nf0:
    lda tmp5
    cmp #K_SHOT
    bne @nf
    lda E_DIR,x
    beq @nf
@face:
    lda tmp3
    ora #$40
    sta tmp3
@nf:
    ; hurt flash
    lda E_HURT,x
    and #$04
    beq @draw
    lda tmp3
    and #$F1
    ora #$08                ; palette 4 (white)
    sta tmp3
@draw:
    ; boss is 32 tall: its E_Y is the top already
    jsr DrawSprite
    rts

; ================================================================== probe
WriteProbe:
    A16
    lda heroX
    lsr
    lsr
    lsr
    lsr
    sta PROBE
    lda heroY
    jsr Asr4
    sta PROBE+2
    lda frame
    sta PROBE+10
    A8
    lda lvl
    sta PROBE+4
    lda gstate
    sta PROBE+5
    lda lives
    sta PROBE+6
    lda hearts
    sta PROBE+7
    lda coins
    sta PROBE+8
    lda hasKey
    ora bossDead
    asl
    ora heroGnd
    sta PROBE+9
    rts

; ================================================================== tables + data
SolidTable:     ; 0 empty 1 ground 2 fill 3 block 4 platform 5 spikes 6 door 7 decor
    .DB 0, 1, 1, 1, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0
SupportTable:
    .DB 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0

SineTable:      ; 64 steps, amplitude 10 px (1/16 px units)
    .DW 0, 16, 31, 46, 61, 75, 88, 101, 113, 124, 133, 141, 148, 153, 157, 159
    .DW 160, 159, 157, 153, 148, 141, 133, 124, 113, 101, 88, 75, 61, 46, 31, 16
    .DW 0, -16, -31, -46, -61, -75, -88, -101, -113, -124, -133, -141, -148, -153, -157, -159
    .DW -160, -159, -157, -153, -148, -141, -133, -124, -113, -101, -88, -75, -61, -46, -31, -16

SettingAddr:
    .DW $8000, $8A00, $9400, $9E00, $A800, $B200, $BC00, $C600, $D000, $DA00, $E400, $EE00

MsgStage:    .DB "STAGE", 0
MsgPaused:   .DB "PAUSED", 0
MsgOver:     .DB "GAME OVER", 0
MsgClear:    .DB "STAGE CLEAR!", 0
MsgWin:      .DB "YOU WIN!", 0
MsgThanks:   .DB "THANKS FOR PLAYING!", 0
MsgTime:     .DB "TIME", 0
MsgScore:    .DB "SCORE", 0
MsgStageHud: .DB "STAGE", 0
MsgShop:     .DB "SHOP - UP: BUY FOR 10 GEMS", 0

ZeroWord:
    .DW $0000
ConfigData:
    .INCBIN "config.bin"
AsciiTable:
    .INCBIN "ascii.bin"
TextData:
    .INCBIN "text.bin"
.ENDS

.BANK 1 SLOT 0
.ORG 0
.SECTION "Levels" FORCE
Levels:
    .INCBIN "levels.bin"
.ENDS

.BANK 2 SLOT 0
.ORG 0
.SECTION "ObjArt" FORCE
ObjTiles:
    .INCBIN "objtiles.bin"
HudTiles:
    .INCBIN "hudtiles.bin"
HudTilesEnd:
ObjPal:
    .INCBIN "objpal.bin"
HudPal:
    .INCBIN "hudpal.bin"
Bg2Map:
    .INCBIN "bg2map.bin"
.ENDS

.BANK 3 SLOT 0
.ORG 0
.SECTION "Settings" FORCE
Settings:
    .INCBIN "settings.bin"
.ENDS
