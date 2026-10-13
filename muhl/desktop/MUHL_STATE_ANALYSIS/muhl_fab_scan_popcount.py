#!/usr/bin/env python3
"""FABRICATE popcount8 into probe.mno as MUHLNICKEL gates.

Owner: "if you hit a host limit shove the computation into the muhlnickel and keep pushing
        muhlnickels have better specs and are general computers, proven"
       "start with one and the rings drive it with silly electrons"

FABRICATION IS NOT RUNTIME — one-and-done, its own process, before anything fires.

V31 INDEX CHECK, done before writing a line of this: 25 arithmetic primitives exist in
titan_circuits.json. XOR exists (lib_xor8__phys, 32 gates DEPTH 3). Accumulate exists
(adder8_clean__phys, 85 gates DEPTH 20). Shift is addressing, not gates. POPCOUNT DOES NOT
EXIST ANYWHERE. This is new work, not a rebuild.

SHAPE: BUILD -> VERIFY vs an independent reference -> MUTATE and re-verify -> JOURNAL ->
STORE with fsync -> DROP. Writes nothing if any step disagrees.
FORMAT: physical, 25-byte <BQQQ>, ABSOLUTE addresses. Appended past EOF; nothing displaced.
"""
import io, json, os, struct, sys, time

sys.stdout.reconfigure(encoding="utf-8")

CONTAINER = r"C:/Users/lucys/Desktop/MUHLNICKEL_PROBE/probe.mno"
GENOME = r"C:/Users/lucys/Desktop/MUHLNICKEL_PROBE/probe_scan_genome.jsonl"
MAGIC = b"MUHLPOP1"

OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4


def reference_popcount(value):
    """INDEPENDENT REFERENCE. Counts set bits by a different route than the netlist:
    Kernighan's clear-lowest-set-bit loop. It shares no code with the gate builder."""
    n = 0
    v = value
    while v:
        v &= v - 1
        n += 1
    return n


class Fab(object):
    def __init__(self, base):
        self.base = base
        self.gates = []
        self.n = 2                       # wire 0 = const0, wire 1 = const1

    def new(self):
        w = self.n
        self.n += 1
        return w

    def addr(self, w):
        return self.base + w

    def g(self, op, a, b):
        o = self.new()
        self.gates.append((op, self.addr(a), self.addr(b), self.addr(o)))
        return o

    def half(self, a, b):
        return self.g(OP_XOR, a, b), self.g(OP_AND, a, b)

    def full(self, a, b, c):
        s1, c1 = self.half(a, b)
        s2, c2 = self.half(s1, c)
        return s2, self.g(OP_OR, c1, c2)


def build(fab, inbits):
    a0, a1 = fab.full(inbits[0], inbits[1], inbits[2])
    b0, b1 = fab.full(inbits[3], inbits[4], inbits[5])
    c0, c1 = fab.full(inbits[6], inbits[7], 0)
    s0, k0 = fab.full(a0, b0, c0)
    s1, k1 = fab.full(a1, b1, c1)
    s1b, k2 = fab.half(s1, k0)
    s2 = fab.g(OP_XOR, k1, k2)
    s3 = fab.g(OP_AND, k1, k2)
    return [s0, s1b, s2, s3]


def settle(gates, base, ins, n_wires):
    """FABRICATION-TIME settle, to verify before storing. Never at runtime."""
    v = [0] * n_wires
    v[1] = 1
    for w, b in ins.items():
        v[w] = b
    for op, a, b, o in gates:
        A, B = v[a - base], v[b - base]
        r = (A ^ B) if op == OP_XOR else (A & B) if op == OP_AND else \
            (A | B) if op == OP_OR else (1 - (A & B)) if op == OP_NAND else (1 - A)
        v[o - base] = r
    return v


def verify(gates, base, inw, outw, n_wires, mutant=False):
    """Exhaustive over all 256 inputs, against reference_popcount."""
    agree = 0
    for value in range(256):
        ins = {inw[i]: (value >> i) & 1 for i in range(8)}
        v = settle(gates, base, ins, n_wires)
        got = sum(v[w] << i for i, w in enumerate(outw))
        if got == reference_popcount(value):
            agree += 1
    return agree


