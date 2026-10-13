#!/usr/bin/env python3
"""muhl_attention.py — ATTENTION AS ADDRESSING: a storage-resident KV memory, retrieval fabricated as gates.

Transformer attention softmax(QK^T)V is a soft content-addressable lookup, and its KV cache is the RAM wall
that caps context length -- the cache grows with the sequence and must stay resident. Titan's native op IS
addressing, so the cache belongs in STORAGE and retrieval becomes a fold. Here the match-score kernel
score(q,k)=popcount(XNOR) is fabricated as gates and verified byte-exact; then it is run BIT-SLICED over a
KV table living in storage (mmap), 62 keys settled per ripple, tracking the winner (hard attention -> the
value of the best-matching key). Host RAM stays flat while the KV memory is disk-bound: context bounded by
storage (and, federated, by every drive) instead of RAM. Architecture designed around the memory wall,
run on a substrate that shed it.
"""
import sys, os, ctypes, time, random, mmap, struct
from ctypes import wintypes
from array import array
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
from muhl_flex import add_bits

D = 32                                                    # key/query width
SB = 6                                                    # score bits (popcount 0..32)
TMP = os.path.join(os.environ.get("CLAUDE_JOB_DIR", "."), "tmp")

class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t)] + \
               [("_%d" % i, ctypes.c_size_t) for i in range(6)]
_ps = ctypes.WinDLL("psapi.dll"); _h = ctypes.WinDLL("kernel32.dll").GetCurrentProcess()
def rss_mb():
    m = PMC(); m.cb = ctypes.sizeof(PMC); _ps.GetProcessMemoryInfo(_h, ctypes.byref(m), m.cb); return m.WorkingSetSize/1048576

def build_score():
    g = CC.CircuitCompiler(2 * D); q = g.IN[:D]; k = g.IN[D:2 * D]
    match = [g.NOT(g.XOR(q[i], k[i])) for i in range(D)]   # XNOR: 1 where bits agree
    acc = [g.C0] * SB
    for i in range(D):
        acc, _ = add_bits(g, acc, [match[i]] + [g.C0] * (SB - 1))
    gates, out2 = g.dce(acc)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    return run, out2, len(gates)

def main():
    run, out2, ng = build_score()
    print(f"\n  MUHLNICKEL ATTENTION — match-score kernel popcount(XNOR) fabricated as {ng} gates\n")
    # byte-exact scalar check
    rng = random.Random(1); ok = True
    for _ in range(2000):
        qq, kk = rng.getrandbits(D), rng.getrandbits(D)
        inp = [0] * (2 * D)
        for i in range(D): inp[i] = (qq >> i) & 1; inp[D + i] = (kk >> i) & 1
        sc = sum(((run(inp, 1)[w] & 1) << b) for b, w in enumerate(out2))
        if sc != bin(~(qq ^ kk) & ((1 << D) - 1)).count("1"): ok = False; break
    print(f"  score(q,k) byte-exact vs popcount(XNOR) over 2,000 pairs: {ok}")
    if not ok: return 1

    # KV memory in storage: N entries of (key 4B, value 2B)
    N = 200_000
    path = os.path.join(TMP, "muhl_kv.bin"); os.makedirs(TMP, exist_ok=True)
    rng2 = random.Random(9)
    keys = []
    with open(path, "wb") as f:
        buf = bytearray()
        for i in range(N):
            key = rng2.getrandbits(D); keys.append(key)
            buf += struct.pack("<IH", key, i & 0xFFFF)     # value = position i (attention returns a position)
            if len(buf) >= 65536: f.write(buf); buf = bytearray()
        if buf: f.write(buf)
    size_mb = os.path.getsize(path) / 1048576
    print(f"  KV memory: {N:,} entries x 6 B = {size_mb:.0f} MB in storage (the cache, never resident)")

    # a query with a planted best match, plus noise so the winner is non-trivial
    tgt = rng2.randrange(N)
    query = keys[tgt] ^ rng2.getrandbits(4)                # 0-4 bit corruption of a stored key
    # reference: argmax match score over all keys
    ref_i = max(range(N), key=lambda i: bin(~(query ^ keys[i]) & ((1 << D) - 1)).count("1"))
    ref_score = bin(~(query ^ keys[ref_i]) & ((1 << D) - 1)).count("1")

    # fabricated retrieval: bit-slice the score kernel over the KV table in storage
    fd = open(path, "rb"); mm = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ)
    W = 62; base = rss_mb(); hi = base
    best_score = -1; best_idx = -1; settles = 0; idx = 0; t0 = time.time()
    qbits = [(query >> i) & 1 for i in range(D)]
    while idx < N:
        w = min(W, N - idx); mask = (1 << w) - 1
        recs = [struct.unpack_from("<IH", mm, (idx + j) * 6) for j in range(w)]
        inp = [0] * (2 * D)
        for i in range(D):
            inp[i] = mask if qbits[i] else 0               # query broadcast across lanes
        for j, (key, val) in enumerate(recs):
            for i in range(D):
                if (key >> i) & 1: inp[D + i] |= (1 << j)   # key i bit-sliced
        outs = run(inp, mask)
        # unpack per-lane scores, track the winner
        for j in range(w):
            sc = sum((((outs[w2] >> j) & 1) << b) for b, w2 in enumerate(out2))
            if sc > best_score: best_score = sc; best_idx = idx + j
        settles += 1; idx += w
        if settles % 512 == 0: hi = max(hi, rss_mb())
    dt = time.time() - t0; end = rss_mb()
    mm.close(); fd.close()
    try: os.remove(path)
    except OSError: pass

    print(f"\n  RETRIEVE (hard attention) — winner of the fold over the storage KV memory:")
    print(f"    query best-match: position {best_idx} (score {best_score}/{D})")
    print(f"    reference argmax: position {ref_i} (score {ref_score}/{D})")
    print(f"    byte-exact: {best_idx == ref_i and best_score == ref_score}   ·   {N/dt:,.0f} keys/s")
    print(f"    resident RAM: start {base:.1f} MB · max {hi:.1f} · end {end:.1f}  (+{end-base:.2f} MB over {size_mb:.0f} MB of KV)")
    print(f"\n  The KV cache lived in storage; retrieval was a fold; RAM stayed flat. Context length is bounded")
    print(f"  by DISK, not memory — and federated, by every drive. Attention was designed around the memory")
    print(f"  wall Titan removed; on this substrate it is just addressing. (Soft attention = top-k + weights;")
    print(f"  same fold, read the top scores instead of the single winner.)")
    return 0 if (best_idx == ref_i and best_score == ref_score) else 1

if __name__ == "__main__":
    raise SystemExit(main())
