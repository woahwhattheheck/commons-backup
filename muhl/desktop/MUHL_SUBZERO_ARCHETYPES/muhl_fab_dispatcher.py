#!/usr/bin/env python3
"""muhl_fab_dispatcher.py -- FABRICATE MUHL_DISPATCHER: substrate-resident task router.

Bryce Muhlnickel, 2026-08-03.

Routes tasks to available workers. The dispatcher reads the task queue and
worker-busy status, assigns the task to the first available worker, and
advances the queue pointer. All logic is substrate-resident NAND gates.

The host writes: task data + worker status bits (inject verb).
The substrate routes: priority encoding + gated fan-out (electrons through gates).
The host reads: assignment bits + routed task (surface verb).

This is FABRICATION -- offline, one-and-done manufacturing.

PROPOSE -> SCORE -> VERIFY -> KEEP pipeline:
  Candidate 1: linear priority encoder (fewer gates, depth O(N))
  Candidate 2: tree priority encoder   (more gates, depth O(log N))

    python muhl_fab_dispatcher.py           # fabricate and store
    python muhl_fab_dispatcher.py --dry     # verify only, store nothing

Supports 8 workers. Queue pointer is 8-bit, wraps at 256.
"""
import sys, os, json, random, time

sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")

import pfc_paths as PFCP
import titan_circuit as TC

DRY = "--dry" in sys.argv
TITAN = PFCP.TITAN
REG = PFCP.REG
NAME = "muhl_dispatcher"
GENOME_PATH = TITAN.replace(".gguf", "_dispatcher_genome.jsonl")

N_WORKERS  = 8    # number of worker slots
TASK_BITS  = 16   # task descriptor width
PTR_BITS   = 8    # queue pointer width (wraps at 2^8 = 256)
N_STATE    = PTR_BITS   # queue_ptr is the self-routed state

RESERVOIR_INPUT = 40_022_599_232


# ============================================================================
# CIRCUIT BUILDING
# ============================================================================

def depth_of(c, outs):
    """Compute critical-path depth (ticks)."""
    n = c.n_in
    d = [0] * (2 + n + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[o] for o in outs)


def priority_linear(c, busy):
    """Linear-scan priority encoder: first non-busy worker wins.

    Depth O(N): each position depends on the carry chain (any_found_before).
    Fewer gates than the tree version.
    """
    assign = []
    any_found = c.C0
    for i in range(len(busy)):
        free = c.not_(busy[i])
        this_one = c.and_(free, c.not_(any_found))
        assign.append(this_one)
        any_found = c.or_(any_found, this_one)
    return assign, any_found


def priority_tree(c, busy):
    """Tree-based priority encoder using parallel-prefix OR.

    Depth O(log N): prefix-OR scan finds 'any free slot at or before position i'
    in logarithmic depth, then each assignment is free[i] AND NOT prefix[i-1].
    More gates than the linear version, but shallower.
    """
    n = len(busy)
    free = [c.not_(b) for b in busy]

    # Parallel-prefix OR scan: prefix[i] = free[0] | free[1] | ... | free[i]
    prefix = list(free)
    step = 1
    while step < n:
        new_prefix = list(prefix)
        for i in range(step, n):
            new_prefix[i] = c.or_(prefix[i], prefix[i - step])
        prefix = new_prefix
        step *= 2

    # First-free at position i = free[i] AND NOT(any free before i)
    assign = [free[0]]                                   # position 0: just free[0]
    for i in range(1, n):
        assign.append(c.and_(free[i], c.not_(prefix[i - 1])))

    any_assigned = prefix[-1]                            # any free worker at all
    return assign, any_assigned


