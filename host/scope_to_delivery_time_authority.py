#!/usr/bin/env python3
"""Source-recomputed current-time authority for Commons scope-to-delivery.

Current authority is intentionally isolated from the historical/replay surface.
The current evaluator is constructed from a closed local semantic graph and
recomputes the canonical project in a fresh Python child process. Ordinary
post-import rebinding of this module's public/private helper names therefore
cannot redirect its clock, temporal semantics, canonical composition, or
project-binding decision. This is an application input-authority boundary, not
a sandbox against arbitrary same-process code execution or operating-system
compromise.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from host import scope_to_delivery as canonical_scope
except ModuleNotFoundError:  # direct execution
    import scope_to_delivery as canonical_scope

SCHEMA_AGREEMENT = "commons-scope-agreement/v1"
SCHEMA_OBSERVATIONS = "commons-scope-observations/v1"
SCHEMA_RECEIPT = "commons-scope-time-authority/v1"
MAX_INPUT_BYTES = 2_000_000
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TemporalAuthorityError(ValueError):
    pass


def _build_strict_loader(
    *,
    loads=json.loads,
    max_bytes=MAX_INPUT_BYTES,
    error_cls=TemporalAuthorityError,
):
    """Bind strict parsing once; normalize parser/resource-limit failures."""

    def strict(raw: bytes, field: str) -> Any:
        if type(raw) is not bytes:
            raise error_cls(f"{field} must be exact bytes")
        if len(raw) > max_bytes:
            raise error_cls(f"{field} exceeds {max_bytes} bytes")
        try:
            text = raw.decode("utf-8")
        except UnicodeError as exc:
            raise error_cls(f"{field} must be UTF-8 JSON") from exc

        def pairs(items):
            out = {}
            for key, value in items:
                if key in out:
                    raise error_cls(f"duplicate JSON key: {key}")
                out[key] = value
            return out

        def bad_constant(value):
            raise error_cls(f"{field} contains non-finite JSON number {value}")

        try:
            return loads(text, object_pairs_hook=pairs, parse_constant=bad_constant)
        except error_cls:
            raise
        except (ValueError, TypeError, RecursionError) as exc:
            raise error_cls(f"{field} is not valid bounded JSON") from exc

    return strict


_STRICT_LOADS = _build_strict_loader()
del _build_strict_loader


def strict_loads(raw: bytes, field: str) -> Any:
    return _STRICT_LOADS(raw, field)


def canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value or not (
        value.endswith("Z") or re.search(r"[+-]\d\d:\d\d$", value)
    ):
        raise TemporalAuthorityError(
            f"{field} must be an offset-aware ISO-8601 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError as exc:
        raise TemporalAuthorityError(f"{field} must be a real timestamp") from exc
    if parsed.utcoffset() is None:
        raise TemporalAuthorityError(f"{field} must include an offset")
    return parsed.astimezone(timezone.utc)


def read_plain_bytes(path: str | Path, field: str) -> bytes:
    target = os.fspath(path)
    if not hasattr(os, "O_NOFOLLOW"):
        raise TemporalAuthorityError(
            "platform lacks O_NOFOLLOW; exact plain-file custody cannot be proven"
        )
    try:
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise TemporalAuthorityError(
            f"{field} must be a readable non-symlink file"
        ) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise TemporalAuthorityError(f"{field} must be a regular file")
        if info.st_size > MAX_INPUT_BYTES:
            raise TemporalAuthorityError(f"{field} exceeds {MAX_INPUT_BYTES} bytes")
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, MAX_INPUT_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                raise TemporalAuthorityError(
                    f"{field} exceeds {MAX_INPUT_BYTES} bytes"
                )
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def read_plain_json(path: str | Path, field: str) -> tuple[Any, str]:
    raw = read_plain_bytes(path, field)
    return strict_loads(raw, field), hashlib.sha256(raw).hexdigest()


def _require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TemporalAuthorityError(f"{field} must be an object")
    return value


def _agreement_times(
    agreement: Any,
) -> tuple[dict[str, Any], datetime, datetime, datetime | None]:
    agreement = _require_dict(agreement, "agreement")
    agreement_id = agreement.get("agreement_id")
    if not isinstance(agreement_id, str) or not agreement_id.strip():
        raise TemporalAuthorityError(
            "agreement.agreement_id must be a nonempty string"
        )
    if agreement_id != agreement_id.strip():
        raise TemporalAuthorityError(
            "agreement.agreement_id must not have surrounding whitespace"
        )
    if agreement.get("schema_version") != SCHEMA_AGREEMENT:
        raise TemporalAuthorityError(
            f"agreement.schema_version must be {SCHEMA_AGREEMENT}"
        )
    if agreement.get("kind") != "SCOPE_AGREEMENT":
        raise TemporalAuthorityError("agreement.kind must be SCOPE_AGREEMENT")
    window = _require_dict(agreement.get("window"), "agreement.window")
    start = parse_time(window.get("start"), "agreement.window.start")
    end = parse_time(window.get("end"), "agreement.window.end")
    if end <= start:
        raise TemporalAuthorityError("agreement.window.end must be after start")
    written = _require_dict(
        agreement.get("written_acceptance"), "agreement.written_acceptance"
    )
    accepted_at = None
    if written.get("status") == "PRESENT":
        accepted_at = parse_time(
            written.get("accepted_at"), "agreement.written_acceptance.accepted_at"
        )
        if accepted_at > end:
            raise TemporalAuthorityError(
                "PRESENT acceptance occurs after the contracted window ended"
            )
    elif written.get("accepted_at") is not None:
        raise TemporalAuthorityError(
            "non-PRESENT acceptance must not carry accepted_at"
        )
    return agreement, start, end, accepted_at


def _validate_observations(
    observations: Any | None,
    agreement: dict[str, Any],
    *,
    accepted_at: datetime | None,
    start: datetime,
    end: datetime,
    as_of: datetime,
) -> tuple[list[dict[str, Any]], str | None]:
    if observations is None:
        return [], None
    observations = _require_dict(observations, "observations")
    if observations.get("schema_version") != SCHEMA_OBSERVATIONS:
        raise TemporalAuthorityError(
            f"observations.schema_version must be {SCHEMA_OBSERVATIONS}"
        )
    if observations.get("kind") != "EXECUTION_OBSERVATIONS":
        raise TemporalAuthorityError(
            "observations.kind must be EXECUTION_OBSERVATIONS"
        )
    if observations.get("agreement_id") != agreement.get("agreement_id"):
        raise TemporalAuthorityError(
            "observations.agreement_id does not match agreement"
        )
    items = observations.get("observations")
    if not isinstance(items, list):
        raise TemporalAuthorityError("observations.observations must be a list")
    if items and accepted_at is None:
        raise TemporalAuthorityError(
            "execution observations exist without PRESENT acceptance"
        )
    seen = set()
    parsed = []
    for index, item in enumerate(items):
        item = _require_dict(item, f"observations[{index}]")
        observation_id = item.get("observation_id")
        if not isinstance(observation_id, str) or not observation_id:
            raise TemporalAuthorityError(
                f"observations[{index}].observation_id must be a nonempty string"
            )
        if observation_id in seen:
            raise TemporalAuthorityError(
                f"duplicate observation_id: {observation_id}"
            )
        seen.add(observation_id)
        when = parse_time(
            item.get("observed_at"), f"observations[{index}].observed_at"
        )
        assert accepted_at is not None
        if when < accepted_at:
            raise TemporalAuthorityError(
                f"observation {observation_id} predates written acceptance"
            )
        if when < start:
            raise TemporalAuthorityError(
                f"observation {observation_id} predates contracted work window"
            )
        if when > end:
            raise TemporalAuthorityError(
                f"observation {observation_id} occurs after contracted work window"
            )
        if when > as_of:
            raise TemporalAuthorityError(
                f"observation {observation_id} is in the verifier's future"
            )
        parsed.append({"observation_id": observation_id, "observed_at": when})
    return parsed, digest(observations)


def _temporal_facts(
    agreement: Any, observations: Any | None, *, as_of: datetime
) -> dict[str, Any]:
    """Historical/replay facts. Production current authority does not call this."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise TemporalAuthorityError("as_of must be timezone-aware")
    as_of = as_of.astimezone(timezone.utc)
    agreement, start, end, accepted_at = _agreement_times(agreement)
    written = agreement["written_acceptance"]
    if accepted_at is not None and accepted_at > as_of:
        raise TemporalAuthorityError("PRESENT acceptance is in the verifier's future")
    parsed_observations, observations_digest = _validate_observations(
        observations,
        agreement,
        accepted_at=accepted_at,
        start=start,
        end=end,
        as_of=as_of,
    )
    if written.get("status") != "PRESENT":
        state = "HOLD_NO_PRESENT_ACCEPTANCE"
        ready = False
    elif as_of < start:
        state = "HOLD_WINDOW_NOT_STARTED"
        ready = False
    elif as_of > end:
        state = "HOLD_WINDOW_EXPIRED"
        ready = False
    else:
        state = "TEMPORAL_PREREQUISITE_READY"
        ready = True
    return {
        "agreement_id": agreement.get("agreement_id"),
        "state": state,
        "temporal_ready": ready,
        "trusted_as_of": as_of.isoformat().replace("+00:00", "Z"),
        "window_start": start.isoformat().replace("+00:00", "Z"),
        "window_end": end.isoformat().replace("+00:00", "Z"),
        "accepted_at": (
            accepted_at.isoformat().replace("+00:00", "Z") if accepted_at else None
        ),
        "agreement_canonical_sha256": digest(agreement),
        "observations_canonical_sha256": observations_digest,
        "observation_count": len(parsed_observations),
        "historical_evidence_temporally_admissible": bool(parsed_observations),
    }


