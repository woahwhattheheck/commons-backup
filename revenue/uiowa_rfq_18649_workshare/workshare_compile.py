#!/usr/bin/env python3
"""Current, historical, and explicitly untrusted compilation entrypoints."""
from __future__ import annotations

import datetime as _dt
from typing import Any

from workshare_contract import (
    MODE_CURRENT, MODE_HISTORICAL, MODE_UNTRUSTED, _coerce_now, _utc_now,
)
from workshare_assessment import _compile

def compile_current(
    candidate: Any,
    evidence_authority: Any,
    trusted_authority_sha256: str,
) -> dict[str, Any]:
    """Compile a current packet at a trusted-host boundary.

    The caller must obtain ``trusted_authority_sha256`` independently from the
    candidate and authority bytes. This module verifies equality but cannot
    authenticate how the caller acquired that root.
    """

    return _compile(
        candidate,
        evidence_authority,
        mode=MODE_CURRENT,
        evaluated_at=_utc_now(),
        trusted_authority_sha256=trusted_authority_sha256,
    )


def compile_historical(
    candidate: Any,
    evidence_authority: Any,
    trusted_authority_sha256: str,
    *,
    evaluated_at: _dt.datetime | str,
) -> dict[str, Any]:
    """Deterministic, explicitly non-current historical replay."""

    return _compile(
        candidate,
        evidence_authority,
        mode=MODE_HISTORICAL,
        evaluated_at=_coerce_now(evaluated_at, "historical_evaluated_at"),
        trusted_authority_sha256=trusted_authority_sha256,
    )


def compile_untrusted_inspection(
    candidate: Any,
    evidence_authority: Any,
    *,
    now: _dt.datetime | str | None = None,
) -> dict[str, Any]:
    """Public inspection path that can never mint current review authority."""

    return _compile(
        candidate,
        evidence_authority,
        mode=MODE_UNTRUSTED,
        evaluated_at=_coerce_now(now),
        trusted_authority_sha256=None,
    )


