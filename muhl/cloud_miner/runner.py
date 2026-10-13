"""muhl/cloud_miner/runner.py — adapter between a live Stratum session and a
Muhlnickel-shaped cloud substrate.

This module is an ADAPTER. It contains no gate evaluator, no SHA implementation,
no CPU/GPU fallback and no nonce search. All computation belongs to a substrate
driver supplied through `SubstrateIO`. Until a real driver is configured, every
entry point reports `executor_unavailable` and no progress is invented.

What this file owns:
  * the `muhl-cloud-miner-layout/v1` manifest binding (ram map + state bank),
  * bit-byte encoding of header / nonce / target / nonce_end for that layout,
  * the enable/disable and sticky-ready protocol,
  * non-overlapping per-job nonce range allocation and checkpointing,
  * one hash-check of a surfaced candidate, on the live session only.

Honesty rules enforced by the types:
  * A candidate exists only when `result_ready == 1 AND win == 1`. Nonce 0 is a
    legitimate winner, so a zero `winner_nonce` is never treated as "no result".
  * A frontier is only recorded from a coherent snapshot the driver declares
    coherent with `commit_ready == 1`. Elapsed time and raw nonce reads are
    never used to infer covered work.
  * A share is not payment. Only a header below the network target is a block
    candidate, and it is only a block once the network accepts it.
  * A retired session can never submit. Work is cancelled, not resubmitted.

  from muhl.cloud_miner.runner import CloudMiner, MuhlnickelExecutor
  miner = CloudMiner(client, executor=MuhlnickelExecutor(driver))
  report = miner.run_once()
"""

from __future__ import annotations

import json
import os
import struct
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from .stratum import (
    Candidate,
    Job,
    StratumClient,
    StratumDisconnected,
    StratumError,
    StratumTimeout,
    SubmitOutcome,
    SubmitStatus,
    Verification,
)

__all__ = [
    "LAYOUT_SCHEMA",
    "LayoutError",
    "Layout",
    "CoherentSnapshot",
    "SubstrateIO",
    "WorkRequest",
    "WorkState",
    "WorkProgress",
    "WorkHandle",
    "Executor",
    "MuhlnickelExecutor",
    "NonceRange",
    "CheckpointStore",
    "JsonFileCheckpoint",
    "RunnerStatus",
    "RunnerReport",
    "CloudMiner",
    "pack_header_bitbytes",
    "pack_uint32_bitbytes",
    "pack_target_bitbytes",
    "unpack_uint32_bitbytes",
]

LAYOUT_SCHEMA = "muhl-cloud-miner-layout/v1"

# ram field names and their exact widths in bit-bytes (one byte per bit)
F_HEADER = "header"                   # 608 — header76, big-endian words, LSB bits
F_NONCE = "nonce"                     # 32  — numeric uint32, LSB bits
F_TARGET = "target"                   # 256 — numeric, little-endian, LSB bits
F_NONCE_END = "nonce_end"             # 32  — INCLUSIVE end of the range
F_WINNER_NONCE = "winner_nonce"       # 32  — numeric uint32, LSB bits
F_WIN = "win"                         # 1
F_EXHAUSTED = "exhausted"             # 1
F_ENABLED = "enabled"                 # 1
F_RECEIVER = "receiver"               # 1
F_COMMIT_READY = "commit_ready"       # 1
F_RESULT_READY = "result_ready"       # 1 — sticky
F_EXHAUSTED_READY = "exhausted_ready" # 1 — sticky

FIELD_WIDTHS: Dict[str, int] = {
    F_HEADER: 608, F_NONCE: 32, F_TARGET: 256, F_NONCE_END: 32,
    F_WINNER_NONCE: 32, F_WIN: 1, F_EXHAUSTED: 1, F_ENABLED: 1,
    F_RECEIVER: 1, F_COMMIT_READY: 1, F_RESULT_READY: 1, F_EXHAUSTED_READY: 1,
}

# fields that must be re-read together to decide readiness
POLL_FIELDS: Tuple[str, ...] = (
    F_COMMIT_READY, F_RESULT_READY, F_WIN, F_WINNER_NONCE,
    F_EXHAUSTED_READY, F_EXHAUSTED, F_NONCE, F_ENABLED,
)

# sticky contacts cleared on every fresh job load
STICKY_FIELDS: Tuple[str, ...] = (F_RESULT_READY, F_EXHAUSTED_READY, F_WIN, F_EXHAUSTED)

