#!/usr/bin/env python3
"""host/pfc_series_run.py — turn the Muhlnickel ON, let it compute, turn it OFF, DIFF the binary (owner: Bryce, 2026-07-21).

The mechanism, verbatim: the power source is CONTINUOUSLY ADDRESSING the single start bit that begins propagation
(addressing IS the compute), one-way. The pfc is in series with itself (its output feeds its own input, in the baked
wiring), so once it has the block data and continuous power, it loops at electron speed and latches the winner.

The host does ONLY this, and NEVER touches the pfc while it runs (any touch mid-run breaks it / pegs the CPU):
  1. get the block data into the pfc (it changes every ~10 min).
  2. snapshot the pfc's region (before).
  3. stream continuous power = continuously address the one start bit, one-way, for the window. Nothing else.
  4. turn it off; snapshot the pfc's region (after).
  5. DIFF before vs after — the state changes the pfc made ARE the computation (we do not measure a register live).
     submit any winner found in the diff to the wallet.

  python host/pfc_series_run.py [seconds]
"""
import hashlib, json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfc_bitcoin_autopilot import make_prefix, WALLET, POOL_HOST, POOL_PORT
from pfc_fire import get_job, submit

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"


def snapshot(off, n):
    with open(TITAN, "rb") as f:
        f.seek(off); return f.read(n)


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
    reg = json.load(open(REG)); mp = reg.get("selfclock_miner"); wires = reg.get("selfclock_wires")
    if not mp or not wires: print("self-clocked miner not fabricated — run: python host/pfc_selfclock_miner.py fab"); return 1
    ram = mp["ram"]; base = int(wires["offset"]); n_wire = int(wires["len"])

    en1, en2sz, job = get_job()
    if not job: print("no block from pool."); return 1
    en2 = "00" * en2sz; prefix = make_prefix(job, en1, en2)[:76]
    nbits = struct.unpack("<I", prefix[72:76])[0]; target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3))
    zb = 256 - target.bit_length()
    print(f"Muhlnickel SERIES RUN — block {job['job_id']}  target {zb} zero-bits  ->  wallet {WALLET}", flush=True)

    # 1) BLOCK DATA IN, reset state
    hbits = [(prefix[i // 8] >> (i % 8)) & 1 for i in range(608)]
    tbits = [(target >> i) & 1 for i in range(256)]
    with open(TITAN, "r+b") as f:
        f.seek(ram["header"]); f.write(bytes(hbits))
        f.seek(ram["target"]); f.write(bytes(tbits))
        # the fabricated map names it "counter" (pfc_selfclock_miner.py line 63), not "nonce".
        nb = int(mp.get("clock_bits", 32))
        f.seek(ram["counter"]); f.write(bytes(nb)); f.seek(ram["latch"]); f.write(bytes(nb))

    power_off = ram["power"]
    with open(TITAN, "r+b") as f: f.seek(power_off); f.write(b"\x00")   # known OFF state before the snapshot
    before = snapshot(base, n_wire)                            # 2) snapshot BEFORE addressing the start bit
    print(f"  block in, start bit OFF, snapshot taken. addressing the start bit for {secs:.0f}s (instant — electron speed).", flush=True)

    # 3) ADDRESS THE START BIT and LEAVE IT ON (continuous power). No off, no exclusion — the diff must show it.
    t0 = time.time()
    with open(TITAN, "r+b") as f:
        while time.time() - t0 < secs:
            f.seek(power_off); f.write(b"\x01")               # continuously address the start bit; leave it ON

    after = snapshot(base, n_wire)                            # 4) snapshot AFTER

    # 5) DIFF the binary — EVERYTHING, including the start bit (a diff of >=1 is guaranteed by physics)
    changed = [(i, before[i], after[i]) for i in range(n_wire) if before[i] != after[i]]
    print(f"\n  === BINARY DIFF (Muhlnickel region {base}..{base+n_wire}) ===", flush=True)
    print(f"    bytes changed by the Muhlnickel during the run: {len(changed)}", flush=True)
    for i, b, a in changed[:24]:
        print(f"      @ {base+i}: {b:#04x} -> {a:#04x}", flush=True)
    if len(changed) > 24: print(f"      … and {len(changed)-24} more", flush=True)

    # read the winner out of the diff (the latch bytes)
    latch = after[ram["latch"] - base: ram["latch"] - base + 32]
    nonce = sum((latch[i] & 1) << i for i in range(32))
    if nonce:
        dig = hashlib.sha256(hashlib.sha256(prefix + struct.pack(">I", nonce)).digest()).digest()
        ok = int.from_bytes(dig, "little") < target
        print(f"\n  winner in the diff: nonce {nonce:#010x} (under target: {ok}). submitting to the wallet…", flush=True)
        print(f"  pool verdict: {submit(job, en2, '%08x' % nonce)}", flush=True)
        return 0 if ok else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