def _receipt_base(facts: dict[str, Any], *, state: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_RECEIPT,
        "kind": "SCOPE_TO_DELIVERY_TEMPORAL_AUTHORITY",
        "agreement_id": facts["agreement_id"],
        "state": state,
        "temporal_state": facts["state"],
        "trusted_as_of": facts["trusted_as_of"],
        "window_start": facts["window_start"],
        "window_end": facts["window_end"],
        "accepted_at": facts["accepted_at"],
        "agreement_canonical_sha256": facts["agreement_canonical_sha256"],
        "observations_canonical_sha256": facts[
            "observations_canonical_sha256"
        ],
        "observation_count": facts["observation_count"],
        "temporal_prerequisite_only": True,
        "canonical_scope_validation_still_required": True,
        "historical_evidence_temporally_admissible": facts[
            "historical_evidence_temporally_admissible"
        ],
        "external_action_authorized": False,
        "payment_authorized": False,
        "delivery_claim_authorized": False,
        "revenue_authorized": False,
    }


def _seal(core: dict[str, Any]) -> dict[str, Any]:
    out = dict(core)
    out["receipt_sha256"] = digest(core)
    return out


def _receipt_hash_valid(receipt: dict[str, Any]) -> bool:
    claimed = receipt.get("receipt_sha256")
    if not isinstance(claimed, str) or not SHA256_RE.fullmatch(claimed):
        return False
    core = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    return hmac.compare_digest(claimed, digest(core))


