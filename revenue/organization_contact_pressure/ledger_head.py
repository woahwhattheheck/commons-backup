"""Host-authenticated retained current-ledger checkpoints.

The ledger file is mutable retained evidence. While its independently protected
checkpoint directory remains intact, a copied-back authentic ledger cannot become
current below a retained higher head. Only checkpoints from the active verifier-
and-policy epoch can authorize the current ledger; older epochs may remain for
history without becoming current authority.
"""

from __future__ import annotations

import hmac
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Optional

from .core import (
    LEDGER_HEAD_SCHEMA,
    MAX_JSON_BYTES,
    MAX_LEDGER_HEAD_FILES,
    MAX_SAFE_INTEGER,
    ActiveKey,
    AuthorityView,
    InputError,
    LedgerView,
    VerificationError,
    _expect_exact_fields,
    _expect_hex64,
    _expect_int,
    _expect_key_id,
    _expect_object,
    _expect_slug,
    _format_time,
    _hmac_hex,
    _parse_time,
    _sha256,
    strict_json_loads,
)
from .storage import _open_directory_fd, _read_regular_file_at

_HEAD_NAME_RE = re.compile(r"^(\d{20})-(\d{20})-([0-9a-f]{64})-([0-9a-f]{64})\.json$")


def _ledger_head_epoch_sha256(key_id: str, verifier_id: str) -> str:
    return _sha256((key_id + "\x00" + verifier_id).encode("utf-8"))


def _ledger_head_filename(body: Mapping[str, Any]) -> str:
    return (
        f"{body['policy_generation']:020d}-"
        f"{body['ledger_generation']:020d}-"
        f"{body['ledger_sha256']}-"
        f"{_ledger_head_epoch_sha256(body['key_id'], body['verifier_id'])}.json"
    )


