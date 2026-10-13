"""Canonical, privacy-minimized v2 outreach claim coordination."""
from .core import (
    API_VERSION, AUTHORITY_DIGEST, AUTHORITY_GENERATION, AUTHORITY_POLICY,
    CANONICAL_API_URL, CANONICAL_REPOSITORY, DEFAULT_BRANCH, DEFAULT_ROOT, SCHEMA,
    ClaimConflict, ClaimFenceError, ClaimNotFound, ClaimReceipt, HttpResponse,
    OwnershipError, ProtocolError, RemoteError, TargetIdentity, UrllibTransport,
    ValidationError, _HEX_64, _canonical_json_bytes, _format_timestamp,
    _record_digest, _seal_record, digest_message_bytes, digest_message_file,
    normalize_target, sign_unsent_reconciliation, verify_unsent_reconciliation,
)
from .store import GitHubContentsClaimStore
from .cli import main

__all__ = [
    "AUTHORITY_DIGEST", "AUTHORITY_GENERATION", "AUTHORITY_POLICY", "CANONICAL_API_URL",
    "CANONICAL_REPOSITORY", "DEFAULT_BRANCH", "DEFAULT_ROOT", "SCHEMA", "ClaimConflict",
    "ClaimFenceError", "ClaimNotFound", "ClaimReceipt", "GitHubContentsClaimStore", "HttpResponse",
    "OwnershipError", "ProtocolError", "RemoteError", "TargetIdentity", "UrllibTransport",
    "ValidationError", "digest_message_bytes", "digest_message_file", "main", "normalize_target",
    "sign_unsent_reconciliation", "verify_unsent_reconciliation",
]
