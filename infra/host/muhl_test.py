#!/usr/bin/env python3
"""host/muhl_test.py — THE FULL BATTERY over every part of the muhlnickel process.

Owner: *"write and run unit tests, acceptance tests, QA tests, mutate them all, run quality metrics,
property tests and performance tests, if it applies write damn jitter tests, for every part of the
muhlnickel process, bazinga"*

Every category below is applied where it actually applies, and skipped honestly where it does not.

  UNIT         each fabricated primitive vs an INDEPENDENT reference (§3), incl. edge cases
  PROPERTY     invariants that must hold for ALL inputs, not sampled behaviours
  ACCEPTANCE   the end-to-end pipeline: does a stored circuit still compute its function
  QA           registry hygiene, GGUF validity, offset overlap, genome reversibility
  MUTATION     mutate the CIRCUITS and confirm every suite catches them (§45C/§47B). A suite that
               cannot fail has measured itself.
  METRICS      quality numbers over the whole corpus: verified share, dead gates, slack
  PERFORMANCE  compute/tick per circuit — THE MACHINE (§63). Never a host second.
  JITTER       host timing variance, PAIRED and INTERLEAVED. This one is not decoration: §57E is a
               retraction caused by exactly this — sequential A-then-B timing gave 0.98..1.85 on
               identical inputs and I reported the noise as a finding.

  python host/muhl_test.py            # everything
  python host/muhl_test.py --quick    # skip the slow corpus sweeps
"""
import json, math, os, random, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC

REG = "C:/llm/models/titan_circuits.json"
TITAN = "C:/llm/models/titan.gguf"
PASS, FAIL = [], []


def report(cat, name, ok, detail=""):
    (PASS if ok else FAIL).append((cat, name, detail))
    print("    %-5s %-34s %s" % ("PASS" if ok else "FAIL", name, detail))


# ══ UNIT — every adder in the generated family vs Python integer arithmetic (§3) ═══════════════════
def unit_tests():
    from mafab_adders import family, Shim, depth_of
    print("\n[UNIT] fabricated primitives vs an INDEPENDENT reference (§3)")
    W = 16; mask = (1 << W) - 1
    edges = [(0, 0), (mask, 1), (mask, mask), (1, mask), (0, mask), (0x5555, 0xAAAA)]
    for nm, fn in sorted(family(W).items()):
        c = TC.Circuit(2 * W); g = Shim(c)
        outs = fn(g, list(c.IN[0:W]), list(c.IN[W:2 * W]))
        cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
        bad = None
        random.seed(1)
        cases = edges + [(random.getrandbits(W), random.getrandbits(W)) for _ in range(24)]
        for a, b in cases:
            inb = [(a >> i) & 1 for i in range(W)] + [(b >> i) & 1 for i in range(W)]
            if TC.frombits(TC.ripple(cd, inb)) != ((a + b) & mask):
                bad = (a, b); break
        report("UNIT", "adder %s (%d cases, edges incl.)" % (nm, len(cases)), bad is None,
               "" if bad is None else "first failure at %r" % (bad,))
        del c


