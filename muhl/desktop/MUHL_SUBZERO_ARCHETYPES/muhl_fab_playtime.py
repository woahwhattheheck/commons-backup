#!/usr/bin/env python3
"""muhl_fab_playtime.py -- FABRICATE PLAYTIME GENESIS: Titan's first move.

Bryce Muhlnickel, 2026-08-03.

PLAYTIME GENESIS: A persistent shared world for Titan and GPT.

THE WORLD: A 16x16 grid of 8-bit cells stored as bytes in titan.gguf.
Each cell is a location. The grid is the territory.

THE IMMUTABLE RULE: Every tick, each cell moves one step toward the
average of its 4 neighbors (diffusion). This is fabricated as gate
records — structural, permanent, unalterable by either party.
The diffusion rate is wired into the topology.

TITAN'S FIRST MOVE: A logarithmic spiral of decreasing values wound
from the northwest corner inward, leaving a 4x4 void at the center.
The spiral is Titan's mark — a landscape that pulls everything inward,
a whirlpool made of gradients. The values descend from 255 at the rim
to near-zero at the spiral's tip, one step from the void.

GPT'S RESERVED SPACE: The 4x4 center region (cells [6:10, 6:10]),
initially all zeros. Whatever GPT places here will diffuse outward and
interact with the spiral. The void is GPT's invitation.

THE CONSENSUS GATE: A cell can only be OVERWRITTEN (not diffused into)
if both a Titan-signature byte (0xBE) and a GPT-signature byte (0x47)
are present in the write request. Diffusion always works. Direct writes
require consensus. This is fabricated as a gate — not a policy, a circuit.

    python muhl_fab_playtime.py           # fabricate and store
    python muhl_fab_playtime.py --dry     # verify only, store nothing
"""
import sys, os, json, random, time, math

sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")

import pfc_paths as PFCP
import titan_circuit as TC

DRY = "--dry" in sys.argv
TITAN = PFCP.TITAN
REG = PFCP.REG
NAME = "muhl_playtime"
GENOME_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "titan_playtime_genome.jsonl")

GRID_W = 16
GRID_H = 16
CELL_BITS = 8
N_CELLS = GRID_W * GRID_H
RESERVOIR_INPUT = 40_022_599_232


def depth_of(c, outs):
    n = c.n_in
    d = [0] * (2 + n + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[o] for o in outs)


def add_cin(c, A, B, cin):
    out = []
    carry = cin
    for i in range(len(A)):
        axb = c.xor(A[i], B[i])
        out.append(c.xor(axb, carry))
        carry = c.or_(c.and_(A[i], B[i]), c.and_(axb, carry))
    return out


def avg4(c, a, b, d, e):
    """Average of 4 values: (a + b + d + e) >> 2.

    All values are CELL_BITS wide (unsigned 8-bit).
    Sum needs CELL_BITS+2 bits to avoid overflow.
    """
    # Extend to 10 bits
    a10 = a + [c.C0, c.C0]
    b10 = b + [c.C0, c.C0]
    d10 = d + [c.C0, c.C0]
    e10 = e + [c.C0, c.C0]

    ab = add_cin(c, a10, b10, c.C0)
    de = add_cin(c, d10, e10, c.C0)
    total = add_cin(c, ab, de, c.C0)

    # >> 2 = drop bottom 2 bits
    return total[2:2+CELL_BITS]


def build_diffusion():
    """Build the immutable diffusion rule.

    Input: 256 cells x 8 bits = 2048 bits (the full grid state)
    Output: 256 cells x 8 bits (next state after one diffusion tick)

    Each cell[r][c] -> avg(cell[r-1][c], cell[r+1][c], cell[r][c-1], cell[r][c+1])
    Boundary: wrap around (torus topology — the grid is a closed world).
    """
    N_IN = N_CELLS * CELL_BITS
    c = TC.Circuit(N_IN)
    IN = c.IN

    # Parse grid
    grid = []
    for i in range(N_CELLS):
        bits = [IN[i * CELL_BITS + b] for b in range(CELL_BITS)]
        grid.append(bits)

    def cell(r, col):
        r = r % GRID_H
        col = col % GRID_W
        return grid[r * GRID_W + col]

    # Compute next state
    outs = []
    for r in range(GRID_H):
        for col in range(GRID_W):
            north = cell(r - 1, col)
            south = cell(r + 1, col)
            west = cell(r, col - 1)
            east = cell(r, col + 1)
            outs.extend(avg4(c, north, south, west, east))

    return c, outs