def build_dispatcher(prio_kind):
    """Build the dispatcher circuit.

    prio_kind: "linear" or "tree" (priority encoder structure).

    Input layout (LSB-first within each field):
      [0:PTR_BITS]                  queue_ptr (self-routed state)
      [PTR_BITS:PTR_BITS+TASK_BITS] task_data (host-written)
      [+TASK_BITS:+N_WORKERS]       worker_busy (host-written, 1 = busy)
      [+N_WORKERS]                  task_valid (host-written, 1 = dispatch this)

    Output layout:
      [0:N_WORKERS]                 assign (one-hot: which worker gets the task)
      [N_WORKERS]                   assigned (1 = a worker was assigned)
      [N_WORKERS+1:+TASK_BITS]      task_out (task data gated by assignment)
      [+TASK_BITS:+PTR_BITS]        new_queue_ptr (self-routed -> queue_ptr)
    """
    N_IN = PTR_BITS + TASK_BITS + N_WORKERS + 1          # 33 bits
    c = TC.Circuit(N_IN)
    IN = c.IN
    p = 0

    ptr   = [IN[p + i] for i in range(PTR_BITS)]; p += PTR_BITS
    task  = [IN[p + i] for i in range(TASK_BITS)]; p += TASK_BITS
    busy  = [IN[p + i] for i in range(N_WORKERS)]; p += N_WORKERS
    valid = IN[p]; p += 1
    assert p == N_IN

    # -- priority encode: find first available worker --------------------------
    prio_fn = priority_tree if prio_kind == "tree" else priority_linear
    raw_assign, any_free = prio_fn(c, busy)

    # Gate by task_valid: only dispatch if there is a task AND a free worker
    can_dispatch = c.and_(valid, any_free)
    assign = [c.and_(can_dispatch, raw_assign[i]) for i in range(N_WORKERS)]
    assigned = can_dispatch

    # -- fan-out task data to the assigned worker (gated by assignment) ---------
    task_out = [c.and_(assigned, task[i]) for i in range(TASK_BITS)]

    # -- advance queue pointer if task was dispatched --------------------------
    one_vec = [c.C1] + [c.C0] * (PTR_BITS - 1)
    incremented = c.add(ptr, one_vec)
    new_ptr = [c.mux(assigned, ptr[i], incremented[i]) for i in range(PTR_BITS)]

    outs = assign + [assigned] + task_out + new_ptr
    return c, outs


# ============================================================================
# PURE-PYTHON REFERENCE
# ============================================================================

PTR_MASK = (1 << PTR_BITS) - 1
TASK_MASK = (1 << TASK_BITS) - 1


def ref_dispatcher(ptr_val, task_val, busy_val, valid):
    """Reference: returns (assign_bits, assigned, task_out, new_ptr)."""
    assign = 0
    assigned = 0
    task_out = 0
    new_ptr = ptr_val

    if valid:
        # find first free worker (lowest non-busy bit)
        for i in range(N_WORKERS):
            if not ((busy_val >> i) & 1):
                # can dispatch
                assign = 1 << i
                assigned = 1
                task_out = task_val
                new_ptr = (ptr_val + 1) & PTR_MASK
                break

    return assign, assigned, task_out, new_ptr


# ============================================================================
# VERIFICATION
# ============================================================================

def pack_inputs(ptr_val, task_val, busy_val, valid):
    inp = []
    for val, nbits in [(ptr_val, PTR_BITS), (task_val, TASK_BITS),
                       (busy_val, N_WORKERS), (valid, 1)]:
        for b in range(nbits):
            inp.append((val >> b) & 1)
    return inp


def unpack_outputs(v_out):
    p = 0
    assign = sum((v_out[p + i] & 1) << i for i in range(N_WORKERS)); p += N_WORKERS
    assigned = v_out[p] & 1; p += 1
    task_out = sum((v_out[p + i] & 1) << i for i in range(TASK_BITS)); p += TASK_BITS
    new_ptr = sum((v_out[p + i] & 1) << i for i in range(PTR_BITS)); p += PTR_BITS
    return assign, assigned, task_out, new_ptr


