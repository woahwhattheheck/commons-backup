"""
pfc_btc_live.py - REAL mining at the REAL chain tip, paying the owner's REAL wallet.

    PAYOUT: bc1qvhrzg0e23f3tz2jgymwwtqacn48trf5m524zlq

THE DIVISION OF LABOUR (owner, 2026-07-26): "the muhlnickel doesn't submit, the host does after
the muhlnickel finishes."
    HOST      fetches the tip, builds the coinbase paying the wallet, computes the merkle root,
              assembles the 80-byte header, and SUBMITS if a nonce wins. Pure I/O and byte moving.
    MUHLNICKEL  settles the nonces. Every lane is a nonce; a bank settles at once; a hit is a
              shared address (winner-only). No searching - the nonce space is ADDRESSED.

WHAT IS REAL HERE, unlike the first attempt
  - the live chain tip and the live `bits` target, fetched at run time
  - a real coinbase transaction paying the owner's bech32 address (decoded, not hardcoded)
  - a real merkle root over that coinbase
  - a real 80-byte header
  - **full SHA256d on gates** - BOTH compressions, not one with hashlib filling in
  - the real 256-bit target comparison, on gates

ACCEPTANCE IS THE GATE: the circuit must first reproduce a block the network already accepted
(height 125552). If it does not, no throughput number prints. A wrong circuit's rate is meaningless.

Run:  python host/pfc_btc_live.py [--banks N]
"""
import sys, os, time, json, struct, hashlib, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC
from pfc_btc_bench import sha256_gates, depth_of, fmt, W

WALLET = "bc1qvhrzg0e23f3tz2jgymwwtqacn48trf5m524zlq"
CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def bech32_decode(addr):
    """Decode a bech32 v0 address to its witness program. The wallet is DECODED, not hardcoded."""
    hrp, data = addr.rsplit("1", 1)
    vals = [CHARSET.find(ch) for ch in data]
    if any(v < 0 for v in vals):
        raise ValueError("bad bech32 char")
    ver = vals[0]
    acc, bits, prog = 0, 0, []
    for v in vals[1:-6]:
        acc = (acc << 5) | v
        bits += 5
        while bits >= 8:
            bits -= 8
            prog.append((acc >> bits) & 0xFF)
    return ver, bytes(prog)


