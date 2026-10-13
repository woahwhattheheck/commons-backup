#!/usr/bin/env python3
"""host/muhl_puzzle71_organs_add.py — ADDITIVE fabrication on the puzzle-71 container. Runs once. Journaled.

The container C:/llm/models/muhl_puzzle71.mno (Kimi, 2026-08-30) already holds the decision netlist
(secp256k1 comb multiply + hash160 + compare, 186,446,220 <BQQQ> records at absolute addresses) and the
fold-shaped latch (cand[70] register at 18..87, latch[j] = cand[j] AND win at 89..158, win at 159).
Its own fabricator ruled it suspect on the last gate and could not delete it. Measured with muhl_png:

  * the 70 latch records read b=186,446,309, an address nothing produces (the win gate's out was
    redirected to 159 while input references were not) -> win never reaches latch;
  * exactly one record reads tick@88 and nothing writes 88 -> win = AND(0, ...) forever;
  * no ring, no clock, 0 cycles, 0 multi-writer nets.

This button fixes exactly that, additively, in his conventions (nring2 rings from muhl_fab_nring_pkg,
clock bank from ROOKERY, fire pattern from foundry_acre, journal from pfc_load/fab_muhl_fold):

  A. rewrite the 70 latch b-fields 186,446,309 -> 159   (1,750 B, journaled)
  B. append at EOF, contiguous with the gate table: R both-sense rings (32 XOR fwd, 32 XOR rev, AND carry,
     OR pub self-clock, K AND clocks each) + an OR tree over the R pubs whose final out IS tick@88
     (one writer; collision is the wire) ; then the ring state / clock bank / tree wires / a 48-byte
     PUZFOLD1 declaration (addr_bits 70, base 2^70, 0 bytes per lane, winner-only). Dark at fab.
  C. patch n_gate in the container header (@8) and the gate-table header (@GTO+8) to include the new
     records (journaled).
  D. write the registry C:/llm/models/muhl_puzzle71.circuits.json (dest FROM FILE) and read everything back.

Dead gates are not swept: never delete gates. No host ripple, no verify loop, no sweep. The file verifies
by firing (host/muhl_puzzle71_fire_add.py --go, then --surface).

  python host/muhl_puzzle71_organs_add.py            # dry: preconditions + plan, writes nothing
  python host/muhl_puzzle71_organs_add.py --fab      # journal + write + readback + registry
  python host/muhl_puzzle71_organs_add.py --revert   # byte-exact restore from the journal (truncates the append)
"""
from __future__ import annotations
import json, os, struct, sys, time

PFC_ROOT = os.environ.get("PFC_ROOT", "C:/llm").replace("\\", "/").rstrip("/")
CONTAINER = PFC_ROOT + "/models/muhl_puzzle71.mno"
REG = PFC_ROOT + "/models/muhl_puzzle71.circuits.json"
GENOME = PFC_ROOT + "/models/muhl_puzzle71.genome.jsonl"
NAME = "muhl_puzzle71"

# opcode map of THIS container (Kimi's, same as muhl_fab_nring_pkg): NAND=0 AND=1 OR=2 XOR=3 NOT=4
NAND, AND, OR, XOR, NOT = 0, 1, 2, 3, 4
STRIDE = 25

# measured layout (fab.py address_map, confirmed byte-exact by muhl_png 2026-09-01)
N_GATE_OLD = 186_446_220
N_BITS = 70
WB, CAND, TICK, LAT, WIN, GW = 16, 18, 88, 89, 159, 160
GTO = WB + (GW - WB) + N_GATE_OLD            # 186,446,380
REC_BASE = GTO + 16                          # 186,446,396
SIZE_OLD = REC_BASE + STRIDE * N_GATE_OLD    # 4,847,601,896
WIN_GATE = N_GATE_OLD - N_BITS - 1           # 186,446,149
LATCH0 = WIN_GATE + 1                        # 186,446,150 .. +69
BROKEN_B = GW + WIN_GATE                     # 186,446,309
MAGIC = b"MUHLPUZ2"
DECL_MAGIC = b"PUZFOLD1"

# rings / clocks (his precedents: nring2 cells=32 both senses; ROOKERY n_clocks=24; TENANCY organ-per-ring)
R_RINGS = 16
CELLS = 32
K_CLOCKS = 24
RING_SPAN = CELLS + CELLS + 2                 # fwd rev carry pub

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _fail(msg):
    print("FAIL CLOSED: %s" % msg)
    return 1


