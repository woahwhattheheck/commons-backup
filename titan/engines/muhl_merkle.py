#!/usr/bin/env python3
"""muhl_merkle.py — VERIFIABLE DATA STRUCTURES: SHA-256 fabricated as gates -> a Merkle tree + inclusion proofs.

SHA-256 of a 64-byte node (two child digests) is fabricated as a gate netlist and verified byte-exact vs
hashlib. A Merkle tree is then built over N leaves through that gate function, and an inclusion proof for a
leaf is checked by recomputing the root through the same gates -- byte-exact. This is the primitive under
blockchain light clients, certificate transparency, content-addressed storage, and tamper-evident logs:
prove a record is in a dataset without holding the dataset. The verifier is gates; the tree is storage.
"""
import sys, os, hashlib, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
from muhl_flex import add_bits, consts

def rotr(x, n): return [x[(i + n) % 32] for i in range(32)]
def shr(x, n):  return [x[i + n] if i + n < 32 else 0 for i in range(32)]   # 0 == g.C0
def xorw(g, *xs):
    o = list(xs[0])
    for y in xs[1:]: o = [g.XOR(o[k], y[k]) for k in range(32)]
    return o
def addw(g, *xs):
    o = list(xs[0])
    for y in xs[1:]: o, _ = add_bits(g, o, y)
    return o

K256 = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2]
H0 = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]

def sha256_block(g, H, block16):
    W = list(block16)
    for t in range(16, 64):
        s0 = xorw(g, rotr(W[t-15],7), rotr(W[t-15],18), shr(W[t-15],3))
        s1 = xorw(g, rotr(W[t-2],17), rotr(W[t-2],19), shr(W[t-2],10))
        W.append(addw(g, W[t-16], s0, W[t-7], s1))
    a,b,c,d,e,f,h = H[0],H[1],H[2],H[3],H[4],H[5],H[6]
    hh = H[7]
    for t in range(64):
        S1 = xorw(g, rotr(e,6), rotr(e,11), rotr(e,25))
        ch = [g.XOR(g.AND(e[k],f[k]), g.AND(g.NOT(e[k]),h[k])) for k in range(32)]   # Ch uses g (=my h)
        t1 = addw(g, hh, S1, ch, consts(g,K256[t],32), W[t])                          # T1 leads with h (=my hh)
        S0 = xorw(g, rotr(a,2), rotr(a,13), rotr(a,22))
        maj = [g.XOR(g.XOR(g.AND(a[k],b[k]), g.AND(a[k],c[k])), g.AND(b[k],c[k])) for k in range(32)]
        t2 = addw(g, S0, maj)
        hh=h; h=f; f=e; e=addw(g,d,t1); d=c; c=b; b=a; a=addw(g,t1,t2)
    return [addw(g,H[i],[a,b,c,d,e,f,h,hh][i]) for i in range(8)]

def h_arr(g, x): return (x,)  # noop helper to keep line above readable

def bytes_to_words(g, IN, base_bit, nbytes):
    """big-endian: word = 4 bytes MSB-first; returns list of 32-bit LSB-first wire lists."""
    words = []
    for w in range(nbytes // 4):
        bits = []
        for byte in range(4):
            for bit in range(8):                          # wire index 0 is already the byte's MSB
                bits.append(IN[base_bit + (w*4+byte)*8 + bit])
        # bits is MSB-first (bit0 = value's MSB) -> convert to LSB-first list
        words.append([bits[31-k] for k in range(32)])
    return words

def build_node():
    """SHA-256(left||right): 64-byte message -> two padded blocks, fabricated as gates."""
    g = CC.CircuitCompiler(64*8)                           # 64 input bytes
    msg = bytes_to_words(g, g.IN, 0, 64)                   # 16 words
    # block 1 = the 64 message bytes; block 2 = padding (0x80, zeros, len=512)
    blk1 = msg
    pad = [consts(g, 0x80000000, 32)] + [consts(g,0,32) for _ in range(13)] + [consts(g,0,32), consts(g,512,32)]
    H = [consts(g, v, 32) for v in H0]
    H = sha256_block(g, H, blk1)
    H = sha256_block(g, H, pad)
    outs = [w for word in H for w in word]
    gates, out2 = g.dce(outs)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    words_out = [out2[i*32:(i+1)*32] for i in range(8)]
    def node(left32, right32):
        msg = left32 + right32
        inp = [0]*(64*8)
        for i,byte in enumerate(msg):
            for bit in range(8):
                if (byte>>(7-bit))&1: inp[i*8+bit] = 1     # MSB-first, matching bytes_to_words
        v = run(inp, 1)
        out = bytearray()
        for wf in words_out:
            val = sum((v[w]&1)<<k for k,w in enumerate(wf))
            out += val.to_bytes(4, "big")
        return bytes(out)
    return node, len(gates)

def main():
    print("\n  MUHLNICKEL MERKLE — SHA-256 node hash fabricated as gates, then verifiable inclusion proofs\n")
    node, ng = build_node()
    # byte-exact vs hashlib on random 64-byte nodes
    rng = random.Random(2); ok = True
    for _ in range(8):
        l = bytes(rng.getrandbits(8) for _ in range(32)); r = bytes(rng.getrandbits(8) for _ in range(32))
        if node(l, r) != hashlib.sha256(l+r).digest(): ok = False; break
    print(f"  SHA-256(left||right) fabricated as {ng:,} gates · byte-exact vs hashlib over 8 nodes: {ok}")
    if not ok: print("  MISMATCH"); return 1

    # build a Merkle tree over N leaves THROUGH the gate node function
    N = 8
    leaves = [hashlib.sha256(f"record-{i}".encode()).digest() for i in range(N)]
    level = list(leaves); tree = [level]
    while len(level) > 1:
        level = [node(level[i], level[i+1]) for i in range(0, len(level), 2)]
        tree.append(level)
    root = tree[-1][0]
    # reference root via hashlib directly
    def ref_root(ls):
        lv = list(ls)
        while len(lv) > 1: lv = [hashlib.sha256(lv[i]+lv[i+1]).digest() for i in range(0,len(lv),2)]
        return lv[0]
    print(f"  Merkle root over {N} leaves (built through the gates) == hashlib root: {root == ref_root(leaves)}")
    print(f"    root = {root.hex()[:32]}...")

    # inclusion proof for one leaf, verified through the gate node function
    idx = 5; proof = []; i = idx
    for lvl in tree[:-1]:
        sib = i ^ 1; proof.append((lvl[sib], i & 1)); i //= 2
    acc = leaves[idx]
    for sib, right in proof:
        acc = node(sib, acc) if right else node(acc, sib)
    print(f"  inclusion proof for leaf {idx}: {len(proof)} sibling hashes, recomputes root through gates: {acc == root}")
    tampered = bytearray(leaves[idx]); tampered[0] ^= 1
    acc2 = bytes(tampered)
    for sib, right in proof: acc2 = node(sib, acc2) if right else node(acc2, sib)
    print(f"  tampered leaf is REJECTED (root differs): {acc2 != root}")
    print(f"\n  Prove membership in a dataset without holding the dataset: {len(proof)} hashes verify one record")
    print(f"  against a 32-byte root. The verifier is gates; the tree is storage. Light clients, transparency")
    print(f"  logs, content-addressed dedup, tamper-evident audit -- all at flat RAM, byte-exact.")
    return 0 if (ok and root == ref_root(leaves) and acc == root and acc2 != root) else 1

if __name__ == "__main__":
    raise SystemExit(main())
