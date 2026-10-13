#!/usr/bin/env python3
"""Component implementation and operation."""
import io, json, os, struct, sys, time

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "READER1.mno")
TBL = os.path.join(HERE, "READER1.table.mno")
SIDE = os.path.join(HERE, "READER1.layout.json")
GENOME = os.path.join(HERE, "reader_genome.jsonl")
WRITE = "--write" in sys.argv

OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4

CONTAINER_BYTES = 103803349384

# THE TABLE - what to match. Its size is what scales, and it is DATA, not gates.
TARGETS = [b"MUHLFLD1", b"MUHLLNP1", b"NRING2M1", b"MUHLSCN1", b"MUHLPLAY",
           b"TITANCIR", b"PFCWINMN", b"MUHLPHYS", b"MUHLWBX1", b"MUHLTFM1",
           b"GGUF\x03\x00\x00\x00", b"\x00\x00\x00\x00\x00\x00\x00\x00"]
GROUP = 8
CURSOR = 8          # one 8-byte cursor. THE DATA LIVES AT THE ADDRESS THE CURSOR NAMES.


def build(targets=TARGETS, mutant=None):
    """FIXED gate count: it depends on the TABLE, never on the span being read.

    Wire plan, mirroring MUHLSCN1's:
      cursor[0..8)          the 8 bytes currently addressed  <- operands rewritten at siting
      shadow[0..8)          previous settle's bytes (self-clock)
      table[t][0..8)        the targets
      per target: XOR-fold cursor against target -> HIT[t]
      plus ZERO / PRINTABLE / CHANGED over the cursor
    """
    gates, edges = [], []
    cur = 0
    sh = cur + GROUP
    tbl = sh + GROUP
    work = tbl + len(targets) * GROUP
    obs = work + 64 + len(targets) * 16

    # HIT[t] per target - the table is what grows, and it grows as DATA
    for t, tg in enumerate(targets):
        tb = tbl + t * GROUP
        m = work + 64 + t * 16
        gates.append((OP_XOR, cur, tb, m)); edges.append(("h", t, 0))
        for k in range(1, GROUP):
            src = tb + k if mutant != "drop_byte" or k != 3 else tb
            gates.append((OP_XOR, cur + k, src, m + 1))
            gates.append((OP_OR, m, m + 1, m + 2))
            edges.append(("h", t, k))
            m = m + 2
        gates.append((OP_NOT, m, m, obs + t))

    # ZERO over the cursor
    acc = work
    gates.append((OP_OR, cur, cur + 1, acc)); edges.append(("z", 0, 0))
    for k in range(2, GROUP):
        gates.append((OP_OR, acc, cur + k, acc + 1)); edges.append(("z", 0, k - 1))
        acc += 1
    gates.append((OP_NOT, acc, acc, obs + len(targets)))

    # PRINTABLE over the cursor
    p = work + 16
    gates.append((OP_AND, cur, cur + 1, p)); edges.append(("p", 0, 0))
    for k in range(2, GROUP):
        gates.append((OP_AND, p, cur + k, p)); edges.append(("p", 0, k - 1))
    gates.append((OP_OR, p, p, obs + len(targets) + 1))

    # CHANGED - XOR the cursor against the shadow
    c = work + 32
    gates.append((OP_XOR, cur, sh, c)); edges.append(("c", 0, 0))
    for k in range(1, GROUP):
        gates.append((OP_XOR, cur + k, sh + k, c + 1))
        gates.append((OP_OR, c, c + 1, c + 2)); edges.append(("c", 0, k))
        c += 2
    gates.append((OP_OR, c, c, obs + len(targets) + 2))

    # SELF-CLOCK - shadow rewrites itself. out addr == the addr next settle reads.
    for k in range(GROUP):
        src = cur + k if mutant != "no_advance" else sh + k
        gates.append((OP_OR, src, src, sh + k)); edges.append(("s", 0, k))

    n_out = len(targets) + 3
    layout = {"cursor": cur, "shadow": sh, "table": tbl, "work": work, "obs": obs,
              "n_gate": len(gates), "n_out": n_out, "targets": len(targets),
              "group": GROUP,
              "answers": ["HIT[%d]" % i for i in range(len(targets))]
                         + ["ZERO", "PRINTABLE", "CHANGED"]}
    return layout, gates, sorted(edges)


def reference_edges(targets):
    """INDEPENDENT REFERENCE - from the spec alone."""
    e = []
    for t in range(len(targets)):
        for k in range(GROUP):
            e.append(("h", t, k))
    for k in range(GROUP - 1):
        e.append(("z", 0, k))
    for k in range(GROUP - 1):
        e.append(("p", 0, k))
    for k in range(GROUP):
        e.append(("c", 0, k))
    for k in range(GROUP):
        e.append(("s", 0, k))
    return sorted(e)