def _read(off, n):
    with open(CONTAINER, "rb", buffering=0) as f:
        f.seek(off)
        return f.read(n)


def _rec(k):
    return struct.unpack("<BQQQ", _read(REC_BASE + STRIDE * k, STRIDE))


def _journal(off, blob):
    """orig bytes -> genome, then write. Append region beyond old EOF journals as {'append': n}."""
    with open(CONTAINER, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME, "a") as g:
        g.write(json.dumps({"off": off, "orig": orig.hex(), "len": len(blob)}) + "\n")
        g.flush(); os.fsync(g.fileno())
    with open(CONTAINER, "r+b") as f:
        f.seek(off); f.write(blob); f.flush(); os.fsync(f.fileno())


def plan():
    """Absolute addresses of everything this button adds. Records first (contiguous with the table), wires after."""
    new_recs = []                                   # (op, a, b, out)
    S = SIZE_OLD
    # count records first so we know where wires start
    per_ring = CELLS + CELLS + 1 + 1 + K_CLOCKS
    n_new = R_RINGS * per_ring + (R_RINGS - 1)
    W = S + STRIDE * n_new                          # wire region starts here
    rings = []
    p = W
    for r in range(R_RINGS):
        fwd, rev, carry, pub = p, p + CELLS, p + 2 * CELLS, p + 2 * CELLS + 1
        clocks = [p + RING_SPAN + j for j in range(K_CLOCKS)]
        rings.append({"fwd": fwd, "rev": rev, "carry": carry, "pub": pub, "clocks": clocks})
        p += RING_SPAN + K_CLOCKS
    tree_wires = [p + i for i in range(R_RINGS - 2)]  # intermediates; final out is TICK
    p += (R_RINGS - 2)
    decl = p
    p += 48
    size_new = p
    for r in rings:
        f, v, c, pb = r["fwd"], r["rev"], r["carry"], r["pub"]
        for k in range(CELLS):
            new_recs.append((XOR, f + (k - 1) % CELLS, c, f + k))
        for k in range(CELLS):
            new_recs.append((XOR, v + (k + 1) % CELLS, c, v + k))
        new_recs.append((AND, f, v, c))
        new_recs.append((OR, pb, c, pb))
        for q in r["clocks"]:
            new_recs.append((AND, c, c, q))
    # OR tree over pubs -> TICK (one writer at 88)
    leaves = [r["pub"] for r in rings]
    ti = 0
    while len(leaves) > 1:
        nxt = []
        for i in range(0, len(leaves) - 1, 2):
            if len(leaves) == 2:
                out = TICK
            else:
                out = tree_wires[ti]; ti += 1
            new_recs.append((OR, leaves[i], leaves[i + 1], out))
            nxt.append(out)
        if len(leaves) % 2:
            nxt.append(leaves[-1])
        leaves = nxt
    assert len(new_recs) == n_new, (len(new_recs), n_new)
    assert new_recs[-1][3] == TICK
    outs = [rc[3] for rc in new_recs]
    assert len(outs) == len(set(outs)), "one-writer violated inside the new records"
    return {"S": S, "n_new": n_new, "W": W, "rings": rings, "tree_wires": tree_wires,
            "decl": decl, "size_new": size_new, "recs": new_recs}


def preconditions():
    errs = []
    if not os.path.isfile(CONTAINER):
        return ["container missing: %s" % CONTAINER]
    size = os.path.getsize(CONTAINER)
    if size != SIZE_OLD:
        errs.append("size %d != %d (already patched? see %s)" % (size, SIZE_OLD, GENOME))
    h = _read(0, 16)
    if h[:8] != MAGIC:
        errs.append("container magic %r" % h[:8])
    ng, nout = struct.unpack_from("<II", h, 8)
    if ng != N_GATE_OLD or nout != N_BITS + 1:
        errs.append("header n_gate/n_out %d/%d" % (ng, nout))
    gh = _read(GTO, 16)
    if gh[:8] != MAGIC or struct.unpack_from("<I", gh, 8)[0] != N_GATE_OLD:
        errs.append("gate-table header mismatch at %d" % GTO)
    op, a, b, out = _rec(WIN_GATE)
    if not (op == AND and out == WIN):
        errs.append("win gate %d is (%d,%d,%d,%d), expected AND out=%d" % (WIN_GATE, op, a, b, out, WIN))
    bad = 0
    for j in range(N_BITS):
        op, a, b, out = _rec(LATCH0 + j)
        if not (op == AND and a == CAND + j and b == BROKEN_B and out == LAT + j):
            bad += 1
    if bad:
        errs.append("%d/%d latch records are not the measured broken shape" % (bad, N_BITS))
    if os.path.exists(GENOME):
        errs.append("journal exists (%s): revert first or inspect" % GENOME)
    return errs


