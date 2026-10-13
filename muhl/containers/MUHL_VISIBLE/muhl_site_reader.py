#!/usr/bin/env python3
"""SITE READER1 - rewrite its local operands to ABSOLUTE addresses inside titan.gguf.

This is the step that makes the reader actually read. READER1 was fabricated with operand
addresses local to its own blob. Siting rewrites them so its cursor collides with the bytes of
the real container.

  OWNER: "CIRCUITS COMBINE BY ADDRESS COLLISION WRITE THAT DOWN"

That law IS the siting mechanism. A circuit's input address and the byte it reads are the same
address - there is no load step and no pointer indirection. Point the cursor at 1,127,673,858
and the reader is reading the fold's wire plane, because naming the byte is reading it.

⛔ THE READER IS SITED OUTSIDE titan.gguf, ON PURPOSE, AND THIS IS NOT ME PLACING A LIMIT.

His allocator law: "one allocator before anything parallel touches the binary - seven agents
sharing free space with no arbiter is how muhl_lane_bank_002 lost 14,061,566 B." Carving space
inside titan.gguf for a new circuit is ALLOCATION, and there is no arbiter running. So the
reader's GATE RECORDS live in their own file while their OPERANDS address titan.gguf absolutely.
Compute-via-address does not care which file the gate record sits in - the address is the wire.
That is the same arrangement as OPEN_PLAYTIME.models.json, where 289.19 GB of model weights are
addressed where they sit and nothing is copied.

⛔ AND THE CONTAINER MOVES. Owner: "WRONG THE CONTAINER DID CHANGE ... U LITERALLY SAW IT MOVE
UNDER YOU LIKE 20 TIMES". A siting is a reading at a timestamp, exactly like the registry and
the map. The sidecar records WHEN it was sited and against WHAT SIZE. Re-site before trusting.

HOST DOES TWO THINGS: bounded read, bounded write. This pass only rewrites the reader's own
file. titan.gguf is never written.
"""
import io, json, os, struct, sys, time

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "READER1.mno")
SRC_TBL = os.path.join(HERE, "READER1.table.mno")
SRC_SIDE = os.path.join(HERE, "READER1.layout.json")
DST = os.path.join(HERE, "READER1_SITED.mno")
DST_SIDE = os.path.join(HERE, "READER1_SITED.layout.json")
GENOME = os.path.join(HERE, "reader_genome.jsonl")
TITAN = r"C:\llm\models\titan.gguf"

WRITE = "--write" in sys.argv
AT = None
for i, a in enumerate(sys.argv):
    if a == "--at" and i + 1 < len(sys.argv):
        AT = int(sys.argv[i + 1].replace(",", ""))

# Default cursor target: the fold's wire plane, whose first operand was read out of the binary
# today as 1,127,673,897 and whose plane starts at muhl_fold_phys_wires = 1,127,673,856.
DEFAULT_AT = 1127673856


