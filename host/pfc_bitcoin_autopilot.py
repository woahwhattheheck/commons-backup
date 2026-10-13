#!/usr/bin/env python3
"""host/pfc_bitcoin_autopilot.py — the in-spec Bitcoin AUTOPILOT for the full-throttle Muhlnickel (owner 07-19).

Per FINALREADME §4: a RESIDENT I/O router is allowed — it is NOT the executor. Each cycle, on ONE stratum connection
(the pool ties the job to the subscribe session), it does ONLY I/O:
  1. subscribe + authorize + pull the live block  — network in,
  2. ONE-WAY route the target into the pfc (titan + every federated node) — the pfc can never reach back,
  3. fire ONE signal (an addressed read of the receiver) — the routing-button act,
  4. READ the FULL answer from the safezone (`full_answer`: status | en2/group | nonce), READ-ONLY,
  5. submit that answer back to the pool on the same connection, read the verdict.
It NEVER ripples/evaluates the pfc's gates (the forbidden EXECUTOR) and NEVER writes the safezone. The pfc is fabricated
(mining gates + clock + `sdc_federate` nodes + the fold + `pfc_answer_full` write-out); this is purely the runtime.

  python host/pfc_bitcoin_autopilot.py [cycles] [wait_s]   # cycles: 0 = forever (default); wait_s: signal-settle wait (default 3)
"""
import argparse, hashlib, json, math, mmap, os, socket, struct, sys, tempfile, time

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
FOLD_MAN = "C:/llm/sdc_fold/manifest.json"; FED = "C:/llm/sdc_fold/federation.json"
OUT = "C:/llm/sdc_out"; JOB = OUT + "/autopilot_job.json"
WALLET = "bc1qvhrzg0e23f3tz2jgymwwtqacn48trf5m524zlq"
POOL_HOST = os.environ.get("TITAN_POOL_HOST", "solo.ckpool.org"); POOL_PORT = int(os.environ.get("TITAN_POOL_PORT", "3333"))
DESC_TARGET = 8 + 4 + 8            # node descriptor: magic(8)+node_id(4)+addr_bits(u64) -> the 32-byte target slot
WAIT = 3.0


def make_prefix(job, en1, en2):
    cb = job["coinb1"] + en1 + en2 + job["coinb2"]
    m = hashlib.sha256(hashlib.sha256(bytes.fromhex(cb)).digest()).digest()
    for br in job["merkle_branch"]:
        m = hashlib.sha256(hashlib.sha256(m + bytes.fromhex(br)).digest()).digest()
    ph = bytes.fromhex(job["prevhash"]); prev = b"".join(ph[i:i + 4][::-1] for i in range(0, 32, 4))
    return (struct.pack("<I", int(job["version"], 16)) + prev + m
            + struct.pack("<I", int(job["ntime"], 16)) + struct.pack("<I", int(job["nbits"], 16)))


def send_block(reg, job, en1, en2sz, target):
    """THE ROUTING BUTTON (owner 07-19): (1) route the block data (header|group|target) into the input-window receiver;
    (2) WAIT so the fill completes; (3) send the FINISHED signal into the receiver (flip `pfc_on` 0->1) to alert it that
    the entire block is present and START the chain reaction; then the button dies. Reads NOTHING. The finished signal is
    not premature — the block is already fully written when it fires."""
    io = int(reg["pfc_exec_input"]["offset"]); on = int(reg["pfc_on"]["offset"])
    header = make_prefix(job, en1, "00" * en2sz)[:76]                      # 76-byte header (base group, en2=0)
    buf = header + struct.pack("<I", 0) + struct.pack("<I", 0) + target.to_bytes(32, "little")   # nonce field unused (nonce_reg)
    with open(TITAN, "r+b") as f:
        f.seek(io); f.write(buf[:116])                                     # (1) route the block data in — one-way, blind
    time.sleep(1.0)                                                        # (2) wait for the fill to complete
    with open(TITAN, "r+b") as f:
        f.seek(on); f.write(b"\x01")                                       # (3) FINISHED signal -> receiver: block filled, START