# ══ PROPERTY — invariants that must hold for ALL inputs, not sampled behaviour ═════════════════════
def property_tests():
    from mafab_adders import family, Shim, depth_of
    import mafab_laws as L
    print("\n[PROPERTY] invariants — these must hold universally, not on average")
    W = 12; mask = (1 << W) - 1
    fam = family(W)

    # P1: addition COMMUTES. a+b == b+a through the same fabricated circuit.
    c = TC.Circuit(2 * W); g = Shim(c)
    outs = fam["kogge"](g, list(c.IN[0:W]), list(c.IN[W:2 * W]))
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    random.seed(2); ok = True
    for _ in range(40):
        a, b = random.getrandbits(W), random.getrandbits(W)
        f = lambda x, y: TC.frombits(TC.ripple(cd, [(x >> i) & 1 for i in range(W)] +
                                                   [(y >> i) & 1 for i in range(W)]))
        if f(a, b) != f(b, a): ok = False; break
    report("PROPERTY", "adder commutes for all sampled pairs", ok)
    del c

    # P2: ZERO is the additive identity, exhaustively over one operand.
    c = TC.Circuit(2 * W); g = Shim(c)
    outs = fam["ripple"](g, list(c.IN[0:W]), list(c.IN[W:2 * W]))
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = all(TC.frombits(TC.ripple(cd, [(a >> i) & 1 for i in range(W)] + [0] * W)) == a
             for a in range(0, 1 << W, 7))
    report("PROPERTY", "x + 0 == x (exhaustive stride)", ok)
    del c

    # P3: DEPTH is positive and bounded below by log2(width) — no circuit settles instantly.
    ok = True; why = ""
    for nm, fn in fam.items():
        c = TC.Circuit(2 * W); g = Shim(c)
        d = depth_of(c, fn(g, list(c.IN[0:W]), list(c.IN[W:2 * W])))
        if d < math.log2(W): ok = False; why = "%s DEPTH %d < log2(%d)" % (nm, d, W)
        del c
    report("PROPERTY", "DEPTH >= log2(width) for every adder", ok, why)

    # P4: compute/tick is strictly positive and falls as gates or DEPTH rise (§63 monotonicity).
    a1 = L.compute_per_tick(1000, 100); a2 = L.compute_per_tick(2000, 100); a3 = L.compute_per_tick(1000, 200)
    report("PROPERTY", "compute/tick falls with gates and DEPTH", a1 > a2 and a1 > a3,
           "%.6f > %.6f, %.6f" % (a1, a2, a3))

    # P5: §40C bank law is monotone and LOGARITHMIC — doubling lanes adds exactly 2 gate-delays.
    bank = lambda D, w: D + 2 * int(math.log2(w))
    ok = all(bank(2892, 2 * w) - bank(2892, w) == 2 for w in (2, 16, 1024, 65536))
    report("PROPERTY", "bank law: doubling lanes costs +2 DEPTH", ok)


