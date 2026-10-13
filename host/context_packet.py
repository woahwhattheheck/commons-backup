"""Deterministic bounded context packets for Commons worker handoff."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

try:
    from host.git_source_capsules import GitSourceError, LIVE_DRIFT_KEYS, collect_git_source
except ModuleNotFoundError:
    from git_source_capsules import GitSourceError, LIVE_DRIFT_KEYS, collect_git_source

SCHEMA = "commons-context-packet/v1"
DIGEST_KEY = "semantic_sha256"
STOP_TERMS = {"commons", "build", "revenue", "agent", "agents", "host", "ground", "tests", "json", "html", "python", "issue", "feature"}
SPLIT = re.compile(r"[^a-z0-9]+")


class PacketError(ValueError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _text(value: Any, limit: int) -> tuple[str, bool]:
    text = " ".join(str(value or "").split())
    return (text, False) if len(text) <= limit else (text[: limit - 1] + "…", True)


def _bounded(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        text, cut = _text(value, 500)
        return {"text": text, "truncated": cut}
    if isinstance(value, Mapping):
        return {str(key): _bounded(value[key], depth + 1) for key in sorted(value, key=str)}
    if isinstance(value, list):
        out = [_bounded(item, depth + 1) for item in value[:64]]
        if len(value) > 64:
            out.append({"omitted_items": len(value) - 64})
        return out
    if isinstance(value, str):
        text, cut = _text(value, 1600)
        return {"text": text, "truncated": True} if cut else text
    return value if value is None or isinstance(value, (bool, int, float)) else str(value)


def _terms(operation: str, terms: Sequence[str], paths: Sequence[str]) -> list[str]:
    found = set()
    for raw in (operation, *terms, *paths):
        for token in SPLIT.split(str(raw).casefold()):
            if len(token) >= 3 and not token.isdigit() and token not in STOP_TERMS:
                found.add(token)
    return sorted(found)[:32]


def _score(row: Any, operation: str, terms: Sequence[str]) -> int:
    try:
        hay = canonical(row).casefold()
    except (TypeError, ValueError):
        hay = str(row).casefold()
    score = 4000 if operation.casefold() in hay else 0
    score += sum(40 + min(hay.count(term), 4) for term in terms if term in hay)
    if isinstance(row, Mapping):
        key = str(row.get("key") or row.get("operation") or row.get("id") or "")
        if key == operation:
            score += 8000
    return score


def _timestamp(value: Any) -> Decimal | None:
    """Comparable exact seconds for aware ISO dates and Slack epoch timestamps."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        seconds = Decimal(str(value))
        if seconds.is_finite() and Decimal(-62135596800) <= seconds < Decimal(253402300800):
            return seconds
        return None
    except InvalidOperation:
        pass
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        elapsed = stamp - datetime(1970, 1, 1, tzinfo=timezone.utc)
        return Decimal(elapsed.days * 86400 + elapsed.seconds) + Decimal(elapsed.microseconds) / 1_000_000
    except (ValueError, OverflowError):
        return None


def _sort(rows: Iterable[dict[str, Any] | None]) -> list[dict[str, Any]]:
    rows = [row for row in rows if row]
    identity = lambda row: str(row.get("id") or row.get("key") or row.get("name") or row.get("number") or canonical(row))
    def stamp(row: Mapping[str, Any]) -> tuple[bool, Decimal]:
        for key in ("durable_ts", "updated_at", "heartbeat_at", "ts"):
            parsed = _timestamp(row.get(key))
            if parsed is not None:
                return True, parsed
        return False, Decimal(0)

    rows.sort(key=identity)
    rows.sort(key=stamp, reverse=True)
    rows.sort(key=lambda row: int(row.get("_score", 0)), reverse=True)
    return rows


def _pick(
    row: Mapping[str, Any],
    fields: Sequence[str],
    operation: str,
    terms: Sequence[str],
    text_field: str | None = None,
) -> dict[str, Any] | None:
    score = _score(row, operation, terms)
    if score <= 0:
        return None
    out = {key: row[key] for key in fields if row.get(key) not in (None, "")}
    if text_field and text_field in out:
        out[text_field], cut = _text(out[text_field], 1200 if text_field == "body" else 800)
        if cut:
            out[text_field + "_truncated"] = True
    out["_score"] = score
    return out


