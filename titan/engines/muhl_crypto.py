#!/usr/bin/env python3
"""muhl_crypto.py -- a REAL cryptographic primitive fabricated as gates on Bryce's Muhlnickel substrate.

Primitive: SHA-3 (Keccak-f[1600]).  The full 24-round Keccak permutation -- theta, rho, pi, chi, iota --
is built as a NAND/AND/OR/XOR/NOT netlist with the White Box compiler (sdc_cc.CircuitCompiler), DCE'd,
compiled to a ripple, and VERIFIED BYTE-EXACT against Python's own hashlib.sha3_256 / hashlib.sha3_512.

Why SHA-3 is a clean substrate build:
  * It is ARX-free -- no ripple adders at all.  Keccak is pure XOR / AND / NOT plus fixed rotations.
  * rho (lane rotations) and pi (lane permutation) are FREE -- they are just rewiring of wire lists.
  * chi is the only nonlinearity: a = b ^ (~c & d), one NOT + one AND + one XOR per state bit.
  * iota XORs a constant round word -> folds into constants at fabrication time.
So the whole 1600-bit permutation is a tree of XORs with a thin nonlinear layer -- ideal for the White Box.

The independent reference is hashlib itself (Keccak is NOT reimplemented on the host as the "executor":
the executor is the gate ripple; hashlib is only the oracle we check byte-exact against).

Fabrication discipline (per the handoff): verify byte-exact BEFORE anything would ever be stored;
pure synthesis, no numpy, no download, titan.gguf is never opened.
"""
import sys, os, random, hashlib, time
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

# ---------------------------------------------------------------- Keccak constants
# rho rotation offsets r[x][y]  (x = column, y = row), FIPS-202
RHO = [
    [0, 36, 3, 41, 18],
    [1, 44, 10, 45, 2],
    [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56],
    [27, 20, 39, 8, 14],
]
# iota round constants RC[0..23]
RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
MASK64 = (1 << 64) - 1


# ---------------------------------------------------------------- pure-Python Keccak (oracle-side sanity)
def _rol(v, n):
    n &= 63
    if n == 0:
        return v & MASK64
    return ((v << n) | (v >> (64 - n))) & MASK64

