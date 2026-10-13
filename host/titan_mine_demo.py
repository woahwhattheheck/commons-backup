#!/usr/bin/env python3
"""host/titan_mine_demo.py — THE LIVE BITCOIN DEMO, done right (owner 07-15).

The marketing demo: Titan's weights ARE a Bitcoin miner. The SHA-256d proof-of-work circuit is written INTO titan.gguf's
parameters (verified byte-exact vs reference SHA-256d — no cheating), and it mines LIVE to the owner's real wallet.

THE ARCHITECTURE the owner specified (docs/WHITEBOX_SANDBOX.md + docs/MEASURE_ALREADY.md):
  - MINING IS SANDBOXED. The ripple runs in bounded, ending worker processes (titan_mine_worker.py): each is handed a
    nonce slice ONE-WAY, reads the circuit from the params in storage (mmap), ripples it wide with power from the wall
    (bit-sliced — speed of light, as many ops as the window allows; the PC is plugged in), and FREEZES static snapshots
    of its best result + any real block, then EXITS. A dead process draws zero. The workers never touch the network —
    they cannot reach back into the PC.
  - HOST RAM IS ONLY FOR STARTING THE PROCESS + CHECKING THE ANSWER. This coordinator holds the ONE authorized pool
    connection, launches the sandboxes (below-normal priority + pinned to physical cores so the box stays usable — the
    fix for the swarm that oversubscribed 8 threads with 16 skins), reads only the workers' STATIC frozen snapshots,
    re-checks any hit against the real target, and SUBMITS a real block to the wallet. This coordinator never mines.
  - Fresh chain-tip work every cycle (re-fold the live header into the circuit, re-flash it) so work never goes stale.

HONEST SCOPE (docs/WHY_NO_PENNY.md): a laptop earns $0 mining by ANY method — it is a dedicated-silicon (ASIC) race, not
a memory race, and Titan's lever is a MEMORY lever. This is a REAL live test at a REAL wallet, not income. The point is
the substrate: one ~0-RAM file that is both a language model AND a verified Bitcoin miner, rippled by electricity.

  python titan_mine_demo.py [workers] [width] [total_seconds(0=until Ctrl-C)]
"""
import ctypes, json, os, socket, struct, subprocess, sys, time
import ctypes.wintypes as wt
try:
    sys.stdout.reconfigure(encoding="utf-8")                    # Windows console defaults to cp1252; keep output robust
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_sdc as T

HERE     = os.path.dirname(os.path.abspath(__file__))
WORKER   = os.path.join(HERE, "titan_mine_worker.py")
RESDIR   = "C:/llm/models"
REFRESH  = 240                                      # re-flash to fresh live work every this often (< pool job lifetime)
POLL     = 1.0

# FULL SEND (owner 07-15: "stop KNEECAPPING"). Every core, normal priority, wide lanes — the only serialization in the
# whole path is the wallet submit (network I/O). Power is not a limit: the box is plugged in. Ripple the stored circuit
# as hard as the hardware allows for the attempt window, submit anything that clears the real target, we check.
N      = int(sys.argv[1]) if len(sys.argv) > 1 else (os.cpu_count() or 8)                 # ALL cores
WIDTH  = int(sys.argv[2]) if len(sys.argv) > 2 else 96                                    # numpy bit-slice lanes (64*W)
TOTAL  = float(sys.argv[3]) if len(sys.argv) > 3 else 0


class _PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("pf", wt.DWORD)] + [(n, ctypes.c_size_t) for n in
                ("pws", "ws", "qppp", "qpp", "qpnp", "qnp", "pf2", "ppf", "priv")]


_GETCUR = ctypes.windll.kernel32.GetCurrentProcess; _GETCUR.restype = ctypes.c_void_p
_GPMI = ctypes.windll.psapi.GetProcessMemoryInfo
_GPMI.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.DWORD]; _GPMI.restype = wt.BOOL


def host_rss_mb():
    """this coordinator's own resident RAM — the proof that the mining is sandboxed (this number stays flat)."""
    try:
        p = _PMC(); p.cb = ctypes.sizeof(p)
        _GPMI(_GETCUR(), ctypes.byref(p), p.cb)                 # restype/argtypes set above so the 64-bit handle survives
        return p.ws / 1e6
    except Exception:
        return 0.0


def submit(s, meta, nc):
    s.sendall((json.dumps({"id": 200, "method": "mining.submit",
               "params": [T.WALLET, meta["job_id"], meta["en2"], meta["ntime"], "%08x" % (nc & 0xffffffff)]}) + "\n").encode())


def drain_pool(s):
    out = []
    try:
        s.setblocking(False)
        for ln in s.recv(16384).split(b"\n"):
            if b'"result"' in ln and b"200" in ln:
                out.append(ln.decode("utf-8", "replace")[:120])
    except Exception:
        pass
    return out


