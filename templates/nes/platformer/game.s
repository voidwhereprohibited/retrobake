; RetroBake NES platformer engine (original RetroBake file).
;
; Data the builder drops next to this fixed code (never code, only bytes):
;   levels.bin - level table, see retrobake.builders.nes_platformer.level_data
;   text.bin   - title-screen text records: [addr_hi, addr_lo, len, tile...]..., then 0
;
; Flip-screen platformer: the hero runs and jumps through each level, one 16-metatile screen
; at a time. Touching the goal moves on to the next level. Spikes or falling restart the
; level. Picking up the key opens doors. Enemies and collectibles are not drawn yet.

.export _main
.import _ppu_off, _ppu_on_all, _ppu_wait_nmi, _pal_all, _oam_clear, _pad_trigger, _pad_state

PPU_ADDR = $2006
PPU_DATA = $2007
OAM_BUF  = $0200
SIG      = $07FC             ; qa boot signature: 'R' 'B' version state

PAD_A     = $80
PAD_START = $10
PAD_LEFT  = $02
PAD_RIGHT = $01

T_EMPTY  = 0
T_BLOCK  = 3
T_PLAT   = 4
T_SPIKES = 5
T_DOOR   = 6

ROWS      = 12
TOP_PX    = 32               ; level row 0 is drawn 32 pixels down the screen
META_BASE = $40              ; first background tile of the metatile graphics
GRAVITY   = 4                ; all speeds in 1/16 pixel per frame
MAX_FALL  = 64
JUMP_VY   = $A8              ; -88: about 3.8 metatiles high, 5.5 long
RUN_SPEED = 2                ; pixels per frame

.segment "ZEROPAGE"
lv_ptr:     .res 2
map_ptr:    .res 2
dict_ptr:   .res 2
lv_count:   .res 1
lv_index:   .res 1
lv_width:   .res 1
start_x:    .res 1
start_y:    .res 1
goal_x:     .res 1
goal_y:     .res 1
key_x:      .res 1
key_y:      .res 1
has_key:    .res 1
hx:         .res 2           ; hero left edge, level pixels
hy_frac:    .res 1
hy:         .res 1           ; hero top edge, level pixels
old_hy:     .res 1
vy:         .res 1
on_ground:  .res 1
facing:     .res 1           ; 0 right, 1 left
screen:     .res 1           ; screen shown now ($FF = none)
pad:        .res 1
padt:       .res 1
tx:         .res 2           ; probe point
ty:         .res 1
trow:       .res 1
tmp:        .res 4

.segment "RODATA"
levels:     .incbin "levels.bin"
title_text: .incbin "text.bin"

palette:
    .byte $21,$30,$17,$0A, $21,$30,$17,$0A, $21,$30,$17,$0A, $21,$30,$17,$0A
    .byte $21,$16,$37,$0F, $21,$28,$30,$0F, $21,$16,$37,$0F, $21,$16,$37,$0F

; 0 = passable, 1 = solid, 2 = solid until the hero has the key
solid_tbl:  .byte 0, 1, 1, 1, 0, 1, 2, 0

.segment "CODE"

_main:
    lda #<palette
    ldx #>palette
    jsr _pal_all
    lda levels
    sta lv_count

title:
    lda #1
    jsr set_sig
    jsr _ppu_off
    jsr _oam_clear
    jsr clear_nametable
    jsr draw_text
    lda #$FF
    sta screen
    jsr _ppu_on_all
@wait:
    jsr _ppu_wait_nmi
    lda #0
    jsr _pad_trigger
    and #PAD_START
    beq @wait

    lda #2
    jsr set_sig
    lda #0
    jsr load_level

game_loop:
    jsr _ppu_wait_nmi
    lda #0
    jsr _pad_trigger
    sta padt
    lda #0
    jsr _pad_state
    sta pad
    jsr move_x
    jsr move_y
    jsr check_hazards
    bcs @dead
    jsr check_pickups
    bcs @next
    jsr show_screen
    jsr draw_sprites
    jmp game_loop
@dead:
    lda lv_index
    jsr load_level
    jmp game_loop
@next:
    ldx lv_index
    inx
    cpx lv_count
    bcc @load
    jmp title                ; all levels done: back to the title screen
@load:
    txa
    jsr load_level
    jmp game_loop

; A = state
set_sig:
    sta SIG+3
    lda #'R'
    sta SIG
    lda #'B'
    sta SIG+1
    lda #1
    sta SIG+2
    rts