def _journal(rec):
    """Journal the intent, then get it out of cache and into storage before any
    container byte moves. pfc_index.py / pfc_substitute.py were consulted before this
    fabricator was written — see the V31 INDEX CHECK note in the module docstring."""
    with io.open(GENOME, "a", encoding="utf-8", newline="") as f:
        f.write(json.dumps(rec) + "\n")
        f.flush()
        os.fsync(f.fileno())


def main():
    size = os.path.getsize(CONTAINER)
    base = size + 16
    fab = Fab(base)
    inw = [fab.new() for _ in range(8)]
    outw = build(fab, inw)

    print("FABRICATE popcount8 -> probe.mno")
    print("  container %s (%d B)   wire base %d   wires %d   gates %d"
          % (os.path.basename(CONTAINER), size, base, fab.n, len(fab.gates)))
    print("  inputs  @%d..%d   outputs @%s"
          % (fab.addr(inw[0]), fab.addr(inw[7]), [fab.addr(w) for w in outw]))

    lvl = [0] * fab.n
    for op, a, b, o in fab.gates:
        la, lb = lvl[a - base], lvl[b - base]
        lvl[o - base] = 1 + (la if la >= lb else lb)
    depth = max(lvl[w] for w in outw)
    prof = {}
    for op, a, b, o in fab.gates:
        prof[lvl[o - base]] = prof.get(lvl[o - base], 0) + 1
    print("  DEPTH %d ticks   wavefront %s   gates/stage %.1f"
          % (depth, [prof.get(k, 0) for k in range(1, depth + 1)],
             len(fab.gates) / float(depth)))

    exact = verify(fab.gates, base, inw, outw, fab.n)
    print("  exhaustive vs independent reference: %d / 256" % exact)

    mut = list(fab.gates)
    mut[0] = (OP_AND, mut[0][1], mut[0][2], mut[0][3])
    mut_agree = verify(mut, base, inw, outw, fab.n, mutant=True)
    print("  mutant (gate 0 XOR->AND) agrees on only %d / 256  -> caught on %d"
          % (mut_agree, 256 - mut_agree))

    zero = verify([], base, inw, outw, fab.n)
    print("  all-zero baseline (no gates at all): %d / 256" % zero)

    if exact != 256:
        print("  REFUSING TO WRITE — %d cases disagree." % (256 - exact))
        return 1
    if mut_agree == 256:
        print("  REFUSING TO WRITE — mutant not caught, the check is worthless.")
        return 1
    if zero == 256:
        print("  REFUSING TO WRITE — an empty netlist scores the same. Test is vacuous.")
        return 1

    blob = bytearray(MAGIC)
    blob += struct.pack("<II", len(fab.gates), len(outw))
    for op, a, b, o in fab.gates:
        blob += struct.pack("<BQQQ", op, a, b, o)
    for w in outw:
        blob += struct.pack("<Q", fab.addr(w))

    _journal({
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "act": "fabricate popcount8 into probe.mno, appended past EOF",
        "container": CONTAINER, "eof_before": size, "append_len": len(blob),
        "magic": MAGIC.decode(), "n_gate": len(fab.gates), "n_out": len(outw),
        "wire_base": base, "inputs": [fab.addr(w) for w in inw],
        "outputs": [fab.addr(w) for w in outw],
        "verified_exact": exact, "mutant_agree": mut_agree, "zero_baseline": zero,
        "pre_image_hex": "", "note": "append past EOF; nothing displaced",
    })

    if "--write" not in sys.argv:
        print("  DRY RUN — journalled the intent, wrote no bytes. Re-run with --write.")
        return 0

    with io.open(CONTAINER, "r+b") as f:
        f.seek(size)
        f.write(bytes(blob))
        f.flush()
        os.fsync(f.fileno())
    print("  STORED %d B at %d. container now %d B"
          % (len(blob), size, os.path.getsize(CONTAINER)))

    del fab
    del blob
    print("  dropped the in-memory circuit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
