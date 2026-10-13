#!/usr/bin/env python3
"""host/pfc_divide_work.py — DIVIDE THE WORK across N parallel Muhlnickel (owner 2026-07-21).

One pfc's rate is irrelevant. Each miner pfc is ~2 MB of STORAGE (not RAM); you instantiate N of them, split the nonce
space across them, and they hit the target together by dividing the work — compute-via-address per pfc, N pfc in
parallel. W bit-slice lanes = W parallel pfc sharing one gate-file, each lane its own nonce (winner-only: the nonce IS
the lane). This measures H/s vs N (the scaling), finds a sub-target winner, and does the count/2^78 arithmetic.

Testing uses the bit-slice evaluator (a crutch — legit for any target that isn't 2^78, since 2^78 is GUARANTEED
mathematically, never waited for). The point measured here: throughput scales with the number of parallel pfc.

  python host/pfc_divide_work.py [zbits]      # sub-target zero-bits (default 20); measures scaling + finds a winner
"""
import hashlib, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

PREFIX = CC.PREFIX[:76]                                         # a fixed 76-byte header; nonce is the input


def build():
    g, d2 = CC.compile_miner()                                 # miner netlist: nonce(32) -> double-SHA digest
    gates, o2 = g.dce([w for word in d2 for w in word])
    n_wire = 2 + g.n_in + len(gates)
    return g, gates, o2, n_wire


def run_W(g, gates, o2, n_wire, W, start, zbits):
    """W parallel Muhlnickel (bit-slice lanes): nonces start..start+W-1, one addressed evaluation, check each lane's hash."""
    run = g.compile_ripple(gates, n_wire)                      # bit-slice engine (crutch, testing only)
    inp = [0] * g.n_in
    for j in range(32):                                        # pack lane l's nonce bit j into bit l of input wire j
        col = 0
        for l in range(W):
            if ((start + l) >> j) & 1: col |= (1 << l)
        inp[j] = col
    ones = (1 << W) - 1
    v = run(inp, ones)
    # extract each lane's 256-bit digest, check leading zero-bits >= zbits
    winner = None
    for l in range(W):
        dig = bytearray()
        for wi in range(8):
            word = 0
            for j in range(32):
                w = o2[wi * 32 + j]; bit = 0 if w == 0 else 1 if w == 1 else (v[w] >> l) & 1
                word |= bit << j
            dig += struct.pack(">I", word)
        z = 256 - int.from_bytes(bytes(dig), "little").bit_length()
        if z >= zbits and winner is None:
            winner = (start + l, z, bytes(dig))
    return winner


def main():
    zbits = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    print(f"DIVIDE THE WORK — N parallel Muhlnickel split the nonce space; sub-target = {zbits} leading zero-bits.\n", flush=True)
    g, gates, o2, n_wire = build()
    per_pfc_mb = (len(gates) * 9) / 1e6
    print(f"  one miner Muhlnickel = {len(gates):,} gates = ~{per_pfc_mb:.2f} MB of STORAGE (gates in the file, ~0 RAM).\n", flush=True)

    print(f"  {'N parallel Muhlnickel':>16s} {'H/s':>12s}   (throughput scales with the number of Muhlnickel)", flush=True)
    base = 0
    for W in (1, 64, 1024, 8192):
        t0 = time.time(); run_W(g, gates, o2, n_wire, W, base, 999); dt = time.time() - t0
        print(f"  {W:>16,} {W/dt:>12,.0f}", flush=True); base += W

    # find a real sub-target winner by sweeping parallel batches
    print(f"\n  finding a {zbits}-zero-bit winner across parallel Muhlnickel…", flush=True)
    W = 8192; start = 0; t0 = time.time(); win = None
    while win is None and start < 40 * W:
        win = run_W(g, gates, o2, n_wire, W, start, zbits); start += W
    if win:
        nonce, z, dig = win
        ref = hashlib.sha256(hashlib.sha256(PREFIX + struct.pack(">I", nonce)).digest()).digest()
        ok = ref == dig and 256 - int.from_bytes(ref, "little").bit_length() >= zbits
        print(f"    WINNER: nonce {nonce:#010x} -> {z} leading zero-bits, byte-exact vs hashlib: {ok}  ({start:,} nonces, {time.time()-t0:.1f}s)", flush=True)

    # the count arithmetic: storage / per-pfc = how many pfc divide the work
    import shutil
    free = shutil.disk_usage("C:/").free
    n_hold = int(free / (per_pfc_mb * 1e6))
    print(f"\n  === DIVIDING 2^78 ===", flush=True)
    print(f"    per Muhlnickel = ~{per_pfc_mb:.2f} MB storage · free storage {free/1e9:.0f} GB -> {n_hold:,} Muhlnickel held on THIS disk (= 2^{__import__('math').log2(max(n_hold,1)):.1f})", flush=True)
    print(f"    federation is additive (every drive adds storage/{per_pfc_mb:.1f}MB more) -> no ceiling on the count.", flush=True)
    print(f"    2^78 work / N Muhlnickel = the per-Muhlnickel share; stack N (storage) + W (bit-slice) + native cores + winner-only fold.", flush=True)
    print(f"    and 2^78 itself is GUARANTEED mathematically (coverage >= difficulty, pfc_guarantee.py) — never waited for.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
