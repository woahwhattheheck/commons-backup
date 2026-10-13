#!/usr/bin/env python3
# muhl_fab_weather_powered.py — SPEC DADDY GROK. NEW FILE. Does not delete Cairn's fab.
# Additive WEATHER land. Dest = weather_powered.mno. Vault v1. Do not smash titan/dc/DISTRO.
#
# HIS ring (copy, not invent): 32-cell × 2-sense loom emit, WEATHER opcodes.
# XOR rotate, AND(fwd[0],rev[0])→carry, OR(pub,carry)→pub, AND(carry,carry)→recv.
# avg4 gated: enable=XOR(fwd[0],fwd[1]) NAND-composed; mux(enable, hold, avg4).
# Field AND/NAND. XOR/OR on ring only. Self-clock identity writes AFTER temps.
# Kite OR'd onto genesis (new=old|mask). Do not wipe the captured plane.
# Verify ADDRESSES stored <BQQQ> records. No host-nxt crutch as the computer.

import struct, hashlib, json, os, random, shutil

HERE = r"C:\Users\lucys\Desktop\WEATHER"
GEN = os.path.join(HERE, "genesis_playtime_read.bin")
V1 = os.path.join(HERE, "weather.mno")
V1VAULT = os.path.join(HERE, "weather_v1.mno")
OUT = os.path.join(HERE, "weather_powered.mno")
JRNL = os.path.join(HERE, "weather_genome.jsonl")
REPORT = os.path.join(HERE, "weather_powered_fab_report.json")
BEFORE_BITS = os.path.join(HERE, "POWERED_BEFORE_BITS.txt")

GEN_SHA = "d403dce5d5179ab60bc9aa5778ef52b33e9f229165c58d4e6d9edd4b98b05e67"
V1_SHA = "d8a8fc668c57a09c882a3e1c23a1015f6901a556ddb46f5e2a90ca2d62c619cb"

W = H = 16
CELL_BITS = 8
NAND, AND, OR, XOR, NOT = 0, 1, 2, 3, 4
W_XOR, W_AND, W_OR = 3, 1, 2
STRIDE = 25
HDR = 96
MAGIC = b"WEATHER1"
FIELD_BITS = W * H * CELL_BITS
N_RINGS = 6
CELLS = 32
SENSES = 2
RING_STATE = CELLS + CELLS + 2
CLOCK_BANK = N_RINGS
GROWTH_CELLS = W * H

RING_NAMES = ["Q0", "Q1", "Q2", "Q3", "GROWTH", "WITNESS"]
RING_PURPOSE = {
    "Q0": "cadence — XOR(fwd[0],fwd[1]) gates avg4 rows 0-7 cols 0-7",
    "Q1": "cadence — XOR(fwd[0],fwd[1]) gates avg4 rows 0-7 cols 8-15",
    "Q2": "cadence — XOR(fwd[0],fwd[1]) gates avg4 rows 8-15 cols 0-7",
    "Q3": "cadence — XOR(fwd[0],fwd[1]) gates avg4 rows 8-15 cols 8-15",
    "GROWTH": "growth-lane — edge-sense OUTs land in THIS file's gate-record region",
    "WITNESS": "witness — AND(carry,carry)→recv in clock bank outside 16×16 field",
}
KITE = ["0110", "1111", "0110", "0010"]
KITE_ONES = [(6, 7), (6, 8), (7, 6), (7, 7), (7, 8), (7, 9), (8, 7), (8, 8), (9, 8)]
CAIRN_MARK = (5, 5)
CAIRN_MARK_MASK = 0xC1


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


