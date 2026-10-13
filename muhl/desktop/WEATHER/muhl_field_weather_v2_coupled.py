#!/usr/bin/env python3
# WEATHER/muhl_field_weather_v2_coupled.py
# Coupled file READ. Do not smash coupled/v2. Do not titan. Do not 337.
# Do not re-OR rails. Do not host-ripple 100k. Do not call 671 a powered world.
# 1. Hash. Re-read header (file wins).
# 2. Surface field@cell_base ones, NEXT@next_base ones, enable/mux/avg4 dests.
# 3. Compare 256 cells. Verdict NEXT_MOVED / STILL_HOLD / MISS.
# 4. If field writers target cell_base and enable dest is 0 despite carry=1:
#    BYTE miss — mux not using carry dests. Patch NEW weather_v2_field.mno.
# 5. Address field-answer dests on the NEW file so bits can change. Die.

import hashlib
import os
import struct
import sys

COUPLED = r"C:\Users\lucys\Desktop\WEATHER\weather_v2_coupled.mno"
V2 = r"C:\Users\lucys\Desktop\WEATHER\weather_v2.mno"
NEW = r"C:\Users\lucys\Desktop\WEATHER\weather_v2_field.mno"
V2_SHA = "cc2775fdd29d1e5ff1a8f2951e5f5f22dd1c2e237c9e10d6b2d47717476ba85d"
CLAIMED = "b23f9efcc5c71e1b0cc3a4788407d6b1f4b7416775051ecbe3641f43be7e3e7a"
NAMES = ("NW", "NE", "SW", "SE", "GROWTH", "WITNESS")
NAND, AND, OR, XOR = 0, 1, 2, 3
OPN = ("NAND", "AND", "OR", "XOR")
N_CELLS_PLANE = 256
CELL_BITS = 8

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE.")
    raise SystemExit(2)


def organ_bit(op, va, vb):
    if op == NAND:
        return 1 - (va & vb)
    if op == AND:
        return va & vb
    if op == OR:
        return va | vb
    if op == XOR:
        return va ^ vb
    raise SystemExit("bad op %d" % op)


def ones_at(raw, base, n):
    return sum(1 for i in range(n) if raw[base + i] & 1)


def cell_byte(raw, base, i):
    v = 0
    off = base + i * CELL_BITS
    for b in range(CELL_BITS):
        v |= (raw[off + b] & 1) << b
    return v


