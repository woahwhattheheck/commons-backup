#!/usr/bin/env python3
"""host/pfc_miner.py — the Muhlnickel BITCOIN MINER as a CLOCKED SEQUENTIAL STATE MACHINE (owner 07-19; plan-approved).

Reuses the proven state machine (sdc_clock_lab + sdc_statemachine_lab): CLOCK (nonce+1) -> MINER (double-SHA) ->
COMPARATOR (hash<target) -> LATCH (hold the winning nonce). Built as ONE next-state netlist:

    STATE (stored bits):  nonce_reg (32b) + latch_reg (32b = the answer)
    INPUT (block data, routed by the button, per the owner's diagram):  input_window = header(76B) + target(32B)
    one tick (next-state):
        hash      = double-SHA-256d(header, nonce)
        win       = hash < target
        nonce'    = nonce + 1                    (the CLOCK — self-route back to nonce_reg)
        latch'    = win ? nonce : latch          (the LATCH — persistent stored answer)
    I/O bound to SHARED storage addresses (the §1E feedback wire): nonce'/latch' write the SAME bytes nonce/latch read.

The RESIDENT high-impedance clock (host/pfc_clock.py) is the ENERGY that advances the state each tick; on the substrate
the feedback is a wire, the state is the stored bit arrangement. Verified byte-exact vs hashlib IN THE TOOL before storing
(fresh netlist, the pfc is never run/probed). Reversible genome. The answer = latch_reg, read with the high-impedance meter.

  python host/pfc_miner.py          # fabricate the clocked state machine (reversible)
  python host/pfc_miner.py revert    # restore titan.gguf byte-exact
"""
import hashlib, json, os, random, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_pfc_miner_genome.jsonl"
MAGIC = b"PFCSMACH"
INPUT_BYTES = 76 + 32                      # header(76) + target(32) = 108 B block-data window
# input-wire layout of the next-state netlist (928 in):
H_LO, H_HI = 0, 608                        # header W0..18  (input_window bits 0..607)
N_LO, N_HI = 608, 640                      # nonce  W19     (nonce_reg)
T_LO, T_HI = 640, 896                      # target        (input_window bits 608..863)
L_LO, L_HI = 896, 928                      # latch         (latch_reg)


