#!/usr/bin/env python3
# muhl_fab_nring_pkg.py
# NEW LAND n-ring computers. Does not smash weather_v2 / titan / dc / DISTRO.
# HIS nring2 formula. Field AND/NAND. Gated latch: ding takes inject, dark holds.
# Header: magic + n_in/n_wire/n_gate/n_out at 8/12/16/20. Dest FROM FILE.
# argv: tenancy | probe | foundry
# Fab, address, die.

import hashlib, json, os, struct, sys

NAND, AND, OR, XOR = 0, 1, 2, 3
W_XOR, W_AND, W_OR = 3, 1, 2
STRIDE = 25
HDR = 96
CELLS = 32
RING_SPAN = CELLS + CELLS + 2

PKGS = {
    "tenancy": {
        "magic": b"TENANCY1",
        "out": r"C:\Users\lucys\Desktop\MUHL_TENANCY\muhl_tenancy.mno",
        "n_in": 12,
        "rings": [
            ("PALF", "tenant — both-sense gates PALF inject slot"),
            ("NEFG", "tenant — both-sense gates NEFG object_a[0] slot"),
            ("ARDR", "tenant — both-sense gates ARDR inject slot"),
            ("VSCF", "tenant — both-sense gates VSCF input[0] slot"),
            ("KEGN", "tenant — both-sense gates KEGN input[0] slot"),
            ("NMPIS", "tenant — both-sense gates NMPIS input[0] slot"),
            ("AWCG", "tenant — both-sense gates AWCG input slot"),
            ("DMB", "tenant — both-sense gates DMB input slot"),
            ("CGAT", "tenant — both-sense gates CGAT input_U slot"),
            ("EAL", "tenant — both-sense gates EAL attractor_select slot"),
            ("MHA", "tenant — both-sense gates MHA input[0] slot"),
            ("HPC", "tenant — both-sense gates HPC input[0] slot"),
        ],
        "ring_of": lambda i: i,
    },
    "probe": {
        "magic": b"PROBEMN2",
        "out": r"C:\Users\lucys\Desktop\WEATHER\axiom_probe.mno",
        "n_in": 20,
        "rings": [
            ("V2", "telemetry — weather_v2 ring0/clock/carry/pub"),
            ("AVG4", "telemetry — weather_v2_avg4full dests"),
            ("XORW", "telemetry — weather_v2_xorwalk dests (surface only, leftover no re-OR on source)"),
            ("FIELD", "telemetry — weather_v2_field dests"),
            ("COUP", "telemetry — weather_v2_coupled dests"),
            ("WITNESS", "power — AND(carry,carry) OUT clock_bank"),
        ],
        "ring_of": lambda i: min(i // 4, 4),
    },
    "foundry": {
        "magic": b"FNDRYAC1",
        "out": r"C:\Users\lucys\Desktop\MUHL_FOUNDRY\foundry_acre.mno",
        "n_in": 65,
        "rings": [
            ("IN0", "foundry acre — gates phys inject bits 0-10"),
            ("IN1", "foundry acre — gates phys inject bits 11-21"),
            ("IN2", "foundry acre — gates phys inject bits 22-32"),
            ("IN3", "foundry acre — gates phys inject bits 33-43"),
            ("IN4", "foundry acre — gates phys inject bits 44-54"),
            ("FIRE", "foundry acre — gates phys inject bits 55-64 + start"),
        ],
        "ring_of": lambda i: min(i // 11, 5),
    },
}


class Net:
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
        t = self.tmp()
        self.emit(NAND, a, b, t)
        return t

    def and_(self, a, b):
        t = self.tmp()
        self.emit(AND, a, b, t)
        return t

    def not_(self, a):
        return self.nand(a, a)

    def or_(self, a, b):
        return self.nand(self.not_(a), self.not_(b))

    def mux(self, s, hold, nxt):
        return self.or_(self.and_(self.not_(s), hold), self.and_(s, nxt))


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


def emit_net(L, n_in, n_rings, ring_of, ungated=False):
    net = Net(L["fixed"])
    inj, field = L["inj"], L["field"]
    for i in range(n_in):
        ri = ring_of(i) % n_rings
        en = 1 if ungated else net.and_(ring_fwd(L, ri), ring_rev(L, ri))
        bit = inj + i if ungated else net.mux(en, field + i, inj + i)
        net.emit(AND, bit, bit, field + i)
    return net


def pack_header(magic, n_in, n_wire, n_gate, n_out, depth, L, growth_base, n_rings):
    wb = HDR
    body = bytearray()
    body += magic
    body += struct.pack("<IIII", n_in, n_wire, n_gate, n_out)
    body += struct.pack("<I", depth)
    body += struct.pack("<IIII", n_in, 1, 1, STRIDE)
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


def parse_hdr(raw, magic):
    assert raw[:8] == magic
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw, 8)
    depth = struct.unpack_from("<I", raw, 24)[0]
    wire_base, cell_base, inj_base = struct.unpack_from("<QQQ", raw, 44)
    n_rings, cells = struct.unpack_from("<II", raw, 68)
    ring0, clock = struct.unpack_from("<QQ", raw, 76)
    return {
        "n_in": n_in, "n_wire": n_wire, "n_gate": n_gate, "n_out": n_out,
        "depth": depth, "wire_base": wire_base, "cell_base": cell_base,
        "inj_base": inj_base, "n_rings": n_rings, "cells": cells,
        "ring0": ring0, "clock": clock,
    }


def address_stored(img, magic):
    h = parse_hdr(img, magic)
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


def serialize(magic, L, net, ring_recs, n_in, n_rings, inj_bits, field_bits):
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
    n_gate = len(recs)
    growth_base = HDR + n_wire + n_gate * STRIDE
    depth = 0
    if net.dep:
        depth = max(net.dep[L["fixed"]:] or [0])
    hdr = pack_header(magic, n_in, n_wire, n_gate, n_in, depth, L, growth_base, n_rings)
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
    body += b"\x00"
    return bytes(body), n_gate, n_wire, depth, growth_base


def one_writer(recs):
    seen = {}
    for i, rec in enumerate(recs):
        out = rec[3]
        if out in seen:
            return False, (out, seen[out], i)
        seen[out] = i
    return True, None


def net_ops_ok(net):
    return all(op in (NAND, AND) for op, _, _, _ in net.gates)


def ring_ops_ok(recs):
    return all(op in (W_XOR, W_AND, W_OR) for op, _, _, _ in recs)


def field_from(img, h):
    return [img[h["cell_base"] + i] & 1 for i in range(h["n_in"])]


def verify_image(body, magic, inj, field0, enables):
    img = bytearray(body)
    h = parse_hdr(img, magic)
    for i, v in enumerate(inj):
        img[h["inj_base"] + i] = v & 1
    for i, v in enumerate(field0):
        img[h["cell_base"] + i] = v & 1
    n_rings = h["n_rings"]
    span = h["cells"] + h["cells"] + 2
    for ri, en in enumerate(enables):
        fwd = h["ring0"] + ri * span
        img[fwd] = en & 1
        img[fwd + h["cells"]] = en & 1
    address_stored(img, magic)
    got = field_from(img, parse_hdr(img, magic))
    expect = []
    for i in range(h["n_in"]):
        ri = min(i, n_rings - 1)
        # ring_of applied by caller via enables already placed; expect uses enables[ring]
        expect.append(inj[i] if enables[ri] else field0[i])
    return got == expect, got, expect


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    kind = (argv[0] if argv else "").lower()
    if kind not in PKGS:
        print("REFUSE mode — tenancy | probe | foundry")
        return 2
    cfg = PKGS[kind]
    magic, out, n_in = cfg["magic"], cfg["out"], cfg["n_in"]
    rings = cfg["rings"]
    n_rings = len(rings)
    ring_of = cfg["ring_of"]
    if os.path.isfile(out):
        print("REFUSE — %s exists. New dest only." % out)
        return 2
    os.makedirs(os.path.dirname(out), exist_ok=True)

    L = layout(n_rings, n_in)
    ring_recs = emit_rings(L, n_rings)
    net = emit_net(L, n_in, n_rings, ring_of)
    assert net_ops_ok(net), "XOR/OR leaked into net"
    assert ring_ops_ok(ring_recs), "bad ring op"
    ok, w = one_writer(ring_recs + [(op, a, b, outw) for op, a, b, outw in net.gates])
    assert ok, "ONE-WRITER %r" % (w,)

    inj0 = [0] * n_in
    field0 = [0] * n_in
    body, n_gate, n_wire, depth, growth_base = serialize(
        magic, L, net, ring_recs, n_in, n_rings, inj0, field0)
    h = parse_hdr(body, magic)
    assert h["n_in"] == n_in and h["n_wire"] == n_wire

    # expect helper matching ring_of
    def expect_of(inj, fld, enables):
        return [inj[i] if enables[ring_of(i) % n_rings] else fld[i] for i in range(n_in)]

    def run(inj, fld, enables):
        img = bytearray(body)
        hh = parse_hdr(img, magic)
        for i, v in enumerate(inj):
            img[hh["inj_base"] + i] = v & 1
        for i, v in enumerate(fld):
            img[hh["cell_base"] + i] = v & 1
        span = CELLS + CELLS + 2
        for ri, en in enumerate(enables):
            fwd = hh["ring0"] + ri * span
            img[fwd] = en & 1
            img[fwd + CELLS] = en & 1
        address_stored(img, magic)
        return field_from(img, parse_hdr(img, magic))

    on = [1] * n_rings
    off = [0] * n_rings
    inj1 = [i & 1 for i in range(n_in)]
    fld1 = [1 - (i & 1) for i in range(n_in)]
    cases = []
    g_on = run(inj1, fld1, on)
    cases.append(("fire_take_inject", g_on == expect_of(inj1, fld1, on)))
    g_off = run(inj1, fld1, off)
    cases.append(("dark_hold", g_off == expect_of(inj1, fld1, off)))
    mixed = [0] + [1] * (n_rings - 1)
    g_m = run(inj1, fld1, mixed)
    cases.append(("mixed_ring0_dark", g_m == expect_of(inj1, fld1, mixed)))
    one = [1] + [0] * (n_rings - 1)
    img = bytearray(body)
    hh = parse_hdr(img, magic)
    img[hh["ring0"]] = 1
    img[hh["ring0"] + CELLS] = 0
    address_stored(img, magic)
    dc_hold = field_from(img, parse_hdr(img, magic)) == field0
    cases.append(("one_sense_DC", dc_hold))

    n2 = emit_net(L, n_in, n_rings, ring_of, ungated=True)
    b2, _, _, _, _ = serialize(magic, L, n2, ring_recs, n_in, n_rings, inj0, field0)
    img2 = bytearray(b2)
    hh2 = parse_hdr(img2, magic)
    for i, v in enumerate(inj1):
        img2[hh2["inj_base"] + i] = v & 1
    for i, v in enumerate(fld1):
        img2[hh2["cell_base"] + i] = v & 1
    address_stored(img2, magic)
    ungated_caught = field_from(img2, parse_hdr(img2, magic)) != expect_of(inj1, fld1, off)
    cases.append(("ungated_caught", ungated_caught))
    verified = all(c[1] for c in cases)
    if not verified:
        print("REFUSING", cases)
        return 1

    with open(out, "wb") as f:
        f.write(body)
    sha = hashlib.sha256(body).hexdigest()
    cpt = (float(n_gate) / depth) if depth else 0.0
    jrnl = out + ".genome.jsonl"
    rec = {
        "action": "nring_fab", "kind": kind, "path": out, "len": len(body),
        "sha256": sha, "n_gate": n_gate, "n_wire": n_wire, "depth": depth,
        "computations_per_tick": cpt, "magic": magic.decode("ascii"),
        "n_in": n_in, "n_rings": n_rings, "growth_base": growth_base,
        "rings": [{"name": n, "purpose": p, "fwd": HDR + ring_fwd(L, i),
                   "rev": HDR + ring_rev(L, i), "carry": HDR + ring_carry(L, i),
                   "pub": HDR + ring_pub(L, i)} for i, (n, p) in enumerate(rings)],
        "cell_base": h["cell_base"], "inj_base": h["inj_base"],
        "clock": h["clock"], "ring0": h["ring0"],
        "cases": cases, "status": "WROTE",
    }
    with open(jrnl, "a") as f:
        f.write(json.dumps(rec) + "\n")
    with open(out + ".fab_report.json", "w") as f:
        json.dump(rec, f, indent=2)
    print("WROTE", out, len(body), "sha", sha)
    print("  magic", magic, "n_in", n_in, "n_wire", n_wire, "n_gate", n_gate, "n_out", n_in)
    print("  depth", depth, "cpt", "%.3f" % cpt)
    print("  ring0", h["ring0"], "clock", h["clock"], "inj", h["inj_base"], "field", h["cell_base"])
    for i, (n, p) in enumerate(rings):
        print("  RING", n, "fwd", HDR + ring_fwd(L, i), p)
    print("  cases", cases)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
