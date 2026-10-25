; RetroBake NES platformer engine (M2). NROM-256: 32 KB PRG + 8 KB CHR, vertical mirroring.
;
; Fixed template. The builder never writes code; it only drops in data files:
;   levels.bin  - loaded at $8000: config, level table, object lists, page-aligned column maps
;   title.bin   - title-screen text records [addr_hi, addr_lo, len, tile...]..., 0 = end
;   str_*.bin   - [len, tile...] for fixed words (stage, game over, the end, ...)
;   gfx.chr     - 8 KB CHR (RetroBake's own art, builders/nes_gfx.py)
; User text reaches the ROM only as tile numbers inside title.bin.
;
; levels.bin layout (see builders/nes.py: level_blob):
;   $8000 count, combat, flags, max_hp, start_lives
;   $8010 + 16*i: map_page, cols, lflags, time_lo, time_hi, sx, sy, gx, gy, setting,
;                 obj_lo, obj_hi, obj_count
;   maps: 16 bytes per column (12 rows + 4 pad), column c at page+(c>>4), offset (c&15)<<4

PPUCTRL   = $2000
PPUMASK   = $2001
PPUSTATUS = $2002
OAMADDR   = $2003
PPUSCROLL = $2005
PPUADDR   = $2006
PPUDATA   = $2007
DMC_FREQ  = $4010
OAMDMA    = $4014
JOY1      = $4016
APU_FRAME = $4017

SIG       = $07FC     ; qa rom-boot-signature: 'R' 'B' 1 state
OAM       = $0200
CTRL_BASE = %10001000 ; NMI on, sprites from $1000, background from $0000

LEVELS     = $8000
CFG_COUNT  = LEVELS+0
CFG_COMBAT = LEVELS+1
CFG_FLAGS  = LEVELS+2
CFG_MAXHP  = LEVELS+3
CFG_LIVES  = LEVELS+4
LEVEL_TAB  = LEVELS+16

F_HEARTS = 1
F_LIVES  = 2
F_COINS  = 4
F_TIMER  = 8
COMBAT_STOMP = 0
COMBAT_MELEE = 1
COMBAT_SHOT  = 2

BTN_A      = $80
BTN_B      = $40
BTN_START  = $10
BTN_LEFT   = $02
BTN_RIGHT  = $01

T_PLATFORM = 4
T_SPIKES   = 5
T_DOOR     = 6

K_WALKER = 1
K_HOPPER = 2
K_FLYER  = 3
K_COIN   = 4
K_HEART  = 5
K_LIFE   = 6
K_KEY    = 7
K_BOSS   = 8
K_SHOP   = 9

ACCEL   = 3           ; 1/16 px per frame per frame
FRICT   = 2
MAXV    = 40          ; 2.5 px/frame
GRAV    = 5
MAXFALL = 96
JUMPV   = 100         ; 6.25 px/frame -> about 3.9 tiles high, 6 tiles long
CUTV    = 32

MAXOBJ  = 40
obj_kind = $0300
obj_xl   = $0328
obj_xh   = $0350
obj_y    = $0378
obj_st   = $03A0      ; 0 gone, 1 alive moving left, 2 alive moving right
obj_t    = $03C8      ; timer / phase
obj_base = $03F0      ; home y for hoppers and flyers
obj_hp   = $0418
col_l    = $0440      ; 24 tiles, left half of a metatile column
col_r    = $0458      ; 24 tiles, right half

.segment "HEADER"
    .byte "NES", $1A, 2, 1, $01, $00
    .res 8, $00

.segment "ZEROPAGE"
frame:     .res 1
busy:      .res 1     ; 1 = main code owns the PPU (rendering off), NMI only counts
mask_sh:   .res 1
ctrl_sh:   .res 1
scroll_x:  .res 1
col_ready: .res 1
col_hi:    .res 1
col_lo:    .res 1
pad:       .res 1
pad_old:   .res 1
pad_new:   .res 1
t0:        .res 1
t1:        .res 1
t2:        .res 1
t3:        .res 1
t4:        .res 1
ptr:       .res 2
mptr:      .res 2
lvptr:     .res 2
tx_lo:     .res 1
tx_hi:     .res 1
ty:        .res 1
o_xl:      .res 1
o_xh:      .res 1
o_y:       .res 1
o_w:       .res 1
o_h:       .res 1
level:     .res 1
lvl_page:  .res 1
lvl_cols:  .res 1
lvl_flags: .res 1
goal_x:    .res 1
goal_y:    .res 1
n_obj:     .res 1
time_lo:   .res 1
time_hi:   .res 1
tframes:   .res 1
maxcam_lo: .res 1
maxcam_hi: .res 1
cam_lo:    .res 1
cam_hi:    .res 1
next_col:  .res 1
hx_lo:     .res 1     ; hero x in 1/16 px
hx_hi:     .res 1
hy_lo:     .res 1     ; hero y in 1/16 px
hy_hi:     .res 1
hpx_lo:    .res 1     ; hero x in px
hpx_hi:    .res 1
hpy:       .res 1     ; hero y in px
prev_py:   .res 1
vx:        .res 1
vy:        .res 1
on_ground: .res 1
facing:    .res 1     ; 0 right, 1 left
moving:    .res 1
hp:        .res 1
lives:     .res 1
coins:     .res 1
has_key:   .res 1
boss_dead: .res 1
invuln:    .res 1
attack:    .res 1
shot_on:   .res 1
shot_lo:   .res 1
shot_hi:   .res 1
shot_y:    .res 1
shot_dir:  .res 1
event:     .res 1     ; 0 none, 1 died, 2 cleared
paused:    .res 1
oam_i:     .res 1
cur:       .res 1     ; current object index
s_x:       .res 1     ; sprite being placed
s_y:       .res 1
s_t:       .res 1
s_a:       .res 1
bt:        .res 1
bflip:     .res 1
brow:      .res 1
bcol:      .res 1

.segment "CODE"

; ================================================================ boot

.proc reset
    sei
    cld
    ldx #$40
    stx APU_FRAME
    ldx #$FF
    txs
    inx
    stx PPUCTRL
    stx PPUMASK
    stx DMC_FREQ
    bit PPUSTATUS
@vb1:
    bit PPUSTATUS
    bpl @vb1
    txa
@clr:
    sta $0000,x
    sta $0100,x
    sta $0200,x
    sta $0300,x
    sta $0400,x
    sta $0500,x
    sta $0600,x
    sta $0700,x
    inx
    bne @clr
@vb2:
    bit PPUSTATUS
    bpl @vb2
    lda #$52
    sta SIG
    lda #$42
    sta SIG+1
    lda #$01
    sta SIG+2
    lda #$00
    sta SIG+3            ; booting
    lda #1
    sta busy
    lda #CTRL_BASE
    sta ctrl_sh
    sta PPUCTRL          ; NMI on from here
    jmp title_screen
.endproc

; ================================================================ NMI

.proc nmi
    pha
    txa
    pha
    tya
    pha
    inc frame
    lda busy
    bne @done
    lda #0
    sta OAMADDR
    lda #>OAM
    sta OAMDMA
    lda col_ready
    beq @scroll
    lda ctrl_sh
    ora #%00000100       ; PPUDATA steps down a column
    sta PPUCTRL
    ldx #0
    lda col_hi
    sta PPUADDR
    lda col_lo
    sta PPUADDR
@left:
    lda col_l,x
    sta PPUDATA
    inx
    cpx #24
    bne @left
    ldx #0
    lda col_hi
    sta PPUADDR
    ldy col_lo
    iny
    sty PPUADDR
@right:
    lda col_r,x
    sta PPUDATA
    inx
    cpx #24
    bne @right
    lda #0
    sta col_ready
@scroll:
    bit PPUSTATUS
    lda scroll_x
    sta PPUSCROLL
    lda #0
    sta PPUSCROLL
    lda ctrl_sh
    sta PPUCTRL
    lda mask_sh
    sta PPUMASK
@done:
    pla
    tay
    pla
    tax
    pla
    rti
.endproc

.proc irq
    rti
.endproc

; ================================================================ helpers

.proc wait_frame
    lda frame
@w:
    cmp frame
    beq @w
    rts
.endproc

.proc read_pad
    lda pad
    sta pad_old
    lda #1
    sta JOY1
    lda #0
    sta JOY1
    ldx #8
@r:
    lda JOY1
    lsr a
    rol pad
    dex
    bne @r
    lda pad_old
    eor #$FF
    and pad
    sta pad_new
    rts
.endproc

; Turn rendering off after the next frame; main code then owns the PPU.
.proc screen_off
    jsr wait_frame
    lda #1
    sta busy
    lda #0
    sta PPUMASK
    sta mask_sh
    rts
.endproc

; Hand the PPU back to the NMI with rendering on.
.proc screen_on
    lda #%00011110
    sta mask_sh
    lda #0
    sta busy
    jmp wait_frame
.endproc

; Clear both nametables (+ attributes) to tile 0 and hide all sprites.
.proc clear_screen
    lda #CTRL_BASE
    sta ctrl_sh
    sta PPUCTRL
    bit PPUSTATUS
    lda #$20
    sta PPUADDR
    lda #$00
    sta PPUADDR
    tax
    ldy #8
@c:
    sta PPUDATA
    inx
    bne @c
    dey
    bne @c
    ; fall through
.endproc
.proc hide_sprites
    lda #$FF
    ldx #0
@h:
    sta OAM,x
    inx
    bne @h
    lda #0
    sta scroll_x
    rts
.endproc

; A = palette set (0 = text screens, 1.. = 1 + setting id)
.proc load_palette
    asl a
    asl a
    tax
    bit PPUSTATUS
    lda #$3F
    sta PPUADDR
    lda #$00
    sta PPUADDR
    ldy #4
@bg:
    lda bg_palettes,x
    sta PPUDATA
    lda bg_palettes+1,x
    sta PPUDATA
    lda bg_palettes+2,x
    sta PPUDATA
    lda bg_palettes+3,x
    sta PPUDATA
    dey
    bne @bg
    ldx #0
@sp:
    lda spr_palettes,x
    sta PPUDATA
    inx
    cpx #16
    bne @sp
    rts
.endproc

; Text records at (ptr): [hi, lo, len, tiles...]..., 0 = end. Rendering must be off.
.proc draw_records
@next:
    ldy #0
    lda (ptr),y
    beq @done
    sta PPUADDR
    iny
    lda (ptr),y
    sta PPUADDR
    iny
    lda (ptr),y
    tax
    iny
@put:
    lda (ptr),y
    sta PPUDATA
    iny
    dex
    bne @put
    tya
    clc
    adc ptr
    sta ptr
    bcc @next
    inc ptr+1
    jmp @next
@done:
    rts
.endproc

; String at (ptr) = [len, tiles...]; centred on nametable row A. Rendering must be off.
.proc print_centred
    sta t0               ; row
    ldy #0
    lda (ptr),y
    sta t1               ; len
    lda #32
    sec
    sbc t1
    lsr a
    sta t2               ; column
    lda t0               ; addr = $2000 + row*32 + col
    lsr a
    lsr a
    lsr a
    ora #$20
    bit PPUSTATUS
    sta PPUADDR
    lda t0
    asl a
    asl a
    asl a
    asl a
    asl a
    ora t2
    sta PPUADDR
    ldx t1
    ldy #1
@p:
    lda (ptr),y
    sta PPUDATA
    iny
    dex
    bne @p
    rts
.endproc

; Wait A frames, or until Start is pressed.
.proc wait_or_start
    sta t4
@w:
    jsr wait_frame
    jsr read_pad
    lda pad_new
    and #BTN_START
    bne @done
    dec t4
    bne @w
@done:
    rts
.endproc

.macro set_ptr label
    lda #<label
    sta ptr
    lda #>label
    sta ptr+1
.endmacro

TILE_0 = 27           ; font tile for "0" (nes_font.CHARSET)

; ================================================================ screens

.proc title_screen
    jsr screen_off
    jsr clear_screen
    lda #0
    jsr load_palette
    set_ptr title_text
    jsr draw_records
    lda #CTRL_BASE
    sta ctrl_sh
    jsr screen_on
    lda #1
    sta SIG+3            ; title screen
@w:
    jsr wait_frame
    jsr read_pad
    lda pad_new
    and #BTN_START
    beq @w
    lda #2
    sta SIG+3            ; gameplay
    lda CFG_LIVES
    sta lives
    lda #0
    sta level
    sta coins
    jmp stage_intro
.endproc

; Text screen with a word and a number: (ptr) word, A = number shown after it, X = row.
.proc word_and_number
    pha
    txa
    jsr print_centred
    pla
    clc
    adc #TILE_0
    sta PPUDATA
    rts
.endproc

.proc stage_intro
    jsr screen_off
    jsr clear_screen
    lda #0
    jsr load_palette
    set_ptr str_stage
    ldx level
    inx
    txa
    ldx #12
    jsr word_and_number
    lda CFG_FLAGS
    and #F_LIVES
    beq @show
    set_ptr str_lives
    lda lives
    cmp #10
    bcc @l
    lda #9
@l:
    ldx #16
    jsr word_and_number
@show:
    jsr screen_on
    lda #120
    jsr wait_or_start
    jmp start_level
.endproc

.proc game_over
    jsr screen_off
    jsr clear_screen
    lda #0
    jsr load_palette
    set_ptr str_gameover
    lda #13
    jsr print_centred
    jsr screen_on
    lda #180
    jsr wait_or_start
    jmp title_screen
.endproc

.proc ending
    jsr screen_off
    jsr clear_screen
    lda #0
    jsr load_palette
    set_ptr str_end
    lda #11
    jsr print_centred
    set_ptr str_thanks
    lda #15
    jsr print_centred
    jsr screen_on
@w:
    jsr wait_frame
    jsr read_pad
    lda pad_new
    and #BTN_START
    beq @w
    jmp title_screen
.endproc

; ================================================================ level setup

.proc start_level
    jsr screen_off
    jsr clear_screen
    lda level
    asl a
    asl a
    asl a
    asl a
    clc
    adc #<LEVEL_TAB
    sta lvptr
    lda #>LEVEL_TAB
    adc #0
    sta lvptr+1
    ldy #0
    lda (lvptr),y
    sta lvl_page
    iny
    lda (lvptr),y
    sta lvl_cols
    iny
    lda (lvptr),y
    sta lvl_flags
    iny
    lda (lvptr),y
    sta time_lo
    iny
    lda (lvptr),y
    sta time_hi
    iny
    lda (lvptr),y
    sta hx_hi            ; hero x = sx * 16 px = sx * 256 sixteenths
    iny
    lda (lvptr),y
    sta hy_hi
    iny
    lda (lvptr),y
    sta goal_x
    iny
    lda (lvptr),y
    sta goal_y
    lda lvl_cols         ; max camera = cols*16 - 256
    lsr a
    lsr a
    lsr a
    lsr a
    sec
    sbc #1
    sta maxcam_hi
    lda lvl_cols
    asl a
    asl a
    asl a
    asl a
    sta maxcam_lo
    lda #0
    sta hx_lo
    sta hy_lo
    sta vx
    sta vy
    sta on_ground
    sta facing
    sta moving
    sta has_key
    sta boss_dead
    sta invuln
    sta attack
    sta shot_on
    sta event
    sta paused
    sta cam_lo
    sta cam_hi
    sta mptr
    sta col_ready
    lda #60
    sta tframes
    lda CFG_MAXHP
    sta hp
    jsr calc_hero_px
    jsr load_objects
    lda #0
    sta next_col
@col:
    jsr build_column
    jsr write_column_now
    inc next_col
    lda next_col
    cmp #17
    beq @cols_done
    cmp lvl_cols
    bcc @col
@cols_done:
    ldy #9
    lda (lvptr),y
    clc
    adc #1
    jsr load_palette
    lda #CTRL_BASE
    sta ctrl_sh
    jsr draw_sprites
    jsr screen_on
    jmp play_loop
.endproc

.proc load_objects
    ldy #10
    lda (lvptr),y
    sta ptr
    iny
    lda (lvptr),y
    sta ptr+1
    iny
    lda (lvptr),y
    sta n_obj
    ldx #0
    ldy #0
@obj:
    cpx n_obj
    bcs @rest
    lda (ptr),y
    sta obj_kind,x
    iny
    lda (ptr),y
    pha
    asl a
    asl a
    asl a
    asl a
    sta obj_xl,x
    pla
    lsr a
    lsr a
    lsr a
    lsr a
    sta obj_xh,x
    iny
    lda (ptr),y
    asl a
    asl a
    asl a
    asl a
    sta obj_y,x
    sta obj_base,x
    iny
    lda #1
    sta obj_st,x
    sta obj_hp,x
    txa
    asl a
    asl a
    asl a
    sta obj_t,x
    lda obj_kind,x
    cmp #K_BOSS
    bne @next
    lda obj_y,x          ; boss (x, y) is its bottom-left metatile
    sec
    sbc #16
    sta obj_y,x
    lda #3
    sta obj_hp,x
    lda #0
    sta obj_t,x
@next:
    inx
    jmp @obj
@rest:
    cpx #MAXOBJ
    bcs @done
    lda #0
    sta obj_kind,x
    sta obj_st,x
    inx
    bne @rest
@done:
    rts
.endproc

; Fill col_l/col_r with the tiles of metatile column next_col and set col_hi/col_lo.
.proc build_column
    lda next_col
    lsr a
    lsr a
    lsr a
    lsr a
    pha
    and #1
    asl a
    asl a
    ora #$20
    sta col_hi
    pla
    clc
    adc lvl_page
    sta mptr+1
    lda next_col
    and #15
    asl a
    sta col_lo
    lda next_col
    asl a
    asl a
    asl a
    asl a
    tay
    ldx #0
@row:
    lda (mptr),y
    beq @empty
    asl a
    asl a
    clc
    adc #60              ; metatile t uses tiles 64+4*(t-1) .. +3
    sta col_l,x
    adc #1
    sta col_r,x
    adc #1
    sta col_l+1,x
    adc #1
    sta col_r+1,x
    jmp @nx
@empty:
    sta col_l,x
    sta col_r,x
    sta col_l+1,x
    sta col_r+1,x
@nx:
    iny
    inx
    inx
    cpx #24
    bne @row
    rts
.endproc

; Write the built column straight to the PPU (rendering must be off).
.proc write_column_now
    lda ctrl_sh
    ora #%00000100
    sta PPUCTRL
    bit PPUSTATUS
    lda col_hi
    sta PPUADDR
    lda col_lo
    sta PPUADDR
    ldx #0
@l:
    lda col_l,x
    sta PPUDATA
    inx
    cpx #24
    bne @l
    lda col_hi
    sta PPUADDR
    ldy col_lo
    iny
    sty PPUADDR
    ldx #0
@r:
    lda col_r,x
    sta PPUDATA
    inx
    cpx #24
    bne @r
    lda ctrl_sh
    sta PPUCTRL
    rts
.endproc

; ================================================================ main loop

.proc play_loop
@loop:
    jsr wait_frame
    jsr read_pad
    lda pad_new
    and #BTN_START
    beq @np
    lda paused
    eor #1
    sta paused
@np:
    lda paused
    bne @loop
    jsr update_hero
    jsr update_objects
    jsr update_shot
    jsr update_camera
    jsr update_timer
    jsr draw_sprites
    lda event
    beq @loop
    cmp #2
    beq @cleared
    lda CFG_FLAGS        ; lost a life
    and #F_LIVES
    beq @retry
    dec lives
    bne @retry
    jmp game_over
@retry:
    lda #45
    jsr wait_or_start
    jmp stage_intro
@cleared:
    lda #45
    jsr wait_or_start
    inc level
    lda level
    cmp CFG_COUNT
    bcc @more
    jmp ending
@more:
    jmp stage_intro
.endproc

.proc update_camera
    lda hpx_lo           ; target = hero x - 112, never moves left
    sec
    sbc #112
    sta t0
    lda hpx_hi
    sbc #0
    sta t1
    bmi @scroll
    lda t0
    cmp cam_lo
    lda t1
    sbc cam_hi
    bcc @scroll
    lda t0
    cmp maxcam_lo
    lda t1
    sbc maxcam_hi
    bcc @set
    lda maxcam_lo
    sta t0
    lda maxcam_hi
    sta t1
@set:
    lda t0
    sta cam_lo
    lda t1
    sta cam_hi
@scroll:
    lda cam_lo
    sta scroll_x
    lda cam_hi
    and #1
    ora #CTRL_BASE
    sta ctrl_sh
    lda col_ready
    bne @done
    lda next_col
    cmp lvl_cols
    bcs @done
    lda cam_hi           ; draw next column once it is within 16 columns of the camera
    asl a
    asl a
    asl a
    asl a
    sta t0
    lda cam_lo
    lsr a
    lsr a
    lsr a
    lsr a
    ora t0
    clc
    adc #16
    cmp next_col
    bcc @done
    jsr build_column
    inc next_col
    lda #1
    sta col_ready
@done:
    rts
.endproc

.proc update_timer
    lda time_lo
    ora time_hi
    beq @done
    dec tframes
    bne @done
    lda #60
    sta tframes
    lda time_lo
    sec
    sbc #1
    sta time_lo
    lda time_hi
    sbc #0
    sta time_hi
    ora time_lo
    bne @done
    lda #1
    sta event            ; out of time
@done:
    rts
.endproc

; ================================================================ map + collision

; hpx = hx / 16, hpy = hy / 16
.proc calc_hero_px
    lda hx_hi
    sta hpx_hi
    lda hx_lo
    lsr hpx_hi
    ror a
    lsr hpx_hi
    ror a
    lsr hpx_hi
    ror a
    lsr hpx_hi
    ror a
    sta hpx_lo
    lda hy_hi
    asl a
    asl a
    asl a
    asl a
    sta t0
    lda hy_lo
    lsr a
    lsr a
    lsr a
    lsr a
    ora t0
    sta hpy
    rts
.endproc

.proc set_hx_from_px
    lda hpx_hi
    asl a
    asl a
    asl a
    asl a
    sta hx_hi
    lda hpx_lo
    lsr a
    lsr a
    lsr a
    lsr a
    ora hx_hi
    sta hx_hi
    lda hpx_lo
    asl a
    asl a
    asl a
    asl a
    sta hx_lo
    rts
.endproc

.proc set_hy_from_py
    lda hpy
    lsr a
    lsr a
    lsr a
    lsr a
    sta hy_hi
    lda hpy
    asl a
    asl a
    asl a
    asl a
    sta hy_lo
    rts
.endproc

; Tile at pixel (tx_hi:tx_lo, ty). Below the map = air, outside the sides = block.
; Clobbers Y and t3.
.proc tile_at
    lda ty
    cmp #192
    bcs @air
    lda tx_hi
    cmp #8
    bcs @wall
    asl a
    asl a
    asl a
    asl a
    sta t3
    lda tx_lo
    lsr a
    lsr a
    lsr a
    lsr a
    ora t3
    cmp lvl_cols
    bcs @wall
    sta t3
    lsr a
    lsr a
    lsr a
    lsr a
    clc
    adc lvl_page
    sta mptr+1
    lda t3
    asl a
    asl a
    asl a
    asl a
    sta t3
    lda ty
    lsr a
    lsr a
    lsr a
    lsr a
    ora t3
    tay
    lda (mptr),y
    rts
@air:
    lda #0
    rts
@wall:
    lda #3
    rts
.endproc

; A = tile -> A = 1 if solid (doors open once you hold the key). Clobbers Y.
.proc is_solid
    cmp #T_DOOR
    bne @t
    lda has_key
    eor #1
    rts
@t:
    tay
    lda solid_tab,y
    rts
.endproc

; A = tile -> A = 1 if you can stand on it.
.proc is_support
    cmp #T_PLATFORM
    bne is_solid
    lda #1
    rts
.endproc

; A = tile -> carry set if it blocks the hero; spikes also hurt.
.proc check_block
    cmp #T_SPIKES
    bne @s
    jsr hurt_hero
    lda #T_SPIKES
@s:
    jsr is_solid
    cmp #1
    rts
.endproc

; Side probe at x = tx, rows hpy+2 and hpy+13. Carry set if blocked.
.proc probe_side
    lda hpy
    clc
    adc #2
    sta ty
    jsr tile_at
    jsr check_block
    bcs @yes
    lda hpy
    clc
    adc #13
    sta ty
    jsr tile_at
    jmp check_block
@yes:
    rts
.endproc

; Floor probe at (tx, ty = hpy+16). Carry set if the hero lands here.
.proc probe_floor
    jsr tile_at
    cmp #T_PLATFORM
    bne @solid
    lda ty               ; one-way: only when last frame's feet were above its top
    and #$F0
    sta t0
    lda prev_py
    clc
    adc #15
    cmp t0
    bcs @no              ; feet were already at or below its top: pass through
    sec
    rts
@no:
    clc
    rts
@solid:
    jmp check_block
.endproc

.macro probe_x offset
    lda hpx_lo
    clc
    adc #offset
    sta tx_lo
    lda hpx_hi
    adc #0
    sta tx_hi
.endmacro

; ================================================================ hero

.proc update_hero
    lda invuln
    beq @i
    dec invuln
@i:
    lda attack
    beq @a
    dec attack
@a:
    lda #0
    sta moving
    lda pad
    and #BTN_RIGHT
    beq @notr
    lda #0
    sta facing
    lda #1
    sta moving
    lda vx
    clc
    adc #ACCEL
    bmi @sv
    cmp #MAXV
    bcc @sv
    lda #MAXV
    jmp @sv
@notr:
    lda pad
    and #BTN_LEFT
    beq @fric
    lda #1
    sta facing
    sta moving
    lda vx
    sec
    sbc #ACCEL
    bpl @sv
    cmp #256-MAXV
    bcs @sv
    lda #256-MAXV
    jmp @sv
@fric:
    lda vx
    beq @sv
    bmi @fneg
    sec
    sbc #FRICT
    bpl @sv
    lda #0
    jmp @sv
@fneg:
    clc
    adc #FRICT
    bmi @sv
    lda #0
@sv:
    sta vx
    ; ---- move x
    ldx #0
    ora #0
    bpl @px
    dex
@px:
    clc
    adc hx_lo
    sta hx_lo
    txa
    adc hx_hi
    sta hx_hi
    bmi @clampl
    jsr calc_hero_px
    lda hpx_lo
    cmp cam_lo
    lda hpx_hi
    sbc cam_hi
    bcs @hcol
@clampl:
    lda cam_lo
    sta hpx_lo
    lda cam_hi
    sta hpx_hi
    jsr set_hx_from_px
    lda #0
    sta vx
    jsr calc_hero_px
@hcol:
    lda vx
    beq @vert
    bmi @hleft
    probe_x 13
    jsr probe_side
    bcc @vert
    lda tx_lo
    and #$F0
    sec
    sbc #14
    sta hpx_lo
    lda tx_hi
    sbc #0
    sta hpx_hi
    jmp @stopx
@hleft:
    probe_x 2
    jsr probe_side
    bcc @vert
    lda tx_lo
    and #$F0
    clc
    adc #14
    sta hpx_lo
    lda tx_hi
    adc #0
    sta hpx_hi
@stopx:
    jsr set_hx_from_px
    lda #0
    sta vx
@vert:
    ; ---- jump, variable height, gravity
    lda pad_new
    and #BTN_A
    beq @nj
    lda on_ground
    beq @nj
    lda #256-JUMPV
    sta vy
    lda #0
    sta on_ground
@nj:
    lda pad
    and #BTN_A
    bne @grav
    lda vy
    bpl @grav
    cmp #256-CUTV
    bcs @grav
    lda #256-CUTV
    sta vy
@grav:
    lda vy
    clc
    adc #GRAV
    bmi @svy
    cmp #MAXFALL
    bcc @svy
    lda #MAXFALL
@svy:
    sta vy
    lda hpy
    sta prev_py
    lda vy
    ldx #0
    ora #0
    bpl @py
    dex
@py:
    clc
    adc hy_lo
    sta hy_lo
    txa
    adc hy_hi
    sta hy_hi
    bpl @inmap
    lda #0               ; bumped the top of the map
    sta hy_lo
    sta hy_hi
    sta vy
@inmap:
    jsr calc_hero_px
    lda vy
    bmi @up
    lda hpy              ; falling or standing: probe one pixel below the feet
    clc
    adc #16
    sta ty
    probe_x 3
    jsr probe_floor
    bcs @land
    probe_x 12
    jsr probe_floor
    bcs @land
    lda #0
    sta on_ground
    jmp @after
@land:
    lda ty
    and #$F0
    sec
    sbc #16
    sta hpy
    jsr set_hy_from_py
    lda #0
    sta vy
    lda #1
    sta on_ground
    jmp @after
@up:
    lda hpy
    sta ty
    probe_x 3
    jsr tile_at
    jsr check_block
    bcs @bonk
    probe_x 12
    jsr tile_at
    jsr check_block
    bcc @after
@bonk:
    lda hpy
    and #$F0
    clc
    adc #16
    sta hpy
    jsr set_hy_from_py
    lda #0
    sta vy
@after:
    lda hpy
    cmp #200
    bcc @goal
    lda #1
    sta event            ; fell into a pit
    rts
@goal:
    lda lvl_flags
    and #1
    beq @g
    lda boss_dead
    beq @r
@g:
    lda goal_x
    asl a
    asl a
    asl a
    asl a
    sta o_xl
    lda goal_x
    lsr a
    lsr a
    lsr a
    lsr a
    sta o_xh
    lda goal_y
    asl a
    asl a
    asl a
    asl a
    sta o_y
    lda #16
    sta o_w
    sta o_h
    jsr hit_test
    bcc @r
    lda #2
    sta event            ; reached the goal
@r:
    rts
.endproc

.proc hurt_hero
    lda invuln
    bne @r
    lda event
    bne @r
    dec hp
    beq @dead
    lda #90
    sta invuln
    lda #256-40
    sta vy
    rts
@dead:
    lda #1
    sta event
@r:
    rts
.endproc

; Hero box (hpx+2, hpy+1, 12x14) vs object box (o_x+2, o_y+2, o_w-4 x o_h-4).
; Carry set on overlap. Clobbers t0-t2.
.proc hit_test
    lda o_xl
    sec
    sbc hpx_lo
    sta t0
    lda o_xh
    sbc hpx_hi
    sta t1
    lda t0
    clc
    adc o_w
    sta t0
    lda t1
    adc #0
    sta t1
    lda t0
    sec
    sbc #4
    sta t0
    lda t1
    sbc #0
    bne @no
    lda o_w
    clc
    adc #8
    sta t2
    lda t0
    cmp t2
    bcs @no
    lda o_y
    sec
    sbc hpy
    sta t0
    lda #0
    sbc #0
    sta t1
    lda t0
    clc
    adc o_h
    sta t0
    lda t1
    adc #0
    sta t1
    lda t0
    sec
    sbc #3
    sta t0
    lda t1
    sbc #0
    bne @no
    lda o_h
    clc
    adc #10
    sta t2
    lda t0
    cmp t2
    bcs @no
    sec
    rts
@no:
    clc
    rts
.endproc

; ================================================================ objects

.proc update_objects
    ldx #0
@loop:
    stx cur
    lda obj_st,x
    beq @next
    lda obj_xl,x         ; only objects near the screen move or touch
    sec
    sbc cam_lo
    sta t0
    lda obj_xh,x
    sbc cam_hi
    beq @act
    cmp #1
    bne @left
    lda t0
    cmp #48
    bcc @act
    jmp @next
@left:
    cmp #$FF
    bne @next
    lda t0
    cmp #$C0
    bcc @next
@act:
    lda obj_kind,x
    jsr behave
    ldx cur
    jsr touch
@next:
    ldx cur
    inx
    cpx #MAXOBJ
    bne @loop
    rts
.endproc

; A = kind, X = object.
.proc behave
    cmp #K_WALKER
    bne @h
    lda frame
    and #1
    beq @r
    lda #16
    sta o_w
    jmp walk_step
@h:
    cmp #K_HOPPER
    bne @f
    inc obj_t,x
    lda obj_t,x
    and #63
    tay
    lda obj_base,x
    sec
    sbc hop_tab,y
    sta obj_y,x
    rts
@f:
    cmp #K_FLYER
    bne @b
    lda frame
    clc
    adc obj_t,x
    and #63
    tay
    lda obj_base,x
    clc
    adc wave_tab,y
    sta obj_y,x
    rts
@b:
    cmp #K_BOSS
    bne @r
    lda obj_t,x
    beq @bm
    dec obj_t,x
@bm:
    lda #32
    sta o_w
    jmp walk_step
@r:
    rts
.endproc

; Walk one pixel, turning at walls and ledges. X = object, o_w = its width.
.proc walk_step
    lda obj_st,x
    cmp #2
    beq @right
    lda obj_xl,x
    sec
    sbc #1
    sta tx_lo
    lda obj_xh,x
    sbc #0
    sta tx_hi
    jmp @probe
@right:
    lda obj_xl,x
    clc
    adc o_w
    sta tx_lo
    lda obj_xh,x
    adc #0
    sta tx_hi
@probe:
    lda obj_y,x
    clc
    adc o_w
    sec
    sbc #8
    sta ty
    jsr tile_at
    jsr is_solid
    ldx cur
    cmp #0
    bne @turn
    lda obj_y,x
    clc
    adc o_w
    sta ty
    jsr tile_at
    jsr is_support
    ldx cur
    cmp #0
    beq @turn
    lda obj_st,x
    cmp #2
    beq @mr
    lda obj_xl,x
    bne @dl
    dec obj_xh,x
@dl:
    dec obj_xl,x
    rts
@mr:
    inc obj_xl,x
    bne @r
    inc obj_xh,x
@r:
    rts
@turn:
    lda obj_st,x
    eor #3
    sta obj_st,x
    rts
.endproc

; Carry set for enemies (walker, hopper, flyer, boss).
.proc is_enemy
    cmp #K_COIN
    bcc @yes
    cmp #K_BOSS
    beq @yes
    clc
    rts
@yes:
    sec
    rts
.endproc

; Hero (and weapon) contact with object X.
.proc touch
    lda obj_xl,x
    sta o_xl
    lda obj_xh,x
    sta o_xh
    lda obj_y,x
    sta o_y
    lda #16
    sta o_w
    sta o_h
    lda obj_kind,x
    cmp #K_BOSS
    bne @sz
    lda #32
    sta o_w
    sta o_h
@sz:
    lda obj_kind,x
    jsr is_enemy
    bcc @pick
    jsr weapon_hits
    ldx cur
    lda obj_st,x
    beq @r
    jsr hit_test
    ldx cur
    bcc @r
    lda CFG_COMBAT
    cmp #COMBAT_STOMP
    bne @ouch
    lda vy               ; falling onto its head = stomp
    bmi @ouch
    beq @ouch
    lda hpy
    clc
    adc #8
    cmp o_y
    bcs @ouch
    jsr damage
    lda #256-60
    sta vy
    rts
@ouch:
    jmp hurt_hero
@pick:
    jsr hit_test
    ldx cur
    bcc @r
    lda obj_kind,x
    cmp #K_COIN
    bne @heart
    lda coins
    cmp #99
    bcs @gone
    inc coins
    jmp @gone
@heart:
    cmp #K_HEART
    bne @life
    lda hp
    cmp CFG_MAXHP
    bcs @gone
    inc hp
    jmp @gone
@life:
    cmp #K_LIFE
    bne @key
    lda lives
    cmp #99
    bcs @gone
    inc lives
    jmp @gone
@key:
    cmp #K_KEY
    bne @shop
    lda #1
    sta has_key
@gone:
    lda #0
    sta obj_st,x
@r:
    rts
@shop:
    cmp #K_SHOP          ; press Up at the shop: 10 coins for a heart (or a life)
    bne @r
    lda pad_new
    and #$08
    beq @r
    lda coins
    cmp #10
    bcc @r
    lda hp
    cmp CFG_MAXHP
    bcc @buyhp
    lda CFG_FLAGS
    and #F_LIVES
    beq @r
    lda lives
    cmp #99
    bcs @r
    inc lives
    jmp @pay
@buyhp:
    inc hp
@pay:
    lda coins
    sec
    sbc #10
    sta coins
    rts
.endproc

; Sword or shot against object X (o_* already set).
.proc weapon_hits
    lda CFG_COMBAT
    cmp #COMBAT_MELEE
    bne @shot
    lda attack
    beq @r
    lda hpx_lo
    pha
    lda hpx_hi
    pha
    lda facing
    bne @l
    lda hpx_lo
    clc
    adc #14
    sta hpx_lo
    lda hpx_hi
    adc #0
    sta hpx_hi
    jmp @t
@l:
    lda hpx_lo
    sec
    sbc #14
    sta hpx_lo
    lda hpx_hi
    sbc #0
    sta hpx_hi
@t:
    jsr hit_test
    pla
    sta hpx_hi
    pla
    sta hpx_lo
    bcc @r
    ldx cur
    jmp damage
@shot:
    cmp #COMBAT_SHOT
    bne @r
    lda shot_on
    beq @r
    lda hpx_lo
    pha
    lda hpx_hi
    pha
    lda hpy
    pha
    lda shot_lo
    sec
    sbc #4
    sta hpx_lo
    lda shot_hi
    sbc #0
    sta hpx_hi
    lda shot_y
    sec
    sbc #4
    sta hpy
    jsr hit_test
    pla
    sta hpy
    pla
    sta hpx_hi
    pla
    sta hpx_lo
    bcc @r
    lda #0
    sta shot_on
    ldx cur
    jmp damage
@r:
    rts
.endproc

.proc damage
    lda obj_kind,x
    cmp #K_BOSS
    bne @kill
    lda obj_t,x          ; boss: 3 hits, short break between hits
    bne @r
    lda #45
    sta obj_t,x
    dec obj_hp,x
    bne @r
    lda #1
    sta boss_dead
@kill:
    lda #0
    sta obj_st,x
@r:
    rts
.endproc

.proc update_shot
    lda CFG_COMBAT
    cmp #COMBAT_MELEE
    bne @s
    lda pad_new
    and #BTN_B
    beq @r
    lda attack
    bne @r
    lda #12
    sta attack
    rts
@s:
    cmp #COMBAT_SHOT
    bne @r
    lda pad_new
    and #BTN_B
    beq @move
    lda shot_on
    bne @move
    lda #1
    sta shot_on
    lda facing
    sta shot_dir
    lda hpx_lo
    clc
    adc #4
    sta shot_lo
    lda hpx_hi
    adc #0
    sta shot_hi
    lda hpy
    clc
    adc #5
    sta shot_y
@move:
    lda shot_on
    beq @r
    lda shot_dir
    bne @left
    lda shot_lo
    clc
    adc #4
    sta shot_lo
    bcc @chk
    inc shot_hi
    jmp @chk
@left:
    lda shot_lo
    sec
    sbc #4
    sta shot_lo
    bcs @chk
    dec shot_hi
@chk:
    lda shot_lo
    sec
    sbc cam_lo
    lda shot_hi
    sbc cam_hi
    bne @off
    lda shot_lo
    clc
    adc #4
    sta tx_lo
    lda shot_hi
    adc #0
    sta tx_hi
    lda shot_y
    clc
    adc #4
    sta ty
    jsr tile_at
    jsr is_solid
    beq @r
@off:
    lda #0
    sta shot_on
@r:
    rts
.endproc

; ================================================================ sprites

; One 8x8 sprite at (s_x, s_y) with tile s_t, attributes s_a. Keeps X.
.proc put1
    ldy oam_i
    cpy #252
    bcs @r
    lda s_y
    sec
    sbc #1
    sta OAM,y
    lda s_t
    sta OAM+1,y
    lda s_a
    sta OAM+2,y
    lda s_x
    sta OAM+3,y
    tya
    clc
    adc #4
    sta oam_i
@r:
    rts
.endproc

; 16x16 metasprite: tiles s_t..s_t+3 (TL TR BL BR), flipped when s_a bit 6 is set. Keeps X.
.proc meta16
    lda s_t
    sta bt
    lda s_a
    and #$40
    beq @n
    lda #1
@n:
    sta bflip
    lda bt
    clc
    adc bflip
    sta s_t
    jsr put1
    lda s_x
    clc
    adc #8
    sta s_x
    lda bflip
    eor #1
    clc
    adc bt
    sta s_t
    jsr put1
    lda s_y
    clc
    adc #8
    sta s_y
    lda bflip
    eor #1
    clc
    adc bt
    adc #2
    sta s_t
    jsr put1
    lda s_x
    sec
    sbc #8
    sta s_x
    lda bt
    clc
    adc bflip
    adc #2
    sta s_t
    jsr put1
    lda s_y
    sec
    sbc #8
    sta s_y
    rts
.endproc

.proc draw_sprites
    lda #0
    sta oam_i
    lda invuln           ; hero blinks while invulnerable
    and #4
    bne @nohero
    lda hpx_lo
    sec
    sbc cam_lo
    sta s_x
    lda hpy
    sta s_y
    lda #64
    sta s_t
    lda on_ground
    beq @pose
    lda moving
    beq @face
    lda frame
    and #8
    beq @face
@pose:
    lda #68
    sta s_t
@face:
    lda #0
    ldx facing
    beq @fa
    lda #$40
@fa:
    sta s_a
    jsr meta16
    lda attack           ; sword
    beq @nohero
    lda s_x
    ldx facing
    bne @swl
    clc
    adc #16
    jmp @sw
@swl:
    sec
    sbc #8
@sw:
    sta s_x
    lda s_y
    clc
    adc #4
    sta s_y
    lda #129
    sta s_t
    jsr put1
@nohero:
    lda shot_on
    beq @noshot
    lda shot_lo
    sec
    sbc cam_lo
    sta s_x
    lda shot_y
    sta s_y
    lda #124
    sta s_t
    lda #3
    sta s_a
    jsr put1
@noshot:
    lda goal_x           ; goal flag
    lsr a
    lsr a
    lsr a
    lsr a
    sta t1
    lda goal_x
    asl a
    asl a
    asl a
    asl a
    sec
    sbc cam_lo
    sta s_x
    lda t1
    sbc cam_hi
    bne @objs
    lda s_x
    cmp #241
    bcs @objs
    lda goal_y
    asl a
    asl a
    asl a
    asl a
    sta s_y
    lda #120
    sta s_t
    lda #2
    sta s_a
    jsr meta16
@objs:
    lda frame            ; alternate order so crowded lines flicker instead of vanishing
    and #1
    beq @fwd
    ldx #MAXOBJ-1
@back:
    jsr draw_obj
    dex
    bpl @back
    jmp @hud
@fwd:
    ldx #0
@fl:
    jsr draw_obj
    inx
    cpx #MAXOBJ
    bne @fl
@hud:
    jsr draw_hud
    ldx oam_i
    lda #$FF
@hide:
    sta OAM,x
    inx
    inx
    inx
    inx
    bne @hide
    rts
.endproc

; Draw object X if it is on screen. Keeps X.
.proc draw_obj
    lda obj_st,x
    beq @r
    lda obj_xl,x
    sec
    sbc cam_lo
    sta s_x
    lda obj_xh,x
    sbc cam_hi
    bne @r
    lda obj_y,x
    sta s_y
    ldy obj_kind,x
    lda kind_tile,y
    sta s_t
    lda kind_attr,y
    sta s_a
    cpy #K_BOSS
    beq @boss
    lda s_x
    cmp #241
    bcs @r
    jmp meta16
@boss:
    lda s_x
    cmp #225
    bcs @r
    lda obj_t,x          ; blink after a hit
    and #4
    bne @r
    lda #0
    sta brow
@row:
    lda #0
    sta bcol
@col:
    jsr put1
    inc s_t
    lda s_x
    clc
    adc #8
    sta s_x
    inc bcol
    lda bcol
    cmp #4
    bne @col
    lda s_x
    sec
    sbc #32
    sta s_x
    lda s_y
    clc
    adc #8
    sta s_y
    inc brow
    lda brow
    cmp #4
    bne @row
@r:
    rts
.endproc

.proc draw_hud
    lda #208
    sta s_y
    lda #16
    sta s_x
    lda #3
    sta s_a
    lda CFG_FLAGS
    and #F_HEARTS
    beq @lives
    lda #126
    jsr hud_icon
    lda hp
    jsr hud_num2
@lives:
    lda CFG_FLAGS
    and #F_LIVES
    beq @coins
    lda #127
    jsr hud_icon
    lda lives
    jsr hud_num2
@coins:
    lda CFG_FLAGS
    and #F_COINS
    beq @line2
    lda #125
    jsr hud_icon
    lda coins
    jsr hud_num2
@line2:
    lda #220
    sta s_y
    lda #16
    sta s_x
    lda has_key
    beq @time
    lda #128
    jsr hud_icon
@time:
    lda time_lo
    ora time_hi
    beq @r
    lda #200
    sta s_x
    jsr hud_time
@r:
    rts
.endproc

.proc hud_icon
    sta s_t
    jsr put1
    lda s_x
    clc
    adc #10
    sta s_x
    rts
.endproc

.proc hud_digit
    clc
    adc #TILE_0
    sta s_t
    jsr put1
    lda s_x
    clc
    adc #8
    sta s_x
    rts
.endproc

; A = 0-99, shown as 1 or 2 digits.
.proc hud_num2
    ldx #0
@l:
    cmp #10
    bcc @d
    sbc #10
    inx
    bne @l
@d:
    pha
    txa
    beq @u
    jsr hud_digit
@u:
    pla
    jsr hud_digit
    lda s_x
    clc
    adc #6
    sta s_x
    rts
.endproc

; time_hi:time_lo seconds (capped at 999), 3 digits.
.proc hud_time
    lda time_lo
    sta t0
    lda time_hi
    sta t1
    ldx #0
@h:
    lda t1
    bne @sub
    lda t0
    cmp #100
    bcc @done
@sub:
    lda t0
    sec
    sbc #100
    sta t0
    lda t1
    sbc #0
    sta t1
    inx
    cpx #9
    bne @h
@done:
    txa
    jsr hud_digit
    lda t0
    cmp #100
    bcc @ok
    lda #99
@ok:
    ldx #0
@l:
    cmp #10
    bcc @d
    sbc #10
    inx
    bne @l
@d:
    pha
    txa
    jsr hud_digit
    pla
    jmp hud_digit
.endproc

; ================================================================ data

.segment "RODATA"
solid_tab:
    .byte 0, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1
kind_tile:
    .byte 0, 72, 76, 80, 84, 88, 92, 96, 100, 116
kind_attr:
    .byte 0, 1, 1, 1, 2, 3, 0, 2, 3, 2
hop_tab:
    .byte 0, 4, 8, 11, 14, 16, 18, 20, 22, 23, 23, 24, 24, 23, 23, 22
    .byte 20, 18, 16, 14, 11, 8, 4, 0
    .res 40, 0
wave_tab:
    .byte 0, 1, 2, 3, 4, 5, 6, 6, 7, 8, 8, 9, 9, 10, 10, 10
    .byte 10, 10, 10, 10, 9, 9, 8, 8, 7, 6, 6, 5, 4, 3, 2, 1
    .byte 0, <-1, <-2, <-3, <-4, <-5, <-6, <-6, <-7, <-8, <-8, <-9, <-9, <-10, <-10, <-10
    .byte <-10, <-10, <-10, <-10, <-9, <-9, <-8, <-8, <-7, <-6, <-6, <-5, <-4, <-3, <-2, <-1

; Background palettes: set 0 = text screens, then one per setting in catalog order:
; grassland forest castle cave desert ocean ice volcano city space haunted sky
bg_palettes:
    .byte $0F, $30, $10, $00
    .byte $21, $08, $17, $2A
    .byte $1B, $08, $18, $29
    .byte $0F, $00, $10, $27
    .byte $0F, $07, $17, $27
    .byte $31, $17, $27, $38
    .byte $22, $0C, $1C, $37
    .byte $31, $02, $12, $30
    .byte $0F, $06, $16, $27
    .byte $0C, $00, $10, $30
    .byte $0F, $03, $13, $33
    .byte $0F, $08, $13, $23
    .byte $31, $17, $27, $2A
; Sprite palettes: hero, enemies, items, red/white (hearts, boss, HUD text)
spr_palettes:
    .byte $0F, $0F, $12, $36
    .byte $0F, $0F, $17, $27
    .byte $0F, $0F, $28, $38
    .byte $0F, $0F, $16, $30

title_text:
    .incbin "title.bin"
str_stage:
    .incbin "str_stage.bin"
str_lives:
    .incbin "str_lives.bin"
str_gameover:
    .incbin "str_gameover.bin"
str_end:
    .incbin "str_end.bin"
str_thanks:
    .incbin "str_thanks.bin"

.segment "LEVELS"
    .incbin "levels.bin"

.segment "VECTORS"
    .addr nmi, reset, irq

.segment "CHARS"
    .incbin "gfx.chr"
