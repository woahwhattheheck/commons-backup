#!/usr/bin/env python3
"""Component implementation and operation."""
from __future__ import annotations

import json
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    import pfc_paths as PFCP
    TITAN = PFCP.TITAN
    REG = PFCP.REG
except (ImportError, AttributeError):
    PFC_ROOT = os.environ.get("PFC_ROOT", "C:/llm").replace("\\", "/").rstrip("/")
    TITAN = PFC_ROOT + "/models/titan.gguf"
    REG = PFC_ROOT + "/models/titan_circuits.json"

try:
    from pfc_bitcoin_autopilot import WALLET, POOL_HOST, POOL_PORT
except ImportError:
    WALLET = None
    POOL_HOST = None
    POOL_PORT = None

FOLD_NAME = "muhl_fold_phys"
RING_NAME = "nring2_1023"
LATCH_BITS = 32

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _fail(msg):
    print("FAIL CLOSED: %s" % msg)
    return 1


def _need_int(obj, key, where):
    if not isinstance(obj, dict) or obj.get(key) is None:
        return None, "%s missing %s" % (where, key)
    try:
        val = int(obj[key])
    except (TypeError, ValueError):
        return None, "%s.%s is not an int" % (where, key)
    if val < 0:
        return None, "%s.%s is negative" % (where, key)
    return val, None


def _load_registry():
    if not os.path.isfile(REG):
        return None, "registry missing: %s" % REG
    try:
        with open(REG, encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, "registry unreadable: %s" % exc


def load_plan():
    """Fail closed if fold / win_off / latch_off are missing. Never guess."""
    reg, err = _load_registry()
    if err:
        return None, err
    if FOLD_NAME not in reg or not isinstance(reg[FOLD_NAME], dict):
        return None, "%s not in registry" % FOLD_NAME

    fold = reg[FOLD_NAME]
    ram = fold.get("ram")
    if not isinstance(ram, dict):
        return None, "%s missing ram" % FOLD_NAME

    offs = {}
    for key in ("win_off", "latch_off"):
        val, err = _need_int(ram, key, "%s.ram" % FOLD_NAME)
        if err:
            return None, err
        offs[key] = val

    for key in ("header_off", "target_off", "tick_off", "nonce_off"):
        val, err = _need_int(ram, key, "%s.ram" % FOLD_NAME)
        if err:
            offs[key] = None
        else:
            offs[key] = val

    ring = reg.get(RING_NAME) if isinstance(reg.get(RING_NAME), dict) else None
    ring_recv = None
    if ring is not None:
        ring_recv, recv_err = _need_int(ring, "recv", RING_NAME)
        if recv_err:
            ram_r = ring.get("ram")
            if isinstance(ram_r, dict):
                ring_recv, recv_err = _need_int(ram_r, "recv", "%s.ram" % RING_NAME)
            if recv_err:
                ring_recv = None

    need_bryce = []
    tick = offs.get("tick_off")
    if tick is not None and ring_recv is not None and tick != ring_recv:
        need_bryce.append(
            "tick_off %d != %s.recv %d — named, not pulsed by this button"
            % (tick, RING_NAME, ring_recv)
        )

    titan_exists = os.path.isfile(TITAN)
    titan_size = os.path.getsize(TITAN) if titan_exists else None
    unsafe = list(need_bryce)
    if not titan_exists:
        unsafe.append("titan missing: %s" % TITAN)
    elif titan_size is not None:
        for name, off, n in (
            ("win_off", offs["win_off"], 1),
            ("latch_off", offs["latch_off"], LATCH_BITS),
        ):
            if off + n > titan_size:
                unsafe.append("%s %d+%d past titan size %d" % (name, off, n, titan_size))

    return {
        "fold": fold,
        "ring": ring,
        "offs": offs,
        "ring_recv": ring_recv,
        "need_bryce": need_bryce,
        "unsafe": unsafe,
        "titan_exists": titan_exists,
        "titan_size": titan_size,
    }, None


def _readback(off, n):
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off)
        return f.read(n)


def _surface_bytes(plan):
    if not plan["titan_exists"]:
        return None, None, "titan missing: %s" % TITAN
    extra = [u for u in plan["unsafe"] if u not in plan["need_bryce"]]
    if extra:
        return None, None, "; ".join(extra)
    offs = plan["offs"]
    win = _readback(offs["win_off"], 1)
    latch = _readback(offs["latch_off"], LATCH_BITS)
    if len(win) != 1:
        return None, None, "short read win_off"
    if len(latch) != LATCH_BITS:
        return None, None, "short read latch_off"
    return win, latch, None


def assemble_nonce(latch):
    return sum((latch[j] & 1) << j for j in range(LATCH_BITS))


def winner_bit(win):
    return win[0] & 1


