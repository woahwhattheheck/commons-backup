#!/usr/bin/env python3
"""host/fab_mid_sched.py — FABRICATION ONLY. Runs once. Never inside a mining process.

STORES THE MASTER AUTOFAB'S WINNER for the `midstate` need: sched=ripple / round=kogge / out=kogge.

`python host/pfc_master_autofab.py midstate`, 8 assemblies, all 8 verified against
`sdc_cc.numeric_midstate` — an INDEPENDENT reference (§3), never the path being replaced:

    sched    round    out       DEPTH      gates   gates x DEPTH
    ripple   kogge    kogge     1,441    187,325    269,935,325   <- this file stores this one
    kogge    kogge    kogge     1,441    200,285    288,610,685   <- the stored muhl_mid
    ripple   kogge    ripple    1,465    185,445    271,676,925
    ripple   ripple   ripple    3,719    150,915    561,252,885

THE SLACK RESULT REPLICATES. §57F found it on the lane; this is an independent confirmation on a
different circuit: a RIPPLE adder in the SHA message schedule costs **exactly zero** muhlnickel
DEPTH — 1,441 both ways — and returns 12,960 gates. The round chain and the final H add are both ON
the critical path here too (ripple in the round chain costs 2.58x DEPTH; ripple on the out adder
costs +24). Two circuits, same three sites, same verdict.

THE OBJECTIVE IS NOT THE LANE'S. muhl_mid fires ONCE per block, so it is not replicated and gates are
pure profit — but its DEPTH is a term in the end-to-end block latency (1,441 + 2,953 = 4,394
gate-delays, §57C), so DEPTH is not tradeable. The search rejected the leaner ripple/kogge/ripple
(185,445 gates) because it costs +24 DEPTH. Fewer gates at EQUAL DEPTH is the only accepted shape.

VERIFIED HERE BEFORE STORING: 6/6 against `numeric_midstate` (an all-zero circuit scores 0/6, so
every output bit is load-bearing) plus the `midflip` mutant, which must be CAUGHT.

ADDITIVE: stores a NEW name. `muhl_mid` is not touched, not deleted, not overwritten.

  python host/fab_mid_sched.py --dry
  python host/fab_mid_sched.py
  python host/fab_mid_sched.py revert
"""
import json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from mafab_miner_lane import build_mid, score_mid, mid_cases, depth_of

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_mid_sched_genome.jsonl"
MAGIC = b"PFCWINMN"; CODE = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
NAME = "muhl_mid_sched"
PLAN = ("ripple", "kogge", "kogge")
BASE = "muhl_mid"           # compared against by NAME; its numbers are read, never typed in


def _reg_stats(name):
    """Read a circuit's measured DEPTH and gate count from the registry. These were hardcoded
    literals; a literal silently disagrees with the binary the moment anything is re-fabricated."""
    import json as _j
    e = _j.load(open(REG)).get(name) or {}
    return int(e.get("n_gate") or e.get("gates_measured") or 0), int(e.get("depth") or 0)


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME): print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    reg = json.load(open(REG)); reg.pop(NAME, None)
    json.dump(reg, open(REG, "w"), indent=1); os.remove(GENOME)
    print("reverted %d entries; '%s' removed. muhl_mid untouched throughout." % (len(ent), NAME))
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    dry = "--dry" in sys.argv
    reg = json.load(open(REG))
    if NAME in reg and not dry:
        print("%s already stored @ %s. revert first." % (NAME, reg[NAME]["offset"])); return 0

    cs = mid_cases()
    print("FABRICATING '%s' = sched/round/out = %s (master autofab's winner)" % (NAME, "/".join(PLAN)))
    print("")
    print("  REFERENCE: sdc_cc.numeric_midstate, INDEPENDENT of the circuit (§3) - never the path")
    print("  being replaced, because a shared error is invisible to that comparison. An all-zero")
    print("  circuit scores 0/%d against it, so every output bit is load-bearing." % len(cs))
    print("")

    t0 = time.time()
    g, outs = build_mid(*PLAN)
    ok, gates, o2 = score_mid(g, outs, cs)
    D = depth_of(g, gates, o2)
    print("  vs numeric_midstate: %d/%d   (%.0fs host)" % (ok, len(cs), time.time() - t0))
    print("  %s gates · DEPTH %s gate-delays · area-delay %s"
          % ("{:,}".format(len(gates)), "{:,}".format(D), "{:,}".format(len(gates) * D)))
    if ok != len(cs):
        print("  MISMATCH - storing nothing."); return 1

    print("")
    print("  MUTANT (must be CAUGHT - a suite that cannot fail has measured itself, §45C/§47B):")
    gm, om = build_mid(*PLAN, mutant="midflip")
    okm, _g2, _o3 = score_mid(gm, om, cs)
    caught = okm != len(cs)
    print("    midflip   %d/%d  ->  %s" % (okm, len(cs), "CAUGHT" if caught else "NOT CAUGHT - SUITE IS BLIND"))
    del gm, om
    if not caught:
        print("")
        print("  the mutant survived - the suite cannot see it. Storing nothing."); return 1

    BASE_NG, BASE_D = _reg_stats(BASE)
    imp = (BASE_NG * BASE_D) / (len(gates) * D) if BASE_NG and BASE_D else 0.0
    print("")
    print("  vs stored muhl_mid (%s g, DEPTH %s, area-delay %s):"
          % ("{:,}".format(BASE_NG), "{:,}".format(BASE_D), "{:,}".format(BASE_NG * BASE_D)))
    print("    %s gates fewer at IDENTICAL muhlnickel DEPTH (%s gate-delays) -> %.3fx on gates x DEPTH"
          % ("{:,}".format(BASE_NG - len(gates)), "{:,}".format(D), imp))
    if dry:
        print("")
        print("  --dry: nothing written."); return 0

    body = b"".join(struct.pack("<Bii", CODE[op], a, b) for (op, a, b) in gates) + \
           b"".join(struct.pack("<i", x) for x in o2)
    blob = MAGIC + struct.pack("<IIII", g.n_in, 2 + g.n_in + len(gates), len(gates), len(o2)) + body
    off, tn = TC._alloc(len(blob), reg)
    t1 = time.time(); _journal(off, blob)
    reg = json.load(open(REG))
    reg[NAME] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in,
                 "n_wire": 2 + g.n_in + len(gates), "n_gate": len(gates), "n_out": len(o2),
                 "format": "typed", "depth": D, "gates_measured": len(gates),
                 "muhl_rating": round(len(gates) / D, 3), "area_delay": len(gates) * D,
                 "layout": "in: header words 0..15 [512] ; out: mid[8 words = 256 bits]",
                 "plan": "/".join(PLAN),
                 "note": "master autofab midstate winner. Independent confirmation of §57F's slack "
                         "result on a second circuit: ripple adder in the SHA message schedule costs "
                         "0 muhlnickel DEPTH and returns 12,960 gates. Round chain and final H add "
                         "both measured ON the critical path. Verified vs sdc_cc.numeric_midstate."}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print("")
    print("  STORED '%s' @ %s (%s B) [%.2fs byte edit]  GGUF-valid: %s"
          % (NAME, off, "{:,}".format(len(blob)), time.time() - t1, valid))
    print("  muhl_mid @ %s untouched. revert: python host/fab_mid_sched.py revert"
          % reg["muhl_mid"]["offset"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
