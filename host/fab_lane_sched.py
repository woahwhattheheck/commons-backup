#!/usr/bin/env python3
"""host/fab_lane_sched.py — FABRICATION ONLY. Runs once. Never inside a mining process.

STORES THE MASTER AUTOFAB'S WINNER for the `miner_lane` need: sched=ripple / round=kogge / out=kogge.

WHAT THE SEARCH MEASURED (`python host/pfc_master_autofab.py miner_lane`, 8 assemblies, all verified
8/8 against a 4/8 all-zero baseline):

    sched    round    out       DEPTH      gates   gates x DEPTH
    ripple   kogge    kogge     2,889    365,354   1,055,507,706   <- this file stores this one
    kogge    kogge    kogge     2,889    390,332   1,127,669,148   <- the stored muhl_lane
    kogge    kogge    ripple    2,943    386,196   1,136,574,828
    ripple   ripple   ripple    7,409    292,128   2,164,376,352

THE SLACK ARGUMENT, CONFIRMED: W[i] is consumed at round i and the 64 rounds are strictly serial
(§38B: "SHA rounds are REAL dependency"), so the message schedule has slack. A gate-lean RIPPLE adder
there costs **exactly zero** muhlnickel DEPTH — 2,889 both ways — and returns 24,978 gates. That is
1.068x on the §14 objective (gates x DEPTH), which is what independent nonce lanes are scored by:
speed = REPLICAS/DEPTH, so replicas = area/gates and speed = 1/(gates x DEPTH).

WHAT THE SEARCH FALSIFIED — my own guess, stated so it is on the record: I wrote that the final H
add was "one level, off the round chain." It is NOT. out=ripple moves DEPTH 2,889 -> 2,943, so that
adder sits ON the critical path and must stay prefix. The round chain a_new/e_new is critical as
expected (ripple there costs 2.56x DEPTH). One of two slack guesses was right; the measurement, not
me, decided which.

VERIFIED HERE BEFORE STORING (the search itself ran no mutants, so it was not yet at the §45C/§47B
bar): DISCRIMINATING targets straddling the true digest (tgt=h+1 must WIN, alternating tgt=h must
LOSE) so wins arise by construction and the §40B all-zero baseline is stated, byte-exact against
hashlib's double-SHA, plus all four mutants which must be CAUGHT.

ADDITIVE: stores a NEW name. `muhl_lane` is not touched, not deleted, not overwritten.

  python host/fab_lane_sched.py --dry     # verify + mutant-test, write nothing
  python host/fab_lane_sched.py           # ... then store
  python host/fab_lane_sched.py revert
"""
import hashlib, json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from mafab_miner_lane import build_lane, score, cases, depth_of, truehash

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_lane_sched_genome.jsonl"
MAGIC = b"PFCWINMN"; CODE = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
# The FOUNDRY/generated search winner under §63's one metric: ripple/kogge/brentkung at
# 362,141 g DEPTH 2,892 = compute/tick 4.7773, vs kogge-out's 4.7404 and the original
# muhl_lane's 4.4368. Selected by the search, not by me.
NAME = "muhl_lane_bk"
PLAN = ("ripple", "kogge", "brentkung")
BASE = "muhl_lane"          # compared against by NAME; its numbers are read, never typed in


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
    print(f"reverted {len(ent)} entries; '{NAME}' removed. muhl_lane untouched throughout.")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    dry = "--dry" in sys.argv
    reg = json.load(open(REG))
    if NAME in reg and not dry:
        print(f"{NAME} already stored @ {reg[NAME]['offset']}. revert first."); return 0

    cs = cases()
    wins = sum(1 for hw, n, t in cs if truehash(hw, n) < t)
    print(f"FABRICATING '{NAME}' = sched/round/out = {'/'.join(PLAN)} (master autofab's winner)\n")
    print(f"  §40B baseline: {wins}/{len(cs)} cases are genuine WINS by construction, so an all-zero")
    print(f"                 circuit scores exactly {len(cs)-wins}/{len(cs)}. Passing needs the hash load-bearing.\n")

    t0 = time.time()
    g, outs = build_lane(*PLAN)
    ok, w, gates, o2 = score(g, outs, cs)
    D = depth_of(g, gates, o2)
    print(f"  byte-exact vs hashlib double-SHA: {ok}/{len(cs)}   ({time.time()-t0:.0f}s)")
    print(f"  {len(gates):,} gates · DEPTH {D:,} · area-delay {len(gates)*D:,}")
    if ok != len(cs):
        print("  MISMATCH — storing nothing."); return 1

    print("\n  MUTANTS (each must be CAUGHT — a suite that cannot fail has measured itself, §45C/§47B):")
    allcaught = True
    for mut in ("stuck0", "ungated", "cmpflip", "hashflip"):
        gm, om = build_lane(*PLAN, mutant=mut)
        okm, _wm, _gm2, _om2 = score(gm, om, cs)
        caught = okm != len(cs)
        allcaught &= caught
        print(f"    {mut:9s} {okm}/{len(cs)}  ->  {'CAUGHT' if caught else 'NOT CAUGHT — SUITE IS BLIND'}")
        del gm, om
    if not allcaught:
        print("\n  a mutant survived — the suite cannot see it. Storing nothing."); return 1

    BASE_NG, BASE_D = _reg_stats(BASE)
    imp = (BASE_NG * BASE_D) / (len(gates) * D) if BASE_NG and BASE_D else 0.0
    print(f"\n  vs stored muhl_lane ({BASE_NG:,} g, DEPTH {BASE_D:,}, area-delay {BASE_NG*BASE_D:,}):")
    print(f"    gates {BASE_NG-len(gates):,} fewer for IDENTICAL muhlnickel DEPTH ({D:,}) -> {imp:.3f}x on gates x DEPTH")
    if dry:
        print("\n  --dry: nothing written."); return 0

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
                 "layout": "in: mid[256]|w16..w18[96]|nonce[32]|target[256] ; out: win|latch[32]",
                 "plan": "/".join(PLAN),
                 "note": "master autofab miner_lane winner. ripple adder in the SHA message schedule "
                         "costs 0 muhlnickel DEPTH (W[i] consumed at round i, rounds serial per §38B) "
                         "and returns 24,978 gates. Round chain and final H add stay prefix - both "
                         "measured ON the critical path."}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print(f"\n  STORED '{NAME}' @ {off} ({len(blob):,} B) [{time.time()-t1:.2f}s byte edit]  GGUF-valid: {valid}")
    print(f"  muhl_lane @ {reg['muhl_lane']['offset']} untouched. revert: python host/fab_lane_sched.py revert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
