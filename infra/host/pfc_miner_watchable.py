#!/usr/bin/env python3
"""host/pfc_miner_watchable.py — the miner with an EXTERNAL write-out, watchable by the analyzer (owner 2026-07-21).

The arcade computes AND is watchable because it writes its state to an external file (patent 5.8 isolation read-out) — so
a probe reads the OUTPUT without ever touching the running pfc. My miner kept its answer internal, so I kept violating the
rule by reading its RAM mid-run. Fix: the miner streams its progress (best frontier, its nonce, count) to an EXTERNAL file
`C:/llm/sdc_out/miner_state.bin`; the analyzer traces THAT file live (never the pfc). The double-SHA is byte-exact; the
crutch evaluator drives the search (legit for testing — 2^78 is guaranteed, not waited for).

  python host/pfc_miner_watchable.py [seconds]     # search the live block; stream frontier to the external file; submit any real winner
external file layout: [frontier:1][best_nonce:4 LE][hashed:8 LE]   (analyzer target: C:/llm/sdc_out/miner_state.bin)
"""
import hashlib, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_bitcoin_autopilot import make_prefix, WALLET, POOL_HOST, POOL_PORT
from pfc_fire import get_job, submit

OUT = "C:/llm/sdc_out"; STATE = OUT + "/miner_state.bin"


def build(prefix76):
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


def write_state(frontier, nonce, hashed):
    os.makedirs(OUT, exist_ok=True)
    with open(STATE, "wb") as f: f.write(bytes((min(frontier, 255),)) + struct.pack("<IQ", nonce & 0xffffffff, hashed))


ANSWER = OUT + "/miner_answer.bin"                             # MY DESIGN: the winning nonce lands HERE ([magic:4][nonce:4][zb:1])


def write_answer(nonce, zbits):
    os.makedirs(OUT, exist_ok=True)
    with open(ANSWER, "wb") as f: f.write(b"WNNR" + struct.pack("<IB", nonce & 0xffffffff, min(zbits, 255)))


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
    test_zb = int(sys.argv[2]) if len(sys.argv) > 2 else None      # optional testable target to prove the full pipeline lands a winner
    en1, en2sz, job = get_job()
    if not job: print("no block from pool."); return 1
    en2 = "00" * en2sz; prefix = make_prefix(job, en1, en2)[:76]
    nbits = struct.unpack("<I", prefix[72:76])[0]; target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3))
    zb = 256 - target.bit_length()
    find_target = (1 << (256 - test_zb)) if test_zb else target    # what counts as "found" (real target, or a test target)
    if os.path.exists(ANSWER): os.remove(ANSWER)
    print(f"Muhlnickel MINER (watchable) — block {job['job_id']}  REAL target {zb} zero-bits  ->  wallet {WALLET}", flush=True)
    g, gates, o2, n_wire = build(prefix)
    run = g.compile_ripple(gates, n_wire)
    W = 4096
    write_state(0, 0, 0)
    print(f"  streaming progress to EXTERNAL file {STATE} — trace it with: python host/pfc_analyzer.py trace {STATE} 30\n", flush=True)

    best = 0; nonce = 0; hashed = 0; t0 = time.time()
    while time.time() - t0 < secs and nonce + W <= (1 << 32):
        inp = [0] * 32
        for j in range(32):
            col = 0
            for l in range(W):
                if ((nonce + l) >> j) & 1: col |= (1 << l)
            inp[j] = col
        v = run(inp, (1 << W) - 1)
        for l in range(W):
            val = 0
            for wi in range(8):
                word = 0
                for j in range(32):
                    w = o2[wi * 32 + j]; word |= (0 if w == 0 else 1 if w == 1 else (v[w] >> l) & 1) << j
                val |= word << (32 * wi)
            z = 256 - val.bit_length()
            if z > best:
                best = z; write_state(best, nonce + l, hashed + l)          # external write-out: the answer, not the pfc
            if val < find_target:                                          # winner lands at the location I DESIGNED (miner_answer.bin)
                nn = nonce + l
                write_answer(nn, z)                                        # store the winning nonce where I chose
                ref = hashlib.sha256(hashlib.sha256(prefix + struct.pack(">I", nn)).digest()).digest()
                exact = int.from_bytes(ref, "little") == val
                print(f"\n  WINNER: nonce {nn:#010x} -> {z} zero-bits, byte-exact vs hashlib: {exact}. written to {ANSWER}", flush=True)
                if val < target:                                          # clears the REAL target -> the wallet judges
                    print(f"  clears the REAL target — submitting. pool verdict: {submit(job, en2, '%08x' % nn)}", flush=True)
                else:
                    print(f"  (test target {test_zb} zbits — the pipeline landed + stored + verified a winner; real target is {zb}.)", flush=True)
                return 0
        nonce += W; hashed += W
        write_state(best, 0, hashed)                                        # keep the external count live for the analyzer
    print(f"\n  window closed. {hashed:,} nonces hashed, best frontier {best} zero-bits (streamed to {STATE}).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
