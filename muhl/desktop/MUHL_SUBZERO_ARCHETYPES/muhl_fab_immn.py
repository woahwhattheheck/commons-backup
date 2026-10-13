#!/usr/bin/env python3
"""muhl_fab_immn.py — FABRICATE muhl_immn (MUHLIMMN), clonal selection field.

PLUMB 1/3 organ 4. Construction is the gate tax:

  128 detectors x 32-bit self-window. negative selection.
  FLAGS, NEVER GATES — the door stays open.
  match  per det XOR32 (32) + popcount32 (160) + thresh (6) = 198
         128 x 198 = 25,344 + alarm OR-tree 127               25,471
  mature affinity maturation, 32-bit LFSR mutate per detector
         128 x 35                                              4,480
  TOTAL                                                       29,951  depth 27
  CLK detector bank advances on match count. maturation in gates.

popcount32 is 32 full adders (5 g). One unused pad FA keeps the 5n
budget. The other 31 are a 5-level carry tree. Threshold is the hopf
6-gate 4+2 pad so match flags sit at 20. The 127-OR alarm tree adds
7 and the alarm sits at 27. Detector bits self-clock through a
32-bit Fibonacci LFSR (3 tap XOR + 32 identity XOR).

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records are <BQQQ> stride 25. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno. Does not open titan.gguf.
Does not evaluate the organ. Existing titan circuits and landed excerpts stay.

  python3 muhl_fab_immn.py          # write .mno + registry sidecar
  python3 muhl_fab_immn.py --dry    # structural verify, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_immn"
MAGIC = b"MUHLIMMN"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N_DET = 128
D = 32
N_XOR = D
GATES_PER_FA = 5
N_FA = D
N_POP = N_FA * GATES_PER_FA
N_THRESH = 6
GATES_PER_MATCH = N_XOR + N_POP + N_THRESH
N_MATCH = N_DET * GATES_PER_MATCH
N_ALARM = N_DET - 1
GATES_PER_MATURE = 35
N_MATURE = N_DET * GATES_PER_MATURE
N_GATE = N_MATCH + N_ALARM + N_MATURE
N_IN = D
N_OUT = 1
DEPTH = 27
N_DET_BITS = N_DET * D

W_CONST0 = 0
W_CONST1 = 1
W_WIN0 = 2
W_DET0 = W_WIN0 + N_IN
N_WIRES = 2 + N_IN + N_DET_BITS + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_immn.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "immn_circuits.json")


def win_wire(index):
    return W_WIN0 + (index % D)


def det_wire(det, bit):
    return W_DET0 + det * D + (bit % D)


def det_bit(det, bit):
    """Baked self-window bit. Deterministic, not a host table walk."""
    z = (((det + 1) << 8) | bit) * 0x9E3779B97F4A7C15
    z &= 0xFFFFFFFFFFFFFFFF
    z ^= z >> 30
    z = (z * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    z ^= z >> 27
    z = (z * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    z ^= z >> 31
    return z & 1


def det_bits(det):
    return [det_bit(det, bit) for bit in range(D)]


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def build_gates():
    """Return records, 128 flags, alarm wire, and next detector bits."""
    records = []
    next_wire = 2 + N_IN + N_DET_BITS

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

    flags = []
    for det in range(N_DET):
        start = len(records)
        mismatch = []
        bits = det_bits(det)
        for bit in range(D):
            const = W_CONST1 if bits[bit] else W_CONST0
            mismatch.append(emit(OP_XOR, win_wire(bit), const))
        if len(records) - start != N_XOR:
            raise RuntimeError("xor count det %d" % det)

        fa(mismatch[0], mismatch[1], W_CONST0)
        level = list(mismatch)
        while len(level) > 1:
            nxt = []
            for i in range(0, len(level), 2):
                nxt.append(fa(level[i], level[i + 1], W_CONST0))
            level = nxt
        if len(level) != 1:
            raise RuntimeError("popcount det %d" % det)
        root = level[0]
        t0 = emit(OP_NOT, root, root)
        t1 = emit(OP_AND, root, W_CONST1)
        u0 = emit(OP_OR, t0, t1)
        u1 = emit(OP_AND, t0, t1)
        v = emit(OP_OR, u0, u1)
        flags.append(emit(OP_AND, v, W_CONST1))
        if len(records) - start != GATES_PER_MATCH:
            raise RuntimeError("match %d count %d" % (det, len(records) - start))

    if len(records) != N_MATCH:
        raise RuntimeError("match total %d != %d" % (len(records), N_MATCH))

    level = list(flags)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            nxt.append(emit(OP_OR, level[i], level[i + 1]))
        level = nxt
    if len(level) != 1:
        raise RuntimeError("alarm tree did not reduce")
    alarm = level[0]
    if len(records) != N_MATCH + N_ALARM:
        raise RuntimeError("alarm count %d" % (len(records) - N_MATCH))

    next_det = [None] * N_DET_BITS
    for det in range(N_DET):
        start = len(records)
        # Fibonacci taps 32,22,2,1 (1-indexed) = bits 31,21,1,0.
        t0 = emit(OP_XOR, det_wire(det, 31), det_wire(det, 21))
        t1 = emit(OP_XOR, det_wire(det, 1), det_wire(det, 0))
        feedback = emit(OP_XOR, t0, t1)
        next_det[det * D + 0] = emit(OP_XOR, feedback, W_CONST0)
        for bit in range(1, D):
            next_det[det * D + bit] = emit(OP_XOR, det_wire(det, bit - 1), W_CONST0)
        if len(records) - start != GATES_PER_MATURE:
            raise RuntimeError("mature %d count %d" % (det, len(records) - start))

    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    if any(w is None for w in next_det):
        raise RuntimeError("missing next detector wire")
    return records, flags, alarm, next_det


def fabricate(base_off=0):
    records, flags, alarm, next_det = build_gates()
    remap = {next_det[i]: wa(base_off, W_DET0 + i) for i in range(N_DET_BITS)}
    if len(set(remap.values())) != N_DET_BITS:
        raise RuntimeError("self-clock outs are not unique")

    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    alarm_addr = wa(base_off, alarm)
    struct.pack_into("<Q", blob, 28, alarm_addr)
    blob[hsz + W_CONST0] = 0
    blob[hsz + W_CONST1] = 1
    for det in range(N_DET):
        bits = det_bits(det)
        for bit in range(D):
            blob[hsz + det_wire(det, bit)] = bits[bit]

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
        "input_addrs": [wa(base_off, win_wire(i)) for i in range(N_IN)],
        "output_addrs": [alarm_addr],
        "flag_wires": flags,
        "alarm_wire": alarm,
        "detectors": ["".join("1" if bit else "0" for bit in det_bits(det)) for det in range(N_DET)],
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

    records, flags, alarm, next_det = build_gates()
    wire_depth = {wire: 0 for wire in range(W_DET0 + N_DET_BITS)}
    max_gate_depth = 0
    for _op, a, b, out in records:
        assert a in wire_depth and b in wire_depth
        gate_depth = max(wire_depth[a], wire_depth[b]) + 1
        max_gate_depth = max(max_gate_depth, gate_depth)
        wire_depth[out] = gate_depth
    assert max_gate_depth == DEPTH, "depth %d != %d" % (max_gate_depth, DEPTH)
    assert [wire_depth[w] for w in flags] == [20] * N_DET
    assert wire_depth[alarm] == DEPTH

    valid_addresses = {wa(meta["base_off"], wire) for wire in range(N_WIRES)}
    for _op, a, b, out in stored:
        assert a in valid_addresses and b in valid_addresses and out in valid_addresses

    stored_out = struct.unpack_from("<Q", blob, 28)[0]
    assert stored_out == meta["output_addrs"][0]
    assert stored_out == wa(meta["base_off"], alarm)

    for det in range(N_DET):
        chunk = stored[det * GATES_PER_MATCH:(det + 1) * GATES_PER_MATCH]
        xor = chunk[:N_XOR]
        assert [g[0] for g in xor] == [OP_XOR] * N_XOR
        pop = chunk[N_XOR:N_XOR + N_POP]
        for adder in range(N_FA):
            fa_ops = [g[0] for g in pop[adder * GATES_PER_FA:(adder + 1) * GATES_PER_FA]]
            assert fa_ops == [OP_XOR, OP_XOR, OP_AND, OP_AND, OP_OR]
        thresh = chunk[N_XOR + N_POP:]
        assert [g[0] for g in thresh] == [OP_NOT, OP_AND, OP_OR, OP_AND, OP_OR, OP_AND]

    alarm_ops = [g[0] for g in stored[N_MATCH:N_MATCH + N_ALARM]]
    assert alarm_ops == [OP_OR] * N_ALARM
    mature = stored[N_MATCH + N_ALARM:]
    assert len(mature) == N_MATURE
    assert [g[0] for g in mature] == [OP_XOR] * N_MATURE

    hsz = hdr_size()
    assert blob[hsz + W_CONST0] == 0 and blob[hsz + W_CONST1] == 1
    for det in range(N_DET):
        bits = det_bits(det)
        for bit in range(D):
            assert blob[hsz + det_wire(det, bit)] == bits[bit]
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
            "container": "muhl_immn.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "detectors": N_DET,
            "self_window_bits": D,
            "flags": "128 match flags. FLAGS, NEVER GATES. Door stays open.",
            "alarm": "127-OR tree over the flags. Result plane only.",
            "clock": "detector bank out IS detector bank in via 32-bit LFSR",
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
    print("MUHLIMMN structural receipt")
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