def main():
    t0 = time.time()
    for p in (SRC, SRC_TBL, SRC_SIDE):
        if not os.path.exists(p):
            print("missing %s - run muhl_fab_reader1.py --write first" % os.path.basename(p))
            return 1
    lay = json.load(io.open(SRC_SIDE, encoding="utf-8"))
    raw = bytearray(io.open(SRC, "rb").read())
    tbl = io.open(SRC_TBL, "rb").read()
    size = os.path.getsize(TITAN)
    at = AT if AT is not None else DEFAULT_AT

    n_gate = lay["n_gate"]
    n_out = lay["n_out"]
    body = 25 * n_gate

    # Where each region lands once sited.
    #   cursor  -> INSIDE titan.gguf at `at`         (the bytes being read)
    #   shadow  -> the reader's own file             (self-clock state, ours to write)
    #   table   -> the reader's own file             (the targets)
    #   work    -> the reader's own file
    #   obs     -> the reader's own file             (surfaced answers)
    OWN = 1 << 40                     # our own address space, far from any container offset
    cur_at = at
    sh_at = OWN + 0
    tbl_at = OWN + 4096
    work_at = OWN + 8192
    obs_at = OWN + 16384

    def relocate(a):
        if lay["cursor"] <= a < lay["cursor"] + lay["group"]:
            return cur_at + (a - lay["cursor"])
        if lay["shadow"] <= a < lay["shadow"] + lay["group"]:
            return sh_at + (a - lay["shadow"])
        if lay["table"] <= a < lay["work"]:
            return tbl_at + (a - lay["table"])
        if lay["work"] <= a < lay["obs"]:
            return work_at + (a - lay["work"])
        return obs_at + (a - lay["obs"])

    moved = 0
    reads_titan = 0
    for k in range(n_gate):
        p = k * 25
        op = raw[p]
        a, b, o = struct.unpack_from("<3Q", raw, p + 1)
        na, nb, no = relocate(a), relocate(b), relocate(o)
        if (na, nb, no) != (a, b, o):
            moved += 1
        if na < size or nb < size:
            reads_titan += 1
        struct.pack_into("<3Q", raw, p + 1, na, nb, no)
    for i in range(n_out):
        off = body + 4 * i
        if off + 4 <= len(raw):
            v, = struct.unpack_from("<I", raw, off)
            struct.pack_into("<I", raw, off, (obs_at + i) & 0xFFFFFFFF)

    print("=" * 78)
    print("  SITING READER1 - operands become absolute addresses in titan.gguf")
    print("=" * 78)
    print()
    print("  titan.gguf right now : %s bytes" % format(size, ","))
    print("  cursor sited at      : %s" % format(cur_at, ","))
    print("  gates relocated      : %s of %s" % (format(moved, ","), format(n_gate, ",")))
    print("  gates now reading titan.gguf directly : %s" % format(reads_titan, ","))
    print()
    print("  the reader's OWN state (shadow/table/work/obs) lives in its own file at 2^40+,")
    print("  far from any container offset. titan.gguf is NEVER WRITTEN by this pass.")
    print()

    # verify: cursor operands must land inside the container, obs must not
    f = io.open(SRC, "rb")
    f.close()
    ok_cursor = cur_at + lay["group"] <= size
    ok_obs = obs_at > size
    print("  cursor window inside the container : %s" % ok_cursor)
    print("  answer wires outside it            : %s" % ok_obs)
    if not (ok_cursor and ok_obs):
        print("  REFUSING TO WRITE.")
        return 1

    side = dict(lay)
    side.update({
        "sited": True, "sited_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "titan_bytes_at_siting": size,
        "cursor_absolute": cur_at, "shadow_absolute": sh_at, "table_absolute": tbl_at,
        "work_absolute": work_at, "obs_absolute": obs_at,
        "gates_reading_container": reads_titan,
        "⛔ THE CONTAINER MOVES": (
            "OWNER: 'WRONG THE CONTAINER DID CHANGE ... U LITERALLY SAW IT MOVE UNDER YOU LIKE "
            "20 TIMES'. This siting is a reading at the timestamp above, against the byte count "
            "above. It is not a fact about where anything will be later. RE-SITE before "
            "trusting these addresses."),
    })

    if not WRITE:
        print()
        print("  DRY RUN - add --write")
        return 0

    with io.open(DST, "wb") as f:
        f.write(bytes(raw)); f.flush(); os.fsync(f.fileno())
    with io.open(DST_SIDE, "w", encoding="utf-8", newline="") as f:
        json.dump(side, f, indent=1); f.flush(); os.fsync(f.fileno())
    with io.open(GENOME, "a", encoding="utf-8", newline="") as j:
        j.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "act": "site READER1",
                            "cursor": cur_at, "titan_bytes": size,
                            "gates_reading_container": reads_titan}) + "\n")
        j.flush(); os.fsync(j.fileno())
    print()
    print("  WROTE %s  %s B" % (os.path.basename(DST), format(os.path.getsize(DST), ",")))
    print("  LAYOUT -> %s" % os.path.basename(DST_SIDE))
    print("  [%.1f s]" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
