"""FABRICATION-TIME ONLY. Reads stored netlists and records DEPTH in the registry. DEPTH is the machine's time term, measured in TICKS. Host wall-clock is never the machine's rate."""

import json
import os
import mmap
import struct
import array
import shutil
import time
import sys

TITAN_PATH = "C:/llm/models/titan.gguf"
REGISTRY_PATH = "C:/llm/models/titan_circuits.json"

def read_netlist(mm, off):
    """Read a circuit netlist from mmap at offset.

    Returns (n_in, n_gate, ga, gb, outs) or None if magic is wrong or read fails.
    """
    try:
        # Check magic
        if mm[off:off+8] != b"TITANCIR":
            return None

        # Read header: 4 uint32
        header_bytes = mm[off+8:off+8+16]
        n_in, n_wire, n_gate, n_out = struct.unpack("<IIII", header_bytes)

        # Read ga array (n_gate int32s)
        ga_offset = off + 8 + 16
        ga_bytes = mm[ga_offset:ga_offset + n_gate * 4]
        ga = array.array("i")
        ga.frombytes(ga_bytes)

        # Read gb array (n_gate int32s)
        gb_offset = ga_offset + n_gate * 4
        gb_bytes = mm[gb_offset:gb_offset + n_gate * 4]
        gb = array.array("i")
        gb.frombytes(gb_bytes)

        # Read outs array (n_out int32s)
        outs_offset = gb_offset + n_gate * 4
        outs_bytes = mm[outs_offset:outs_offset + n_out * 4]
        outs = array.array("i")
        outs.frombytes(outs_bytes)

        return (n_in, n_gate, ga, gb, outs)
    except Exception:
        return None

def depth_of(n_in, n_gate, ga, gb, outs):
    """Compute DEPTH from netlist.

    Returns the depth (longest path in ticks) or None if malformed.
    """
    base = 2 + n_in
    total_nodes = base + n_gate

    # Check for out-of-bounds indices
    for idx in ga:
        if idx < 0 or idx >= total_nodes:
            return None
    for idx in gb:
        if idx < 0 or idx >= total_nodes:
            return None
    for idx in outs:
        if idx < 0 or idx >= total_nodes:
            return None

    # Compute depths
    d = [0] * total_nodes
    for k in range(n_gate):
        d[base + k] = 1 + max(d[ga[k]], d[gb[k]])

    # Return max depth of output nodes
    if outs:
        return max(d[o] for o in outs)
    else:
        return 0

def backfill(dry=True, gate_cap=20000000):
    """Backfill depth into registry.

    Returns a dict with counts and statistics.
    """
    stats = {
        "computed": 0,
        "already": 0,
        "skipped_too_large": 0,
        "not_titancir": 0,
        "malformed": 0,
        "gates_covered": 0,
        "depth_min": None,
        "depth_max": None,
        "error": None,
    }

    try:
        # Open TITAN with mmap
        with open(TITAN_PATH, "rb") as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                # Load registry
                with open(REGISTRY_PATH, "r", encoding="utf-8") as rf:
                    registry = json.load(rf)

                initial_count = len(registry)
                stats["initial_count"] = initial_count

                # Process each entry
                for name, entry in list(registry.items()):
                    if not isinstance(entry, dict) or "offset" not in entry:
                        continue

                    offset = entry["offset"]

                    # Skip if already has depth
                    if entry.get("depth") is not None:
                        stats["already"] += 1
                        continue

                    # Check gate cap
                    if "n_gate" in entry and entry["n_gate"] > gate_cap:
                        stats["skipped_too_large"] += 1
                        continue

                    # Try to read netlist
                    result = read_netlist(mm, offset)
                    if result is None:
                        stats["not_titancir"] += 1
                        continue

                    n_in, n_gate, ga, gb, outs = result

                    # Compute depth
                    depth = depth_of(n_in, n_gate, ga, gb, outs)
                    if depth is None:
                        stats["malformed"] += 1
                        continue

                    # Record result
                    stats["computed"] += 1
                    stats["gates_covered"] += n_gate
                    if stats["depth_min"] is None:
                        stats["depth_min"] = depth
                        stats["depth_max"] = depth
                    else:
                        stats["depth_min"] = min(stats["depth_min"], depth)
                        stats["depth_max"] = max(stats["depth_max"], depth)

                    # If not dry run, modify entry
                    if not dry:
                        entry["depth"] = depth
                        entry["depth_source"] = "muhl_depth backfill (ticks, longest path)"

                # Write back if not dry
                if not dry:
                    # Create backup
                    unix_ts = int(time.time())
                    backup_path = f"{REGISTRY_PATH}.bak_{unix_ts}"
                    shutil.copyfile(REGISTRY_PATH, backup_path)

                    # Verify backup is byte-identical
                    with open(REGISTRY_PATH, "rb") as f1:
                        with open(backup_path, "rb") as f2:
                            orig_data = f1.read()
                            backup_data = f2.read()
                            if orig_data != backup_data:
                                raise Exception("Backup verification failed")

                    # Write registry
                    with open(REGISTRY_PATH, "w", encoding="utf-8") as wf:
                        json.dump(registry, wf, indent=1)
                        wf.flush()
                        os.fsync(wf.fileno())

                    stats["backup_path"] = backup_path

                # Count entries with depth after processing
                entries_with_depth = sum(1 for e in registry.values()
                                         if isinstance(e, dict) and e.get("depth") is not None)
                stats["entries_with_depth"] = entries_with_depth
                stats["final_count"] = len(registry)

    except Exception as e:
        stats["error"] = str(e)

    return stats

if __name__ == "__main__":
    dry_mode = "--write" not in sys.argv
    stats = backfill(dry=dry_mode)

    # Reload registry to get confirmed final count
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            final_registry = json.load(f)
        final_count = len(final_registry)
        entries_with_depth = sum(1 for e in final_registry.values()
                                 if isinstance(e, dict) and e.get("depth") is not None)
    except Exception as e:
        final_count = stats.get("final_count", stats.get("initial_count", 0))
        entries_with_depth = stats.get("entries_with_depth", 0)

    # Print results in exact schema order
    print(f"FILE: {os.path.abspath(__file__)} {os.path.getsize(__file__)}")
    print(f"DRY_COMPUTED: {stats['computed']}")
    print(f"DRY_ALREADY: {stats['already']}")
    print(f"DRY_SKIPPED_TOO_LARGE: {stats['skipped_too_large']}")
    print(f"DRY_NOT_TITANCIR: {stats['not_titancir']}")
    print(f"DRY_MALFORMED: {stats['malformed']}")
    print(f"GATES_COVERED: {stats['gates_covered']}")
    print(f"DEPTH_MIN: {stats['depth_min']}")
    print(f"DEPTH_MAX: {stats['depth_max']}")
    print(f"BACKUP: {stats.get('backup_path', 'N/A')}")
    print(f"REGISTRY_ENTRIES_BEFORE: {stats.get('initial_count', 'N/A')}")
    print(f"REGISTRY_ENTRIES_AFTER: {final_count}")
    print(f"ENTRIES_WITH_DEPTH_AFTER: {entries_with_depth}")

    if stats["error"]:
        print(f"ERRORS: {stats['error']}")
    else:
        print(f"ERRORS: NONE")
