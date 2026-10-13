#!/usr/bin/env python3
"""Deterministic CSV and Markdown projections for creative-review packets."""
from __future__ import annotations

import csv
import io
from typing import Any

from _validation import canonical_json

def _csv_safe(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def _render_assets_csv(manifest: dict[str, Any]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "asset_id",
            "state",
            "version",
            "content_sha256",
            "media_type",
            "author_id",
            "destinations",
            "required_roles",
            "holds",
            "changes",
            "review",
        ]
    )
    raw_by_id = {item["asset_id"]: item for item in manifest["assets"]}
    derived_by_id = {item["asset_id"]: item for item in manifest["derived"]["assets"]}
    for requirement in manifest["campaign"]["spec"]["assets"]:
        asset_id = requirement["asset_id"]
        raw = raw_by_id.get(asset_id, {})
        version = raw.get("current_version")
        derived = derived_by_id[asset_id]
        writer.writerow(
            [
                _csv_safe(asset_id),
                derived["state"],
                "" if version is None else version["version"],
                "" if version is None else version["content_sha256"],
                requirement["media_type"],
                "" if version is None else _csv_safe(version["author_id"]),
                "|".join(requirement["destinations"]),
                "|".join(requirement["required_roles"]),
                "|".join(derived["holds"]),
                "|".join(derived["changes"]),
                "|".join(derived["review"]),
            ]
        )
    return output.getvalue().encode("utf-8")


def _render_annotations_csv(manifest: dict[str, Any]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "asset_id",
            "annotation_id",
            "status",
            "role",
            "reviewer_id",
            "category",
            "location_json",
            "note",
            "resolved_by",
        ]
    )
    for item in sorted(manifest["assets"], key=lambda row: row["asset_id"]):
        for annotation in sorted(item["annotations"], key=lambda row: row["annotation_id"]):
            writer.writerow(
                [
                    _csv_safe(item["asset_id"]),
                    _csv_safe(annotation["annotation_id"]),
                    annotation["status"],
                    _csv_safe(annotation["role"]),
                    _csv_safe(annotation["reviewer_id"]),
                    annotation["category"],
                    canonical_json(annotation["location"]),
                    _csv_safe(annotation["note"]),
                    _csv_safe(annotation["resolved_by"]),
                ]
            )
    return output.getvalue().encode("utf-8")


def _markdown_text(value: Any) -> str:
    text = str(value)
    for token in ("\\", "`", "*", "_", "[", "]", "<", ">", "#", "|"):
        text = text.replace(token, "\\" + token)
    return text


def _render_markdown(manifest: dict[str, Any]) -> bytes:
    campaign = manifest["campaign"]
    derived = manifest["derived"]
    lines = [
        f"# Creative review packet — {_markdown_text(campaign['name'])}",
        "",
        f"- Campaign ID: `{campaign['campaign_id']}`",
        f"- Campaign revision: `{campaign['revision']}`",
        f"- Exact spec SHA-256: `{campaign['spec_sha256']}`",
        f"- Workflow state: **{derived['campaign_state']}**",
        "- Authority: **LOCAL OWNER REVIEW ONLY / UNSENT**",
        "",
        "`READY_FOR_OWNER_HANDOFF` means only that the retained owner-supplied workflow requirements are coherently satisfied for the exact listed bytes. It is not a legal, rights, brand, compliance, publication, customer-acceptance, payment, or revenue conclusion.",
        "",
        "## Assets",
        "",
    ]
    raw_by_id = {item["asset_id"]: item for item in manifest["assets"]}
    for item in derived["assets"]:
        raw = raw_by_id.get(item["asset_id"], {})
        version = raw.get("current_version")
        lines.extend(
            [
                f"### {item['asset_id']} — {item['state']}",
                "",
                f"- Version: `{item['current_version'] if item['current_version'] is not None else 'MISSING'}`",
                f"- SHA-256: `{item['current_sha256'] if item['current_sha256'] is not None else 'MISSING'}`",
                f"- Destinations: {', '.join(item['destinations'])}",
                f"- Required roles: {', '.join(item['required_roles'])}",
                f"- Author: `{version['author_id'] if version else 'MISSING'}`",
            ]
        )
        for label, values in (("Holds", item["holds"]), ("Changes", item["changes"]), ("Review", item["review"])):
            lines.append(f"- {label}: {', '.join(values) if values else 'none'}")
        lines.append("")
    lines.extend(["## Authority flags", ""])
    for key, value in sorted(derived["authority"].items()):
        lines.append(f"- `{key}`: `{str(value).lower()}`")
    lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")