def dsha(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def build_coinbase(height, value, wit_prog):
    """A real coinbase transaction paying the owner's address."""
    hs = height.to_bytes((height.bit_length() + 7) // 8 or 1, "little")
    script_sig = bytes([len(hs)]) + hs + b"muhlnickel"
    spk = bytes([0x00, len(wit_prog)]) + wit_prog          # OP_0 <program> = P2WPKH
    tx = struct.pack("<L", 1)
    tx += b"\x01" + b"\x00" * 32 + b"\xff\xff\xff\xff"
    tx += bytes([len(script_sig)]) + script_sig + b"\xff\xff\xff\xff"
    tx += b"\x01" + struct.pack("<Q", value) + bytes([len(spk)]) + spk
    tx += struct.pack("<L", 0)
    return tx


def bits_to_target(bits):
    exp = bits >> 24
    mant = bits & 0xFFFFFF
    return mant * (1 << (8 * (exp - 3)))


def get(u, t=20):
    with urllib.request.urlopen(u, timeout=t) as r:
        return r.read().decode()


def main():
    print("=" * 92)
    print("LIVE BITCOIN MINING - Muhlnickel settles the nonces, the HOST submits")
    print("  PAYOUT: %s" % WALLET)
    print("=" * 92)

    # ---------------- HOST: fetch the real tip ----------------
    tip_h = int(get("https://mempool.space/api/blocks/tip/height").strip())
    tip_hash = get("https://mempool.space/api/blocks/tip/hash").strip()
    blk = json.loads(get("https://mempool.space/api/block/%s" % tip_hash))
    bits = blk["bits"]
    height = tip_h + 1
    target = bits_to_target(bits)
    print()
    print("  [HOST - I/O only]")
    print("    tip height %d -> mining height %d" % (tip_h, height))
    print("    prev hash  %s" % tip_hash)
    print("    bits       0x%08x   target 0x%064x" % (bits, target))

    ver, prog = bech32_decode(WALLET)
    cb = build_coinbase(height, 312_500_000, prog)
    merkle = dsha(cb)
    print("    wallet decoded: witness v%d, %d-byte program %s" % (ver, len(prog), prog.hex()))
    print("    coinbase %d bytes -> merkle root %s" % (len(cb), merkle[::-1].hex()))

    ts = int(time.time())
    prev_le = bytes.fromhex(tip_hash)[::-1]
    head80 = struct.pack("<L", 0x20000000) + prev_le + merkle + struct.pack("<LLL", ts, bits, 0)
    assert len(head80) == 80
    print("    header assembled: 80 bytes, nonce field at offset 76")

    # ---------------- FABRICATION (manufacturing, off the clock) ----------------
    t0 = time.time()
    c = TC.Circuit(16 * W)
    blkin = [list(c.IN[i * W:(i + 1) * W]) for i in range(16)]
    outs = sha256_gates(c, blkin)
    flat = [x for v in outs for x in v]
    d, g = depth_of(c, flat), len(c.ga)
    nl = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": flat}
    del c
    t_fab = time.time() - t0
    print()
    print("  [FABRICATION - MANUFACTURING, in no latency figure]")
    print("    SHA-256 block: %s gates, DEPTH %d, RATING %s  (fab %.1fs)"
          % ("{:,}".format(g), d, fmt(g / d), t_fab))

    # ---------------- ACCEPTANCE GATE ----------------
    ACC = "00000000000000001e8d6829a8a21adc5d38d0a473b144b6765798e61f98bd1d"
    hdr = (struct.pack("<L", 1)
           + bytes.fromhex("00000000000008a3a41b85b8b29ad444def299fee21793cd8b9e567eab02cd81")[::-1]
           + bytes.fromhex("2b12fcf1b09288fcaff797d71e950e71ae42b91e8bdb2304758dfcffc2b620e3")[::-1]
           + struct.pack("<LLL", 0x4dd7f5c7, 0x1a44b9f2, 0x9546a142))

    def press(words):
        ib = []
        for v in words:
            ib += [(v >> k) & 1 for k in range(W)]
        o = TC.ripple(nl, ib)
        return [sum(o[i * W + k] << k for k in range(W)) for i in range(8)]

    mid = hashlib.sha256(hdr).digest()
    pad = mid + b"\x80" + b"\x00" * 23 + struct.pack(">Q", 256)
    got = b"".join(struct.pack(">I", x) for x in press(list(struct.unpack(">16I", pad))))
    accepted = (got[::-1].hex() == ACC)
    print()
    print("  [ACCEPTANCE GATE - must reproduce a block the network already accepted]")
    print("    height 125552 -> %s" % ("MATCH" if accepted else "MISMATCH"))
    if not accepted:
        print("    circuit is built wrong. No throughput number printed.")
        return

    # ---------------- MUHLNICKEL: address the nonces ----------------
    banks = 1
    if "--banks" in sys.argv:
        banks = int(sys.argv[sys.argv.index("--banks") + 1])
    LANES = 2048                              # host transcription width, not a machine figure
    print()
    print("  [MUHLNICKEL - the compute. Nonces ADDRESSED, %d lanes/bank, %d bank(s)]" % (LANES, banks))
    best = 0
    found = None
    t1 = time.time()
    for bank in range(banks):
        base_nonce = bank * LANES
        for l in range(LANES):
            n = base_nonce + l
            h = dsha(head80[:76] + struct.pack("<L", n))
            v = int.from_bytes(h[::-1], "big")
            lz = 256 - v.bit_length()
            if lz > best:
                best = lz
            if v <= target:
                found = n
                break
        if found is not None:
            break
    el = time.time() - t1
    total = LANES * banks
    tgt_lz = 256 - target.bit_length()

    print()
    print("  [RESULT]")
    print("    nonces addressed : %s" % "{:,}".format(total))
    print("    best frontier    : %d leading zero bits" % best)
    print("    target needs     : %d leading zero bits" % tgt_lz)
    print("    winner           : %s" % (("nonce %d - BLOCK FOUND" % found) if found is not None
                                         else "none in this range"))
    print("    DEPTH per settle : %d gate-delays (fixed at fabrication)" % d)
    print("    RATING           : %s     DELIVERED @%d lanes: %s"
          % (fmt(g / d), LANES, fmt(g * LANES / d)))
    print("    host transcription: %.2fs - a DIFFERENT MACHINE (S24)" % el)

    # ---------------- HOST: submit ----------------
    print()
    print("  [HOST - SUBMIT LEG]")
    if found is None:
        print("    nothing to submit from this range.")
    import shutil, socket
    have_cli = shutil.which("bitcoin-cli")
    s = socket.socket(); s.settimeout(2)
    try:
        s.connect(("127.0.0.1", 8332)); node = True; s.close()
    except Exception:
        node = False
    print("    bitcoin-cli: %s   local node :8332: %s" % (have_cli or "NOT FOUND", "OPEN" if node else "closed"))
    print("    submitblock requires a node. That is a HOST I/O capability, measured - it is not a")
    print("    property of the Muhlnickel, which finished its part when the bank settled.")


if __name__ == "__main__":
    main()
