#!/usr/bin/env python3
"""host/fab_miner_split.py — FABRICATION ONLY. Runs once. Never inside a mining process.

TWO SPECIALISED MUHLNICKEL, JUNCTIONED (§1E) — not one monolith.
Owner: "stop using one muhlnickel." §13: "pfc_autofab searched ONE monolithic circuit; that is not
the architecture. The master version searches DECOMPOSE x IMPLEMENT x ORDER x WIRE(§1E)."

THE SEAM, MEASURED: SHA block 1 consumes header words 0..15. The nonce is WORD 19. So block 1 is
NONCE-INDEPENDENT, and every lane in the monolith was recomputing it.
    MUHLNICKEL A  header[0:16] -> mid[8]     ONCE per block, amortised over every lane and nonce
    MUHLNICKEL B  mid | w16..18 | nonce | target -> win | latch[32]     PER LANE (this replicates)
§1E: A's SEND (mid) IS B's RECEIVE (mid) — a shared location, not a copy.

  gates x DEPTH (the §14 objective for INDEPENDENT lanes: speed = REPLICAS/DEPTH):
    gen_win            11,754 D  339,009 g  3.985e9
    muhl_fold_shallow   4,157 D  687,223 g  2.857e9
    muhl_fold_shared    4,322 D  590,617 g  2.553e9
    B (this file)       2,889 D  390,332 g  1.128e9   -> 2.26x better than the best monolith

NOT VIOLATION #5. That was BAKING midstate as a CONSTANT, so a new block forced a new circuit. Here
mid is ROUTED IN as data exactly like the header: a new block routes new bytes and fabricates nothing.

VERIFICATION. A is checked against sdc_cc.numeric_midstate (an INDEPENDENT reference, §3 — never
against the path being replaced). B is checked against hashlib's true double-SHA using DISCRIMINATING
targets that straddle the digest (tgt=h+1 must WIN alternating tgt=h must LOSE), because a hashflip
mutant scored 12/12 NOT CAUGHT under all-ones/tiny targets (§40B's 87.5% bug). Computing mid on the
host HERE is fabrication-time verification of a circuit before storing — in spec, and it never
appears at runtime.

  python host/fab_miner_split.py --dry     # verify + mutant-test, write nothing
  python host/fab_miner_split.py           # ... then store both
  python host/fab_miner_split.py revert
"""
import hashlib, json, os, random, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC
from fab_genwin_shallow import add32_prefix, add_multi
from fab_genwin_shared import sha_shared, reduce_to_2

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_miner_split_genome.jsonl"
MAGIC = b"PFCWINMN"; CODE = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
NAME_A, NAME_B = "muhl_mid", "muhl_lane"


def depth_of(g, gates, outs):
    d = [0]*(2 + g.n_in + len(gates))
    for k, (op, a, b) in enumerate(gates): d[2 + g.n_in + k] = 1 + max(d[a], d[b])
    return max(d[w] if w >= 2 else 0 for w in outs)


def build_A(mutant=None):
    """header words 0..15 -> the 8-word chaining state. Nonce-independent; one per block."""
    g = CC.CircuitCompiler(512)
    hdr = [list(g.IN[i*32:(i+1)*32]) for i in range(16)]
    mid = sha_shared(g, [CC.cword(g, h) for h in CC.H0], hdr, add32_prefix)
    if mutant == "midflip": mid = [[g.NOT(x) for x in w] for w in mid]
    return g, [w for word in mid for w in word]