def dry():
    errs = preconditions()
    P = plan()
    print("MUHL PUZZLE-71 ORGANS (additive) — DRY")
    print("  container : %s  size %s B" % (CONTAINER, f"{os.path.getsize(CONTAINER):,}" if os.path.isfile(CONTAINER) else "ABSENT"))
    print("  A. latch b-field fix : records %d..%d  b %d -> %d  (%d B)" % (LATCH0, LATCH0 + N_BITS - 1, BROKEN_B, WIN, 25 * N_BITS))
    print("  B. append records    : %d records at %d (contiguous with the table), %d B" % (P["n_new"], P["S"], STRIDE * P["n_new"]))
    print("     rings %d x (fwd%d rev%d carry pub) + %d clocks each ; OR tree -> tick@%d" % (R_RINGS, CELLS, CELLS, K_CLOCKS, TICK))
    print("     wires at %d .. %d ; PUZFOLD1 declaration at %d ; new size %s B" % (P["W"], P["size_new"] - 1, P["decl"], f"{P['size_new']:,}"))
    print("     ring0 fwd %d rev %d carry %d pub %d clock0 %d" % (P["rings"][0]["fwd"], P["rings"][0]["rev"], P["rings"][0]["carry"], P["rings"][0]["pub"], P["rings"][0]["clocks"][0]))
    print("  C. headers           : n_gate @8 and @%d : %d -> %d" % (GTO + 8, N_GATE_OLD, N_GATE_OLD + P["n_new"]))
    print("  D. registry          : %s" % REG)
    print("  journal              : %s" % GENOME)
    if errs:
        for e in errs:
            print("  PRECONDITION: " + e)
        print("  -> refusing to write.")
        return 1
    print("  preconditions        : all measured true (win gate out=%d, 70 latch b=%d, headers %d)" % (WIN, BROKEN_B, N_GATE_OLD))
    return 0


