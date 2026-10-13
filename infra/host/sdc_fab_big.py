#!/usr/bin/env python3
"""host/sdc_fab_big.py — FABRICATE the enlarged Bitcoin SDC: the SHARED-VECTOR + WINNER-ONLY fold (owner 07-17).

Cost model: compute is light-speed and free; the only cost is communicating a single bit (the signal). Storage is the
only ceiling. So we drive the per-lane storage toward 0 with the densest fold, all via the White Box circuit tool
(`titan_circuit`), one-time, PERMANENT, REVERSIBLE (a genome journals every overwritten byte range -> byte-exact revert).

The fold (docs/SDC_SWARM.md):
  - ONE shared miner circuit (`gen_miner`, the generic double-SHA-256d, block routed in) — referenced by every group,
    not copied. (Fixes the old "100 literal 1.92 MB copies + overlapping registers" design.)
  - ONE shared WIN comparator (`win = hash < target`), verified byte-exact vs Python's own `< target`.
  - ONE shared TARGET register (difficulty, routed in once by the button).
  - N GROUP descriptors, ~81 bytes each (a 76-byte header input register + a 5-byte answer register). Each group = a
    distinct extranonce2 -> a distinct header -> its own 2^32 nonce field; the nonce IS the address (0 bytes/lane,
    winner-only). So N groups cover N * 2^32 lanes for ~81*N bytes -> lanes-per-byte -> 0, storage-bound.
The self-advancing nonce is the proven CLOCK (sdc_clock_lab, a gate incrementer). Runtime = the one-time button
(sdc_button_big.py): route each group's header + the target, fire ONE power signal, die. Nothing else runs on the SDC.

  python host/sdc_fab_big.py [n_groups]     # fabricate the fold (default 4096 groups = 2^32*4096 = 2^44 lanes)
  python host/sdc_fab_big.py revert         # restore titan.gguf byte-exact from the genome
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_sdc_genome.jsonl"          # reversible edit journal
GROUP_BYTES = 81                                         # per group: 76-byte header input + 5-byte answer register


def backup_and_write(off, blob):
    """REVERSIBLE write: journal the original bytes at [off, off+len) to the genome, THEN overwrite. Byte-exact revertible."""
    with open(TITAN, "rb") as f:
        f.seek(off); original = f.read(len(blob))
    with open(GENOME, "a") as g:
        g.write(json.dumps({"off": off, "orig": original.hex()}) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME):
        print("no genome — nothing to revert."); return 0
    lines = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(lines):
        b = bytes.fromhex(e["orig"])
        with open(TITAN, "r+b") as f:
            f.seek(int(e["off"])); f.write(b)
    os.remove(GENOME)
    print(f"reverted {len(lines)} edits — titan.gguf restored byte-exact.")
    return 0


def build_comparator():
    """WIN = (hash < target), both 256-bit little-endian (Bitcoin's comparison). Pure gates (the circuit baker)."""
    c = TC.Circuit(512)
    A = c.IN[0:256]; B = c.IN[256:512]                    # A = hash, B = target (LSB-first)
    lt = c.C0; eq = c.C1
    for i in range(255, -1, -1):                          # MSB down
        a = A[i]; b = B[i]
        lt = c.or_(lt, c.and_(eq, c.and_(c.not_(a), b)))  # A<B if higher bits equal and a<b here
        eq = c.and_(eq, c.not_(c.xor(a, b)))
    return c, [lt]


def le_bits(digest32):
    val = int.from_bytes(digest32, "little")
    return [(val >> i) & 1 for i in range(256)]


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    n_groups = int(sys.argv[1]) if len(sys.argv) > 1 else 4096

    reg = json.load(open(REG))
    if "gen_miner" not in reg:
        print("gen_miner not fabricated — run sdc_fab.py first."); return 1
    for k in [k for k in reg if k.startswith("clone_") or k in ("win_cmp", "target_reg", "groups_block")]:
        reg.pop(k, None)                                  # drop any stale names from a prior fabrication (bytes already reverted)
    json.dump(reg, open(REG, "w"), indent=1)

    # 1) fabricate + verify the WIN comparator (difficulty-aware; the requested change), REVERSIBLE
    print("fabricating the WIN comparator (hash < target) as gates…", flush=True)
    cc, outs = build_comparator(); blob = TC.serialize(cc, outs)
    import random, hashlib; random.seed(2); ok = True
    for _ in range(3000):
        d = random.randbytes(32); t = random.getrandbits(256)
        inb = le_bits(d) + [(t >> i) & 1 for i in range(256)]
        if TC.ripple({"n_in": 512, "n_wire": cc.n_wire(), "ga": cc.ga, "gb": cc.gb, "outs": outs}, inb)[0] != (1 if int.from_bytes(d, "little") < t else 0):
            ok = False; break
    print(f"  comparator == (hash < target) over 3000 random cases: {ok}  ({len(cc.ga):,} gates)", flush=True)
    if not ok:
        print("  MISMATCH — not fabricating (no cheating)."); return 1
    reg = json.load(open(REG)); coff, ctn = TC._alloc(len(blob), reg)
    backup_and_write(coff, blob)
    reg["win_cmp"] = {"tensor": ctn, "offset": coff, "len": len(blob), "n_in": 512, "n_gate": len(cc.ga)}

    # 2) shared TARGET register (32 bytes) — the difficulty, routed in once by the button
    toff, ttn = TC._alloc(32, reg)
    backup_and_write(toff, b"\x00" * 32)
    reg["target_reg"] = {"tensor": ttn, "offset": toff, "len": 32}

    # 3) N GROUP descriptors as ONE contiguous, reversible block (fast, and no register can overlap another)
    total = n_groups * GROUP_BYTES
    boff, btn = TC._alloc(total, reg)
    backup_and_write(boff, b"\x00" * total)               # one reversible write for all groups
    reg["groups_block"] = {"tensor": btn, "offset": boff, "len": total, "n_groups": n_groups,
                           "group_bytes": GROUP_BYTES, "miner_off": int(reg["gen_miner"]["offset"]), "cmp_off": coff,
                           "target_off": toff}
    json.dump(reg, open(REG, "w"), indent=1)

    lanes = n_groups * (1 << 32)
    import math
    print(f"\nFABRICATED (reversible, shared-vector + winner-only fold):", flush=True)
    print(f"  1 shared miner (@ {reg['gen_miner']['offset']}) + 1 comparator (@ {coff}) + 1 target reg (@ {toff})", flush=True)
    print(f"  {n_groups:,} groups x 2^32 = {lanes:,} lanes  (2^{math.log2(lanes):.1f})  covered by ONE signal", flush=True)
    print(f"  storage for the fold: {total/1e3:.1f} KB total  ->  {total/lanes:.2e} bytes/lane  (~0, storage-bound)", flush=True)
    print(f"  revert byte-exact any time:  python host/sdc_fab_big.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
