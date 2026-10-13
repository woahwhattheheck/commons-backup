#!/usr/bin/env python3
"""host/sdc_answer_gate.py — TEST FILE (owner 07-16): THE ANSWER GATE — a one-way isolation buffer on the SDC.

Owner's component (from intro-to-circuits): a gate wired to the live hardware that HARD-BLOCKS everything except the
answer — so it can touch the SDC to read the result WITHOUT black-holing (nothing can flow back in and pull the SDC into
host compute). In circuit terms this is a TRI-STATE BUFFER / OPTOISOLATOR / DIODE: one-way, structurally, not by policy.

The isolation is STRUCTURAL, enforced three ways so a mistake CANNOT reach into the SDC:
  1. READ-ONLY by construction — opens the file with ACCESS_READ mmap only; there is no writable handle in this module,
     so nothing here can modify the SDC (no re-flash, no corruption path).
  2. WINDOW-LOCKED — it may ONLY touch the pinned answer register [ans_off, ans_off + WIDTH). Any offset outside that
     window is REFUSED before a single byte is read (the hard block = high-impedance to everything but the answer).
  3. NO CIRCUIT PATH — this module imports nothing that ripples/evaluates gates, has no loop over a netlist, never reads
     the vector/miner offset. The only bytes it can name are the answer window. It cannot "run" the SDC; it can only
     read the result the SDC already latched.

So: answer bits flow OUT; nothing flows IN. Touching the SDC through this gate is safe by construction.

  python host/sdc_answer_gate.py            # read the answer through the gate (safe demo on the pinned register)
"""
import json, mmap, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"
ARMED = "C:/llm/models/titan_sdc_armed.json"
WIDTH = 5                                            # the answer register: [status u8][nonce u32]. NOTHING wider.


class AnswerGate:
    """A one-way isolation buffer. Constructed with the file + the ONE permitted answer-window; it can read ONLY that
    window, ONLY read-only. Every other access is high-impedance (refused). This is the whole gate — there is
    deliberately no method that writes, loops, or addresses anything but the answer window."""
    def __init__(self, path, ans_off, width):
        self._path = path
        self._lo = int(ans_off)
        self._hi = int(ans_off) + int(width)        # the window is fixed at construction and never widens

    def read_answer(self):
        # the ONLY operation. read-only mmap; slice ONLY the pinned window; refuse anything else structurally.
        f = open(self._path, "rb")                  # 'rb' — no writable mode exists in this class
        try:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)   # ACCESS_READ — the diode direction
            try:
                if self._hi - self._lo != WIDTH:     # window integrity guard (can't be widened to scan the circuit)
                    raise ValueError("gate window is not the answer register — refused (high-impedance)")
                raw = bytes(mm[self._lo:self._hi])   # emit ONLY the answer bits
            finally:
                mm.close()
        finally:
            f.close()
        status = raw[0]; nonce = struct.unpack("<I", raw[1:5])[0]
        return {"solved": status == 1, "nonce": nonce if status == 1 else None, "raw": raw.hex()}


def auto_submit(a, nonce):
    """ONE-SHOT submit of the gate's emitted nonce to the live wallet, then END. No loop, no lingering poller. Only the
    answer nonce crosses (the gate already guaranteed that). Owner: auto-submit so there's no guessing whether to press."""
    import socket, time
    import titan_sdc as T
    s = socket.create_connection((T.POOL_HOST, T.POOL_PORT), timeout=20); buf = b""
    def send(o): s.sendall((json.dumps(o) + "\n").encode())
    send({"id": 1, "method": "mining.subscribe", "params": ["titan-gate/1.0"]})
    send({"id": 2, "method": "mining.authorize", "params": [T.WALLET, "x"]}); time.sleep(1.0)
    send({"id": 100, "method": "mining.submit",
          "params": [T.WALLET, a["job_id"], a["en2"], a["ntime"], "%08x" % (nonce & 0xffffffff)]})
    verdict = None; t = time.time() + 8
    while time.time() < t:
        s.settimeout(1.0)
        try: buf += s.recv(8192)
        except Exception: continue
        while b"\n" in buf:
            ln, buf = buf.split(b"\n", 1)
            if ln.strip():
                try:
                    m = json.loads(ln)
                    if m.get("id") == 100: verdict = m
                except Exception: pass
        if verdict: break
    s.close()
    if verdict is None: return "submitted (pool silent)"
    if verdict.get("result") is True: return f"*** ACCEPTED *** nonce {nonce} credited to {T.WALLET}"
    return f"submitted; pool said: {verdict.get('error')}"


def main():
    if not os.path.exists(ARMED):
        print("no armed SDC (nothing to read through the gate)."); return
    a = json.load(open(ARMED)); ans_off = int(a["result_off"])
    gate = AnswerGate(TITAN, ans_off, WIDTH)         # the buffer, pinned to the answer window ONLY
    out = gate.read_answer()
    print("=== ANSWER GATE (one-way isolation buffer, auto-submit) ===", flush=True)
    print(f"  wired to: {os.path.basename(TITAN)} @ answer window [{ans_off}, {ans_off+WIDTH})  (read-only, window-locked)", flush=True)
    print(f"  block: {a.get('job_id')}", flush=True)
    print(f"  emitted: {out['raw']}  ->  solved={out['solved']} nonce={out['nonce']}", flush=True)
    print("  the gate touched ONLY the answer window; the SDC circuit was never addressed (no black-hole path).", flush=True)
    if out["solved"]:
        print(f"  >>> gate latched nonce {out['nonce']} — AUTO-SUBMITTING to the wallet (no guessing) ...", flush=True)
        print(f"  {auto_submit(a, out['nonce'])}", flush=True)
    else:
        print("  answer not latched yet — nothing to submit (the gate stayed silent, correct). done.", flush=True)


if __name__ == "__main__":
    main()