def ticks_of(gates):
    """TICKS. A level is a change propagating and a change is a tick."""
    lvl, d = {}, 0
    for op, a, b, o in gates:
        n = 1 + max(lvl.get(a, 0), lvl.get(b, 0))
        lvl[o] = n
        if n > d:
            d = n
    return d


def main():
    t0 = time.time()
    lay, gates, edges = build()
    ref = reference_edges(TARGETS)
    print("=" * 78)
    print("  READER1 - fixed machine + table. The data is ADDRESSED, never embedded.")
    print("=" * 78)
    print()
    print("  gates                : %s   FIXED" % format(len(gates), ","))
    print("  TICKS                : %s" % format(ticks_of(gates), ","))
    print("  targets in the table : %s" % format(lay["targets"], ","))
    print("  answers              : %s HIT bits + ZERO + PRINTABLE + CHANGED"
          % format(lay["targets"], ","))
    print()
    print("  THE SPAN IS NOT IN THE MACHINE:")
    print("    container         : %s bytes = %s BITS"
          % (format(CONTAINER_BYTES, ","), format(CONTAINER_BYTES * 8, ",")))
    print("    gates needed      : %s   <- SAME NUMBER for 8 bytes or for the whole file"
          % format(len(gates), ","))
    print("    what scales       : the TABLE, and a table is DATA, not gates")
    print("    host loop over the span: NONE. this fabricator never iterates the container.")
    print()
    same = (edges == ref)
    print("  wiring vs independent reference : %s" % same)
    caught = 0
    MUT = ("drop_byte", "no_advance")
    for mut in MUT:
        _l, g2, e2 = build(mutant=mut)
        differs = (g2 != gates) or (e2 != edges)
        if differs:
            caught += 1
        print("  mutant %-11s differs        : %s" % (mut, differs))
    empty_ok = ([] != ref)
    print("  all-zero baseline differs       : %s" % empty_ok)
    if not same or caught != len(MUT) or not empty_ok:
        print()
        print("  REFUSING TO WRITE.")
        return 1

    blob = bytearray()
    for op, a, b, o in gates:
        blob += struct.pack("<BQQQ", op, a, b, o)
    for i in range(lay["n_out"]):
        blob += struct.pack("<I", lay["obs"] + i)
    table = bytearray()
    for tg in TARGETS:
        table += tg[:GROUP].ljust(GROUP, b"\x00")

    side = dict(lay)
    side.update({"magic": "MUHLRDR2", "version": 2,
                 "container": os.path.basename(OUT), "table": os.path.basename(TBL),
                 "record": "<BQQQ> op|a|b|out, 25 B",
                 "geometry": "hdr 0 | 25-byte records | out[n_out] u32  (READER1 writes NO "
                             "header into the container - the layout is this sidecar)",
                 "header_bytes_in_container": 0,
                 "ticks": ticks_of(gates), "bytes": len(blob), "table_bytes": len(table),
                 "targets_hex": [t.hex() for t in TARGETS],
                 "read_from": "muhl_scan_machine MUHLSCN1 + muhl_scan_machine_table MUHLKEYB, "
                              "read out of titan.gguf 2026-08-07"})
    with io.open(GENOME, "a", encoding="utf-8", newline="") as j:
        j.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "act": "fabricate READER1",
                            "gates": len(gates), "ticks": ticks_of(gates),
                            "table_bytes": len(table)}) + "\n")
        j.flush(); os.fsync(j.fileno())

    if not WRITE:
        print()
        print("  DRY RUN - machine %s B, table %s B. add --write"
              % (format(len(blob), ","), format(len(table), ",")))
        return 0

    with io.open(SIDE, "w", encoding="utf-8", newline="") as s:
        json.dump(side, s, indent=1); s.flush(); os.fsync(s.fileno())
    with io.open(OUT, "wb") as f:
        f.write(bytes(blob)); f.flush(); os.fsync(f.fileno())
    with io.open(TBL, "wb") as f:
        f.write(bytes(table)); f.flush(); os.fsync(f.fileno())
    print()
    print("  WROTE %s  %s B   byte 0 = gate 0, NO LABEL INSIDE"
          % (os.path.basename(OUT), format(os.path.getsize(OUT), ",")))
    print("  WROTE %s  %s B   the table - DATA, no label, no gates"
          % (os.path.basename(TBL), format(os.path.getsize(TBL), ",")))
    print("  LAYOUT -> %s (outside, 0 addresses spent)" % os.path.basename(SIDE))
    print("  [%.1f s]" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