; ---------------------------------------------------------------- levels

; A = level number. Points at its data and puts the hero at the start.
load_level:
    sta lv_index
    asl
    tay
    lda levels+1,y
    clc
    adc #<levels
    sta lv_ptr
    lda levels+2,y
    adc #>levels
    sta lv_ptr+1
    ldy #0
@fields:
    lda (lv_ptr),y
    sta lv_width,y           ; width, start x/y, goal x/y, key x/y in that order
    iny
    cpy #7
    bne @fields
    lda lv_ptr               ; column map follows the 8-byte header
    clc
    adc #8
    sta map_ptr
    lda lv_ptr+1
    adc #0
    sta map_ptr+1
    lda map_ptr              ; column dictionary follows the map
    clc
    adc lv_width
    sta dict_ptr
    lda map_ptr+1
    adc #0
    sta dict_ptr+1

    lda #0
    sta has_key
    sta vy
    sta hy_frac
    sta facing
    sta on_ground
    sta hx+1
    lda start_x
    asl
    rol hx+1
    asl
    rol hx+1
    asl
    rol hx+1
    asl
    rol hx+1
    sta hx
    lda start_y
    asl
    asl
    asl
    asl
    sta hy
    lda #$FF
    sta screen
    rts

; Tile at column A, row trow -> A. Outside the level sides is wall; below is empty.
tile_cr:
    cmp lv_width
    bcs @wall
    ldy trow
    cpy #ROWS
    bcs @empty
    tay
    lda (map_ptr),y          ; which unique column
    sta tmp
    asl
    adc tmp                  ; x3 (carry is clear: at most 42 columns)
    asl                      ; x6 bytes per column
    sta tmp
    lda trow
    lsr
    clc
    adc tmp
    tay
    lda (dict_ptr),y         ; two rows per byte, even row in the low nibble
    tax
    lda trow
    and #1
    beq @low
    txa
    lsr
    lsr
    lsr
    lsr
    rts
@low:
    txa
    and #$0F
    rts
@wall:
    lda #T_BLOCK
    rts
@empty:
    lda #T_EMPTY
    rts

; Tile under the probe point (tx, ty) -> A.
tile_at:
    lda ty
    lsr
    lsr
    lsr
    lsr
    sta trow
    lda tx+1
    cmp #8
    bcs @wall
    asl
    asl
    asl
    asl
    sta tmp+1
    lda tx
    lsr
    lsr
    lsr
    lsr
    ora tmp+1
    jmp tile_cr
@wall:
    lda #T_BLOCK
    rts

; tx = hx + A, ty = hy + X
probe:
    clc
    adc hx
    sta tx
    lda hx+1
    adc #0
    sta tx+1
    txa
    clc
    adc hy
    sta ty
    rts

; A = tile -> carry set if the hero can't pass it
is_solid:
    tax
    lda solid_tbl,x
    beq @no
    cmp #2
    bne @yes
    lda has_key
    bne @no
@yes:
    sec
    rts
@no:
    clc
    rts

; Carry set if (A, X) offset from the hero is solid.
solid_probe:
    jsr probe
    jsr tile_at
    jmp is_solid

; ---------------------------------------------------------------- movement

move_x:
    lda pad
    and #PAD_RIGHT
    beq @left
    lda #0
    sta facing
    lda hx
    clc
    adc #RUN_SPEED
    sta hx
    bcc :+
    inc hx+1
:   lda #13
    ldx #2
    jsr solid_probe
    bcs @hit_right
    lda #13
    ldx #15
    jsr solid_probe
    bcc @done
@hit_right:                  ; hx = tile left edge - 14
    lda tx
    and #$F0
    sec
    sbc #14
    sta hx
    lda tx+1
    sbc #0
    sta hx+1
    rts
@left:
    lda pad
    and #PAD_LEFT
    beq @done
    lda #1
    sta facing
    lda hx
    sec
    sbc #RUN_SPEED
    sta hx
    bcs :+
    dec hx+1
:   lda hx+1
    bpl :+
    lda #0                   ; stop at the level's left edge
    sta hx
    sta hx+1
:   lda #2
    ldx #2
    jsr solid_probe
    bcs @hit_left
    lda #2
    ldx #15
    jsr solid_probe
    bcc @done
@hit_left:                   ; hx = tile right edge + 1 - 2
    lda tx
    and #$F0
    clc
    adc #14
    sta hx
    lda tx+1
    adc #0
    sta hx+1
@done:
    rts