SAFEZONE = "C:/llm/sdc_out/pfc_safezone.bin"                 # the answer lands OUTSIDE the pfc; we read only this file


class AnswerReadError(OSError):
    """The external file did not provide a complete nine-byte answer record."""


def read_full_answer():
    """Read the external record only: [status:1][en2/group:4 LE][nonce:4 LE].

    Preserve every complete record's values. Status is not a readiness marker;
    this byte layout does not provide a job or session freshness identifier.
    """
    try:
        with open(SAFEZONE, "rb") as answer_file:
            record = answer_file.read(9)
    except OSError as exc:
        raise AnswerReadError("cannot read external answer: %s" % (str(exc) or type(exc).__name__)) from exc
    if len(record) < 9:
        raise AnswerReadError("incomplete external answer: expected 9 bytes, read %d" % len(record))
    return record[0], struct.unpack_from("<I", record, 1)[0], struct.unpack_from("<I", record, 5)[0]


class Conn:
    """one stratum connection for a whole cycle (subscribe/authorize/notify/submit on the SAME session)."""
    def __init__(self):
        self.s = socket.create_connection((POOL_HOST, POOL_PORT), timeout=15); self.buf = b""
    def send(self, o, timeout=15.0):
        self.s.settimeout(timeout)
        self.s.sendall((json.dumps(o) + "\n").encode())
    def lines(self, wait=2.0):
        out = []
        if b"\n" not in self.buf:
            self.s.settimeout(wait)
            try:
                chunk = self.s.recv(8192)
            except (socket.timeout, BlockingIOError):
                return out
            if not chunk:
                raise ConnectionError("pool disconnected")
            self.buf += chunk
        while b"\n" in self.buf:
            ln, self.buf = self.buf.split(b"\n", 1)
            if ln.strip():
                try: out.append(json.loads(ln))
                except Exception: pass
        return out
    def drain(self, timeout=1.0):
        """Read all currently available fragments; bound an always-busy pool."""
        deadline = time.monotonic() + timeout
        out = []
        self.s.settimeout(0.0)
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("pool notification drain did not catch up before deadline")
            while b"\n" in self.buf:
                if time.monotonic() >= deadline:
                    raise TimeoutError("pool notification drain did not catch up before deadline")
                ln, self.buf = self.buf.split(b"\n", 1)
                if ln.strip():
                    try: out.append(json.loads(ln))
                    except Exception: pass
            if time.monotonic() >= deadline:
                raise TimeoutError("pool notification drain did not catch up before deadline")
            try:
                chunk = self.s.recv(8192)
            except (socket.timeout, BlockingIOError):
                return out
            if not chunk:
                raise ConnectionError("pool disconnected")
            self.buf += chunk
    def close(self):
        try: self.s.close()
        except Exception: pass


class PoolProtocolError(ConnectionError):
    """The existing pool protocol returned an incomplete or failed reply."""


def parse_job(params):
    """Decode one notification without changing the job already routed."""
    if not isinstance(params, list) or len(params) < 9:
        raise PoolProtocolError("mining.notify failed: incomplete job parameters")
    if type(params[8]) is not bool:
        raise PoolProtocolError("mining.notify failed: clean_jobs must be a boolean")
    return dict(job_id=params[0], prevhash=params[1], coinb1=params[2], coinb2=params[3],
                merkle_branch=params[4], version=params[5], nbits=params[6],
                ntime=params[7], clean_jobs=params[8])


