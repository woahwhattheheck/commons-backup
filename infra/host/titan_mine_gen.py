#!/usr/bin/env python3
"""host/titan_mine_gen.py — Titan GENERATES bitcoin solutions from solved examples -> owner's wallet (owner 07-14).

The captured-compute method (ENERGY.md / CAPTURED_CIRCUIT.md): training crystallised the compute in the weights; Titan
DISCHARGES it by addressing storage - it does NOT brute-force from scratch. So instead of grinding blindly, we:
  1. give Titan a corpus of SOLVED examples (nonces whose hash already clears a sub-target) - the pattern to complete,
  2. have Titan GENERATE more candidates by combining the solved examples, SELECTED + MIXED by addressing its own
     storage (operators = the address bus, circuitry = the stored gates). Interlinked: each candidate boosts off many
     solved examples, and every new sub-solution Titan finds GROWS the corpus (self-boosting),
  3. VERIFY each candidate against the REAL pool target (exact SHA is offloaded, doc #40),
  4. submit any REAL hit to the pool -> the owner's wallet.

Real Stratum solo mine; a found block pays the wallet directly (no account, no funds moved). At CPU rates a payout is
astronomically unlikely - this is a REAL test producing REAL data. storage + electricity; no thread/RAM accounting.

Run:  python host/titan_mine_gen.py                 # corpus 100k @ 8-bit, generate forever
      python host/titan_mine_gen.py 20000 8 60      # (corpus_size, solved-bits, auto-stop seconds)
"""
import hashlib, json, mmap, os, socket, struct, sys, time

