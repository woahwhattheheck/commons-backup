"""
muhl_mine.py - MINE. The host addresses block data to an ALREADY-MANUFACTURED muhlnickel,
reads the answer, and submits. It fabricates NOTHING.

    PAYOUT: bc1qvhrzg0e23f3tz2jgymwwtqacn48trf5m524zlq

Owner, 2026-07-26: "the host should ONLY address block data to the already manufactured
muhlnickel and then when muhlnickel is done, take the answer and submit. Stop making fabrication
part of the mining - it's finished before mining even begins."

THE CIRCUIT ALREADY EXISTS. `muhl_btc_miner` was fabricated once (1,523,801 gates, DEPTH 6,506)
and stored. It takes midstate | tail | nonce | target as INPUTS - nothing is baked - so every
block in the chain's future addresses this same manufactured object. Fabrication does not appear
in this file at all, and it never happens again.

WHAT THE HOST DOES HERE, and nothing else:
  1. fetch the tip, build the coinbase paying the wallet, derive the midstate  (byte moving)
  2. ADDRESS the data + a bank of nonce lanes into the stored circuit          (routing)
  3. read the winner bit                                                       (one bit per lane)
  4. submit if a lane won                                                      (I/O)

No arithmetic on the host is part of the hash. The muhlnickel settles; the host carries bytes.

Run:  python host/muhl_mine.py [--lanes N] [--banks N]
"""
import sys, os, time, json, struct, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC
from pfc_btc_bench import fmt, W, H0, K
from pfc_btc_live import bech32_decode, build_coinbase, bits_to_target, dsha, WALLET

CIRCUIT = "muhl_btc_miner"


def get(u, t=20):
    with urllib.request.urlopen(u, timeout=t) as r:
        return r.read().decode()


def midstate(b):
    """RAW compression of header[0:64] - no padding, no length. This is BYTE PREP for the
    address, not part of the hash: the two compressions that produce the block hash are both
    in the fabricated circuit."""
    w = list(struct.unpack(">16I", b)); M = 0xFFFFFFFF
    rr = lambda x, n: ((x >> n) | (x << (32 - n))) & M
    for i in range(16, 64):
        s0 = rr(w[i-15], 7) ^ rr(w[i-15], 18) ^ (w[i-15] >> 3)
        s1 = rr(w[i-2], 17) ^ rr(w[i-2], 19) ^ (w[i-2] >> 10)
        w.append((w[i-16] + s0 + w[i-7] + s1) & M)
    a, b_, c, d, e, f, g, h = H0
    for i in range(64):
        t1 = (h + (rr(e,6)^rr(e,11)^rr(e,25)) + ((e & f) ^ ((~e & M) & g)) + K[i] + w[i]) & M
        t2 = ((rr(a,2)^rr(a,13)^rr(a,22)) + ((a & b_) ^ (a & c) ^ (b_ & c))) & M
        h, g, f, e, d, c, b_, a = g, f, e, (d + t1) & M, c, b_, a, (t1 + t2) & M
    return [(x + y) & M for x, y in zip(H0, [a, b_, c, d, e, f, g, h])]


