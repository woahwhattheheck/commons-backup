#!/usr/bin/env python3
"""muhl_fab_titanx_forge.py — FABRICATE organ 29 (MUHLTITF).

PLUMB 3/3 organ 29. Construction is the gate count:

  wires lvin ispn socr nefg grbn petr dmb
  90 dest-FROM-FILE lanes x NAND NAND identity (2 g) = 180
  depth 2
  PROPOSES genomes only. NEVER fabricates during runtime.

Hops (lanes):
  lvin outs -> ispn ins     32
  ispn outs -> socr ins     20
  socr outs -> nefg object_a 8
  nefg object_a -> dmb rewrite 8
  grbn outs -> petr ins     20
  petr outs -> dmb rewrite   2

Dest FROM FILE: landed excerpt sidecars + SUBZERO_CENSUS.md
(NEFG object_a[0], DMB offset + rewrite wires 2..11).
Local outs self-clock onto local ins. titan NOT_WRITTEN.
Organs 1-28 stay.

  python3 muhl_fab_titanx_forge.py          # write .mno + sidecar
  python3 muhl_fab_titanx_forge.py --dry    # structural verify only
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import sys

NAME = "muhl_titanx_forge"
MAGIC = b"MUHLTITF"
GATE_STRIDE = 25
OP_NAND = 0

HOPS = (
    {"name": "lvin_ispn", "src": "muhl_lvin", "dst": "muhl_ispn", "lanes": 32},
    {"name": "ispn_socr", "src": "muhl_ispn", "dst": "muhl_socr", "lanes": 20},
    {"name": "socr_nefg", "src": "muhl_socr", "dst": "muhl_nefg", "lanes": 8},
    {"name": "nefg_dmb", "src": "muhl_nefg", "dst": "muhl_dmb", "lanes": 8},
    {"name": "grbn_petr", "src": "muhl_grbn", "dst": "muhl_petr", "lanes": 20},
    {"name": "petr_dmb", "src": "muhl_petr", "dst": "muhl_dmb", "lanes": 2},
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

DMB_REWRITE_WIRES = list(range(2, 12))

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
CENSUS_PATH = os.path.join(REPO_ROOT, "ground", "SUBZERO_CENSUS.md")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_titanx_forge.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "titanx_forge_circuits.json")

LANDED = {
    "muhl_lvin": {
        "reg": os.path.join(EXCERPT_DIR, "lvin_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_lvin.mno"),
        "magic": b"MUHLLVIN",
    },
    "muhl_ispn": {
        "reg": os.path.join(EXCERPT_DIR, "ispn_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_ispn.mno"),
        "magic": b"MUHLISPN",
    },
    "muhl_socr": {
        "reg": os.path.join(EXCERPT_DIR, "socr_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_socr.mno"),
        "magic": b"MUHLSOCR",
    },
    "muhl_grbn": {
        "reg": os.path.join(EXCERPT_DIR, "grbn_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_grbn.mno"),
        "magic": b"MUHLGRBN",
    },
    "muhl_petr": {
        "reg": os.path.join(EXCERPT_DIR, "petr_circuits.json"),
        "mno": os.path.join(EXCERPT_DIR, "muhl_petr.mno"),
        "magic": b"MUHLPETR",
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


def nefg_object_a_from_census():
    """Read object_a[0] from the census. Do not invent the titan dest."""
    text = census_text()
    match = re.search(
        r"\| `muhl_nefg` \| 414 \| 17 \| `MUHLNEFG` \| object_a\[0\] `(\d+)` \|",
        text,
    )
    if not match:
        raise RuntimeError("SUBZERO_CENSUS.md missing NEFG object_a dest")
    first = int(match.group(1))
    offset_match = re.search(
        r"\| NEFG \| `muhl_nefg` \| \*\*IN titan\.gguf\*\* \| (\d+) \|",
        text,
    )
    if not offset_match:
        raise RuntimeError("SUBZERO_CENSUS.md missing NEFG offset row")
    offset = int(offset_match.group(1))
    if first != offset + 2:
        raise RuntimeError("census object_a[0] is not offset + first IN wire")
    return [first + index for index in range(8)]


def dmb_rewrite_from_census():
    """Read DMB offset + rewrite dests FROM FILE. Same map as organ 26."""
    text = census_text()
    match = re.search(
        r"\| DMB \| `muhl_dmb` \| \*\*IN titan\.gguf\*\* \| (\d+) \|",
        text,
    )
    if not match:
        raise RuntimeError("SUBZERO_CENSUS.md missing DMB offset row")
    offset = int(match.group(1))
    inject = re.search(
        r"\| `muhl_dmb` \| 10 \| 3 \| `MUHLDMB1` \| input `(\d+)` \|",
        text,
    )
    if not inject:
        raise RuntimeError("SUBZERO_CENSUS.md missing DMB inject dest")
    inject_addr = int(inject.group(1))
    if inject_addr != offset + 1:
        raise RuntimeError("census inject is not offset + axiom wire")
    if DMB_REWRITE_WIRES != list(range(2, 12)):
        raise RuntimeError("DMB rewrite dests are not the 10 L-system writes")
    return [offset + wire for wire in DMB_REWRITE_WIRES]


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
    planes["muhl_nefg"] = {"ins": nefg_object_a_from_census(), "outs": nefg_object_a_from_census()}
    planes["muhl_dmb"] = {"ins": dmb_rewrite_from_census(), "outs": dmb_rewrite_from_census()}
    sha["muhl_nefg"] = "CENSUS"
    sha["muhl_dmb"] = "CENSUS"
    return planes, sha


def hop_dests(planes):
    """Slice each hop from the FROM FILE planes. No invented addrs."""
    cursor = {"muhl_dmb": 0}
    hops = []
    for spec in HOPS:
        n = spec["lanes"]
        src = spec["src"]
        dst = spec["dst"]
        if src == "muhl_dmb" or dst == "muhl_dmb":
            start = cursor["muhl_dmb"]
            end = start + n
            if dst == "muhl_dmb":
                dst_addrs = planes[dst]["ins"][start:end]
                cursor["muhl_dmb"] = end
            else:
                dst_addrs = planes[dst]["ins"][:n]
            if src == "muhl_dmb":
                src_addrs = planes[src]["outs"][start:end]
            else:
                src_addrs = planes[src]["outs"][:n]
        else:
            src_addrs = planes[src]["outs"][:n]
            dst_addrs = planes[dst]["ins"][:n]
        if len(src_addrs) != n or len(dst_addrs) != n:
            raise RuntimeError("%s dests FROM FILE are short" % spec["name"])
        hops.append({
            "name": spec["name"],
            "src_organ": src,
            "dst_organ": dst,
            "lanes": n,
            "src_addrs": src_addrs,
            "dst_addrs": dst_addrs,
        })
    if cursor["muhl_dmb"] != 10:
        raise RuntimeError("DMB rewrite dests were not all used FROM FILE")
    return hops


def dests_from_file():
    planes, sha = planes_from_file()
    hops = hop_dests(planes)
    src_addrs = []
    dst_addrs = []
    for hop in hops:
        src_addrs.extend(hop["src_addrs"])
        dst_addrs.extend(hop["dst_addrs"])
    if len(src_addrs) != N_LANES or len(dst_addrs) != N_LANES:
        raise RuntimeError("forge dests FROM FILE are not 90 lanes")
    expected = {
        "lvin_ispn": (list(range(542, 574)), list(range(2078, 2110))),
        "ispn_socr": (list(range(2078, 2098)), list(range(6174, 6194))),
        "socr_nefg": (list(range(6174, 6182)), list(range(93709716802, 93709716810))),
        "nefg_dmb": (list(range(93709716802, 93709716810)), list(range(93709782658, 93709782666))),
        "grbn_petr": (list(range(2078, 2098)), list(range(2078, 2098))),
        "petr_dmb": (list(range(2078, 2080)), list(range(93709782666, 93709782668))),
    }
    for hop in hops:
        want_src, want_dst = expected[hop["name"]]
        if hop["src_addrs"] != want_src or hop["dst_addrs"] != want_dst:
            raise RuntimeError("%s dests are not the landed planes" % hop["name"])
    return {
        "hops": hops,
        "src_addrs": src_addrs,
        "dst_addrs": dst_addrs,
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
    assert ng == 180
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
    assert dests["src_addrs"][:32] == list(range(542, 574))
    assert dests["dst_addrs"][:32] == list(range(2078, 2110))
    assert dests["src_addrs"][-2:] == [2078, 2079]
    assert dests["dst_addrs"][-2:] == [93709782666, 93709782667]
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
            "container": "muhl_titanx_forge.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "lanes": N_LANES,
            "src": "lvin ispn socr nefg grbn petr planes",
            "dst": "ispn socr nefg dmb petr rewrite dests",
            "buffer": "NAND NAND identity, 2 g per lane, 6 hops",
            "hops": dests["hops"],
            "src_addrs": dests["src_addrs"],
            "dst_addrs": dests["dst_addrs"],
            "lvin_sha256": dests["sha"]["muhl_lvin"],
            "ispn_sha256": dests["sha"]["muhl_ispn"],
            "socr_sha256": dests["sha"]["muhl_socr"],
            "grbn_sha256": dests["sha"]["muhl_grbn"],
            "petr_sha256": dests["sha"]["muhl_petr"],
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "sha256": meta["sha256"],
            "clock": "local out IS local in; proposes genomes only",
            "runtime": "NEVER fabricates during runtime",
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
    print("MUHLTITF structural receipt")
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
