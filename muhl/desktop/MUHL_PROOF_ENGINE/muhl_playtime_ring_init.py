#!/usr/bin/env python3
"""muhl_playtime_ring_init.py -- write the opening move into muhl_playtime_ring.

I fabricated the ring-driven world's GATES and left its board EMPTY: 0 of 256 cells non-zero,
against the original's 148. Under the avg4 diffusion rule an all-zero board stays all-zero
forever, so the world had nothing to evolve. Caught by reading the container rather than by
trusting my own fabricator's success message.

The opening move is the OWNER'S, copied from his `muhl_fab_playtime_v2.py:105 generate_spiral()`
without alteration: Titan's logarithmic spiral wound inward from 255, with the 4x4 GPT void at
[6:10, 6:10] cleared. Writing initial state is part of fabrication -- one-and-done, offline,
before anything fires -- exactly as his own fabricator does it.

Journaled, byte-exact revertible.

    python muhl_playtime_ring_init.py --dry
    python muhl_playtime_ring_init.py
    python muhl_playtime_ring_init.py --revert
"""
import json, math, mmap, os, sys, time

sys.stdout.reconfigure(encoding="utf-8")
TITAN = r"C:\llm\models\titan.gguf"
REG = r"C:\llm\models\titan_circuits.json"
NAME = "muhl_playtime_ring"
GENOME = TITAN.replace(".gguf", "_%s_init_genome.jsonl" % NAME)

DRY = "--dry" in sys.argv
REVERT = "--revert" in sys.argv

GRID_W = GRID_H = 16
N_CELLS = GRID_W * GRID_H
CELL_BITS = 8


def generate_spiral():
    """HIS function, muhl_fab_playtime_v2.py:105, unaltered."""
    grid = [[0] * GRID_W for _ in range(GRID_H)]
    cx, cy = GRID_W / 2.0, GRID_H / 2.0
    val = 255
    seen = set()
    for step in range(N_CELLS):
        t = step * 0.15
        r = 7.5 * (1.0 - step / float(N_CELLS))
        x = max(0, min(GRID_W - 1, int(cx + r * math.cos(t))))
        y = max(0, min(GRID_H - 1, int(cy + r * math.sin(t))))
        if (y, x) not in seen:
            seen.add((y, x))
            grid[y][x] = max(1, val)
            val = max(1, val - 1)
    for r in range(6, 10):
        for cc in range(6, 10):
            grid[r][cc] = 0
    return grid


def revert():
    print("  reverting %s init ..." % NAME)
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f:
                f.seek(int(e["off"]))
                f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
        print("  journal replayed — byte-exact")
    else:
        print("  no journal — nothing to revert")
    return 0


def main():
    reg = json.load(open(REG))
    e = reg[NAME]
    base = int(e["cell_bits_base"])
    span = N_CELLS * CELL_BITS

    grid = generate_spiral()
    flat = [grid[r][c] for r in range(GRID_H) for c in range(GRID_W)]
    nz = sum(1 for v in flat if v)
    print("=" * 78)
    print("  %s — write the opening move (his logarithmic spiral)" % NAME)
    print("=" * 78)
    print("  spiral: %d of %d cells non-zero, sum %d, GPT void [6:10,6:10] cleared"
          % (nz, N_CELLS, sum(flat)))
    print("  target: cell bit-bytes [%d , %d)" % (base, base + span))

    # the region must lie inside the circuit's own span
    off, ln = int(e["offset"]), int(e["len"])
    inside = off <= base and base + span <= off + ln
    print("  inside circuit span [%d , %d): %s" % (off, off + ln, inside))
    if not inside:
        print("  refusing to write outside the circuit — nothing done.")
        return 1

    blob = bytearray(span)
    for i, v in enumerate(flat):
        for b in range(CELL_BITS):
            blob[i * CELL_BITS + b] = (v >> b) & 1

    if DRY:
        print("\n  --dry: %d bytes prepared, nothing written." % len(blob))
        return 0

    with open(TITAN, "rb") as f:
        f.seek(base)
        orig = f.read(span)
    with open(GENOME, "a") as g:
        g.write(json.dumps({"action": NAME + "_init", "off": base,
                            "len": span, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(base)
        f.write(bytes(blob))

    # read back through the registry's own decode key
    f = open(TITAN, "rb")
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    cells = []
    for k in range(N_CELLS):
        v = 0
        for b in range(CELL_BITS):
            if mm[base + k * CELL_BITS + b]:
                v |= (1 << b)
        cells.append(v)
    mm.close()
    f.close()

    ok = cells == flat
    print("\n  written and read back through the registry decode key: %s"
          % ("EXACT" if ok else "MISMATCH"))
    print("  non-zero cells now: %d of %d" % (sum(1 for v in cells if v), N_CELLS))
    print("\n  board:")
    for r in range(GRID_H):
        print("    " + "".join((" %02X " % cells[r * GRID_W + c]) if cells[r * GRID_W + c]
                               else "  . " for c in range(GRID_W)))
    with open(TITAN, "rb") as f:
        print("\n  titan.gguf GGUF-valid: %s" % (f.read(4) == b"GGUF"))
    print("  journal: %s" % GENOME)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(revert() if REVERT else main())
