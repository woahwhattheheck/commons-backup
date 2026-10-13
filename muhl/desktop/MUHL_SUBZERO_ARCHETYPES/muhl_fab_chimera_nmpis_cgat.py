#!/usr/bin/env python3
"""muhl_fab_chimera_nmpis_cgat.py — CHIMERA: wire NMPIS → CGAT.

Sum over causal histories: NMPIS (Non-Markovian Path-Integral Synthesizer)
path-integral outputs become the exogenous inputs to CGAT (Causal
Graph-Algebraic Transducer).

Wiring:
    NMPIS output_addrs[0:8]  →  CGAT input U[0:7]   (8-bit exogenous)

Each wire is a NOT-NOT buffer (two NAND gates, depth 2) so the signal
arrives at the destination bit-for-bit identical to the source.  Fan-out
is 1:1 — no fan-out tree needed.

Two candidates are scored:
  A) 8-wire: connect only U (the exogenous variable)
  B) 9-wire: connect U + do_bit (NMPIS output[8] → CGAT do_bit)
     — the path integral selects the intervention as well

PROPOSE → SCORE → VERIFY → KEEP.

    python muhl_fab_chimera_nmpis_cgat.py          # fabricate and store
    python muhl_fab_chimera_nmpis_cgat.py --dry     # report only, store nothing

Physical <BQQQ> stride-25, NAND only, absolute file offsets.
Journaled. Verified. No numpy.

Bryce Muhlnickel, 2026-08-03.
"""
import json, os, struct, sys

