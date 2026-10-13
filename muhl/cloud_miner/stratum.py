"""muhl/cloud_miner/stratum.py — live Stratum V1 session for ordinary Bitcoin block mining.

Standard library only. No mining is performed here: this module owns the network
protocol, the canonical 80-byte header construction, and the verification of a
candidate that some executor surfaced. Nonce search belongs to the executor
(see runner.py) — never to this file and never to the host laptop.

Scope and honesty rules baked into the types:
  * A share is not payment. Pool acceptance of a share is NOT a Bitcoin block.
    Only `Verification.is_block` (double-SHA256d of the canonical 80-byte header
    below the *network* nBits target) may be described as a block, and even then
    the block is only real once the network accepts it.
  * A candidate is bound to the session and job generation that produced it.
    A reconnect starts a new session; work from a retired session is dead and is
    refused at submit time rather than silently resubmitted.

  from muhl.cloud_miner.stratum import StratumClient, StratumConfig
  cfg = StratumConfig()
  with StratumClient(cfg) as c:
      job = c.wait_for_job(timeout=30.0)
      ...
"""

from __future__ import annotations

import hashlib
import itertools
import json
import socket
import struct
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

__all__ = [
    "StratumConfig",
    "StratumError",
    "StratumTimeout",
    "StratumDisconnected",
    "StratumProtocolError",
    "StratumAuthError",
    "Job",
    "Candidate",
    "Verification",
    "SubmitPolicy",
    "SubmitStatus",
    "SubmitOutcome",
    "SessionState",
    "StratumClient",
    "dsha256",
    "bits_to_target",
    "difficulty_to_target",
    "build_header",
    "merkle_root_from_branch",
    "DIFF1_TARGET",
]

# ── constants ────────────────────────────────────────────────────────────────

DEFAULT_HOST = "stratum.ckpool.org"
DEFAULT_PORT = 3333
DEFAULT_ADDRESS = "bc1qvhrzg0e23f3tz2jgymwwtqacn48trf5m524zlq"
DEFAULT_WORKER_SUFFIX = "muhl"
DEFAULT_PASSWORD = "x"
DEFAULT_USER_AGENT = "muhl-cloud-miner/1.0"

# difficulty-1 target, the pool-share reference (not the network target)
DIFF1_TARGET = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
MAX_TARGET = (1 << 256) - 1

_HEADER_LEN = 80
_HEADER76_LEN = 76


def dsha256(data: bytes) -> bytes:
    """Bitcoin's double SHA-256. Returns the 32-byte internal (little-endian) digest."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def bits_to_target(nbits: int) -> int:
    """Decode a compact nBits field into the full 256-bit target.

    Raises ValueError on the encodings Bitcoin consensus rejects, so a corrupt or
    hostile `mining.notify` cannot silently widen the target we mine against.
    """
    if not 0 <= nbits <= 0xFFFFFFFF:
        raise ValueError("nbits out of range: %r" % (nbits,))
    exponent = nbits >> 24
    mantissa = nbits & 0x007FFFFF
    if nbits & 0x00800000:
        raise ValueError("nbits sign bit set (negative target): 0x%08x" % nbits)
    if mantissa == 0:
        raise ValueError("nbits mantissa is zero: 0x%08x" % nbits)
    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        if exponent > 34:
            raise ValueError("nbits exponent overflows 256 bits: 0x%08x" % nbits)
        target = mantissa << (8 * (exponent - 3))
    if target > MAX_TARGET:
        raise ValueError("nbits target overflows 256 bits: 0x%08x" % nbits)
    return target


def difficulty_to_target(difficulty: float) -> int:
    """Pool share target for a given difficulty. Share targets are cosmetic vs revenue."""
    if difficulty <= 0:
        raise ValueError("difficulty must be positive, got %r" % (difficulty,))
    return min(MAX_TARGET, int(DIFF1_TARGET / difficulty))


def _swap32(data: bytes) -> bytes:
    """Reverse each 4-byte word in place order — the stratum prevhash convention."""
    if len(data) % 4:
        raise ValueError("length %d is not a multiple of 4" % len(data))
    return b"".join(data[i : i + 4][::-1] for i in range(0, len(data), 4))


def merkle_root_from_branch(coinbase: bytes, branch: List[str]) -> bytes:
    """Fold the coinbase transaction up through the pool's merkle branch."""
    node = dsha256(coinbase)
    for step in branch:
        sibling = bytes.fromhex(step)
        if len(sibling) != 32:
            raise ValueError("merkle branch entry is not 32 bytes: %r" % step)
        node = dsha256(node + sibling)
    return node


