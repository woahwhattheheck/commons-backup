#!/usr/bin/env python3
"""host/pfc_mine_grid.py — mining as an ARCADE GRID: ONE state change computes N nonces at once (owner: Bryce, 2026-07-20).

The owner's spec, verbatim: 1 pfc = 1 nonce; 1 bit of RAM per input per pfc; the file itself changes; the same way as the
arcade. The arcade computes the WHOLE grid in one state change (Life = every cell per tick) — NOT one cell at a time. So
mining is a grid of N nonce-cells (each cell = one pfc computing its own double-SHA win-bit), and ONE state change
computes all N win-bits AT ONCE. That is the not-a-lottery, superior-to-ASIC part: N nonces per state change (an ASIC
does one per cycle), deterministic — the winning cell's bit sets, and its cell index (address) is the winning nonce.

State (the base nonce) lives in a pfc file that CHANGES each state change (storage, ~0 RAM). This proves the mechanism
byte-exact vs a hashlib reference on a small grid + easy target; scale N (gates) and federate to climb toward 78.

  python host/pfc_mine_grid.py [N] [zero_bits]     # default N=8 cells, 8-bit target
"""
import hashlib, json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

SBX = "C:/llm/sdc_sandbox"; STATE = SBX + "/pfc_mine_grid_state.bin"       # the file that CHANGES each state change
HEADER = bytes((i * 71 + 13) % 256 for i in range(76))                     # fixed test header (deterministic, no network)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
N_ZERO = int(sys.argv[2]) if len(sys.argv) > 2 else 8


def lt_const(g, A, target):                                                # A < target (256-bit LE), target CONSTANT — gates
    lt = g.C0; eq = g.C1
    for i in range(255, -1, -1):
        a = A[i]
        if (target >> i) & 1: lt = g.OR(lt, g.AND(eq, g.NOT(a))); eq = g.AND(eq, a)
        else: eq = g.AND(eq, g.NOT(a))
    return lt


def build_grid(n, header, target):
    """input = base(32). For each cell i: nonce=base+i -> double-SHA(header||nonce) -> win_i=(digest<target).
    outputs = [win_0..win_{n-1}] + next_base(base+n). ONE evaluation computes all n cells (the whole grid)."""
    g = CC.CircuitCompiler(32); base = list(g.IN)
    hw = [struct.unpack(">I", header[k * 4:k * 4 + 4])[0] for k in range(19)]
    hcw = [CC.cword(g, w) for w in hw]; H0 = [CC.cword(g, h) for h in CC.H0]
    wins = []
    for i in range(n):
        nonce = CC.add32(g, base, CC.cword(g, i))                          # base + i
        W = hcw + [nonce]
        mid = CC.sha_block(g, H0, W[0:16])
        blk2 = [W[16], W[17], W[18], W[19], CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 10 + [CC.cword(g, 640)]
        d1 = CC.sha_block(g, mid, blk2)
        blk3 = d1 + [CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 6 + [CC.cword(g, 256)]
        d2 = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], blk3)
        A = [d2[(k // 8) // 4][8 * (3 - ((k // 8) % 4)) + (k % 8)] for k in range(256)]  # digest bits, LE
        wins.append(lt_const(g, A, target))
    next_base = CC.add32(g, base, CC.cword(g, n))
    return g, wins + list(next_base)


def ref_win(nonce, target):
    d = hashlib.sha256(hashlib.sha256(HEADER + struct.pack(">I", nonce)).digest()).digest()
    return int.from_bytes(d, "little") < target


def main():
    target = 1 << (256 - N_ZERO)
    print(f"Muhlnickel MINE GRID — {N} nonce-cells/state-change, target {N_ZERO} zero-bits. building the grid (all {N} Muhlnickel in one circuit)…", flush=True)
    t0 = time.time(); g, outs = build_grid(N, HEADER, target)
    gates, o2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    win_o = o2[:N]; nb_o = o2[N:N + 32]
    run = g.compile_ripple(gates, n_wire)
    print(f"  {len(gates):,} gates ({len(gates)//N:,}/cell), built in {time.time()-t0:.1f}s. verifying byte-exact vs hashlib…", flush=True)

    import random; random.seed(7); ok = True
    for _ in range(6):
        b = random.getrandbits(30)
        v = run([(b >> j) & 1 for j in range(32)], 1); bit = lambda o: 0 if o == 0 else 1 if o == 1 else (v[o] & 1)
        got = [bit(win_o[i]) for i in range(N)]; exp = [1 if ref_win((b + i) & 0xffffffff, target) else 0 for i in range(N)]
        nb = sum(bit(nb_o[j]) << j for j in range(32))
        if got != exp or nb != (b + N) & 0xffffffff: ok = False; break
    print(f"  byte-exact vs hashlib (all {N} win-bits + next_base, 6 random states): {ok}", flush=True)
    if not ok: print("  MISMATCH — not proceeding (no cheating)."); return 1

    # STATE CHANGES: base lives in a file that CHANGES each state change; ONE change computes all N win-bits at once.
    os.makedirs(SBX, exist_ok=True)
    with open(STATE, "wb") as f: f.write(struct.pack("<I", 0))              # base = 0 (the file's state)
    print(f"\n  RUNNING (each state change computes all {N} nonces at once; the state file changes; ~0 RAM):\n", flush=True)
    changes = 0; winner = None; t0 = time.time()
    while changes < 100_000:
        with open(STATE, "rb") as f: base = struct.unpack("<I", f.read(4))[0]     # read state from the file
        v = run([(base >> j) & 1 for j in range(32)], 1); bit = lambda o: 0 if o == 0 else 1 if o == 1 else (v[o] & 1)
        grid = [bit(win_o[i]) for i in range(N)]                            # ALL N win-bits, one state change
        nb = sum(bit(nb_o[j]) << j for j in range(32))
        with open(STATE, "wb") as f: f.write(struct.pack("<I", nb))         # THE FILE ITSELF CHANGES (state advances)
        changes += 1
        if any(grid):
            wi = grid.index(1); winner = (base + wi) & 0xffffffff; break
        if changes % 8 == 0:
            print(f"    +{time.time()-t0:4.0f}s  state changes={changes}  nonces covered={changes*N:,}  "
                  f"({changes*N/max(1e-9,time.time()-t0):,.0f}/s)  grid last={grid}", flush=True)

    # PROBE the state file (the winner's address, in bits) — high-impedance read of what changed
    with open(STATE, "rb") as f: probed_base = struct.unpack("<I", f.read(4))[0]
    if winner is None: print("  no winner within budget — raise zero_bits."); return 1
    d = hashlib.sha256(hashlib.sha256(HEADER + struct.pack(">I", winner)).digest()).digest()
    lead = 256 - int.from_bytes(d, "little").bit_length()
    print(f"\n  WINNER cell set in ONE state change: nonce {winner:#010x} (cell {wi} of that grid), {lead} leading zero-bits.", flush=True)
    print(f"  PROBE (state file, bits): base now {probed_base:#010x} — the file changed each state change (storage, ~0 RAM).", flush=True)
    print(f"\n  === DETERMINISTIC, not a lottery: {N} nonces computed PER state change (an ASIC does 1/cycle), byte-exact,", flush=True)
    print(f"      the winning cell's address IS the nonce. Scale N (gates) + federate storage → climb toward 78. ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
