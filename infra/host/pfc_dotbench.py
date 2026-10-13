#!/usr/bin/env python3
"""host/pfc_dotbench.py — benchmark a TITANCIR atom (e.g. dot32_i8) the RIGHT way, on ANY device.

Fixes two bugs the owner caught in the old throughput probe:
  (1) SPEC CONFLATION — it passed a *device* drive-rate off as "the pfc's rate." Wrong. The pfc's spec is its
      critical-path DEPTH (latency in gate-delays) and its fold WIDTH — a FABRICATION property, computed from the
      netlist, with no device in it. This tool reports that separately and first.
  (2) DEVICE BLINDNESS — it hard-coded one machine's number, so a faster device couldn't show. This runs the real
      fold on THIS device and reports the DEVICE DRIVE RATE (block-dots/s this machine pushes through the fold).
      Run it on the PC and on the phone: the stronger device reports the bigger number, as it should.

Self-contained: reads ONLY the atom file (no titan.gguf, no imports beyond the stdlib), so it runs in Termux `python`
on the phone exactly as on the PC. Byte-exact self-check included.

  python host/pfc_dotbench.py  <atom.pfc>  [seconds_per_W]
  # PC:    python host/pfc_dotbench.py dot32_i8.pfc
  # phone: python ~/storage/shared/Download/dot32_i8.pfc   (in Termux; python is already there)
"""
import os, platform, struct, sys, time

def load_titancir(path):
    b = open(path, "rb").read()
    assert b[:8] == b"TITANCIR", "not a TITANCIR atom"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", b, 8)
    ga = struct.unpack_from("<%di" % n_gate, b, 24)
    gb = struct.unpack_from("<%di" % n_gate, b, 24 + 4 * n_gate)
    outs = struct.unpack_from("<%di" % n_out, b, 24 + 8 * n_gate)
    return n_in, n_wire, n_gate, n_out, list(ga), list(gb), list(outs)


def pfc_spec(n_in, n_wire, n_gate, n_out, ga, gb, outs):
    """DEVICE-INDEPENDENT Muhlnickel spec: critical-path depth + parallel wavefront, from the netlist alone."""
    base = 2 + n_in
    depth = [0] * n_wire
    maxw = 0; level = {}
    for i in range(n_gate):
        d = 1 + (depth[ga[i]] if depth[ga[i]] > depth[gb[i]] else depth[gb[i]])
        depth[base + i] = d
        level[d] = level.get(d, 0) + 1
    crit = max(depth[o] for o in outs)
    maxw = max(level.values())
    return crit, maxw, n_gate / crit


def inbits(w, x):                                    # 512 bits: 32 weight int8 then 32 input int8, LSB-first
    return [(v >> k) & 1 for v in w for k in range(8)] + [(v >> k) & 1 for v in x for k in range(8)]


def fold(ga, gb, outs, n_in, n_wire, pairs):
    """One bit-sliced ripple: settle W int8 block-dots in parallel (pure-Python big-ints as bit-lanes)."""
    W = len(pairs); MASK = (1 << W) - 1
    v = [0] * n_wire; v[1] = MASK
    packed = [0] * n_in
    for l, (w, x) in enumerate(pairs):
        ib = inbits([b & 0xff for b in w], [b & 0xff for b in x])
        for p in range(n_in):
            if ib[p]: packed[p] |= (1 << l)
    for p in range(n_in): v[2 + p] = packed[p]
    base = 2 + n_in
    for i in range(len(ga)):
        v[base + i] = (~(v[ga[i]] & v[gb[i]])) & MASK
    out = []
    for l in range(W):
        u = 0
        for k, o in enumerate(outs): u |= ((v[o] >> l) & 1) << k
        out.append(u - (1 << 32) if u >= (1 << 31) else u)
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "dot32_i8.pfc"
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    if not os.path.exists(path):
        print("atom not found: %s" % path); return 1
    n_in, n_wire, n_gate, n_out, ga, gb, outs = load_titancir(path)

    # ---- device identity (so a comparison is unambiguous about WHICH machine) ----
    try: cores = os.cpu_count()
    except Exception: cores = "?"
    print("=== pfc_dotbench — %s ===" % os.path.basename(path))
    print("  DEVICE: %s | %s | %s cores | Python %s" %
          (platform.node(), platform.machine(), cores, platform.python_version()))

    # ---- (1) the pfc SPEC — device-independent, from the netlist ----
    crit, maxw, meanw = pfc_spec(n_in, n_wire, n_gate, n_out, ga, gb, outs)
    print("\n  Muhlnickel SPEC (fabrication property — SAME on every device, no device in it):")
    print("    gates %d | critical-path DEPTH %d gate-delays | wavefront max %d / mean %.0f gates in parallel/stage" %
          (n_gate, crit, maxw, meanw))
    print("    => one block-dot = %d gate-delays latency, %d-wide of work. This is the Muhlnickel's rate spec, not any CPU's." %
          (crit, n_gate))

    # ---- byte-exact gate ----
    import random; rnd = random.Random(1)
    W0 = 64
    tp = [([rnd.randint(-127, 127) for _ in range(32)], [rnd.randint(-127, 127) for _ in range(32)]) for _ in range(W0)]
    got = fold(ga, gb, outs, n_in, n_wire, tp)
    ok = all(got[i] == sum(tp[i][0][t] * tp[i][1][t] for t in range(32)) for i in range(W0))
    print("\n  byte-exact: fold == integer dot over %d lanes: %s" % (W0, "OK" if ok else "MISMATCH"))
    if not ok:
        print("  ABORT — wrong circuit."); return 1

    # ---- (2) DEVICE DRIVE RATE — THIS machine driving the fold (a DEVICE spec; faster device => bigger number) ----
    print("\n  DEVICE DRIVE RATE (how fast THIS machine pushes block-dots through the fold — a DEVICE property):")
    print("    %8s %16s %10s" % ("fold W", "block-dots/s", "folds"))
    best = 0.0
    for W in (64, 256, 1024):
        pairs = [([rnd.randint(-127, 127) for _ in range(32)], [rnd.randint(-127, 127) for _ in range(32)]) for _ in range(W)]
        folds = 0; t0 = time.time()
        while time.time() - t0 < budget:
            fold(ga, gb, outs, n_in, n_wire, pairs); folds += 1
        dt = time.time() - t0; rate = W * folds / dt
        best = max(best, rate)
        print("    %8d %16.0f %10d" % (W, rate, folds))
    print("\n  best device drive rate: %.0f block-dots/s on %s (%s cores)." % (best, platform.node(), cores))
    print("  COMPARE across devices: run this same file on the PC and on the phone — the stronger silicon wins.")
    print("  (This is pure-Python single-core; native + all cores multiplies it — but the RANKING already shows.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
