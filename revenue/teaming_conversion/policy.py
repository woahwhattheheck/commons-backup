from __future__ import annotations

from types import MappingProxyType
from typing import Any

from .common import digest_object

# Repository-owned policy.  The scalar/tuple defaults below are captured when
# this module is imported so ordinary post-import rebinding of module globals
# cannot select a different CURRENT policy.
_POLICY_SCHEMA = "teaming-conversion-policy/v2"
_POLICY_ID = "commons-teaming-conversion-control"
_POLICY_VERSION = "2026-09-15"
_MAX_FUTURE_SKEW_SECONDS = 300
_MAX_REPLY_AGE_SECONDS = 7 * 24 * 60 * 60
_MAX_SOURCE_AGE_SECONDS = 14 * 24 * 60 * 60
_MAX_CURRENT_RECEIPT_AGE_SECONDS = 5 * 60
_REQUIRED_CLEAR_GATE_IDS: tuple[str, ...] = ()
_REQUIRED_COMMITMENT_IDS: tuple[str, ...] = ()


def policy_dict(
    _schema: str = _POLICY_SCHEMA,
    _policy_id: str = _POLICY_ID,
    _policy_version: str = _POLICY_VERSION,
    _max_future_skew_seconds: int = _MAX_FUTURE_SKEW_SECONDS,
    _max_reply_age_seconds: int = _MAX_REPLY_AGE_SECONDS,
    _max_source_age_seconds: int = _MAX_SOURCE_AGE_SECONDS,
    _max_current_receipt_age_seconds: int = _MAX_CURRENT_RECEIPT_AGE_SECONDS,
    _required_clear_gate_ids: tuple[str, ...] = _REQUIRED_CLEAR_GATE_IDS,
    _required_commitment_ids: tuple[str, ...] = _REQUIRED_COMMITMENT_IDS,
) -> dict[str, Any]:
    """Return a detached copy of the repository-owned policy snapshot."""
    return {
        "schema": _schema,
        "policy_id": _policy_id,
        "policy_version": _policy_version,
        "max_future_skew_seconds": _max_future_skew_seconds,
        "max_reply_age_seconds": _max_reply_age_seconds,
        "max_source_age_seconds": _max_source_age_seconds,
        "max_current_receipt_age_seconds": _max_current_receipt_age_seconds,
        "required_clear_gate_ids": list(_required_clear_gate_ids),
        "required_commitment_ids": list(_required_commitment_ids),
    }


_POLICY_SNAPSHOT = policy_dict()
POLICY_SHA256 = digest_object(_POLICY_SNAPSHOT)
POLICY = MappingProxyType(
    {
        **_POLICY_SNAPSHOT,
        "required_clear_gate_ids": tuple(_POLICY_SNAPSHOT["required_clear_gate_ids"]),
        "required_commitment_ids": tuple(_POLICY_SNAPSHOT["required_commitment_ids"]),
    }
)
