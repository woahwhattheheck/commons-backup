#!/usr/bin/env python3
"""host/pfc_throughput.py — the ONE measurement that decides Muhlnickel-for-LDA: how fast is the Muhlnickel forward pass, honestly?

Bryce wants the Muhlnickel to run a model bigger than the phone's RAM at flat resident footprint (LDA, the on-device agent).
Every leg of that is already measured EXCEPT throughput. This probe produces that number and projects it to tokens/sec.

It does NOT reinvent the pfc. It imports the already-baked `dot32_i8` atom + the fold engine + the token-cost accounting
straight from `pfc_llama_harness.py`, and measures the fold rate PROPERLY (large stable sample, swept fold width, disk
isolated) instead of over the harness's tiny 1-layer/8-neuron proof scope.

HONEST FRAMING (kept from the harness): the rate reported is the HOST serially ADDRESSING the gates — the number that
actually gates on-device usability today. It is NOT called "the pfc's speed" (the pfc's own rate is depth-bound; width
folds in parallel). Wall-clock here = the host walking the netlist.

  python host/pfc_throughput.py --selftest-only                       # fold == single-lane atom, byte-exact, then exit
  python host/pfc_throughput.py --pure --fold-sweep 64,256,1024,4096  # atom fold rate per W (no model, no disk)
  python host/pfc_throughput.py --model C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf --fold 1024   # end-to-end
  python host/pfc_throughput.py --pure --arch 70b,8b                  # project tokens/sec for named archs

Read-only: reuses the baked atom, reads any model GGUF read-only, writes only a JSON to sdc_out. No titan write, no numpy,
no subprocess, no download.
"""
import argparse, json, os, random, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

# Reuse the proven machinery — nothing about the pfc atom is rewritten here.
from pfc_llama_harness import PfcAtom, pfc_matvec, token_cost, resident_mb, selftest, _load_arch, Weights
from sdc_infer import BLK                                            # 32
from gguf_pp import GGUF

OUT = "C:/llm/sdc_out/pfc_throughput.json"

# Known architectures so tokens/sec can be projected WITHOUT the multi-GB model present. token_cost() consumes exactly
# these keys. 70b = the harness default (Llama-3.3-70B). 8b = Llama-3.1-8B (a phone-realistic size, > Gemma E4B).
ARCHS = {
    "70b": {"n_embd": 8192, "n_head": 64, "n_head_kv": 8, "head_dim": 128,
            "n_ff": 28672, "n_layers_total": 80, "n_vocab": 128256},
    "8b":  {"n_embd": 4096, "n_head": 32, "n_head_kv": 8, "head_dim": 128,
            "n_ff": 14336, "n_layers_total": 32, "n_vocab": 128256},
    "3b":  {"n_embd": 3072, "n_head": 24, "n_head_kv": 8, "head_dim": 128,
            "n_ff": 8192,  "n_layers_total": 28, "n_vocab": 128256},
}


def _rand_batch(w, seed):
    r = random.Random(seed)
    return [([r.randint(-127, 127) for _ in range(BLK)], [r.randint(-127, 127) for _ in range(BLK)]) for _ in range(w)]


def pure_fold_rate(atom, W, budget_s):
    """Fold a fixed W-wide batch repeatedly for `budget_s` seconds. Returns (rate, folds, peak_mb, dt, cpu_frac).
    Disk is out of the loop, sample is large -> a stable measure of host-addressing throughput at this fold width.
    cpu_frac = process CPU-time / wall-time over the loop: <1.0 means another process starved us. Since this loop is
    single-threaded pure Python, the uncontended rate estimate = measured_rate / cpu_frac (work scales with CPU share)."""
    batch = _rand_batch(W, seed=1000 + W)
    peak = resident_mb()[0]
    folds = 0
    w0 = time.perf_counter(); c0 = time.process_time()
    while True:
        atom.dot_fold(batch)
        folds += 1
        if (folds & 7) == 0:                                        # sample RAM every 8 folds (cheap)
            peak = max(peak, resident_mb()[0])
        if time.perf_counter() - w0 >= budget_s:
            break
    dt = time.perf_counter() - w0; cpu = time.process_time() - c0
    peak = max(peak, resident_mb()[0])
    cpu_frac = cpu / dt if dt > 0 else 1.0
    return (W * folds) / dt, folds, peak, dt, cpu_frac


