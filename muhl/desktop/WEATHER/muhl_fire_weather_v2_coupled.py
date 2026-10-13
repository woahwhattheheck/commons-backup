#!/usr/bin/env python3
# WEATHER/muhl_fire_weather_v2_coupled.py
# Coupled file ONLY. v2 vaulted. No 100k walk. No titan. No 337. No wipe.
# 1. Hash. Rails dark → fire 0x01 both senses all six (new=old|mask). Else do not re-OR.
# 2. Address ANSWER dests this file names: records whose OUT is carry/pub/field.
#    Organ write so the bit can change. Do not invent a 1. Do not skip the organ.
# 3. Surface field ones + carry FROM FILE. Die.

import hashlib
import os
import struct
import sys

PKG = r"C:\Users\lucys\Desktop\WEATHER\weather_v2_coupled.mno"
V2 = r"C:\Users\lucys\Desktop\WEATHER\weather_v2.mno"
V2_SHA = "cc2775fdd29d1e5ff1a8f2951e5f5f22dd1c2e237c9e10d6b2d47717476ba85d"
NAMES = ("NW", "NE", "SW", "SE", "GROWTH", "WITNESS")
NAND, AND, OR, XOR = 0, 1, 2, 3
OPN = ("NAND", "AND", "OR", "XOR")

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


