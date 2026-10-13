#!/usr/bin/env python3
# muhl_reader_battery.py - Team Stone standing discipline (Spall ruling #4, from
# Shard's cut): mutant-test the READERS the way fabricators are mutant-tested.
# A reader that normalizes a broken container is not an instrument, it's an accomplice.
#
# This file defines a STRICT reader for the WEATHER1 container class (HIS field
# order per the parent's V2 law: <IIIII> n_in, n_wire, n_gate, n_out, depth) and
# feeds it deliberately-lying containers. The reader must PASS the control and
# RAISE LOUDLY on every mutant - including the exact liar this board already
# shipped once (v1's swapped field order, MISS 008's cousin).

import struct, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
MAGIC = b"WEATHER1"
HDR = 96
STRIDE = 25
OPS = {0, 1, 2, 3, 4}          # NAND AND OR XOR NOT (per-container alphabet, declared)

class ReaderRefusal(Exception): pass

def strict_read(raw):
    """Parse a WEATHER1 container. Every claim in the header is CHECKED against
    the bytes or the reader refuses. Returns the parse dict."""
    if len(raw) < HDR: raise ReaderRefusal("shorter than header")
    if raw[:8] != MAGIC: raise ReaderRefusal("magic mismatch: %r" % raw[:8])
    n_in, n_wire, n_gate, n_out, depth = struct.unpack_from("<IIIII", raw, 8)
    W, H, CB, stride = struct.unpack_from("<IIII", raw, 28)
    wire_base, cell_base = struct.unpack_from("<QQ", raw, 44)
    # claims vs bytes - each failure is a refusal, never a normalization
    if stride != STRIDE: raise ReaderRefusal("stride %d != %d" % (stride, STRIDE))
    if n_in != W * H * CB: raise ReaderRefusal(
        "n_in %d != field %d - field-order liar? (n_gate in the n_in slot reads huge)" % (n_in, W * H * CB))
    if wire_base != HDR: raise ReaderRefusal("wire_base %d != %d" % (wire_base, HDR))
    if cell_base < wire_base or cell_base + n_in > wire_base + n_wire:
        raise ReaderRefusal("cell span escapes wire region")
    gate_base = wire_base + n_wire
    need = gate_base + n_gate * STRIDE
    if need != len(raw): raise ReaderRefusal(
        "size mismatch: header implies %d bytes, file holds %d" % (need, len(raw)))
    for w in raw[wire_base:gate_base]:
        if w not in (0, 1): raise ReaderRefusal("wire byte %d not a bit" % w)
    lo, hi = wire_base, wire_base + n_wire
    writers = set()
    for k in range(n_gate):
        op, a, b, out = struct.unpack_from("<BQQQ", raw, gate_base + k * STRIDE)
        if op not in OPS: raise ReaderRefusal("gate %d op %d outside alphabet" % (k, op))
        for name, addr in (("a", a), ("b", b), ("out", out)):
            if not (lo <= addr < hi): raise ReaderRefusal(
                "gate %d %s=%d outside wire region [%d,%d)" % (k, name, addr, lo, hi))
        if out in writers: raise ReaderRefusal("gate %d second writer on %d" % (k, out))
        writers.add(out)
    return {"n_in": n_in, "n_wire": n_wire, "n_gate": n_gate, "depth": depth}

def make_control():
    """Minimal honest container: 8 field bits, 2 consts, 4 gates."""
    W, H, CB = 8, 1, 1
    n_in = W * H * CB
    n_wire = 2 + n_in + 4
    n_gate = 4
    body = bytearray()
    body += MAGIC
    body += struct.pack("<IIIII", n_in, n_wire, n_gate, n_in, 3)
    body += struct.pack("<IIII", W, H, CB, STRIDE)
    body += struct.pack("<QQ", HDR, HDR + 2)
    body += b"\x00" * (HDR - len(body))
    body += bytes([0, 1] + [0] * n_in + [0] * 4)             # wires
    gb = HDR + n_wire
    t = HDR + 2 + n_in                                        # first temp
    for k in range(n_gate):                                   # 4 NANDs, distinct outs
        body += struct.pack("<BQQQ", 0, HDR + 2 + k, HDR + 2 + (k + 1) % 8, t + k)
    return bytes(body)

def mutants(ctrl):
    W, H, CB = 8, 1, 1
    n_in = W * H * CB; n_wire = 2 + n_in + 4; n_gate = 4
    out = {}
    m = bytearray(ctrl); m[:8] = b"WEATHER2"                          # 1 wrong magic
    out["wrong_magic"] = bytes(m)
    m = bytearray(ctrl)                                               # 2 swapped field order (the historical liar)
    struct.pack_into("<IIIII", m, 8, n_gate, n_wire, n_in, n_in, 3)   #   n_gate where n_in belongs
    out["swapped_field_order"] = bytes(m)
    out["truncated_table"] = ctrl[:-STRIDE]                           # 3 header claims one more record than file holds
    m = bytearray(ctrl)                                               # 4 stride lie in header
    struct.pack_into("<I", m, 40, 24)
    out["stride_lie"] = bytes(m)
    m = bytearray(ctrl)                                               # 5 gate address escapes wire region
    gb = HDR + n_wire
    struct.pack_into("<BQQQ", m, gb, 0, 10 ** 9, HDR + 2, HDR + 2 + n_in)
    out["addr_out_of_range"] = bytes(m)
    m = bytearray(ctrl)                                               # 6 second writer on one address
    op, a, b, o0 = struct.unpack_from("<BQQQ", m, gb)
    struct.pack_into("<BQQQ", m, gb + STRIDE, 0, a, b, o0)
    out["double_writer"] = bytes(m)
    return out

def main():
    ctrl = make_control()
    parse = strict_read(ctrl)
    print("control: PASS  %r" % parse)
    results = {}
    for name, m in mutants(ctrl).items():
        try:
            strict_read(m)
            results[name] = "SURVIVED - READER IS AN ACCOMPLICE"
        except ReaderRefusal as e:
            results[name] = "caught: %s" % e
        print("%-22s %s" % (name, results[name]))
    all_caught = all(v.startswith("caught") for v in results.values())
    report = {"control_pass": True, "mutants": results, "all_caught": all_caught,
              "law": "a reader that normalizes a broken container is an accomplice; "
                     "ship the SPEC not the tool - off-stone checkers author their own readback"}
    with open(os.path.join(HERE, "reader_battery_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    print("ALL MUTANTS CAUGHT:", all_caught)
    if not all_caught:
        print("BATTERY FAILED - this reader may not be relied on")
        return 1
    print("reader certified against 6 liars. reader_battery_report.json written")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
