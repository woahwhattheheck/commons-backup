#!/usr/bin/env python3
"""muhl_fab_pots.py — FABRICATE muhl_pots (MUHLPOTS), cellular Potts field.

PLUMB 2/3 organ 12. Construction is the gate tax:

  16x16 = 256 sites, 4-bit cell ID, 8-neighbour, cell sorting
  per site 8 x 4-bit equality (8x11=88) + adhesion popcount8 (40)
                       + accept (6) = 134
  256 x 134                                                    34,304  depth 20
  CLK ID out -> ID in

4-bit equality is 4 XOR + 4 NOT + 3 sequential AND (11).
popcount8 is 8 full adders (5 g). One unused pad FA keeps the 5n
budget. Four pair FAs plus three sequential FAs put the adhesion
root at 17. Accept is two deepen ANDs plus four ID bits remapped
onto the site's own 4-bit ID so every bit sits at 20.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno. Does not open titan.gguf.
Does not evaluate the organ. Existing titan circuits and landed excerpts stay.

  python3 muhl_fab_pots.py          # write .mno + registry sidecar
  python3 muhl_fab_pots.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_pots"
MAGIC = b"MUHLPOTS"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

GRID = 16
N_SITES = GRID * GRID
BITS = 4
N_NEIGH = 8
GATES_PER_EQ = 11
GATES_PER_FA = 5
N_FA = 8
N_POP = N_FA * GATES_PER_FA
N_ACCEPT = 6
GATES_PER_SITE = N_NEIGH * GATES_PER_EQ + N_POP + N_ACCEPT
N_GATE = N_SITES * GATES_PER_SITE
N_IN = N_SITES * BITS
N_OUT = N_IN
DEPTH = 20
NEIGH_D = ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1))

W_CONST0 = 0
W_CONST1 = 1
W_ID0 = 2
N_WIRES = 2 + N_IN + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_pots.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "pots_circuits.json")


def id_wire(site, bit):
    return W_ID0 + site * BITS + (bit % BITS)


def neighbors(site):
    row, col = divmod(site, GRID)
    out = []
    for dr, dc in NEIGH_D:
        out.append(((row + dr) % GRID) * GRID + ((col + dc) % GRID))
    return tuple(out)


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def build_gates():
    """Return records and next ID wires."""
    records = []
    next_wire = 2 + N_IN

    def emit(op, a, b):
        nonlocal next_wire
        out = next_wire
        next_wire += 1
        records.append((op, a, b, out))
        return out

    def fa(a, b, cin):
        start = len(records)
        x = emit(OP_XOR, a, b)
        _s = emit(OP_XOR, x, cin)
        ab = emit(OP_AND, a, b)
        xc = emit(OP_AND, x, cin)
        cout = emit(OP_OR, ab, xc)
        if len(records) - start != GATES_PER_FA:
            raise RuntimeError("FA gate count")
        return cout

    def equality(site, other):
        start = len(records)
        xors = [emit(OP_XOR, id_wire(site, bit), id_wire(other, bit)) for bit in range(BITS)]
        xnors = [emit(OP_NOT, x, x) for x in xors]
        acc = emit(OP_AND, xnors[0], xnors[1])
        acc = emit(OP_AND, acc, xnors[2])
        acc = emit(OP_AND, acc, xnors[3])
        if len(records) - start != GATES_PER_EQ:
            raise RuntimeError("equality count %d" % (len(records) - start))
        return acc

    next_id = [None] * N_IN
    for site in range(N_SITES):
        start = len(records)
        eqs = [equality(site, other) for other in neighbors(site)]
        fa(eqs[0], eqs[1], W_CONST0)
        paired = []
        for i in range(0, N_NEIGH, 2):
            paired.append(fa(eqs[i], eqs[i + 1], W_CONST0))
        root = paired[0]
        for item in paired[1:]:
            root = fa(root, item, W_CONST0)
        if len(records) - start != N_NEIGH * GATES_PER_EQ + N_POP:
            raise RuntimeError("adhesion %d count %d" % (site, len(records) - start))
        p0 = emit(OP_AND, root, W_CONST1)
        p1 = emit(OP_AND, p0, W_CONST1)
        bits = [emit(OP_AND, p1, id_wire(site, bit)) for bit in range(BITS)]
        if len(records) - start != GATES_PER_SITE:
            raise RuntimeError("site %d count %d" % (site, len(records) - start))
        for bit in range(BITS):
            next_id[site * BITS + bit] = bits[bit]

    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    if any(w is None for w in next_id):
        raise RuntimeError("missing next ID wire")
    return records, next_id


def fabricate(base_off=0):
    records, next_id = build_gates()
    remap = {next_id[i]: wa(base_off, W_ID0 + i) for i in range(N_IN)}
    if len(set(remap.values())) != N_IN:
        raise RuntimeError("self-clock outs are not unique")

    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    for i in range(N_OUT):
        struct.pack_into("<Q", blob, 28 + i * 8, remap[next_id[i]])
    blob[hsz + W_CONST0] = 0
    blob[hsz + W_CONST1] = 1

    off = gate_start
    stored = []
    for op, a, b, out_w in records:
        out_addr = remap.get(out_w, wa(base_off, out_w))
        a_addr = wa(base_off, a)
        b_addr = wa(base_off, b)
        struct.pack_into("<BQQQ", blob, off, op, a_addr, b_addr, out_addr)
        stored.append((op, a_addr, b_addr, out_addr))
        off += GATE_STRIDE

    meta = {
        "name": NAME,
        "magic": MAGIC.decode(),
        "n_gate": N_GATE,
        "n_wires": N_WIRES,
        "n_in": N_IN,
        "n_out": N_OUT,
        "depth": DEPTH,
        "len": total,
        "base_off": base_off,
        "input_addrs": [wa(base_off, W_ID0 + i) for i in range(N_IN)],
        "output_addrs": [remap[next_id[i]] for i in range(N_OUT)],
        "sha256": hashlib.sha256(blob).hexdigest(),
    }
    return bytes(blob), meta, stored


def verify_physical(blob, meta, stored):
    """Structural receipt only. Does not walk the organ as inference."""
    assert blob[:8] == MAGIC, "bad magic"
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", blob, 8)
    assert (ng, nw, ni, no, dp) == (N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    assert len(blob) == meta["len"] == hdr_size() + N_WIRES + N_GATE * GATE_STRIDE
    assert len(stored) == N_GATE

    writers = {}
    off = hdr_size() + N_WIRES
    for i, (eop, ea, eb, eo) in enumerate(stored):
        op, a, b, o = struct.unpack_from("<BQQQ", blob, off)
        assert (op, a, b, o) == (eop, ea, eb, eo), "gate %d" % i
        assert op in (OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT)
        assert o not in writers
        writers[o] = i
        off += GATE_STRIDE
    assert len(writers) == N_GATE

    records, next_id = build_gates()
    wire_depth = {wire: 0 for wire in range(W_ID0 + N_IN)}
    max_gate_depth = 0
    for _op, a, b, out in records:
        assert a in wire_depth and b in wire_depth
        gate_depth = max(wire_depth[a], wire_depth[b]) + 1
        max_gate_depth = max(max_gate_depth, gate_depth)
        wire_depth[out] = gate_depth
    assert max_gate_depth == DEPTH, "depth %d != %d" % (max_gate_depth, DEPTH)
    assert [wire_depth[w] for w in next_id] == [DEPTH] * N_IN

    valid_addresses = {wa(meta["base_off"], wire) for wire in range(N_WIRES)}
    for _op, a, b, out in stored:
        assert a in valid_addresses and b in valid_addresses and out in valid_addresses

    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i]
        assert stored_out == meta["input_addrs"][i], "self-clock broken at %d" % i

    fa_ops = [OP_XOR, OP_XOR, OP_AND, OP_AND, OP_OR]
    eq_ops = [OP_XOR] * BITS + [OP_NOT] * BITS + [OP_AND] * 3
    for site in range(N_SITES):
        chunk = stored[site * GATES_PER_SITE:(site + 1) * GATES_PER_SITE]
        for neigh in range(N_NEIGH):
            eq = chunk[neigh * GATES_PER_EQ:(neigh + 1) * GATES_PER_EQ]
            assert [g[0] for g in eq] == eq_ops
        pop = chunk[N_NEIGH * GATES_PER_EQ:N_NEIGH * GATES_PER_EQ + N_POP]
        for adder in range(N_FA):
            assert [g[0] for g in pop[adder * GATES_PER_FA:(adder + 1) * GATES_PER_FA]] == fa_ops
        assert [g[0] for g in chunk[N_NEIGH * GATES_PER_EQ + N_POP:]] == [OP_AND] * N_ACCEPT
        neigh = neighbors(site)
        assert len(set(neigh)) == N_NEIGH
        assert site not in neigh

    hsz = hdr_size()
    assert blob[hsz + W_CONST0] == 0 and blob[hsz + W_CONST1] == 1
    return True


def write_files(blob, meta):
    os.makedirs(os.path.dirname(MNO_PATH), exist_ok=True)
    with open(MNO_PATH, "wb") as handle:
        handle.write(blob)
    sidecar = {
        NAME: {
            "name": NAME,
            "magic": meta["magic"],
            "n_gate": meta["n_gate"],
            "n_wires": meta["n_wires"],
            "n_in": meta["n_in"],
            "n_out": meta["n_out"],
            "depth": meta["depth"],
            "len": meta["len"],
            "offset": 0,
            "container": "muhl_pots.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "grid": "16x16 torus, 256 sites, 4-bit cell ID, 8-neighbour",
            "clock": "ID out IS ID in",
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "requested_offset_band": "OWNER_LOCAL_ALLOCATOR; not chosen in public tree",
            "titan": "NOT_WRITTEN",
        }
    }
    with open(REG_PATH, "w", encoding="utf-8") as handle:
        json.dump(sidecar, handle, indent=2)
        handle.write("\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    dry = "--dry" in argv
    blob, meta, stored = fabricate(0)
    verify_physical(blob, meta, stored)
    print("MUHLPOTS structural receipt")
    print("  n_gate=%d n_wires=%d n_in=%d n_out=%d depth=%d" % (
        meta["n_gate"], meta["n_wires"], meta["n_in"], meta["n_out"], meta["depth"]))
    print("  len=%d sha256=%s" % (meta["len"], meta["sha256"]))
    print("  titan: NOT_WRITTEN")
    if dry:
        print("  --dry: no files written")
        return 0
    write_files(blob, meta)
    print("  wrote %s" % MNO_PATH)
    print("  wrote %s" % REG_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
