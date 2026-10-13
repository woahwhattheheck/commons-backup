#!/usr/bin/env python3
"""host/muhl_puzzle71_organs_cloud.py — derived scan-based CI helper.

Not the live-run instrument. Exact owner-PC bytes live at
host/muhl_puzzle71_organs_add.py (Fable branch fable/puzzle71-buttons-20260902-01
blob 9128536487cb20181bf4dc96605a23a515ba9854). This copy exists so cloud
tests can run on a tiny fixture without --fab against the 4.8GB container.

Fable 5.1 CLAIM fable-puzzle71-organs-fold-tick-20260901-01 (Slack 1788313096.975209).
Host computes zero inference. Dest FROM FILE. Revert = journal.

Default --dry: scan, print plan, write nothing.
--go: journal, retarget 70 latch b-fields -> win@159, append 16 nring2-class
rings x 32 cells both senses + 24 clocks each, OR tree of pubs -> tick@88,
PUZFOLD1 decl (addr_bits 70, winner-only, 0 B/lane), write registry, die.
revert: restore journaled preimages and truncate the append.

Never titan. Never sweep (gates are not deleted). Never --inject (wipe).
Never commons.mno / dc.

  python3 host/muhl_puzzle71_organs_cloud.py --dry --dest PATH
  python3 host/muhl_puzzle71_organs_cloud.py --go --dest PATH
  python3 host/muhl_puzzle71_organs_cloud.py revert --dest PATH
"""
from __future__ import annotations

import json
import os
import struct
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    import pfc_paths as PFCP

    PFC_ROOT = PFCP.ROOT
except (ImportError, AttributeError):
    PFC_ROOT = os.environ.get("PFC_ROOT", "C:/llm").replace("\\", "/").rstrip("/")

