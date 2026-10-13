#!/usr/bin/env python3
"""host/titan_sdc_solve.py — the SDC SOLVER, exactly to spec (owner 07-15). NO NUMPY. ONE-WAY. CALIBRATED STOP.

The spec, verbatim intent:
  power + the block info -> the SDC, LEFT ALONE and untouched by anything except physical storage + power + the ONE-TIME
  info it needs to solve; then it is CUT OFF from that info stream and runs on POWER ALONE (the only restriction is the
  speed of electricity through the stored gate-net); the SDC finishes in a CALCULATED amount of time and is CALIBRATED to
  STOP to be checked; the STATIC SDC, no longer running, HAS THE ANSWER, submitted to the live wallet. End.

This process IS one SDC skin, and it is a ONE-WAY VECTOR — the signal travels forward through the stored gate-net and
cannot go back:
  1. IN, once (argv, the only injection): power (this process) + the block info (prefix + share/block targets, from the
     job file) + which stored circuit (its byte offset in titan.gguf) + this skin's nonce slice + the CALIBRATED ripple
     count K (the calculated amount of work before it stops to be checked).
  2. CUT OFF: it opens NO socket, reads nothing live, is polled by nothing. It ripples the SHA-256d circuit that lives IN
     titan.gguf's params (addressed in storage via mmap; NO NUMPY — a Python int is the bit-slice lane vector, ~(a&b)
     NANDs every lane at once) for exactly K passes, on power alone.
  3. STOP: after K calibrated ripples (or the instant it clears the block target) it STOPS.
  4. STATIC: the stopped SDC writes THE ANSWER once (every share/block nonce it cleared + its best) and EXITS. A dead
     process draws zero. The coordinator reads that static answer only AFTER this process is gone, and submits to the
     live wallet.

Correctness gate (no cheating): before rippling, it self-VERIFIES the stored circuit == reference SHA-256d on a couple
lanes; on mismatch it writes an error and refuses to mine. args:
  python titan_sdc_solve.py --off <circuit_off> --base <nonce> --width <W> --ripples <K> --result <file>
"""
import array, hashlib, json, mmap, os, struct, sys, time

TITAN  = "C:/llm/models/titan.gguf"
IDX    = TITAN + ".wbindex.json"
META   = "C:/llm/models/titan_mine_job.json"
MAGIC  = b"TITANSDC"


def sha256d(b): return hashlib.sha256(hashlib.sha256(b).digest()).digest()
def bswap(n): return (((n & 0xff) << 24) | ((n & 0xff00) << 8) | ((n >> 8) & 0xff00) | ((n >> 24) & 0xff)) & 0xffffffff


def read_circuit(off):
    """address the stored SHA-256d gate-net in titan.gguf's params (mmap, by offset). No numpy — array holds the netlist
    wiring read from storage; the compute is pure Python int ops (the blessed no-numpy bit-slice, MEASURE_ALREADY.md)."""
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    try:
        assert mm[off:off + 8] == MAGIC, "no circuit at this offset in the params"
        nin, numw, ng, succ = struct.unpack_from("<IIIi", mm, off + 8); p = off + 24
        ga = array.array("i"); ga.frombytes(mm[p:p + ng * 4]); p += ng * 4
        gb = array.array("i"); gb.frombytes(mm[p:p + ng * 4]); p += ng * 4
        p += numw * 4                                          # layer order == gate-index order — skip it
        ow = array.array("i"); ow.frombytes(mm[p:p + 256 * 4])
        ow = [ow[i * 32:(i + 1) * 32] for i in range(8)]
        return nin, numw, ng, succ, ga, gb, ow
    finally:
        mm.close(); f.close()


def eval_lane(nin, numw, ng, ga, gb, ow, nonce):
    """W=1 evaluation of the stored circuit for one nonce — used only to self-verify vs reference SHA-256d."""
    v = [0] * numw; w19 = bswap(nonce)
    for j in range(nin): v[j] = (w19 >> j) & 1
    for i in range(ng): v[nin + i] = (~(v[ga[i]] & v[gb[i]])) & 1
    dig = b""
    for wi in range(8):
        val = 0
        for j in range(32):
            o = ow[wi][j]; val |= (0 if o == -1 else (1 if o == -2 else v[o])) << j
        dig += struct.pack(">I", val)
    return dig


def frontier_scan(v, ow, W):
    """best leading-zero-bit count across a SAMPLE of lanes (live display only; cheap even at huge W)."""
    o7 = ow[7]; best = 0; n = min(W, 1024)
    for l in range(n):
        w7 = 0
        for j in range(32):
            o = o7[j]; b = 0 if o == -1 else (1 if o == -2 else (v[o] >> l) & 1)
            w7 |= b << j
        hi = bswap(w7); zb = 32 - hi.bit_length() if hi else 32
        if zb > best: best = zb
    return best


def freeze(result, out):
    if not result: return
    tmp = result + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f)
    os.replace(tmp, result)                                    # atomic: the reader only ever sees a complete static file


