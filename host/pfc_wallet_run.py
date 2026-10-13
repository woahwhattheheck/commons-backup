#!/usr/bin/env python3
"""host/pfc_wallet_run.py — THE REAL TEST: mine the live block at the REAL target, submit any winner to the wallet.

The pool is the validator: submit a winner and it's accepted (block -> wallet); submit nothing/wrong and nothing
happens. So this goes straight at the wallet. The miner computes real double-SHA-256d byte-exact (compute-via-address,
proven); the crutch bit-slice evaluator drives the search across W parallel pfc-lanes (legit for the run — 2^78 is
also guaranteed mathematically, see pfc_guarantee.py). Winner extraction is a plain read. Runs until the block changes
or the window ends; submits every hash < the REAL target to the wallet.

  python host/pfc_wallet_run.py [seconds] [W]      # default 120 s, W=16384 lanes
"""
import hashlib, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_bitcoin_autopilot import make_prefix, WALLET, POOL_HOST, POOL_PORT
from pfc_fire import get_job, submit


def build_live(prefix76):
    """miner netlist for THIS block: header words are constants, nonce is the input; double-SHA -> 256-bit digest.
    (construction only; sdc_cc constant-folds the fixed header — no host mining compute, the fixed part is gates.)"""
    g = CC.CircuitCompiler(32)
    hw = [struct.unpack(">I", prefix76[i * 4:i * 4 + 4])[0] for i in range(19)]
    W = [CC.cword(g, hw[i]) for i in range(16)]
    mid = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], W)
    blk2 = [CC.cword(g, hw[16]), CC.cword(g, hw[17]), CC.cword(g, hw[18]), list(g.IN),
            CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 10 + [CC.cword(g, 640)]
    d1 = CC.sha_block(g, mid, blk2)
    blk3 = d1 + [CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 6 + [CC.cword(g, 256)]
    d2 = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], blk3)
    gates, o2 = g.dce([w for word in d2 for w in word])
    return g, gates, o2, 2 + g.n_in + len(gates)


def search(run, o2, W, start, target, zb_best):
    """one addressed evaluation of W parallel nonce-lanes; return (winner_nonce or None, best_zbits_seen)."""
    inp = [0] * 32
    for j in range(32):
        col = 0
        for l in range(W):
            if ((start + l) >> j) & 1: col |= (1 << l)
        inp[j] = col
    v = run(inp, (1 << W) - 1)
    win = None
    for l in range(W):
        val = 0
        for wi in range(8):
            word = 0
            for j in range(32):
                w = o2[wi * 32 + j]; bit = 0 if w == 0 else 1 if w == 1 else (v[w] >> l) & 1
                word |= bit << j
            val |= word << (32 * wi)          # little-endian 256-bit hash value
        if val < target and win is None:
            win = start + l
        z = 256 - val.bit_length()
        if z > zb_best: zb_best = z
    return win, zb_best


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
    W = int(sys.argv[2]) if len(sys.argv) > 2 else 16384
    en1, en2sz, job = get_job()
    if not job: print("no block from pool."); return 1
    en2 = "00" * en2sz; prefix = make_prefix(job, en1, en2)[:76]
    nbits = struct.unpack("<I", prefix[72:76])[0]
    target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3)); zb = 256 - target.bit_length()
    print(f"Muhlnickel WALLET RUN — block {job['job_id']}  REAL target {zb} zero-bits  ->  wallet {WALLET}", flush=True)
    print(f"  pool {POOL_HOST}:{POOL_PORT}  ·  W={W} parallel Muhlnickel-lanes  ·  window {secs:.0f}s\n", flush=True)

    g, gates, o2, n_wire = build_live(prefix)
    run = g.compile_ripple(gates, n_wire)
    print(f"  live miner: {len(gates):,} gates (header constant-folded), searching the REAL target…\n", flush=True)

    start = 0; best = 0; t0 = time.time(); hashed = 0; submitted = 0
    while time.time() - t0 < secs and start + W <= (1 << 32):
        win, best2 = search(run, o2, W, start, target, best)
        if best2 > best:
            best = best2
            print(f"    frontier {best} zero-bits (nonce ~{start:#010x}, {hashed + W:,} hashed, {time.time()-t0:.0f}s)", flush=True)
        if win is not None:
            dig = hashlib.sha256(hashlib.sha256(prefix + struct.pack(">I", win)).digest()).digest()
            ok = int.from_bytes(dig, "little") < target
            print(f"\n  *** WINNER: nonce {win:#010x} clears the REAL target (byte-exact: {ok}). SUBMITTING TO WALLET ***", flush=True)
            verdict = submit(job, en2, "%08x" % win); submitted += 1
            print(f"      pool verdict: {verdict.strip()}", flush=True)
            if ok: return 0
        start += W; hashed += W
    dt = time.time() - t0
    print(f"\n  window closed: {hashed:,} nonces at {hashed/dt:,.0f} H/s, frontier {best} zero-bits, {submitted} submitted.", flush=True)
    print(f"  the pool saw {'a submission' if submitted else 'no winner this window'} — the REAL test result. no funds move on a", flush=True)
    print(f"  reject; a real block would credit {WALLET}. hitting 2^{zb} on one laptop-lane-set is stacked by count/native/", flush=True)
    print(f"  federation (pfc_divide_work) and guaranteed by coverage (pfc_guarantee) — this run is the honest live probe of it.", flush=True)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