# ── errors ───────────────────────────────────────────────────────────────────


class StratumError(Exception):
    """Base class for every failure this module raises."""


class StratumTimeout(StratumError):
    """A bounded wait elapsed without the expected response or notification."""


class StratumDisconnected(StratumError):
    """The TCP session ended; every job and candidate from it is now dead."""


class StratumProtocolError(StratumError):
    """The peer sent something that is not usable Stratum V1."""


class StratumAuthError(StratumError):
    """mining.authorize was refused. The client never reports connected."""


# ── typed data ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StratumConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    address: str = DEFAULT_ADDRESS
    worker_suffix: Optional[str] = DEFAULT_WORKER_SUFFIX
    password: str = DEFAULT_PASSWORD
    user_agent: str = DEFAULT_USER_AGENT
    connect_timeout: float = 15.0
    request_timeout: float = 20.0
    socket_timeout: float = 90.0

    @property
    def worker_name(self) -> str:
        """`address.worker` — the pool credits the coinbase to the address part."""
        if self.worker_suffix:
            return "%s.%s" % (self.address, self.worker_suffix)
        return self.address


@dataclass(frozen=True)
class Job:
    """One `mining.notify`, pinned to the session and generation that carried it."""

    job_id: str
    prevhash: str
    coinb1: str
    coinb2: str
    merkle_branch: Tuple[str, ...]
    version: str
    nbits: str
    ntime: str
    clean_jobs: bool
    session_id: str
    generation: int
    extranonce1: str
    extranonce2_size: int
    received_at: float

    @property
    def network_target(self) -> int:
        return bits_to_target(int(self.nbits, 16))

    @property
    def nbits_int(self) -> int:
        return int(self.nbits, 16)

    def coinbase(self, extranonce2: str) -> bytes:
        self.check_extranonce2(extranonce2)
        return bytes.fromhex(self.coinb1 + self.extranonce1 + extranonce2 + self.coinb2)

    def check_extranonce2(self, extranonce2: str) -> None:
        want = self.extranonce2_size * 2
        if len(extranonce2) != want:
            raise ValueError(
                "extranonce2 must be %d hex chars for extranonce2_size=%d, got %d"
                % (want, self.extranonce2_size, len(extranonce2))
            )
        int(extranonce2, 16)  # raises ValueError if not hex

    def header76(self, extranonce2: str) -> bytes:
        """The 76-byte prefix (version..nbits). The executor appends its own nonce."""
        return build_header(self, extranonce2, self.ntime, nonce=0)[:_HEADER76_LEN]


@dataclass(frozen=True)
class Candidate:
    """A nonce an executor surfaced. Unverified until `StratumClient.verify` runs."""

    session_id: str
    job_id: str
    generation: int
    extranonce2: str
    ntime: str
    nonce: int
    source: str = "executor"
    receipt: Optional[str] = None

    @property
    def key(self) -> Tuple[str, str, str, str, int]:
        """Identity for duplicate-submission protection."""
        return (self.session_id, self.job_id, self.extranonce2, self.ntime, self.nonce)

    @property
    def nonce_hex(self) -> str:
        return "%08x" % (self.nonce & 0xFFFFFFFF)


@dataclass(frozen=True)
class Verification:
    """The one result check performed on a surfaced candidate. Not a search."""

    valid_identity: bool
    header: Optional[bytes]
    hash_le: Optional[bytes]
    hash_int: Optional[int]
    network_target: Optional[int]
    share_target: Optional[int]
    meets_network_target: bool
    meets_share_target: bool
    detail: str

    @property
    def is_block(self) -> bool:
        """True only for a header below the *network* target. Still not revenue
        until the network itself accepts the block."""
        return self.valid_identity and self.meets_network_target

    @property
    def block_hash_hex(self) -> Optional[str]:
        return self.hash_le[::-1].hex() if self.hash_le else None


