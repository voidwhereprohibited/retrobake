; RetroBake NES platformer engine (original RetroBake file).
;
; Data the builder drops next to this fixed code (never code, only bytes):
;   levels.bin - level table, see retrobake.builders.nes_platformer.level_data
;   text.bin   - title-screen text records: [addr_hi, addr_lo, len, tile...]..., then 0
;
; Side-scrolling platformer. The camera follows the hero; both nametables form a 512-pixel
; ring and each frame streams at most one missing metatile column through neslib's VRAM
; update buffer. Walkers walk and turn at walls and ledges; patrollers pace a short stretch
; and ignore ledges. Jumping on an enemy defeats it when the level allows stomping; any
; other touch, spikes or a fall costs a life and restarts the level. No lives left: title.
; Touching the goal moves on to the next level. Picking up the key opens doors.

.export _main
.import _ppu_off, _ppu_on_all, _ppu_wait_nmi, _pal_all, _oam_clear, _pad_trigger, _pad_state
.import _set_scroll_x, _set_vram_update

PPU_ADDR = $2006
PPU_DATA = $2007
OAM_BUF  = $0200
QA       = $07F0             ; qa block: lives cam_lo cam_hi enemies_alive level hx_lo hx_hi hy
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
BOUNCE_VY = $C8              ; -56: hop after a stomp
RUN_SPEED = 2                ; pixels per frame
LIVES     = 3
MAX_ENEMIES = 8
PATROL    = 3                ; patrollers pace this many columns either side of their start
CAM_LEAD  = 120              ; hero x on screen while the camera follows
FLAG_STOMP = 1
VERT_RUN  = $80              ; neslib update buffer: vertical run
COL_BUF_LEN = 55

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
lv_flags:   .res 1
has_key:    .res 1
hx:         .res 2           ; hero left edge, level pixels
hy_frac:    .res 1
hy:         .res 1           ; hero top edge, level pixels
old_hy:     .res 1
vy:         .res 1
on_ground:  .res 1
facing:     .res 1           ; 0 right, 1 left
cam_x:      .res 2           ; level pixel at the screen's left edge
lives:      .res 1
frame:      .res 1
n_enemies:  .res 1
ei:         .res 1           ; enemy being updated
col_c:      .res 1           ; column being streamed
pad:        .res 1
padt:       .res 1
tx:         .res 2           ; probe point
ty:         .res 1
trow:       .res 1
tmp:        .res 4

.segment "BSS"
col_buf:    .res COL_BUF_LEN ; neslib update buffer: two 24-tile vertical runs, then $FF
nt_col:     .res 32          ; level column held in each nametable column slot ($FF = none)
e_xl:       .res MAX_ENEMIES ; enemy left edge, level pixels
e_xh:       .res MAX_ENEMIES
e_y:        .res MAX_ENEMIES ; enemy top edge
e_kind:     .res MAX_ENEMIES ; 0 walker, 1 patroller
e_dir:      .res MAX_ENEMIES ; 0 right, 1 left
e_alive:    .res MAX_ENEMIES
e_lo:       .res MAX_ENEMIES ; patrol range, columns
e_hi:       .res MAX_ENEMIES

.segment "RODATA"
levels:     .incbin "levels.bin"
title_text: .incbin "text.bin"

palette:
    .byte $21,$30,$17,$0A, $21,$30,$17,$0A, $21,$30,$17,$0A, $21,$30,$17,$0A
    .byte $21,$16,$37,$0F, $21,$28,$30,$0F, $21,$1A,$30,$0F, $21,$16,$30,$0F

; 0 = passable, 1 = solid, 2 = solid until the hero has the key
solid_tbl:  .byte 0, 1, 1, 1, 0, 1, 2, 0

.segment "CODE"

_main:
    lda #<palette
    ldx #>palette
    jsr _pal_all
    lda levels
    sta lv_count
    lda #$FF
    sta col_buf
    lda #<col_buf
    ldx #>col_buf
    jsr _set_vram_update

title:
    lda #1
    jsr set_sig
    jsr _ppu_off
    jsr _oam_clear
    lda #$FF                 ; nothing to stream
    sta col_buf
    lda #0
    tax
    jsr _set_scroll_x
    jsr clear_nametables
    jsr draw_text
    jsr _ppu_on_all
@wait:
    jsr _ppu_wait_nmi
    lda #0
    jsr _pad_trigger
    and #PAD_START
    beq @wait

    lda #2
    jsr set_sig
    lda #LIVES
    sta lives
    lda #0
    jsr start_level