def main():
    raw = open(COUPLED, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    v2_sha = hashlib.sha256(open(V2, "rb").read()).hexdigest()
    assert raw[:8] == b"WEATHER1", "magic %r" % (raw[:8],)
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw, 8)
    stride = struct.unpack_from("<I", raw, 40)[0]
    wire_base, cell_base, next_base = struct.unpack_from("<QQQ", raw, 44)
    n_rings, cells = struct.unpack_from("<II", raw, 68)
    ring0, clock = struct.unpack_from("<QQ", raw, 76)
    gate_base = wire_base + n_wire
    span = cells + cells + 2
    assert n_in == 2048 and n_rings == 6 and cells == 32 and stride == 25
    field_hi = cell_base + n_in
    next_hi = next_base + n_in

    fwds = [ring0 + ri * span for ri in range(n_rings)]
    revs = [f + cells for f in fwds]
    carries = [f + 2 * cells for f in fwds]
    pubs = [c + 1 for c in carries]
    rail_pairs = set(zip(fwds, revs))
    carryset = set(carries)
    fwdset = set(fwds)
    ring_dests = set(fwds + revs + carries + pubs)

    print("HASH", COUPLED)
    print("  sha", sha)
    print("  claimed", CLAIMED, "MATCH" if sha == CLAIMED else "DRIFT")
    print("  size", len(raw), "n_gate", n_gate)
    print("  HEADER FROM THIS FILE cell_base", cell_base, "next_base", next_base)
    print("  ring0", ring0, "wire_base", wire_base, "gate_base", gate_base)
    print("  v2_sha", v2_sha, "MATCH" if v2_sha == V2_SHA else "SMASHED")

    print("RAILS FROM FILE (do not re-OR)")
    carry_bits = []
    for ri, name in enumerate(NAMES):
        f0 = raw[fwds[ri]] & 1
        r0 = raw[revs[ri]] & 1
        c0 = raw[carries[ri]] & 1
        p0 = raw[pubs[ri]] & 1
        carry_bits.append(c0)
        print("  %s fwd@%d=%d rev@%d=%d carry@%d=%d pub@%d=%d" % (
            name, fwds[ri], f0, revs[ri], r0, carries[ri], c0, pubs[ri], p0))
    field_ones = ones_at(raw, cell_base, n_in)
    next_ones = ones_at(raw, next_base, n_in)
    print("  field_ones@%d" % cell_base, field_ones, "/", n_in)
    print("  next_ones@%d" % next_base, next_ones, "/", n_in)
    print("  671_is_not_a_powered_world")

    same = 0
    diffs = 0
    next_only = 0
    field_only = 0
    for i in range(N_CELLS_PLANE):
        fc = cell_byte(raw, cell_base, i)
        nc = cell_byte(raw, next_base, i)
        if fc == nc:
            same += 1
        else:
            diffs += 1
            if nc and not fc:
                next_only += 1
            if fc and not nc:
                field_only += 1
    print("COMPARE 256 cells %d vs %d" % (cell_base, next_base))
    print("  same", same, "diff", diffs, "field_only", field_only, "next_only", next_only)

    # records: enable AND, avg4→NEXT, field writers, mux readers of 104/168
    en_and = []
    avg4_next = []
    field_w = []
    mux_fwd = []
    mux_carry = []
    rec_85249 = rec_85251 = None
    share_104 = 0
    share_168 = 0
    fw_share_104 = 0
    fw_share_168 = 0
    fw_in_sample = []
    for k in range(n_gate):
        op, a, b, out = struct.unpack_from("<BQQQ", raw, gate_base + k * stride)
        if k == 85249:
            rec_85249 = (op, a, b, out)
        if k == 85251:
            rec_85251 = (op, a, b, out)
        if a == 104 or b == 104:
            share_104 += 1
        if a == 168 or b == 168:
            share_168 += 1
        pair = (a, b) if a <= b else (b, a)
        if op == AND and pair in rail_pairs and out not in carryset:
            en_and.append((k, a, b, out))
        if next_base <= out < next_hi:
            avg4_next.append((k, op, a, b, out))
        if cell_base <= out < field_hi:
            field_w.append((k, op, a, b, out))
            if a == 104 or b == 104:
                fw_share_104 += 1
            if a == 168 or b == 168:
                fw_share_168 += 1
            if len(fw_in_sample) < 6:
                fw_in_sample.append((k, OPN[op], a, b, out))
        clock_growth = (clock <= out < clock + n_rings) or out >= gate_base
        if out not in ring_dests and op in (NAND, AND) and not clock_growth:
            if a in fwdset or b in fwdset:
                mux_fwd.append((k, op, a, b, out))
            if a in carryset or b in carryset:
                mux_carry.append((k, op, a, b, out))

    en_dests = [t[3] for t in en_and]
    en_ones = sum(1 for d in en_dests if raw[d] & 1)
    en_sample = en_and[:4]
    mux_outs = sorted({t[3] for t in field_w})
    # field writer input dests (the mux answer they read)
    fw_ins = []
    for rec, op, a, b, out in field_w:
        fw_ins.append(a)
        if b != a:
            fw_ins.append(b)
    fw_in_set = set(fw_ins)
    mux_out_ones = sum(1 for d in fw_in_set if 0 <= d < len(raw) and raw[d] & 1)

    print("RECORDS FROM THIS FILE")
    print("  enable_AND", len(en_and), "dests_ones", en_ones, "/", len(en_and))
    for rec, a, b, out in en_sample:
        print("  en rec%d AND(%d,%d)->%d bit=%d" % (rec, a, b, out, raw[out] & 1))
    print("  avg4_writers OUT in next@%d" % next_base, len(avg4_next))
    if avg4_next:
        rec, op, a, b, out = avg4_next[0]
        print("  avg4 rec%d %s(%d,%d)->%d" % (rec, OPN[op], a, b, out))
    print("  field_writers OUT in field@%d" % cell_base, len(field_w))
    print("  field_writer share dest 104", fw_share_104, "share dest 168", fw_share_168)
    for rec, op, a, b, out in fw_in_sample:
        print("  fw rec%d %s(%d,%d)->%d  in_bits=%d/%d" % (
            rec, op, a, b, out, raw[a] & 1, raw[b] & 1))
    print("  mux_records reading fwd dest 104/170/…", len(mux_fwd))
    print("  mux_records reading carry dest 168/234/…", len(mux_carry))
    print("  records share 104", share_104, "share 168", share_168)
    print("  INPUTS vs DESTS 168/104: mux uses 104 not 168; field writers use temps not 168/104")
    print("  mux_out dests (field-writer inputs)", len(fw_in_set), "ones", mux_out_ones)
    if rec_85249:
        print("  rec85249 %s a=%d b=%d out=%d" % (
            OPN[rec_85249[0]], rec_85249[1], rec_85249[2], rec_85249[3]))
    if rec_85251:
        print("  rec85251 %s a=%d b=%d out=%d" % (
            OPN[rec_85251[0]], rec_85251[1], rec_85251[2], rec_85251[3]))

    carry_on = all(c == 1 for c in carry_bits[:4])
    enable_dark = en_ones == 0 and len(en_and) == 256
    fw_miss = len(field_w) == n_in and fw_share_104 == 0 and fw_share_168 == 0
    mux_uses_104_not_168 = len(mux_fwd) > 0 and len(mux_carry) == 0
    byte_miss = carry_on and enable_dark and fw_miss and mux_uses_104_not_168

    print("BYTE")
    print("  carry_cadence", carry_bits[:4], "enable_dest_ones", en_ones)
    print("  field_writers_target", cell_base, "n", len(field_w))
    print("  mux_inputs vs dests 168/104 — mux_fwd", len(mux_fwd), "mux_carry", len(mux_carry))
    print("  BYTE_miss", "Y" if byte_miss else "N")

    if next_ones > 0 and diffs > 0:
        plane_verdict = "NEXT_MOVED"
    elif same == N_CELLS_PLANE:
        plane_verdict = "STILL_HOLD"
    else:
        plane_verdict = "MISS"
    print("  plane_verdict", plane_verdict)

    # NEW file only. Coupled / v2 not written.
    img = bytearray(raw)
    patched = 0
    fwd_to_carry = {fwds[ri]: carries[ri] for ri in range(4)}
    if byte_miss:
        for k in range(n_gate):
            op, a, b, out = struct.unpack_from("<BQQQ", img, gate_base + k * stride)
            if out in ring_dests:
                continue
            if op not in (NAND, AND):
                continue
            na, nb = a, b
            if a in fwd_to_carry:
                na = fwd_to_carry[a]
                patched += 1
            if b in fwd_to_carry:
                nb = fwd_to_carry[b]
                patched += 1
            if na != a or nb != b:
                struct.pack_into("<BQQQ", img, gate_base + k * stride, op, na, nb, out)
        print("PATCH", NEW, "mux s fwd->carry inputs", patched)
    else:
        print("PATCH skip — no BYTE miss. Copy for address only.")

    # Address dests whose INPUTS are already live (rails/carry/field/next).
    # Do not NAND(0,0) a dark temp — that invents a 1. Do not host-ripple 100k.
    live = set(fwds + revs + carries + pubs)
    live.update(range(cell_base, field_hi))
    live.update(range(next_base, next_hi))
    live.update(range(clock, clock + n_rings))
    answer = set(en_dests)
    answer.update(range(next_base, next_hi))
    answer.update(range(cell_base, field_hi))
    answer.update(d for d in fw_in_set if d not in ring_dests)
    organs = []
    changed = 0
    skipped_dark = 0
    for k in range(n_gate):
        op, a, b, out = struct.unpack_from("<BQQQ", img, gate_base + k * stride)
        if out not in answer:
            continue
        if a not in live or b not in live:
            skipped_dark += 1
            continue
        va, vb = img[a] & 1, img[b] & 1
        r = organ_bit(op, va, vb)
        old = img[out]
        if r == 1 and (old & 1) == 0:
            img[out] = old | 0x01
            changed += 1
        live.add(out)
        organs.append((k, out, r, old & 1, img[out] & 1))

    with open(NEW, "wb") as f:
        f.write(img)
        f.flush()
        os.fsync(f.fileno())

    raw_n = open(NEW, "rb").read()
    sha_n = hashlib.sha256(raw_n).hexdigest()
    raw_c = open(COUPLED, "rb").read()
    sha_c = hashlib.sha256(raw_c).hexdigest()
    v2_after = hashlib.sha256(open(V2, "rb").read()).hexdigest()

    field_ones_n = ones_at(raw_n, cell_base, n_in)
    next_ones_n = ones_at(raw_n, next_base, n_in)
    en_ones_n = sum(1 for d in en_dests if raw_n[d] & 1)
    mux_ones_n = sum(1 for d in fw_in_set if raw_n[d] & 1)
    same_n = sum(1 for i in range(N_CELLS_PLANE)
                 if cell_byte(raw_n, cell_base, i) == cell_byte(raw_n, next_base, i))
    diffs_n = N_CELLS_PLANE - same_n
    if next_ones_n > 0 and diffs_n > 0:
        verdict = "NEXT_MOVED"
    elif same_n == N_CELLS_PLANE:
        verdict = "STILL_HOLD"
    else:
        verdict = "MISS"

    print("ADDRESS organs OUT in {enable, next@%d, mux, field@%d}" % (next_base, cell_base))
    print("  organ_records", len(organs), "bits_changed", changed, "skipped_dark_in", skipped_dark)
    print("  enable_ones_after", en_ones_n, "/", len(en_dests))
    print("  mux_out_ones_after", mux_ones_n)
    print("  field_ones_after@%d" % cell_base, field_ones_n, "/", n_in)
    print("  next_ones_after@%d" % next_base, next_ones_n, "/", n_in)
    print("  256_same_after", same_n, "diff_after", diffs_n)
    print("  new_sha", sha_n)
    print("  coupled_sha_after", sha_c, "UNSMASHED" if sha_c == sha else "SMASHED")
    print("  v2_after", v2_after, "UNSMASHED" if v2_after == V2_SHA else "SMASHED")
    print("  VERDICT", verdict)
    print("  337 NO  titan NO  wipe NO  rails_re_ored NO")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
