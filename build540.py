#!/usr/bin/env python3
"""Build the high-rate simulation patch for Super Hexagon (Neo, Steam build 72b0c260...).

The game already scales most of its simulation by a per-update delta (inherited from
the 120 FPS mobile builds) but the desktop build pins that delta to 1.0 and runs a
fixed 60 Hz loop. This patch:
  * runs the fixed-step loop at 60*N Hz,
  * feeds the game a dyadic per-step delta (k/64, summing to exactly 1.0 per 60 Hz tick),
    so every float timer / equality check lands on the same values at tick boundaries,
  * replaces integer truncations that assumed whole ticks (walls, player, menu) with a
    carry that reproduces the exact 60 Hz per-tick totals,
  * evaluates discrete 60 Hz events (pattern spawns, zoom transitions) only on the last
    step of each 60 Hz tick.
"""
import hashlib, struct, sys


ORIG_SHA = "72b0c26053c37edd3435def461e9027cd6ffad12032db2fd0b32c256fdbee6b9"
BASE = 0x400000
SEC_RVA = 0x16b000
S = BASE + SEC_RVA
SEC_SIZE = 0x4000

# data layout
D = dict(magic=0x00, N=0x08, idx=0x0c, tick=0x10, force=0x14, cur_delta=0x18, force_delta=0x20,
         force_idx=0x28, force_n=0x2c, carry_wall=0x30, carry_player=0x38, carry_menu=0x40,
         m_wall=0x48, c_1_64=0x50, c_neg1=0x58, table=0x60, version=0x70, steps=0x74, ticks=0x78,
         xs=0x80, last_timer=0x7c, m_int=0xc0, M_acc=0xc8, M_prev=0xd0, m_len=0xd8, ev_flag=0xe0, first=0xe4, cur_delta_f=0xe8, spin_active=0xec, spin_rate=0xf0, c_half=0xf8, rateA=0x100, rateB=0x108, c_20=0x110, c_24=0x118, c_60=0x120, c_2=0x128, c_32=0x130, c_64=0x138, c_400=0x140, ang_step=0x148, ang_tick=0x14c, ang_free=0x150, softblk=0x154, c_145=0x158, snap_n=0x160, swapped=0x164)
A = {k: S + v for k, v in D.items()}
SNAP = S + 0x2000
SNAP_MAX = 400
CODE = S + 0x200
VERSION = 24


def table_for(n):
    """Dyadic step sizes (in 1/64) for n steps per 60 Hz tick, spread evenly, summing to 64."""
    base, extra = divmod(64, n)
    t = []
    acc = 0
    for i in range(n):
        # Bresenham spread of the extra units, the last step always gets one if any
        acc += extra
        if acc >= n:
            acc -= n
            t.append(base + 1)
        else:
            t.append(base)
    assert sum(t) == 64, t
    return t


