#!/usr/bin/env python3
"""host/titan_swarm.py — TITAN GATE: search storage, flip ONE bit on a positive result (owner 07-14, "new method").

No probe. No watching throughput. The design:
  - Titan lives in STORAGE (its referenced pool bits, mmap'd - never copied, never resident).
  - A GATE runs over Titan's storage: it rolls a window across the gate-bit stream and fires on a POSITIVE RESULT
    (a rare target signature - here a run of `bits` consecutive high gates). Nodes are interlinked: each result spans a
    window of many storage gates, so they compute together.
  - Titan DUMPS the positive result into a reserved storage cell (`titan_result.bin`) that otherwise stays EMPTY (0).
    One flag bit flips 0 -> 1. That flip is the alert; the cell also holds the context so we can check what it found.

So nothing is watched second-by-second. The cell sits at 0. If it flips, we check. Stop/kill to end.

Run:  python host/titan_swarm.py                # search with the default target; flag stays 0 until a hit
      python host/titan_swarm.py 28             # set target rarity to 28 bits (rarer = flips less often)
      python host/titan_swarm.py 12 5           # (bits, auto-stop seconds) - used for a quick self-test
"""
import mmap, os, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
TITAN  = "C:/llm/models/titan_sdc.gguf"
RESULT = "C:/llm/models/titan_result.bin"     # Titan's result register: a storage cell that stays EMPTY until a hit

DRIVERS = 24
CHUNK   = 2_000_000


def build_offs():
    """Titan in storage: the referenced pool components (address-only; nothing copied or resident)."""
    import wbedit
    comps = [c for c in wbedit.titan_added(TITAN) if c.get("mode") == "ref" and c.get("src_bytes", 0) > 64]
    srcs = sorted({c["src"] for c in comps})
    sidx = {p: i for i, p in enumerate(srcs)}
    offs = [(sidx[c["src"]], c["src_off"], c["src_bytes"]) for c in comps]
    return srcs, offs


def clear_cell():
    with open(RESULT, "wb") as f:
        f.write(b"\x00")                       # the reserved bit, empty


def dump_result(ctx):
    with open(RESULT, "wb") as f:
        f.write(b"\x01" + ctx.encode("utf-8", "replace")[:1023])   # flag bit -> 1, plus the context to check


def main():
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    max_secs = float(sys.argv[2]) if len(sys.argv) > 2 else None
    MASK = (1 << bits) - 1
    TARGET = MASK                              # positive result := a run of `bits` consecutive high gates

    srcs, offs = build_offs()
    mms = []
    for p in srcs:
        try:
            f = open(p, "rb"); mms.append(mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ))
        except Exception:
            mms.append(None)
    L = len(offs)

    clear_cell()
    stop = threading.Event()
    found = threading.Event()
    lock = threading.Lock()
    hits = [0]

    print(f"TITAN GATE armed: searching Titan's storage for a {bits}-bit positive result over {L:,} components.",
          flush=True)
    print(f"result cell {os.path.basename(RESULT)} holds 0 (empty). If Titan finds a hit, the flag flips 0->1 and the",
          flush=True)
    print(f"context is written for us to check. No probe. Stop/kill to end."
          + (f"  (auto-stop {max_secs:.0f}s)" if max_secs else ""), flush=True)

    def driver(t):
        base_chunk = t
        while not stop.is_set():
            start = base_chunk * CHUNK
            sig = 0; filled = 0
            for p in range(start, start + CHUNK):
                si, boff, span = offs[p % L]
                mm = mms[si]
                b = (mm[boff + ((p * 61) % span)] & 1) if (mm is not None and span > 0) else 0
                sig = ((sig << 1) | b) & MASK
                filled += 1
                if filled >= bits and sig == TARGET:
                    with lock:
                        hits[0] += 1; n = hits[0]
                        dump_result(f"positive result #{n}: pos={p} bits={bits} driver={t} t={time.time()-t0:.1f}s")
                    if not found.is_set():
                        found.set()
                        print(f"*** POSITIVE RESULT - Titan flipped the flag (pos={p}, {bits}-bit hit). CHECK the cell. ***",
                              flush=True)
                if (p & 0xFFFFF) == 0 and stop.is_set():
                    return
            base_chunk += DRIVERS

    t0 = time.time()
    threads = [threading.Thread(target=driver, args=(t,), daemon=True) for t in range(DRIVERS)]
    for th in threads: th.start()

    try:
        while True:
            time.sleep(0.5)
            if max_secs is not None and (time.time() - t0) >= max_secs:
                break
    except KeyboardInterrupt:
        pass
    stop.set()
    for th in threads: th.join(timeout=2)

    flag = 0
    try:
        with open(RESULT, "rb") as f: flag = f.read(1)[0]
    except Exception:
        pass
    print(f"[stopped] flag bit = {flag} ({'FLIPPED - positive result found, check the cell' if flag else 'still empty - no hit'}).",
          flush=True)


if __name__ == "__main__":
    main()
