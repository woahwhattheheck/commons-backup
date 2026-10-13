#!/usr/bin/env python3
"""muhl_fab_palf.py — FABRICATE A PHASE-ASYNCHRONOUS LOGIC FIELD (PALF).

Bryce Muhlnickel, 2026-08-03.

A PALF is an unweighted wave-frequency fabric: self-clocked oscillator rings
whose cross-coupling NAND gates create interference patterns. Computation
emerges from the phase relationships between oscillators.

Each oscillator is a NAND ring segment whose output address feeds back to its
own input — the self-clock mechanism (predates the ring by 11 days, ~Jul 21).
Cross-coupling gates between oscillators compute interference. A NAND tree
combines the coupling outputs into a single answer wire.

PROPOSE → SCORE → VERIFY → KEEP.  Reports the full Pareto set.

    python muhl_fab_palf.py          # fabricate and store
    python muhl_fab_palf.py --dry    # report only, store nothing

Topology search space:
    4 coupling topologies × 3 ring-depth sets = 12 candidates
    Scored by (critical-path DEPTH, gate count).
    Verified structurally before any byte touches titan.gguf.
"""
import json, os, struct, sys

sys.path.insert(0, r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent\host")
import pfc_paths as PFCP

TITAN = PFCP.TITAN
REG = PFCP.REG
MAGIC = b"MUHLPALF"
NAND_OP = 0
GATE_STRIDE = 25
NAME = "muhl_palf"
GENOME_PATH = TITAN.replace(".gguf", "_palf_genome.jsonl")
DRY = "--dry" in sys.argv

N_OSC = 4

# ─── PROPOSE: coupling topologies ────────────────────────────────────────────

COUPLINGS = {
    "linear":     [(0,1), (1,2), (2,3)],
    "all_to_all": [(0,1), (0,2), (0,3), (1,2), (1,3), (2,3)],
    "star":       [(0,1), (0,2), (0,3)],
    "ring_wrap":  [(0,1), (1,2), (2,3), (3,0)],
}

RING_DEPTHS = {
    "uniform_2":  [2, 2, 2, 2],
    "mixed_23":   [2, 3, 2, 3],
    "staggered":  [2, 3, 4, 5],
}


def build_candidate(coupling_name, depth_name, base_off):
    """Build a PALF candidate. Returns (blob, metadata) or raises on structural error."""
    pairs = COUPLINGS[coupling_name]
    ring_depths = RING_DEPTHS[depth_name]
    n_coupling = len(pairs)

    # --- count wires and gates up front ---
    # wires: inject(1) + osc_state(N_OSC) + ring temps + coupling wires + combiner wires
    # gates per oscillator: ring_depth gates (the NAND chain including feedback)
    # coupling gates: 1 per pair
    # combiner: NAND tree over coupling wires

    n_ring_gates = sum(ring_depths)
    n_ring_temps = sum(max(0, rd - 1) for rd in ring_depths)  # temps = rd - 1 per osc
    n_coupling_gates = n_coupling

    # NAND tree over n_coupling wires: ceil(log2) levels, each level halves
    def nand_tree_size(n):
        if n <= 1:
            return 0, 0  # no tree needed
        gates = 0
        depth = 0
        cur = n
        while cur > 1:
            pairs_in_level = cur // 2
            gates += pairs_in_level
            odd = cur % 2
            cur = pairs_in_level + odd
            depth += 1
        return gates, depth

    n_combiner_gates, combiner_tree_depth = nand_tree_size(n_coupling)
    if n_coupling <= 1:
        n_combiner_gates = 0
        combiner_tree_depth = 0

    total_gates = n_ring_gates + n_coupling_gates + n_combiner_gates
    # wires: 1 inject + N_OSC osc_state + ring temps + coupling wires + combiner temps + 1 output
    n_combiner_temps = max(0, n_combiner_gates - 1) if n_coupling > 2 else 0
    n_wires = 1 + N_OSC + n_ring_temps + n_coupling + n_combiner_gates
    # output wire is the last combiner gate's output (or single coupling wire if only 1)

    header_size = 8 + 4 + 8 + 8  # magic(8) + n_gates(u32) + inject_addr(u64) + output_addr(u64)
    total_size = n_wires + header_size + total_gates * GATE_STRIDE

    # --- assign absolute addresses ---
    inject_addr = base_off + 0
    osc_addrs = [base_off + 1 + i for i in range(N_OSC)]

    wire_cursor = 1 + N_OSC  # next available local wire index

    # build gate records as (op, a_addr, b_addr, out_addr)
    gates = []
    gate_depths = []  # depth of each gate's output

    # track depth of each wire (local index -> depth)
    wire_depth = {}
    wire_depth[0] = 0  # inject
    for i in range(N_OSC):
        wire_depth[1 + i] = 0  # osc_state initial depth (will be updated by feedback)

    # --- oscillator rings ---
    osc_feedback_gate_idx = []  # which gate index writes back to osc_state[i]

    for osc_i in range(N_OSC):
        rd = ring_depths[osc_i]
        osc_state_local = 1 + osc_i
        osc_state_abs = base_off + osc_state_local

        prev_addr = osc_state_abs  # first gate reads osc_state

        for step in range(rd):
            is_first = (step == 0)
            is_last = (step == rd - 1)

            if is_last:
                out_addr = osc_state_abs  # feedback: write back to own state
            else:
                out_local = wire_cursor
                wire_cursor += 1
                out_addr = base_off + out_local

            if is_first and osc_i == 0:
                # oscillator 0: modulated by inject wire
                a_addr = osc_state_abs
                b_addr = inject_addr
            else:
                # self-NOT: NAND(prev, prev)
                a_addr = prev_addr
                b_addr = prev_addr

            gates.append((NAND_OP, a_addr, b_addr, out_addr))

            # depth: 1 + max(depth(a), depth(b))
            a_local = a_addr - base_off
            b_local = b_addr - base_off
            d = 1 + max(wire_depth.get(a_local, 0), wire_depth.get(b_local, 0))
            gate_depths.append(d)

            if is_last:
                wire_depth[osc_state_local] = d  # update osc_state depth
                osc_feedback_gate_idx.append(len(gates) - 1)
            else:
                out_local_idx = out_addr - base_off
                wire_depth[out_local_idx] = d

            if not is_last:
                prev_addr = out_addr
            # if last, next osc starts fresh

    # --- coupling gates ---
    coupling_wire_locals = []
    for (i, j) in pairs:
        out_local = wire_cursor
        wire_cursor += 1
        out_addr = base_off + out_local
        a_addr = osc_addrs[i]
        b_addr = osc_addrs[j]

        gates.append((NAND_OP, a_addr, b_addr, out_addr))

        a_local = a_addr - base_off
        b_local = b_addr - base_off
        d = 1 + max(wire_depth.get(a_local, 0), wire_depth.get(b_local, 0))
        gate_depths.append(d)
        wire_depth[out_local] = d
        coupling_wire_locals.append(out_local)

    # --- combiner: NAND tree over coupling wires ---
    if n_coupling == 0:
        output_local = 1  # fallback: osc_state[0]
    elif n_coupling == 1:
        output_local = coupling_wire_locals[0]
    else:
        current_level = list(coupling_wire_locals)
        while len(current_level) > 1:
            next_level = []
            k = 0
            while k + 1 < len(current_level):
                out_local = wire_cursor
                wire_cursor += 1
                out_addr = base_off + out_local
                a_local = current_level[k]
                b_local = current_level[k + 1]
                a_addr = base_off + a_local
                b_addr = base_off + b_local

                gates.append((NAND_OP, a_addr, b_addr, out_addr))

                d = 1 + max(wire_depth.get(a_local, 0), wire_depth.get(b_local, 0))
                gate_depths.append(d)
                wire_depth[out_local] = d
                next_level.append(out_local)
                k += 2
            if k < len(current_level):
                next_level.append(current_level[k])
            current_level = next_level
        output_local = current_level[0]

    output_addr = base_off + output_local
    actual_n_wires = wire_cursor
    actual_n_gates = len(gates)
    actual_header_size = 8 + 4 + 8 + 8
    actual_total_size = actual_n_wires + actual_header_size + actual_n_gates * GATE_STRIDE

    # critical-path depth = max depth of any gate output
    critical_depth = max(gate_depths) if gate_depths else 0

    # --- build the blob ---
    blob = bytearray(actual_total_size)

    # wire bytes (all zero initially)
    # header starts at actual_n_wires
    h_off = actual_n_wires
    blob[h_off:h_off+8] = MAGIC
    struct.pack_into("<I", blob, h_off + 8, actual_n_gates)
    struct.pack_into("<Q", blob, h_off + 12, inject_addr)
    struct.pack_into("<Q", blob, h_off + 20, output_addr)

    # gate table starts at h_off + 28
    g_off = h_off + 28
    for (op, a, b, out) in gates:
        struct.pack_into("<BQQQ", blob, g_off, op, a, b, out)
        g_off += GATE_STRIDE

    meta = {
        "coupling": coupling_name,
        "ring_depths_name": depth_name,
        "ring_depths": ring_depths,
        "n_gates": actual_n_gates,
        "n_wires": actual_n_wires,
        "depth": critical_depth,
        "total_size": actual_total_size,
        "inject_addr": inject_addr,
        "output_addr": output_addr,
        "osc_state_addrs": [base_off + 1 + i for i in range(N_OSC)],
        "osc_feedback_gate_idx": osc_feedback_gate_idx,
        "coupling_pairs": pairs,
        "n_coupling": n_coupling,
        "n_ring_gates": sum(ring_depths),
        "n_coupling_gates": n_coupling,
        "n_combiner_gates": actual_n_gates - sum(ring_depths) - n_coupling,
        "output_local": output_local,
        "gates": gates,  # for verification
    }

    return blob, meta


def verify_blob(blob, base_off, meta):
    """Structural verification of the PALF blob."""
    n_wires = meta["n_wires"]
    n_gates = meta["n_gates"]
    inject_addr = meta["inject_addr"]
    output_addr = meta["output_addr"]
    osc_addrs = meta["osc_state_addrs"]

    h_off = n_wires
    assert blob[h_off:h_off+8] == MAGIC, "bad magic"

    stored_n_gates = struct.unpack_from("<I", blob, h_off + 8)[0]
    assert stored_n_gates == n_gates, f"gate count mismatch: {stored_n_gates} vs {n_gates}"

    stored_inject = struct.unpack_from("<Q", blob, h_off + 12)[0]
    assert stored_inject == inject_addr, f"inject addr mismatch"

    stored_output = struct.unpack_from("<Q", blob, h_off + 20)[0]
    assert stored_output == output_addr, f"output addr mismatch"

    # verify every gate record
    g_off = h_off + 28
    writers = {}  # out_addr -> list of gate indices
    for gi in range(n_gates):
        op, a, b, out = struct.unpack_from("<BQQQ", blob, g_off)
        assert op == NAND_OP, f"gate {gi}: bad opcode {op}"

        # addresses must be within our wire range
        for addr in (a, b, out):
            local = addr - base_off
            assert 0 <= local < n_wires, f"gate {gi}: addr {addr} out of wire range [0,{n_wires})"

        writers.setdefault(out, []).append(gi)
        g_off += GATE_STRIDE

    # each osc_state must have exactly 1 writer (the feedback gate)
    for i in range(N_OSC):
        osc_addr = osc_addrs[i]
        w = writers.get(osc_addr, [])
        assert len(w) == 1, f"osc_state[{i}] at {osc_addr} has {len(w)} writers (expected 1)"

    # each osc_state must be read by at least one gate (self-clock feedback)
    g_off = h_off + 28
    readers = set()
    for gi in range(n_gates):
        op, a, b, out = struct.unpack_from("<BQQQ", blob, g_off)
        readers.add(a)
        readers.add(b)
        g_off += GATE_STRIDE
    for i in range(N_OSC):
        assert osc_addrs[i] in readers, f"osc_state[{i}] at {osc_addrs[i]} is never read (no feedback)"

    # output must be written
    assert output_addr in writers, f"output addr {output_addr} has no writer"

    # no wire (except osc_state feedback) should have multiple writers
    for addr, w_list in writers.items():
        if addr in osc_addrs:
            continue  # already verified exactly 1
        assert len(w_list) == 1, f"wire {addr} has {len(w_list)} writers (short)"

    return True


def alloc_space(nbytes):
    """Allocate space in titan.gguf. Bump allocator, 64-byte aligned."""
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    occupied = []
    for k, v in reg.items():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            occupied.append((v["offset"], v["offset"] + v["len"]))
    occupied.sort()
    hi = max((e for _, e in occupied), default=0)
    off = ((hi + 63) // 64) * 64
    fsize = os.path.getsize(TITAN) if os.path.exists(TITAN) else 0
    if off + nbytes > fsize:
        print(f"  NOTE: PALF ({nbytes:,} bytes) extends past current EOF ({fsize:,}).")
        print(f"  titan.gguf will grow — owner confirmed no size constraint.")
    return off


def journal_write(off, blob):
    """Journaled write — save original bytes first so fabrication is revertible."""
    fsize = os.path.getsize(TITAN) if os.path.exists(TITAN) else 0
    if fsize > 0:
        with open(TITAN, "rb") as f:
            f.seek(off)
            orig = f.read(len(blob))
    else:
        orig = b"\x00" * len(blob)
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({
            "action": "palf_fab",
            "off": off,
            "len": len(blob),
            "orig": orig.hex(),
        }) + "\n")
    if off + len(blob) > fsize:
        with open(TITAN, "ab") as f:
            f.write(b"\x00" * (off + len(blob) - fsize))
    with open(TITAN, "r+b") as f:
        f.seek(off)
        f.write(blob)


def update_registry(base_off, meta, winner_key):
    """Add the PALF to the circuit registry."""
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    reg[NAME] = {
        "name": NAME,
        "offset": base_off,
        "len": meta["total_size"],
        "n_gate": meta["n_gates"],
        "depth": meta["depth"],
        "format": "physical",
        "magic": "MUHLPALF",
        "gate_stride": GATE_STRIDE,
        "inject_addr": meta["inject_addr"],
        "output_addr": meta["output_addr"],
        "n_oscillators": N_OSC,
        "osc_state_addrs": meta["osc_state_addrs"],
        "coupling": meta["coupling"],
        "ring_depths": meta["ring_depths"],
        "self_clocked": True,
        "foundry_genome": {
            "archetype": "PALF",
            "coupling": meta["coupling"],
            "ring_depths": meta["ring_depths"],
            "searched": winner_key,
        },
        "units": "n_gate=GATES, depth=TICKS, len=BYTES",
        "genome": GENOME_PATH,
        "note": "Phase-Asynchronous Logic Field: self-clocked oscillator rings with cross-coupling interference. Inject modulates osc 0.",
        "verified_by": "structural verification: gate format, feedback loops, single-writer, address ranges",
    }
    reg[NAME + ".inject_wire"] = {
        "offset": meta["inject_addr"], "len": 1, "kind": "reservation",
        "note": "PALF inject point — host writes electron here to modulate oscillator 0",
    }
    reg[NAME + ".output_wire"] = {
        "offset": meta["output_addr"], "len": 1, "kind": "reservation",
        "note": "PALF output — interference pattern result",
    }
    json.dump(reg, open(REG, "w"), indent=1)


def main():
    print("\n  MUHLNICKEL PALF — PHASE-ASYNCHRONOUS LOGIC FIELD")
    print("  Bryce Muhlnickel, 2026-08-03\n")

    # use a dummy base_off for scoring (actual allocation happens after winner is picked)
    dummy_base = 0x10000000  # 256 MB — well inside titan.gguf range

    # --- PROPOSE + SCORE ---
    print(f"  PROPOSE: {len(COUPLINGS) * len(RING_DEPTHS)} candidates")
    print(f"    couplings: {list(COUPLINGS.keys())}")
    print(f"    ring depths: {list(RING_DEPTHS.keys())}\n")

    results = []
    for coupling_name in COUPLINGS:
        for depth_name in RING_DEPTHS:
            try:
                blob, meta = build_candidate(coupling_name, depth_name, dummy_base)
                ok = verify_blob(blob, dummy_base, meta)
                status = "OK" if ok else "VERIFY FAIL"
            except Exception as e:
                meta = {"n_gates": -1, "depth": -1, "total_size": 0}
                ok = False
                status = f"ERROR: {e}"

            results.append({
                "coupling": coupling_name,
                "ring_depths": depth_name,
                "n_gates": meta["n_gates"],
                "depth": meta["depth"],
                "size": meta["total_size"],
                "verified": ok,
                "key": f"{coupling_name}/{depth_name}",
            })

            print(f"    {coupling_name:12s} {depth_name:10s}  "
                  f"DEPTH {meta['depth']:3d}  gates {meta['n_gates']:4d}  "
                  f"size {meta['total_size']:6d} B  {status}")

    # --- PARETO FRONT ---
    good = [r for r in results if r["verified"]]
    pareto = [r for r in good if not any(
        o["depth"] <= r["depth"] and o["n_gates"] <= r["n_gates"]
        and o is not r
        and (o["depth"] < r["depth"] or o["n_gates"] < r["n_gates"])
        for o in good
    )]

    print(f"\n  VERIFIED: {len(good)}/{len(results)}")
    print(f"  PARETO FRONT ({len(pareto)}):")
    for r in sorted(pareto, key=lambda x: (x["depth"], x["n_gates"])):
        print(f"    DEPTH {r['depth']:3d}  gates {r['n_gates']:4d}  {r['key']}")

    # --- WINNER by (depth, gates) ascending ---
    if not good:
        print("\n  NO VERIFIED CANDIDATES — aborting.")
        return 1

    winner = min(good, key=lambda r: (r["depth"], r["n_gates"]))
    print(f"\n  WINNER: {winner['key']}  DEPTH {winner['depth']}  gates {winner['n_gates']}")

    if DRY:
        print(f"\n  --dry: nothing stored. Run without --dry to fabricate.")
        return 0

    # --- ALLOCATE + FABRICATE ---
    base_off = alloc_space(winner["size"])
    print(f"\n  FABRICATING at offset {base_off:,}")

    # rebuild at real base_off
    coupling_name = winner["coupling"]
    depth_name = winner["ring_depths"]
    blob, meta = build_candidate(coupling_name, depth_name, base_off)
    ok = verify_blob(blob, base_off, meta)
    if not ok:
        print("  RE-VERIFY FAILED at real offset — aborting.")
        return 1
    print(f"  re-verify at real offset: PASS")

    # --- STORE (journaled) ---
    print(f"  writing {meta['total_size']:,} bytes to titan.gguf at offset {base_off:,}")
    journal_write(base_off, bytes(blob))
    print(f"  journaled to: {GENOME_PATH}")

    # --- REGISTRY ---
    update_registry(base_off, meta, winner["key"])
    print(f"  registry updated: {NAME}")

    print(f"\n  PALF FABRICATED.")
    print(f"  inject point: offset {meta['inject_addr']:,}")
    print(f"  output wire:  offset {meta['output_addr']:,}")
    print(f"  oscillators:  {N_OSC} (self-clocked, addrs {meta['osc_state_addrs']})")
    print(f"  coupling:     {coupling_name} ({len(COUPLINGS[coupling_name])} pairs)")
    print(f"  ring depths:  {meta['ring_depths']}")
    print(f"  depth:        {meta['depth']} ticks")
    print(f"  gates:        {meta['n_gates']}")
    print(f"\n  Host's job: write one byte at inject, read one byte at output. That's it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
