from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .common import digest_object, sorted_unique
from .parse import ParsedCandidate, ParsedEvidence
from .policy import policy_dict

_POLICY_AT_IMPORT = policy_dict()
_MAX_FUTURE_SKEW_SECONDS = int(_POLICY_AT_IMPORT["max_future_skew_seconds"])
del _POLICY_AT_IMPORT


def asset_descriptor(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": asset["asset_id"],
        "title": asset["title"],
        "version": asset["version"],
        "sha256": asset["sha256"],
        "release_class": asset["release_class"],
        "safe_snippets": list(asset["safe_snippets"]),
    }


def asset_descriptor_sha256(asset: dict[str, Any]) -> str:
    return digest_object(asset_descriptor(asset))


def _project(asset: dict[str, Any]) -> dict[str, Any]:
    result = asset_descriptor(asset)
    result["descriptor_sha256"] = asset_descriptor_sha256(asset)
    return result


def evaluate_assets(
    candidate: ParsedCandidate,
    evidence: ParsedEvidence,
    *,
    now: datetime,
    _max_future_skew_seconds: int = _MAX_FUTURE_SKEW_SECONDS,
    _timedelta=timedelta,
    _descriptor_sha256=asset_descriptor_sha256,
    _project_asset=_project,
    _sorted_unique=sorted_unique,
) -> dict[str, Any]:
    future_skew = _timedelta(seconds=_max_future_skew_seconds)
    blockers: list[str] = []
    owner_actions: list[str] = []
    assets = {row["asset_id"]: row for row in evidence.assets}
    releases_by_asset: dict[str, list[dict[str, Any]]] = {}
    for release in evidence.releases:
        releases_by_asset.setdefault(release["asset_id"], []).append(release)
        if release["released_at"] > evidence.captured_at:
            blockers.append(f"asset_release_after_capture:{release['release_id']}")
        if release["released_at"] > now + future_skew:
            blockers.append(f"asset_release_in_future:{release['release_id']}")

    required_ids = set(candidate.requested_asset_ids)
    required_ids.update(evidence.requirements["required_asset_ids"])
    required_ids.update(
        row["asset_id"] for row in evidence.assets if row["required_for_followup"]
    )
    safe_assets: list[dict[str, Any]] = []
    for asset_id in sorted(required_ids):
        asset = assets.get(asset_id)
        if asset is None:
            blockers.append(f"required_asset_missing:{asset_id}")
            continue
        if asset["prep_state"] != "READY":
            blockers.append(f"required_asset_not_ready:{asset_id}")
            owner_actions.append(f"prepare_asset:{asset_id}")
            continue
        if asset["release_class"] == "INTERNAL_ONLY":
            blockers.append(f"required_asset_internal_only:{asset_id}")
            owner_actions.append(f"replace_internal_asset:{asset_id}")
            continue
        if asset["release_class"] == "OWNER_APPROVAL_REQUIRED":
            descriptor_digest = _descriptor_sha256(asset)
            matching = [
                release
                for release in releases_by_asset.get(asset_id, [])
                if release["asset_version"] == asset["version"]
                and release["asset_sha256"] == asset["sha256"]
                and release["descriptor_sha256"] == descriptor_digest
            ]
            if len(matching) != 1:
                blockers.append(f"required_asset_exact_release_missing:{asset_id}")
                owner_actions.append(f"retain_exact_asset_release:{asset_id}")
                continue
        safe_assets.append(_project_asset(asset))

    return {
        "blockers": _sorted_unique(blockers),
        "owner_actions": _sorted_unique(owner_actions),
        "safe_assets": safe_assets,
    }