def evaluate(
    agreement: Any, observations: Any | None, *, as_of: datetime
) -> dict[str, Any]:
    facts = _temporal_facts(agreement, observations, as_of=as_of)
    state = (
        "HOLD_PARSED_OBJECT_UNVERIFIED"
        if facts["temporal_ready"]
        else facts["state"]
    )
    return _seal(
        {
            **_receipt_base(facts, state=state),
            "clock_authority": "CALLER_SUPPLIED_HISTORICAL_ONLY",
            "agreement_raw_sha256": None,
            "observations_raw_sha256": None,
            "raw_byte_provenance_verified": False,
            "provenance_mode": "CANONICAL_OBJECT_ONLY",
            "canonical_scope_validated": False,
            "canonical_project_bound": False,
            "canonical_project_sha256": None,
            "canonical_binding_required": True,
            "current_work_authorized": False,
            "authority_boundary": (
                "Parsed-object evaluation is chronology-only and cannot "
                "authorize current work."
            ),
        }
    )


def _historical_project(
    agreement: dict[str, Any], observations: dict[str, Any] | None
) -> dict[str, Any]:
    try:
        catalog = canonical_scope.load_json(canonical_scope.DEFAULT_CATALOG)
        bindings = canonical_scope.load_bindings(canonical_scope.DEFAULT_BINDINGS)
        return canonical_scope.compose_project(
            agreement, catalog, bindings, observations, None
        )
    except canonical_scope.PipelineError as exc:
        raise TemporalAuthorityError(
            "exact temporal inputs fail canonical scope validation"
        ) from exc