def main():
    raw0 = open(PKG, "rb").read()
    sha0 = hashlib.sha256(raw0).hexdigest()
    assert raw0[:8] == b"WEATHER1", "magic %r" % (raw0[:8],)
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw0, 8)
    stride = struct.unpack_from("<I", raw0, 40)[0]
    wire_base, cell_base, next_base = struct.unpack_from("<QQQ", raw0, 44)
    n_rings, cells = struct.unpack_from("<II", raw0, 68)
    ring0, clock = struct.unpack_from("<QQ", raw0, 76)
    gate_base = wire_base + n_wire
    span = cells + cells + 2
    assert n_in == 2048 and n_rings == 6 and cells == 32 and stride == 25

    fwds = [ring0 + ri * span for ri in range(n_rings)]
    revs = [f + cells for f in fwds]
    carries = [f + 2 * cells for f in fwds]
    pubs = [c + 1 for c in carries]
    field_hi = cell_base + n_in
    answer = set(carries + pubs + list(range(cell_base, field_hi)))
    ring_dests = set(fwds + revs)

    print("HASH", PKG)
    print("  sha_before", sha0)
    print("  size", len(raw0), "n_gate", n_gate, "ring0", ring0, "cell_base", cell_base)
    print("  dests FROM THIS FILE")

    rails_dark = False
    for ri, name in enumerate(NAMES):
        f0 = raw0[fwds[ri]] & 1
        r0 = raw0[revs[ri]] & 1
        c0 = raw0[carries[ri]] & 1
        p0 = raw0[pubs[ri]] & 1
        print("  %s fwd@%d=%d rev@%d=%d carry@%d=%d pub@%d=%d" % (
            name, fwds[ri], f0, revs[ri], r0, carries[ri], c0, pubs[ri], p0))
        if f0 == 0 or r0 == 0:
            rails_dark = True
    field_ones_before = sum(1 for i in range(n_in) if raw0[cell_base + i] & 1)
    print("  field_ones_before", field_ones_before, "rails_dark", "Y" if rails_dark else "N")

    with open(PKG, "r+b") as f:
        img = bytearray(f.read())

        fired = []
        if rails_dark:
            for ri, name in enumerate(NAMES):
                pair = []
                for addr in (fwds[ri], revs[ri]):
                    old = img[addr]
                    new = old | 0x01
                    img[addr] = new
                    pair.append((addr, old, new))
                fired.append((name, pair[0], pair[1]))
            print("FIRE rails new=old|0x01 (were dark)")
            for name, (fa, fo, fn), (ra, ro, rn) in fired:
                print("  %s fwd@%d %d->%d  rev@%d %d->%d" % (
                    name, fa, fo & 1, fn & 1, ra, ro & 1, rn & 1))
        else:
            print("FIRE rails SKIP — already 1. Do not re-OR.")

        # bounded: stored records whose OUT is an answer dest. That is the organ.
        organs = []
        share_ring = 0
        share_104_136 = 0
        rec_85249 = rec_85251 = None
        for k in range(n_gate):
            op, a, b, out = struct.unpack_from("<BQQQ", img, gate_base + k * stride)
            if a in ring_dests or b in ring_dests:
                share_ring += 1
            if a in (fwds[0], revs[0]) or b in (fwds[0], revs[0]):
                share_104_136 += 1
            if k == 85249:
                rec_85249 = (op, a, b, out)
            if k == 85251:
                rec_85251 = (op, a, b, out)
            if out not in answer:
                continue
            va, vb = img[a] & 1, img[b] & 1
            r = organ_bit(op, va, vb)
            old = img[out]
            # address = write so the bit can change. Do not invent a 1.
            # Do not skip if the organ is there. Do not write 0 over a 1 (wipe).
            if r == 1 and (old & 1) == 0:
                img[out] = old | 0x01
            organs.append((k, OPN[op], a, b, out, va, vb, r, old & 1, img[out] & 1))

        f.seek(0)
        f.write(img)
        f.flush()
        os.fsync(f.fileno())

    raw1 = open(PKG, "rb").read()
    sha1 = hashlib.sha256(raw1).hexdigest()
    v2_sha = hashlib.sha256(open(V2, "rb").read()).hexdigest()

    print("ADDRESS organs OUT in {carry, pub, field@%d}" % cell_base)
    print("  organ_records", len(organs))
    carry_after = []
    pub_after = []
    for ri, name in enumerate(NAMES):
        c = raw1[carries[ri]] & 1
        p = raw1[pubs[ri]] & 1
        carry_after.append(c)
        pub_after.append(p)
        hits = [o for o in organs if o[4] == carries[ri] or o[4] == pubs[ri]]
        for rec, op, a, b, out, va, vb, r, oldb, newb in hits:
            print("  %s rec%d %s(%d,%d)->%d  in=%d/%d organ=%d  %d->%d" % (
                name, rec, op, a, b, out, va, vb, r, oldb, newb))
        print("  %s AFTER carry@%d=%d pub@%d=%d" % (
            name, carries[ri], c, pubs[ri], p))

    field_ones_after = sum(1 for i in range(n_in) if raw1[cell_base + i] & 1)
    field_writes = sum(1 for o in organs if cell_base <= o[4] < field_hi and o[8] != o[9])
    print("  field_ones_after", field_ones_after, "field_bits_changed", field_writes)
    print("  RECORDS sharing a ring dest (a or b)", share_ring)
    print("  RECORDS sharing dest %d or %d" % (fwds[0], revs[0]), share_104_136)
    if rec_85249:
        print("  rec85249 %s a=%d b=%d out=%d  share_104_136=%s" % (
            OPN[rec_85249[0]], rec_85249[1], rec_85249[2], rec_85249[3],
            rec_85249[1] in (fwds[0], revs[0]) or rec_85249[2] in (fwds[0], revs[0])))
    if rec_85251:
        print("  rec85251 %s a=%d b=%d out=%d  share_104_136=%s" % (
            OPN[rec_85251[0]], rec_85251[1], rec_85251[2], rec_85251[3],
            rec_85251[1] in (fwds[0], revs[0]) or rec_85251[2] in (fwds[0], revs[0])))
    print("  sha_after", sha1)
    print("  v2_sha", v2_sha, "MATCH" if v2_sha == V2_SHA else "SMASHED")

    carry_moved = any(raw1[c] & 1 != raw0[c] & 1 for c in carries)
    field_moved = field_ones_after != field_ones_before
    if field_moved and carry_moved:
        verdict = "FIELD_MOVED+CARRY_MOVED"
    elif field_moved:
        verdict = "FIELD_MOVED"
    elif carry_moved:
        verdict = "CARRY_MOVED"
    else:
        verdict = "STILL_DARK"
    print("  VERDICT", verdict)
    print("  337 NO  titan NO  wipe NO  v2_smashed", "NO" if v2_sha == V2_SHA else "YES")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
