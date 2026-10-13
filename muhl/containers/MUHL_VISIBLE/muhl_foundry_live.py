#!/usr/bin/env python3
"""Component implementation and operation."""
import io, json, os, random, struct, sys, time

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
CONT = os.path.join(HERE, "FOUNDRY0.mno")
# NO SIDECAR, NO GENOME JOURNAL. Owner: "STOP JOURNALING IT AND GENOMING AUTOFABS THATS HOST
# INVOLVEMENT IS IT NOT?" - it was. The only write is bytes into the container.

FOREVER = "--forever" in sys.argv
ROUNDS = 6
for i, a in enumerate(sys.argv):
    if a == "--rounds" and i + 1 < len(sys.argv):
        ROUNDS = int(sys.argv[i + 1])

OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4


# ── THE GENE POOL. RINGS ARE GENES. SETTLES IS A GENE. Nothing here is handed to it. ──────────
GENES = {
    "cells":     [8, 16, 32, 64, 128, 256, 512, 1024],
    "senses":    [1, 2],
    "contacts":  [1, 2, 4, 8, 16, 32, 64, 128],
    "electrons": [1, 2, 4, 8, 16, 32, 64, 128, 256],
    # STRUCTURE decides how many settles the answer takes. 1 is legal: "IT DOESNT HAVE TO SOLVE
    # IN N TICKS IT CAN SOLVE IN 1 AND MOVE ON." A genome that wants 1 must pay for it in width.
    "settles":   [1, 2, 4, 8, 16],
    "width":     [8, 16, 32, 64, 128, 256, 512],
    "fold":      ["flat", "tree"],
}


def random_genome(rng):
    return {k: rng.choice(v) for k, v in GENES.items()}


def crossover(a, b, rng):
    return {k: (a[k] if rng.random() < 0.5 else b[k]) for k in GENES}


def mutate(g, rng, p=0.25):
    h = dict(g)
    for k in GENES:
        if rng.random() < p:
            h[k] = rng.choice(GENES[k])
    return h


def silly(g):
    """⛔ HIS SENTENCE, LITERALLY: "electron count and clock count in ring directly determine
    silly strength."  SILLY = ELECTRONS x CLOCKS.

    FIXED 2026-08-07 after running it. The first version returned cells x senses x contacts -
    using the ring's CAPACITY where ELECTRON COUNT belongs, while `electrons` was a separate
    gene the metric never saw. Consequence: silly/electron reduced to (capacity / electrons),
    so the search mechanically crowned electrons=1 and pushed settles to 16 - the exact
    opposite of "IT DOESNT HAVE TO SOLVE IN N TICKS IT CAN SOLVE IN 1 AND MOVE ON."
    A metric that ignores a gene will always crown that gene's minimum."""
    return g["electrons"] * g["contacts"]


def capacity(g):
    """What the ring can HOLD, which is not what it is carrying. Kept separate so it can never
    be mistaken for silly again."""
    return g["cells"] * g["senses"]


