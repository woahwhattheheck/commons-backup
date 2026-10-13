#!/usr/bin/env python3
# muhl_fab_probe_pop.py
# Axiom blessing: the probe PUBLISHES a ones-count at dests the file names.
# NEW LAND. Does not smash axiom_probe.mno / weather_v2 / titan / dc.
# 20 weather dest bits into inj. Field latches on fire (same nring law).
# Popcount tree of the 20 inj bits writes 5 bits at growth_base+1..5.
# Header +92 names growth_base. Reader addresses records; pad settles.
# Fab, address, die.

import hashlib, json, os, struct, sys

NAND, AND, OR, XOR = 0, 1, 2, 3
W_XOR, W_AND, W_OR = 3, 1, 2
STRIDE = 25
HDR = 96
CELLS = 32
RING_SPAN = CELLS + CELLS + 2
MAGIC = b"PROBEPOP"
OUT = r"C:\Users\lucys\Desktop\WEATHER\axiom_probe_pop.mno"
N_IN = 20
POP_BITS = 5
RINGS = [
    ("V2", "telemetry — weather_v2 ring0/clock/carry/pub"),
    ("AVG4", "telemetry — weather_v2_avg4full dests"),
    ("XORW", "telemetry — weather_v2_xorwalk dests (surface only, leftover no re-OR)"),
    ("FIELD", "telemetry — weather_v2_field dests"),
    ("COUP", "telemetry — weather_v2_coupled dests"),
    ("WITNESS", "power — AND(carry,carry) OUT clock_bank; popcount pad lives after growth"),
]


class Net:
    def __init__(self, n_fixed):
        self.n_fixed = n_fixed
        self.n = n_fixed
        self.gates = []
        self.dep = [0] * n_fixed
        self.inv = {}
        self.origin = {}

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
        t = self.tmp()
        self.emit(NAND, a, b, t)
        return t

    def and_(self, a, b):
        t = self.tmp()
        self.emit(AND, a, b, t)
        return t

    def not_(self, a):
        if a in self.origin:
            return self.origin[a]
        if a in self.inv:
            return self.inv[a]
        t = self.nand(a, a)
        self.inv[a] = t
        self.origin[t] = a
        return t

    def or_(self, a, b):
        return self.nand(self.not_(a), self.not_(b))

    def xor(self, a, b):
        n = self.nand(a, b)
        return self.nand(self.nand(a, n), self.nand(b, n))

    def mux(self, s, hold, nxt):
        return self.or_(self.and_(self.not_(s), hold), self.and_(s, nxt))

    def add(self, A, B):
        L = max(len(A), len(B))
        A = A + [0] * (L - len(A))
        B = B + [0] * (L - len(B))
        P0 = [self.xor(A[i], B[i]) for i in range(L)]
        P = [self.or_(A[i], B[i]) for i in range(L)]
        G = [self.and_(A[i], B[i]) for i in range(L)]
        d = 1
        while d < L:
            nG, nP = list(G), list(P)
            for i in range(d, L):
                nG[i] = self.nand(self.not_(G[i]), self.nand(P[i], G[i - d]))
                nP[i] = self.and_(P[i], P[i - d])
            G, P = nG, nP
            d <<= 1
        S = [P0[0]] + [self.xor(P0[i], G[i - 1]) for i in range(1, L)]
        return S + [G[L - 1]]

    def popcount(self, bits):
        vecs = [[b] for b in bits]
        while len(vecs) > 1:
            nxt = []
            i = 0
            while i < len(vecs):
                if i + 1 < len(vecs):
                    nxt.append(self.add(vecs[i], vecs[i + 1]))
                    i += 2
                else:
                    nxt.append(vecs[i])
                    i += 1
            vecs = nxt
        return (vecs[0] + [0] * POP_BITS)[:POP_BITS]


def layout(n_rings, n_in):
    clock = 2
    ring0 = clock + n_rings
    inj = ring0 + n_rings * RING_SPAN
    field = inj + n_in
    fixed = field + n_in
    return {"clock": clock, "ring0": ring0, "inj": inj, "field": field, "fixed": fixed}


def ring_fwd(L, ri):
    return L["ring0"] + ri * RING_SPAN


def ring_rev(L, ri):
    return ring_fwd(L, ri) + CELLS


def ring_carry(L, ri):
    return ring_fwd(L, ri) + 2 * CELLS


def ring_pub(L, ri):
    return ring_fwd(L, ri) + 2 * CELLS + 1


