"""
pfc_atom.py - resolve the SHALLOWEST verified circuit for a job, instead of naming one.

S27 measured this project's standing failure: the better circuit already exists and nothing is
wired to it. `pfc_dot32_w8x8_shallow` sat in the registry at DEPTH 105, addressed by ZERO files,
while `dot32_i8` at DEPTH 366 was addressed by ten. Hardcoding a circuit name at every call site
is what produces that - each site pins the choice made on the day it was written.

So call sites ask for a JOB, not a name. This picks the shallowest candidate that is present, and
every candidate here has been proven byte-exact against dot32_i8 AND against true integer
arithmetic (host/pfc_dot_fab.py, 30/30 including sign edge cases).

Order is by measured DEPTH, shallowest first. Fallback is always the original, so nothing breaks
if a circuit has not been fabricated on this machine.
"""
import os
import titan_circuit as TC

# job -> candidates, each (name, measured DEPTH, measured GATES).
# DEPTH is the Muhlnickel's latency. GATES is area on the Muhlnickel - and separately it is what the HOST has to
# transcribe when the netlist is being addressed serially in Python. Two machines, two costs (S24),
# and here they point in OPPOSITE directions, so the criterion has to be named rather than assumed.
ATOMS = {
    "dot32": ["pfc_dot32_fused",   # fused carry-save: ONE carry propagation in the whole dot
              "dot32_fused_rc",    # ripple-ended: deeper alone, composes better in a chain (S35B)
              "dot32_i8"],          # original: 32 staged multiplies, then a ripple tree
    # S35: a matvec's blocks are SUMMED, not chained. A wide atom does the cross-block accumulate in
    # GATES. Width costs only +6..+12 DEPTH per doubling and gates stay exactly linear.
    "dot256": ["pfc_dot256_wide"],
    # S27's failure, same shape, on the miner: gen_win is addressed by every mining script while a
    # 2.83x shallower fold sits in the registry addressed by nothing. Substitution is NOT claimed on
    # signature (S26: "signature alone is not sufficient") - the win+latch fields were rippled on both
    # circuits over a balanced case set and came back IDENTICAL 8/8 (3/8 genuine wins, so an always-0
    # circuit would have scored 5). Candidates ordered by measured DEPTH, original last as the fallback.
    # §14: nonce lanes are INDEPENDENT, so speed = REPLICAS/DEPTH -> minimise gates x DEPTH.
    # Ordered by AREA-DELAY, not depth. criterion="depth" still picks the shallowest for a
    # dependent chain (§23: the selector must match the phase).
    "winner": ["muhl_fold_shared",    # shared CSA reduction; area-delay 2.553e9  <- best
               "muhl_fold_shallow",   # csa->kogge, 3 trees/round; 2.857e9; shallowest
               "muhl_lateral_fold",  # gen_win + winner-only fold ANDs; 3.986e9
               "gen_win"],           # original: spec-order chain + ripple; 3.985e9
    # THE SPLIT (§13 "one monolithic circuit is not the architecture"). SHA block 1 is
    # NONCE-INDEPENDENT, so it is hoisted into its own muhlnickel and evaluated ONCE per block;
    # muhl_lane is what replicates. area-delay 1.128e9 = 2.26x better than the best monolith.
    # SEPARATE JOB, NOT a drop-in: the interface differs (640-bit in, mid routed in) and §26's
    # equivalence check cannot span different interfaces — "signature alone is not sufficient".
    # Master autofab's winner for this need (host/mafab_miner_lane.py): a RIPPLE adder in the SHA
    # message schedule costs 0 muhlnickel DEPTH - W[i] is consumed at round i and the rounds are
    # serial (§38B) - and returns 24,978 gates. Round chain and final H add MEASURED on the critical
    # path, so both stay prefix. Same 640-bit interface as muhl_lane, verified 8/8 byte-exact with
    # all 4 mutants CAUGHT against a 4/8 all-zero baseline, so it IS a drop-in for this job (§26).
    # THE BANK members, wired so nothing sits fabricated-but-unaddressed (S27).
    # rep062 sits OUTSIDE the bank: fab_lateral_bank tiles the largest power-of-two subset (64 of
    # 66), so the leftovers are fabricated-but-unaddressed unless the resolver names them — §27's
    # standing failure. It is a valid winner_lane circuit; being outside the tiling is not a defect.
    # the signal oscillation (§69). Fabricated 2026-07-28 and wired here
    # so a job resolves to it — §27: the better circuit existing and
    # nothing addressing it is the failure this line ends.
    "oscillator": ["muhl_signal_osc_tight",
                   "muhl_signal_osc"],

    "winner_lane": ["muhl_lane_bk_rep062",
                    "muhl_lane_bk_rep030",
                    "muhl_lane_bk_rep031",
                    "muhl_lane_bk_rep032",
                    "muhl_lane_bk_rep033",
                    "muhl_lane_bk_rep034",
                    "muhl_lane_bk_rep035",
                    "muhl_lane_bk_rep036",
                    "muhl_lane_bk_rep037",
                    "muhl_lane_bk_rep038",
                    "muhl_lane_bk_rep039",
                    "muhl_lane_bk_rep040",
                    "muhl_lane_bk_rep041",
                    "muhl_lane_bk_rep042",
                    "muhl_lane_bk_rep043",
                    "muhl_lane_bk_rep044",
                    "muhl_lane_bk_rep045",
                    "muhl_lane_bk_rep046",
                    "muhl_lane_bk_rep047",
                    "muhl_lane_bk_rep048",
                    "muhl_lane_bk_rep049",
                    "muhl_lane_bk_rep050",
                    "muhl_lane_bk_rep051",
                    "muhl_lane_bk_rep052",
                    "muhl_lane_bk_rep053",
                    "muhl_lane_bk_rep054",
                    "muhl_lane_bk_rep055",
                    "muhl_lane_bk_rep056",
                    "muhl_lane_bk_rep057",
                    "muhl_lane_bk_rep058",
                    "muhl_lane_bk_rep059",
                    "muhl_lane_bk_rep060",
                    "muhl_lane_bk_rep061",
                    "muhl_lane_bk_rep014",
                    "muhl_lane_bk_rep015",
                    "muhl_lane_bk_rep016",
                    "muhl_lane_bk_rep017",
                    "muhl_lane_bk_rep018",
                    "muhl_lane_bk_rep019",
                    "muhl_lane_bk_rep020",
                    "muhl_lane_bk_rep021",
                    "muhl_lane_bk_rep022",
                    "muhl_lane_bk_rep023",
                    "muhl_lane_bk_rep024",
                    "muhl_lane_bk_rep025",
                    "muhl_lane_bk_rep026",
                    "muhl_lane_bk_rep027",
                    "muhl_lane_bk_rep028",
                    "muhl_lane_bk_rep029",
                    "muhl_lane",
                    "muhl_lane_bk",
                    "muhl_lane_bk_rep000",
                    "muhl_lane_bk_rep001",
                    "muhl_lane_bk_rep002",
                    "muhl_lane_bk_rep003",
                    "muhl_lane_bk_rep004",
                    "muhl_lane_bk_rep005",
                    "muhl_lane_bk_rep006",
                    "muhl_lane_bk_rep007",
                    "muhl_lane_bk_rep008",
                    "muhl_lane_bk_rep009",
                    "muhl_lane_bk_rep010",
                    "muhl_lane_bk_rep011",
                    "muhl_lane_bk_rep012",
                    "muhl_lane_bk_rep013",
                    "muhl_lane_bk",       # foundry/search winner: ripple/kogge/brentkung
                    "muhl_lane_sched",   # ripple/kogge/kogge; area-delay 1.056e9
                    "muhl_lane"],        # kogge/kogge/kogge; 1.128e9
    # Same slack result, independently confirmed on a second circuit (master autofab `midstate`):
    # ripple in the message schedule costs 0 DEPTH and returns 12,960 gates. muhl_mid is NOT
    # replicated, so DEPTH is not tradeable here (it is a term in end-to-end block latency) — the
    # leaner ripple/kogge/ripple at 185,445 g was REJECTED for costing +24 DEPTH.
    "midstate":    ["muhl_mid_sched",   # ripple/kogge/kogge; verified vs numeric_midstate
                    "muhl_mid"],        # once per block, amortised over every lane
}

