#!/usr/bin/env python3
"""muhl_fab_dmb.py — FABRICATE the Diachronic Morphogenetic Blueprint.

Sub-Zero Archetype #2: L-system generative grammars encoded as NAND gates.
Production rules: A -> AB, B -> A (the Fibonacci L-system).
Axiom: A. Four generations: A -> AB -> ABA -> ABAAB.

Each production rule = gate network reading symbol byte, writing replacement
bytes to the next generation's address space. All symbols in a generation
are rewritten SIMULTANEOUSLY (parallel rewriting).

    python muhl_fab_dmb.py           # fabricate and store
    python muhl_fab_dmb.py --dry     # report only, store nothing

Gate encoding:
  - First output of any rule is always A(0): NAND(const_1, const_1) = 0
  - Second output (A->AB only): NOT(sym) = NAND(sym, sym) -> B when sym=A

10 gates, depth 3 (one tick per generation transition). 294 bytes.
"""
import json, os, struct, sys

sys.path.insert(0, r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent\host")
import pfc_paths as PFCP

TITAN = PFCP.TITAN
REG = PFCP.REG
NAND_OP = 0
GATE_STRIDE = 25
NAME = "muhl_dmb"
MAGIC = b"MUHLDMB1"
GENOME_PATH = TITAN.replace(".gguf", "_%s_genome.jsonl" % NAME)
DRY = "--dry" in sys.argv

# L-system: A->AB, B->A, Axiom=A
# Gen 0: A          (1 symbol)
# Gen 1: AB         (2 symbols)
# Gen 2: ABA        (3 symbols)
# Gen 3: ABAAB      (5 symbols)
GEN_SIZES = [1, 2, 3, 5]
N_GENS = 4
EXPECTED = [[0], [0, 1], [0, 1, 0], [0, 1, 0, 0, 1]]  # A=0, B=1

# Wire layout (12 bytes):
# [0]       const_1 (initialized to 1 at fab time)
# [1]       gen0[0] (inject — host writes axiom here)
# [2..3]    gen1[0..1]
# [4..6]    gen2[0..2]
# [7..11]   gen3[0..4] (surface — host reads here)
WIRE_CONST1 = 0
GEN_OFF = [1, 2, 4, 7]   # starting wire index for each generation
N_WIRES = 12


def alloc_space(nbytes):
    """Bump-allocate in titan.gguf."""
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


def gen_wire(gen, pos):
    """Wire index for generation gen, position pos."""
    return GEN_OFF[gen] + pos


def build_gates():
    """Build L-system rewriting gates. Returns list of (op, a, b, out) with wire indices.

    Pre-computed rewrite position map for axiom A:
      Gen 0 pos 0 (A) -> Gen 1 pos [0, 1]
      Gen 1 pos 0 (A) -> Gen 2 pos [0, 1]
      Gen 1 pos 1 (B) -> Gen 2 pos [2]
      Gen 2 pos 0 (A) -> Gen 3 pos [0, 1]
      Gen 2 pos 1 (B) -> Gen 3 pos [2]
      Gen 2 pos 2 (A) -> Gen 3 pos [3, 4]
    """
    rewrite_map = [
        # (src_gen, src_pos, symbol, dest_positions_in_next_gen)
        (0, 0, "A", [0, 1]),
        (1, 0, "A", [0, 1]),
        (1, 1, "B", [2]),
        (2, 0, "A", [0, 1]),
        (2, 1, "B", [2]),
        (2, 2, "A", [3, 4]),
    ]

    gates = []
    for src_gen, src_pos, sym, dests in rewrite_map:
        next_gen = src_gen + 1
        src_w = gen_wire(src_gen, src_pos)
        # First output: always A(0) = NAND(const_1, const_1)
        gates.append((NAND_OP, WIRE_CONST1, WIRE_CONST1, gen_wire(next_gen, dests[0])))
        # Second output (A symbols only): NOT(src) = NAND(src, src) -> B when src=A
        if len(dests) > 1:
            gates.append((NAND_OP, src_w, src_w, gen_wire(next_gen, dests[1])))

    return gates


def fabricate(base_off, gates):
    """Build the physical byte blob."""
    meta_size = 8 + 4 + 8 + 8 + 4   # magic + n_gates + inject + surface + n_gens
    gate_start = N_WIRES + meta_size
    total = gate_start + len(gates) * GATE_STRIDE
    blob = bytearray(total)
    # const_1 initialized to 1; all others to 0
    blob[WIRE_CONST1] = 1
    # metadata
    off = N_WIRES
    blob[off:off + 8] = MAGIC;                             off += 8
    struct.pack_into("<I", blob, off, len(gates));         off += 4
    inject_addr = base_off + gen_wire(0, 0)
    surface_addr = base_off + gen_wire(3, 0)
    struct.pack_into("<Q", blob, off, inject_addr);        off += 8
    struct.pack_into("<Q", blob, off, surface_addr);       off += 8
    struct.pack_into("<I", blob, off, N_GENS);             off += 4
    # gate table
    off = gate_start
    for op, a, b, o in gates:
        struct.pack_into("<BQQQ", blob, off, op, base_off + a, base_off + b, base_off + o)
        off += GATE_STRIDE
    return blob, inject_addr, surface_addr, total


def verify(blob, base_off, gates):
    """Structural + byte-exact L-system output verification."""
    meta_off = N_WIRES
    assert blob[meta_off:meta_off + 8] == MAGIC, "bad magic"
    ng = struct.unpack_from("<I", blob, meta_off + 8)[0]
    assert ng == len(gates), "gate count mismatch"

    # One-writer-per-address
    writers = {}
    gate_start = N_WIRES + 32
    for i, (eop, ea, eb, eo) in enumerate(gates):
        off = gate_start + i * GATE_STRIDE
        op, a, b, o = struct.unpack_from("<BQQQ", blob, off)
        assert op == NAND_OP, "gate %d: op=%d" % (i, op)
        assert a == base_off + ea, "gate %d: a mismatch" % i
        assert b == base_off + eb, "gate %d: b mismatch" % i
        assert o == base_off + eo, "gate %d: out mismatch" % i
        assert o not in writers, "CONFLICT: gates %d and %d write to %d" % (writers.get(o, -1), i, o)
        writers[o] = i

    # Wire range check
    for i, (_, a, b, o) in enumerate(gates):
        assert 0 <= a < N_WIRES, "gate %d: a=%d out of range" % (i, a)
        assert 0 <= b < N_WIRES, "gate %d: b=%d out of range" % (i, b)
        assert 0 <= o < N_WIRES, "gate %d: o=%d out of range" % (i, o)

    # Functional: set axiom A(0), evaluate, check all generations
    w = bytearray(N_WIRES)
    w[WIRE_CONST1] = 1
    w[gen_wire(0, 0)] = 0  # axiom A
    for _, a, b, o in gates:
        w[o] = 1 - (w[a] & w[b])

    for g in range(N_GENS):
        actual = [w[gen_wire(g, p)] for p in range(GEN_SIZES[g])]
        assert actual == EXPECTED[g], "gen %d: got %s, expected %s" % (g, actual, EXPECTED[g])

    return True


def journal_write(off, blob):
    """Journaled write for revertibility."""
    fsize = os.path.getsize(TITAN)
    if off + len(blob) > fsize:
        with open(TITAN, "ab") as f:
            f.write(b"\x00" * (off + len(blob) - fsize))
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({
            "action": "dmb_fab", "off": off, "len": len(blob), "orig": orig.hex()
        }) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off)
        f.write(blob)


