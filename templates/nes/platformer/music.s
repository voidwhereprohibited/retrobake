; RetroBake placeholder tune (original RetroBake music, written by hand for this engine).
; FamiStudio engine data layout: song table, instruments, then one stream per channel.
; Stream bytes: $80|(i<<1) = instrument i, 1..$3F = note (engine note = byte + 12),
; $81+2k = k+1 empty rows, $42 + word = loop.

.export music_data

.segment "RODATA"

music_data:
    .byte 1                         ; one song
    .word instruments
    .word instruments               ; no DPCM samples (pointer unused)
    .word sq1_stream, sq2_stream, tri_stream, noise_stream, silent_stream
    .word $0100, $0100              ; tempo step: one row every 6 frames

instruments:
    .word env_lead_vol, env_flat_arp, env_half_duty, env_flat_pitch   ; 0 = square lead
    .word env_full_vol, env_flat_arp, env_half_duty, env_flat_pitch   ; 1 = triangle bass

env_lead_vol:   .byte $00, $cb, $c9, $c7, $c6, $c5, $c4, $7f, $00, $07
env_full_vol:   .byte $00, $cf, $7f, $00, $02
env_flat_arp:   .byte $c0, $7f, $00, $01
env_half_duty:  .byte $c2, $7f, $00, $00
env_flat_pitch: .byte $00, $c0, $7f, $00, $02

; Lead: a bouncy two-bar phrase, played twice with a different ending.
sq1_stream:
    .byte $80
    .byte 37, $81, 41, 44, $81, 41, 42, $81, 46, 44, $81, 41, 39, 41, 42, $81
    .byte 37, $81, 41, 44, $81, 41, 42, $81, 46, 49, $81, 46, 44, $85
    .byte $42
    .word sq1_stream

; Bass: root notes on the beat.
tri_stream:
    .byte $82
    .byte 25, $85, 25, $85, 30, $85, 30, $85, 32, $85, 32, $85, 25, $85, 32, $85
    .byte $42
    .word tri_stream

sq2_stream:
noise_stream:
silent_stream:
    .byte $ff, $42
    .word silent_stream