class SubmitPolicy(Enum):
    """Which verified candidates are allowed onto the wire."""

    NETWORK_ONLY = "network_only"  # default: only true block candidates
    SHARE_OR_BETTER = "share_or_better"


class SubmitStatus(Enum):
    ACCEPTED = "accepted"          # pool said true. A share, unless is_block.
    REJECTED = "rejected"          # pool said false / returned an error
    STALE_SESSION = "stale_session"
    STALE_JOB = "stale_job"
    DUPLICATE = "duplicate"
    BELOW_POLICY = "below_policy"  # verified, but policy forbids sending it
    INVALID = "invalid"            # failed verification; never sent
    NOT_SENT = "not_sent"
    ERROR = "error"


@dataclass(frozen=True)
class SubmitOutcome:
    status: SubmitStatus
    candidate: Candidate
    verification: Optional[Verification]
    pool_result: Any = None
    pool_error: Any = None
    detail: str = ""
    submitted_at: Optional[float] = None

    @property
    def is_accepted_share(self) -> bool:
        """Pool accepted it. This is a share, not payment and not a block."""
        return self.status is SubmitStatus.ACCEPTED

    @property
    def is_accepted_block_candidate(self) -> bool:
        """Accepted AND below the network target. Still awaits network confirmation."""
        return self.status is SubmitStatus.ACCEPTED and bool(
            self.verification and self.verification.is_block
        )


@dataclass
class SessionState:
    """Everything a single TCP session owns. A reconnect makes a brand new one."""

    session_id: str
    started_at: float
    extranonce1: str = ""
    extranonce2_size: int = 0
    subscriptions: Tuple[Any, ...] = ()
    authorized: bool = False
    generation: int = 0
    difficulty: float = 1.0
    current_job: Optional[Job] = None
    live_job_ids: set = field(default_factory=set)
    retired: bool = False


def build_header(job: Job, extranonce2: str, ntime: str, nonce: int) -> bytes:
    """Canonical 80-byte Bitcoin block header for this job and candidate.

    version(4 LE) | prevhash(32, per-word byte-swapped) | merkle_root(32)
                  | ntime(4 LE) | nbits(4 LE) | nonce(4 LE)
    """
    prevhash = bytes.fromhex(job.prevhash)
    if len(prevhash) != 32:
        raise ValueError("prevhash is not 32 bytes: %r" % job.prevhash)
    merkle_root = merkle_root_from_branch(job.coinbase(extranonce2), list(job.merkle_branch))
    header = (
        struct.pack("<I", int(job.version, 16))
        + _swap32(prevhash)
        + merkle_root
        + struct.pack("<I", int(ntime, 16))
        + struct.pack("<I", int(job.nbits, 16))
        + struct.pack("<I", nonce & 0xFFFFFFFF)
    )
    if len(header) != _HEADER_LEN:
        raise ValueError("built header is %d bytes, expected 80" % len(header))
    return header


class _Pending:
    """One outstanding JSON-RPC request, resolved by the reader thread."""

    __slots__ = ("event", "result", "error", "done")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None
        self.error: Any = None
        self.done = False


