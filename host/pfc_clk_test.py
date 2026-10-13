#!/usr/bin/env python3
"""host/pfc_clk_test.py — POWER the clk-wired Muhlnickel and let the PROBES speak (owner 07-19).

pfc_mine_clk now has clk_bit wired into the whole net (input wire 928). Try the two signal shapes the owner named and
read the answer memory with high-impedance probes — no host ripple, no assuming, just power + probe:

  BUTTON (single edge)   — flip clk_bit 0->1 once.
  BUTTON (repeated edges) — toggle clk_bit 1/0 many times (pressing the button over and over = the clock).
  SUSTAINED (hold)       — write clk_bit=1 and HOLD it, probe over time.

Owner's theory: the button (edge) propagates better; a sustained signal needs a pfc fabricated to *care* it's sustained.
Every write is bounded 1-byte seek (one-way energy); every probe is a bounded seek+read (high impedance, no mmap). The
block is routed with target = all-FF, so ANY real advance makes nonce_reg climb / latch_reg track it — max sensitivity.

  python host/pfc_clk_test.py [edges] [hold_seconds]
"""
import json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
TEST_HEADER = bytes((i * 37 + 11) % 256 for i in range(76))


def main():
    edges = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    hold_s = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
    reg = json.load(open(REG))
    if "pfc_mine_clk" not in reg:
        print("pfc_mine_clk absent — run host/pfc_miner_clk.py first."); return 1
    iw = int(reg["input_window"]["offset"]); no = int(reg["nonce_reg"]["offset"])
    lo = int(reg["latch_reg"]["offset"]); cb = int(reg["clk_bit"]["offset"])
    target = (1 << 256) - 1                                       # all-FF: every hash wins -> any advance shows

    def route_reset():
        with open(TITAN, "r+b") as f:
            f.seek(iw); f.write((TEST_HEADER + target.to_bytes(32, "little"))[:108])
            f.seek(no); f.write(b"\x00\x00\x00\x00"); f.seek(lo); f.write(b"\x00\x00\x00\x00"); f.seek(cb); f.write(b"\x00")
    def probe():
        with open(TITAN, "rb") as f:
            f.seek(no); n = struct.unpack("<I", f.read(4))[0]
            f.seek(lo); l = struct.unpack("<I", f.read(4))[0]
            f.seek(cb); c = f.read(1)[0]
        return n, l, c

    print("Muhlnickel CLK TEST — clk_bit wired into the net (input 928). Power + probe, no host ripple.\n", flush=True)

    # ---- BUTTON: single edge ----
    route_reset(); n0, l0, c0 = probe()
    with open(TITAN, "r+b") as f: f.seek(cb); f.write(b"\x01")    # one edge 0->1
    n1, l1, c1 = probe()
    print(f"  BUTTON single edge   clk {c0}->{c1}   nonce_reg {n0}->{n1}   latch_reg {l0:#010x}->{l1:#010x}", flush=True)

    # ---- BUTTON: repeated edges (the clock) ----
    route_reset()
    t = time.time(); f = open(TITAN, "r+b")
    for _ in range(edges): f.seek(cb); f.write(b"\x01"); f.seek(cb); f.write(b"\x00")
    f.close(); dt = time.time() - t
    n2, l2, c2 = probe()
    print(f"  BUTTON x{edges:,} edges  ({dt:.1f}s)   nonce_reg 0->{n2}   latch_reg {l2:#010x}   clk now {c2}", flush=True)

    # ---- SUSTAINED: hold clk high ----
    route_reset()
    with open(TITAN, "r+b") as f: f.seek(cb); f.write(b"\x01")    # set high and HOLD (rewrite 1 each sample to sustain)
    t0 = time.time()
    while time.time() - t0 < hold_s:
        with open(TITAN, "r+b") as f: f.seek(cb); f.write(b"\x01")   # keep it sustained (one-way)
        n, l, c = probe()
        print(f"    SUSTAINED t={time.time()-t0:4.1f}s  clk={c}  nonce_reg={n}  latch_reg={l:#010x}", flush=True)
        time.sleep(1.0)

    n3, l3, c3 = probe()
    print(f"\n  === PROBES SAY ===", flush=True)
    print(f"  button single edge : nonce_reg={n1}  latch_reg={l1:#010x}", flush=True)
    print(f"  button {edges:,} edges : nonce_reg={n2}  latch_reg={l2:#010x}", flush=True)
    print(f"  sustained {hold_s:g}s hold : nonce_reg={n3}  latch_reg={l3:#010x}", flush=True)
    print(f"  (all-FF target -> any nonzero here = the state advanced under that signal shape. clk is now an input of the net.)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
