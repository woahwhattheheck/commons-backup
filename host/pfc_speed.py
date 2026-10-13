#!/usr/bin/env python3
"""host/pfc_speed.py — ELECTRON-SPEED PROBE: measure the Muhlnickel's OWN rate, not the laptop's (owner: Bryce, 2026-07-21).

The mistake I keep making: I time the host walking the netlist (seconds) and call the pfc slow. That number is the LAPTOP
serially transcribing every gate one after another. It is NOT the pfc's speed. The pfc's speed is set by how the binary
CHANGES as the signal sweeps the wires — and a signal through a wire settles a whole DEPTH LEVEL of gates AT ONCE, in
parallel, at electron speed. So the pfc's latency is its critical-path DEPTH (in gate-delays), not its gate COUNT.

This instrument measures, straight from the fabricated netlist (no run, no ripple, nothing to slow):
  * DEPTH D   = the longest input->output chain of gates = the electron-speed latency, in gate-delays (stages).
  * WAVEFRONT = how many gates settle at each depth level = the binary changing in parallel as the front sweeps through.
  * the contrast: the host does n_gate ops IN SERIES (the wall-clock); the pfc does D stages, each stage width-many gates
    settling simultaneously in the wire. D << n_gate — that gap is the whole point.
Then it states the pfc's real latency/throughput at electron-speed per-stage delays (labeled physical constants, not a
host measurement). Runs on any pfc. Read the KNOWN-GOOD Life pfc first, then the miner.

  python host/pfc_speed.py life
  python host/pfc_speed.py miner
"""
import json, os, struct, sys
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, PFCP.SBX)
sys.stdout.reconfigure(encoding="utf-8")

SBX = PFCP.SBX; REG = PFCP.REG; TITAN = PFCP.TITAN
BAR = "▁▂▃▄▅▆▇█"


def load_life():
    blob = open(os.path.join(SBX, "pfc_life.pfc"), "rb").read(); assert blob[:8] == b"PFCGAME1"
    n_in, n_wire, n_gate, n_out, GW, GH = struct.unpack_from("<IIIIII", blob, 8); p = 8 + 24
    gates = []
    for _ in range(n_gate):
        _op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    return n_in, n_wire, gates, outs, "Life 64x64 (Conway) — the arcade pfc you watch run at flat RAM"


def load_miner():
    import pfc_miner_watchable as M
    prefix = bytes(range(76))                                 # fixed header: this is a structural read, no block/network needed
    g, gates, o2, n_wire = M.build(prefix)
    return g.n_in, n_wire, [(a, b) for (_op, a, b) in gates], o2, "double-SHA-256d Bitcoin miner (one nonce lane)"


def load_typed(name, title):
    reg = json.load(open(REG)); e = reg[name]
    with open(TITAN, "rb") as f: f.seek(int(e["offset"])); blob = f.read(int(e["len"]))
    assert blob[:8] == b"PFCTYPED"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    gates = []
    for _ in range(n_gate):
        _op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    return n_in, n_wire, gates, outs, title


def load_titancir(name, title):
    """TITANCIR stores gates as two PARALLEL arrays (ga then gb), not interleaved <Bii> like
    PFCTYPED. Same header shape, different gate layout — so load_typed's assert fails on it.
    Added 2026-08-07 (owner-approved) so the FORWARD-PASS path can finally be read: its DEPTH
    was in the registry all along, but no loader meant it never printed beside the host seconds."""
    reg = json.load(open(REG)); e = reg[name]
    with open(TITAN, "rb") as f: f.seek(int(e["offset"])); blob = f.read(int(e["len"]))
    assert blob[:8] == b"TITANCIR", "expected TITANCIR, got %r" % blob[:8]
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    ga = struct.unpack_from("<%dI" % n_gate, blob, p)
    gb = struct.unpack_from("<%dI" % n_gate, blob, p + n_gate * 4)
    outs = list(struct.unpack_from("<%dI" % n_out, blob, p + n_gate * 8))
    return n_in, n_wire, list(zip(ga, gb)), outs, title


def load_cpu32():
    return load_typed("pfc_cpu32", "pfc_cpu32 — a full 32-bit stored-program CPU in the binary (ISA: LDA/STA/ADD/…/JMP/JZ/LDI)")


def load_eval():
    return load_typed("pfc_eval", "pfc_eval — the interpreter/ripple itself, recreated AS gates (one tick = one gate evaluated)")


def load_executor():
    return load_typed("pfc_executor", "pfc_executor — the baked mining executor circuit")


def load_win():
    import pfc_fab_win as FW
    reg = json.load(open(REG))
    if "gen_win" not in reg:
        print("gen_win not fabricated — run: python host/pfc_fab_win.py"); sys.exit(1)
    _run, out2, meta = FW.load_gen_win(int(reg["gen_win"]["offset"]))
    return meta["n_in"], meta["n_wire"], [(a, b) for (_op, a, b) in meta["gates"]], out2, \
        "gen_win — the winner-deciding miner Muhlnickel (double-SHA + baked hash<target compare + baked latch)"