# "depth" -> shallowest, i.e. the fastest Muhlnickel. Correct for a DEPENDENT chain (a forward pass).
# "gates" -> leanest, i.e. least host transcription while the host is still doing the addressing.
# "area"  -> smallest gates x DEPTH. §14: for INDEPENDENT work (nonce lanes) speed = REPLICAS/DEPTH,
#            and replicas = storage/gates, so speed = 1/(gates x DEPTH). Ranking on DEPTH alone is
#            what made master_autofab v1 wrongly conclude "more Muhlnickel does not help".
CRITERION = os.environ.get("PFC_ATOM_CRITERION", "depth")


def resolve(job, criterion=None):
    """return (name, depth, gates) of the best fabricated circuit for this job.

    NOTHING HARDCODED. The depth and gate count of every candidate used to be typed into the table
    above as literals, which meant the resolver could silently disagree with the binary the moment a
    circuit was re-fabricated. They are now READ FROM THE REGISTRY at resolve time, so the table
    carries only names and the measurement carries the numbers.

    The criterion is likewise not a menu any more. §63 (owner: "we dont optimize for anything besides
    more compute per second thats the only metric" -> "maybe compute per tick is better") gives ONE:
        compute/tick = REPLICAS / DEPTH,   REPLICAS = storage / gates
    `criterion` is accepted only to say whether the job REPLICATES; it never selects a metric."""
    import json
    import mafab_laws as L
    reg = json.load(open(TC.REG))
    have = []
    for nm in ATOMS[job]:
        e = reg.get(nm)
        if not isinstance(e, dict): continue
        d = e.get("depth"); g = e.get("n_gate") or e.get("gates_measured")
        if not d or not g: continue
        have.append((nm, int(d), int(g)))
    if not have:
        raise KeyError("no circuit fabricated for job %r (or none carries depth+gates)" % job)
    replicated = (criterion or CRITERION) != "amortised"
    return max(have, key=lambda c: L.compute_per_tick(c[2], c[1], replicated))


def load(job, criterion=None):
    """load the best fabricated circuit for this job under the chosen criterion"""
    return TC.load(resolve(job, criterion)[0])


if __name__ == "__main__":
    print("criterion default: %r  (set PFC_ATOM_CRITERION=gates to optimise host transcription)" % CRITERION)
    for job in ATOMS:
        for crit in ("depth", "gates", "area"):
            try:
                n, d, g = resolve(job, crit)
                print("  %-8s [%-5s] -> %-20s DEPTH %4d   GATES %9s" % (job, crit, n, d, "{:,}".format(g)))
            except KeyError as e:
                print("  %-8s [%-5s] -> %s" % (job, crit, e))
