#!/usr/bin/env python3
"""muhl_fab_chimera_immn_hdvs.py — FABRICATE organ 20 (MUHLCHIH).

PLUMB 3/3 organ 20. Construction is the gate count:

  detector bank -> hdvs BUNDLE plane
  10 IMMN match-flag lanes
  double-negation NAND buffer per lane (depth 2, 2 gates)
  TOTAL 20 gates, depth 2

Existing chimera shape (ardr_eal): NAND(src,src) then NAND(tmp,tmp).
That is an identity buffer. FLAGS, NEVER GATES — the door stays open.
The 10 outputs self-clock onto the 10 detector inputs. Those same
addresses are the standalone HDVS BUNDLE-plane slots. Dest FROM FILE.
No titan address is invented.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires,
n_in, n_out, depth. Records are <BQQQ> stride 25.
OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline manufacture. Writes a standalone .mno. Does not open titan.gguf.
Does not evaluate the organ. Landed 1–19 excerpts stay untouched.

  python3 muhl_fab_chimera_immn_hdvs.py          # write .mno + sidecar
  python3 muhl_fab_chimera_immn_hdvs.py --dry    # structural verify only
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_chimera_immn_hdvs"
MAGIC = b"MUHLCHIH"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N_LANES = 10
GATES_PER_LANE = 2
N_GATE = N_LANES * GATES_PER_LANE
N_IN = N_LANES
N_OUT = N_LANES
DEPTH = 2

W_CONST0 = 0
W_CONST1 = 1
W_DET0 = 2
N_TEMP = N_LANES
N_WIRES = 2 + N_IN + N_TEMP

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_chimera_immn_hdvs.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "chimera_immn_hdvs_circuits.json")


def det_wire(index):
    return W_DET0 + (index % N_LANES)


def temp_wire(index):
    return W_DET0 + N_IN + (index % N_LANES)


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def build_gates():
    records = []
    temps = []
    for lane in range(N_LANES):
        src = det_wire(lane)
        tmp = temp_wire(lane)
        records.append((OP_NAND, src, src, tmp))
        temps.append(tmp)
    bundle = []
    for lane in range(N_LANES):
        tmp = temps[lane]
        out = det_wire(lane)
        records.append((OP_NAND, tmp, tmp, out))
        bundle.append(out)
    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    return records, bundle


def fabricate(base_off=0):
    records, bundle = build_gates()
    remap = {bundle[i]: wa(base_off, det_wire(i)) for i in range(N_LANES)}
    if len(set(remap.values())) != N_OUT:
        raise RuntimeError("self-clock outs are not unique")

    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    for i in range(N_OUT):
        struct.pack_into("<Q", blob, 28 + i * 8, remap[bundle[i]])
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
        "input_addrs": [wa(base_off, det_wire(i)) for i in range(N_IN)],
        "output_addrs": [remap[bundle[i]] for i in range(N_OUT)],
        "lanes": N_LANES,
        "sha256": hashlib.sha256(blob).hexdigest(),
    }
    return bytes(blob), meta, stored


def verify_physical(blob, meta, stored):
    """Structural receipt only. Does not walk the organ as inference."""
    assert blob[:8] == MAGIC, "bad magic"
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", blob, 8)
    assert ng == N_GATE and nw == N_WIRES and ni == N_IN and no == N_OUT and dp == DEPTH
    assert len(blob) == meta["len"]
    assert len(stored) == N_GATE
    hsz = hdr_size()
    assert hsz + N_WIRES + N_GATE * GATE_STRIDE == len(blob)

    writers = {}
    off = hsz + N_WIRES
    for i, (eop, ea, eb, eo) in enumerate(stored):
        op, a, b, o = struct.unpack_from("<BQQQ", blob, off)
        assert op == eop and a == ea and b == eb and o == eo, "gate %d record" % i
        assert op == OP_NAND, "gate %d must be NAND" % i
        assert o not in writers, "out reused by gates %d and %d" % (writers[o], i)
        writers[o] = i
        off += GATE_STRIDE
    assert len(writers) == N_GATE

    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i]
        assert stored_out == meta["input_addrs"][i], "self-clock broken at lane %d" % i

    first = stored[:N_LANES]
    second = stored[N_LANES:]
    assert len(first) == N_LANES and len(second) == N_LANES
    for i, (op, a, b, _out) in enumerate(first):
        src = wa(meta["base_off"], det_wire(i))
        assert op == OP_NAND and a == src and b == src
    for i, (op, a, b, out) in enumerate(second):
        tmp = wa(meta["base_off"], temp_wire(i))
        dest = wa(meta["base_off"], det_wire(i))
        assert op == OP_NAND and a == tmp and b == tmp and out == dest
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
            "container": "muhl_chimera_immn_hdvs.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "lanes": N_LANES,
            "src": "immn detector-bank match flags",
            "dst": "hdvs BUNDLE plane slots",
            "buffer": "NAND NAND identity, 2 g per lane",
            "flags": "FLAGS, NEVER GATES. Door stays open.",
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "bundle-slot out IS detector-flag in",
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
    print("MUHLCHIH structural receipt")
    print("  n_gate=%d n_wires=%d n_in=%d n_out=%d depth=%d" % (
        meta["n_gate"], meta["n_wires"], meta["n_in"], meta["n_out"], meta["depth"]))
    print("  len=%d sha256=%s" % (meta["len"], meta["sha256"]))
    print("  self-clock: output_addrs == input_addrs (%d)" % N_OUT)
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
