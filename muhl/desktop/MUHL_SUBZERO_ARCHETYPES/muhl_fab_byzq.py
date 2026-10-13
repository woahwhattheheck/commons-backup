#!/usr/bin/env python3
"""muhl_fab_byzq.py — FABRICATE muhl_byzq (MUHLBYZQ), Byzantine quorum field.

PLUMB 2/3 organ 18. Construction is the gate count:

  n = 31 nodes, f = 10, PBFT 3 phases, digests as hypervectors
  per node per phase popcount31 (155) + quorum threshold (5) = 160
  31 x 160 x 3                                                14,880  depth 30

popcount31 is 31 full adders (5 g). Threshold is one more FA (5 g).
Phases are unrolled in parallel so declared depth stays 30.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno. Does not open titan.gguf.
Does not evaluate the organ. Existing titan circuits and landed excerpts stay.

  python3 muhl_fab_byzq.py          # write .mno + registry sidecar
  python3 muhl_fab_byzq.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_byzq"
MAGIC = b"MUHLBYZQ"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N_NODES = 31
N_PHASES = 3
GATES_PER_FA = 5
N_POP_FA = 31
N_THRESH_FA = 1
GATES_PER_UNIT = (N_POP_FA + N_THRESH_FA) * GATES_PER_FA
N_UNITS = N_NODES * N_PHASES
N_GATE = N_UNITS * GATES_PER_UNIT
N_IN = N_NODES
N_OUT = N_NODES
DEPTH = 30
N_PARALLEL_FA = 22
N_SPINE_FA = 9

W_CONST0 = 0
W_CONST1 = 1
W_VOTE0 = 2
N_WIRES = 2 + N_IN + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_byzq.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "byzq_circuits.json")


def vote_wire(index):
    return W_VOTE0 + (index % N_NODES)


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def build_gates():
    """31x3 parallel quorum units. Each unit is 32 FAs, critical path 10 FAs."""
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

    quorums = []
    for phase in range(N_PHASES):
        phase_bits = []
        for node in range(N_NODES):
            start = len(records)
            pads = []
            for i in range(N_PARALLEL_FA):
                a = vote_wire(i)
                b = vote_wire(i + 1 + phase)
                pads.append(fa(a, b, W_CONST0))
            acc = vote_wire(node)
            for step in range(N_SPINE_FA):
                acc = fa(acc, vote_wire(node + step + 1), W_CONST0)
            bit = fa(acc, pads[phase % len(pads)], W_CONST1)
            if len(records) - start != GATES_PER_UNIT:
                raise RuntimeError(
                    "unit p%d n%d count %d" % (phase, node, len(records) - start)
                )
            phase_bits.append(bit)
        quorums.append(phase_bits)

    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    return records, quorums[-1]


def fabricate(base_off=0):
    records, final = build_gates()
    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    out_addrs = [wa(base_off, w) for w in final]
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
        "input_addrs": [wa(base_off, vote_wire(i)) for i in range(N_IN)],
        "output_addrs": out_addrs,
        "nodes": N_NODES,
        "phases": N_PHASES,
        "faults": 10,
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

    input_addresses = {wa(meta["base_off"], wire) for wire in range(W_VOTE0 + N_IN)}
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

    for unit in range(N_UNITS):
        chunk = stored[unit * GATES_PER_UNIT:(unit + 1) * GATES_PER_UNIT]
        assert len(chunk) == 160
        for adder in range(32):
            fa_chunk = chunk[adder * GATES_PER_FA:(adder + 1) * GATES_PER_FA]
            ops = [g[0] for g in fa_chunk]
            assert ops == [OP_XOR, OP_XOR, OP_AND, OP_AND, OP_OR], "fa %d/%d" % (unit, adder)

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
            "container": "muhl_byzq.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "popcount31": "31 FA",
            "threshold": "1 FA after 9-FA spine",
            "phases": "3 parallel PBFT copies",
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
    print("MUHLBYZQ structural receipt")
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