def receive_job(c, timeout=15.0):
    """Finish subscribe, the pool's authorize reply, and notify on one session."""
    en1 = None; en2sz = None; job = None; pool_ready = False
    deadline = time.monotonic() + timeout
    if timeout <= 0:
        raise TimeoutError("pool handshake deadline expired")
    c.send({"id": 1, "method": "mining.subscribe", "params": ["pfc-autopilot/1.0"]}, timeout=timeout)
    while en1 is None or job is None or not pool_ready:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("pool handshake incomplete: subscribe, authorize reply, and job required")
        for m in c.lines(wait=min(2.0, remaining)):
            if m.get("id") == 1:
                result = m.get("result")
                if (m.get("error") is not None or not isinstance(result, list) or len(result) < 3
                        or not isinstance(result[1], str) or type(result[2]) is not int or result[2] < 0):
                    raise PoolProtocolError("mining.subscribe failed: %s" % (m.get("error") or result))
                en1, en2sz = result[1:3]
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("pool handshake deadline expired before authorize reply")
                c.send({"id": 2, "method": "mining.authorize", "params": [WALLET, "x"]}, timeout=remaining)
            elif m.get("id") == 2:
                if m.get("result") is not True or m.get("error") is not None:
                    raise PoolProtocolError("mining.authorize failed: %s" % (m.get("error") or m.get("result")))
                pool_ready = True
            elif m.get("method") == "mining.notify":
                job = parse_job(m.get("params"))
    return en1, en2sz, job


def _invalidates_job(messages):
    """Latch every clean notification, including reuse of the routed job ID."""
    stale = False
    for message in messages:
        if not isinstance(message, dict):
            raise PoolProtocolError("pool sent a non-object message")
        if message.get("method") == "mining.notify":
            update = parse_job(message.get("params"))
            if update["clean_jobs"]:
                stale = True
    return stale


def wait_for_job(c, wait_s):
    """Observe invalidations for the entire original signal-settle interval."""
    deadline = time.monotonic() + wait_s
    stale = False
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return stale
            # Evaluate every batch even after stale=True, including validation.
            stale = _invalidates_job(c.lines(wait=min(2.0, remaining))) or stale
    except OSError:
        # A broken connection must not make the next worker cycle start early.
        # PoolProtocolError also follows this path; cycle records its own label.
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        raise


