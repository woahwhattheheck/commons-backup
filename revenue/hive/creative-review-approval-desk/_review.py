#!/usr/bin/env python3
"""Reviewer assignment, annotation, resolution, and disposition mixin."""
from __future__ import annotations

import sqlite3
from typing import Any

from _validation import (
    ANNOTATION_CATEGORIES,
    DECISIONS,
    InvalidInput,
    InvalidState,
    _id,
    _text,
    canonical_json,
    normalize_location,
    strict_json_loads,
)


class ReviewWorkflowMixin:
    def assign_reviewer(
        self,
        request_id: str,
        campaign_id: str,
        asset_id: str,
        role: str,
        reviewer_id: str,
    ) -> dict[str, Any]:
        campaign_id = _id("campaign_id", campaign_id)
        asset_id = _id("asset_id", asset_id)
        role = _id("role", role)
        reviewer_id = _id("reviewer_id", reviewer_id)
        payload = {"campaign_id": campaign_id, "asset_id": asset_id, "role": role, "reviewer_id": reviewer_id}

        def apply(connection: sqlite3.Connection, at_utc: str) -> dict[str, Any]:
            campaign, spec = self._campaign(connection, campaign_id)
            requirement = self._requirement(spec, asset_id)
            if role not in requirement["required_roles"]:
                raise InvalidState("role is not required for this asset")
            version = self._current_version(connection, campaign_id, asset_id)
            if spec["policy"]["prohibit_author_review"] and reviewer_id == version["author_id"]:
                raise InvalidState("author cannot review own asset under current policy")
            if spec["policy"]["require_distinct_reviewers"]:
                collision = connection.execute(
                    "SELECT role FROM assignments WHERE campaign_id=? AND asset_id=? AND campaign_revision=? AND asset_version=? AND reviewer_id=? AND role<>?",
                    (campaign_id, asset_id, campaign["revision"], version["version"], reviewer_id, role),
                ).fetchone()
                if collision is not None:
                    raise InvalidState("current policy requires distinct reviewers for each role")
            prior = connection.execute(
                "SELECT reviewer_id FROM assignments WHERE campaign_id=? AND asset_id=? AND campaign_revision=? AND asset_version=? AND role=?",
                (campaign_id, asset_id, campaign["revision"], version["version"], role),
            ).fetchone()
            if prior is not None and prior["reviewer_id"] == reviewer_id:
                return {**payload, "campaign_revision": campaign["revision"], "asset_version": version["version"], "changed": False}
            connection.execute(
                "INSERT INTO assignments VALUES(?,?,?,?,?,?,?) ON CONFLICT(campaign_id,asset_id,campaign_revision,asset_version,role) DO UPDATE SET reviewer_id=excluded.reviewer_id,assigned_at=excluded.assigned_at",
                (campaign_id, asset_id, campaign["revision"], version["version"], role, reviewer_id, at_utc),
            )
            connection.execute(
                "DELETE FROM dispositions WHERE campaign_id=? AND asset_id=? AND campaign_revision=? AND asset_version=? AND role=?",
                (campaign_id, asset_id, campaign["revision"], version["version"], role),
            )
            self._append_event(
                connection,
                campaign_id,
                "REVIEWER_ASSIGNED",
                {
                    "asset_id": asset_id,
                    "campaign_revision": campaign["revision"],
                    "asset_version": version["version"],
                    "role": role,
                    "reviewer_id": reviewer_id,
                },
                at_utc,
            )
            return {**payload, "campaign_revision": campaign["revision"], "asset_version": version["version"], "changed": True}

        return self._mutate(request_id, "assign_reviewer", payload, apply)

    def add_annotation(
        self,
        request_id: str,
        annotation_id: str,
        campaign_id: str,
        asset_id: str,
        role: str,
        reviewer_id: str,
        location_value: Any,
        category: str,
        note: str,
    ) -> dict[str, Any]:
        annotation_id = _id("annotation_id", annotation_id)
        campaign_id = _id("campaign_id", campaign_id)
        asset_id = _id("asset_id", asset_id)
        role = _id("role", role)
        reviewer_id = _id("reviewer_id", reviewer_id)
        if type(category) is not str or category not in ANNOTATION_CATEGORIES:
            raise InvalidInput("invalid annotation category")
        note = _text("annotation note", note)
        payload_base = {
            "annotation_id": annotation_id,
            "campaign_id": campaign_id,
            "asset_id": asset_id,
            "role": role,
            "reviewer_id": reviewer_id,
            "category": category,
            "note": note,
        }

        def apply(connection: sqlite3.Connection, at_utc: str) -> dict[str, Any]:
            campaign, _ = self._campaign(connection, campaign_id)
            version = self._current_version(connection, campaign_id, asset_id)
            assignment = connection.execute(
                "SELECT reviewer_id FROM assignments WHERE campaign_id=? AND asset_id=? AND campaign_revision=? AND asset_version=? AND role=?",
                (campaign_id, asset_id, campaign["revision"], version["version"], role),
            ).fetchone()
            if assignment is None or assignment["reviewer_id"] != reviewer_id:
                raise InvalidState("annotation author is not the current assigned reviewer for this role")
            metadata = strict_json_loads(version["metadata_json"])
            location = normalize_location(location_value, version["media_type"], metadata)
            if connection.execute("SELECT 1 FROM annotations WHERE annotation_id=?", (annotation_id,)).fetchone():
                raise InvalidState(f"annotation_id already exists: {annotation_id}")
            connection.execute(
                "INSERT INTO annotations VALUES(?,?,?,?,?,?,?,?,?,?,'OPEN',?,NULL,NULL)",
                (
                    annotation_id,
                    campaign_id,
                    asset_id,
                    campaign["revision"],
                    version["version"],
                    role,
                    reviewer_id,
                    canonical_json(location),
                    category,
                    note,
                    at_utc,
                ),
            )
            self._append_event(
                connection,
                campaign_id,
                "ANNOTATION_OPENED",
                {
                    "annotation_id": annotation_id,
                    "asset_id": asset_id,
                    "campaign_revision": campaign["revision"],
                    "asset_version": version["version"],
                    "role": role,
                    "reviewer_id": reviewer_id,
                    "location": location,
                    "category": category,
                    "note": note,
                },
                at_utc,
            )
            return {
                **payload_base,
                "campaign_revision": campaign["revision"],
                "asset_version": version["version"],
                "location": location,
                "status": "OPEN",
            }

        payload = {**payload_base, "location": location_value}
        return self._mutate(request_id, "add_annotation", payload, apply)

    def resolve_annotation(
        self,
        request_id: str,
        campaign_id: str,
        annotation_id: str,
        resolver_id: str,
    ) -> dict[str, Any]:
        campaign_id = _id("campaign_id", campaign_id)
        annotation_id = _id("annotation_id", annotation_id)
        resolver_id = _id("resolver_id", resolver_id)
        payload = {"campaign_id": campaign_id, "annotation_id": annotation_id, "resolver_id": resolver_id}

        def apply(connection: sqlite3.Connection, at_utc: str) -> dict[str, Any]:
            self._campaign(connection, campaign_id)
            row = connection.execute(
                "SELECT * FROM annotations WHERE annotation_id=? AND campaign_id=?",
                (annotation_id, campaign_id),
            ).fetchone()
            if row is None:
                raise InvalidState("unknown annotation")
            if row["status"] == "RESOLVED":
                return {**payload, "status": "RESOLVED", "changed": False}
            connection.execute(
                "UPDATE annotations SET status='RESOLVED',resolved_at=?,resolved_by=? WHERE annotation_id=?",
                (at_utc, resolver_id, annotation_id),
            )
            self._append_event(
                connection,
                campaign_id,
                "ANNOTATION_RESOLVED",
                {"annotation_id": annotation_id, "asset_id": row["asset_id"], "resolver_id": resolver_id},
                at_utc,
            )
            return {**payload, "status": "RESOLVED", "changed": True}

        return self._mutate(request_id, "resolve_annotation", payload, apply)

    def decide(
        self,
        request_id: str,
        campaign_id: str,
        asset_id: str,
        role: str,
        reviewer_id: str,
        decision: str,
        note: str,
    ) -> dict[str, Any]:
        campaign_id = _id("campaign_id", campaign_id)
        asset_id = _id("asset_id", asset_id)
        role = _id("role", role)
        reviewer_id = _id("reviewer_id", reviewer_id)
        if type(decision) is not str or decision not in DECISIONS:
            raise InvalidInput("invalid review decision")
        note = _text("decision note", note, empty=True)
        payload = {
            "campaign_id": campaign_id,
            "asset_id": asset_id,
            "role": role,
            "reviewer_id": reviewer_id,
            "decision": decision,
            "note": note,
        }

        def apply(connection: sqlite3.Connection, at_utc: str) -> dict[str, Any]:
            campaign, _ = self._campaign(connection, campaign_id)
            version = self._current_version(connection, campaign_id, asset_id)
            assignment = connection.execute(
                "SELECT reviewer_id FROM assignments WHERE campaign_id=? AND asset_id=? AND campaign_revision=? AND asset_version=? AND role=?",
                (campaign_id, asset_id, campaign["revision"], version["version"], role),
            ).fetchone()
            if assignment is None or assignment["reviewer_id"] != reviewer_id:
                raise InvalidState("decision author is not the current assigned reviewer for this role")
            if decision == "APPROVE":
                open_annotation = connection.execute(
                    "SELECT annotation_id FROM annotations WHERE campaign_id=? AND asset_id=? AND campaign_revision=? AND asset_version=? AND role=? AND reviewer_id=? AND status='OPEN' LIMIT 1",
                    (campaign_id, asset_id, campaign["revision"], version["version"], role, reviewer_id),
                ).fetchone()
                if open_annotation is not None:
                    raise InvalidState("reviewer must resolve own open annotations before approving")
            ordinal = self._append_event(
                connection,
                campaign_id,
                "REVIEW_DISPOSITION_RECORDED",
                {
                    "asset_id": asset_id,
                    "campaign_revision": campaign["revision"],
                    "asset_version": version["version"],
                    "role": role,
                    "reviewer_id": reviewer_id,
                    "decision": decision,
                    "note": note,
                },
                at_utc,
            )
            connection.execute(
                "INSERT INTO dispositions VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(campaign_id,asset_id,campaign_revision,asset_version,role) DO UPDATE SET reviewer_id=excluded.reviewer_id,decision=excluded.decision,note=excluded.note,event_ordinal=excluded.event_ordinal,decided_at=excluded.decided_at",
                (
                    campaign_id,
                    asset_id,
                    campaign["revision"],
                    version["version"],
                    role,
                    reviewer_id,
                    decision,
                    note,
                    ordinal,
                    at_utc,
                ),
            )
            return {
                **payload,
                "campaign_revision": campaign["revision"],
                "asset_version": version["version"],
                "event_ordinal": ordinal,
            }

        return self._mutate(request_id, "decide", payload, apply)
