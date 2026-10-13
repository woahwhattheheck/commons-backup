#!/usr/bin/env python3
"""Fail-closed creative-review state derivation."""
from __future__ import annotations

from typing import Any

from _events import _verify_event_chain
from _validation import (
    ANNOTATION_CATEGORIES,
    AUTHORITY,
    DECISIONS,
    MAX_ARRAY,
    MAX_ASSET_BYTES,
    SCHEMA,
    SHA_RE,
    InvalidInput,
    _exact_dict,
    _id,
    _metadata_matches,
    _positive_int,
    _text,
    normalize_location,
    normalize_metadata,
    normalize_spec,
    sha256_json,
)


def _derive(manifest_without_derived: dict[str, Any]) -> dict[str, Any]:
    required = {"schema", "campaign", "events", "assets"}
    if type(manifest_without_derived) is not dict or set(manifest_without_derived) != required:
        raise InvalidInput("manifest projection has unexpected keys")
    if manifest_without_derived["schema"] != SCHEMA:
        raise InvalidInput("unsupported manifest schema")
    campaign = manifest_without_derived["campaign"]
    campaign = _exact_dict(
        campaign,
        {"campaign_id", "name", "revision", "spec_sha256", "spec"},
        "manifest campaign",
    )
    spec = normalize_spec(campaign["spec"])
    if spec["campaign_id"] != campaign["campaign_id"]:
        raise InvalidInput("campaign/spec identity mismatch")
    if campaign["name"] != spec["name"]:
        raise InvalidInput("campaign/spec name mismatch")
    if type(campaign["revision"]) is not int or campaign["revision"] < 1:
        raise InvalidInput("invalid campaign revision")
    if campaign["spec_sha256"] != sha256_json(spec):
        raise InvalidInput("campaign spec digest mismatch")
    events = manifest_without_derived["events"]
    if type(events) is not list or len(events) > 100_000:
        raise InvalidInput("invalid event list")
    audit_ok, audit_reason = _verify_event_chain(campaign["campaign_id"], events)
    event_by_ordinal = {
        event.get("ordinal"): event
        for event in events
        if type(event) is dict and type(event.get("ordinal")) is int
    }

    def has_event(kind: str, expected: dict[str, Any]) -> bool:
        return any(
            type(event) is dict
            and event.get("event_kind") == kind
            and type(event.get("payload")) is dict
            and all(event["payload"].get(key) == value for key, value in expected.items())
            for event in events
        )

    def latest_event(kind: str, key: dict[str, Any]) -> dict[str, Any] | None:
        """Return the latest event of ``kind`` for one semantic state key."""
        for event in reversed(events):
            if type(event) is not dict or event.get("event_kind") != kind:
                continue
            payload = event.get("payload")
            if type(payload) is dict and all(payload.get(name) == value for name, value in key.items()):
                return event
        return None

    assets_raw = manifest_without_derived["assets"]
    if type(assets_raw) is not list:
        raise InvalidInput("manifest assets must be an array")
    by_id: dict[str, dict[str, Any]] = {}
    for item in assets_raw:
        item = _exact_dict(
            item,
            {"asset_id", "current_version", "assignments", "annotations", "dispositions"},
            "manifest asset",
        )
        asset_id = _id("manifest asset_id", item["asset_id"])
        if asset_id in by_id:
            raise InvalidInput("duplicate manifest asset")
        by_id[asset_id] = item
    asset_results: list[dict[str, Any]] = []
    campaign_holds: list[str] = []
    has_changes = False
    has_review = False
    if not audit_ok:
        campaign_holds.append(audit_reason or "AUDIT_INVALID")
    expected_campaign_kind = "CAMPAIGN_CREATED" if campaign["revision"] == 1 else "CAMPAIGN_REQUIREMENTS_REVISED"
    latest_campaign_event = next(
        (
            event
            for event in reversed(events)
            if type(event) is dict
            and event.get("event_kind") in {"CAMPAIGN_CREATED", "CAMPAIGN_REQUIREMENTS_REVISED"}
        ),
        None,
    )
    expected_campaign_payload = {"revision": campaign["revision"], "spec_sha256": campaign["spec_sha256"]}
    if (
        type(latest_campaign_event) is not dict
        or latest_campaign_event.get("event_kind") != expected_campaign_kind
        or type(latest_campaign_event.get("payload")) is not dict
        or not all(
            latest_campaign_event["payload"].get(key) == value
            for key, value in expected_campaign_payload.items()
        )
    ):
        campaign_holds.append("CAMPAIGN_STATE_NOT_LATEST_AUDIT")
    for requirement in spec["assets"]:
        asset_id = requirement["asset_id"]
        item = by_id.get(asset_id)
        holds: list[str] = []
        changes: list[str] = []
        review: list[str] = []
        version = None if item is None else item.get("current_version")
        assignments = [] if item is None else item.get("assignments")
        annotations = [] if item is None else item.get("annotations")
        dispositions = [] if item is None else item.get("dispositions")
        for label, collection in (
            ("assignments", assignments),
            ("annotations", annotations),
            ("dispositions", dispositions),
        ):
            if type(collection) is not list or len(collection) > MAX_ARRAY:
                raise InvalidInput(f"invalid {label} collection for {asset_id}")
        if version is None:
            holds.append("MISSING_CURRENT_VERSION")
        else:
            version = _exact_dict(
                version,
                {
                    "version",
                    "content_sha256",
                    "content_size",
                    "file_name",
                    "media_type",
                    "metadata",
                    "provenance_ref",
                    "author_id",
                    "created_at",
                },
                f"current version {asset_id}",
            )
            if type(version["version"]) is not int or version["version"] < 1:
                holds.append("INVALID_VERSION")
            if type(version["content_sha256"]) is not str or not SHA_RE.fullmatch(version["content_sha256"]):
                holds.append("INVALID_CONTENT_DIGEST")
            if type(version["content_size"]) is not int or version["content_size"] < 0 or version["content_size"] > MAX_ASSET_BYTES:
                holds.append("INVALID_CONTENT_SIZE")
            try:
                _text("file_name", version["file_name"], maximum=255)
                _text("provenance_ref", version["provenance_ref"], maximum=512)
                _id("author_id", version["author_id"])
                _text("created_at", version["created_at"], maximum=64)
            except InvalidInput:
                holds.append("INVALID_VERSION_METADATA")
            if version["media_type"] != requirement["media_type"]:
                holds.append("MEDIA_TYPE_MISMATCH")
            metadata = normalize_metadata(version["metadata"])
            holds.extend(_metadata_matches(metadata, requirement["constraints"]))
            expected_version_payload = {
                "asset_id": asset_id,
                "version": version["version"],
                "content_sha256": version["content_sha256"],
                "content_size": version["content_size"],
                "file_name": version["file_name"],
                "media_type": version["media_type"],
                "metadata": metadata,
                "provenance_ref": version["provenance_ref"],
                "author_id": version["author_id"],
            }
            latest_version_event = latest_event("ASSET_VERSION_SUBMITTED", {"asset_id": asset_id})
            if (
                type(latest_version_event) is not dict
                or latest_version_event.get("payload") != expected_version_payload
            ):
                holds.append("ASSET_STATE_NOT_LATEST_AUDIT")
            current_version = version["version"]
            revision = campaign["revision"]
            assignment_by_role: dict[str, str] = {}
            assignment_event_ordinal_by_role: dict[str, int] = {}
            for assignment in assignments:
                assignment = _exact_dict(
                    assignment,
                    {"campaign_revision", "asset_version", "role", "reviewer_id", "assigned_at"},
                    f"assignment {asset_id}",
                )
                if assignment["campaign_revision"] != revision or assignment["asset_version"] != current_version:
                    holds.append("STALE_ASSIGNMENT_INCLUDED")
                    continue
                try:
                    role = _id("assignment role", assignment["role"])
                    reviewer = _id("assignment reviewer_id", assignment["reviewer_id"])
                    _text("assignment assigned_at", assignment["assigned_at"], maximum=64)
                except InvalidInput:
                    holds.append("INVALID_ASSIGNMENT_FIELDS")
                    continue
                if role not in requirement["required_roles"]:
                    holds.append("UNREQUIRED_ROLE_ASSIGNMENT")
                    continue
                if role in assignment_by_role:
                    holds.append("DUPLICATE_ROLE_ASSIGNMENT")
                    continue
                if spec["policy"]["prohibit_author_review"] and reviewer == version["author_id"]:
                    holds.append("AUTHOR_ASSIGNED_AS_REVIEWER")
                assignment_key = {
                    "asset_id": asset_id,
                    "campaign_revision": revision,
                    "asset_version": current_version,
                    "role": role,
                }
                latest_assignment_event = latest_event("REVIEWER_ASSIGNED", assignment_key)
                expected_assignment_payload = {**assignment_key, "reviewer_id": reviewer}
                if (
                    type(latest_assignment_event) is not dict
                    or latest_assignment_event.get("payload") != expected_assignment_payload
                ):
                    holds.append(f"ASSIGNMENT_NOT_LATEST_AUDIT:{role}")
                else:
                    assignment_event_ordinal_by_role[role] = latest_assignment_event["ordinal"]
                assignment_by_role[role] = reviewer
            if spec["policy"]["require_distinct_reviewers"]:
                reviewers = list(assignment_by_role.values())
                if len(reviewers) != len(set(reviewers)):
                    holds.append("REVIEWER_ROLE_COLLISION")
            for role in requirement["required_roles"]:
                if role not in assignment_by_role:
                    review.append(f"MISSING_ASSIGNMENT:{role}")
            open_annotations: list[str] = []
            for annotation in annotations:
                annotation = _exact_dict(
                    annotation,
                    {
                        "annotation_id",
                        "campaign_revision",
                        "asset_version",
                        "role",
                        "reviewer_id",
                        "location",
                        "category",
                        "note",
                        "status",
                        "created_at",
                        "resolved_at",
                        "resolved_by",
                    },
                    f"annotation {asset_id}",
                )
                if annotation["campaign_revision"] != revision or annotation["asset_version"] != current_version:
                    holds.append("STALE_ANNOTATION_INCLUDED")
                    continue
                try:
                    annotation_id = _id("annotation_id", annotation["annotation_id"])
                    annotation_role = _id("annotation role", annotation["role"])
                    annotation_reviewer = _id("annotation reviewer_id", annotation["reviewer_id"])
                    if annotation["category"] not in ANNOTATION_CATEGORIES:
                        raise InvalidInput("invalid annotation category")
                    _text("annotation note", annotation["note"])
                    normalized_location = normalize_location(annotation["location"], version["media_type"], metadata)
                    if normalized_location != annotation["location"]:
                        raise InvalidInput("annotation location is not canonical")
                except InvalidInput:
                    holds.append("INVALID_ANNOTATION_FIELDS")
                    continue
                assigned = assignment_by_role.get(annotation_role) == annotation_reviewer
                if not has_event(
                    "ANNOTATION_OPENED",
                    {
                        "annotation_id": annotation_id,
                        "asset_id": asset_id,
                        "campaign_revision": revision,
                        "asset_version": current_version,
                        "role": annotation_role,
                        "reviewer_id": annotation_reviewer,
                        "location": annotation["location"],
                        "category": annotation["category"],
                        "note": annotation["note"],
                    },
                ):
                    holds.append(f"ANNOTATION_NOT_AUDIT_BOUND:{annotation_id}")
                latest_resolution_event = latest_event("ANNOTATION_RESOLVED", {"annotation_id": annotation_id})
                if annotation["status"] == "OPEN":
                    if annotation["resolved_at"] is not None or annotation["resolved_by"] is not None:
                        holds.append("OPEN_ANNOTATION_HAS_RESOLUTION")
                    if latest_resolution_event is not None:
                        holds.append("OPEN_ANNOTATION_HAS_AUDIT_RESOLUTION")
                    if not assigned:
                        holds.append("UNASSIGNED_OPEN_ANNOTATION")
                    open_annotations.append(annotation_id)
                elif annotation["status"] == "RESOLVED":
                    try:
                        _text("resolved_at", annotation["resolved_at"], maximum=64)
                        resolver = _id("resolved_by", annotation["resolved_by"])
                    except InvalidInput:
                        holds.append("INVALID_ANNOTATION_RESOLUTION")
                        continue
                    expected_resolution_payload = {
                        "annotation_id": annotation_id,
                        "asset_id": asset_id,
                        "resolver_id": resolver,
                    }
                    if (
                        type(latest_resolution_event) is not dict
                        or latest_resolution_event.get("payload") != expected_resolution_payload
                    ):
                        holds.append(f"RESOLUTION_NOT_AUDIT_BOUND:{annotation_id}")
                else:
                    holds.append("INVALID_ANNOTATION_STATUS")
            if open_annotations:
                changes.extend(f"OPEN_ANNOTATION:{annotation_id}" for annotation_id in sorted(open_annotations))
            disposition_by_role: dict[str, dict[str, Any]] = {}
            for disposition in dispositions:
                disposition = _exact_dict(
                    disposition,
                    {
                        "campaign_revision",
                        "asset_version",
                        "role",
                        "reviewer_id",
                        "decision",
                        "note",
                        "event_ordinal",
                        "decided_at",
                    },
                    f"disposition {asset_id}",
                )
                if disposition["campaign_revision"] != revision or disposition["asset_version"] != current_version:
                    holds.append("STALE_DISPOSITION_INCLUDED")
                    continue
                try:
                    role = _id("disposition role", disposition["role"])
                    disposition_reviewer = _id("disposition reviewer_id", disposition["reviewer_id"])
                    if disposition["decision"] not in DECISIONS:
                        raise InvalidInput("invalid disposition decision")
                    _text("disposition note", disposition["note"], empty=True)
                    _positive_int("disposition event_ordinal", disposition["event_ordinal"])
                    _text("disposition decided_at", disposition["decided_at"], maximum=64)
                except InvalidInput:
                    holds.append("INVALID_DISPOSITION_FIELDS")
                    continue
                if assignment_by_role.get(role) != disposition_reviewer:
                    holds.append("UNASSIGNED_DISPOSITION")
                    continue
                disposition_key = {
                    "asset_id": asset_id,
                    "campaign_revision": revision,
                    "asset_version": current_version,
                    "role": role,
                }
                expected_payload = {
                    **disposition_key,
                    "reviewer_id": disposition_reviewer,
                    "decision": disposition["decision"],
                    "note": disposition["note"],
                }
                event = event_by_ordinal.get(disposition["event_ordinal"])
                latest_disposition_event = latest_event("REVIEW_DISPOSITION_RECORDED", disposition_key)
                assignment_ordinal = assignment_event_ordinal_by_role.get(role)
                if (
                    type(event) is not dict
                    or event.get("event_kind") != "REVIEW_DISPOSITION_RECORDED"
                    or event.get("payload") != expected_payload
                ):
                    holds.append(f"DISPOSITION_NOT_AUDIT_BOUND:{role}")
                if (
                    type(latest_disposition_event) is not dict
                    or latest_disposition_event.get("ordinal") != disposition["event_ordinal"]
                    or latest_disposition_event.get("payload") != expected_payload
                    or type(assignment_ordinal) is not int
                    or disposition["event_ordinal"] <= assignment_ordinal
                ):
                    holds.append(f"DISPOSITION_NOT_LATEST_AUDIT:{role}")
                disposition_by_role[role] = disposition
                if disposition["decision"] == "CHANGES_REQUESTED":
                    changes.append(f"CHANGES_REQUESTED:{role}")
            for role in requirement["required_roles"]:
                disposition = disposition_by_role.get(role)
                if disposition is None or disposition["decision"] != "APPROVE":
                    if not any(reason == f"CHANGES_REQUESTED:{role}" for reason in changes):
                        review.append(f"MISSING_APPROVAL:{role}")
        holds = sorted(set(holds))
        changes = sorted(set(changes))
        review = sorted(set(review))
        if holds:
            state = "HOLD"
            campaign_holds.extend(f"{asset_id}:{reason}" for reason in holds)
        elif changes:
            state = "CHANGES_REQUESTED"
            has_changes = True
        elif review:
            state = "REVIEW_REQUIRED"
            has_review = True
        else:
            state = "READY_FOR_OWNER_HANDOFF"
        asset_results.append(
            {
                "asset_id": asset_id,
                "state": state,
                "holds": holds,
                "changes": changes,
                "review": review,
                "current_sha256": None if version is None else version["content_sha256"],
                "current_version": None if version is None else version["version"],
                "destinations": requirement["destinations"],
                "required_roles": requirement["required_roles"],
            }
        )
    extras = sorted(set(by_id) - {asset["asset_id"] for asset in spec["assets"]})
    if extras:
        campaign_holds.extend(f"UNEXPECTED_ASSET:{asset_id}" for asset_id in extras)
    campaign_holds = sorted(set(campaign_holds))
    if campaign_holds:
        campaign_state = "HOLD"
    elif has_changes:
        campaign_state = "CHANGES_REQUESTED"
    elif has_review:
        campaign_state = "REVIEW_REQUIRED"
    else:
        campaign_state = "READY_FOR_OWNER_HANDOFF"
    return {
        "campaign_state": campaign_state,
        "campaign_holds": campaign_holds,
        "assets": asset_results,
        "authority": dict(AUTHORITY),
    }
