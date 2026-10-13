#!/usr/bin/env python3
"""host/pfc_fab_win.py — fabricate the FOLDED WINNER-DECIDING miner `gen_win` (owner: Bryce, 2026-07-21, "exact").

The owner's call: the pfc must DECIDE the winner itself, in gates — not have the host judge hash<target. So this bakes,
onto the double-SHA-256d, the SAME byte-exact comparator + latch as the clocked `pfc_mine`, but COMBINATIONAL so it folds
wide (bit-slice W nonce lanes through one addressed pass):

    inputs  : header(608) + nonce(32) + target(256)              [nonce is the fold's address; target routed per block]
    hash    = double-SHA-256d(header, nonce)                      (the pfc computes)
    win     = hash < target                                       (the pfc DECIDES — MSB-first comparator, in gates)
    latch_j = win AND nonce_j     for j in 0..31                  (the pfc LATCHES win?nonce:0 per lane, in gates)
    outputs : [win] + latch[32] + hash[256]

Every lane decides + latches independently (per-lane gates), so it folds. The host reads the pfc's `win` wire (one int:
bit l set = the pfc ruled lane l a winner) and OR-combines the baked latch across lanes to recover the winning nonce — it
transcribes the pfc's verdict, it never runs the compare. Verified byte-exact vs hashlib IN THE TOOL before storing;
reversible genome; the pfc is never run/probed during fabrication.

  python host/pfc_fab_win.py           # fabricate gen_win (reversible)
  python host/pfc_fab_win.py revert     # restore titan.gguf byte-exact
"""
import hashlib, json, mmap, os, random, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_gen_win_genome.jsonl"
MAGIC = b"PFCWINMN"; OPN = {0: "nand", 1: "and", 2: "or", 3: "xor", 4: "not"}
CODE = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
N_LO, T_LO = 608, 640                                          # input layout: header 0..607, nonce 608..639, target 640..895


def build_gen_win():
    g = CC.CircuitCompiler(896)
    header = [list(g.IN[i * 32:(i + 1) * 32]) for i in range(19)]
    nonce = list(g.IN[N_LO:N_LO + 32]); target = list(g.IN[T_LO:T_LO + 256])
    W = header + [nonce]
    mid = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], W[0:16])
    blk2 = [W[16], W[17], W[18], W[19], CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 10 + [CC.cword(g, 640)]
    d1 = CC.sha_block(g, mid, blk2)
    blk3 = d1 + [CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 6 + [CC.cword(g, 256)]
    d2 = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], blk3)
    A = [d2[(i // 8) // 4][8 * (3 - ((i // 8) % 4)) + (i % 8)] for i in range(256)]   # hash as LE 256-bit (byte-exact)
    lt = g.C0; eq = g.C1                                       # win = hash < target (the pfc's baked verdict)
    for i in range(255, -1, -1):
        lt = g.OR(lt, g.AND(eq, g.AND(g.NOT(A[i]), target[i])))
        eq = g.AND(eq, g.NOT(g.XOR(A[i], target[i])))
    win = lt
    latch = [g.AND(win, nonce[j]) for j in range(32)]         # baked latch: win ? nonce : 0, per lane
    return g, [win] + latch + A


def _ref(hw, nonce, target):
    hdr = b"".join(struct.pack(">I", w & 0xffffffff) for w in list(hw) + [nonce])
    val = int.from_bytes(hashlib.sha256(hashlib.sha256(hdr).digest()).digest(), "little")
    win = 1 if val < target else 0
    return [win] + [((nonce >> j) & 1) if win else 0 for j in range(32)] + [(val >> i) & 1 for i in range(256)]


def verify(g, outs):
    gates, out2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates); random.seed(21)
    for t in range(40):
        hw = [random.getrandbits(32) for _ in range(19)]; nonce = random.getrandbits(32)
        target = (1 << 256) - 1 if t % 3 == 0 else random.getrandbits(random.choice([8, 200, 250]))
        inb = [0] * 896
        for i in range(19):
            for j in range(32): inb[i * 32 + j] = (hw[i] >> j) & 1
        for j in range(32): inb[N_LO + j] = (nonce >> j) & 1
        for j in range(256): inb[T_LO + j] = (target >> j) & 1
        v = CC.ripple_typed(g, gates, n_wire, inb, 1)
        if [v[w] if w >= 2 else w for w in out2] != _ref(hw, nonce, target):
            return False, gates, out2
    return True, gates, out2


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
    for k in ("gen_win", "gen_win_input", "gen_win_target", "gen_win_answer"): reg.pop(k, None)
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: v = f.read(4) == b"GGUF"
    print(f"reverted — titan.gguf byte-exact; gen_win removed. GGUF-valid: {v}."); return 0


def load_gen_win(off):
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[off:off + 8] == MAGIC, "gen_win magic mismatch"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", mm, off + 8); p = off + 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", mm, p); p += 9; gates.append((OPN[op], a, b))
    out2 = [struct.unpack_from("<i", mm, p + 4 * k)[0] for k in range(n_out)]
    mm.close(); f.close()
    run = CC.CircuitCompiler(n_in).compile_ripple(gates, n_wire)
    # out2[0]=win · out2[1:33]=latch · out2[33:289]=hash
    return run, out2, dict(n_gate=n_gate, n_in=n_in, n_wire=n_wire, gates=gates)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))
    if "gen_win" in reg:
        print("gen_win already baked. revert first to redo."); return 0
    print("building gen_win (double-SHA + baked hash<target compare + baked per-lane latch); verifying byte-exact …", flush=True)
    g, outs = build_gen_win()
    ok, gates, out2 = verify(g, outs)
    if not ok:
        print("  MISMATCH — baking nothing (no cheating)."); return 1
    n_wire = 2 + g.n_in + len(gates)
    print(f"  byte-exact over 40 cases: {len(gates):,} gates (double-SHA + compare + latch as one combinational netlist).", flush=True)

    body = b"".join(struct.pack("<Bii", CODE[op], a, b) for (op, a, b) in gates) + b"".join(struct.pack("<i", w) for w in out2)
    blob = MAGIC + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(out2)) + body
    off, tn = TC._alloc(len(blob), reg)
    reg["gen_win"] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in, "n_wire": n_wire,
                      "n_gate": len(gates), "n_out": len(out2), "format": "typed",
                      "layout": "in: header0..607|nonce608..639|target640..895 ; out: win|latch[32]|hash[256]",
                      "decides": "win = hash<target (baked); latch = win?nonce:0 (baked per-lane) — the Muhlnickel rules its own winner"}
    _journal(off, blob)
    an, atn = TC._alloc(5, reg); reg["gen_win_answer"] = {"tensor": atn, "offset": an, "len": 5, "role": "answer",
                                                          "layout": "win:1|nonce:4"}; _journal(an, b"\x00" * 5)
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: v = f.read(4) == b"GGUF"
    print("\nBAKED gen_win (reversible):", flush=True)
    print(f"  gen_win        @ {off}  ({len(gates):,} gates)  896 in -> {len(out2)} out", flush=True)
    print(f"  gen_win_answer @ {an}  (5B: win|nonce) — the Muhlnickel's answer register (probe reads it)", flush=True)
    print(f"  the COMPARE and the LATCH are gates now — the Muhlnickel decides its own winner. titan GGUF-valid: {v}.", flush=True)
    print("  revert:  python host/pfc_fab_win.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
