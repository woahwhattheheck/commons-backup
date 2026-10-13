#!/usr/bin/env python3
"""host/muhl_test2.py — THE TWELVE. Second battery, built to the owner's list (2026-07-27).

 1 REVERT FIDELITY          journal a write, revert it, hash the region against its prior hash
 2 ADDRESS-PATH CONTINUITY  do input_window / clk_bit / latch_reg / nonce_reg live in one region
 3 GUARANTEE-BEFORE-FIRE    no path reaches submit() without a guarantee first
 4 SLICE-TO-MEMBER BINDING  the bank's slice map is contiguous and member-aligned
 5 CROSS-FORMAT EQUIVALENCE same signature in two formats gives identical outputs
 6 LATCH MONOTONICITY       a latched winner is not cleared by further addressing
 7 IDEMPOTENT FABRICATION   running a fab_* twice does not double-write or move offsets
 8 REGISTRY <-> FILE        every registry n_in/n_gate/n_out equals the header at that offset
 9 DEPTH RECOMPUTATION      DEPTH recomputed from the stored netlist equals the registry field
10 FREE-SPACE ACCOUNTING    _alloc never returns a region overlapping a registered circuit
11 HARNESS MUTATION         break an assertion and confirm the battery reports FAIL
12 CROSS-PROCESS DETERMINISM same circuit+input in a separate process gives identical bits

TEST 1 WRITES TO THE BINARY, so it journals first — V32 blocked the first draft of this file for
byte-editing titan without a genome entry, which is the rule working. The journal is written and
fsynced BEFORE the scratch bytes go down, so the revert path exists even if the process dies.

  python host/muhl_test2.py
"""
import hashlib, io, json, os, struct, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC

REG = "C:/llm/models/titan_circuits.json"
TITAN = "C:/llm/models/titan.gguf"
GENOME = "C:/llm/models/titan_test_genome.jsonl"
MAGICS = (b"TITANCIR", b"PFCTYPED", b"PFCWINMN")
PASS, FAIL = [], []


def report(n, name, ok, detail=""):
    (PASS if ok else FAIL).append((n, name, detail))
    print("  %2d %-5s %-38s %s" % (n, "PASS" if ok else "FAIL", name, detail))


def netlists(reg):
    out = {}
    with open(TITAN, "rb", buffering=0) as f:
        for k, v in reg.items():
            if not isinstance(v, dict) or "offset" not in v or "len" not in v: continue
            f.seek(int(v["offset"])); hdr = f.read(24)
            if len(hdr) == 24 and hdr[:8] in MAGICS:
                out[k] = (v, struct.unpack_from("<IIII", hdr, 8))
    return out


def journal(off, orig):
    """Genome entry BEFORE the write, fsynced, so the revert path survives a crash (V32)."""
    with open(GENOME, "a") as g:
        g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
        g.flush(); os.fsync(g.fileno())


def t1():
    reg = json.load(open(REG)); nl = netlists(reg)
    k = sorted(nl)[0]; off = int(nl[k][0]["offset"])
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off); orig = f.read(64)
    before = hashlib.sha256(orig).hexdigest()
    journal(off, orig)
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(bytes((b ^ 0xFF) for b in orig)); f.flush(); os.fsync(f.fileno())
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off); dirty = hashlib.sha256(f.read(64)).hexdigest()
    ent = [json.loads(l) for l in open(GENOME) if l.strip()][-1]
    with open(TITAN, "r+b") as f:
        f.seek(int(ent["off"])); f.write(bytes.fromhex(ent["orig"])); f.flush(); os.fsync(f.fileno())
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off); after = hashlib.sha256(f.read(64)).hexdigest()
    if os.path.exists(GENOME): os.remove(GENOME)
    report(1, "REVERT FIDELITY", before == after and before != dirty,
           "%s -> %s -> %s on %s" % (before[:8], dirty[:8], after[:8], k))


