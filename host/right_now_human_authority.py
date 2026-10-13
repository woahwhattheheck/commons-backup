#!/usr/bin/env python3
"""Bind right-now buyer-response truth to one canonical evidence generation.

The right-now catalog may state expected counters for reviewability, but those
numbers are assertions only. Production capture reads each canonical reply
source once, derives both semantics and receipt hashes from those exact bytes,
and then verifies the source generation did not move before returning. It never
reads a mailbox directly, sends mail, accepts a scope, or publishes private
message content.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host import reply_to_revenue  # noqa: E402


EXPECTED_KIND = "REPLY_TO_REVENUE_FUNNEL"


class HumanOutcomeAuthorityError(ValueError):
    """Human-outcome assertions or their retained evidence failed closed."""


def _non_negative_integer(value: Any, where: str) -> int:
    if type(value) is not int or value < 0:
        raise HumanOutcomeAuthorityError(f"{where} must be a non-negative integer")
    return value


def _normalized_sha256(data: bytes) -> str:
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def source_paths() -> list[Path]:
    """Return the complete canonical file set consumed by the reply compiler."""
    paths = [reply_to_revenue.OBSERVATIONS_PATH]
    paths.extend(sorted(reply_to_revenue.RECEIPTS_DIR.glob("*.json")))
    return paths


def _relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError as error:
        raise HumanOutcomeAuthorityError("human outcome source escaped repository root") from error


def _capture_source_generation() -> list[dict[str, Any]]:
    paths = source_paths()
    if not paths or paths[0] != reply_to_revenue.OBSERVATIONS_PATH:
        raise HumanOutcomeAuthorityError("canonical reply source inventory is malformed")
    if len(paths) < 2:
        raise HumanOutcomeAuthorityError("canonical reply source inventory has no outreach receipts")

    captured: list[dict[str, Any]] = []
    for path in paths:
        try:
            data = path.read_bytes()
        except OSError as error:
            raise HumanOutcomeAuthorityError(f"cannot capture canonical reply source {path}") from error
        captured.append(
            {
                "path": path,
                "relative": _relative(path),
                "data": data,
                "sha256": _normalized_sha256(data),
            }
        )
    return captured


def _compile_captured_funnel(captured: list[dict[str, Any]]) -> dict[str, Any]:
    """Run canonical validators/compiler over immutable copies of captured bytes."""
    if not captured:
        raise HumanOutcomeAuthorityError("captured reply source generation is empty")
    try:
        with tempfile.TemporaryDirectory(prefix="commons-reply-generation-") as temporary:
            root = Path(temporary)
            observations_path = root / "observations.json"
            receipts_dir = root / "receipts"
            receipts_dir.mkdir()
            observations_path.write_bytes(captured[0]["data"])
            for row in captured[1:]:
                (receipts_dir / Path(row["path"]).name).write_bytes(row["data"])
            observations = reply_to_revenue.load_observations(observations_path)
            receipts = reply_to_revenue.load_receipts(receipts_dir)
            return reply_to_revenue.build_funnel(
                receipts=receipts,
                observations=observations,
            )
    except (OSError, reply_to_revenue.ReplyRevenueError) as error:
        raise HumanOutcomeAuthorityError(
            f"canonical reply compiler rejected captured source evidence: {error}"
        ) from error


def _assert_generation_stable(captured: list[dict[str, Any]]) -> None:
    """Fail if membership or bytes moved while the captured generation compiled."""
    current_paths = source_paths()
    expected_paths = [row["path"] for row in captured]
    if current_paths != expected_paths:
        raise HumanOutcomeAuthorityError("canonical reply source membership changed during compile")
    for row in captured:
        try:
            current = row["path"].read_bytes()
        except OSError as error:
            raise HumanOutcomeAuthorityError(
                f"canonical reply source disappeared during compile: {row['relative']}"
            ) from error
        if _normalized_sha256(current) != row["sha256"]:
            raise HumanOutcomeAuthorityError(
                f"canonical reply source changed during compile: {row['relative']}"
            )


def derive_human_truth(
    catalog_truth: dict[str, Any],
    *,
    funnel: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconcile catalog assertions against one already-compiled canonical funnel.

    Supplying ``funnel`` is the production-safe primitive. The fallback direct
    compiler exists for source-compatible tests/tools; the right-now control uses
    :func:`capture_human_truth` so its semantics and receipt hashes share one read.
    """
    if not isinstance(catalog_truth, dict):
        raise HumanOutcomeAuthorityError("catalog truth must be an object")
    asserted_positive = _non_negative_integer(
        catalog_truth.get("verified_positive_replies"),
        "catalog truth.verified_positive_replies",
    )
    asserted_acceptances = _non_negative_integer(
        catalog_truth.get("accepted_scopes"),
        "catalog truth.accepted_scopes",
    )

    if funnel is None:
        try:
            funnel = reply_to_revenue.build_funnel()
        except reply_to_revenue.ReplyRevenueError as error:
            raise HumanOutcomeAuthorityError(
                f"canonical reply compiler rejected its source evidence: {error}"
            ) from error
    if not isinstance(funnel, dict):
        raise HumanOutcomeAuthorityError("compiled reply funnel must be an object")
    if funnel.get("kind") != EXPECTED_KIND:
        raise HumanOutcomeAuthorityError("compiled reply funnel kind is unsupported")
    measured_at = funnel.get("measured_at")
    if not isinstance(measured_at, str) or not measured_at.strip():
        raise HumanOutcomeAuthorityError(
            "compiled reply funnel measured_at must be non-empty"
        )
    truth = funnel.get("truth")
    if not isinstance(truth, dict):
        raise HumanOutcomeAuthorityError("compiled reply funnel truth must be an object")
    positive = _non_negative_integer(
        truth.get("human_positive"), "reply truth.human_positive"
    )
    acceptances = _non_negative_integer(
        truth.get("scope_acceptances"), "reply truth.scope_acceptances"
    )

    if asserted_positive != positive:
        raise HumanOutcomeAuthorityError(
            "catalog verified_positive_replies differs from compiled human-positive truth"
        )
    if asserted_acceptances != acceptances:
        raise HumanOutcomeAuthorityError(
            "catalog accepted_scopes differs from compiled scope-acceptance truth"
        )

    return {
        "as_of": measured_at,
        "authority": "REPLY_TO_REVENUE_COMPILED_PUBLIC_EVIDENCE",
        "verified_positive_replies": positive,
        "accepted_scopes": acceptances,
    }


def capture_human_truth(catalog_truth: dict[str, Any]) -> dict[str, Any]:
    """Return human truth plus hashes from one stable canonical source generation."""
    captured = _capture_source_generation()
    funnel = _compile_captured_funnel(captured)
    result = derive_human_truth(catalog_truth, funnel=funnel)
    _assert_generation_stable(captured)
    result["source_receipts"] = [
        {"path": row["relative"], "sha256": row["sha256"]}
        for row in captured
    ]
    return result
