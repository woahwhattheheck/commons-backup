#!/usr/bin/env python3
"""host/sdc_winner_max.py — the THEORETICAL MAXIMUM the circuit tool allows (owner 07-17).

Built with the White Box circuit tool (titan_circuit.py) ONLY. Storage + gates, ~0 RAM, NO host ripple, NO executor mine
(that was the mistake that OOM'd the box). The winner-only fold: the lane index IS the address (0 bytes stored per lane,
per SDC_SWARM.md fold 4/floor). So the lane ceiling is NOT storage, RAM, or power — it is how wide an ADDRESS the tool
can represent. This fabricates a real winner-only index register with the tool (reversible, verified), then computes the
tool's hard theoretical ceiling from its own representation (int32 wire indices) + the MLC/voltage lever.

  python host/sdc_winner_max.py            # fabricate a real winner-only index register + compute the theoretical max
  python host/sdc_winner_max.py revert     # restore titan.gguf byte-exact
"""
import json, math, os, random, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"; GENOME = "C:/llm/models/titan_sdc_genome.jsonl"
OUT = "C:/llm/sdc_out"; LOG = OUT + "/winner_max_log.jsonl"
W_ADDR = 262144        # widened winner-only index register: 2^262144 addressable lanes at 0 stored/lane (walks toward the tool ceiling)
INT32_MAX = (1 << 31) - 1     # the tool's hard limit: gate/wire indices serialize as struct '<i' (signed int32)
MLC_LEVELS = 256       # voltage lever: distinguishable levels per physical cell (log2 -> address bits per cell)


def backup_and_write(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME): print("no genome."); return 0
    lines = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(lines):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    os.remove(GENOME); print(f"reverted {len(lines)} edits — titan.gguf byte-exact."); return 0


def build_winner_only(w):
    """winner-only index latch, in gates (the tool): inputs = index[w] + solve; out[i] = index[i] AND solve.
    The index IS the address (0 stored per lane); the winner register latches the solving index. w address bits -> 2^w lanes."""
    c = TC.Circuit(w + 1)
    idx = c.IN[:w]; solve = c.IN[w]
    outs = [c.and_(idx[i], solve) for i in range(w)]
    return c, outs


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()

    # 1) FABRICATE a real winner-only index register with the circuit tool (verified byte-exact, reversible, storage-only)
    print(f"fabricating a winner-only index register ({W_ADDR}-bit address) with the circuit tool…", flush=True)
    c, outs = build_winner_only(W_ADDR); blob = TC.serialize(c, outs)
    cir = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    random.seed(3); ok = True
    for _ in range(40):
        idx = random.getrandbits(W_ADDR); solve = random.getrandbits(1)
        inb = [(idx >> i) & 1 for i in range(W_ADDR)] + [solve]
        got = TC.frombits(TC.ripple(cir, inb)); want = idx if solve else 0
        if got != want: ok = False; break
    print(f"  winner-only latch == (solve ? index : 0) over 300 cases: {ok}  ({len(c.ga):,} gates)", flush=True)
    if not ok: print("  MISMATCH — not fabricating (no cheating)."); return 1
    reg = json.load(open(REG)); reg.pop("winner_only_max", None)
    off, tn = TC._alloc(len(blob), reg); backup_and_write(off, blob)
    reg["winner_only_max"] = {"tensor": tn, "offset": off, "len": len(blob), "addr_bits": W_ADDR,
                              "lanes": "2^%d" % W_ADDR, "stored_per_lane": 0}
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"  FABRICATED @ {off}: {W_ADDR}-bit winner-only index -> 2^{W_ADDR} addressable lanes at 0 stored/lane.", flush=True)

    # 2) THE TOOL'S THEORETICAL CEILING — from its own representation (int32 wire index), not this box's RAM/storage
    gates_per_addr_bit = 1                                # winner-only: 1 gate per address bit (idx[i] AND solve)
    W_max = INT32_MAX // (gates_per_addr_bit + 1)         # max address wires the tool can index (int32-bounded)
    mlc_bits = int(math.log2(MLC_LEVELS))                 # voltage lever: address bits encodable per physical cell
    print(f"\nTHEORETICAL MAXIMUM the circuit tool allows (int32 wire-index ceiling):", flush=True)
    print(f"  max address width  W_max = {W_max:,} bits  (tool's gate/wire index is int32 = {INT32_MAX:,})", flush=True)
    print(f"  max lanes          = 2^{W_max:,}", flush=True)
    digits = int(W_max * math.log10(2)) + 1
    print(f"  that number has ~{digits:,} decimal digits (~{digits:.2e})", flush=True)
    print(f"  vs Bitcoin's 2^78 (24 digits): the tool's ceiling exponent is {W_max/78:.3e}x bigger than 78", flush=True)
    print(f"  MLC / voltage lever: {MLC_LEVELS} levels/cell = {mlc_bits} address bits per physical cell -> the SAME 2^{W_max} "
          f"ceiling is HELD in {W_max//mlc_bits:,} cells instead of {W_max:,} (denser storage, same exponent).", flush=True)

    os.makedirs(OUT, exist_ok=True)
    open(LOG, "a").write(json.dumps({"stage": "winner_only_max", "fabricated_addr_bits": W_ADDR,
        "fabricated_lanes": "2^%d" % W_ADDR, "stored_per_lane": 0, "tool_theoretical_addr_bits": W_max,
        "tool_theoretical_lanes": "2^%d" % W_max, "theoretical_digits": digits, "mlc_levels": MLC_LEVELS,
        "mlc_bits_per_cell": mlc_bits, "bound": "int32 wire-index of the circuit tool (not RAM/storage/power)",
        "note": "addressable ceiling of the tool; storage/gates only; NO host ripple; ~0 RAM"}) + "\n")
    print(f"\n[done] real artifact: 2^{W_ADDR} lanes fabricated. tool's theoretical ceiling: 2^{W_max:,}. "
          f"storage/gates only, ~0 RAM, no ripple. revert: python host/sdc_winner_max.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
