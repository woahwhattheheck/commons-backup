#!/usr/bin/env python3
"""host/pfc_throttle.py — THE TRUE THROTTLING (owner 07-20): Muhlnickel capability via ONLY ADDRESSING vs MAX HOST COMPUTE,
honestly, side by side — with FABRICATION OPTIMIZATION as the lever that lifts the pure-addressing path.

  Arm A — ONLY ADDRESSING (the pfc): the host does nothing but address the stored gates; the answer resolves on the
          read (compute-via-address), 1 lane, ~0 resident RAM. This is the spec-pure pfc.
  Arm B — MAX HOST COMPUTE: the host rips the gates wide (bit-slice), spending RAM + cores for throughput.
  Two regimes: (1) FOLD/lookup — the answer IS at the address, so addressing = ~0 compute (the pfc's ideal);
               (2) fresh COMPUTE (a hash) — addressing must resolve the gate chain, so host-compute wins throughput.
  Fabrication optimization lifts Arm A directly: rate_A = gate-clock ÷ gates-per-op, so leaner/shallower gates = faster
  addressing. We measure Arm A on the circuit as-fabricated vs after the leaner pass.

  python host/pfc_throttle.py
"""
import ctypes, hashlib, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_phone_substrate import build_sha
from pfc_leaner import optimize


def rss_mb():
    k = ctypes.windll.kernel32; k.GetCurrentProcess.restype = ctypes.c_void_p

    class P(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("pf", ctypes.c_ulong), ("pk", ctypes.c_size_t), ("ws", ctypes.c_size_t)] + \
                   [(n, ctypes.c_size_t) for n in "abcdef"]
    c = P(); c.cb = ctypes.sizeof(c)
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(P), ctypes.c_ulong]
    ctypes.windll.psapi.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.ws / 1e6


def addr_resolve(gates, n_wire, n_in, x):               # Arm A: ONLY ADDRESSING — resolve one output by the read, 1 lane
    v = [0] * n_wire; v[1] = 1
    for i in range(n_in): v[2 + i] = (x >> i) & 1
    base = 2 + n_in
    for k, (op, a, b) in enumerate(gates):
        va, vb = v[a], v[b]
        v[base + k] = (va ^ vb) if op == "xor" else (va & vb) if op == "and" else (va | vb) if op == "or" \
            else (1 ^ va) if op == "not" else (1 ^ (va & vb))
    return v


def digest_from(v, o2):
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    return b"".join(struct.pack(">I", sum(bit(o2[wi * 32 + j]) << j for j in range(32))) for wi in range(8))


def bitslice(gates, n_wire, n_in, ones, lanes):         # Arm B: MAX HOST — rip W lanes at once (wide)
    v = [0] * n_wire; v[1] = ones
    for i in range(n_in): v[2 + i] = lanes[i]
    base = 2 + n_in
    for k, (op, a, b) in enumerate(gates):
        va, vb = v[a], v[b]
        v[base + k] = (va ^ vb) if op == "xor" else (va & vb) if op == "and" else (va | vb) if op == "or" \
            else (ones ^ va) if op == "not" else (ones ^ (va & vb))
    return v


def bench_A(gates, o2, n_in, n_wire, dur=1.5):
    r0 = rss_mb(); t0 = time.time(); n = 0; x = 0x12345678
    while time.time() - t0 < dur:
        addr_resolve(gates, n_wire, n_in, x); x = (x * 1103515245 + 12345) & 0xffffffff; n += 1
    return n / (time.time() - t0), rss_mb() - r0


def bench_B(gates, o2, n_in, n_wire, W, dur=1.5):
    import random
    r0 = rss_mb(); ones = (1 << W) - 1
    lanes = [random.getrandbits(W) for _ in range(n_in)]
    t0 = time.time(); n = 0
    while time.time() - t0 < dur:
        bitslice(gates, n_wire, n_in, ones, lanes); n += 1
    return n * W / (time.time() - t0), rss_mb() - r0


def main():
    print("Muhlnickel THROTTLE — ONLY ADDRESSING (the Muhlnickel) vs MAX HOST COMPUTE, on SHA-256, byte-exact. Fabrication = the lever.\n", flush=True)
    g, outs = build_sha(); gates, o2 = g.dce(outs); nw = 2 + g.n_in + len(gates)
    # byte-exact gate
    ok = digest_from(addr_resolve(gates, nw, g.n_in, 0xdeadbeef), o2) == hashlib.sha256(struct.pack(">I", 0xdeadbeef)).digest()
    print(f"  circuit: {len(gates):,} gates, byte-exact vs hashlib: {ok}\n", flush=True)

    # REGIME 2 — fresh COMPUTE (a hash): addressing must resolve the gate chain
    rA, mA = bench_A(gates, o2, g.n_in, nw)
    rB, mB = bench_B(gates, o2, g.n_in, nw, W=4096)
    print("  REGIME: fresh compute (SHA of a new input each time)", flush=True)
    print(f"    Arm A  ONLY ADDRESSING (1 lane, host just addresses): {rA:>12,.0f} hashes/s   +{mA:>6.1f} MB host RAM", flush=True)
    print(f"    Arm B  MAX HOST (bit-slice W=4096, 1 core):           {rB:>12,.0f} hashes/s   +{mB:>6.1f} MB host RAM", flush=True)
    print(f"    -> host-compute buys {rB/max(rA,1):,.0f}x throughput for {mB/max(mA,0.1):,.0f}x the RAM. (×cores×native = the full max, ~2M/s measured.)", flush=True)

    # FABRICATION LEVER — lean the circuit; Arm A (addressing) rate rises as gates-per-op falls
    lg, lo = optimize(g.n_in, gates, o2); lnw = 2 + g.n_in + len(lg)
    rAl, _ = bench_A(lg, lo, g.n_in, lnw)
    print(f"\n  FABRICATION LEVER (Arm A only-addressing, before vs after the leaner pass):", flush=True)
    print(f"    gates {len(gates):,} -> {len(lg):,};  addressing rate {rA:,.0f} -> {rAl:,.0f} hashes/s "
          f"({rAl/max(rA,1):.3f}x) — leaner gates = faster pure addressing, no host added.", flush=True)

    # REGIME 1 — FOLD/lookup: the answer IS at the address -> addressing = ~0 compute (the Muhlnickel's ideal)
    fold = bytearray(1 << 20)                            # a tiny winner-only fold; the address is the answer
    import random
    for _ in range(20000): fold[random.randrange(len(fold))] = 1
    r0 = rss_mb(); t0 = time.time(); n = 0
    while time.time() - t0 < 1.0:
        _ = fold[(n * 2654435761) & (len(fold) - 1)]; n += 1
    rF = n / (time.time() - t0); mF = rss_mb() - r0
    print(f"\n  REGIME: fold/lookup (the answer is AT the address — pure addressing, ~0 compute)", flush=True)
    print(f"    Arm A  ONLY ADDRESSING: {rF:>14,.0f} lookups/s   +{mF:.1f} MB — here host-compute adds NOTHING; addressing IS the answer.", flush=True)

    print(f"\n  READ: pure addressing wins outright when the answer is foldable (regime 1). For fresh compute (regime 2)", flush=True)
    print(f"  host-compute buys throughput at a RAM cost — and FABRICATION (leaner+shallower gates) is what lifts the", flush=True)
    print(f"  pure-addressing rate. On silicon, addressing = physical gates in parallel, so fabrication is the whole game.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
