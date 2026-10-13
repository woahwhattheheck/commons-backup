#!/usr/bin/env python3
"""Independent adversarial re-check of wf_forge_ram.py. Fresh ground-truth reference, edge cases the
builder may have skipped: all-zeros, all-ones, max address, we=0 hold, write-doesn't-corrupt-neighbors,
read-doesn't-mutate. Pure Python, read-only on the forge (imports it)."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wf_forge_ram import build_ram, tick, cell_label
sys.stdout.reconfigure(encoding="utf-8")


def fresh_state(k, w):
    nwords = 1 << k
    return {cell_label(word, bit): 0 for word in range(nwords) for bit in range(w)}


def run_suite(k, w, seed):
    random.seed(seed)
    c, meta = build_ram(k, w)
    nwords, mask = 1 << k, (1 << w) - 1
    st = fresh_state(k, w)
    ref = [0] * nwords          # my OWN independent reference model (plain list)
    checks = 0; bad = 0
    fails = []

    def do_write(addr, val):
        nonlocal st
        ref[addr] = val & mask
        _, st = tick(c, st, k, w, addr, we=1, data=val)

    def do_read(addr, note=""):
        nonlocal st, checks, bad
        got, st = tick(c, st, k, w, addr, we=0, data=0)
        checks += 1
        if got != ref[addr]:
            bad += 1; fails.append((note, addr, got, ref[addr]))
        return got

    # --- edge 1: everything starts at 0 ---
    for a in range(nwords): do_read(a, "init-zero")

    # --- edge 2: all-ones to max address, verify neighbors stay 0 ---
    do_write(nwords - 1, mask)
    for a in range(nwords): do_read(a, "maxaddr-allones-neighbors")

    # --- edge 3: all-ones everywhere, then all-zeros to addr 0 only ---
    for a in range(nwords): do_write(a, mask)
    for a in range(nwords): do_read(a, "all-ones")
    do_write(0, 0)
    for a in range(nwords): do_read(a, "zero-addr0-only")   # only addr0 should flip

    # --- edge 4: we=0 must NOT write (drive data+addr but hold) ---
    do_write(1 % nwords, mask)                 # set a known value
    before = ref[1 % nwords]
    _, st = tick(c, st, k, w, 1 % nwords, we=0, data=(~mask) & mask)  # try to overwrite with we=0
    got = do_read(1 % nwords, "we0-hold")      # ref unchanged -> must still equal 'before'
    if got != before:
        bad += 1; fails.append(("we0-should-not-write", 1 % nwords, got, before))

    # --- edge 5: write-doesn't-corrupt: write distinct value per address, read all back ---
    for a in range(nwords): do_write(a, (a * 0x9E37 + 0x5A) & mask)
    for a in range(nwords): do_read(a, "distinct-per-addr")

    # --- edge 6: 800 fully-random interleaved ops vs my reference ---
    for _ in range(800):
        a = random.randrange(nwords)
        if random.random() < 0.5:
            do_write(a, random.getrandbits(w))
        else:
            do_read(a, "random-mix")

    return c, meta, checks, bad, fails


def main():
    print("INDEPENDENT ADVERSARIAL RE-CHECK of wf_forge_ram.py\n")
    total_bad = 0
    for (k, w, seed) in [(3, 4, 12345), (5, 4, 999), (2, 3, 7), (1, 1, 3)]:
        c, meta, checks, bad, fails = run_suite(k, w, seed)
        verdict = "PASS" if bad == 0 else f"FAIL ({bad})"
        print(f"  {c.name:10s}: {c.n_gates():>5} gates depth {c.depth():>3} | "
              f"{checks:>4} addressed read-checks -> {verdict}")
        for f in fails[:6]:
            print(f"      MISMATCH {f}")
        total_bad += bad
    print(f"\n  {'ALL PASS' if total_bad == 0 else f'{total_bad} MISMATCHES'} "
          f"across edge cases + random mix, vs a fresh independent reference.")
    return 0 if total_bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
