#!/usr/bin/env python3
"""Fabricate organ 13: muhl_petr (MUHLPETR), a Petri/CRN field.

PLUMB 2/3 construction, preserved exactly:

  64 places x 4-bit token counts
  32 transitions, each with 3 input arcs and 2 output arcs
  enabled: 3 OR4 reductions (9 gates) + AND3 (2 gates) = 11
  consume: 3 x 4-bit subtract (20 gates each) = 60
  produce: 2 x 4-bit add (20 gates each) = 40
  32 x 111 = 3,552 gates, declared depth 14

Each transition owns a disjoint pair of places and encodes the chemical
reaction 2A + B -> 2B.  The three input arcs are A,A,B and the two output
arcs are B,B.  Arc arithmetic is conditional on enabled.  Aggregate roots
write the next A/B marking back onto those same marking addresses; the
remaining arc results are structural witnesses in scratch.

Header: 8-byte magic, then LE n_gate, n_wires, n_in, n_out, depth.
Records: <BQQQ>, 25 bytes. OPS NAND AND OR XOR NOT = 0 1 2 3 4.

Offline one-and-done manufacture only.  Writes a standalone public excerpt
and deterministic registry sidecar.  Does not open or write titan.gguf and
does not evaluate the organ.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys


NAME = "muhl_petr"
MAGIC = b"MUHLPETR"
GATE_STRIDE = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

N_PLACES = 64
PLACE_BITS = 4
N_TRANSITIONS = 32
GATES_PER_TRANSITION = 111
N_GATE = N_TRANSITIONS * GATES_PER_TRANSITION
N_IN = N_PLACES * PLACE_BITS
N_OUT = N_IN
DEPTH = 14

# MHA physical layout: const0, const1, state bits, then one wire per gate.
W_CONST0 = 0
W_CONST1 = 1
W_MARKING0 = 2
N_WIRES = 2 + N_IN + N_GATE

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
MNO_PATH = os.path.join(EXCERPT_DIR, "muhl_petr.mno")
REG_PATH = os.path.join(EXCERPT_DIR, "petr_circuits.json")


def marking_wire(place: int, bit: int) -> int:
    if not (0 <= place < N_PLACES and 0 <= bit < PLACE_BITS):
        raise ValueError("marking coordinate")
    return W_MARKING0 + place * PLACE_BITS + bit


def transition_places(transition: int) -> tuple[int, int]:
    """Disjoint reaction pair for transition t: 2A + B -> 2B."""
    if not 0 <= transition < N_TRANSITIONS:
        raise ValueError("transition")
    return 2 * transition, 2 * transition + 1


def build_gates():
    """Return physical-independent records, next marking roots, and arc map."""
    records: list[tuple[int, int, int, int]] = []
    marking_out: list[int | None] = [None] * N_OUT
    transitions = []
    next_wire = W_MARKING0 + N_IN

    def emit(op: int, a: int, b: int) -> int:
        nonlocal next_wire
        out = next_wire
        next_wire += 1
        records.append((op, a, b, out))
        return out

    def or4(bits: list[int]) -> int:
        if len(bits) != 4:
            raise ValueError("OR4 needs four wires")
        acc = emit(OP_OR, bits[0], bits[1])
        acc = emit(OP_OR, acc, bits[2])
        return emit(OP_OR, acc, bits[3])

    def add4(a_bits: list[int], b_bits: list[int], carry_in: int):
        """Four ripple full adders, five gates per bit, exactly 20 gates."""
        if len(a_bits) != 4 or len(b_bits) != 4:
            raise ValueError("ADD4 width")
        sums = []
        carry = carry_in
        for bit, (a, b) in enumerate(zip(a_bits, b_bits)):
            propagate = emit(OP_XOR, a, b)
            generate = emit(OP_AND, a, b)
            carry_prop = emit(OP_AND, propagate, carry)
            if bit < 3:
                next_carry = emit(OP_OR, generate, carry_prop)
                sums.append(emit(OP_XOR, propagate, carry))
                carry = next_carry
            else:
                # Four-bit token arithmetic is modulo 16, so the terminal
                # carry is discarded.  Its fifth gate becomes a zero-OR
                # identity on the MSB, keeping the exact 20-gate block and
                # PLUMB's physical depth 14 without changing the value.
                msb_sum = emit(OP_XOR, propagate, carry)
                buffered_msb = emit(OP_OR, msb_sum, W_CONST0)
                sums.append(buffered_msb)
                carry = buffered_msb
        return sums, carry

    for transition in range(N_TRANSITIONS):
        start = len(records)
        place_a, place_b = transition_places(transition)
        a = [marking_wire(place_a, bit) for bit in range(PLACE_BITS)]
        b = [marking_wire(place_b, bit) for bit in range(PLACE_BITS)]

        # Three input arcs A,A,B.  The second A arc checks A >= 2 by
        # reducing the upper three token bits plus const0 through OR4.
        a_nonzero = or4(a)
        a_second_token = or4([a[1], a[2], a[3], W_CONST0])
        b_nonzero = or4(b)
        enabled_ab = emit(OP_AND, a_nonzero, a_second_token)
        enabled = emit(OP_AND, enabled_ab, b_nonzero)

        # Emit all per-arc witnesses before the marking roots.  This makes
        # self-clock remaps terminal writes: no gate reads a marking address
        # after its next-tick value has been written.
        a_arc, _ = add4(a, [enabled] * 4, W_CONST0)
        b_arc, _ = add4(b, [enabled] * 4, W_CONST0)
        b_produce_arc, _ = add4(
            b, [enabled, W_CONST0, W_CONST0, W_CONST0], W_CONST0
        )

        # Aggregate roots compile the net effects in parallel: A - 2 and
        # B - 1 + 2 = B + 1.  No host/runtime sequence is introduced.
        a_net, _ = add4(a, [W_CONST0, enabled, enabled, enabled], W_CONST0)
        b_net, _ = add4(
            b, [enabled, W_CONST0, W_CONST0, W_CONST0], W_CONST0
        )

        for bit in range(PLACE_BITS):
            marking_out[place_a * PLACE_BITS + bit] = a_net[bit]
            marking_out[place_b * PLACE_BITS + bit] = b_net[bit]

        if len(records) - start != GATES_PER_TRANSITION:
            raise RuntimeError("transition %d gate count" % transition)
        transitions.append(
            {
                "transition": transition,
                "input_places": [place_a, place_a, place_b],
                "output_places": [place_b, place_b],
                "reaction": "2P%d + P%d -> 2P%d" % (place_a, place_b, place_b),
                "enabled_wire": enabled,
                "aggregate_output_wires": a_net + b_net,
                "scratch_witness_wires": a_arc + b_arc + b_produce_arc,
            }
        )

    if len(records) != N_GATE:
        raise RuntimeError("gate count %d != %d" % (len(records), N_GATE))
    if next_wire != N_WIRES:
        raise RuntimeError("wire cursor %d != %d" % (next_wire, N_WIRES))
    if any(w is None for w in marking_out):
        raise RuntimeError("missing next marking wire")
    return records, [int(w) for w in marking_out], transitions


def hdr_size() -> int:
    return 28 + N_OUT * 8


def wa(base_off: int, wire: int) -> int:
    return base_off + hdr_size() + wire


def fabricate(base_off: int = 0):
    records, marking_out, transitions = build_gates()
    remap = {
        marking_out[index]: wa(base_off, marking_wire(index // PLACE_BITS, index % PLACE_BITS))
        for index in range(N_OUT)
    }
    if len(remap) != N_OUT or len(set(remap.values())) != N_OUT:
        raise RuntimeError("self-clock marking roots are not unique")

    hsz = hdr_size()
    gate_start = hsz + N_WIRES
    total = gate_start + N_GATE * GATE_STRIDE
    blob = bytearray(total)
    blob[0:8] = MAGIC
    struct.pack_into("<IIIII", blob, 8, N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    output_addrs = [remap[marking_out[index]] for index in range(N_OUT)]
    for index, address in enumerate(output_addrs):
        struct.pack_into("<Q", blob, 28 + index * 8, address)
    blob[hsz + W_CONST0] = 0
    blob[hsz + W_CONST1] = 1

    stored = []
    off = gate_start
    for op, a, b, out_wire in records:
        a_addr = wa(base_off, a)
        b_addr = wa(base_off, b)
        out_addr = remap.get(out_wire, wa(base_off, out_wire))
        struct.pack_into("<BQQQ", blob, off, op, a_addr, b_addr, out_addr)
        stored.append((op, a_addr, b_addr, out_addr))
        off += GATE_STRIDE

    input_addrs = [
        wa(base_off, marking_wire(place, bit))
        for place in range(N_PLACES)
        for bit in range(PLACE_BITS)
    ]
    meta = {
        "name": NAME,
        "magic": MAGIC.decode(),
        "n_gate": N_GATE,
        "n_wires": N_WIRES,
        "n_in": N_IN,
        "n_out": N_OUT,
        "depth": DEPTH,
        "len": total,
        "base_off": base_off,
        "input_addrs": input_addrs,
        "output_addrs": output_addrs,
        "transitions": transitions,
        "sha256": hashlib.sha256(blob).hexdigest(),
    }
    return bytes(blob), meta, stored


def verify_physical(blob, meta, stored):
    """Structural receipt only; never evaluates or schedules the organ."""
    assert blob[:8] == MAGIC
    header = struct.unpack_from("<IIIII", blob, 8)
    assert header == (N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    assert len(blob) == meta["len"]
    assert len(stored) == N_GATE
    assert hdr_size() + N_WIRES + N_GATE * GATE_STRIDE == len(blob)

    writers = {}
    off = hdr_size() + N_WIRES
    for index, expected in enumerate(stored):
        actual = struct.unpack_from("<BQQQ", blob, off)
        assert actual == expected, "gate %d record" % index
        op, _a, _b, out = actual
        assert op in (OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT)
        assert out not in writers, "out reused by gates %d and %d" % (writers[out], index)
        writers[out] = index
        off += GATE_STRIDE
    assert len(writers) == N_GATE

    # The header's declared depth is a physical bound, not just a label.
    input_addresses = {
        wa(meta["base_off"], wire) for wire in range(W_MARKING0 + N_IN)
    }
    marking_addresses = set(meta["input_addrs"])
    valid_addresses = {
        wa(meta["base_off"], wire) for wire in range(N_WIRES)
    }
    wire_depth = {address: 0 for address in input_addresses}
    max_gate_depth = 0
    written_marking = set()
    for _op, a, b, out in stored:
        assert a in wire_depth and b in wire_depth
        assert a not in written_marking and b not in written_marking
        assert a in valid_addresses and b in valid_addresses and out in valid_addresses
        gate_depth = max(wire_depth[a], wire_depth[b]) + 1
        max_gate_depth = max(max_gate_depth, gate_depth)
        # Self-clock roots overwrite marking inputs but are terminal within
        # this settle; preserving input depth avoids treating the next tick
        # as a same-tick dependency.
        if out not in input_addresses:
            wire_depth[out] = gate_depth
        elif out in marking_addresses:
            written_marking.add(out)
    assert written_marking == marking_addresses
    assert max_gate_depth == DEPTH

    header_outputs = [struct.unpack_from("<Q", blob, 28 + i * 8)[0] for i in range(N_OUT)]
    assert header_outputs == meta["output_addrs"]
    assert meta["output_addrs"] == meta["input_addrs"]

    for transition in range(N_TRANSITIONS):
        chunk = stored[
            transition * GATES_PER_TRANSITION : (transition + 1) * GATES_PER_TRANSITION
        ]
        ops = [record[0] for record in chunk]
        assert len(chunk) == 111
        assert ops.count(OP_OR) == 29
        assert ops.count(OP_AND) == 42
        assert ops.count(OP_XOR) == 40
        assert ops.count(OP_NAND) == 0 and ops.count(OP_NOT) == 0
        place_a, place_b = transition_places(transition)
        row = meta["transitions"][transition]
        assert row["input_places"] == [place_a, place_a, place_b]
        assert row["output_places"] == [place_b, place_b]

    assert blob[hdr_size() + W_CONST0] == 0
    assert blob[hdr_size() + W_CONST1] == 1
    return True


def write_files(blob, meta):
    os.makedirs(EXCERPT_DIR, exist_ok=True)
    with open(MNO_PATH, "wb") as handle:
        handle.write(blob)
    sidecar = {
        NAME: {
            "name": NAME,
            "magic": meta["magic"],
            "n_gate": meta["n_gate"],
            "n_wires": meta["n_wires"],
            "n_in": meta["n_in"],
            "n_out": meta["n_out"],
            "depth": meta["depth"],
            "len": meta["len"],
            "offset": 0,
            "container": "muhl_petr.mno",
            "format": "physical",
            "gate_stride": GATE_STRIDE,
            "places": N_PLACES,
            "place_bits": PLACE_BITS,
            "transition_count": N_TRANSITIONS,
            "arcs_per_transition": {"input": 3, "output": 2},
            "reaction_family": "2A + B -> 2B over 32 disjoint place pairs",
            "input_addrs": meta["input_addrs"],
            "output_addrs": meta["output_addrs"],
            "transitions": [
                {
                    "transition": row["transition"],
                    "input_places": row["input_places"],
                    "output_places": row["output_places"],
                    "reaction": row["reaction"],
                }
                for row in meta["transitions"]
            ],
            "sha256": meta["sha256"],
            "clock": "marking out IS marking in",
            "requested_offset_band": "OWNER_LOCAL_ALLOCATOR; not chosen in public tree",
            "titan": "NOT_WRITTEN",
        }
    }
    with open(REG_PATH, "w", encoding="utf-8") as handle:
        json.dump(sidecar, handle, indent=2)
        handle.write("\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    dry = "--dry" in argv
    blob, meta, stored = fabricate(0)
    verify_physical(blob, meta, stored)
    print("MUHLPETR structural receipt")
    print(
        "  n_gate=%d n_wires=%d n_in=%d n_out=%d depth=%d"
        % (meta["n_gate"], meta["n_wires"], meta["n_in"], meta["n_out"], meta["depth"])
    )
    print("  len=%d sha256=%s" % (meta["len"], meta["sha256"]))
    print("  transitions=32 places=64 reaction=2A+B->2B")
    print("  self-clock: output_addrs == input_addrs (%d marking bits)" % N_OUT)
    print("  titan: NOT_WRITTEN; offset band: OWNER_LOCAL_ALLOCATOR")
    if dry:
        print("  --dry: no files written")
        return 0
    write_files(blob, meta)
    print("  wrote %s" % MNO_PATH)
    print("  wrote %s" % REG_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