STATE_SPANS: Tuple[str, ...] = ("master_q", "master_not_q", "slave_q", "slave_not_q")

UINT32_MAX = 0xFFFFFFFF


class LayoutError(Exception):
    """The manifest does not describe a usable muhl-cloud-miner-layout/v1 device."""


# ── bit-byte encoding for this layout ────────────────────────────────────────


def pack_uint32_bitbytes(value: int) -> bytes:
    """Numeric uint32 as 32 bit-bytes, LSB first. The circuit does any SHA word
    byteswap internally, so this is a plain numeric encoding."""
    if not 0 <= value <= UINT32_MAX:
        raise ValueError("uint32 out of range: %r" % (value,))
    return bytes((value >> j) & 1 for j in range(32))


def unpack_uint32_bitbytes(data: bytes) -> int:
    """Inverse of `pack_uint32_bitbytes`. Any non-zero bit-byte reads as 1."""
    if len(data) != 32:
        raise ValueError("expected 32 bit-bytes, got %d" % len(data))
    value = 0
    for j, b in enumerate(data):
        if b & 1:
            value |= 1 << j
    return value


def pack_target_bitbytes(target: int) -> bytes:
    """256-bit target, numeric little-endian, LSB bits within each byte."""
    if not 0 <= target < (1 << 256):
        raise ValueError("target out of 256-bit range")
    raw = target.to_bytes(32, "little")
    out = bytearray(256)
    for k, byte in enumerate(raw):
        for j in range(8):
            out[k * 8 + j] = (byte >> j) & 1
    return bytes(out)


def pack_header_bitbytes(header76: bytes) -> bytes:
    """76-byte header prefix -> 608 bit-bytes.

    Packing matches fabricate.header_bits: parse each 4-byte word big-endian,
    then emit its 32 bits least-significant first. Word w occupies
    [w*32, w*32+32).
    """
    if len(header76) != 76:
        raise ValueError("header prefix must be 76 bytes, got %d" % len(header76))
    out = bytearray(608)
    for w in range(19):
        word = header76[w * 4 : (w + 1) * 4]
        value = int.from_bytes(word, "big")
        base = w * 32
        for j in range(32):
            out[base + j] = (value >> j) & 1
    return bytes(out)


def _invert_bitbytes(data: bytes) -> bytes:
    return bytes(1 - (b & 1) for b in data)


# ── layout binding ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Layout:
    """Validated `muhl-cloud-miner-layout/v1` manifest. No hardcoded addresses."""

    schema: str
    ram: Mapping[str, Mapping[str, int]]
    state_bank: Mapping[str, Mapping[str, int]]
    instance_id: str
    raw: Mapping[str, Any]

    @classmethod
    def from_manifest(cls, manifest: Mapping[str, Any]) -> "Layout":
        schema = manifest.get("schema")
        if schema != LAYOUT_SCHEMA:
            raise LayoutError("manifest schema %r is not %r" % (schema, LAYOUT_SCHEMA))
        ram = manifest.get("ram")
        if not isinstance(ram, Mapping):
            raise LayoutError("manifest has no ram map")
        for name, width in FIELD_WIDTHS.items():
            entry = ram.get(name)
            if not isinstance(entry, Mapping):
                raise LayoutError("ram map is missing field %r" % name)
            if "offset" not in entry:
                raise LayoutError("ram field %r has no offset" % name)
            bits = entry.get("width", width)
            if int(bits) != width:
                raise LayoutError(
                    "ram field %r is %s bits, layout v1 requires %d" % (name, bits, width)
                )
            if int(entry["offset"]) < 0:
                raise LayoutError("ram field %r has a negative addr" % name)
        bank = manifest.get("state_bank")
        if not isinstance(bank, Mapping):
            raise LayoutError("manifest has no state_bank")
        return cls(
            schema=schema,
            ram=dict(ram),
            state_bank=dict(bank),
            instance_id=str(manifest.get("instance_id") or manifest.get("container") or "unnamed"),
            raw=dict(manifest),
        )

    def addr(self, name: str) -> int:
        return int(self.ram[name]["offset"])

    def state_writes(self, name: str, bitbytes: bytes) -> Dict[str, bytes]:
        """Initial master/slave NAND-latch contents for a state bank.

        Restarting at an arbitrary nonce means seeding the latch itself, not just
        the input contact: master_q and slave_q take the value, and their not_q
        spans take the complement. Written only while `enabled == 0`.
        """
        entry = self.state_bank.get(name)
        if not isinstance(entry, Mapping):
            raise LayoutError("state_bank has no bank %r" % name)
        bits = int(entry.get("width", len(bitbytes)))
        if bits != len(bitbytes):
            raise LayoutError(
                "state bank %r is %d bits, got %d bit-bytes" % (name, bits, len(bitbytes))
            )
        inverted = _invert_bitbytes(bitbytes)
        writes: Dict[str, bytes] = {}
        for span in STATE_SPANS:
            if span not in entry:
                raise LayoutError("state bank %r has no %r span" % (name, span))
            writes["%s.%s" % (name, span)] = inverted if span.endswith("not_q") else bitbytes
        return writes