def asm_source():
    a = A
    SNAP_ = SNAP
    return f"""
; ---------------- target elapsed time: divisor 60 -> 60*N ----------------
cave_div:
    mov eax, dword ptr [{a['N']:#x}]
    imul eax, eax, 60
    mov dword ptr [esp+0xc], eax
    jmp 0x4ebc30

; ---------------- per-update step: delta, tick, carries ----------------
cave_step:
    push eax
    push ecx
    push edx
    cmp dword ptr [{a['force']:#x}], 0
    je step_normal
    mov eax, dword ptr [{a['force_idx']:#x}]
    mov ecx, dword ptr [{a['force_n']:#x}]
    movsd xmm0, qword ptr [{a['force_delta']:#x}]
    jmp step_common
step_normal:
    mov eax, dword ptr [{a['idx']:#x}]
    inc eax
    mov ecx, dword ptr [{a['N']:#x}]
    cmp eax, ecx
    jb step_idx_ok
    xor eax, eax
step_idx_ok:
    mov dword ptr [{a['idx']:#x}], eax
    movzx edx, byte ptr [eax + {a['table']:#x}]
    cvtsi2sd xmm0, edx
    mulsd xmm0, qword ptr [{a['c_1_64']:#x}]
step_common:
    mov edx, dword ptr [esi+0x297c]
    mov dword ptr [{a['ang_step']:#x}], edx
    test eax, eax
    jne step_not_first
    mov dword ptr [{a['ang_tick']:#x}], edx
    ; walls as they are at the start of this 60 Hz tick (the original collision saw these)
    push esi
    push edi
    push ecx
    mov ecx, dword ptr [esi+0x2920]
    cmp ecx, {SNAP_MAX}
    jbe snap_ok
    mov ecx, -1
    mov dword ptr [{a['snap_n']:#x}], ecx
    jmp snap_done
snap_ok:
    mov dword ptr [{a['snap_n']:#x}], ecx
    lea ecx, [ecx+ecx*4]
    lea esi, [esi+0x210]
    mov edi, {SNAP:#x}
    cld
    rep movsd
snap_done:
    pop ecx
    pop edi
    pop esi
    xor edx, edx
step_not_first:
    xor edx, edx
    test eax, eax
    sete dl
    mov dword ptr [{a['first']:#x}], edx
    ; tick = (idx == n-1)
    dec ecx
    xor edx, edx
    cmp eax, ecx
    sete dl
    mov dword ptr [{a['tick']:#x}], edx
    add dword ptr [{a['ticks']:#x}], edx
    inc dword ptr [{a['steps']:#x}]
    ; new 60 Hz tick starts: clear carries
    test eax, eax
    jne step_no_reset
    xor edx, edx
    mov dword ptr [{a['carry_wall']:#x}], edx
    mov dword ptr [{a['carry_wall']+4:#x}], edx
    mov dword ptr [{a['carry_player']:#x}], edx
    mov dword ptr [{a['carry_player']+4:#x}], edx
    mov dword ptr [{a['carry_menu']:#x}], edx
    mov dword ptr [{a['carry_menu']+4:#x}], edx
    mov dword ptr [{a['M_acc']:#x}], edx
    mov dword ptr [{a['M_acc']+4:#x}], edx
step_no_reset:
    mov dword ptr [{a['ev_flag']:#x}], 0
    movsd qword ptr [{a['cur_delta']:#x}], xmm0
    cvtsd2ss xmm1, xmm0
    movss dword ptr [{a['cur_delta_f']:#x}], xmm1
    movsd qword ptr [esi+0x2950], xmm0
    movsd qword ptr [esi+0x2940], xmm0
    mov eax, dword ptr [0x55e900]
    test eax, eax
    je step_no_float
    cvtsd2ss xmm1, xmm0
    movss dword ptr [eax], xmm1
step_no_float:
    pop edx
    pop ecx
    pop eax
    movsd xmm0, qword ptr [esi+0x2950]
    jmp 0x431098

; ---------------- integer step with carry ----------------
; in: xmm7 = signed movement x for this step, eax = &carry
; out: xmm7 = integer-valued movement m. On the last step of a tick m = ceil(x+carry)
; (this is what trunc(pos - x) did per 60 Hz tick), else floor and keep the remainder.
stepk:
    movsd qword ptr [{a['xs']+0x30:#x}], xmm6
    addsd xmm7, qword ptr [eax]
    cmp dword ptr [{a['tick']:#x}], 0
    je stepk_floor
    roundsd xmm7, xmm7, 2
    xorpd xmm6, xmm6
    movsd qword ptr [eax], xmm6
    jmp stepk_done
stepk_floor:
    movapd xmm6, xmm7
    roundsd xmm7, xmm7, 1
    subsd xmm6, xmm7
    movsd qword ptr [eax], xmm6
stepk_done:
    movsd xmm6, qword ptr [{a['xs']+0x30:#x}]
    ret

; ---------------- walls: choose branch, precompute integer movement ----------------
cave_wall:
    comiss xmm4, dword ptr [edi+0x2970]
    jb wall_normal
    ; fast/outward branch: x = delta * 5.0 * ramp
    movsd qword ptr [{a['xs']:#x}], xmm7
    push eax
    movss xmm7, dword ptr [edi+0x2970]
    cvtps2pd xmm7, xmm7
    mulsd xmm7, qword ptr [0x4f16f0]
    mulsd xmm7, qword ptr [edi+0x2950]
    mov eax, {a['carry_wall']:#x}
    call stepk
    call wall_acc
    pop eax
    movsd xmm7, qword ptr [{a['xs']:#x}]
    jmp 0x429cfa
wall_normal:
    movsd qword ptr [{a['xs']:#x}], xmm7
    push eax
    movss xmm7, dword ptr [edi+0x2968]
    cvtps2pd xmm7, xmm7
    mulsd xmm7, qword ptr [edi+0x2950]
    mov eax, {a['carry_wall']:#x}
    call stepk
    call wall_acc
    pop eax
    movsd xmm7, qword ptr [{a['xs']:#x}]
    jmp 0x429da5
wall_acc:               ; xmm7 = m (integer valued)
    movsd qword ptr [{a['m_wall']:#x}], xmm7
    movsd qword ptr [{a['m_len']:#x}], xmm7
    cvttsd2si eax, xmm7
    mov dword ptr [{a['m_int']:#x}], eax
    movsd qword ptr [{a['xs']+0x10:#x}], xmm6
    movsd xmm6, qword ptr [{a['M_acc']:#x}]
    movsd qword ptr [{a['M_prev']:#x}], xmm6
    addsd xmm6, xmm7
    movsd qword ptr [{a['M_acc']:#x}], xmm6
    movsd xmm6, qword ptr [{a['xs']+0x10:#x}]
    ret

; wall inner edge reached the centre this step: the length shrinks by everything the
; wall moved since the tick started (what the 60 Hz update did in one go)
cross_calc:             ; eax = new pos (<= 0)
    push edx
    mov edx, eax
    add edx, dword ptr [{a['m_int']:#x}]
    movsd qword ptr [{a['xs']+0x20:#x}], xmm7
    movsd xmm7, qword ptr [{a['m_wall']:#x}]
    test edx, edx
    jle cross_no
    addsd xmm7, qword ptr [{a['M_prev']:#x}]
cross_no:
    movsd qword ptr [{a['m_len']:#x}], xmm7
    movsd xmm7, qword ptr [{a['xs']+0x20:#x}]
    pop edx
    ret
cave_wn_cross:
    mov dword ptr [ecx], eax
    test eax, eax
    jg wn_ret_move
    ; event marker walls (kind >= 10) fire on the tick step, as in the 60 Hz update
    cmp dword ptr [ecx-4], 10
    jl wn_normal
    cmp dword ptr [{a['tick']:#x}], 0
    jne wn_normal
    mov dword ptr [ecx], 1
    jmp 0x429ead
wn_normal:
    ; a marker that unfreezes the pattern countdown: at 60 Hz the countdown then ran
    ; for this whole tick; here the earlier steps of the tick were frozen -> catch up
    cmp dword ptr [ecx-4], 0x14
    je wn_unfreeze
    cmp dword ptr [ecx-4], 0x15
    jne wn_calc
wn_unfreeze:
    cmp byte ptr [ecx+0xc], 0
    je wn_calc
    cmp dword ptr [edi+0x550c], 0
    je wn_calc
    movsd qword ptr [{a['xs']+0x38:#x}], xmm7
    movss xmm7, dword ptr [edi+0x295c]
    cvtps2pd xmm7, xmm7
    subsd xmm7, qword ptr [0x4f16d0]
    addsd xmm7, qword ptr [{a['cur_delta']:#x}]
    cvtpd2ps xmm7, xmm7
    movss dword ptr [edi+0x295c], xmm7
    movsd xmm7, qword ptr [{a['xs']+0x38:#x}]
wn_calc:
    call cross_calc
    jmp 0x429e1d
wn_ret_move:
    jmp 0x429ead
cave_wf_cross:
    mov dword ptr [ecx], eax
    test eax, eax
    jg wf_ret_move
    call cross_calc
    jmp 0x429d51
wf_ret_move:
    jmp 0x429d94

; ---------------- player / menu movement ----------------
; generic: xmm7 = x (positive magnitude times sign given by caller)
pl_add_common:          ; eax=&carry, xmm7 = +x  -> xmm7 = m
    call stepk
    ret
pl_sub_common:          ; eax=&carry, xmm7 = +x  -> xmm7 = -step(-x)
    mulsd xmm7, qword ptr [{a['c_neg1']:#x}]
    call stepk
    mulsd xmm7, qword ptr [{a['c_neg1']:#x}]
    ret

site_pr1:   ; right key: xmm1=int spd, xmm0=int prev, xmm2=delta; want xmm1=m, xmm0=(double)prev
    cvtdq2pd xmm1, xmm1
    cvtdq2pd xmm0, xmm0
    mulsd xmm1, xmm2
    movsd qword ptr [{a['xs']:#x}], xmm7
    push eax
    movapd xmm7, xmm1
    mov eax, {a['carry_player']:#x}
    call pl_add_common
    movapd xmm1, xmm7
    pop eax
    movsd xmm7, qword ptr [{a['xs']:#x}]
    ret

site_pl1:   ; left key: xmm0=int spd, xmm1=int prev, xmm2=delta; want xmm0=v (prev - v)
    cvtdq2pd xmm0, xmm0
    cvtdq2pd xmm1, xmm1
    mulsd xmm0, xmm2
    movsd qword ptr [{a['xs']:#x}], xmm7
    push eax
    movapd xmm7, xmm0
    mov eax, {a['carry_player']:#x}
    call pl_sub_common
    movapd xmm0, xmm7
    pop eax
    movsd xmm7, qword ptr [{a['xs']:#x}]
    ret

site_pr2:   ; auto-center towards +: xmm1=int spd, xmm0=int prev; want xmm1=m
    cvtdq2pd xmm1, xmm1
    cvtdq2pd xmm0, xmm0
    mulsd xmm1, qword ptr [edi+0x2950]
    movsd qword ptr [{a['xs']:#x}], xmm7
    push eax
    movapd xmm7, xmm1
    mov eax, {a['carry_player']:#x}
    call pl_add_common
    movapd xmm1, xmm7
    pop eax
    movsd xmm7, qword ptr [{a['xs']:#x}]
    ret

site_pl2:   ; auto-center towards -: xmm0=int spd, xmm1=int prev; want xmm0=v
    cvtdq2pd xmm0, xmm0
    cvtdq2pd xmm1, xmm1
    mulsd xmm0, qword ptr [edi+0x2950]
    movsd qword ptr [{a['xs']:#x}], xmm7
    push eax
    movapd xmm7, xmm0
    mov eax, {a['carry_player']:#x}
    call pl_sub_common
    movapd xmm0, xmm7
    pop eax
    movsd xmm7, qword ptr [{a['xs']:#x}]
    ret

site_mr:    ; menu rotate +: xmm3=delta; want xmm0=m (prev + m)
    movapd xmm0, xmm3
    mulsd xmm0, qword ptr [0x4f1c98]
    movsd qword ptr [{a['xs']:#x}], xmm7
    push eax
    movapd xmm7, xmm0
    mov eax, {a['carry_menu']:#x}
    call pl_add_common
    movapd xmm0, xmm7
    pop eax
    movsd xmm7, qword ptr [{a['xs']:#x}]
    ret

site_ml:    ; menu rotate -: want xmm0=v (prev - v)
    movapd xmm0, xmm3
    mulsd xmm0, qword ptr [0x4f1c98]
    movsd qword ptr [{a['xs']:#x}], xmm7
    push eax
    movapd xmm7, xmm0
    mov eax, {a['carry_menu']:#x}
    call pl_sub_common
    movapd xmm0, xmm7
    pop eax
    movsd xmm7, qword ptr [{a['xs']:#x}]
    ret

; ---------------- discrete 60 Hz events: only on the tick step ----------------
cave_z1:                ; flags from comiss [0x188] vs 60.0 still live
    jb z1_skip
    cmp dword ptr [{a['tick']:#x}], 0
    je z1_skip
    jmp 0x429589
z1_skip:
    jmp 0x4299b8

cave_z2:
    cmp dword ptr [{a['tick']:#x}], 0
    je z2_skip
    mov eax, dword ptr [edi+0x190]
    cmp eax, 0x28
    jle z2_skip
    jmp 0x42998c
z2_skip:
    jmp 0x4299b8

cave_g1:
    cmp dword ptr [{a['tick']:#x}], 0
    je g_skip_ccf1
    comiss xmm2, dword ptr [edi+0x295c]
    jb g_skip_ccf1
    call ev_begin
    jmp 0x42a5dd

cave_g2:
    cmp dword ptr [{a['tick']:#x}], 0
    je g2_skip
    comiss xmm2, xmm0
    jb g2_skip
    call ev_begin
    push 0xcd
    mov ecx, esi
    mov dword ptr [edi+0x295c], 0
    call 0x40fbf0
    call ev_end
    jmp 0x42b359
g2_skip:
    jmp 0x42b361

cave_g3:
    cmp dword ptr [{a['tick']:#x}], 0
    je g_skip_ccf1
    comiss xmm1, xmm0
    jb g_skip_ccf1
    call ev_begin
    jmp 0x42b569

cave_g4:
    movss dword ptr [edi+0x295c], xmm0
    cmp dword ptr [{a['tick']:#x}], 0
    je g_skip_ccf1
    comiss xmm2, xmm0
    jb g_skip_ccf1
    call ev_begin
    movsd xmm1, qword ptr [0x4f16d0]
    jmp 0x42bd59

cave_g5:
    movss dword ptr [edi+0x295c], xmm0
    cmp dword ptr [{a['tick']:#x}], 0
    je g_skip_ccf1
    comiss xmm1, xmm0
    jb g_skip_ccf1
    call ev_begin
    jmp 0x42c5d0

cave_g6:
    cmp dword ptr [{a['tick']:#x}], 0
    je g_skip_ccf1
    comiss xmm2, xmm0
    jb g_skip_ccf1
    call ev_begin
    jmp 0x42a387

g_skip_ccf1:
    jmp 0x42ccf1

; a 60 Hz event fires on the tick step: its body sees one whole tick of delta
ev_begin:
    push eax
    movsd qword ptr [{a['xs']+0x28:#x}], xmm7
    movsd xmm7, qword ptr [0x4f16d0]
    jmp ev_write
ev_end:
    cmp dword ptr [{a['ev_flag']:#x}], 0
    je ev_end_ret
    push eax
    movsd qword ptr [{a['xs']+0x28:#x}], xmm7
    movsd xmm7, qword ptr [{a['cur_delta']:#x}]
ev_write:
    movsd qword ptr [edi+0x2950], xmm7
    movsd qword ptr [edi+0x2940], xmm7
    mov eax, dword ptr [0x55e900]
    test eax, eax
    je ev_nf
    cvtsd2ss xmm7, xmm7
    movss dword ptr [eax], xmm7
ev_nf:
    xor dword ptr [{a['ev_flag']:#x}], 1
    movsd xmm7, qword ptr [{a['xs']+0x28:#x}]
    pop eax
ev_end_ret:
    ret
cave_ccf1:
    call ev_end
    cmp dword ptr [edi+0x579c], 1
    jmp 0x42ccf8

; ---------------- level reset: the rest of this update is one whole 60 Hz tick ----------------
cave_rst1:
    push ecx
    call tramp_rst1
    pop ecx
    jmp realign
tramp_rst1:
    push ebp
    mov ebp, esp
    push ecx
    push esi
    jmp 0x405495
cave_rst2:
    push ecx
    call tramp_rst2
    pop ecx
    jmp realign
tramp_rst2:
    push esi
    mov esi, ecx
    call 0x418430
    jmp 0x418488
realign:                        ; ecx = game+0x10
    movsd xmm0, qword ptr [0x4f16d0]
    movsd qword ptr [ecx+0x2940], xmm0
    movsd qword ptr [ecx+0x2930], xmm0
    movsd qword ptr [{a['cur_delta']:#x}], xmm0
    mov dword ptr [{a['cur_delta_f']:#x}], 0x3f800000
    mov eax, dword ptr [0x55e900]
    test eax, eax
    je realign_nf
    cvtsd2ss xmm0, xmm0
    movss dword ptr [eax], xmm0
realign_nf:
    mov dword ptr [{a['snap_n']:#x}], -1
    mov dword ptr [{a['tick']:#x}], 1
    mov dword ptr [{a['first']:#x}], 1
    mov eax, dword ptr [{a['ang_step']:#x}]
    mov dword ptr [{a['ang_tick']:#x}], eax
    mov eax, dword ptr [{a['N']:#x}]
    dec eax
    mov dword ptr [{a['idx']:#x}], eax
    xor eax, eax
    mov dword ptr [{a['carry_wall']:#x}], eax
    mov dword ptr [{a['carry_wall']+4:#x}], eax
    mov dword ptr [{a['carry_player']:#x}], eax
    mov dword ptr [{a['carry_player']+4:#x}], eax
    mov dword ptr [{a['carry_menu']:#x}], eax
    mov dword ptr [{a['carry_menu']+4:#x}], eax
    mov dword ptr [{a['M_acc']:#x}], eax
    mov dword ptr [{a['M_acc']+4:#x}], eax
    ret

; ---------------- pause timer (game+0x54b0): counts whole ticks, at the start of each tick ----------------
cave_pause:
    cmp dword ptr [{a['first']:#x}], 0
    je pause_ret
    subsd xmm0, qword ptr [0x4f16d0]
pause_ret:
    jmp 0x41ab25

; ---------------- rank-up checks (timer thresholds): once per 60 Hz tick ----------------
cave_rank:
    cmp dword ptr [{a['tick']:#x}], 0
    jne rank_go
    lea esi, [edi+0x10]
    jmp 0x429981
rank_go:
    movd xmm0, dword ptr [edi+0x5528]
    jmp 0x429774

; ---------------- screen effect sequences (this+0x5478 offset, this+0x5484 tilt) ----------------
; decided once per tick from the tick-start state (as the 60 Hz update did), the resulting
; per-tick change of the visual value is spread over the steps of the tick
cave_fx:
    push ecx
    push edx
    cmp dword ptr [{a['first']:#x}], 0
    je fx_spread
    ; 547c trigger
    mov eax, dword ptr [esi+0x547c]
    test eax, eax
    jle fx_a
    cmp eax, 0x1e
    jl fx_a
    mov dword ptr [esi+0x547c], 0
    mov dword ptr [esi+0x5478], 1
fx_a:
    xorpd xmm0, xmm0
    movsd qword ptr [{a['rateA']:#x}], xmm0
    movsd qword ptr [{a['rateB']:#x}], xmm0
    mov eax, dword ptr [esi+0x5478]
    test eax, eax
    jle fx_b
    mov dword ptr [esi+0x5470], 0x186a0
    movss xmm1, dword ptr [esi+0x5480]
    cvtss2sd xmm1, xmm1
    cmp eax, 1
    jne fx_a2
    movsd xmm0, qword ptr [{a['c_20']:#x}]
    movsd qword ptr [{a['rateA']:#x}], xmm0
    addsd xmm0, xmm1
    comisd xmm0, qword ptr [{a['c_400']:#x}]
    jb fx_b
    mov dword ptr [esi+0x5478], 2
    jmp fx_b
fx_a2:
    cmp eax, 2
    jne fx_b
    movsd xmm0, qword ptr [{a['c_20']:#x}]
    mulsd xmm0, qword ptr [{a['c_neg1']:#x}]
    movapd xmm2, xmm1
    addsd xmm2, xmm0
    xorpd xmm4, xmm4
    comisd xmm4, xmm2
    jb fx_a2_keep
    ; reaches 0 this tick: end of the sequence
    movapd xmm0, xmm1
    mulsd xmm0, qword ptr [{a['c_neg1']:#x}]
    mov dword ptr [esi+0x5478], 0
    mov eax, dword ptr [esi]
    mov dword ptr [esi+0x5470], eax
fx_a2_keep:
    movsd qword ptr [{a['rateA']:#x}], xmm0
fx_b:
    mov eax, dword ptr [esi+0x5484]
    test eax, eax
    jle fx_spread
    mov dword ptr [esi+0x5470], 0x186a0
    ; beat at the end of this tick: pulse_end = pulse - delta + 1 (wrap 64), beat when %4 == 0
    mov ecx, dword ptr [ebp+8]
    movss xmm0, dword ptr [ecx+0x34]
    cvtss2sd xmm0, xmm0
    subsd xmm0, qword ptr [{a['cur_delta']:#x}]
    addsd xmm0, qword ptr [0x4f16d0]
    comisd xmm0, qword ptr [{a['c_64']:#x}]
    jb fx_nowrap
    subsd xmm0, qword ptr [{a['c_64']:#x}]
fx_nowrap:
    cvtsd2si ecx, xmm0
    and ecx, 3
    ; ecx == 0 -> beat
    movss xmm1, dword ptr [esi+0x548c]
    cvtss2sd xmm1, xmm1               ; v2
    xorpd xmm0, xmm0                  ; change this tick
    cmp eax, 1
    jne fx_t14
    test ecx, ecx
    jne fx_t1c
    movsd xmm0, qword ptr [0x4f16d0]
fx_t1c:
    movapd xmm2, xmm1
    addsd xmm2, xmm0
    comisd xmm2, qword ptr [{a['c_24']:#x}]
    jb fx_bstore
    mov dword ptr [esi+0x5484], 0x14
    jmp fx_bstore
fx_t14:
    cmp eax, 0x14
    je fx_hold
    cmp eax, 0x16
    jne fx_t15
fx_hold:
    movss xmm2, dword ptr [esi+0x5488]
    addss xmm2, dword ptr [0x4f1668]
    movss dword ptr [esi+0x5488], xmm2
    cvtss2sd xmm2, xmm2
    comisd xmm2, qword ptr [{a['c_60']:#x}]
    jb fx_bstore
    inc dword ptr [esi+0x5484]
    jmp fx_bstore
fx_t15:
    cmp eax, 0x15
    jne fx_t2
    test ecx, ecx
    jne fx_t15c
    movsd xmm0, qword ptr [{a['c_neg1']:#x}]
fx_t15c:
    movapd xmm2, xmm1
    addsd xmm2, xmm0
    xorpd xmm4, xmm4
    comisd xmm2, xmm4
    ja fx_bstore
    jmp fx_reset
fx_t2:
    cmp eax, 2
    jne fx_t17
    test ecx, ecx
    jne fx_t2c
    movsd xmm0, qword ptr [{a['c_neg1']:#x}]
fx_t2c:
    movapd xmm2, xmm1
    addsd xmm2, xmm0
    movsd xmm4, qword ptr [{a['c_24']:#x}]
    mulsd xmm4, qword ptr [{a['c_neg1']:#x}]
    comisd xmm2, xmm4
    ja fx_bstore
    mov dword ptr [esi+0x5484], 0x16
    jmp fx_bstore
fx_t17:
    cmp eax, 0x17
    jne fx_t3
    test ecx, ecx
    jne fx_t17c
    movsd xmm0, qword ptr [0x4f16d0]
fx_t17c:
    movapd xmm2, xmm1
    addsd xmm2, xmm0
    xorpd xmm4, xmm4
    comisd xmm2, xmm4
    jb fx_bstore
    jmp fx_reset
fx_t3:
    cmp eax, 3
    jne fx_t18
    movsd xmm0, qword ptr [{a['c_2']:#x}]
    movapd xmm2, xmm1
    addsd xmm2, xmm0
    comisd xmm2, qword ptr [{a['c_32']:#x}]
    jb fx_bstore
    mov dword ptr [esi+0x5484], 0x18
    jmp fx_bstore
fx_t18:
    cmp eax, 0x18
    jne fx_t19
    movsd xmm0, qword ptr [{a['c_2']:#x}]
    mulsd xmm0, qword ptr [{a['c_neg1']:#x}]
    movapd xmm2, xmm1
    addsd xmm2, xmm0
    movsd xmm4, qword ptr [{a['c_32']:#x}]
    mulsd xmm4, qword ptr [{a['c_neg1']:#x}]
    comisd xmm2, xmm4
    ja fx_bstore
    mov dword ptr [esi+0x5484], 0x19
    jmp fx_bstore
fx_t19:
    cmp eax, 0x19
    jne fx_bstore
    movsd xmm0, qword ptr [{a['c_2']:#x}]
    movapd xmm2, xmm1
    addsd xmm2, xmm0
    xorpd xmm4, xmm4
    comisd xmm2, xmm4
    jb fx_bstore
fx_reset:                              ; sequence ends: value returns to 0 over this tick
    movapd xmm0, xmm1
    mulsd xmm0, qword ptr [{a['c_neg1']:#x}]
    mov eax, dword ptr [esi]
    mov dword ptr [esi+0x5470], eax
    mov dword ptr [esi+0x5488], 0
    mov dword ptr [esi+0x5484], 0
fx_bstore:
    movsd qword ptr [{a['rateB']:#x}], xmm0
fx_spread:
    movss xmm0, dword ptr [esi+0x5480]
    cvtss2sd xmm0, xmm0
    movsd xmm1, qword ptr [{a['rateA']:#x}]
    mulsd xmm1, qword ptr [esi+0x2940]
    addsd xmm0, xmm1
    cvtsd2ss xmm0, xmm0
    movss dword ptr [esi+0x5480], xmm0
    movss xmm0, dword ptr [esi+0x548c]
    cvtss2sd xmm0, xmm0
    movsd xmm1, qword ptr [{a['rateB']:#x}]
    mulsd xmm1, qword ptr [esi+0x2940]
    addsd xmm0, xmm1
    cvtsd2ss xmm0, xmm0
    movss dword ptr [esi+0x548c], xmm0
    movsd xmm2, qword ptr [0x4f16d8]
    xorps xmm3, xmm3
    pop edx
    pop ecx
    jmp 0x41aefc

; ---------------- flash / colour-transition state flips only on the tick step ----------------
cave_f0:
    jne 0x429ee5
    cmp dword ptr [{a['tick']:#x}], 0
    je 0x429f78
    mov dword ptr [edi+0x194], 1
    jmp 0x429f78
cave_f1:
    jb 0x429f78
    mov dword ptr [edi+0x1ac], 0x437f0000
    cmp dword ptr [{a['tick']:#x}], 0
    je 0x429f78
    mov dword ptr [edi+0x194], 2
    jmp 0x429f78
cave_f2:
    jb 0x429f78
    mov dword ptr [edi+0x1ac], 0
    cmp dword ptr [{a['tick']:#x}], 0
    je 0x429f78
    mov dword ptr [edi+0x194], 0
    jmp 0x429f78
cave_f3:
    jb 0x42a0be
    cmp dword ptr [{a['tick']:#x}], 0
    jne 0x429fef
    mov dword ptr [edi+0x1ac], 0
    jmp 0x42a0be
cave_f4:
    jb 0x42a098
    mov dword ptr [edi+0x1ac], 0x437f0000
    cmp dword ptr [{a['tick']:#x}], 0
    je 0x42a0be
    mov dword ptr [edi+0x194], 2
    jmp 0x42a0a1

; ---------------- player collision: decided once per 60 Hz tick, as the original did ----------------
; between ticks the arrow follows the keyboard at full rate; on the tick step the original
; check runs and a blocked side move goes back to where the arrow was when the tick began
cave_col:
    push ebx
    push esi
    ; track where the arrow would be with no mid-tick blocking
    cmp dword ptr [{a['first']:#x}], 0
    je col_track
    mov eax, dword ptr [{a['ang_tick']:#x}]
    mov dword ptr [{a['ang_free']:#x}], eax
    mov dword ptr [{a['softblk']:#x}], 0
col_track:
    mov eax, dword ptr [edi+0x2980]
    sub eax, dword ptr [edi+0x297c]
    cmp eax, 180
    jle col_t1
    sub eax, 360
col_t1:
    cmp eax, -180
    jge col_t2
    add eax, 360
col_t2:
    add eax, dword ptr [{a['ang_free']:#x}]
    call norm360
    mov dword ptr [{a['ang_free']:#x}], eax
    cmp dword ptr [{a['tick']:#x}], 0
    jne col_tick
    ; ---- between ticks: no death; only keep the arrow out of a side that is blocked
    mov eax, dword ptr [edi+0x2980]
    call sector_of
    mov ebx, eax
    mov eax, dword ptr [edi+0x297c]
    call sector_of
    cmp eax, ebx
    je col_mid_done
    mov eax, ebx
    call side_blocked
    test eax, eax
    je col_mid_done
    mov eax, dword ptr [edi+0x297c]
    mov dword ptr [edi+0x2980], eax
    mov dword ptr [{a['softblk']:#x}], 1
col_mid_done:
    mov eax, dword ptr [edi+0x2980]
    call sector_of
    mov dword ptr [edi+0x1cc], eax
    mov ecx, 0x168
    mov eax, ecx
    cdq
    idiv dword ptr [edi+0x198]
    mov dword ptr [ebp-0x10], eax
    lea ecx, [edi+0x198]
    mov dword ptr [ebp-8], ecx
    mov ecx, dword ptr [edi+0x2980]
    xorps xmm1, xmm1
    pop esi
    pop ebx
    jmp 0x429b0f
col_tick:
    ; ---- tick step: put the arrow where the full 60 Hz move puts it (mid-tick blocking
    ; only held it visually), then run the original check exactly as the 60 Hz game did
    mov eax, dword ptr [{a['ang_free']:#x}]
    mov dword ptr [edi+0x2980], eax
col_go:
    mov eax, dword ptr [{a['ang_tick']:#x}]
    mov dword ptr [edi+0x297c], eax
    ; check against the walls of the tick start, like the 60 Hz game
    call swap_walls
    pop esi
    pop ebx
    lea ecx, [edi+0x198]
    jmp 0x4299e5

swap_walls:              ; exchange live walls with the tick-start snapshot (both ways)
    push ecx
    push edx
    push esi
    push ebx
    mov ecx, dword ptr [{a['snap_n']:#x}]
    cmp ecx, 0
    jl sw_ret
    mov edx, dword ptr [edi+0x2920]
    cmp ecx, edx
    jbe sw_n
    mov ecx, edx
sw_n:
    lea ecx, [ecx+ecx*4]
    test ecx, ecx
    je sw_ret
    lea esi, [edi+0x210]
    mov edx, {SNAP:#x}
sw_loop:
    mov eax, dword ptr [esi]
    mov ebx, dword ptr [edx]
    mov dword ptr [esi], ebx
    mov dword ptr [edx], eax
    add esi, 4
    add edx, 4
    dec ecx
    jne sw_loop
sw_flag:
    xor dword ptr [{a['swapped']:#x}], 1
sw_ret:
    pop ebx
    pop esi
    pop edx
    pop ecx
    ret
cave_colend:
    cmp dword ptr [{a['swapped']:#x}], 0
    je colend_x
    call swap_walls
colend_x:
    mov ecx, dword ptr [edi+0x2980]
    lea esi, [edi+0x10]
    xorps xmm1, xmm1
    jmp 0x429b0f

norm360:                 ; eax -> [0,360)
    cmp eax, 0
    jge n360_hi
    add eax, 360
    jmp norm360
n360_hi:
    cmp eax, 360
    jl n360_ret
    sub eax, 360
    jmp n360_hi
n360_ret:
    ret

sector_of:               ; eax = angle -> eax = angle / (360 / sides)
    push ecx
    push edx
    mov ecx, eax
    mov eax, 0x168
    cdq
    idiv dword ptr [edi+0x198]
    xchg eax, ecx
    cdq
    idiv ecx
    pop edx
    pop ecx
    ret

side_blocked:            ; eax = sector -> eax = 1 if a wall there would push the arrow back
    push ecx
    push edx
    push esi
    mov esi, eax
    mov edx, dword ptr [edi+0x2920]
    lea ecx, [edi+0x210]
    movss xmm2, dword ptr [{a['c_145']:#x}]
    subss xmm2, dword ptr [edi+0x2968]
sb_loop:
    test edx, edx
    jle sb_no
    cmp byte ptr [ecx+0x10], 0
    je sb_next
    cmp dword ptr [ecx], esi
    jne sb_next
    mov eax, dword ptr [ecx+4]
    cmp eax, 0x96
    jg sb_next
    cvtsi2ss xmm0, eax
    comiss xmm0, xmm2
    jae sb_next
    cmp dword ptr [ecx+8], 0xc8
    jl sb_next
    mov eax, 1
    jmp sb_ret
sb_next:
    add ecx, 0x14
    dec edx
    jmp sb_loop
sb_no:
    xor eax, eax
sb_ret:
    pop esi
    pop edx
    pop ecx
    ret

; ---------------- world spin sequence (this+0x5490): advance once per tick, spread the
; per-tick rotation over the steps of that tick
cave_spin:
    cmp dword ptr [{a['first']:#x}], 0
    je spin_mid
    mov eax, dword ptr [esi+0x5490]
    test eax, eax
    jne spin_tick
    mov dword ptr [{a['spin_active']:#x}], 0
    jmp 0x41af0a
spin_mid:
    cmp dword ptr [{a['spin_active']:#x}], 0
    jne spin_apply
    jmp 0x41af0a
spin_tick:
    mov dword ptr [{a['spin_active']:#x}], 1
    xorpd xmm2, xmm2                 ; rate = 0
    movss xmm1, dword ptr [esi+0x5498]
    cvtss2sd xmm1, xmm1              ; v (double)
    cmp eax, 1
    jne spin_s2
    mov eax, dword ptr [esi+0x2980]
    test eax, 1
    je spin_to5
    cmp eax, 7
    ja spin_to5
    mov dword ptr [esi+0x5490], 2
    jmp spin_store_rate
spin_to5:
    mov dword ptr [esi+0x5490], 5
    jmp spin_store_rate
spin_s2:
    cmp eax, 2
    je spin_up
    cmp eax, 5
    jne spin_s3
spin_up:                              ; states 2/5: v += 1, rate = +-0.5 v, v >= 14 -> next
    addsd xmm1, qword ptr [0x4f16d0]
    movapd xmm2, xmm1
    mulsd xmm2, qword ptr [{a['c_half']:#x}]
    cvtsd2ss xmm0, xmm1
    movss dword ptr [esi+0x5498], xmm0
    comiss xmm0, dword ptr [0x4f1734]
    jb spin_sign
    inc dword ptr [esi+0x5490]
    jmp spin_sign
spin_s3:
    cmp eax, 3
    je spin_mid_state
    cmp eax, 6
    jne spin_s4
spin_mid_state:                       ; states 3/6: v += 1, rate = +-7, v >= 45 -> next, v = 10
    addsd xmm1, qword ptr [0x4f16d0]
    movsd xmm2, qword ptr [0x4f16f8]
    cvtsd2ss xmm0, xmm1
    movss dword ptr [esi+0x5498], xmm0
    comiss xmm0, dword ptr [0x4f1750]
    jb spin_sign
    inc dword ptr [esi+0x5490]
    mov dword ptr [esi+0x5498], 0x41200000
    jmp spin_sign
spin_s4:
    cmp eax, 4
    je spin_down
    cmp eax, 7
    jne spin_store_rate
spin_down:                            ; states 4/7: v -= 1, rate = +-0.5 v, v <= 0 -> state 0
    subsd xmm1, qword ptr [0x4f16d0]
    movapd xmm2, xmm1
    mulsd xmm2, qword ptr [{a['c_half']:#x}]
    cvtsd2ss xmm0, xmm1
    movss dword ptr [esi+0x5498], xmm0
    xorps xmm1, xmm1
    comiss xmm1, xmm0
    jb spin_sign
    mov dword ptr [esi+0x5490], 0
spin_sign:                            ; states 5..7 rotate the other way
    cmp eax, 5
    jb spin_store_rate
    mulsd xmm2, qword ptr [{a['c_neg1']:#x}]
spin_store_rate:
    movsd qword ptr [{a['spin_rate']:#x}], xmm2
spin_apply:
    movss xmm0, dword ptr [esi+0x190]
    cvtss2sd xmm0, xmm0
    movsd xmm1, qword ptr [{a['spin_rate']:#x}]
    mulsd xmm1, qword ptr [esi+0x2940]
    addsd xmm0, xmm1
    cvtsd2ss xmm0, xmm0
    movss dword ptr [esi+0x190], xmm0
    xorps xmm3, xmm3
    jmp 0x41b341

; ---------------- game timer: counts whole frames, on the tick step (like the 60 Hz update) ----------------
cave_timer:
    cmp dword ptr [{a['tick']:#x}], 0
    je timer_ret
    addsd xmm0, qword ptr [0x4f16d0]
timer_ret:
    jmp 0x429700

; ---------------- side-count morph: accumulate once per 60 Hz tick with a whole tick ----------------
cave_morph:             ; the whole morph state machine advances once per 60 Hz tick
    cmp dword ptr [{a['first']:#x}], 0
    je 0x41b49e
    mov eax, dword ptr [esi+0x1f0]
    jmp 0x41b379
cave_m1:
    cmp dword ptr [{a['first']:#x}], 0
    jne m1_tick
    mov dword ptr [esi+0x54a0], 0x41a00000
    jmp 0x41b49e
m1_tick:
    movsd xmm0, qword ptr [0x4f16d0]
    jmp 0x41b386
cave_m5:
    cmp dword ptr [{a['first']:#x}], 0
    jne m5_tick
    jmp 0x41b49e
m5_tick:
    movsd xmm0, qword ptr [0x4f16d0]
    jmp 0x41b467

; ---------------- beat pulse 0x29b8: store T-1+delta so the steady state stays T-1 ----------------
cave_pulse1:
    cvtps2pd xmm0, xmm0
    addsd xmm0, qword ptr [edi+0x2950]
    subsd xmm0, qword ptr [0x4f16d0]
    cvtpd2ps xmm0, xmm0
    movss dword ptr [edi+0x29b8], xmm0
    jmp 0x42a3cb
cave_pulse2:
    cvtps2pd xmm0, xmm0
    addsd xmm0, qword ptr [edi+0x2950]
    subsd xmm0, qword ptr [0x4f16d0]
    cvtpd2ps xmm0, xmm0
    movss dword ptr [edi+0x29b8], xmm0
    jmp 0x42a323

; ---------------- oscillator (0x403c8 object): flips only on the tick step ----------------
cave_osc_up:
    jb osc_ret
    cmp dword ptr [{a['tick']:#x}], 0
    je osc_ret
    mov dword ptr [ecx+0x38], 1
    jmp 0x424adc
cave_osc_dn:
    jbe osc_ret
    cmp dword ptr [{a['tick']:#x}], 0
    je osc_ret
    mov dword ptr [ecx+0x38], 0
osc_ret:
    jmp 0x424b01

"""


