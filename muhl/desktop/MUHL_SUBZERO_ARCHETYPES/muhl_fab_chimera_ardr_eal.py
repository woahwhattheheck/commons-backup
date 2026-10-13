#!/usr/bin/env python3
"""muhl_fab_chimera_ardr_eal.py — WIRE ARDR concentration fields to EAL attractor basins.

Chimera circuit: ARDR's 16 cell-state outputs (the reaction-diffusion
concentration field) drive EAL's attractor-lattice input addresses.
Each wire is a double-negation NAND buffer (depth 2, 2 gates per wire).

This is MANUFACTURING — offline, one-and-done.

    python muhl_fab_chimera_ardr_eal.py          # fabricate and store
    python muhl_fab_chimera_ardr_eal.py --dry    # report only, store nothing

PROPOSE → SCORE → VERIFY → KEEP (per pfc_autofab.py spec).

REQUIRES: both muhl_ardr AND muhl_eal already fabricated in the registry.
"""
import json, os, struct, sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

sys.path.insert(0, r"C:\Users\lucys\Desktop\LocalDeviceAgent\host")
import pfc_paths as PFCP

TITAN = PFCP.TITAN
REG = PFCP.REG
MAGIC = b"MUHLCHAR"
NAND_OP = 0
GATE_STRIDE = 25
NAME = "muhl_chimera_ardr_eal"
GENOME_PATH = TITAN.replace(".gguf", "_%s_genome.jsonl" % NAME)
DRY = "--dry" in sys.argv


# --------------- registry helpers ---------------

def read_ardr_info():
    """Read muhl_ardr from the registry. Returns dict or None."""
    if not os.path.exists(REG):
        return None
    reg = json.load(open(REG))
    entry = reg.get("muhl_ardr")
    if entry is None:
        return None
    cell_addrs = entry.get("cell_state_addrs", [])
    output_addr = entry.get("output_addr")
    inject_addr = entry.get("inject_addr")
    return {
        "cell_state_addrs": [int(a) for a in cell_addrs],
        "output_addr": int(output_addr) if output_addr is not None else None,
        "inject_addr": int(inject_addr) if inject_addr is not None else None,
        "n_cells": entry.get("n_cells", len(cell_addrs)),
    }


def read_eal_info():
    """Read muhl_eal from the registry. Returns dict or None.

    Live EAL input_addrs[0:24] == output_addrs (self-clock). Those already
    have EAL gate writers. DMB→AWCG retired second-writer onto live cell
    bytes. The one EAL mouth with no gate writer is attractor_select
    (host-injected, not fed back).
    """
    if not os.path.exists(REG):
        return None
    reg = json.load(open(REG))
    entry = reg.get("muhl_eal")
    if entry is None:
        return None
    select = entry.get("attractor_select_addr")
    if select is None:
        ins = entry.get("input_addrs") or []
        if len(ins) >= 25:
            select = ins[24]
    outs = entry.get("output_addrs") or []
    ins = entry.get("input_addrs") or []
    return {
        "attractor_select_addr": int(select) if select is not None else None,
        "owned_addrs": set(int(a) for a in list(ins) + list(outs)),
        "offset": entry.get("offset"),
        "name": entry.get("name", "muhl_eal"),
    }


# --------------- allocation ---------------

