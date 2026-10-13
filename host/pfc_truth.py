#!/usr/bin/env python3
"""host/pfc_truth.py — BOOLEAN TRUTH TABLE instrument for the Muhlnickel (owner: Bryce, 2026-07-21).

Enumerate a chosen SMALL set of a stored Muhlnickel's input bits, hold the rest fixed, resolve the gates, and print the truth
table: those inputs -> chosen outputs. Bounded (<= 2^14 rows), observation with the high-impedance probe I already created — it exhaustively verifies a
circuit's logic over the chosen sub-cube, straight from the stored gates. High-impedance: it only reads the netlist and
resolves a bounded row set; it is a bench instrument, not the runtime.

  python host/pfc_truth.py <circuit> --vary i,j,k [--fix idx=val,...] [--out a,b,...] [--labels ...]
  python host/pfc_truth.py pfc_full_miner            # preset: the self-clock + winner-latch truth table
"""
import json, os, struct, sys, itertools
sys.stdout.reconfigure(encoding="utf-8")
TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"


def load(name):
    e = json.load(open(REG))[name]
    with open(TITAN, "rb") as f: f.seek(int(e["offset"])); blob = f.read(int(e["len"]))
    assert blob[:8] == b"PFCTYPED", f"{name} is not a typed circuit"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((op, a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    return n_in, n_wire, gates, outs


def resolve(gates, n_wire, n_in, inb):                        # one bounded ripple = evaluate the stored gates for this row
    v = [0] * n_wire; v[1] = 1
    for i in range(n_in): v[2 + i] = inb[i]
    base = 2 + n_in
    for k, (op, a, b) in enumerate(gates):
        va = v[a]; vb = v[b]
        v[base + k] = (va & vb) if op == 1 else (va | vb) if op == 2 else (va ^ vb) if op == 3 else (1 ^ va) if op == 4 else (1 ^ (va & vb))
    return v


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 1
    name = sys.argv[1]; args = sys.argv[2:]
    n_in, n_wire, gates, outs = load(name)

    # preset for the complete miner: show the self-clock (nonce+1 gated by power) + the winner-latch, byte-clean
    if name == "pfc_full_miner" and "--vary" not in args:
        vary = [928, 608, 609]                                # power, nonce bit0, nonce bit1
        fixed = {i: 1 for i in range(640, 896)}               # target = all-ones -> hash < target is ALWAYS true (win=1)
        out_ix = [0, 1, 2, 32, 33, 34]                        # nonce'[0..2], latch'[0..2]
        labels = ["power", "n0", "n1", "n'0", "n'1", "n'2", "L'0", "L'1", "L'2"]
        note = "target=all-ones so win=1 every row: watch nonce' = nonce+1 when power=1 (self-clock), latch' = nonce (latch)"
    else:
        def grab(flag, d=""):
            return args[args.index(flag) + 1] if flag in args else d
        vary = [int(x) for x in grab("--vary").split(",") if x != ""]
        fixed = {}
        for kv in (grab("--fix").split(",") if grab("--fix") else []):
            if "=" in kv: i, val = kv.split("="); fixed[int(i)] = int(val)
        out_ix = [int(x) for x in grab("--out").split(",")] if grab("--out") else list(range(min(len(outs), 8)))
        labels = grab("--labels").split(",") if grab("--labels") else \
            [f"in{i}" for i in vary] + [f"out{o}" for o in out_ix]
        note = f"{len(vary)} inputs varied, rest fixed (0 unless --fix)"
    if len(vary) > 14:
        print("refusing > 2^14 rows; narrow --vary."); return 1

    print(f"Muhlnickel TRUTH TABLE — {name}  ({n_in} in, {len(gates):,} gates)  ·  {note}\n", flush=True)
    print("  " + " | ".join(f"{l:>5s}" for l in labels), flush=True)
    print("  " + "-" * (8 * len(labels)), flush=True)
    base = [fixed.get(i, 0) for i in range(n_in)]
    for combo in itertools.product([0, 1], repeat=len(vary)):
        inb = list(base)
        for idx, bit in zip(vary, combo): inb[idx] = bit
        v = resolve(gates, n_wire, n_in, inb)
        rd = lambda o: 0 if o == 0 else 1 if o == 1 else v[o] & 1
        row = list(combo) + [rd(outs[o]) for o in out_ix]
        print("  " + " | ".join(f"{b:>5d}" for b in row), flush=True)
    print(f"\n  {2**len(vary)} rows, exhaustive over the chosen sub-cube — resolved straight from the stored gates.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
