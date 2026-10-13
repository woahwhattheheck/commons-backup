#!/usr/bin/env python3
# muhl_fab_weather_v2.py
# WEATHER1 kept. +8 = HIS <IIII> n_in, n_wire, n_gate, n_out. Not MUHLPKG1.
# Six 32-cell both-sense rings. NAND avg4 -> NEXT (≠ field). Ring-gated latch.
# Verifier addresses STORED <BQQQ> with immediate writes. No host nxt.
# Does not overwrite v1. Does not touch titan/dc. Fab, address, die.

import struct, hashlib, json, os, random, shutil

HERE = r"C:\Users\lucys\Desktop\WEATHER"
GEN = os.path.join(HERE, "genesis_playtime_read.bin")
V1 = os.path.join(HERE, "weather.mno")
V1VAULT = os.path.join(HERE, "weather_v1.mno")
OUT = os.path.join(HERE, "weather_v2.mno")
JRNL = os.path.join(HERE, "weather_genome.jsonl")
REPORT = os.path.join(HERE, "weather_v2_fab_report.json")

W = H = 16
CELL_BITS = 8
FIELD_BITS = W * H * CELL_BITS
NAND, AND, OR, XOR = 0, 1, 2, 3
W_XOR, W_AND, W_OR = 3, 1, 2
STRIDE = 25
HDR = 96
MAGIC = b"WEATHER1"
N_RINGS = 6
CELLS = 32
RING_SPAN = CELLS + CELLS + 2
RING_NAMES = ["NW", "NE", "SW", "SE", "GROWTH", "WITNESS"]
RING_PURPOSE = {
    "NW": "cadence — both-sense carry gates avg4 rows 0-7 cols 0-7",
    "NE": "cadence — both-sense carry gates avg4 rows 0-7 cols 8-15",
    "SW": "cadence — both-sense carry gates avg4 rows 8-15 cols 0-7",
    "SE": "cadence — both-sense carry gates avg4 rows 8-15 cols 8-15",
    "GROWTH": "power — AND(carry,carry) OUT into this file's gate-record pad",
    "WITNESS": "power — AND(carry,carry) OUT into clock_bank, outside field",
}
KITE = ["0110", "1111", "0110", "0010"]
CAIRN = (5, 5, 0xC1)

def cidx(r, c):
    return (r % H) * W + (c % W)

def quadrant(r, c):
    if r < 8 and c < 8: return 0
    if r < 8: return 1
    if c < 8: return 2
    return 3

class Net:
    """NAND/AND field only. State inputs stay dep 0. NEXT ≠ FIELD."""
    def __init__(self, n_fixed):
        self.n_fixed = n_fixed
        self.n = n_fixed
        self.gates = []
        self.dep = [0] * n_fixed
    def tmp(self):
        i = self.n
        self.n += 1
        self.dep.append(0)
        return i
    def emit(self, op, a, b, out):
        assert op in (NAND, AND)
        self.gates.append((op, a, b, out))
        da = self.dep[a] if a < len(self.dep) else 0
        db = self.dep[b] if b < len(self.dep) else 0
        while out >= len(self.dep):
            self.dep.append(0)
        if out >= self.n_fixed:
            self.dep[out] = 1 + max(da, db)
    def nand(self, a, b):
        t = self.tmp(); self.emit(NAND, a, b, t); return t
    def and_(self, a, b):
        t = self.tmp(); self.emit(AND, a, b, t); return t
    def not_(self, a):
        return self.nand(a, a)
    def or_(self, a, b):
        return self.nand(self.not_(a), self.not_(b))
    def xor(self, a, b):
        n = self.nand(a, b)
        return self.nand(self.nand(a, n), self.nand(b, n))
    def mux(self, s, hold, nxt):
        return self.or_(self.and_(self.not_(s), hold), self.and_(s, nxt))
    def fa(self, a, b, cin):
        axb = self.xor(a, b)
        s = self.xor(axb, cin)
        cout = self.or_(self.and_(a, b), self.and_(axb, cin))
        return s, cout
    def add(self, A, B):
        L = max(len(A), len(B))
        A = A + [0] * (L - len(A))
        B = B + [0] * (L - len(B))
        carry = 0
        out = []
        for i in range(L):
            s, carry = self.fa(A[i], B[i], carry)
            out.append(s)
        out.append(carry)
        return out
    def avg4(self, N, S, E, Ww):
        tot = self.add(self.add(N, S), self.add(E, Ww))
        return tot[2:2 + CELL_BITS]