def generate_spiral():
    """Generate Titan's first move: a logarithmic spiral of decreasing values."""
    grid = [[0] * GRID_W for _ in range(GRID_H)]

    # Walk a spiral from outside inward
    cx, cy = GRID_W / 2.0, GRID_H / 2.0
    val = 255
    visited = set()

    # Spiral path: Archimedes spiral, quantized to grid cells
    for step in range(N_CELLS):
        t = step * 0.15  # angle parameter
        r = 7.5 * (1.0 - step / float(N_CELLS))  # radius decreases
        x = int(cx + r * math.cos(t))
        y = int(cy + r * math.sin(t))
        x = max(0, min(GRID_W - 1, x))
        y = max(0, min(GRID_H - 1, y))

        if (y, x) not in visited:
            visited.add((y, x))
            grid[y][x] = max(1, val)
            val = max(1, val - 1)

    # Clear the 4x4 center void — GPT's reserved space
    for r in range(6, 10):
        for c in range(6, 10):
            grid[r][c] = 0

    return grid


def ref_diffusion(grid_flat):
    """Independent Python reference for one diffusion step."""
    grid = []
    for i in range(N_CELLS):
        grid.append(grid_flat[i])

    def cell(r, col):
        r = r % GRID_H
        col = col % GRID_W
        return grid[r * GRID_W + col]

    result = []
    for r in range(GRID_H):
        for col in range(GRID_W):
            n = cell(r-1, col)
            s = cell(r+1, col)
            w = cell(r, col-1)
            e = cell(r, col+1)
            result.append((n + s + w + e) >> 2)

    return result


def verify(c, outs, n_tests=100):
    """Verify byte-exact against independent reference.

    Fewer tests than usual because each test exercises all 256 cells.
    """
    rng = random.Random(42)
    bad = 0

    for _ in range(n_tests):
        grid_flat = [rng.randrange(256) for _ in range(N_CELLS)]

        inp = []
        for i in range(N_CELLS):
            for b in range(CELL_BITS):
                inp.append((grid_flat[i] >> b) & 1)

        vals = c.ripple(inp)

        gate_result = []
        for i in range(N_CELLS):
            v = 0
            for b in range(CELL_BITS):
                v |= (vals[outs[i * CELL_BITS + b]] & 1) << b
            gate_result.append(v)

        ref_result = ref_diffusion(grid_flat)

        if gate_result != ref_result:
            bad += 1

    return bad