STRIDE = 25
NAND, AND, OR, XOR = 0, 1, 2, 3
CELLS = 32
N_RINGS = 16
CLOCKS_PER_RING = 24
RING_SPAN = CELLS + CELLS + 2  # fwd, rev, carry, pub
LATCH_B_OLD = 186446309
LATCH_N = 70
WIN_OUT = 159
TICK_ADDR = 88
ADDR_BITS = 70
PUZFOLD_MAGIC = b"PUZFOLD1"
PUZFOLD_LEN = 32
DEFAULT_DEST = PFC_ROOT + "/models/muhl_puzzle71.mno"
DEFAULT_REG = PFC_ROOT + "/models/muhl_puzzle71.circuits.json"
DEFAULT_JOURNAL = PFC_ROOT + "/models/muhl_puzzle71_organs_add_genome.jsonl"
FORBIDDEN = frozenset(
    ("titan.gguf", "muhlnickel_dc.mno", "dc.mno", "commons.mno")
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fail(msg):
    print("FAIL CLOSED: %s" % msg)
    return 1


def _arg_value(argv, flag, default=None):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 >= len(argv):
            return None, "%s needs a value" % flag
        return argv[i + 1], None
    return default, None


def _arg_int(argv, flag, default):
    raw, err = _arg_value(argv, flag, None)
    if err:
        return None, err
    if raw is None:
        return default, None
    try:
        val = int(raw, 0)
    except ValueError:
        return None, "%s is not an int" % flag
    if val < 0:
        return None, "%s is negative" % flag
    return val, None


def refuse_dest(path):
    base = os.path.basename(os.path.normpath(path)).lower()
    if base in FORBIDDEN:
        return "REFUSE dest %s" % base
    lower = os.path.normpath(path).replace("\\", "/").lower()
    if lower.endswith("/titan.gguf") or lower.endswith("\\titan.gguf"):
        return "REFUSE dest titan.gguf"
    return None


def pack_rec(op, a, b, out):
    return struct.pack("<BQQQ", op, a, b, out)


def unpack_rec(blob):
    return struct.unpack("<BQQQ", blob)


def _read_at(path, off, n):
    with open(path, "rb") as f:
        f.seek(off)
        got = f.read(n)
    if len(got) != n:
        raise IOError("short read @%s n=%s got=%s" % (off, n, len(got)))
    return got


def _write_at(path, off, data):
    with open(path, "r+b") as f:
        f.seek(off)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def _append(path, data):
    with open(path, "ab") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def scan_records(path, stride=STRIDE):
    size = os.path.getsize(path)
    recs = []
    writers = {}
    with open(path, "rb") as f:
        off = 0
        while off + stride <= size:
            blob = f.read(stride)
            if len(blob) < stride:
                break
            op, a, b, out = unpack_rec(blob)
            recs.append({"off": off, "op": op, "a": a, "b": b, "out": out})
            writers.setdefault(out, []).append(off)
            off += stride
    return {"size": size, "n_records": len(recs), "records": recs, "writers": writers, "tail": size % stride}


def pack_puzfold():
    body = PUZFOLD_MAGIC + struct.pack("<I", ADDR_BITS) + struct.pack("<BBH", 1, 0, 0)
    body += b"\x00" * (PUZFOLD_LEN - len(body))
    return body


def build_plan(scan, latch_b_old, latch_n, win_out, tick_addr, n_rings, cells, clocks):
    latches = [r for r in scan["records"] if r["b"] == latch_b_old]
    tick_writers = scan["writers"].get(tick_addr, [])
    if len(latches) != latch_n:
        return None, "latch b=%s count %s != expected %s" % (latch_b_old, len(latches), latch_n)
    if tick_writers:
        return None, "tick@%s already has writer(s) at %s" % (tick_addr, tick_writers)
    if win_out == tick_addr:
        return None, "win_out and tick_addr collide"
    ring_base = scan["size"]
    span = cells + cells + 2
    rings = []
    for ri in range(n_rings):
        fwd = ring_base + ri * span
        rings.append(
            {
                "name": "nring2_puz%02d" % ri,
                "fwd": fwd,
                "rev": fwd + cells,
                "carry": fwd + 2 * cells,
                "pub": fwd + 2 * cells + 1,
                "cells": cells,
            }
        )
    clock_base = ring_base + n_rings * span
    for ri, ring in enumerate(rings):
        ring["clocks"] = [clock_base + ri * clocks + k for k in range(clocks)]
    tmp_base = clock_base + n_rings * clocks
    n_tmp = n_rings - 2  # 16->8->4->2 uses 8+4+2 tmps; last OR writes tick
    if n_rings < 2:
        return None, "need at least 2 rings"
    gate_base = tmp_base + n_tmp
    recs = []
    for ring in rings:
        f, r, c, p = ring["fwd"], ring["rev"], ring["carry"], ring["pub"]
        for k in range(cells):
            recs.append((XOR, f + (k - 1) % cells, c, f + k))
        for k in range(cells):
            recs.append((XOR, r + (k + 1) % cells, c, r + k))
        recs.append((AND, f, r, c))
        recs.append((OR, p, c, p))
        for clk in ring["clocks"]:
            recs.append((AND, c, c, clk))
    or_recs, tmps = _or_tree([ring["pub"] for ring in rings], tmp_base, tick_addr)
    recs.extend(or_recs)
    outs = [t[3] for t in recs]
    seen = {}
    for i, out in enumerate(outs):
        if out in seen:
            return None, "ONE-WRITER collision out=%s gates %s and %s" % (out, seen[out], i)
        seen[out] = i
    puzfold_off = gate_base + len(recs) * STRIDE
    new_size = puzfold_off + PUZFOLD_LEN
    return {
        "old_size": scan["size"],
        "n_records_now": scan["n_records"],
        "latch_b_old": latch_b_old,
        "latch_n": latch_n,
        "latch_offs": [r["off"] for r in latches],
        "win_out": win_out,
        "tick_addr": tick_addr,
        "ring_base": ring_base,
        "clock_base": clock_base,
        "tmp_base": tmp_base,
        "tmps": tmps,
        "gate_base": gate_base,
        "n_new_gates": len(recs),
        "puzfold_off": puzfold_off,
        "new_size": new_size,
        "rings": rings,
        "new_recs": recs,
        "addr_bits": ADDR_BITS,
        "winner_only": 1,
        "stored_per_lane": 0,
        "puzfold": "PUZFOLD1",
    }, None


def _or_tree(pubs, tmp_base, final_out):
    recs = []
    tmps = []
    tmp = tmp_base
    level = list(pubs)
    while len(level) > 1:
        nxt = []
        i = 0
        last_pair = len(level) == 2
        while i < len(level):
            if i + 1 == len(level):
                nxt.append(level[i])
                i += 1
                continue
            a, b = level[i], level[i + 1]
            if last_pair and not nxt:
                out = final_out
            else:
                out = tmp
                tmps.append(out)
                tmp += 1
            recs.append((OR, a, b, out))
            nxt.append(out)
            i += 2
        level = nxt
    return recs, tmps


def registry_from_plan(dest, plan):
    return {
        "container": dest.replace("\\", "/"),
        "measured_at": _now(),
        "PUZFOLD1": {
            "magic": "PUZFOLD1",
            "offset": plan["puzfold_off"],
            "len": PUZFOLD_LEN,
            "addr_bits": plan["addr_bits"],
            "base": "2^%s" % plan["addr_bits"],
            "winner_only": True,
            "stored_per_lane": 0,
        },
        "tick": {"addr": plan["tick_addr"]},
        "win": {"addr": plan["win_out"]},
        "latch_retarget": {
            "count": plan["latch_n"],
            "old_b": plan["latch_b_old"],
            "new_b": plan["win_out"],
            "offs": plan["latch_offs"],
        },
        "or_tree": {"out": plan["tick_addr"], "tmps": plan["tmps"]},
        "gate_base": plan["gate_base"],
        "n_new_gates": plan["n_new_gates"],
        "rings": [
            {
                "name": ring["name"],
                "fwd": ring["fwd"],
                "rev": ring["rev"],
                "carry": ring["carry"],
                "pub": ring["pub"],
                "clocks": ring["clocks"],
                "cells": ring["cells"],
            }
            for ring in plan["rings"]
        ],
        "law": "additive journaled; new=old|mask on fire; no sweep; no titan",
    }


def print_plan(plan, dest, reg_path, journal_path, mode):
    print("PUZZLE71 ORGANS", mode)
    print("  dest", dest)
    print("  registry", reg_path)
    print("  journal", journal_path)
    print("  now records=%s size=%s" % (plan["n_records_now"], plan["old_size"]))
    print("  latch b %s -> win@%s  n=%s" % (plan["latch_b_old"], plan["win_out"], plan["latch_n"]))
    print("  tick@%s writers=0 (will gain OR-tree writer)" % plan["tick_addr"])
    print("  rings %s cells=%s clocks/ring=%s ring_base=%s" % (
        len(plan["rings"]), plan["rings"][0]["cells"], len(plan["rings"][0]["clocks"]), plan["ring_base"]
    ))
    print("  new gates=%s gate_base=%s PUZFOLD1@%s new_size=%s" % (
        plan["n_new_gates"], plan["gate_base"], plan["puzfold_off"], plan["new_size"]
    ))
    print("  PUZFOLD1 addr_bits=%s winner_only=1 stored_per_lane=0 base=2^%s" % (
        plan["addr_bits"], plan["addr_bits"]
    ))


def _journal(journal_path, row):
    parent = os.path.dirname(journal_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(journal_path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def apply_plan(dest, plan, reg_path, journal_path):
    old_reg = None
    if os.path.isfile(reg_path):
        with open(reg_path, encoding="utf-8") as f:
            old_reg = json.load(f)
        if isinstance(old_reg, dict) and old_reg.get("rings"):
            return _fail("already fabricated; revert first")
    session = {"ts": _now(), "kind": "session", "dest": dest, "old_size": plan["old_size"], "reg": reg_path}
    _journal(journal_path, session)
    patches = []
    for off in plan["latch_offs"]:
        old = _read_at(dest, off, STRIDE)
        op, a, _b, out = unpack_rec(old)
        new = pack_rec(op, a, plan["win_out"], out)
        patches.append({"off": off, "old_hex": old.hex(), "new_hex": new.hex()})
        _journal(journal_path, {"kind": "patch", "off": off, "old_hex": old.hex(), "new_hex": new.hex()})
        _write_at(dest, off, new)
    wire_len = plan["gate_base"] - plan["old_size"]
    wires = bytes(wire_len)
    gate_blob = b"".join(pack_rec(*rec) for rec in plan["new_recs"])
    puz = pack_puzfold()
    append_blob = wires + gate_blob + puz
    _journal(
        journal_path,
        {
            "kind": "append",
            "off": plan["old_size"],
            "old_size": plan["old_size"],
            "blob_len": len(append_blob),
        },
    )
    _append(dest, append_blob)
    if old_reg is not None:
        _journal(journal_path, {"kind": "reg", "old": old_reg})
    else:
        _journal(journal_path, {"kind": "reg", "old": None})
    parent = os.path.dirname(reg_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(reg_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(registry_from_plan(dest, plan), f, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    after = os.path.getsize(dest)
    if after != plan["new_size"]:
        return _fail("size after write %s != plan %s" % (after, plan["new_size"]))
    print("JOURNAL", journal_path)
    print("REGISTRY", reg_path)
    print("AFTER size=%s patches=%s" % (after, len(patches)))
    print("DIE")
    return 0


def revert(dest, journal_path, reg_path):
    if not os.path.isfile(journal_path):
        return _fail("no journal — nothing to revert")
    rows = []
    with open(journal_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    old_size = None
    old_reg = None
    for row in reversed(rows):
        kind = row.get("kind")
        if kind == "patch":
            _write_at(dest, int(row["off"]), bytes.fromhex(row["old_hex"]))
        elif kind == "append":
            old_size = int(row["old_size"])
        elif kind == "reg":
            old_reg = row.get("old")
        elif kind == "session" and old_size is None:
            old_size = int(row["old_size"])
    if old_size is None:
        return _fail("journal has no size to truncate")
    with open(dest, "r+b") as f:
        f.truncate(old_size)
        f.flush()
        os.fsync(f.fileno())
    if old_reg is None:
        if os.path.isfile(reg_path):
            os.remove(reg_path)
    else:
        with open(reg_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(old_reg, f, indent=2, sort_keys=True)
            f.write("\n")
    os.remove(journal_path)
    print("REVERT dest size=%s" % os.path.getsize(dest))
    print("DIE")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--inject" in argv:
        print("REFUSE: --inject 0x01 is WIPE. Law is new=old|mask / journaled additive.")
        return 2
    dest, err = _arg_value(argv, "--dest", DEFAULT_DEST)
    if err:
        return _fail(err)
    refuse = refuse_dest(dest)
    if refuse:
        print(refuse)
        return 2
    reg_path, err = _arg_value(argv, "--reg", os.path.splitext(dest)[0] + ".circuits.json")
    if err:
        return _fail(err)
    journal_path, err = _arg_value(argv, "--journal", os.path.splitext(dest)[0] + "_organs_add_genome.jsonl")
    if err:
        return _fail(err)
    if "revert" in argv:
        return revert(dest, journal_path, reg_path)
    if "--go" not in argv and "--dry" not in argv:
        print("NEED --dry or --go (or revert). dest FROM FILE. default --dry is the safe act.")
        return 1
    if not os.path.isfile(dest):
        return _fail("dest missing: %s" % dest)
    latch_b, err = _arg_int(argv, "--latch-b", LATCH_B_OLD)
    if err:
        return _fail(err)
    latch_n, err = _arg_int(argv, "--latch-n", LATCH_N)
    if err:
        return _fail(err)
    win_out, err = _arg_int(argv, "--win-out", WIN_OUT)
    if err:
        return _fail(err)
    tick_addr, err = _arg_int(argv, "--tick", TICK_ADDR)
    if err:
        return _fail(err)
    n_rings, err = _arg_int(argv, "--rings", N_RINGS)
    if err:
        return _fail(err)
    cells, err = _arg_int(argv, "--cells", CELLS)
    if err:
        return _fail(err)
    clocks, err = _arg_int(argv, "--clocks", CLOCKS_PER_RING)
    if err:
        return _fail(err)
    scan = scan_records(dest)
    plan, err = build_plan(scan, latch_b, latch_n, win_out, tick_addr, n_rings, cells, clocks)
    if err:
        return _fail(err)
    mode = "GO" if "--go" in argv else "DRY"
    print_plan(plan, dest, reg_path, journal_path, mode)
    if "--go" not in argv:
        print("DRY. no write.")
        print("DIE")
        return 0
    return apply_plan(dest, plan, reg_path, journal_path)


if __name__ == "__main__":
    raise SystemExit(main())
