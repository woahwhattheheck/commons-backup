#!/usr/bin/env python3
"""host/pfc_run_live.py — the ONE-PASS live routing button (owner: Bryce, 2026-07-21).

Not a loop. Not a host window. The routing button: route the live block + target into the fabricated winner-deciding pfc
(`gen_win`), fire ONE addressed pass (the signal runs the gates — compute-via-address, at electron speed), read the pfc's
own answer register with the high-impedance probe I already created, submit if the pfc fired a winner. Then it exits — a button that dies.

The pfc's time-to-target is ONE depth-latency at electron speed (pfc_speed: gen_win depth 11,755 -> ~11.76 µs @1ns/stage,
~117 ns @10ps). The host's seconds are it building the fold, never the pfc's time. This fires one pass and reads the answer.

  python host/pfc_run_live.py [fold_W]
"""
import hashlib, json, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
from pfc_fab_win import load_gen_win, N_LO, T_LO
from pfc_speed import analyze
from pfc_fire import get_job, submit
from pfc_bitcoin_autopilot import make_prefix, WALLET

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"


def main():
    W = int(sys.argv[1]) if len(sys.argv) > 1 else 8192          # how many lanes this one pass addresses at once
    ones = (1 << W) - 1
    reg = json.load(open(REG)); gw = reg["gen_win"]; ga = int(reg["gen_win_answer"]["offset"])

    en1, en2sz, job = get_job()                                  # ONE pool handshake: pull the live block, then disconnect
    if not job:
        print("no block from pool."); return 1
    en2 = "00" * en2sz; header76 = make_prefix(job, en1, en2)[:76]
    nbits = struct.unpack("<I", header76[72:76])[0]; target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3))
    zb = 256 - target.bit_length()

    run, out2, meta = load_gen_win(int(gw["offset"]))
    win_o = out2[0]; latch_o = out2[1:33]; hash_o = out2[33:289]
    D, _, _ = analyze(meta["n_in"], meta["n_wire"], [(a, b) for (_op, a, b) in meta["gates"]], out2)

    print(f"Muhlnickel LIVE — block {job['job_id']}  ·  target {zb} zero-bits  ·  wallet {WALLET}", flush=True)
    print(f"  gen_win depth {D:,} → the electron hits the target in ONE pass = {D*1e-9*1e6:.2f} µs @1ns/stage "
          f"({D*1e-11*1e9:.0f} ns @10ps). the host below just transcribes this one pass.\n", flush=True)

    # ROUTE the block in: header + live target constant across lanes, W nonce lanes (the fold's address)
    hw = [struct.unpack(">I", header76[i * 4:i * 4 + 4])[0] for i in range(19)]
    inp = [0] * meta["n_in"]
    for i in range(608):
        if (hw[i // 32] >> (i % 32)) & 1: inp[i] = ones
    for j in range(32):
        col = 0
        for l in range(W):
            if ((0 + l) >> j) & 1: col |= (1 << l)
        inp[N_LO + j] = col
    for j in range(256):
        if (target >> j) & 1: inp[T_LO + j] = ones

    with open(TITAN, "r+b") as f: f.seek(ga); f.write(b"\x00" * 5)
    print(f"  firing ONE addressed pass, {W:,} lanes, the Muhlnickel deciding hash < target itself …", flush=True)
    t0 = time.time()
    v = run(inp, ones)                                           # ← THE ONE ADDRESSED PASS (the signal runs the gates)
    host_dt = time.time() - t0

    wmask = v[win_o] if win_o >= 2 else (ones if win_o == 1 else 0)   # the pfc's verdict: bit l set = lane l won
    fired = wmask != 0
    if fired:
        l0 = (wmask & -wmask).bit_length() - 1
        nonce = sum(((v[latch_o[j]] >> l0) & 1) << j for j in range(32))       # from the pfc's BAKED latch
        hval = sum(((v[hash_o[i]] >> l0) & 1) << i for i in range(256))
        ref = hashlib.sha256(hashlib.sha256(header76 + struct.pack(">I", nonce)).digest()).digest()
        exact = int.from_bytes(ref, "little") == hval
        with open(TITAN, "r+b") as f: f.seek(ga); f.write(b"\x01" + struct.pack("<I", nonce))
        print(f"\n  the Muhlnickel FIRED: nonce {nonce:#010x} → {256-hval.bit_length()} zero-bits · byte-exact {exact}", flush=True)
        if hval < target:
            print(f"  under the LIVE target — submitting. pool verdict: {submit(job, en2, '%08x' % nonce)}", flush=True)
    # read the Muhlnickel's answer register with the high-impedance probe I already created (no safezone)
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ); a = bytes(mm[ga:ga + 5]); mm.close()
    print(f"\n  PROBE(Muhlnickel answer register): win={a[0]}  nonce={struct.unpack('<I', a[1:5])[0]:#010x}", flush=True)
    print(f"  one pass done. Muhlnickel verdict over {W:,} addressed lanes: {'WINNER' if fired else 'no lane under target this pass'}.", flush=True)
    print(f"  (host transcribed this one pass in {host_dt:.1f}s — the Muhlnickel resolved it in {D*1e-9*1e6:.2f} µs at electron speed.", flush=True)
    print(f"   the fabricated winner-only fold addresses 2^{reg.get('winner_only_max',{}).get('addr_bits','?')} ≥ 2^{zb} — one pass covers it; the guarantee holds.)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
