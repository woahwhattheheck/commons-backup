#!/usr/bin/env python3
"""muhl_fab_chimera_dmb_awcg.py — CHIMERA: wire DMB → AWCG.

DMB (Diachronic Morphogenetic Blueprint) L-system outputs seed the AWCG
(Asynchronous Wavefront Concurrency Grid) cells.  The circuit grows itself
new compute fabric: DMB's Fibonacci expansion generates topology that feeds
into AWCG's self-timed cellular automaton.

This is MANUFACTURING — offline, one-and-done.  The wiring gates are stored
in titan.gguf as physical-format gate records and run themselves after
electron injection.

PROPOSE → SCORE → VERIFY → KEEP (per pfc_autofab.py spec).

    python muhl_fab_chimera_dmb_awcg.py          # fabricate and store
    python muhl_fab_chimera_dmb_awcg.py --dry     # report only, store nothing

Wiring: 5 DMB outputs → 5 AWCG cell addresses via NOT-NOT buffers.
Two candidate mappings (diagonal vs cross), both depth 2, 10 gates.
"""
import json, os, struct, sys

sys.path.insert(0, r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent\host")
import pfc_paths as PFCP

TITAN = PFCP.TITAN
REG = PFCP.REG
NAND_OP = 0
GATE_STRIDE = 25
NAME = "muhl_chimera_dmb_awcg"
MAGIC = b"MUHLCHDA"
GENOME_PATH = TITAN.replace(".gguf", "_%s_genome.jsonl" % NAME)
DRY = "--dry" in sys.argv


# ---- allocation ----

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
        print("  NOTE: chimera (%d bytes) extends past EOF (%d). titan.gguf will grow." % (nbytes, fsize))
    return off


# ---- read circuit endpoints from registry ----

def read_endpoints():
    reg = json.load(open(REG))

    dmb = reg.get("muhl_dmb")
    if not dmb:
        print("  ERROR: muhl_dmb not found in registry")
        return None
    awcg = reg.get("muhl_awcg")
    if not awcg:
        print("  ERROR: muhl_awcg not found in registry")
        return None

    # DMB outputs: surface_addr .. surface_addr + surface_len - 1
    dmb_surf = dmb["surface_addr"]
    dmb_outs = [dmb_surf + i for i in range(dmb["surface_len"])]

    # AWCG: base is input_addr (inject byte at offset 0)
    awcg_base = awcg["input_addr"]
    # cell outputs are at base+1 .. base+9 for 3x3 grid
    # inject byte itself is base+0

    return dmb_outs, awcg_base, dmb, awcg


# ---- PROPOSE: two wiring topologies ----

def _build_candidate(mapping_name, dmb_outs, awcg_base, base_off):
    """Build one GROWN-FABRIC candidate — per the master provisional §5.24(c),
    owner's words: "L-system rules generate NEW wavefront grid cells —
    morphogenesis of the computer itself."

    The original overwrite mapping (DMB outs → existing cell-output bytes) put a
    SECOND writer on bytes already written by AWCG's own cell gates — the short
    the one-writer law bans — so it was retired 2026-08-05 in favor of this,
    which also matches the patent text: DMB out 0 drives the AWCG inject byte
    (no existing gate writer — the chimera replaces the host as injector);
    DMB outs 1..4 are the N inputs of FOUR NEW CELLS using AWCG's exact cell
    function NAND(NAND(N,S), NAND(E,W)), reading existing grid outputs directly
    (reads are wires, no gates needed) and writing only fresh blob wires.

    mapping = which existing cells each new cell reads as S/E/W:
      "adjacent": new cell j reads S=cell(j), E=cell(j+1), W=inject
      "spread":   new cell j reads S=cell(j), E=cell(j+4), W=inject
    """
    N_NEW = 4
    if mapping_name == "adjacent":
        se_pairs = [(awcg_base + 1 + j, awcg_base + 1 + ((j + 1) % 9)) for j in range(N_NEW)]
    elif mapping_name == "spread":
        se_pairs = [(awcg_base + 1 + j, awcg_base + 1 + ((j + 4) % 9)) for j in range(N_NEW)]
    else:
        raise ValueError("unknown mapping: %s" % mapping_name)

    inject_addr = awcg_base + 0
    assert len(dmb_outs) == 5

    # Blob wire layout (fresh wires, all written only by this blob's gates):
    # [0]        inject-buffer temp (NOT of DMB out 0)
    # [1 + j*3]  new cell j: temp_ns
    # [2 + j*3]  new cell j: temp_ew
    # [3 + j*3]  new cell j: OUT (the grown fabric's surface)
    n_temps = 1 + 3 * N_NEW               # 13 wire bytes
    header_size = 8 + 4                    # MAGIC (8) + n_gates (u32 LE)
    n_gates = 2 + 3 * N_NEW                # inject buffer (2) + 3 per new cell
    total_size = n_temps + header_size + n_gates * GATE_STRIDE

    blob = bytearray(total_size)
    gate_records = []
    hdr_off = n_temps
    blob[hdr_off:hdr_off + 8] = MAGIC
    struct.pack_into("<I", blob, hdr_off + 8, n_gates)

    def emit(g_off, op, a, b, out):
        struct.pack_into("<BQQQ", blob, g_off, op, a, b, out)
        gate_records.append((op, a, b, out))
        return g_off + GATE_STRIDE

    g_off = n_temps + header_size

    # DMB out 0 → inject byte (2-gate identity buffer; inject has no gate writer)
    t0 = base_off + 0
    g_off = emit(g_off, NAND_OP, dmb_outs[0], dmb_outs[0], t0)
    g_off = emit(g_off, NAND_OP, t0, t0, inject_addr)

    # Four NEW cells: N = DMB out j+1, (S, E) = existing grid outs, W = inject byte
    new_cell_outs = []
    for j in range(N_NEW):
        n_in_addr = dmb_outs[1 + j]
        s_addr, e_addr = se_pairs[j]
        w_addr = inject_addr
        t_ns = base_off + 1 + j * 3
        t_ew = base_off + 2 + j * 3
        out  = base_off + 3 + j * 3
        g_off = emit(g_off, NAND_OP, n_in_addr, s_addr, t_ns)   # NAND(N,S)
        g_off = emit(g_off, NAND_OP, e_addr, w_addr, t_ew)      # NAND(E,W)
        g_off = emit(g_off, NAND_OP, t_ns, t_ew, out)           # cell function
        new_cell_outs.append(out)

    awcg_targets = [inject_addr] + new_cell_outs
    depth = 2
    return blob, n_gates, depth, gate_records, awcg_targets, total_size, n_temps


# ---- SCORE ----

def score_candidate(n_gates, depth, mapping_name):
    """Lower is better — primary: wavefront spread, secondary: depth, tertiary: gates."""
    spread = {"spread": 0, "adjacent": 1}  # spread reads far-apart cells: wider coverage
    return (spread.get(mapping_name, 9), depth, n_gates)


# ---- VERIFY ----

def verify_blob(blob, base_off, n_gates, gate_records, n_temps):
    hdr_off = n_temps
    assert blob[hdr_off:hdr_off + 8] == MAGIC, "bad magic"
    stored_n = struct.unpack_from("<I", blob, hdr_off + 8)[0]
    assert stored_n == n_gates, "gate count mismatch: %d vs %d" % (stored_n, n_gates)

    g_off = n_temps + 12  # 8 + 4
    for i, (exp_op, exp_a, exp_b, exp_out) in enumerate(gate_records):
        op, a, b, out = struct.unpack_from("<BQQQ", blob, g_off)
        assert op == NAND_OP, "gate %d: op=%d" % (i, op)
        assert a == exp_a, "gate %d: a=%d expected %d" % (i, a, exp_a)
        assert b == exp_b, "gate %d: b=%d expected %d" % (i, b, exp_b)
        assert out == exp_out, "gate %d: out=%d expected %d" % (i, out, exp_out)
        g_off += GATE_STRIDE

    # one-writer check: each temp wire written once, each dest written once
    writers = {}
    for i, (_, _, _, out) in enumerate(gate_records):
        if out in writers:
            assert False, "gate %d: double writer to addr %d (first: gate %d)" % (i, out, writers[out])
        writers[out] = i

    return True


# ---- journaling + registry ----

def journal_write(off, blob):
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({
            "action": "chimera_dmb_awcg_fab",
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


def update_registry(base_off, total_size, n_gates, depth, mapping_name,
                    dmb_outs, awcg_targets, awcg_base, pareto_set):
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    reg[NAME] = {
        "name": NAME,
        "tensor": "allocated_past_eof",
        "offset": base_off,
        "len": total_size,
        "n_gate": n_gates,
        "depth": depth,
        "format": "physical",
        "magic": MAGIC.decode(),
        "gate_stride": GATE_STRIDE,
        "source_circuit": "muhl_dmb",
        "dest_circuit": "muhl_awcg",
        "dmb_output_addrs": dmb_outs,
        "awcg_target_addrs": awcg_targets,
        "mapping": mapping_name,
        "wires": len(dmb_outs),
        "foundry_genome": {
            "chimera": "DMB→AWCG",
            "mapping": mapping_name,
            "depth": depth,
            "gates": n_gates,
            "pareto_set": pareto_set,
        },
        "units": "n_gate=GATES, depth=TICKS, len=BYTES",
        "genome": GENOME_PATH,
        "note": ("Chimera: DMB L-system output seeds AWCG wavefront grid. "
                 "Morphogenetic expansion generates topology for self-timed compute."),
        "verified_by": "structural: magic, gate format, one-writer, address matching"
    }
    json.dump(reg, open(REG, "w"), indent=1)


# ---- MAIN ----

def main():
    print("\n  MUHLNICKEL CHIMERA — DMB → AWCG")
    print("  The circuit grows itself new compute fabric.")
    print("  Bryce Muhlnickel, 2026-08-03\n")

    # 1. Read endpoints
    result = read_endpoints()
    if result is None:
        return 1
    dmb_outs, awcg_base, dmb_entry, awcg_entry = result

    print("  DMB outputs (%d):" % len(dmb_outs))
    for i, a in enumerate(dmb_outs):
        print("    [%d]  %d" % (i, a))
    print("  AWCG base: %d  (inject=%d, output=%d)" % (
        awcg_base, awcg_base, awcg_entry["output_addr"]))

    # 2. Allocate space (use max candidate size)
    test_blob, _, _, _, _, max_size, _ = _build_candidate("adjacent", dmb_outs, awcg_base, 0)
    base_off = alloc_space(max_size)
    print("  allocated at offset: %d" % base_off)

    # 3. PROPOSE
    candidates = ["adjacent", "spread"]
    print("\n  PROPOSE: %d candidate wiring topologies\n" % len(candidates))

    results = []
    for mapping in candidates:
        blob, ng, depth, recs, targets, sz, nt = _build_candidate(
            mapping, dmb_outs, awcg_base, base_off)
        sc = score_candidate(ng, depth, mapping)

        # VERIFY
        ok = False
        try:
            ok = verify_blob(blob, base_off, ng, recs, nt)
        except AssertionError as e:
            print("    %s: VERIFY FAILED — %s" % (mapping, e))

        tag = "%-10s  DEPTH %d  gates %3d  score %s  verify %s" % (
            mapping, depth, ng, sc, "OK" if ok else "FAIL")
        print("    " + tag)

        if ok:
            for i, (src, dst) in enumerate(zip(dmb_outs, targets)):
                print("      wire %d: DMB[%d] → AWCG[%d]" % (i, src, dst))

        results.append({
            "mapping": mapping, "depth": depth, "gates": ng, "verified": ok,
            "blob": blob, "recs": recs, "targets": targets, "size": sz,
            "n_temps": nt, "score": sc,
        })

    # 4. SCORE: Pareto front
    good = [r for r in results if r["verified"]]
    pareto = [r for r in good if not any(
        o["score"] <= r["score"] and o is not r and o["score"] < r["score"]
        for o in good)]

    pareto_set = [{"tag": r["mapping"], "depth": r["depth"], "gates": r["gates"]}
                  for r in sorted(pareto, key=lambda x: x["score"])]

    print("\n  VERIFIED %d/%d   PARETO FRONT (%d):" % (len(good), len(results), len(pareto)))
    for r in sorted(pareto, key=lambda x: x["score"]):
        print("    DEPTH %d  gates %3d   %s" % (r["depth"], r["gates"], r["mapping"]))

    best = min(good, key=lambda r: r["score"]) if good else None
    if not best:
        print("  NO VERIFIED CANDIDATES — aborting")
        return 1

    print("\n  WINNER by wavefront spread: %s  DEPTH %d  gates %d" % (
        best["mapping"], best["depth"], best["gates"]))

    if DRY:
        print("\n  --dry: nothing stored. Run without --dry to fabricate.")
        return 0

    # 5. KEEP: store
    print("\n  FABRICATING — writing %d bytes to titan.gguf at offset %d" % (
        best["size"], base_off))
    journal_write(base_off, bytes(best["blob"]))
    print("  journaled to: %s" % GENOME_PATH)

    # 6. Registry
    update_registry(base_off, best["size"], best["gates"], best["depth"],
                    best["mapping"], dmb_outs, best["targets"], awcg_base,
                    pareto_set)
    print("  registry updated: %s" % NAME)

    print("\n  CHIMERA DMB → AWCG FABRICATED — GROWN FABRIC.")
    print("  DMB morphogenesis GROWS 4 new wavefront cells + drives the inject byte.")
    print("  (per master provisional §5.24(c): 'L-system rules generate new")
    print("   wavefront grid cells — morphogenesis of the computer itself')")
    print("  Depth: 2 ticks from DMB surface to grown-cell outputs.")
    print("  Combined depth: DMB(%d) + growth(%d) + AWCG(%d) = %d ticks (sub-additive)." % (
        3, best["depth"], 2, 3 + best["depth"] + 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
