#!/usr/bin/env python3
"""Coherent snapshot, semantic status, and export mixin."""
from __future__ import annotations

import os
from contextlib import closing
from typing import Any

from _bundle import _bundle_bytes, publish_bundle
from _projection import _derive
from _validation import SCHEMA, _id, canonical_json, strict_json_loads


class ManifestMixin:
    def manifest(self, campaign_id: str) -> dict[str, Any]:
        campaign_id = _id("campaign_id", campaign_id)
        with closing(self.connection()) as connection:
            connection.execute("BEGIN")
            try:
                campaign, spec = self._campaign(connection, campaign_id)
                events = [
                    {
                        "ordinal": row["ordinal"],
                        "event_kind": row["event_kind"],
                        "payload": strict_json_loads(row["payload_json"]),
                        "at_utc": row["at_utc"],
                        "previous_hash": row["previous_hash"],
                        "event_hash": row["event_hash"],
                    }
                    for row in connection.execute(
                        "SELECT * FROM events WHERE campaign_id=? ORDER BY ordinal",
                        (campaign_id,),
                    )
                ]
                assets: list[dict[str, Any]] = []
                for requirement in spec["assets"]:
                    asset_id = requirement["asset_id"]
                    version = connection.execute(
                        "SELECT * FROM asset_versions WHERE campaign_id=? AND asset_id=? ORDER BY version DESC LIMIT 1",
                        (campaign_id, asset_id),
                    ).fetchone()
                    current = None
                    if version is not None:
                        current = {
                            "version": version["version"],
                            "content_sha256": version["content_sha256"],
                            "content_size": version["content_size"],
                            "file_name": version["file_name"],
                            "media_type": version["media_type"],
                            "metadata": strict_json_loads(version["metadata_json"]),
                            "provenance_ref": version["provenance_ref"],
                            "author_id": version["author_id"],
                            "created_at": version["created_at"],
                        }
                    version_number = -1 if version is None else version["version"]
                    assignments = [
                        {
                            "campaign_revision": row["campaign_revision"],
                            "asset_version": row["asset_version"],
                            "role": row["role"],
                            "reviewer_id": row["reviewer_id"],
                            "assigned_at": row["assigned_at"],
                        }
                        for row in connection.execute(
                            "SELECT * FROM assignments WHERE campaign_id=? AND asset_id=? AND campaign_revision=? AND asset_version=? ORDER BY role",
                            (campaign_id, asset_id, campaign["revision"], version_number),
                        )
                    ]
                    annotations = [
                        {
                            "annotation_id": row["annotation_id"],
                            "campaign_revision": row["campaign_revision"],
                            "asset_version": row["asset_version"],
                            "role": row["role"],
                            "reviewer_id": row["reviewer_id"],
                            "location": strict_json_loads(row["location_json"]),
                            "category": row["category"],
                            "note": row["note"],
                            "status": row["status"],
                            "created_at": row["created_at"],
                            "resolved_at": row["resolved_at"],
                            "resolved_by": row["resolved_by"],
                        }
                        for row in connection.execute(
                            "SELECT * FROM annotations WHERE campaign_id=? AND asset_id=? AND campaign_revision=? AND asset_version=? ORDER BY annotation_id",
                            (campaign_id, asset_id, campaign["revision"], version_number),
                        )
                    ]
                    dispositions = [
                        {
                            "campaign_revision": row["campaign_revision"],
                            "asset_version": row["asset_version"],
                            "role": row["role"],
                            "reviewer_id": row["reviewer_id"],
                            "decision": row["decision"],
                            "note": row["note"],
                            "event_ordinal": row["event_ordinal"],
                            "decided_at": row["decided_at"],
                        }
                        for row in connection.execute(
                            "SELECT * FROM dispositions WHERE campaign_id=? AND asset_id=? AND campaign_revision=? AND asset_version=? ORDER BY role",
                            (campaign_id, asset_id, campaign["revision"], version_number),
                        )
                    ]
                    assets.append(
                        {
                            "asset_id": asset_id,
                            "current_version": current,
                            "assignments": assignments,
                            "annotations": annotations,
                            "dispositions": dispositions,
                        }
                    )
                raw = {
                    "schema": SCHEMA,
                    "campaign": {
                        "campaign_id": campaign_id,
                        "name": campaign["name"],
                        "revision": campaign["revision"],
                        "spec_sha256": campaign["spec_sha256"],
                        "spec": spec,
                    },
                    "events": events,
                    "assets": assets,
                }
                derived = _derive(raw)
                connection.execute("COMMIT")
                return {**raw, "derived": derived}
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def status(self, campaign_id: str) -> dict[str, Any]:
        manifest = self.manifest(campaign_id)
        return {
            "campaign": manifest["campaign"],
            "derived": manifest["derived"],
            "event_chain_head": "0" * 64 if not manifest["events"] else manifest["events"][-1]["event_hash"],
        }

    def export(self, campaign_id: str, output_directory: os.PathLike[str] | str) -> dict[str, Any]:
        manifest = self.manifest(campaign_id)
        result = publish_bundle(output_directory, _bundle_bytes(manifest))
        return {
            "campaign_id": campaign_id,
            "campaign_revision": manifest["campaign"]["revision"],
            "campaign_state": manifest["derived"]["campaign_state"],
            **result,
        }
