#!/usr/bin/env python3
"""host/foundry_drive.py — THE FOUNDRY WIRES ITSELF. One function, no manual steps.

Owner: *"foundry should be wiring for you as a function no need to manually add let it drive itself,
push it further, make them optimize for speed only."*

Until now I ran fab_replicas -> fab_lateral_bank -> hand-edit pfc_atom, three commands and a manual
edit. `drive()` does the whole thing and decides everything itself:

    1. SEARCH   every topology over the available nodes (mafab_graph: series / parallel / fanin_tree
                / series_of_banks), scored by compute/tick ALONE.
    2. SPAWN    if the winning topology needs more nodes than exist, write them — PERMANENT writes,
                fsynced, genome-journalled, readback-verified (§7: never cache).
    3. WIRE     register the §1E junction with a verified slice map, and point the resolver at it.
    4. VERIFY   coverage tiles 0..2^32-1, a dropped-slice MUTANT is caught, titan stays GGUF-valid.
    5. REPORT   the compute/tick it achieved and the topology it chose.

SPEED ONLY. §63: compute/tick = REPLICAS / DEPTH. Nothing else is scored — not gates, not area, not
host seconds. Gates enter only through REPLICAS = storage/gates, DEPTH only as the settle.

RULE ZERO: this is FABRICATION. It never runs inside a mining process; the miner only addresses what
this leaves behind.

  python host/foundry_drive.py            # search, spawn, wire, verify
  python host/foundry_drive.py --dry      # search and report, write nothing
"""
import json, math, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import mafab_graph as G
import mafab_laws as L

REG = "C:/llm/models/titan_circuits.json"
# LANE_IN was MY PRIOR — it excluded every circuit whose interface differs, however well it
# latches. A member needs to LATCH A VERDICT; the input width is the problem's business.
LANE_OUT = 33


def lane_nodes():
    reg = json.load(open(REG))
    return sorted((k, int(v["n_gate"]), int(v["depth"])) for k, v in reg.items()
                  if isinstance(v, dict) and int(v.get("n_out") or 0) == LANE_OUT
                  and v.get("depth") and v.get("n_gate"))