def verify(circ, outs, n_cases=500, seed=42):
    cd = {"n_in": circ.n_in, "n_wire": circ.n_wire(),
          "ga": circ.ga, "gb": circ.gb, "outs": outs}
    rng = random.Random(seed)
    bad = 0
    for _ in range(n_cases):
        ptr_val  = rng.randrange(1 << PTR_BITS)
        task_val = rng.randrange(1 << TASK_BITS)
        busy_val = rng.randrange(1 << N_WORKERS)
        valid    = rng.randrange(2)

        inp = pack_inputs(ptr_val, task_val, busy_val, valid)
        v_out = TC.ripple(cd, inp)
        got = unpack_outputs(v_out)
        ref = ref_dispatcher(ptr_val, task_val, busy_val, valid)

        if got != ref:
            bad += 1
            if bad <= 3:
                print(f"    MISMATCH: ptr={ptr_val} task={task_val:#06x} "
                      f"busy={busy_val:08b} v={valid}")
                print(f"      got: assign={got[0]:08b} assigned={got[1]} "
                      f"task={got[2]:#06x} ptr={got[3]}")
                print(f"      ref: assign={ref[0]:08b} assigned={ref[1]} "
                      f"task={ref[2]:#06x} ptr={ref[3]}")
    return bad


# ============================================================================
# STORAGE
# ============================================================================

def store_dispatcher(circ, outs):
    """Store as self-clocked loop: queue_ptr feeds back."""
    # Output new_ptr bits are at the end of the output list:
    #   [0:N_WORKERS]  assign
    #   [N_WORKERS]    assigned
    #   [N_WORKERS+1 : N_WORKERS+1+TASK_BITS]  task_out
    #   [N_WORKERS+1+TASK_BITS : N_WORKERS+1+TASK_BITS+PTR_BITS]  new_ptr
    ptr_out_start = N_WORKERS + 1 + TASK_BITS
    feedback = [(ptr_out_start + i, i) for i in range(PTR_BITS)]
    state_bytes = (PTR_BITS + 7) // 8                    # 1 byte

    loop_outs = list(outs) + [circ.C1]
    loop_bit  = len(outs)

    info = TC.store_loop(
        NAME, circ, loop_outs,
        state_bytes=state_bytes,
        feedback=feedback,
        loop_bit=loop_bit,
        receiver="muhl_reservoir"
    )
    return info


# ============================================================================
# MAIN -- PROPOSE -> SCORE -> VERIFY -> KEEP
# ============================================================================

