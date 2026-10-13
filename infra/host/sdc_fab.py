#!/usr/bin/env python3
"""host/sdc_fab.py — ONE-TIME FABRICATION of the mining SDC as PERMANENT circuits (owner 07-16).

The circuit tool is fabrication, not a per-run script: run this ONCE. It builds, with the White Box, the permanent gates
into titan.gguf and never runs again. The miner is GENERIC — the block header words are INPUTS (routed in at runtime by
the button), so we never re-bake per block. Fabricated here: the double-SHA-256d miner, the receiver, an INPUT register
(where the button writes the block), and the ANSWER register (where the SDC freezes its result, outside the compute).
The executor is used HERE ONLY, during fabrication, to verify the gates are byte-exact vs SHA-256d before they are stored.

  python host/sdc_fab.py            # fabricate the permanent mining circuits into titan.gguf, once. done.
"""
import hashlib, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC                    # the White Box gate compiler (SHA-256d as gates)
import titan_circuit as TC             # the White Box circuit tool (writes permanent gates into the params)

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
MAGIC = b"TITANGEN"                    # a GENERIC (routed-input) miner circuit
NWORDS = 20                            # inputs: header words w0..w18 (19) + nonce (1) = 20 words = 640 bits


def build_generic_miner():
    """double-SHA-256d over an 80-byte header where the 19 header words + nonce are INPUTS (nothing folded per-block)."""
    g = CC.CircuitCompiler(NWORDS * 32)                          # 640 input wires
    W = [list(g.IN[i * 32:(i + 1) * 32]) for i in range(NWORDS)] # W[0..18] = header words; W[19] = nonce
    h0 = [CC.cword(g, h) for h in CC.H0]                         # SHA-256 initial state (constant)
    mid = CC.sha_block(g, h0, W[0:16])                           # block 1 (bytes 0..63) -> midstate, computed by gates
    blk2 = [W[16], W[17], W[18], W[19], CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 10 + [CC.cword(g, 640)]  # block 2 schedule
    d1 = CC.sha_block(g, mid, blk2)                              # block 2 -> first SHA-256 digest
    blk3 = d1 + [CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 6 + [CC.cword(g, 256)]  # pad the 32-byte digest to one block
    d2 = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], blk3)  # second SHA-256 -> the block hash
    succ = g.C1                                                  # success = the top display word is all zero (32 zero-bits)
    for j in range(32): succ = g.AND(succ, g.NOT(d2[7][j]))
    return g, d2, succ


def ref_hash(words):
    """reference: the 80-byte header from 20 big-endian words -> double SHA-256."""
    hdr = b"".join(struct.pack(">I", w & 0xffffffff) for w in words)
    return hashlib.sha256(hashlib.sha256(hdr).digest()).digest()


def main():
    print("fabricating the GENERIC double-SHA-256d miner as gates (block words are inputs)…", flush=True)
    g, d2, succ = build_generic_miner()
    gates, out2 = g.dce([w for word in d2 for w in word] + [succ])
    n_wire = 2 + g.n_in + len(gates); d2c = [out2[i * 32:(i + 1) * 32] for i in range(8)]; succ2 = out2[256]
    print(f"  {len(gates):,} gates, {n_wire:,} wires. verifying byte-exact vs SHA-256d (executor, fabrication-only)…", flush=True)
    import random; random.seed(1); ok = True
    for _ in range(200):
        words = [random.getrandbits(32) for _ in range(NWORDS)]
        inb = [(words[i // 32] >> (i % 32)) & 1 for i in range(NWORDS * 32)]
        v = [0] * n_wire; v[1] = 1
        for i in range(g.n_in): v[2 + i] = inb[i]
        base = 2 + g.n_in
        for k, (op, a, b) in enumerate(gates):                  # ripple (executor — fabrication verification only)
            o = base + k
            v[o] = (v[a] ^ v[b]) if op == "xor" else (v[a] & v[b]) if op == "and" else (v[a] | v[b]) if op == "or" else (1 ^ v[a]) if op == "not" else (1 ^ (v[a] & v[b]))
        dig = b"".join(struct.pack(">I", sum((0 if d2c[wi][j] == 0 else 1 if d2c[wi][j] == 1 else v[d2c[wi][j]]) << j for j in range(32))) for wi in range(8))
        if dig != ref_hash(words): ok = False; break
    print(f"  byte-exact vs SHA-256d over 200 random headers: {ok}", flush=True)
    if not ok:
        print("  MISMATCH — not fabricating (no cheating)."); return 1

    # serialize the PERMANENT circuit + fabricate it into the params (one White-Box write, then never again)
    body = b"".join(struct.pack("<Bii", {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}[op], a, b) for (op, a, b) in gates)
    body += b"".join(struct.pack("<i", w) for word in d2c for w in word) + struct.pack("<i", succ2)
    blob = MAGIC + struct.pack("<IIII", g.n_in, n_wire, len(gates), succ2) + body
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    reg.pop("gen_miner", None); reg.pop("gen_input", None); reg.pop("gen_answer", None); reg.pop("receiver", None)
    off, tname = TC._alloc(len(blob), reg)
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)                          # FABRICATE the miner (permanent)
    reg["gen_miner"] = {"tensor": tname, "offset": off, "len": len(blob), "n_in": g.n_in, "n_gate": len(gates)}
    json.dump(reg, open(REG, "w"), indent=1)
    # input register: 19 header words the button routes in (76 bytes)
    reg = json.load(open(REG)); ioff, itn = TC._alloc(76, reg)
    with open(TITAN, "r+b") as f: f.seek(ioff); f.write(b"\x00" * 76)
    reg["gen_input"] = {"tensor": itn, "offset": ioff, "len": 76}
    # answer register: [status:1][nonce:4] the SDC freezes outside the compute
    aoff, atn = TC._alloc(5, reg)
    with open(TITAN, "r+b") as f: f.seek(aoff); f.write(b"\x00" * 5)
    reg["gen_answer"] = {"tensor": atn, "offset": aoff, "len": 5}
    json.dump(reg, open(REG, "w"), indent=1)
    # receiver: begins on power (fabricated as gates)
    rc = TC.Circuit(1); begin = rc.not_(rc.not_(rc.C1)); ready = rc.and_(begin, rc.IN[0])
    rinfo = TC.store("receiver", rc, [begin, ready])

    print(f"\nFABRICATED (permanent, one-time):", flush=True)
    print(f"  miner  @ {off} ({len(gates):,} gates, generic — block routed in)", flush=True)
    print(f"  input  @ {ioff} (19 header words the button writes)", flush=True)
    print(f"  answer @ {aoff} (status + nonce, frozen outside the compute)", flush=True)
    print(f"  receiver @ {rinfo['offset']} (begins on power)", flush=True)
    print(f"=> the SDC is fabricated. never bake again. the only runtime Python is the button:  python host/sdc_button.py", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