def evaluate_bytes(
    agreement_raw: bytes,
    observations_raw: bytes | None,
    *,
    as_of: datetime,
    canonical_project: Any | None = None,
) -> dict[str, Any]:
    """Historical exact-byte analysis; caller time can never authorize current work."""
    agreement = strict_loads(agreement_raw, "agreement")
    observations = (
        strict_loads(observations_raw, "observations")
        if observations_raw is not None
        else None
    )
    expected_project = _historical_project(agreement, observations)
    project_sha = digest(expected_project)
    project_bound = False
    if canonical_project is not None:
        supplied = _require_dict(canonical_project, "canonical_project")
        if (
            supplied.get("schema_version") != canonical_scope.SCHEMA_PROJECT
            or supplied.get("kind") != "SCOPE_TO_DELIVERY_PROJECT"
            or supplied.get("agreement_id") != agreement.get("agreement_id")
        ):
            raise TemporalAuthorityError("canonical_project identity is invalid")
        if not hmac.compare_digest(digest(supplied), project_sha):
            raise TemporalAuthorityError(
                "canonical_project does not bind the exact temporal inputs"
            )
        project_bound = True
    facts = _temporal_facts(agreement, observations, as_of=as_of)
    if facts["temporal_ready"]:
        state = "HOLD_CALLER_TIME_UNVERIFIED"
    elif facts["state"] == "HOLD_WINDOW_EXPIRED":
        state = "HISTORICAL_WINDOW_EXPIRED"
    else:
        state = facts["state"]
    return _seal(
        {
            **_receipt_base(facts, state=state),
            "clock_authority": "CALLER_SUPPLIED_HISTORICAL_ONLY",
            "agreement_raw_sha256": hashlib.sha256(agreement_raw).hexdigest(),
            "observations_raw_sha256": (
                hashlib.sha256(observations_raw).hexdigest()
                if observations_raw is not None
                else None
            ),
            "raw_byte_provenance_verified": True,
            "provenance_mode": "EXACT_RAW_BYTES_VERIFIED",
            "canonical_scope_validated": True,
            "canonical_project_bound": project_bound,
            "canonical_project_sha256": project_sha,
            "canonical_binding_required": True,
            "current_work_authorized": False,
            "authority_boundary": (
                "Exact bytes and canonical binding are historical/integrity "
                "evidence only because as_of is caller supplied."
            ),
        }
    )