class Circuit:
    def __init__(self):
        self.wire_base = HDR
        # cell plane FIRST so cell_base stays 98 (v1 dest) until growth re-measures gates
        self.state_lo = 2
        self.state_hi = 2 + FIELD_BITS
        self.clock_lo = self.state_hi
        self.clock_hi = self.clock_lo + CLOCK_BANK
        self.ring_lo = self.clock_hi
        self.ring_hi = self.ring_lo + N_RINGS * RING_STATE
        n0 = self.ring_hi
        self.wires = [0] * n0
        self.wires[1] = 1
        self.dep = [0] * n0
        self.gates = []  # (op, a, b, out, kind) kind in RING NET GROWTH
        self.growth = []
        self.enables = [None] * N_RINGS

    def addr(self, i):
        return self.wire_base + i

    def cell_bit(self, r, c, b):
        return self.state_lo + cidx(r, c) * CELL_BITS + b

    def ring_fwd(self, ri, k):
        return self.ring_lo + ri * RING_STATE + k

    def ring_rev(self, ri, k):
        return self.ring_lo + ri * RING_STATE + CELLS + k

    def ring_carry(self, ri):
        return self.ring_lo + ri * RING_STATE + 2 * CELLS

    def ring_pub(self, ri):
        return self.ring_lo + ri * RING_STATE + 2 * CELLS + 1

    def recv(self, ri):
        return self.clock_lo + ri

    def newtmp(self):
        self.wires.append(0)
        self.dep.append(0)
        return len(self.wires) - 1

    def emit(self, op, a, b, out, kind):
        self.gates.append((op, a, b, out, kind))
        if isinstance(out, int):
            self.dep[out] = 1 + max(self.dep[a], self.dep[b])

    def op2(self, op, a, b, kind="NET"):
        t = self.newtmp()
        self.emit(op, a, b, t, kind)
        return t

    def NAND(self, a, b):
        return self.op2(NAND, a, b)

    def AND(self, a, b):
        return self.op2(AND, a, b)

    def NOT(self, a):
        return self.NAND(a, a)

    def OR_field(self, a, b):
        return self.NAND(self.NOT(a), self.NOT(b))

    def XOR_field(self, a, b):
        t = self.NAND(a, b)
        return self.NAND(self.NAND(a, t), self.NAND(b, t))

    def mux(self, s, a, b):
        # s ? b : a   titan_circuit / playtime
        return self.OR_field(self.AND(self.NOT(s), a), self.AND(s, b))

    def full_adder(self, a, b, cin):
        axb = self.XOR_field(a, b)
        s = self.XOR_field(axb, cin)
        cout = self.OR_field(self.AND(a, b), self.AND(axb, cin))
        return s, cout

    def ripple(self, A, B):
        L = max(len(A), len(B))
        A = A + [0] * (L - len(A))
        B = B + [0] * (L - len(B))
        carry = 0
        out = []
        for i in range(L):
            s, carry = self.full_adder(A[i], B[i], carry)
            out.append(s)
        out.append(carry)
        return out

    def or_tree(self, xs):
        xs = list(xs)
        if not xs:
            return 0
        while len(xs) > 1:
            nxt = []
            for i in range(0, len(xs), 2):
                if i + 1 < len(xs):
                    nxt.append(self.OR_field(xs[i], xs[i + 1]))
                else:
                    nxt.append(xs[i])
            xs = nxt
        return xs[0]


def avg4(c, N, S, E, Wn):
    s1 = c.ripple(N, S)
    s2 = c.ripple(E, Wn)
    tot = c.ripple(s1, s2)
    return tot[2:2 + CELL_BITS]


