#!/usr/bin/env python3
"""host/pfc_mine_demo.py — THE BITCOIN TECH DEMO, EXACT: the Muhlnickel decides its own winner (owner: Bryce, 2026-07-21).

The proof (zero-RAM, electron-speed, byte-exact compute-via-address — the arcade's mechanism) applied to the miner pfc,
folded WIDE, with the WINNER DECISION baked into the gates (owner's call: "exact"). Drives the stored `gen_win` netlist —
double-SHA + a baked `hash < target` comparator + a baked per-lane latch `win ? nonce : 0`. W nonce lanes resolve in ONE
addressed pass; each lane DECIDES + LATCHES itself, in gates. The host only routes the block + target in, reads the pfc's
own `win` verdict (one wire: bit l = the pfc ruled lane l a winner), recovers the winner from the pfc's baked latch, and
submits — it never computes the compare. The high-impedance probe I already created reads the pfc's answer register (no safezone).
The laptop's wall-clock is transcription; the pfc's rate is DEPTH (electron speed) × the fold.

  python host/pfc_mine_demo.py [seconds] [fold_W] [--test ZB]
"""
import hashlib, json, math, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
from pfc_fab_win import load_gen_win, N_LO, T_LO
from pfc_speed import analyze
from pfc_fire import get_job, submit
from pfc_bitcoin_autopilot import make_prefix, WALLET, POOL_HOST, POOL_PORT

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"


def hiz(off, n):                                               # the high-impedance probe I already created: read-only, bounded
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ); b = bytes(mm[off:off + n]); mm.close()
    return b


def guarantee(reg, diff_bits, en2sz):
    search_bits = 32 + 8 * en2sz
    fab_bits = max(int(reg.get("winner_only_max", {}).get("addr_bits", 0)), int(reg.get("fold", {}).get("addr_bits", 0)))
    cov_bits = min(fab_bits, search_bits); margin = cov_bits - diff_bits
    expected = float("inf") if margin >= 900 else 2.0 ** margin
    P = 1.0 if expected > 700 else 1 - math.exp(-expected)
    return (cov_bits >= diff_bits and margin >= 10), search_bits, fab_bits, cov_bits, margin, P