game_loop:
    jsr _ppu_wait_nmi
    inc frame
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
    jsr update_enemies
    bcs @dead
    jsr check_pickups
    bcs @next
    jsr update_camera
    jsr stream_column
    jsr draw_sprites
    jsr write_qa
    jmp game_loop
@dead:
    dec lives
    bne @retry
    jmp title                ; game over
@retry:
    lda lv_index
    jsr start_level
    jmp game_loop
@next:
    ldx lv_index
    inx
    cpx lv_count
    bcc @load
    jmp title                ; all levels done: back to the title screen
@load:
    txa
    jsr start_level
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

write_qa:
    lda lives
    sta QA
    lda cam_x
    sta QA+1
    lda cam_x+1
    sta QA+2
    lda #0
    sta tmp
    ldx n_enemies
@count:
    dex
    bmi @counted
    lda e_alive,x
    clc
    adc tmp
    sta tmp
    jmp @count
@counted:
    lda tmp
    sta QA+3
    lda lv_index
    sta QA+4
    lda hx
    sta QA+5
    lda hx+1
    sta QA+6
    lda hy
    sta QA+7
    rts

; ---------------------------------------------------------------- levels

; A = level number. Loads it, then draws the first screen while the hero waits.
start_level:
    jsr load_level
    jsr _ppu_off
    jsr _oam_clear
    jsr clear_nametables
    jsr forget_columns
    lda #$FF
    sta col_buf
    jsr update_camera
    jsr write_qa
    jsr _ppu_on_all
@fill:
    jsr stream_column
    php
    jsr _ppu_wait_nmi
    plp
    bcs @fill
    rts

; A = level number. Points at its data, places the enemies and puts the hero at the start.
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
    ldy #8
    lda (lv_ptr),y
    sta lv_flags
    iny
    lda (lv_ptr),y
    sta n_enemies
    iny
    ldx #0
@enemy:
    cpx n_enemies
    bcs @enemies_done
    lda (lv_ptr),y           ; column, row, kind
    sta e_lo,x
    iny
    lda (lv_ptr),y
    asl
    asl
    asl
    asl
    sta e_y,x
    iny
    lda (lv_ptr),y
    sta e_kind,x
    iny
    jsr place_enemy
    inx
    bne @enemy
@enemies_done:
    tya                      ; column map follows the enemy list
    clc
    adc lv_ptr
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
    lda start_x
    jsr col_px
    lda tmp+2
    sta hx
    lda tmp+3
    sta hx+1
    lda start_y
    asl
    asl
    asl
    asl
    sta hy
    rts

; Enemy X: start column in e_lo -> position, patrol range, facing left, alive. Keeps X, Y.
place_enemy:
    lda e_lo,x
    clc
    adc #PATROL
    sta e_hi,x
    lda e_lo,x
    pha
    sec
    sbc #PATROL
    bcs :+
    lda #0
:   sta e_lo,x
    pla
    sty tmp
    jsr col_px
    ldy tmp
    lda tmp+2
    sta e_xl,x
    lda tmp+3
    sta e_xh,x
    lda #1
    sta e_dir,x
    sta e_alive,x
    rts

; A = column -> tmp+2/tmp+3 = column * 16 (level pixels). Keeps X; uses Y.
col_px:
    ldy #0
    sty tmp+3
    asl
    rol tmp+3
    asl
    rol tmp+3
    asl
    rol tmp+3
    asl
    rol tmp+3
    sta tmp+2
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
    lda #1                   ; got the key: doors open, redraw what's on screen
    sta has_key
    jsr forget_columns
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


; ---------------------------------------------------------------- enemies

; Moves every enemy; carry set if one hurt the hero.
update_enemies:
    lda #0
    sta ei
@loop:
    lda ei
    cmp n_enemies
    bcs @safe
    tax
    lda e_alive,x
    beq @next
    jsr move_enemy
    jsr touch_enemy
    bcs @hurt
@next:
    inc ei
    jmp @loop
@safe:
    clc
@hurt:
    rts

; Walkers step every other frame and turn at walls and ledges; patrollers step every frame
; and turn at walls and at the ends of their range.
move_enemy:
    ldx ei
    lda e_kind,x
    bne @patrol
    lda frame
    lsr
    bcc @done
    jsr enemy_step
    jsr enemy_wall
    bcs enemy_turn
    ldx ei
    lda e_y,x
    clc
    adc #16
    sta ty
    jsr tile_at              ; floor under the front edge?
    cmp #T_PLAT
    beq @done
    jsr is_solid
    bcc enemy_turn