move_y:
    lda padt                 ; jump
    and #PAD_A
    beq @gravity
    lda on_ground
    beq @gravity
    lda #JUMP_VY
    sta vy
    lda #0
    sta on_ground
    beq @move
@gravity:
    lda vy
    clc
    adc #GRAVITY
    bmi @set
    cmp #MAX_FALL
    bcc @set
    lda #MAX_FALL
@set:
    sta vy
@move:
    lda hy
    sta old_hy
    lda vy                   ; hy:hy_frac += vy * 16 (signed)
    sta tmp
    ldx #0
    lda vy
    bpl :+
    ldx #$FF
:   stx tmp+1
    ldx #4
:   asl tmp
    rol tmp+1
    dex
    bne :-
    lda hy_frac
    clc
    adc tmp
    sta hy_frac
    lda hy
    adc tmp+1
    sta hy
    lda vy
    bpl @down

    lda hy                   ; moving up
    cmp #224
    bcc :+
    lda #0                   ; jumped above the top of the screen
    sta hy
    sta hy_frac
    sta vy
    rts
:   lda #3
    ldx #2
    jsr solid_probe
    bcs @bump
    lda #12
    ldx #2
    jsr solid_probe
    bcc @air
@bump:
    lda ty
    and #$F0
    clc
    adc #14
    sta hy
    lda #0
    sta hy_frac
    sta vy
@air:
    lda #0
    sta on_ground
    rts

@down:
    lda #3
    jsr land_probe
    bcs @land
    lda #12
    jsr land_probe
    bcc @air
@land:
    lda ty
    and #$F0
    sec
    sbc #16
    sta hy
    lda #0
    sta hy_frac
    sta vy
    lda #1
    sta on_ground
    rts

; Probe just under the feet at hero x + A. Carry set if the hero lands there: solid, or a platform the
; feet were above before this frame's move.
land_probe:
    ldx #16
    jsr probe
    jsr tile_at
    cmp #T_PLAT
    beq @platform
    jmp is_solid
@platform:
    lda old_hy
    clc
    adc #15
    and #$F0
    sta tmp
    lda ty
    and #$F0
    cmp tmp
    beq @no
    bcc @no
    sec
    rts
@no:
    clc
    rts

; Carry set if the hero touches spikes or fell out of the level.
check_hazards:
    lda hy
    cmp #184
    bcc :+
    cmp #224
    bcs :+
    sec                      ; fell below the bottom row
    rts
:   lda #1
    ldx #8
    jsr spike_probe
    bcs @hurt
    lda #14
    ldx #8
    jsr spike_probe
    bcs @hurt
    lda #8
    ldx #16
    jsr spike_probe
    bcs @hurt
    lda #8
    ldx #1
    jsr spike_probe
@hurt:
    rts

spike_probe:
    jsr probe
    jsr tile_at
    cmp #T_SPIKES
    beq @yes
    clc
    rts
@yes:
    sec
    rts

; Hero centre metatile -> tmp (column), tmp+1 (row)
hero_cell:
    lda hx
    clc
    adc #8
    sta tmp
    lda hx+1
    adc #0
    asl
    asl
    asl
    asl
    sta tmp+1
    lda tmp
    lsr
    lsr
    lsr
    lsr
    ora tmp+1
    sta tmp
    lda hy
    clc
    adc #8
    lsr
    lsr
    lsr
    lsr
    sta tmp+1
    rts

; Picks up the key; carry set when the hero reached the goal.
check_pickups:
    jsr hero_cell
    lda has_key
    bne @goal
    lda tmp
    cmp key_x
    bne @goal
    lda tmp+1
    cmp key_y
    bne @goal
    lda #1                   ; got the key: doors open, redraw the screen
    sta has_key
    lda #$FF
    sta screen
@goal:
    lda tmp
    cmp goal_x
    bne @no
    lda tmp+1
    cmp goal_y
    bne @no
    sec
    rts
@no:
    clc
    rts

; ---------------------------------------------------------------- drawing

; Screen = (hx + 8) / 256. Redraws the background when it changes.
show_screen:
    lda hx
    clc
    adc #8
    lda hx+1
    adc #0
    cmp screen
    bne draw_screen
    rts

; A = screen number
draw_screen:
    sta screen
    jsr _ppu_off
    jsr clear_nametable
    lda #0
    sta trow