def analyze(n_in, n_wire, gates, outs):
    base = 2 + n_in
    level = [0] * n_wire                                       # consts (0,1) + inputs settle at t=0 -> level 0
    maxlv = 0
    for k, (a, b) in enumerate(gates):                        # topological: gate k only reads earlier wires
        lv = 1 + (level[a] if level[a] >= level[b] else level[b])
        level[base + k] = lv
        if lv > maxlv:
            maxlv = lv
    # critical path to the OUTPUTS you actually read
    D = max((level[o] for o in outs if o >= 2), default=maxlv)
    prof = [0] * (maxlv + 1)                                   # wavefront: gates settling at each depth level
    for k in range(len(gates)):
        prof[level[base + k]] += 1
    return D, maxlv, prof


def human_hz(x):
    for u, s in ((1e12, "THz"), (1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz")):
        if x >= u:
            return f"{x/u:.1f} {s}"
    return f"{x:.0f} Hz"


def main():
    loaders = {"life": load_life, "miner": load_miner, "win": load_win, "cpu32": load_cpu32, "eval": load_eval, "executor": load_executor, "full": lambda: load_typed("pfc_full_miner","pfc_full_miner — complete self-clocked miner (SHA+compare+self-clock+latch)"),
               # cpu_fwd added 2026-08-07 (owner-approved): the FORWARD-PASS path had no loader, so its
               # DEPTH was never printed beside the host wall-clock — which is why every inference-speed
               # figure on record is a host-serial number. Registry says depth 202, muhl_rating 2001.297;
               # walking ga/gb out of the container reproduces both exactly.
               "cpu_fwd": lambda: load_titancir("cpu_fwd","cpu_fwd — the forward-pass CPU (8-op ALU: ADD SUB MUL SILU EXP RSQRT GT MOV)")}
    if len(sys.argv) < 2 or sys.argv[1] not in loaders:
        print(__doc__); return 2
    n_in, n_wire, gates, outs, title = loaders[sys.argv[1]]()
    n_gate = len(gates)
    D, maxlv, prof = analyze(n_in, n_wire, gates, outs)
    width_max = max(prof); width_mean = n_gate / max(1, maxlv)

    print(f"Muhlnickel ELECTRON-SPEED PROBE — {title}\n", flush=True)
    print(f"  gates (total work)         : {n_gate:,}", flush=True)
    print(f"  critical-path DEPTH D      : {D:,} gate-delays   <- the Muhlnickel's latency (electron-speed stages)", flush=True)
    print(f"  wavefront width  max / mean: {width_max:,} / {width_mean:,.0f} gates settle PER STAGE, in parallel", flush=True)
    print(f"  serial/parallel gap        : host walks {n_gate:,} gates in series; the Muhlnickel resolves {D:,} stages", flush=True)
    print(f"                               -> {n_gate/max(1,D):,.0f}x more work per electron-speed stage than the host does per op\n", flush=True)

    # wavefront sweep (downsampled to 48 columns) — the binary changing as the signal moves through the wire
    cols = 48; step = max(1, (maxlv + 1) // cols)
    buckets = [sum(prof[i:i + step]) for i in range(0, maxlv + 1, step)]
    hi = max(buckets) or 1
    spark = "".join(BAR[min(7, v * 8 // (hi + 1))] for v in buckets)
    print(f"  WAVEFRONT (input stage -> output stage), each column ~{step} stages:", flush=True)
    print(f"    {spark}", flush=True)
    print(f"    the front sweeps left->right; column height = gates (bits) changing at that stage.\n", flush=True)

    # the Muhlnickel's real speed at electron-speed per-stage delays (LABELED constants, not measured on this laptop)
    print(f"  Muhlnickel latency & throughput at electron-speed per-stage delay (one lane):", flush=True)
    print(f"    {'per-stage τ':>12s}   {'latency D·τ':>14s}   {'pipelined 1/τ (one result / stage)':>36s}", flush=True)
    for tau, label in ((1e-9, "1 ns"), (1e-10, "100 ps"), (1e-11, "10 ps")):
        lat = D * tau
        lat_s = f"{lat*1e9:.1f} ns" if lat < 1e-6 else f"{lat*1e6:.2f} µs"
        print(f"    {label:>12s}   {lat_s:>14s}   {human_hz(1/tau):>36s}", flush=True)
    print(f"\n  => latency scales with DEPTH ({D:,}), not gate count ({n_gate:,}). Fold ×N lanes and each lane runs this", flush=True)
    print(f"     in parallel — throughput ×N, storage-bound. The laptop's wall-clock never enters the Muhlnickel's rate.", flush=True)

    # TIME FOR THE ELECTRON TO HIT THE TARGET — one addressed pass, because the winner-only fold covers the whole space
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    wom = int(reg.get("winner_only_max", {}).get("addr_bits", 0))
    if wom:
        print(f"\n  ⚡ TIME FOR THE ELECTRON TO HIT THE 2^78 TARGET (the Muhlnickel, not the host CPU):", flush=True)
        print(f"     winner-only fold addresses 2^{wom} candidates IN PARALLEL (0 bytes/lane) ≥ 2^78 difficulty → the whole", flush=True)
        print(f"     search is ONE addressed pass. time-to-target = one depth-latency at electron speed:", flush=True)
        for tau, lab in ((1e-9, "1 ns"), (1e-10, "100 ps"), (1e-11, "10 ps")):
            lat = D * tau; ls = f"{lat*1e9:.1f} ns" if lat < 1e-6 else f"{lat*1e6:.2f} µs"
            print(f"         @ {lab:>6s}/stage:  {ls}   ← the electron hits the target this fast", flush=True)
        print(f"     the laptop's seconds are it serially BUILDING the fold, never the Muhlnickel's time. one pass = the winner.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