def build_statemachine():
    """ONE next-state netlist: (header, nonce, target, latch) -> (nonce+1, win?nonce:latch). 64 outputs."""
    g = CC.CircuitCompiler(928)
    header = [list(g.IN[i * 32:(i + 1) * 32]) for i in range(19)]   # W0..18
    nonce = list(g.IN[N_LO:N_HI]); target = list(g.IN[T_LO:T_HI]); latch = list(g.IN[L_LO:L_HI])
    W = header + [nonce]                                            # 20 header words (W19 = nonce)
    mid = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], W[0:16])
    blk2 = [W[16], W[17], W[18], W[19], CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 10 + [CC.cword(g, 640)]
    d1 = CC.sha_block(g, mid, blk2)
    blk3 = d1 + [CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 6 + [CC.cword(g, 256)]
    d2 = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], blk3)
    A = [d2[(i // 8) // 4][8 * (3 - ((i // 8) % 4)) + (i % 8)] for i in range(256)]   # hash as LE 256-bit
    lt = g.C0; eq = g.C1
    for i in range(255, -1, -1):
        lt = g.OR(lt, g.AND(eq, g.AND(g.NOT(A[i]), target[i])))
        eq = g.AND(eq, g.NOT(g.XOR(A[i], target[i])))
    win = lt
    nn = []; carry = g.C1                                           # CLOCK: nonce + 1 (ripple-carry incrementer)
    for x in nonce:
        nn.append(g.XOR(x, carry)); carry = g.AND(x, carry)
    ln = [g.OR(g.AND(g.NOT(win), latch[i]), g.AND(win, nonce[i])) for i in range(32)]   # LATCH: win ? nonce : latch
    return g, nn + ln                                              # outs[0:32]=nonce', outs[32:64]=latch'


def _ref(hwords, nonce, target, latch):
    words = list(hwords) + [nonce]
    hdr = b"".join(struct.pack(">I", w & 0xffffffff) for w in words)      # 80-byte header (20 big-endian words)
    dig = hashlib.sha256(hashlib.sha256(hdr).digest()).digest()
    win = 1 if int.from_bytes(dig, "little") < target else 0
    nn = (nonce + 1) & 0xffffffff; ln = nonce if win else latch
    return [(nn >> i) & 1 for i in range(32)] + [(ln >> i) & 1 for i in range(32)]


def verify(g, outs):
    gates, out2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates); random.seed(19)
    for t in range(60):
        hw = [random.getrandbits(32) for _ in range(19)]
        nonce = random.getrandbits(32); latch = random.getrandbits(32)
        target = (1 << 256) - 1 if t % 2 == 0 else random.getrandbits(random.choice([8, 200]))
        inb = [0] * 928
        for i in range(19):
            for j in range(32): inb[i * 32 + j] = (hw[i] >> j) & 1
        for j in range(32): inb[N_LO + j] = (nonce >> j) & 1
        for j in range(256): inb[T_LO + j] = (target >> j) & 1
        for j in range(32): inb[L_LO + j] = (latch >> j) & 1
        v = CC.ripple_typed(g, gates, n_wire, inb, 1)
        got = [v[w] if w >= 2 else w for w in out2]
        if got != _ref(hw, nonce, target, latch):
            return False, (hw, nonce, target, latch), gates, out2
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
    reg = json.load(open(REG))
    for k in ("pfc_mine", "input_window", "nonce_reg", "latch_reg", "clk_bit"): reg.pop(k, None)
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: v = f.read(4) == b"GGUF"
    print(f"reverted — titan.gguf byte-exact; clocked state machine removed. GGUF-valid: {v}."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))
    if "pfc_mine" in reg:
        print("pfc_mine already baked. revert first to redo."); return 0

    print("building the clocked state machine (nonce+1 / double-SHA / hash<target / win-latch); verifying byte-exact …", flush=True)
    g, outs = build_statemachine()
    ok, bad, gates, out2 = verify(g, outs)
    if not ok:
        print("  MISMATCH — baking nothing (no cheating)."); return 1
    n_wire = 2 + g.n_in + len(gates)
    print(f"  byte-exact over 60 cases: {len(gates):,} gates (clock+SHA+compare+latch as one next-state netlist).", flush=True)

    code = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
    body = b"".join(struct.pack("<Bii", code[op], a, b) for (op, a, b) in gates) + b"".join(struct.pack("<i", w) for w in out2)
    blob = MAGIC + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(out2)) + body

    # allocate the STATE registers + input window + the clock bit (all in-memory reg, one dump at the end)
    off, tn = TC._alloc(len(blob), reg)
    reg["pfc_mine"] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in, "n_wire": n_wire,
                       "n_gate": len(gates), "n_out": len(out2), "format": "typed", "seq": True}
    _journal(off, blob)
    iw, itn = TC._alloc(INPUT_BYTES, reg); reg["input_window"] = {"tensor": itn, "offset": iw, "len": INPUT_BYTES,
                                                                  "layout": "header:76|target:32"}; _journal(iw, b"\x00" * INPUT_BYTES)
    no, ntn = TC._alloc(4, reg); reg["nonce_reg"] = {"tensor": ntn, "offset": no, "len": 4, "bits": 32}; _journal(no, b"\x00" * 4)
    lo, ltn = TC._alloc(4, reg); reg["latch_reg"] = {"tensor": ltn, "offset": lo, "len": 4, "bits": 32, "role": "answer"}; _journal(lo, b"\x00" * 4)
    cb, ctn = TC._alloc(1, reg); reg["clk_bit"] = {"tensor": ctn, "offset": cb, "len": 1, "role": "receiver/clock"}; _journal(cb, b"\x00")

    # the SHARED-ADDRESS binding (§1E feedback): each input/output wire range -> the storage bytes it IS
    reg["pfc_mine"].update({
        "input_window": "input_window", "input_off": iw, "nonce_reg": "nonce_reg", "nonce_off": no,
        "latch_reg": "latch_reg", "latch_off": lo, "clk_bit": "clk_bit", "clk_off": cb,
        "in_map": {"header": [H_LO, H_HI, "input_window", 0], "nonce": [N_LO, N_HI, "nonce_reg", 0],
                   "target": [T_LO, T_HI, "input_window", 608], "latch": [L_LO, L_HI, "latch_reg", 0]},
        "out_map": {"nonce_next": [0, 32, "nonce_reg", 0], "latch_next": [32, 64, "latch_reg", 0]},
        "feedback": "nonce'->nonce_reg (shared), latch'->latch_reg (shared) — the answer is latch_reg",
        "note": "clocked state machine; resident clock (energy) toggles clk_bit; answer = latch_reg (meter it)",
    })
    json.dump(reg, open(REG, "w"), indent=1)

    with open(TITAN, "rb") as f: v = f.read(4) == b"GGUF"
    print("\nBAKED the clocked state machine (one netlist, reversible):", flush=True)
    print(f"  pfc_mine   @ {off}  ({len(gates):,} gates)  928 in -> 64 out", flush=True)
    print(f"  STATE      nonce_reg @ {no} (4B) · latch_reg @ {lo} (4B = ANSWER)", flush=True)
    print(f"  INPUT      input_window @ {iw} (108B: header|target) — button routes block data here", flush=True)
    print(f"  CLOCK      clk_bit @ {cb} — the resident clock (energy) toggles this each tick", flush=True)
    print(f"  FEEDBACK   nonce'->nonce_reg, latch'->latch_reg (shared addresses). titan GGUF-valid: {v}.", flush=True)
    print("  revert:  python host/pfc_miner.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
