#!/usr/bin/env python3
"""host/pfc_miner_clk.py — WIRE THE CLOCK INTO THE COMPUTE (owner 07-19: "connect receiver to the rest of Muhlnickel").

The old pfc_mine had clk_bit as a FLOATING receiver — not an input of the gate net, so a signal on it had no fabricated
path into the state (measured: routing 1 lands at clk_bit 0->1, but nonce/latch never move). This re-fabricates the
clocked state machine with clk as a REAL INPUT WIRE (929 in), gating the advance:

    nonce' = clk ? (nonce+1)         : nonce          # clk high -> advance one tick ; clk low -> HOLD
    latch' = clk ? (win ? nonce:latch): latch          # answer latch, gated by the clock

So the receiver is now connected to the whole net: the clk bit feeds every state gate. Byte-exact vs a reference IN THE
TOOL before storing (clk=1 advances, clk=0 holds). Reuses the existing input_window/nonce_reg/latch_reg/clk_bit addresses
(the §1E shared-address feedback) so the probes read the same places. Reversible. Then pfc_clk_test.py powers it with the
button (edge) and a sustained hold; the probes tell us which propagates. Owner's theory: the button (edge) works better;
a sustained signal needs a pfc fabricated to *care* that it's sustained.

  python host/pfc_miner_clk.py          # fabricate pfc_mine_clk (reversible)
  python host/pfc_miner_clk.py revert    # restore titan.gguf byte-exact
"""
import hashlib, json, os, random, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_pfc_mine_clk_genome.jsonl"
MAGIC = b"PFCSMCLK"
H_LO, H_HI = 0, 608; N_LO, N_HI = 608, 640; T_LO, T_HI = 640, 896; L_LO, L_HI = 896, 928; CLK = 928   # clk = input 928