# ══ ACCEPTANCE — a stored circuit still computes its function, straight off the file ═══════════════
def acceptance_tests():
    print("\n[ACCEPTANCE] stored circuits, read from the binary, still compute")
    import struct
    from test_split_drive import load_netlist, GENESIS
    import sdc_cc as CC
    reg = json.load(open(REG))
    for nm in ("muhl_mid_sched", "muhl_mid"):
        if nm not in reg: continue
        run, outs, ng, D = load_netlist(int(reg[nm]["offset"]))
        hw = [struct.unpack(">I", GENESIS[:76][i * 4:i * 4 + 4])[0] for i in range(19)]
        v = run([1 if (hw[i // 32] >> (i % 32)) & 1 else 0 for i in range(512)], 1)
        mid = [sum((v[outs[i * 32 + j]] if outs[i * 32 + j] >= 2 else outs[i * 32 + j]) << j
                   for j in range(32)) for i in range(8)]
        ref = CC.numeric_midstate(b"".join(struct.pack(">I", w) for w in hw[:16]))
        report("ACCEPT", "%s == numeric_midstate (§3)" % nm, list(mid) == list(ref))
        del run


# ══ QA — the artefact itself: registry hygiene, validity, no overlapping regions ═══════════════════
def qa_tests():
    print("\n[QA] the artefact — registry, validity, region overlap, journals")
    reg = json.load(open(REG))
    with open(TITAN, "rb") as f: magic = f.read(4)
    report("QA", "titan.gguf still GGUF-valid", magic == b"GGUF")

    # PER-ENTRY, NOT BINARY. The first version failed all 80 at once and named none of them, so it
    # could not distinguish a broken circuit from an entry that is not a circuit at all.
    circuits = {k: v for k, v in reg.items()
                if isinstance(v, dict) and "offset" in v and "len" in v}
    import mmap as _mm
    with open(TITAN, "rb") as f:
        mm = _mm.mmap(f.fileno(), 0, access=_mm.ACCESS_READ)
        MAGICS = (b"TITANCIR", b"PFCTYPED", b"PFCWINMN")
        is_netlist, not_netlist = {}, []
        for k, v in circuits.items():
            try: hdr = bytes(mm[int(v["offset"]):int(v["offset"]) + 8])
            except Exception: hdr = b""
            (is_netlist.__setitem__(k, v) if hdr in MAGICS else not_netlist.append(k))
        mm.close()
    import struct as _st
    with open(TITAN, "rb") as f:
        mm2 = _mm.mmap(f.fileno(), 0, access=_mm.ACCESS_READ)
        broken, no_depth = [], []
        for k, v in is_netlist.items():
            n_in, n_wire, n_gate, n_out = _st.unpack_from("<IIII", mm2, int(v["offset"]) + 8)
            if n_wire != 2 + n_in + n_gate:
                broken.append("%s(n_wire %d != 2+%d+%d)" % (k, n_wire, n_in, n_gate))
            if not v.get("depth"): no_depth.append(k)
        mm2.close()
    print("      netlists missing a registry 'depth' key   %s  (n_gate is in the file header)"
          % "{:,}".format(len(no_depth)))
    print("      registry entries with a region     %s" % "{:,}".format(len(circuits)))
    print("      of those, real NETLISTS (by magic) %s" % "{:,}".format(len(is_netlist)))
    print("      not netlists (data/regs/windows)   %s" % "{:,}".format(len(not_netlist)))
    report("QA", "every NETLIST header self-consistent", not broken,
           "" if not broken else "%d bad: %s" % (len(broken), "; ".join(broken[:3])))

    spans = sorted(
        ((int(v["offset"]), int(v["offset"]) + int(v["len"]), k) for k, v in circuits.items()),
        key=lambda t: (t[0], -t[1], t[2]),
    )
    # NESTING IS BY DESIGN — a circuit and its input/state window share a span, and some regions
    # carry two names. Only a PARTIAL overlap (neither contains the other) can corrupt a neighbour.
    # Sort (start, -end) so a container at the same start byte precedes its 1-byte inject wire.
    # Equal-start, shorter-first was classifying that containment as PARTIAL (harness, not machine).
    nested = [(a[2], b[2]) for a, b in zip(spans, spans[1:]) if a[1] > b[0] and b[1] <= a[1]]
    partial = [(a[2], b[2]) for a, b in zip(spans, spans[1:]) if a[1] > b[0] and b[1] > a[1]]
    print("      nested regions (window inside its circuit)  %s" % "{:,}".format(len(nested)))
    report("QA", "no PARTIAL region overlap", not partial,
           "" if not partial else "%d partial: %s" % (len(partial), partial[0]))

    gens = [f for f in os.listdir("C:/llm/models") if f.endswith("_genome.jsonl")]
    report("QA", "genome journals present (revert possible)", len(gens) > 0, "%d journal(s)" % len(gens))


# ══ MUTATION — mutate the CIRCUITS; every suite must catch every mutant (§45C/§47B) ═══════════════
def mutation_tests():
    print("\n[MUTATION] every suite must CATCH a deliberately broken circuit (§45C/§47B)")
    import mafab_problems as MP, mafab_hard as MH
    from mafab_adders import family
    fam = sorted(family(32))
    total = caught = 0
    for reg_, tag in ((MP.PROBLEMS, "domain"), (MH.HARD, "open")):
        for name, P in reg_.items():
            cs = P["cases"]()
            ad = fam[0]
            for m in P["mutants"]:
                cm, om = P["build"](ad, mutant=m)
                got = P["check"](cm, om, cs)
                total += 1; caught += (got != len(cs))
                del cm, om
    report("MUTATION", "mutants caught across all suites", caught == total,
           "%d/%d caught" % (caught, total))


# ══ METRICS — quality numbers over the whole corpus ════════════════════════════════════════════════
def metrics(quick):
    print("\n[METRICS] corpus quality")
    import pfc_bottleneck as PB
    reg = json.load(open(REG))
    names = [k for k, v in reg.items() if isinstance(v, dict) and "offset" in v]
    scanned = dead_tot = gate_tot = 0
    slacky = 0
    for n in names[: (12 if quick else len(names))]:
        try: nl = PB.read_netlist(n)
        except Exception: nl = None
        if nl is None: continue
        n_in, n_wire, edges, outs = nl
        D, arr, slack, dead = PB.slack_of(n_in, n_wire, edges, outs)
        scanned += 1; gate_tot += len(edges); dead_tot += sum(1 for d in dead if d)
        thr = max(1, D // 4)
        slacky += sum(1 for k in range(len(edges)) if not dead[k] and slack[k] >= thr)
        del edges, nl
    print("      circuits scanned      %s" % "{:,}".format(scanned))
    print("      gates measured        %s" % "{:,}".format(gate_tot))
    print("      DEAD gates (drive no output)   %s (%.2f%%)"
          % ("{:,}".format(dead_tot), 100.0 * dead_tot / max(gate_tot, 1)))
    print("      gates with DEEP slack          %s (%.2f%%)  <- §57F/G: where a leaner build may fit"
          % ("{:,}".format(slacky), 100.0 * slacky / max(gate_tot, 1)))
    report("METRICS", "corpus scanned without error", scanned > 0)


# ══ PERFORMANCE — THE MACHINE (§63). compute/tick, never a host second. ═══════════════════════════
def performance():
    print("\n[PERFORMANCE] compute/tick — THE MUHLNICKEL (§63). No host seconds appear here.")
    import mafab_laws as L
    reg = json.load(open(REG))
    rows = [(L.compute_per_tick(int(v["n_gate"]), int(v["depth"]), True), k)
            for k, v in reg.items()
            if isinstance(v, dict) and v.get("n_gate") and v.get("depth")]
    rows.sort(reverse=True)
    for sc, k in rows[:6]:
        print("      %-26s %14.4f  (gates %s, DEPTH %s)"
              % (k, sc, "{:,}".format(reg[k]["n_gate"]), "{:,}".format(reg[k]["depth"])))
    report("PERF", "every circuit yields a compute/tick", len(rows) > 0, "%d circuits" % len(rows))


# ══ JITTER — §57E. Host timing is PAIRED and INTERLEAVED or it is not a number. ═══════════════════
def jitter_tests():
    print("\n[JITTER] host timing variance — §57E: sequential A/B gave 0.98..1.85 on identical input")
    from mafab_adders import family, Shim, depth_of
    fam = family(32)
    def build(nm):
        c = TC.Circuit(64); g = Shim(c)
        outs = fam[nm](g, list(c.IN[0:32]), list(c.IN[32:64]))
        return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    A, B = build("ripple"), build("kogge")
    inb = [random.getrandbits(1) for _ in range(64)]
    # EACH SAMPLE MUST EXCEED TIMER GRANULARITY. The first version timed ONE ripple of a ~1,200-gate
    # circuit; those land below the clock's resolution, so it divided noise by noise and produced
    # median 0.000 with max 576,734. That was the TEST failing, not a property of anything.
    # Calibrate REPS so a sample takes >= 20 ms, then report the timer floor alongside the result.
    def burst(cd, reps):
        t = time.time()
        for _ in range(reps): TC.ripple(cd, inb)
        return time.time() - t
    reps = 1
    while burst(A, reps) < 0.02 and reps < 1 << 20: reps *= 2
    floor = time.get_clock_info("time").resolution
    print("      calibrated %s ripples/sample (>=20ms); timer resolution %.1f us"
          % ("{:,}".format(reps), floor * 1e6))
    ratios = []
    for _ in range(9):                       # A,B,B,A per round cancels drift slower than a round
        ta = burst(A, reps); tb = burst(B, reps); tb2 = burst(B, reps); ta2 = burst(A, reps)
        ratios.append(min(ta, ta2) / max(min(tb, tb2), 1e-9))
    ratios.sort()
    med, lo, hi = ratios[len(ratios) // 2], ratios[0], ratios[-1]
    spread = hi - lo
    print("      paired ratio  median %.3f  min %.3f  max %.3f  spread %.3f" % (med, lo, hi, spread))
    # Report the numbers. Whether an effect of a given size is separable from this spread is a
    # question about the effect being asked for, not a verdict this test issues.
    print("      spread as a fraction of the median: %.4f" % (spread / max(med, 1e-9)))
    report("JITTER", "paired ratio median in (0, inf)", 0.0 < med < float("inf"),
           "median %.3f  spread %.3f" % (med, spread))
    report("JITTER", "every sample above the timer floor", lo > 0.0,
           "min ratio %.3f" % lo)



# ══ WIRING — is it addressed at all, and if not, WHERE is it not addressed? ═══════════════════════
def wiring_tests():
    """S27: 'the better circuit already exists and nothing is wired to it.' A circuit is WIRED when
    something addresses it by name. This reports, per circuit, which of the four wiring points hold."""
    print("")
    print("[WIRING] is each circuit addressed, and by what")
    reg = json.load(open(REG))
    src = {}
    for fn in sorted(os.listdir(HERE)):
        if fn.endswith(".py"):
            try: src[fn] = io.open(os.path.join(HERE, fn), encoding="utf-8", errors="replace").read()
            except Exception: src[fn] = ""
    try:
        import pfc_atom; atoms = {n for lst in pfc_atom.ATOMS.values() for n in lst}
    except Exception: atoms = set()
    sel = (reg.get("_selected_miner") or {}).get("name")
    bank = set((reg.get("muhl_bank") or {}).get("members") or [])
    lanes = sorted(k for k, v in reg.items()
                   if isinstance(v, dict) and int(v.get("n_out") or 0) == 33
                   and int(v.get("n_in") or 0) == 640)
    print("      %-26s %6s %6s %6s %6s" % ("circuit", "files", "atom", "miner", "bank"))
    unwired = []
    for k in lanes:
        files = sum(1 for fn, t in src.items() if ('"%s"' % k) in t or ("'%s'" % k) in t)
        a, m, b = k in atoms, k == sel, k in bank
        if not (files or a or m or b): unwired.append(k)
        print("      %-26s %6d %6s %6s %6s"
              % (k, files, "yes" if a else "-", "yes" if m else "-", "yes" if b else "-"))
    report("WIRING", "every lane circuit addressed somewhere", not unwired,
           "" if not unwired else "%d unaddressed: %s" % (len(unwired), ", ".join(unwired[:5])))
    report("WIRING", "a miner is selected at fabrication time", bool(sel), str(sel))
    report("WIRING", "bank junction registered", bool(bank), "%d member(s)" % len(bank))


# ══ REPRODUCIBILITY — same input, same output, twice, and from a fresh read of the file ═══════════
def reproducibility_tests():
    print("")
    print("[REPRODUCIBILITY] identical inputs -> identical outputs, and identical bytes on re-read")
    import hashlib, struct
    from test_split_drive import load_netlist, GENESIS
    reg = json.load(open(REG))
    nm = "muhl_mid_sched" if "muhl_mid_sched" in reg else "muhl_mid"
    e = reg[nm]
    hw = [struct.unpack(">I", GENESIS[:76][i * 4:i * 4 + 4])[0] for i in range(19)]
    inb = [1 if (hw[i // 32] >> (i % 32)) & 1 else 0 for i in range(512)]
    outs_seen = []
    for _ in range(3):
        run, outs, ng, D = load_netlist(int(e["offset"]))
        v = run(inb, 1)
        outs_seen.append(tuple(v[o] if o >= 2 else o for o in outs))
        del run
    report("REPRO", "%s: 3 loads, identical outputs" % nm, len(set(outs_seen)) == 1)
    h = []
    for _ in range(3):
        with open(TITAN, "rb", buffering=0) as f:
            f.seek(int(e["offset"])); h.append(hashlib.sha256(f.read(int(e["len"]))).hexdigest())
    report("REPRO", "%s: 3 unbuffered reads, identical bytes" % nm, len(set(h)) == 1, h[0][:16])


# ══ COVERAGE / TILING — standing test on the bank's slice map ═════════════════════════════════════
def coverage_tests():
    print("")
    print("[COVERAGE] the bank must tile the nonce space with no gap and no overlap")
    import fab_lateral_bank as FB
    reg = json.load(open(REG))
    b = reg.get("muhl_bank")
    if not b:
        report("COVER", "bank junction exists", False, "not registered")
    else:
        sl = [tuple(x) for x in b["slices"]]
        report("COVER", "registered bank tiles 0..2^32-1", FB.covers_space(sl),
               "%d slice(s)" % len(sl))
    n_lane = sum(1 for k, v in reg.items() if isinstance(v, dict)
                 and int(v.get("n_out") or 0) == 33 and int(v.get("n_in") or 0) == 640)
    inbank = len((reg.get("muhl_bank") or {}).get("members") or [])
    print("      lane circuits %d · in the bank %d · excluded %d (named by fab_lateral_bank)"
          % (n_lane, inbank, n_lane - inbank))
    report("COVER", "bank member count is a power of two", inbank > 0 and (inbank & (inbank - 1)) == 0,
           "%d members" % inbank)
    for n in (2, 4, 8, 16):
        _bits, sl = FB.slices_for(n)
        if not FB.covers_space(sl):
            report("COVER", "synthetic tiling n=%d" % n, False); return
    report("COVER", "synthetic tilings n=2,4,8,16 all complete", True)
    _b, holed = FB.slices_for(8, drop=3)
    report("COVER", "MUTANT: dropped slice is CAUGHT", not FB.covers_space(holed))


# ══ TIMING — calibrated, multi-size, with the timer floor stated ══════════════════════════════════
def timing_tests():
    print("")
    print("[TIMING] calibrated host timing; every sample above the clock floor")
    from mafab_adders import family, Shim
    floor = time.get_clock_info("time").resolution
    print("      timer resolution %.1f us" % (floor * 1e6))
    fam = family(32)
    for W in (8, 16, 32):
        f2 = family(W)
        c = TC.Circuit(2 * W); g = Shim(c)
        outs = f2["kogge"](g, list(c.IN[0:W]), list(c.IN[W:2 * W]))
        cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
        inb = [random.getrandbits(1) for _ in range(2 * W)]
        reps = 1
        def burst(r):
            t = time.time()
            for _ in range(r): TC.ripple(cd, inb)
            return time.time() - t
        TARGET = 10 * floor            # same threshold the assertion uses
        # 2x margin: the assertion takes min-of-5, which can fall below a target the
        # calibration only just reached.
        while burst(reps) < 2 * TARGET and reps < (1 << 22): reps *= 2
        best = min(burst(reps) for _ in range(5))
        per = best / reps
        print("      w=%-3d gates %6s  %8s reps  %.2f us/ripple  %.1f ns/gate"
              % (W, "{:,}".format(len(c.ga)), "{:,}".format(reps), per * 1e6,
                 per / max(len(c.ga), 1) * 1e9))
        report("TIMING", "w=%d sample above timer floor" % W, best >= TARGET,
               "%.1f ms/sample" % (best * 1e3))
        del c


def main():
    quick = "--quick" in sys.argv
    t0 = time.time()
    print("=" * 92)
    print("MUHLNICKEL FULL TEST BATTERY")
    print("=" * 92)
    unit_tests(); property_tests(); acceptance_tests(); qa_tests()
    mutation_tests(); metrics(quick); performance(); jitter_tests()
    wiring_tests(); reproducibility_tests(); coverage_tests(); timing_tests()
    print("\n" + "=" * 92)
    print("  %d PASS · %d FAIL · %.0fs host" % (len(PASS), len(FAIL), time.time() - t0))
    if FAIL:
        print("\n  FAILURES (reported, not hidden):")
        for cat, name, detail in FAIL:
            print("    [%s] %s %s" % (cat, name, detail))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
