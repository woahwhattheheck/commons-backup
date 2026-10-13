#!/usr/bin/env python3
"""Fail-closed CUHK-X Large Model Track readiness checker.

This utility records evidence; it cannot perform website/Kaggle actions or grant
competition authority. Exit 0 means only that the committed receipts satisfy the
requested local gate. It never means a prize, award, or organizer acceptance.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

STATE = Path(__file__).with_name("readiness.json")
STAGES = ("entry-ready", "submission-complete", "verification-ready")


class InvalidState(ValueError):
    pass


def _reject_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise InvalidState(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def _require_bool(obj: dict[str, Any], key: str, label: str) -> bool:
    if key not in obj or type(obj[key]) is not bool:
        raise InvalidState(f"{label}.{key} must be boolean")
    return obj[key]


def _receipt_present(receipts: dict[str, Any], key: str) -> bool:
    value = receipts.get(key)
    return isinstance(value, str) and bool(value.strip())


def _entry_gate_complete(state: dict[str, Any]) -> bool:
    gates, team = state["gates"], state["team"]
    return all(
        (
            gates["official_site_registered"],
            gates["kaggle_large_model_track_joined"],
            gates["kaggle_rules_accepted"],
            gates["cuhkx_data_use_terms_accepted"],
            team["team_name_match_verified"],
        )
    )


def _entry_evidenced(state: dict[str, Any]) -> bool:
    receipts = state["receipts"]
    return (
        _entry_gate_complete(state)
        and _receipt_present(receipts, "official_site_registration")
        and _receipt_present(receipts, "kaggle_join_and_terms")
    )


def _submission_evidenced(state: dict[str, Any]) -> bool:
    gates, receipts, authority = state["gates"], state["receipts"], state["authority"]
    return (
        _entry_evidenced(state)
        and gates["dataset_accessed_from_official_mirror"]
        and _receipt_present(receipts, "dataset_access")
        and gates["valid_submission_made"]
        and _receipt_present(receipts, "submission")
        and authority["dataset_access_claimed"]
        and authority["submission_claimed"]
    )


def load_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_object,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidState(f"cannot load readiness state: {exc}") from exc
    if not isinstance(payload, dict):
        raise InvalidState("readiness state must be an object")
    schema = payload.get("schema_version")
    if type(schema) is not int or schema != 1:
        raise InvalidState("schema_version must be integer 1")
    if type(payload.get("track_prize_pool_usd")) is not int or payload["track_prize_pool_usd"] != 10000:
        raise InvalidState("track_prize_pool_usd must be integer 10000")

    team = payload.get("team")
    auth = payload.get("organizer_authorization")
    gates = payload.get("gates")
    receipts = payload.get("receipts")
    conflict = payload.get("verification_deadline_conflict")
    authority = payload.get("authority")
    if not all(isinstance(v, dict) for v in (team, auth, gates, receipts, conflict, authority)):
        raise InvalidState("team/authorization/gates/receipts/deadline/authority must be objects")

    if auth.get("sender") != "cuhkx.competition@gmail.com" or auth.get("written_permission_received") is not True:
        raise InvalidState("organizer written-permission evidence must remain bound")
    if auth.get("effective_prerequisites") != [
        "official_site_registered",
        "kaggle_rules_accepted",
        "cuhkx_data_use_terms_accepted",
    ]:
        raise InvalidState("organizer authorization prerequisites changed")
    for key in ("no_redistribution", "no_test_ground_truth_use", "no_manual_test_labeling"):
        if auth.get(key) is not True:
            raise InvalidState(f"organizer_authorization.{key} must remain true")

    for key in (
        "official_site_registered", "kaggle_large_model_track_joined",
        "kaggle_rules_accepted", "cuhkx_data_use_terms_accepted",
        "dataset_accessed_from_official_mirror", "valid_submission_made",
        "final_submission_selected", "top15_notified",
        "verification_deadline_rechecked_after_top15",
    ):
        _require_bool(gates, key, "gates")
    match_verified = _require_bool(team, "team_name_match_verified", "team")
    for key in ("dataset_access_claimed", "submission_ready", "submission_claimed", "prize_or_award_claimed"):
        _require_bool(authority, key, "authority")

    if match_verified:
        official_name = team.get("official_site_team_name")
        kaggle_name = team.get("kaggle_team_name")
        if not isinstance(official_name, str) or not official_name.strip():
            raise InvalidState("team-name match claim requires official_site_team_name")
        if not isinstance(kaggle_name, str) or not kaggle_name.strip():
            raise InvalidState("team-name match claim requires kaggle_team_name")
        if official_name != official_name.strip() or kaggle_name != kaggle_name.strip():
            raise InvalidState("team names must be trimmed exact values")
        if official_name != kaggle_name:
            raise InvalidState("team_name_match_verified contradicts actual team names")

    if gates["dataset_accessed_from_official_mirror"] and not _entry_gate_complete(payload):
        raise InvalidState(
            "official-mirror dataset access requires completed registration/rules/join/team-name gates"
        )
    if gates["valid_submission_made"] and not gates["dataset_accessed_from_official_mirror"]:
        raise InvalidState("valid submission requires prior official-mirror dataset access")
    if gates["final_submission_selected"] and not gates["valid_submission_made"]:
        raise InvalidState("final submission selection requires a valid submission")

    if authority["prize_or_award_claimed"]:
        raise InvalidState("this packet is not permitted to claim a prize or award")
    if authority["dataset_access_claimed"] and not gates["dataset_accessed_from_official_mirror"]:
        raise InvalidState("dataset access claim lacks official-mirror access gate")
    if authority["submission_claimed"] and not gates["valid_submission_made"]:
        raise InvalidState("submission claim lacks valid-submission gate")

    derived_submission_ready = _submission_evidenced(payload)
    if authority["submission_ready"] != derived_submission_ready:
        raise InvalidState(
            "authority.submission_ready must equal mechanically evidenced submission readiness"
        )
    if gates["final_submission_selected"] and not derived_submission_ready:
        raise InvalidState("final submission selection requires evidenced submission readiness")

    if gates["top15_notified"]:
        if not derived_submission_ready:
            raise InvalidState("Top-15 notification requires evidenced submission readiness")
        if not _receipt_present(receipts, "top15_notification"):
            raise InvalidState("Top-15 notification requires a receipt")
    if gates["verification_deadline_rechecked_after_top15"]:
        if not derived_submission_ready:
            raise InvalidState("verification deadline recheck requires evidenced submission readiness")
        if not gates["top15_notified"] or not _receipt_present(receipts, "verification_deadline_recheck"):
            raise InvalidState("verification deadline recheck requires Top-15 plus receipt")
        if not isinstance(conflict.get("controlling_deadline"), str) or not conflict["controlling_deadline"].strip():
            raise InvalidState("controlling verification deadline must be recorded after recheck")
    return payload


def evaluate(state: dict[str, Any], stage: str) -> tuple[bool, list[str]]:
    team, gates, receipts, authority = (
        state["team"], state["gates"], state["receipts"], state["authority"]
    )
    missing: list[str] = []

    entry_checks = (
        (gates["official_site_registered"], "official_site_registered"),
        (gates["kaggle_large_model_track_joined"], "kaggle_large_model_track_joined"),
        (gates["kaggle_rules_accepted"], "kaggle_rules_accepted"),
        (gates["cuhkx_data_use_terms_accepted"], "cuhkx_data_use_terms_accepted"),
        (team["team_name_match_verified"], "team_name_match_verified"),
        (_receipt_present(receipts, "official_site_registration"), "official_site_registration receipt"),
        (_receipt_present(receipts, "kaggle_join_and_terms"), "kaggle_join_and_terms receipt"),
    )
    missing.extend(label for ok, label in entry_checks if not ok)

    if stage in ("submission-complete", "verification-ready"):
        submission_checks = (
            (gates["dataset_accessed_from_official_mirror"], "dataset_accessed_from_official_mirror"),
            (_receipt_present(receipts, "dataset_access"), "dataset_access receipt"),
            (gates["valid_submission_made"], "valid_submission_made"),
            (_receipt_present(receipts, "submission"), "submission receipt"),
            (authority["dataset_access_claimed"], "dataset_access_claimed"),
            (authority["submission_claimed"], "submission_claimed"),
        )
        missing.extend(label for ok, label in submission_checks if not ok)

    if stage == "verification-ready":
        verification_checks = (
            (gates["top15_notified"], "top15_notified"),
            (_receipt_present(receipts, "top15_notification"), "top15_notification receipt"),
            (gates["verification_deadline_rechecked_after_top15"], "verification_deadline_rechecked_after_top15"),
            (_receipt_present(receipts, "verification_deadline_recheck"), "verification_deadline_recheck receipt"),
            (bool(state["verification_deadline_conflict"].get("controlling_deadline")), "controlling verification deadline"),
        )
        missing.extend(label for ok, label in verification_checks if not ok)

    return not missing, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=STATE)
    parser.add_argument("--stage", choices=STAGES, default="entry-ready")
    args = parser.parse_args(argv)
    try:
        state = load_state(args.state)
        ready, missing = evaluate(state, args.stage)
    except InvalidState as exc:
        print(json.dumps({"decision": "INVALID", "stage": args.stage, "ready": False, "error": str(exc)}, sort_keys=True))
        return 1
    decision = "READY_EVIDENCED" if ready else "BLOCKED_MISSING_EVIDENCE"
    print(json.dumps({"decision": decision, "stage": args.stage, "ready": ready, "missing": missing}, sort_keys=True))
    return 0 if ready else 2


if __name__ == "__main__":
    sys.exit(main())