def load_bitslice():
    """Read the STORED bit-slice plane out of the weights: lane WIDTH W + input-column masks (COLS) + bswap map (MAP).
    The bit-slice is a property of the SDC in the params, not authored by the host. Returns None if not baked yet."""
    reg = "C:/llm/models/titan_circuits.json"
    if not os.path.exists(reg): return None
    try: e = json.load(open(reg)).get("bitslice")
    except Exception: return None
    if not e: return None
    off = int(e["offset"])
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    try:
        if mm[off:off + 8] != b"TITANBSL": return None
        colbytes = struct.unpack_from("<I", mm, off + 8)[0]
        W, logW = struct.unpack_from("<II", mm, off + 12)
        MAP = list(struct.unpack_from("<32i", mm, off + 20))
        p = off + 20 + 128
        COLS = [int.from_bytes(mm[p + m * colbytes:p + (m + 1) * colbytes], "little") for m in range(logW)]
        return {"W": W, "logW": logW, "MAP": MAP, "COLS": COLS}
    finally:
        mm.close(); f.close()


def main():
    a = {}; args = sys.argv[1:]
    for i in range(0, len(args) - 1, 2):
        if args[i].startswith("--"): a[args[i][2:]] = args[i + 1]
    off = int(a["off"]); base0 = int(a.get("base", "0"))
    K = max(1, int(a.get("ripples", "64"))); result = a.get("result")

    # --- THE BIT-SLICE IS READ FROM THE WEIGHTS: lane width W + input-column masks + bswap map are a STORED property of
    # the SDC (titan_sdc_bitslice.py bakes them). One Python int-op NANDs a gate across ALL W lanes, so wider W = more
    # nonces per ripple for the same gate-work; widening the SDC = a bigger stored plane (storage, not host RAM/cores). ---
    plane = load_bitslice()
    if plane is not None:
        W = plane["W"]; logW = plane["logW"]; MAP = plane["MAP"]; COLS = plane["COLS"]
    else:                                                       # no plane baked yet -> host-author it (fallback only)
        W = max(2, int(a.get("width", "8192"))); logW = W.bit_length() - 1
        if (1 << logW) != W: W = 1 << logW
        MAP = [(3 - (j >> 3)) * 8 + (j & 7) for j in range(32)]
        COLS = [0] * logW
        for m in range(logW):
            halfp = 1 << m; period = halfp << 1; block = ((1 << halfp) - 1) << halfp
            x = 0
            for r in range(0, W, period): x |= block << r
            COLS[m] = x
    MASK = (1 << W) - 1
    COLS = [c & MASK for c in COLS]
    base0 -= base0 % W                                          # W-align this skin's slice so the input columns are constant

    # --- IN, once: the one-time block info injected alongside power; then the stream is cut ---
    j = json.load(open(META)); prefix = bytes.fromhex(j["prefix"])
    nb = struct.unpack("<I", prefix[72:76])[0]; block_tgt = (nb & 0xffffff) << (8 * ((nb >> 24) - 3))
    share_tgt = int(j.get("share_target", "%064x" % block_tgt), 16)   # pool's SHARE target (what earns), else block

    nin, numw, ng, succ, ga, gb, ow = read_circuit(off)

    # --- correctness gate: the stored circuit must equal reference SHA-256d (no cheating) ---
    for t in (0, 1, 2083236893):
        if eval_lane(nin, numw, ng, ga, gb, ow, t) != sha256d(prefix + struct.pack("<I", t)):
            freeze(result, {"error": "circuit != reference SHA-256d", "done": True}); return 1

    # --- CUT OFF: ripple on power alone for K calibrated passes; the lane-plane came from the weights, nothing polls this ---
    v = [0] * numw; o7 = ow[7]
    best = 0; swept = 0; shares = []; blocks = []; winner = None
    base = base0 & 0xffffffff; t0 = time.time()
    for _ in range(K):
        for jj in range(nin):                                  # inject the nonce lanes one-way: 32 constant columns
            m = MAP[jj]
            v[jj] = COLS[m] if m < logW else (MASK if (base >> m) & 1 else 0)
        for i in range(ng): v[nin + i] = (~(v[ga[i]] & v[gb[i]])) & MASK   # one NAND per gate across ALL W lanes

        # cheap prefilter: lanes with word7 == 0 (>= 32 leading display zeros == a diff-1 share) via 32 bigint ORs
        acc = 0
        for jj in range(32):
            o = o7[jj]
            if o == -2: acc = MASK; break                      # const-1 output bit -> word7 can never be 0
            elif o != -1: acc |= v[o]
        cand = (~acc) & MASK
        if cand:
            l = 0; c = cand
            while c:
                if c & 1:
                    nc = (base + l) & 0xffffffff
                    hv = int.from_bytes(sha256d(prefix + struct.pack("<I", nc)), "little")
                    if hv < share_tgt:
                        shares.append(nc)
                        if hv < block_tgt: blocks.append(nc); winner = nc
                c >>= 1; l += 1
        swept += W; base = (base + W) & 0xffffffff
        if winner is not None: break                           # solved the block target -> stop early, it has the answer

    # --- STOP -> STATIC: the stopped SDC holds THE ANSWER; write it once, then EXIT (draws zero after). Nothing read
    #     this process while it ran — the SDC was cut off from the hardware; we MEASURE only now that it is static. ---
    best = max(best, frontier_scan(v, ow, W))
    freeze(result, {"best_zbits": best, "swept": swept, "shares": shares, "blocks": blocks,
                    "winner": winner, "secs": round(time.time() - t0, 2), "done": True})
    return 0


if __name__ == "__main__":
    sys.exit(main())