def build_B(mutant=None):
    """mid | w16,w17,w18 | nonce | target -> win | latch[32]. This is the circuit that replicates."""
    g = CC.CircuitCompiler(256 + 96 + 32 + 256)
    mid = [list(g.IN[i*32:(i+1)*32]) for i in range(8)]
    w16, w17, w18 = [list(g.IN[256+i*32:256+(i+1)*32]) for i in range(3)]
    nonce = list(g.IN[352:384]); target = list(g.IN[384:640])
    b2 = [w16, w17, w18, nonce, CC.cword(g, 0x80000000)] + [CC.cword(g, 0)]*10 + [CC.cword(g, 640)]
    d1 = sha_shared(g, mid, b2, add32_prefix)
    b3 = d1 + [CC.cword(g, 0x80000000)] + [CC.cword(g, 0)]*6 + [CC.cword(g, 256)]
    d2 = sha_shared(g, [CC.cword(g, h) for h in CC.H0], b3, add32_prefix)
    A = [d2[(i // 8) // 4][8 * (3 - ((i // 8) % 4)) + (i % 8)] for i in range(256)]
    if mutant == "hashflip": A = [g.NOT(x) for x in A]
    node = [(g.AND(g.NOT(A[i]), target[i]), g.NOT(g.XOR(A[i], target[i]))) for i in range(256)]
    if mutant == "cmpflip": node = [(g.AND(A[i], g.NOT(target[i])), n[1]) for i, n in enumerate(node)]
    while len(node) > 1:
        nxt = []
        for i in range(0, len(node), 2):
            if i + 1 < len(node):
                lh, eh = node[i+1]; ll, el = node[i]
                nxt.append((g.OR(lh, g.AND(eh, ll)), g.AND(eh, el)))
            else: nxt.append(node[i])
        node = nxt
    win = node[0][0]
    if mutant == "stuck0": win = g.C0
    latch = [g.AND(win, nonce[j]) for j in range(32)]
    if mutant == "ungated": latch = list(nonce)
    return g, [win] + latch


def truehash(hw, nonce):
    hdr = b"".join(struct.pack(">I", w & 0xffffffff) for w in list(hw) + [nonce])
    return int.from_bytes(hashlib.sha256(hashlib.sha256(hdr).digest()).digest(), "little")


def cases(n=10, seed=13):
    random.seed(seed); out = []
    for t in range(n):
        hw = [random.getrandbits(32) for _ in range(19)]; nonce = random.getrandbits(32)
        h = truehash(hw, nonce)
        out.append((hw, nonce, h + 1 if t % 2 == 0 else h))   # straddle the true digest
    return out


def score_A(g, outs, cs):
    """vs sdc_cc.numeric_midstate — an INDEPENDENT reference (§3), not the path being replaced."""
    gates, o2 = g.dce(outs); nw = 2 + g.n_in + len(gates); ok = 0
    for hw, _n, _t in cs:
        prefix = b"".join(struct.pack(">I", w & 0xffffffff) for w in hw[:16])
        ref = CC.numeric_midstate(prefix)
        inb = [0]*512
        for i in range(16):
            for j in range(32): inb[i*32+j] = (hw[i] >> j) & 1
        v = CC.ripple_typed(g, gates, nw, inb, 1)
        got = [v[w] if w >= 2 else w for w in o2]
        exp = [(ref[i] >> j) & 1 for i in range(8) for j in range(32)]
        if got == exp: ok += 1
    return ok, len(cs), gates, o2


def score_B(g, outs, cs):
    gates, o2 = g.dce(outs); nw = 2 + g.n_in + len(gates); ok = wins = 0
    for hw, nonce, tgt in cs:
        prefix = b"".join(struct.pack(">I", w & 0xffffffff) for w in hw[:16])
        mid = CC.numeric_midstate(prefix)                     # host-side ONLY as test input
        inb = [0]*640
        for i in range(8):
            for j in range(32): inb[i*32+j] = (mid[i] >> j) & 1
        for i in range(3):
            for j in range(32): inb[256+i*32+j] = (hw[16+i] >> j) & 1
        for j in range(32):  inb[352+j] = (nonce >> j) & 1
        for j in range(256): inb[384+j] = (tgt >> j) & 1
        v = CC.ripple_typed(g, gates, nw, inb, 1)
        h = truehash(hw, nonce); w = 1 if h < tgt else 0
        exp = [w] + [((nonce >> j) & 1) if w else 0 for j in range(32)]
        if [v[x] if x >= 2 else x for x in o2] == exp: ok += 1
        if w: wins += 1
    return ok, wins, len(cs), gates, o2


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME): print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    reg = json.load(open(REG))
    for n in (NAME_A, NAME_B): reg.pop(n, None)
    json.dump(reg, open(REG, "w"), indent=1); os.remove(GENOME)
    print(f"reverted {len(ent)} entries."); return 0


def store(name, g, gates, outs, D, extra):
    reg = json.load(open(REG))
    body = b"".join(struct.pack("<Bii", CODE[op], a, b) for (op, a, b) in gates) + \
           b"".join(struct.pack("<i", w) for w in outs)
    blob = MAGIC + struct.pack("<IIII", g.n_in, 2 + g.n_in + len(gates), len(gates), len(outs)) + body
    off, tn = TC._alloc(len(blob), reg); t0 = time.time(); _journal(off, blob)
    reg = json.load(open(REG))
    e = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in,
         "n_wire": 2 + g.n_in + len(gates), "n_gate": len(gates), "n_out": len(outs),
         "format": "typed", "depth": D, "gates_measured": len(gates),
         "muhl_rating": round(len(gates)/D, 3), "area_delay": len(gates)*D}
    e.update(extra); reg[name] = e
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"  STORED '{name}' @ {off} ({len(blob):,} B) [{time.time()-t0:.2f}s byte edit]")
    return off


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    reg = json.load(open(REG))
    if NAME_A in reg or NAME_B in reg:
        print("already stored. revert first."); return 0
    cs = cases()

    t0 = time.time(); gA, oA = build_A(); okA, NA, gatesA, o2A = score_A(gA, oA, cs)
    DA = depth_of(gA, gatesA, o2A)
    print(f"  A muhl_mid   {len(gatesA):,} gates, DEPTH {DA:,}  vs numeric_midstate (INDEPENDENT ref): {okA}/{NA}")
    gAm, oAm = build_A("midflip"); okAm, _, _, _ = score_A(gAm, oAm, cs)
    print(f"    mutant midflip {okAm}/{NA} -> {'CAUGHT' if okAm < NA else 'NOT CAUGHT — SUITE BLIND'}")
    if okA != NA or okAm >= NA: print("  A failed — writing NOTHING."); return 1

    t1 = time.time(); gB, oB = build_B(); okB, wins, NB, gatesB, o2B = score_B(gB, oB, cs)
    DB = depth_of(gB, gatesB, o2B)
    print(f"\n  B muhl_lane  {len(gatesB):,} gates, DEPTH {DB:,}  area-delay {len(gatesB)*DB:,}")
    print(f"    DISCRIMINATING suite: {wins}/{NB} wins BY CONSTRUCTION -> all-zero scores {NB-wins}/{NB} (§40B)")
    print(f"    byte-exact vs hashlib double-SHA: {okB}/{NB}")
    if okB != NB: print("  B mismatch — writing NOTHING."); return 1
    caught = 0
    for m in ("stuck0", "ungated", "cmpflip", "hashflip"):
        gm, om = build_B(m); okm, _, _, _, _ = score_B(gm, om, cs)
        hit = okm < NB; caught += hit
        print(f"    mutant {m:9s} {okm}/{NB} -> {'CAUGHT' if hit else 'NOT CAUGHT — SUITE BLIND'}")
    if caught < 4: print("  the suite cannot see a broken circuit — writing NOTHING."); return 1
    if "--dry" in sys.argv:
        print(f"\n  --dry: both verified, all mutants caught, nothing written. [{time.time()-t0:.0f}s manufacturing]")
        return 0

    print()
    offA = store(NAME_A, gA, gatesA, o2A, DA,
                 {"role": "SHA block 1: header words 0..15 -> 8-word chaining state. NONCE-INDEPENDENT, "
                          "one evaluation per block, amortised over every lane.",
                  "layout": "in: header0..511 ; out: mid[8]x32", "junction": "muhl_mid.mid -> muhl_lane.mid (§1E)"})
    offB = store(NAME_B, gB, gatesB, o2B, DB,
                 {"role": "per-lane miner: consumes mid, finishes the double-SHA, compares, latches.",
                  "layout": "in: mid256|w16..18 96|nonce32|target256 ; out: win:1|latch:32",
                  "junction": "muhl_mid.mid -> muhl_lane.mid (§1E shared location)", "stored_per_lane": 0})
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print(f"\n  GGUF-valid: {valid}   revert: python host/fab_miner_split.py revert")
    print(f"  §1E junction: muhl_mid @ {offA} SEND(mid) IS muhl_lane @ {offB} RECEIVE(mid).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