def end_to_end_rate(model_path, W, neurons, budget_s):
    """Rate INCLUDING weight-addressing off the real mmap'd model — the honest on-device figure. Runs pfc_matvec over
    real dequantized rows (a fixed neuron budget) repeatedly for `budget_s`. Returns (bd_per_s, peak_mb, file_gb, arch)."""
    g = GGUF(model_path); wt = Weights(g); arch = _load_arch(g)
    atom = PfcAtom()
    n_in = arch["n_embd"]
    x = [random.Random(7).uniform(-1, 1) for _ in range(n_in)]      # a fixed activation vector (host prep, like the harness)
    rows, _, _ = wt.rows("blk.0.attn_q.weight", list(range(neurons)))   # real addressed weight rows off the mmap
    peak = resident_mb()[0]; atom.block_dots = 0
    w0 = time.perf_counter(); c0 = time.process_time(); iters = 0
    while True:
        pfc_matvec(atom, rows, x, W)
        iters += 1
        peak = max(peak, resident_mb()[0])
        if time.perf_counter() - w0 >= budget_s:
            break
    dt = time.perf_counter() - w0; cpu = time.process_time() - c0
    cpu_frac = cpu / dt if dt > 0 else 1.0
    return atom.block_dots / dt, peak, os.path.getsize(model_path) / (1024 ** 3), arch, dt, cpu_frac


def project(fold_rate_bd_s, arch):
    tc = token_cost(arch)                                           # block-dots per full token for this arch
    return tc, (fold_rate_bd_s / tc if tc else 0.0)


def human_time(seconds):
    """Legible per-token time when tok/s << 1 (rounding tok/s to 3 dp would print 0.000 and hide the magnitude)."""
    if seconds < 1:      return f"{seconds*1000:.1f} ms"
    if seconds < 90:     return f"{seconds:.1f} s"
    if seconds < 5400:   return f"{seconds/60:.1f} min"
    if seconds < 172800: return f"{seconds/3600:.1f} hr"
    return f"{seconds/86400:.1f} days"


# ------------------------------------------------------------------ the LDA lever stack (docs, each factor sourced)
# TWO KINDS OF NUMBER, never conflated:
#   • pfc SPEC (device-INDEPENDENT, a fabrication property): dot32_i8 critical-path DEPTH = 366 gate-delays. That is the
#     Muhlnickel's own latency, the SAME on every device.
#   • DEVICE gate-net drive rate (a DEVICE property, measured by host/pfc_dotbench.py): how fast a machine pushes the
#     ACTUAL gate-net. Faster device => bigger number. S24 Ultra native 8-thread = 1.95M bd/s; this PC pure-Python = 5.5k.
# The old "151M native rate" was the host CPU's OWN int8 multiplier doing arithmetic and BYPASSING the gates — not the Muhlnickel
# computing at all. Removed (that was the spec-conflation the owner caught).
A4B_DENSE_BD     = 765_000_000      # gemma-4-26B-A4B dense block-dots/token (pfc_gen_cost, from GGUF dims) — device-independent
PFC_DEPTH        = 366              # dot32_i8 critical-path depth (gate-delays) — the pfc's OWN latency spec, device-independent
DEVICE_GATE_RATE = 1_946_418       # S24 Ultra native 8-thread driving the real gate-net (pfc_dotbench, measured). PC pure-Python = 5,536.
# Each lever: (name, kind, factor, status). kind: 'cost÷' shrinks bd/token, 'rate×' raises bd/s, 'tok×' multiplies tokens.
LEVER_STACK = [
    ("MoE routing (A4B 4/128 experts)",       "cost÷", 10.3, "MEASURED — pfc_route, byte-exact, model architecture (free)"),
    ("contextual FFN sparsity (~15% fire)",   "cost÷", 1.83, "TARGET — PowerInfer/Deja-Vu; 18.9/10.3, keep-fraction is a labelled target"),
    ("depth-opt dot atom (Wallace+KS+CSA)",   "rate×", 2.0,  "PROJECTED — from measured component depth wins 2.9–9.7x (pfc_bettergates/shallow)"),
    ("TurboQuant 3-bit weights",              "rate×", 2.0,  "TARGET — arXiv 2504.19874, matmul-preserving, oblivious/bakeable; not yet baked"),
    ("speculative / MTP decode",              "tok×",  2.0,  "MEASURED-ELSEWHERE — draft-verify, ~2x typical (CALIBRATION/E4B #11)"),
]