def assemble():
    import subprocess, tempfile, os
    src = asm_source()
    lines = []
    for l in src.split('\n'):
        l = l.split(';')[0].rstrip()
        if l.strip():
            lines.append(l)
    d = tempfile.mkdtemp()
    open(os.path.join(d, 'p.s'), 'w').write('.intel_syntax noprefix\n.globl cave_div\n' + '\n'.join(lines) + '\n')
    subprocess.run(['as', '--32', 'p.s', '-o', 'p.o'], cwd=d, check=True)
    subprocess.run(['ld', '-m', 'elf_i386', '-e', 'cave_div', '-Ttext=%#x' % CODE, 'p.o', '-o', 'p.elf'], cwd=d, check=True)
    subprocess.run(['ld', '-m', 'elf_i386', '-e', 'cave_div', '-Ttext=%#x' % CODE, '--oformat', 'binary', 'p.o', '-o', 'p.bin'], cwd=d, check=True)
    enc = open(os.path.join(d, 'p.bin'), 'rb').read()
    labels = {}
    for l in subprocess.run(['nm', 'p.elf'], cwd=d, capture_output=True, text=True).stdout.split('\n'):
        p = l.split()
        if len(p) == 3 and p[1] in 'tT':
            labels[p[2]] = int(p[0], 16)
    return enc, labels