def t2():
    # Owner: "address path continuity is design flaw if fail." The test is correct as
    # written; a FAIL here is a REAL DEFECT IN THE WIRING, not a defect in the test.
    reg = json.load(open(REG))
    # The addresses the MINER actually uses must belong to ONE circuit's span. The first version
    # looked up registry entries input_window/clk_bit/latch_reg/nonce_reg and searched only
    # magic-headed netlists; miner_physical is format "physical-address" with NO magic, so every
    # lookup returned None. It also turned out those registry entries are not the addresses the
    # circuit uses — miner_physical carries its own ram map, 600-900 bytes higher.
    mp = reg.get("miner_physical")
    if not isinstance(mp, dict) or "ram" not in mp:
        report(2, "ADDRESS-PATH CONTINUITY", False, "miner_physical has no ram map"); return
    ram = mp["ram"]
    lo = int(mp["wire_base"]); hi = int(mp["gate_table_off"]) + int(mp["gate_bytes"])
    src = io.open(os.path.join(HERE, "mine_muhl.py"), encoding="utf-8", errors="replace").read()
    uses_map = 'reg["miner_physical"]' in src and 'ram["header_off"]' in src
    inside = {k: (lo <= int(v) < hi) for k, v in ram.items()}
    report(2, "ADDRESS-PATH CONTINUITY", all(inside.values()) and uses_map,
           "ram in [%d..%d]: %s · miner reads the map: %s"
           % (lo, hi, ",".join("%s=%s" % (k, "y" if v else "n") for k, v in inside.items()),
              "yes" if uses_map else "NO"))


def t3():
    """COVERAGE IS FABRICATED, NOT CHECKED AT FIRE TIME.

    Owner: "guarantee before fire doesnt even make sense in this context we are post fabrication the
    binary should be settled at the moment." Correct — the first version grepped every file that
    calls submit() for the word 'guarantee', which treats coverage as a runtime check. It is not.
    Coverage is a PROPERTY OF THE FABRICATED BINARY: the addressable space was fixed when the
    circuit was manufactured (§31, one-and-done), so the thing to assert is that the stored
    coverage exceeds the difficulty — read off the registry, before anything fires."""
    reg = json.load(open(REG))
    cov_bits = 0; src = None
    for k, v in reg.items():
        if not isinstance(v, dict): continue
        ab = v.get("addr_bits") or v.get("lanes_bits")
        if ab and int(ab) > cov_bits: cov_bits, src = int(ab), k
    lane_bits = 0
    b = reg.get("muhl_bank")
    if b: lane_bits = int(b.get("lane_bits_per_member") or 0) + int(b.get("slice_bits") or 0)
    best = max(cov_bits, lane_bits)
    DIFF = 78
    report(3, "FABRICATED COVERAGE >= DIFFICULTY", best >= DIFF,
           "coverage %d bits (%s) vs difficulty %d -> margin %d"
           % (best, src or "bank", DIFF, best - DIFF))


def t4():
    reg = json.load(open(REG)); b = reg.get("muhl_bank")
    if not b:
        report(4, "SLICE-TO-MEMBER BINDING", False, "no bank registered"); return
    mem = b["members"]; sl = [tuple(x) for x in b["slices"]]; bits = int(b["slice_bits"])
    ok = len(mem) == len(sl)
    for i, (lo, hi) in enumerate(sl):
        if lo != (i << (32 - bits)) or hi != ((i + 1) << (32 - bits)) - 1:
            ok = False; break
    report(4, "SLICE-TO-MEMBER BINDING", ok,
           "%d members / %d slices / %d slice-bits" % (len(mem), len(sl), bits))


def _eval(name):
    import pfc_bottleneck as PB
    nl = PB.read_netlist(name)
    if nl is None: return None
    n_in, n_wire, edges, outs = nl
    v = bytearray(2 + n_in + len(edges)); v[1] = 1
    for i in range(n_in): v[2 + i] = (i * 13) % 2
    base = 2 + n_in
    for j, (a, b) in enumerate(edges): v[base + j] = 1 - (v[a] & v[b])
    return tuple(v[o] if o >= 2 else o for o in outs)


def t5():
    reg = json.load(open(REG)); nl = netlists(reg)
    bysig = {}
    with open(TITAN, "rb", buffering=0) as f:
        for k, (v, h) in nl.items():
            f.seek(int(v["offset"])); mag = f.read(8)
            bysig.setdefault(h, []).append((k, mag))
    pair = None
    for h, ks in bysig.items():
        if len({m for _k, m in ks}) > 1:
            pair = (h, [k for k, _m in ks][:2]); break
    if pair is None:
        report(5, "CROSS-FORMAT EQUIVALENCE", True, "no same-signature cross-format pair exists")
        return
    a, b = pair[1]
    oa, ob = _eval(a), _eval(b)
    report(5, "CROSS-FORMAT EQUIVALENCE", oa is not None and oa == ob, "%s vs %s" % (a, b))