def _build_current_evaluator(
    *,
    now_fn=datetime.now,
    datetime_cls=datetime,
    utc=timezone.utc,
    loads=json.loads,
    dumps=json.dumps,
    sha256=hashlib.sha256,
    compare_digest=hmac.compare_digest,
    run_process=subprocess.run,
    devnull=subprocess.DEVNULL,
    pipe=subprocess.PIPE,
    subprocess_error=subprocess.SubprocessError,
    temp_dir=tempfile.TemporaryDirectory,
    pyexe=sys.executable,
    composer_path=str(Path(canonical_scope.__file__).resolve()),
    os_open=os.open,
    os_write=os.write,
    os_close=os.close,
    o_wronly=os.O_WRONLY,
    o_creat=os.O_CREAT,
    o_excl=os.O_EXCL,
    max_bytes=MAX_INPUT_BYTES,
    schema_agreement=SCHEMA_AGREEMENT,
    schema_observations=SCHEMA_OBSERVATIONS,
    schema_receipt=SCHEMA_RECEIPT,
    error_cls=TemporalAuthorityError,
):
    """Construct a closed production authority graph.

    The nested graph deliberately does not call module semantic helpers. Canonical
    composition runs in a fresh Python process against the repository composer.
    """

    def canon_local(value):
        try:
            return dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise error_cls("value is not canonical bounded JSON") from exc

    def hash_value(value):
        return sha256(canon_local(value)).hexdigest()

    def strict_local(raw, field):
        if type(raw) is not bytes:
            raise error_cls(f"{field} must be exact bytes")
        if len(raw) > max_bytes:
            raise error_cls(f"{field} exceeds {max_bytes} bytes")
        try:
            text = raw.decode("utf-8")
        except UnicodeError as exc:
            raise error_cls(f"{field} must be UTF-8 JSON") from exc

        def pairs(items):
            out = {}
            for key, value in items:
                if key in out:
                    raise error_cls(f"duplicate JSON key: {key}")
                out[key] = value
            return out

        def bad_constant(value):
            raise error_cls(f"{field} contains non-finite JSON number {value}")

        try:
            return loads(text, object_pairs_hook=pairs, parse_constant=bad_constant)
        except error_cls:
            raise
        except (ValueError, TypeError, RecursionError) as exc:
            raise error_cls(f"{field} is not valid bounded JSON") from exc

    def require_dict(value, field):
        if not isinstance(value, dict):
            raise error_cls(f"{field} must be an object")
        return value

    def parse_time_local(value, field):
        if not isinstance(value, str) or not value or not (
            value.endswith("Z")
            or (
                len(value) >= 6
                and value[-6] in "+-"
                and value[-3] == ":"
                and value[-5:-3].isdigit()
                and value[-2:].isdigit()
            )
        ):
            raise error_cls(
                f"{field} must be an offset-aware ISO-8601 timestamp"
            )
        try:
            parsed = datetime_cls.fromisoformat(
                value[:-1] + "+00:00" if value.endswith("Z") else value
            )
        except ValueError as exc:
            raise error_cls(f"{field} must be a real timestamp") from exc
        if parsed.utcoffset() is None:
            raise error_cls(f"{field} must include an offset")
        return parsed.astimezone(utc)

    def write_exact(path, payload):
        fd = os_open(path, o_wronly | o_creat | o_excl, 0o600)
        try:
            view = memoryview(payload)
            while view:
                count = os_write(fd, view)
                if count <= 0:
                    raise error_cls("short write while staging canonical input")
                view = view[count:]
        finally:
            os_close(fd)

    def canonical_project_from_fresh_process(agreement_raw, observations_raw):
        with temp_dir() as td:
            ap = td + "/agreement.json"
            write_exact(ap, agreement_raw)
            cmd = [pyexe, composer_path, "project", "--agreement", ap]
            if observations_raw is not None:
                op = td + "/observations.json"
                write_exact(op, observations_raw)
                cmd.extend(["--observations", op])
            try:
                result = run_process(
                    cmd,
                    stdin=devnull,
                    stdout=pipe,
                    stderr=pipe,
                    timeout=30,
                    check=False,
                )
            except (OSError, subprocess_error) as exc:
                raise error_cls("canonical scope subprocess failed") from exc
            if result.returncode != 0:
                raise error_cls("exact temporal inputs fail canonical scope validation")
            return strict_local(result.stdout, "canonical_project_subprocess")

    def temporal_facts_local(agreement, observations, as_of):
        if not isinstance(agreement, dict):
            raise error_cls("agreement must be an object")
        if agreement.get("schema_version") != schema_agreement:
            raise error_cls(f"agreement.schema_version must be {schema_agreement}")
        if agreement.get("kind") != "SCOPE_AGREEMENT":
            raise error_cls("agreement.kind must be SCOPE_AGREEMENT")
        agreement_id = agreement.get("agreement_id")
        if not isinstance(agreement_id, str) or not agreement_id:
            raise error_cls("agreement.agreement_id must be a nonempty string")
        window = require_dict(agreement.get("window"), "agreement.window")
        start = parse_time_local(window.get("start"), "agreement.window.start")
        end = parse_time_local(window.get("end"), "agreement.window.end")
        if end <= start:
            raise error_cls("agreement.window.end must be after start")
        written = require_dict(
            agreement.get("written_acceptance"), "agreement.written_acceptance"
        )
        accepted_at = None
        if written.get("status") == "PRESENT":
            accepted_at = parse_time_local(
                written.get("accepted_at"),
                "agreement.written_acceptance.accepted_at",
            )
            if accepted_at > end:
                raise error_cls(
                    "PRESENT acceptance occurs after contracted window end"
                )
            if accepted_at > as_of:
                raise error_cls("PRESENT acceptance is in verifier future")
        elif written.get("accepted_at") is not None:
            raise error_cls("non-PRESENT acceptance must not carry accepted_at")

        parsed_count = 0
        obs_digest = None
        if observations is not None:
            observations = require_dict(observations, "observations")
            if observations.get("schema_version") != schema_observations:
                raise error_cls(
                    f"observations.schema_version must be {schema_observations}"
                )
            if observations.get("kind") != "EXECUTION_OBSERVATIONS":
                raise error_cls(
                    "observations.kind must be EXECUTION_OBSERVATIONS"
                )
            if observations.get("agreement_id") != agreement_id:
                raise error_cls(
                    "observations.agreement_id does not match agreement"
                )
            items = observations.get("observations")
            if not isinstance(items, list):
                raise error_cls("observations.observations must be a list")
            if items and accepted_at is None:
                raise error_cls(
                    "execution observations exist without PRESENT acceptance"
                )
            seen = set()
            for index, item in enumerate(items):
                item = require_dict(item, f"observations[{index}]")
                oid = item.get("observation_id")
                if not isinstance(oid, str) or not oid:
                    raise error_cls(
                        f"observations[{index}].observation_id must be nonempty"
                    )
                if oid in seen:
                    raise error_cls(f"duplicate observation_id: {oid}")
                seen.add(oid)
                when = parse_time_local(
                    item.get("observed_at"),
                    f"observations[{index}].observed_at",
                )
                if accepted_at is None or when < accepted_at:
                    raise error_cls(
                        f"observation {oid} predates written acceptance"
                    )
                if when < start:
                    raise error_cls(
                        f"observation {oid} predates contracted work window"
                    )
                if when > end:
                    raise error_cls(
                        f"observation {oid} occurs after contracted work window"
                    )
                if when > as_of:
                    raise error_cls(f"observation {oid} is in verifier future")
                parsed_count += 1
            obs_digest = hash_value(observations)

        if written.get("status") != "PRESENT":
            state = "HOLD_NO_PRESENT_ACCEPTANCE"
            ready = False
        elif as_of < start:
            state = "HOLD_WINDOW_NOT_STARTED"
            ready = False
        elif as_of > end:
            state = "HOLD_WINDOW_EXPIRED"
            ready = False
        else:
            state = "TEMPORAL_PREREQUISITE_READY"
            ready = True

        return {
            "agreement_id": agreement_id,
            "state": state,
            "temporal_ready": ready,
            "trusted_as_of": as_of.isoformat().replace("+00:00", "Z"),
            "window_start": start.isoformat().replace("+00:00", "Z"),
            "window_end": end.isoformat().replace("+00:00", "Z"),
            "accepted_at": (
                accepted_at.isoformat().replace("+00:00", "Z")
                if accepted_at
                else None
            ),
            "agreement_canonical_sha256": hash_value(agreement),
            "observations_canonical_sha256": obs_digest,
            "observation_count": parsed_count,
            "historical_evidence_temporally_admissible": bool(parsed_count),
        }

    def evaluate_current_bytes(
        agreement_raw: bytes,
        observations_raw: bytes | None,
        *,
        canonical_project: Any | None = None,
    ) -> dict[str, Any]:
        observed_now = now_fn(utc)
        agreement = strict_local(agreement_raw, "agreement")
        observations = (
            strict_local(observations_raw, "observations")
            if observations_raw is not None
            else None
        )
        expected_project = canonical_project_from_fresh_process(
            agreement_raw, observations_raw
        )
        expected_project_sha = hash_value(expected_project)
        project_bound = False
        if canonical_project is not None:
            supplied = require_dict(canonical_project, "canonical_project")
            if (
                supplied.get("schema_version")
                != expected_project.get("schema_version")
                or supplied.get("kind") != "SCOPE_TO_DELIVERY_PROJECT"
                or supplied.get("agreement_id") != agreement.get("agreement_id")
            ):
                raise error_cls("canonical_project identity is invalid")
            if not compare_digest(
                hash_value(supplied), expected_project_sha
            ):
                raise error_cls(
                    "canonical_project does not bind exact temporal inputs"
                )
            project_bound = True

        facts = temporal_facts_local(agreement, observations, observed_now)
        state = facts["state"]
        if facts["temporal_ready"] and not project_bound:
            state = "HOLD_CANONICAL_PROJECT_UNBOUND"
        current = bool(facts["temporal_ready"] and project_bound)
        core = {
            "schema_version": schema_receipt,
            "kind": "SCOPE_TO_DELIVERY_TEMPORAL_AUTHORITY",
            "agreement_id": facts["agreement_id"],
            "state": state,
            "temporal_state": facts["state"],
            "trusted_as_of": facts["trusted_as_of"],
            "window_start": facts["window_start"],
            "window_end": facts["window_end"],
            "accepted_at": facts["accepted_at"],
            "agreement_canonical_sha256": facts[
                "agreement_canonical_sha256"
            ],
            "observations_canonical_sha256": facts[
                "observations_canonical_sha256"
            ],
            "observation_count": facts["observation_count"],
            "temporal_prerequisite_only": True,
            "canonical_scope_validation_still_required": True,
            "historical_evidence_temporally_admissible": facts[
                "historical_evidence_temporally_admissible"
            ],
            "external_action_authorized": False,
            "payment_authorized": False,
            "delivery_claim_authorized": False,
            "revenue_authorized": False,
            "clock_authority": "VERIFIER_PROCESS_UTC_CLOSURE_BOUND",
            "agreement_raw_sha256": sha256(agreement_raw).hexdigest(),
            "observations_raw_sha256": (
                sha256(observations_raw).hexdigest()
                if observations_raw is not None
                else None
            ),
            "raw_byte_provenance_verified": True,
            "provenance_mode": "EXACT_RAW_BYTES_VERIFIED",
            "canonical_scope_validated": True,
            "canonical_project_bound": project_bound,
            "canonical_project_sha256": expected_project_sha,
            "canonical_binding_required": True,
            "current_work_authorized": current,
            "authority_boundary": (
                "Current authority uses a closure-local temporal graph plus a "
                "fresh-process canonical composer. External action/payment/"
                "delivery/revenue gates remain separate."
            ),
        }
        out = dict(core)
        out["receipt_sha256"] = sha256(canon_local(core)).hexdigest()
        return out

    return evaluate_current_bytes


