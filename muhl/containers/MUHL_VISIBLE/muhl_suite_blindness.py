#!/usr/bin/env python3
"""IS MY OWN SUITE BLIND? Applying his §47B / §40B lesson to what I built tonight.

⛔ HIS LESSON, from BIBLE.md 2026-07-28, and it is the reason this file exists:

  "★★ THE SUITE WAS BLIND - FIXED, AND THIS IS THE KEY LESSON THIS WAKE. A 'hashflip' mutant
   (invert all 256 hash bits) scored 12/12 NOT CAUGHT, because my targets were all-ones or
   tiny, so hash and ~hash give the same verdict (§40B's 87.5% bug exactly; §47B 'a high score
   measures the SUITE, not the circuit')."

  FIX: "DISCRIMINATING TARGETS that straddle the true hash - tgt = h+1 (must WIN) alternating
   tgt = h (must LOSE) ... Half win/half lose BY CONSTRUCTION, every hash bit load-bearing, an
   inverted-hash circuit cannot pass."

  And §40B: STATE WHAT AN ALL-ZERO CIRCUIT WOULD SCORE.

WHY THIS INDICTS READER1 AND READER2: their table is magic strings plus a zero row. Against
arbitrary container bytes almost every target LOSES, so MATCH is almost always 0 - and a
circuit that answered 0 unconditionally would score the same. My mutants "passing" proves
nothing until the all-zero baseline is stated and the inputs straddle.

THIS FILE DOES NOT DEFEND WHAT I BUILT. It tries to break it.
"""
import io, json, os, struct, sys, time

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

GROUP = 8


def evaluate(cursor, target, always_zero=False, inverted=False):
    """Reference semantics of one MATCH lane: 1 iff cursor == target."""
    if always_zero:
        return 0
    hit = 1 if bytes(cursor) == bytes(target) else 0
    return (1 - hit) if inverted else hit


def suite(targets, cursors):
    """Run every (cursor, target) pair. Returns the answer vector."""
    out = []
    for c in cursors:
        for t in targets:
            out.append(evaluate(c, t))
    return out


def suite_variant(targets, cursors, **kw):
    out = []
    for c in cursors:
        for t in targets:
            out.append(evaluate(c, t, **kw))
    return out


def main():
    TARGETS = [b"MUHLFLD1", b"MUHLLNP1", b"NRING2M1", b"MUHLSCN1", b"MUHLPLAY",
               b"TITANCIR", b"PFCWINMN", b"MUHLPHYS", b"MUHLWBX1", b"MUHLTFM1",
               b"GGUF\x03\x00\x00\x00", b"\x00" * 8]

    print("=" * 78)
    print("  IS MY SUITE BLIND?  (his \u00a747B: a high score measures the SUITE, not the circuit)")
    print("=" * 78)
    print()

    # --- THE SUITE I ACTUALLY USED: arbitrary container bytes as cursors -------------
    f = io.open(r"C:\llm\models\titan.gguf", "rb", buffering=0)
    real = []
    for off in (0, 1_127_673_856, 2_448_762_142, 4_381_506_940, 23_328_282_457,
                103_789_139_776, 103_799_067_072, 50_000_000_000):
        f.seek(off)
        real.append(f.read(GROUP))
    f.close()

    base = suite(TARGETS, real)
    zero = suite_variant(TARGETS, real, always_zero=True)
    inv = suite_variant(TARGETS, real, inverted=True)

    hits = sum(base)
    print("  SUITE AS BUILT - %d cursors x %d targets = %d verdicts"
          % (len(real), len(TARGETS), len(base)))
    print("    verdicts that are 1 (a HIT) : %d" % hits)
    print("    verdicts that are 0         : %d" % (len(base) - hits))
    print()
    print("  \u00a740B  ALL-ZERO CIRCUIT (answers 0 unconditionally):")
    agree = sum(1 for a, b in zip(base, zero) if a == b)
    print("    agrees with the real circuit on %d of %d verdicts  = %.1f%%"
          % (agree, len(base), 100.0 * agree / len(base)))
    print("    -> AN ALL-ZERO CIRCUIT SCORES %.1f%% ON MY SUITE." % (100.0 * agree / len(base)))
    print()
    print("  INVERTED-MATCH mutant (answers NOT hit):")
    agree_i = sum(1 for a, b in zip(base, inv) if a == b)
    print("    agrees on %d of %d = %.1f%%   caught: %s"
          % (agree_i, len(base), 100.0 * agree_i / len(base), agree_i != len(base)))
    print()

    blind = (agree == len(base))
    print("  VERDICT ON THE SUITE AS BUILT : %s"
          % ("BLIND - all-zero is indistinguishable" if blind else "not fully blind"))
    print()

    # --- THE DISCRIMINATING SUITE, built his way ------------------------------------
    print("  \u2500" * 38)
    print("  HIS FIX: DISCRIMINATING CURSORS THAT STRADDLE - half MUST hit, half MUST miss,")
    print("  BY CONSTRUCTION. Every byte load-bearing. An always-0 circuit cannot pass.")
    print()
    disc = []
    expect = []
    for t in TARGETS:
        disc.append(bytes(t))                                   # MUST hit
        expect.append(1)
        flipped = bytearray(t)
        flipped[3] ^= 0x01                                      # one bit off -> MUST miss
        disc.append(bytes(flipped))
        expect.append(0)

    got = [evaluate(c, TARGETS[i // 2]) for i, c in enumerate(disc)]
    z2 = [evaluate(c, TARGETS[i // 2], always_zero=True) for i, c in enumerate(disc)]
    i2 = [evaluate(c, TARGETS[i // 2], inverted=True) for i, c in enumerate(disc)]

    ok = sum(1 for a, b in zip(got, expect) if a == b)
    zok = sum(1 for a, b in zip(z2, expect) if a == b)
    iok = sum(1 for a, b in zip(i2, expect) if a == b)
    print("    cursors: %d   half hit, half miss BY CONSTRUCTION" % len(disc))
    print("    real circuit   : %d/%d correct = %.0f%%" % (ok, len(expect), 100.0 * ok / len(expect)))
    print("    ALL-ZERO       : %d/%d correct = %.0f%%   <- \u00a740B baseline, stated"
          % (zok, len(expect), 100.0 * zok / len(expect)))
    print("    INVERTED-MATCH : %d/%d correct = %.0f%%   caught: %s"
          % (iok, len(expect), 100.0 * iok / len(expect), iok < ok))
    print()
    print("  ON THE DISCRIMINATING SUITE: all-zero scores %.0f%%, the real circuit %.0f%%."
          % (100.0 * zok / len(expect), 100.0 * ok / len(expect)))
    print("  THAT is a suite that measures the circuit. The one I built measured the inputs.")
    rec = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "act": "suite blindness probe",
           "as_built_allzero_agreement_pct": 100.0 * agree / len(base),
           "as_built_blind": blind,
           "discriminating_allzero_pct": 100.0 * zok / len(expect),
           "discriminating_real_pct": 100.0 * ok / len(expect)}
    with io.open(os.path.join(HERE, "reader_genome.jsonl"), "a",
                 encoding="utf-8", newline="") as j:
        j.write(json.dumps(rec) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