# ── substrate driver contract (supplied by root; never defaulted here) ───────


@dataclass(frozen=True)
class CoherentSnapshot:
    """One read of several fields.

    `coherent` MUST be set True only when the driver actually captured the fields
    as one consistent view with `commit_ready == 1`. Ordinary repeated file reads
    do not qualify; a driver that cannot guarantee this must report False, and
    this adapter will then refuse to record a frontier from it.
    """

    fields: Mapping[str, bytes]
    coherent: bool
    taken_at: float
    receipt: Optional[str] = None
    detail: str = ""

    def bit(self, name: str) -> int:
        raw = self.fields.get(name)
        if not raw:
            raise LayoutError("snapshot has no field %r" % name)
        return raw[0] & 1

    def u32(self, name: str) -> int:
        raw = self.fields.get(name)
        if raw is None:
            raise LayoutError("snapshot has no field %r" % name)
        return unpack_uint32_bitbytes(raw)


class SubstrateIO(Protocol):
    """Real ring-shaped substrate execution driver. Root/Gemini supply this.

    A conforming driver actuates the fabricated organ. It is not a Python
    evaluator, and this module never provides a default implementation.
    """

    def manifest(self) -> Mapping[str, Any]:
        """The `muhl-cloud-miner-layout/v1` manifest for this container."""

    def write_fields(self, values: Mapping[str, bytes]) -> None:
        """Write named ram fields / state spans. Caller guarantees enabled == 0."""

    def read_coherent(self, fields: Sequence[str]) -> CoherentSnapshot:
        """Atomic, commit_ready-gated snapshot of the named fields."""

    def set_enabled(self, enabled: bool) -> None:
        """Enable the rings or disable and await substrate quiescence.

        Returning from set_enabled(False) must establish that all prior
        propagation has settled; otherwise loading new state is not safe.
        """

    def close(self) -> None:
        """Release the container. Idempotent."""


# ── work contract ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NonceRange:
    start: int
    end_exclusive: int

    def __post_init__(self) -> None:
        if not 0 <= self.start < self.end_exclusive <= UINT32_MAX + 1:
            raise ValueError("bad nonce range [%d, %d)" % (self.start, self.end_exclusive))

    @property
    def end_inclusive(self) -> int:
        """The device field is INCLUSIVE; our range arithmetic is exclusive."""
        return self.end_exclusive - 1

    @property
    def size(self) -> int:
        return self.end_exclusive - self.start

    def overlaps(self, other: "NonceRange") -> bool:
        return self.start < other.end_exclusive and other.start < self.end_exclusive


@dataclass(frozen=True)
class WorkRequest:
    """Exactly what one device load covers. Identity is adapter-bound."""

    instance_id: str
    session_id: str
    job_id: str
    generation: int
    extranonce2: str
    ntime: str
    header76: bytes
    network_target: int
    nonce_range: NonceRange
    issued_at: float

    @property
    def identity(self) -> Tuple[str, str, int, str, int, int]:
        return (
            self.session_id, self.job_id, self.generation, self.extranonce2,
            self.nonce_range.start, self.nonce_range.end_exclusive,
        )


class WorkState(Enum):
    RUNNING = "running"                  # enabled, no ready contact yet
    CANDIDATE_READY = "candidate_ready"  # result_ready == 1 and win == 1
    EXHAUSTED = "exhausted"              # exhausted_ready == 1, inclusive end done
    CANCELLED = "cancelled"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"          # no real engine configured


@dataclass(frozen=True)
class WorkProgress:
    """Progress that is actually evidenced, or nothing at all."""

    state: WorkState
    winner_nonce: Optional[int] = None
    frontier_exclusive: Optional[int] = None   # only from a coherent snapshot
    coherent: bool = False
    receipt: Optional[str] = None
    detail: str = ""