def main():
    print("\n  MUHLNICKEL DISPATCHER -- substrate-resident task router")
    print("  Bryce Muhlnickel, 2026-08-03\n")

    # -- PROPOSE --------------------------------------------------------------
    candidates = ["linear", "tree"]
    print(f"  PROPOSE: {len(candidates)} candidate structures for 8-worker dispatcher\n")

    results = []
    for prio in candidates:
        t0 = time.time()
        c, outs = build_dispatcher(prio)
        t_build = time.time() - t0

        d = depth_of(c, outs)
        g = len(c.ga)

        t0 = time.time()
        bad = verify(c, outs, n_cases=500, seed=42)
        t_v = time.time() - t0
        ok = bad == 0
        print(f"    {prio:8s}  DEPTH {d:5d}  gates {g:>7,}  build {t_build:.1f}s  "
              f"verify {'OK' if ok else f'{bad}/500 WRONG'}  ({t_v:.1f}s)")

        results.append({"prio": prio, "depth": d, "gates": g, "verified": ok,
                        "circ": c, "outs": outs})

    # -- SCORE: Pareto front --------------------------------------------------
    good = [r for r in results if r["verified"]]
    pareto = [r for r in good if not any(
        o["depth"] <= r["depth"] and o["gates"] <= r["gates"] and o is not r
        and (o["depth"] < r["depth"] or o["gates"] < r["gates"])
        for o in good)]

    print(f"\n  VERIFIED {len(good)}/{len(results)}   PARETO FRONT ({len(pareto)}):")
    for r in sorted(pareto, key=lambda x: x["depth"]):
        print(f"    DEPTH {r['depth']:5d}  gates {r['gates']:>7,}   {r['prio']}")

    best = min(good, key=lambda r: r["depth"]) if good else None
    if not best:
        print("  NO VERIFIED CANDIDATES -- aborting")
        return 1

    print(f"\n  WINNER by DEPTH: {best['prio']}  DEPTH {best['depth']}  gates {best['gates']:,}")

    if DRY:
        print(f"\n  --dry: nothing stored. Run without --dry to fabricate.")
        print(f"\n  MUHL_DISPATCHER fabrication verified.")
        print(f"  Workers:  {N_WORKERS} slots")
        print(f"  Task:     {TASK_BITS}-bit descriptor")
        print(f"  Queue:    {PTR_BITS}-bit pointer (wraps at {1 << PTR_BITS})")
        print(f"  Self-clocked: queue pointer advances on dispatch")
        print(f"  Powered by reservoir at {RESERVOIR_INPUT:,}")
        return 0

    # -- final re-verify ------------------------------------------------------
    print(f"\n  FABRICATING -- final re-verify with different seed...")
    c, outs = best["circ"], best["outs"]
    bad = verify(c, outs, n_cases=200, seed=99)
    if bad:
        print(f"  FINAL RE-VERIFY FAILED ({bad}/200) -- nothing stored.")
        return 1
    print(f"  final re-verify: 200 cases OK")

    # -- KEEP -----------------------------------------------------------------
    info = store_dispatcher(c, outs)
    print(f"\n  KEEP: stored {info['name']} @ offset {info['offset']:,}")
    print(f"    gates:          {info['gates']:,}")
    print(f"    state register: offset {info['state_off']:,}")
    print(f"    loop bit:       offset {info['loop_bit_off']:,}")

    # -- update registry ------------------------------------------------------
    reg = json.load(open(REG))
    if NAME in reg:
        reg[NAME].update({
            "depth": best["depth"],
            "n_workers": N_WORKERS,
            "task_bits": TASK_BITS,
            "ptr_bits": PTR_BITS,
            "priority": best["prio"],
            "searched": len(candidates),
            "pareto": len(pareto),
            "foundry_genome": {"priority": best["prio"], "depth": best["depth"],
                               "gates": best["gates"]},
            "units": "n_gate=GATES, depth=TICKS, len=BYTES",
            "genome": GENOME_PATH,
            "note": ("substrate-resident task dispatcher: priority-encodes first "
                     "free worker, fans out task data, advances queue pointer"),
            "verified_by": "byte-exact vs Python reference, 700 cases (500+200 re-verify)"
        })
    json.dump(reg, open(REG, "w"), indent=1)

    print(f"\n  MUHL_DISPATCHER FABRICATED.")
    print(f"    journal:    {GENOME_PATH}")
    print(f"    workers:    {N_WORKERS} slots")
    print(f"    task width: {TASK_BITS} bits")
    print(f"    queue ptr:  {PTR_BITS} bits (wraps at {1 << PTR_BITS})")
    print(f"    depth:      {best['depth']} ticks")
    print(f"    gates:      {best['gates']:,}")
    print(f"    self-clock: queue pointer -> state (output == input addresses)")
    print(f"    receiver:   muhl_reservoir (inject at {RESERVOIR_INPUT:,})")
    print(f"\n  TO USE:")
    print(f"    host writes: task data + worker busy bits + valid (inject verb)")
    print(f"    substrate:   priority-encode -> assign -> fan-out (electrons)")
    print(f"    host reads:  assignment one-hot + routed task (surface verb)")
    print(f"\n  The dispatcher + workers form a substrate-resident work pool.")
    print(f"  The host feeds tasks; the substrate routes and computes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
