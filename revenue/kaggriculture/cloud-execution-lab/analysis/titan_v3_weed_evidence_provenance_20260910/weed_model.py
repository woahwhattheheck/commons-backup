# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

RECEIPT_SCHEMA = "titan.weed-semantics-receipt.v1"
CLAIM_SCHEMA = "titan.weed-evidence-claim.v1"
GATE_SCHEMA = "titan.weed-evidence-gate.v1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")


class Semantics(str, Enum):
    EXPLICIT_W0 = "EXPLICIT_W0"
    EXPLICIT_W1 = "EXPLICIT_W1"
    LEGACY_PRE_GATE_W1 = "LEGACY_PRE_GATE_W1"
    COUPLED_WEED = "COUPLED_WEED"
    AMBIGUOUS = "AMBIGUOUS"


class Decision(str, Enum):
    ACCEPT = "ACCEPT"
    QUARANTINE = "QUARANTINE"
    INVALID = "INVALID"


class AnalysisError(ValueError):
    """Raised for malformed or unverifiable gate inputs."""


@dataclass(frozen=True)
class Artifact:
    role: str
    path: str
    data: bytes

    def receipt(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "path": self.path,
            "bytes": len(self.data),
            "sha256": hashlib.sha256(self.data).hexdigest(),
            "git_blob_sha1": git_blob_sha1(self.data),
        }


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def stable_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()