def layout():
    # wire 0,1 = const0, const1
    clock = 2
    ring0 = clock + N_RINGS
    field = ring0 + N_RINGS * RING_SPAN
    nxt = field + FIELD_BITS
    fixed = nxt + FIELD_BITS
    return {
        "clock": clock, "ring0": ring0, "field": field, "next": nxt, "fixed": fixed,
    }

def ring_fwd(L, ri):
    return L["ring0"] + ri * RING_SPAN

def ring_rev(L, ri):
    return ring_fwd(L, ri) + CELLS

def ring_carry(L, ri):
    return ring_fwd(L, ri) + 2 * CELLS

def ring_pub(L, ri):
    return ring_fwd(L, ri) + 2 * CELLS + 1

def emit_rings(L):
    recs = []
    for ri in range(N_RINGS):
        f, r, c, p = ring_fwd(L, ri), ring_rev(L, ri), ring_carry(L, ri), ring_pub(L, ri)
        for k in range(CELLS):
            recs.append((W_XOR, f + (k - 1) % CELLS, c, f + k))
        for k in range(CELLS):
            recs.append((W_XOR, r + (k + 1) % CELLS, c, r + k))
        recs.append((W_AND, f, r, c))
        recs.append((W_OR, p, c, p))
        recs.append((W_AND, c, c, L["clock"] + ri))
    return recs

def emit_net(L, drop_shift=False, swap_neighbor=False, ungated=False):
    net = Net(L["fixed"])
    field, nxt = L["field"], L["next"]
    def cell(r, c, b):
        return field + cidx(r, c) * CELL_BITS + b
    def ncell(r, c, b):
        return nxt + cidx(r, c) * CELL_BITS + b
    for r in range(H):
        for cc in range(W):
            N = [cell(r - 1, cc, b) for b in range(CELL_BITS)]
            S = [cell(r + 1, cc, b) for b in range(CELL_BITS)]
            E = [cell(r, cc + 2 if swap_neighbor else cc + 1, b) for b in range(CELL_BITS)]
            Ww = [cell(r, cc - 1, b) for b in range(CELL_BITS)]
            tot = net.add(net.add(N, S), net.add(E, Ww))
            avg = tot[0:CELL_BITS] if drop_shift else tot[2:2 + CELL_BITS]
            avg = avg + [0] * (CELL_BITS - len(avg))
            for b in range(CELL_BITS):
                net.emit(AND, avg[b], avg[b], ncell(r, cc, b))
    for r in range(H):
        for cc in range(W):
            ri = quadrant(r, cc)
            en = 1 if ungated else net.and_(ring_fwd(L, ri), ring_rev(L, ri))
            for b in range(CELL_BITS):
                bit = ncell(r, cc, b) if ungated else net.mux(en, cell(r, cc, b), ncell(r, cc, b))
                net.emit(AND, bit, bit, cell(r, cc, b))
    return net

