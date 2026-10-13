# SPDX-License-Identifier: Apache-2.0
"""Blob pinning: hash-pin every promotion input before it can be gated.

A pin manifest records the SHA-256 of each input file, copies the exact
bytes into a content-addressed blob store, and derives a deterministic
``input_digest`` used as the queue dedupe key. Pinning is idempotent:
pinning the same bytes twice yields the same pin id.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from . import SCHEMA_VERSION


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value) -> bytes:
    """Deterministic JSON encoding used for every digest the queue signs."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PinStore:
    """Content-addressed blob store plus pin manifests under ``root``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.blobs = self.root / "blobs"
        self.pins = self.root / "pins"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.pins.mkdir(parents=True, exist_ok=True)

    # -- blobs ---------------------------------------------------------
    def put_blob(self, path: Path) -> dict:
        """Copy ``path`` into the store keyed by its SHA-256. Idempotent."""
        digest = sha256_file(path)
        target = self.blobs / digest
        if not target.exists():
            tmp = target.with_suffix(".tmp")
            shutil.copyfile(path, tmp)
            tmp.replace(target)
        return {
            "sha256": digest,
            "bytes": target.stat().st_size,
            "stored_as": f"blobs/{digest}",
        }

    def blob_path(self, digest: str) -> Path:
        target = self.blobs / digest
        if not target.is_file():
            raise KeyError(f"blob not pinned: {digest}")
        return target

    def verify_blob(self, digest: str) -> bool:
        """Re-hash the stored bytes; False when missing or tampered."""
        try:
            target = self.blob_path(digest)
        except KeyError:
            return False
        return sha256_file(target) == digest

    # -- pins ----------------------------------------------------------
    def pin(
        self,
        inputs: Mapping[str, Path],
        *,
        note: str = "",
    ) -> dict:
        """Pin a named set of input files. Returns the pin manifest.

        The manifest's ``pin_id`` and ``input_digest`` are deterministic
        functions of the input bytes, so identical submissions dedupe.
        """
        pinned: dict[str, dict] = {}
        for name in sorted(inputs):
            source = Path(inputs[name])
            if not source.is_file():
                raise FileNotFoundError(f"pin input missing: {name} -> {source}")
            record = self.put_blob(source)
            record["source_name"] = source.name
            pinned[name] = record
        input_digest = sha256_bytes(
            canonical_json(
                {name: pinned[name]["sha256"] for name in sorted(pinned)}
            )
        )
        pin_id = f"pq-{datetime.now(timezone.utc):%Y%m%d}-{input_digest[:12]}"
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "pin_id": pin_id,
            "created_at": utcnow_iso(),
            "note": note,
            "inputs": pinned,
            "input_digest": input_digest,
        }
        manifest_path = self.pins / f"{pin_id}.json"
        if not manifest_path.exists():
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return manifest

    def get_pin(self, pin_id: str) -> dict:
        path = self.pins / f"{pin_id}.json"
        if not path.is_file():
            raise KeyError(f"unknown pin: {pin_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def verify_pin(self, pin_id: str) -> tuple[bool, list[str]]:
        """Re-hash every pinned blob; returns (ok, [problems])."""
        manifest = self.get_pin(pin_id)
        problems: list[str] = []
        for name, record in manifest["inputs"].items():
            if not self.verify_blob(record["sha256"]):
                problems.append(f"input {name}: blob missing or modified")
        recomputed = sha256_bytes(
            canonical_json(
                {
                    name: manifest["inputs"][name]["sha256"]
                    for name in sorted(manifest["inputs"])
                }
            )
        )
        if recomputed != manifest["input_digest"]:
            problems.append("input_digest mismatch: manifest tampered")
        return (not problems, problems)