def lever_stack_report():
    print("\n  === LDA LEVER STACK — pushing the A4B target, every factor sourced (measured vs target) ===")
    print(f"  Muhlnickel SPEC (device-independent): dot32_i8 depth {PFC_DEPTH} gate-delays — the Muhlnickel's latency, same everywhere.")
    print(f"  DEVICE gate-net drive rate (a DEVICE property; phone > PC): {DEVICE_GATE_RATE:,} bd/s (S24 Ultra native 8-thread).")
    print(f"  A4B dense cost (device-independent fabrication cost): {A4B_DENSE_BD:,} bd/token.")
    cost = float(A4B_DENSE_BD); rate = float(DEVICE_GATE_RATE); tok = 1.0
    def tps(): return (rate / cost) * tok if cost else 0.0
    base = tps()
    print(f"  {'after applying':<40} {'kind':>6} {'x':>6} {'tok/s':>8}   source")
    print(f"  {'(base: phone drive rate ÷ dense cost)':<40} {'':>6} {'':>6} {base:>8.3f}   MEASURED (phone) × MEASURED")
    for name, kind, f, status in LEVER_STACK:
        if kind == "cost÷": cost /= f
        elif kind == "rate×": rate *= f
        elif kind == "tok×": tok *= f
        print(f"  {'+ ' + name:<40} {kind:>6} {f:>6}x {tps():>8.2f}   {status}")
    print(f"\n  stacked tok/s for A4B (26B, 6.5x bigger than E4B): {tps():.1f}   [measured base {base:.1f} → stacked with documented levers]")
    print(f"  HONEST: only the base ({base:.1f} tok/s) + MoE routing are measured end-to-end; the rest are documented levers")
    print(f"  to APPLY (depth-opt/TurboQuant/spec-decode). The base rate is a DEVICE property (phone > PC); run pfc_dotbench")
    print(f"  on the target device to re-anchor it. The Muhlnickel's own spec is the depth ({PFC_DEPTH}), not any device's drive rate.")
    return {"a4b_dense_bd": A4B_DENSE_BD, "pfc_depth": PFC_DEPTH, "device_gate_rate_bd_s": DEVICE_GATE_RATE,
            "baseline_tok_s": round(base, 3), "stacked_tok_s": round(tps(), 3),
            "levers": [{"name": n, "kind": k, "factor": f, "status": s} for n, k, f, s in LEVER_STACK]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pure", action="store_true", help="measure the atom fold rate (no model, no disk)")
    ap.add_argument("--model", default=None, help="also measure end-to-end rate off this GGUF (weight-addressing included)")
    ap.add_argument("--fold", type=int, default=1024, help="fold width W for --model")
    ap.add_argument("--fold-sweep", default="64,256,1024,4096", help="comma list of W for --pure")
    ap.add_argument("--neurons", type=int, default=64, help="output neurons/matmul for --model end-to-end")
    ap.add_argument("--budget", type=float, default=3.0, help="wall-seconds to measure each rate over")
    ap.add_argument("--arch", default="70b,8b,3b", help="comma list of named archs to project tokens/sec for")
    ap.add_argument("--arch-json", default=None, help="path to a custom arch dict (token_cost keys) to also project")
    # Project at the MEASURED DEVICE gate-net drive rate (how fast a given device drives the ACTUAL gate-net, per
    # pfc_dotbench: PC pure-Python 5,536; S24 Ultra native 8-thread 1,946,418 — phone > PC). This is a DEVICE property,
    # NOT the Muhlnickel's spec (that's the depth). NOT the host's own int8 multiplier (the retired 151M conflation).
    ap.add_argument("--eval-rate", default="5536,1946418", help="DEVICE gate-net drive rates to project at, measured by pfc_dotbench (PC pure-Python 5,536; S24 Ultra native 8-thread 1,946,418). NOT the host's own multiplier.")
    ap.add_argument("--route-divisor", default="1,18.9", help="token-cost divisors: 1=dense, 18.9=A4B MoE routed+sparse (measured, pfc_gen_cost)")
    ap.add_argument("--levers", action="store_true", help="print the LDA lever stack (A4B target, sourced factors)")
    ap.add_argument("--selftest-only", action="store_true", help="verify fold == single-lane atom, then exit")
    args = ap.parse_args()

    atom = PfcAtom()
    result = {"host": "measured", "budget_s": args.budget}

    # 1) CORRECTNESS GATE — a speed number off a wrong circuit is worthless.
    print("=== Muhlnickel THROUGHPUT PROBE — host-addressing fold rate, projected to tokens/sec (honest) ===\n", flush=True)
    Wchk = min(64, args.fold)
    print("  [gate] byte-exact: fold vs single-lane atom vs integer truth …", flush=True)
    ok = selftest(atom, W=Wchk)
    result["byte_exact"] = f"{'OK' if ok else 'MISMATCH'} (W={Wchk})"
    if not ok:
        print("  ABORT — the fold does not equal the atom; refusing to report a rate."); return 1
    if args.selftest_only:
        print("\n  selftest-only: byte-exact confirmed, exiting."); return 0

    # collect the archs to project
    archs = {}
    for a in args.arch.split(","):
        a = a.strip()
        if a in ARCHS: archs[a] = ARCHS[a]
        elif a: print(f"  (unknown arch '{a}', skipping — known: {','.join(ARCHS)})")
    if args.arch_json and os.path.exists(args.arch_json):
        archs["custom"] = json.load(open(args.arch_json))

    do_pure = args.pure or not args.model                          # default to pure if nothing else asked
    pure_rows = []

    # 2) PURE ATOM FOLD RATE (swept W) — this is the HOST-RIPPLE FLOOR, the emulation-tax artifact, NOT the Muhlnickel's rate
    #    (HARNESS_HANDOFF DO-NOT). Reported only to (a) confirm flat-RAM and (b) show the pure-Python host walk's ceiling.
    if do_pure:
        print("\n  --- HOST-RIPPLE FLOOR (pure-Python fold; the EMULATION-TAX artifact, NOT the Muhlnickel's rate) ---")
        print(f"  contention accounting: cpu_frac = CPU-time I got / wall-time; adj = measured / cpu_frac (uncontended est.)")
        print(f"  {'fold W':>8} {'bd/s (measured)':>17} {'cpu_frac':>9} {'bd/s (adj est)':>16} {'peak MB':>9}")
        for W in [int(x) for x in args.fold_sweep.split(",") if x.strip()]:
            rate, folds, peak, dt, cf = pure_fold_rate(atom, W, args.budget)
            adj = rate / cf if cf > 0 else rate
            print(f"  {W:>8} {rate:>17,.0f} {cf:>9.2f} {adj:>16,.0f} {peak:>9.1f}", flush=True)
            pure_rows.append({"W": W, "block_dots_s": round(rate, 1), "cpu_frac": round(cf, 3),
                              "block_dots_s_adj": round(adj, 1), "folds": folds, "peak_mb": round(peak, 1)})
        result["pure"] = pure_rows

    # 3) END-TO-END RATE off the real model (weight-addressing included).
    if args.model:
        if not os.path.exists(args.model):
            print(f"\n  (--model not found: {args.model}; skipping end-to-end)")
        else:
            print(f"\n  --- END-TO-END RATE off {os.path.basename(args.model)} (weight-addressing included, W={args.fold}) ---")
            rate, peak, file_gb, real_arch, dt, cf = end_to_end_rate(args.model, args.fold, args.neurons, args.budget)
            adj = rate / cf if cf > 0 else rate
            print(f"  {rate:,.0f} bd/s measured · cpu_frac {cf:.2f} · {adj:,.0f} bd/s adj est · peak resident {peak:.1f} MB "
                  f"vs {file_gb:.1f} GB model = {'FLAT' if peak < 500 else 'CHECK'}", flush=True)
            result["end_to_end"] = {"model": os.path.basename(args.model), "block_dots_s": round(rate, 1),
                                    "cpu_frac": round(cf, 3), "block_dots_s_adj": round(adj, 1),
                                    "peak_mb": round(peak, 1), "file_gb": round(file_gb, 1), "fold_W": args.fold}
            archs["real:" + os.path.basename(args.model)] = real_arch

    # 4) PROJECT tokens/sec at the MEASURED NATIVE rate(s) × the routing/sparsity divisor — the honest LDA line.
    #    NOT off the pure-Python host walk (that is the emulation-tax floor, §2). token_cost is the DENSE per-token
    #    block-dots; route-divisor applies the measured MoE+sparsity lever (A4B ≈ 18.9×, pfc_gen_cost).
    eval_rates = [float(x) for x in args.eval_rate.split(",") if x.strip()]
    divisors = [float(x) for x in args.route_divisor.split(",") if x.strip()]
    print("\n  --- PROJECTED TOKENS/SEC at MEASURED DEVICE gate-net drive rates × routing lever (the honest LDA line) ---")
    print(f"  device gate-net drive rates (per device, pfc_dotbench — phone > PC): {', '.join(f'{r:,.0f}' for r in eval_rates)} block-dots/s")
    print(f"  route divisors: {', '.join(str(d) for d in divisors)}  (1=dense · 18.9=A4B MoE routed+sparse, measured)")
    print(f"  {'arch':>16} {'dense bd/tok':>14} {'route÷':>7} {'rate bd/s':>12} {'tok/s':>10} {'time/token':>12}")
    proj = {}
    for name, arch in archs.items():
        tc = token_cost(arch)
        rows = []
        for d in divisors:
            eff = tc / d
            for r in eval_rates:
                tps = r / eff if eff else 0.0
                secs = 1.0 / tps if tps > 0 else float("inf")
                print(f"  {name:>16} {tc:>14,} {d:>7} {r:>12,.0f} {tps:>10.2f} {human_time(secs):>12}", flush=True)
                rows.append({"route_divisor": d, "eval_rate_bd_s": r, "tokens_s": round(tps, 3),
                             "sec_per_token": round(secs, 3)})
        proj[name] = {"dense_block_dots_per_token": tc, "projections": rows}
    result["projection"] = proj
    result["host_ripple_floor_note"] = ("§2's pure-Python fold rate is a DEVICE drive rate; tokens/sec is projected off "
                                        "the MEASURED DEVICE gate-net drive rate (phone > PC), never the host's own multiplier.")

    if args.levers:
        result["lever_stack"] = lever_stack_report()

    print("\n  HONEST NOTES:")
    print("   · the Muhlnickel's OWN spec is its DEPTH (dot32_i8 = 366 gate-delays), device-independent — NOT any device's rate.")
    print("   · the rate above is a DEVICE gate-net drive rate (pfc_dotbench): PC pure-Python 5,536, S24 Ultra native 8-thread")
    print("     1,946,418 — phone > PC, as it must be. NOT the host's own int8 multiplier (the retired 151M conflation).")
    print("   · dense bd/tok is measured from the arch; the route divisor is the measured MoE+sparsity lever (pfc_gen_cost).")
    print("   · peak resident RAM (§2) is the flat-RAM check — contention-proof, the memory ceiling-lift that IS the LDA win.")
    print("   · the remaining open item is the Phase-3 on-device native evaluator (a build), not whether it works.")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(result, open(OUT, "w"), indent=1)
    print(f"\n  json -> {OUT}   (nothing modified; atom + model read-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