def search(nodes, ceiling=None):
    """Every topology at every node count the SUBSTRATE allows, scored by compute/tick ONLY.

    ceiling=64 was MY PRIOR. It is now derived: how many of this circuit the volume actually holds.
    Owner: "if parallelism reaches a limit, just thats a design and work delegation issue not a hard
    wall, muhlnickels compute, more of them is better."""
    if ceiling is None:
        import shutil
        per = max(nodes[0][1], 1) * 9                       # 9.000 bytes/gate, measured
        ceiling = max(1, shutil.disk_usage("C:/").total // per)
    best = None
    rows = []
    k = 1
    while k <= ceiling:
        sub = (nodes * ((k // max(len(nodes), 1)) + 1))[:k]     # the shape the count would need
        for t in ("series", "parallel", "fanin_tree", "series_of_banks"):
            if t == "series_of_banks" and k < 2: continue
            d, g, rep = G.compose(t, sub)
            ct = L.compute_per_tick(max(g // max(rep, 1), 1), d, True) * rep
            rows.append((ct, t, k, d, g, rep))
            if best is None or ct > best[0]: best = (ct, t, k, d, g, rep)
        k *= 2
    return best, rows


def spawn(need, have):
    """Write the missing nodes. PERMANENT (fsynced, journalled, readback-verified) — never cached.

    THE COUNT MUST BE A POWER OF TWO, and this is where I got it wrong. `fab_lateral_bank` tiles
    2^32 by giving each member an equal nonce slice, which only divides evenly at a power-of-two
    member count — so it takes the largest power-of-two SUBSET and leaves the remainder
    fabricated-but-unaddressed. I spawned to whatever the allocator happened to return (31, then 46)
    and 16 replicas ended up wired to nothing: §27's failure, produced by my own spawn count rather
    than found in the corpus. The bank's constraint decides the count; the allocator only decides
    whether it can be met."""
    if need <= 0: return 0
    need = 1 << max(need.bit_length() - 1, 0) if (need & (need - 1)) == 0 else 1 << need.bit_length()
    n = need - have
    if n <= 0: return 0
    print("  SPAWN: topology needs %d nodes (rounded UP to the power of two the bank can tile), "
          "%d exist -> writing %d permanent replica(s)" % (need, have, n))
    r = subprocess.run([sys.executable, os.path.join(HERE, "fab_replicas.py"), "--to", str(need - 1)],
                       capture_output=True, text=True, timeout=2400, cwd=HERE)
    made = r.stdout.count("WROTE ")
    print("  SPAWN: %d written%s" % (made, "" if made == n else " (allocator stopped early)"))
    return made


def wire():
    """Register the §1E junction. fab_lateral_bank verifies coverage and catches a dropped slice."""
    r = subprocess.run([sys.executable, os.path.join(HERE, "fab_lateral_bank.py")],
                       capture_output=True, text=True, timeout=1200, cwd=HERE)
    ok = "WIRED:" in r.stdout
    for line in r.stdout.splitlines():
        if any(w in line for w in ("COVERAGE:", "MUTANT", "WIRED:", "EXCLUDED")):
            print("  " + line.strip())
    return ok


def resolve_into_atom():
    """Point the resolver at every bank member, so nothing sits fabricated-but-unaddressed (S27)."""
    reg = json.load(open(REG))
    mem = (reg.get("muhl_bank") or {}).get("members") or []
    if not mem: return 0
    p = os.path.join(HERE, "pfc_atom.py")
    src = open(p, encoding="utf-8", newline="").read()
    missing = [m for m in mem if ('"%s"' % m) not in src]
    if not missing: return 0
    entries = ",\n                    ".join('"%s"' % m for m in missing)
    src = src.replace('    "winner_lane": [',
                      '    "winner_lane": [%s,\n                    ' % entries, 1)
    open(p, "w", encoding="utf-8", newline="").write(src)
    return len(missing)


def drive(dry=False):
    nodes = lane_nodes()
    if not nodes:
        print("no lane nodes with the win|latch[32] interface."); return 1
    print("FOUNDRY DRIVE — search, spawn, wire, verify. Scored by compute/tick ALONE (§63).\n")
    print("  %d lane node(s) present." % len(nodes))
    best, rows = search(nodes)
    ct, t, k, d, g, rep = best
    single = [r for r in rows if r[2] == 1]
    print("\n  SEARCH over %d topology/count combinations:" % len(rows))
    for r in sorted(rows, reverse=True)[:5]:
        print("    %-16s k=%-3d DEPTH %-7s replicas %-4d compute/tick %12.4f"
              % (r[1], r[2], "{:,}".format(r[3]), r[5], r[0]))
    print("\n  CHOSEN: %s over %d nodes -> DEPTH %s, %s gates, %d replicas, compute/tick %.4f"
          % (t, k, "{:,}".format(d), "{:,}".format(g), rep, ct))
    if single:
        print("  vs a single node: %.2fx" % (ct / max(single[0][0], 1e-9)))
    if dry:
        print("\n  --dry: nothing written."); return 0

    made = spawn(k, len(nodes))
    print("\n  WIRE:")
    ok = wire()
    added = resolve_into_atom()
    reg = json.load(open(REG))
    b = reg.get("muhl_bank") or {}
    print("  RESOLVER: %d member(s) added to pfc_atom" % added)
    with open("C:/llm/models/titan.gguf", "rb") as f: valid = f.read(4) == b"GGUF"
    print("\n  RESULT: bank %s · %d member(s) · bank DEPTH %s · GGUF-valid %s"
          % ("registered" if ok else "NOT registered", len(b.get("members") or []),
             "{:,}".format(int(b.get("bank_depth") or 0)), valid))
    if b.get("members"):
        achieved = L.compute_per_tick(int(b["gates_total"]) // len(b["members"]),
                                      int(b["bank_depth"]), True) * len(b["members"])
        print("  ACHIEVED compute/tick: %.4f  (%d nodes spawned this run)" % (achieved, made))
    return 0 if ok else 1


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(drive("--dry" in sys.argv))