@dataclass
class WorkHandle:
    request: WorkRequest
    started_at: float
    handle_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    last: Optional[WorkProgress] = None
    cancelled: bool = False


class Executor(Protocol):
    """What `CloudMiner` drives. Implemented here only by `MuhlnickelExecutor`."""

    def available(self) -> Tuple[bool, str]: ...
    def start(self, request: WorkRequest) -> WorkHandle: ...
    def poll(self, handle: WorkHandle) -> WorkProgress: ...
    def cancel(self, handle: WorkHandle) -> WorkProgress: ...
    def instance_id(self) -> str: ...


class MuhlnickelExecutor:
    """Adapter from `WorkRequest` to a `muhl-cloud-miner-layout/v1` container.

    Holds no compute. Every operation is a field write, an enable toggle or a
    coherent read on the injected driver.
    """

    def __init__(self, driver: Optional[SubstrateIO] = None) -> None:
        self._driver = driver
        self._layout: Optional[Layout] = None
        self._layout_error: Optional[str] = None
        self._loaded: Optional[Tuple[str, str, int, str, int, int]] = None
        if driver is not None:
            try:
                self._layout = Layout.from_manifest(driver.manifest())
            except (LayoutError, Exception) as exc:  # a bad manifest is unavailability
                self._layout_error = "manifest rejected: %s" % exc

    def available(self) -> Tuple[bool, str]:
        if self._driver is None:
            return False, (
                "no SubstrateIO driver configured — a Muhlnickel-shaped execution "
                "engine has not been supplied; an uploaded container file does not compute"
            )
        if self._layout is None:
            return False, self._layout_error or "layout not bound"
        return True, "layout %s bound on instance %s" % (LAYOUT_SCHEMA, self._layout.instance_id)

    def instance_id(self) -> str:
        return self._layout.instance_id if self._layout else "unavailable"

    def start(self, request: WorkRequest) -> WorkHandle:
        ok, why = self.available()
        if not ok:
            handle = WorkHandle(request=request, started_at=time.time())
            handle.last = WorkProgress(WorkState.UNAVAILABLE, detail=why)
            return handle
        driver, layout = self._driver, self._layout
        assert driver is not None and layout is not None
        handle = WorkHandle(request=request, started_at=time.time())
        try:
            # 1. quiesce: no field write is legal while the rings are advancing
            driver.set_enabled(False)
            # 2. fresh job load clears the sticky ready contacts
            writes: Dict[str, bytes] = {name: b"\x00" for name in STICKY_FIELDS}
            writes[F_RECEIVER] = b"\x00"
            writes[F_HEADER] = pack_header_bitbytes(request.header76)
            writes[F_TARGET] = pack_target_bitbytes(request.network_target)
            writes[F_NONCE_END] = pack_uint32_bitbytes(request.nonce_range.end_inclusive)
            writes[F_WINNER_NONCE] = pack_uint32_bitbytes(0)
            start_bits = pack_uint32_bitbytes(request.nonce_range.start)
            writes[F_NONCE] = start_bits
            # 3. seed the latch itself so an arbitrary start nonce really restarts
            writes.update(layout.state_writes(F_NONCE, start_bits))
            writes.update(layout.state_writes(F_WINNER_NONCE, pack_uint32_bitbytes(0)))
            writes.update(layout.state_writes(F_WIN, b"\x00"))
            writes.update(layout.state_writes(F_EXHAUSTED, b"\x00"))
            driver.write_fields(writes)
            # 4. enable: rings begin driving the master/slave NAND latches
            driver.set_enabled(True)
        except Exception as exc:
            handle.last = WorkProgress(WorkState.FAILED, detail="load failed: %s" % exc)
            self._loaded = None
            return handle
        self._loaded = request.identity
        handle.last = WorkProgress(WorkState.RUNNING, detail="enabled")
        return handle

    def poll(self, handle: WorkHandle) -> WorkProgress:
        ok, why = self.available()
        if not ok:
            return WorkProgress(WorkState.UNAVAILABLE, detail=why)
        if handle.cancelled:
            return handle.last or WorkProgress(WorkState.CANCELLED, detail="cancelled")
        if self._loaded != handle.request.identity:
            return WorkProgress(
                WorkState.CANCELLED,
                detail="container now holds different work; this handle is retired",
            )
        driver = self._driver
        assert driver is not None
        try:
            snap = driver.read_coherent(POLL_FIELDS)
        except Exception as exc:
            return WorkProgress(WorkState.FAILED, detail="read_coherent failed: %s" % exc)

        # readiness is decided only from a coherent, commit_ready-gated snapshot
        if not snap.coherent or snap.bit(F_COMMIT_READY) != 1:
            progress = WorkProgress(
                WorkState.RUNNING, coherent=False, receipt=snap.receipt,
                detail="snapshot not coherent / commit_ready low; no frontier recorded",
            )
            handle.last = progress
            return progress

        rng = handle.request.nonce_range
        if snap.bit(F_RESULT_READY) == 1 and snap.bit(F_WIN) == 1:
            # winner_nonce is stable once result_ready latches. 0 is a real winner.
            progress = WorkProgress(
                WorkState.CANDIDATE_READY,
                winner_nonce=snap.u32(F_WINNER_NONCE),
                frontier_exclusive=None,
                coherent=True, receipt=snap.receipt,
                detail="result_ready=1 win=1",
            )
        elif snap.bit(F_EXHAUSTED_READY) == 1 and snap.bit(F_EXHAUSTED) == 1:
            progress = WorkProgress(
                WorkState.EXHAUSTED,
                frontier_exclusive=rng.end_exclusive,
                coherent=True, receipt=snap.receipt,
                detail="exhausted_ready=1 (inclusive end %d complete)" % rng.end_inclusive,
            )
        else:
            committed = snap.u32(F_NONCE)
            frontier = committed if rng.start <= committed <= rng.end_inclusive else None
            progress = WorkProgress(
                WorkState.RUNNING, frontier_exclusive=frontier,
                coherent=True, receipt=snap.receipt,
                detail="committed nonce %d" % committed,
            )
        handle.last = progress
        return progress

    def cancel(self, handle: WorkHandle) -> WorkProgress:
        handle.cancelled = True
        ok, why = self.available()
        if not ok:
            return WorkProgress(WorkState.UNAVAILABLE, detail=why)
        driver = self._driver
        assert driver is not None
        last = handle.last
        try:
            driver.set_enabled(False)  # cancels ring and state advancement
        except Exception as exc:
            progress = WorkProgress(WorkState.FAILED, detail="disable failed: %s" % exc)
            handle.last = progress
            return progress
        if self._loaded == handle.request.identity:
            self._loaded = None
        progress = WorkProgress(
            WorkState.CANCELLED,
            frontier_exclusive=last.frontier_exclusive if last and last.coherent else None,
            coherent=bool(last and last.coherent),
            receipt=last.receipt if last else None,
            detail="disabled; frontier kept only if a coherent snapshot recorded one",
        )
        handle.last = progress
        return progress


