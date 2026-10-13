#!/usr/bin/env python3
"""Transactional SQLite state machine for creative review and approval."""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from typing import Any, Callable

from _events import _event_hash
from _validation import (
    ANNOTATION_CATEGORIES,
    DECISIONS,
    MEDIA_TYPES,
    SCHEMA,
    IdempotencyConflict,
    InvalidInput,
    InvalidState,
    _id,
    _metadata_matches,
    _text,
    canonical_json,
    normalize_location,
    normalize_metadata,
    normalize_spec,
    read_asset,
    sha256_json,
    strict_json_loads,
    utc_now,
)

class CreativeReviewStore:
    def __init__(self, db_path: os.PathLike[str] | str):
        self.db_path = os.fspath(db_path)
        self._initialize()

    def connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        schema = """
CREATE TABLE IF NOT EXISTS campaigns(
  campaign_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  spec_json TEXT NOT NULL,
  spec_sha256 TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision>=1),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS asset_versions(
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
  asset_id TEXT NOT NULL,
  version INTEGER NOT NULL CHECK(version>=1),
  content_sha256 TEXT NOT NULL,
  content_size INTEGER NOT NULL CHECK(content_size>=0),
  file_name TEXT NOT NULL,
  media_type TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  provenance_ref TEXT NOT NULL,
  author_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(campaign_id,asset_id,version)
);
CREATE TABLE IF NOT EXISTS assignments(
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
  asset_id TEXT NOT NULL,
  campaign_revision INTEGER NOT NULL,
  asset_version INTEGER NOT NULL,
  role TEXT NOT NULL,
  reviewer_id TEXT NOT NULL,
  assigned_at TEXT NOT NULL,
  PRIMARY KEY(campaign_id,asset_id,campaign_revision,asset_version,role)
);
CREATE TABLE IF NOT EXISTS annotations(
  annotation_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
  asset_id TEXT NOT NULL,
  campaign_revision INTEGER NOT NULL,
  asset_version INTEGER NOT NULL,
  role TEXT NOT NULL,
  reviewer_id TEXT NOT NULL,
  location_json TEXT NOT NULL,
  category TEXT NOT NULL,
  note TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN('OPEN','RESOLVED')),
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolved_by TEXT
);
CREATE TABLE IF NOT EXISTS dispositions(
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
  asset_id TEXT NOT NULL,
  campaign_revision INTEGER NOT NULL,
  asset_version INTEGER NOT NULL,
  role TEXT NOT NULL,
  reviewer_id TEXT NOT NULL,
  decision TEXT NOT NULL,
  note TEXT NOT NULL,
  event_ordinal INTEGER NOT NULL,
  decided_at TEXT NOT NULL,
  PRIMARY KEY(campaign_id,asset_id,campaign_revision,asset_version,role)
);
CREATE TABLE IF NOT EXISTS events(
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL,
  event_kind TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  at_utc TEXT NOT NULL,
  previous_hash TEXT NOT NULL,
  event_hash TEXT NOT NULL,
  UNIQUE(campaign_id,ordinal)
);
CREATE TABLE IF NOT EXISTS commands(
  request_id TEXT PRIMARY KEY,
  op TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  result_json TEXT NOT NULL
);
"""
        with closing(self.connection()) as connection:
            connection.executescript(schema)

    def _append_event(
        self,
        connection: sqlite3.Connection,
        campaign_id: str,
        event_kind: str,
        payload: dict[str, Any],
        at_utc: str,
    ) -> int:
        row = connection.execute(
            "SELECT ordinal,event_hash FROM events WHERE campaign_id=? ORDER BY ordinal DESC LIMIT 1",
            (campaign_id,),
        ).fetchone()
        ordinal = 1 if row is None else int(row["ordinal"]) + 1
        previous = "0" * 64 if row is None else row["event_hash"]
        digest = _event_hash(campaign_id, ordinal, event_kind, payload, at_utc, previous)
        connection.execute(
            "INSERT INTO events(campaign_id,ordinal,event_kind,payload_json,at_utc,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?)",
            (campaign_id, ordinal, event_kind, canonical_json(payload), at_utc, previous, digest),
        )
        connection.execute("UPDATE campaigns SET updated_at=? WHERE campaign_id=?", (at_utc, campaign_id))
        return ordinal

    def _mutate(
        self,
        request_id: str,
        operation: str,
        payload: dict[str, Any],
        function: Callable[[sqlite3.Connection, str], dict[str, Any]],
    ) -> dict[str, Any]:
        request_id = _id("request_id", request_id)
        payload_digest = sha256_json({"operation": operation, "payload": payload})
        at_utc = utc_now()
        with closing(self.connection()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                prior = connection.execute("SELECT * FROM commands WHERE request_id=?", (request_id,)).fetchone()
                if prior is not None:
                    if prior["op"] != operation or prior["payload_sha256"] != payload_digest:
                        raise IdempotencyConflict(f"request_id {request_id!r} reused with different semantics")
                    result = strict_json_loads(prior["result_json"])
                    connection.execute("COMMIT")
                    return result
                result = function(connection, at_utc)
                connection.execute(
                    "INSERT INTO commands(request_id,op,payload_sha256,result_json) VALUES(?,?,?,?)",
                    (request_id, operation, payload_digest, canonical_json(result)),
                )
                connection.execute("COMMIT")
                return result
            except Exception:
                connection.execute("ROLLBACK")
                raise

    @staticmethod
    def _campaign(connection: sqlite3.Connection, campaign_id: str) -> tuple[sqlite3.Row, dict[str, Any]]:
        row = connection.execute("SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
        if row is None:
            raise InvalidState(f"unknown campaign: {campaign_id}")
        return row, strict_json_loads(row["spec_json"])

    @staticmethod
    def _requirement(spec: dict[str, Any], asset_id: str) -> dict[str, Any]:
        for requirement in spec["assets"]:
            if requirement["asset_id"] == asset_id:
                return requirement
        raise InvalidState(f"asset is not in current campaign spec: {asset_id}")

    @staticmethod
    def _current_version(connection: sqlite3.Connection, campaign_id: str, asset_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM asset_versions WHERE campaign_id=? AND asset_id=? ORDER BY version DESC LIMIT 1",
            (campaign_id, asset_id),
        ).fetchone()
        if row is None:
            raise InvalidState(f"asset has no submitted version: {asset_id}")
        return row

    def create_campaign(self, request_id: str, spec_value: Any) -> dict[str, Any]:
        spec = normalize_spec(spec_value)
        campaign_id = spec["campaign_id"]
        digest = sha256_json(spec)
        payload = {"spec": spec}

        def apply(connection: sqlite3.Connection, at_utc: str) -> dict[str, Any]:
            if connection.execute("SELECT 1 FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone():
                raise InvalidState(f"campaign already exists: {campaign_id}")
            connection.execute(
                "INSERT INTO campaigns VALUES(?,?,?,?,1,?,?)",
                (campaign_id, spec["name"], canonical_json(spec), digest, at_utc, at_utc),
            )
            self._append_event(
                connection,
                campaign_id,
                "CAMPAIGN_CREATED",
                {"revision": 1, "spec_sha256": digest},
                at_utc,
            )
            return {"campaign_id": campaign_id, "revision": 1, "spec_sha256": digest}

        return self._mutate(request_id, "create_campaign", payload, apply)

    def revise_campaign(self, request_id: str, expected_revision: int, spec_value: Any) -> dict[str, Any]:
        if type(expected_revision) is not int or expected_revision < 1:
            raise InvalidInput("expected_revision must be a positive integer")
        spec = normalize_spec(spec_value)
        campaign_id = spec["campaign_id"]
        digest = sha256_json(spec)
        payload = {"expected_revision": expected_revision, "spec": spec}

        def apply(connection: sqlite3.Connection, at_utc: str) -> dict[str, Any]:
            row, _ = self._campaign(connection, campaign_id)
            if row["revision"] != expected_revision:
                raise InvalidState("campaign revision moved")
            if row["spec_sha256"] == digest:
                return {"campaign_id": campaign_id, "revision": expected_revision, "spec_sha256": digest, "changed": False}
            revision = expected_revision + 1
            connection.execute(
                "UPDATE campaigns SET name=?,spec_json=?,spec_sha256=?,revision=?,updated_at=? WHERE campaign_id=?",
                (spec["name"], canonical_json(spec), digest, revision, at_utc, campaign_id),
            )
            self._append_event(
                connection,
                campaign_id,
                "CAMPAIGN_REQUIREMENTS_REVISED",
                {"old_revision": expected_revision, "revision": revision, "spec_sha256": digest},
                at_utc,
            )
            return {"campaign_id": campaign_id, "revision": revision, "spec_sha256": digest, "changed": True}

        return self._mutate(request_id, "revise_campaign", payload, apply)

    def submit_asset(
        self,
        request_id: str,
        campaign_id: str,
        asset_id: str,
        author_id: str,
        path: os.PathLike[str] | str,
        media_type: str,
        metadata_value: Any,
        provenance_ref: str,
    ) -> dict[str, Any]:
        campaign_id = _id("campaign_id", campaign_id)
        asset_id = _id("asset_id", asset_id)
        author_id = _id("author_id", author_id)
        if type(media_type) is not str or media_type not in MEDIA_TYPES:
            raise InvalidInput("invalid media_type")
        metadata = normalize_metadata(metadata_value)
        provenance_ref = _text("provenance_ref", provenance_ref, maximum=512)
        _, digest, size, file_name = read_asset(path)
        file_name = _text("file_name", file_name, maximum=255)
        payload = {
            "campaign_id": campaign_id,
            "asset_id": asset_id,
            "author_id": author_id,
            "content_sha256": digest,
            "content_size": size,
            "file_name": file_name,
            "media_type": media_type,
            "metadata": metadata,
            "provenance_ref": provenance_ref,
        }

        def apply(connection: sqlite3.Connection, at_utc: str) -> dict[str, Any]:
            _, spec = self._campaign(connection, campaign_id)
            requirement = self._requirement(spec, asset_id)
            if requirement["media_type"] != media_type:
                raise InvalidState("submitted media_type differs from current requirement")
            mismatches = _metadata_matches(metadata, requirement["constraints"])
            if mismatches:
                raise InvalidState("submitted metadata violates current requirement: " + ", ".join(mismatches))
            prior = connection.execute(
                "SELECT * FROM asset_versions WHERE campaign_id=? AND asset_id=? ORDER BY version DESC LIMIT 1",
                (campaign_id, asset_id),
            ).fetchone()
            if prior is not None and all(
                (
                    prior["content_sha256"] == digest,
                    prior["media_type"] == media_type,
                    prior["metadata_json"] == canonical_json(metadata),
                    prior["provenance_ref"] == provenance_ref,
                    prior["author_id"] == author_id,
                )
            ):
                return {
                    "campaign_id": campaign_id,
                    "asset_id": asset_id,
                    "version": prior["version"],
                    "content_sha256": digest,
                    "changed": False,
                }
            version = 1 if prior is None else int(prior["version"]) + 1
            connection.execute(
                "INSERT INTO asset_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    campaign_id,
                    asset_id,
                    version,
                    digest,
                    size,
                    file_name,
                    media_type,
                    canonical_json(metadata),
                    provenance_ref,
                    author_id,
                    at_utc,
                ),
            )
            self._append_event(
                connection,
                campaign_id,
                "ASSET_VERSION_SUBMITTED",
                {
                    "asset_id": asset_id,
                    "version": version,
                    "content_sha256": digest,
                    "content_size": size,
                    "file_name": file_name,
                    "media_type": media_type,
                    "metadata": metadata,
                    "provenance_ref": provenance_ref,
                    "author_id": author_id,
                },
                at_utc,
            )
            return {
                "campaign_id": campaign_id,
                "asset_id": asset_id,
                "version": version,
                "content_sha256": digest,
                "changed": True,
            }

        return self._mutate(request_id, "submit_asset", payload, apply)
