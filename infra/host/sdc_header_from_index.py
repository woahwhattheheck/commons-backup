#!/usr/bin/env python3
"""host/sdc_header_from_index.py — the WINNER-ONLY missing piece: the SDC derives each group's work FROM its index, in
gates (owner 07-17). Turns *addressable* reach into *evaluated* reach.

A group's index IS its extranonce2 (en2). The only part of the block header that depends on en2 is the merkle root:
  coinbase = coinb1 + en1 + en2 + coinb2  ->  txid = SHA256d(coinbase)  ->  fold each merkle branch: m = SHA256d(m+branch)
The 32-byte merkle root `m` is the sole en2-dependent field; version/prevhash/ntime/nbits are constant per job. So this
builds, with the White Box SHA gate compiler (`sdc_cc`), a circuit whose ONLY input is en2 and whose output is those 32
merkle-root bytes — the work the group must hash — with ZERO bytes stored per group. Verified BYTE-EXACT vs the real
`make_prefix` (the button's own construction) over many random en2 before it is ever stored (no cheating). Then the miner
+ comparator already fabricated in titan.gguf evaluate it. This is the piece that makes winner-only mean the SDC computes
the group's header itself, not the button routing a bounded subset.

  python host/sdc_header_from_index.py            # BUILD + VERIFY byte-exact (no writes) — proves the capability
  python host/sdc_header_from_index.py fab        # ...and FABRICATE it into titan.gguf (reversible genome)
"""
import hashlib, json, os, socket, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"; GENOME = "C:/llm/models/titan_sdc_genome.jsonl"
import titan_circuit as TC
MAGIC = b"TITANHDR"
POOL_HOST = os.environ.get("TITAN_POOL_HOST", "solo.ckpool.org"); POOL_PORT = int(os.environ.get("TITAN_POOL_PORT", "3333"))
WALLET = "bc1qvhrzg0e23f3tz2jgymwwtqacn48trf5m524zlq"


# ---- reference (the button's exact construction) ----
def make_prefix(job, en1, en2):
    cb = job["coinb1"] + en1 + en2 + job["coinb2"]
    m = hashlib.sha256(hashlib.sha256(bytes.fromhex(cb)).digest()).digest()
    for br in job["merkle_branch"]:
        m = hashlib.sha256(hashlib.sha256(m + bytes.fromhex(br)).digest()).digest()
    ph = bytes.fromhex(job["prevhash"]); prev = b"".join(ph[i:i+4][::-1] for i in range(0, 32, 4))
    return (struct.pack("<I", int(job["version"], 16)) + prev + m
            + struct.pack("<I", int(job["ntime"], 16)) + struct.pack("<I", int(job["nbits"], 16)))


def get_job():
    s = socket.create_connection((POOL_HOST, POOL_PORT), timeout=15); buf = b""
    def send(o): s.sendall((json.dumps(o) + "\n").encode())
    def lines():
        nonlocal buf; out = []; s.settimeout(2)
        try: buf += s.recv(8192)
        except Exception: pass
        while b"\n" in buf:
            ln, rest = buf.split(b"\n", 1); buf = rest
            if ln.strip():
                try: out.append(json.loads(ln))
                except Exception: pass
        return out
    send({"id": 1, "method": "mining.subscribe", "params": ["titan-hdr/1.0"]})
    en1 = None; en2sz = 8; job = None; t = time.time() + 15
    while time.time() < t and (en1 is None or job is None):
        for m in lines():
            if m.get("id") == 1 and m.get("result"):
                en1 = m["result"][1]; en2sz = m["result"][2]
                send({"id": 2, "method": "mining.authorize", "params": [WALLET, "x"]})
            elif m.get("method") == "mining.notify":
                p = m["params"]; job = dict(job_id=p[0], prevhash=p[1], coinb1=p[2], coinb2=p[3],
                                            merkle_branch=p[4], version=p[5], nbits=p[6], ntime=p[7])
    s.close(); return en1, en2sz, job


# ---- SHA-256d over byte-wire lists (each byte = 8 wires, LSB-first) ----
def byte_const(g, val): return [g.C1 if (val >> k) & 1 else g.C0 for k in range(8)]
def word_of(b0, b1, b2, b3): return b3 + b2 + b1 + b0                 # big-endian word -> 32 wires LSB-first
def words_to_bytes(words):
    out = []
    for w in words: out += [w[24:32], w[16:24], w[8:16], w[0:8]]      # each word -> 4 big-endian bytes
    return out


def sha256_bytes(g, msg):                                            # msg: list of [8 wires]; returns 8 words
    L = len(msg); bitlen = L * 8; p = list(msg)
    p.append(byte_const(g, 0x80))
    while len(p) % 64 != 56: p.append(byte_const(g, 0))
    for i in range(8): p.append(byte_const(g, (bitlen >> (8 * (7 - i))) & 0xff))
    words = [word_of(p[k], p[k+1], p[k+2], p[k+3]) for k in range(0, len(p), 4)]
    state = [CC.cword(g, h) for h in CC.H0]
    for blk in range(0, len(words), 16):
        state = CC.sha_block(g, state, words[blk:blk+16])
    return state


