# SPDX-License-Identifier: Apache-2.0
"""FIFO queue store with dedupe and status tracking.

Statuses: ``pending`` -> ``running`` -> ``passed`` | ``failed``.
``rerun`` moves a terminal entry (or any entry) back to ``pending`` and
records the requeue; prior receipts are preserved as attempt history.
The JSON store is guarded by an advisory lock file so two writers do
not interleave a read-modify-write cycle.
"""
from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import SCHEMA_VERSION
from .pinning import utcnow_iso

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
TERMINAL = (STATUS_PASSED, STATUS_FAILED)


class QueueError(Exception):
    pass


class Queue:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "queue.json"
        self.lock_path = self.root / "queue.lock"
        if not self.path.exists():
            self._write({"schema_version": SCHEMA_VERSION, "entries": []})

    @contextmanager
    def _locked(self) -> Iterator[dict]:
        with open(self.lock_path, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                yield data
                self._write(data)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    # -- submit --------------------------------------------------------
    def find_by_input_digest(self, input_digest: str) -> dict | None:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for entry in data["entries"]:
            if entry["input_digest"] == input_digest:
                return entry
        return None

    def submit(
        self,
        *,
        submission_id: str,
        name: str,
        pin_id: str,
        input_digest: str,
        note: str = "",
    ) -> tuple[dict, bool]:
        """Enqueue a pinned candidate. Returns (entry, created).

        When another entry already carries the same ``input_digest`` the
        existing entry is returned and nothing is enqueued (dedupe).
        """
        with self._locked() as data:
            for entry in data["entries"]:
                if entry["input_digest"] == input_digest:
                    return entry, False
            entry = {
                "id": submission_id,
                "name": name,
                "status": STATUS_PENDING,
                "pin_id": pin_id,
                "input_digest": input_digest,
                "note": note,
                "created_at": utcnow_iso(),
                "updated_at": utcnow_iso(),
                "attempts": [],
                "last_receipt": None,
            }
            data["entries"].append(entry)
            return entry, True

    # -- scheduling ----------------------------------------------------
    def get(self, submission_id: str) -> dict:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for entry in data["entries"]:
            if entry["id"] == submission_id:
                return entry
        raise QueueError(f"unknown submission: {submission_id}")

    def list(self, status: str | None = None) -> list[dict]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        entries = data["entries"]
        if status is not None:
            entries = [e for e in entries if e["status"] == status]
        return entries

    def next_pending(self) -> dict | None:
        """Oldest pending entry (FIFO)."""
        pending = self.list(STATUS_PENDING)
        pending.sort(key=lambda e: e["created_at"])
        return pending[0] if pending else None

    def set_status(self, submission_id: str, status: str, **extra) -> dict:
        with self._locked() as data:
            for entry in data["entries"]:
                if entry["id"] == submission_id:
                    entry["status"] = status
                    entry["updated_at"] = utcnow_iso()
                    entry.update(extra)
                    return entry
        raise QueueError(f"unknown submission: {submission_id}")

    def record_attempt(self, submission_id: str, attempt: dict) -> dict:
        with self._locked() as data:
            for entry in data["entries"]:
                if entry["id"] == submission_id:
                    entry["attempts"].append(attempt)
                    entry["last_receipt"] = attempt.get("receipt_id")
                    entry["updated_at"] = utcnow_iso()
                    return entry
        raise QueueError(f"unknown submission: {submission_id}")

    def rerun(self, submission_id: str) -> dict:
        """Requeue an entry for another attempt. Prior history is kept."""
        with self._locked() as data:
            for entry in data["entries"]:
                if entry["id"] == submission_id:
                    if entry["status"] == STATUS_RUNNING:
                        raise QueueError("cannot rerun a running submission")
                    entry["status"] = STATUS_PENDING
                    entry["updated_at"] = utcnow_iso()
                    entry["attempts"].append(
                        {
                            "n": len(entry["attempts"]) + 1,
                            "kind": "requeue",
                            "at": utcnow_iso(),
                        }
                    )
                    return entry
        raise QueueError(f"unknown submission: {submission_id}")