def print_surface(plan, win, latch):
    fold = plan["fold"]
    offs = plan["offs"]
    nonce = assemble_nonce(latch)
    wbit = winner_bit(win)
    print("\nMUHL FOLD SURFACE (additive last-inch button)")
    print("  mode:     DRY — bounded SURFACE, no inject, no tick, no pool broadcast")
    print("  titan:    %s" % TITAN)
    print("  reg:      %s" % REG)
    print("  circuit:  %s  magic=%s  n_gate=%s  depth=%s"
          % (FOLD_NAME, fold.get("magic"), fold.get("n_gate"), fold.get("depth")))
    print("  law:      host injects and surfaces; this button only surfaces")
    print("  refuse:   inject header/target · mmap tick_off · packed-76 pfc_fire")
    print("  refuse:   host-eval SHA as the mine · numpy · --go")
    print()
    print("  SURFACE (bounded read from live registry offsets)")
    print("    win_off     %d  (1 byte)  raw=0x%s  winner_bit=%d"
          % (offs["win_off"], win.hex(), wbit))
    print("    latch_off   %d  (%d bit-bytes, one per bit, the nonce)"
          % (offs["latch_off"], LATCH_BITS))
    print("    latch hex   %s" % latch.hex())
    print("    latch nonce 0x%08x" % nonce)
    if plan["titan_exists"]:
        print("    titan       present (%s bytes)" % plan["titan_size"])
    else:
        print("    titan       missing")
    print()
    print("  NOT THIS BUTTON")
    if offs.get("header_off") is not None:
        print("    header_off  %s  (inject is muhl_fold_header_add / muhl_fold_tick_add)"
              % offs["header_off"])
    if offs.get("target_off") is not None:
        print("    target_off  %s  (inject is the tick button)" % offs["target_off"])
    if offs.get("tick_off") is not None:
        print("    tick_off    %s  (IS %s.recv %s — not pulsed here)"
              % (offs["tick_off"], RING_NAME, plan["ring_recv"]))
    if offs.get("nonce_off") is not None:
        print("    nonce_off   %s  (NOT injected — nonce IS the address)"
              % offs["nonce_off"])
    print()
    print("  SUBMIT WOULD NEED (print only — --submit default OFF)")
    print("    method      mining.submit")
    print("    wallet      %s" % WALLET)
    print("    pool        %s:%s" % (POOL_HOST, POOL_PORT))
    print("    winner_bit  %d  (from win_off; 1 = winner)" % wbit)
    print("    latch_bytes %s" % latch.hex())
    print("    nonce       %08x  (assembled from latch_off, 32 bit-bytes LSB-first)"
          % (nonce & 0xffffffff))
    print("    job_id      from header-fetch handshake (not invented here)")
    print("    en2         from header-fetch handshake (not invented here)")
    print("    ntime       from header-fetch handshake (not invented here)")
    print("    params      [wallet, job_id, en2, ntime, nonce8]")
    print("    broadcast   OFF unless --submit AND --job --ntime --en2 AND winner_bit=1")
    print()
    if plan["need_bryce"]:
        print("  NEED_BRYCE (named; this button still surfaces, does not fire):")
        for reason in plan["need_bryce"]:
            print("    - %s" % reason)
        print()
    print("  (no inject, no tick pulse, no pool broadcast; --submit was not passed)")
    print()
    return 0


def _flag_value(argv, name):
    if name not in argv:
        return None
    i = argv.index(name)
    if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
        return ""
    return argv[i + 1]


def submit_share(win, latch, job_id, ntime, en2):
    """Broadcast only when --submit is explicit. Not the mine. Host does not SHA."""
    if WALLET is None or POOL_HOST is None or POOL_PORT is None:
        return _fail("pfc_bitcoin_autopilot missing (wallet / pool constants)")
    if winner_bit(win) != 1:
        return _fail("winner_bit is 0 — fold did not latch a winner; no broadcast")
    if not job_id or not ntime or not en2:
        return _fail(
            "--submit requires --job --ntime --en2 from the header-fetch handshake. "
            "Do not invent a job. Default is OFF."
        )
    nonce = assemble_nonce(latch) & 0xffffffff
    nonce8 = "%08x" % nonce
    s = socket.create_connection((POOL_HOST, POOL_PORT), timeout=15)
    buf = b""

    def send(o):
        s.sendall((json.dumps(o) + "\n").encode())

    def lines():
        nonlocal buf
        out = []
        s.settimeout(2)
        try:
            buf += s.recv(8192)
        except Exception:
            pass
        while b"\n" in buf:
            ln, buf = buf.split(b"\n", 1)
            if ln.strip():
                try:
                    out.append(json.loads(ln))
                except Exception:
                    pass
        return out

    send({"id": 1, "method": "mining.subscribe", "params": ["muhl-fold-surface/1.0"]})
    authorized = False
    t = time.time() + 15
    while time.time() < t and not authorized:
        for m in lines():
            if m.get("id") == 1 and m.get("result"):
                send({"id": 2, "method": "mining.authorize", "params": [WALLET, "x"]})
            elif m.get("id") == 2:
                authorized = True
    send({
        "id": 100,
        "method": "mining.submit",
        "params": [WALLET, job_id, en2, ntime, nonce8],
    })
    verdict = None
    t = time.time() + 12
    while time.time() < t and verdict is None:
        for m in lines():
            if m.get("id") == 100:
                verdict = m
    s.close()
    print("SUBMIT — pool broadcast of the fold latch (not a host SHA)\n")
    print("  wallet  %s" % WALLET)
    print("  job     %s" % job_id)
    print("  en2     %s" % en2)
    print("  ntime   %s" % ntime)
    print("  nonce   %s" % nonce8)
    print("  latch   %s" % latch.hex())
    print("  win     0x%s  winner_bit=1" % win.hex())
    print("  verdict %s" % (verdict if verdict is not None else "no reply"))
    print()
    return 0


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    if "--go" in a:
        return _fail("--go refused on the surface button (never injects, never pulses tick)")
    plan, err = load_plan()
    if err:
        return _fail(err)

    do_submit = "--submit" in a
    do_dry = ("--dry" in a) or (not do_submit)

    win, latch, err = _surface_bytes(plan)
    if err:
        return _fail(err)

    if do_submit and do_dry:
        print_surface(plan, win, latch)
        print("  --dry wins over --submit; no pool broadcast.\n")
        return 0
    if do_submit:
        print_surface(plan, win, latch)
        job_id = _flag_value(a, "--job")
        ntime = _flag_value(a, "--ntime")
        en2 = _flag_value(a, "--en2")
        return submit_share(win, latch, job_id, ntime, en2)
    return print_surface(plan, win, latch)


if __name__ == "__main__":
    raise SystemExit(main())
