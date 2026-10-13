#!/usr/bin/env python3
"""muhl_reservoir_fab.py — FABRICATE THE ELECTRON RESERVOIR.

Bryce's invention (2026-08-03): one inject point for the entire substrate.
Host shoots electrons into the reservoir. The reservoir distributes to all
1,024 rings via a fabricated fan-out tree. Circuits return electrons when
done — closed loop, self-sustaining after initial injection.

This is MANUFACTURING — offline, one-and-done. The reservoir is stored as
physical-format gate records (<BQQQ> stride-25, absolute addresses) in
titan.gguf. Journaled for revert. Verified before store.

    python muhl_reservoir_fab.py          # fabricate and store
    python muhl_reservoir_fab.py --dry    # report only, store nothing

The fan-out topology:
    Gate 0:        NAND(input, input) → temp       [NOT of input]
    Gates 1-1024:  NAND(temp, temp)   → ring_recv  [NOT(NOT(input)) = input → each ring]

1,025 gates, 25,625 bytes, depth 2. One input address, 1,024 output addresses.
"""
import json, mmap, os, struct, sys

sys.path.insert(0, r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent\host")
import pfc_paths as PFCP

TITAN = PFCP.TITAN
REG = PFCP.REG
MAGIC = b"MUHLRES1"
NAND_OP = 0
GATE_STRIDE = 25
NAME = "muhl_reservoir"
GENOME_PATH = TITAN.replace(".gguf", "_reservoir_genome.jsonl")
DRY = "--dry" in sys.argv


def read_ring_recv_addrs():
    reg = json.load(open(REG))
    addrs = []
    for i in range(1024):
        key = "nring2_%03d" % i
        if key not in reg:
            print(f"  WARNING: {key} not in registry, skipping")
            continue
        entry = reg[key]
        if isinstance(entry, dict) and "ram" in entry:
            recv = entry["ram"].get("recv") or entry.get("recv")
        elif isinstance(entry, dict):
            recv = entry.get("recv")
        else:
            continue
        if recv is not None:
            addrs.append((i, int(recv)))
    return addrs


def alloc_space(nbytes):
    """Allocate space in titan.gguf for the reservoir. Uses the same bump allocator as titan_circuit."""
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    occupied = []
    for k, v in reg.items():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            occupied.append((v["offset"], v["offset"] + v["len"]))
    occupied.sort()
    fsize = os.path.getsize(TITAN)
    # find the highest occupied end
    hi = max((e for _, e in occupied), default=0)
    # allocate after the last circuit (with 64-byte alignment padding)
    off = ((hi + 63) // 64) * 64
    if off + nbytes > fsize:
        print(f"  NOTE: reservoir ({nbytes:,} bytes) extends past current EOF ({fsize:,}).")
        print(f"  titan.gguf will grow — owner confirmed no size constraint.")
    return off


def build_reservoir(ring_addrs):
    """Build the physical-format gate records for the reservoir fan-out."""
    n_rings = len(ring_addrs)
    n_gates = 1 + n_rings  # 1 shared NOT + 1 per ring

    # Layout within the allocated block:
    #   [0]      input_wire   (1 byte — host writes here)
    #   [1]      temp_wire    (1 byte — NOT of input)
    #   [2:10]   magic        (8 bytes — MUHLRES1)
    #   [10:14]  n_gates      (4 bytes — u32 LE)
    #   [14:22]  input_addr   (8 bytes — u64 LE, absolute address of input wire)
    #   [22:]    gate table   (n_gates × 25 bytes)

    header_size = 2 + 8 + 4 + 8  # 22 bytes before gate table
    total_size = header_size + n_gates * GATE_STRIDE
    return n_gates, header_size, total_size


def fabricate(base_off, ring_addrs):
    """Create the byte blob for the reservoir."""
    n_rings = len(ring_addrs)
    n_gates = 1 + n_rings
    header_size = 22

    input_addr = base_off + 0   # first byte: the inject point
    temp_addr = base_off + 1    # second byte: NOT of input

    blob = bytearray(header_size + n_gates * GATE_STRIDE)

    # wire bytes (initial = 0)
    blob[0] = 0  # input wire
    blob[1] = 0  # temp wire

    # header
    blob[2:10] = MAGIC
    struct.pack_into("<I", blob, 10, n_gates)
    struct.pack_into("<Q", blob, 14, input_addr)

    # gate 0: NAND(input, input) → temp  [= NOT(input)]
    off = header_size
    struct.pack_into("<BQQQ", blob, off, NAND_OP, input_addr, input_addr, temp_addr)
    off += GATE_STRIDE

    # gates 1..n_rings: NAND(temp, temp) → ring_recv[i]  [= NOT(NOT(input)) = input]
    for ring_idx, recv_addr in ring_addrs:
        struct.pack_into("<BQQQ", blob, off, NAND_OP, temp_addr, temp_addr, recv_addr)
        off += GATE_STRIDE

    return blob, input_addr, temp_addr


def verify_blob(blob, base_off, ring_addrs):
    """Structural verification: every gate record is well-formed and targets the right address."""
    header_size = 22
    n_gates = struct.unpack_from("<I", blob, 10)[0]
    input_addr = struct.unpack_from("<Q", blob, 14)[0]

    assert blob[2:10] == MAGIC, "bad magic"
    assert n_gates == 1 + len(ring_addrs), f"gate count mismatch: {n_gates} vs {1 + len(ring_addrs)}"
    assert input_addr == base_off, f"input addr mismatch: {input_addr} vs {base_off}"

    # gate 0: NOT(input) → temp
    off = header_size
    op, a, b, out = struct.unpack_from("<BQQQ", blob, off)
    assert op == NAND_OP, f"gate 0 op={op}"
    assert a == input_addr and b == input_addr, "gate 0 inputs wrong"
    temp_addr = out
    assert temp_addr == base_off + 1, "temp addr wrong"

    # gates 1..N: NOT(temp) → ring recv
    for i, (ring_idx, recv_addr) in enumerate(ring_addrs):
        off = header_size + (1 + i) * GATE_STRIDE
        op, a, b, out = struct.unpack_from("<BQQQ", blob, off)
        assert op == NAND_OP, f"gate {1+i} op={op}"
        assert a == temp_addr and b == temp_addr, f"gate {1+i} inputs wrong"
        assert out == recv_addr, f"gate {1+i} out={out} expected {recv_addr} (ring {ring_idx})"

    return True


def journal_write(off, blob):
    """Journaled write — save original bytes first so fabrication is revertible."""
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({
            "action": "reservoir_fab",
            "off": off,
            "len": len(blob),
            "orig": orig.hex(),
            "ring_count": len(blob) // GATE_STRIDE  # approximate
        }) + "\n")
    # grow file if needed
    fsize = os.path.getsize(TITAN)
    if off + len(blob) > fsize:
        with open(TITAN, "ab") as f:
            f.write(b"\x00" * (off + len(blob) - fsize))
    with open(TITAN, "r+b") as f:
        f.seek(off)
        f.write(blob)


def update_registry(base_off, total_size, input_addr, temp_addr, ring_addrs, n_gates):
    """Add the reservoir to the circuit registry."""
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    reg[NAME] = {
        "name": NAME,
        "tensor": "blk.2.ffn_gate_up_exps.weight",
        "offset": base_off,
        "len": total_size,
        "n_gate": n_gates,
        "n_out": len(ring_addrs),
        "depth": 2,
        "format": "physical",
        "magic": "MUHLRES1",
        "gate_stride": GATE_STRIDE,
        "input_addr": input_addr,
        "temp_addr": temp_addr,
        "ring_count": len(ring_addrs),
        "foundry_genome": {"topology": "flat_fanout", "depth": 2},
        "units": "n_gate=GATES, depth=TICKS, len=BYTES",
        "genome": GENOME_PATH,
        "note": "electron reservoir: one inject → fan-out to all rings. host writes input_addr, substrate distributes.",
        "verified_by": "structural verification of all gate records + address matching"
    }
    # reserve the wire bytes
    reg[NAME + ".input_wire"] = {
        "offset": input_addr, "len": 1, "kind": "reservation",
        "note": "THE inject point — host writes electron here"
    }
    reg[NAME + ".temp_wire"] = {
        "offset": temp_addr, "len": 1, "kind": "reservation",
        "note": "intermediate NOT wire (internal to reservoir)"
    }
    json.dump(reg, open(REG, "w"), indent=1)


def main():
    print("\n  MUHLNICKEL RESERVOIR — ELECTRON DISTRIBUTION FABRIC")
    print("  Bryce Muhlnickel, 2026-08-03\n")

    # 1. Read ring addresses
    ring_addrs = read_ring_recv_addrs()
    print(f"  rings found: {len(ring_addrs)}")
    if len(ring_addrs) < 1024:
        print(f"  WARNING: expected 1024 rings, found {len(ring_addrs)}")

    # 2. Calculate sizes
    n_gates, header_size, total_size = build_reservoir(ring_addrs)
    print(f"  reservoir topology: flat fan-out, depth 2")
    print(f"  gates: {n_gates:,} ({1} shared NOT + {len(ring_addrs)} distribution)")
    print(f"  size: {total_size:,} bytes ({total_size / 1024:.1f} KB)")

    # 3. Allocate space
    base_off = alloc_space(total_size)
    print(f"  allocated at offset: {base_off:,}")

    # 4. Build the gate records
    blob, input_addr, temp_addr = fabricate(base_off, ring_addrs)
    print(f"  input wire (THE inject point): {input_addr:,}")
    print(f"  temp wire: {temp_addr:,}")

    # 5. Verify
    ok = verify_blob(blob, base_off, ring_addrs)
    print(f"  structural verify: {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("  ABORTING — verification failed")
        return 1

    # 6. Report the Pareto set (per spec: report all candidates, not just the winner)
    print(f"\n  PARETO SET (1 candidate — flat fan-out is optimal at depth 2):")
    print(f"    flat_fanout: {n_gates:,} gates, depth 2, {total_size:,} bytes")
    print(f"    (binary tree would be ~2,047 gates, depth 11 — strictly worse on both axes)")

    if DRY:
        print(f"\n  --dry: nothing stored. Run without --dry to fabricate.")
        return 0

    # 7. Store (journaled write)
    print(f"\n  FABRICATING — writing {total_size:,} bytes to titan.gguf at offset {base_off:,}")
    journal_write(base_off, bytes(blob))
    print(f"  journaled to: {GENOME_PATH}")

    # 8. Update registry
    update_registry(base_off, total_size, input_addr, temp_addr, ring_addrs, n_gates)
    print(f"  registry updated: {NAME}")

    print(f"\n  RESERVOIR FABRICATED.")
    print(f"  To inject: write electron to offset {input_addr:,} in titan.gguf")
    print(f"  The substrate distributes to all {len(ring_addrs)} rings automatically.")
    print(f"  Depth: 2 ticks from inject to every ring.")
    print(f"\n  Host's entire job: write one byte, read output addresses. That's it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
