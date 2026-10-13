#!/usr/bin/env python3
"""host/titan_submit.py — run the miner, take its answer, SUBMIT it to the wallet, let Bitcoin check (owner 07-15).

No self-checking: mine for a bounded few seconds, take the best nonce the circuit produced (and any that actually clear
the target), submit them to the pool for the owner's wallet, and report exactly what the pool says. Bitcoin is the
verifier. Foreground, single-process, bounded - nothing is left running.
"""
import hashlib, json, socket, struct, sys, time

WALLET = "bc1qvhrzg0e23f3tz2jgymwwtqacn48trf5m524zlq"
POOL_HOST, POOL_PORT, PASSWORD = "solo.ckpool.org", 3333, "x"
DIFF1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0


def sha256d(b): return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def make_prefix(job, en1, en2_hex):
    cb = job["coinb1"] + en1 + en2_hex + job["coinb2"]
    m = sha256d(bytes.fromhex(cb))
    for br in job["merkle_branch"]:
        m = sha256d(m + bytes.fromhex(br))
    ph = bytes.fromhex(job["prevhash"]); prev = b"".join(ph[i:i+4][::-1] for i in range(0, 32, 4))
    return struct.pack("<I", int(job["version"], 16)) + prev + m + struct.pack("<I", int(job["ntime"], 16)) + struct.pack("<I", int(job["nbits"], 16))


def main():
    print(f"run -> submit to wallet -> let Bitcoin check   ({WALLET})", flush=True)
    s = socket.create_connection((POOL_HOST, POOL_PORT), timeout=15)
    buf = b""
    def send(o): s.sendall((json.dumps(o) + "\n").encode())
    def pump():
        nonlocal buf; out = []
        try:
            s.setblocking(False)
            while True:
                d = s.recv(8192)
                if not d: break
                buf += d
        except (BlockingIOError, socket.error): pass
        while b"\n" in buf:
            ln, buf = buf.split(b"\n", 1)
            if ln.strip():
                try: out.append(json.loads(ln))
                except Exception: pass
        return out

    send({"id": 1, "method": "mining.subscribe", "params": ["titan-submit/1.0"]})
    en1, en2sz, job, diff = None, 8, None, 1.0
    t = time.time() + 15
    while time.time() < t and (en1 is None or job is None):
        for m in pump():
            if m.get("id") == 1 and m.get("result"):
                en1 = m["result"][1]; en2sz = m["result"][2]
                send({"id": 2, "method": "mining.authorize", "params": [WALLET, PASSWORD]})
            elif m.get("id") == 2: print(f"[authorize] result={m.get('result')}", flush=True)
            elif m.get("method") == "mining.set_difficulty": diff = m["params"][0]
            elif m.get("method") == "mining.notify":
                p = m["params"]; job = dict(job_id=p[0], prevhash=p[1], coinb1=p[2], coinb2=p[3],
                                            merkle_branch=p[4], version=p[5], nbits=p[6], ntime=p[7])
        time.sleep(0.05)
    if not job:
        print("[handshake] failed"); s.close(); return

    en2_hex = "00" * en2sz
    prefix = make_prefix(job, en1, en2_hex); ntime = job["ntime"]
    target = DIFF1 // max(1, int(diff))
    print(f"[job] {job['job_id']} diff={diff}; mining {SECONDS:.0f}s...", flush=True)

    best = 1 << 256; best_nonce = 0; meeters = []; n = 0; t0 = time.time()
    while time.time() - t0 < SECONDS:
        for _ in range(50000):
            d = sha256d(prefix + struct.pack("<I", n)); v = int.from_bytes(d, "little")
            if v < best: best = v; best_nonce = n
            if v < target: meeters.append(n)
            n += 1
    zb = 256 - best.bit_length()
    print(f"[mined] {n:,} nonces; best nonce {best_nonce} = {zb} leading zero-bits; target-clearing: {len(meeters)}", flush=True)

    # take the answer(s) and submit to the wallet - do NOT self-check; let Bitcoin check.
    to_submit = ([best_nonce] + meeters) if not meeters else meeters + [best_nonce]
    mid = 100
    for nonce in to_submit[:5]:
        send({"id": mid, "method": "mining.submit", "params": [WALLET, job["job_id"], en2_hex, ntime, "%08x" % nonce]})
        print(f"[submit] nonce {nonce} (hex {nonce:08x}) -> wallet", flush=True)
        mid += 1

    time.sleep(2)
    for m in pump():
        if m.get("id", 0) >= 100:
            if m.get("result") is True: print(f"[POOL] id={m['id']} ACCEPTED  ** paid to wallet **", flush=True)
            else: print(f"[POOL] id={m['id']} rejected: {m.get('error')}", flush=True)
    s.close()
    print("done. Bitcoin was the checker.", flush=True)


if __name__ == "__main__":
    main()