@done:
    rts
@patrol:
    jsr enemy_step
    jsr enemy_wall
    bcs enemy_turn
    ldx ei
    lda tx+1                 ; front column
    asl
    asl
    asl
    asl
    sta tmp
    lda tx
    lsr
    lsr
    lsr
    lsr
    ora tmp
    cmp e_lo,x
    bcc enemy_turn
    beq @done
    cmp e_hi,x
    bcc @done
    beq @done
enemy_turn:
    ldx ei
    lda e_dir,x
    eor #1
    sta e_dir,x
    ; fall through: step back the way it came

; Enemy ei moves one pixel its way.
enemy_step:
    ldx ei
    lda e_dir,x
    bne @left
    inc e_xl,x
    bne :+
    inc e_xh,x
:   rts
@left:
    lda e_xl,x
    bne :+
    dec e_xh,x
:   dec e_xl,x
    rts

; Carry set if a wall is just ahead of enemy ei (front edge in tx/tx+1 afterwards).
enemy_wall:
    ldx ei
    lda e_xl,x
    ldy e_dir,x
    bne @left
    clc
    adc #15
    sta tx
    lda e_xh,x
    adc #0
    sta tx+1
    jmp @probe
@left:
    sta tx
    lda e_xh,x
    sta tx+1
@probe:
    lda e_y,x
    clc
    adc #8
    sta ty
    jsr tile_at
    jmp is_solid

; Hero against enemy ei. Carry set if the hero is hurt; a stomp defeats the enemy instead.
touch_enemy:
    ldx ei
    lda e_xl,x               ; dx = enemy x - hero x, must be within -11..11
    sec
    sbc hx
    sta tmp
    lda e_xh,x
    sbc hx+1
    beq @right
    cmp #$FF
    bne @miss
    lda tmp
    cmp #245
    bcc @miss
    bcs @near
@right:
    lda tmp
    cmp #12
    bcs @miss
@near:
    lda e_y,x                ; dy = enemy y - hero y, must be within -13..13
    sec
    sbc hy
    clc
    adc #13
    cmp #27
    bcs @miss
    sta tmp
    lda lv_flags
    and #FLAG_STOMP
    beq @hurt
    lda vy                   ; falling, with the hero's feet near the enemy's top
    beq @hurt
    bmi @hurt
    lda tmp
    cmp #13+6
    bcc @hurt
    lda #0
    sta e_alive,x
    sta on_ground
    lda #BOUNCE_VY
    sta vy
@miss:
    clc
    rts
@hurt:
    sec
    rts

; ---------------------------------------------------------------- scrolling

; cam_x = hx - CAM_LEAD, kept inside the level, and handed to neslib.
update_camera:
    lda hx
    sec
    sbc #CAM_LEAD
    sta cam_x
    lda hx+1
    sbc #0
    sta cam_x+1
    bpl :+
    lda #0
    sta cam_x
    sta cam_x+1
:   lda lv_width             ; widths are whole screens: the last camera x is (screens-1)*256
    lsr
    lsr
    lsr
    lsr
    sec
    sbc #1
    cmp cam_x+1
    bcs :+
    sta cam_x+1
    lda #0
    sta cam_x
:   lda cam_x
    ldx cam_x+1
    jmp _set_scroll_x

forget_columns:
    lda #$FF
    ldx #31
:   sta nt_col,x
    dex
    bpl :-
    rts

; Queues the first of the 17 columns in view that isn't in the nametables yet.
; Carry set if one was queued.
stream_column:
    lda cam_x+1
    asl
    asl
    asl
    asl
    sta col_c
    lda cam_x
    lsr
    lsr
    lsr
    lsr
    ora col_c
    sta col_c
    lda #17
    sta tmp+3
@scan:
    lda col_c
    cmp lv_width
    bcs @none
    and #31
    tax
    lda nt_col,x
    cmp col_c
    bne @draw
    inc col_c
    dec tmp+3
    bne @scan
@none:
    lda #$FF
    sta col_buf
    clc
    rts
