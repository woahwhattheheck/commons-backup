#!/usr/bin/env python3
"""host/pfc_exp_clock.py — EXPERIMENTAL (host+Muhlnickel combo, owner-approved 07-19): the RESIDENT high-impedance CLOCK.

⚠ EXPERIMENTAL / SEGREGATED: this is a host process that keeps ENERGY addressed to the pfc — a compromise the owner OK'd
now that we have impedance. It is HIGH IMPEDANCE by construction: bounded SINGLE-BYTE seek+writes, WRITE-ONLY, blind to
the pfc (never reads or ripples it), NO mmap (mmap maps the file resident = RAM). It routes the block data ONCE, resets the
state, then holds a resident clock on `clk_bit` — the energy that advances the stored-bit state each tick.

  python host/pfc_exp_clock.py [seconds] [target_hex]   # run for N s (default 20; 0 = until Ctrl-C). target defaults to
                                                          # all-FF (easy test: every tick wins -> latch_reg tracks the nonce)
"""
import json, os, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
# a fixed 76-byte test header (version|prevhash|merkle|ntime|nbits) — any bytes; the miner double-SHAs header+nonce
TEST_HEADER = bytes((i * 37 + 11) % 256 for i in range(76))


def main():
    reg = json.load(open(REG))
    for k in ("input_window", "nonce_reg", "latch_reg", "clk_bit"):
        if k not in reg:
            print(f"{k} absent — run host/pfc_miner.py first."); return 1
    iw = int(reg["input_window"]["offset"]); no = int(reg["nonce_reg"]["offset"])
    lo = int(reg["latch_reg"]["offset"]); cb = int(reg["clk_bit"]["offset"])
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    target = int(sys.argv[2], 16) if len(sys.argv) > 2 else (1 << 256) - 1     # all-FF = every tick wins (test)

    # route block data ONCE (header | target) + reset the state (one-way writes, then the clock holds energy)
    block = TEST_HEADER + target.to_bytes(32, "little")
    with open(TITAN, "r+b") as f:
        f.seek(iw); f.write(block[:108])                # block data -> input_window
        f.seek(no); f.write(b"\x00\x00\x00\x00")        # nonce = 0
        f.seek(lo); f.write(b"\x00\x00\x00\x00")        # clear the answer latch
    print(f"routed block ({len(block)} B) -> input_window @ {iw}; nonce_reg=0, latch_reg=0; target={'FF*32' if target==(1<<256)-1 else hex(target)}", flush=True)
    print(f"RESIDENT CLOCK on clk_bit @ {cb} (high-impedance 1-byte seek+writes, no mmap). Running {secs:g}s …", flush=True)

    f = open(TITAN, "r+b"); ticks = 0; t0 = time.time(); last = t0
    try:
        while secs == 0 or time.time() - t0 < secs:
            f.seek(cb); f.write(b"\x01")                 # rising edge — energy addressed to the receiver/clock bit
            f.seek(cb); f.write(b"\x00")                 # falling edge
            ticks += 1
            if ticks % 200000 == 0:
                now = time.time(); print(f"  {ticks:,} ticks  ({ticks/(now-t0):,.0f}/s)", flush=True); last = now
    except KeyboardInterrupt:
        print("\n  stopped (Ctrl-C).", flush=True)
    finally:
        f.close()
    print(f"clock done: {ticks:,} ticks over {time.time()-t0:.1f}s ({ticks/max(1e-9,time.time()-t0):,.0f}/s). "
          f"Read state with:  python host/pfc_meter.py nonce_reg  /  latch_reg", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