def publish_receipt(receipt):
    """Stage complete JSON beside JOB, then publish it with one replacement."""
    serialized = json.dumps(receipt)
    destination = os.path.abspath(JOB)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=os.path.dirname(destination),
                prefix="." + os.path.basename(destination) + ".", suffix=".tmp",
                delete=False) as receipt_file:
            temporary = receipt_file.name
            if receipt_file.write(serialized) != len(serialized):
                raise OSError("incomplete receipt write")
            receipt_file.flush()
        # Close the staging handle before replacement, including on Windows.
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def cycle(reg, wait_s=WAIT):
    c = Conn(); verdict = None; connection_error = None; protocol_error = None
    stale = False; submission_attempted = False; submission_error = None
    answer = None; answer_error = None
    try:
        en1, en2sz, job = receive_job(c)
        nbref = struct.unpack("<I", make_prefix(job, en1, "00" * en2sz)[72:76])[0]
        target = (nbref & 0xffffff) << (8 * ((nbref >> 24) - 3))

        send_block(reg, job, en1, en2sz, target)                   # BUTTON: one unchanged job, one signal
        try:
            stale = wait_for_job(c, wait_s)
        except PoolProtocolError as exc:
            protocol_error = str(exc) or type(exc).__name__
        except OSError as exc:
            connection_error = str(exc) or type(exc).__name__
        try:
            status, en2v, nonce = read_full_answer()                # READ ONLY the external answer bytes
            answer = {"status": status, "en2": en2v, "nonce": nonce}
        except AnswerReadError as exc:
            answer_error = str(exc) or type(exc).__name__

        if answer is not None:
            en2 = "%0*x" % (2 * en2sz, en2v & ((1 << (8 * en2sz)) - 1))
        if connection_error is None and protocol_error is None:
            try:
                # Drain after reading the answer, including for a zero settle wait.
                stale = _invalidates_job(c.drain()) or stale
            except PoolProtocolError as exc:
                protocol_error = str(exc) or type(exc).__name__
            except TimeoutError as exc:
                submission_error = str(exc) or type(exc).__name__
            except OSError as exc:
                connection_error = str(exc) or type(exc).__name__

        if (answer is not None and not stale and connection_error is None
                and protocol_error is None and submission_error is None):
            deadline = time.monotonic() + 12
            try:
                submission_attempted = True
                c.send({"id": 100, "method": "mining.submit",
                        "params": [WALLET, job["job_id"], en2, job["ntime"], "%08x" % (nonce & 0xffffffff)]}, timeout=12.0)
                while verdict is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    for message in c.lines(wait=min(2.0, remaining)):
                        # Notifications after the send cannot replace its actual verdict.
                        if isinstance(message, dict) and message.get("id") == 100:
                            verdict = message
            except OSError as exc:
                connection_error = str(exc) or type(exc).__name__
    finally:
        c.close()

    res = (verdict or {}).get("result"); err = (verdict or {}).get("error")
    zb = 256 - target.bit_length() if job else 0
    if protocol_error:
        pool = "invalid-pool-message (%s)" % protocol_error
    elif connection_error:
        pool = "connection-lost (%s)" % connection_error
    elif submission_error:
        pool = "submission-skipped (%s)" % submission_error
    elif stale:
        pool = "stale-job (pool invalidated work before submission)"
    elif answer_error is not None:
        pool = "answer-unavailable (%s)" % answer_error
    elif err is not None or res is False:
        pool = "REJECTED (%s)" % (err[1] if isinstance(err, list) and len(err) > 1 else err)
    elif res is True:
        pool = "ACCEPTED — SHARE"
    elif verdict is not None:
        pool = "invalid-reply"
    else:
        pool = "no-reply"
    submission = "submission attempted" if submission_attempted else "submission skipped"
    if answer is None:
        answer_description = "answer unavailable from external file [%s]" % answer_error
    else:
        answer_description = f"answer read from external file [status={status} en2={en2v} nonce={nonce}]"
    print(f"  [autopilot] NEW block {job['job_id']} target {zb} zbits -> stored into input window, one signal fired; "
          f"{answer_description} -> {submission}; pool: {pool}", flush=True)
    os.makedirs(OUT, exist_ok=True)
    publish_receipt({"job_id": job["job_id"], "zbits": zb, "answer": answer, "answer_error": answer_error,
                     "pool": pool, "verdict": verdict, "submission_attempted": submission_attempted})


def main(argv=None):
    parser = argparse.ArgumentParser(description="Route a pool job and return its existing worker answer.")
    parser.add_argument("cycles", nargs="?", type=int, default=0, help="cycles to run; 0 runs until interrupted")
    parser.add_argument("wait_s", nargs="?", type=float, default=WAIT, help="initial signal-settle wait in seconds")
    args = parser.parse_args(argv)
    if args.cycles < 0 or args.wait_s < 0 or not math.isfinite(args.wait_s):
        parser.error("cycles and wait_s must be nonnegative; wait_s must be finite")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass
    with open(REG) as registry_file:
        reg = json.load(registry_file)
    if "pfc_exec_input" not in reg or "pfc_on" not in reg:
        print("Muhlnickel miner not baked (pfc_exec_input/pfc_on absent) — run host/pfc_miner.py first."); return 1
    print(f"Muhlnickel Bitcoin autopilot — one stratum connection/cycle: pull a NEW block, store it into pfc_exec_input, fire ONE "
          f"signal, read the answer from the EXTERNAL file, submit. NEVER touches the miner / ripples a gate. Ctrl+C stops.\n",
          flush=True)
    n = 0
    try:
        while args.cycles == 0 or n < args.cycles:
            n += 1
            try: cycle(reg, wait_s=args.wait_s)
            except Exception as e: print(f"  [autopilot] cycle error: {e}", flush=True)
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[autopilot] stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