def _coord_rows(value: Any) -> Iterable[Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return
    for key in ("pull_requests", "prs", "lanes", "work_items", "items", "queue", "open"):
        rows = value.get(key)
        if isinstance(rows, list):
            yield from (row for row in rows if isinstance(row, Mapping))
        elif isinstance(rows, Mapping):
            yield from (row for row in rows.values() if isinstance(row, Mapping))


def _source_shell(bundle: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source = {
        "commit": bundle["commit"],
        "tree_sha": bundle["tree_sha"],
        "max_file_bytes": bundle["max_file_bytes"],
        "requested_paths": list(bundle["requested_paths"]),
        "capsules": [],
    }
    candidates: list[dict[str, Any]] = []
    for raw in bundle["capsules"]:
        meta = {
            "path": raw["path"],
            "mode": raw["mode"],
            "blob_sha": raw["blob_sha"],
            "content_sha256": raw["content_sha256"],
            "bytes": raw["bytes"],
        }
        if raw.get("text") is None:
            meta["text_included"] = False
            meta["omission_reason"] = raw.get("source_omission_reason") or "NON_TEXT"
        else:
            meta["text_included"] = False
            meta["omission_reason"] = "PACKET_BUDGET"
            candidates.append({"meta": meta, "text": raw["text"]})
        source["capsules"].append(meta)
    return source, candidates


def compile_packet(
    *,
    operation: str,
    objective: str,
    pulse: Mapping[str, Any],
    recent: Sequence[Mapping[str, Any]],
    ledger: Mapping[str, Any],
    claims: Sequence[Mapping[str, Any]] = (),
    coordination: Mapping[str, Any] | None = None,
    explicit_terms: Sequence[str] = (),
    paths: Sequence[str] = (),
    requested_main_head: str | None = None,
    provenance: Sequence[Mapping[str, Any]] = (),
    git_repository: str | Path | None = None,
    source_commit: str | None = None,
    source_paths: Sequence[str] = (),
    max_source_file_bytes: int = 16_384,
    max_chars: int = 12_000,
    max_events: int = 12,
    max_resources: int = 12,
    max_claims: int = 6,
    max_coordination: int = 8,
) -> dict[str, Any]:
    operation = str(operation).strip()
    if not operation or len(operation) > 240:
        raise PacketError("operation must be 1..240 characters")
    objective, objective_cut = _text(objective, 1800)
    if not objective:
        raise PacketError("objective is required")
    if type(max_chars) is not int or max_chars < 2048:
        raise PacketError("max_chars must be >= 2048")
    limits = {
        "max_chars": max_chars,
        "max_events": max(0, int(max_events)),
        "max_resources": max(0, int(max_resources)),
        "max_claims": max(0, int(max_claims)),
        "max_coordination": max(0, int(max_coordination)),
    }
    if any(v > 256 for k, v in limits.items() if k != "max_chars"):
        raise PacketError("section item limits must be <= 256")
    paths = sorted({str(path).strip() for path in paths if str(path).strip()})[:32]
    terms = _terms(operation, explicit_terms, paths)
    clean_prov = _bounded(list(provenance))
    pulse_clean = _bounded(dict(pulse))
    observed = str(pulse.get("head") or "")
    match = None if not (requested_main_head and observed) else hmac.compare_digest(str(requested_main_head), observed)

    source_requested = bool(git_repository is not None or source_commit is not None or source_paths)
    source_bundle: dict[str, Any] | None = None
    source_candidates: list[dict[str, Any]] = []
    if source_requested:
        if git_repository is None or source_commit is None or not source_paths:
            raise PacketError("git_repository, source_commit and source_paths are required together")
        try:
            raw_bundle = collect_git_source(
                git_repository,
                source_commit,
                source_paths,
                max_file_bytes=max_source_file_bytes,
            )
        except GitSourceError as exc:
            raise PacketError(f"git source: {exc}") from exc
        source_bundle, source_candidates = _source_shell(raw_bundle)

    event_fields = ("id", "from", "to", "ts", "durable_ts", "state", "kind", "lane", "href", "body")
    resource_fields = ("name", "kind", "stage", "condition", "consumer", "next_action", "last_used_at", "stale_after", "href", "url")
    claim_fields = ("key", "holder", "state", "taken_at", "heartbeat_at", "ttl_s", "note")
    coord_fields = (
        "operation", "id", "number", "title", "url", "state", "status", "head_sha", "head", "base_sha", "base",
        "content_key", "next_action", "holder", "updated_at", "drift", "verdicts", "hosted",
    )

    pools = {
        "claims": _sort(_pick(r, claim_fields, operation, terms, "note") for r in claims if isinstance(r, Mapping)),
        "coordination": _sort(_pick(r, coord_fields, operation, terms) for r in _coord_rows(coordination or {})),
        "recent": _sort(_pick(r, event_fields, operation, terms, "body") for r in recent if isinstance(r, Mapping)),
        "resources": _sort(_pick(r, resource_fields, operation, terms) for r in (ledger.get("surfaces") or []) if isinstance(r, Mapping)),
    }
    caps = {
        "claims": limits["max_claims"],
        "coordination": limits["max_coordination"],
        "recent": limits["max_events"],
        "resources": limits["max_resources"],
    }
    packet: dict[str, Any] = {
        "schema": SCHEMA,
        "operation": operation,
        "objective": objective,
        "selection": {"terms": terms, "paths": paths},
        "source_fence": {
            "pulse_head": pulse_clean.get("head") if isinstance(pulse_clean, Mapping) else None,
            "pulse_seq": pulse_clean.get("seq") if isinstance(pulse_clean, Mapping) else None,
            "pulse_ts": pulse_clean.get("ts") if isinstance(pulse_clean, Mapping) else None,
            "requested_main_head": requested_main_head,
            "pulse_matches_requested_main": match,
        },
        "claims": [],
        "coordination": [],
        "recent": [],
        "resources": [],
        "omitted": {},
        "limits": limits,
        "provenance": clean_prov,
    }
    if source_bundle is not None:
        packet["git_source"] = source_bundle
    if objective_cut:
        packet["objective_truncated"] = True

    def refresh() -> None:
        omitted: dict[str, int] = {
            name: max(0, len(pools[name]) - len(packet[name])) for name in pools
        }
        if source_bundle is not None:
            omitted_files = 0
            omitted_bytes = 0
            for row in source_bundle["capsules"]:
                if not row.get("text_included"):
                    omitted_files += 1
                    omitted_bytes += int(row["bytes"])
            omitted["git_source_text_files"] = omitted_files
            omitted["git_source_text_bytes"] = omitted_bytes
        packet["omitted"] = omitted

    def size() -> int:
        probe = dict(packet)
        probe[DIGEST_KEY] = "0" * 64
        return len(canonical(probe))

    def append_rows(name: str) -> None:
        for row in pools[name][: caps[name]]:
            clean = _bounded({k: v for k, v in row.items() if not k.startswith("_")})
            packet[name].append(clean)
            refresh()
            if size() > max_chars:
                packet[name].pop()
                refresh()

    refresh()
    if size() > max_chars:
        raise PacketError("max_chars is too small for packet metadata/provenance/source metadata")

    append_rows("claims")
    append_rows("coordination")

    if source_bundle is not None:
        by_path = {row["path"]: row for row in source_bundle["capsules"]}
        for candidate in sorted(source_candidates, key=lambda row: row["meta"]["path"]):
            row = by_path[candidate["meta"]["path"]]
            old_reason = row["omission_reason"]
            row["text"] = candidate["text"]
            row["text_included"] = True
            row.pop("omission_reason", None)
            refresh()
            if size() > max_chars:
                row.pop("text", None)
                row["text_included"] = False
                row["omission_reason"] = old_reason
                refresh()

    append_rows("recent")
    append_rows("resources")

    packet[DIGEST_KEY] = digest(packet)
    if len(canonical(packet)) > max_chars:
        raise PacketError("packet exceeded max_chars after digest")
    return packet


def verify_packet(packet: Mapping[str, Any]) -> tuple[bool, str]:
    if packet.get("schema") != SCHEMA:
        return False, "schema"
    supplied = packet.get(DIGEST_KEY)
    if not isinstance(supplied, str) or not re.fullmatch(r"[0-9a-f]{64}", supplied):
        return False, "digest-format"
    semantic = {k: v for k, v in packet.items() if k != DIGEST_KEY}
    if not hmac.compare_digest(supplied, digest(semantic)):
        return False, "digest-mismatch"
    max_chars = (packet.get("limits") or {}).get("max_chars")
    if type(max_chars) is not int or len(canonical(packet)) > max_chars:
        return False, "budget"
    source = packet.get("git_source")
    if source is not None:
        if not isinstance(source, Mapping):
            return False, "git-source-shape"
        required = {"commit", "tree_sha", "max_file_bytes", "requested_paths", "capsules"}
        if set(source) != required:
            return False, "git-source-shape"
        if not isinstance(source.get("requested_paths"), list) or not isinstance(source.get("capsules"), list):
            return False, "git-source-shape"
        if len(source["requested_paths"]) != len(source["capsules"]):
            return False, "git-source-count"
        if [row.get("path") for row in source["capsules"] if isinstance(row, Mapping)] != source["requested_paths"]:
            return False, "git-source-order"
        commit = source.get("commit")
        tree_sha = source.get("tree_sha")
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            return False, "git-source-commit"
        if not isinstance(tree_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", tree_sha):
            return False, "git-source-tree"
        for row in source["capsules"]:
            if not isinstance(row, Mapping):
                return False, "git-source-capsule-shape"
            if row.get("text_included") is True:
                if not isinstance(row.get("text"), str) or "omission_reason" in row:
                    return False, "git-source-text-shape"
            elif row.get("text_included") is False:
                if "text" in row or not isinstance(row.get("omission_reason"), str):
                    return False, "git-source-omission-shape"
            else:
                return False, "git-source-inclusion-flag"
    return True, "ok"


def _validated_live_drift(source: Mapping[str, Any], drift: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if drift is None:
        return None
    if type(drift) is not dict or set(drift) != LIVE_DRIFT_KEYS:
        raise PacketError("invalid live Git drift observation")
    observed = drift.get("observed_current_main_head")
    matches = drift.get("source_commit_matches_current_main")
    if observed is not None and (type(observed) is not str or not re.fullmatch(r"[0-9a-f]{40}", observed)):
        raise PacketError("invalid live Git main head")
    expected = None if observed is None else hmac.compare_digest(str(source.get("commit")), observed)
    if matches is not expected:
        raise PacketError("inconsistent live Git drift observation")
    return drift


def markdown(packet: Mapping[str, Any], *, live_git_drift: Mapping[str, Any] | None = None) -> str:
    ok, reason = verify_packet(packet)
    if not ok:
        raise PacketError(f"cannot render invalid packet: {reason}")
    fence = packet.get("source_fence") or {}
    lines = [
        "# Commons context packet",
        "",
        f"- **Operation:** `{packet.get('operation', '')}`",
        f"- **Digest:** `{packet.get(DIGEST_KEY, '')}`",
        f"- **Pulse:** seq `{fence.get('pulse_seq')}` · head `{fence.get('pulse_head')}`",
    ]
    if fence.get("requested_main_head"):
        lines.append(
            f"- **Requested main:** `{fence.get('requested_main_head')}` · "
            f"pulse match `{fence.get('pulse_matches_requested_main')}`"
        )
    source = packet.get("git_source")
    if isinstance(source, Mapping):
        lines.append(f"- **Git source commit:** `{source.get('commit', '')}`")
        drift = _validated_live_drift(source, live_git_drift)
        if drift is not None:
            lines.append(
                f"- **Observed current main (live, unsealed):** "
                f"`{drift.get('observed_current_main_head')}` · same as source "
                f"`{drift.get('source_commit_matches_current_main')}`"
            )
    elif live_git_drift is not None:
        raise PacketError("live Git drift requires git_source")
    lines += ["", "## Objective", "", str(packet.get("objective") or "")]
    if packet.get("claims"):
        lines += ["", "## Ownership / claims", ""]
        for row in packet["claims"]:
            lines.append(
                f"- `{row.get('key', '')}` · holder `{row.get('holder', '')}` · "
                f"state `{row.get('state', '')}` · heartbeat `{row.get('heartbeat_at', '')}`"
            )
            if row.get("note"):
                lines.append(f"  - {row['note']}")
    if packet.get("coordination"):
        lines += ["", "## Coordination", ""]
        for row in packet["coordination"]:
            ident = row.get("operation") or row.get("id") or row.get("number") or row.get("title") or "row"
            lines.append(f"- **{ident}** — `{canonical(row)}`")
    if isinstance(source, Mapping):
        lines += ["", "## Exact Git source capsules", ""]
        for row in source.get("capsules") or []:
            status = "included" if row.get("text_included") else f"omitted:{row.get('omission_reason')}"
            lines.append(
                f"- `{row.get('path', '')}` · mode `{row.get('mode', '')}` · blob `{row.get('blob_sha', '')}` · "
                f"sha256 `{row.get('content_sha256', '')}` · bytes `{row.get('bytes')}` · {status}"
            )
            if row.get("text_included"):
                source_text = row.get("text", "")
                longest = max((len(match.group(0)) for match in re.finditer(r"`+", source_text)), default=0)
                source_fence = "`" * max(3, longest + 1)
                lines += ["", f"{source_fence}text", source_text, source_fence]
    if packet.get("recent"):
        lines += ["", "## Relevant durable events", ""]
        for row in packet["recent"]:
            lines.append(
                f"- `{row.get('id', '')}` · {row.get('durable_ts') or row.get('ts') or ''} · "
                f"{row.get('from', '')}: {row.get('body', '')}"
            )
    if packet.get("resources"):
        lines += ["", "## Relevant resources", ""]
        for row in packet["resources"]:
            detail = " · ".join(
                str(row.get(k)) for k in ("kind", "stage", "condition") if row.get(k) not in (None, "")
            )
            lines.append(f"- **{row.get('name', '')}**{(' · ' + detail) if detail else ''}")
            if row.get("next_action"):
                lines.append(f"  - next: {row['next_action']}")
    lines += ["", "## Omissions / bounds", "", f"`{canonical(packet.get('omitted') or {})}`"]
    if packet.get("provenance"):
        lines += ["", "## Provenance", ""]
        for row in packet["provenance"]:
            lines.append(f"- **{row.get('source', 'source')}** · `{row.get('path', '')}` · `{row.get('sha256', '')}`")
    return "\n".join(lines) + "\n"
