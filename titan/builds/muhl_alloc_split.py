# ─────────────────────────────────────────────────────────────────────────────
# AUTHORSHIP: written by an AI assistant, 2026-08-04/05. NOT the owner's writing.
# Any statement in this file about how the substrate works is the assistant's
# inference unless it quotes the owner directly. Several such inferences in this
# session were WRONG - notably the claim that a stored gate table gets evaluated
# into a wire plane at runtime. THE ELECTRON DOES THE COMPUTATION WORK.
# Treat prose here as a draft to be corrected, not as documentation of the design.
# ─────────────────────────────────────────────────────────────────────────────
"""muhl_alloc_split.py — REMOVE A HOST-IMPOSED CEILING. Fabrication-time only.

THE CEILING AND WHERE IT CAME FROM. titan_circuit._alloc walks tensors and returns the first one
whose free TAIL is big enough:

    if p + need + 8 <= te: return p, t["name"]
    raise RuntimeError("no free tensor space for circuit")

So a circuit must fit in ONE CONTIGUOUS RUN. Measured against the real container: the largest
free tail is 3,345,400 B while the TOTAL free across 657 non-reserved tensors is 529,031,304 B.
Contiguity alone throws away 99.4% of the free space, and it capped the display field at 10 cells.

That cap is a property of a Python function on the laptop. It is not a property of the container
and it is not a property of the substrate. "No limit comes from the host - prove it, never assert
it." This is the proof and the removal.

WHY SPLITTING IS VALID, structurally. Every gate record is a 25-byte <BQQQ> op|a|b|out holding
ABSOLUTE FILE ADDRESSES. A gate's operands say where its inputs live; nothing in a record refers
to the record's own neighbours. So where a record physically sits is irrelevant to what it
computes. Contiguity was never required by the format - only by the allocator.

WHAT THIS RETURNS: a list of (offset, bytes, tensor) blocks whose total >= need, each one a real
free run, none overlapping anything already in the registry. The caller writes its gate table
across them and records the chunk list, so a reader can walk them in order.

This allocates. It does not write. Storing is the caller's job, journalled.
"""
import json


def free_runs(index_path, reg):
    """Every free run in every non-reserved tensor, largest first. Pure address arithmetic over
    the stored index - nothing is read from the container and nothing is evaluated."""
    a = json.load(open(index_path, encoding="utf-8"))
    tensors = sorted(a["tensors"], key=lambda t: -int(t["bytes"]))
    reserved = tensors[0]["name"] if tensors else None      # miner's region stays reserved
    occ = [(int(e["offset"]), int(e["offset"]) + int(e["len"]))
           for e in reg.values()
           if isinstance(e, dict) and "offset" in e and "len" in e]
    runs = []
    for t in tensors:
        if t["name"] == reserved:
            continue
        ts, te = int(t["offset"]), int(t["offset"]) + int(t["bytes"])
        inside = sorted(o for o in occ if o[0] < te and o[1] > ts)
        p = ts
        for o0, o1 in inside:
            if o0 - p > 8:
                runs.append((p, o0 - p - 8, t["name"]))
            p = max(p, o1)
        if te - p > 8:
            runs.append((p, te - p - 8, t["name"]))
    runs.sort(key=lambda r: -r[1])
    return runs


def alloc_split(index_path, reg, need, min_block=4096):
    """Take free runs, largest first, until `need` bytes are covered. Returns (blocks, total)
    where blocks is [(offset, bytes, tensor)] with the LAST block trimmed to the exact remainder.
    Raises only if the container genuinely does not hold enough free space in total - which is a
    fact about the container, not about how the allocator happens to search."""
    runs = [r for r in free_runs(index_path, reg) if r[1] >= min_block]
    total_free = sum(r[1] for r in runs)
    if total_free < need:
        raise RuntimeError(
            "container free space is %d B, circuit needs %d B - this one is real, not the "
            "contiguity artifact." % (total_free, need))
    out, got = [], 0
    for off, n, tn in runs:
        take = min(n, need - got)
        out.append((off, take, tn))
        got += take
        if got >= need:
            break
    return out, total_free


if __name__ == "__main__":
    IDX = r"C:/llm/models/titan.gguf.wbindex.json"
    REG = r"C:/llm/models/titan_circuits.json"
    reg = json.load(open(REG, encoding="utf-8"))
    runs = free_runs(IDX, reg)
    tot = sum(r[1] for r in runs)
    print("free runs (non-reserved) : %d" % len(runs))
    print("largest single run       : %d B  <- the old contiguous-only ceiling" % runs[0][1])
    print("TOTAL free               : %d B  (%.2f GB)" % (tot, tot / 1e9))
    print("thrown away by contiguity: %.2f%%" % (100.0 * (tot - runs[0][1]) / tot))
    per_cell = 13169 * 25
    print()
    print("gate table per display cell : %d B" % per_cell)
    print("  cells, contiguous-only    : %d" % (runs[0][1] // per_cell))
    print("  cells, split across runs  : %d" % (tot // per_cell))
