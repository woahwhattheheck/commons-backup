"""Classify GitHub write failures into narrow retry and circuit scopes.

This module is network-free and stateless. It sits above the content-write
pacemaker so callers can distinguish provider-wide quota from route-local
rejections before deciding which delivery rail may continue. The planner never
stores credentials, request bodies, or provider error text.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import sys
from typing import Any


@dataclass(frozen=True)
class FailurePlan:
    classification: str
    circuit_scope: dict[str, str]
    provider_effect: str
    readback_required: bool
    retry_guidance: str
    alternate_rail_guidance: str
    pacemaker_v2_guidance: str
    retry_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        return {
            "classification": value["classification"],
            "circuitScope": value["circuit_scope"],
            "providerEffect": value["provider_effect"],
            "readbackRequired": value["readback_required"],
            "retryGuidance": value["retry_guidance"],
            "alternateRailGuidance": value["alternate_rail_guidance"],
            "pacemakerV2Guidance": value["pacemaker_v2_guidance"],
            "retryAt": value["retry_at"],
        }


def _label(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    value = value.strip()
    if (
        not value
        or len(value.encode("utf-8")) > 96
        or "\0" in value
        or "\n" in value
        or "\r" in value
    ):
        raise ValueError(f"{name} must be a single non-empty label up to 96 bytes")
    return value


def _scope(level: str, rail: str, operation_class: str) -> dict[str, str]:
    result = {"level": level, "rail": rail}
    if level != "rail":
        result["operationClass"] = operation_class
    return result


def plan_write_failure(
    *,
    rail: str,
    operation_class: str,
    provider_status: int | None = None,
    message: str = "",
    pre_provider: bool = False,
    retry_at: str | None = None,
) -> FailurePlan:
    """Return a conservative delivery plan for one observed write failure."""
    rail = _label("rail", rail)
    operation_class = _label("operation_class", operation_class)
    if provider_status is not None and (
        isinstance(provider_status, bool)
        or not isinstance(provider_status, int)
        or provider_status < 100
        or provider_status > 599
    ):
        raise ValueError("provider_status must be an HTTP status from 100 through 599")
    if not isinstance(message, str) or len(message.encode("utf-8")) > 16384:
        raise ValueError("message must be text up to 16384 bytes")
    if retry_at is not None and (
        not isinstance(retry_at, str)
        or not retry_at
        or len(retry_at.encode("utf-8")) > 128
    ):
        raise ValueError("retry_at must be non-empty text up to 128 bytes")

    folded = " ".join(message.casefold().split())

    if pre_provider or any(marker in folded for marker in (
        "pre-provider",
        "blocked before provider",
        "safety check",
    )):
        return FailurePlan(
            "pre_provider_block",
            _scope("mutation", rail, operation_class),
            "none",
            False,
            "return_to_caller_without_provider_retry",
            "do_not_reroute_the_same_blocked_operation",
            "no_provider_result_to_record",
            retry_at,
        )

    if provider_status == 401 or any(marker in folded for marker in (
        "bad credentials",
        "requires authentication",
        "authentication failed",
    )):
        return FailurePlan(
            "authentication_failure",
            _scope("rail", rail, operation_class),
            "rejected",
            False,
            "retry_only_after_the_rail_is_reauthenticated",
            "other_already_authorized_rails_remain_independent",
            "record_rejected_on_the_failed_rail",
            retry_at,
        )

    if any(marker in folded for marker in (
        "resource not accessible by integration",
        "insufficient permissions for integration",
    )):
        return FailurePlan(
            "integration_scope_denied",
            _scope("operation", rail, operation_class),
            "rejected",
            False,
            "retry_only_after_route_or_integration_scope_changes",
            "unaffected_already_authorized_rails_may_continue",
            "do_not_convert_this_route_local_403_into_a_global_cooldown",
            retry_at,
        )

    if any(marker in folded for marker in (
        "api rate limit exceeded",
        "rate limit exceeded for user",
        "primary rate limit",
    )):
        return FailurePlan(
            "primary_quota_exhausted",
            _scope("rail", rail, operation_class),
            "rejected",
            False,
            "wait_for_the_reported_reset_or_retry_deadline",
            "other_credential_or_app_rails_remain_independent",
            "global_cooldown_is_safe_only_for_a_single_rail_store",
            retry_at,
        )

    if any(marker in folded for marker in (
        "secondary rate limit",
        "secondary-rate-limit",
        "abuse detection",
    )) or provider_status == 429:
        return FailurePlan(
            "secondary_provider_throttle",
            _scope("operation", rail, operation_class),
            "rejected",
            False,
            "back_off_only_the_affected_rail_and_operation_family",
            "unaffected_already_authorized_rails_may_continue",
            "do_not_globalize_this_route_local_throttle_in_a_mixed_rail_store",
            retry_at,
        )

    if any(marker in folded for marker in (
        "submitted too quickly",
        "submission was too quick",
        "action throttle",
    )):
        return FailurePlan(
            "action_throttle",
            _scope("operation", rail, operation_class),
            "rejected",
            False,
            "defer_this_operation_family_before_another_attempt",
            "unaffected_already_authorized_rails_may_continue",
            "do_not_globalize_this_action_throttle_in_a_mixed_rail_store",
            retry_at,
        )

    if (
        (provider_status is not None and provider_status >= 500)
        or any(marker in folded for marker in (
            "timed out",
            "timeout",
            "connection reset",
            "broken pipe",
            "connection closed",
            "gateway timeout",
        ))
    ):
        return FailurePlan(
            "ambiguous_transport",
            _scope("mutation", rail, operation_class),
            "unknown",
            True,
            "read_back_the_exact_provider_effect_before_any_retry",
            "do_not_reroute_until_readback_resolves_the_effect",
            "record_ambiguous_then_reconcile_from_provider_readback",
            retry_at,
        )

    return FailurePlan(
        "provider_rejected",
        _scope("mutation", rail, operation_class),
        "rejected",
        False,
        "retry_only_after_the_request_or_provider_condition_changes",
        "an_alternate_rail_does_not_change_request_semantics",
        "record_rejected",
        retry_at,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify one GitHub write failure without provider I/O."
    )
    parser.add_argument("--rail", required=True)
    parser.add_argument("--operation-class", required=True)
    parser.add_argument("--provider-status", type=int)
    parser.add_argument("--message", default="")
    parser.add_argument("--pre-provider", action="store_true")
    parser.add_argument("--retry-at")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        plan = plan_write_failure(
            rail=args.rail,
            operation_class=args.operation_class,
            provider_status=args.provider_status,
            message=args.message,
            pre_provider=args.pre_provider,
            retry_at=args.retry_at,
        )
    except ValueError as exc:
        print(
            json.dumps({"error": "invalid_input", "message": str(exc)}, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(plan.as_dict(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
