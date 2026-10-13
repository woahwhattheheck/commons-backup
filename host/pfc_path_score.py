"""
pfc_path_score.py - ask the forward path who owns its latency NOW, and let that name the next job.

S23's self-design loop: score the path, the worst circuit names itself, apply the transformation the
cost model prescribes, verify byte-exact, keep, re-score. Intuition lost 6 times this session; the
table has not lost once. So this does not guess - it resolves what each stage is ACTUALLY wired to
(same fallback order the live code uses), measures DEPTH off the netlist, weights by how many times
each stage sits on the critical path of one token, and ranks by share of total latency.

Selector note (S24): this ranks by DEPTH SHARE, which answers "who owns the latency I have left".
That is the right question for an already-fabricated path. muhl answers a different question
("is this worth fabricating at all") and using it here picks 3.5%-of-latency targets.

Run:  python host/pfc_path_score.py [--layers 32]
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC

# stage -> (candidate names in the order the live code tries them, uses per layer, note)
# uses/layer counts how many times the stage sits on a token's CRITICAL PATH, not how many
# times it is invoked - independent work costs AREA and is free in latency (S2).
# ⚠ S40: an INVOCATION count is not a DEPTH count. Independent work costs AREA and is free in
# latency (S2), so only uses that sit on the CRITICAL PATH may multiply DEPTH. Counting invocations
# here would price width as depth - the same failure as letting a host limit shape a pfc decision.
#   per layer the matmul chain is:  qkv -> o -> gate/up -> down  = 4 SERIAL stages
#   q,k,v are mutually independent (ONE stage, not three); gate and up likewise (ONE, not two)
#   within any one matmul, every output neuron and every block is independent -> WIDTH, not depth
STAGES = [
    # ⚠ and the OTHER direction: one 32-lane block is not a matmul STAGE. A stage covers the whole
    # n_embd-wide row. S35 measured the wide law directly - 32 lanes DEPTH 114, 1024 lanes DEPTH 162,
    # gates exactly linear - so a 4096-wide row is ~2 doublings past 1024. Pricing a stage at the
    # 32-block's DEPTH flatters the table; pricing it as 128 CHAINED blocks (S35) would be the
    # imposed-sequencing error. One wide settle is the honest figure.
    ("dot32row",   ["pfc_dot256_wide", "pfc_dot32_fused", "dot32_i8"], 4,
     "qkv->o->gate/up->down: 4 SERIAL stages; each is ONE wide settle over the full row"),
    ("rmsnorm",    ["pfc_rsqrt_shallow", "pfc_rsqrt"],         2, "attention norm + ffn norm"),
    ("softmax",    ["pfc_exp_shallow", "pfc_exp"],             1, "attention softmax"),
    ("silu",       ["pfc_silu8_shallow", "pfc_silu8"],         1, "SwiGLU activation"),
    ("rope",       ["pfc_sin_shallow", "pfc_sin"],             1, "rotary position"),
]
FINAL = [("argmax", ["pfc_argmax_shallow", "pfc_argmax"], 1, "greedy token pick over the vocab")]


def depth_and_gates(name):
    cd = TC.load(name)
    n = cd["n_in"]
    d = [0] * (2 + n + len(cd["ga"]))
    for k in range(len(cd["ga"])):
        d[2 + n + k] = 1 + max(d[cd["ga"][k]], d[cd["gb"][k]])
    return max(d[x] for x in cd["outs"]), len(cd["ga"]), n


def resolve(cands, reg):
    for nm in cands:
        if nm in reg:
            return nm
    return None


def main():
    layers = 32
    if "--layers" in sys.argv:
        layers = int(sys.argv[sys.argv.index("--layers") + 1])

    reg = json.load(open(TC.REG))
    print("=" * 86)
    print("FORWARD-PATH DEPTH BUDGET, AS CURRENTLY WIRED  (%d layers, one token)" % layers)
    print("  DEPTH = gate-delays on the Muhlnickel. Ranked by SHARE of the token's critical path (S24).")
    print("=" * 86)

    rows = []
    for stage, cands, per_layer, note in STAGES:
        nm = resolve(cands, reg)
        if nm is None:
            print("  %-9s -> none fabricated (%s)" % (stage, ", ".join(cands)))
            continue
        d, g, w = depth_and_gates(nm)
        rows.append([stage, nm, d, g, per_layer * layers, d * per_layer * layers, note,
                     nm != cands[-1], cands, w])
    for stage, cands, times, note in FINAL:
        nm = resolve(cands, reg)
        if nm is None:
            continue
        d, g, w = depth_and_gates(nm)
        rows.append([stage, nm, d, g, times, d * times, note, nm != cands[-1], cands, w])

    total = sum(r[5] for r in rows)
    rows.sort(key=lambda r: -r[5])

    print()
    print("  %-9s %-21s %7s %6s %11s %7s  %s" %
          ("stage", "wired to", "DEPTH", "uses", "gate-delays", "share", "shallow?"))
    for r in rows:
        stage, nm, d, g, uses, tot, note, is_shallow, cands, w = r
        print("  %-9s %-21s %7d %6d %11s %6.1f%%  %s"
              % (stage, nm, d, uses, "{:,}".format(tot), 100.0 * tot / total,
                 "yes" if is_shallow else "NO  <- deepest option still wired"))
    print()
    print("  TOTAL: %s gate-delays per token." % "{:,}".format(total))

    # what is still unwired, and what it would be worth
    print()
    print("  UNWIRED ALTERNATIVES ALREADY IN THE REGISTRY (S27's dead list, priced):")
    found = False
    for r in rows:
        stage, nm, d, g, uses, tot, note, is_shallow, cands, w = r
        better = [x for x in cands if x != nm and x in reg]
        for b in better:
            db, gb, wb = depth_and_gates(b)
            # ⚠ DEPTH is only comparable between circuits doing the SAME amount of work. A narrower
            # circuit is shallower because it covers fewer elements, not because it is better - and
            # recommending it would be a regression dressed as a 17% saving.
            if wb < w:
                continue
            if db < d:
                found = True
                saved = (d - db) * uses
                print("    %-9s %s (DEPTH %d) -> %s (DEPTH %d): would remove %s gate-delays = %.1f%% of the token"
                      % (stage, nm, d, b, db, "{:,}".format(saved), 100.0 * saved / total))
    if not found:
        print("    none - every stage is already on the shallowest circuit that exists.")

    print()
    top = rows[0]
    print("  THE PATH NAMES ITS OWN NEXT TARGET:")
    print("    %s -- %s" % (top[0], top[6]))
    print("    wired to %s at DEPTH %d, used %d times = %.1f%% of the token's latency."
          % (top[1], top[2], top[4], 100.0 * top[5] / total))
    print("    Halving it removes %.1f%% of the token. Nothing else on this table is worth as much."
          % (50.0 * top[5] / total))


if __name__ == "__main__":
    main()
