#!/usr/bin/env python3
"""Fail-closed local evidence checker for the Agents for Humans blog bonus.

This checker never awards points or proves remote publication. It validates that
three distinct drafts exist and, when supplied, that recorded public URLs have
the expected builder.aws HTTPS shape.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

SCHEMA = "commercial-decision-relay-blog-bonus/v1"
EXPECTED_COMPETITION = "Agents for Humans Hackathon"
EXPECTED_RULES = "https://agentsforhumans.devpost.com/rules"
EXPECTED_DEADLINE = "2026-09-14T17:00:00-07:00"
EXPECTED_COUNT = 3
ALLOWED_STATUS = {"DRAFT_READY", "PUBLIC_URL_RECORDED"}
AUTHORITY = {
    "publication_authorized": False,
    "bonus_points_awarded": False,
    "prize_awarded": False,
    "revenue_recognized": False,
}


class BonusManifestError(ValueError):
    pass


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_draft(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise BonusManifestError(f"{label} must be a non-empty relative path")
    rel = Path(value)
    if rel.is_absolute() or ".." in rel.parts:
        raise BonusManifestError(f"{label} must stay inside the project root")
    resolved = (root / rel).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise BonusManifestError(f"{label} escapes the project root") from exc
    if not resolved.is_file():
        raise BonusManifestError(f"{label} does not exist")
    text = resolved.read_text(encoding="utf-8")
    if len(text.split()) < 250:
        raise BonusManifestError(f"{label} is not a substantive publish-ready draft")
    return resolved


def _builder_url(value: object, label: str) -> tuple[str, str]:
    if not isinstance(value, str) or not value.strip():
        raise BonusManifestError(f"{label} must be a non-empty URL")
    raw = value.strip()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise BonusManifestError(f"{label} is not a valid URL") from exc
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or host != "builder.aws.com":
        raise BonusManifestError(f"{label} must be an HTTPS builder.aws.com URL")
    if port not in {None, 443}:
        raise BonusManifestError(f"{label} must use the standard HTTPS port")
    if parsed.username is not None or parsed.password is not None:
        raise BonusManifestError(f"{label} must not contain URL credentials")

    decoded_path = unquote(parsed.path)
    parts = [part for part in decoded_path.split("/") if part]
    if len(parts) < 2 or parts[0] != "content" or parts[1] in {".", ".."}:
        raise BonusManifestError(f"{label} must identify a specific public builder.aws content post")

    # The opaque content ID, not the cosmetic slug/query/fragment, identifies a
    # builder.aws post. This prevents one publication from being counted more
    # than once via URL aliases.
    post_identity = f"{host}/content/{parts[1]}"
    return raw, post_identity


def validate(manifest: object, root: Path) -> dict:
    if not isinstance(manifest, dict):
        raise BonusManifestError("manifest must be an object")
    expected_keys = {
        "schema", "competition", "official_rules", "deadline",
        "points_per_post", "maximum_bonus_points", "authority", "posts",
    }
    if set(manifest) != expected_keys:
        raise BonusManifestError("manifest has unexpected or missing keys")
    if manifest["schema"] != SCHEMA:
        raise BonusManifestError("unexpected schema")
    if manifest["competition"] != EXPECTED_COMPETITION:
        raise BonusManifestError("unexpected competition")
    if manifest["official_rules"] != EXPECTED_RULES:
        raise BonusManifestError("official rules URL drift")
    if manifest["deadline"] != EXPECTED_DEADLINE:
        raise BonusManifestError("deadline drift")
    if type(manifest["points_per_post"]) not in {int, float} or manifest["points_per_post"] != 0.2:
        raise BonusManifestError("points_per_post must be exactly 0.2")
    if type(manifest["maximum_bonus_points"]) not in {int, float} or manifest["maximum_bonus_points"] != 0.6:
        raise BonusManifestError("maximum_bonus_points must be exactly 0.6")
    if manifest["authority"] != AUTHORITY:
        raise BonusManifestError("authority must remain exactly all-false")

    posts = manifest["posts"]
    if not isinstance(posts, list) or len(posts) != EXPECTED_COUNT:
        raise BonusManifestError("exactly three bonus posts are required")

    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    seen_post_identities: set[str] = set()
    recorded = 0
    for index, post in enumerate(posts):
        label = f"posts[{index}]"
        if not isinstance(post, dict) or set(post) != {"id", "title", "draft_path", "status", "public_url"}:
            raise BonusManifestError(f"{label} has unexpected or missing keys")
        ident = post["id"]
        title = post["title"]
        if not isinstance(ident, str) or not ident.strip() or ident in seen_ids:
            raise BonusManifestError(f"{label}.id must be unique and non-empty")
        seen_ids.add(ident)
        if not isinstance(title, str) or "Agents for Humans" not in title or title in seen_titles:
            raise BonusManifestError(f"{label}.title must be unique and contain 'Agents for Humans'")
        seen_titles.add(title)
        _safe_draft(root, post["draft_path"], f"{label}.draft_path")

        status = post["status"]
        if status not in ALLOWED_STATUS:
            raise BonusManifestError(f"{label}.status is unsupported")
        if status == "DRAFT_READY":
            if post["public_url"] is not None:
                raise BonusManifestError(f"{label} DRAFT_READY must not carry a public URL")
        else:
            _, post_identity = _builder_url(post["public_url"], f"{label}.public_url")
            if post_identity in seen_post_identities:
                raise BonusManifestError("public bonus posts must be distinct")
            seen_post_identities.add(post_identity)
            recorded += 1

    return {
        "state": "PUBLICATION_URLS_RECORDED" if recorded == EXPECTED_COUNT else "PUBLICATION_PENDING",
        "draft_count": EXPECTED_COUNT,
        "public_urls_recorded": recorded,
        "remaining_publications": EXPECTED_COUNT - recorded,
        "maximum_rules_bonus_if_eligible": 0.6,
        "recorded_url_nominal_bonus_if_eligible": round(recorded * 0.2, 1),
        "network_publication_verified": False,
        "bonus_points_awarded": False,
        "prize_awarded": False,
        "revenue_recognized": False,
    }


def main() -> int:
    root = _project_root()
    manifest = json.loads((root / "submission" / "blog_bonus_manifest.json").read_text(encoding="utf-8"))
    print(json.dumps(validate(manifest, root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