@row:
    lda trow                 ; nametable address of the row's top half: $2080 + row * 64
    lsr
    lsr
    clc
    adc #$20
    sta tmp+2
    lda trow
    and #3
    lsr
    ror
    ror
    clc
    adc #$80
    sta tmp+3
    bcc :+
    inc tmp+2
:   lda #0
    sta tmp+1                ; 0 = top half, 2 = bottom half
@half:
    lda tmp+2
    sta PPU_ADDR
    lda tmp+3
    sta PPU_ADDR
    ldx #0
@col:
    txa
    pha
    lda screen
    asl
    asl
    asl
    asl
    sta tmp
    txa
    ora tmp
    jsr tile_cr
    cmp #T_DOOR
    bne :+
    ldx has_key
    beq :+
    lda #T_EMPTY             ; open door
:   asl
    asl
    ora tmp+1
    clc
    adc #META_BASE
    sta PPU_DATA
    clc
    adc #1
    sta PPU_DATA
    pla
    tax
    inx
    cpx #16
    bne @col
    lda tmp+3
    clc
    adc #32
    sta tmp+3
    bcc :+
    inc tmp+2
:   lda tmp+1
    bne :+
    lda #2
    sta tmp+1
    bne @half
:   inc trow
    lda trow
    cmp #ROWS
    bne @row
    jmp _ppu_on_all

clear_nametable:
    lda #$20
    sta PPU_ADDR
    lda #$00
    sta PPU_ADDR
    tax
    ldy #4
:   sta PPU_DATA
    inx
    bne :-
    dey
    bne :-
    rts

draw_text:
    ldy #0
@record:
    lda title_text,y
    beq @done
    sta PPU_ADDR
    iny
    lda title_text,y
    sta PPU_ADDR
    iny
    lda title_text,y
    tax
    iny
@tile:
    lda title_text,y
    sta PPU_DATA
    iny
    dex
    bne @tile
    beq @record
@done:
    rts

; Hero (4 sprites), the key and the goal flag when they are on this screen.
draw_sprites:
    jsr _oam_clear
    lda hx+1                 ; x on screen, held at the edges while the screen flips
    sec
    sbc screen
    beq @onscreen
    bpl @right_edge
    lda #0
    beq @sx
@right_edge:
    lda #240
    bne @sx
@onscreen:
    lda hx
@sx:
    sta tmp
    clc
    adc #8
    sta tmp+1
    lda hy
    clc
    adc #TOP_PX-1
    sta tmp+2
    ldx facing
    lda tmp+2                ; top row
    sta OAM_BUF+0
    sta OAM_BUF+4
    clc
    adc #8
    sta OAM_BUF+8
    sta OAM_BUF+12
    lda tmp
    sta OAM_BUF+3
    sta OAM_BUF+11
    lda tmp+1
    sta OAM_BUF+7
    sta OAM_BUF+15
    lda hero_attr,x
    sta OAM_BUF+2
    sta OAM_BUF+6
    sta OAM_BUF+10
    sta OAM_BUF+14
    lda hero_left,x
    sta OAM_BUF+1
    ora #2
    sta OAM_BUF+9
    lda hero_right,x
    sta OAM_BUF+5
    ora #2
    sta OAM_BUF+13

    lda has_key              ; key
    bne @flag
    lda key_x
    cmp #$FF
    beq @flag
    lsr
    lsr
    lsr
    lsr
    cmp screen
    bne @flag
    lda key_y
    asl
    asl
    asl
    asl
    clc
    adc #TOP_PX+4-1
    sta OAM_BUF+16
    lda #4
    sta OAM_BUF+17
    lda #1
    sta OAM_BUF+18
    lda key_x
    asl
    asl
    asl
    asl
    clc
    adc #4
    sta OAM_BUF+19
@flag:
    lda goal_x
    lsr
    lsr
    lsr
    lsr
    cmp screen
    bne @done
    lda goal_y
    asl
    asl
    asl
    asl
    clc
    adc #TOP_PX-1
    sta OAM_BUF+20
    clc
    adc #8
    sta OAM_BUF+24
    lda #5
    sta OAM_BUF+21
    lda #6
    sta OAM_BUF+25
    lda #1
    sta OAM_BUF+22
    sta OAM_BUF+26
    lda goal_x
    asl
    asl
    asl
    asl
    clc
    adc #4
    sta OAM_BUF+23
    sta OAM_BUF+27
@done:
    rts

hero_attr:  .byte $00, $40
hero_left:  .byte 0, 1       ; tile in the left column (flipped when facing left)
hero_right: .byte 1, 0
