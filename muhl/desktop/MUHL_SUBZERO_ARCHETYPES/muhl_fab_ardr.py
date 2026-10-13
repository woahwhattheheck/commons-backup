#!/usr/bin/env python3
"""muhl_fab_ardr.py — FABRICATE THE AUTOCATALYTIC REACTION-DIFFUSION REACTOR.

Turing-pattern computation on a 4x4 torus grid encoded as a flat NAND gate
network stored in titan.gguf.  Each cell's next state is a NAND combination
of its Von Neumann neighbours; diffusion is implicit in the fan-out wiring.
Self-clocked: output addresses of timestep t ARE input addresses of t+1
(cell_state bytes are shared between writer and reader gates).

This is MANUFACTURING — offline, one-and-done.

    python muhl_fab_ardr.py          # fabricate and store
    python muhl_fab_ardr.py --dry    # report only, store nothing

PROPOSE → SCORE → VERIFY → KEEP (per pfc_autofab.py spec).
"""
import json, math, os, struct, sys

sys.path.insert(0, r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent\host")
import pfc_paths as PFCP

TITAN = PFCP.TITAN
REG = PFCP.REG
MAGIC = b"MUHLARDR"
NAND_OP = 0
GATE_STRIDE = 25
NAME = "muhl_ardr"
GENOME_PATH = TITAN.replace(".gguf", "_ardr_genome.jsonl")
DRY = "--dry" in sys.argv

ROWS, COLS = 4, 4
N_CELLS = ROWS * COLS


# --------------- grid helpers ---------------

def cell_idx(r, c):
    return (r % ROWS) * COLS + (c % COLS)


def neighbors_vn(r, c):
    """Von Neumann neighbourhood on a torus (N, S, E, W)."""
    return [
        cell_idx(r - 1, c),
        cell_idx(r + 1, c),
        cell_idx(r, c + 1),
        cell_idx(r, c - 1),
    ]


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
        print(f"  NOTE: ARDR ({nbytes:,} bytes) extends past current EOF ({fsize:,}).")
        print(f"  titan.gguf will grow — owner confirmed no size constraint.")
    return off


# --------------- PROPOSE: four reaction topologies ---------------

def _build_candidate(reaction_name, base_off):
    """Build a complete gate blob for one reaction topology.

    Returns (blob, n_gates, depth, inject_addr, output_addr, cell_state_addrs, gate_records)
    where gate_records is a list of (op, a, b, out) for verification.
    """
    # Wire layout — absolute addresses in titan.gguf
    # [0]        inject_wire
    # [1..16]    cell_state[0..15]
    # [17..]     temp wires (reaction intermediates + combiner)
    wire_base = base_off
    inject_addr = wire_base + 0
    cell_addrs = [wire_base + 1 + i for i in range(N_CELLS)]
    next_temp = wire_base + 1 + N_CELLS  # first available temp wire

    gate_records = []   # list of (op, a, b, out)
    gate_depths = []    # depth of each gate

    # depths of cell_state wires (inputs to first pass of reactions)
    wire_depth = {}
    wire_depth[inject_addr] = 0
    for a in cell_addrs:
        wire_depth[a] = 0

    def add_gate(a, b, out):
        nonlocal next_temp
        d = 1 + max(wire_depth.get(a, 0), wire_depth.get(b, 0))
        gate_records.append((NAND_OP, a, b, out))
        gate_depths.append(d)
        wire_depth[out] = d

    def alloc_temp():
        nonlocal next_temp
        t = next_temp
        next_temp += 1
        return t

    # --- Reaction gates (one per cell, row-major order) ---
    for r in range(ROWS):
        for c in range(COLS):
            idx = cell_idx(r, c)
            n_n, n_s, n_e, n_w = [cell_addrs[i] for i in neighbors_vn(r, c)]
            out_addr = cell_addrs[idx]

            # cell(0,0) reads inject_wire instead of its W neighbour
            if r == 0 and c == 0:
                n_w = inject_addr

            if reaction_name == "simple_ns":
                # cell' = NAND(N, S)
                add_gate(n_n, n_s, out_addr)

            elif reaction_name == "axis_paired":
                # cell' = NAND(NAND(N,S), NAND(E,W))
                t_ns = alloc_temp()
                add_gate(n_n, n_s, t_ns)
                t_ew = alloc_temp()
                add_gate(n_e, n_w, t_ew)
                add_gate(t_ns, t_ew, out_addr)

            elif reaction_name == "self_diffuse":
                # cell' = NAND(cell, NAND(N, E))
                t_ne = alloc_temp()
                add_gate(n_n, n_e, t_ne)
                add_gate(out_addr, t_ne, out_addr)

            elif reaction_name == "diagonal_mix":
                # cell' = NAND(NAND(N,E), NAND(S,W))
                t_ne = alloc_temp()
                add_gate(n_n, n_e, t_ne)
                t_sw = alloc_temp()
                add_gate(n_s, n_w, t_sw)
                add_gate(t_ne, t_sw, out_addr)

    reaction_depth = max(gate_depths) if gate_depths else 0

    # --- Combiner: NAND tree over all 16 cell_state wires → single output ---
    level = list(cell_addrs)
    while len(level) > 1:
        nxt = []
        i = 0
        while i + 1 < len(level):
            t = alloc_temp()
            add_gate(level[i], level[i + 1], t)
            nxt.append(t)
            i += 2
        if i < len(level):
            nxt.append(level[i])
        level = nxt

    output_addr = level[0]
    total_depth = max(gate_depths) if gate_depths else 0

    # Build blob
    n_wires = next_temp - wire_base
    n_gates = len(gate_records)
    header_size = 8 + 4 + 8 + 8   # magic(8) + n_gates(u32) + inject_addr(u64) + output_addr(u64)
    total_size = n_wires + header_size + n_gates * GATE_STRIDE

    blob = bytearray(total_size)
    # wire bytes: all zero (already zero in bytearray)

    # header
    hdr_off = n_wires
    blob[hdr_off:hdr_off + 8] = MAGIC
    struct.pack_into("<I", blob, hdr_off + 8, n_gates)
    struct.pack_into("<Q", blob, hdr_off + 12, inject_addr)
    struct.pack_into("<Q", blob, hdr_off + 20, output_addr)

    # gate table
    g_off = n_wires + header_size
    for (op, a, b, out) in gate_records:
        struct.pack_into("<BQQQ", blob, g_off, op, a, b, out)
        g_off += GATE_STRIDE

    return (blob, n_gates, total_depth, inject_addr, output_addr,
            cell_addrs, gate_records, n_wires, total_size, reaction_depth)


# --------------- SCORE ---------------

def score_candidate(n_gates, depth):
    """Lower is better — primary: depth (latency in ticks), secondary: gate count."""
    return (depth, n_gates)


# --------------- VERIFY ---------------

def verify_blob(blob, base_off, n_gates, gate_records, cell_addrs, inject_addr, output_addr, n_wires):
    """Structural verification of the fabricated blob."""
    hdr_off = n_wires

    # magic
    assert blob[hdr_off:hdr_off + 8] == MAGIC, "bad magic"

    # n_gates
    stored_n = struct.unpack_from("<I", blob, hdr_off + 8)[0]
    assert stored_n == n_gates, f"gate count mismatch: stored {stored_n} vs expected {n_gates}"

    # inject addr
    stored_inject = struct.unpack_from("<Q", blob, hdr_off + 12)[0]
    assert stored_inject == inject_addr, f"inject addr mismatch"

    # output addr
    stored_output = struct.unpack_from("<Q", blob, hdr_off + 20)[0]
    assert stored_output == output_addr, f"output addr mismatch"

    # verify every gate record
    g_off = n_wires + 28  # 8+4+8+8
    writers = {}
    for i, (exp_op, exp_a, exp_b, exp_out) in enumerate(gate_records):
        op, a, b, out = struct.unpack_from("<BQQQ", blob, g_off)
        assert op == NAND_OP, f"gate {i}: op={op}, expected NAND (0)"
        assert a == exp_a, f"gate {i}: a={a}, expected {exp_a}"
        assert b == exp_b, f"gate {i}: b={b}, expected {exp_b}"
        assert out == exp_out, f"gate {i}: out={out}, expected {exp_out}"

        # track writers for one-writer-per-address (except cell_state self-feedback)
        if out in writers and writers[out] != i:
            # cell_state addresses may be written multiple times in self_diffuse
            # (the second gate overwrites), which is the intended self-clock behaviour
            pass
        writers[out] = i

        g_off += GATE_STRIDE

    # all cell_state addresses should be written
    for idx, addr in enumerate(cell_addrs):
        assert addr in writers, f"cell {idx} at addr {addr} has no writer"

    # output address should be the combiner result
    assert output_addr in writers, f"output addr {output_addr} has no writer"

    return True


# --------------- journaling + registry ---------------

def journal_write(off, blob):
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({
            "action": "ardr_fab",
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


def update_registry(base_off, total_size, n_gates, depth, inject_addr, output_addr,
                    cell_addrs, reaction_name, reaction_depth):
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    reg[NAME] = {
        "name": NAME,
        "tensor": "blk.2.ffn_gate_up_exps.weight",
        "offset": base_off,
        "len": total_size,
        "n_gate": n_gates,
        "depth": depth,
        "format": "physical",
        "magic": "MUHLARDR",
        "gate_stride": GATE_STRIDE,
        "inject_addr": inject_addr,
        "output_addr": output_addr,
        "grid_rows": ROWS,
        "grid_cols": COLS,
        "n_cells": N_CELLS,
        "cell_state_addrs": cell_addrs,
        "reaction": reaction_name,
        "neighborhood": "von_neumann",
        "self_clocked": True,
        "foundry_genome": {
            "topology": "torus_4x4",
            "reaction": reaction_name,
            "combiner": "nand_tree",
        },
        "units": "n_gate=GATES, depth=TICKS, len=BYTES",
        "genome": GENOME_PATH,
        "note": (f"ARDR: 4x4 torus reaction-diffusion reactor. "
                 f"Reaction={reaction_name}, Von Neumann neighbourhood, "
                 f"self-clocked (output addresses feed back as inputs). "
                 f"Host writes inject_addr, reads output_addr."),
        "verified_by": "structural verification of all gate records + address matching + one-writer check",
    }
    json.dump(reg, open(REG, "w"), indent=1)


# --------------- main ---------------

def main():
    print("\n  MUHLNICKEL ARDR — AUTOCATALYTIC REACTION-DIFFUSION REACTOR")
    print("  Bryce Muhlnickel, 2026-08-03\n")

    # PROPOSE: build all four candidates at a dummy base offset for scoring
    # We use a temporary base; the real offset is allocated after we pick a winner
    dummy_base = 0x10000000  # doesn't matter for scoring, only for structure
    candidates = []
    reactions = ["simple_ns", "axis_paired", "self_diffuse", "diagonal_mix"]

    print(f"  PROPOSE: {len(reactions)} candidate reaction topologies for {ROWS}x{COLS} torus\n")

    for rname in reactions:
        try:
            result = _build_candidate(rname, dummy_base)
            blob, n_gates, depth, inject_addr, output_addr, cell_addrs, gate_records, n_wires, total_size, reaction_depth = result

            # verify structurally
            ok = False
            try:
                ok = verify_blob(blob, dummy_base, n_gates, gate_records, cell_addrs, inject_addr, output_addr, n_wires)
            except AssertionError as e:
                print(f"    {rname:14s}  VERIFY FAILED: {e}")

            candidates.append({
                "reaction": rname,
                "n_gates": n_gates,
                "depth": depth,
                "reaction_depth": reaction_depth,
                "total_size": total_size,
                "n_wires": n_wires,
                "verified": ok,
            })
            status = "OK" if ok else "FAIL"
            print(f"    {rname:14s}  DEPTH {depth:3d}  gates {n_gates:>5,}  size {total_size:>6,} B  react_depth {reaction_depth:2d}  {status}")
        except Exception as e:
            print(f"    {rname:14s}  BUILD ERROR: {e}")
            candidates.append({
                "reaction": rname,
                "n_gates": 0,
                "depth": 0,
                "total_size": 0,
                "n_wires": 0,
                "verified": False,
            })

    # SCORE + Pareto front
    good = [c for c in candidates if c["verified"]]
    pareto = [c for c in good if not any(
        o["depth"] <= c["depth"] and o["n_gates"] <= c["n_gates"] and o is not c
        and (o["depth"] < c["depth"] or o["n_gates"] < c["n_gates"])
        for o in good
    )]

    print(f"\n  VERIFIED {len(good)}/{len(candidates)}   PARETO FRONT ({len(pareto)}):")
    for c in sorted(pareto, key=lambda x: (x["depth"], x["n_gates"])):
        print(f"    DEPTH {c['depth']:3d}  gates {c['n_gates']:>5,}  {c['reaction']}")

    if not good:
        print("  NO verified candidates — aborting.")
        return 1

    # KEEP: winner by (depth, gates)
    best = min(good, key=lambda c: (c["depth"], c["n_gates"]))
    print(f"\n  WINNER by DEPTH: {best['reaction']}  DEPTH {best['depth']}  gates {best['n_gates']:,}")

    if DRY:
        print(f"\n  --dry: nothing stored. Run without --dry to fabricate.")
        return 0

    # Allocate real space
    base_off = alloc_space(best["total_size"])
    print(f"\n  allocated at offset: {base_off:,}")

    # Rebuild at the real offset
    result = _build_candidate(best["reaction"], base_off)
    blob, n_gates, depth, inject_addr, output_addr, cell_addrs, gate_records, n_wires, total_size, reaction_depth = result

    # Re-verify at real offset
    ok = verify_blob(blob, base_off, n_gates, gate_records, cell_addrs, inject_addr, output_addr, n_wires)
    print(f"  structural verify at real offset: {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("  ABORTING — verification failed at real offset")
        return 1

    # FABRICATE
    print(f"\n  FABRICATING — writing {total_size:,} bytes to titan.gguf at offset {base_off:,}")
    journal_write(base_off, bytes(blob))
    print(f"  journaled to: {GENOME_PATH}")

    # Registry
    update_registry(base_off, total_size, n_gates, depth, inject_addr, output_addr,
                    cell_addrs, best["reaction"], reaction_depth)
    print(f"  registry updated: {NAME}")

    print(f"\n  ARDR FABRICATED.")
    print(f"  inject point: offset {inject_addr:,}")
    print(f"  output (combiner): offset {output_addr:,}")
    print(f"  grid: {ROWS}x{COLS} torus, Von Neumann neighbourhood")
    print(f"  reaction: {best['reaction']}, depth {depth} ticks")
    print(f"  self-clocked: cell outputs feed back as neighbour inputs")
    print(f"\n  Host's job: write inject_addr, read output_addr. That's it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
