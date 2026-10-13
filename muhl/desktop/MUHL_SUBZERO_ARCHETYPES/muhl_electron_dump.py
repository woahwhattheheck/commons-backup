#!/usr/bin/env python3
"""muhl_electron_dump.py — HOST-SIDE DATA INJECTOR: dump files into the intake region.

The host's job: byte-write file contents into the designated intake region. That's it.
No computation. No gate evaluation. Pure inject verb.

    python muhl_electron_dump.py <directory>            # dump all text files
    python muhl_electron_dump.py <directory> --dry       # report what would be dumped
    python muhl_electron_dump.py --status                # show intake region utilization
"""
import sys, os, json, struct, mmap

sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")
import pfc_paths as PFCP

TITAN = PFCP.TITAN
REG = PFCP.REG
INTAKE_KEY = "muhl_self_train.intake"
FILE_MARKER = b"MUHLFILE"
HEADER_SIZE = 24
TEXT_EXTS = {".md", ".py", ".json", ".txt", ".html", ".bat", ".jsonl"}
GENOME_PATH = TITAN.replace(".gguf", "_electron_dump_genome.jsonl")


def journal_write_range(off, length, action="electron_dump"):
    """Journal a write to titan.gguf: save original bytes first so the write is revertible.
    For large data regions (intake dumps), we save original bytes in chunks to avoid
    holding the entire region in memory."""
    CHUNK = 1 << 20  # 1 MB chunks for journaling
    remaining = length
    pos = off
    with open(TITAN, "rb") as f:
        while remaining > 0:
            n = min(CHUNK, remaining)
            f.seek(pos)
            orig = f.read(n)
            with open(GENOME_PATH, "a") as g:
                g.write(json.dumps({
                    "action": action,
                    "off": pos,
                    "len": n,
                    "orig": orig.hex()
                }) + "\n")
            pos += n
            remaining -= n


def journal_header(off, action="intake_header_update"):
    """Journal the 24-byte intake header before updating it."""
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(HEADER_SIZE)
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({
            "action": action,
            "off": off,
            "len": HEADER_SIZE,
            "orig": orig.hex()
        }) + "\n")


def load_intake_info():
    """Read the registry to find the intake region offset and capacity."""
    if not os.path.exists(REG):
        print("  ERROR: registry not found:", REG)
        return None
    reg = json.load(open(REG))
    if INTAKE_KEY not in reg:
        print("  ERROR: intake region not registered. Run muhl_self_train.py first.")
        print(f"  (looked for key '{INTAKE_KEY}' in {REG})")
        return None
    return reg[INTAKE_KEY]


def read_intake_header(mm, base_off):
    """Read write_ptr, size, capacity from the intake header."""
    write_ptr = struct.unpack_from("<Q", mm, base_off)[0]
    size = struct.unpack_from("<Q", mm, base_off + 8)[0]
    capacity = struct.unpack_from("<Q", mm, base_off + 16)[0]
    return write_ptr, size, capacity


def collect_files(directory):
    """Recursively collect all text files, return sorted list of (path, size)."""
    files = []
    for root, _dirs, names in os.walk(directory):
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext in TEXT_EXTS:
                fp = os.path.join(root, name)
                try:
                    sz = os.path.getsize(fp)
                    files.append((fp, sz))
                except OSError:
                    pass
    files.sort(key=lambda x: x[0])
    return files