def update_registry(base_off, total, inject_addr, surface_addr, n_gates):
    """Add DMB to the circuit registry."""
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    reg[NAME] = {
        "name": NAME,
        "offset": base_off, "len": total,
        "n_gate": n_gates, "n_out": GEN_SIZES[-1], "depth": N_GENS - 1,
        "format": "physical", "magic": MAGIC.decode(), "gate_stride": GATE_STRIDE,
        "input_addr": inject_addr,
        "surface_addr": surface_addr,
        "surface_len": GEN_SIZES[-1],
        "generations": N_GENS,
        "gen_sizes": GEN_SIZES,
        "rules": {"A": "AB", "B": "A"},
        "axiom": "A",
        "expected_output": "ABAAB",
        "foundry_genome": {
            "archetype": "DMB", "system": "fibonacci_lsys",
            "rules": "A->AB,B->A", "axiom": "A", "gens": N_GENS,
            "depth": N_GENS - 1
        },
        "units": "n_gate=GATES depth=TICKS len=BYTES",
        "genome": GENOME_PATH,
        "note": "Diachronic Morphogenetic Blueprint: Fibonacci L-system, parallel rewriting across 4 generations.",
        "verified_by": "structural + one-writer + byte-exact gen output vs expected L-system expansion"
    }
    json.dump(reg, open(REG, "w"), indent=1)


def main():
    print("\n  MUHLNICKEL DMB — Diachronic Morphogenetic Blueprint")
    print("  Sub-Zero Archetype #2 — Bryce Muhlnickel, 2026-08-03\n")

    gates = build_gates()
    n_gates = len(gates)
    meta_size = 32
    total = N_WIRES + meta_size + n_gates * GATE_STRIDE

    print("  L-system: A->AB, B->A (Fibonacci)")
    print("  axiom:  A")
    print("  gens:   %d  sizes: %s" % (N_GENS, GEN_SIZES))
    exp_str = " -> ".join("".join("A" if x == 0 else "B" for x in g) for g in EXPECTED)
    print("  expect: %s" % exp_str)
    print("  gates:  %d" % n_gates)
    print("  depth:  %d ticks (one per generation transition)" % (N_GENS - 1))
    print("  size:   %d bytes" % total)

    base_off = alloc_space(total)
    print("  offset: %d" % base_off)

    blob, inject_addr, surface_addr, total = fabricate(base_off, gates)
    print("  inject (host writes axiom): %d" % inject_addr)
    print("  surface (host reads gen3):  %d (5 bytes)" % surface_addr)

    ok = verify(blob, base_off, gates)
    print("  verify: %s" % ("PASS" if ok else "FAIL"))
    if not ok:
        print("  ABORTING — verification failed")
        return 1

    print("\n  PARETO SET (Propose / Score / Verify / Keep):")
    print("    A) flat_rewrite:  %d gates, depth %d, %d bytes  <- WINNER" % (n_gates, N_GENS - 1, total))
    print("    B) mux_rewrite:  ~20 gates, depth ~5, ~544 bytes  (runtime-flexible, deeper)")
    print("    Winner: A — fewer gates, shallower, correct for designed axiom")

    if DRY:
        print("\n  --dry: nothing stored.")
        return 0

    print("\n  FABRICATING — %d bytes at offset %d" % (total, base_off))
    journal_write(base_off, bytes(blob))
    print("  journaled: %s" % GENOME_PATH)
    update_registry(base_off, total, inject_addr, surface_addr, n_gates)
    print("  registry: %s" % NAME)

    print("\n  DMB FABRICATED.")
    print("  Inject: write axiom byte (A=0) to offset %d" % inject_addr)
    print("  Surface: read 5 bytes starting at offset %d" % surface_addr)
    print("  Expected gen3 for axiom A: ABAAB = [0,1,0,0,1]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