def rel32(src, dst, op):
    return bytes([op]) + struct.pack('<i', dst - (src + 5))


def jmp(src, dst, total=5):
    b = rel32(src, dst, 0xE9)
    return b + b'\x90' * (total - 5)


def call(src, dst, total=5):
    b = rel32(src, dst, 0xE8)
    return b + b'\x90' * (total - 5)


NOP4 = bytes.fromhex('0f1f4000')


def patch_sites(L):
    """(va, original_bytes, new_bytes)"""
    m_wall = A['m_wall']
    movsd_xmm1_mwall = bytes.fromhex('f20f100d') + struct.pack('<I', m_wall)
    movsd_xmm0_mwall = bytes.fromhex('f20f1005') + struct.pack('<I', m_wall)
    movsd_xmm1_mlen = bytes.fromhex('f20f100d') + struct.pack('<I', A['m_len'])
    movsd_xmm0_mlen = bytes.fromhex('f20f1005') + struct.pack('<I', A['m_len'])
    sites = [
        # loop target elapsed time 1/60 -> 1/(60N)
        (0x432653, bytes.fromhex('e8d8950b00'), call(0x432653, L['cave_div'])),
        # per-update delta / tick
        (0x431090, bytes.fromhex('f20f108650290000'), jmp(0x431090, L['cave_step'], 8)),
        # expected frame delta getter returns the current step delta
        (0x431120, bytes.fromhex('d90588d15500c3'), bytes.fromhex('dd05') + struct.pack('<I', A['cur_delta']) + b'\xc3'),
        # walls: branch + integer movement
        (0x429ced, bytes.fromhex('0f2fa770290000') + bytes.fromhex('0f82ab000000'), jmp(0x429ced, L['cave_wall'], 13)),
        (0x429d28, bytes.fromhex('f20f108f50290000'), movsd_xmm1_mwall),
        (0x429d37, bytes.fromhex('f20f59cb'), NOP4),
        (0x429d3f, bytes.fromhex('f20f59c8'), NOP4),
        (0x429d66, bytes.fromhex('f20f108f50290000'), movsd_xmm1_mlen),
        (0x429d4b, bytes.fromhex('890185c07f43'), jmp(0x429d4b, L['cave_wf_cross'], 6)),
        (0x429e13, bytes.fromhex('890185c00f8f90000000'), jmp(0x429e13, L['cave_wn_cross'], 10)),
        (0x429d71, bytes.fromhex('f20f59cb'), NOP4),
        (0x429d7d, bytes.fromhex('f20f59c8'), NOP4),
        (0x429e03, bytes.fromhex('f20f598750290000'), movsd_xmm0_mwall),
        (0x429e8e, bytes.fromhex('f20f598750290000'), movsd_xmm0_mlen),
        # player movement (keys)
        (0x4250c6, bytes.fromhex('f30fe6c9') + bytes.fromhex('c78770570000' + '01000000') + bytes.fromhex('f30fe6c0') + bytes.fromhex('f20f59ca'),
         bytes.fromhex('c78770570000' + '01000000') + call(0x4250c6 + 10, L['site_pr1'], 12)),
        (0x42511c, bytes.fromhex('f30fe6c0') + bytes.fromhex('c78770570000' + 'ffffffff') + bytes.fromhex('f30fe6c9') + bytes.fromhex('f20f59c2'),
         bytes.fromhex('c78770570000' + 'ffffffff') + call(0x42511c + 10, L['site_pl1'], 12)),
        # player movement (auto-center option)
        (0x4251c4, bytes.fromhex('f30fe6c9f30fe6c0f20f598f50290000'), call(0x4251c4, L['site_pr2'], 16)),
        (0x425204, bytes.fromhex('f30fe6c0f30fe6c9f20f598750290000'), call(0x425204, L['site_pl2'], 16)),
        # level-select rotation
        (0x424d13, bytes.fromhex('0f28c3f20f5905981c4f00'), call(0x424d13, L['site_mr'], 11)),
        (0x424dab, bytes.fromhex('0f28c3f20f5905981c4f00'), call(0x424dab, L['site_ml'], 11)),
        # zoom in (death) / zoom out (level start): once per 60 Hz tick
        (0x429583, bytes.fromhex('0f822f040000'), jmp(0x429583, L['cave_z1'], 6)),
        (0x429981, bytes.fromhex('8b8790010000') + bytes.fromhex('83f828') + bytes.fromhex('7e2c'), jmp(0x429981, L['cave_z2'], 11)),
        # pattern spawn decisions: once per 60 Hz tick
        (0x42a5d0, bytes.fromhex('0f2f975c290000') + bytes.fromhex('0f8214270000'), jmp(0x42a5d0, L['cave_g1'], 13)),
        (0x42b33e, bytes.fromhex('0f2fd0') + bytes.fromhex('721e'), jmp(0x42b33e, L['cave_g2'], 5)),
        (0x42b560, bytes.fromhex('0f2fc8') + bytes.fromhex('0f8288170000'), jmp(0x42b560, L['cave_g3'], 9)),
        (0x42bd48, bytes.fromhex('0f2fd0') + bytes.fromhex('f30f11875c290000') + bytes.fromhex('0f82980f0000'), jmp(0x42bd48, L['cave_g4'], 17)),
        (0x42c5bf, bytes.fromhex('0f2fc8') + bytes.fromhex('f30f11875c290000') + bytes.fromhex('0f8221070000'), jmp(0x42c5bf, L['cave_g5'], 17)),
        (0x42a37e, bytes.fromhex('0f2fd0') + bytes.fromhex('0f826a290000'), jmp(0x42a37e, L['cave_g6'], 9)),
        # level reset realigns the 60 Hz tick phase
        (0x405490, bytes.fromhex('558bec5156'), jmp(0x405490, L['cave_rst1'], 5)),
        (0x418480, bytes.fromhex('568bf1e8a8ffffff'), jmp(0x418480, L['cave_rst2'], 8)),
        # common exit of the pattern logic: restore the step delta after an event
        (0x42ccf1, bytes.fromhex('83bf9c57000001'), jmp(0x42ccf1, L['cave_ccf1'], 7)),
        # rank-up checks
        (0x42976c, bytes.fromhex('660f6e8728550000'), jmp(0x42976c, L['cave_rank'], 8)),
        # spin tilt: unscaled 1.0 per beat step -> step delta
        (0x41ad4c, bytes.fromhex('f30f5c0d68164f00'), bytes.fromhex('f30f5c0d') + struct.pack('<I', A['cur_delta_f'])),
        (0x41adf5, bytes.fromhex('f30f580568164f00'), bytes.fromhex('f30f5805') + struct.pack('<I', A['cur_delta_f'])),
        # player collision once per tick
        (0x4299df, bytes.fromhex('8d8f98010000'), jmp(0x4299df, L['cave_col'], 6)),
        (0x429b03, bytes.fromhex('8b8f80290000') + bytes.fromhex('8d7710') + bytes.fromhex('0f57c9'), jmp(0x429b03, L['cave_colend'], 12)),
        # flash / colour transitions
        (0x429ed4, bytes.fromhex('750f') + bytes.fromhex('c78794010000' + '01000000'), jmp(0x429ed4, L['cave_f0'], 12)),
        (0x429f18, bytes.fromhex('725e') + bytes.fromhex('c787ac010000' + '00007f43') + bytes.fromhex('c78794010000' + '02000000'), jmp(0x429f18, L['cave_f1'], 22)),
        (0x429f62, bytes.fromhex('7214') + bytes.fromhex('c787ac010000' + '00000000') + bytes.fromhex('c78794010000' + '00000000'), jmp(0x429f62, L['cave_f2'], 22)),
        (0x429fe9, bytes.fromhex('0f82cf000000'), jmp(0x429fe9, L['cave_f3'], 6)),
        (0x42a080, bytes.fromhex('7216') + bytes.fromhex('c787ac010000' + '00007f43') + bytes.fromhex('c78794010000' + '02000000') + bytes.fromhex('eb09'), jmp(0x42a080, L['cave_f4'], 24)),
        # screen effect sequences
        (0x41ab31, bytes.fromhex('8b867c540000'), jmp(0x41ab31, L['cave_fx'], 6)),
        # world spin sequence
        (0x41aefc, bytes.fromhex('8b8690540000') + bytes.fromhex('85c0') + bytes.fromhex('0f85c1010000'), jmp(0x41aefc, L['cave_spin'], 14)),
        # game timer
        (0x4296f8, bytes.fromhex('f20f588750290000'), jmp(0x4296f8, L['cave_timer'], 8)),
        # pause timer
        (0x41ab1d, bytes.fromhex('f20f5c8640290000'), jmp(0x41ab1d, L['cave_pause'], 8)),
        # side-count morph
        (0x41b373, bytes.fromhex('8b86f0010000'), jmp(0x41b373, L['cave_morph'], 6)),
        (0x41b37e, bytes.fromhex('f20f108640290000'), jmp(0x41b37e, L['cave_m1'], 8)),
        (0x41b45f, bytes.fromhex('f20f108640290000'), jmp(0x41b45f, L['cave_m5'], 8)),
        # beat pulse steady state
        (0x42a284, bytes.fromhex('f30f1187b8290000') + bytes.fromhex('e93a010000'), jmp(0x42a284, L['cave_pulse1'], 13)),
        (0x42a2f0, bytes.fromhex('f30f1187b8290000') + bytes.fromhex('eb29'), jmp(0x42a2f0, L['cave_pulse2'], 10)),
        # oscillator flips
        (0x424ad3, bytes.fromhex('722c') + bytes.fromhex('c7413801000000'), jmp(0x424ad3, L['cave_osc_up'], 9)),
        (0x424af8, bytes.fromhex('7607') + bytes.fromhex('c7413800000000'), jmp(0x424af8, L['cave_osc_dn'], 9)),
    ]
    return sites