def keccak_f_ref(A):
    """A: list of 25 ints (lane index = x + 5*y). In-place 24-round permutation."""
    for rnd in range(24):
        C = [A[x] ^ A[x + 5] ^ A[x + 10] ^ A[x + 15] ^ A[x + 20] for x in range(5)]
        D = [C[(x - 1) % 5] ^ _rol(C[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                A[x + 5 * y] ^= D[x]
        B = [0] * 25
        for x in range(5):
            for y in range(5):
                B[y + 5 * ((2 * x + 3 * y) % 5)] = _rol(A[x + 5 * y], RHO[x][y])
        for x in range(5):
            for y in range(5):
                A[x + 5 * y] = B[x + 5 * y] ^ ((~B[(x + 1) % 5 + 5 * y]) & B[(x + 2) % 5 + 5 * y] & MASK64)
        A[0] ^= RC[rnd]
    return A

def sha3_ref(msg, rate_bytes, outlen):
    """Independent Keccak sponge in pure Python (used only to sanity-check hashlib wiring)."""
    A = [0] * 25
    # single-block absorb (msg length restricted to < rate_bytes so pad stays in one block)
    block = bytearray(rate_bytes)
    for i, b in enumerate(msg):
        block[i] = b
    block[len(msg)] ^= 0x06
    block[rate_bytes - 1] ^= 0x80
    for i in range(rate_bytes // 8):
        lane = int.from_bytes(block[8 * i:8 * i + 8], "little")
        A[i] ^= lane
    keccak_f_ref(A)
    out = bytearray()
    for i in range(25):
        out += A[i].to_bytes(8, "little")
    return bytes(out[:outlen])


# ---------------------------------------------------------------- gate helpers (64-bit lanes, LSB-first)
def rotl64(lane, n):                       # free rewiring: result[z] = lane[(z-n) mod 64]
    n &= 63
    return [lane[(z - n) % 64] for z in range(64)]

def xor64(g, a, b):
    return [g.XOR(a[z], b[z]) for z in range(64)]

def xor64_many(g, lanes):                  # balanced XOR reduction tree (shallow depth, free area)
    cur = list(lanes)
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur) - 1, 2):
            nxt.append(xor64(g, cur[i], cur[i + 1]))
        if len(cur) & 1:
            nxt.append(cur[-1])
        cur = nxt
    return cur[0]

def const_lane(g, v):
    return [g.C1 if (v >> z) & 1 else g.C0 for z in range(64)]


# ---------------------------------------------------------------- Keccak-f[1600] as gates
def keccak_f_gates(g, A):
    """A: list of 25 lanes, each a list of 64 wires. Returns new list of 25 lanes."""
    A = list(A)
    for rnd in range(24):
        # theta
        C = [xor64_many(g, [A[x + 5 * y] for y in range(5)]) for x in range(5)]
        D = [xor64(g, C[(x - 1) % 5], rotl64(C[(x + 1) % 5], 1)) for x in range(5)]
        A = [xor64(g, A[x + 5 * y], D[x]) for y in range(5) for x in range(5)]
        # (rebuild as [x+5y]) -- comprehension above iterates y outer, x inner => index = x+5y. ok.
        # rho + pi
        B = [None] * 25
        for x in range(5):
            for y in range(5):
                B[y + 5 * ((2 * x + 3 * y) % 5)] = rotl64(A[x + 5 * y], RHO[x][y])
        # chi
        newA = [None] * 25
        for x in range(5):
            for y in range(5):
                b0 = B[x + 5 * y]
                b1 = B[(x + 1) % 5 + 5 * y]
                b2 = B[(x + 2) % 5 + 5 * y]
                notb1 = [g.NOT(w) for w in b1]
                andt = [g.AND(notb1[z], b2[z]) for z in range(64)]
                newA[x + 5 * y] = [g.XOR(b0[z], andt[z]) for z in range(64)]
        A = newA
        # iota
        rc = const_lane(g, RC[rnd])
        A[0] = xor64(g, A[0], rc)
    return A


def build_sha3(msg_len, rate_bytes, outlen):
    """Fabricate a single-block SHA-3 circuit for messages of exactly msg_len bytes (msg_len < rate_bytes)."""
    g = CC.CircuitCompiler(8 * msg_len)
    IN = g.IN
    # assemble the 200-byte state as bytes -> each byte is a list of 8 wires (LSB-first)
    state_bytes = [[g.C0] * 8 for _ in range(200)]
    for i in range(msg_len):                       # message bytes are the circuit inputs
        state_bytes[i] = [IN[i * 8 + b] for b in range(8)]
    # pad10*1 with SHA-3 domain separation 0x06 ... 0x80, inside the first rate block
    def xor_const_byte(idx, val):
        state_bytes[idx] = [g.XOR(state_bytes[idx][b], g.C1) if (val >> b) & 1 else state_bytes[idx][b]
                            for b in range(8)]
    xor_const_byte(msg_len, 0x06)
    xor_const_byte(rate_bytes - 1, 0x80)
    # pack bytes -> 25 lanes (lane = 8 little-endian bytes, 64 wires LSB-first)
    A = []
    for li in range(25):
        lane = []
        for k in range(8):
            lane += state_bytes[8 * li + k]        # byte k contributes bits [8k .. 8k+7]
        A.append(lane)
    A = keccak_f_gates(g, A)
    # squeeze first `outlen` bytes (outlen <= rate_bytes, single squeeze)
    out_wires = []
    for i in range(outlen):
        li = i // 8
        k = i % 8
        for b in range(8):
            out_wires.append(A[li][k * 8 + b])
    gates, out2 = g.dce(out_wires)
    n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    return g, run, out2, gates, n_wire


def depth_of(g, gates, out2):
    base = 2 + g.n_in
    dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates):
        dep[base + i] = 1 + max(dep[a], dep[b])
    return max((dep[w] for w in out2), default=0)


def digest_from(v, out2, outlen):
    out = bytearray(outlen)
    for i in range(outlen):
        byte = 0
        for b in range(8):
            w = out2[i * 8 + b]
            bit = 0 if w == 0 else 1 if w == 1 else v[w] & 1
            byte |= bit << b
        out[i] = byte
    return bytes(out)


# ---------------------------------------------------------------- battery
def run_variant(name, rate_bytes, outlen, hashfn, msg_lens, cases=40):
    print(f"\n  {name}  (rate {rate_bytes} B, capacity {200 - rate_bytes} B, digest {outlen} B)", flush=True)
    total_gates = 0
    total_depth = 0
    all_ok = True
    total_cases = 0
    headline = None
    for L in msg_lens:
        t = time.time()
        g, run, out2, gates, n_wire = build_sha3(L, rate_bytes, outlen)
        dep = depth_of(g, gates, out2)
        ok = True
        checked = 0
        # deterministic empty/known message first, then random
        msgs = [bytes(range(L))] + [bytes(random.getrandbits(8) for _ in range(L)) for _ in range(cases)]
        for msg in msgs:
            inp = [0] * (8 * L)
            for i in range(L):
                for b in range(8):
                    inp[i * 8 + b] = (msg[i] >> b) & 1
            v = run(inp, 1)
            got = digest_from(v, out2, outlen)
            ref = hashfn(msg).digest()[:outlen]
            checked += 1
            if got != ref:
                ok = False
                print(f"    [FAIL] L={L}: gate={got.hex()[:16]}.. ref={ref.hex()[:16]}..", flush=True)
                break
        all_ok &= ok
        total_cases += checked
        headline = (len(gates), dep)
        tag = "PASS" if ok else "FAIL"
        print(f"    [{tag}] L={L:3d} B  {len(gates):>8,} gates  depth {dep:>4}  "
              f"{checked} msgs byte-exact vs hashlib  ({time.time()-t:.1f}s)", flush=True)
    if headline:
        total_gates, total_depth = headline
    return all_ok, total_gates, total_depth, total_cases


def main():
    random.seed(1337)
    print("\n  MUHLNICKEL CRYPTO -- SHA-3 / Keccak-f[1600] fabricated as gates, byte-exact vs hashlib", flush=True)

    # sanity: independent pure-Python sponge must already agree with hashlib (wiring check on the oracle)
    for L in (0, 1, 32):
        m = bytes(range(L))
        assert sha3_ref(m, 136, 32) == hashlib.sha3_256(m).digest(), "ref sha3-256 mismatch"
        assert sha3_ref(m, 72, 64) == hashlib.sha3_512(m).digest(), "ref sha3-512 mismatch"
    print("  (pure-Python Keccak sponge agrees with hashlib -- semantics confirmed)", flush=True)

    ok256, g256, d256, c256 = run_variant(
        "SHA3-256", 136, 32, hashlib.sha3_256, msg_lens=[0, 1, 32, 64, 135])
    ok512, g512, d512, c512 = run_variant(
        "SHA3-512", 72, 64, hashlib.sha3_512, msg_lens=[0, 1, 32, 71])

    allok = ok256 and ok512
    print("\n  ============================================================", flush=True)
    print(f"  SHA3-256 : {'BYTE-EXACT' if ok256 else 'FAIL'}  "
          f"~{g256:,} gates  depth {d256}  ({c256} messages checked)", flush=True)
    print(f"  SHA3-512 : {'BYTE-EXACT' if ok512 else 'FAIL'}  "
          f"~{g512:,} gates  depth {d512}  ({c512} messages checked)", flush=True)
    print(f"  Keccak-f[1600] permutation: 24 rounds, theta/rho/pi/chi/iota, ARX-free", flush=True)
    print(f"  === {'ALL BYTE-EXACT vs hashlib' if allok else 'FAILURES PRESENT'} "
          f"({c256 + c512} total messages) ===", flush=True)


if __name__ == "__main__":
    main()