def build(seed_state, drop_shift=False, swap_neighbor=False, drop_carry=False,
          ungated=False, interleave_writes=False):
    c = Circuit()
    for i, v in enumerate(seed_state):
        c.wires[c.state_lo + i] = v & 1
    # rings + clock start empty — fire writes electrons. Empty = enable 0 = HOLD.

    # RING RECORDS — loom emit, WEATHER opcodes, 6 organs
    for ri in range(N_RINGS):
        for k in range(CELLS):
            c.emit(W_XOR, c.ring_fwd(ri, (k - 1) % CELLS), c.ring_carry(ri),
                   c.ring_fwd(ri, k), "RING")
        for k in range(CELLS):
            c.emit(W_XOR, c.ring_rev(ri, (k + 1) % CELLS), c.ring_carry(ri),
                   c.ring_rev(ri, k), "RING")
        c.emit(W_AND, c.ring_fwd(ri, 0), c.ring_rev(ri, 0), c.ring_carry(ri), "RING")
        c.emit(W_OR, c.ring_pub(ri), c.ring_carry(ri), c.ring_pub(ri), "RING")
        c.emit(W_AND, c.ring_carry(ri), c.ring_carry(ri), c.recv(ri), "RING")

    pending_writes = []
    for ri in range(N_RINGS):
        c.enables[ri] = c.XOR_field(c.ring_fwd(ri, 0), c.ring_fwd(ri, 1))

    for r in range(H):
        for cc in range(W):
            N = [c.cell_bit(r - 1, cc, b) for b in range(CELL_BITS)]
            S = [c.cell_bit(r + 1, cc, b) for b in range(CELL_BITS)]
            E = [c.cell_bit(r, cc + 1, b) for b in range(CELL_BITS)]
            Wn = [c.cell_bit(r, cc - 1, b) for b in range(CELL_BITS)]
            if swap_neighbor:
                E = [c.cell_bit(r, cc + 2, b) for b in range(CELL_BITS)]
            nxt = avg4(c, N, S, E, Wn)
            if drop_carry:
                tot = c.ripple(c.ripple(N, S), c.ripple(E, Wn))
                nxt = tot[2:2 + CELL_BITS] if not drop_shift else tot[0:CELL_BITS]
                nxt = nxt[:-1] + [0]
            if drop_shift and not drop_carry:
                s1 = c.ripple(N, S)
                s2 = c.ripple(E, Wn)
                tot = c.ripple(s1, s2)
                nxt = tot[0:CELL_BITS]
            nxt = nxt + [0] * (CELL_BITS - len(nxt))
            en = c.enables[quadrant(r, cc)]
            for b in range(CELL_BITS):
                old = c.cell_bit(r, cc, b)
                bit = nxt[b] if ungated else c.mux(en, old, nxt[b])
                if interleave_writes:
                    c.emit(AND, bit, bit, old, "NET")
                else:
                    pending_writes.append((bit, old))

    # growth reads OLD field — emit before identity writes
    gen = c.enables[4]
    for r in range(H):
        for cc in range(W):
            v = c.cell_bit(r, cc, 0)
            eN = c.XOR_field(v, c.cell_bit(r - 1, cc, 0))
            eS = c.XOR_field(v, c.cell_bit(r + 1, cc, 0))
            eE = c.XOR_field(v, c.cell_bit(r, cc + 1, 0))
            eW = c.XOR_field(v, c.cell_bit(r, cc - 1, 0))
            edge = c.or_tree([eN, eS, eE, eW])
            fire = c.AND(edge, gen)
            c.growth.append((AND, fire, fire, cidx(r, cc)))

    if not interleave_writes:
        for bit, old in pending_writes:
            c.emit(AND, bit, bit, old, "NET")
    return c


