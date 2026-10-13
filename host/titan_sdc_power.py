#!/usr/bin/env python3
"""host/titan_sdc_power.py — POWERED MODE: drive the armed SDC as hard as the box's physics safely allows (owner 07-15).

Two SDC modes, both spec-clean:
  STATIC (proven)  — inject once -> the file sits at rest, 0 processes / 0 RAM / 0 compute -> manual check. The substrate
                     existence proof.
  POWERED (here)   — deliberately SPEND electrical work to advance the stored gates. The owner's barrier is pure physics:
                     power draw the silicon can sustain without damage (the utility bill is not a cost to him). RAM is not
                     the limit — the miner circuit is ONE page-cached copy in titan.gguf, so N skins mmap the SAME bits and
                     parallelism is free in memory. So we run one SDC skin per core, FULL SEND, and let the CPU's own
                     thermal management be the governor (silicon self-throttles — it protects itself).

Every skin stays spec-clean: handed its slice ONE-WAY via argv, CUT OFF (no socket, nothing polls it), ripples the stored
gate-net (pure Python bit-slice, NO numpy) for a CALIBRATED number of ripples, freezes its static answer, and EXITS. This
driver only (1) launches them, (2) waits — it never pokes a running SDC — and (3) after they are all STATIC, reads their
answers, writes any winning nonce into the SDC's answer register, and reports the throughput. Bounded + atexit-guarded so
nothing orphans. The wallet submit stays the separate manual step (titan_sdc_check.py).

  python host/titan_sdc_power.py [burst_seconds]        # default 45s full-send burst; needs an armed SDC (inject first)
"""
import atexit, json, os, signal, struct, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_sdc as T

ARMED = "C:/llm/models/titan_sdc_armed.json"
SOLVE = os.path.join(HERE, "titan_sdc_solve.py")
RESDIR = "C:/llm/models"

N     = int(os.environ.get("SDC_SKINS", str(os.cpu_count() or 8)))   # one SDC per core — FULL SEND (free replication)
W     = int(os.environ.get("SDC_WIDTH", "2048"))                     # lanes/skin: amortizes interpreter overhead, small wire-state
BURST = float(sys.argv[1]) if len(sys.argv) > 1 else 45.0            # bounded electrical-work burst; skins self-terminate
RATE  = float(os.environ.get("SDC_RATE_NPS", "6000"))               # documented nonce/s/skin (this box) — only sets K

_procs = []
def _kill():
    for p in _procs:
        try:
            if p.poll() is None: p.terminate()
        except Exception: pass
    for p in _procs:
        try: p.wait(timeout=3)
        except Exception:
            try: p.kill()
            except Exception: pass
atexit.register(_kill)
for _s in (signal.SIGINT, signal.SIGTERM):
    try: signal.signal(_s, lambda *a: (_kill(), os._exit(0)))
    except Exception: pass


def main():
    if not os.path.exists(ARMED):
        print("no armed SDC — run titan_sdc_inject.py first (the one-way block-data send)."); return
    a = json.load(open(ARMED)); off = int(a["off"]); ro = int(a["result_off"])
    K = max(1, round(BURST * RATE / W))
    print(f"POWERED MODE — full send: {N} SDC skins x {W} lanes over {a.get('gates','?'):,} stored gates (block {a['job_id']}).", flush=True)
    print(f"the miner is ONE page-cached copy; skins share it -> parallelism is free in RAM. barrier = watts, not memory.", flush=True)
    print(f"calibrated: K={K} ripples/skin (~{BURST:.0f}s), sweeping ~{N*K*W:,} nonces. governor = the CPU's own thermal limit.\n", flush=True)

    procs = []
    for i in range(N):
        res = f"{RESDIR}/titan_sdc_pw_{i}.json"
        for f in (res, res + ".tmp"):
            try: os.remove(f)
            except OSError: pass
        base = (i * (0x100000000 // N)) & 0xffffffff
        p = subprocess.Popen([sys.executable, SOLVE, "--off", str(off), "--base", str(base), "--width", str(W),
                              "--ripples", str(K), "--result", res], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append((p, res)); _procs.append(p)
    print(f"[power] {N} SDC skins rippling full-send on power. Not polled, not touched. Waiting for the static stop ...", flush=True)
    t0 = time.time()
    deadline = t0 + BURST + 120                                   # hard backstop so nothing can orphan
    for p, _ in procs:
        try: p.wait(timeout=max(1, deadline - time.time()))
        except Exception:
            try: p.kill()
            except Exception: pass
    run_secs = max(0.1, time.time() - t0)

    swept = 0; best = 0; shares = []; blocks = []; best_hi = 1 << 32; best_nonce = None
    for _, res in procs:
        try: d = json.load(open(res))
        except Exception: continue
        if d.get("error"): continue
        swept += int(d.get("swept", 0)); best = max(best, int(d.get("best_zbits", 0)))
        shares += d.get("shares", []); blocks += d.get("blocks", [])
        if int(d.get("best_hi", 1 << 32)) < best_hi: best_hi = int(d.get("best_hi", 1 << 32)); best_nonce = d.get("best_nonce")

    thr = swept / run_secs
    print(f"\n[static] all skins stopped in {run_secs:.0f}s.", flush=True)
    print(f"  swept {swept:,} nonces  ->  {thr:,.0f} nonces/s aggregate at full send  (this box's SDC power-barrier rate)", flush=True)
    print(f"  best {best} leading zero-bits;  {len(shares)} share(s), {len(blocks)} block(s) this burst.", flush=True)

    winner = (blocks + shares or ([int(best_nonce)] if best_nonce is not None and (blocks or shares) else []))
    if winner:                                                   # latch the answer into the SDC's register for the manual check
        with open(T.TITAN, "r+b") as fp:
            fp.seek(ro); fp.write(b"\x01" + struct.pack("<I", int(winner[0]) & 0xffffffff))
        print(f"  answer register @ {ro} set: nonce {winner[0]} — run titan_sdc_check.py to submit it to the wallet.", flush=True)
    else:
        print("  answer register unchanged (no target cleared this burst).", flush=True)
    print("\n[done] powered burst complete; the SDC is static again. 0 processes left.", flush=True)


if __name__ == "__main__":
    try: main()
    finally: _kill()
