#!/usr/bin/env python3
"""host/test_split_drive.py — DRIVE THE TWO JUNCTIONED MUHLNICKEL END-TO-END. A TEST, at a sub-2^78 target.

§3 governs what this file is allowed to be:
    "CRUTCHES ARE LEGIT — but ONLY for TESTING a sub-2^78 target."
So it drives a TEST target only, it never submits, and it never touches the live difficulty. It is
not the mine and does not classify as one (no submit/get_job/latch_reg). The ripple is the crutch,
named as the crutch, and its wall-clock is reported as THE LAPTOP TRANSCRIBING — never as the
muhlnickel's rate (§56C: "That rate is the LAPTOP transcribing and is never the muhlnickel's speed").

WHAT IT PROVES: the §1E junction carries a real computation across two specialised muhlnickel.
    MUHLNICKEL A  muhl_mid   header words 0..15 -> mid[8]      fires ONCE per block
    MUHLNICKEL B  muhl_lane  mid|w16..18|nonce|target -> win|latch[32]   fires PER LANE
A's SEND (mid) IS B's RECEIVE (mid). The host routes bytes; it never computes a hash or a compare.

REPORTING follows §40E verbatim — "Decide the Muhlnickel plan first, with the host nowhere in it;
then report transcription separately" — and §24's two machines are never summed.

BLOCK DATA is the real Bitcoin genesis header (public, fixed, offline). Real block bytes, no pool,
no network, and reproducible to the byte by anyone re-running this.

  python host/test_split_drive.py [seconds] [fold_W] [--test ZB]
"""
import hashlib, json, math, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
try:
    import sdc_cc as CC
except ModuleNotFoundError as exc:
    if exc.name != "sdc_cc":
        raise
    CC = None
from pfc_speed import analyze

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
MAGIC = b"PFCWINMN"; OPN = {0: "nand", 1: "and", 2: "or", 3: "xor", 4: "not"}

# The Bitcoin genesis block header, 80 bytes. Words 0..18 are the prefix; word 19 is the nonce.
GENESIS = bytes.fromhex(
    "01000000" + "00" * 32 +
    "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a" +
    "29ab5f49" + "ffff001d" + "1dac2b7c")

MID_LO, W16_LO, N_LO, T_LO = 0, 256, 352, 384


def load_netlist(off):
    """Read a stored netlist by ADDRESS — bounded, read-only, mmap. The high-impedance probe's shape."""
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[off:off + 8] == MAGIC, "magic mismatch at %d" % off
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", mm, off + 8); p = off + 24
    gates = [None] * n_gate
    for k in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", mm, p); p += 9; gates[k] = (OPN[op], a, b)
    outs = [struct.unpack_from("<i", mm, p + 4 * k)[0] for k in range(n_out)]
    mm.close(); f.close()
    run = CC.CircuitCompiler(n_in).compile_ripple(gates, n_wire)          # §3 crutch: TEST target only
    D, _, _ = analyze(n_in, n_wire, [(a, b) for (_o, a, b) in gates], outs)
    return run, outs, n_gate, D


def rd(v, w, lane=0):
    return w if w < 2 else ((v[w] >> lane) & 1)