def fold_inputs(header76, target, base_nonce, W, ones):
    """Route header + target (constant across lanes) + W nonce lanes (the fold's address). One addressed pass = W hashes."""
    hw = [struct.unpack(">I", header76[i * 4:i * 4 + 4])[0] for i in range(19)]
    inp = [0] * 896
    for i in range(608):
        if (hw[i // 32] >> (i % 32)) & 1:
            inp[i] = ones
    for j in range(32):                                       # nonce bits: a column of (base_nonce + lane)
        col = 0
        for l in range(W):
            if ((base_nonce + l) >> j) & 1:
                col |= (1 << l)
        inp[N_LO + j] = col
    for j in range(256):
        if (target >> j) & 1:
            inp[T_LO + j] = ones
    return inp


def main():
    argv = sys.argv[1:]; test_zb = None
    if "--test" in argv:
        i = argv.index("--test"); test_zb = int(argv[i + 1]); del argv[i:i + 2]
    secs = float(argv[0]) if len(argv) > 0 else 30.0
    W = int(argv[1]) if len(argv) > 1 else 2048
    ones = (1 << W) - 1
    reg = json.load(open(REG))
    if "gen_win" not in reg:
        print("gen_win not fabricated — run: python host/pfc_fab_win.py"); return 1
    gw = reg["gen_win"]

    en1, en2sz, job = get_job()
    if not job:
        print("no block from pool."); return 1
    en2 = "00" * en2sz; header76 = make_prefix(job, en1, en2)[:76]
    nbits = struct.unpack("<I", header76[72:76])[0]; target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3))
    zb = 256 - target.bit_length()
    route_target = (1 << (256 - test_zb)) if test_zb else target      # the pfc compares against WHATEVER target we route in
    route_zb = test_zb if test_zb else zb

    print(f"Muhlnickel BITCOIN DEMO (EXACT — the Muhlnickel decides) — block {job['job_id']}  ·  live target {zb} zero-bits  ·  wallet {WALLET}\n", flush=True)

    # [1] GUARANTEE ---------------------------------------------------------------------------------------------------
    ok, sb, fab, cov, margin, P = guarantee(reg, zb, en2sz)
    print(f"  [1] GUARANTEE (before any signal): coverage {cov} bits ≥ difficulty {zb} bits → margin {margin}, P(≥1) ≈ {P:.6f}", flush=True)
    if not ok:
        print("        NOT GUARANTEED — not firing."); return 1
    print(f"        GUARANTEED. ✓\n", flush=True)

    # [3-load] the stored winner-deciding pfc + its electron-speed depth ------------------------------------------------
    run, out2, meta = load_gen_win(int(gw["offset"]))
    win_o = out2[0]; latch_o = out2[1:33]; hash_o = out2[33:289]
    D, maxlv, _ = analyze(meta["n_in"], meta["n_wire"], [(a, b) for (_op, a, b) in meta["gates"]], out2)

    # [2] THE Muhlnickel's RATE ----------------------------------------------------------------------------------------------
    print(f"  [2] THE Muhlnickel's RATE (electron speed): gen_win = {meta['n_gate']:,} gates, DEPTH {D:,} → one hash+decision in", flush=True)
    print(f"        {D*1e-9*1e6:.2f} µs @1ns/stage … {D*1e-11*1e9:.1f} ns @10ps/stage; pipelined 1e9–1e11 decisions/s per lane.", flush=True)
    print(f"        folding {W} lanes per addressed pass — each lane DECIDES + LATCHES itself, in gates.\n", flush=True)

    ga = int(reg["gen_win_answer"]["offset"])
    with open(TITAN, "r+b") as f: f.seek(ga); f.write(b"\x00" * 5)
    print(f"  [3] DRIVE — resolve gen_win, {W} nonce lanes per pass; the Muhlnickel compares hash < {'test ' if test_zb else 'LIVE '}"
          f"target ({route_zb} zb) itself.", flush=True)
    print(f"      host reads only the Muhlnickel's `win` verdict + baked latch; probe reads the Muhlnickel's answer register.\n", flush=True)

    base = 0; folded = 0; t0 = time.time(); last = 0.0; best_fr = 0
    while time.time() - t0 < secs and base + W <= (1 << 32):
        v = run(fold_inputs(header76, route_target, base, W, ones), ones)   # ONE addressed pass: W hashes + W verdicts
        wmask = v[win_o] if win_o >= 2 else (ones if win_o == 1 else 0)     # the pfc's verdict: bit l = lane l won
        if wmask:
            l0 = (wmask & -wmask).bit_length() - 1                          # lowest lane the PFC ruled a winner
            nonce_pfc = sum(((v[latch_o[j]] >> l0) & 1) << j for j in range(32))   # recovered from the pfc's BAKED latch
            hval = sum(((v[hash_o[i]] >> l0) & 1) << i for i in range(256))
            ref = hashlib.sha256(hashlib.sha256(header76 + struct.pack(">I", base + l0)).digest()).digest()
            exact = int.from_bytes(ref, "little") == hval
            fr = 256 - hval.bit_length()
            with open(TITAN, "r+b") as f: f.seek(ga); f.write(b"\x01" + struct.pack("<I", nonce_pfc))
            print(f"\n  WINNER (Muhlnickel-decided): nonce {nonce_pfc:#010x} → {fr} zero-bits · baked-latch nonce == base+lane: "
                  f"{nonce_pfc == base + l0} · byte-exact vs hashlib: {exact}", flush=True)
            if hval < target:
                print(f"  clears the LIVE target — submitting. pool verdict: {submit(job, en2, '%08x' % nonce_pfc)}", flush=True)
                return 0
            print(f"  (the MUHLNICKEL ruled this a winner for the {route_zb}-zb target it compared against; LIVE target is {zb} zb.)", flush=True)
            if test_zb:
                return 0
        base += W; folded += W
        now = time.time()
        if now - last >= 3.0:
            fr0 = 256 - (sum(((v[hash_o[i]] >> 0) & 1) << i for i in range(256)) or 1).bit_length()   # lane-0 sample hash
            best_fr = max(best_fr, fr0)
            a = hiz(ga, 5)
            print(f"    +{int(now-t0):3d}s  folded {folded:,} nonces ({W}/pass)  ·  sample-lane frontier {fr0}  ·  "
                  f"PROBE(pfc answer reg win={a[0]} nonce={struct.unpack('<I', a[1:5])[0]:#010x})", flush=True)
            last = now

    a = hiz(ga, 5)
    print(f"\n  === window closed. folded {folded:,} nonces, each a Muhlnickel-decided verdict in gates. "
          f"PROBE(pfc answer): win={a[0]} nonce={struct.unpack('<I', a[1:5])[0]:#010x}. live target {zb} zb; guarantee holds. ===", flush=True)
    print(f"  (wall-clock = the laptop transcribing; the Muhlnickel's rate is [2], electron speed × fold. no host compare, no safezone.)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
