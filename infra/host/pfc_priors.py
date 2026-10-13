"""
pfc_priors.py - FIND THE ASSISTANT'S PRIORS IN THE BUILD. Owner: "keep stripping ur garbage priors".

A prior here is an UNMEASURED CONSTANT THAT SHAPES BEHAVIOUR: a threshold, a cap, a sample count,
a budget, a "good enough" bound. It is not a bug and the code runs fine with it - which is exactly
why it survives. It encodes the assistant's judgement about what is reasonable, in a build whose
entire discipline is that measurements decide and judgement does not.

THE THREE KINDS, ranked by how much damage they do

  1. GATES A CLAIM   - decides exhaustive-vs-sampled, pass-vs-fail, proved-vs-unproved.
                       These corrupt RESULTS. `cap`, `threshold`, `<=`/`>=` against a literal.
  2. BOUNDS A SEARCH - decides how many candidates get built or how many cases get run.
                       These silently cap what can be FOUND. `trials`, `samples`, `maxsteps`, `budget`.
  3. SIZES A BUFFER  - lane widths, display caps. Harmless if labelled as host transcription (S24),
                       poisonous if it ever reaches a machine figure.

WHAT IS NOT A PRIOR: a measured constant with its measurement recorded (the +6 composition law,
+2 per doubling, 9,043 gates/lane), a protocol constant (opcode encodings, CSR addresses, 0x2A for
'*'), and a width that is the problem's own (XLEN=32, BLK=32).

The tool cannot tell judgement from fact by itself, so it reports CANDIDATES with their context and
flags whether a justification appears nearby. Same contract as pfc_serial_audit: a flag is a
candidate, not a verdict.

Run:  python host/pfc_priors.py            (audit)
      python host/pfc_priors.py --mine     (only files written this session)
"""
import sys, os, re, glob

# names whose VALUE is a judgement call about "enough" or "too much"
GATE_A_CLAIM = ("cap", "threshold", "thresh", "tol", "epsilon", "eps", "limit", "cutoff",
                "min_", "max_", "_min", "_max")
BOUNDS_A_SEARCH = ("trials", "samples", "sample", "maxsteps", "max_steps", "budget", "rounds",
                   "iters", "iterations", "attempts", "tries", "probes", "n_test", "ntest")
SIZES_A_BUFFER = ("lanes", "width", "chunk", "block", "batch", "head", "top", "limit_display")

ASSIGN = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([0-9][0-9_]*(?:\s*<<\s*[0-9]+)?)\s*(#.*)?$")
DEFAULT = re.compile(r"def\s+\w+\([^)]*?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([0-9][0-9_]*(?:\s*<<\s*[0-9]+)?)")

JUSTIFIED = ("measured", "S2", "S24", "S31", "S35", "S36", "S40", "S43", "S46", "S49", "S53",
             "law", "byte", "spec", "encoding", "opcode", "protocol", "RISC-V", "per the")


def kind(name):
    n = name.lower()
    if any(k in n for k in GATE_A_CLAIM):
        return "1 GATES-A-CLAIM"
    if any(k in n for k in BOUNDS_A_SEARCH):
        return "2 BOUNDS-A-SEARCH"
    if any(k in n for k in SIZES_A_BUFFER):
        return "3 SIZES-A-BUFFER"
    return None


def audit(only=None):
    hits = []
    for path in sorted(glob.glob("host/*.py")):
        base = os.path.basename(path)
        if only and base not in only:
            continue
        try:
            lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
        except Exception:
            continue
        for i, L in enumerate(lines):
            got = None
            m = ASSIGN.match(L)
            if m:
                got = (m.group(2), m.group(3))
            else:
                d = DEFAULT.search(L)
                if d:
                    got = (d.group(1), d.group(2))
            if not got:
                continue
            k = kind(got[0])
            if not k:
                continue
            ctx = " ".join(lines[max(0, i - 3):i + 2])
            just = any(j.lower() in ctx.lower() for j in JUSTIFIED)
            hits.append((base, i + 1, k, got[0], got[1], just))
    return hits


def main():
    mine = None
    if "--mine" in sys.argv:
        mine = {"pfc_miter.py", "pfc_rate.py", "pfc_muhl.py", "pfc_riscv.py", "pfc_riscv_run.py",
                "pfc_riscv_priv2.py", "pfc_sv32.py", "pfc_open_problems.py", "pfc_pattern_bank.py",
                "pfc_knowledge.py", "pfc_grand_challenge.py", "pfc_searchfab.py", "pfc_serial_audit.py",
                "pfc_path_score.py", "pfc_priors.py", "pfc_riscv_bank.py"}
    hits = audit(mine)
    print("=" * 94)
    print("PRIORS IN THE BUILD - unmeasured constants that shape behaviour")
    print("  A prior is not a bug. The code runs fine with it. That is why it survives.")
    print("=" * 94)
    if not hits:
        print("  none found")
        return
    hits.sort(key=lambda h: (h[2], not h[5], h[0]))
    print()
    print("  %-24s %5s %-18s %-14s %10s  %s" % ("file", "line", "kind", "name", "value", "justified nearby?"))
    for base, ln, k, nm, val, just in hits:
        print("  %-24s %5d %-18s %-14s %10s  %s"
              % (base, ln, k, nm, val, "yes" if just else "NO  <-- unjustified"))
    un = [h for h in hits if not h[5]]
    print()
    print("  %d candidates, %d with NO justification nearby." % (len(hits), len(un)))
    by = {}
    for h in un:
        by[h[2]] = by.get(h[2], 0) + 1
    for k in sorted(by):
        print("    %-18s %d unjustified" % (k, by[k]))
    print()
    print("  A flag is a CANDIDATE, not a verdict - same contract as pfc_serial_audit.py. The test")
    print("  per hit: WAS THIS NUMBER MEASURED, OR DID I DECIDE IT WAS REASONABLE? If the second,")
    print("  either measure it, derive it from something measured, or make it an argument so the")
    print("  caller owns the judgement instead of the build.")


if __name__ == "__main__":
    main()