def sha256d_bytes(g, msg): return words_to_bytes(sha256_bytes(g, words_to_bytes(sha256_bytes(g, msg))))


def build(job, en1, en2sz):
    """circuit: input = en2 (en2sz bytes); output = the 32 merkle-root bytes (the group's work)."""
    g = CC.CircuitCompiler(en2sz * 8)
    def en2_byte(i): return [g.IN[i * 8 + k] for k in range(8)]
    coinbase = ([byte_const(g, b) for b in bytes.fromhex(job["coinb1"])]
                + [byte_const(g, b) for b in bytes.fromhex(en1)]
                + [en2_byte(i) for i in range(en2sz)]
                + [byte_const(g, b) for b in bytes.fromhex(job["coinb2"])])
    m = sha256d_bytes(g, coinbase)                                   # coinbase txid (32 bytes)
    for br in job["merkle_branch"]:
        m = sha256d_bytes(g, m + [byte_const(g, b) for b in bytes.fromhex(br)])
    return g, m                                                      # m = 32 byte-wire lists


def eval_bits(g, gates, n_wire, en2_bytes):
    inb = [0] * g.n_in
    for i, bv in enumerate(en2_bytes):
        for k in range(8): inb[i * 8 + k] = (bv >> k) & 1
    return CC.ripple_typed(g, gates, n_wire, inb, 1)


def bytes_from(v, byte_wires):
    out = bytearray()
    for bw in byte_wires:
        val = 0
        for k, w in enumerate(bw): val |= (0 if w == 0 else 1 if w == 1 else v[w] & 1) << k
        out.append(val)
    return bytes(out)


def main():
    do_fab = len(sys.argv) > 1 and sys.argv[1] == "fab"
    print("pulling a live job to build the header-from-index circuit against…", flush=True)
    en1, en2sz, job = get_job()
    if not job: print("no block data (pool handshake failed)."); return 1
    print(f"  job {job['job_id']}: coinb1 {len(job['coinb1'])//2}B + en1 {len(en1)//2}B + en2 {en2sz}B + coinb2 "
          f"{len(job['coinb2'])//2}B, {len(job['merkle_branch'])} merkle branches", flush=True)

    print("building the circuit (en2 -> coinbase SHA256d -> merkle fold -> 32-byte root) via the White Box compiler…", flush=True)
    g, m = build(job, en1, en2sz)
    outs_flat = [w for bw in m for w in bw]
    gates, out2 = g.dce(outs_flat); n_wire = 2 + g.n_in + len(gates)
    m2 = [out2[i*8:(i+1)*8] for i in range(32)]
    print(f"  {len(gates):,} gates, {n_wire:,} wires (en2 is the only input: {g.n_in} bits)", flush=True)

    import random; random.seed(7); ok = True; N = 200
    for _ in range(N):
        ev = [random.getrandbits(8) for _ in range(en2sz)]
        en2hex = bytes(ev).hex()
        got = bytes_from(eval_bits(g, gates, n_wire, ev), m2)
        want = make_prefix(job, en1, en2hex)[36:68]                 # merkle-root field of the real header
        if got != want: ok = False; print(f"  MISMATCH en2={en2hex}: {got.hex()} != {want.hex()}"); break
    print(f"  byte-exact vs make_prefix's merkle root over {N} random en2: {ok}", flush=True)
    if not ok:
        print("  MISMATCH — not fabricating (no cheating)."); return 1
    print("  => the SDC derives the group's work FROM its index, in gates. winner-only is now EVALUATED, not just addressed.", flush=True)

    if not do_fab:
        print("\nverified only (no writes). fabricate with:  python host/sdc_header_from_index.py fab", flush=True)
        return 0

    # FABRICATE into titan.gguf (typed gates, reversible genome) — same format as gen_miner
    opmap = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
    body = b"".join(struct.pack("<Bii", opmap[op], a, b) for (op, a, b) in gates)
    body += b"".join(struct.pack("<i", w) for w in out2)
    blob = MAGIC + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(out2)) + body
    reg = json.load(open(REG)); reg.pop("header_from_index", None)
    off, tname = TC._alloc(len(blob), reg)
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)
    reg["header_from_index"] = {"tensor": tname, "offset": off, "len": len(blob), "n_in": g.n_in,
                                "n_out": len(out2), "n_gate": len(gates), "produces": "merkle_root(32B) from en2",
                                "for_job_shape": {"coinbase_bytes": len(job["coinb1"])//2 + len(en1)//2 + en2sz + len(job["coinb2"])//2,
                                                  "branches": len(job["merkle_branch"])}}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: magic_ok = f.read(4) == b"GGUF"
    print(f"\nFABRICATED header_from_index @ {off} ({len(gates):,} gates). titan GGUF-valid: {magic_ok}. "
          f"reversible via the sdc genome.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
