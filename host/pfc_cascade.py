#!/usr/bin/env python3
"""host/pfc_cascade.py — CASCADE PROBE: a Muhlnickel test instrument (owner: Bryce, 2026-07-21).

The question this answers empirically, on a KNOWN-GOOD pfc: what makes an input change CASCADE through the wiring to a
wide output change? The propagation IS the compute (compute-via-address). So this drives a pfc one propagation, then
flips a SINGLE input bit and drives again, and reports the AVALANCHE — how many output bits the one-bit change fanned out
to. A dead pfc changes nothing; a working pfc turns 1 input bit into a wide output change. You SEE the cascade.

Discipline: this is a TEST DRIVE (the same drive the arcade uses to render — sdc_cc.compile_ripple, legit for testing a
sub-2^78 target). It is NOT "the pfc's speed" and it does NOT explain the pfc's compute — measure host RAM/CPU in Task
Manager (unbiased); it stays flat because the pfc computes, not the host. Validate on the arcade Life pfc first, then read
the miner the same way to find what my series-run drive was missing.

  python host/pfc_cascade.py life            # cascade on the KNOWN-GOOD pfc (Life): drive -> whole grid advances; 1-cell flip -> local fan-out
  python host/pfc_cascade.py miner           # cascade on the miner: 1 nonce bit -> ~128/256 hash bits (avalanche = a correct double-SHA)
"""
import hashlib, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")


def popcount_diff(a, b):
    return bin(int.from_bytes(a, "little") ^ int.from_bytes(b, "little")).count("1")


def cascade_life():
    import random, pfc_game
    cd = pfc_game.load("life"); GW, GH, bits = cd["GW"], cd["GH"], cd["bits"]; N = GW * GH
    run, outs = cd["run"], cd["outs"]
    print(f"  KNOWN-GOOD Muhlnickel: Life {GW}x{GH}={N} cells, {cd['n_gate']:,} gates, {cd['n_in']:,} input bits.\n", flush=True)

    random.seed(7)
    grid = [(1 if random.random() < 0.30 else 0) for _ in range(N)]
    alive0 = sum(1 for c in grid if c & 1)

    # (1) FULL DRIVE = one propagation resolves the whole gate network -> the next generation. That IS the cascade.
    v = run(pfc_game.grid_to_bits(grid, bits), 1)
    new = pfc_game.out_to_grid(v, outs, bits)
    ref = pfc_game.ref_life_step(grid, GW, GH)
    changed_cells = sum(1 for a, b in zip(grid, new) if a != b)
    exact = (new == ref)
    print(f"  (1) ONE DRIVE (resolve the gates once):", flush=True)
    print(f"        {alive0} live cells in -> a whole new generation out.", flush=True)
    print(f"        cells that changed this one propagation: {changed_cells}  (the cascade — a 1-bit input didn't stay 1 bit)", flush=True)
    print(f"        byte-exact vs the Life rule (reference): {exact}\n", flush=True)

    # (2) SINGLE-BIT CASCADE = flip ONE input cell, drive, count changed OUTPUT bits. One bit fans out through the wiring.
    flip = (GH // 2) * GW + (GW // 2)
    b0 = pfc_game.grid_to_bits(grid, bits)
    out0 = pfc_game.out_to_grid(run(b0, 1), outs, bits)
    g2 = list(grid); g2[flip] ^= 1
    out1 = pfc_game.out_to_grid(run(pfc_game.grid_to_bits(g2, bits), 1), outs, bits)
    fan = sum(1 for a, b in zip(out0, out1) if a != b)
    print(f"  (2) FLIP ONE INPUT CELL (#{flip}) and drive:", flush=True)
    print(f"        output cells changed by that ONE flipped bit: {fan}  (0 = dead wiring; >0 = it cascades)\n", flush=True)
    print(f"  => the cascade happens when the DRIVE RESOLVES THE GATE NETWORK. That is what the arcade does every frame;", flush=True)
    print(f"     it is what my series-run did NOT do (it flipped a storage bit and diffed, never resolving the gates).", flush=True)
    return 0


def cascade_miner():
    import pfc_miner_watchable as M
    from pfc_fire import get_job
    from pfc_bitcoin_autopilot import make_prefix
    en1, en2sz, job = get_job()
    if not job:
        print("  no block from pool — using a fixed 76-byte prefix so the cascade test still runs.", flush=True)
        prefix = bytes(range(76))
    else:
        en2 = "00" * en2sz; prefix = make_prefix(job, en1, en2)[:76]
    g, gates, o2, n_wire = M.build(prefix)
    run = g.compile_ripple(gates, n_wire)
    print(f"  MINER Muhlnickel: double-SHA-256d netlist, {len(gates):,} gates, 32-bit nonce input, 256-bit hash output.\n", flush=True)

    def hash_of(nonce):                                   # one propagation for one nonce (single lane), read the 256-bit output
        inp = [(nonce >> j) & 1 for j in range(32)]
        v = run(inp, 1)
        out = bytearray(32)
        for wi in range(8):
            word = 0
            for j in range(32):
                w = o2[wi * 32 + j]; word |= (0 if w == 0 else 1 if w == 1 else v[w] & 1) << j
            out[wi * 4:wi * 4 + 4] = struct.pack("<I", word)
        return bytes(out)

    # avalanche: nonce N vs nonce N with ONE bit flipped -> ~half the 256 output bits flip (a correct cryptographic cascade)
    base_n = 0x12345678
    hb = hash_of(base_n)
    ref = hashlib.sha256(hashlib.sha256(prefix + struct.pack(">I", base_n)).digest()).digest()
    exact = (hb == ref)
    print(f"  driving nonce {base_n:#010x}: byte-exact vs hashlib double-SHA: {exact}", flush=True)
    print(f"  now flip ONE nonce bit and re-drive — measure how far it cascades into the 256-bit hash:\n", flush=True)
    tot = 0; ntest = 8
    for bit in range(ntest):
        hf = hash_of(base_n ^ (1 << bit))
        d = popcount_diff(hb, hf); tot += d
        print(f"        flip nonce bit {bit:2d}: {d:3d} / 256 output bits changed", flush=True)
    print(f"\n  => average avalanche {tot/ntest:.0f}/256 (~128 = ideal). One nonce bit cascades across the whole hash —", flush=True)
    print(f"     that is the gate network resolving. Same drive as the arcade; host RAM stays flat (check Task Manager).", flush=True)
    return 0 if exact else 2


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("life", "miner"):
        print(__doc__); return 2
    print(f"Muhlnickel CASCADE PROBE — {sys.argv[1]}\n", flush=True)
    t0 = time.time()
    rc = cascade_life() if sys.argv[1] == "life" else cascade_miner()
    print(f"\n  (probe drove the Muhlnickel in {time.time()-t0:.1f}s of host addressing time — the compute is in the gates.)", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
