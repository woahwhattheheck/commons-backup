#!/usr/bin/env python3
"""muhl_fab_chimera_grbn_socr.py — FABRICATE organ 23 (MUHLCHGS).

PLUMB 3/3 organ 23. Construction is the gate count:

  RBN state -> sandpile grain drop
  10 state/grain lanes
  double-negation NAND buffer per lane (depth 2, 2 gates)
  TOTAL 20 gates, depth 2

Existing chimera shape (organs 20–22 / ardr_eal): NAND(src,src) then
NAND(tmp,tmp). That is an identity buffer. Dest FROM FILE: grbn
output_addrs[0:10] and socr input_addrs[0:10]. Local outs self-clock
onto local ins. No titan address is invented. Landed organs 1–22 stay
untouched.

Header matches live muhl_mha: 8-char magic, then LE n_gate, n_wires,
n_in, n_out, depth. Records are <BQQQ> stride 25.
OPS NAND AND OR XOR NOT = 0 1 2 3 4.

  python3 muhl_fab_chimera_grbn_socr.py          # write .mno + sidecar
  python3 muhl_fab_chimera_grbn_socr.py --dry    # structural verify only
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_chimera_grbn_socr"
MAGIC = b"MUHLCHGS"
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
W_STATE0 = 2
N_TEMP = N_LANES
N_WIRES = 2 + N_IN + N_TEMP

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_chimera_grbn_socr.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "chimera_grbn_socr_circuits.json")
GRBN_REG = os.path.join(EXCERPT_DIR, "grbn_circuits.json")
SOCR_REG = os.path.join(EXCERPT_DIR, "socr_circuits.json")


def state_wire(index):
    return W_STATE0 + (index % N_LANES)


def temp_wire(index):
    return W_STATE0 + N_IN + (index % N_LANES)


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def dests_from_file():
    """Read landed sidecars. Do not invent addresses."""
    with open(GRBN_REG, encoding="utf-8") as handle:
        grbn = json.load(handle)["muhl_grbn"]
    with open(SOCR_REG, encoding="utf-8") as handle:
        socr = json.load(handle)["muhl_socr"]
    src = list(grbn["output_addrs"][:N_LANES])
    dst = list(socr["input_addrs"][:N_LANES])
    if len(src) != N_LANES or len(dst) != N_LANES:
        raise RuntimeError("landed sidecars missing RBN state or grain dests")
    if grbn.get("n_out") != 256:
        raise RuntimeError("grbn sidecar is not the landed 256-node RBN")
    if socr.get("cells") != 256:
        raise RuntimeError("socr sidecar is not the landed 256-cell sandpile")
    if grbn.get("sha256") != "09214540b3f3117ab93a4c509017a5e7b9c5f12d86545069af4ffcdae99c6632":
        raise RuntimeError("grbn sidecar sha is not the landed excerpt")
    if socr.get("sha256") != "d3af1a99d99e3c7779438abbd9644461627a655fd2fac374f337049ea37c360b":
        raise RuntimeError("socr sidecar sha is not the landed excerpt")
    return {
        "src_organ": "muhl_grbn",
        "src_plane": "RBN state outs 0..9",
        "src_addrs": src,
        "dst_organ": "muhl_socr",
        "dst_plane": "sandpile grain-drop ins 0..9",
        "dst_addrs": dst,
        "grbn_sha256": grbn["sha256"],
        "socr_sha256": socr["sha256"],
    }


def build_gates():
    records = []
    temps = []
    for lane in range(N_LANES):
        src = state_wire(lane)
        tmp = temp_wire(lane)
        records.append((OP_NAND, src, src, tmp))
        temps.append(tmp)
    grains = []
    for lane in range(N_LANES):
        tmp = temps[lane]
        out = state_wire(lane)
        records.append((OP_NAND, tmp, tmp, out))
        grains.append(out)
    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    return records, grains


def fabricate(base_off=0):
    dests = dests_from_file()
    records, grains = build_gates()
    remap = {grains[i]: wa(base_off, state_wire(i)) for i in range(N_LANES)}
    if len(set(remap.values())) != N_OUT:
        raise RuntimeError("self-clock outs are not unique")

    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    for i in range(N_OUT):
        struct.pack_into("<Q", blob, 28 + i * 8, remap[grains[i]])
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
        "input_addrs": [wa(base_off, state_wire(i)) for i in range(N_IN)],
        "output_addrs": [remap[grains[i]] for i in range(N_OUT)],
        "lanes": N_LANES,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "dests": dests,
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
        src = wa(meta["base_off"], state_wire(i))
        assert op == OP_NAND and a == src and b == src
    for i, (op, a, b, out) in enumerate(second):
        tmp = wa(meta["base_off"], temp_wire(i))
        dest = wa(meta["base_off"], state_wire(i))
        assert op == OP_NAND and a == tmp and b == tmp and out == dest
    dests = meta["dests"]
    assert dests["src_addrs"] == list(range(2078, 2088))
    assert dests["dst_addrs"] == list(range(6174, 6184))
    assert blob[hsz + W_CONST0] == 0 and blob[hsz + W_CONST1] == 1
    return True


def write_files(blob, meta):
    os.makedirs(os.path.dirname(MNO_PATH), exist_ok=True)
    with open(MNO_PATH, "wb") as handle:
        handle.write(blob)
    dests = meta["dests"]
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
            "container": "muhl_chimera_grbn_socr.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "lanes": N_LANES,
            "src": "grbn RBN state outs",
            "dst": "socr sandpile grain-drop ins",
            "buffer": "NAND NAND identity, 2 g per lane",
            "src_addrs": dests["src_addrs"],
            "dst_addrs": dests["dst_addrs"],
            "grbn_sha256": dests["grbn_sha256"],
            "socr_sha256": dests["socr_sha256"],
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "grain-drop out IS RBN-state in",
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
    print("MUHLCHGS structural receipt")
    print("  n_gate=%d n_wires=%d n_in=%d n_out=%d depth=%d" % (
        meta["n_gate"], meta["n_wires"], meta["n_in"], meta["n_out"], meta["depth"]))
    print("  len=%d sha256=%s" % (meta["len"], meta["sha256"]))
    print("  dest FROM FILE src=%s dst=%s" % (
        meta["dests"]["src_addrs"], meta["dests"]["dst_addrs"]))
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