# ── checkpointing ────────────────────────────────────────────────────────────


class CheckpointStore(Protocol):
    def load(self) -> Dict[str, Any]: ...
    def save(self, state: Mapping[str, Any]) -> None: ...


class JsonFileCheckpoint:
    """Atomic JSON checkpoint. Written only when a run actually executes."""

    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, state: Mapping[str, Any]) -> None:
        parent = os.path.dirname(os.path.abspath(self.path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = "%s.tmp.%s" % (self.path, uuid.uuid4().hex[:8])
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(dict(state), fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)


# ── runner ───────────────────────────────────────────────────────────────────


class RunnerStatus(Enum):
    EXECUTOR_UNAVAILABLE = "executor_unavailable"
    NO_JOB = "no_job"
    RUNNING = "running"
    CANDIDATE_SUBMITTED = "candidate_submitted"
    CANDIDATE_REJECTED_LOCALLY = "candidate_rejected_locally"
    RANGE_EXHAUSTED = "range_exhausted"
    STALE_CANCELLED = "stale_cancelled"
    SESSION_LOST = "session_lost"
    ERROR = "error"


@dataclass(frozen=True)
class RunnerReport:
    status: RunnerStatus
    detail: str
    session_id: Optional[str] = None
    job_id: Optional[str] = None
    generation: Optional[int] = None
    nonce_range: Optional[Tuple[int, int]] = None
    frontier_exclusive: Optional[int] = None
    candidate: Optional[Candidate] = None
    verification: Optional[Verification] = None
    submit: Optional[SubmitOutcome] = None
    receipt: Optional[str] = None

    @property
    def is_accepted_block_candidate(self) -> bool:
        return bool(self.submit and self.submit.is_accepted_block_candidate)


class CloudMiner:
    """Drives one executor against one live Stratum session.

    `run_once()` performs a single bounded step: ensure a live job, ensure a
    loaded range, poll, and act on whatever the device actually surfaced.
    """

    def __init__(
        self,
        client: StratumClient,
        executor: Optional[Executor] = None,
        checkpoint: Optional[CheckpointStore] = None,
        range_size: int = 1 << 24,
        poll_timeout: float = 30.0,
    ) -> None:
        if range_size <= 0 or range_size > UINT32_MAX + 1:
            raise ValueError("range_size out of bounds: %r" % (range_size,))
        self.client = client
        self.executor = executor
        self.checkpoint = checkpoint
        self.range_size = range_size
        self.poll_timeout = poll_timeout
        self._handle: Optional[WorkHandle] = None
        self._job: Optional[Job] = None
        self._extranonce2_counter = 0
        # (session_id, job_id, generation, extranonce2) -> issued ranges
        self._issued: Dict[Tuple[str, str, int, str], List[NonceRange]] = {}
        self._frontier: Dict[Tuple[str, str, int, str], int] = {}
        self._submitted_keys: set = set()
        if checkpoint is not None:
            self._restore(checkpoint.load())

    # ── checkpoint ───────────────────────────────────────────────────────

    def _restore(self, state: Mapping[str, Any]) -> None:
        """Reload issued ranges and frontiers. Restored work is historical: it is
        never revived for submission, because its session is retired by definition."""
        for row in state.get("issued", []) or []:
            try:
                key = (str(row["session_id"]), str(row["job_id"]), int(row["generation"]),
                       str(row["extranonce2"]))
                self._issued.setdefault(key, []).append(
                    NonceRange(int(row["start"]), int(row["end_exclusive"]))
                )
                if row.get("frontier_exclusive") is not None:
                    self._frontier[key] = int(row["frontier_exclusive"])
            except (KeyError, TypeError, ValueError):
                continue
        for key in state.get("submitted", []) or []:
            if isinstance(key, list) and len(key) == 5:
                self._submitted_keys.add((key[0], key[1], key[2], key[3], int(key[4])))

    def _persist(self) -> None:
        if self.checkpoint is None:
            return
        rows = []
        for key, ranges in self._issued.items():
            for rng in ranges:
                rows.append({
                    "session_id": key[0], "job_id": key[1], "generation": key[2],
                    "extranonce2": key[3], "start": rng.start,
                    "end_exclusive": rng.end_exclusive,
                    "frontier_exclusive": self._frontier.get(key),
                })
        live = self.client.session
        self.checkpoint.save({
            "schema": "muhl-cloud-miner-checkpoint/v1",
            "written_at": time.time(),
            "live_session_id": live.session_id if live and not live.retired else None,
            "instance_id": self.executor.instance_id() if self.executor else None,
            "issued": rows,
            "submitted": [list(k) for k in sorted(self._submitted_keys)],
        })

    # ── range allocation ─────────────────────────────────────────────────

    def _key(self, job: Job, extranonce2: str) -> Tuple[str, str, int, str]:
        return (job.session_id, job.job_id, job.generation, extranonce2)

    def _next_extranonce2(self, job: Job) -> str:
        value = self._extranonce2_counter & ((1 << (8 * job.extranonce2_size)) - 1)
        self._extranonce2_counter += 1
        return "%0*x" % (job.extranonce2_size * 2, value)

    def _next_range(self, job: Job, extranonce2: str) -> Optional[NonceRange]:
        """Next non-overlapping range for this exact (session, job, gen, en2)."""
        issued = self._issued.setdefault(self._key(job, extranonce2), [])
        start = max((r.end_exclusive for r in issued), default=0)
        if start > UINT32_MAX:
            return None
        end = min(start + self.range_size, UINT32_MAX + 1)
        rng = NonceRange(start, end)
        if any(rng.overlaps(other) for other in issued):
            raise AssertionError("range allocator produced an overlap: %r" % (rng,))
        issued.append(rng)
        return rng

    # ── one step ─────────────────────────────────────────────────────────

    def run_once(self) -> RunnerReport:
        if self.executor is None:
            return RunnerReport(
                RunnerStatus.EXECUTOR_UNAVAILABLE,
                "no executor configured — supply a SubstrateIO-backed "
                "MuhlnickelExecutor; nothing was run and no progress is claimed",
            )
        available, why = self.executor.available()
        if not available:
            return RunnerReport(RunnerStatus.EXECUTOR_UNAVAILABLE, why)

        if not self.client.connected:
            self._cancel_current("stratum session is not ready")
            return RunnerReport(
                RunnerStatus.SESSION_LOST,
                "no authorized live session; retired work cannot be submitted",
            )

        try:
            job = self.client.wait_for_job(timeout=self.poll_timeout)
        except StratumTimeout as exc:
            return RunnerReport(RunnerStatus.NO_JOB, str(exc))
        except StratumDisconnected as exc:
            self._cancel_current(str(exc))
            return RunnerReport(RunnerStatus.SESSION_LOST, str(exc))

        # a new generation (clean_jobs / set_extranonce / new session) kills work
        if self._handle is not None:
            req = self._handle.request
            if (req.session_id, req.job_id, req.generation) != (
                job.session_id, job.job_id, job.generation
            ) or not self.client.is_job_live(req.session_id, req.job_id, req.generation):
                report = self._cancel_current(
                    "job %s gen %d retired; live job is %s gen %d"
                    % (req.job_id, req.generation, job.job_id, job.generation)
                )
                self._persist()
                return report

        if self._handle is None:
            return self._load(job)
        return self._poll(job)

    def _load(self, job: Job) -> RunnerReport:
        assert self.executor is not None
        extranonce2 = self._next_extranonce2(job)
        try:
            job.check_extranonce2(extranonce2)
            header76 = job.header76(extranonce2)
        except (ValueError, TypeError) as exc:
            return RunnerReport(RunnerStatus.ERROR, "header build failed: %s" % exc)
        rng = self._next_range(job, extranonce2)
        if rng is None:
            return RunnerReport(
                RunnerStatus.RANGE_EXHAUSTED,
                "nonce space exhausted for extranonce2 %s" % extranonce2,
                session_id=job.session_id, job_id=job.job_id, generation=job.generation,
            )
        request = WorkRequest(
            instance_id=self.executor.instance_id(),
            session_id=job.session_id, job_id=job.job_id, generation=job.generation,
            extranonce2=extranonce2, ntime=job.ntime, header76=header76,
            network_target=job.network_target, nonce_range=rng, issued_at=time.time(),
        )
        handle = self.executor.start(request)
        progress = handle.last or WorkProgress(WorkState.FAILED, detail="no progress returned")
        if progress.state is WorkState.UNAVAILABLE:
            return RunnerReport(RunnerStatus.EXECUTOR_UNAVAILABLE, progress.detail)
        if progress.state is WorkState.FAILED:
            return RunnerReport(
                RunnerStatus.ERROR, progress.detail,
                session_id=job.session_id, job_id=job.job_id, generation=job.generation,
                nonce_range=(rng.start, rng.end_exclusive),
            )
        self._handle = handle
        self._job = job
        self._persist()
        return RunnerReport(
            RunnerStatus.RUNNING,
            "loaded nonce [%d, %d) (device nonce_end=%d, inclusive) and enabled"
            % (rng.start, rng.end_exclusive, rng.end_inclusive),
            session_id=job.session_id, job_id=job.job_id, generation=job.generation,
            nonce_range=(rng.start, rng.end_exclusive), receipt=progress.receipt,
        )

    def _poll(self, job: Job) -> RunnerReport:
        assert self.executor is not None and self._handle is not None
        handle = self._handle
        req = handle.request
        rng = req.nonce_range
        progress = self.executor.poll(handle)
        key = self._key(job, req.extranonce2)
        if progress.coherent and progress.frontier_exclusive is not None:
            prior = self._frontier.get(key, rng.start)
            self._frontier[key] = max(prior, progress.frontier_exclusive)

        base = dict(
            session_id=req.session_id, job_id=req.job_id, generation=req.generation,
            nonce_range=(rng.start, rng.end_exclusive),
            frontier_exclusive=self._frontier.get(key), receipt=progress.receipt,
        )

        if progress.state is WorkState.UNAVAILABLE:
            return RunnerReport(RunnerStatus.EXECUTOR_UNAVAILABLE, progress.detail, **base)

        if progress.state is WorkState.FAILED:
            self._handle = None
            self._persist()
            return RunnerReport(RunnerStatus.ERROR, progress.detail, **base)

        if progress.state is WorkState.CANCELLED:
            self._handle = None
            self._persist()
            return RunnerReport(RunnerStatus.STALE_CANCELLED, progress.detail, **base)

        if progress.state is WorkState.EXHAUSTED:
            self.executor.cancel(handle)
            self._handle = None
            self._persist()
            return RunnerReport(
                RunnerStatus.RANGE_EXHAUSTED,
                "range covered through inclusive end %d" % rng.end_inclusive, **base
            )

        if progress.state is WorkState.RUNNING:
            self._persist()
            return RunnerReport(RunnerStatus.RUNNING, progress.detail, **base)

        # CANDIDATE_READY — one hash-check, on the live session only
        nonce = progress.winner_nonce
        if nonce is None:
            return RunnerReport(
                RunnerStatus.ERROR, "result_ready with no winner_nonce field", **base
            )
        if not rng.start <= nonce <= rng.end_inclusive:
            self.executor.cancel(handle)
            self._handle = None
            self._persist()
            return RunnerReport(
                RunnerStatus.CANDIDATE_REJECTED_LOCALLY,
                "winner_nonce %d is outside the loaded range [%d, %d]"
                % (nonce, rng.start, rng.end_inclusive), **base
            )
        candidate = Candidate(
            session_id=req.session_id, job_id=req.job_id, generation=req.generation,
            extranonce2=req.extranonce2, ntime=req.ntime, nonce=nonce,
            source="muhlnickel:%s" % req.instance_id, receipt=progress.receipt,
        )
        if candidate.key in self._submitted_keys:
            return RunnerReport(
                RunnerStatus.CANDIDATE_REJECTED_LOCALLY,
                "duplicate candidate already submitted", candidate=candidate, **base
            )
        if not self.client.is_job_live(req.session_id, req.job_id, req.generation):
            report = self._cancel_current("job retired before the candidate could be sent")
            self._persist()
            return report

        verification = self.client.verify(job, candidate)
        if not verification.is_block:
            # A sticky winner stops device progression. An invalid surfaced
            # winner is a concrete executor error, not continuing mining.
            self.executor.cancel(handle)
            self._handle = None
            self._persist()
            return RunnerReport(
                RunnerStatus.CANDIDATE_REJECTED_LOCALLY,
                "surfaced candidate did not meet the network target: %s" % verification.detail,
                candidate=candidate, verification=verification, **base
            )
        try:
            outcome = self.client.submit(job, candidate)
        except StratumError as exc:
            return RunnerReport(
                RunnerStatus.ERROR, "submit failed: %s" % exc,
                candidate=candidate, verification=verification, **base
            )
        if outcome.status is SubmitStatus.ERROR:
            # Delivery is ambiguous. Keep the sticky candidate and live handle
            # for retry/reconciliation; do not discard the potential block.
            self._persist()
            return RunnerReport(
                RunnerStatus.ERROR, "submission outcome unknown; candidate retained",
                candidate=candidate, verification=verification, submit=outcome, **base
            )
        if outcome.status in (SubmitStatus.ACCEPTED, SubmitStatus.REJECTED):
            self._submitted_keys.add(candidate.key)
        self.executor.cancel(handle)
        self._handle = None
        self._persist()
        return RunnerReport(
            RunnerStatus.CANDIDATE_SUBMITTED,
            "%s (pool acceptance of a share is not payment and not a confirmed block)"
            % outcome.detail,
            candidate=candidate, verification=verification, submit=outcome, **base
        )

    def _cancel_current(self, why: str) -> RunnerReport:
        handle, self._handle = self._handle, None
        if handle is None or self.executor is None:
            return RunnerReport(RunnerStatus.STALE_CANCELLED, why)
        progress = self.executor.cancel(handle)
        req = handle.request
        key = (req.session_id, req.job_id, req.generation, req.extranonce2)
        if progress.coherent and progress.frontier_exclusive is not None:
            self._frontier[key] = max(self._frontier.get(key, req.nonce_range.start),
                                      progress.frontier_exclusive)
        return RunnerReport(
            RunnerStatus.STALE_CANCELLED, why,
            session_id=req.session_id, job_id=req.job_id, generation=req.generation,
            nonce_range=(req.nonce_range.start, req.nonce_range.end_exclusive),
            frontier_exclusive=self._frontier.get(key), receipt=progress.receipt,
        )

    def close(self) -> None:
        self._cancel_current("runner closed")
        self._persist()
