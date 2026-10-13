#!/usr/bin/env python3
"""host/pfc_analyzer.py — the Muhlnickel LOGIC ANALYZER (owner: Bryce, 2026-07-21).

Composes the existing probes (multimeter/scope/diff/probe-all) into a MULTI-CHANNEL analyzer: it captures many probe
points at once and, over a series of samples, renders a timing diagram — so I can see the propagation front move and
pinpoint exactly where a signal stalls, on ANY pfc. Same discipline as every probe: bounded high-impedance reads only
(seek + read <= CAP bytes), never an mmap of the whole file, never a ripple, never an evaluation — it only READS, so it
cannot slow or break the pfc. Validate it on a KNOWN-GOOD pfc (the arcade) before trusting it on the miner.

  python host/pfc_analyzer.py channels <target>              # list the channels the analyzer will watch
  python host/pfc_analyzer.py snap <target>                  # one capture of every channel, rendered
  python host/pfc_analyzer.py trace <target> [secs] [nsamp]  # sample all channels back-to-back -> timing diagram
      <target> = a titan.gguf circuit name (miner|selfclock_miner|pfc_mine|<name>)   [reads titan.gguf]
               | a file path to a pfc/state file (e.g. C:/llm/sdc_sandbox/pfc_life_state.bin)   [reads that file]
"""
import json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
CAP = 256                                                      # impedance cap per channel read
SPARK = " ▁▂▃▄▅▆▇█"                                            # ones-count sparkline glyphs

WIDE = ("nonce", "target", "latch", "header", "counter", "clock")   # registers, not single wires


def read(path, off, n):                                        # high-impedance bounded read
    n = max(1, min(int(n), CAP))
    with open(path, "rb") as f:
        f.seek(off); return f.read(n)