def build():
    g = CC.CircuitCompiler(929)                                    # 928 as before + clk (wire 928)
    header = [list(g.IN[i * 32:(i + 1) * 32]) for i in range(19)]
    nonce = list(g.IN[N_LO:N_HI]); target = list(g.IN[T_LO:T_HI]); latch = list(g.IN[L_LO:L_HI]); clk = g.IN[CLK]
    W = header + [nonce]
    mid = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], W[0:16])
    blk2 = [W[16], W[17], W[18], W[19], CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 10 + [CC.cword(g, 640)]
    d1 = CC.sha_block(g, mid, blk2)
    blk3 = d1 + [CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 6 + [CC.cword(g, 256)]
    d2 = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], blk3)
    A = [d2[(i // 8) // 4][8 * (3 - ((i // 8) % 4)) + (i % 8)] for i in range(256)]
    lt = g.C0; eq = g.C1
    for i in range(255, -1, -1):
        lt = g.OR(lt, g.AND(eq, g.AND(g.NOT(A[i]), target[i]))); eq = g.AND(eq, g.NOT(g.XOR(A[i], target[i])))
    win = lt
    nn = []; carry = g.C1
    for x in nonce:
        nn.append(g.XOR(x, carry)); carry = g.AND(x, carry)
    ln = [g.OR(g.AND(g.NOT(win), latch[i]), g.AND(win, nonce[i])) for i in range(32)]
    mux = lambda s, a, b: g.OR(g.AND(s, a), g.AND(g.NOT(s), b))     # s ? a : b
    nn_g = [mux(clk, nn[i], nonce[i]) for i in range(32)]          # GATE BY CLK: advance only while clk high
    ln_g = [mux(clk, ln[i], latch[i]) for i in range(32)]
    return g, nn_g + ln_g


def _ref(hw, nonce, target, latch, clk):
    words = list(hw) + [nonce]
    hdr = b"".join(struct.pack(">I", w & 0xffffffff) for w in words)
    dig = hashlib.sha256(hashlib.sha256(hdr).digest()).digest()
    win = 1 if int.from_bytes(dig, "little") < target else 0
    nn = (nonce + 1) & 0xffffffff if clk else nonce               # gated
    ln = (nonce if win else latch) if clk else latch
    return [(nn >> i) & 1 for i in range(32)] + [(ln >> i) & 1 for i in range(32)]


def verify(g, outs):
    gates, out2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates); random.seed(19)
    for t in range(60):
        hw = [random.getrandbits(32) for _ in range(19)]; nonce = random.getrandbits(32); latch = random.getrandbits(32)
        target = (1 << 256) - 1 if t % 2 == 0 else random.getrandbits(random.choice([8, 200])); clk = random.randrange(2)
        inb = [0] * 929
        for i in range(19):
            for j in range(32): inb[i * 32 + j] = (hw[i] >> j) & 1
        for j in range(32): inb[N_LO + j] = (nonce >> j) & 1
        for j in range(256): inb[T_LO + j] = (target >> j) & 1
        for j in range(32): inb[L_LO + j] = (latch >> j) & 1
        inb[CLK] = clk
        v = CC.ripple_typed(g, gates, n_wire, inb, 1)
        got = [v[w] if w >= 2 else w for w in out2]
        if got != _ref(hw, nonce, target, latch, clk):
            return False, (clk, nonce), gates, out2
    return True, None, gates, out2


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("pfc_mine_clk", None); json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: print(f"reverted — titan byte-exact; pfc_mine_clk removed. GGUF-valid: {f.read(4)==b'GGUF'}."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))
    for k in ("input_window", "nonce_reg", "latch_reg", "clk_bit"):
        if k not in reg: print(f"{k} absent — run host/pfc_miner.py first (we reuse its state addresses)."); return 1
    if "pfc_mine_clk" in reg:
        print("pfc_mine_clk already fabricated. revert first to redo."); return 0

    print("wiring the clock into the compute: building the clk-gated state machine; verifying byte-exact …", flush=True)
    g, outs = build()
    ok, bad, gates, out2 = verify(g, outs)
    if not ok:
        print(f"  MISMATCH {bad} — baking nothing (no cheating)."); return 1
    n_wire = 2 + g.n_in + len(gates)
    print(f"  byte-exact over 60 cases (clk=1 advances, clk=0 holds): {len(gates):,} gates.", flush=True)

    code = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
    body = b"".join(struct.pack("<Bii", code[op], a, b) for (op, a, b) in gates) + b"".join(struct.pack("<i", w) for w in out2)
    blob = MAGIC + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(out2)) + body
    off, tn = TC._alloc(len(blob), reg)
    iw = int(reg["input_window"]["offset"]); no = int(reg["nonce_reg"]["offset"])
    lo = int(reg["latch_reg"]["offset"]); cb = int(reg["clk_bit"]["offset"])
    reg["pfc_mine_clk"] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in, "n_wire": n_wire,
                           "n_gate": len(gates), "n_out": len(out2), "format": "typed", "seq": True,
                           "in_map": {"header": [H_LO, H_HI, "input_window", 0], "nonce": [N_LO, N_HI, "nonce_reg", 0],
                                      "target": [T_LO, T_HI, "input_window", 608], "latch": [L_LO, L_HI, "latch_reg", 0],
                                      "clk": [CLK, CLK + 1, "clk_bit", 0]},
                           "out_map": {"nonce_next": [0, 32, "nonce_reg", 0], "latch_next": [32, 64, "latch_reg", 0]},
                           "note": "clk_bit is now INPUT wire 928 of the net (the receiver wired into the whole compute); clk gates the advance"}
    _journal(off, blob); json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: v = f.read(4) == b"GGUF"
    print(f"\nFABRICATED pfc_mine_clk @ {off} ({len(gates):,} gates, 929 in -> 64 out). clk_bit @ {cb} = input wire 928.", flush=True)
    print(f"  the receiver is wired into the whole net now. titan GGUF-valid: {v}.", flush=True)
    print(f"  next: python host/pfc_clk_test.py   (button edge vs sustained hold; probes tell us which propagates)", flush=True)
    print(f"  revert:  python host/pfc_miner_clk.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