def _normalize_ledger_head_document(document: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    fields = {
        "schema",
        "organization_scope_sha256",
        "policy_generation",
        "ledger_generation",
        "ledger_state_sha256",
        "ledger_sha256",
        "ledger_updated_at",
        "committed_at",
        "key_id",
        "verifier_id",
        "signature",
    }
    _expect_exact_fields(document, fields, "ledger head")
    if document["schema"] != LEDGER_HEAD_SCHEMA:
        raise InputError("unsupported ledger head schema")
    body = {
        "schema": LEDGER_HEAD_SCHEMA,
        "organization_scope_sha256": _expect_hex64(
            document["organization_scope_sha256"], "ledger_head.organization_scope_sha256"
        ),
        "policy_generation": _expect_int(
            document["policy_generation"],
            "ledger_head.policy_generation",
            minimum=1,
            maximum=MAX_SAFE_INTEGER,
        ),
        "ledger_generation": _expect_int(
            document["ledger_generation"],
            "ledger_head.ledger_generation",
            minimum=0,
            maximum=MAX_SAFE_INTEGER,
        ),
        "ledger_state_sha256": _expect_hex64(
            document["ledger_state_sha256"], "ledger_head.ledger_state_sha256"
        ),
        "ledger_sha256": _expect_hex64(document["ledger_sha256"], "ledger_head.ledger_sha256"),
        "ledger_updated_at": _format_time(
            _parse_time(document["ledger_updated_at"], "ledger_head.ledger_updated_at")
        ),
        "committed_at": _format_time(_parse_time(document["committed_at"], "ledger_head.committed_at")),
        "key_id": _expect_key_id(document["key_id"], "ledger_head.key_id"),
        "verifier_id": _expect_slug(document["verifier_id"], "ledger_head.verifier_id"),
    }
    signature = _expect_hex64(document["signature"], "ledger_head.signature")
    return body, signature


def _verify_current_ledger_head(
    root: Path,
    active: ActiveKey,
    authority: AuthorityView,
    ledger: LedgerView,
    now: datetime,
) -> None:
    directory = root / "ledger-heads" / authority.organization_scope_sha256
    directory_fd = _open_directory_fd(directory)
    try:
        names = sorted(os.listdir(directory_fd))
        if not names:
            raise VerificationError("current ledger head is missing")
        if len(names) > MAX_LEDGER_HEAD_FILES:
            raise VerificationError("ledger head journal exceeds entry limit")

        # generation, event-state digest, full ledger digest, coverage time, commit time
        current: list[tuple[int, str, str, datetime, datetime]] = []
        active_policy_generations: set[int] = set()
        for name in names:
            if not _HEAD_NAME_RE.fullmatch(name):
                raise VerificationError("ledger head journal contains an unexpected entry")
            raw = _read_regular_file_at(directory_fd, name, limit=min(MAX_JSON_BYTES, 16_384), private=True)
            try:
                document = _expect_object(strict_json_loads(raw), "ledger head")
                body, signature = _normalize_ledger_head_document(document)
            except InputError as exc:
                raise VerificationError("retained ledger head is malformed") from exc
            if name != _ledger_head_filename(body):
                raise VerificationError("ledger head filename/body mismatch")
            if body["organization_scope_sha256"] != authority.organization_scope_sha256:
                raise VerificationError("ledger head path/scope mismatch")

            # Historical verifier epochs are retained but cannot authorize the
            # current ledger. The active epoch must publish its own checkpoint.
            if body["key_id"] != active.key_id or body["verifier_id"] != active.verifier_id:
                continue
            if not hmac.compare_digest(signature, _hmac_hex(active.key, body)):
                raise VerificationError("ledger head HMAC is invalid")
            ledger_updated = _parse_time(body["ledger_updated_at"], "ledger_head.ledger_updated_at")
            committed = _parse_time(body["committed_at"], "ledger_head.committed_at")
            skew = timedelta(seconds=authority.max_future_skew_seconds)
            if ledger_updated > committed:
                raise VerificationError("ledger head predates the ledger update")
            if committed > now + skew:
                raise VerificationError("ledger head is future-committed")

            active_policy_generations.add(body["policy_generation"])
            # Policy generations are independent retained epochs. A legitimate
            # policy rotation may re-sign an unchanged event set at the same
            # event-count generation, so older policy checkpoints remain
            # historical without becoming a false same-generation fork.
            if body["policy_generation"] != authority.policy_generation:
                continue
            current.append(
                (
                    body["ledger_generation"],
                    body["ledger_state_sha256"],
                    body["ledger_sha256"],
                    ledger_updated,
                    committed,
                )
            )
    finally:
        os.close(directory_fd)

    if active_policy_generations and authority.policy_generation < max(active_policy_generations):
        raise VerificationError("authority policy rollback detected below retained head")
    if not current:
        raise VerificationError("current verifier/policy epoch has no ledger head")

    # Event-count generation identifies semantic ledger state. Coverage heartbeats
    # may re-sign the *same* state at a later updated_at while no contact event
    # changed. A different event-state digest at the same generation remains a fork.
    states_by_generation: dict[int, set[str]] = {}
    rows_by_generation: dict[int, list[tuple[str, str, datetime, datetime]]] = {}
    for generation, state_digest, digest, ledger_updated, committed in current:
        states_by_generation.setdefault(generation, set()).add(state_digest)
        rows_by_generation.setdefault(generation, []).append(
            (state_digest, digest, ledger_updated, committed)
        )
    for generation, states in states_by_generation.items():
        if len(states) != 1:
            raise VerificationError(f"same-generation ledger fork detected at generation {generation}")

    # Across the append-only checkpoint history, both coverage time and commit
    # time must move monotonically forward as event generation increases or an
    # identical-state coverage heartbeat advances.
    prior_updated: Optional[datetime] = None
    prior_committed: Optional[datetime] = None
    ordered = sorted(current, key=lambda row: (row[0], row[3], row[4], row[2]))
    for _, _, _, ledger_updated, committed in ordered:
        if prior_updated is not None and ledger_updated < prior_updated:
            raise VerificationError("ledger head journal update time moved backward")
        if prior_committed is not None and committed < prior_committed:
            raise VerificationError("ledger head journal commit time moved backward")
        prior_updated = ledger_updated
        prior_committed = committed

    highest = max(states_by_generation)
    if ledger.generation < highest:
        raise VerificationError("ledger rollback detected below retained head")
    if ledger.generation > highest:
        raise VerificationError("ledger is newer than the retained committed head")

    highest_rows = rows_by_generation[highest]
    # Coverage is the latest signed updated_at for the highest semantic state.
    latest_updated = max(row[2] for row in highest_rows)
    latest_rows = [row for row in highest_rows if row[2] == latest_updated]
    latest_digests = {row[1] for row in latest_rows}
    if len(latest_digests) != 1:
        raise VerificationError(f"same-generation ledger fork detected at generation {highest}")
    expected_state, expected_digest, expected_updated, _ = max(
        latest_rows, key=lambda row: (row[3], row[1])
    )
    if ledger.state_digest != expected_state:
        raise VerificationError("same-generation ledger fork detected")
    if ledger.digest != expected_digest:
        raise VerificationError("ledger does not match latest retained coverage head")
    if ledger.updated_at != expected_updated:
        raise VerificationError("ledger head update-time mismatch")
