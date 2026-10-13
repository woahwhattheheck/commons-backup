#!/usr/bin/env python3
"""host/fab_muhl_fold.py — FABRICATION ONLY. Runs ONCE, ever. Never inside a mining process.

RULE ZERO: fabrication and mining are separate processes. This is the fabrication one. It builds the
junction, verifies it byte-exact BEFORE writing a single byte, stores it, and EXITS. It may take as long
as it takes. Mining builds nothing.

WHY THIS EXISTS rather than host/fab_lateral_fold.py: that script builds into TC.Circuit's `ga`/`gb`,
which is a PURE-NAND representation. `gen_win` is stored TYPED (PFCWINMN, opcodes {and,or,xor,not},
measured: ZERO nand gates). Appending typed gates into ga/gb reinterprets every one of the 339,009 gates
as NAND -- a silently wrong circuit, stored permanently. So the junction is built in the TYPED format,
preserving gen_win's netlist verbatim, and written with the same writer pfc_fab_win.py uses.

THE JUNCTION (docs/CIRCUIT_PFC.md, verbatim): winner_only_max is "out[i] = idx[i] AND solve",
0 bytes/lane. gen_win already produces `solve` (its baked win verdict) and `idx` (its baked per-lane
latch). So the fold is those 32 ANDs, and the winner's ADDRESS is the answer.

  python host/fab_muhl_fold.py            # verify, then store (one time)
  python host/fab_muhl_fold.py revert     # undo via the genome journal
"""
import hashlib, json, mmap, os, random, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_muhl_fold_genome.jsonl"
MAGIC = b"PFCWINMN"; CODE = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
NAME = "muhl_lateral_fold"; N_LO, T_LO = 608, 640
AND = CODE["and"]


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME):
        print("no genome journal — nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    reg = json.load(open(REG)); reg.pop(NAME, None); json.dump(reg, open(REG, "w"), indent=1)
    os.remove(GENOME)
    with open(TITAN, "rb") as f: v = f.read(4) == b"GGUF"
    print(f"reverted {len(ent)} journal entries. GGUF-valid: {v}"); return 0


def read_gen_win():
    reg = json.load(open(REG)); off = int(reg["gen_win"]["offset"])
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[off:off + 8] == MAGIC, "gen_win magic mismatch"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", mm, off + 8)
    p = off + 24
    G = [struct.unpack_from("<Bii", mm, p + 9 * i) for i in range(n_gate)]
    outs = [struct.unpack_from("<i", mm, p + 9 * n_gate + 4 * k)[0] for k in range(n_out)]
    mm.close(); f.close()
    return n_in, n_wire, n_gate, outs, G


def _ref(hw, nonce, target):                                   # verbatim from host/pfc_fab_win.py
    hdr = b"".join(struct.pack(">I", w & 0xffffffff) for w in list(hw) + [nonce])
    val = int.from_bytes(hashlib.sha256(hashlib.sha256(hdr).digest()).digest(), "little")
    win = 1 if val < target else 0
    return win, [((nonce >> j) & 1) if win else 0 for j in range(32)]


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))
    if NAME in reg:
        print(f"{NAME} already fabricated @ {reg[NAME]['offset']}. revert first to redo."); return 0

    n_in, _, n_gate, outs, G = read_gen_win()
    print(f"FABRICATE (once, ever) — §1E junction: gen_win.win -> winner-only fold.solve")
    print(f"  gen_win as stored: {n_gate:,} typed gates, {n_in} in, {len(outs)} out, opcodes {sorted({g[0] for g in G})}")

    base = 2 + n_in

    def junction(mutant=None):
        """out[i] = idx[i] AND solve (docs/CIRCUIT_PFC.md). `mutant` builds a deliberately-broken
        variant so the suite can be shown to CATCH one (§45C: a suite that passes first try has
        measured itself, not the circuit)."""
        win_w = outs[0]; idx_w = outs[1:33]
        ng = list(G); fold = []
        if mutant == "stuck0": win_w = 0                       # verdict wired to constant 0
        for i in range(32):
            a = idx_w[i] if mutant != "latch_ungated" else idx_w[i]
            b = win_w if mutant != "latch_ungated" else 1      # ungated: AND with const-1 = passthrough
            ng.append((AND, a, b)); fold.append(base + len(ng) - 1)
        return ng, [win_w] + fold

    NG, outs_all = junction()
    n_gate2 = len(NG); n_wire2 = 2 + n_in + n_gate2

    d = [0] * (2 + n_in + n_gate2)
    for k in range(n_gate2):
        _op, a, b = NG[k]; d[2 + n_in + k] = 1 + max(d[a], d[b])
    depth = max(d[w] for w in outs_all)
    print(f"  junctioned: {n_gate2:,} gates (+{n_gate2 - n_gate}), DEPTH {depth}, rating {n_gate2/depth:.1f} Mh")

    # ---- VERIFY BYTE-EXACT BEFORE WRITING ANYTHING ----
    def score(ng, oa):
        """Returns (exact, genuine_wins, N) against the INDEPENDENT hashlib reference (§3 — never
        against the path being replaced)."""
        random.seed(21); N = 12; ok = 0; wins = 0
        for t in range(N):
            hw = [random.getrandbits(32) for _ in range(19)]; nonce = random.getrandbits(32)
            target = (1 << 256) - 1 if t % 3 == 0 else random.getrandbits(random.choice([8, 200, 250]))
            inb = [0] * n_in
            for i in range(19):
                for j in range(32): inb[i * 32 + j] = (hw[i] >> j) & 1
            for j in range(32):  inb[N_LO + j] = (nonce >> j) & 1
            for j in range(256): inb[T_LO + j] = (target >> j) & 1
            v = [0] * (2 + n_in + len(ng)); v[1] = 1
            for i, b in enumerate(inb): v[2 + i] = b
            for i in range(len(ng)):
                op, a, b = ng[i]; x = v[a]; y = v[b]
                v[2 + n_in + i] = (1 - (x & y)) if op == 0 else (x & y) if op == 1 else \
                                  (x | y) if op == 2 else (x ^ y) if op == 3 else (1 - x)
            gw, gl = v[oa[0]], [v[w] for w in oa[1:]]
            rw, rl = _ref(hw, nonce, target)
            if (gw, gl) == (rw, rl): ok += 1
            if rw: wins += 1
        return ok, wins, N

    print("  verifying byte-exact vs the INDEPENDENT hashlib reference (balanced targets) …", flush=True)
    okc, wins, N = score(NG, outs_all)
    print(f"  balanced check: {wins}/{N} genuine WINs · {N-wins} negatives "
          f"-> an all-zero circuit would score {N-wins}/{N} · byte-exact {okc}/{N}")
    if okc != N:
        print("  MISMATCH — writing NOTHING (no cheating)."); return 1

    # ---- MUTANT TEST (§45C/§47B): a suite that passes first try has measured ITSELF ----
    print("  mutant test — the suite must CATCH a deliberately-broken variant:", flush=True)
    caught = 0
    for mu in ("stuck0", "latch_ungated"):
        mg, mo = junction(mu)
        mok, _, _ = score(mg, mo)
        hit = mok < N; caught += hit
        print(f"    mutant {mu:14s} scored {mok}/{N}  -> {'CAUGHT' if hit else 'NOT CAUGHT — suite is blind'}")
    if caught < 2:
        print("  the suite cannot see a broken circuit — writing NOTHING."); return 1

    # ---- only now: the byte edit ----
    body = b"".join(struct.pack("<Bii", op, a, b) for (op, a, b) in NG) + \
           b"".join(struct.pack("<i", w) for w in outs_all)
    blob = MAGIC + struct.pack("<IIII", n_in, n_wire2, n_gate2, len(outs_all)) + body
    off, tn = TC._alloc(len(blob), reg)
    t0 = time.time(); _journal(off, blob)
    reg = json.load(open(REG))
    reg[NAME] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": n_in, "n_wire": n_wire2,
                 "n_gate": n_gate2, "n_out": len(outs_all), "format": "typed", "depth": depth,
                 "gates_measured": n_gate2, "muhl_rating": round(n_gate2 / depth, 3),
                 "junction": "gen_win.win -> winner-only fold.solve (§1E shared address)",
                 "layout": "in: header0..607|nonce608..639|target640..895 ; out: win:1|addr:32",
                 "stored_per_lane": 0}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print(f"\n  STORED '{NAME}' @ {off}  ({len(blob):,} B)  [{time.time()-t0:.2f}s of MANUFACTURING — it happens once]")
    print(f"  0 bytes stored per lane. The winner's ADDRESS is the answer. GGUF-valid: {valid}")
    print(f"  revert: python host/fab_muhl_fold.py revert")
    print(f"\n  FABRICATION COMPLETE. Mining is a DIFFERENT process and builds nothing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