evaluate_current_bytes = _build_current_evaluator()
del _build_current_evaluator


def verify_project_binding_integrity(
    project: Any, receipt: Any
) -> dict[str, Any]:
    project = _require_dict(project, "canonical_project")
    receipt = _require_dict(receipt, "temporal_receipt")
    if receipt.get("schema_version") != SCHEMA_RECEIPT:
        raise TemporalAuthorityError(
            "temporal_receipt schema_version is invalid"
        )
    if not _receipt_hash_valid(receipt):
        raise TemporalAuthorityError(
            "temporal_receipt receipt_sha256 is invalid"
        )
    if receipt.get("canonical_scope_validated") is not True:
        raise TemporalAuthorityError(
            "temporal_receipt lacks canonical scope validation"
        )
    if receipt.get("canonical_project_bound") is not True:
        raise TemporalAuthorityError(
            "temporal_receipt lacks canonical project binding"
        )
    expected = receipt.get("canonical_project_sha256")
    if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
        raise TemporalAuthorityError(
            "temporal_receipt canonical project digest is invalid"
        )
    if project.get("agreement_id") != receipt.get("agreement_id"):
        raise TemporalAuthorityError(
            "canonical project agreement_id does not match receipt"
        )
    if not hmac.compare_digest(digest(project), expected):
        raise TemporalAuthorityError(
            "canonical project and receipt are different artifacts"
        )
    return {
        "integrity_valid": True,
        "authority": "INTEGRITY_ONLY_NOT_CURRENT_WORK",
        "canonical_project_sha256": expected,
        "current_work_authority_verified": False,
    }


