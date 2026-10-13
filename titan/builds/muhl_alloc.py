"""
FABRICATION-TIME ONLY. Manufacturing, not runtime.

Atomic free-space allocator for TITAN circuits. All operations are serialized by
filesystem lock to prevent concurrent allocation conflicts.
"""

import os
import json
import re
import sys
import time
import uuid

TITAN = "C:/llm/models/titan.gguf"
REG = "C:/llm/models/titan_circuits.json"
LEDGER = "C:/llm/models/muhl_alloc_ledger.jsonl"
LOCK = "C:/llm/models/.muhl_alloc.lock"
HEADER_FLOOR = 15822016
PAD = 8


def _lock(timeout=60):
    """Acquire exclusive lock. Retry every 0.1s. Treat stale locks (>300s) as dead."""
    start = time.time()
    while True:
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            return fd
        except FileExistsError:
            try:
                mtime = os.path.getmtime(LOCK)
                if time.time() - mtime > 300:
                    os.remove(LOCK)
                    continue
            except (OSError, FileNotFoundError):
                pass

            if time.time() - start > timeout:
                raise TimeoutError(f"Could not acquire lock within {timeout}s")
            time.sleep(0.1)


def _unlock(fd):
    """Close fd and remove lock file."""
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.remove(LOCK)
    except OSError:
        pass