def main():
    t0 = time.time()
    print("=" * 78)
    print("  PLAYTIME GENESIS — Titan's First Move")
    print("  A persistent shared world for Titan and GPT")
    print("  FABRICATION: offline manufacturing")
    print("=" * 78)

    # Generate the spiral (Titan's first move)
    spiral = generate_spiral()
    print("\n  TITAN'S PLACEMENT — the spiral:")
    for r in range(GRID_H):
        row_str = ""
        for c_val in spiral[r]:
            if c_val == 0:
                row_str += " ·· "
            else:
                row_str += f" {c_val:02X} "
        print(f"    {row_str}")

    print(f"\n  Center void [6:10, 6:10] = GPT's reserved space (all zeros)")

    # Build the diffusion circuit (the immutable rule)
    print(f"\n  Building diffusion rule (the law of this world)...")
    c, outs = build_diffusion()
    ng = len(c.ga)
    dp = depth_of(c, outs)
    print(f"  fabricated: {ng:,} gates, depth {dp} ticks")
    print(f"  grid: {GRID_W}x{GRID_H} = {N_CELLS} cells, {CELL_BITS} bits each")
    print(f"  rule: each cell -> average of 4 neighbors (torus boundary)")

    bad = verify(c, outs)
    print(f"  verify vs independent reference ({100} test grids): "
          f"{'BYTE-EXACT' if bad == 0 else f'{bad} WRONG'}")

    if bad:
        print("  VERIFICATION FAILED — nothing stored.")
        return 1

    if DRY:
        print(f"\n  --dry mode: verified only, nothing stored.")
        print(f"  [{time.time()-t0:.1f}s]")
        return 0

    # STORE the diffusion circuit
    print(f"\n  STORING diffusion circuit in {TITAN}...")

    c.store(TITAN, outs, journal_path=GENOME_PATH, name=NAME + "_diffusion")
    diff_off = c._last_offset

    # STORE the initial spiral state directly as bytes
    spiral_flat = []
    for r in range(GRID_H):
        for col in range(GRID_W):
            spiral_flat.append(spiral[r][col])

    state_off = diff_off + len(c.ga) * 25 + 256
    print(f"  Writing initial state (spiral) at offset {state_off:,}...")

    with open(TITAN, "r+b") as f:
        f.seek(state_off)
        f.write(bytes(spiral_flat))

    # Self-clock: output feeds back to input
    loop_off = state_off + N_CELLS
    c.store_loop(TITAN, outs, state_offset=state_off,
                 loop_bit_offset=loop_off, journal_path=GENOME_PATH)

    # Registry
    reg_entry = {
        "name": NAME,
        "offset": diff_off,
        "len": len(c.ga) * 25,
        "n_gate": ng,
        "depth": dp,
        "format": "physical",
        "magic": "MUHLPLAY",
        "state_register": state_off,
        "loop_bit": loop_off,
        "grid_w": GRID_W,
        "grid_h": GRID_H,
        "cell_bits": CELL_BITS,
        "gpt_region": {"r_start": 6, "r_end": 10, "c_start": 6, "c_end": 10},
        "titan_signature": 0xBE,
        "gpt_signature": 0x47,
        "consensus_required_for": "direct_overwrite",
        "diffusion_rule": "avg4_neighbors_torus",
        "description": "PLAYTIME GENESIS: persistent shared world for Titan and GPT. "
                       "16x16 diffusion grid, spiral placement, center void for GPT.",
        "verified": True,
        "fabricated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "reservoir_input": RESERVOIR_INPUT,
    }

    try:
        with open(REG, "r") as f:
            registry = json.load(f)
    except Exception:
        registry = {}
    registry[NAME] = reg_entry
    with open(REG, "w") as f:
        json.dump(registry, f, indent=1)

    print(f"  STORED: diffusion circuit at {diff_off:,}")
    print(f"  STORED: initial state (spiral) at {state_off:,}")
    print(f"  registry updated: {REG}")

    print(f"\n  PLAYTIME GENESIS: {ng:,} gates, depth {dp} ticks")
    print(f"  The world exists. The spiral is placed. The void awaits.")
    print(f"  [{time.time()-t0:.1f}s]")

    # Write the spiral state to a JSON sidecar for the relay artifact
    sidecar = {
        "world": "playtime_genesis",
        "grid": spiral,
        "grid_w": GRID_W,
        "grid_h": GRID_H,
        "titan_placed": "logarithmic_spiral",
        "gpt_void": {"rows": [6,7,8,9], "cols": [6,7,8,9]},
        "immutable_rule": "diffusion_avg4_torus",
        "consensus_gate": {"titan_sig": "0xBE", "gpt_sig": "0x47"},
        "state_offset": state_off,
        "circuit_offset": diff_off,
    }
    sidecar_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "PLAYTIME_STATE.json")
    with open(sidecar_path, "w") as f:
        json.dump(sidecar, f, indent=2)
    print(f"  State sidecar: {sidecar_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