def verify_project_binding(project: Any, receipt: Any) -> dict[str, Any]:
    out = verify_project_binding_integrity(project, receipt)
    return {**out, "deprecated_name": "verify_project_binding"}


def _build_current_verifier(current_evaluator=evaluate_current_bytes):
    def verify_current_work_authority(
        agreement_raw: bytes,
        observations_raw: bytes | None,
        *,
        canonical_project: Any,
    ) -> dict[str, Any]:
        receipt = current_evaluator(
            agreement_raw,
            observations_raw,
            canonical_project=canonical_project,
        )
        valid = bool(
            receipt["state"] == "TEMPORAL_PREREQUISITE_READY"
            and receipt["current_work_authorized"] is True
            and receipt["raw_byte_provenance_verified"] is True
            and receipt["provenance_mode"] == "EXACT_RAW_BYTES_VERIFIED"
            and receipt["canonical_scope_validated"] is True
            and receipt["canonical_project_bound"] is True
            and receipt["clock_authority"]
            == "VERIFIER_PROCESS_UTC_CLOSURE_BOUND"
        )
        return {
            "valid": valid,
            "state": receipt["state"],
            "current_work_authorized": valid,
            "receipt_sha256": receipt["receipt_sha256"],
            "canonical_project_sha256": receipt[
                "canonical_project_sha256"
            ],
            "clock_authority": receipt["clock_authority"],
        }

    return verify_current_work_authority


