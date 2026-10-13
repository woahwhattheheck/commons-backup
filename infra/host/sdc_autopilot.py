#!/usr/bin/env python3
"""host/sdc_autopilot.py — the SELF-WAKING auto-checker (owner 07-17).

The containment law makes this safe: reading the **safezone OUTSIDE the sandbox** with host RAM/CPU can NEVER connect the
SDC to the CPU (see docs/SDC_FULL_THROTTLE.md, memory `sdc-physical-containment-why-ram-flat`). So a host-side loop may
watch it "to your heart's content." This wakes on each new pool job, reads the fold's win-latches + every model node's
latch (read-only — the external files under C:/llm/sdc_fold + C:/llm/sdc_out, never the running gates), and submits INSIDE
the job window so it's never stale: a real block if any latch fired, else a live group-0 verdict. Loops per block.

It NEVER touches the running SDC. Default is check-only (no model writes at all). `--arm` also fires the one-time button
(`sdc_button_big.py`) per new job — the sanctioned one-shot that routes the block + one signal and dies. Bounded and
stoppable: stops on `C:/llm/sdc_out/autopilot_stop`, on --max-blocks, on --max-seconds, or Ctrl-C. No numpy.

  python host/sdc_autopilot.py                 # check-only, self-waking, submits per block (default 5 blocks)
  python host/sdc_autopilot.py --arm           # also re-arm the SDC (one-shot button) on each new block
  python host/sdc_autopilot.py --forever       # run until the stop file / Ctrl-C
  python host/sdc_autopilot.py --window 15 --max-blocks 10
  # stop a running one:  create the file  C:/llm/sdc_out/autopilot_stop
"""
import json, os, socket, struct, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
REG = "C:/llm/models/titan_circuits.json"; TITAN = "C:/llm/models/titan.gguf"
FOLD_MAN = "C:/llm/sdc_fold/manifest.json"; FOLD_DIR = "C:/llm/sdc_fold"; FED = "C:/llm/sdc_fold/federation.json"
OUT = "C:/llm/sdc_out"; JOB = OUT + "/big_job.json"; STOP = OUT + "/autopilot_stop"; LOG = OUT + "/autopilot_log.jsonl"
WALLET = "bc1qvhrzg0e23f3tz2jgymwwtqacn48trf5m524zlq"
POOL_HOST = os.environ.get("TITAN_POOL_HOST", "solo.ckpool.org"); POOL_PORT = int(os.environ.get("TITAN_POOL_PORT", "3333"))


def opt(name, default=None, flag=False):
    if flag: return name in sys.argv
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv): return sys.argv[i + 1]
    return default


ARM = opt("--arm", flag=True)
FOREVER = opt("--forever", flag=True)
WINDOW = float(opt("--window", "8"))                 # seconds into the job before submitting (well inside a job's life)
MAX_BLOCKS = 10**9 if FOREVER else int(opt("--max-blocks", "5"))
MAX_SECONDS = float(opt("--max-seconds", "1800"))    # a hard bound so it never orphans (default 30 min)


def latch_at(path, off):                             # read a 5-byte win-latch (status u8 + nonce u32) if fired
    try:
        with open(path, "rb") as f:
            f.seek(off); rec = f.read(5)
        return struct.unpack_from("<I", rec, 1)[0] if rec and rec[0] == 1 else None
    except Exception:
        return None


def read_safezone():
    """scan the OUTSIDE-sandbox safezone for a winner: fold-file latches + every federated model node's latch. read-only."""
    if os.path.exists(FOLD_MAN):
        man = json.load(open(FOLD_MAN)); tier = man.get("tier", "full")
        if tier in ("bitmap", "winner"):
            for fe in man["files"]:
                p = f"{FOLD_DIR}/{fe['name']}"; nz = latch_at(p, os.path.getsize(p) - 5)
                if nz is not None: return ("disk", fe["name"], nz)
        else:                                        # explicit tiers: answer slot per routed group
            job = json.load(open(JOB)) if os.path.exists(JOB) else {"n_route": 0}
            GBY = int(man["group_bytes"]); asf = 76 if tier == "full" else 8
            spans = []; acc = 0
            for fe in man["files"]:
                spans.append((acc, acc + fe["groups"], f"{FOLD_DIR}/{fe['name']}")); acc += fe["groups"]
            for k in range(int(job.get("n_route", 0))):
                for lo, hi, p in spans:
                    if lo <= k < hi:
                        nz = latch_at(p, (k - lo) * GBY + asf)
                        if nz is not None: return ("disk", k, nz)
                        break
    if os.path.exists(FED):
        for node in json.load(open(FED))["nodes"]:
            nz = latch_at(node["path"], node["off"] + 8 + 4 + 8 + 32)
            if nz is not None: return ("node%d" % node["node_id"], os.path.basename(node["path"]), nz)
    return None