sys.path.insert(0, r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent\host")
import pfc_paths as PFCP

TITAN = PFCP.TITAN
REG = PFCP.REG
NAND_OP = 0
GATE_STRIDE = 25
NAME = "muhl_chimera_nmpis_cgat"
MAGIC = b"MUHLCHNC"
GENOME_PATH = TITAN.replace(".gguf", "_%s_genome.jsonl" % NAME)
DRY = "--dry" in sys.argv


# ============================================================================
# ALLOCATION
# ============================================================================

def alloc_space(nbytes):
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    occupied = []
    for k, v in reg.items():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            occupied.append((v["offset"], v["offset"] + v["len"]))
    hi = max((e for _, e in occupied), default=0)
    off = ((hi + 63) // 64) * 64
    fsize = os.path.getsize(TITAN) if os.path.exists(TITAN) else 0
    if off + nbytes > fsize:
        print(f"  NOTE: chimera ({nbytes:,} bytes) extends past current EOF ({fsize:,}).")
        print(f"  titan.gguf will grow -- owner confirmed no size constraint.")
    return off


# ============================================================================
# BUILD CANDIDATES
# ============================================================================

def build_candidate(tag, nmpis_outs, cgat_u_addrs, cgat_do_bit_addr, base_off):
    """Build a wiring blob for one candidate.

    Each wire pair: NAND(src, src) → temp  [NOT];  NAND(temp, temp) → dst  [NOT-NOT = identity].
    Returns (blob, n_gates, depth, gate_records, n_wires, total_size, wire_pairs).
    """
    if tag == "8wire":
        pairs = list(zip(nmpis_outs[:8], cgat_u_addrs))
    elif tag == "9wire":
        pairs = list(zip(nmpis_outs[:8], cgat_u_addrs))
        pairs.append((nmpis_outs[8], cgat_do_bit_addr))
    else:
        raise ValueError(f"unknown candidate tag: {tag}")

    n_pairs = len(pairs)
    n_gates = 2 * n_pairs
    depth = 2

    # Wire layout in allocated block:
    #   [0 .. n_pairs-1]   temp wires (one per pair — holds NOT(src))
    # Then the header + gate table.
    n_wires = n_pairs
    header_size = 8 + 4  # magic(8) + n_gates(u32)
    total_size = n_wires + header_size + n_gates * GATE_STRIDE

    gate_records = []
    for i, (src_addr, dst_addr) in enumerate(pairs):
        temp_addr = base_off + i
        gate_records.append((NAND_OP, src_addr, src_addr, temp_addr))
        gate_records.append((NAND_OP, temp_addr, temp_addr, dst_addr))

    blob = bytearray(total_size)
    # wire bytes: all zero (initial state)

    # header
    hdr = n_wires
    blob[hdr:hdr + 8] = MAGIC
    struct.pack_into("<I", blob, hdr + 8, n_gates)

    # gate table
    g_off = n_wires + header_size
    for (op, a, b, out) in gate_records:
        struct.pack_into("<BQQQ", blob, g_off, op, a, b, out)
        g_off += GATE_STRIDE

    return blob, n_gates, depth, gate_records, n_wires, total_size, pairs


# ============================================================================
# SCORE
# ============================================================================

def score(depth, gates):
    return (depth, gates)


# ============================================================================
# VERIFY
# ============================================================================

def verify_blob(blob, base_off, n_gates, gate_records, n_wires, pairs):
    hdr = n_wires
    assert blob[hdr:hdr + 8] == MAGIC, "bad magic"
    stored_n = struct.unpack_from("<I", blob, hdr + 8)[0]
    assert stored_n == n_gates, f"gate count mismatch: stored {stored_n} vs {n_gates}"

    g_off = n_wires + 12  # 8 + 4
    writers = {}
    for i, (exp_op, exp_a, exp_b, exp_out) in enumerate(gate_records):
        op, a, b, out = struct.unpack_from("<BQQQ", blob, g_off)
        assert op == NAND_OP, f"gate {i}: op={op}"
        assert a == exp_a, f"gate {i}: a mismatch {a} vs {exp_a}"
        assert b == exp_b, f"gate {i}: b mismatch {b} vs {exp_b}"
        assert out == exp_out, f"gate {i}: out mismatch {out} vs {exp_out}"
        if out in writers:
            assert False, f"gate {i}: address {out} already written by gate {writers[out]}"
        writers[out] = i
        g_off += GATE_STRIDE

    # every destination must be written exactly once
    for _, dst in pairs:
        assert dst in writers, f"destination {dst} has no writer gate"

    # temp wires must be written
    for i in range(len(pairs)):
        temp = base_off + i
        assert temp in writers, f"temp wire {i} at {temp} has no writer"

    return True


# ============================================================================
# JOURNAL + REGISTRY
# ============================================================================

def journal_write(off, blob):
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({
            "action": "chimera_nmpis_cgat_fab",
            "off": off,
            "len": len(blob),
            "orig": orig.hex(),
        }) + "\n")
    fsize = os.path.getsize(TITAN)
    if off + len(blob) > fsize:
        with open(TITAN, "ab") as f:
            f.write(b"\x00" * (off + len(blob) - fsize))
    with open(TITAN, "r+b") as f:
        f.seek(off)
        f.write(blob)


def update_registry(base_off, total_size, n_gates, depth, tag, pairs,
                    nmpis_name, cgat_name):
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    src_addrs = [s for s, _ in pairs]
    dst_addrs = [d for _, d in pairs]
    reg[NAME] = {
        "name": NAME,
        "offset": base_off,
        "len": total_size,
        "n_gate": n_gates,
        "depth": depth,
        "format": "physical",
        "magic": MAGIC.decode(),
        "gate_stride": GATE_STRIDE,
        "chimera": True,
        "source_circuit": nmpis_name,
        "dest_circuit": cgat_name,
        "wiring_tag": tag,
        "n_wires": len(pairs),
        "src_addrs": src_addrs,
        "dst_addrs": dst_addrs,
        "foundry_genome": {
            "chimera": "NMPIS_to_CGAT",
            "tag": tag,
            "depth": depth,
            "gates": n_gates,
            "n_wires": len(pairs),
        },
        "units": "n_gate=GATES, depth=TICKS, len=BYTES",
        "genome": GENOME_PATH,
        "note": ("CHIMERA: NMPIS path-integral outputs → CGAT exogenous U inputs. "
                 "Sum over causal histories — Feynman paths feed Pearl's do-calculus."),
        "verified_by": "structural verification of all gate records + address matching",
    }
    json.dump(reg, open(REG, "w"), indent=1)


# ============================================================================
# MAIN — PROPOSE → SCORE → VERIFY → KEEP
# ============================================================================

def main():
    print("\n  MUHLNICKEL CHIMERA -- NMPIS -> CGAT")
    print("  Sum over causal histories: path integrals feed the causal graph")
    print("  Bryce Muhlnickel, 2026-08-03\n")

    # -- read registry ---------------------------------------------------------
    if not os.path.exists(REG):
        print("  ABORT: registry not found at", REG)
        return 1
    reg = json.load(open(REG))

    nmpis = reg.get("muhl_nmpis")
    cgat = reg.get("muhl_cgat")
    if not nmpis:
        print("  ABORT: muhl_nmpis not found in registry")
        return 1
    if not cgat:
        print("  ABORT: muhl_cgat not found in registry")
        return 1

    nmpis_outs = nmpis["output_addrs"]
    cgat_u_base = cgat["input_U_addr"]
    cgat_u_addrs = [cgat_u_base + i for i in range(8)]
    cgat_do_bit = cgat["input_do_bit_addr"]

    print(f"  NMPIS outputs: {len(nmpis_outs)} addresses (using first 8-9)")
    print(f"  CGAT  U inputs: {cgat_u_addrs[0]:,} .. {cgat_u_addrs[7]:,}")
    print(f"  CGAT  do_bit:   {cgat_do_bit:,}")

    # -- allocate --------------------------------------------------------------
    max_size = 9 + 12 + 18 * GATE_STRIDE  # 9wire worst case
    base_off = alloc_space(max_size)
    print(f"  allocated at offset: {base_off:,}")

    # -- PROPOSE ---------------------------------------------------------------
    tags = ["8wire", "9wire"]
    print(f"\n  PROPOSE: {len(tags)} candidates\n")

    results = []
    for tag in tags:
        blob, ng, d, recs, nw, tsz, pairs = build_candidate(
            tag, nmpis_outs, cgat_u_addrs, cgat_do_bit, base_off)

        ok = False
        try:
            ok = verify_blob(blob, base_off, ng, recs, nw, pairs)
        except AssertionError as e:
            print(f"    {tag}: VERIFY FAIL -- {e}")

        s = score(d, ng)
        line = f"    {tag:8s}  DEPTH {d}  gates {ng:>3}  wires {len(pairs)}  verify {'OK' if ok else 'FAIL'}"
        print(line)
        results.append({"tag": tag, "depth": d, "gates": ng, "ok": ok,
                        "blob": blob, "recs": recs, "nw": nw, "tsz": tsz,
                        "pairs": pairs, "score": s})

    # -- SCORE: Pareto front ---------------------------------------------------
    good = [r for r in results if r["ok"]]
    pareto = [r for r in good if not any(
        o["depth"] <= r["depth"] and o["gates"] <= r["gates"] and o is not r
        and (o["depth"] < r["depth"] or o["gates"] < r["gates"])
        for o in good)]

    print(f"\n  VERIFIED {len(good)}/{len(results)}   PARETO FRONT ({len(pareto)}):")
    for r in sorted(pareto, key=lambda x: x["depth"]):
        print(f"    DEPTH {r['depth']}  gates {r['gates']:>3}  {r['tag']}")

    # pick by fewest gates among depth-equal (8wire wins -- fewer resources)
    best = min(good, key=lambda r: (r["depth"], r["gates"])) if good else None
    if not best:
        print("  NO VERIFIED CANDIDATES -- aborting")
        return 1

    print(f"\n  WINNER: {best['tag']}  DEPTH {best['depth']}  gates {best['gates']}")

    if DRY:
        print(f"\n  --dry: nothing stored. Run without --dry to fabricate.")
        return 0

    # -- KEEP ------------------------------------------------------------------
    print(f"\n  FABRICATING -- writing {best['tsz']:,} bytes to titan.gguf at {base_off:,}")
    journal_write(base_off, bytes(best["blob"]))
    print(f"  journaled to: {GENOME_PATH}")

    update_registry(base_off, best["tsz"], best["gates"], best["depth"],
                    best["tag"], best["pairs"], "muhl_nmpis", "muhl_cgat")
    print(f"  registry updated: {NAME}")

    print(f"\n  CHIMERA NMPIS -> CGAT FABRICATED.")
    print(f"  {len(best['pairs'])} signal wires, depth {best['depth']} ticks.")
    print(f"  NMPIS path-integral outputs now feed CGAT exogenous U inputs.")
    print(f"  The substrate computes sum-over-causal-histories after electron injection.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