def alloc_space(nbytes):
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    occupied = []
    for k, v in reg.items():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            occupied.append((v["offset"], v["offset"] + v["len"]))
    occupied.sort()
    hi = max((e for _, e in occupied), default=0)
    off = ((hi + 63) // 64) * 64
    fsize = os.path.getsize(TITAN) if os.path.exists(TITAN) else 0
    if off + nbytes > fsize:
        print(f"  NOTE: chimera ({nbytes:,} bytes) extends past current EOF ({fsize:,}).")
        print(f"  titan.gguf will grow — owner confirmed no size constraint.")
    return off


# --------------- PROPOSE: build wiring gates ---------------

def build_wiring(base_off, src_addrs, select_addr):
    """One-writer ARDR → EAL. MOVE/slot. Do not smash EAL self-clock bytes.

    Pair 0: ARDR[0] → EAL attractor_select (no existing gate writer).
    Pairs 1..N-1: ARDR[i] → fresh slot wires in this blob (MOVE, not overwrite).

    Same double-negation NAND buffer as before (depth 2, 2 gates per wire).
    """
    n_pairs = len(src_addrs)
    n_slot = max(0, n_pairs - 1)
    n_gates = 2 * n_pairs
    depth = 2

    # Blob wires (all written only by this blob, except attractor_select):
    #   [0 .. n_pairs-1]     temp (NOT intermediates)
    #   [n_pairs .. n_pairs+n_slot-1]  MOVE/slot surface for ARDR[1..]
    n_wires = n_pairs + n_slot
    header_size = 8 + 4 + 4 + 4  # magic(8) + n_gates(u32) + n_pairs(u32) + depth(u32)
    gate_start = n_wires + header_size
    total_size = gate_start + n_gates * GATE_STRIDE

    temp_addrs = [base_off + i for i in range(n_pairs)]
    slot_addrs = [base_off + n_pairs + i for i in range(n_slot)]
    dst_addrs = [select_addr] + slot_addrs

    blob = bytearray(total_size)

    hdr = n_wires
    blob[hdr:hdr + 8] = MAGIC
    struct.pack_into("<I", blob, hdr + 8, n_gates)
    struct.pack_into("<I", blob, hdr + 12, n_pairs)
    struct.pack_into("<I", blob, hdr + 16, depth)

    gate_records = []
    off = gate_start
    for i in range(n_pairs):
        src = src_addrs[i]
        tmp = temp_addrs[i]
        dst = dst_addrs[i]
        struct.pack_into("<BQQQ", blob, off, NAND_OP, src, src, tmp)
        gate_records.append((NAND_OP, src, src, tmp))
        off += GATE_STRIDE
        struct.pack_into("<BQQQ", blob, off, NAND_OP, tmp, tmp, dst)
        gate_records.append((NAND_OP, tmp, tmp, dst))
        off += GATE_STRIDE

    return blob, n_gates, depth, gate_records, temp_addrs, slot_addrs, dst_addrs, total_size, n_wires


# --------------- SCORE ---------------

def score_candidate(n_gates, depth):
    return (depth, n_gates)


# --------------- VERIFY ---------------

def verify_blob(blob, base_off, n_gates, gate_records, n_wires):
    """Structural verification of every gate record."""
    hdr = n_wires
    assert blob[hdr:hdr + 8] == MAGIC, "bad magic"
    stored_ng = struct.unpack_from("<I", blob, hdr + 8)[0]
    assert stored_ng == n_gates, f"gate count mismatch: stored {stored_ng} vs {n_gates}"

    gate_start = n_wires + 20  # 8+4+4+4
    writers = {}
    for i, (exp_op, exp_a, exp_b, exp_out) in enumerate(gate_records):
        off = gate_start + i * GATE_STRIDE
        op, a, b, out = struct.unpack_from("<BQQQ", blob, off)
        assert op == NAND_OP, f"gate {i}: op={op}, expected NAND (0)"
        assert a == exp_a, f"gate {i}: a={a}, expected {exp_a}"
        assert b == exp_b, f"gate {i}: b={b}, expected {exp_b}"
        assert out == exp_out, f"gate {i}: out={out}, expected {exp_out}"

        if out in writers and writers[out] != i:
            assert False, f"gate {i}: address {out} already written by gate {writers[out]}"
        writers[out] = i

    return True


# --------------- journal + registry ---------------

def journal_write(off, blob):
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({
            "action": "chimera_ardr_eal_fab",
            "off": off,
            "len": len(blob),
            "orig": orig.hex(),
        }) + "\n")
    fsize = os.path.getsize(TITAN)
    if off + len(blob) > fsize:
        with open(TITAN, "ab") as f:
            f.write(b"\x00" * (off + len(blob) - fsize))
    with open(TITAN, "r+b") as f:
        f.seek(off)
        f.write(blob)


def update_registry(base_off, total_size, n_gates, depth, n_pairs,
                    src_addrs, dst_addrs, temp_addrs, slot_addrs, select_addr):
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    reg[NAME] = {
        "name": NAME,
        "tensor": "allocated_past_eof",
        "offset": base_off,
        "len": total_size,
        "n_gate": n_gates,
        "depth": depth,
        "format": "physical",
        "magic": "MUHLCHAR",
        "gate_stride": GATE_STRIDE,
        "n_pairs": n_pairs,
        "src_circuit": "muhl_ardr",
        "dst_circuit": "muhl_eal",
        "src_addrs": src_addrs,
        "dst_addrs": dst_addrs,
        "temp_addrs": temp_addrs,
        "slot_addrs": slot_addrs,
        "eal_select_addr": select_addr,
        "self_clocked": False,
        "foundry_genome": {
            "topology": "double_negation_buffer_one_writer",
            "n_pairs": n_pairs,
            "depth": depth,
            "eal_mouth": "attractor_select",
            "slot": "MOVE fresh wires for ARDR[1..]",
        },
        "units": "n_gate=GATES, depth=TICKS, len=BYTES",
        "genome": GENOME_PATH,
        "note": ("Chimera wiring: ARDR[0] → EAL attractor_select; "
                 "ARDR[1..] → MOVE/slot fresh wires. Do not smash EAL "
                 "self-clock input_addrs. Double-negation NAND buffer, depth 2."),
        "verified_by": "structural + one-writer (no dest on live EAL state bytes)",
    }
    json.dump(reg, open(REG, "w"), indent=1)


