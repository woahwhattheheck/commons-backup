"""Fail-closed offline authority for Swarm seat identity selection.

The guard consumes a normalized, complete Slack identity census produced by a
separate collector. It never searches Slack, posts messages, or mutates source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

CENSUS_SCHEMA = "swarm-identity-census/v1"
DECISION_SCHEMA = "swarm-identity-decision/v1"
MAX_ROWS = 10000
MAX_PROPOSALS = 64
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,95}$")


class IdentityGuardError(ValueError):
    """Raised when identity evidence is malformed or non-authoritative."""


def _pairs_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise IdentityGuardError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(token: str) -> None:
    raise IdentityGuardError(f"non-finite JSON number: {token}")


def loads_strict(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_pairs_object, parse_constant=_reject_constant)
    except IdentityGuardError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise IdentityGuardError("invalid JSON") from exc


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise IdentityGuardError("value is not canonical-JSON serializable") from exc


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _exact_keys(obj: Mapping[str, Any], *, required: set[str], optional: set[str] = set(), where: str) -> None:
    keys = set(obj)
    missing = required - keys
    extra = keys - required - optional
    if missing:
        raise IdentityGuardError(f"{where}: missing keys {sorted(missing)}")
    if extra:
        raise IdentityGuardError(f"{where}: unexpected keys {sorted(extra)}")


def _safe_token(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise IdentityGuardError(f"{field}: must be string")
    normalized = unicodedata.normalize("NFKC", value)
    if normalized != value:
        raise IdentityGuardError(f"{field}: must already be NFKC-normalized")
    if not value.isascii() or not _ID_RE.fullmatch(value):
        raise IdentityGuardError(f"{field}: unsafe identity token")
    return value.casefold()


def _display_token(value: Any, *, field: str) -> str:
    _safe_token(value, field=field)
    return value


def _parse_time(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise IdentityGuardError(f"{field}: must be non-empty RFC3339 string")
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise IdentityGuardError(f"{field}: invalid RFC3339 timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise IdentityGuardError(f"{field}: timezone required")
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _string_list(value: Any, *, field: str, max_items: int = 32) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > max_items:
        raise IdentityGuardError(f"{field}: must be list with <= {max_items} items")
    seen: set[str] = set()
    result: list[str] = []
    for i, item in enumerate(value):
        display = _display_token(item, field=f"{field}[{i}]")
        canon = display.casefold()
        if canon in seen:
            raise IdentityGuardError(f"{field}: duplicate identity token")
        seen.add(canon)
        result.append(display)
    return tuple(result)


@dataclass(frozen=True)
class Row:
    seat_id: str
    lineage: str
    aliases: tuple[str, ...]
    first_seen: datetime
    last_seen: datetime

    @property
    def identity_tokens(self) -> frozenset[str]:
        return frozenset([self.seat_id.casefold(), *(a.casefold() for a in self.aliases)])


@dataclass(frozen=True)
class Proposal:
    seat_id: str
    lineage: str
    aliases: tuple[str, ...]

    @property
    def identity_tokens(self) -> frozenset[str]:
        return frozenset([self.seat_id.casefold(), *(a.casefold() for a in self.aliases)])


def _parse_row(raw: Any, index: int, *, as_of: datetime) -> Row:
    if not isinstance(raw, dict):
        raise IdentityGuardError(f"rows[{index}]: must be object")
    _exact_keys(
        raw,
        required={"seat_id", "lineage", "aliases", "first_seen", "last_seen"},
        where=f"rows[{index}]",
    )
    seat = _display_token(raw["seat_id"], field=f"rows[{index}].seat_id")
    lineage = _display_token(raw["lineage"], field=f"rows[{index}].lineage")
    aliases = _string_list(raw["aliases"], field=f"rows[{index}].aliases")
    first = _parse_time(raw["first_seen"], field=f"rows[{index}].first_seen")
    last = _parse_time(raw["last_seen"], field=f"rows[{index}].last_seen")
    if first > last:
        raise IdentityGuardError(f"rows[{index}]: first_seen after last_seen")
    if last > as_of:
        raise IdentityGuardError(f"rows[{index}]: last_seen after census as_of")
    if seat.casefold() in {a.casefold() for a in aliases}:
        raise IdentityGuardError(f"rows[{index}]: seat_id repeated as alias")
    return Row(seat, lineage, aliases, first, last)


def _parse_proposal(raw: Any, index: int) -> Proposal:
    if not isinstance(raw, dict):
        raise IdentityGuardError(f"proposals[{index}]: must be object")
    _exact_keys(raw, required={"seat_id", "lineage", "aliases"}, where=f"proposals[{index}]")
    seat = _display_token(raw["seat_id"], field=f"proposals[{index}].seat_id")
    lineage = _display_token(raw["lineage"], field=f"proposals[{index}].lineage")
    aliases = _string_list(raw["aliases"], field=f"proposals[{index}].aliases")
    if seat.casefold() in {a.casefold() for a in aliases}:
        raise IdentityGuardError(f"proposals[{index}]: seat_id repeated as alias")
    return Proposal(seat, lineage, aliases)


def _dedupe_rows(rows: Sequence[Row]) -> tuple[tuple[Row, ...], int]:
    by_id: dict[str, Row] = {}
    duplicates = 0
    for row in rows:
        key = row.seat_id.casefold()
        prior = by_id.get(key)
        if prior is None:
            by_id[key] = row
            continue
        if prior != row:
            raise IdentityGuardError(f"conflicting census rows for seat_id {row.seat_id}")
        duplicates += 1
    return tuple(sorted(by_id.values(), key=lambda row: row.seat_id.casefold())), duplicates


def _validate_census(
    census: Any,
    *,
    evaluated_at: datetime,
    max_age_seconds: int,
    max_future_skew_seconds: int,
) -> tuple[tuple[Row, ...], dict[str, Any]]:
    if not isinstance(census, dict):
        raise IdentityGuardError("census: must be object")
    _exact_keys(
        census,
        required={"schema", "complete", "next_cursor", "query_id", "captured_at", "as_of", "rows"},
        where="census",
    )
    if census["schema"] != CENSUS_SCHEMA:
        raise IdentityGuardError("census: unsupported schema")
    if census["complete"] is not True:
        raise IdentityGuardError("census: complete must be true")
    if census["next_cursor"] is not None:
        raise IdentityGuardError("census: pagination not exhausted")
    query_id = _display_token(census["query_id"], field="census.query_id")
    captured = _parse_time(census["captured_at"], field="census.captured_at")
    as_of = _parse_time(census["as_of"], field="census.as_of")
    if as_of > captured:
        raise IdentityGuardError("census: as_of after captured_at")
    future_skew = (captured - evaluated_at).total_seconds()
    if future_skew > max_future_skew_seconds:
        raise IdentityGuardError("census: captured_at too far in future")
    age = (evaluated_at - as_of).total_seconds()
    if age < -max_future_skew_seconds:
        raise IdentityGuardError("census: as_of too far in future")
    if age > max_age_seconds:
        raise IdentityGuardError("census: stale")
    raw_rows = census["rows"]
    if not isinstance(raw_rows, list) or len(raw_rows) > MAX_ROWS:
        raise IdentityGuardError(f"census.rows: must be list with <= {MAX_ROWS} rows")
    rows = [_parse_row(raw, i, as_of=as_of) for i, raw in enumerate(raw_rows)]
    deduped, duplicate_count = _dedupe_rows(rows)
    meta = {
        "query_id": query_id,
        "captured_at": _iso(captured),
        "as_of": _iso(as_of),
        "row_count": len(deduped),
        "exact_duplicate_rows": duplicate_count,
    }
    return deduped, meta


def _collision_reasons(proposal: Proposal, rows: Sequence[Row]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    candidate_tokens = proposal.identity_tokens
    candidate_lineage = proposal.lineage.casefold()
    for row in rows:
        row_lineage = row.lineage.casefold()
        overlap = candidate_tokens & row.identity_tokens
        if overlap:
            results.append({
                "code": "IDENTITY_TOKEN_COLLISION",
                "existing_seat_id": row.seat_id,
                "matched_token": sorted(overlap)[0],
            })
        if candidate_lineage == row_lineage:
            results.append({
                "code": "LINEAGE_COLLISION",
                "existing_seat_id": row.seat_id,
                "matched_lineage": row.lineage,
            })
        # Lineages and aliases share one human-visible namespace. A candidate alias
        # that reuses an old lineage (or a new lineage that reuses an old alias)
        # is still blurry even when the full seat ids differ.
        if row_lineage in candidate_tokens:
            results.append({
                "code": "IDENTITY_REUSES_EXISTING_LINEAGE",
                "existing_seat_id": row.seat_id,
                "matched_lineage": row.lineage,
            })
        row_identity_tokens = row.identity_tokens
        if candidate_lineage in row_identity_tokens:
            results.append({
                "code": "LINEAGE_REUSES_EXISTING_IDENTITY",
                "existing_seat_id": row.seat_id,
                "matched_lineage": proposal.lineage,
            })
    # A proposal must also be internally unambiguous.
    if proposal.lineage.casefold() in proposal.identity_tokens:
        results.append({"code": "LINEAGE_REUSED_AS_IDENTITY_TOKEN", "existing_seat_id": "", "matched_lineage": proposal.lineage})
    return sorted(results, key=lambda item: (item["code"], item.get("existing_seat_id", ""), item.get("matched_token", ""), item.get("matched_lineage", "")))


def evaluate(
    census: Any,
    proposals: Any,
    *,
    evaluated_at: str,
    max_age_seconds: int = 900,
    max_future_skew_seconds: int = 30,
) -> dict[str, Any]:
    if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or max_age_seconds <= 0:
        raise IdentityGuardError("max_age_seconds must be positive int")
    if isinstance(max_future_skew_seconds, bool) or not isinstance(max_future_skew_seconds, int) or max_future_skew_seconds < 0:
        raise IdentityGuardError("max_future_skew_seconds must be non-negative int")
    eval_dt = _parse_time(evaluated_at, field="evaluated_at")
    rows, meta = _validate_census(
        census,
        evaluated_at=eval_dt,
        max_age_seconds=max_age_seconds,
        max_future_skew_seconds=max_future_skew_seconds,
    )
    if not isinstance(proposals, list) or not proposals or len(proposals) > MAX_PROPOSALS:
        raise IdentityGuardError(f"proposals must be non-empty list with <= {MAX_PROPOSALS} items")
    parsed = [_parse_proposal(raw, i) for i, raw in enumerate(proposals)]
    # Conflicting duplicate candidate IDs are rejected; exact duplicates are noise and are not useful priorities.
    seen_candidates: dict[str, Proposal] = {}
    for item in parsed:
        key = item.seat_id.casefold()
        if key in seen_candidates:
            raise IdentityGuardError(f"duplicate proposal seat_id {item.seat_id}")
        seen_candidates[key] = item

    rejected: list[dict[str, Any]] = []
    selected: Proposal | None = None
    for index, proposal in enumerate(parsed):
        reasons = _collision_reasons(proposal, rows)
        if reasons:
            rejected.append({"index": index, "seat_id": proposal.seat_id, "lineage": proposal.lineage, "reasons": reasons})
            continue
        selected = proposal
        selected_index = index
        break

    census_digest = sha256_json(census)
    proposals_digest = sha256_json(proposals)
    decision: dict[str, Any] = {
        "schema": DECISION_SCHEMA,
        "evaluated_at": _iso(eval_dt),
        "census": {**meta, "sha256": census_digest},
        "proposals_sha256": proposals_digest,
        "decision": "CLAIM_AUTHORIZED" if selected is not None else "HOLD",
        "claim_authorized": selected is not None,
        "source_write_authorized": False,
        "slack_write_authorized": False,
        "rejected": rejected,
        "selected": None,
    }
    if selected is not None:
        decision["selected"] = {
            "index": selected_index,
            "seat_id": selected.seat_id,
            "lineage": selected.lineage,
            "aliases": list(selected.aliases),
        }
    receipt_input = dict(decision)
    decision["receipt_sha256"] = sha256_json(receipt_input)
    return decision


def _read_strict(path: Path) -> Any:
    try:
        return loads_strict(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise IdentityGuardError(f"unable to read {path}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Swarm identity collision guard")
    parser.add_argument("--census", required=True, type=Path)
    parser.add_argument("--proposals", required=True, type=Path)
    parser.add_argument("--evaluated-at", required=True)
    parser.add_argument("--max-age-seconds", type=int, default=900)
    parser.add_argument("--max-future-skew-seconds", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        decision = evaluate(
            _read_strict(args.census),
            _read_strict(args.proposals),
            evaluated_at=args.evaluated_at,
            max_age_seconds=args.max_age_seconds,
            max_future_skew_seconds=args.max_future_skew_seconds,
        )
    except IdentityGuardError as exc:
        parser.error(str(exc))
    print(_canonical_json(decision).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