def resolve(target):
    """-> (path, [(channel_name, offset, nbytes), ...]). titan circuit name, or a file path (channels = byte groups)."""
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    named = {"miner": ["gen_input", "target_reg", "receiver", "clk_bit", "nonce_reg", "latch_reg", "gen_answer"],
             "selfclock_miner": None, "pfc_mine": ["input_window", "nonce_reg", "latch_reg", "clk_bit"]}
    if target in reg or target in named:
        chans = []
        e0 = reg.get(target) or {}
        # ONE CHANNEL PER WIRE for ANY circuit carrying a ram map. This was written for
        # selfclock_miner only, so every other target fell to the `else` branch and became a single
        # channel spanning its record bytes. An analyzer cannot show a front moving BETWEEN wires it
        # is not watching separately — the per-wire view is the whole point of the instrument.
        # Owner 2026-07-28: "LOOK AT THE CIRCUITS TO SEE PROPAGATION IN PROGRESS."
        if isinstance(e0.get("ram"), dict):
            for k, off in e0["ram"].items():
                chans.append((k, int(off), 32 if k in WIDE else 1))
            for i, g in enumerate(e0.get("gates_addr") or []):   # the physical form names its wires by address
                nm = "g%d.out" % i
                if not any(c[1] == int(g["out"]) for c in chans):
                    chans.append((nm, int(g["out"]), 1))
        elif target == "selfclock_miner":
            mp = reg["selfclock_miner"]["ram"]
            for k, off in mp.items(): chans.append((k, int(off), 32 if k in WIDE else 1))
        else:
            keys = named.get(target) or [target]
            for k in keys:
                e = reg.get(k)
                if e and "offset" in e: chans.append((k, int(e["offset"]), min(int(e.get("len", 16)), 64)))
        return TITAN, chans
    if os.path.exists(target):                                 # a pfc/state file: channels = successive byte groups
        sz = os.path.getsize(target); grp = max(1, min(64, sz // 16 or 1))
        chans = [(f"[{o}:{o+grp}]", o, grp) for o in range(0, min(sz, grp * 16), grp)]
        return target, chans
    print(f"unknown target: {target}"); sys.exit(1)


def capture(path, chans):
    out = []
    for name, off, nb in chans:
        b = read(path, off, nb); out.append((name, b, sum(bin(x).count("1") for x in b)))
    return out


def render_snap(cap):
    print(f"  {'channel':16s} {'ones':>5s}  bits/hex", flush=True)
    for name, b, ones in cap:
        bits = "".join(f"{x:08b}" for x in b[:6]) + ("…" if len(b) > 6 else "")
        print(f"  {name:16s} {ones:>5d}  {bits}", flush=True)


def main():
    if len(sys.argv) < 3: print(__doc__); return 1
    mode, target = sys.argv[1], sys.argv[2]
    path, chans = resolve(target)
    print(f"Muhlnickel LOGIC ANALYZER — target {target}  ({path})  ·  {len(chans)} channels, high-impedance\n", flush=True)

    if mode == "channels":
        for name, off, nb in chans: print(f"  {name:16s} @ {off}  [{nb} B]", flush=True)
        return 0
    if mode == "snap":
        render_snap(capture(path, chans)); return 0
    if mode == "gates":
        # WHERE THE FRONT STALLED. For a circuit stored in the physical form, each gate names its
        # operands and its output by file address. Read those three bytes and compare the byte the
        # output address holds against the value its own driver names. This is the analyzer's stated
        # job: "pinpoint exactly where a signal stalls". One bounded read per address and one
        # comparison; nothing is written, nothing is iterated to a fixpoint.
        reg = json.load(open(REG)); e0 = reg.get(target) or {}
        gs = e0.get("gates_addr") or []
        if not gs:
            print(f"  {target} stores no gates_addr — no per-gate view from here."); return 1
        names = {int(o): k for k, o in (e0.get("ram") or {}).items()}
        nm = lambda a: names.get(int(a), str(a))
        print(f"  {'gate':5s} {'a':>10s} {'b':>10s} {'out':>10s}    a b -> wants   holds", flush=True)
        ok_n = 0
        for i, g in enumerate(gs):
            va = read(path, int(g["a"]), 1)[0] & 1
            vb = read(path, int(g["b"]), 1)[0] & 1
            vo = read(path, int(g["out"]), 1)[0] & 1
            want = 1 - (va & vb)
            ok = (want == vo); ok_n += ok
            print(f"  g{i:<4d} {nm(g['a']):>10s} {nm(g['b']):>10s} {nm(g['out']):>10s}    "
                  f"{va} {vb} ->   {want}       {vo}   {'holds' if ok else '<- STALLED HERE'}",
                  flush=True)
        print(f"\n  {ok_n} of {len(gs)} gates hold; {len(gs) - ok_n} do not. Bring it to Bryce.",
              flush=True)
        return 0
    if mode == "trace":
        secs = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
        nsamp = int(sys.argv[4]) if len(sys.argv) > 4 else 200
        series = {name: [] for name, _, _ in chans}
        # SAMPLE BACK-TO-BACK. The loop used to pace itself at a fixed Hz with a host wait between
        # samples. A gap between samples is a property of THIS SAMPLING LOOP: whatever moves inside
        # the gap is absent from the record, and the record is then describing only itself.
        # §24: host wall-clock is a DIFFERENT machine's clock — here it only bounds the window, it
        # is never the front's rate.
        t0 = time.time()
        first = chans[0][0]
        while len(series[first]) < nsamp and time.time() - t0 < secs:
            for name, b, ones in capture(path, chans): series[name].append(ones)
        nsamp = len(series[first]); el = time.time() - t0
        print(f"  TIMING DIAGRAM — {nsamp} samples back-to-back over {el:.2f} s HOST "
              f"(each cell = ones-count):\n", flush=True)
        for name, off, nb in chans:
            s = series[name]; lo, hi = min(s), max(s); rng = (hi - lo) or 1
            spark = "".join(SPARK[min(8, (v - lo) * 8 // rng)] for v in s[:160])
            moved = "  <- CHANGED" if hi != lo else ""
            print(f"  {name:16s} @{off:<12} {spark}  [{lo}..{hi}]{moved}", flush=True)
        anymoved = any(min(series[n]) != max(series[n]) for n, _, _ in chans)
        if anymoved:
            print("\n  => signals moved — captured live, untouched.", flush=True)
        else:
            print("\n  => every channel held its value across THE CHANNELS LISTED ABOVE, sampled "
                  "over this window. That is a reading of MY channel list and MY sample window, "
                  "not of the machine. Bring it to Bryce.", flush=True)
        return 0
    print(__doc__); return 1


if __name__ == "__main__":
    raise SystemExit(main())