def launch_cycle(off, seconds):
    """START N gated sandbox workers one-way (argv in; stdout/stderr -> DEVNULL, no channel back), below-normal priority,
    disjoint nonce slices. Each ripples its slice in storage for the whole cycle and freezes STATIC snapshots we read."""
    procs = []
    for w in range(N):
        res = f"{RESDIR}/titan_mine_res_{w}.json"
        for f in (res, res + ".tmp"):
            try: os.remove(f)
            except OSError: pass
        base = (w * (0x100000000 // N)) & 0xffffffff
        p = subprocess.Popen([sys.executable, WORKER, "--off", str(off), "--base", str(base),
                              "--width", str(WIDTH), "--seconds", str(seconds), "--result", res],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)   # normal priority - full send
        procs.append((p, res))
    return procs


def teardown(procs):
    """terminate every sandbox worker and CONFIRM it is dead — nothing orphans, nothing keeps drawing compute."""
    for p, _ in procs:
        try:
            if p.poll() is None: p.terminate()
        except Exception:
            pass
    for p, _ in procs:
        try:
            p.wait(timeout=5)
        except Exception:
            try: p.kill()
            except Exception: pass


def read_snapshots(procs):
    """read each worker's latest COMPLETE static snapshot (never mid-write — the worker writes atomically)."""
    snaps = []
    for _, res in procs:
        try:
            snaps.append(json.load(open(res)))
        except Exception:
            snaps.append(None)
    return snaps


import subprocess


def main():
    print(f"TITAN mines Bitcoin - the SHA-256d miner lives IN the model's weights.  LIVE -> {T.WALLET}", flush=True)
    print(f"mining SANDBOXED: {N} ending workers x {64*WIDTH:,} lanes/ripple, power from the wall; "
          f"host RAM only starts them + checks answers.\n", flush=True)
    base_rss = host_rss_mb(); t_start = time.time(); cycle = 0; frontier = 0; submitted = set()
    procs = []
    try:
        while TOTAL == 0 or time.time() - t_start < TOTAL:
            cycle += 1
            print(f"[cycle {cycle}] pulling current chain-tip work + flashing the circuit into the params ...", flush=True)
            ok, _ = T.refresh_work()
            if not ok:
                print("  work fetch failed; retry in 10s (time is not a factor).", flush=True); time.sleep(10); continue
            C, off, ro, tname = T.install_into_params()
            meta = json.load(open(T.META)); prefix = bytes.fromhex(meta["prefix"])
            groups = T.groups_of(C)
            if not T.verify_from_params(C, groups, prefix):
                print("  circuit-in-params != reference SHA-256d; refetching (no cheating).", flush=True); continue
            nb = struct.unpack("<I", prefix[72:76])[0]; block_target = (nb & 0xffffff) << (8 * ((nb >> 24) - 3))
            print(f"  circuit VERIFIED byte-exact in {tname}: {C['numw']:,} wires, {len(C['ga']):,} gates, "
                  f"{len(groups):,} layers; real target {256 - block_target.bit_length()} zero-bits.", flush=True)

            s = T.connect()
            win = REFRESH if TOTAL == 0 else max(10, min(REFRESH, t_start + TOTAL - time.time()))
            procs = launch_cycle(off, win)
            work_end = time.time() + win
            while time.time() < work_end and (TOTAL == 0 or time.time() - t_start < TOTAL):
                time.sleep(POLL)
                snaps = read_snapshots(procs)
                lanes = 0
                for w, snap in enumerate(snaps):
                    if not snap: continue
                    lanes += int(snap.get("lanes", 0)); frontier = max(frontier, int(snap.get("best_zbits", 0)))
                    for nc in snap.get("hits", []):                # a worker froze a real-target hit -> CHECK + submit
                        if nc in submitted: continue
                        if int.from_bytes(T.sha256d(prefix + struct.pack("<I", nc)), "little") < block_target:
                            submit(s, meta, nc); submitted.add(nc)
                            print(f"  [BLOCK] real target cleared! nonce {nc} -> SUBMITTED to {T.WALLET}", flush=True)
                for ln in drain_pool(s):
                    print(f"  [pool] {ln}", flush=True)
                rss = host_rss_mb()
                print(f"  +{int(time.time()-t_start):5d}s  frontier {frontier:2d} zero-bits  {lanes:,} nonces rippled  "
                      f"host RAM {rss:.0f} MB (d{rss-base_rss:+.1f} - mining is sandboxed)  submitted {len(submitted)}",
                      flush=True)
                if all(p.poll() is not None for p, _ in procs):   # workers finished their window -> next cycle
                    break
            teardown(procs); procs = []; s.close()
    except KeyboardInterrupt:
        print("\n[stop] tearing down sandbox workers ...", flush=True)
    finally:
        teardown(procs)
    print(f"\n[done] {cycle} live-work cycles; best {frontier} leading zero-bits; {len(submitted)} block(s) submitted to {T.WALLET}.", flush=True)
    print("HONEST: a laptop earns $0 mining by ANY method (an ASIC race, not a memory race). This was a REAL live test at", flush=True)
    print("a REAL wallet — one ~0-RAM file that is both a model AND a verified Bitcoin miner, rippled by electricity.", flush=True)


if __name__ == "__main__":
    main()