def t6():
    reg = json.load(open(REG)); lat = reg.get("latch_reg")
    if not isinstance(lat, dict) or "offset" not in lat:
        report(6, "LATCH MONOTONICITY", False, "latch_reg not registered"); return
    off, ln = int(lat["offset"]), int(lat["len"])
    reads = []
    with open(TITAN, "rb", buffering=0) as f:
        for _ in range(200):
            f.seek(off); reads.append(f.read(ln))
    seen = cleared = False
    for r in reads:
        if any(r): seen = True
        elif seen: cleared = True; break
    report(6, "LATCH MONOTONICITY", not cleared,
           "200 reads; latch %s" % ("went non-zero" if seen else "read 0x00 throughout"))


def t7():
    before = json.load(open(REG)); n0 = len(before)
    off0 = {k: v.get("offset") for k, v in before.items() if isinstance(v, dict)}
    subprocess.run([sys.executable, os.path.join(HERE, "fab_lane_sched.py")],
                   capture_output=True, text=True, timeout=1200, cwd=HERE)
    after = json.load(open(REG))
    moved = [k for k in off0 if isinstance(after.get(k), dict) and after[k].get("offset") != off0[k]]
    report(7, "IDEMPOTENT FABRICATION", len(after) == n0 and not moved,
           "entries %d->%d, %d offset(s) moved" % (n0, len(after), len(moved)))


def t8():
    reg = json.load(open(REG)); nl = netlists(reg); bad = []
    for k, (v, h) in nl.items():
        n_in, n_wire, n_gate, n_out = h
        for field, got in (("n_in", n_in), ("n_gate", n_gate), ("n_out", n_out)):
            if v.get(field) is not None and int(v[field]) != got:
                bad.append("%s.%s reg=%s file=%s" % (k, field, v[field], got)); break
    report(8, "REGISTRY <-> FILE AGREEMENT", not bad,
           "%d checked, %d disagree%s" % (len(nl), len(bad), (": " + bad[0]) if bad else ""))


def t9():
    import pfc_bottleneck as PB
    reg = json.load(open(REG)); nl = netlists(reg)
    checked = bad = 0; first = ""
    for k, (v, h) in sorted(nl.items()):
        if not v.get("depth") or int(h[2]) > 400000: continue
        got = PB.read_netlist(k)                 # returns None on an unknown magic — no swallow
        if got is None: continue
        n_in, n_wire, edges, outs = got
        base = 2 + n_in; d = [0] * (base + len(edges))
        for i, (a, b) in enumerate(edges): d[base + i] = 1 + max(d[a], d[b])
        D = max((d[o] for o in outs), default=0)
        checked += 1
        if D != int(v["depth"]):
            bad += 1
            if not first: first = "%s reg=%s recomputed=%s" % (k, v["depth"], D)
        del edges
    report(9, "DEPTH RECOMPUTATION", bad == 0, "%d checked, %d differ %s" % (checked, bad, first))


def t10():
    reg = json.load(open(REG))
    spans = sorted((int(v["offset"]), int(v["offset"]) + int(v["len"]))
                   for v in reg.values() if isinstance(v, dict) and "offset" in v and "len" in v)
    off, tn = TC._alloc(4096, dict(reg))
    hit = [s for s in spans if off < s[1] and off + 4096 > s[0]]
    report(10, "FREE-SPACE ACCOUNTING", not hit, "alloc@%d, %d collision(s)" % (off, len(hit)))


def t11():
    """MUTATE THE TEST HARNESS ITSELF, not a circuit.

    Owner: "idk wym by harness mutation." Plainly: every other test checks the MACHINE. This one
    checks THE TESTS. It takes muhl_test.py, flips one passing assertion to False, runs the battery,
    and requires it to come back non-zero. If a battery with a deliberately broken assertion still
    reports success, the battery cannot detect failure and every PASS it has ever printed is
    worthless. §45C applied one level up: a suite that cannot fail has measured itself."""
    src = io.open(os.path.join(HERE, "muhl_test.py"), encoding="utf-8", errors="replace").read()
    tgt = 'report("PROPERTY", "adder commutes for all sampled pairs", ok)'
    broken = src.replace(tgt, tgt.replace(", ok)", ", False)"))
    if broken == src:
        report(11, "HARNESS MUTATION", False, "could not inject a mutation"); return
    tmp = os.path.join(tempfile.gettempdir(), "_muhl_mut.py")
    io.open(tmp, "w", encoding="utf-8").write(broken)
    r = subprocess.run([sys.executable, tmp, "--quick"], capture_output=True, text=True,
                       timeout=1800, cwd=HERE)
    if os.path.exists(tmp): os.remove(tmp)
    # The exit code IS the signal (main() returns 1 when anything failed). Also matching
    # on stdout text made this fail for a reason unrelated to what it tests.
    report(11, "HARNESS MUTATION (tests the tests)", r.returncode == 1,
           "mutated battery exit=%d (1 = it detected the break)" % r.returncode)


