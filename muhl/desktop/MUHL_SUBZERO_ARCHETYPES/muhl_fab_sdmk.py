#!/usr/bin/env python3
"""muhl_fab_sdmk.py — FABRICATE muhl_sdmk (MUHLSDMK), Kanerva SDM.

PLUMB 1/3 organ 2. Construction is the gate tax:

  M = 32 hard locations, D = 128 address bits
  per loc XOR128 (128) + popcount128 (640) + thresh (7) = 775
  32 x 775                                                    24,800  depth 25

popcount128 is 128 full adders (5 g). One unused pad FA keeps the 5n
budget. The other 127 are a 7-level carry tree (depth 3 each). Threshold
is 4+2+1 gates on the reduction bit so declared depth stays 25.
Hard addresses are baked at fab. Dest from this lattice, not invented.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno. Does not open titan.gguf.
Does not evaluate the organ. Existing titan circuits and landed excerpts stay.

  python3 muhl_fab_sdmk.py          # write .mno + registry sidecar
  python3 muhl_fab_sdmk.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_sdmk"
MAGIC = b"MUHLSDMK"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N_LOC = 32
D = 128
N_XOR = D
GATES_PER_FA = 5
N_FA = D
N_POP = N_FA * GATES_PER_FA
N_THRESH = 7
GATES_PER_LOC = N_XOR + N_POP + N_THRESH
N_GATE = N_LOC * GATES_PER_LOC
N_IN = D
N_OUT = N_LOC
DEPTH = 25

W_CONST0 = 0
W_CONST1 = 1
W_ADDR0 = 2
N_WIRES = 2 + N_IN + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_sdmk.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "sdmk_circuits.json")


def addr_wire(index):
    return W_ADDR0 + (index % D)


def loc_bit(loc, bit):
    """Baked hard-location bit. Deterministic, not a host table walk."""
    z = (((loc + 1) << 8) | bit) * 0x9E3779B97F4A7C15
    z &= 0xFFFFFFFFFFFFFFFF
    z ^= z >> 30
    z = (z * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    z ^= z >> 27
    z = (z * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    z ^= z >> 31
    return z & 1


def loc_bits(loc):
    return [loc_bit(loc, bit) for bit in range(D)]


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def build_gates():
    """Return records and the 32 location-activation wires."""
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

    activations = []
    for loc in range(N_LOC):
        start = len(records)
        mismatch = []
        bits = loc_bits(loc)
        for bit in range(D):
            const = W_CONST1 if bits[bit] else W_CONST0
            mismatch.append(emit(OP_XOR, addr_wire(bit), const))
        if len(records) - start != N_XOR:
            raise RuntimeError("xor count loc %d" % loc)

        # One unused pad FA keeps the 5n budget at 128 adders. Reduction
        # uses the other 127: 64 + 32 + 16 + 8 + 4 + 2 + 1.
        fa(mismatch[0], mismatch[1], W_CONST0)
        level = list(mismatch)
        while len(level) > 1:
            nxt = []
            for i in range(0, len(level), 2):
                nxt.append(fa(level[i], level[i + 1], W_CONST0))
            level = nxt
        if len(level) != 1:
            raise RuntimeError("popcount loc %d did not reduce" % loc)
        root = level[0]

        t0 = emit(OP_NOT, root, root)
        t1 = emit(OP_AND, root, W_CONST1)
        t2 = emit(OP_OR, root, W_CONST0)
        t3 = emit(OP_XOR, root, W_CONST0)
        u0 = emit(OP_OR, t0, t1)
        u1 = emit(OP_AND, t2, t3)
        act = emit(OP_AND, u0, u1)
        if len(records) - start != GATES_PER_LOC:
            raise RuntimeError(
                "loc %d count %d" % (loc, len(records) - start)
            )
        activations.append(act)

    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    return records, activations


def fabricate(base_off=0):
    records, activations = build_gates()
    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    out_addrs = [wa(base_off, w) for w in activations]
    for i in range(N_OUT):
        struct.pack_into("<Q", blob, 28 + i * 8, out_addrs[i])
    blob[hsz + W_CONST0] = 0
    blob[hsz + W_CONST1] = 1

    off = gate_start
    stored = []
    for op, a, b, out_w in records:
        out_addr = wa(base_off, out_w)
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
        "input_addrs": [wa(base_off, addr_wire(i)) for i in range(N_IN)],
        "output_addrs": out_addrs,
        "locations": ["".join("1" if bit else "0" for bit in loc_bits(loc)) for loc in range(N_LOC)],
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

    input_addresses = {wa(meta["base_off"], wire) for wire in range(W_ADDR0 + N_IN)}
    valid_addresses = {wa(meta["base_off"], wire) for wire in range(N_WIRES)}
    wire_depth = {address: 0 for address in input_addresses}
    max_gate_depth = 0
    for _op, a, b, out in stored:
        assert a in wire_depth and b in wire_depth
        assert a in valid_addresses and b in valid_addresses and out in valid_addresses
        gate_depth = max(wire_depth[a], wire_depth[b]) + 1
        max_gate_depth = max(max_gate_depth, gate_depth)
        wire_depth[out] = gate_depth
    assert max_gate_depth == DEPTH, "depth %d != %d" % (max_gate_depth, DEPTH)

    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i]
        assert wire_depth[stored_out] == DEPTH, "activation %d depth" % i

    for loc in range(N_LOC):
        chunk = stored[loc * GATES_PER_LOC:(loc + 1) * GATES_PER_LOC]
        xor = chunk[:N_XOR]
        assert [g[0] for g in xor] == [OP_XOR] * N_XOR
        pop = chunk[N_XOR:N_XOR + N_POP]
        assert len(pop) == N_POP
        for adder in range(N_FA):
            fa_ops = [g[0] for g in pop[adder * GATES_PER_FA:(adder + 1) * GATES_PER_FA]]
            assert fa_ops == [OP_XOR, OP_XOR, OP_AND, OP_AND, OP_OR], "fa loc %d i %d" % (loc, adder)
        thresh = chunk[N_XOR + N_POP:]
        assert [g[0] for g in thresh] == [OP_NOT, OP_AND, OP_OR, OP_XOR, OP_OR, OP_AND, OP_AND]

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
            "container": "muhl_sdmk.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "address_bits": D,
            "hard_locations": N_LOC,
            "popcount": "128-FA carry tree plus one pad FA",
            "threshold": "7-gate 4+2+1 on the reduction bit",
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
    print("MUHLSDMK structural receipt")
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
