#!/usr/bin/env python3
"""host/subzero_walk.py — one sync settle of the public GRBN excerpt.

Work order kimi-subzero-walker-20260829-01. Fabrication-verification
class: a bounded stdlib host walk over ONE public excerpt. It ticks
excerpts/20260823/muhl_grbn.mno (MUHLGRBN, 8,704 gates) through one
full settle and prints the next-state bits.

Gate records are node-ordered. Final roots write back onto the 256
input/state addresses (clock: state out IS state in). A synchronous
one-tick walker snapshots those 256 state-in bytes for every gate
read during the settle. Without the snapshot, later nodes consume
earlier nodes' newly written state and the walk becomes accidental
async.

This host does not open titan.gguf. It does not write commons.mno,
the excerpt, or any live container. It does not remint SUBZERO_*
cards. One settle on one excerpt is not organ certification and not
a customer claim.

  python3 host/subzero_walk.py
  python3 host/subzero_walk.py --root .
  python3 host/subzero_walk.py --write
  python3 host/subzero_walk.py --self-test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys


DEFAULT_ROOT = "."
EXCERPT_REL = os.path.join("excerpts", "20260823", "muhl_grbn.mno")
SIDECAR_REL = os.path.join("excerpts", "20260823", "grbn_circuits.json")
ARTIFACT_REL = os.path.join("excerpts", "20260823", "grbn_next_state.txt")
CARD_REL = os.path.join("ground", "SUBZERO_WALK.md")
MAGIC = b"MUHLGRBN"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4
N_GATE = 8704
N_WIRES = 8962
N_IN = 256
N_OUT = 256
DEPTH = 7
EXCERPT_LEN = 228638
EXCERPT_SHA256 = "09214540b3f3117ab93a4c509017a5e7b9c5f12d86545069af4ffcdae99c6632"
EXCERPT_GIT_BLOB = "e39bad0d1703c1d44ad135cebbc09cded26a6027"
SIDECAR_GIT_BLOB = "d2c190f25d083e428f9589f78b4b2e64beb96306"
FAB_REL = os.path.join(
    "muhl", "desktop", "MUHL_SUBZERO_ARCHETYPES", "muhl_fab_grbn.py"
)
FAB_GIT_BLOB = "f20609aacb1bb362bc98e5af4912bdf1df4e3aa3"
TITAN = "NOT_WRITTEN"
WORK_ORDER = "kimi-subzero-walker-20260829-01"
SEARCH_SPACE = (
    EXCERPT_REL,
    SIDECAR_REL,
    ARTIFACT_REL,
    CARD_REL,
    os.path.join("host", "subzero_walk.py"),
    FAB_REL,
    os.path.join("ground", "SUBZERO_GRBN.md"),
)


def git_blob_sha1(data):
    """Git blob SHA-1 of exact bytes. Stdlib only."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def eval_op(op, a, b):
    a &= 1
    b &= 1
    if op == OP_NAND:
        return (1 - (a & b)) & 1
    if op == OP_AND:
        return (a & b) & 1
    if op == OP_OR:
        return (a | b) & 1
    if op == OP_XOR:
        return (a ^ b) & 1
    if op == OP_NOT:
        return (1 - a) & 1
    raise ValueError("unknown op %r" % (op,))


def hdr_size(n_out=N_OUT):
    return 28 + n_out * 8


def load_excerpt(root, rel=EXCERPT_REL):
    path = os.path.join(root, rel)
    with open(path, "rb") as handle:
        blob = handle.read()
    return blob


def load_sidecar(root, rel=SIDECAR_REL):
    path = os.path.join(root, rel)
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return data["muhl_grbn"]