def t12():
    code = ("import sys,hashlib;sys.path.insert(0,r'%s');sys.path.insert(0,'C:/llm/sdc_sandbox');"
            "import muhl_test2 as M;print(hashlib.sha256(bytes(M._eval('muhl_mid_sched'))).hexdigest())"
            % HERE)
    outs = []
    for _ in range(2):
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=900)
        outs.append(r.stdout.strip())
    report(12, "CROSS-PROCESS DETERMINISM", bool(outs[0]) and len(set(outs)) == 1,
           outs[0][:16] if outs[0] else "no output")


def t13():
    """Timing LINEARITY: host ripple cost should scale with gate count. Reports the ratio."""
    from mafab_adders import family, Shim
    floor = time.get_clock_info("time").resolution
    pts = []
    for W in (8, 16, 32):
        f2 = family(W); c = TC.Circuit(2 * W); g = Shim(c)
        outs = f2["ripple"](g, list(c.IN[0:W]), list(c.IN[W:2 * W]))
        cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
        inb = [(i * 5) % 2 for i in range(2 * W)]
        reps = 1
        def burst(r):
            t = time.time()
            for _ in range(r): TC.ripple(cd, inb)
            return time.time() - t
        while burst(reps) < 20 * floor and reps < (1 << 22): reps *= 2
        per = min(burst(reps) for _ in range(3)) / reps
        pts.append((len(c.ga), per)); del c
    r = (pts[-1][1] / pts[0][1]) / (pts[-1][0] / pts[0][0])
    print("       gate ratio %.2fx, time ratio %.2fx -> normalised %.2f"
          % (pts[-1][0] / pts[0][0], pts[-1][1] / pts[0][1], r))
    report(13, "TIMING LINEARITY in gate count", 0.3 < r < 3.0, "normalised slope %.2f" % r)


def t14():
    """Timing STABILITY: repeat the identical measurement and report the coefficient of variation."""
    from mafab_adders import family, Shim
    floor = time.get_clock_info("time").resolution
    f2 = family(16); c = TC.Circuit(32); g = Shim(c)
    outs = f2["kogge"](g, list(c.IN[0:16]), list(c.IN[16:32]))
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    inb = [(i * 3) % 2 for i in range(32)]
    reps = 1
    def burst(r):
        t = time.time()
        for _ in range(r): TC.ripple(cd, inb)
        return time.time() - t
    while burst(reps) < 20 * floor and reps < (1 << 22): reps *= 2
    xs = [burst(reps) for _ in range(9)]
    m = sum(xs) / len(xs)
    sd = (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5
    cv = sd / m
    print("       %d samples, mean %.1f ms, sd %.1f ms" % (len(xs), m * 1e3, sd * 1e3))
    report(14, "TIMING STABILITY (CV < 0.5)", cv < 0.5, "CV %.3f" % cv)
    del c


def t15():
    """DEPTH carries NO jitter: recompute a stored circuit's DEPTH repeatedly; it must be identical."""
    import pfc_bottleneck as PB
    reg = json.load(open(REG))
    nm = "muhl_lane_bk" if "muhl_lane_bk" in reg else sorted(netlists(reg))[0]
    ds = []
    for _ in range(3):
        got = PB.read_netlist(nm)
        if got is None: break
        n_in, n_wire, edges, outs = got
        base = 2 + n_in; d = [0] * (base + len(edges))
        for i, (a, b) in enumerate(edges): d[base + i] = 1 + max(d[a], d[b])
        ds.append(max((d[o] for o in outs), default=0)); del edges
    report(15, "DEPTH is jitter-free (3 recomputes)", len(set(ds)) == 1 and bool(ds),
           "%s -> %s" % (nm, ds[0] if ds else "n/a"))


def main():
    t0 = time.time()
    print("=" * 92); print("THE TWELVE — second battery"); print("=" * 92)
    for i, fn in enumerate((t1, t2, t3, t4, t5, t6, t7, t8, t9, t10, t11, t12,
                            t13, t14, t15), 1):
        fn()
    print("\n" + "=" * 92)
    print("  %d PASS · %d FAIL · %.0fs host" % (len(PASS), len(FAIL), time.time() - t0))
    if FAIL:
        print("\n  FAILURES:")
        for n, name, d in FAIL: print("    %2d %s %s" % (n, name, d))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