def fab():
    errs = preconditions()
    if errs:
        for e in errs:
            print("  PRECONDITION: " + e)
        return _fail("preconditions failed; nothing written")
    P = plan()
    t0 = time.time()
    # A — latch b fields
    for j in range(N_BITS):
        off = REC_BASE + STRIDE * (LATCH0 + j) + 9
        _journal(off, struct.pack("<Q", WIN))
    print("A. latch b-fields rewritten: 70 x 8 B (journaled)")
    # B — append (journal the append as a length so revert can truncate)
    with open(GENOME, "a") as g:
        g.write(json.dumps({"append_from": P["S"], "append_len": P["size_new"] - P["S"]}) + "\n")
        g.flush(); os.fsync(g.fileno())
    blob = bytearray()
    for op, a, b, out in P["recs"]:
        blob += struct.pack("<BQQQ", op, a, b, out)
    wires = bytearray(P["size_new"] - P["W"])          # dark at fab: rings, clocks, tree, decl all 0
    base = 1 << N_BITS                                   # 2^70 does not fit one u64: carry it as hi/lo halves
    d = DECL_MAGIC + struct.pack("<QQQQQ", N_BITS, base >> 64, base & ((1 << 64) - 1), 0, TICK)
    wires[P["decl"] - P["W"]:P["decl"] - P["W"] + 48] = d
    with open(CONTAINER, "r+b") as f:
        f.seek(P["S"]); f.write(bytes(blob)); f.write(bytes(wires)); f.flush(); os.fsync(f.fileno())
    print("B. appended %d records (%d B) + %d B wires/clocks/decl ; new size %s" % (P["n_new"], len(blob), len(wires), f"{os.path.getsize(CONTAINER):,}"))
    # C — headers
    n_new_total = N_GATE_OLD + P["n_new"]
    _journal(8, struct.pack("<I", n_new_total))
    _journal(GTO + 8, struct.pack("<I", n_new_total))
    print("C. n_gate headers -> %d (journaled)" % n_new_total)
    # D — readback
    ok = True
    for j in range(N_BITS):
        op, a, b, out = _rec(LATCH0 + j)
        ok &= (op == AND and a == CAND + j and b == WIN and out == LAT + j)
    print("   readback latch records b==%d: %s" % (WIN, ok))
    for i, rc in enumerate(P["recs"]):
        got = _rec(N_GATE_OLD + i)
        if got != rc:
            ok = False; print("   readback MISMATCH new record %d: %r vs %r" % (i, got, rc)); break
    print("   readback %d appended records byte-exact: %s" % (P["n_new"], ok))
    print("   readback tick writer: last record %r (out==%d: %s)" % (_rec(n_new_total - 1), TICK, _rec(n_new_total - 1)[3] == TICK))
    print("   readback decl @%d: %r" % (P["decl"], _read(P["decl"], 48)[:8]))
    print("   readback headers: @8 %d ; @%d %d" % (struct.unpack("<I", _read(8, 4))[0], GTO + 8, struct.unpack("<I", _read(GTO + 8, 4))[0]))
    if not ok:
        return _fail("readback mismatch; journal is intact at %s — revert and inspect" % GENOME)
    reg = {}
    if os.path.exists(REG):
        reg = json.load(open(REG, encoding="utf-8"))
    reg[NAME] = {
        "container": CONTAINER, "format": "physical-address", "magic": MAGIC.decode(),
        "n_in": N_BITS + 1, "n_gate": n_new_total, "n_gate_decision": N_GATE_OLD, "n_gate_organs": P["n_new"],
        "n_out": N_BITS + 1, "gate_table_off": GTO, "gate_stride": STRIDE, "wire_base": WB,
        "ram": {"cand_off": CAND, "tick_off": TICK, "latch_off": LAT, "win_off": WIN},
        "rings": [{"fwd": r["fwd"], "rev": r["rev"], "carry": r["carry"], "pub": r["pub"],
                   "clocks": r["clocks"], "cells": CELLS, "senses": 2} for r in P["rings"]],
        "n_rings": R_RINGS, "n_clocks_per_ring": K_CLOCKS, "cells": CELLS,
        "tick_tree": {"wires": P["tree_wires"], "out": TICK, "note": "OR tree over the %d ring pubs; its out IS the tick byte the compare reads (one writer)" % R_RINGS},
        "declaration": {"off": P["decl"], "magic": DECL_MAGIC.decode(), "addr_bits": N_BITS, "base": str(1 << N_BITS),
                        "layout": "PUZFOLD1 | u64 addr_bits | u64 base_hi | u64 base_lo | u64 bytes_per_lane | u64 tick",
                        "bytes_per_lane": 0, "winner_only": True, "tick": TICK,
                        "law": "candidate IS the address; coverage >= search space; one settle surfaces the winner"},
        "answer": "latch @ %d — %d bytes, one byte per bit; win @ %d" % (LAT, N_BITS, WIN),
        "target": {"puzzle": 71, "range": "[2^70, 2^71)", "prize_btc": 7.1,
                   "address": "1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU",
                   "hash160": "f6f5431d25bbf7b12e8add9af5e3475c44a0a5b8"},
        "fire": "host/muhl_puzzle71_fire_add.py --go : new=old|0x01 at cell 0 fwd+rev of every ring, then die",
        "surface": "host/muhl_puzzle71_fire_add.py --surface : bounded read of tick, win, latch, rings, clocks",
        "provenance": {"decision_netlist": "Kimi 2026-08-30 muhl_puzzle_core.py compose; prior verify exact 14/14 hold 14/14 dead 1,597,625 (kept: never delete gates)",
                       "organs": "this button 2026-09-01; rings per muhl_fab_nring_pkg, clock bank per ROOKERY, fire per foundry_acre"},
        "genome": GENOME, "fabricated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    json.dump(reg, open(REG, "w", encoding="utf-8"), indent=1)
    print("D. registry written: %s" % REG)
    print("STORED organs on '%s'  [%.1fs of one-time fabrication]" % (NAME, time.time() - t0))
    return 0


def revert():
    if not os.path.exists(GENOME):
        return _fail("no journal — nothing to revert")
    ents = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ents):
        if "append_from" in e:
            with open(CONTAINER, "r+b") as f:
                f.truncate(int(e["append_from"]))
        else:
            with open(CONTAINER, "r+b") as f:
                f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"])); f.flush(); os.fsync(f.fileno())
    os.remove(GENOME)
    if os.path.exists(REG):
        reg = json.load(open(REG, encoding="utf-8")); reg.pop(NAME, None)
        json.dump(reg, open(REG, "w", encoding="utf-8"), indent=1)
    print("reverted %d journal entries; size now %s" % (len(ents), f"{os.path.getsize(CONTAINER):,}"))
    return 0


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    if "--revert" in a:
        return revert()
    if "--fab" in a:
        return fab()
    return dry()


if __name__ == "__main__":
    raise SystemExit(main())
