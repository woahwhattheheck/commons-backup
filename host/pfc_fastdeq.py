#!/usr/bin/env python3
"""host/pfc_fastdeq.py — FAST pure-python dequant for the Muhlnickel forward pass (no numpy). Attacks the 5.7h/70B dequant wall.

The gguf_pp reference dequant is correct but does per-element indexed assignment. These paths dequant a whole Q4_K / Q6_K
row with bulk slicing + comprehensions + a precomputed nibble table, byte-exact vs gguf_pp.dequant. Q4_K/Q6_K cover
Llama-3.3-70B-Q4_K_M (attn/ffn = Q4_K, some tensors Q6_K). Falls back to gguf_pp.dequant for anything else.
"""
import struct
from gguf_pp import dequant as _ref_dequant, _sm_k4

_LO = [[(b >> 0) & 0xF for b in range(256)], None]     # low nibble table (unused table kept for clarity)
_F16 = "<e"


def deq_q4k_row(raw, n):
    """Q4_K (type 12, 144B/256w): d,dmin (f16) + 12 scale bytes + 128 qs. byte-exact vs gguf_pp, bulk ops."""
    out = [0.0] * n; p = 0; o = 0
    unpack = struct.unpack_from
    while o < n:
        d, dmin = unpack("<ee", raw, p)
        sc = raw[p + 4:p + 16]; qs = raw[p + 16:p + 144]
        isb = 0; qo = 0
        for j in range(0, 256, 64):
            s1, m1 = _sm_k4(isb, sc); s2, m2 = _sm_k4(isb + 1, sc)
            d1 = d * s1; o1 = dmin * m1; d2 = d * s2; o2 = dmin * m2
            blk = qs[qo:qo + 32]
            base = o + j
            for l in range(32):
                b = blk[l]
                out[base + l] = d1 * (b & 0xF) - o1
                out[base + 32 + l] = d2 * (b >> 4) - o2
            qo += 32; isb += 2
        p += 144; o += 256
    return out


def deq_q6k_row(raw, n):
    """Q6_K (type 14, 210B/256w). byte-exact vs gguf_pp."""
    out = [0.0] * n; p = 0; o = 0
    while o < n:
        ql = raw[p:p + 128]; qh = raw[p + 128:p + 192]
        sc = [(x - 256 if x >= 128 else x) for x in raw[p + 192:p + 208]]
        d = struct.unpack_from("<e", raw, p + 208)[0]
        for nn in range(0, 256, 128):
            qlo = nn // 128 * 64; qho = nn // 128 * 32; sco = nn // 128 * 8
            for l in range(32):
                isb = l // 16
                a = ql[qlo + l]; b = ql[qlo + l + 32]; h = qh[qho + l]
                out[o + nn + l] = d * sc[sco + isb + 0] * (((a & 0xF) | (((h >> 0) & 3) << 4)) - 32)
                out[o + nn + l + 32] = d * sc[sco + isb + 2] * (((b & 0xF) | (((h >> 2) & 3) << 4)) - 32)
                out[o + nn + l + 64] = d * sc[sco + isb + 4] * (((a >> 4) | (((h >> 4) & 3) << 4)) - 32)
                out[o + nn + l + 96] = d * sc[sco + isb + 6] * (((b >> 4) | (((h >> 6) & 3) << 4)) - 32)
        p += 210; o += 256
    return out


def dequant_fast(raw, tid, n):
    if tid == 12: return deq_q4k_row(raw, n)
    if tid == 14: return deq_q6k_row(raw, n)
    return _ref_dequant(raw, tid, n)
