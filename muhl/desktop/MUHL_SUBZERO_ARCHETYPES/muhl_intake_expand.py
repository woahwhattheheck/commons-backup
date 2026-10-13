#!/usr/bin/env python3
"""muhl_intake_expand.py — EXPAND the intake region capacity.

Manufacturing step (offline, not runtime). Grows titan.gguf, updates the
intake header capacity field, and updates the registry. All writes journaled.

    python muhl_intake_expand.py 50          # expand to 50 GB
    python muhl_intake_expand.py 50 --dry    # report only, no writes
"""
import sys, os, json, struct, mmap

sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")
import pfc_paths as PFCP

TITAN = PFCP.TITAN
REG = PFCP.REG
INTAKE_KEY = "muhl_self_train.intake"
GENOME_PATH = TITAN.replace(".gguf", "_intake_expand_genome.jsonl")


def journal_write(off, length, orig_bytes, action="intake_expand"):
    """Journal original bytes before overwriting."""
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({
            "action": action,
            "off": off,
            "len": length,
            "orig": orig_bytes.hex()
        }) + "\n")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv

    if not args:
        print("  usage: python muhl_intake_expand.py <size_gb> [--dry]")
        return 1

    new_gb = int(args[0])
    new_capacity = new_gb * (1 << 30)

    print(f"\n  MUHLNICKEL INTAKE EXPANSION — manufacturing step")
    print(f"  target capacity: {new_gb} GB ({new_capacity:,} bytes)")

    # Load registry
    if not os.path.exists(REG):
        print(f"  ERROR: registry not found: {REG}")
        return 1
    reg = json.load(open(REG))
    if INTAKE_KEY not in reg:
        print(f"  ERROR: intake region not registered ({INTAKE_KEY})")
        return 1

    info = reg[INTAKE_KEY]
    base_off = int(info["offset"])
    old_capacity = int(info["capacity"])
    header_len = int(info["header_len"])

    print(f"  current capacity: {old_capacity:,} bytes ({old_capacity / (1 << 30):.2f} GB)")

    if new_capacity <= old_capacity:
        print(f"  ERROR: new capacity must be larger than current ({old_capacity:,})")
        return 1

    # Calculate growth needed
    current_size = os.path.getsize(TITAN)
    needed_end = base_off + header_len + new_capacity
    growth = needed_end - current_size if needed_end > current_size else 0

    print(f"  titan.gguf current size: {current_size:,} bytes ({current_size / (1 << 30):.2f} GB)")
    print(f"  needed end:              {needed_end:,} bytes ({needed_end / (1 << 30):.2f} GB)")
    print(f"  growth needed:           {growth:,} bytes ({growth / (1 << 30):.2f} GB)")

    # Read current header
    with open(TITAN, "rb") as f:
        f.seek(base_off)
        header_bytes = f.read(24)
    write_ptr, size_used, cap_stored = struct.unpack("<QQQ", header_bytes)
    print(f"  header: write_ptr={write_ptr:,}, size_used={size_used:,}, capacity={cap_stored:,}")

    if dry:
        print(f"\n  --dry: would grow titan.gguf by {growth:,} bytes")
        print(f"  --dry: would update capacity from {old_capacity:,} to {new_capacity:,}")
        print(f"  --dry: would update registry")
        return 0

    # Step 1: Grow titan.gguf
    if growth > 0:
        print(f"\n  growing titan.gguf by {growth:,} bytes ({growth / (1 << 30):.2f} GB)...")
        chunk = 1 << 20  # 1 MB at a time
        written = 0
        with open(TITAN, "ab") as f:
            remaining = growth
            while remaining > 0:
                w = min(chunk, remaining)
                f.write(b"\x00" * w)
                remaining -= w
                written += w
                if written % (1 << 30) == 0:
                    print(f"    ... {written / (1 << 30):.0f} GB written")
        print(f"    done. titan.gguf now {os.path.getsize(TITAN):,} bytes")

    # Step 2: Journal and update the header capacity field
    print(f"  journaling header update...")
    journal_write(base_off + 16, 8, struct.pack("<Q", cap_stored), "capacity_update")

    # Update capacity in header (field at offset base_off + 16)
    with open(TITAN, "r+b") as f:
        f.seek(base_off + 16)
        f.write(struct.pack("<Q", new_capacity))
    print(f"  header capacity updated: {cap_stored:,} -> {new_capacity:,}")

    # Step 3: Update registry
    print(f"  updating registry...")
    info["capacity"] = new_capacity
    info["len"] = header_len + new_capacity
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"  registry updated: {REG}")

    # Step 4: Update INTAKE_CAPACITY in muhl_self_train.py for future runs
    selftrain_path = os.path.join(os.path.dirname(__file__), "muhl_self_train.py")
    if os.path.exists(selftrain_path):
        txt = open(selftrain_path).read()
        old_line = "INTAKE_CAPACITY = 1 << 30"
        new_line = f"INTAKE_CAPACITY = {new_gb} * (1 << 30)                        # {new_gb} GB"
        if old_line in txt:
            txt = txt.replace(old_line, new_line)
            with open(selftrain_path, "w") as f:
                f.write(txt)
            print(f"  updated muhl_self_train.py constant: {new_line.strip()}")

    # Verify
    with open(TITAN, "rb") as f:
        f.seek(base_off)
        hdr = f.read(24)
    wp, su, cap = struct.unpack("<QQQ", hdr)
    remaining = new_capacity - su
    print(f"\n  EXPANSION COMPLETE.")
    print(f"    new capacity:  {cap:,} bytes ({cap / (1 << 30):.1f} GB)")
    print(f"    bytes used:    {su:,}")
    print(f"    remaining:     {remaining:,} bytes ({remaining / (1 << 30):.2f} GB)")
    print(f"    journal:       {GENOME_PATH}")
    print(f"    titan.gguf:    {os.path.getsize(TITAN):,} bytes ({os.path.getsize(TITAN) / (1 << 30):.2f} GB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