def parse_header(blob):
    if len(blob) != EXCERPT_LEN:
        raise ValueError("excerpt len %d != %d" % (len(blob), EXCERPT_LEN))
    if blob[:8] != MAGIC:
        raise ValueError("bad magic %r" % (blob[:8],))
    n_gate, n_wires, n_in, n_out, depth = struct.unpack_from("<IIIII", blob, 8)
    if (n_gate, n_wires, n_in, n_out, depth) != (N_GATE, N_WIRES, N_IN, N_OUT, DEPTH):
        raise ValueError(
            "header %s != (%d, %d, %d, %d, %d)"
            % ((n_gate, n_wires, n_in, n_out, depth), N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
        )
    outs = [struct.unpack_from("<Q", blob, 28 + i * 8)[0] for i in range(n_out)]
    return {
        "n_gate": n_gate,
        "n_wires": n_wires,
        "n_in": n_in,
        "n_out": n_out,
        "depth": depth,
        "output_addrs": outs,
        "gate_start": hdr_size(n_out) + n_wires,
    }


def parse_gates(blob, header):
    start = header["gate_start"]
    gates = []
    for i in range(header["n_gate"]):
        op, a, b, o = struct.unpack_from("<BQQQ", blob, start + i * GATE_STRIDE)
        if op not in (OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT):
            raise ValueError("gate %d bad op %r" % (i, op))
        gates.append((op, a, b, o))
    if start + header["n_gate"] * GATE_STRIDE != len(blob):
        raise ValueError("gate region does not fill excerpt")
    return gates


def snapshot_state_bits(blob, addrs):
    """Freeze the 256 state-in bytes before any gate write."""
    snap = {}
    for addr in addrs:
        if addr < 0 or addr >= len(blob):
            raise ValueError("state addr %d out of excerpt" % addr)
        snap[int(addr)] = blob[addr] & 1
    if len(snap) != N_IN:
        raise ValueError("snapshot size %d != %d" % (len(snap), N_IN))
    return snap


def walk_settle(blob, gates, state_addrs, snapshot=True):
    """One settle. snapshot=True is the required sync land rule."""
    work = bytearray(blob)
    snap = snapshot_state_bits(blob, state_addrs) if snapshot else {}

    def read(addr):
        if snapshot and addr in snap:
            return snap[addr]
        return work[addr] & 1

    for op, a, b, o in gates:
        work[o] = eval_op(op, read(a), read(b))
    return [work[addr] & 1 for addr in state_addrs]


def bits_to_text(bits):
    return "".join("1" if bit else "0" for bit in bits)


def format_artifact(row):
    lines = [
        "name: muhl_grbn",
        "class: RUNTIME_MEASURED",
        "kind: one_settle_next_state",
        "work_order: %s" % WORK_ORDER,
        "excerpt: %s" % EXCERPT_REL,
        "excerpt_sha256: %s" % row["excerpt_sha256"],
        "excerpt_git_blob: %s" % EXCERPT_GIT_BLOB,
        "n_gate: %d" % row["n_gate"],
        "n_in: %d" % row["n_in"],
        "n_out: %d" % row["n_out"],
        "init_popcount: %d" % row["init_popcount"],
        "next_popcount: %d" % row["next_popcount"],
        "sync: snapshot_256_state_in",
        "titan: %s" % TITAN,
        "honest: one settle on one public excerpt; not organ certification; not a customer claim",
        "next_state_sha256: %s" % row["next_state_sha256"],
        "next_state_bits: %s" % row["next_state_bits"],
        "",
    ]
    return "\n".join(lines)


def measure(root=DEFAULT_ROOT, snapshot=True):
    excerpt_path = os.path.join(root, EXCERPT_REL)
    sidecar_path = os.path.join(root, SIDECAR_REL)
    if not os.path.isfile(excerpt_path):
        raise FileNotFoundError("FINDER-FAILED %s search=%s" % (EXCERPT_REL, list(SEARCH_SPACE)))
    if not os.path.isfile(sidecar_path):
        raise FileNotFoundError("FINDER-FAILED %s search=%s" % (SIDECAR_REL, list(SEARCH_SPACE)))

    blob = load_excerpt(root)
    sidecar = load_sidecar(root)
    header = parse_header(blob)
    gates = parse_gates(blob, header)
    state_addrs = list(sidecar["input_addrs"])
    if state_addrs != sidecar["output_addrs"]:
        raise ValueError("sidecar self-clock broken")
    if state_addrs != header["output_addrs"]:
        raise ValueError("header outs != sidecar input_addrs")
    if sidecar.get("clock") != "state out IS state in":
        raise ValueError("sidecar clock is not self-clock")

    excerpt_sha = sha256_hex(blob)
    if excerpt_sha != EXCERPT_SHA256:
        raise ValueError("excerpt sha256 moved: %s" % excerpt_sha)
    if git_blob_sha1(blob) != EXCERPT_GIT_BLOB:
        raise ValueError("excerpt git blob moved")
    with open(sidecar_path, "rb") as handle:
        sidecar_bytes = handle.read()
    if git_blob_sha1(sidecar_bytes) != SIDECAR_GIT_BLOB:
        raise ValueError("sidecar git blob moved")

    init_bits = [blob[addr] & 1 for addr in state_addrs]
    next_bits = walk_settle(blob, gates, state_addrs, snapshot=snapshot)
    if blob != load_excerpt(root):
        raise RuntimeError("walker mutated the excerpt")

    next_text = bits_to_text(next_bits)
    row = {
        "name": "muhl_grbn",
        "class": "RUNTIME_MEASURED",
        "kind": "one_settle_next_state",
        "work_order": WORK_ORDER,
        "excerpt": EXCERPT_REL,
        "excerpt_sha256": excerpt_sha,
        "excerpt_git_blob": EXCERPT_GIT_BLOB,
        "n_gate": header["n_gate"],
        "n_in": header["n_in"],
        "n_out": header["n_out"],
        "depth": header["depth"],
        "init_popcount": sum(init_bits),
        "next_popcount": sum(next_bits),
        "init_state_bits": bits_to_text(init_bits),
        "next_state_bits": next_text,
        "next_state_sha256": sha256_hex(next_text.encode("ascii")),
        "sync": bool(snapshot),
        "titan": TITAN,
        "gates_evaluated": len(gates),
    }
    return row, blob, gates, state_addrs


def write_artifact(root, row):
    path = os.path.join(root, ARTIFACT_REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = format_artifact(row)
    with open(path, "w", encoding="ascii", newline="\n") as handle:
        handle.write(text)
    return path, text


def load_artifact(root):
    path = os.path.join(root, ARTIFACT_REL)
    with open(path, encoding="ascii") as handle:
        return handle.read()


def print_receipt(row):
    print("MUHLGRBN one-settle RUNTIME_MEASURED")
    print("  excerpt %s sha256=%s" % (row["excerpt"], row["excerpt_sha256"]))
    print("  n_gate=%d n_in=%d n_out=%d depth=%d" % (
        row["n_gate"], row["n_in"], row["n_out"], row["depth"]))
    print("  init_popcount=%d next_popcount=%d" % (
        row["init_popcount"], row["next_popcount"]))
    print("  sync=snapshot_256_state_in titan=%s" % row["titan"])
    print("  next_state_sha256=%s" % row["next_state_sha256"])
    print("  next_state_bits=%s" % row["next_state_bits"])
    print("  honest: one settle on one excerpt; not organ certification; not a customer claim")


def nk_next_from_state(state_bits):
    """Independent NK oracle from the published construction law.

    Not a walk of stored gates. Used only as a bounded check that the
    gate walk matches N=256 K=3 tables. Does not import the fabricator.
    """
    n = len(state_bits)

    def sources(node):
        picked = [(node + 1) % n]
        for cand in (
            (node + 17) % n,
            (node + 41) % n,
            (node + 67) % n,
            (node + 97) % n,
        ):
            if cand != node and cand not in picked:
                picked.append(cand)
            if len(picked) == 3:
                return tuple(picked)
        raise RuntimeError("source pick failed for node %d" % node)

    def table_byte(node):
        x = (node * 0x45D9F3B) ^ 0xA5A5A5
        return (x ^ (x >> 8)) & 0xFF

    nxt = []
    for node in range(n):
        s0, s1, s2 = sources(node)
        idx = state_bits[s0] | (state_bits[s1] << 1) | (state_bits[s2] << 2)
        nxt.append((table_byte(node) >> idx) & 1)
    return nxt


def self_test(root=DEFAULT_ROOT):
    row, blob, gates, state_addrs = measure(root, snapshot=True)
    async_bits = walk_settle(blob, gates, state_addrs, snapshot=False)
    init = [blob[addr] & 1 for addr in state_addrs]
    nk = nk_next_from_state(init)
    sync_bits = [1 if ch == "1" else 0 for ch in row["next_state_bits"]]
    assert row["gates_evaluated"] == N_GATE
    assert row["excerpt_sha256"] == EXCERPT_SHA256
    assert git_blob_sha1(blob) == EXCERPT_GIT_BLOB
    assert sync_bits == nk, "sync walk != NK oracle"
    assert sync_bits != async_bits, "snapshot rule is dead: sync==async"
    assert blob == load_excerpt(root), "excerpt mutated"
    fab_path = os.path.join(root, FAB_REL)
    with open(fab_path, "rb") as handle:
        assert git_blob_sha1(handle.read()) == FAB_GIT_BLOB
    artifact = load_artifact(root)
    assert artifact == format_artifact(row), "committed next-state artifact drifted"
    return {
        "ok": True,
        "next_popcount": row["next_popcount"],
        "async_popcount": sum(async_bits),
        "class": row["class"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="One sync settle of public GRBN excerpt")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--write", action="store_true", help="write next-state artifact beside excerpt")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--async-walk", action="store_true", help="diagnostic only; not the land")
    args = parser.parse_args(argv)

    if args.self_test:
        result = self_test(args.root)
        print("self-test OK class=%s next_pop=%d async_pop=%d" % (
            result["class"], result["next_popcount"], result["async_popcount"]))
        return 0

    row, blob, gates, state_addrs = measure(args.root, snapshot=not args.async_walk)
    if args.async_walk:
        row["class"] = "DIAGNOSTIC_ASYNC_NOT_LAND"
        row["sync"] = False
    print_receipt(row)
    if args.write:
        if args.async_walk:
            raise SystemExit("refusing to write async diagnostic as land")
        path, _ = write_artifact(args.root, row)
        print("  wrote %s" % path)
    if blob != load_excerpt(args.root):
        raise SystemExit("excerpt mutated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