def emit_rings(L, n_rings):
    recs = []
    for ri in range(n_rings):
        f, r, c, p = ring_fwd(L, ri), ring_rev(L, ri), ring_carry(L, ri), ring_pub(L, ri)
        for k in range(CELLS):
            recs.append((W_XOR, f + (k - 1) % CELLS, c, f + k))
        for k in range(CELLS):
            recs.append((W_XOR, r + (k + 1) % CELLS, c, r + k))
        recs.append((W_AND, f, r, c))
        recs.append((W_OR, p, c, p))
        recs.append((W_AND, c, c, L["clock"] + ri))
    return recs


def ring_of(i):
    return min(i // 4, 4)


def emit_net(L, n_in, n_rings, ungated=False):
    net = Net(L["fixed"])
    inj, field = L["inj"], L["field"]
    for i in range(n_in):
        ri = ring_of(i) % n_rings
        en = 1 if ungated else net.and_(ring_fwd(L, ri), ring_rev(L, ri))
        bit = inj + i if ungated else net.mux(en, field + i, inj + i)
        net.emit(AND, bit, bit, field + i)
    bits = [inj + i for i in range(n_in)]
    pop = net.popcount(bits)
    return net, pop


def pack_header(n_in, n_wire, n_gate, n_out, depth, L, growth_base, n_rings):
    wb = HDR
    body = bytearray()
    body += MAGIC
    body += struct.pack("<IIII", n_in, n_wire, n_gate, n_out)
    body += struct.pack("<I", depth)
    body += struct.pack("<IIII", n_in, 1, POP_BITS, STRIDE)
    body += struct.pack("<Q", wb)
    body += struct.pack("<Q", wb + L["field"])
    body += struct.pack("<Q", wb + L["inj"])
    body += struct.pack("<II", n_rings, CELLS)
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
    wire_base, cell_base, inj_base = struct.unpack_from("<QQQ", raw, 44)
    n_rings, cells = struct.unpack_from("<II", raw, 68)
    ring0, clock = struct.unpack_from("<QQ", raw, 76)
    growth = struct.unpack_from("<I", raw, 92)[0]
    return {
        "n_in": n_in, "n_wire": n_wire, "n_gate": n_gate, "n_out": n_out,
        "depth": depth, "wire_base": wire_base, "cell_base": cell_base,
        "inj_base": inj_base, "n_rings": n_rings, "cells": cells,
        "ring0": ring0, "clock": clock, "growth_base": growth,
    }


def address_stored(img):
    h = parse_hdr(img)
    n_wire, n_gate = h["n_wire"], h["n_gate"]
    gate_base = HDR + n_wire
    for k in range(n_gate):
        op, a, b, out = struct.unpack_from("<BQQQ", img, gate_base + k * STRIDE)
        va, vb = img[a] & 1, img[b] & 1
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


def serialize(L, net, ring_recs, n_in, n_rings, inj_bits, field_bits, pop):
    n_wire = net.n
    wires = [0] * n_wire
    wires[1] = 1
    for i, v in enumerate(inj_bits):
        wires[L["inj"] + i] = v & 1
    for i, v in enumerate(field_bits):
        wires[L["field"] + i] = v & 1
    recs = list(net.gates) + list(ring_recs)
    gcarry = ring_carry(L, n_rings - 1)
    recs.append((W_AND, gcarry, gcarry, ("GROWTH", 0)))
    for i, w in enumerate(pop):
        recs.append((AND, w, w, ("POP", i + 1)))
    n_gate = len(recs)
    growth_base = HDR + n_wire + n_gate * STRIDE
    depth = 0
    if net.dep:
        depth = max(net.dep[L["fixed"]:] or [0])
    hdr = pack_header(n_in, n_wire, n_gate, n_in, depth, L, growth_base, n_rings)
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
    body += b"\x00" * (1 + POP_BITS)
    return bytes(body), n_gate, n_wire, depth, growth_base


def one_writer(recs):
    seen = {}
    for i, rec in enumerate(recs):
        out = rec[3]
        if out in seen:
            return False, (out, seen[out], i)
        seen[out] = i
    return True, None


def field_from(img, h):
    return [img[h["cell_base"] + i] & 1 for i in range(h["n_in"])]


def pop_from(img, h):
    g = h["growth_base"]
    return [img[g + 1 + i] & 1 for i in range(POP_BITS)]


def main():
    if os.path.isfile(OUT):
        print("REFUSE — %s exists. New dest only." % OUT)
        return 2
    n_rings = len(RINGS)
    L = layout(n_rings, N_IN)
    ring_recs = emit_rings(L, n_rings)
    net, pop = emit_net(L, N_IN, n_rings)
    assert all(op in (NAND, AND) for op, _, _, _ in net.gates)
    assert all(op in (W_XOR, W_AND, W_OR) for op, _, _, _ in ring_recs)
    ok, w = one_writer(ring_recs + list(net.gates) + [(AND, 0, 0, ("POP", i + 1)) for i in range(POP_BITS)] + [(W_AND, 0, 0, ("GROWTH", 0))])
    # serialize assigns unique pad outs; check net+rings only here
    ok2, w2 = one_writer(ring_recs + [(op, a, b, o) for op, a, b, o in net.gates])
    assert ok2, "ONE-WRITER %r" % (w2,)

    inj0 = [0] * N_IN
    field0 = [0] * N_IN
    body, n_gate, n_wire, depth, growth_base = serialize(
        L, net, ring_recs, N_IN, n_rings, inj0, field0, pop)
    h = parse_hdr(body)

    def run(inj, fld, enables):
        img = bytearray(body)
        hh = parse_hdr(img)
        for i, v in enumerate(inj):
            img[hh["inj_base"] + i] = v & 1
        for i, v in enumerate(fld):
            img[hh["cell_base"] + i] = v & 1
        span = CELLS + CELLS + 2
        for ri, en in enumerate(enables):
            fwd = hh["ring0"] + ri * span
            img[fwd] = en & 1
            img[fwd + CELLS] = en & 1
        address_stored(img)
        hh = parse_hdr(img)
        return field_from(img, hh), pop_from(img, hh)

    on = [1] * n_rings
    off = [0] * n_rings
    inj1 = [i & 1 for i in range(N_IN)]
    fld1 = [1 - (i & 1) for i in range(N_IN)]

    def expect_field(inj, fld, enables):
        return [inj[i] if enables[ring_of(i) % n_rings] else fld[i] for i in range(N_IN)]

    def expect_pop(inj):
        s = sum(inj)
        return [(s >> i) & 1 for i in range(POP_BITS)]

    cases = []
    g, p = run(inj1, fld1, on)
    cases.append(("fire_take_inject", g == expect_field(inj1, fld1, on)))
    cases.append(("pop_on_fire", p == expect_pop(inj1)))
    g, p = run(inj1, fld1, off)
    cases.append(("dark_hold", g == expect_field(inj1, fld1, off)))
    cases.append(("pop_on_dark", p == expect_pop(inj1)))  # pop reads inj, not field
    mixed = [0] + [1] * (n_rings - 1)
    g, p = run(inj1, fld1, mixed)
    cases.append(("mixed_ring0_dark", g == expect_field(inj1, fld1, mixed)))
    img = bytearray(body)
    hh = parse_hdr(img)
    img[hh["ring0"]] = 1
    img[hh["ring0"] + CELLS] = 0
    address_stored(img)
    dc_hold = field_from(img, parse_hdr(img)) == field0
    cases.append(("one_sense_DC", dc_hold))
    all20 = [1] * N_IN
    _, p20 = run(all20, field0, on)
    cases.append(("pop_all20", p20 == expect_pop(all20)))
    none = [0] * N_IN
    _, p0 = run(none, [1] * N_IN, on)
    cases.append(("pop_none", p0 == expect_pop(none)))
    verified = all(c[1] for c in cases)
    if not verified:
        print("REFUSING", cases)
        return 1

    with open(OUT, "wb") as f:
        f.write(body)
    sha = hashlib.sha256(body).hexdigest()
    cpt = (float(n_gate) / depth) if depth else 0.0
    rec = {
        "action": "probe_pop_fab", "path": OUT, "len": len(body), "sha256": sha,
        "n_gate": n_gate, "n_wire": n_wire, "depth": depth,
        "computations_per_tick": cpt, "magic": MAGIC.decode("ascii"),
        "n_in": N_IN, "pop_bits": POP_BITS, "growth_base": growth_base,
        "pop_dests": [growth_base + 1 + i for i in range(POP_BITS)],
        "cases": cases, "status": "WROTE",
    }
    with open(OUT + ".genome.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    print("WROTE", OUT, len(body), "sha", sha)
    print("  magic", MAGIC, "n_in", N_IN, "n_wire", n_wire, "n_gate", n_gate)
    print("  depth", depth, "cpt", "%.3f" % cpt)
    print("  growth_base", growth_base)
    print("  pop dests", [growth_base + 1 + i for i in range(POP_BITS)])
    print("  cases", cases)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
