#!/usr/bin/env python3
# WEATHER/muhl_avg4full_weather_v2.py
# Copy-forward weather_v2_field.mno → weather_v2_avg4full.mno.
# Do not smash avg4 / field / coupled / v2. Do not titan. Do not 337. Do not wipe.
# Do not host-ripple 100k. Fab-time STORE of real avg4, then address those organs.
#
# SPANK: FIELD_MOVED via AND(N,S) is NOT Cairn's organ.
# Commission: cell' = (N+S+E+W)>>2. E/W dump AND(508,620)→4837 is kneecap.
#
# STORE: four neighbor dests from 16×16 at cell_base (header wins).
# (N+S+E+W)>>2 NAND/AND composed. Gated by carry dests already 1.
# Write next, then self-clock to cell. XOR/OR on ring only.
# ADDRESS avg4/next/field answer dests (composed set, not n_gate walk).
# Surface 500 and 2548 FROM FILE. leftover 4837 as avg4 writer must be 0.

import hashlib
import json
import os
import struct
import sys

HERE = r"C:\Users\lucys\Desktop\WEATHER"
SRC = os.path.join(HERE, "weather_v2_field.mno")
AVG4 = os.path.join(HERE, "weather_v2_avg4.mno")
OUT = os.path.join(HERE, "weather_v2_avg4full.mno")
COUPLED = os.path.join(HERE, "weather_v2_coupled.mno")
V2 = os.path.join(HERE, "weather_v2.mno")
JRNL = os.path.join(HERE, "weather_genome.jsonl")
FIELD_SHA = "44904c96abb02f961713ba44df3967dd56c6cf526717db94f6b58861e813addf"
AVG4_SHA = "a869b2e2b81abd58a36600708cb0bf919bf168836df44fe0bc86f8588eceb2b3"
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


