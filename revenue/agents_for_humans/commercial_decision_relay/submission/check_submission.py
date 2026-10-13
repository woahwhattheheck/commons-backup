#!/usr/bin/env python3
"""Validate the local Agents for Humans submission packet without external side effects."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlparse

SCHEMA = "commercial-decision-relay-submission/v1"
ALLOWED_STATUS = {"COMPLETE", "HUMAN_PENDING", "OPTIONAL_PENDING"}
REQUIRED_EXTERNAL = {"public_code_repo", "aws_builder_id", "public_demo_video", "devpost_submission"}
OPTIONAL_EXTERNAL = {"live_demo"}
EXPECTED_AUTHORITY = {
    "devpost_submission_authorized": False,
    "aws_account_mutation_authorized": False,
    "video_publication_authorized": False,
    "prize_awarded": False,
    "revenue_recognized": False,
}

_YOUTUBE_PAGE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
_VIMEO_PAGE_HOSTS = {"vimeo.com", "www.vimeo.com"}
_YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_VIMEO_ID = re.compile(r"[0-9]{1,20}\Z")


class SubmissionError(ValueError):
    pass


def _obj(value, label):
    if type(value) is not dict:
        raise SubmissionError(f"{label} must be an object")
    return value


def _list(value, label):
    if type(value) is not list:
        raise SubmissionError(f"{label} must be a list")
    return value


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise SubmissionError(f"{label} must be a non-empty string")
    return value.strip()


def _bool(value, label):
    if type(value) is not bool:
        raise SubmissionError(f"{label} must be a boolean")
    return value


def _https(value, label, *, github_repo=False):
    text = _text(value, label)
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SubmissionError(f"{label} must be an https URL")
    if github_repo:
        if parsed.netloc.lower() != "github.com":
            raise SubmissionError(f"{label} must use github.com")
        pieces = [p for p in parsed.path.split("/") if p]
        if len(pieces) != 2:
            raise SubmissionError(f"{label} must be a repository-root URL")
    return text


def _video_id(raw, label, *, numeric=False):
    if type(raw) is not str or not raw or unquote(raw) != raw:
        raise SubmissionError(f"{label} must contain one unescaped video id")
    pattern = _VIMEO_ID if numeric else _YOUTUBE_ID
    if pattern.fullmatch(raw) is None:
        raise SubmissionError(f"{label} must contain a valid video id")
    return raw


def _video_url_id(video_url, label):
    parsed = urlparse(video_url)
    host = (parsed.hostname or "").lower().rstrip(".")
    try:
        port = parsed.port
    except ValueError as exc:
        raise SubmissionError(f"{label} has an invalid port") from exc
    if parsed.username is not None or parsed.password is not None or port not in (None, 443):
        raise SubmissionError(f"{label} must not contain userinfo or a non-default port")

    pieces = [piece for piece in parsed.path.split("/") if piece]
    if host == "youtu.be":
        if len(pieces) != 1:
            raise SubmissionError(f"{label} must identify one YouTube video")
        return ("youtube", _video_id(pieces[0], label))

    if host in _YOUTUBE_PAGE_HOSTS:
        if pieces == ["watch"]:
            values = parse_qs(parsed.query, keep_blank_values=True).get("v", [])
            if len(values) != 1:
                raise SubmissionError(f"{label} must contain exactly one YouTube v id")
            return ("youtube", _video_id(values[0], label))
        if len(pieces) == 2 and pieces[0] in {"shorts", "embed", "live"}:
            return ("youtube", _video_id(pieces[1], label))
        raise SubmissionError(f"{label} must identify a concrete YouTube video")

    if host in _VIMEO_PAGE_HOSTS:
        candidate = None
        if len(pieces) == 1:
            candidate = pieces[0]
        elif len(pieces) == 3 and pieces[0] == "channels":
            candidate = pieces[2]
        elif len(pieces) == 4 and pieces[0] == "groups" and pieces[2] == "videos":
            candidate = pieces[3]
        elif len(pieces) == 4 and pieces[0] in {"album", "showcase"} and pieces[2] == "video":
            candidate = pieces[3]
        if candidate is None:
            raise SubmissionError(f"{label} must identify a concrete Vimeo video")
        return ("vimeo", _video_id(candidate, label, numeric=True))

    if host == "player.vimeo.com":
        if len(pieces) != 2 or pieces[0] != "video":
            raise SubmissionError(f"{label} must identify one Vimeo player video")
        return ("vimeo", _video_id(pieces[1], label, numeric=True))

    raise SubmissionError(f"{label} must use a supported YouTube or Vimeo host")


def _validate_public_demo_video(item, label):
    """Validate offline proof for the Devpost public-video requirement.

    The validator deliberately does not make a network request. COMPLETE is an
    operator assertion backed by a concrete public video URL, a measured
    duration, and explicit public-access confirmation. The URL grammar rejects
    channel, profile, playlist, search, and other non-video pages.
    """
    video_url = _https(item.get("value"), f"{label}.value")
    _video_url_id(video_url, f"{label}.value")

    duration = item.get("duration_seconds")
    if type(duration) is not int or not 1 <= duration <= 300:
        raise SubmissionError(f"{label}.duration_seconds must be an integer from 1 through 300")
    if item.get("public_confirmed") is not True:
        raise SubmissionError(f"{label}.public_confirmed must be true")
    return video_url


def validate(manifest, project_root: Path):
    m = _obj(manifest, "manifest")
    if m.get("schema") != SCHEMA:
        raise SubmissionError(f"schema must be {SCHEMA}")

    _text(m.get("project_name"), "project_name")
    comp = _obj(m.get("competition"), "competition")
    _text(comp.get("name"), "competition.name")
    _text(comp.get("track"), "competition.track")
    deadline_text = _text(comp.get("deadline"), "competition.deadline")
    try:
        deadline = datetime.fromisoformat(deadline_text)
    except ValueError as exc:
        raise SubmissionError("competition.deadline must be ISO-8601") from exc
    if deadline.tzinfo is None or deadline.utcoffset() is None:
        raise SubmissionError("competition.deadline must include timezone")
    _https(comp.get("official_url"), "competition.official_url")

    repo_url = _https(m.get("public_code_repo_url"), "public_code_repo_url", github_repo=True)
    source_url = _https(m.get("project_source_url"), "project_source_url")
    if not source_url.startswith(repo_url + "/"):
        raise SubmissionError("project_source_url must be under public_code_repo_url")

    licenses = _obj(m.get("license"), "license")
    if _text(licenses.get("repository"), "license.repository") not in {"MIT", "Apache-2.0"}:
        raise SubmissionError("repository license must be MIT or Apache-2.0")
    if _text(licenses.get("project"), "license.project") not in {"MIT", "Apache-2.0"}:
        raise SubmissionError("project license must be MIT or Apache-2.0")

    required_artifacts = _list(m.get("required_artifacts"), "required_artifacts")
    normalized = []
    for idx, raw in enumerate(required_artifacts):
        path_text = _text(raw, f"required_artifacts[{idx}]")
        path = Path(path_text)
        if path.is_absolute() or ".." in path.parts:
            raise SubmissionError(f"required_artifacts[{idx}] must stay under project root")
        normalized.append(path_text)
        if not (project_root / path).is_file():
            raise SubmissionError(f"required artifact missing: {path_text}")
    if len(set(normalized)) != len(normalized):
        raise SubmissionError("required_artifacts contains duplicates")

    external = _list(m.get("external_requirements"), "external_requirements")
    by_id = {}
    for idx, raw in enumerate(external):
        item = _obj(raw, f"external_requirements[{idx}]")
        label = f"external_requirements[{idx}]"
        item_id = _text(item.get("id"), f"{label}.id")
        if item_id in by_id:
            raise SubmissionError(f"duplicate external requirement: {item_id}")
        status = _text(item.get("status"), f"{label}.status")
        if status not in ALLOWED_STATUS:
            raise SubmissionError(f"unsupported external status: {status}")
        required = _bool(item.get("required"), f"{label}.required")
        value = item.get("value")
        if status == "COMPLETE":
            if item_id == "public_demo_video":
                value = _validate_public_demo_video(item, label)
            elif type(value) is not str or not value.strip():
                raise SubmissionError(f"{item_id} COMPLETE requires a non-empty value")
        else:
            if value not in (None, ""):
                raise SubmissionError(f"{item_id} non-COMPLETE must not carry a value")
            if item_id == "public_demo_video" and (
                item.get("duration_seconds") is not None or item.get("public_confirmed") is not None
            ):
                raise SubmissionError("public_demo_video non-COMPLETE must not carry video proof")
        by_id[item_id] = {"required": required, "status": status, "value": value}

    if set(by_id) != REQUIRED_EXTERNAL | OPTIONAL_EXTERNAL:
        missing = sorted((REQUIRED_EXTERNAL | OPTIONAL_EXTERNAL) - set(by_id))
        extra = sorted(set(by_id) - (REQUIRED_EXTERNAL | OPTIONAL_EXTERNAL))
        raise SubmissionError(f"external requirement ids mismatch; missing={missing}, extra={extra}")
    for item_id in REQUIRED_EXTERNAL:
        if by_id[item_id]["required"] is not True:
            raise SubmissionError(f"{item_id} must be required")
    for item_id in OPTIONAL_EXTERNAL:
        if by_id[item_id]["required"] is not False:
            raise SubmissionError(f"{item_id} must be optional")
    if by_id["public_code_repo"]["status"] != "COMPLETE":
        raise SubmissionError("public_code_repo must be COMPLETE for this packet")
    if by_id["public_code_repo"]["value"] != repo_url:
        raise SubmissionError("public_code_repo value must equal public_code_repo_url")

    authority = _obj(m.get("authority"), "authority")
    if authority != EXPECTED_AUTHORITY:
        raise SubmissionError("authority block must exactly preserve all-false external authority")

    pending = sorted(item_id for item_id in REQUIRED_EXTERNAL if by_id[item_id]["status"] != "COMPLETE")
    state = "SUBMISSION_READY" if not pending else "INTERNAL_READY_EXTERNAL_PENDING"
    return {
        "schema": "commercial-decision-relay-submission-check/v1",
        "state": state,
        "pending_required_external": pending,
        "deadline": deadline.isoformat(),
        "public_code_repo_url": repo_url,
        "project_source_url": source_url,
        "devpost_submission_authorized": False,
        "prize_awarded": False,
        "revenue_recognized": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="submission/manifest.json")
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve()
    path = Path(args.manifest)
    if not path.is_absolute():
        path = root / path
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    result = validate(manifest, root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["state"] in {"INTERNAL_READY_EXTERNAL_PENDING", "SUBMISSION_READY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