class StratumClient:
    """A live Stratum V1 session.

    Threading: one background reader thread owns the socket read side and
    resolves correlated request ids and notifications. Callers block on
    `threading.Event`s with explicit deadlines — never on sleeps or bare recv.
    """

    def __init__(
        self,
        config: Optional[StratumConfig] = None,
        submit_policy: SubmitPolicy = SubmitPolicy.NETWORK_ONLY,
        on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        self.config = config or StratumConfig()
        self.submit_policy = submit_policy
        self._on_event = on_event
        self._sock: Optional[socket.socket] = None
        self._reader: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._pending: Dict[int, _Pending] = {}
        self._ids = itertools.count(1)
        self._session: Optional[SessionState] = None
        self._session_counter = itertools.count(1)
        self._job_event = threading.Event()
        self._closed = threading.Event()
        self._submitted: set = set()
        self._fatal: Optional[BaseException] = None
        self._preauth_notify: Optional[List[Any]] = None

    # ── lifecycle ────────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        """True only after subscribe AND authorize both succeeded."""
        s = self._session
        return bool(
            s
            and not s.retired
            and s.authorized
            and s.extranonce1
            and self._sock is not None
            and not self._closed.is_set()
        )

    @property
    def session(self) -> Optional[SessionState]:
        return self._session

    @property
    def current_job(self) -> Optional[Job]:
        s = self._session
        return s.current_job if s and not s.retired else None

    def __enter__(self) -> "StratumClient":
        self.connect()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def connect(self) -> SessionState:
        """Open a new session: TCP, mining.subscribe, mining.authorize.

        Any previously issued job or candidate belongs to the retired session and
        is refused by `submit` afterwards.
        """
        self.close()
        self._closed.clear()
        self._fatal = None
        self._job_event.clear()
        session_id = uuid.uuid4().hex
        self._preauth_notify = None
        session = SessionState(session_id=session_id, started_at=time.time())
        try:
            sock = socket.create_connection(
                (self.config.host, self.config.port), timeout=self.config.connect_timeout
            )
        except OSError as exc:
            raise StratumDisconnected(
                "connect to %s:%d failed: %s" % (self.config.host, self.config.port, exc)
            ) from exc
        sock.settimeout(self.config.socket_timeout)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        with self._lock:
            self._sock = sock
            self._session = session
            self._pending.clear()
        self._reader = threading.Thread(
            target=self._read_loop, name="stratum-reader-%s" % session_id, daemon=True
        )
        self._reader.start()

        sub = self._request("mining.subscribe", [self.config.user_agent])
        if not isinstance(sub, list) or len(sub) < 3:
            raise StratumProtocolError("mining.subscribe result is not [subs, en1, en2size]: %r" % (sub,))
        extranonce1 = sub[1]
        extranonce2_size = sub[2]
        if not isinstance(extranonce1, str):
            raise StratumProtocolError("extranonce1 is not a hex string: %r" % (extranonce1,))
        try:
            bytes.fromhex(extranonce1)
        except ValueError as exc:
            raise StratumProtocolError("extranonce1 is not hex: %r" % (extranonce1,)) from exc
        if not isinstance(extranonce2_size, int) or not 1 <= extranonce2_size <= 32:
            raise StratumProtocolError("extranonce2_size out of range: %r" % (extranonce2_size,))
        with self._lock:
            session.extranonce1 = extranonce1
            session.extranonce2_size = extranonce2_size
            session.subscriptions = tuple(sub[0]) if isinstance(sub[0], list) else ()

        auth = self._request(
            "mining.authorize", [self.config.worker_name, self.config.password]
        )
        if auth is not True:
            self.close()
            raise StratumAuthError(
                "pool refused mining.authorize for worker %r: %r"
                % (self.config.worker_name, auth)
            )
        with self._lock:
            session.authorized = True
            early_notify, self._preauth_notify = self._preauth_notify, None
            if early_notify is not None:
                self._handle_notify(early_notify)
        self._emit(
            "session_open",
            {
                "session_id": session.session_id,
                "worker": self.config.worker_name,
                "extranonce1": extranonce1,
                "extranonce2_size": extranonce2_size,
            },
        )
        return session

    def close(self) -> None:
        """Retire the session. Its jobs and candidates become permanently unusable."""
        with self._lock:
            session = self._session
            sock = self._sock
            self._sock = None
            if session is not None:
                session.retired = True
                session.authorized = False
                session.current_job = None
                session.live_job_ids.clear()
            pending = list(self._pending.values())
            self._pending.clear()
        self._closed.set()
        self._job_event.set()
        for slot in pending:
            if not slot.done:
                slot.error = {"code": -1, "message": "session closed"}
                slot.done = True
                slot.event.set()
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
            if session is not None:
                self._emit("session_close", {"session_id": session.session_id})
        reader, self._reader = self._reader, None
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=2.0)

    # ── wire ─────────────────────────────────────────────────────────────

    def _emit(self, kind: str, data: Dict[str, Any]) -> None:
        if self._on_event is not None:
            try:
                self._on_event(kind, data)
            except Exception:  # a broken observer must not kill the session
                pass

    def _send(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            sock = self._sock
        if sock is None:
            raise StratumDisconnected("no live socket")
        line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            sock.sendall(line)
        except OSError as exc:
            raise StratumDisconnected("send failed: %s" % exc) from exc

    def _request(self, method: str, params: List[Any], timeout: Optional[float] = None) -> Any:
        """Correlated JSON-RPC call. Blocks on this id's event only."""
        timeout = self.config.request_timeout if timeout is None else timeout
        req_id = next(self._ids)
        slot = _Pending()
        with self._lock:
            if self._closed.is_set():
                raise StratumDisconnected("session is closed")
            self._pending[req_id] = slot
        try:
            self._send({"id": req_id, "method": method, "params": params})
            if not slot.event.wait(timeout):
                raise StratumTimeout("no response to %s (id=%d) within %.1fs" % (method, req_id, timeout))
        finally:
            with self._lock:
                self._pending.pop(req_id, None)
        if self._fatal is not None and not slot.done:
            raise StratumDisconnected("session died awaiting %s: %s" % (method, self._fatal))
        if slot.error:
            raise StratumProtocolError("%s failed: %r" % (method, slot.error))
        return slot.result

    def _read_loop(self) -> None:
        buf = b""
        try:
            while not self._closed.is_set():
                with self._lock:
                    sock = self._sock
                if sock is None:
                    break
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    self._fatal = StratumTimeout(
                        "no data for %.0fs" % self.config.socket_timeout
                    )
                    break
                except OSError as exc:
                    self._fatal = StratumDisconnected("recv failed: %s" % exc)
                    break
                if not chunk:
                    self._fatal = StratumDisconnected("pool closed the connection")
                    break
                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        msg = json.loads(raw.decode("utf-8", errors="replace"))
                    except ValueError:
                        self._emit("bad_line", {"raw": raw[:256].decode("latin-1")})
                        continue
                    if isinstance(msg, dict):
                        self._dispatch(msg)
        finally:
            if self._fatal is not None:
                self._emit("session_error", {"error": str(self._fatal)})
                self.close()

    def _dispatch(self, msg: Dict[str, Any]) -> None:
        msg_id = msg.get("id")
        if msg_id is not None and ("result" in msg or "error" in msg):
            with self._lock:
                slot = self._pending.get(msg_id)
            if slot is not None and not slot.done:
                slot.result = msg.get("result")
                slot.error = msg.get("error")
                slot.done = True
                slot.event.set()
            return
        method = msg.get("method")
        params = msg.get("params") or []
        if method == "mining.notify":
            self._handle_notify(params)
        elif method == "mining.set_difficulty":
            if params and isinstance(params[0], (int, float)) and params[0] > 0:
                with self._lock:
                    if self._session:
                        self._session.difficulty = float(params[0])
                self._emit("set_difficulty", {"difficulty": float(params[0])})
        elif method == "mining.set_extranonce":
            # extranonce1 changed: all outstanding work is invalid, bump generation.
            if len(params) >= 2 and isinstance(params[0], str) and isinstance(params[1], int):
                with self._lock:
                    if self._session:
                        self._session.extranonce1 = params[0]
                        self._session.extranonce2_size = params[1]
                        self._session.generation += 1
                        self._session.live_job_ids.clear()
                        self._session.current_job = None
                self._emit("set_extranonce", {"extranonce1": params[0], "extranonce2_size": params[1]})
        elif method == "client.reconnect":
            self._fatal = StratumDisconnected("pool requested client.reconnect")
            self.close()

    def _handle_notify(self, params: List[Any]) -> None:
        if len(params) < 9:
            self._emit("bad_notify", {"params_len": len(params)})
            return
        with self._lock:
            session = self._session
            if session is None or session.retired:
                return
            if not session.authorized:
                # Pools may notify between subscribe and authorize responses.
                # Retain the newest job until subscription/auth are complete.
                self._preauth_notify = list(params)
                return
            clean = bool(params[8])
            if clean:
                session.generation += 1
                session.live_job_ids.clear()
            branch = params[4] if isinstance(params[4], list) else []
            try:
                job = Job(
                    job_id=str(params[0]),
                    prevhash=str(params[1]),
                    coinb1=str(params[2]),
                    coinb2=str(params[3]),
                    merkle_branch=tuple(str(b) for b in branch),
                    version=str(params[5]),
                    nbits=str(params[6]),
                    ntime=str(params[7]),
                    clean_jobs=clean,
                    session_id=session.session_id,
                    generation=session.generation,
                    extranonce1=session.extranonce1,
                    extranonce2_size=session.extranonce2_size,
                    received_at=time.time(),
                )
                target = job.network_target  # validates nBits now, not at submit time
            except (ValueError, TypeError) as exc:
                self._emit("bad_notify", {"error": str(exc)})
                return
            session.current_job = job
            session.live_job_ids.add(job.job_id)
        self._job_event.set()
        self._emit(
            "job",
            {
                "job_id": job.job_id,
                "clean_jobs": clean,
                "generation": job.generation,
                "network_target_zero_bits": 256 - target.bit_length(),
            },
        )

    # ── job access ───────────────────────────────────────────────────────

    def wait_for_job(self, timeout: float = 30.0, after: Optional[Job] = None) -> Job:
        """Block until a job is available (optionally, one newer than `after`)."""
        deadline = time.monotonic() + timeout
        while True:
            job = self.current_job
            if job is not None and (after is None or job.job_id != after.job_id):
                return job
            if self._closed.is_set() or not self.connected:
                raise StratumDisconnected("session ended while waiting for a job")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise StratumTimeout("no job within %.1fs" % timeout)
            self._job_event.clear()
            self._job_event.wait(min(remaining, 1.0))

    def is_job_live(self, session_id: str, job_id: str, generation: int) -> bool:
        """A job is live only in its own session and its own generation."""
        with self._lock:
            s = self._session
            if s is None or s.retired or not s.authorized:
                return False
            return (
                s.session_id == session_id
                and s.generation == generation
                and job_id in s.live_job_ids
            )

    def share_target(self) -> int:
        s = self._session
        return difficulty_to_target(s.difficulty if s else 1.0)

    # ── verification ─────────────────────────────────────────────────────

    def verify(self, job: Job, candidate: Candidate) -> Verification:
        """One result check on a surfaced candidate. Never a search.

        Checks identity (candidate belongs to this live job/session/generation),
        rebuilds the canonical 80-byte header, and compares its double-SHA256d
        against the network target and the current share target.
        """
        if (candidate.session_id, candidate.job_id, candidate.generation) != (
            job.session_id,
            job.job_id,
            job.generation,
        ):
            return Verification(
                False, None, None, None, None, None, False, False,
                "candidate identity %s/%s/gen%d does not match job %s/%s/gen%d"
                % (
                    candidate.session_id, candidate.job_id, candidate.generation,
                    job.session_id, job.job_id, job.generation,
                ),
            )
        if not self.is_job_live(job.session_id, job.job_id, job.generation):
            return Verification(
                False, None, None, None, None, None, False, False,
                "job %s is no longer live in the current session" % job.job_id,
            )
        try:
            job.check_extranonce2(candidate.extranonce2)
            header = build_header(job, candidate.extranonce2, candidate.ntime, candidate.nonce)
        except (ValueError, TypeError) as exc:
            return Verification(
                False, None, None, None, None, None, False, False,
                "header construction failed: %s" % exc,
            )
        digest = dsha256(header)
        value = int.from_bytes(digest, "little")
        network_target = job.network_target
        share_target = self.share_target()
        meets_network = value <= network_target
        meets_share = value <= share_target
        return Verification(
            valid_identity=True,
            header=header,
            hash_le=digest,
            hash_int=value,
            network_target=network_target,
            share_target=share_target,
            meets_network_target=meets_network,
            meets_share_target=meets_share,
            detail=(
                "block candidate (below network target)"
                if meets_network
                else ("share (below share target)" if meets_share else "above share target")
            ),
        )

    # ── submit ───────────────────────────────────────────────────────────

    def submit(self, job: Job, candidate: Candidate) -> SubmitOutcome:
        """Verify, then submit on the SAME live session that issued the job.

        A pool `true` here means the pool accepted a share. It is not payment,
        and it is only a block when `verification.is_block` is also true.
        """
        if not self.connected:
            return SubmitOutcome(
                SubmitStatus.STALE_SESSION, candidate, None,
                detail="no authorized live session; a retired session cannot submit",
            )
        s = self._session
        assert s is not None
        if candidate.session_id != s.session_id:
            return SubmitOutcome(
                SubmitStatus.STALE_SESSION, candidate, None,
                detail="candidate belongs to retired session %s (live: %s)"
                % (candidate.session_id, s.session_id),
            )
        if not self.is_job_live(job.session_id, job.job_id, job.generation):
            return SubmitOutcome(
                SubmitStatus.STALE_JOB, candidate, None,
                detail="job %s was cleared (clean_jobs or new session)" % job.job_id,
            )
        if candidate.key in self._submitted:
            return SubmitOutcome(
                SubmitStatus.DUPLICATE, candidate, None,
                detail="this exact candidate was already submitted",
            )

        verification = self.verify(job, candidate)
        if not verification.valid_identity:
            return SubmitOutcome(
                SubmitStatus.INVALID, candidate, verification, detail=verification.detail
            )
        if self.submit_policy is SubmitPolicy.NETWORK_ONLY and not verification.meets_network_target:
            return SubmitOutcome(
                SubmitStatus.BELOW_POLICY, candidate, verification,
                detail="policy NETWORK_ONLY: %s" % verification.detail,
            )
        if self.submit_policy is SubmitPolicy.SHARE_OR_BETTER and not verification.meets_share_target:
            return SubmitOutcome(
                SubmitStatus.BELOW_POLICY, candidate, verification,
                detail="policy SHARE_OR_BETTER: %s" % verification.detail,
            )

        params = [
            self.config.worker_name,
            candidate.job_id,
            candidate.extranonce2,
            candidate.ntime,
            candidate.nonce_hex,
        ]
        sent_at = time.time()
        try:
            result = self._request("mining.submit", params)
        except StratumProtocolError as exc:
            self._submitted.add(candidate.key)
            return SubmitOutcome(
                SubmitStatus.REJECTED, candidate, verification,
                pool_error=str(exc), detail=str(exc), submitted_at=sent_at,
            )
        except StratumError as exc:
            return SubmitOutcome(
                SubmitStatus.ERROR, candidate, verification,
                pool_error=str(exc), detail=str(exc), submitted_at=sent_at,
            )
        status = SubmitStatus.ACCEPTED if result is True else SubmitStatus.REJECTED
        self._submitted.add(candidate.key)
        outcome = SubmitOutcome(
            status, candidate, verification, pool_result=result,
            detail=(
                "pool accepted a share%s"
                % (" for a BLOCK-target header" if verification.is_block else "")
                if status is SubmitStatus.ACCEPTED
                else "pool rejected the submission"
            ),
            submitted_at=sent_at,
        )
        self._emit(
            "submit",
            {
                "job_id": candidate.job_id,
                "nonce": candidate.nonce_hex,
                "status": status.value,
                "is_block_candidate": verification.is_block,
            },
        )
        return outcome


# ── author validation: protocol and byte-order invariants, no mining ─────────


def _selftest() -> int:
    """Narrow protocol/byte-order checks. No network, no nonce search, no device."""
    failures: List[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if cond:
            print("  ok   %s" % name)
        else:
            failures.append(name)
            print("  FAIL %s %s" % (name, detail))

    # 1. dsha256 / header byte order against mainnet block 125552 (public constant).
    header = bytes.fromhex(
        "01000000"
        "81cd02ab7e569e8bcd9317e2fe99f2de44d49ab2b8851ba4a308000000000000"
        "e320b6c2fffc8d750423db8b1eb942ae710e951ed797f7affc8892b0f1fc122b"
        "c7f5d74d" "f2b9441a" "42a14695"
    )
    got = dsha256(header)[::-1].hex()
    check(
        "dsha256 header byte order",
        got == "00000000000000001e8d6829a8a21adc5d38d0a473b144b6765798e61f98bd1d",
        got,
    )

    # 2. nBits decode, and that the block's own hash is below its own target.
    target = bits_to_target(0x1A44B9F2)
    check("bits_to_target 0x1a44b9f2", target == 0x44B9F2 << (8 * (0x1A - 3)), hex(target))
    check("block 125552 meets its own target", int.from_bytes(dsha256(header), "little") <= target)

    # 3. Consensus-invalid nBits encodings must raise, not silently widen the target.
    for bad, why in ((0x00000000, "zero mantissa"), (0x01800000, "sign bit"), (0xFF123456, "overflow")):
        try:
            bits_to_target(bad)
            check("bits_to_target rejects %s" % why, False, "accepted 0x%08x" % bad)
        except ValueError:
            check("bits_to_target rejects %s" % why, True)

    # 4. prevhash per-word swap is its own inverse and is not a plain reversal.
    raw = bytes(range(32))
    check("_swap32 involution", _swap32(_swap32(raw)) == raw)
    check("_swap32 != full reverse", _swap32(raw) != raw[::-1])

    # 5. Merkle fold with an empty branch is the bare coinbase double-SHA.
    cb = b"\xab" * 64
    check("merkle_root empty branch", merkle_root_from_branch(cb, []) == dsha256(cb))
    sib = "11" * 32
    check(
        "merkle_root one branch",
        merkle_root_from_branch(cb, [sib]) == dsha256(dsha256(cb) + bytes.fromhex(sib)),
    )

    # 6. Header assembly: 80 bytes, correct field placement, nonce little-endian.
    job = Job(
        job_id="j1", prevhash="00" * 32, coinb1="01", coinb2="02",
        merkle_branch=(), version="20000000", nbits="1a44b9f2", ntime="4d74f5c7",
        clean_jobs=True, session_id="s1", generation=0,
        extranonce1="deadbeef", extranonce2_size=4, received_at=0.0,
    )
    h = build_header(job, "00000001", job.ntime, 0x42A14695)
    check("header is 80 bytes", len(h) == 80, str(len(h)))
    check("version LE at [0:4]", h[0:4] == struct.pack("<I", 0x20000000), h[0:4].hex())
    check("ntime LE at [68:72]", h[68:72] == struct.pack("<I", 0x4D74F5C7), h[68:72].hex())
    check("nbits LE at [72:76]", h[72:76] == struct.pack("<I", 0x1A44B9F2), h[72:76].hex())
    check("nonce LE at [76:80]", h[76:80] == struct.pack("<I", 0x42A14695), h[76:80].hex())
    check("header76 excludes the nonce", job.header76("00000001") == h[:76])
    check(
        "coinbase splices en1+en2 between coinb1 and coinb2",
        job.coinbase("00000001") == bytes.fromhex("01" + "deadbeef" + "00000001" + "02"),
    )

    # 7. extranonce2 width is enforced (a short en2 changes the coinbase silently).
    for bad in ("0001", "000000010", "zzzzzzzz"):
        try:
            job.check_extranonce2(bad)
            check("extranonce2 width rejects %r" % bad, False)
        except ValueError:
            check("extranonce2 width rejects %r" % bad, True)

    # 8. Worker name carries the .muhl suffix; the address stays the payout key.
    cfg = StratumConfig()
    check(
        "worker name",
        cfg.worker_name == DEFAULT_ADDRESS + ".muhl",
        cfg.worker_name,
    )
    check("suffix optional", StratumConfig(worker_suffix=None).worker_name == DEFAULT_ADDRESS)

    # 9. Difficulty-1 share target is far wider than a real network target.
    check("diff1 > network target", difficulty_to_target(1.0) > target)
    check("difficulty scales the share target", difficulty_to_target(2.0) < difficulty_to_target(1.0))

    # 10. Candidate identity is what duplicate protection keys on.
    c1 = Candidate("s1", "j1", 0, "00000001", "4d74f5c7", 1)
    c2 = Candidate("s1", "j1", 0, "00000001", "4d74f5c7", 2)
    check("candidate key distinguishes nonce", c1.key != c2.key)
    check("nonce_hex is 8 chars", Candidate("s", "j", 0, "00", "00", 0xFF).nonce_hex == "000000ff")

    print("\n%s — %d failure(s)" % ("FAIL" if failures else "PASS", len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())