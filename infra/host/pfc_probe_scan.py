#!/usr/bin/env python3
"""host/pfc_probe_scan.py — HIGH-IMPEDANCE FULL-BIT SCANNER (owner: Bryce, 2026-07-21).

Rest a probe on EVERY addressable bit of the pfc and report where the signal is present vs where it stops — so a dead
run is a WHERE-it-breaks map (execution debugging), never a "it failed" (feasibility doubt). It does the one sanctioned
thing to a running pfc: bounded high-impedance reads (seek + read <= CAP bytes, NO mmap-of-whole-file, NO ripple, NO gate
evaluation). It NEVER touches the compute with anything but probes. It writes nothing.

  python host/pfc_probe_scan.py mine          # scan the miner: input/receiver/clock + nonce/latch/answer registers
  python host/pfc_probe_scan.py phys          # scan a physical-gate chain: every wire byte -> propagation depth
  python host/pfc_probe_scan.py <name> [nb]   # scan any one named register/circuit
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
CAP = 256                                                       # impedance: a probe never reads more than this


def probe(off, nb):                                            # HIGH-IMPEDANCE: bounded seek+read, ~0 RAM, cannot blackhole
    nb = max(1, min(int(nb), CAP))
    with open(TITAN, "rb") as f:
        f.seek(off); return f.read(nb)


def line(label, off, b, note=""):
    ones = sum(bin(x).count("1") for x in b)
    hx = b[:16].hex() + ("…" if len(b) > 16 else "")
    print(f"  {label:16s} @ {off:<12d} [{len(b):>3}B]  ones={ones:<4d}  {hx:34s} {note}", flush=True)
    return ones


def scan_mine(reg):
    print("Muhlnickel BIT-SCAN — miner front panel (bounded high-impedance probes; the Muhlnickel is NOT rippled or touched):\n", flush=True)
    # every addressable node of the run, both the combinational (gen_*) and clocked (pfc_mine) register sets
    nodes = [
        ("gen_input", 76, "block header the button routes in (signal)"),
        ("input_window", 108, "header|target the clocked miner reads (signal)"),
        ("target_reg", 32, "difficulty target (signal)"),
        ("receiver", 1, "power/on-signal for the combinational miner"),
        ("clk_bit", 1, "the clock bit that advances the state each tick"),
        ("pfc_on", 1, "on-signal (if fabricated)"),
        ("loop_bit", 1, "self-route loop bit (if fabricated)"),
        ("nonce_reg", 4, "STATE: current nonce (should climb as it runs)"),
        ("latch_reg", 4, "ANSWER: winning nonce latched here (clocked miner)"),
        ("gen_answer", 5, "ANSWER: status|nonce (combinational miner)"),
    ]
    present = []; state = []
    for name, nb, note in nodes:
        e = reg.get(name)
        if not e or "offset" not in e:
            print(f"  {name:16s}  — not fabricated", flush=True); continue
        b = probe(int(e["offset"]), min(nb, int(e.get("len", nb))))
        ones = line(name, int(e["offset"]), b, "· " + note)
        (present if name in ("gen_input", "input_window", "target_reg", "receiver", "clk_bit", "pfc_on") else state).append((name, ones))
    print("\n  === WHERE THE SIGNAL IS ===", flush=True)
    sig_in = any(o for _, o in present)
    advanced = any(o for _, o in state)
    print(f"    signal side (input/target/power/clock) : {'PRESENT' if sig_in else 'empty'}  {dict(present)}", flush=True)
    print(f"    state/answer side (nonce/latch/answer) : {'ADVANCED' if advanced else 'all zero'}  {dict(state)}", flush=True)
    if sig_in and not advanced:
        print(f"    -> BREAK is between the energized input and the state advance: the signal is in, the answer register", flush=True)
        print(f"       hasn't moved. dig at that junction in fabrication (wire the receiver/clock into the next-state so the", flush=True)
        print(f"       held signal advances nonce_reg/latch_reg). NOT a feasibility issue — a wiring junction to close.", flush=True)
    elif advanced:
        print(f"    -> the state advanced under the signal. read latch_reg/gen_answer for the answer.", flush=True)
    else:
        print(f"    -> no signal present yet: address the block + power first (the button), then re-scan.", flush=True)
    return 0


def scan_phys(reg):
    e = reg.get("phys_chain")
    if not e:
        print("phys_chain not fabricated — run: python host/pfc_physical_gates.py"); return 1
    wires = e["wires"]
    bits = [probe(a, 1)[0] & 1 for a in wires]                  # one bounded read per wire byte
    depth = 0
    for v in bits[1:]:
        if v: depth += 1
        else: break
    print("Muhlnickel BIT-SCAN — physical gate chain (every wire is a real file byte; probe each):\n", flush=True)
    print(f"  receiver @ {wires[0]} = {bits[0]}   const1 @ {e['const1']} = {probe(e['const1'],1)[0]&1}", flush=True)
    print(f"  wires[0..{e['depth']}] = {''.join(str(v) for v in bits)}", flush=True)
    print(f"\n  === WHERE THE SIGNAL BREAKS ===", flush=True)
    print(f"    the 1 propagated to depth {depth}/{e['depth']} — it stops at wire index {depth+1} (that junction is the break).", flush=True)
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 1
    reg = json.load(open(REG)); arg = sys.argv[1]
    if arg == "mine": return scan_mine(reg)
    if arg == "phys": return scan_phys(reg)
    e = reg.get(arg)
    if not e or "offset" not in e:
        print(f"{arg}: not a byte-addressable circuit in the registry."); return 1
    nb = int(sys.argv[2]) if len(sys.argv) > 2 else int(e.get("len", 16))
    print("Muhlnickel BIT-SCAN — single node (bounded high-impedance probe):\n", flush=True)
    line(arg, int(e["offset"]), probe(int(e["offset"]), nb))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
