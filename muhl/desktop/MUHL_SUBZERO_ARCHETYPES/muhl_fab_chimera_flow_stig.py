#!/usr/bin/env python3
"""muhl_fab_chimera_flow_stig.py — FABRICATE organ 25 (MUHLCHFS).

PLUMB 3/3 organ 25. Construction is the gate count:

  conductance -> evaporation rate
  9 conductance lanes
  double-negation NAND buffer per lane (depth 2, 2 gates)
  TOTAL 18 gates, depth 2

Dest FROM FILE: flow output_addrs[0:9] and stig input_addrs[0:9].
Local outs self-clock onto local ins. titan NOT_WRITTEN.
Landed organs 1–24 stay untouched.

  python3 muhl_fab_chimera_flow_stig.py          # write .mno + sidecar
  python3 muhl_fab_chimera_flow_stig.py --dry    # structural verify only
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

NAME = "muhl_chimera_flow_stig"
MAGIC = b"MUHLCHFS"
GATE_STRIDE = 25
OP_NAND = 0

N_LANES = 9
N_GATE = N_LANES * 2
N_IN = N_LANES
N_OUT = N_LANES
DEPTH = 2
W_CONST0 = 0
W_CONST1 = 1
W_COND0 = 2
N_WIRES = 2 + N_IN + N_LANES

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_chimera_flow_stig.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "chimera_flow_stig_circuits.json")
FLOW_REG = os.path.join(EXCERPT_DIR, "flow_circuits.json")
STIG_REG = os.path.join(EXCERPT_DIR, "stig_circuits.json")


def cond_wire(index):
    return W_COND0 + (index % N_LANES)


def temp_wire(index):
    return W_COND0 + N_IN + (index % N_LANES)


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def dests_from_file():
    with open(FLOW_REG, encoding="utf-8") as handle:
        flow = json.load(handle)["muhl_flow"]
    with open(STIG_REG, encoding="utf-8") as handle:
        stig = json.load(handle)["muhl_stig"]
    src = list(flow["output_addrs"][:N_LANES])
    dst = list(stig["input_addrs"][:N_LANES])
    if len(src) != N_LANES or len(dst) != N_LANES:
        raise RuntimeError("landed sidecars missing conductance or evaporate dests")
    if flow.get("n_out") != 2048:
        raise RuntimeError("flow sidecar is not the landed 2048-bit conductance")
    if stig.get("cells") != 256:
        raise RuntimeError("stig sidecar is not the landed 256-cell field")
    return {
        "src_organ": "muhl_flow",
        "src_plane": "conductance outs 0..8",
        "src_addrs": src,
        "dst_organ": "muhl_stig",
        "dst_plane": "evaporation-rate ins 0..8",
        "dst_addrs": dst,
        "flow_sha256": flow["sha256"],
        "stig_sha256": stig["sha256"],
    }


def build_gates():
    records = []
    temps = []
    for lane in range(N_LANES):
        src = cond_wire(lane)
        tmp = temp_wire(lane)
        records.append((OP_NAND, src, src, tmp))
        temps.append(tmp)
    rates = []
    for lane in range(N_LANES):
        out = cond_wire(lane)
        records.append((OP_NAND, temps[lane], temps[lane], out))
        rates.append(out)
    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    return records, rates


def fabricate(base_off=0):
    dests = dests_from_file()
    records, rates = build_gates()
    remap = {rates[i]: wa(base_off, cond_wire(i)) for i in range(N_LANES)}
    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    for i in range(N_OUT):
        struct.pack_into("<Q", blob, 28 + i * 8, remap[rates[i]])
    blob[hsz + W_CONST0] = 0
    blob[hsz + W_CONST1] = 1
    stored = []
    off = gate_start
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
        "input_addrs": [wa(base_off, cond_wire(i)) for i in range(N_IN)],
        "output_addrs": [remap[rates[i]] for i in range(N_OUT)],
        "lanes": N_LANES,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "dests": dests,
    }
    return bytes(blob), meta, stored


def verify_physical(blob, meta, stored):
    assert blob[:8] == MAGIC
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", blob, 8)
    assert (ng, nw, ni, no, dp) == (N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    assert len(blob) == meta["len"] == hdr_size() + N_WIRES + N_GATE * GATE_STRIDE
    writers = {}
    off = hdr_size() + N_WIRES
    for i, (eop, ea, eb, eo) in enumerate(stored):
        op, a, b, o = struct.unpack_from("<BQQQ", blob, off)
        assert (op, a, b, o) == (eop, ea, eb, eo)
        assert op == OP_NAND and o not in writers
        writers[o] = i
        off += GATE_STRIDE
    for i in range(N_OUT):
        stored_out = struct.unpack_from("<Q", blob, 28 + i * 8)[0]
        assert stored_out == meta["output_addrs"][i] == meta["input_addrs"][i]
    dests = meta["dests"]
    assert dests["src_addrs"] == list(range(16414, 16423))
    assert dests["dst_addrs"] == list(range(6174, 6183))
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
            "container": "muhl_chimera_flow_stig.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "lanes": N_LANES,
            "src": "flow conductance outs",
            "dst": "stig evaporation-rate ins",
            "buffer": "NAND NAND identity, 2 g per lane",
            "src_addrs": dests["src_addrs"],
            "dst_addrs": dests["dst_addrs"],
            "flow_sha256": dests["flow_sha256"],
            "stig_sha256": dests["stig_sha256"],
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "evaporate-rate out IS conductance in",
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
    print("MUHLCHFS structural receipt")
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