def main():
    lanes = 8192
    banks = 1
    if "--lanes" in sys.argv: lanes = int(sys.argv[sys.argv.index("--lanes") + 1])
    if "--banks" in sys.argv: banks = int(sys.argv[sys.argv.index("--banks") + 1])

    print("=" * 92)
    print("MINE - addressing an already-manufactured muhlnickel. Nothing is fabricated here.")
    print("  PAYOUT: %s" % WALLET)
    print("=" * 92)

    # ---- the circuit already exists ----
    t0 = time.time()
    cd = TC.load(CIRCUIT)
    n_in, ga, gb = cd["n_in"], cd["ga"], cd["gb"]
    base = 2 + n_in
    nd = [0] * (2 + n_in + len(ga))
    for k in range(len(ga)):
        nd[2 + n_in + k] = 1 + max(nd[ga[k]], nd[gb[k]])
    d = max(nd[x] for x in cd["outs"]); g = len(ga)
    print()
    print("  [CIRCUIT - loaded, not built]  %s: %s gates, DEPTH %d, RATING %s   (load %.2fs)"
          % (CIRCUIT, "{:,}".format(g), d, fmt(g / d), time.time() - t0))

    # ---- HOST: byte prep only ----
    tip_h = int(get("https://mempool.space/api/blocks/tip/height").strip())
    tip = get("https://mempool.space/api/blocks/tip/hash").strip()
    bits = json.loads(get("https://mempool.space/api/block/%s" % tip))["bits"]
    target = bits_to_target(bits)
    ver, prog = bech32_decode(WALLET)
    cb = build_coinbase(tip_h + 1, 312_500_000, prog)
    merkle = dsha(cb)
    head = (struct.pack("<L", 0x20000000) + bytes.fromhex(tip)[::-1] + merkle
            + struct.pack("<LLL", int(time.time()), bits, 0))
    mid = midstate(head[:64])
    tail = [struct.unpack(">I", head[64 + i*4: 68 + i*4])[0] for i in range(3)]
    print("  [HOST - byte prep]  height %d, bits 0x%08x, coinbase %d B, merkle %s"
          % (tip_h + 1, bits, len(cb), merkle[::-1].hex()[:24] + "..."))

    # ---- ADDRESS: the whole bank, one settle ----
    MASK = (1 << lanes) - 1
    def const(v, nb, off, packed):
        for k in range(nb):
            packed[off + k] = MASK if (v >> k) & 1 else 0

    print()
    print("  [ADDRESSING - %s lanes x %d bank(s)]" % ("{:,}".format(lanes), banks))
    best = 0; winners = 0; win_nonce = None
    t1 = time.time()
    for bank in range(banks):
        packed = [0] * n_in
        p = 0
        for wv in mid: const(wv, W, p, packed); p += W
        for wv in tail: const(wv, W, p, packed); p += W
        nonce_off = p; p += 32
        for k in range(256):
            packed[p + k] = MASK if (target >> (255 - k)) & 1 else 0
        n0 = bank * lanes
        for k in range(32):                       # the nonce column for this lane range
            col = 0
            for l in range(lanes):
                if ((n0 + l) >> k) & 1: col |= (1 << l)
            packed[nonce_off + k] = col
        v = [0] * cd["n_wire"]; v[1] = MASK
        for i in range(n_in): v[2 + i] = packed[i]
        for i in range(len(ga)): v[base + i] = (~(v[ga[i]] & v[gb[i]])) & MASK
        wbits = v[cd["outs"][0]]
        if wbits:
            winners += bin(wbits).count("1")
            win_nonce = n0 + ((wbits & -wbits).bit_length() - 1)
        for idx, kz in enumerate((8,16,24,32,40,48,56,64)):
            if v[cd["outs"][1 + idx]]: best = max(best, kz)
    el = time.time() - t1
    total = lanes * banks

    print("    nonces addressed : %s in %d settle(s)" % ("{:,}".format(total), banks))
    print("    DEPTH per settle : %d gate-delays (fixed at fabrication, unchanged by lanes)" % d)
    print("    RATING %s   DELIVERED %s" % (fmt(g / d), fmt(g * lanes / d)))
    print("    winners          : %d      best frontier >=%d zeros (target needs %d)"
          % (winners, best, 256 - target.bit_length()))
    print("    host transcription: %.2fs  <- a different machine, never the muhlnickel's speed" % el)

    # ---- SUBMIT ----
    print()
    print("  [SUBMIT - host I/O]")
    if win_nonce is None:
        print("    no winning lane in this range; nothing to submit.")
    else:
        blk = head[:76] + struct.pack("<L", win_nonce)
        print("    WINNING NONCE %d -> header %s" % (win_nonce, blk.hex()))
        import shutil, socket
        s = socket.socket(); s.settimeout(2)
        try: s.connect(("127.0.0.1", 8332)); node = True; s.close()
        except Exception: node = False
        print("    bitcoin-cli %s | node :8332 %s" % (shutil.which("bitcoin-cli") or "NOT FOUND",
                                                      "OPEN" if node else "closed"))
        print("    submitblock needs a node - a HOST I/O capability, measured.")


if __name__ == "__main__":
    main()