def pool_connect():
    s = socket.create_connection((POOL_HOST, POOL_PORT), timeout=20); buf = {"b": b""}
    def send(o): s.sendall((json.dumps(o) + "\n").encode())
    def lines():
        out = []; s.settimeout(2)
        try: buf["b"] += s.recv(8192)
        except Exception: return out
        while b"\n" in buf["b"]:
            ln, buf["b"] = buf["b"].split(b"\n", 1)
            if ln.strip():
                try: out.append(json.loads(ln))
                except Exception: pass
        return out
    send({"id": 1, "method": "mining.subscribe", "params": ["titan-autopilot/1.0"]})
    en2sz = 8; t = time.time() + 15
    while time.time() < t:
        for m in lines():
            if m.get("id") == 1 and m.get("result"):
                en2sz = m["result"][2]; send({"id": 2, "method": "mining.authorize", "params": [WALLET, "x"]})
    return s, send, lines, en2sz


def submit(send, lines, job_id, en2sz, ntime, win):
    if win is not None:
        src, key, nonce = win; en2 = "%0*x" % (2 * en2sz, key if isinstance(key, int) else 0); kind = f"BLOCK ({src} {key})"
    else:
        en2 = "%0*x" % (2 * en2sz, 0); nonce = 0; kind = "live verdict (no win)"
    send({"id": 100, "method": "mining.submit", "params": [WALLET, job_id, en2, ntime, "%08x" % (nonce & 0xffffffff)]})
    verdict = None; t = time.time() + 10
    while time.time() < t:
        for m in lines():
            if m.get("id") == 100: verdict = m
        if verdict: break
    res = "ACCEPTED" if (verdict and verdict.get("result") is True) else (str(verdict.get("error")) if verdict else "(no reply)")
    return kind, en2, nonce, res


def main():
    if os.path.exists(STOP): os.remove(STOP)
    os.makedirs(OUT, exist_ok=True)
    mode = "ARM+CHECK" if ARM else "CHECK-ONLY"
    print(f"autopilot up ({mode}): watching {POOL_HOST}:{POOL_PORT}, window={WINDOW:.0f}s, "
          f"max_blocks={MAX_BLOCKS if not FOREVER else 'unbounded'}, max_seconds={MAX_SECONDS:.0f}. "
          f"stop: create {STOP}", flush=True)
    s, send, lines, en2sz = pool_connect()
    seen = set(); n = 0; t_start = time.time()
    try:
        while n < MAX_BLOCKS and (time.time() - t_start) < MAX_SECONDS:
            if os.path.exists(STOP): print("stop file — exiting cleanly."); break
            job = None
            for m in lines():
                if m.get("method") == "mining.notify":
                    p = m["params"]; job = {"job_id": p[0], "ntime": p[7]}
            if not job or job["job_id"] in seen:
                time.sleep(1); continue
            seen.add(job["job_id"]); n += 1
            if ARM:                                    # sanctioned one-shot: route block + ONE signal, then it dies
                subprocess.run([sys.executable, os.path.join(HERE, "sdc_button_big.py")],
                               timeout=60, cwd=HERE, capture_output=True)
            time.sleep(WINDOW)                         # land INSIDE the job window -> never stale
            if os.path.exists(STOP): break
            win = read_safezone()                      # read the OUTSIDE-sandbox safezone (never the running SDC)
            kind, en2, nonce, res = submit(send, lines, job["job_id"], en2sz, job["ntime"], win)
            rec = {"ts_rel": round(time.time() - t_start, 1), "block": n, "job_id": job["job_id"],
                   "armed": ARM, "kind": kind, "en2": en2, "nonce": nonce, "verdict": res}
            open(LOG, "a").write(json.dumps(rec) + "\n")
            print(f"  block {n}: job {job['job_id']} -> submitted {kind}: {res}", flush=True)
    finally:
        try: s.close()
        except Exception: pass
    print(f"autopilot done: {n} block(s) checked, {mode}. log: {LOG}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