verify_current_work_authority = _build_current_verifier()
del _build_current_verifier


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Current trusted-time prerequisite for Commons scope-to-delivery."
    )
    parser.add_argument("--agreement", required=True)
    parser.add_argument("--observations")
    parser.add_argument(
        "--project",
        required=True,
        help="canonical project JSON for the exact same source inputs",
    )
    args = parser.parse_args(argv)
    try:
        agreement_raw = read_plain_bytes(args.agreement, "agreement")
        observations_raw = (
            read_plain_bytes(args.observations, "observations")
            if args.observations
            else None
        )
        project = strict_loads(
            read_plain_bytes(args.project, "canonical_project"),
            "canonical_project",
        )
        receipt = evaluate_current_bytes(
            agreement_raw,
            observations_raw,
            canonical_project=project,
        )
    except (OSError, TemporalAuthorityError) as exc:
        print(
            json.dumps(
                {
                    "state": "HOLD_INVALID_TEMPORAL_EVIDENCE",
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["current_work_authorized"] else 3


__all__ = [
    "SCHEMA_AGREEMENT",
    "SCHEMA_OBSERVATIONS",
    "SCHEMA_RECEIPT",
    "MAX_INPUT_BYTES",
    "TemporalAuthorityError",
    "canonical",
    "digest",
    "parse_time",
    "strict_loads",
    "read_plain_bytes",
    "read_plain_json",
    "_temporal_facts",
    "_receipt_base",
    "evaluate",
    "evaluate_bytes",
    "evaluate_current_bytes",
    "verify_project_binding_integrity",
    "verify_project_binding",
    "verify_current_work_authority",
    "main",
    "datetime",
]


if __name__ == "__main__":
    raise SystemExit(main())
