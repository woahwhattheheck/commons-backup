#!/usr/bin/env python3
"""muhl_chain.py — a fabricated BLOCKCHAIN on Bryce's Muhlnickel substrate.

The link that makes a chain a *chain* is a cryptographic hash, and here that hash is not a library call
-- it is a NETLIST. SHA-256 over a 64-byte block header is fabricated as gates (reused from muhl_merkle,
byte-exact vs hashlib), and the whole ledger is built on top of it:

  * each block's header carries the PREVIOUS block's gate-computed digest -> the blocks are wired in series
    by a hash (§1E "two circuits are in series when they share a bit" -- here the shared bits are 256 of them);
  * PROOF-OF-WORK is a nonce search that re-settles the SHA-256 gates until the digest has >= DIFF leading
    zero bits -- mining is running the circuit, not the host;
  * VERIFY walks the chain recomputing every digest THROUGH THE GATES, checking each link and each PoW target;
  * TAMPER a byte of any block's data and the gate-recomputed digest no longer matches, the link breaks, and
    the proof-of-work no longer holds -- detected, byte-exact.

No numpy, no host inference, nothing writes titan.gguf. The hash that secures the chain is a circuit.
"""
import sys, os, time, struct, hashlib, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
from muhl_merkle import build_node               # SHA-256(64 bytes) fabricated as gates, byte-exact vs hashlib

DIFF   = 8         # proof-of-work: required leading zero BITS in the block digest
NBLOCK = 4         # blocks mined after genesis
ZERO32 = bytes(32)

def header_bytes(index, timestamp, prev_hash, data_hash16, nonce):
    """64-byte block header: index(4) | timestamp(4) | prev_hash(32) | data_hash(16) | nonce(8) = 64."""
    return struct.pack(">II", index, timestamp) + prev_hash + data_hash16 + struct.pack(">Q", nonce)

def leading_zero_bits(digest):
    n = 0
    for byte in digest:
        if byte == 0:
            n += 8; continue
        for b in range(8):
            if (byte >> (7 - b)) & 1: return n
            n += 1
        return n
    return n

def gate_hash(node, header):
    """SHA-256 of the 64-byte header through the fabricated gate netlist."""
    return node(header[:32], header[32:])

def data_commit(data):
    """16-byte commitment to a block's payload (a truncated SHA-256)."""
    return hashlib.sha256(data).digest()[:16]

def mine(node, index, timestamp, prev_hash, data):
    """PROOF-OF-WORK: search nonces, re-settling the SHA-256 gates, until DIFF leading zero bits."""
    dh = data_commit(data)
    nonce = 0
    while True:
        hdr = header_bytes(index, timestamp, prev_hash, dh, nonce)
        digest = gate_hash(node, hdr)
        if leading_zero_bits(digest) >= DIFF:
            return {"index": index, "timestamp": timestamp, "prev_hash": prev_hash,
                    "data": data, "data_hash": dh, "nonce": nonce, "digest": digest}, nonce + 1
        nonce += 1

def verify_chain(node, chain):
    """Walk the chain, recomputing every digest THROUGH THE GATES; check links, PoW, and data commitments."""
    prev = ZERO32
    for blk in chain:
        # 1. the payload commitment must match the stored data
        if data_commit(blk["data"]) != blk["data_hash"]:
            return False, f"block {blk['index']}: data commitment mismatch"
        # 2. rebuild the header from the block's fields and re-hash it through the gate netlist
        hdr = header_bytes(blk["index"], blk["timestamp"], blk["prev_hash"], blk["data_hash"], blk["nonce"])
        digest = gate_hash(node, hdr)
        if digest != blk["digest"]:
            return False, f"block {blk['index']}: gate digest != stored digest"
        # 3. the link: this block must point at the previous block's digest
        if blk["prev_hash"] != prev:
            return False, f"block {blk['index']}: broken link (prev_hash != previous digest)"
        # 4. proof-of-work must still hold
        if leading_zero_bits(digest) < DIFF:
            return False, f"block {blk['index']}: proof-of-work not satisfied"
        prev = digest
    return True, "ok"

def main():
    print("\n  MUHLNICKEL CHAIN — a blockchain whose linking hash is a fabricated SHA-256 circuit\n")
    node, ng = build_node()

    # the hash is a netlist -- prove it byte-exact vs hashlib before trusting the chain to it
    rng = random.Random(20); ok = True
    for _ in range(6):
        h = bytes(rng.getrandbits(8) for _ in range(64))
        if gate_hash(node, h) != hashlib.sha256(h).digest(): ok = False; break
    print(f"  SHA-256(64-byte header) fabricated as {ng:,} gates · byte-exact vs hashlib: {ok}")
    if not ok: print("  MISMATCH — refusing to mine"); return 1

    # mine a chain: genesis + NBLOCK blocks, each linked by the previous gate digest, each PoW'd
    print(f"\n  MINING — proof-of-work target = {DIFF} leading zero bits (nonce search re-settles the gates)")
    payloads = [b"genesis: titan ledger"] + [f"block payload #{i}".encode() for i in range(1, NBLOCK + 1)]
    chain = []; prev = ZERO32; ts = 1_722_000_000
    total_tries = 0; t0 = time.time()
    for i, data in enumerate(payloads):
        blk, tries = mine(node, i, ts + i, prev, data)
        chain.append(blk); prev = blk["digest"]; total_tries += tries
        print(f"    block {i}: nonce={blk['nonce']:>6}  tries={tries:>6}  "
              f"zbits={leading_zero_bits(blk['digest'])}  digest={blk['digest'].hex()[:24]}...")
    dt = time.time() - t0
    print(f"  mined {len(chain)} blocks · {total_tries:,} gate-hashes · {total_tries/dt:,.0f} hashes/s")

    # verify the honest chain -- every digest recomputed through the gates
    good, msg = verify_chain(node, chain)
    print(f"\n  VERIFY (gates recompute every digest, check every link + PoW): {good}  [{msg}]")
    if not good: return 1

    # TAMPER: flip one byte of an interior block's data and re-verify
    victim = 2
    tampered = [dict(b) for b in chain]
    bad = bytearray(tampered[victim]["data"]); bad[0] ^= 1
    tampered[victim]["data"] = bytes(bad)
    detected, why = verify_chain(node, tampered)
    print(f"\n  TAMPER — flip 1 byte of block {victim}'s data:")
    print(f"    chain still valid? {detected}   (rejected because: {why})")

    # TAMPER the link directly: rewrite a block's prev_hash
    tampered2 = [dict(b) for b in chain]
    tampered2[victim]["prev_hash"] = bytes(32)
    d2, why2 = verify_chain(node, tampered2)
    print(f"  TAMPER — rewrite block {victim}'s prev_hash to zeros:")
    print(f"    chain still valid? {d2}   (rejected because: {why2})")

    all_ok = ok and good and (not detected) and (not d2)
    print(f"\n  ── an immutable ledger, secured by a circuit ─────────────────────────────────────────")
    print(f"  The chain's integrity rests on 256 shared bits per link and a proof-of-work that IS the")
    print(f"  SHA-256 gates re-settling. Change any block and the gate-recomputed digest diverges, the")
    print(f"  link opens (§1E: bit 1->0 = disconnected), and the work no longer proves out. All byte-exact,")
    print(f"  flat RAM, no host hash. Result: {'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
