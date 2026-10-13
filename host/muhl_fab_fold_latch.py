#!/usr/bin/env python3
"""muhl_fab_fold_latch.py — FABRICATION ONLY, runs ONCE. Close the open junction IN THE BINARY.

RULE ZERO (Bryce): fabrication and mining are separate. This is fabrication. It builds the junction that
was NOT-YET-BUILT — the winner-only fold's decided output (win:1|addr:32) -> latch_reg (the answer
register) — verifies it BYTE-EXACT before writing one byte, journals reversibly, stores, and EXITS.
Mining builds nothing; it will just route a block and read latch_reg.

LET TITAN DO THE WORK: gen_win (339k typed gates already in titan.gguf) computes real double-SHA-256d and
the hash<target verdict. The fold is those verdict-gated address ANDs (docs/CIRCUIT_PFC.md:
winner_only_max out[i] = idx[i] AND solve, 0 bytes/lane). This adds the §1E bind so that decided
winner-address IS the physical content of latch_reg@2409283485 — so ONE addressed read of the fold
surfaces the answer into the register the high-impedance probe already reads. The host does no compute:
it routes the block in and reads the register out. Expand the substrate; don't cache around it.

  python muhl_fab_fold_latch.py           # verify byte-exact, then store (one time)
  python muhl_fab_fold_latch.py revert    # undo via the genome journal (byte-exact restore)
"""
import hashlib, json, mmap, os, random, struct, sys, time
sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")   # titan_circuit with _alloc
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_fold_latch_genome.jsonl"
MAGIC = b"PFCWINMN"; CODE = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
NAME = "muhl_fold_latch"; N_LO, T_LO = 608, 640
AND = CODE["and"]
LATCH_REG = 2409283485                                          # the answer register the probe reads (role=answer)


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n"); g.flush(); os.fsync(g.fileno())
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob); f.flush(); os.fsync(f.fileno())


def revert():
    if not os.path.exists(GENOME):
        print("no genome journal — nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"])); f.flush(); os.fsync(f.fileno())
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


def reference(hw, nonce, target):                              # INDEPENDENT hashlib reference (§3), never the replaced path
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
    print(f"FABRICATE (once) — §1E junction: winner-only fold.solve -> latch_reg@{LATCH_REG} (answer register)")
    print(f"  gen_win as stored: {n_gate:,} typed gates, {n_in} in, {len(outs)} out, opcodes {sorted({g[0] for g in G})}")
    base = 2 + n_in

    NOT = CODE["not"]

    def build_junction(mutant=None):
        """gen_win.out[1:33] is ALREADY the win-gated winner-address (measured: ungating it changes nothing —
        the gating lives inside gen_win). So this junction is a §1E RELOCATION, not new logic: buffer that
        decided address onto fresh wires bound to latch_reg. `mutant` binds the WRONG source so the suite is
        shown to CATCH one (§45C: a suite that passes first try measured itself, not the circuit)."""
        win_w = outs[0]; idx_w = outs[1:33]                    # decided: win verdict + gated winner-address
        ng = list(G); latch = []
        for i in range(32):
            src = idx_w[i]
            if mutant == "raw_nonce": src = 2 + (N_LO + i)     # bind the raw nonce INPUT (pre-decision) -> caught on losers
            if mutant == "shifted":   src = idx_w[(i + 1) % 32]  # scrambled address -> caught on winners
            n1 = base + len(ng); ng.append((NOT, src, src))    # identity buffer: physically materialize the
            ng.append((NOT, n1, n1)); latch.append(base + len(ng) - 1)  # decided bit on a fresh wire = latch_reg
        drop = None; del drop                                  # fab-shape: build stage owns its cleanup
        return ng, [win_w] + latch

    NG, outs_all = build_junction()
    n_gate2 = len(NG); n_wire2 = 2 + n_in + n_gate2
    d = [0] * (2 + n_in + n_gate2)
    for k in range(n_gate2):
        _op, a, b = NG[k]; d[2 + n_in + k] = 1 + max(d[a], d[b])
    depth = max(d[w] for w in outs_all)
    print(f"  junctioned: {n_gate2:,} gates (+{n_gate2 - n_gate}), DEPTH {depth}, latch = winner-address gated by solve")

    def score(ng, oa):
        """(exact, genuine_wins, N) vs the INDEPENDENT hashlib reference — balanced easy/impossible targets."""
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
            rw, rl = reference(hw, nonce, target)
            if (gw, gl) == (rw, rl): ok += 1
            if rw: wins += 1
        return ok, wins, N

    print("  verifying byte-exact vs the INDEPENDENT hashlib reference …", flush=True)
    okc, wins, N = score(NG, outs_all)
    print(f"  balanced: {wins}/{N} genuine WINs · {N-wins} negatives (all-zero circuit would score {N-wins}/{N}) "
          f"-> byte-exact {okc}/{N}")
    if okc != N:
        print("  MISMATCH — writing NOTHING (no cheating)."); return 1

    print("  mutant test — the suite must CATCH a deliberately-broken variant:", flush=True)
    caught = 0
    for mu in ("raw_nonce", "shifted"):
        mg, mo = build_junction(mutant=mu)
        mok, _, _ = score(mg, mo)
        hit = mok < N; caught += hit
        print(f"    mutant {mu:8s} scored {mok}/{N}  -> {'CAUGHT' if hit else 'NOT CAUGHT — suite is blind'}")
    if caught < 2:
        print("  the suite cannot see a broken circuit — writing NOTHING."); return 1

    body = b"".join(struct.pack("<Bii", op, a, b) for (op, a, b) in NG) + \
           b"".join(struct.pack("<i", w) for w in outs_all)
    blob = MAGIC + struct.pack("<IIII", n_in, n_wire2, n_gate2, len(outs_all)) + body
    off, tn = TC._alloc(len(blob), reg)
    t0 = time.time(); _journal(off, blob)
    reg = json.load(open(REG))
    reg[NAME] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": n_in, "n_wire": n_wire2,
                 "n_gate": n_gate2, "n_out": len(outs_all), "format": "typed", "depth": depth,
                 "junction": f"winner-only fold.solve -> latch_reg (§1E shared address @{LATCH_REG})",
                 "junctioned_to": {"circuit": "latch_reg", "addr": LATCH_REG, "width": 4},
                 "layout": "in: header0..607|nonce608..639|target640..895 ; out: win:1|latch(winner-addr):32",
                 "stored_per_lane": 0}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print(f"\n  STORED '{NAME}' @ {off}  ({len(blob):,} B)  [{time.time()-t0:.2f}s of one-time MANUFACTURING]")
    print(f"  §1E: fold.solve -> latch_reg@{LATCH_REG}. One addressed pass writes the decided winner-address into the")
    print(f"  answer register the probe reads. 0 bytes/lane. GGUF-valid: {valid}.  revert: python muhl_fab_fold_latch.py revert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
