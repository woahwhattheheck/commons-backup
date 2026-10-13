#!/usr/bin/env python3
"""muhl_fab_titanx_mirror.py — FABRICATE organ 30 (MUHLTITM).

PLUMB 3/3 organ 30. Construction is the gate count:

  wires pred hpc_fabric immn hdvs sdmk + rookery witness ring
  input plane = the OTHER ORGANS' out planes. emits surprise only.
  120 dest-FROM-FILE lanes x NAND NAND identity (2 g) = 240
  depth 2
  surprise is a bit plane -> renders under muhl_png.py bits

Hops (lanes):
  pred outs -> local surprise          32
  hpc_fabric ins (census delta)        28
  immn alarm out                        1
  hdvs outs                            32
  sdmk outs                            16
  rookery witness clocks               11

Dest FROM FILE: landed excerpt sidecars + SUBZERO_CENSUS.md
(HPC input[0] - HPC offset applied to hpc_fabric offset)
+ SUBZERO_MINDS.md rookery clock bank 256..279, witness ring 11 clocks.
Local outs self-clock onto local ins. titan NOT_WRITTEN.
Organs 1-29 stay.

  python3 muhl_fab_titanx_mirror.py          # write .mno + sidecar
  python3 muhl_fab_titanx_mirror.py --dry    # structural verify only
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import sys

NAME = "muhl_titanx_mirror"
MAGIC = b"MUHLTITM"
GATE_STRIDE = 25
OP_NAND = 0

HOPS = (
    {"name": "pred_surprise", "src": "muhl_pred", "lanes": 32},
    {"name": "hpc_fabric_surprise", "src": "muhl_hpc_fabric", "lanes": 28},
    {"name": "immn_surprise", "src": "muhl_immn", "lanes": 1},
    {"name": "hdvs_surprise", "src": "muhl_hdvs", "lanes": 32},
    {"name": "sdmk_surprise", "src": "muhl_sdmk", "lanes": 16},
    {"name": "rookery_witness_surprise", "src": "muhl_rookery0", "lanes": 11},
)
N_LANES = sum(hop["lanes"] for hop in HOPS)
N_GATE = N_LANES * 2
N_IN = N_LANES
N_OUT = N_LANES
DEPTH = 2

W_CONST0 = 0
W_CONST1 = 1
W_LANE0 = 2
N_WIRES = 2 + N_IN + N_LANES

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
CENSUS_PATH = os.path.join(REPO_ROOT, "ground", "SUBZERO_CENSUS.md")
MINDS_PATH = os.path.join(REPO_ROOT, "ground", "SUBZERO_MINDS.md")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_titanx_mirror.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "titanx_mirror_circuits.json")

LANDED = {
    "muhl_pred": {
        "reg": os.path.join(EXCERPT_DIR, "pred_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_pred.mno"),
        "magic": b"MUHLPRED",
    },
    "muhl_immn": {
        "reg": os.path.join(EXCERPT_DIR, "immn_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_immn.mno"),
        "magic": b"MUHLIMMN",
    },
    "muhl_hdvs": {
        "reg": os.path.join(EXCERPT_DIR, "hdvs_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_hdvs.mno"),
        "magic": b"MUHLHDVS",
    },
    "muhl_sdmk": {
        "reg": os.path.join(EXCERPT_DIR, "sdmk_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_sdmk.mno"),
        "magic": b"MUHLSDMK",
    },
}


def lane_wire(index):
    return W_LANE0 + (index % N_LANES)


def temp_wire(index):
    return W_LANE0 + N_IN + (index % N_LANES)


def hdr_size():
    return 28 + N_OUT * 8


def wa(base_off, wire):
    return base_off + hdr_size() + wire


def _read_landed(key):
    spec = LANDED[key]
    with open(spec["reg"], encoding="utf-8") as handle:
        row = json.load(handle)[key]
    with open(spec["mno"], "rb") as handle:
        blob = handle.read()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != row["sha256"]:
        raise RuntimeError("%s sha256 is not the landed sidecar" % key)
    if blob[:8] != spec["magic"]:
        raise RuntimeError("%s magic is not the landed file" % key)
    return row, digest


def census_text():
    with open(CENSUS_PATH, encoding="utf-8") as handle:
        return handle.read()


def minds_text():
    with open(MINDS_PATH, encoding="utf-8") as handle:
        return handle.read()


def hpc_fabric_ins_from_census():
    """Apply measured HPC input[0]-offset delta to hpc_fabric offset.

    Dest FROM FILE. Do not invent the titan dest.
    """
    text = census_text()
    hpc_off = re.search(
        r"\| HPC \| `muhl_hpc` \| \*\*IN titan\.gguf\*\* \| (\d+) \|",
        text,
    )
    hpc_in0 = re.search(
        r"\| `muhl_hpc` \| 26480 \| 421 \| `MUHLHPC0` \| input\[0\] `(\d+)` \|",
        text,
    )
    fabric_off = re.search(
        r"\| `muhl_hpc_fabric` \| 26480 \| `MUHLHPCF` \| (\d+) \|",
        text,
    )
    if not hpc_off or not hpc_in0 or not fabric_off:
        raise RuntimeError("SUBZERO_CENSUS.md missing HPC / hpc_fabric dests")
    offset = int(hpc_off.group(1))
    first = int(hpc_in0.group(1))
    fabric = int(fabric_off.group(1))
    delta = first - offset
    if delta != 206:
        raise RuntimeError("census HPC input[0] is not offset + 206")
    if fabric != 103788450688:
        raise RuntimeError("census hpc_fabric offset is not the measured land")
    return [fabric + delta + index for index in range(28)]


def rookery_witness_from_minds():
    """Read rookery witness-ring dests FROM FILE. Do not invent them."""
    text = minds_text()
    bank = re.search(
        r"Recv = clock bank at bytes (\d+)\.\.(\d+) \(24 junction OUTs\)",
        text,
    )
    witness = re.search(
        r"\| 10 \| witness \| (\d+) \|",
        text,
    )
    if not bank or not witness:
        raise RuntimeError("SUBZERO_MINDS.md missing rookery witness dests")
    start = int(bank.group(1))
    end = int(bank.group(2))
    clocks = int(witness.group(1))
    if start != 256 or end != 279:
        raise RuntimeError("rookery clock bank is not bytes 256..279")
    if clocks != 11:
        raise RuntimeError("witness ring is not 11 clocks")
    if start + clocks - 1 > end:
        raise RuntimeError("witness clocks overflow the documented bank")
    return list(range(start, start + clocks))


def planes_from_file():
    """Read landed dests. Do not invent addresses."""
    planes = {}
    sha = {}
    for key in LANDED:
        row, digest = _read_landed(key)
        planes[key] = {
            "ins": list(row["input_addrs"]),
            "outs": list(row["output_addrs"]),
        }
        sha[key] = digest
    planes["muhl_hpc_fabric"] = {
        "ins": hpc_fabric_ins_from_census(),
        "outs": hpc_fabric_ins_from_census(),
    }
    planes["muhl_rookery0"] = {
        "ins": rookery_witness_from_minds(),
        "outs": rookery_witness_from_minds(),
    }
    sha["muhl_hpc_fabric"] = "CENSUS"
    sha["muhl_rookery0"] = "MINDS"
    return planes, sha


def hop_dests(planes):
    """Slice each hop from the FROM FILE planes. No invented addrs.

    Input plane = other organs' out planes. Local surprise is the dest.
    """
    hops = []
    for spec in HOPS:
        n = spec["lanes"]
        src = spec["src"]
        src_addrs = planes[src]["outs"][:n]
        if len(src_addrs) != n:
            raise RuntimeError("%s dests FROM FILE are short" % spec["name"])
        hops.append({
            "name": spec["name"],
            "src_organ": src,
            "dst_organ": NAME,
            "lanes": n,
            "src_addrs": src_addrs,
            "dst_kind": "local surprise bit plane",
        })
    return hops


def dests_from_file():
    planes, sha = planes_from_file()
    hops = hop_dests(planes)
    src_addrs = []
    for hop in hops:
        src_addrs.extend(hop["src_addrs"])
    if len(src_addrs) != N_LANES:
        raise RuntimeError("mirror dests FROM FILE are not 120 lanes")
    expected = {
        "pred_surprise": list(range(3102, 3134)),
        "hpc_fabric_surprise": list(range(103788450894, 103788450922)),
        "immn_surprise": [29636],
        "hdvs_surprise": planes["muhl_hdvs"]["outs"][:32],
        "sdmk_surprise": planes["muhl_sdmk"]["outs"][:16],
        "rookery_witness_surprise": list(range(256, 267)),
    }
    if expected["hdvs_surprise"][:3] != [10274, 10279, 10284]:
        raise RuntimeError("hdvs outs are not the landed sidecar plane")
    if expected["sdmk_surprise"][:3] != [1188, 1963, 2738]:
        raise RuntimeError("sdmk outs are not the landed sidecar plane")
    for hop in hops:
        if hop["src_addrs"] != expected[hop["name"]]:
            raise RuntimeError("%s dests are not the landed planes" % hop["name"])
    return {
        "hops": hops,
        "src_addrs": src_addrs,
        "sha": sha,
    }


def build_gates():
    records = []
    for lane in range(N_LANES):
        src = lane_wire(lane)
        tmp = temp_wire(lane)
        records.append((OP_NAND, src, src, tmp))
    for lane in range(N_LANES):
        tmp = temp_wire(lane)
        out = lane_wire(lane)
        records.append((OP_NAND, tmp, tmp, out))
    return records


def fabricate(base_off=0):
    dests = dests_from_file()
    records = build_gates()
    remap = {lane_wire(i): wa(base_off, lane_wire(i)) for i in range(N_LANES)}
    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    for i in range(N_OUT):
        struct.pack_into("<Q", blob, 28 + i * 8, remap[lane_wire(i)])
    blob[hsz + W_CONST0] = 0
    blob[hsz + W_CONST1] = 1
    stored = []
    off = gate_start
    for op, a, b, out_w in records:
        a_addr = wa(base_off, a)
        b_addr = wa(base_off, b)
        out_addr = remap.get(out_w, wa(base_off, out_w))
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
        "input_addrs": [remap[lane_wire(i)] for i in range(N_IN)],
        "output_addrs": [remap[lane_wire(i)] for i in range(N_OUT)],
        "lanes": N_LANES,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "dests": dests,
    }
    return bytes(blob), meta, stored


def verify_physical(blob, meta, stored):
    assert blob[:8] == MAGIC
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", blob, 8)
    assert (ng, nw, ni, no, dp) == (N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    assert ng == 240
    assert len(blob) == meta["len"]
    hsz = hdr_size()
    writers = {}
    off = hsz + N_WIRES
    for i, (eop, ea, eb, eo) in enumerate(stored):
        op, a, b, o = struct.unpack_from("<BQQQ", blob, off)
        assert (op, a, b, o) == (eop, ea, eb, eo)
        assert o not in writers
        writers[o] = i
        off += GATE_STRIDE
    assert len(writers) == N_GATE
    dests = meta["dests"]
    assert dests["src_addrs"][:32] == list(range(3102, 3134))
    assert dests["src_addrs"][32:60] == list(range(103788450894, 103788450922))
    assert dests["src_addrs"][60:61] == [29636]
    assert dests["src_addrs"][-11:] == list(range(256, 267))
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
            "container": "muhl_titanx_mirror.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "lanes": N_LANES,
            "src": "pred hpc_fabric immn hdvs sdmk rookery witness planes",
            "dst": "local surprise bit plane",
            "buffer": "NAND NAND identity, 2 g per lane, 6 hops",
            "hops": dests["hops"],
            "src_addrs": dests["src_addrs"],
            "pred_sha256": dests["sha"]["muhl_pred"],
            "immn_sha256": dests["sha"]["muhl_immn"],
            "hdvs_sha256": dests["sha"]["muhl_hdvs"],
            "sdmk_sha256": dests["sha"]["muhl_sdmk"],
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "local out IS local in; surprise bit plane only",
            "render": "muhl_png.py bits",
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
    print("MUHLTITM structural receipt")
    print("  n_gate=%d n_wires=%d depth=%d len=%d" % (
        meta["n_gate"], meta["n_wires"], meta["depth"], meta["len"]))
    print("  sha256=%s" % meta["sha256"])
    print("  hops=%s" % ",".join(hop["name"] for hop in meta["dests"]["hops"]))
    print("  dest FROM FILE lanes=%d" % meta["lanes"])
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