def va2off(va):
    rva = va - BASE
    for v, s, r in [(0x1000, 0xee9c8, 0x400), (0xf0000, 0x6c714, 0xeee00), (0x15d000, 0x2dec, 0x15b600)]:
        if v <= rva < v + s:
            return rva - v + r
    raise ValueError(hex(va))


def build(orig: bytes, n: int) -> bytes:
    assert hashlib.sha256(orig).hexdigest() == ORIG_SHA, "unsupported executable"
    assert 1 <= n <= 16
    code, L = assemble()
    assert len(code) <= SEC_SIZE - 0x200, len(code)
    buf = bytearray(orig)
    # --- PE: add section, fixed base ---
    pe = struct.unpack_from('<I', buf, 0x3c)[0]
    nsec = struct.unpack_from('<H', buf, pe + 6)[0]
    opt = pe + 24
    sizeopt = struct.unpack_from('<H', buf, pe + 20)[0]
    sec_tab = opt + sizeopt
    new_hdr = sec_tab + 40 * nsec
    assert new_hdr + 40 <= 0x400 and buf[new_hdr:new_hdr + 40] == b'\x00' * 40
    raw_ptr = len(buf)
    assert raw_ptr % 0x200 == 0
    hdr = struct.pack('<8sIIIIIIHHI', b'.sh540\x00\x00', SEC_SIZE, SEC_RVA, SEC_SIZE, raw_ptr, 0, 0, 0, 0, 0xE0000060)
    buf[new_hdr:new_hdr + 40] = hdr
    struct.pack_into('<H', buf, pe + 6, nsec + 1)
    struct.pack_into('<I', buf, opt + 56, SEC_RVA + SEC_SIZE)          # SizeOfImage
    dllch = struct.unpack_from('<H', buf, opt + 70)[0]
    struct.pack_into('<H', buf, opt + 70, dllch & ~0x0040)               # no ASLR: fixed 0x400000
    # --- section content ---
    sec = bytearray(SEC_SIZE)
    sec[0:8] = b'SH540PAT'
    struct.pack_into('<i', sec, D['N'], n)
    struct.pack_into('<i', sec, D['idx'], n - 1)
    struct.pack_into('<d', sec, D['cur_delta'], 1.0)
    struct.pack_into('<d', sec, D['c_1_64'], 1.0 / 64.0)
    struct.pack_into('<d', sec, D['c_neg1'], -1.0)
    struct.pack_into('<d', sec, D['c_half'], 0.5)
    struct.pack_into('<f', sec, D['c_145'], 145.0)
    for k, v in (('c_20', 20.0), ('c_24', 24.0), ('c_60', 60.0), ('c_2', 2.0), ('c_32', 32.0), ('c_64', 64.0), ('c_400', 400.0)):
        struct.pack_into('<d', sec, D[k], v)
    struct.pack_into('<i', sec, D['version'], VERSION)
    for i, v in enumerate(table_for(n)):
        sec[D['table'] + i] = v
    sec[0x200:0x200 + len(code)] = code
    buf += sec
    # --- patch sites ---
    for va, old, new in patch_sites(L):
        assert len(old) == len(new), (hex(va), len(old), len(new))
        o = va2off(va)
        assert bytes(buf[o:o + len(old)]) == old, (hex(va), bytes(buf[o:o + len(old)]).hex(), old.hex())
        buf[o:o + len(new)] = new
    return bytes(buf)


if __name__ == '__main__':
    src, dst, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    out = build(open(src, 'rb').read(), n)
    open(dst, 'wb').write(out)
    code, L = assemble()
    print('ok', len(out), 'code bytes', len(code), 'table', table_for(n))