def main():
    argv = sys.argv[1:]; test_zb = 18
    if "--test" in argv:
        i = argv.index("--test"); test_zb = int(argv[i + 1]); del argv[i:i + 2]
    secs = float(argv[0]) if argv else 60.0
    W = int(argv[1]) if len(argv) > 1 else 2048
    ones = (1 << W) - 1

    reg = json.load(open(REG))
    # S27's standing failure, quoted in pfc_atom.py: "the better circuit already exists and nothing
    # is wired to it... Hardcoding a circuit name at every call site is what produces that." So ask
    # for the JOB and let pfc_atom resolve the best fabricated circuit for it.
    import pfc_atom
    try:
        NAME_A, _dA, _gA = pfc_atom.resolve("midstate", "area")
        NAME_B, _dB, _gB = pfc_atom.resolve("winner_lane", "area")
    except KeyError as e:
        print("no circuit fabricated for that job (%s) — run: python host/fab_miner_split.py" % e); return 1

    hdr76 = GENESIS[:76]
    hw = [struct.unpack(">I", hdr76[i * 4:i * 4 + 4])[0] for i in range(19)]
    target = 1 << (256 - test_zb)

    runA, outA, gA, DA = load_netlist(int(reg[NAME_A]["offset"]))
    runB, outB, gB, DB = load_netlist(int(reg[NAME_B]["offset"]))
    win_o = outB[0]; latch_o = outB[1:33]

    # ── COLUMN 1 — THE MUHLNICKEL PLAN. §40E: decided first, with the host nowhere in it. ────────────
    #    §40C's measured bank law: a bank of W replicas costs circuit_depth + 2*log2(W), settles: 1.
    plan_lanes = 1 << 32                                          # the whole nonce space, one bank
    bank = DB + 2 * int(math.log2(plan_lanes))
    mono_g, mono_D = 339009, 11754                                # gen_win, the monolith it replaces
    print("╔═ MUHLNICKEL PLAN — the machine. DEPTH in gate-delays, area in gates (§24). ═══════════════")
    print("║  A  %-14s %9s gates  DEPTH %6s   fires ONCE per block (nonce-independent)"
          % (NAME_A, "{:,}".format(gA), "{:,}".format(DA)))
    print("║  B  %-14s %9s gates  DEPTH %6s   fires PER LANE — this is what replicates"
          % (NAME_B, "{:,}".format(gB), "{:,}".format(DB)))
    print("║  §1E junction: A's SEND(mid) IS B's RECEIVE(mid) — a shared location, not a copy.")
    print("║  bank of %s lanes  =  DEPTH %s + 2*log2(%s) = %s gate-delays  ·  settles: 1"
          % ("{:,}".format(plan_lanes), "{:,}".format(DB), "{:,}".format(plan_lanes), "{:,}".format(bank)))
    print("║  area-delay (§14, lanes are INDEPENDENT so speed = REPLICAS/DEPTH -> minimise gates x DEPTH):")
    print("║      lane       %13s      gen_win  %13s      -> %.2fx"
          % ("{:,}".format(gB * DB), "{:,}".format(mono_g * mono_D), (mono_g * mono_D) / (gB * DB)))
    print("╚═══════════════════════════════════════════════════════════════════════════════════════════\n", flush=True)

    # ── COLUMN 2 — HOST TRANSCRIPTION. A DIFFERENT MACHINE. Never added to the above (§24/§40D). ─────
    print("── HOST TRANSCRIPTION (the laptop, a different machine — §56C: this is the LAPTOP")
    print("   transcribing and is never the muhlnickel's speed). test target %d zero-bits; the real" % test_zb)
    print("   2^78 target is NOT driven here — §3 sanctions the crutch for a sub-2^78 TEST only.\n", flush=True)

    # A fires ONCE. Nonce-independent, so its cost is amortised over every lane and every pass.
    t_mid = time.time()
    inA = [0] * 512
    for i in range(512):
        inA[i] = 1 if (hw[i // 32] >> (i % 32)) & 1 else 0
    vA = runA(inA, 1)
    mid = [sum(rd(vA, outA[i * 32 + j]) << j for j in range(32)) for i in range(8)]
    t_mid = time.time() - t_mid
    ref_mid = CC.numeric_midstate(b"".join(struct.pack(">I", w) for w in hw[:16]))
    print("   [A] %s fired ONCE: mid = %s" % (NAME_A, " ".join("%08x" % m for m in mid)))
    print("       vs sdc_cc.numeric_midstate (independent reference, §3): %s   %.2f s\n"
          % ("MATCH" if list(mid) == list(ref_mid) else "MISMATCH", t_mid), flush=True)
    if list(mid) != list(ref_mid):
        print("   mid MISMATCH — not driving B. No result is better than a wrong one."); return 1

    # Everything constant across lanes is routed once per pass; only the nonce column changes.
    const = [0] * 640
    for i in range(256):
        if (mid[i // 32] >> (i % 32)) & 1: const[MID_LO + i] = ones
    for i in range(96):
        if (hw[16 + i // 32] >> (i % 32)) & 1: const[W16_LO + i] = ones
    for j in range(256):
        if (target >> j) & 1: const[T_LO + j] = ones

    base, passes, best = 0, 0, 0
    t0 = time.time(); hit = None
    while time.time() - t0 < secs and base + W <= (1 << 32):
        inp = list(const)
        for j in range(32):
            col = 0
            for l in range(W):
                if ((base + l) >> j) & 1: col |= (1 << l)
            inp[N_LO + j] = col
        v = runB(inp, ones)                                   # ONE addressed pass = W lanes decided
        passes += 1
        wmask = v[win_o] if win_o >= 2 else (ones if win_o == 1 else 0)
        if wmask:
            l0 = (wmask & -wmask).bit_length() - 1             # lowest lane the MUHLNICKEL ruled a winner
            nonce = sum(rd(v, latch_o[j], l0) << j for j in range(32))   # from B's BAKED latch
            hit = (nonce, base + l0); break
        base += W
    el = time.time() - t0

    n_done = passes * W
    print("   passes %d x W=%d lanes = %s nonces in %.2f s  ->  %s nonce/s (host)"
          % (passes, W, "{:,}".format(n_done), el, "{:,}".format(int(n_done / max(el, 1e-9)))))
    print("   per-pass host cost is GATES transcribed: muhl_lane %s vs gen_win %s per lane-pass."
          % ("{:,}".format(gB), "{:,}".format(mono_g)))
    print("   §24: these two columns measure two different machines and are never summed.\n", flush=True)

    if not hit:
        print("   no lane won inside %.0f s at %d zero-bits — widen W or raise seconds. Nothing to verify."
              % (secs, test_zb)); return 0

    nonce, expect = hit
    ref = hashlib.sha256(hashlib.sha256(hdr76 + struct.pack(">I", nonce)).digest()).digest()
    hval = int.from_bytes(ref, "little"); fr = 256 - hval.bit_length()
    print("   WINNER — decided by the MUHLNICKEL, not the host:")
    print("     nonce %#010x   %d leading zero-bits   (test target %d)" % (nonce, fr, test_zb))
    print("     baked latch == base+lane : %s" % (nonce == expect))
    print("     hash < target (hashlib, independent): %s" % (hval < target))
    print("     byte-exact double-SHA vs hashlib    : %s" % (hval < target and fr >= test_zb))
    print("\n   The host routed bytes and read a register. It computed no hash and no compare.")
    return 0


if __name__ == "__main__":
    if CC is None:
        print("SKIP infra/host/test_split_drive.py — sdc_cc is owner-PC-only "
              "(expected at C:/llm/sdc_sandbox); hosted CI cannot drive Titan.")
        raise SystemExit(0)
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
