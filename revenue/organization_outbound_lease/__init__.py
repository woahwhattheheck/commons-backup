"""Atomic organization-wide outbound lease.

Internal coordination only. This package never authorizes or performs an external send.
The pressure-verifier trust boundary is structural in :mod:`.core`; this facade only
re-exports that implementation and the explicit local/reference diagnostics.
"""

from pathlib import Path

from . import core as _core
from .local_reference import (
    _LOCAL_REFERENCE_ACQUIRE_IMPLS,
    _LOCAL_REFERENCE_CHECKER,
    _LOCAL_REFERENCE_PATH_TYPE,
    _LOCAL_REFERENCE_STORE_TYPE,
    mechanically_local_reference_store as _mechanically_local_reference_store,
)
from .stores import FileLeaseStore, GitHubContentsLeaseStore, StoreConflict, StoreUncertain

READY_STATE = _core.READY_STATE
TERMINAL_STATES = _core.TERMINAL_STATES
RsaPublicKey = _core.RsaPublicKey
acquire_lease = _core.acquire_lease
canonical_json = _core.canonical_json
finalize_lease = _core.finalize_lease
fingerprint_organization = _core.fingerprint_organization
holder_capability_commitment = _core.holder_capability_commitment
normalize_organization_fingerprint = _core.normalize_organization_fingerprint
verify_lease_document = _core.verify_lease_document
verify_outcome_document = _core.verify_outcome_document
verify_pressure_attestation = _core.verify_pressure_attestation

__all__ = [
    "READY_STATE",
    "TERMINAL_STATES",
    "RsaPublicKey",
    "FileLeaseStore",
    "GitHubContentsLeaseStore",
    "StoreConflict",
    "StoreUncertain",
    "acquire_lease",
    "canonical_json",
    "finalize_lease",
    "fingerprint_organization",
    "holder_capability_commitment",
    "normalize_organization_fingerprint",
    "verify_lease_document",
    "verify_outcome_document",
    "verify_pressure_attestation",
]
