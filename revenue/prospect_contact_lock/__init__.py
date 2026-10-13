"""Canonical fail-closed prospect contact coordination."""
from typing import Any, Mapping

from . import hardened as _hardened
from . import lock as _core
from .lock import (
    AUTHORITY_BRANCH,
    AUTHORITY_DIGEST,
    AUTHORITY_GENERATION,
    AUTHORITY_ROOT,
    CANONICAL_API_ORIGIN,
    CANONICAL_REPOSITORY,
    ConflictError,
    LockError,
    Receipt,
    RemoteError,
    Target,
    ValidationError,
    digest_message_bytes,
    digest_message_file,
    normalize_target,
    verify_receipt,
)

_CoreProspectContactLock = _core.ProspectContactLock
_InjectedProspectContactLock = _hardened.ProspectContactLock


def _mark_test_artifact(doc: Mapping[str, Any]) -> dict[str, Any]:
    marked = dict(doc)
    # Deliberately do not reseal mutation receipts: production verify_receipt()
    # must reject anything emitted through an injected transport seam.
    marked["test_only_transport"] = True
    return marked


class ProspectContactLock(_InjectedProspectContactLock):
    """Only supported production mutation surface.

    Production owns the canonical GitHub transport. Arbitrary caller transport
    injection is intentionally absent from this constructor so a caller cannot
    synthesize authority-branch/ref/commit/content truth.
    """

    def __init__(self, token: str) -> None:
        super().__init__(token, None)


class _TestCoreProspectContactLock(_CoreProspectContactLock):
    """Private legacy-state-machine test seam with non-production artifacts."""

    def __init__(self, token: str, transport: _core.Transport) -> None:
        super().__init__(token, transport)

    @staticmethod
    def _receipt(
        action: str,
        outcome: str,
        target: Target,
        record: Mapping[str, Any],
        blob_sha: str | None,
        commit_sha: str | None,
    ) -> dict[str, Any]:
        return _mark_test_artifact(
            _CoreProspectContactLock._receipt(
                action, outcome, target, record, blob_sha, commit_sha
            )
        )

    def status(self, kind: str, raw_target: str) -> dict[str, Any]:
        return _mark_test_artifact(super().status(kind, raw_target))


class _TestProspectContactLock(_InjectedProspectContactLock):
    """Private hardened deterministic-transport seam for repository hostiles.

    Both the legacy marker fake and the transactional whole-ref fake are allowed
    here because this class is test-only. Every status/receipt is marked; signed
    mutation receipts retain the old seal and therefore fail production receipt
    validation instead of masquerading as canonical authority output.
    """

    def __init__(self, token: str, transport: _core.Transport) -> None:
        supported = bool(
            getattr(transport, "supports_authority_transactions", False)
            or hasattr(transport, "authority_available")
        )
        if not supported:
            raise ValidationError("test transport lacks a recognized repository test protocol")
        super().__init__(token, transport)

    @staticmethod
    def _receipt(
        action: str,
        outcome: str,
        target: Target,
        record: Mapping[str, Any],
        blob_sha: str | None,
        commit_sha: str | None,
    ) -> dict[str, Any]:
        return _mark_test_artifact(
            _InjectedProspectContactLock._receipt(
                action, outcome, target, record, blob_sha, commit_sha
            )
        )

    def status(self, kind: str, raw_target: str) -> dict[str, Any]:
        return _mark_test_artifact(super().status(kind, raw_target))


# One production class is installed onto every ordinary mutation import path.
# Captured pre-alias implementations survive only under explicit underscore test
# names and cannot emit production-verifiable receipts.
_hardened.ProspectContactLock = ProspectContactLock
_hardened._TestProspectContactLock = _TestProspectContactLock
_core.ProspectContactLock = ProspectContactLock
_core._TestProspectContactLock = _TestCoreProspectContactLock

__all__ = [
    "AUTHORITY_BRANCH", "AUTHORITY_DIGEST", "AUTHORITY_GENERATION",
    "AUTHORITY_ROOT", "CANONICAL_API_ORIGIN", "CANONICAL_REPOSITORY",
    "ConflictError", "LockError", "ProspectContactLock", "Receipt",
    "RemoteError", "Target", "ValidationError", "digest_message_bytes",
    "digest_message_file", "normalize_target", "verify_receipt",
]
