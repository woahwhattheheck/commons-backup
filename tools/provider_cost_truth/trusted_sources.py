"""Source-controlled provider evidence authority for the cost-truth gate.

Entries in this manifest are SHA-256 fingerprints of fully normalized evidence
rows (including provider/account/scope identity, amount/currency, event and
observation/validity times, source reference, source SHA-256, and authority).

The manifest is intentionally empty in v1. A raw caller snapshot can therefore
never mint ZERO_COST_VERIFIED or BILLABLE_VERIFIED merely by writing
``authority='PROVIDER_AUTHENTICATED'``. Adding a fingerprint is an explicit
source change and must be backed by independently authenticated provider
material reviewed outside this package.
"""
from __future__ import annotations

import hashlib
import json

TRUSTED_PROVIDER_EVIDENCE_SCHEMA = "provider-cost-trusted-evidence/v1"

# Immutable by construction so rebinding the module name after evaluator import
# cannot mutate the generation captured by the supported current API.
TRUSTED_PROVIDER_EVIDENCE_FINGERPRINTS: frozenset[str] = frozenset()


def _manifest_digest(fingerprints: frozenset[str]) -> str:
    payload = {
        "schema": TRUSTED_PROVIDER_EVIDENCE_SCHEMA,
        "fingerprints": sorted(fingerprints),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


# Every current/historical evaluation binds this source-controlled generation.
TRUSTED_PROVIDER_EVIDENCE_MANIFEST_SHA256 = _manifest_digest(
    TRUSTED_PROVIDER_EVIDENCE_FINGERPRINTS
)