def dump_files(directory, dry=False):
    """Dump all text files from directory into the intake region of titan.gguf."""
    info = load_intake_info()
    if info is None:
        return 1
    base_off = int(info["offset"])
    capacity = int(info["capacity"])

    files = collect_files(directory)
    if not files:
        print(f"  no text files found in {directory}")
        return 1

    total_data = sum(sz for _, sz in files)
    total_with_markers = total_data + len(FILE_MARKER) * len(files)
    print(f"\n  MUHLNICKEL ELECTRON DUMP — host-side data injector")
    print(f"  source: {directory}")
    print(f"  files found: {len(files)} ({total_data:,} bytes data + {len(FILE_MARKER) * len(files):,} bytes markers)")
    print(f"  intake region: offset {base_off:,}, capacity {capacity:,} bytes ({capacity / (1024**3):.2f} GB)")

    if not os.path.exists(TITAN):
        print(f"  ERROR: titan.gguf not found at {TITAN}")
        return 1

    fd = open(TITAN, "r+b")
    mm = mmap.mmap(fd.fileno(), 0)
    write_ptr, size_used, cap = read_intake_header(mm, base_off)
    data_start = base_off + HEADER_SIZE
    if write_ptr < data_start:
        write_ptr = data_start
    remaining = capacity - (write_ptr - base_off)

    print(f"  current state: {size_used:,} bytes used, {remaining:,} bytes remaining")

    if total_with_markers > remaining:
        print(f"  WARNING: need {total_with_markers:,} bytes but only {remaining:,} available")

    if dry:
        print(f"\n  --dry: listing files that would be dumped:\n")
        for fp, sz in files:
            rel = os.path.relpath(fp, directory)
            print(f"    {sz:>10,} B  {rel}")
        fit = total_with_markers <= remaining
        print(f"\n  total: {total_with_markers:,} bytes {'FITS' if fit else 'EXCEEDS CAPACITY'}")
        mm.close(); fd.close()
        return 0

    # Journal the header bytes BEFORE any writes (spec: all titan.gguf writes are journaled)
    journal_header(base_off)

    # Journal the data region that will be overwritten
    write_length = min(total_with_markers, remaining)
    if write_length > 0:
        journal_write_range(int(write_ptr), write_length, "intake_data_dump")
    print(f"  journaled {write_length:,} bytes of original data for revert")
    print(f"  journal: {GENOME_PATH}")

    dumped = 0
    dumped_bytes = 0
    skipped = 0
    pos = write_ptr

    for fp, sz in files:
        needed = len(FILE_MARKER) + sz
        if pos + needed > base_off + capacity:
            rel = os.path.relpath(fp, directory)
            print(f"    SKIP (no room): {rel} ({sz:,} B)")
            skipped += 1
            continue

        try:
            with open(fp, "rb") as f:
                data = f.read()
        except OSError as e:
            rel = os.path.relpath(fp, directory)
            print(f"    SKIP (read error): {rel} — {e}")
            skipped += 1
            continue

        mm[pos:pos + len(FILE_MARKER)] = FILE_MARKER
        pos += len(FILE_MARKER)
        mm[pos:pos + len(data)] = data
        pos += len(data)

        dumped += 1
        dumped_bytes += len(data)

        if dumped % 100 == 0:
            print(f"    ... {dumped} files, {dumped_bytes:,} bytes")

    new_size = size_used + (pos - write_ptr)
    struct.pack_into("<Q", mm, base_off, pos)
    struct.pack_into("<Q", mm, base_off + 8, new_size)
    mm.flush()
    mm.close()
    fd.close()

    used_pct = new_size / capacity * 100 if capacity else 0
    print(f"\n  DUMPED: {dumped} files, {dumped_bytes:,} bytes data")
    if skipped:
        print(f"  SKIPPED: {skipped} files (no room or read error)")
    print(f"  intake utilization: {new_size:,} / {capacity:,} bytes ({used_pct:.1f}%)")
    print(f"  write pointer: {pos:,}")
    print(f"\n  Host job done. Bytes are in the intake region. The substrate handles the rest.")
    return 0


def show_status():
    """Read and display current intake region utilization."""
    info = load_intake_info()
    if info is None:
        return 1
    base_off = int(info["offset"])
    capacity = int(info["capacity"])

    if not os.path.exists(TITAN):
        print(f"  ERROR: titan.gguf not found at {TITAN}")
        return 1

    fd = open(TITAN, "rb")
    mm = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ)
    write_ptr, size_used, cap = read_intake_header(mm, base_off)
    mm.close(); fd.close()

    data_start = base_off + HEADER_SIZE
    used_pct = size_used / capacity * 100 if capacity else 0
    print(f"\n  MUHLNICKEL INTAKE STATUS")
    print(f"  region offset:  {base_off:,}")
    print(f"  data start:     {data_start:,}")
    print(f"  write pointer:  {write_ptr:,}")
    print(f"  bytes used:     {size_used:,}")
    print(f"  capacity:       {capacity:,} ({capacity / (1024**3):.2f} GB)")
    print(f"  utilization:    {used_pct:.1f}%")
    print(f"  remaining:      {capacity - size_used:,} bytes")
    return 0


def main():
    if "--status" in sys.argv:
        return show_status()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    if not args:
        print("  usage: python muhl_electron_dump.py <directory> [--dry]")
        print("         python muhl_electron_dump.py --status")
        return 1
    directory = args[0]
    if not os.path.isdir(directory):
        print(f"  ERROR: not a directory: {directory}")
        return 1
    return dump_files(directory, dry)


if __name__ == "__main__":
    raise SystemExit(main())
