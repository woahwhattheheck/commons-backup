from __future__ import annotations

from typing import Any

from .common import (
    ControlError,
    require_bool,
    require_enum,
    require_exact_keys,
    require_int,
    require_list,
    require_object,
    require_ref,
    require_ref_list,
    require_sha256,
    require_string,
    require_timestamp,
    require_unique,
)

from ._parse_models import INTERPRETATIONS, PREP_STATES, RELEASE_CLASSES, SOURCE_CLASSES

def _parse_observation(value: Any, index: int) -> dict[str, Any]:
    label = f"evidence.observations[{index}]"
    obj = require_object(value, label)
    require_exact_keys(
        obj,
        required={
            "observation_id",
            "message_ref",
            "source_class",
            "sender_ref",
            "thread_id",
            "received_at",
            "content_sha256",
            "supersedes",
        },
        label=label,
    )
    supersedes_raw = obj["supersedes"]
    supersedes = None if supersedes_raw is None else require_ref(supersedes_raw, f"{label}.supersedes")
    return {
        "observation_id": require_ref(obj["observation_id"], f"{label}.observation_id"),
        "message_ref": require_ref(obj["message_ref"], f"{label}.message_ref"),
        "source_class": require_enum(obj["source_class"], SOURCE_CLASSES, f"{label}.source_class"),
        "sender_ref": require_ref(obj["sender_ref"], f"{label}.sender_ref"),
        "thread_id": require_ref(obj["thread_id"], f"{label}.thread_id"),
        "received_at": require_timestamp(obj["received_at"], f"{label}.received_at"),
        "content_sha256": require_sha256(obj["content_sha256"], f"{label}.content_sha256"),
        "supersedes": supersedes,
    }

def _parse_interpretation(value: Any, index: int) -> dict[str, Any]:
    label = f"evidence.interpretations[{index}]"
    obj = require_object(value, label)
    require_exact_keys(
        obj,
        required={
            "interpretation_id",
            "observation_id",
            "message_ref",
            "content_sha256",
            "decision",
            "reviewed_at",
            "owner_review_ref",
            "owner_review_sha256",
        },
        label=label,
    )
    return {
        "interpretation_id": require_ref(obj["interpretation_id"], f"{label}.interpretation_id"),
        "observation_id": require_ref(obj["observation_id"], f"{label}.observation_id"),
        "message_ref": require_ref(obj["message_ref"], f"{label}.message_ref"),
        "content_sha256": require_sha256(obj["content_sha256"], f"{label}.content_sha256"),
        "decision": require_enum(obj["decision"], INTERPRETATIONS, f"{label}.decision"),
        "reviewed_at": require_timestamp(obj["reviewed_at"], f"{label}.reviewed_at"),
        "owner_review_ref": require_ref(obj["owner_review_ref"], f"{label}.owner_review_ref"),
        "owner_review_sha256": require_sha256(
            obj["owner_review_sha256"], f"{label}.owner_review_sha256"
        ),
    }

def _parse_asset(value: Any, index: int) -> dict[str, Any]:
    label = f"evidence.assets[{index}]"
    obj = require_object(value, label)
    require_exact_keys(
        obj,
        required={
            "asset_id",
            "title",
            "version",
            "sha256",
            "release_class",
            "prep_state",
            "safe_snippets",
            "required_for_followup",
        },
        label=label,
    )
    snippets = require_list(obj["safe_snippets"], f"{label}.safe_snippets", max_items=32)
    parsed_snippets = [
        require_string(
            snippet,
            f"{label}.safe_snippets[{snippet_index}]",
            maximum=1024,
            allow_newlines=False,
        )
        for snippet_index, snippet in enumerate(snippets)
    ]
    require_unique(parsed_snippets, f"{label}.safe_snippets")
    return {
        "asset_id": require_ref(obj["asset_id"], f"{label}.asset_id"),
        "title": require_string(obj["title"], f"{label}.title", maximum=256),
        "version": require_ref(obj["version"], f"{label}.version"),
        "sha256": require_sha256(obj["sha256"], f"{label}.sha256"),
        "release_class": require_enum(
            obj["release_class"], RELEASE_CLASSES, f"{label}.release_class"
        ),
        "prep_state": require_enum(obj["prep_state"], PREP_STATES, f"{label}.prep_state"),
        "safe_snippets": parsed_snippets,
        "required_for_followup": require_bool(
            obj["required_for_followup"], f"{label}.required_for_followup"
        ),
    }

def _parse_release(value: Any, index: int) -> dict[str, Any]:
    label = f"evidence.releases[{index}]"
    obj = require_object(value, label)
    require_exact_keys(
        obj,
        required={
            "release_id",
            "asset_id",
            "asset_version",
            "asset_sha256",
            "descriptor_sha256",
            "released_at",
            "release_ref",
            "release_sha256",
        },
        label=label,
    )
    return {
        "release_id": require_ref(obj["release_id"], f"{label}.release_id"),
        "asset_id": require_ref(obj["asset_id"], f"{label}.asset_id"),
        "asset_version": require_ref(obj["asset_version"], f"{label}.asset_version"),
        "asset_sha256": require_sha256(obj["asset_sha256"], f"{label}.asset_sha256"),
        "descriptor_sha256": require_sha256(
            obj["descriptor_sha256"], f"{label}.descriptor_sha256"
        ),
        "released_at": require_timestamp(obj["released_at"], f"{label}.released_at"),
        "release_ref": require_ref(obj["release_ref"], f"{label}.release_ref"),
        "release_sha256": require_sha256(obj["release_sha256"], f"{label}.release_sha256"),
    }

