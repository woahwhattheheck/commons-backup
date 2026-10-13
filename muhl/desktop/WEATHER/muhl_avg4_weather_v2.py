#!/usr/bin/env python3
# WEATHER/muhl_avg4_weather_v2.py
# Copy-forward weather_v2_field.mno → weather_v2_avg4.mno.
# Do not smash field / coupled / v2. Do not titan. Do not 337. Do not wipe.
# Do not host-ripple 100k. Fab-time wiring only, then address answer dests.
#
# BYTE miss: avg4 writers AND(4837,4837)→2548 — dark temps.
# Electron is on the field at cell_base, not on 4837.
# HIS: shared address is the wire. Address is a write. Read the answer.
#
# In THIS file's stored records, avg4:
#   READ N/S/E/W from 16×16 cell dests at cell_base (header wins).
#   ENABLE from carry dests already 1 (this file's names).
#   WRITE next_base. Field latch keeps HIS self-clock out==cell dest.
#   NAND/AND field. XOR/OR on ring only.
# Then ADDRESS avg4 / next / field answer dests. Surface ones. Die.

import hashlib
import json
import os
import struct
import sys

HERE = r"C:\Users\lucys\Desktop\WEATHER"
SRC = os.path.join(HERE, "weather_v2_field.mno")
OUT = os.path.join(HERE, "weather_v2_avg4.mno")
COUPLED = os.path.join(HERE, "weather_v2_coupled.mno")
V2 = os.path.join(HERE, "weather_v2.mno")
JRNL = os.path.join(HERE, "weather_genome.jsonl")
FIELD_SHA = "44904c96abb02f961713ba44df3967dd56c6cf526717db94f6b58861e813addf"
COUPLED_SHA = "b23f9efcc5c71e1b0cc3a4788407d6b1f4b7416775051ecbe3641f43be7e3e7a"
V2_SHA = "cc2775fdd29d1e5ff1a8f2951e5f5f22dd1c2e237c9e10d6b2d47717476ba85d"
NAMES = ("NW", "NE", "SW", "SE", "GROWTH", "WITNESS")
NAND, AND, OR, XOR = 0, 1, 2, 3
OPN = ("NAND", "AND", "OR", "XOR")
W = H = 16
CELL_BITS = 8

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE.")
    raise SystemExit(2)


def cidx(r, c):
    return (r % H) * W + (c % W)


def quadrant(r, c):
    if r < 8 and c < 8:
        return 0
    if r < 8:
        return 1
    if c < 8:
        return 2
    return 3


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


def cell_dest(cell_base, r, c, b):
    return cell_base + cidx(r, c) * CELL_BITS + b