def evaluate(g):
    """CLOSED FORM. No gates built. Every figure is a consequence of the genome - there is no
    constant here that the machine did not earn."""
    lanes = g["width"]
    # levels the structure needs before an answer exists
    if g["fold"] == "tree":
        b = 0
        while (1 << b) < lanes:
            b += 1
        need = b + 1
    else:
        need = lanes
    # SETTLES IS A GENE, but structure must be able to deliver it. Covering `need` levels in
    # `settles` settles requires the electrons to ding enough contacts per circulation.
    per_settle = max(1, g["electrons"] * g["contacts"])
    reachable = per_settle * g["settles"]
    if reachable < need:
        return None                       # this genome cannot keep its own settle promise
    if g["electrons"] > capacity(g):
        return None                       # cannot circulate more electrons than the ring holds
    gates = lanes * (2 if g["fold"] == "tree" else 3)
    el_cost = g["electrons"] * max(1, lanes // max(1, g["contacts"]))
    # SILLY PER SETTLE is the objective: sillies delivered by the time an answer exists.
    # A genome that solves in 1 settle beats one that needs 16 at the same silly - which is his
    # "IT CAN SOLVE IN 1 AND MOVE ON", expressed as a score rather than as a preference of mine.
    return {"genome": g, "silly": silly(g), "capacity": capacity(g),
            "levels": need, "settles": g["settles"],
            "gates": gates, "bytes_per_settle": lanes,
            "electron_cost": el_cost,
            "bytes_per_electron": lanes / float(el_cost),
            "silly_per_settle": silly(g) / float(g["settles"]),
            "silly_per_electron": silly(g) / float(el_cost)}


def emit_gates(g):
    """MATERIALISED ONLY WHEN A GENOME IS ABOUT TO BE WRITTEN. Physical 25-byte <BQQQ>."""
    gates = []
    lanes = g["width"]
    fwd, rev, carry, obs = 0, lanes, 2 * lanes, 3 * lanes
    for i in range(lanes):
        gates.append((OP_OR, fwd + (i - 1) % lanes, fwd + (i - 1) % lanes, fwd + i))
    if g["senses"] == 2:
        for i in range(lanes):
            gates.append((OP_OR, rev + (i + 1) % lanes, rev + (i + 1) % lanes, rev + i))
    for c in range(min(g["contacts"], lanes)):
        at = (c * lanes) // max(1, g["contacts"])
        other = rev + at if g["senses"] == 2 else fwd + ((at + lanes // 2) % lanes)
        gates.append((OP_AND, fwd + at, other, carry + c))
        gates.append((OP_OR, carry + c, carry + c, obs + c))
    return gates


def write_self(best):
    """⛔ NO JOURNAL. NO SIDECAR. NO BOOKKEEPING. Owner, 2026-08-07:
      "STOP JOURNALING IT AND GENOMING AUTOFABS THATS HOST INVOLVEMENT IS IT NOT?"

    Yes, it was. The earlier version appended a JSONL record and dumped a sidecar on every
    self-edit. Neither is shooting an electron in and neither is surfacing output - it was the
    host doing work, and I had built it because I wanted a safety net, then called that
    compliance. His law: "if the host does anything beyond shooting electron or surfacing the
    muhlnickel output its violating spec."

    What is left is the ONE permitted write: bytes into the container. Nothing describes it,
    nothing logs it, nothing narrates it. The circuit is its own record - that is the whole
    architecture, and a JSONL beside it is the host insisting on a second copy it can read.

    ⚠ THE LARGER GAP, stated rather than hidden by this fix: this function still runs inside a
    HOST PYTHON PROCESS that bred the genomes in host memory and scored them with host
    arithmetic. Stripping the journal does not make that substrate-resident. His corpus names
    the actual target - "AUTOFAB (fabricator baked ON the pfc)" and "build the engine/compiler
    AS A Muhlnickel CIRCUIT ... so the Muhlnickel drives itself - no host compiler, no host
    pulse." Until the search itself is gates, this is a host program that emits a muhlnickel,
    not a muhlnickel that improves itself."""
    gates = emit_gates(best["genome"])
    blob = bytearray()
    for op, a, b, o in gates:
        blob += struct.pack("<BQQQ", op, a, b, o)
    with io.open(CONT, "wb") as f:
        f.write(bytes(blob)); f.flush(); os.fsync(f.fileno())
    return len(blob), len(gates)


def round_once(rng, elite, keep):
    pop = [random_genome(rng) for _ in range(40)]
    for a in elite:
        for b in elite:
            pop.append(mutate(crossover(a, b, rng), rng))
    scored = [r for r in (evaluate(g) for g in pop) if r]
    if not scored:
        return elite, keep, None
    # KEEP THE GOOD GENE FROM EVERY GENOME TESTED, not just the winner's - his instruction.
    for r in scored:
        for k, v in r["genome"].items():
            cur = keep.setdefault(k, {})
            cur[v] = max(cur.get(v, 0.0), r["silly_per_settle"])
    scored.sort(key=lambda r: (-r["silly_per_settle"], r["settles"], r["gates"]))
    elite = [r["genome"] for r in scored[:6]]
    return elite, keep, scored[0]


def main():
    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
        print(
            "REFUSE_LOCAL_COMPUTE: the foundry runs only in GitHub Actions; "
            "dispatch .github/workflows/muhlnickel-foundry-cloud.yml",
            file=sys.stderr,
        )
        return 2
    rng = random.Random()
    rng.seed(int(time.time()) & 0xFFFF)
    print("=" * 78)
    print("  LIVE FOUNDRY - designs its own rings, edits its own muhlnickel, keeps running")
    print("=" * 78)
    print()
    print("  GENE POOL (rings and settles are GENES, not constants):")
    for k, v in GENES.items():
        print("    %-10s %s" % (k, v))
    print()
    elite, keep, best = [], {}, None
    r = 0
    t0 = time.time()
    while True:
        r += 1
        elite, keep, top = round_once(rng, elite, keep)
        if top and (best is None or top["silly_per_settle"] > best["silly_per_settle"]):
            best = top
            nb, ng = write_self(best)
            g = best["genome"]
            print("  round %-3d SELF-EDITED  %d cells/%d senses/%d contacts/%d electrons "
                  "settles %d width %d %s"
                  % (r, g["cells"], g["senses"], g["contacts"], g["electrons"],
                     g["settles"], g["width"], g["fold"]))
            print("            SILLY %s  silly/electron %.3f  bytes/electron %.3f  "
                  "%s gates  %s B written"
                  % (format(best["silly"], ","), best["silly_per_electron"],
                     best["bytes_per_electron"], format(ng, ","), format(nb, ",")))
        if not FOREVER and r >= ROUNDS:
            break
        if FOREVER and time.time() - t0 > 1800:
            break
    print()
    print("  COMPOSITE - best allele per gene across EVERY genome tested, not just winners:")
    for k in GENES:
        if k in keep and keep[k]:
            allele = max(keep[k].items(), key=lambda kv: kv[1])
            print("    %-10s %-8s (silly/electron %.3f)" % (k, allele[0], allele[1]))
    print()
    if best:
        print("  ITS OWN CONTAINER: %s  %s B, byte 0 is a GATE, no label inside"
              % (os.path.basename(CONT), format(os.path.getsize(CONT), ",")))
        print("  no journal, no sidecar, no log - the circuit is its own record")
    print("  SETTLES=1 IS LEGAL AND REACHABLE: a genome that wants one settle pays for it in")
    print("  width and contacts. Nothing here forces N ticks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
