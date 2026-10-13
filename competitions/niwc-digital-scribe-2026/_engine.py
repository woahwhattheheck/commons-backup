#!/usr/bin/env python3
"""EvidenceAAR: deterministic, evidence-bound offline Digital Scribe prototype.

This module deliberately has no network/provider code. It consumes a bounded
strict-JSON event packet, corrects per-source clock offsets, segments a
timeline, builds evidence-linked AAR claims, records contradictions/coverage,
and emits deterministic JSON/Markdown/HTML plus a content-addressed receipt.

Authority ceiling: synthetic/offline evaluation only. Nothing here registers,
submits, contacts a sponsor, processes restricted exercise data, or claims an
award/payment.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ENGINE_VERSION = "evidenceaar/1.0"
INPUT_SCHEMA = "evidenceaar-input/v1"
BUNDLE_SCHEMA = "evidenceaar-bundle/v1"
RECEIPT_SCHEMA = "evidenceaar-receipt/v1"

MAX_INPUT_BYTES = 2_000_000
MAX_SOURCES = 128
MAX_EVENTS = 10_000
MAX_TEXT_BYTES = 16_384
MAX_ID_LEN = 128
MAX_SUBJECT_LEN = 256
MAX_ASSERTION_LEN = 1024
MAX_TAGS = 32
MAX_GAP_MS = 86_400_000
MAX_OFFSET_MS = 86_400_000
MAX_NESTING = 64

MODALITIES = {"TEXT", "AUDIO", "VIDEO", "SENSOR", "CHAT", "IMAGE", "OTHER"}
CLAIM_KINDS = {"OBSERVATION", "DECISION", "ACTION", "OUTCOME"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_MD_META = re.compile(r"([\\`*_{}\[\]()<>#+\-.!|])")


class ContractError(ValueError):
    """Input/bundle violates the deterministic contract."""


def _fail(message: str) -> None:
    raise ContractError(message)


def _exact_int(value: Any, field: str, lo: int, hi: int) -> int:
    if type(value) is not int:
        _fail(f"{field}: expected integer")
    if value < lo or value > hi:
        _fail(f"{field}: out of range")
    return value


def _exact_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        _fail(f"{field}: expected boolean")
    return value


def _text(value: Any, field: str, *, max_chars: int, allow_empty: bool = False) -> str:
    if type(value) is not str:
        _fail(f"{field}: expected string")
    if not allow_empty and not value:
        _fail(f"{field}: empty")
    if "\x00" in value:
        _fail(f"{field}: NUL forbidden")
    if len(value) > max_chars:
        _fail(f"{field}: too long")
    if len(value.encode("utf-8")) > MAX_TEXT_BYTES:
        _fail(f"{field}: UTF-8 byte limit exceeded")
    return value


def _identifier(value: Any, field: str) -> str:
    value = _text(value, field, max_chars=MAX_ID_LEN)
    if not _SAFE_ID.fullmatch(value):
        _fail(f"{field}: invalid identifier")
    return value


def _expect_keys(obj: Any, field: str, allowed: set[str], required: set[str]) -> dict[str, Any]:
    if type(obj) is not dict:
        _fail(f"{field}: expected object")
    keys = set(obj)
    missing = required - keys
    unknown = keys - allowed
    if missing:
        _fail(f"{field}: missing fields {sorted(missing)}")
    if unknown:
        _fail(f"{field}: unknown fields {sorted(unknown)}")
    return obj


def _reject_float(_: str) -> Any:
    _fail("floating point JSON numbers are forbidden")


def _reject_constant(value: str) -> Any:
    _fail(f"non-finite JSON constant forbidden: {value}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            _fail(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: bytes | str) -> Any:
    if isinstance(raw, bytes):
        if len(raw) > MAX_INPUT_BYTES:
            _fail("input exceeds byte limit")
        try:
            text = raw.decode("utf-8", "strict")
        except UnicodeError as exc:
            _fail(f"invalid UTF-8: {exc}")
    elif isinstance(raw, str):
        text = raw
        if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
            _fail("input exceeds byte limit")
    else:
        _fail("raw input must be bytes or string")
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except ContractError:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        _fail(f"invalid JSON: {exc}")


def _depth(value: Any, level: int = 0) -> int:
    if level > MAX_NESTING:
        _fail("JSON nesting exceeds limit")
    if type(value) is dict:
        for k, v in value.items():
            if type(k) is not str:
                _fail("object key must be string")
            _depth(v, level + 1)
    elif type(value) is list:
        for v in value:
            _depth(v, level + 1)
    return level


def canonical_bytes(value: Any) -> bytes:
    _depth(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        _fail(f"not canonical JSON: {exc}")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _parse_time(value: Any, field: str) -> datetime:
    text = _text(value, field, max_chars=64)
    # Require explicit RFC3339 timezone to avoid machine-local interpretation.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        _fail(f"{field}: invalid RFC3339 timestamp: {exc}")
    if dt.tzinfo is None:
        _fail(f"{field}: timezone required")
    dt = dt.astimezone(timezone.utc)
    # Millisecond precision is enough for this challenge envelope and avoids
    # platform-specific string differences.
    return dt.replace(microsecond=(dt.microsecond // 1000) * 1000)


def _format_time(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    millis = dt.microsecond // 1000
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{millis:03d}Z"


def _markdown(text: str) -> str:
    return _MD_META.sub(r"\\\1", text.replace("\r", " ").replace("\n", " "))


def _normalize_tags(value: Any, field: str) -> list[str]:
    if type(value) is not list:
        _fail(f"{field}: expected array")
    if len(value) > MAX_TAGS:
        _fail(f"{field}: too many tags")
    tags: set[str] = set()
    for i, tag in enumerate(value):
        tag = _identifier(tag, f"{field}[{i}]")
        tags.add(tag)
    return sorted(tags)


def normalize_input(raw_value: Any) -> dict[str, Any]:
    obj = _expect_keys(
        raw_value,
        "input",
        {
            "schema_version",
            "exercise_id",
            "episode_gap_ms",
            "required_modalities",
            "sources",
            "events",
            "synthetic",
        },
        {
            "schema_version",
            "exercise_id",
            "episode_gap_ms",
            "required_modalities",
            "sources",
            "events",
            "synthetic",
        },
    )
    if obj["schema_version"] != INPUT_SCHEMA:
        _fail("input.schema_version: unsupported")
    exercise_id = _identifier(obj["exercise_id"], "input.exercise_id")
    gap_ms = _exact_int(obj["episode_gap_ms"], "input.episode_gap_ms", 1, MAX_GAP_MS)
    synthetic = _exact_bool(obj["synthetic"], "input.synthetic")
    # This published source carrier is intentionally synthetic/offline only.
    if synthetic is not True:
        _fail("input.synthetic must be true in this source carrier")

    if type(obj["required_modalities"]) is not list:
        _fail("input.required_modalities: expected array")
    required_modalities: set[str] = set()
    for i, modality in enumerate(obj["required_modalities"]):
        modality = _text(modality, f"input.required_modalities[{i}]", max_chars=16)
        if modality not in MODALITIES:
            _fail(f"input.required_modalities[{i}]: unknown modality")
        required_modalities.add(modality)
    if not required_modalities:
        _fail("input.required_modalities: at least one required")

    sources_raw = obj["sources"]
    if type(sources_raw) is not list or not (1 <= len(sources_raw) <= MAX_SOURCES):
        _fail("input.sources: invalid count")
    sources: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    for i, item in enumerate(sources_raw):
        item = _expect_keys(
            item,
            f"input.sources[{i}]",
            {"source_id", "modality", "sha256", "clock_offset_ms", "description"},
            {"source_id", "modality", "sha256", "clock_offset_ms", "description"},
        )
        sid = _identifier(item["source_id"], f"input.sources[{i}].source_id")
        if sid in source_ids:
            _fail(f"duplicate source_id: {sid}")
        source_ids.add(sid)
        modality = _text(item["modality"], f"input.sources[{i}].modality", max_chars=16)
        if modality not in MODALITIES:
            _fail(f"input.sources[{i}].modality: unknown")
        sha256 = _text(item["sha256"], f"input.sources[{i}].sha256", max_chars=64)
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            _fail(f"input.sources[{i}].sha256: lowercase hex required")
        offset = _exact_int(
            item["clock_offset_ms"],
            f"input.sources[{i}].clock_offset_ms",
            -MAX_OFFSET_MS,
            MAX_OFFSET_MS,
        )
        desc = _text(
            item["description"],
            f"input.sources[{i}].description",
            max_chars=512,
            allow_empty=True,
        )
        sources.append(
            {
                "source_id": sid,
                "modality": modality,
                "sha256": sha256,
                "clock_offset_ms": offset,
                "description": desc,
            }
        )
    sources.sort(key=lambda x: x["source_id"])
    source_by_id = {x["source_id"]: x for x in sources}

    events_raw = obj["events"]
    if type(events_raw) is not list or not (1 <= len(events_raw) <= MAX_EVENTS):
        _fail("input.events: invalid count")
    events: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    for i, item in enumerate(events_raw):
        item = _expect_keys(
            item,
            f"input.events[{i}]",
            {
                "event_id",
                "source_id",
                "observed_at",
                "kind",
                "subject",
                "assertion",
                "confidence_milli",
                "tags",
            },
            {
                "event_id",
                "source_id",
                "observed_at",
                "kind",
                "subject",
                "assertion",
                "confidence_milli",
                "tags",
            },
        )
        eid = _identifier(item["event_id"], f"input.events[{i}].event_id")
        if eid in event_ids:
            _fail(f"duplicate event_id: {eid}")
        event_ids.add(eid)
        sid = _identifier(item["source_id"], f"input.events[{i}].source_id")
        if sid not in source_by_id:
            _fail(f"input.events[{i}].source_id: unknown")
        observed = _parse_time(item["observed_at"], f"input.events[{i}].observed_at")
        corrected = observed + timedelta(milliseconds=source_by_id[sid]["clock_offset_ms"])
        kind = _text(item["kind"], f"input.events[{i}].kind", max_chars=16)
        if kind not in CLAIM_KINDS:
            _fail(f"input.events[{i}].kind: unknown")
        subject = _text(
            item["subject"],
            f"input.events[{i}].subject",
            max_chars=MAX_SUBJECT_LEN,
        )
        assertion = _text(
            item["assertion"],
            f"input.events[{i}].assertion",
            max_chars=MAX_ASSERTION_LEN,
        )
        confidence = _exact_int(
            item["confidence_milli"],
            f"input.events[{i}].confidence_milli",
            0,
            1000,
        )
        tags = _normalize_tags(item["tags"], f"input.events[{i}].tags")
        events.append(
            {
                "event_id": eid,
                "source_id": sid,
                "modality": source_by_id[sid]["modality"],
                "observed_at": _format_time(observed),
                "corrected_at": _format_time(corrected),
                "kind": kind,
                "subject": subject,
                "assertion": assertion,
                "confidence_milli": confidence,
                "tags": tags,
                "source_sha256": source_by_id[sid]["sha256"],
            }
        )
    events.sort(key=lambda x: (x["corrected_at"], x["source_id"], x["event_id"]))

    return {
        "schema_version": INPUT_SCHEMA,
        "exercise_id": exercise_id,
        "episode_gap_ms": gap_ms,
        "required_modalities": sorted(required_modalities),
        "sources": sources,
        "events": events,
        "synthetic": True,
    }


def segment_events(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    events = normalized["events"]
    gap_ms = normalized["episode_gap_ms"]
    episodes: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    prev_time: datetime | None = None
    for event in events:
        current_time = _parse_time(event["corrected_at"], "event.corrected_at")
        if prev_time is not None:
            delta_ms = int((current_time - prev_time).total_seconds() * 1000)
            if delta_ms > gap_ms:
                episodes.append(_make_episode(len(episodes) + 1, current))
                current = []
        current.append(event)
        prev_time = current_time
    if current:
        episodes.append(_make_episode(len(episodes) + 1, current))
    return episodes


def _make_episode(index: int, events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "episode_id": f"episode-{index:04d}",
        "start_at": events[0]["corrected_at"],
        "end_at": events[-1]["corrected_at"],
        "event_ids": [x["event_id"] for x in events],
        "modalities": sorted({x["modality"] for x in events}),
    }


def _build_contradictions(events: list[dict[str, Any]], episode_for: dict[str, str]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], dict[str, list[str]]] = {}
    for event in events:
        # Different observations about one subject can conflict; an observation,
        # decision, action and outcome about that subject are a narrative, not
        # automatically a contradiction. Bind contradiction identity to kind.
        key = (episode_for[event["event_id"]], event["subject"], event["kind"])
        groups.setdefault(key, {}).setdefault(event["assertion"], []).append(event["event_id"])
    out: list[dict[str, Any]] = []
    counter = 1
    for (episode_id, subject, kind), assertions in sorted(groups.items()):
        if len(assertions) < 2:
            continue
        out.append(
            {
                "contradiction_id": f"contradiction-{counter:04d}",
                "episode_id": episode_id,
                "subject": subject,
                "kind": kind,
                "alternatives": [
                    {"assertion": assertion, "event_ids": sorted(ids)}
                    for assertion, ids in sorted(assertions.items())
                ],
                "status": "UNRESOLVED",
            }
        )
        counter += 1
    return out


def build_aar(normalized: dict[str, Any]) -> dict[str, Any]:
    episodes = segment_events(normalized)
    episode_for: dict[str, str] = {}
    for episode in episodes:
        for event_id in episode["event_ids"]:
            episode_for[event_id] = episode["episode_id"]

    claims = [
        {
            "claim_id": f"claim-{i:05d}",
            "episode_id": episode_for[event["event_id"]],
            "kind": event["kind"],
            "subject": event["subject"],
            "assertion": event["assertion"],
            "confidence_milli": event["confidence_milli"],
            "evidence": [
                {
                    "event_id": event["event_id"],
                    "source_id": event["source_id"],
                    "source_sha256": event["source_sha256"],
                    "observed_at": event["observed_at"],
                    "corrected_at": event["corrected_at"],
                }
            ],
        }
        for i, event in enumerate(normalized["events"], start=1)
    ]

    contradictions = _build_contradictions(normalized["events"], episode_for)
    required = set(normalized["required_modalities"])
    coverage = []
    for episode in episodes:
        present = set(episode["modalities"])
        missing = sorted(required - present)
        coverage.append(
            {
                "episode_id": episode["episode_id"],
                "present_modalities": sorted(present),
                "missing_required_modalities": missing,
                "complete": not missing,
            }
        )

    return {
        "schema_version": "evidenceaar-aar/v1",
        "exercise_id": normalized["exercise_id"],
        "episodes": episodes,
        "claims": claims,
        "contradictions": contradictions,
        "coverage": coverage,
        "summary": {
            "episode_count": len(episodes),
            "claim_count": len(claims),
            "contradiction_count": len(contradictions),
            "coverage_complete_episodes": sum(1 for row in coverage if row["complete"]),
        },
        "authority": {
            "synthetic_offline_only": True,
            "operational_exercise_data_processed": False,
            "sponsor_submission_authorized": False,
            "winner_or_award_claimed": False,
            "payment_or_revenue_claimed": False,
        },
    }


def render_markdown(aar: dict[str, Any]) -> str:
    lines = [
        "# EvidenceAAR — " + _markdown(aar["exercise_id"]),
        "",
        "> Synthetic/offline source carrier. No operational-data, submission, award, or payment claim.",
        "",
        "## Executive summary",
        "",
        f"- Episodes: {aar['summary']['episode_count']}",
        f"- Evidence-linked claims: {aar['summary']['claim_count']}",
        f"- Unresolved contradictions: {aar['summary']['contradiction_count']}",
        f"- Coverage-complete episodes: {aar['summary']['coverage_complete_episodes']}",
        "",
    ]
    claims_by_episode: dict[str, list[dict[str, Any]]] = {}
    for claim in aar["claims"]:
        claims_by_episode.setdefault(claim["episode_id"], []).append(claim)
    coverage_by_episode = {x["episode_id"]: x for x in aar["coverage"]}

    for episode in aar["episodes"]:
        eid = episode["episode_id"]
        lines += [
            f"## {eid}",
            "",
            f"- Window: `{episode['start_at']}` → `{episode['end_at']}`",
            f"- Modalities: {', '.join(episode['modalities'])}",
        ]
        coverage = coverage_by_episode[eid]
        if coverage["missing_required_modalities"]:
            lines.append(
                "- Coverage gap: " + ", ".join(_markdown(x) for x in coverage["missing_required_modalities"])
            )
        else:
            lines.append("- Coverage: complete")
        lines.append("")
        for claim in claims_by_episode.get(eid, []):
            evidence = claim["evidence"][0]
            lines += [
                "### " + claim["kind"] + " · " + _markdown(claim["subject"]),
                "",
                _markdown(claim["assertion"]),
                "",
                f"Evidence: `{evidence['event_id']}` / `{evidence['source_id']}` / `{evidence['source_sha256']}` / corrected `{evidence['corrected_at']}`",
                "",
            ]

    lines += ["## Contradiction ledger", ""]
    if not aar["contradictions"]:
        lines += ["No contradictory assertions detected by the deterministic subject/episode rule.", ""]
    else:
        for row in aar["contradictions"]:
            lines.append(
                f"- **{row['contradiction_id']}** · `{row['episode_id']}` · "
                + _markdown(row["subject"]) + " · UNRESOLVED"
            )
            for alt in row["alternatives"]:
                lines.append(
                    "  - " + _markdown(alt["assertion"]) + " — events "
                    + ", ".join(f"`{x}`" for x in alt["event_ids"])
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(aar: dict[str, Any]) -> str:
    claims_by_episode: dict[str, list[dict[str, Any]]] = {}
    for claim in aar["claims"]:
        claims_by_episode.setdefault(claim["episode_id"], []).append(claim)
    coverage_by_episode = {x["episode_id"]: x for x in aar["coverage"]}
    parts = [
        "<!doctype html>",
        '<html lang="en"><meta charset="utf-8">',
        "<title>EvidenceAAR</title>",
        "<body>",
        "<h1>EvidenceAAR — " + html.escape(aar["exercise_id"]) + "</h1>",
        "<p><strong>Synthetic/offline source carrier.</strong> "
        "No operational-data, submission, award, or payment claim.</p>",
        "<h2>Executive summary</h2>",
        "<ul>",
        f"<li>Episodes: {aar['summary']['episode_count']}</li>",
        f"<li>Evidence-linked claims: {aar['summary']['claim_count']}</li>",
        f"<li>Unresolved contradictions: {aar['summary']['contradiction_count']}</li>",
        f"<li>Coverage-complete episodes: {aar['summary']['coverage_complete_episodes']}</li>",
        "</ul>",
    ]
    for episode in aar["episodes"]:
        eid = episode["episode_id"]
        parts += [
            f"<h2>{html.escape(eid)}</h2>",
            "<p>Window: <code>" + html.escape(episode["start_at"]) + "</code> → " +
            "<code>" + html.escape(episode["end_at"]) + "</code></p>",
            "<p>Modalities: " + html.escape(", ".join(episode["modalities"])) + "</p>",
        ]
        coverage = coverage_by_episode[eid]
        if coverage["missing_required_modalities"]:
            parts.append(
                "<p>Coverage gap: "
                + html.escape(", ".join(coverage["missing_required_modalities"]))
                + "</p>"
            )
        else:
            parts.append("<p>Coverage: complete</p>")
        for claim in claims_by_episode.get(eid, []):
            evidence = claim["evidence"][0]
            parts += [
                "<h3>" + html.escape(claim["kind"]) + " · " + html.escape(claim["subject"]) + "</h3>",
                "<p>" + html.escape(claim["assertion"]) + "</p>",
                "<p>Evidence: "
                + "<code>" + html.escape(evidence["event_id"]) + "</code> / "
                + "<code>" + html.escape(evidence["source_id"]) + "</code> / "
                + "<code>" + html.escape(evidence["source_sha256"]) + "</code> / corrected "
                + "<code>" + html.escape(evidence["corrected_at"]) + "</code></p>",
            ]
    parts.append("<h2>Contradiction ledger</h2>")
    if not aar["contradictions"]:
        parts.append("<p>No contradictory assertions detected.</p>")
    else:
        parts.append("<ul>")
        for row in aar["contradictions"]:
            parts.append(
                "<li><strong>"
                + html.escape(row["contradiction_id"])
                + "</strong> · "
                + html.escape(row["episode_id"])
                + " · "
                + html.escape(row["subject"])
                + " · UNRESOLVED<ul>"
            )
            for alt in row["alternatives"]:
                parts.append(
                    "<li>"
                    + html.escape(alt["assertion"])
                    + " — Events "
                    + ", ".join(f"<code>{html.escape(x)}</code>" for x in alt["event_ids"])
                    + "</li>"
                )
            parts.append("</ul></li>")
        parts.append("</ul>")
    parts += ["</body></html>"]
    return "\n".join(parts) + "\n"


def compile_bundle(raw : bytes | str) -> dict[str, Any]:
    parsed = strict_json_loads(raw)
    normalized = normalize_input(parsed)
    aar = build_aar(normalized)
    markdown = render_markdown(aar)
    html_doc = render_html(aar)
    input_sha = hashlib.sha256(raw if isinstance(raw, bytes) else raw.encode("utf-8")).hexdigest()
    normalized_sha = digest(normalized)
    aar_sha = digest(aar)
    markdown_sha = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    html_sha = hashlib.sha256(html_doc.encode("utf-8")).hexdigest()
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "engine_version": ENGINE_VERSION,
        "input_sha256": input_sha,
        "normalized_sha256": normalized_sha,
        "aar_sha256": aar_sha,
        "markdown_sha256": markdown_sha,
        "html_sha256": html_sha,
        "exercise_id": normalized["exercise_id"],
        "event_count": len(normalized["events"]),
        "source_count": len(normalized["sources"]),
        "authority": aar["authority"],
    }
    return {
        "schema_version": BUNDLE_SCHEMA,
        "engine_version": ENGINE_VERSION,
        "normalized": normalized,
        "aar": aar,
        "markdown": markdown,
        "html": html_doc,
        "receipt": receipt,
        "bundle_sha256": "",  # set below without self-reference
    } | {}


def finalize_bundle(raw: bytes | str) -> dict[str, Any]:
    bundle = compile_bundle(raw)
    body = {k: v for k, v in bundle.items() if k != "bundle_sha256"}
    bundle["bundle_sha256"] = digest(body)
    return bundle


def verify_bundle(raw : bytes | str, bundle_value: Any) -> None:
    _expect_keys(
        bundle_value,
        "bundle",
        {
            "schema_version",
            "engine_version",
            "normalized",
            "aar",
            "markdown",
            "html",
            "receipt",
            "bundle_sha256",
        },
        {
            "schema_version",
            "engine_version",
            "normalized",
            "aar",
            "markdown",
            "html",
            "receipt",
            "bundle_sha256",
        },
    )
    if bundle_value["schema_version"] != BUNDLE_SCHEMA:
        _fail("bundle.schema_version: unsupported")
    if bundle_value["engine_version"] != ENGINE_VERSION:
        _fail("bundle.engine_version: unsupported")
    expected = finalize_bundle(raw)
    if canonical_bytes(bundle_value) != canonical_bytes(expected):
        _fail("bundle does not exactly recompute from input")


def _read(path: str) -> bytes:
    p = Path(path)
    try:
        if p.is_symlink() or not p.is_file():
            _fail(f"{path}: regular file required")
        raw = p.read_bytes()
    except OSError as exc:
        _fail(f"{path}: read failed: {exc}")
    if len(raw) > MAX_INPUT_BYTES:
        _fail(f"{path}: exceeds byte limit")
    return raw


def _write_new(path: Path, data: bytes) -> None:
    # This is a source/demo helper, not a privilege boundary. Still create
    # exclusively so a run cannot silently overwrite prior evidence.
    try:
        with path.open("xb") as f:
            f.write(data)
            f.flush()
    except FileExistsError:
        _fail(f"{path}: already exists")
    except OSError as exc:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        _fail(f"{path}: write failed: {exc}")


def command_compile(args: argparse.Namespace) -> int:
    raw = _read(args.input)
    bundle = finalize_bundle(raw)
    encoded = canonical_bytes(bundle) + b"\n"
    if args.output == "-":
        sys.stdout.buffer.write(encoded)
    else:
        _write_new(Path(args.output), encoded)
    return 0


def command_verify(args: argparse.Namespace) -> int:
    raw = _read(args.input)
    bundle_raw = _read(args.bundle)
    bundle = strict_json_loads(bundle_raw)
    verify_bundle(raw, bundle)
    print("VERIFIED")
    return 0


def command_render(args: argparse.Namespace) -> int:
    raw = _read(args.input)
    bundle = finalize_bundle(raw)
    out = Path(args.output_dir)
    if out.exists():
        _fail(f"{out}: output directory already exists")
    try:
        out.mkdir()
        _write_new(out / "aar.json", canonical_bytes(bundle["aar"]) + b"\n")
        _write_new(out / "aar.md", bundle["markdown"].encode("utf-8"))
        _write_new(out / "aar.html", bundle["html"].encode("utf-8"))
        _write_new(out / "receipt.json", canonical_bytes(bundle["receipt"]) + b"\n")
        _write_new(out / "bundle.json", canonical_bytes(bundle) + b"\n")
    except Exception:
        # Only remove the directory if every child is one of our fixed names.
        try:
            for child in out.iterdir():
                if child.name in {"aar.json", "aar.md", "aar.html", "receipt.json", "bundle.json"}:
                    child.unlink(missing_ok=True)
            out.rmdir()
        except OSError:
            pass
        raise
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="EvidenceAAR deterministic offline Digital Scribe")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile")
    c.add_argument("input")
    c.add_argument("-o", "--output", default="-")
    c.set_defaults(fn=command_compile)
    v = sub.add_parser("verify")
    v.add_argument("input")
    v.add_argument("bundle")
    v.set_defaults(fn=command_verify)
    r = sub.add_parser("render")
    r.add_argument("input")
    r.add_argument("output_dir")
    r.set_defaults(fn=command_render)
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        return args.fn(args)
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