def load_genesis():
    if os.path.isfile(GEN):
        raw = open(GEN, "rb").read()
        assert len(raw) == FIELD_BITS
        bits = [bb & 1 for bb in raw]
    elif os.path.isfile(V1):
        raw = open(V1, "rb").read()
        cell_base = struct.unpack_from("<Q", raw, 44)[0]
        bits = [raw[cell_base + i] & 1 for i in range(FIELD_BITS)]
        return bits
    else:
        raise SystemExit("no genesis and no v1")
    grid = [[0] * W for _ in range(H)]
    for i in range(W * H):
        v = 0
        for b in range(CELL_BITS):
            v |= bits[i * CELL_BITS + b] << b
        grid[i // W][i % W] = v
    for i, row in enumerate(KITE):
        for j, ch in enumerate(row):
            grid[6 + i][6 + j] = 0xFF if ch == "1" else 0
    r, c, val = CAIRN
    grid[r][c] = val
    out = [0] * FIELD_BITS
    for rr in range(H):
        for cc in range(W):
            v = grid[rr][cc]
            for b in range(CELL_BITS):
                out[cidx(rr, cc) * CELL_BITS + b] = (v >> b) & 1
    return out

def decode(bits):
    g = [[0] * W for _ in range(H)]
    for i in range(W * H):
        v = 0
        for b in range(CELL_BITS):
            v |= (bits[i * CELL_BITS + b] & 1) << b
        g[i // W][i % W] = v
    return g

def reference(grid, qen):
    nxt = [row[:] for row in grid]
    for r in range(H):
        for c in range(W):
            if not qen[quadrant(r, c)]:
                continue
            n = (grid[(r - 1) % H][c] + grid[(r + 1) % H][c]
                 + grid[r][(c + 1) % W] + grid[r][(c - 1) % W])
            nxt[r][c] = (n >> 2) & 0xFF
    return nxt

def pack_header(n_in, n_wire, n_gate, n_out, depth, L, growth_base):
    wb = HDR
    body = bytearray()
    body += MAGIC
    body += struct.pack("<IIII", n_in, n_wire, n_gate, n_out)
    body += struct.pack("<I", depth)
    body += struct.pack("<IIII", W, H, CELL_BITS, STRIDE)
    body += struct.pack("<Q", wb)
    body += struct.pack("<Q", wb + L["field"])
    body += struct.pack("<Q", wb + L["next"])
    body += struct.pack("<II", N_RINGS, CELLS)
    body += struct.pack("<Q", wb + ring_fwd(L, 0))
    body += struct.pack("<Q", wb + L["clock"])
    assert len(body) == 92
    body += struct.pack("<I", growth_base & 0xFFFFFFFF)
    assert len(body) == HDR
    return body

def parse_hdr(raw):
    assert raw[:8] == MAGIC
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw, 8)
    depth = struct.unpack_from("<I", raw, 24)[0]
    gw, gh, cbits, stride = struct.unpack_from("<IIII", raw, 28)
    wire_base, cell_base, next_base = struct.unpack_from("<QQQ", raw, 44)
    n_rings, cells = struct.unpack_from("<II", raw, 68)
    ring0, clock = struct.unpack_from("<QQ", raw, 76)
    return {
        "n_in": n_in, "n_wire": n_wire, "n_gate": n_gate, "n_out": n_out,
        "depth": depth, "W": gw, "H": gh, "CELL_BITS": cbits, "STRIDE": stride,
        "wire_base": wire_base, "cell_base": cell_base, "next_base": next_base,
        "n_rings": n_rings, "cells": cells, "ring0": ring0, "clock": clock,
    }

def address_stored(img):
    """Immediate write to each stored out. No nxt. This is the file's law."""
    h = parse_hdr(img)
    wb, n_wire, n_gate = h["wire_base"], h["n_wire"], h["n_gate"]
    gate_base = HDR + n_wire
    for k in range(n_gate):
        op, a, b, out = struct.unpack_from("<BQQQ", img, gate_base + k * STRIDE)
        va = img[a] & 1
        vb = img[b] & 1
        if op == NAND:
            r = 1 - (va & vb)
        elif op == AND:
            r = va & vb
        elif op == OR:
            r = va | vb
        elif op == XOR:
            r = va ^ vb
        else:
            raise ValueError(op)
        img[out] = r
    return img

def serialize(L, net, ring_recs, field_bits, growth_out_wire):
    n_fixed = L["fixed"]
    n_wire = net.n
    wires = [0] * n_wire
    wires[1] = 1
    for i, v in enumerate(field_bits):
        wires[L["field"] + i] = v & 1
    # NET first so fire 0x01 both senses is still on the rails when mux reads.
    # Ring XOR-rotate after would eat fwd[0] before avg4 if rings ran first.
    recs = list(net.gates) + list(ring_recs)
    # growth junction: AND(growth.carry, carry) -> last wire reserved then patched to pad
    gcarry = ring_carry(L, 4)
    recs.append((W_AND, gcarry, gcarry, ("GROWTH", 0)))
    n_gate = len(recs)
    growth_base = HDR + n_wire + n_gate * STRIDE
    depth = 0
    if net.dep:
        depth = max(net.dep[n_fixed:] or [0])
    hdr = pack_header(FIELD_BITS, n_wire, n_gate, FIELD_BITS, depth, L, growth_base)
    body = bytearray(hdr)
    body += bytes(wires)
    for op, a, b, out in recs:
        if isinstance(out, tuple):
            oo = growth_base + out[1]
            aa, bb = HDR + a, HDR + b
        else:
            aa, bb, oo = HDR + a, HDR + b, HDR + out
        body += struct.pack("<BQQQ", op, aa, bb, oo)
    assert len(body) == growth_base
    body += b"\x00"  # growth pad byte 0
    return bytes(body), n_gate, n_wire, depth, growth_base

def one_writer(recs):
    seen = {}
    for i, (op, a, b, out) in enumerate(recs):
        if out in seen:
            return False, (out, seen[out], i)
        seen[out] = i
    return True, None

def net_ops_ok(net):
    return all(op in (NAND, AND) for op, a, b, o in net.gates)

def ring_ops_ok(recs):
    return all(op in (W_XOR, W_AND, W_OR) for op, a, b, o in recs)

def set_ring_fire(img, h, mask):
    """mask[ri]=1 writes 0x01 both senses cell 0 (the fire)."""
    for ri, on in enumerate(mask):
        fwd = h["ring0"] + ri * RING_SPAN
        rev = fwd + h["cells"]
        if on:
            img[fwd] = 1
            img[rev] = 1
        else:
            img[fwd] = 0
            img[rev] = 0

def field_from(img, h):
    return [img[h["cell_base"] + i] & 1 for i in range(FIELD_BITS)]

def verify_image(body, field_bits, mask):
    img = bytearray(body)
    h = parse_hdr(img)
    for i, v in enumerate(field_bits):
        img[h["cell_base"] + i] = v & 1
    set_ring_fire(img, h, mask)
    address_stored(img)
    got = decode(field_from(img, h))
    grid = decode(field_bits)
    qen = [1 if mask[q] else 0 for q in range(4)]
    ref = reference(grid, qen)
    return got == ref, got, ref

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
                 "note": "do not promote v1"})

    field_bits = load_genesis()
    L = layout()
    ring_recs = emit_rings(L)
    net = emit_net(L)
    assert net_ops_ok(net), "XOR/OR leaked into net"
    assert ring_ops_ok(ring_recs), "bad ring op"
    ok, w = one_writer(ring_recs + [(op, a, b, out) for op, a, b, out in net.gates])
    assert ok, "ONE-WRITER %r" % (w,)

    body, n_gate, n_wire, depth, growth_base = serialize(L, net, ring_recs, field_bits, 0)
    h = parse_hdr(body)
    assert h["n_in"] == FIELD_BITS and h["n_wire"] == n_wire
    assert struct.unpack_from("<IIII", body, 8) == (FIELD_BITS, n_wire, n_gate, FIELD_BITS)

    cases = []
    on = [1] * 6
    off = [0] * 6
    good, _, _ = verify_image(body, field_bits, on)
    cases.append(("genesis_fire_both_senses", good))
    good0, _, _ = verify_image(body, field_bits, off)
    cases.append(("genesis_dark_hold", good0))
    n = 12
    fail_on = fail_off = fail_m = 0
    for _ in range(n):
        g = [[random.randint(0, 255) for _ in range(W)] for _ in range(H)]
        bits = [0] * FIELD_BITS
        for r in range(H):
            for c in range(W):
                for b in range(CELL_BITS):
                    bits[cidx(r, c) * CELL_BITS + b] = (g[r][c] >> b) & 1
        if not verify_image(body, bits, on)[0]:
            fail_on += 1
        if not verify_image(body, bits, off)[0]:
            fail_off += 1
        mixed = [0, 1, 1, 1, 1, 1]
        if not verify_image(body, bits, mixed)[0]:
            fail_m += 1
    cases.append(("random_fire", fail_on == 0, fail_on, n))
    cases.append(("random_dark_hold", fail_off == 0, fail_off, n))
    cases.append(("mixed_NW_dark", fail_m == 0, fail_m, n))
    # one sense alone is DC
    img = bytearray(body)
    hh = parse_hdr(img)
    img[hh["ring0"]] = 1
    img[hh["ring0"] + CELLS] = 0
    address_stored(img)
    dc_hold = decode(field_from(img, hh)) == decode(field_bits)
    cases.append(("one_sense_DC", dc_hold))

    def mutant_caught(kwargs):
        n2 = emit_net(L, **kwargs)
        b2, _, _, _, _ = serialize(L, n2, ring_recs, field_bits, 0)
        g = [[random.randint(0, 255) for _ in range(W)] for _ in range(H)]
        bits = [0] * FIELD_BITS
        for r in range(H):
            for c in range(W):
                for b in range(CELL_BITS):
                    bits[cidx(r, c) * CELL_BITS + b] = (g[r][c] >> b) & 1
        ok_on = verify_image(b2, bits, on)[0]
        ok_off = verify_image(b2, bits, off)[0]
        return (not ok_on) or (not ok_off)

    mutants = {
        "drop_shift": mutant_caught({"drop_shift": True}),
        "swap_neighbor": mutant_caught({"swap_neighbor": True}),
        "ungated": mutant_caught({"ungated": True}),
    }
    both = good and good0
    verified = both and fail_on == 0 and fail_off == 0 and fail_m == 0 and dc_hold and all(mutants.values())
    if not verified:
        print("REFUSING", cases, mutants)
        return 1

    stored = list(body[h["cell_base"]: h["cell_base"] + FIELD_BITS])
    assert stored == field_bits, "stored field != genesis REFUSE"
    # rings dark in the file
    assert body[h["ring0"]] == 0 and body[h["ring0"] + CELLS] == 0

    with open(OUT, "wb") as f:
        f.write(body)
    sha = hashlib.sha256(body).hexdigest()
    journal({"action": "weather_fab_v2", "path": OUT, "len": len(body),
             "orig": V1VAULT if os.path.isfile(V1VAULT) else "",
             "sha256": sha, "n_gate": n_gate, "n_wire": n_wire, "depth": depth,
             "header_+8": "n_in,n_wire,n_gate,n_out", "magic": "WEATHER1",
             "rings": RING_PURPOSE, "growth_base": growth_base,
             "verify": "address_stored immediate outs, no nxt",
             "status": "PENDING"})
    report = {
        "container": OUT, "bytes": len(body), "sha256": sha, "magic": "WEATHER1",
        "plus8": {"n_in": FIELD_BITS, "n_wire": n_wire, "n_gate": n_gate, "n_out": FIELD_BITS},
        "depth_one_gated_tick": depth,
        "rings": [{"name": n, "purpose": RING_PURPOSE[n],
                   "fwd": HDR + ring_fwd(L, i), "rev": HDR + ring_rev(L, i),
                   "carry": HDR + ring_carry(L, i), "pub": HDR + ring_pub(L, i)}
                  for i, n in enumerate(RING_NAMES)],
        "cell_base": h["cell_base"], "next_base": h["next_base"],
        "clock_bank": h["clock"], "growth_base": growth_base,
        "cases": cases, "mutants": mutants,
        "verified_stored_outs": True,
        "status": "PENDING",
        "v1_promoted": False,
    }
    with open(REPORT, "w") as f:
        json.dump(report, f, indent=2)
    print("WROTE", OUT, len(body), "sha", sha)
    print("  +8 n_in,n_wire,n_gate,n_out", FIELD_BITS, n_wire, n_gate, FIELD_BITS)
    print("  depth", depth, "growth_base", growth_base)
    for i, n in enumerate(RING_NAMES):
        print("  RING", n, "fwd", HDR + ring_fwd(L, i), "rev", HDR + ring_rev(L, i), RING_PURPOSE[n])
    print("  cases", cases)
    print("  mutants", mutants)
    print("  PENDING — do not promote v1")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
