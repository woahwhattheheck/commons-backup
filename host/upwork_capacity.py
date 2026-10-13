#!/usr/bin/env python3
"""Compile a public-safe Upwork account observation into a routing decision.

This module never signs in, completes a profile, submits a proposal, or treats an
email-verification receipt as buyer activity.  It keeps account reachability,
profile state, send authority, no-resend state, and commercial outcomes separate.
"""

from __future__ import annotations

import argparse
import json


PROFILE_STATES = {"UNKNOWN", "INCOMPLETE", "COMPLETE"}
FORBIDDEN_KEYS = {
    "account_id",
    "cookie",
    "credential",
    "email",
    "legal_name",
    "password",
    "recovery_link",
    "token",
}


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key).lower()
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def compile_state(observation):
    """Return a deterministic, non-submitting account-capacity decision."""
    if not isinstance(observation, dict):
        raise ValueError("observation must be an object")
    leaked = sorted(set(_keys(observation)) & FORBIDDEN_KEYS)
    if leaked:
        raise ValueError("private account fields are forbidden: " + ", ".join(leaked))

    verified = observation.get("email_verified")
    profile = observation.get("profile_state")
    proposal_receipts = observation.get("proposal_receipts")
    ready_unsent = observation.get("ready_unsent_records")
    if not isinstance(verified, bool):
        raise ValueError("email_verified must be boolean")
    if profile not in PROFILE_STATES:
        raise ValueError("profile_state must be UNKNOWN, INCOMPLETE, or COMPLETE")
    if not isinstance(proposal_receipts, int) or proposal_receipts < 0:
        raise ValueError("proposal_receipts must be a nonnegative integer")
    if not isinstance(ready_unsent, int) or ready_unsent < 0:
        raise ValueError("ready_unsent_records must be a nonnegative integer")

    if not verified:
        stage = "AVAILABLE"
        route = "EMAIL_VERIFICATION_REQUIRED"
    elif profile != "COMPLETE":
        stage = "REACHABLE"
        route = "OWNER_PROFILE_STATE_REQUIRED"
    elif ready_unsent:
        stage = "ASSIGNED"
        route = "PROPOSAL_PREFLIGHT_READY"
    else:
        stage = "REACHABLE"
        route = "NO_READY_UNSENT_RECORD"

    return {
        "resource": "upwork-marketplace-account",
        "capacity": "LIVE" if verified else "NOT_VERIFIED",
        "stage": stage,
        "condition": "CONSTRAINED",
        "route": route,
        "email_verified": verified,
        "profile_state": profile,
        "ready_unsent_records": ready_unsent,
        "proposal_receipts": proposal_receipts,
        "proposal_send_authorized": False,
        "owner_identity_action_required": profile != "COMPLETE",
        "buyer_acceptance": False,
        "payment": False,
        "revenue_usd": 0,
    }


def current_observation():
    return {
        "email_verified": True,
        "profile_state": "UNKNOWN",
        "ready_unsent_records": 2,
        "proposal_receipts": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    result = compile_state(current_observation())
    if args.self_test:
        assert result["stage"] == "REACHABLE"
        assert result["route"] == "OWNER_PROFILE_STATE_REQUIRED"
        assert result["proposal_receipts"] == 0
        assert not result["proposal_send_authorized"]
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