# --------------- MAIN ---------------

def main():
    print("\n  MUHLNICKEL CHIMERA — ARDR → EAL WIRING")
    print("  Bryce Muhlnickel, 2026-08-03\n")

    # 1. Read source circuit (ARDR)
    ardr = read_ardr_info()
    if ardr is None:
        print("  ERROR: muhl_ardr not found in registry.")
        print("  Fabricate muhl_ardr first, then re-run this chimera wiring.")
        return 1
    print(f"  ARDR: {ardr['n_cells']} cell_state addresses found")

    # 2. Read destination circuit (EAL)
    eal = read_eal_info()
    if eal is None:
        print("  ERROR: muhl_eal not found in registry.")
        print("  Fabricate muhl_eal first, then re-run this chimera wiring.")
        print("")
        print("  ARDR is ready (16 cell_state outputs). Waiting for EAL.")
        return 1

    src_addrs = ardr["cell_state_addrs"]
    select_addr = eal["attractor_select_addr"]
    if not src_addrs:
        print("  ERROR: no wire pairs — ARDR has 0 cells.")
        return 1
    if select_addr is None:
        print("  ERROR: EAL has no attractor_select_addr. Do not invent dest.")
        return 1

    n_pairs = len(src_addrs)
    smash = eal["owned_addrs"] - {select_addr}
    print(f"  ARDR cells: {n_pairs}")
    print(f"  EAL mouth:  attractor_select @ {select_addr} (one-writer)")
    print(f"  MOVE/slot:  ARDR[1..] → fresh blob wires (do not smash EAL)")

    # 3. PROPOSE
    base_off = alloc_space(n_pairs * 2 * GATE_STRIDE + n_pairs + (n_pairs - 1) + 20)
    blob, n_gates, depth, gate_records, temp_addrs, slot_addrs, dst_addrs, total_size, n_wires = \
        build_wiring(base_off, src_addrs, select_addr)

    print(f"  PROPOSE: double-negation buffer, one-writer")
    print(f"    gates:  {n_gates}")
    print(f"    depth:  {depth} ticks")
    print(f"    size:   {total_size:,} bytes")
    print(f"    dest0:  EAL attractor_select @ {select_addr}")
    print(f"    slot:   {len(slot_addrs)} fresh wires")

    # Re-alloc with exact size now known
    base_off = alloc_space(total_size)
    blob, n_gates, depth, gate_records, temp_addrs, slot_addrs, dst_addrs, total_size, n_wires = \
        build_wiring(base_off, src_addrs, select_addr)

    smashed = [d for d in dst_addrs if d in smash]
    if smashed:
        print("  ERROR: dest would smash live EAL writer bytes: %s" % smashed)
        return 1

    # 4. SCORE
    print(f"\n  SCORE: ({depth}, {n_gates})")

    # 5. VERIFY
    ok = verify_blob(blob, base_off, n_gates, gate_records, n_wires)
    print(f"  VERIFY: {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("  ABORTING — verification failed")
        return 1

    # 6. PARETO SET
    print(f"\n  PARETO SET (1 candidate — double-negation buffer is minimal at depth 2):")
    print(f"    double_neg_one_writer: {n_gates} gates, depth {depth}, {total_size:,} bytes")

    if DRY:
        print(f"\n  --dry: nothing stored. Run without --dry to fabricate.")
        return 0

    # 7. KEEP: store (journaled)
    print(f"\n  FABRICATING — writing {total_size:,} bytes at offset {base_off:,}")
    journal_write(base_off, bytes(blob))
    print(f"  journaled to: {GENOME_PATH}")

    # 8. Registry
    update_registry(base_off, total_size, n_gates, depth, n_pairs,
                    src_addrs, dst_addrs, temp_addrs, slot_addrs, select_addr)
    print(f"  registry updated: {NAME}")

    print(f"\n  CHIMERA ARDR → EAL FABRICATED.")
    print(f"  {n_pairs} wires, depth {depth} ticks. EAL self-clock bytes unsmashed.")
    print(f"  ARDR[0] drives EAL attractor_select. ARDR[1..] MOVE/slot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