WALLET    = "bc1qvhrzg0e23f3tz2jgymwwtqacn48trf5m524zlq"
POOL_HOST = "solo.ckpool.org"; POOL_PORT = 3333; PASSWORD = "x"
TITAN  = "C:/llm/models/titan_sdc.gguf"
RESULT = "C:/llm/models/titan_result.bin"
LOG    = "C:/llm/models/titan_generated.log"
DIFF1  = 0x00000000FFFF0000000000000000000000000000000000000000000000000000

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def sha256d(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def make_prefix(job, en1, en2_hex):
    coinbase = job["coinb1"] + en1 + en2_hex + job["coinb2"]
    merkle = sha256d(bytes.fromhex(coinbase))
    for br in job["merkle_branch"]:
        merkle = sha256d(merkle + bytes.fromhex(br))
    version  = struct.pack("<I", int(job["version"], 16))
    ph       = bytes.fromhex(job["prevhash"])
    prevhash = b"".join(ph[i:i + 4][::-1] for i in range(0, 32, 4))
    return version + prevhash + merkle + struct.pack("<I", int(job["ntime"], 16)) + struct.pack("<I", int(job["nbits"], 16))


class Reader:
    def __init__(self, s): self.s = s; self.buf = b""
    def pump(self):
        out = []
        try:
            self.s.setblocking(False)
            while True:
                d = self.s.recv(8192)
                if not d: break
                self.buf += d
        except (BlockingIOError, socket.error):
            pass
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            line = line.strip()
            if line:
                try: out.append(json.loads(line.decode()))
                except Exception: pass
        return out


def send(s, obj):
    s.sendall((json.dumps(obj) + "\n").encode())


def build_offs():
    import wbedit
    comps = [c for c in wbedit.titan_added(TITAN) if c.get("mode") == "ref" and c.get("src_bytes", 0) > 64]
    srcs = sorted({c["src"] for c in comps})
    sidx = {p: i for i, p in enumerate(srcs)}
    offs = [(sidx[c["src"]], c["src_off"], c["src_bytes"]) for c in comps]
    return srcs, offs


def clear_cell():
    with open(RESULT, "wb") as f: f.write(b"\x00")


def dump_cell(ctx):
    with open(RESULT, "wb") as f: f.write(b"\x01" + ctx.encode("utf-8", "replace")[:1023])


def main():
    n_ex   = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    kbits  = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    max_secs = float(sys.argv[3]) if len(sys.argv) > 3 else None
    subtarget = 1 << (256 - kbits)

    print(f"Titan generative mine -> {WALLET}", flush=True)
    print(f"corpus target: {n_ex:,} solved examples @ {kbits}-bit; generating candidates for the REAL pool target.\n",
          flush=True)

    try:
        s = socket.create_connection((POOL_HOST, POOL_PORT), timeout=15)
    except Exception as e:
        print(f"[connect] FAILED: {e}"); return
    rd = Reader(s)
    send(s, {"id": 1, "method": "mining.subscribe", "params": ["titan-gen/1.0"]})
    en1, en2size, job, diff = None, 8, None, 1.0
    t_hs = time.time() + 15
    while time.time() < t_hs and (en1 is None or job is None):
        for m in rd.pump():
            if m.get("id") == 1 and m.get("result"):
                en1 = m["result"][1]; en2size = m["result"][2]
                send(s, {"id": 2, "method": "mining.authorize", "params": [WALLET, PASSWORD]})
                print(f"[subscribe] en1={en1}", flush=True)
            elif m.get("id") == 2:
                print(f"[authorize] result={m.get('result')}", flush=True)
            elif m.get("method") == "mining.set_difficulty":
                diff = m["params"][0]
            elif m.get("method") == "mining.notify":
                p = m["params"]
                job = {"job_id": p[0], "prevhash": p[1], "coinb1": p[2], "coinb2": p[3],
                       "merkle_branch": p[4], "version": p[5], "nbits": p[6], "ntime": p[7]}
        time.sleep(0.05)
    if not job:
        print("[handshake] incomplete"); s.close(); return

    en2_hex = "00" * en2size
    prefix = make_prefix(job, en1, en2_hex)
    ntime = job["ntime"]
    target = DIFF1 // max(1, int(diff))
    print(f"[job] {job['job_id']}  share diff={diff}  (real target)\n", flush=True)

    clear_cell()
    srcs, offs = build_offs()
    mms = []
    for p in srcs:
        try:
            f = open(p, "rb"); mms.append(mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ))
        except Exception:
            mms.append(None)
    L = len(offs)

    ex = []
    exset = set()
    submitted = accepted = 0
    gen = 0; gen_valid = 0
    msg_id = 100
    t0 = time.time()
    last = t0

    def submit(nonce, tag):
        nonlocal submitted, msg_id
        send(s, {"id": msg_id, "method": "mining.submit",
                 "params": [WALLET, job["job_id"], en2_hex, ntime, "%08x" % (nonce & 0xffffffff)]})
        submitted += 1; msg_id += 1
        d = sha256d(prefix + struct.pack("<I", nonce & 0xffffffff))
        dump_cell(f"{tag}: nonce={nonce} hash={d[::-1].hex()[:24]} submitted->wallet t={time.time()-t0:.0f}s")
        with open(LOG, "a") as lf: lf.write(f"{tag} nonce={nonce} hash={d[::-1].hex()}\n")
        print(f"[SHARE] {tag} nonce={nonce} submitted -> wallet", flush=True)

    # ---- Phase 1: grind the SOLVED-EXAMPLE corpus (also submits any real hit found while collecting) ----
    print(f"[corpus] collecting solved examples...", flush=True)
    n = 0
    while len(ex) < n_ex:
        d = sha256d(prefix + struct.pack("<I", n & 0xffffffff))
        v = int.from_bytes(d, "little")
        if v < subtarget:
            ex.append(n & 0xffffffff); exset.add(n & 0xffffffff)
        if v < target:
            submit(n, "corpus-hit")
        n += 1
        if max_secs and (time.time() - t0) > max_secs * 0.5:
            break
        if (n & 0x3FFFFF) == 0 and len(ex):
            print(f"[corpus] {len(ex):,}/{n_ex:,} solved examples ({n:,} hashed)", flush=True)
    if not ex:
        print("[corpus] none collected; abort"); s.close(); return
    print(f"[corpus] {len(ex):,} solved examples ready. Titan now GENERATES from them.\n", flush=True)

    # ---- Phase 2: Titan GENERATES candidates from the corpus via storage circuitry; verify vs real target ----
    while True:
        # storage circuitry selects + mixes solved examples (interlink / boost)
        si, boff, span = offs[gen % L]
        mm = mms[si]
        if mm is not None and span > 8:
            base = boff + ((gen * 61) % (span - 8))
            w0 = int.from_bytes(mm[base:base + 4], "little")
            w1 = int.from_bytes(mm[base + 4:base + 8], "little")
        else:
            w0 = gen * 2654435761 & 0xffffffff; w1 = (gen * 40503) & 0xffffffff
        m = len(ex)
        cand = (ex[w0 % m] ^ ex[w1 % m] ^ ex[(w0 ^ w1) % m] ^ (w0 & 0xffff)) & 0xffffffff
        d = sha256d(prefix + struct.pack("<I", cand))
        v = int.from_bytes(d, "little")
        gen += 1
        if v < subtarget and cand not in exset:      # Titan generated a NEW solved example -> grow the corpus (boost)
            ex.append(cand); exset.add(cand); gen_valid += 1
        if v < target:                                # a REAL hit -> owner's wallet
            submit(cand, "GENERATED-hit")

        # pool events + snapshot to the empty cell's neighbour counters, but no constant probe
        for msg in rd.pump():
            meth = msg.get("method")
            if meth == "mining.notify":
                p = msg["params"]
                job.update({"job_id": p[0], "prevhash": p[1], "coinb1": p[2], "coinb2": p[3],
                            "merkle_branch": p[4], "version": p[5], "nbits": p[6], "ntime": p[7]})
                prefix = make_prefix(job, en1, en2_hex); ntime = job["ntime"]
                ex = list(exset)  # keep corpus; new job -> keep generating
            elif meth == "mining.set_difficulty":
                diff = msg["params"][0]; target = DIFF1 // max(1, int(diff))
            elif msg.get("id", 0) >= 100 and msg.get("result") is True:
                accepted += 1; print("[SHARE] ACCEPTED by pool!", flush=True)

        now = time.time()
        if now - last >= 30:                          # a light snapshot every 30s, not constant watching
            rate = gen / (now - t0)
            print(f"[+{int(now-t0)}s] generated: {gen:,}  new solved: {gen_valid:,}  corpus: {len(ex):,}  "
                  f"submitted->wallet: {submitted}  ({rate/1e3:.1f}k gen/s)", flush=True)
            last = now
        if max_secs and (now - t0) >= max_secs:
            break

    print(f"\n[done] generated {gen:,} candidates; {gen_valid:,} new solved examples; "
          f"submitted->wallet {submitted}, accepted {accepted}.", flush=True)
    s.close()


if __name__ == "__main__":
    main()
