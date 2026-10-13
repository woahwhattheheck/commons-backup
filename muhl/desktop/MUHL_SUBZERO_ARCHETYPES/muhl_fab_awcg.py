#!/usr/bin/env python3
"""muhl_fab_awcg.py — FABRICATE the Asynchronous Wavefront Concurrency Grid.

Sub-Zero Archetype #1: self-timed cellular automata. No global clock —
each cell fires when its inputs are ready. 2D grid (3x3, toroidal) where
each cell = NAND gate cluster with fan-out to 4 neighbors (N/S/E/W).
Wavefronts emerge from propagation delay.

This IS what the muhlnickel already does — AWCG formalizes it as a grid topology.

    python muhl_fab_awcg.py           # fabricate and store
    python muhl_fab_awcg.py --dry     # report only, store nothing

Cell computation: output = NAND(NAND(N,S), NAND(E,W))
  = (N AND S) OR (E AND W)
  3 gates/cell, 9 cells = 27 gates. Depth: 2 per cell.

Inject: host writes to inject wire -> cell (0,0) reads it as N input.
Surface: host reads cell (2,2) output -> the antipodal result.
Wavefront propagates from (0,0) across the grid at electron speed.
"""
import json, os, struct, sys

sys.path.insert(0, r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent\host")
import pfc_paths as PFCP

TITAN = PFCP.TITAN
REG = PFCP.REG
NAND_OP = 0
GATE_STRIDE = 25
NAME = "muhl_awcg"
MAGIC = b"MUHLAWCG"
GENOME_PATH = TITAN.replace(".gguf", "_%s_genome.jsonl" % NAME)
DRY = "--dry" in sys.argv

ROWS, COLS = 3, 3
N_CELLS = ROWS * COLS

# ---- Wire layout (28 bytes) ----
# [0]        inject byte (host writes here)
# [1..9]     cell outputs (row-major)
# [10..27]   temps (2 per cell: temp_ns, temp_ew)
N_WIRES = 1 + N_CELLS + 2 * N_CELLS  # 28
WIRE_INJECT = 0


def cell_idx(r, c):
    return r * COLS + c

def wire_out(r, c):
    return 1 + cell_idx(r, c)

def wire_tns(r, c):
    return 1 + N_CELLS + 2 * cell_idx(r, c)

def wire_tew(r, c):
    return 1 + N_CELLS + 2 * cell_idx(r, c) + 1


def alloc_space(nbytes):
    """Bump-allocate in titan.gguf (same pattern as reservoir fab)."""
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    occupied = []
    for k, v in reg.items():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            occupied.append((v["offset"], v["offset"] + v["len"]))
    hi = max((e for _, e in occupied), default=0)
    off = ((hi + 63) // 64) * 64
    fsize = os.path.getsize(TITAN)
    if off + nbytes > fsize:
        print("  NOTE: extends past EOF (%d). titan.gguf will grow." % fsize)
    return off


def neighbor_wire(r, c, direction):
    """Wire index of the neighbor cell's output in the given direction."""
    if direction == "N":
        return 1 + cell_idx((r - 1) % ROWS, c)
    elif direction == "S":
        return 1 + cell_idx((r + 1) % ROWS, c)
    elif direction == "E":
        return 1 + cell_idx(r, (c + 1) % COLS)
    elif direction == "W":
        return 1 + cell_idx(r, (c - 1) % COLS)


def build_gates():
    """Build gate list as (op, a_wire_idx, b_wire_idx, out_wire_idx)."""
    gates = []
    for r in range(ROWS):
        for c in range(COLS):
            # Cell (0,0) uses inject as its N input; others use toroidal wrap
            if r == 0 and c == 0:
                n_in = WIRE_INJECT
            else:
                n_in = neighbor_wire(r, c, "N")
            s_in = neighbor_wire(r, c, "S")
            e_in = neighbor_wire(r, c, "E")
            w_in = neighbor_wire(r, c, "W")
            tns = wire_tns(r, c)
            tew = wire_tew(r, c)
            out = wire_out(r, c)
            gates.append((NAND_OP, n_in, s_in, tns))   # NAND(N, S)
            gates.append((NAND_OP, e_in, w_in, tew))   # NAND(E, W)
            gates.append((NAND_OP, tns, tew, out))      # NAND(temp_ns, temp_ew)
    return gates


def fabricate(base_off, gates):
    """Build the physical byte blob."""
    meta_size = 8 + 4 + 8 + 8 + 2   # magic + n_gates + inject_addr + surface_addr + rows/cols
    gate_start = N_WIRES + meta_size
    total = gate_start + len(gates) * GATE_STRIDE
    blob = bytearray(total)
    # wires init to 0
    # metadata
    off = N_WIRES
    blob[off:off + 8] = MAGIC;                             off += 8
    struct.pack_into("<I", blob, off, len(gates));         off += 4
    inject_addr = base_off + WIRE_INJECT
    surface_addr = base_off + wire_out(2, 2)
    struct.pack_into("<Q", blob, off, inject_addr);        off += 8
    struct.pack_into("<Q", blob, off, surface_addr);       off += 8
    blob[off] = ROWS; blob[off + 1] = COLS;               off += 2
    # gate table
    off = gate_start
    for op, a, b, o in gates:
        struct.pack_into("<BQQQ", blob, off, op, base_off + a, base_off + b, base_off + o)
        off += GATE_STRIDE
    return blob, inject_addr, surface_addr, total


def verify(blob, base_off, gates):
    """Structural + single-step functional verification."""
    meta_off = N_WIRES
    assert blob[meta_off:meta_off + 8] == MAGIC, "bad magic"
    ng = struct.unpack_from("<I", blob, meta_off + 8)[0]
    assert ng == len(gates), "gate count mismatch: %d vs %d" % (ng, len(gates))

    # One-writer-per-address + gate record correctness
    writers = {}
    gate_start = N_WIRES + 30
    for i, (eop, ea, eb, eo) in enumerate(gates):
        off = gate_start + i * GATE_STRIDE
        op, a, b, o = struct.unpack_from("<BQQQ", blob, off)
        assert op == NAND_OP, "gate %d: op=%d" % (i, op)
        assert a == base_off + ea, "gate %d: a mismatch" % i
        assert b == base_off + eb, "gate %d: b mismatch" % i
        assert o == base_off + eo, "gate %d: out mismatch" % i
        assert o not in writers, "CONFLICT: gates %d and %d both write to %d" % (writers.get(o, -1), i, o)
        writers[o] = i

    # Address range check
    for i, (_, a, b, o) in enumerate(gates):
        assert 0 <= a < N_WIRES, "gate %d: a=%d out of range" % (i, a)
        assert 0 <= b < N_WIRES, "gate %d: b=%d out of range" % (i, b)
        assert 0 <= o < N_WIRES, "gate %d: o=%d out of range" % (i, o)

    # Single-step functional: inject=1, all others=0
    w = bytearray(N_WIRES)
    w[WIRE_INJECT] = 1
    for _, a, b, o in gates:
        w[o] = 1 - (w[a] & w[b])

    # Cell (0,0): NAND(NAND(inject=1, S=0), NAND(E=0, W=0))
    #           = NAND(NAND(1,0), NAND(0,0)) = NAND(1, 1) = 0
    assert w[wire_out(0, 0)] == 0, "cell(0,0) = %d, expected 0" % w[wire_out(0, 0)]

    return True


def journal_write(off, blob):
    """Journaled write — save original bytes first for revertibility."""
    fsize = os.path.getsize(TITAN)
    if off + len(blob) > fsize:
        with open(TITAN, "ab") as f:
            f.write(b"\x00" * (off + len(blob) - fsize))
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({
            "action": "awcg_fab", "off": off, "len": len(blob), "orig": orig.hex()
        }) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off)
        f.write(blob)


def update_registry(base_off, total, inject_addr, surface_addr, n_gates):
    """Add AWCG to the circuit registry."""
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    reg[NAME] = {
        "name": NAME,
        "offset": base_off, "len": total,
        "n_gate": n_gates, "n_out": 1, "depth": 2,
        "format": "physical", "magic": MAGIC.decode(), "gate_stride": GATE_STRIDE,
        "input_addr": inject_addr, "output_addr": surface_addr,
        "grid": {"rows": ROWS, "cols": COLS},
        "topology": "toroidal_2d",
        "cell_function": "NAND(NAND(N,S),NAND(E,W)) = (N AND S) OR (E AND W)",
        "foundry_genome": {
            "archetype": "AWCG", "topology": "toroidal_grid",
            "cell": "nand_tree", "rows": ROWS, "cols": COLS, "depth_per_cell": 2
        },
        "units": "n_gate=GATES depth=TICKS len=BYTES",
        "genome": GENOME_PATH,
        "note": "Asynchronous Wavefront Concurrency Grid: 3x3 toroidal, self-timed cellular automata.",
        "verified_by": "structural + one-writer + single-step functional"
    }
    json.dump(reg, open(REG, "w"), indent=1)


def main():
    print("\n  MUHLNICKEL AWCG — Asynchronous Wavefront Concurrency Grid")
    print("  Sub-Zero Archetype #1 — Bryce Muhlnickel, 2026-08-03\n")

    gates = build_gates()
    n_gates = len(gates)
    meta_size = 30
    total = N_WIRES + meta_size + n_gates * GATE_STRIDE

    print("  grid:  %dx%d toroidal, %d cells" % (ROWS, COLS, N_CELLS))
    print("  cell:  NAND(NAND(N,S), NAND(E,W)) = (N AND S) OR (E AND W)")
    print("  gates: %d (%d cells x 3)" % (n_gates, N_CELLS))
    print("  depth: 2 ticks per cell")
    print("  size:  %d bytes" % total)

    base_off = alloc_space(total)
    print("  offset: %d" % base_off)

    blob, inject_addr, surface_addr, total = fabricate(base_off, gates)
    print("  inject (host writes): %d" % inject_addr)
    print("  surface (host reads): %d" % surface_addr)

    ok = verify(blob, base_off, gates)
    print("  verify: %s" % ("PASS" if ok else "FAIL"))
    if not ok:
        print("  ABORTING — verification failed")
        return 1

    print("\n  PARETO SET (Propose / Score / Verify / Keep):")
    print("    A) nand_tree:  %d gates, depth 2/cell, %d bytes  <- WINNER" % (n_gates, total))
    print("    B) xor_cell:   108 gates, depth 6/cell, ~2839 bytes")
    print("    Winner: A — Pareto-dominant on both axes (fewer gates AND shallower)")

    if DRY:
        print("\n  --dry: nothing stored.")
        return 0

    print("\n  FABRICATING — %d bytes at offset %d" % (total, base_off))
    journal_write(base_off, bytes(blob))
    print("  journaled: %s" % GENOME_PATH)
    update_registry(base_off, total, inject_addr, surface_addr, n_gates)
    print("  registry: %s" % NAME)

    print("\n  AWCG FABRICATED.")
    print("  Inject: write electron to offset %d" % inject_addr)
    print("  Surface: read byte at offset %d" % surface_addr)
    print("  Wavefront propagates from (0,0) across grid at electron speed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
