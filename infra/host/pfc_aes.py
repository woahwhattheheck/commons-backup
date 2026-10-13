#!/usr/bin/env python3
"""host/pfc_aes.py — BAKE AES-128 as gates: a DATA-OBLIVIOUS, constant-time block cipher (owner 07-19).

The flagship secure-compute bake: AES-128 encryption as a pure gate circuit. Because it is gates, it is data-oblivious
by construction — no S-box table lookup that leaks through the cache, no data-dependent branch. Byte-exact verified
against the FIPS-197 known-answer vector AND random plaintext/keys vs a reference, before anything is stored. Baked
permanent + reversible. The S-box is built as a mux-tree over the constant table; the compiler folds it, and the whole
thing routes through the optimal-implementation discipline.

  python host/pfc_aes.py           # build + verify (KAT + random) + bake AES-128 permanent
  python host/pfc_aes.py revert
"""
import json, os, random, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_aes_genome.jsonl"

SBOX = [
0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16]
RCON = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36]


# ===================== reference AES-128 (for verification) =====================
def ref_encrypt(pt, key):
    def xt(a): return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff
    w = [list(key[4*i:4*i+4]) for i in range(4)]
    for i in range(4, 44):
        t = list(w[i-1])
        if i % 4 == 0:
            t = t[1:] + t[:1]; t = [SBOX[b] for b in t]; t[0] ^= RCON[i//4 - 1]
        w.append([w[i-4][j] ^ t[j] for j in range(4)])
    s = [list(pt[4*c:4*c+4]) for c in range(4)]                    # s[col][row]
    def ark(rnd):
        for c in range(4):
            for r in range(4): s[c][r] ^= w[rnd*4 + c][r]
    ark(0)
    for rnd in range(1, 11):
        for c in range(4):
            for r in range(4): s[c][r] = SBOX[s[c][r]]              # SubBytes
        rows = [[s[c][r] for c in range(4)] for r in range(4)]      # ShiftRows
        for r in range(4): rows[r] = rows[r][r:] + rows[r][:r]
        for c in range(4):
            for r in range(4): s[c][r] = rows[r][c]
        if rnd != 10:                                              # MixColumns
            for c in range(4):
                a = s[c][:]
                s[c][0] = xt(a[0]) ^ (xt(a[1]) ^ a[1]) ^ a[2] ^ a[3]
                s[c][1] = a[0] ^ xt(a[1]) ^ (xt(a[2]) ^ a[2]) ^ a[3]
                s[c][2] = a[0] ^ a[1] ^ xt(a[2]) ^ (xt(a[3]) ^ a[3])
                s[c][3] = (xt(a[0]) ^ a[0]) ^ a[1] ^ a[2] ^ xt(a[3])
        ark(rnd)
    return bytes(s[c][r] for c in range(4) for r in range(4))


# ===================== AES-128 as gates =====================
def build_aes(g):
    IN = g.IN
    byte = lambda base, i: list(IN[base + i*8: base + i*8 + 8])     # 8 wires LSB-first
    pt = [byte(0, i) for i in range(16)]; key = [byte(128, i) for i in range(16)]
    xor = lambda a, b: [g.XOR(a[i], b[i]) for i in range(8)]

    def sbox(x):                                                   # mux-tree over the constant S-box table
        out = []
        for j in range(8):
            cur = [g.C1 if (SBOX[i] >> j) & 1 else g.C0 for i in range(256)]
            for lvl in range(8):
                s = x[lvl]; ns = g.NOT(s); cur = [g.OR(g.AND(ns, cur[i]), g.AND(s, cur[i+1])) for i in range(0, len(cur), 2)]
            out.append(cur[0])
        return out

    def xtime(a):
        sh = [g.C0] + a[:7]; msb = a[7]; rc = [1, 1, 0, 1, 1, 0, 0, 0]      # 0x1b
        return [g.XOR(sh[i], g.AND(msb, g.C1) ) if False else g.XOR(sh[i], (msb if rc[i] else g.C0)) for i in range(8)]

    # key expansion (words = 4 bytes each)
    w = [[key[4*0+r] for r in range(4)]]  # placeholder to shape; rebuild properly below
    w = []
    for i in range(4): w.append([key[4*i + r] for r in range(4)])
    for i in range(4, 44):
        t = [b[:] for b in w[i-1]]
        if i % 4 == 0:
            t = t[1:] + t[:1]; t = [sbox(b) for b in t]
            rc = RCON[i//4 - 1]; t[0] = [g.XOR(t[0][k], g.C1) if (rc >> k) & 1 else t[0][k] for k in range(8)]
        w.append([xor(w[i-4][r], t[r]) for r in range(4)])

    s = [[pt[4*c + r] for r in range(4)] for c in range(4)]         # s[col][row]
    def ark(rnd):
        for c in range(4):
            for r in range(4): s[c][r] = xor(s[c][r], w[rnd*4 + c][r])
    ark(0)
    for rnd in range(1, 11):
        for c in range(4):
            for r in range(4): s[c][r] = sbox(s[c][r])
        rows = [[s[c][r] for c in range(4)] for r in range(4)]
        for r in range(4): rows[r] = rows[r][r:] + rows[r][:r]
        for c in range(4):
            for r in range(4): s[c][r] = rows[r][c]
        if rnd != 10:
            for c in range(4):
                a = [s[c][r][:] for r in range(4)]
                s[c][0] = xor(xor(xtime(a[0]), xor(xtime(a[1]), a[1])), xor(a[2], a[3]))
                s[c][1] = xor(xor(a[0], xtime(a[1])), xor(xor(xtime(a[2]), a[2]), a[3]))
                s[c][2] = xor(xor(a[0], a[1]), xor(xtime(a[2]), xor(xtime(a[3]), a[3])))
                s[c][3] = xor(xor(xor(xtime(a[0]), a[0]), a[1]), xor(a[2], xtime(a[3])))
        ark(rnd)
    return [s[c][r][b] for c in range(4) for r in range(4) for b in range(8)]   # 128 output wires


def _inbits(pt, key):
    b = [0]*256
    for i in range(16):
        for k in range(8): b[i*8 + k] = (pt[i] >> k) & 1
    for i in range(16):
        for k in range(8): b[128 + i*8 + k] = (key[i] >> k) & 1
    return b


def backup_and_write(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("aes128", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan byte-exact; aes128 removed."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    # reference sanity vs FIPS-197 KAT
    pt0 = bytes.fromhex("00112233445566778899aabbccddeeff"); key0 = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    kat = "69c4e0d86a7b0430d8cdb78070b4c55a"
    ok_ref = ref_encrypt(pt0, key0).hex() == kat
    print(f"reference AES vs FIPS-197 KAT: {ok_ref}", flush=True)
    if not ok_ref: print("reference wrong — aborting."); return 1

    print("building AES-128 as gates (S-box mux-tree + key schedule + 10 rounds); folding …", flush=True)
    g = CC.CircuitCompiler(256); outs = g.build_outs = build_aes(g)
    gates, out2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    print(f"  built {len(gates):,} gates. verifying byte-exact vs the reference (KAT + random) …", flush=True)

    def enc_gates(pt, key):
        v = CC.ripple_typed(g, gates, n_wire, _inbits(pt, key), 1)
        bits = [v[w] if w >= 2 else w for w in out2]
        return bytes(sum(bits[i*8 + k] << k for k in range(8)) for i in range(16))

    ok = enc_gates(pt0, key0).hex() == kat
    random.seed(7)
    for _ in range(20):
        pt = bytes(random.getrandbits(8) for _ in range(16)); key = bytes(random.getrandbits(8) for _ in range(16))
        if enc_gates(pt, key) != ref_encrypt(pt, key): ok = False; break
    print(f"  AES-128 gate circuit byte-exact (KAT + 20 random): {ok}", flush=True)
    if not ok:
        print("  MISMATCH — baking nothing (no cheating)."); return 1

    code = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
    body = b"".join(struct.pack("<Bii", code[op], a, b) for (op, a, b) in gates) + b"".join(struct.pack("<i", w) for w in out2)
    blob = b"PFCTYPED" + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(out2)) + body
    reg = json.load(open(REG))
    if "aes128" in reg: print("  aes128 already baked. revert first."); return 0
    off, tn = TC._alloc(len(blob), reg); backup_and_write(off, blob)
    reg = json.load(open(REG))
    reg["aes128"] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": 256, "n_wire": n_wire,
                     "n_gate": len(gates), "n_out": 128, "format": "typed",
                     "layout_in": "plaintext:128|key:128", "layout_out": "ciphertext:128",
                     "role": "AES-128 encrypt, data-oblivious (constant-time, no cache-timing side channel)"}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"\nBAKED aes128 @ {off} ({len(gates):,} gates, 256 in -> 128 out). titan GGUF-valid: {gg}.", flush=True)
    print(f"  a data-oblivious, constant-time AES-128 lives in the permanent binary. revert: python host/pfc_aes.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