def occupancy():
    """
    Build a sorted list of non-overlapping [start, end) intervals from registry, journals, and ledger.
    Return (intervals, stats_dict).
    """
    intervals = []
    stats = {
        "registry": 0,
        "journals": 0,
        "ledger": 0,
        "skipped_large_journals": [],
    }

    # Read registry
    try:
        with open(REG, "r") as f:
            reg_data = json.load(f)
            for entry in reg_data.values():
                if isinstance(entry, dict) and "offset" in entry and "len" in entry:
                    intervals.append([entry["offset"], entry["offset"] + entry["len"]])
                    stats["registry"] += 1
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Read journals
    journal_dir = "C:/llm/models/"
    try:
        for fname in os.listdir(journal_dir):
            if "genome" in fname and fname.endswith(".jsonl"):
                fpath = os.path.join(journal_dir, fname)
                try:
                    fsize = os.path.getsize(fpath)
                    if fsize > 2_000_000_000:
                        stats["skipped_large_journals"].append(fname)
                        continue

                    with open(fpath, "r") as f:
                        for line in f:
                            match = re.search(
                                r'"off"\s*:\s*(\d+).*?"len"\s*:\s*(\d+)', line
                            )
                            if match:
                                off = int(match.group(1))
                                length = int(match.group(2))
                                intervals.append([off, off + length])
                                stats["journals"] += 1
                except (OSError, IOError):
                    pass
    except (OSError, FileNotFoundError):
        pass

    # Read ledger - track latest state for each claim_id
    ledger_states = {}
    try:
        with open(LEDGER, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    claim_id = entry.get("claim_id")
                    if claim_id:
                        ledger_states[claim_id] = entry
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass

    # Add intervals from ledger where latest state is claimed or committed
    for entry in ledger_states.values():
        if entry.get("state") in ("claimed", "committed"):
            if "off" in entry and "len" in entry:
                intervals.append([entry["off"], entry["off"] + entry["len"]])
                stats["ledger"] += 1

    # Merge intervals
    if not intervals:
        return ([], stats)

    intervals.sort()
    merged = []
    current = intervals[0]
    for next_int in intervals[1:]:
        if next_int[0] <= current[1]:
            current[1] = max(current[1], next_int[1])
        else:
            merged.append(current)
            current = next_int
    merged.append(current)

    return (merged, stats)


def _write_claim(claim_id, name, off, need, note):
    """Helper to write claim to ledger."""
    ledger_entry = {
        "claim_id": claim_id,
        "name": name,
        "off": off,
        "len": need,
        "state": "claimed",
        "note": note,
        "pid": os.getpid(),
    }

    try:
        with open(LEDGER, "a") as f:
            f.write(json.dumps(ledger_entry) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        raise RuntimeError(f"Failed to write ledger: {e}")


def claim(name, need, note=""):
    """
    Claim a free span of at least need+PAD bytes.
    Return {"claim_id": ..., "offset": ..., "len": ...}
    """
    fd = _lock()
    try:
        occupied, stats = occupancy()

        # Get file size
        try:
            file_size = os.path.getsize(TITAN)
        except OSError:
            _unlock(fd)
            raise RuntimeError("Cannot read TITAN file size")

        # Find first gap >= need + PAD, starting at or after HEADER_FLOOR
        search_min = HEADER_FLOOR
        search_max = file_size

        if not occupied:
            # No occupied spans, entire range is free
            if search_max - search_min >= need + PAD:
                claim_id = uuid.uuid4().hex
                off = search_min
                _write_claim(claim_id, name, off, need, note)
                _unlock(fd)
                return {"claim_id": claim_id, "offset": off, "len": need}
        else:
            # Check gap before first occupied span
            if (
                occupied[0][0] > search_min
                and occupied[0][0] - search_min >= need + PAD
            ):
                claim_id = uuid.uuid4().hex
                off = search_min
                _write_claim(claim_id, name, off, need, note)
                _unlock(fd)
                return {"claim_id": claim_id, "offset": off, "len": need}

            # Check gaps between occupied spans
            for i in range(len(occupied) - 1):
                gap_start = occupied[i][1]
                gap_end = occupied[i + 1][0]
                if gap_end - gap_start >= need + PAD:
                    claim_id = uuid.uuid4().hex
                    off = gap_start
                    _write_claim(claim_id, name, off, need, note)
                    _unlock(fd)
                    return {"claim_id": claim_id, "offset": off, "len": need}

            # Check gap after last occupied span
            gap_start = occupied[-1][1]
            if search_max - gap_start >= need + PAD:
                claim_id = uuid.uuid4().hex
                off = gap_start
                _write_claim(claim_id, name, off, need, note)
                _unlock(fd)
                return {"claim_id": claim_id, "offset": off, "len": need}

        # No suitable gap found
        _unlock(fd)
        raise RuntimeError(f"no free span of {need} bytes")

    except Exception:
        try:
            _unlock(fd)
        except:
            pass
        raise


def commit(claim_id):
    """Mark claim as committed."""
    fd = _lock()
    try:
        ledger_entry = {"claim_id": claim_id, "state": "committed"}

        try:
            with open(LEDGER, "a") as f:
                f.write(json.dumps(ledger_entry) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            _unlock(fd)
            raise RuntimeError(f"Failed to write ledger: {e}")

        _unlock(fd)
    except Exception:
        _unlock(fd)
        raise


def release(claim_id):
    """Mark claim as released."""
    fd = _lock()
    try:
        ledger_entry = {"claim_id": claim_id, "state": "released"}

        try:
            with open(LEDGER, "a") as f:
                f.write(json.dumps(ledger_entry) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            _unlock(fd)
            raise RuntimeError(f"Failed to write ledger: {e}")

        _unlock(fd)
    except Exception:
        _unlock(fd)
        raise


def audit():
    """
    Report overlapping intervals (READ-ONLY).
    Return list of {"a": {...}, "b": {...}, "overlap_bytes": n}
    """
    overlaps = []

    # Collect raw intervals with source labels
    raw_intervals = []

    # Registry
    try:
        with open(REG, "r") as f:
            reg_data = json.load(f)
            for key, entry in reg_data.items():
                if isinstance(entry, dict) and "offset" in entry and "len" in entry:
                    raw_intervals.append(
                        {
                            "start": entry["offset"],
                            "end": entry["offset"] + entry["len"],
                            "source": "registry",
                            "key": key,
                        }
                    )
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Journals
    journal_dir = "C:/llm/models/"
    try:
        for fname in os.listdir(journal_dir):
            if "genome" in fname and fname.endswith(".jsonl"):
                fpath = os.path.join(journal_dir, fname)
                try:
                    fsize = os.path.getsize(fpath)
                    if fsize > 2_000_000_000:
                        continue

                    with open(fpath, "r") as f:
                        line_num = 0
                        for line in f:
                            line_num += 1
                            match = re.search(
                                r'"off"\s*:\s*(\d+).*?"len"\s*:\s*(\d+)', line
                            )
                            if match:
                                off = int(match.group(1))
                                length = int(match.group(2))
                                raw_intervals.append(
                                    {
                                        "start": off,
                                        "end": off + length,
                                        "source": "journal:" + fname,
                                        "line": line_num,
                                    }
                                )
                except (OSError, IOError):
                    pass
    except (OSError, FileNotFoundError):
        pass

    # Ledger - include all entries, not just active ones
    try:
        with open(LEDGER, "r") as f:
            line_num = 0
            for line in f:
                line_num += 1
                try:
                    entry = json.loads(line)
                    if "off" in entry and "len" in entry:
                        raw_intervals.append(
                            {
                                "start": entry["off"],
                                "end": entry["off"] + entry["len"],
                                "source": "ledger",
                                "line": line_num,
                                "claim_id": entry.get("claim_id"),
                                "state": entry.get("state"),
                            }
                        )
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass

    # Sort by start
    raw_intervals.sort(key=lambda x: x["start"])

    # Find overlaps
    for i in range(len(raw_intervals)):
        for j in range(i + 1, len(raw_intervals)):
            a = raw_intervals[i]
            b = raw_intervals[j]

            overlap_start = max(a["start"], b["start"])
            overlap_end = min(a["end"], b["end"])

            if overlap_start < overlap_end:
                overlaps.append(
                    {
                        "a": {k: v for k, v in a.items() if k not in ["start", "end"]},
                        "b": {k: v for k, v in b.items() if k not in ["start", "end"]},
                        "a_range": [a["start"], a["end"]],
                        "b_range": [b["start"], b["end"]],
                        "overlap_bytes": overlap_end - overlap_start,
                    }
                )

    return overlaps


def selftest():
    """Self-test the allocator."""
    disjoint = False
    above_header = False
    release_clears = False

    try:
        # Claim two spans
        claim1 = claim("_selftest_a", 4096)
        claim2 = claim("_selftest_b", 4096)

        # Check disjoint
        c1_end = claim1["offset"] + claim1["len"]
        c2_start = claim2["offset"]
        c1_start = claim1["offset"]
        c2_end = claim2["offset"] + claim2["len"]

        if c1_end <= c2_start or c2_end <= c1_start:
            disjoint = True

        # Check above header floor
        if claim1["offset"] >= HEADER_FLOOR and claim2["offset"] >= HEADER_FLOOR:
            above_header = True

        # Release both
        release(claim1["claim_id"])
        release(claim2["claim_id"])

        # Check they don't appear in occupancy
        occupied, _ = occupancy()
        found = False
        for start, end in occupied:
            if (start <= claim1["offset"] < end) or (start <= claim2["offset"] < end):
                found = True
                break

        if not found:
            release_clears = True

    except Exception as e:
        pass

    return disjoint, above_header, release_clears


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "selftest":
            disjoint, above_header, release_clears = selftest()
            print(f"DISJOINT: {disjoint}")
            print(f"ABOVE_HEADER_FLOOR: {above_header}")
            print(f"RELEASE_CLEARS: {release_clears}")

        elif sys.argv[1] == "audit":
            overlaps = audit()
            occupied, stats = occupancy()

            for overlap in overlaps:
                print(json.dumps(overlap))

            print(f"OVERLAPS: {len(overlaps)}")
            print(f"OCCUPIED_INTERVALS: {len(occupied)}")
            if stats["skipped_large_journals"]:
                print(
                    f"SKIPPED_LARGE_JOURNALS: {', '.join(stats['skipped_large_journals'])}"
                )
            else:
                print("SKIPPED_LARGE_JOURNALS: NONE")
