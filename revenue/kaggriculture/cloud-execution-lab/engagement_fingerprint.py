# SPDX-License-Identifier: Apache-2.0
"""Deterministic matched-policy engagement fingerprints for TITAN experiments.

This module is deliberately outside the gameplay path. It lets official-engine
workers prove that a candidate actually changed a decision before spending a
large matched seed/seat grid on it.

JSONL rows accepted by the CLI look like::

    {"seed": 7, "seat": 0, "step": 12, "phase": "market",
     "control": [["SELL", "MILK", 1]],
     "candidate": [["SELL", "MILK", 2]],
     "control_id": "v5c:<64 lowercase hex>",
     "candidate_id": "v5c:<64 lowercase hex>"}

The default alignment key is ``seed,seat,step,phase``. Duplicate or incomplete
keys fail closed rather than manufacturing a comparison. Optional ``v5c:``
candidate identities are locked across the whole trace when present, so rows
from different builds cannot be silently aggregated. ``NO_OP_OBSERVED`` means
only that the configured matched prefix did not diverge; it is not a claim that
a policy can never engage later in a game.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_V5C_RE = re.compile(r"^v5c:[0-9a-f]{64}$")


class FingerprintError(ValueError):
    """Raised when a decision contains unsupported or non-finite data."""


class AlignmentError(ValueError):
    """Raised when matched comparison rows are not uniquely aligned."""


def _encode_tree(value: Any) -> str:
    """Encode an already-canonical tree without reinterpreting its type tags."""
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,
        allow_nan=False,
    )


def _canonical(value: Any) -> Any:
    """Return a typed deterministic tree for JSON-like decision data."""
    # Type tags prevent Python equality quirks (True == 1, -0.0 == 0.0) from
    # silently collapsing distinct engine decisions.
    if value is None:
        return ["none"]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        return ["int", str(value)]
    if type(value) is float:
        if not math.isfinite(value):
            raise FingerprintError("non-finite float in decision")
        return ["float", value.hex()]
    if type(value) is str:
        return ["str", value]
    if type(value) is bytes:
        return ["bytes", value.hex()]
    if isinstance(value, Mapping):
        encoded = []
        for key, item in value.items():
            canonical_key = _canonical(key)
            canonical_item = _canonical(item)
            encoded.append((_encode_tree(canonical_key), canonical_key, canonical_item))
        encoded.sort(key=lambda row: row[0])
        return ["map", [[key, item] for _, key, item in encoded]]
    if type(value) is list:
        return ["list", [_canonical(item) for item in value]]
    if type(value) is tuple:
        return ["tuple", [_canonical(item) for item in value]]
    if type(value) is set or type(value) is frozenset:
        items = [_canonical(item) for item in value]
        items.sort(key=_encode_tree)
        return ["set", items]
    raise FingerprintError(f"unsupported decision type: {type(value).__name__}")


def fingerprint(value: Any) -> str:
    """Return a SHA-256 fingerprint of an exact typed decision structure."""
    payload = _encode_tree(_canonical(value)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _alignment_fields(fields: Sequence[str]) -> tuple[str, ...]:
    """Return an unambiguous ordered alignment-field contract."""
    if isinstance(fields, (str, bytes)) or not fields:
        raise AlignmentError("at least one alignment key field is required")
    normalized = tuple(fields)
    if any(type(field) is not str or not field for field in normalized):
        raise AlignmentError("alignment key fields must be non-empty strings")
    if len(normalized) != len(set(normalized)):
        raise AlignmentError("alignment key fields must be unique")
    return normalized


def _payload_fields(
    key_fields: Sequence[str], control_field: str, candidate_field: str
) -> tuple[tuple[str, ...], str, str]:
    """Reject payload aliases and decision-dependent alignment fields."""
    fields = _alignment_fields(key_fields)
    if type(control_field) is not str or not control_field:
        raise AlignmentError("control field must be a non-empty string")
    if type(candidate_field) is not str or not candidate_field:
        raise AlignmentError("candidate field must be a non-empty string")
    if control_field == candidate_field:
        raise AlignmentError("control and candidate fields must be distinct")
    overlap = sorted(set(fields) & {control_field, candidate_field})
    if overlap:
        raise AlignmentError(
            "payload fields cannot be alignment key fields: " + ", ".join(overlap)
        )
    return fields, control_field, candidate_field


def _identity_fields(
    key_fields: Sequence[str],
    control_field: str,
    candidate_field: str,
    control_id_field: str,
    candidate_id_field: str,
) -> tuple[str, str]:
    """Return unambiguous build-identity field names."""
    if type(control_id_field) is not str or not control_id_field:
        raise AlignmentError("control identity field must be a non-empty string")
    if type(candidate_id_field) is not str or not candidate_id_field:
        raise AlignmentError("candidate identity field must be a non-empty string")
    if control_id_field == candidate_id_field:
        raise AlignmentError("control and candidate identity fields must be distinct")
    reserved = set(key_fields) | {control_field, candidate_field}
    overlap = sorted(reserved & {control_id_field, candidate_id_field})
    if overlap:
        raise AlignmentError(
            "identity fields cannot be payload or alignment key fields: "
            + ", ".join(overlap)
        )
    return control_id_field, candidate_id_field


def _key_token(key: Mapping[str, Any], fields: Sequence[str]) -> tuple[str, dict[str, Any]]:
    missing = [field for field in fields if field not in key]
    if missing:
        raise AlignmentError(f"missing alignment fields: {', '.join(missing)}")
    selected = {field: key[field] for field in fields}
    token = fingerprint([selected[field] for field in fields])
    return token, selected


def _v5c_identity(value: Any, field: str) -> str:
    if type(value) is not str or _V5C_RE.fullmatch(value) is None:
        raise AlignmentError(f"{field} must be v5c:<64 lowercase hex>")
    return value


class _IdentityBinder:
    """Lock one optional build identity across a complete matched trace."""

    def __init__(self, field: str, expected: str | None = None) -> None:
        self.field = field
        self.bound = None if expected is None else _v5c_identity(expected, field)
        self._saw_row = False
        self._identity_mode = expected is not None

    def observe(self, row: Mapping[str, Any], row_number: int) -> None:
        present = self.field in row
        if self._identity_mode:
            if not present:
                raise AlignmentError(
                    f"row {row_number} missing bound identity field {self.field!r}"
                )
            value = _v5c_identity(row[self.field], self.field)
            if value != self.bound:
                raise AlignmentError(
                    f"row {row_number} mixed identity for {self.field!r}"
                )
        elif present:
            if self._saw_row:
                raise AlignmentError(
                    f"row {row_number} identity {self.field!r} appears after unbound evidence"
                )
            self.bound = _v5c_identity(row[self.field], self.field)
            self._identity_mode = True
        self._saw_row = True


@dataclass(frozen=True)
class Divergence:
    observation: int
    key: dict[str, Any]
    control_fingerprint: str
    candidate_fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation": self.observation,
            "key": self.key,
            "control_fingerprint": self.control_fingerprint,
            "candidate_fingerprint": self.candidate_fingerprint,
        }


class EngagementTracker:
    """Streaming matched A/B decision comparison with fail-closed alignment."""

    def __init__(
        self,
        *,
        key_fields: Sequence[str] = ("seed", "seat", "step", "phase"),
        noop_threshold: int = 8,
    ) -> None:
        self.key_fields = _alignment_fields(key_fields)
        if noop_threshold < 1:
            raise ValueError("noop_threshold must be positive")
        self.noop_threshold = int(noop_threshold)
        self.observations = 0
        self.divergence_count = 0
        self.first_divergence: Divergence | None = None
        self._seen_keys: set[str] = set()
        self._control_sequence = hashlib.sha256()
        self._candidate_sequence = hashlib.sha256()

    def observe(self, key: Mapping[str, Any], control: Any, candidate: Any) -> None:
        """Add one already-matched decision pair.

        ``key`` must contain every configured key field and each resulting key
        may appear only once. A bad trace therefore cannot look like a no-op.
        """
        token, selected = _key_token(key, self.key_fields)
        if token in self._seen_keys:
            raise AlignmentError(f"duplicate matched key: {selected!r}")
        self._seen_keys.add(token)

        control_fp = fingerprint(control)
        candidate_fp = fingerprint(candidate)
        self.observations += 1

        # Bind sequence summaries to the alignment key as well as the action.
        encoded_key = token.encode("ascii")
        self._control_sequence.update(encoded_key + b":" + control_fp.encode("ascii") + b"\n")
        self._candidate_sequence.update(encoded_key + b":" + candidate_fp.encode("ascii") + b"\n")

        if control_fp != candidate_fp:
            self.divergence_count += 1
            if self.first_divergence is None:
                self.first_divergence = Divergence(
                    observation=self.observations,
                    key=selected,
                    control_fingerprint=control_fp,
                    candidate_fingerprint=candidate_fp,
                )

    @property
    def engagement_rate(self) -> float:
        if not self.observations:
            return 0.0
        return self.divergence_count / self.observations

    @property
    def observed_noop(self) -> bool:
        """Whether the configured matched prefix is long enough and unchanged."""
        return self.observations >= self.noop_threshold and self.divergence_count == 0

    def summary(self) -> dict[str, Any]:
        """Return a stable machine-readable engagement report."""
        if self.divergence_count:
            classification = "ENGAGED"
        elif self.observations >= self.noop_threshold:
            classification = "NO_OP_OBSERVED"
        else:
            classification = "INSUFFICIENT"
        return {
            "classification": classification,
            "observations": self.observations,
            "noop_threshold": self.noop_threshold,
            "divergence_count": self.divergence_count,
            "engagement_rate": self.engagement_rate,
            "first_divergence": (
                self.first_divergence.as_dict() if self.first_divergence else None
            ),
            "control_sequence_fingerprint": self._control_sequence.hexdigest(),
            "candidate_sequence_fingerprint": self._candidate_sequence.hexdigest(),
            "key_fields": list(self.key_fields),
        }


def compare_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    key_fields: Sequence[str] = ("seed", "seat", "step", "phase"),
    control_field: str = "control",
    candidate_field: str = "candidate",
    noop_threshold: int = 8,
    control_id: str | None = None,
    candidate_id: str | None = None,
    control_id_field: str = "control_id",
    candidate_id_field: str = "candidate_id",
) -> dict[str, Any]:
    """Compare a matched iterable and return its engagement summary.

    When either identity field is stamped, it must be present and identical on
    every row after the first observation. Passing an expected identity locks
    that field from row one. Legacy traces with no identity stamps retain the
    exact prior report shape.
    """
    key_fields, control_field, candidate_field = _payload_fields(
        key_fields, control_field, candidate_field
    )
    control_id_field, candidate_id_field = _identity_fields(
        key_fields,
        control_field,
        candidate_field,
        control_id_field,
        candidate_id_field,
    )
    tracker = EngagementTracker(key_fields=key_fields, noop_threshold=noop_threshold)
    control_ids = _IdentityBinder(control_id_field, control_id)
    candidate_ids = _IdentityBinder(candidate_id_field, candidate_id)
    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise AlignmentError(f"row {row_number} is not an object")
        if control_field not in row or candidate_field not in row:
            raise AlignmentError(
                f"row {row_number} must contain {control_field!r} and {candidate_field!r}"
            )
        control_ids.observe(row, row_number)
        candidate_ids.observe(row, row_number)
        tracker.observe(row, row[control_field], row[candidate_field])
    report = tracker.summary()
    if control_ids.bound is not None:
        report["control_id"] = control_ids.bound
    if candidate_ids.bound is not None:
        report["candidate_id"] = candidate_ids.bound
    return report


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AlignmentError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise AlignmentError(f"non-standard JSON number: {value}")


def _read_jsonl(path: Path) -> Iterable[Mapping[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(
                    line,
                    object_pairs_hook=_strict_json_object,
                    parse_constant=_reject_json_constant,
                )
            except AlignmentError as exc:
                raise AlignmentError(
                    f"{path}:{line_number}: invalid JSON: {exc}"
                ) from exc
            except json.JSONDecodeError as exc:
                raise AlignmentError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
            if not isinstance(row, Mapping):
                raise AlignmentError(f"{path}:{line_number}: row is not a JSON object")
            yield row


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report whether matched TITAN control/candidate decisions actually diverge."
    )
    parser.add_argument("jsonl", type=Path, help="paired JSONL decision trace")
    parser.add_argument(
        "--key",
        action="append",
        dest="keys",
        help="alignment field (repeatable; defaults to seed,seat,step,phase)",
    )
    parser.add_argument("--control-field", default="control")
    parser.add_argument("--candidate-field", default="candidate")
    parser.add_argument("--noop-threshold", type=int, default=8)
    parser.add_argument(
        "--control-id",
        help="expected control identity v5c:<64 lowercase hex>; requires every row stamp it",
    )
    parser.add_argument(
        "--candidate-id",
        help="expected candidate identity v5c:<64 lowercase hex>; requires every row stamp it",
    )
    parser.add_argument("--control-id-field", default="control_id")
    parser.add_argument("--candidate-id-field", default="candidate_id")
    args = parser.parse_args(argv)

    try:
        report = compare_rows(
            _read_jsonl(args.jsonl),
            key_fields=tuple(args.keys) if args.keys else ("seed", "seat", "step", "phase"),
            control_field=args.control_field,
            candidate_field=args.candidate_field,
            noop_threshold=args.noop_threshold,
            control_id=args.control_id,
            candidate_id=args.candidate_id,
            control_id_field=args.control_id_field,
            candidate_id_field=args.candidate_id_field,
        )
    except (ValueError, OSError) as exc:
        print(f"engagement_fingerprint: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