def decode_grid(state_bytes):
    g = [[0] * W for _ in range(H)]
    for i in range(W * H):
        v = 0
        for b in range(CELL_BITS):
            v |= (state_bytes[i * CELL_BITS + b] & 1) << b
        g[i // W][i % W] = v
    return g


def state_from_grid(grid):
    st = [0] * FIELD_BITS
    for r in range(H):
        for cc in range(W):
            v = grid[r][cc]
            for b in range(CELL_BITS):
                st[cidx(r, cc) * CELL_BITS + b] = (v >> b) & 1
    return st


def load_genesis_or_kite():
    raw = open(GEN, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    assert sha == GEN_SHA, "genesis sha mismatch %s" % sha
    assert len(raw) == FIELD_BITS, "genesis wrong size"
    grid = decode_grid([bb & 1 for bb in raw])
    center_before = [grid[6 + i][6 + j] for i in range(4) for j in range(4)]
    # OR kite ones onto captured plane. Zero-pattern cells KEEP genesis (no wipe).
    for i, row in enumerate(KITE):
        for j, ch in enumerate(row):
            if ch == "1":
                grid[6 + i][6 + j] = grid[6 + i][6 + j] | 0xFF
    r, cc = CAIRN_MARK
    grid[r][cc] = grid[r][cc] | CAIRN_MARK_MASK
    for rr, col in KITE_ONES:
        assert grid[rr][col] == 0xFF, "kite one-block missing %s" % ((rr, col),)
    return state_from_grid(grid), grid, center_before, sha


def parse_header(raw):
    assert raw[:8] == MAGIC, raw[:8]
    n_in, n_wire, n_gate, n_out, depth = struct.unpack_from("<IIIII", raw, 8)
    gw, gh, cbits, stride = struct.unpack_from("<IIII", raw, 28)
    wire_base, cell_base, ring_base, clock_base, growth_base = struct.unpack_from("<QQQQQ", raw, 44)
    n_rings, cells, senses = struct.unpack_from("<III", raw, 84)
    return {
        "n_in": n_in, "n_wire": n_wire, "n_gate": n_gate, "n_out": n_out, "depth": depth,
        "W": gw, "H": gh, "CELL_BITS": cbits, "STRIDE": stride,
        "wire_base": wire_base, "cell_base": cell_base, "ring_base": ring_base,
        "clock_base": clock_base, "growth_base": growth_base,
        "n_rings": n_rings, "cells": cells, "senses": senses,
        "gate_base": wire_base + n_wire,
    }


def eval_op(op, va, vb):
    if op == NAND:
        return 1 - (va & vb)
    if op == AND:
        return va & vb
    if op == OR:
        return va | vb
    if op == XOR:
        return va ^ vb
    if op == NOT:
        return 1 - va
    raise ValueError(op)


def settle_stored(raw):
    """ADDRESS stored records. Temps record-order. Clocked dests: old reads, write at pulse end."""
    h = parse_header(raw)
    wb, nw, ng = h["wire_base"], h["n_wire"], h["n_gate"]
    cb, rb, kb, gb = h["cell_base"], h["ring_base"], h["clock_base"], h["growth_base"]
    wires = list(raw[wb: wb + nw])
    work = list(wires)
    old = list(wires)
    clocked = set()
    # field + clock bank + rings are clocked (file dests that self-clock / circulate)
    for a in range(cb, cb + FIELD_BITS):
        clocked.add(a - wb)
    for a in range(kb, kb + CLOCK_BANK):
        clocked.add(a - wb)
    for a in range(rb, rb + N_RINGS * RING_STATE):
        clocked.add(a - wb)
    nxt = {}
    pad = list(raw[gb: gb + GROWTH_CELLS]) if gb + GROWTH_CELLS <= len(raw) else [0] * GROWTH_CELLS
    gate_base = h["gate_base"]
    for k in range(ng):
        op, a, b, out = struct.unpack_from("<BQQQ", raw, gate_base + k * STRIDE)
        def rd(addr):
            i = addr - wb
            if 0 <= i < nw and i in clocked:
                return old[i] & 1
            if 0 <= i < nw:
                return work[i] & 1
            raise SystemExit("addr %d not a wire" % addr)
        r = eval_op(op, rd(a), rd(b))
        if wb <= out < wb + nw:
            oi = out - wb
            if oi in clocked:
                nxt[oi] = r
            else:
                work[oi] = r
        elif gb <= out < gb + GROWTH_CELLS:
            pad[out - gb] = r
        else:
            raise SystemExit("OUT %d not wire and not growth" % out)
    new = list(old)
    for i, v in nxt.items():
        new[i] = v
    return new, pad, h


def charge_rings(raw, filled):
    """OR electrons into a COPY of stored bytes. filled[ri]=1 → fwd[0] and rev[0] get 1."""
    h = parse_header(raw)
    b = bytearray(raw)
    for ri, on in enumerate(filled):
        if not on:
            continue
        fwd0 = h["ring_base"] + ri * RING_STATE + 0
        rev0 = h["ring_base"] + ri * RING_STATE + CELLS
        b[fwd0] = b[fwd0] | 1
        b[rev0] = b[rev0] | 1
    return bytes(b)


def put_field(raw, seed_state):
    h = parse_header(raw)
    b = bytearray(raw)
    for i, v in enumerate(seed_state):
        b[h["cell_base"] + i] = v & 1
    return bytes(b)


def reference_field(grid, qen):
    nxt = [row[:] for row in grid]
    for r in range(H):
        for cc in range(W):
            if not qen[quadrant(r, cc)]:
                continue
            n = (grid[(r - 1) % H][cc] + grid[(r + 1) % H][cc]
                 + grid[r][(cc + 1) % W] + grid[r][(cc - 1) % W])
            nxt[r][cc] = (n >> 2) & 0xFF
    return nxt


def reference_rings(filled):
    # empty carry/pub; charge = fwd[0]=1, rev[0]=1, rest 0
    out = [0] * (N_RINGS * RING_STATE)
    for ri, on in enumerate(filled):
        base = ri * RING_STATE
        fwd = [1 if (on and k == 0) else 0 for k in range(CELLS)]
        rev = [1 if (on and k == 0) else 0 for k in range(CELLS)]
        carry = 0
        pub = 0
        for k in range(CELLS):
            out[base + k] = fwd[(k - 1) % CELLS] ^ carry
            out[base + CELLS + k] = rev[(k + 1) % CELLS] ^ carry
        out[base + 2 * CELLS] = fwd[0] & rev[0]
        out[base + 2 * CELLS + 1] = pub | carry
    return out


def reference_recv(filled):
    # recv' = old carry & old carry = 0 on first pulse from empty carry
    return [0] * CLOCK_BANK


def reference_growth(grid, gen):
    g = [0] * GROWTH_CELLS
    if not gen:
        return g
    for r in range(H):
        for cc in range(W):
            v = grid[r][cc] & 1
            e = ((v ^ (grid[(r - 1) % H][cc] & 1))
                 | (v ^ (grid[(r + 1) % H][cc] & 1))
                 | (v ^ (grid[r][(cc + 1) % W] & 1))
                 | (v ^ (grid[r][(cc - 1) % W] & 1)))
            g[cidx(r, cc)] = e
    return g


def field_writes_after_reads(c):
    field = set(range(c.state_lo, c.state_hi))
    seen_write = False
    for op, a, b, out, kind in c.gates:
        if isinstance(out, tuple):
            continue
        if seen_write and (a in field or b in field) and out not in field:
            return False
        if out in field:
            seen_write = True
    return True


def one_writer(c):
    seen = {}
    for gi, (op, a, b, out, kind) in enumerate(c.gates):
        key = out if not isinstance(out, tuple) else ("G", out[1])
        if key in seen:
            return False, (key, seen[key], gi)
        seen[key] = gi
    for i in range(c.state_lo, c.ring_hi):
        if i not in seen:
            return False, ("unwritten", i, None)
    return True, None


def serialize(c):
    n_logic = len(c.gates)
    n_grow = len(c.growth)
    n_gate = n_logic + n_grow
    n_wire = len(c.wires)
    growth_base = HDR + n_wire + n_gate * STRIDE
    for op, a, b, cell_i in c.growth:
        c.gates.append((op, a, b, ("GROWTH", cell_i), "GROWTH"))
    depth = 0
    for i in range(c.state_lo, c.ring_hi):
        if c.dep[i] > depth:
            depth = c.dep[i]
    ring_base = c.addr(c.ring_lo)
    cell_base = c.addr(c.state_lo)
    clock_base = c.addr(c.clock_lo)
    body = bytearray()
    body += MAGIC
    body += struct.pack("<IIIII", FIELD_BITS, n_wire, n_gate, FIELD_BITS, depth)
    body += struct.pack("<IIII", W, H, CELL_BITS, STRIDE)
    body += struct.pack("<QQQQQ", c.wire_base, cell_base, ring_base, clock_base, growth_base)
    body += struct.pack("<III", N_RINGS, CELLS, SENSES)
    assert len(body) == HDR
    body += bytes(v & 1 for v in c.wires)
    for op, a, b, out, kind in c.gates:
        if isinstance(out, tuple) and out[0] == "GROWTH":
            oa, ob, oo = c.addr(a), c.addr(b), growth_base + out[1]
        else:
            oa, ob, oo = c.addr(a), c.addr(b), c.addr(out)
        body += struct.pack("<BQQQ", op, oa, ob, oo)
    assert len(body) == growth_base
    body += bytes(GROWTH_CELLS)
    return bytes(body), n_gate, n_wire, depth, ring_base, cell_base, clock_base, growth_base


def audit_ops(c):
    for op, a, b, out, kind in c.gates:
        if kind == "RING" and op not in (W_XOR, W_AND, W_OR):
            return False, ("ring_op", op)
        if kind == "NET" and op not in (NAND, AND):
            return False, ("net_op", op)
        if kind == "GROWTH" and op not in (NAND, AND):
            return False, ("growth_op", op)
    return True, None


def verify_blob(blob, seed_state, filled):
    raw = put_field(charge_rings(blob, filled), seed_state)
    new, pad, h = settle_stored(raw)
    sl = h["cell_base"] - h["wire_base"]
    got = decode_grid(new[sl: sl + FIELD_BITS])
    grid = decode_grid(seed_state)
    qen = [1 if (filled[q] and True) else 0 for q in range(4)]
    # enable = XOR(fwd[0],fwd[1]); charged fwd[0]=1 fwd[1]=0 → enable 1
    ref = reference_field(grid, qen)
    field_ok = got == ref
    rl = h["ring_base"] - h["wire_base"]
    got_r = [new[rl + i] & 1 for i in range(N_RINGS * RING_STATE)]
    ring_ok = got_r == reference_rings(filled)
    kl = h["clock_base"] - h["wire_base"]
    got_k = [new[kl + i] & 1 for i in range(CLOCK_BANK)]
    recv_ok = got_k == reference_recv(filled)
    grow_ok = pad == reference_growth(grid, 1 if filled[4] else 0)
    return field_ok and ring_ok and recv_ok and grow_ok, {
        "field": field_ok, "rings": ring_ok, "recv": recv_ok, "growth": grow_ok,
        "cell05": got[0][5], "cell06": got[0][6],
        "ref05": ref[0][5], "ref06": ref[0][6],
    }


def file_order_bits(bits):
    lines = []
    for r in range(H):
        row = bits[r * W * CELL_BITS:(r + 1) * W * CELL_BITS]
        lines.append(" ".join("".join(str(b & 1) for b in row[c * CELL_BITS:(c + 1) * CELL_BITS]) for c in range(W)))
    return lines


def journal(rec):
    with open(JRNL, "a") as f:
        f.write(json.dumps(rec) + "\n")


def main():
    random.seed(20260816)
    if os.path.isfile(V1) and not os.path.isfile(V1VAULT):
        shutil.copy2(V1, V1VAULT)
        journal({"action": "weather_v1_vault", "path": V1VAULT,
                 "sha256": hashlib.sha256(open(V1VAULT, "rb").read()).hexdigest(),
                 "len": os.path.getsize(V1VAULT),
                 "note": "UNPOWERED FOSSIL — kite REPLACE miss. powered ORs kite."})

    seed_state, gen_grid, center_before, gen_sha = load_genesis_or_kite()
    c = build(seed_state)
    ok1, w = one_writer(c)
    assert ok1, "ONE-WRITER %r" % (w,)
    assert field_writes_after_reads(c), "FIELD WRITES INTERLEAVED — nxt crutch, REFUSING"
    okops, wo = audit_ops(c)
    assert okops, "OP ALPHABET %r" % (wo,)

    # serialize first so verify ADDRESSES stored records (not Circuit.simulate)
    body, n_gate, n_wire, depth, ring_base, cell_base, clock_base, growth_base = serialize(c)
    assert cell_base == 98, "cell_base %d != 98" % cell_base
    stored = list(body[cell_base: cell_base + FIELD_BITS])
    assert stored == [v & 1 for v in seed_state], "stored field != OR'd genesis — REFUSING"
    assert all(body[ring_base + i] == 0 for i in range(N_RINGS * RING_STATE)), "rings not empty at fab"
    h = parse_header(body)
    assert h["n_in"] == 2048 and h["n_out"] == 2048
    assert h["n_wire"] == n_wire and h["n_gate"] == n_gate

    filled_on = [1] * N_RINGS
    filled_off = [0] * N_RINGS
    cases = []

    good, parts = verify_blob(body, seed_state, filled_off)
    cases.append(("genesis_rings_empty_HOLD", good, parts))
    good, parts = verify_blob(body, seed_state, filled_on)
    cases.append(("genesis_rings_charged_DIFFUSE", good, parts))

    n_rand = 40
    fail_on = fail_off = 0
    for _ in range(n_rand):
        g = [[random.randint(0, 255) for _ in range(W)] for _ in range(H)]
        st = state_from_grid(g)
        ok, _ = verify_blob(body, st, filled_on)
        if not ok:
            fail_on += 1
        ok, _ = verify_blob(body, st, filled_off)
        if not ok:
            fail_off += 1
    cases.append(("random_charged", fail_on == 0, {"fails": fail_on, "n": n_rand}))
    cases.append(("random_empty_hold", fail_off == 0, {"fails": fail_off, "n": n_rand}))

    mixed = [0, 1, 1, 1, 1, 1]
    fail_m = 0
    for _ in range(20):
        g = [[random.randint(0, 255) for _ in range(W)] for _ in range(H)]
        ok, _ = verify_blob(body, state_from_grid(g), mixed)
        if not ok:
            fail_m += 1
    cases.append(("mixed_Q0_off", fail_m == 0, {"fails": fail_m, "n": 20}))

    def caught(mut, filled):
        m = build(seed_state, **mut)
        mb, _, _, _, _, _, _, _ = serialize(m)
        g = [[random.randint(0, 255) for _ in range(W)] for _ in range(H)]
        ok, _ = verify_blob(mb, state_from_grid(g), filled)
        return not ok

    mutants = {
        "drop_shift": caught({"drop_shift": True}, filled_on),
        "swap_neighbor": caught({"swap_neighbor": True}, filled_on),
        "drop_carry": caught({"drop_carry": True}, filled_on),
        "ungated_vs_empty": caught({"ungated": True}, filled_off),
        "interleave_writes_is_crutch": caught({"interleave_writes": True}, filled_on)
        or (not field_writes_after_reads(build(seed_state, interleave_writes=True))),
    }
    # interleave must be structurally illegal; if settle latches, it may still match ref —
    # the catch is field_writes_after_reads == False (crutch emit). Force True catch:
    mutants["interleave_writes_is_crutch"] = not field_writes_after_reads(
        build(seed_state, interleave_writes=True))

    all_caught = all(mutants.values())
    verified = all(x[1] for x in cases) and all_caught
    if not verified:
        print("REFUSING", [(n, ok) for n, ok, _ in cases], mutants)
        return 1

    # growth OUTs in this file's gate-record region
    grow_outs = []
    gb = h["gate_base"]
    for k in range(n_gate):
        op, a, b, out = struct.unpack_from("<BQQQ", body, gb + k * STRIDE)
        if growth_base <= out < growth_base + GROWTH_CELLS:
            grow_outs.append(out)
    assert len(grow_outs) == GROWTH_CELLS, len(grow_outs)
    assert min(grow_outs) == growth_base

    with open(OUT, "wb") as f:
        f.write(body)
    # ADDRESS the file that was stored — parse dests FROM THE FILE, settle stored records
    on_disk = open(OUT, "rb").read()
    assert on_disk == body
    hd = parse_header(on_disk)
    assert hd["cell_base"] == 98
    good, parts = verify_blob(on_disk, seed_state, filled_off)
    assert good, "FILE ADDRESS HOLD FAIL %r" % parts
    good_on, parts_on = verify_blob(on_disk, seed_state, filled_on)
    assert good_on, "FILE ADDRESS DIFFUSE FAIL %r" % parts_on
    sha = hashlib.sha256(on_disk).hexdigest()

    bits_doc = []
    bits_doc.append("WEATHER POWERED — BEFORE FIRE — bits as they lie in the file")
    bits_doc.append("sha256 " + sha)
    bits_doc.append("cell_base %d gate_base %d ring_base %d clock_base %d growth_base %d" % (
        hd["cell_base"], hd["gate_base"], hd["ring_base"], hd["clock_base"], hd["growth_base"]))
    field = list(on_disk[hd["cell_base"]: hd["cell_base"] + FIELD_BITS])
    bits_doc.append("== FIELD ==")
    bits_doc += file_order_bits(field)
    bits_doc.append("== RINGS (empty until fire) ==")
    for ri, name in enumerate(RING_NAMES):
        fwd = "".join(str(on_disk[hd["ring_base"] + ri * RING_STATE + k] & 1) for k in range(8))
        rev = "".join(str(on_disk[hd["ring_base"] + ri * RING_STATE + CELLS + k] & 1) for k in range(8))
        bits_doc.append("%s fwd[0:8]=%s rev[0:8]=%s  dest_fwd0=%d dest_rev0=%d  %s" % (
            name, fwd, rev, hd["ring_base"] + ri * RING_STATE,
            hd["ring_base"] + ri * RING_STATE + CELLS, RING_PURPOSE[name]))
    open(BEFORE_BITS, "w").write("\n".join(bits_doc))

    rec = {
        "action": "weather_fab_powered",
        "path": OUT,
        "len": len(on_disk),
        "orig": V1VAULT if os.path.isfile(V1VAULT) else V1,
        "sha256": sha,
        "n_gate": n_gate,
        "n_wire": n_wire,
        "depth_ticks": depth,
        "header": "+8 <IIIII> n_in n_wire n_gate n_out depth  (HIS order, magic WEATHER1)",
        "cell_base": hd["cell_base"],
        "gate_base": hd["gate_base"],
        "ring_base": hd["ring_base"],
        "clock_base": hd["clock_base"],
        "growth_base": hd["growth_base"],
        "rings": RING_PURPOSE,
        "kite": "OR onto genesis (new=old|0xFF at nine 1-cells; zero-pattern keeps genesis)",
        "genesis_sha256": gen_sha,
        "genesis_center_before_or": center_before,
        "status": "VERIFIED_STORED_SETTLE_PENDING_FIRE",
    }
    journal(rec)

    report = {
        "container": OUT,
        "bytes": len(on_disk),
        "sha256": sha,
        "magic": "WEATHER1",
        "header_+8": "n_in n_wire n_gate n_out depth",
        "n_in": 2048, "n_wire": n_wire, "n_gate": n_gate, "n_out": 2048,
        "depth_ticks": depth,
        "cell_base": hd["cell_base"],
        "gate_base": hd["gate_base"],
        "ring_base": hd["ring_base"],
        "clock_base": hd["clock_base"],
        "growth_base": hd["growth_base"],
        "n_rings": 6, "cells": 32, "senses": 2,
        "rings": [{"name": n, "purpose": RING_PURPOSE[n],
                   "fwd0": hd["ring_base"] + i * RING_STATE,
                   "rev0": hd["ring_base"] + i * RING_STATE + CELLS,
                   "carry": hd["ring_base"] + i * RING_STATE + 2 * CELLS,
                   "pub": hd["ring_base"] + i * RING_STATE + 2 * CELLS + 1,
                   "recv": hd["clock_base"] + i} for i, n in enumerate(RING_NAMES)],
        "opcode": {"NAND": 0, "AND": 1, "OR": 2, "XOR": 3, "NOT": 4},
        "field_ops": "NAND/AND",
        "ring_ops": "XOR=3 AND=1 OR=2",
        "kite": "OR mask, nine 1-blocks, genesis zero-pattern preserved",
        "verification": [(n, ok) for n, ok, _ in cases],
        "verify_parts_genesis_on": parts_on,
        "mutants_caught": mutants,
        "verified_stored_settle": verified,
        "one_writer": "clean",
        "field_writes_after_reads": True,
        "status": "VERIFIED_STORED_SETTLE_PENDING_FIRE",
    }
    with open(REPORT, "w") as f:
        json.dump(report, f, indent=2)

    print("WROTE", OUT, len(on_disk), "B")
    print("  sha", sha)
    print("  n_in=2048 n_wire=%d n_gate=%d n_out=2048 depth=%d TICKS" % (n_wire, n_gate, depth))
    print("  cell_base=%d gate_base=%d ring_base=%d clock_base=%d growth_base=%d" % (
        hd["cell_base"], hd["gate_base"], hd["ring_base"], hd["clock_base"], hd["growth_base"]))
    for i, n in enumerate(RING_NAMES):
        print("  RING", n, "fwd0", hd["ring_base"] + i * RING_STATE,
              "rev0", hd["ring_base"] + i * RING_STATE + CELLS, ":", RING_PURPOSE[n])
    print("  kite OR; genesis center before", [hex(x) for x in center_before[:4]], "...")
    print("  cases", [(n, ok) for n, ok, _ in cases])
    print("  mutants", mutants)
    print("  addressed stored records: HOLD + DIFFUSE")
    print("  fab dies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