@draw:
    lda col_c
    sta nt_col,x
    and #16                  ; nametable $2000 or $2400, row 4, tile column (c & 15) * 2
    lsr
    lsr
    ora #$20|VERT_RUN
    sta col_buf
    sta col_buf+27
    lda col_c
    and #15
    asl
    ora #$80
    sta col_buf+1
    ora #1
    sta col_buf+28
    lda #ROWS*2
    sta col_buf+2
    sta col_buf+29
    lda #$FF
    sta col_buf+54
    lda #0
    sta trow
@row:
    lda col_c
    jsr tile_cr
    cmp #T_DOOR
    bne :+
    ldx has_key
    beq :+
    lda #T_EMPTY             ; open door
:   asl
    asl
    clc
    adc #META_BASE
    sta tmp+2
    lda trow
    asl
    tay
    lda tmp+2                ; left half: top-left, bottom-left; right half: the other two
    sta col_buf+3,y
    ora #2
    sta col_buf+4,y
    lda tmp+2
    ora #1
    sta col_buf+30,y
    ora #3
    sta col_buf+31,y
    inc trow
    lda trow
    cmp #ROWS
    bne @row
    sec
    rts

clear_nametables:
    lda #$20
    sta PPU_ADDR
    lda #$00
    sta PPU_ADDR
    tax
    ldy #8
:   sta PPU_DATA
    inx
    bne :-
    dey
    bne :-
    rts


; ---------------------------------------------------------------- drawing

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

; tmp+2/tmp+3 = level x -> A = screen x. Carry set if it isn't on screen.
to_screen:
    lda tmp+2
    sec
    sbc cam_x
    sta tmp+2
    lda tmp+3
    sbc cam_x+1
    bne @off
    lda tmp+2
    cmp #241
    rts
@off:
    sec
    rts

; Hero, key, goal flag, enemies and one heart per life.
draw_sprites:
    jsr _oam_clear
    lda hx
    sta tmp+2
    lda hx+1
    sta tmp+3
    jsr to_screen            ; the camera keeps the hero on screen
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
    jsr col_px
    jsr to_screen
    bcs @flag
    adc #4
    sta OAM_BUF+19
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
@flag:
    lda goal_x
    jsr col_px
    jsr to_screen
    bcs @enemies
    adc #4
    sta OAM_BUF+23
    sta OAM_BUF+27
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
@enemies:
    ldx #0
    ldy #28                  ; enemies use OAM 28-155, four sprites each
@enemy:
    cpx n_enemies
    bcs @hearts
    lda e_alive,x
    beq @enext
    lda e_xl,x
    sta tmp+2
    lda e_xh,x
    sta tmp+3
    jsr to_screen
    bcs @enext
    sta OAM_BUF+3,y
    sta OAM_BUF+11,y
    adc #8
    sta OAM_BUF+7,y
    sta OAM_BUF+15,y
    lda e_y,x
    clc
    adc #TOP_PX-1
    sta OAM_BUF+0,y
    sta OAM_BUF+4,y
    adc #8
    sta OAM_BUF+8,y
    sta OAM_BUF+12,y
    lda e_kind,x             ; first tile: 8 walker, 12 patroller
    asl
    asl
    adc #8
    sta tmp
    lda e_dir,x
    beq @face_right
    lda #$02                 ; palette 2, drawn facing left
    sta tmp+1
    lda tmp
    jmp @tiles
@face_right:
    lda #$42                 ; mirrored
    sta tmp+1
    lda tmp
    ora #1
@tiles:                      ; A = tile in the left column
    sta OAM_BUF+1,y
    ora #2
    sta OAM_BUF+9,y
    eor #1
    sta OAM_BUF+13,y
    and #$FD
    sta OAM_BUF+5,y
    lda tmp+1
    sta OAM_BUF+2,y
    sta OAM_BUF+6,y
    sta OAM_BUF+10,y
    sta OAM_BUF+14,y
    tya
    clc
    adc #16
    tay
@enext:
    inx
    jmp @enemy
@hearts:
    ldx lives
    ldy #160
    lda #8
    sta tmp
@heart:
    lda #12
    sta OAM_BUF+0,y
    lda #7
    sta OAM_BUF+1,y
    lda #3
    sta OAM_BUF+2,y
    lda tmp
    sta OAM_BUF+3,y
    clc
    adc #10
    sta tmp
    iny
    iny
    iny
    iny
    dex
    bne @heart
    rts

hero_attr:  .byte $00, $40
hero_left:  .byte 0, 1       ; tile in the left column (flipped when facing left)
hero_right: .byte 1, 0
