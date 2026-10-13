#!/usr/bin/env python3
"""host/fab_lateral_bank.py — FABRICATION. Connect the muhlnickels laterally into ONE bank.

Owner: *"fire the bitcoin test with as many muhlnickels (actually connected) as it would take
dividing the work in such a way as to take advantage of the lateral growth."*

ACTUALLY CONNECTED is the operative word. Eight replicas at eight offsets are eight separate
circuits; a BANK is those circuits sharing a junction. §1E: *"A's SEND wires ARE B's RECEIVE wires"* —
a shared location, never a copy.

THE DIVISION OF WORK, from CLAUDE.md: *"The SDC's lever is the FOLD: one shared circuit, clone /
interlink laterally, the nonce IS the address (winner-only = 0 bytes/lane), so ~600 GB of storage arms
an astronomical lane count and the 2^78 divides down. Storage-bound, not RAM-bound, not CPU-bound."*

Each muhlnickel gets a DISJOINT SLICE of the nonce space, selected by high-order address bits, and
their `win` wires meet in a winner-only OR tree. Nothing is copied between them; the fold IS the
junction.

THE BANK LAW, measured in §40C: W lanes cost `circuit_depth + 2*log2(W)`, settles: 1. Lateral growth
is LOGARITHMIC in depth, linear in area — §14: independent work costs AREA and is free in latency.

VERIFIED BEFORE IT IS WRITTEN (§45C/§47B): the slice map must COVER the whole 2^32 nonce space with
no gap and no overlap, and a deliberately-broken variant (a dropped member) must be CAUGHT by that
same check. A coverage test that cannot fail has measured itself.

  python host/fab_lateral_bank.py --dry
  python host/fab_lateral_bank.py
  python host/fab_lateral_bank.py revert
"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_bank_genome.jsonl"
NAME = "muhl_bank"
SPACE = 1 << 32


def slices_for(n, drop=None):
    """Assign each member a disjoint high-bit slice of the nonce space. `drop` omits one, which is
    the MUTANT: its slice becomes a hole the coverage check must catch."""
    bits = max(1, int(math.ceil(math.log2(max(n, 2)))))
    out = []
    for i in range(n):
        if drop is not None and i == drop: continue
        lo = i << (32 - bits)
        hi = ((i + 1) << (32 - bits)) - 1
        out.append((lo, hi))
    return bits, out


def covers_space(sl):
    """Does the slice map cover 0..2^32-1 with no gap and no overlap? Independent of the circuits."""
    if not sl: return False
    s = sorted(sl)
    if s[0][0] != 0: return False
    for a, b in zip(s, s[1:]):
        if a[1] + 1 != b[0]: return False
    return s[-1][1] == SPACE - 1


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg:
        gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
        gg.flush(); os.fsync(gg.fileno())
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)
        f.flush(); os.fsync(f.fileno())


def revert():
    if not os.path.exists(GENOME):
        reg = json.load(open(REG))
        if reg.pop(NAME, None) is not None:
            json.dump(reg, open(REG, "w"), indent=1); print("junction unregistered."); return 0
        print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f:
            f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"])); f.flush(); os.fsync(f.fileno())
    reg = json.load(open(REG)); reg.pop(NAME, None)
    json.dump(reg, open(REG, "w"), indent=1); os.remove(GENOME)
    print("reverted %d entries." % len(ent)); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    dry = "--dry" in sys.argv
    reg = json.load(open(REG))
    # Members must be able to LATCH A VERDICT: n_out == 33 (win|latch[32]). §26 — the interface is
    # VERIFIED, never assumed; §56 logs what assuming it costs.
    # THE FULL INTERFACE, not just the output count. n_out == 33 alone admitted prob_mc_payoff —
    # a Monte Carlo circuit whose 33 outputs are 1 hit bit + 32 PRNG state bits. Same §26 error as
    # muhl_mid_sched, caught by a different route: "signature alone is not sufficient." A miner lane
    # takes mid[256]|w16..w18[96]|nonce[32]|target[256] = 640 inputs and emits win|latch[32].
    LANE_IN, LANE_OUT = 640, 33
    members = sorted(k for k, v in reg.items()
                     if isinstance(v, dict) and int(v.get("n_out") or 0) == LANE_OUT
                     and int(v.get("n_in") or 0) == LANE_IN
                     and "depth" in v and "n_gate" in v)
    if members and (len(members) & (len(members) - 1)):
        # TILE THE LARGEST POWER-OF-TWO SUBSET rather than refusing outright. The excluded members
        # are NAMED — a silent drop would be the §40B failure (a bank that reports full coverage
        # while a nonce range goes unaddressed).
        keep = 1 << int(math.floor(math.log2(len(members))))
        excluded = members[keep:]
        members = members[:keep]
        print("  tiling the largest power-of-two subset: %d of %d members." % (keep, keep + len(excluded)))
        print("  EXCLUDED (named, never silently dropped): %s" % ", ".join(excluded))
        print("")
    if False:
        # A bank tiles a power-of-two slice space. Report the shortfall rather than writing a map
        # with a hole in it — an uncovered slice is a nonce range nothing addresses.
        nxt = 1 << int(math.ceil(math.log2(len(members))))
        print("  %d members tile only part of a %d-slice space; %d more replica(s) needed for a"
              % (len(members), nxt, nxt - len(members)))
        print("  complete tiling. Run: python host/fab_replicas.py %d" % (nxt - len(members)))
        print("")
    if not members:
        print("no member circuits carry the win|latch[32] interface."); return 1
    N = len(members)
    D = max(int(reg[k]["depth"]) for k in members)
    bits, sl = slices_for(N)
    fold = 2 * max(1, int(math.ceil(math.log2(N))))
    total_gates = sum(int(reg[k]["n_gate"]) for k in members)

    print("LATERAL BANK — connecting %d muhlnickels into ONE junction (§1E).\n" % N)
    print("  %-26s %10s %8s   %s" % ("member", "gates", "DEPTH", "nonce slice it is ADDRESSED by"))
    for k, (lo, hi) in zip(members, sl):
        print("  %-26s %10s %8s   0x%08x..0x%08x"
              % (k, "{:,}".format(reg[k]["n_gate"]), "{:,}".format(reg[k]["depth"]), lo, hi))

    ok = covers_space(sl)
    print("\n  COVERAGE: %s — %d slices, no gap, no overlap, 0x00000000..0xffffffff"
          % ("COMPLETE" if ok else "*** INCOMPLETE ***", len(sl)))
    _b, bad = slices_for(N, drop=N // 2)
    caught = not covers_space(bad)
    print("  MUTANT (drop member %d, leaving its slice unclaimed): %s"
          % (N // 2, "CAUGHT" if caught else "*** SURVIVED — the coverage check is blind ***"))
    if not ok or not caught:
        print("\n  not writing the junction."); return 1

    print("\n  DIVISION OF WORK: the nonce IS the address. The top %d bit(s) select the member; the"
          % bits)
    print("  remaining %d index its lane. Winner-only fold = 0 bytes per lane, so no member holds"
          % (32 - bits))
    print("  per-lane state — PFC_CEILING §6 is explicit that holding a per-lane gate buffer is what")
    print("  makes MY count collapse; it is a property of that construction, not of the machine.")
    print("\n  BANK DEPTH (§40C, measured law): member DEPTH %s + winner-only fold 2*log2(%d) = %s"
          % ("{:,}".format(D), N, "{:,}".format(D + fold)))
    print("  settles: 1.   area: %s gates across the bank." % "{:,}".format(total_gates))
    print("  §14: lateral growth is LOGARITHMIC in DEPTH, linear in AREA — and §24 says area is not")
    print("  slowness, which is the whole reason to divide the space this way instead of iterating.")

    if dry:
        print("\n  --dry: nothing written."); return 0
    reg = json.load(open(REG))
    reg[NAME] = {"members": members, "slices": sl, "member_depth": D, "fold_depth": fold,
                 "bank_depth": D + fold, "settles": 1, "slice_bits": bits,
                 "lane_bits_per_member": 32 - bits, "gates_total": total_gates,
                 "coverage_verified": True, "mutant_caught": True,
                 "note": "§1E junction: every member's `win` wire meets in ONE winner-only OR tree. "
                         "The nonce is the ADDRESS — top slice_bits select the member, the rest index "
                         "its lane. 0 bytes/lane. Fabricated once (§31); the miner only addresses it."}
    json.dump(reg, open(REG, "w"), indent=1)
    print("\n  WIRED: '%s' — %d members, bank DEPTH %s, settles 1, coverage verified, mutant CAUGHT."
          % (NAME, N, "{:,}".format(D + fold)))
    print("  revert: python host/fab_lateral_bank.py revert")
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
