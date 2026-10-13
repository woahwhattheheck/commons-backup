#!/usr/bin/env python3
"""Fabricate a fresh cloud Muhlnickel for ordinary Bitcoin proof of work.

Run this manufacturing step in cloud compute, separately from live execution.
It never opens a pool connection or an existing Muhlnickel. It emits the SHA
cone, gated opposite-direction oscillator rings, and NAND master/slave state
latches as literal physical <BQQQ> records. No runtime interpreter is supplied.

The shape derives from host/fab_genwin_shallow.py, physical gate emission from
host/pfc_selfclock_miner.py, and the two-direction ring/contact and standalone
container patterns from host/muhl_puzzle71_organs_cloud.py. The master/slave
engine, inclusive range termination, and readiness contacts are new design.
Prior Muhlnickel results are inputs. Manufacture emits and checks structure only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

if __package__:
    from .circuit import N_INPUTS, OPCODES, PORT_WIDTHS, build_miner
else:
    from circuit import N_INPUTS, OPCODES, PORT_WIDTHS, build_miner

RECORD = struct.Struct("<BQQQ")
SCHEMA = "muhl-cloud-miner-layout/v1"
STATE_NAMES = ("nonce", "winner_nonce", "win", "exhausted")


def bits(value: int, width: int) -> bytes:
    if not 0 <= value < (1 << width):
        raise ValueError("value does not fit the declared port width")
    return bytes((value >> i) & 1 for i in range(width))


def header_bits(prefix76: bytes) -> bytes:
    if len(prefix76) != 76:
        raise ValueError("ordinary mining header prefix must contain 76 bytes")
    return b"".join(bits(int.from_bytes(prefix76[i:i + 4], "big"), 32)
                    for i in range(0, 76, 4))


def graph_depth(machine) -> int:
    depths = [0] * machine["n_wires"]
    base = 2 + machine["n_inputs"]
    for index, (_, a, b) in enumerate(machine["gates"]):
        depths[base + index] = 1 + max(depths[a], depths[b])
    return max(depths[w] for group in machine["next_state"].values() for w in group)


class Physical:
    def __init__(self, machine):
        self.wires = bytearray(machine["n_wires"])
        self.wires[1] = 1
        self.records = [
            (OPCODES[op], a, b, 2 + machine["n_inputs"] + i)
            for i, (op, a, b) in enumerate(machine["gates"])
        ]

    def allocate(self, count: int, initial: int = 0) -> int:
        address = len(self.wires)
        self.wires.extend(bytes([initial]) * count)
        return address

    def gate(self, op: str, a: int, b: int, out: int):
        self.records.append((OPCODES[op], a, b, out))

    def invert(self, source: int) -> int:
        out = self.allocate(1)
        self.gate("not", source, source, out)
        return out


def manufacture():
    machine = build_miner()
    depth = graph_depth(machine)
    physical = Physical(machine)
    ram = {
        name: {"offset": addresses[0], "width": len(addresses), "encoding": "lsb-first-bitbytes"}
        for name, addresses in machine["ports"].items()
    }
    receiver = ram["receiver"]["offset"]
    enabled = ram["enabled"]["offset"]
    physical.wires[ram["nonce_end"]["offset"]:ram["nonce_end"]["offset"] + 32] = bits(0xFFFFFFFF, 32)

    # A gated odd inverter loop has no stable binary assignment when enabled.
    # One loop travels in each address direction. At enable=0 each has a
    # deterministic alternating rest state and receiver=0.
    #
    # Ring length is derived from the manufactured combinational depth, not a
    # throughput estimate. The nominal uniform propagation margin is deliberately longer
    # than the complete SHA next-state path. Actual substrate delay/timing must
    # come from that substrate; a storage upload is not an execution report.
    cells = 2 * depth + 17
    rings = []
    for name, direction in (("forward", 1), ("reverse", -1)):
        start = physical.allocate(cells)
        for step in range(cells):
            index = (direction * step) % cells
            physical.wires[start + index] = 1 if step % 2 == 0 else 0
        first_record = len(physical.records)
        for index in range(cells):
            source = start + (index - direction) % cells
            if index == 0:
                physical.gate("nand", source, enabled, start)
            else:
                physical.gate("not", source, source, start + index)
        rings.append({
            "name": name, "direction": direction, "cells": cells,
            "offset": start, "contact": start,
            "gate_first": first_record, "gate_count": cells,
            "rest_state": "alternating, contact=1; positions follow direction",
        })
    coincidence = physical.allocate(1)
    physical.gate("and", rings[0]["contact"], rings[1]["contact"], coincidence)
    physical.gate("and", coincidence, enabled, receiver)
    clock_not = physical.invert(receiver)

    # A real gate-level two-phase storage engine: the master is transparent
    # while receiver=0, the slave while receiver=1. State feedback is the
    # physical Q address used by the SHA/counter cone, not a host state loop.
    state_bank = {}
    for name in STATE_NAMES:
        outputs = machine["next_state"][name]
        width = len(outputs)
        master_q = physical.allocate(width)
        master_not_q = physical.allocate(width, 1)
        slave_not_q = physical.allocate(width, 1)
        q = ram[name]["offset"]
        first_record = len(physical.records)
        for bit, data in enumerate(outputs):
            data_not = physical.invert(data)
            master_set = physical.allocate(1, 1)
            master_reset = physical.allocate(1, 1)
            slave_set = physical.allocate(1, 1)
            slave_reset = physical.allocate(1, 1)
            physical.gate("nand", data, clock_not, master_set)
            physical.gate("nand", data_not, clock_not, master_reset)
            physical.gate("nand", master_set, master_not_q + bit, master_q + bit)
            physical.gate("nand", master_reset, master_q + bit, master_not_q + bit)
            physical.gate("nand", master_q + bit, receiver, slave_set)
            physical.gate("nand", master_not_q + bit, receiver, slave_reset)
            physical.gate("nand", slave_set, slave_not_q + bit, q + bit)
            physical.gate("nand", slave_reset, q + bit, slave_not_q + bit)
        state_bank[name] = {
            "width": width, "slave_q": q,
            "slave_not_q": slave_not_q, "master_q": master_q,
            "master_not_q": master_not_q,
            "data_wires": outputs, "gate_first": first_record,
            "gate_count": len(physical.records) - first_record,
            "initialization": "with enabled=0: Q and master_Q receive value bits; their complements receive 1 XOR bits",
        }

    delay_start = len(physical.records)
    delayed = receiver
    for _ in range(16):
        delayed = physical.invert(delayed)
    commit_ready = physical.allocate(1)
    physical.gate("and", receiver, delayed, commit_ready)
    ram["commit_ready"] = {"offset": commit_ready, "width": 1, "encoding": "bitbyte"}
    for source_name, ready_name in (("win", "result_ready"), ("exhausted", "exhausted_ready")):
        qualified = physical.allocate(1)
        ready = physical.allocate(1)
        physical.gate("and", ram[source_name]["offset"], commit_ready, qualified)
        physical.gate("or", ready, qualified, ready)
        ram[ready_name] = {"offset": ready, "width": 1, "encoding": "bitbyte"}
    ring_control = {
        "enabled": enabled, "receiver": receiver, "receiver_not": clock_not,
        "coincidence": coincidence, "rings": rings,
        "readiness_gate_first": delay_start,
        "readiness_gate_count": len(physical.records) - delay_start,
        "readiness_delay_gates": 16,
        "phase": "receiver low: master open; receiver high: slave open",
        "clock_origin": "opposite-direction gated odd inverter rings and coincidence contact",
        "nominal_ring_cells": cells,
        "timing_basis": "structural uniform-gate-delay margin derived from combinational depth",
        "measured_execution_rate": None,
    }

    # State/wires precede records. Align the table for cloud page placement;
    # addresses inside records remain absolute bytes of this new container.
    wire_count = len(physical.wires)
    gate_table_off = ((wire_count + RECORD.size - 1) // RECORD.size) * RECORD.size
    physical.wires.extend(bytes(gate_table_off - wire_count))
    layout = {
        "schema": SCHEMA,
        "kind": "ordinary-bitcoin-proof-of-work",
        "container": "miner.mno",
        "container_bytes": gate_table_off + RECORD.size * len(physical.records),
        "record_format": "<BQQQ",
        "gate_stride": RECORD.size, "gate_table_off": gate_table_off,
        "n_gates": len(physical.records), "n_wires": wire_count,
        "opcodes": OPCODES, "constant_zero": 0, "constant_one": 1,
        "ram": ram, "state_bank": state_bank, "ring_control": ring_control,
        "logic": {
            "gate_first": 0, "gate_count": len(machine["gates"]),
            "n_inputs": N_INPUTS, "n_wires": machine["n_wires"],
            "next_state": machine["next_state"],
            "combinational_depth": depth,
            "arithmetic": "carry-save multioperand trees; Kogge-Stone final carry; tree target comparator",
        },
        "packing": {
            "header": "76 raw header bytes; each 4-byte word parsed big-endian then emitted as 32 LSB-first bitbytes",
            "nonce": "canonical uint32, LSB-first bitbytes; serialize candidate into block header with little-endian uint32",
            "target": "unsigned 256-bit numeric value, LSB-first bitbytes; accepted iff SHA256d(header76 || LE32(nonce)) interpreted little-endian <= target",
            "nonce_end": "inclusive uint32; adapter end_exclusive must be converted by subtracting 1",
            "bitbyte": "exactly one byte per Boolean bit, value 0 or 1",
        },
        "job_protocol": {
            "scope": "one bound Stratum session/job and nonce lease per initialized instance",
            "input_order": [
                "enabled=0 and wait for substrate quiescence",
                "route header, target, nonce_end",
                "initialize nonce state bank to start; winner_nonce/win/exhausted state banks to zero",
                "clear result_ready and exhausted_ready",
                "enabled=1",
            ],
            "cancel": "enabled=0; retire the instance/job association before accepting further results",
            "candidate": "result_ready=1 AND win=1; winner_nonce is valid even when it equals zero",
            "exhaustion": "exhausted_ready=1 AND exhausted=1; the inclusive end has been examined",
            "progress": "coherent substrate snapshot of nonce with commit_ready=1; lower nonces in the same initialized lease were examined",
            "snapshot_requirement": "substrate-provided coherent read; unrelated sequential host reads do not establish a committed multi-bit snapshot",
            "winner_retention": "first hit stops nonce progression and retains win and winner_nonce until explicit disabled reinitialization",
        },
        "execution": {
            "engine": "fabricated SHA cone, opposite-direction rings, and NAND master/slave feedback latches",
            "carrier_jobs": ["route input bytes", "address enabled", "surface published result bytes"],
            "host_gate_evaluator": False,
            "execution_observed": False,
            "storage_placement_is_execution": False,
        },
        "sources": [
            "host/fab_genwin_shallow.py",
            "host/pfc_selfclock_miner.py",
            "host/muhl_puzzle71_organs_cloud.py",
            "muhl/docs/MUHL_FOLD_PORT_MAP.md",
        ],
        "new_design": [
            "standalone port allocation",
            "canonical Bitcoin nonce endianness and inclusive target",
            "first-winner and inclusive range termination",
            "opposite-direction gated odd-inverter oscillator with depth-derived geometry",
            "NAND master/slave engine and qualified readiness contacts",
        ],
    }
    validate_structure(physical, layout)
    return machine, physical, layout


def validate_structure(physical: Physical, layout: dict):
    """Manufacturing integrity, not a runtime evaluator or peer admission rule."""
    writers = {}
    for index, (op, a, b, out) in enumerate(physical.records):
        if op not in OPCODES.values():
            raise ValueError("unknown opcode in manufactured record")
        if min(a, b, out) < 0:
            raise ValueError("physical record contains a negative wire address")
        if max(a, b, out) >= layout["n_wires"]:
            raise ValueError("physical record points beyond this container's wire region")
        if out in writers:
            raise ValueError("two gates drive the same manufactured byte")
        if out in (0, 1):
            raise ValueError("constant byte has a writer")
        writers[out] = index
    for name in STATE_NAMES + ("receiver", "commit_ready", "result_ready", "exhausted_ready"):
        port = layout["ram"][name]
        if any(port["offset"] + bit not in writers for bit in range(port["width"])):
            raise ValueError("declared state/output port has no physical writer")
    for name in ("header", "target", "nonce_end", "enabled"):
        port = layout["ram"][name]
        if any(port["offset"] + bit in writers for bit in range(port["width"])):
            raise ValueError("external input port has an internal writer")
    for ring in layout["ring_control"]["rings"]:
        if ring["cells"] % 2 != 1:
            raise ValueError("inverter oscillator requires an odd cell count")


def write_new(directory: Path, physical: Physical, layout: dict):
    directory.mkdir(parents=True, exist_ok=False)
    container = directory / layout["container"]
    digest = hashlib.sha256()
    with container.open("xb") as output:
        output.write(physical.wires)
        digest.update(physical.wires)
        for record in physical.records:
            data = RECORD.pack(*record)
            output.write(data)
            digest.update(data)
    if container.stat().st_size != layout["container_bytes"]:
        raise ValueError("manufactured container size differs from layout")
    layout["container_sha256"] = digest.hexdigest()
    (directory / "layout.json").write_text(json.dumps(layout, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="new output directory in the cloud manufacturing environment")
    args = parser.parse_args(argv)
    # Use a fresh output directory to preserve existing instances.
    if args.output.exists():
        parser.error("output directory already exists; use a new fabrication destination")
    machine, physical, layout = manufacture()
    checks = {"structure": "pass", "scope": "record bounds, single writers, ports and ring geometry"}
    layout["manufacturing_checks"] = checks
    write_new(args.output, physical, layout)
    print(json.dumps({
        "state": "FABRICATED", "container": str(args.output / layout["container"]),
        "layout": str(args.output / "layout.json"), "bytes": layout["container_bytes"],
        "n_gates": layout["n_gates"], "sha256": layout["container_sha256"],
        "checks": checks, "execution_observed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