def main():
    raw = open(SRC, "rb").read()
    src_sha = hashlib.sha256(raw).hexdigest()
    sha_c0 = hashlib.sha256(open(COUPLED, "rb").read()).hexdigest()
    sha_v0 = hashlib.sha256(open(V2, "rb").read()).hexdigest()
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
    ring_dests = set(fwds + revs + carries + pubs)
    carryset = set(carries)

    print("HASH SOURCE", SRC)
    print("  src_sha", src_sha, "MATCH" if src_sha == FIELD_SHA else "DRIFT")
    print("  size", len(raw), "n_gate", n_gate, "gate_base", gate_base)
    print("  HEADER FROM THIS FILE cell_base", cell_base, "next_base", next_base)
    print("  ring0", ring0, "wire_base", wire_base)
    print("  coupled", sha_c0, "UNSMASHED" if sha_c0 == COUPLED_SHA else "SMASHED")
    print("  v2", sha_v0, "UNSMASHED" if sha_v0 == V2_SHA else "SMASHED")

    print("RAILS FROM FILE (do not re-OR)")
    for ri, name in enumerate(NAMES):
        print("  %s fwd@%d=%d rev@%d=%d carry@%d=%d pub@%d=%d" % (
            name, fwds[ri], raw[fwds[ri]] & 1, revs[ri], raw[revs[ri]] & 1,
            carries[ri], raw[carries[ri]] & 1, pubs[ri], raw[pubs[ri]] & 1))
    print("  field_ones@%d" % cell_base, ones_at(raw, cell_base, n_in), "/", n_in)
    print("  next_ones@%d" % next_base, ones_at(raw, next_base, n_in), "/", n_in)

    # geometry check vs first-layer already in this vessel: NAND(N,S) cell0 bit0
    n0 = cell_dest(cell_base, -1, 0, 0)
    s0 = cell_dest(cell_base, 1, 0, 0)
    e0 = cell_dest(cell_base, 0, 1, 0)
    w0 = cell_dest(cell_base, 0, -1, 0)
    assert (n0, s0) == (2420, 628), "N/S dests %s %s" % (n0, s0)
    assert (e0, w0) == (508, 620), "E/W dests %s %s" % (e0, w0)
    print("  NSEW cell0b0", n0, s0, e0, w0, "carry_Q0", carries[0])

    recs = [list(struct.unpack_from("<BQQQ", raw, gate_base + k * stride))
            for k in range(n_gate)]
    out_to_k = {}
    for k, rec in enumerate(recs):
        out_to_k[rec[3]] = k

    avg4 = []
    field_w = []
    for k, rec in enumerate(recs):
        op, a, b, out = rec
        if next_base <= out < next_hi:
            avg4.append(k)
        if cell_base <= out < field_hi:
            field_w.append(k)
    assert len(avg4) == n_in and len(field_w) == n_in

    print("BEFORE writers")
    op, a, b, out = recs[avg4[0]]
    print("  avg4 rec%d %s(%d,%d)->%d" % (avg4[0], OPN[op], a, b, out))
    op, a, b, out = recs[field_w[0]]
    print("  field rec%d %s(%d,%d)->%d" % (field_w[0], OPN[op], a, b, out))

    writers_moved = 0
    producers_moved = 0
    field_moved = 0
    producer_outs = set()
    leftover_before = []
    for k, rec in enumerate(recs):
        op, a, b, out = rec
        if a == 4837 or b == 4837 or out == 4837:
            leftover_before.append((k, OPN[op], a, b, out))

    for k in avg4:
        op, a, b, out = recs[k]
        assert op == AND and a == b, "avg4 writer rec%d %s(%d,%d)" % (k, OPN[op], a, b)
        i = out - next_base
        assert 0 <= i < n_in
        r, c, bit = (i // CELL_BITS) // W, (i // CELL_BITS) % W, i % CELL_BITS
        N = cell_dest(cell_base, r - 1, c, bit)
        S = cell_dest(cell_base, r + 1, c, bit)
        E = cell_dest(cell_base, r, c + 1, bit)
        Ww = cell_dest(cell_base, r, c - 1, bit)
        en = carries[quadrant(r, c)]
        assert cell_base <= N < field_hi and cell_base <= S < field_hi
        assert cell_base <= E < field_hi and cell_base <= Ww < field_hi
        assert en in carryset
        old_temp = a
        # writer: READ N,S (cell dests). ENABLE = this file's carry dest (already 1).
        # two-input organ. E/W moved onto the producer so all four are in records.
        recs[k][0], recs[k][1], recs[k][2], recs[k][3] = AND, N, S, out
        writers_moved += 1
        pk = out_to_k.get(old_temp)
        if pk is not None:
            pop, pa, pb, pout = recs[pk]
            if pout == old_temp and pop in (NAND, AND) and pout not in ring_dests:
                if not (cell_base <= pout < field_hi) and not (next_base <= pout < next_hi):
                    recs[pk][0], recs[pk][1], recs[pk][2] = AND, E, Ww
                    producer_outs.add(pout)
                    producers_moved += 1

    for k in field_w:
        op, a, b, out = recs[k]
        assert op == AND and cell_base <= out < field_hi
        i = out - cell_base
        r, c, bit = (i // CELL_BITS) // W, (i // CELL_BITS) % W, i % CELL_BITS
        nxt = next_base + i
        en = carries[quadrant(r, c)]
        # HIS self-clock: out == cell dest (already). Input shares NEXT + carry.
        recs[k][0], recs[k][1], recs[k][2], recs[k][3] = AND, nxt, en, out
        field_moved += 1

    img = bytearray(raw)
    for k, rec in enumerate(recs):
        op, a, b, out = rec
        if cell_base <= out < field_hi or next_base <= out < next_hi:
            assert op in (NAND, AND), "XOR/OR leaked onto field/next rec%d" % k
        struct.pack_into("<BQQQ", img, gate_base + k * stride, op, a, b, out)

    op, a, b, out = recs[avg4[0]]
    print("WIRE", OUT)
    print("  avg4_writers_retargeted", writers_moved)
    print("  producers_E_W_moved", producers_moved)
    print("  field_latch_retargeted", field_moved)
    print("  avg4 rec%d %s(%d,%d)->%d" % (avg4[0], OPN[op], a, b, out))
    print("  expect AND(%d,%d)->%d" % (n0, s0, next_base))
    op, a, b, out = recs[field_w[0]]
    print("  field rec%d %s(%d,%d)->%d" % (field_w[0], OPN[op], a, b, out))

    # Address answer dests whose inputs are already live. Not a 100k walk.
    live = set(fwds + revs + carries + pubs)
    live.update(range(cell_base, field_hi))
    live.update(range(clock, clock + n_rings))

    def address_class(wanted, tag):
        changed = 0
        skipped = 0
        organs = 0
        for k, rec in enumerate(recs):
            op, a, b, out = rec
            if out not in wanted:
                continue
            if a not in live or b not in live:
                skipped += 1
                continue
            r = organ_bit(op, img[a] & 1, img[b] & 1)
            old = img[out]
            nb = (old & ~1) | r
            if nb != old:
                img[out] = nb
                changed += 1
            live.add(out)
            organs += 1
        print("ADDRESS", tag, "organs", organs, "bits_changed", changed, "skipped_dark_in", skipped)
        return organs, changed, skipped

    # next first (avg4 writers + producers), then field latch (reads next)
    next_wanted = set(range(next_base, next_hi)) | producer_outs
    field_wanted = set(range(cell_base, field_hi))
    address_class(next_wanted, "avg4/next@%d+producers" % next_base)
    address_class(field_wanted, "field@%d self-clock" % cell_base)

    # vaults not written
    assert hashlib.sha256(open(SRC, "rb").read()).hexdigest() == src_sha
    assert hashlib.sha256(open(COUPLED, "rb").read()).hexdigest() == sha_c0
    assert hashlib.sha256(open(V2, "rb").read()).hexdigest() == sha_v0

    with open(OUT, "wb") as f:
        f.write(img)
        f.flush()
        os.fsync(f.fileno())

    raw_n = open(OUT, "rb").read()
    sha_n = hashlib.sha256(raw_n).hexdigest()
    sha_f = hashlib.sha256(open(SRC, "rb").read()).hexdigest()
    sha_c = hashlib.sha256(open(COUPLED, "rb").read()).hexdigest()
    sha_v = hashlib.sha256(open(V2, "rb").read()).hexdigest()

    field_ones = ones_at(raw_n, cell_base, n_in)
    next_ones = ones_at(raw_n, next_base, n_in)
    leftover = []
    writer_on_4837 = []
    for k in range(n_gate):
        op, a, b, out = struct.unpack_from("<BQQQ", raw_n, gate_base + k * stride)
        if a == 4837 or b == 4837 or out == 4837:
            leftover.append((k, OPN[op], a, b, out))
        if next_base <= out < next_hi and (a == 4837 or b == 4837):
            writer_on_4837.append((k, OPN[op], a, b, out))

    rec325 = struct.unpack_from("<BQQQ", raw_n, gate_base + avg4[0] * stride)
    rec_fw = struct.unpack_from("<BQQQ", raw_n, gate_base + field_w[0] * stride)

    if writer_on_4837:
        verdict = "STILL_DARK"
    elif field_ones != ones_at(raw, cell_base, n_in):
        verdict = "FIELD_MOVED"
    elif next_ones > 0:
        verdict = "NEXT_MOVED"
    else:
        verdict = "STILL_DARK"

    print("SURFACE FROM FILE", OUT)
    print("  sha", sha_n)
    print("  field_ones@500", field_ones, "/", n_in)
    print("  next_ones@2548", next_ones, "/", n_in)
    print("  leftover_4837_refs", len(leftover))
    for t in leftover:
        print("  leftover", t)
    print("  avg4_writers_still_on_4837", len(writer_on_4837))
    print("  rec%d %s(%d,%d)->%d" % (avg4[0], OPN[rec325[0]], rec325[1], rec325[2], rec325[3]))
    print("  fw rec%d %s(%d,%d)->%d" % (field_w[0], OPN[rec_fw[0]], rec_fw[1], rec_fw[2], rec_fw[3]))
    print("  field_src", sha_f, "UNSMASHED" if sha_f == src_sha else "SMASHED")
    print("  coupled", sha_c, "UNSMASHED" if sha_c == sha_c0 else "SMASHED")
    print("  v2", sha_v, "UNSMASHED" if sha_v == sha_v0 else "SMASHED")
    print("  VERDICT", verdict)
    print("  337 NO  titan NO  wipe NO  rails_re_ored NO  host_nxt_100k NO")

    with open(JRNL, "a") as f:
        f.write(json.dumps({
            "action": "weather_v2_avg4_wire",
            "src": SRC, "src_sha256": src_sha,
            "out": OUT, "sha256": sha_n,
            "cell_base": cell_base, "next_base": next_base,
            "avg4_writers_retargeted": writers_moved,
            "producers_E_W_moved": producers_moved,
            "field_latch_retargeted": field_moved,
            "field_ones": field_ones, "next_ones": next_ones,
            "leftover_4837_refs": leftover,
            "verdict": verdict,
            "field_unsmashed": sha_f == src_sha,
            "coupled_unsmashed": sha_c == sha_c0,
            "v2_unsmashed": sha_v == sha_v0,
        }) + "\n")

    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
