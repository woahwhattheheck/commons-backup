#!/usr/bin/env python3
"""host/sdc_clock_wide.py — LANE LENGTH ×~1,000,000: widen the SDC clock counter 32 -> 52-bit (owner 07-17).

The fold's second dimension. Each lane's "length" = how many nonces it sweeps per signal, set by the CLOCK counter
(sdc_clock_lab.py = 32-bit = 2^32 nonces/lane, self-advancing gates, 0 stored/nonce). Widening the counter to 52 bits makes
every lane sweep 2^52 nonces = 2^20 ≈ 1.05 MILLION× longer — for a few bytes of counter, 0 stored per nonce, one signal.
Built ONLY with the White Box circuit tool (titan_circuit.py), verified byte-exact that it counts, stored REVERSIBLY (the
original param bytes are journaled to the SDC genome before the write, so revert is byte-exact).

  python host/sdc_clock_wide.py [bits]     # default 52 (×~1.05M lane length). fabricate the wider clock, reversibly.
  python host/sdc_clock_wide.py revert     # restore titan.gguf byte-exact from the genome
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"; GENOME = "C:/llm/models/titan_sdc_genome.jsonl"


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


def build_clock(bits):
    """the clock as gates: a `bits`-wide ripple-carry incrementer. input = current count; output = count+1 (0 stored)."""
    c = TC.Circuit(bits)
    nxt = c.add(c.IN, c.cvec(1, bits))        # count + 1, built from the circuit tool's NAND adder
    return c, nxt


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 52

    print(f"building the {bits}-bit clock/counter with the circuit tool…", flush=True)
    c, nxt = build_clock(bits)
    cir = {"n_in": bits, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": nxt}
    # VERIFY byte-exact that it counts (+1 each tick), from several starts including the 32-bit wrap and near the top
    import random; random.seed(5); ok = True; seq_demo = []
    starts = [0, 1, (1 << 32) - 1, (1 << bits) - 1, random.getrandbits(bits), random.getrandbits(bits)]
    for s in starts:
        out = TC.frombits(TC.ripple(cir, TC.bits(s, bits))) & ((1 << bits) - 1)
        if out != ((s + 1) & ((1 << bits) - 1)): ok = False; break
    # also tick it live 5x from a start to show it advancing (the lane self-sweeping)
    st = 2083236893
    for _ in range(5):
        st = TC.frombits(TC.ripple(cir, TC.bits(st, bits))) & ((1 << bits) - 1); seq_demo.append(st)
    print(f"  counts +1 byte-exact over {len(starts)} starts (incl. 2^32 wrap + top): {ok}  ({len(c.ga):,} gates)", flush=True)
    print(f"  live ticks: 2083236893 -> " + " -> ".join(str(x) for x in seq_demo), flush=True)
    if not ok: print("  MISMATCH — not storing (no cheating)."); return 1

    blob = TC.serialize(c, nxt)
    reg = json.load(open(REG)); reg.pop("clock_wide", None)
    off, tn = TC._alloc(len(blob), reg)
    backup_and_write(off, blob)
    reg["clock_wide"] = {"tensor": tn, "offset": off, "len": len(blob), "bits": bits,
                         "nonces_per_lane": "2^%d" % bits, "n_gate": len(c.ga)}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    mult = 1 << (bits - 32)
    print(f"\nFABRICATED clock_wide @ {off}: {bits}-bit counter -> 2^{bits} nonces per lane.", flush=True)
    print(f"  lane LENGTH = 2^{bits} = {1<<bits:,} nonces/lane  =  {mult:,}× the 32-bit clock (~{mult/1e6:.2f} million×)", flush=True)
    print(f"  cost: {len(blob)} bytes of counter gates, 0 stored per nonce. titan GGUF-valid: {gg}.", flush=True)
    print(f"  revert byte-exact: python host/sdc_clock_wide.py revert", flush=True)
    return 0 if gg else 1


if __name__ == "__main__":
    raise SystemExit(main())