def decode_grid(raw, cell_base):
    g = [[0] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            v = 0
            for b in range(CELL_BITS):
                v |= (raw[cell_dest(cell_base, r, c, b)] & 1) << b
            g[r][c] = v
    return g


def ref_avg4(grid):
    nxt = [[0] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            s = (grid[(r - 1) % H][c] + grid[(r + 1) % H][c]
                 + grid[r][(c + 1) % W] + grid[r][(c - 1) % W])
            nxt[r][c] = (s >> 2) & 0xFF
    return nxt


def grid_ones(grid):
    return sum(1 for r in range(H) for c in range(W)
               for b in range(CELL_BITS) if (grid[r][c] >> b) & 1)


class Emitter:
    """MOVE existing NAND/AND records. Keep each record's dest. Do not invent."""

    def __init__(self, recs, pool):
        self.recs = recs
        self.pool = pool
        self.pi = 0
        self.used = []

    def emit(self, op, a, b):
        if self.pi >= len(self.pool):
            raise SystemExit("pool empty at %d" % self.pi)
        k = self.pool[self.pi]
        self.pi += 1
        out = self.recs[k][3]
        self.recs[k][0] = op
        self.recs[k][1] = a
        self.recs[k][2] = b
        self.used.append(k)
        return out

    def nand(self, a, b):
        return self.emit(NAND, a, b)

    def and_(self, a, b):
        return self.emit(AND, a, b)

    def not_(self, a):
        return self.nand(a, a)

    def or_(self, a, b):
        return self.nand(self.not_(a), self.not_(b))

    def xor(self, a, b):
        n = self.nand(a, b)
        return self.nand(self.nand(a, n), self.nand(b, n))

    def fa(self, a, b, cin):
        axb = self.xor(a, b)
        s = self.xor(axb, cin)
        cout = self.or_(self.and_(a, b), self.and_(axb, cin))
        return s, cout

    def add(self, A, B, const0):
        L = max(len(A), len(B))
        A = A + [const0] * (L - len(A))
        B = B + [const0] * (L - len(B))
        carry = const0
        out = []
        for i in range(L):
            s, carry = self.fa(A[i], B[i], carry)
            out.append(s)
        out.append(carry)
        return out


def main():
    raw = open(SRC, "rb").read()
    src_sha = hashlib.sha256(raw).hexdigest()
    sha_a0 = hashlib.sha256(open(AVG4, "rb").read()).hexdigest()
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
    const0 = wire_base
    const1 = wire_base + 1
    assert (raw[const0] & 1) == 0 and (raw[const1] & 1) == 1

    fwds = [ring0 + ri * span for ri in range(n_rings)]
    revs = [f + cells for f in fwds]
    carries = [f + 2 * cells for f in fwds]
    pubs = [c + 1 for c in carries]
    ring_dests = set(fwds + revs + carries + pubs)
    clock_dests = set(range(clock, clock + n_rings))
    carryset = set(carries)

    print("HASH SOURCE", SRC)
    print("  src_sha", src_sha, "MATCH" if src_sha == FIELD_SHA else "DRIFT")
    print("  avg4_sha", sha_a0, "UNSMASHED" if sha_a0 == AVG4_SHA else "SMASHED")
    print("  size", len(raw), "n_gate", n_gate, "gate_base", gate_base)
    print("  HEADER FROM THIS FILE cell_base", cell_base, "next_base", next_base)
    print("  ring0", ring0, "wire_base", wire_base, "const0", const0, "const1", const1)
    print("  coupled", sha_c0, "UNSMASHED" if sha_c0 == COUPLED_SHA else "SMASHED")
    print("  v2", sha_v0, "UNSMASHED" if sha_v0 == V2_SHA else "SMASHED")

    print("RAILS FROM FILE (do not re-OR)")
    for ri, name in enumerate(NAMES):
        print("  %s fwd@%d=%d rev@%d=%d carry@%d=%d pub@%d=%d" % (
            name, fwds[ri], raw[fwds[ri]] & 1, revs[ri], raw[revs[ri]] & 1,
            carries[ri], raw[carries[ri]] & 1, pubs[ri], raw[pubs[ri]] & 1))
    print("  field_ones@%d" % cell_base, ones_at(raw, cell_base, n_in), "/", n_in)
    print("  next_ones@%d" % next_base, ones_at(raw, next_base, n_in), "/", n_in)

    n0 = cell_dest(cell_base, -1, 0, 0)
    s0 = cell_dest(cell_base, 1, 0, 0)
    e0 = cell_dest(cell_base, 0, 1, 0)
    w0 = cell_dest(cell_base, 0, -1, 0)
    assert (n0, s0) == (2420, 628), "N/S dests %s %s" % (n0, s0)
    assert (e0, w0) == (508, 620), "E/W dests %s %s" % (e0, w0)
    print("  NSEW cell0b0", n0, s0, e0, w0, "carry_Q0", carries[0])

    genesis = decode_grid(raw, cell_base)
    ref_next = ref_avg4(genesis)
    ref_ones = grid_ones(ref_next)
    print("  REF (N+S+E+W)>>2 ones", ref_ones, "/", n_in)

    recs = [list(struct.unpack_from("<BQQQ", raw, gate_base + k * stride))
            for k in range(n_gate)]

    next_w = []
    field_w = []
    internal = []
    for k, rec in enumerate(recs):
        op, a, b, out = rec
        if op in (OR, XOR):
            continue
        if next_base <= out < next_hi:
            next_w.append(k)
        elif cell_base <= out < field_hi:
            field_w.append(k)
        elif out in ring_dests or out in clock_dests:
            continue
        elif wire_base <= out < gate_base:
            internal.append(k)
    next_w.sort(key=lambda k: recs[k][3])
    field_w.sort(key=lambda k: recs[k][3])
    assert len(next_w) == n_in and len(field_w) == n_in
    assert recs[next_w[0]][3] == next_base
    assert recs[field_w[0]][3] == cell_base
    print("POOL internal", len(internal), "next_w", len(next_w), "field_w", len(field_w))

    op, a, b, out = recs[next_w[0]]
    print("BEFORE writers")
    print("  avg4 rec%d %s(%d,%d)->%d" % (next_w[0], OPN[op], a, b, out))
    op, a, b, out = recs[field_w[0]]
    print("  field rec%d %s(%d,%d)->%d" % (field_w[0], OPN[op], a, b, out))

    em = Emitter(recs, internal)
    avg_temps = [0] * n_in
    for r in range(H):
        for c in range(W):
            N = [cell_dest(cell_base, r - 1, c, b) for b in range(CELL_BITS)]
            S = [cell_dest(cell_base, r + 1, c, b) for b in range(CELL_BITS)]
            E = [cell_dest(cell_base, r, c + 1, b) for b in range(CELL_BITS)]
            Ww = [cell_dest(cell_base, r, c - 1, b) for b in range(CELL_BITS)]
            tot = em.add(em.add(N, S, const0), em.add(E, Ww, const0), const0)
            avg = tot[2:2 + CELL_BITS]
            assert len(avg) == CELL_BITS
            en = carries[quadrant(r, c)]
            assert en in carryset
            for b in range(CELL_BITS):
                if avg[b] == 4837:
                    avg[b] = em.and_(avg[b], avg[b])
                i = cidx(r, c) * CELL_BITS + b
                avg_temps[i] = avg[b]
                k = next_w[i]
                recs[k][0], recs[k][1], recs[k][2], recs[k][3] = AND, avg[b], en, next_base + i
    for i in range(n_in):
        r, c = (i // CELL_BITS) // W, (i // CELL_BITS) % W
        en = carries[quadrant(r, c)]
        k = field_w[i]
        recs[k][0], recs[k][1], recs[k][2], recs[k][3] = AND, next_base + i, en, cell_base + i

    print("STORE", OUT)
    print("  fa_organs_moved", len(em.used))
    print("  next_writers_gated", len(next_w))
    print("  field_latch_retargeted", len(field_w))
    print("  pool_left", len(internal) - em.pi)
    op, a, b, out = recs[next_w[0]]
    print("  avg4 rec%d %s(%d,%d)->%d" % (next_w[0], OPN[op], a, b, out))
    print("  expect NOT AND(%d,%d)  avg_temp" % (n0, s0), avg_temps[0], "carry", carries[0])
    op, a, b, out = recs[field_w[0]]
    print("  field rec%d %s(%d,%d)->%d" % (field_w[0], OPN[op], a, b, out))
    assert not (recs[next_w[0]][1] == n0 and recs[next_w[0]][2] == s0), "STILL AND(N,S)"
    assert recs[next_w[0]][1] != 4837 and recs[next_w[0]][2] != 4837

    img = bytearray(raw)
    for k, rec in enumerate(recs):
        op, a, b, out = rec
        if cell_base <= out < field_hi or next_base <= out < next_hi:
            assert op in (NAND, AND), "XOR/OR leaked onto field/next rec%d" % k
        struct.pack_into("<BQQQ", img, gate_base + k * stride, op, a, b, out)

    live = set(fwds + revs + carries + pubs)
    live.update(range(cell_base, field_hi))
    live.update(range(clock, clock + n_rings))
    live.add(const0)
    live.add(const1)

    composed = em.used + next_w + field_w
    wanted = set(composed)

    def address_composed(tag):
        pending = list(composed)
        organs = 0
        changed = 0
        waves = 0
        while pending:
            waves += 1
            nxt = []
            fired = 0
            for k in pending:
                op, a, b, out = recs[k]
                if a not in live or b not in live:
                    nxt.append(k)
                    continue
                r = organ_bit(op, img[a] & 1, img[b] & 1)
                old = img[out]
                nb = (old & ~1) | r
                if nb != old:
                    img[out] = nb
                    changed += 1
                live.add(out)
                organs += 1
                fired += 1
            if fired == 0:
                break
            pending = nxt
        skipped = len(pending)
        print("ADDRESS", tag, "organs", organs, "bits_changed", changed,
              "waves", waves, "skipped_dark_in", skipped)
        return organs, changed, skipped, waves

    address_composed("avg4/next@%d+field@%d" % (next_base, cell_base))

    assert hashlib.sha256(open(SRC, "rb").read()).hexdigest() == src_sha
    assert hashlib.sha256(open(AVG4, "rb").read()).hexdigest() == sha_a0
    assert hashlib.sha256(open(COUPLED, "rb").read()).hexdigest() == sha_c0
    assert hashlib.sha256(open(V2, "rb").read()).hexdigest() == sha_v0

    with open(OUT, "wb") as f:
        f.write(img)
        f.flush()
        os.fsync(f.fileno())

    raw_n = open(OUT, "rb").read()
    sha_n = hashlib.sha256(raw_n).hexdigest()
    sha_f = hashlib.sha256(open(SRC, "rb").read()).hexdigest()
    sha_a = hashlib.sha256(open(AVG4, "rb").read()).hexdigest()
    sha_c = hashlib.sha256(open(COUPLED, "rb").read()).hexdigest()
    sha_v = hashlib.sha256(open(V2, "rb").read()).hexdigest()

    field_ones = ones_at(raw_n, cell_base, n_in)
    next_ones = ones_at(raw_n, next_base, n_in)
    leftover = []
    writer_on_4837 = []
    and_ns = 0
    for k in range(n_gate):
        op, a, b, out = struct.unpack_from("<BQQQ", raw_n, gate_base + k * stride)
        if a == 4837 or b == 4837 or out == 4837:
            leftover.append((k, OPN[op], a, b, out))
        if next_base <= out < next_hi and (a == 4837 or b == 4837):
            writer_on_4837.append((k, OPN[op], a, b, out))
        if next_base <= out < next_hi:
            i = out - next_base
            rr, cc, bit = (i // CELL_BITS) // W, (i // CELL_BITS) % W, i % CELL_BITS
            N = cell_dest(cell_base, rr - 1, cc, bit)
            S = cell_dest(cell_base, rr + 1, cc, bit)
            if op == AND and ((a == N and b == S) or (a == S and b == N)):
                and_ns += 1

    rec325 = struct.unpack_from("<BQQQ", raw_n, gate_base + next_w[0] * stride)
    rec_fw = struct.unpack_from("<BQQQ", raw_n, gate_base + field_w[0] * stride)
    rec241 = struct.unpack_from("<BQQQ", raw_n, gate_base + 241 * stride)

    ns_writer = (rec325[0] == AND and rec325[1] == n0 and rec325[2] == s0)
    if (not ns_writer) and and_ns == 0 and len(writer_on_4837) == 0 and next_ones == ref_ones:
        verdict = "REAL_AVG4"
    else:
        verdict = "STILL_AND_NS"

    print("SURFACE FROM FILE", OUT)
    print("  sha", sha_n)
    print("  field_ones@500", field_ones, "/", n_in)
    print("  next_ones@2548", next_ones, "/", n_in)
    print("  leftover_4837_refs", len(leftover))
    for t in leftover[:8]:
        print("  leftover", t)
    print("  avg4_writers_on_4837", len(writer_on_4837))
    print("  and_ns_writers", and_ns)
    print("  rec%d %s(%d,%d)->%d" % (next_w[0], OPN[rec325[0]], rec325[1], rec325[2], rec325[3]))
    print("  rec241 %s(%d,%d)->%d" % (OPN[rec241[0]], rec241[1], rec241[2], rec241[3]))
    print("  fw rec%d %s(%d,%d)->%d" % (field_w[0], OPN[rec_fw[0]], rec_fw[1], rec_fw[2], rec_fw[3]))
    print("  field_src", sha_f, "UNSMASHED" if sha_f == src_sha else "SMASHED")
    print("  avg4", sha_a, "UNSMASHED" if sha_a == sha_a0 else "SMASHED")
    print("  coupled", sha_c, "UNSMASHED" if sha_c == sha_c0 else "SMASHED")
    print("  v2", sha_v, "UNSMASHED" if sha_v == sha_v0 else "SMASHED")
    print("  REF_ones", ref_ones, "MATCH" if next_ones == ref_ones else "MISS")
    print("  VERDICT", verdict)
    print("  337 NO  titan NO  wipe NO  rails_re_ored NO  host_nxt_100k NO")

    with open(JRNL, "a") as f:
        f.write(json.dumps({
            "action": "weather_v2_avg4full",
            "src": SRC, "src_sha256": src_sha,
            "out": OUT, "sha256": sha_n,
            "cell_base": cell_base, "next_base": next_base,
            "fa_organs_moved": len(em.used),
            "field_ones": field_ones, "next_ones": next_ones,
            "ref_ones": ref_ones,
            "avg4_writers_on_4837": len(writer_on_4837),
            "and_ns_writers": and_ns,
            "leftover_4837_n": len(leftover),
            "verdict": verdict,
            "avg4_unsmashed": sha_a == sha_a0,
            "field_unsmashed": sha_f == src_sha,
            "coupled_unsmashed": sha_c == sha_c0,
            "v2_unsmashed": sha_v == sha_v0,
        }) + "\n")

    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
