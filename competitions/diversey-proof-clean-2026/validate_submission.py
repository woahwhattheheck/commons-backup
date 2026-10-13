#!/usr/bin/env python3
"""Fail-closed release validator for the Diversey Proof-of-Clean carrier.

Repository bytes are candidate-controlled observations. They cannot mint human/legal
or provider authority. READY requires an owner-release record supplied from outside
the competition tree and bound to exact proposal and source generations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

SCHEMA = "DIVERSEY_PROOF_CLEAN_2026_READINESS_V2"
OWNER_RELEASE_SCHEMA = "DIVERSEY_PROOF_CLEAN_2026_OWNER_RELEASE_V1"
EVENT_SCHEMA = "DIVERSEY_PROOF_CLEAN_2026_PROVIDER_EVENT_V1"
CARRIER_ID = "DIVERSEY-RAPID-PROOF-CLEAN-2026"
OPERATION_ID = "DIVERSEY-RECOVERY-AUTHORITY-ZIFK3N7-20260914"
OFFICIAL_URL = "https://www.innocentive.com/challenges/novel-technologies-for-rapid-proof-of-clean-in-professional-environments/"
DEADLINE = "2026-09-21T23:59:00-04:00"
DEADLINE_UTC = datetime.fromisoformat(DEADLINE).astimezone(timezone.utc)
MAX_FILE_BYTES = 2 * 1024 * 1024
AUTHORITY_ROOT = Path("/var/lib/commons-authority/diversey-proof-clean-2026")
OWNER_RELEASE_NAME = "owner-release.json"
EVENT_DIR_NAME = "events"

REQUIRED_GATES = {
    "challenge_agreement_reviewed",
    "solver_eligibility_verified",
    "participation_type_selected",
    "applicant_identity_completed",
    "first_hand_experience_completed",
    "technical_owner_reviewed",
    "trl_confirmed",
    "scientific_claims_verified",
    "ip_and_freedom_to_operate_reviewed",
    "partnership_posture_authorized",
    "human_rewrite_complete",
    "final_proposal_human_reviewed",
    "external_submission_authorized",
}
EXTERNAL_OBSERVATIONS = {
    "registered_or_joined", "submitted", "award_received", "payment_received"
}
REQUIRED_PROPOSAL_HEADINGS = [
    "## 1. Participation Type", "## 2. Solution Level", "## 3. Partnering",
    "## 4. Problem & Opportunity", "## 5. Solution Overview",
    "## 6. Solution Feasibility / Scientific Basis", "## 7. Performance Expectations",
    "## 8. Experience", "## 9. Solution Risks",
    "## 10. Development Timeline and Capability", "## 11. Online References",
]
REQUIRED_SCIENCE_REFS = [
    "10.1016/j.talanta.2023.125561",
    "pubmed.ncbi.nlm.nih.gov/42107219",
    "pubmed.ncbi.nlm.nih.gov/36495704",
    "pubmed.ncbi.nlm.nih.gov/39194631",
]

class DuplicateKeyError(ValueError):
    pass

def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        out[key] = value
    return out

def _load_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError) as exc:
        raise ValueError(f"{label}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label}: must contain a JSON object")
    return data

def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def _hex_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())

def _parse_time(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str):
        errors.append(f"{field} must be an ISO-8601 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be an ISO-8601 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{field} must include a timezone")
        return None
    return parsed.astimezone(timezone.utc)

def _read_fd(fd: int, label: str) -> bytes:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label}: must be a regular file")
    if before.st_size > MAX_FILE_BYTES:
        raise ValueError(f"{label}: exceeds {MAX_FILE_BYTES} byte hard cap")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_FILE_BYTES:
            raise ValueError(f"{label}: exceeds {MAX_FILE_BYTES} byte hard cap")
        chunks.append(chunk)
    after = os.fstat(fd)
    a = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
    b = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    if a != b or total != after.st_size:
        raise ValueError(f"{label}: file generation changed during retained read")
    return b"".join(chunks)

def _root_fd(root: Path) -> int:
    return os.open(root, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))

def _leaf(value: str, field: str) -> str:
    p = PurePosixPath(value)
    if p.is_absolute() or len(p.parts) != 1 or p.name in {"", ".", ".."} or "\\" in value:
        raise ValueError(f"{field}: path must be one regular file directly inside the competition directory")
    return value

def _read_root(root_fd: int, value: str, field: str) -> bytes:
    name = _leaf(value, field)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=root_fd)
    except OSError as exc:
        raise ValueError(f"{field}: cannot open retained no-follow file: {exc.strerror}") from exc
    try:
        return _read_fd(fd, field)
    finally:
        os.close(fd)

def _open_dir_chain_nofollow(path: Path, field: str) -> int:
    supplied = path.expanduser()
    if not supplied.is_absolute():
        supplied = (Path.cwd() / supplied).absolute()
    parts = supplied.parts
    if not parts or parts[0] != os.sep or any(part in {"", ".", ".."} for part in parts[1:]):
        raise ValueError(f"{field}: must be a normalized absolute directory path")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(os.sep, flags)
    try:
        for part in parts[1:]:
            try:
                nxt = os.open(part, flags, dir_fd=fd)
            except OSError as exc:
                raise ValueError(f"{field}: cannot open retained no-follow directory component {part!r}: {exc.strerror}") from exc
            os.close(fd)
            fd = nxt
        return fd
    except Exception:
        os.close(fd)
        raise

def _read_dir_leaf(dir_fd: int, name: str, field: str) -> bytes:
    leaf = _leaf(name, field)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(leaf, flags, dir_fd=dir_fd)
    except OSError as exc:
        raise ValueError(f"{field}: cannot open retained no-follow file: {exc.strerror}") from exc
    try:
        return _read_fd(fd, field)
    finally:
        os.close(fd)

def _try_read_dir_leaf(dir_fd: int, name: str, field: str) -> bytes | None:
    leaf = _leaf(name, field)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(leaf, flags, dir_fd=dir_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError(f"{field}: cannot open retained no-follow file: {exc.strerror}") from exc
    try:
        return _read_fd(fd, field)
    finally:
        os.close(fd)

def _authority_snapshot(authority_root: Path, candidate_fd: int) -> tuple[bytes | None, list[tuple[str, bytes]]]:
    try:
        authority_fd = _open_dir_chain_nofollow(authority_root, "authority root")
    except ValueError as exc:
        # A completely absent fixed host boundary is normal while the candidate is BLOCKED.
        if isinstance(exc.__cause__, FileNotFoundError):
            return None, []
        raise
    try:
        auth_stat = os.fstat(authority_fd)
        cand_stat = os.fstat(candidate_fd)
        if (auth_stat.st_dev, auth_stat.st_ino) == (cand_stat.st_dev, cand_stat.st_ino):
            raise ValueError("authority root must live outside the candidate competition tree")
        owner_raw = _try_read_dir_leaf(authority_fd, OWNER_RELEASE_NAME, "owner release")
        event_records: list[tuple[str, bytes]] = []
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            events_fd = os.open(EVENT_DIR_NAME, flags, dir_fd=authority_fd)
        except FileNotFoundError:
            events_fd = -1
        except OSError as exc:
            raise ValueError(f"provider events directory: cannot open retained no-follow directory: {exc.strerror}") from exc
        if events_fd >= 0:
            try:
                for name in sorted(os.listdir(events_fd)):
                    if not name.endswith(".json"):
                        continue
                    event_records.append((name, _read_dir_leaf(events_fd, name, f"provider event {name}")))
            finally:
                os.close(events_fd)
        return owner_raw, event_records
    finally:
        os.close(authority_fd)

def _bundle_digest(files: dict[str, bytes]) -> str:
    rows = [{"path": name, "sha256": _sha256(raw)} for name, raw in sorted(files.items())]
    return _sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode())

def _load_candidate(root: Path) -> tuple[dict[str, Any], dict[str, bytes], bytes, bytes, int]:
    fd = _root_fd(root)
    try:
        manifest = _load_json_bytes(_read_root(fd, "readiness.json", "readiness.json"), "readiness.json")
        source_files = manifest.get("source_files")
        source: dict[str, bytes] = {}
        if isinstance(source_files, list):
            for i, item in enumerate(source_files):
                if isinstance(item, str):
                    source[item] = _read_root(fd, item, f"source_files[{i}]")
        draft = _read_root(fd, "PROPOSAL-DRAFT.md", "PROPOSAL-DRAFT.md")
        science = _read_root(fd, "SCIENTIFIC-BASIS.md", "SCIENTIFIC-BASIS.md")
        return manifest, source, draft, science, fd
    except Exception:
        os.close(fd)
        raise

def source_bundle_sha256(root: Path) -> str:
    manifest, source, _, _, fd = _load_candidate(root)
    try:
        names = manifest.get("source_files")
        if not isinstance(names, list) or not names or len(source) != len(names):
            raise ValueError("every source_files entry must be a unique readable string")
        return _bundle_digest(source)
    finally:
        os.close(fd)

def _owner_release(record: dict[str, Any], manifest: dict[str, Any], proposal_sha: str, source_sha: str, now: datetime, errors: list[str]) -> None:
    if record.get("schema") != OWNER_RELEASE_SCHEMA:
        errors.append(f"owner release schema must be {OWNER_RELEASE_SCHEMA}")
    if record.get("carrier_id") != CARRIER_ID:
        errors.append("owner release carrier_id does not match this carrier")
    if record.get("operation_id") != manifest.get("operation_id"):
        errors.append("owner release operation_id does not match readiness.json")
    if record.get("decision") != "AUTHORIZE_SUBMISSION":
        errors.append("owner release decision must be AUTHORIZE_SUBMISSION")
    for field in ("applicant_id", "reviewer_id", "challenge_agreement_generation"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"owner release {field} must be a non-empty opaque identifier")
    if not _hex_digest(record.get("challenge_agreement_sha256")):
        errors.append("owner release challenge_agreement_sha256 must be 64 hex characters")
    if record.get("proposal_sha256") != proposal_sha:
        errors.append("owner release proposal_sha256 does not bind the retained final proposal bytes")
    if record.get("source_bundle_sha256") != source_sha:
        errors.append("owner release source_bundle_sha256 does not bind the retained source bundle")
    gates = record.get("human_gates")
    if not isinstance(gates, dict):
        errors.append("owner release human_gates must be an object")
        gates = {}
    missing = sorted(REQUIRED_GATES - set(gates)); extra = sorted(set(gates) - REQUIRED_GATES)
    if missing: errors.append("owner release missing human gates: " + ", ".join(missing))
    if extra: errors.append("owner release unknown human gates: " + ", ".join(extra))
    false = sorted(name for name in REQUIRED_GATES if gates.get(name) is not True)
    if false: errors.append("owner release requires every human gate true: " + ", ".join(false))
    at = _parse_time(record.get("authorized_at_utc"), "owner release authorized_at_utc", errors)
    until = _parse_time(record.get("valid_until_utc"), "owner release valid_until_utc", errors)
    if at is not None:
        if at > now: errors.append("owner release authorized_at_utc cannot be in the future")
        if at > DEADLINE_UTC: errors.append("owner release authorization occurred after the challenge deadline")
    if until is not None:
        if until > DEADLINE_UTC: errors.append("owner release valid_until_utc cannot exceed the challenge deadline")
        if now > until: errors.append("owner release has expired")

def _events(records: Iterable[tuple[str, bytes]], manifest: dict[str, Any], proposal_sha: str | None, now: datetime, errors: list[str]) -> None:
    seen: dict[str, dict[str, Any]] = {}
    digests: dict[str, str] = {}
    times: dict[str, datetime] = {}
    provider_ids: set[str] = set()
    provider_digests: set[str] = set()
    allowed = {"SUBMITTED", "AWARD_RECEIVED", "PAYMENT_RECEIVED"}
    for i, (name, raw) in enumerate(records):
        label = f"provider event record[{i}] ({name})"
        try:
            record = _load_json_bytes(raw, label)
        except ValueError as exc:
            errors.append(str(exc)); continue
        if record.get("schema") != EVENT_SCHEMA: errors.append(f"{label}: schema must be {EVENT_SCHEMA}")
        if record.get("carrier_id") != CARRIER_ID: errors.append(f"{label}: carrier_id does not match")
        if record.get("operation_id") != manifest.get("operation_id"): errors.append(f"{label}: operation_id does not match readiness.json")
        event = record.get("event")
        if event not in allowed:
            errors.append(f"{label}: event must be one of {sorted(allowed)}"); continue
        if event in seen: errors.append(f"{label}: duplicate event {event}")
        seen[event] = record
        digests[event] = _sha256(raw)
        source_id = record.get("provider_source_id")
        source_sha = record.get("provider_source_sha256")
        if not isinstance(source_id, str) or not source_id.strip():
            errors.append(f"{label}: provider_source_id must be non-empty")
        elif source_id in provider_ids:
            errors.append(f"{label}: provider_source_id must be unique across event records")
        else:
            provider_ids.add(source_id)
        if not _hex_digest(source_sha):
            errors.append(f"{label}: provider_source_sha256 must be 64 hex characters")
        else:
            canonical_source_sha = source_sha.lower()
            if canonical_source_sha in provider_digests:
                errors.append(f"{label}: provider_source_sha256 must be unique across event records")
            else:
                provider_digests.add(canonical_source_sha)
        observed = _parse_time(record.get("observed_at_utc"), f"{label}.observed_at_utc", errors)
        if observed is not None:
            times[event] = observed
            if observed > now: errors.append(f"{label}: observed_at_utc cannot be in the future")
        if proposal_sha is None:
            errors.append(f"{label}: {event} requires a retained final proposal")
        elif record.get("proposal_sha256") != proposal_sha:
            errors.append(f"{label}: {event} proposal_sha256 does not match retained final proposal")
    if "AWARD_RECEIVED" in seen and "SUBMITTED" not in seen:
        errors.append("provider event chain: AWARD_RECEIVED requires SUBMITTED evidence")
    if "PAYMENT_RECEIVED" in seen and "AWARD_RECEIVED" not in seen:
        errors.append("provider event chain: PAYMENT_RECEIVED requires AWARD_RECEIVED evidence")
    if "AWARD_RECEIVED" in seen and "SUBMITTED" in seen:
        if seen["AWARD_RECEIVED"].get("predecessor_event_sha256") != digests["SUBMITTED"]:
            errors.append("provider event chain: AWARD_RECEIVED must bind the exact SUBMITTED event record digest")
        if "AWARD_RECEIVED" in times and "SUBMITTED" in times and times["AWARD_RECEIVED"] < times["SUBMITTED"]:
            errors.append("provider event chain: AWARD_RECEIVED cannot predate SUBMITTED")
    if "PAYMENT_RECEIVED" in seen and "AWARD_RECEIVED" in seen:
        if seen["PAYMENT_RECEIVED"].get("predecessor_event_sha256") != digests["AWARD_RECEIVED"]:
            errors.append("provider event chain: PAYMENT_RECEIVED must bind the exact AWARD_RECEIVED event record digest")
        if "PAYMENT_RECEIVED" in times and "AWARD_RECEIVED" in times and times["PAYMENT_RECEIVED"] < times["AWARD_RECEIVED"]:
            errors.append("provider event chain: PAYMENT_RECEIVED cannot predate AWARD_RECEIVED")

def _validate_impl(root: Path, *, authority_root: Path, now_utc: datetime) -> tuple[str, list[str]]:
    errors: list[str] = []
    now = now_utc.astimezone(timezone.utc)
    try:
        manifest, source, draft_raw, science_raw, fd = _load_candidate(root)
    except (OSError, ValueError) as exc:
        return "UNKNOWN", [str(exc)]
    try:
        try:
            owner_release_raw, event_records = _authority_snapshot(authority_root, fd)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
            owner_release_raw, event_records = None, []
        state = manifest.get("state")
        if manifest.get("schema") != SCHEMA: errors.append(f"schema must be {SCHEMA}")
        if manifest.get("carrier_id") != CARRIER_ID: errors.append(f"carrier_id must be {CARRIER_ID}")
        if manifest.get("operation_id") != OPERATION_ID: errors.append(f"operation_id must be {OPERATION_ID}")
        if state not in {"BLOCKED", "READY"}: errors.append("state must be BLOCKED or READY")

        opportunity = manifest.get("opportunity")
        if not isinstance(opportunity, dict): errors.append("opportunity must be an object"); opportunity = {}
        if opportunity.get("official_url") != OFFICIAL_URL: errors.append("official opportunity URL drifted")
        if opportunity.get("deadline_local") != DEADLINE: errors.append("challenge deadline drifted; revalidate official page before changing it")
        if opportunity.get("advertised_award_usd") != 10000: errors.append("advertised award must remain 10000 unless revalidated and validator updated")

        concept = manifest.get("concept")
        if not isinstance(concept, dict): errors.append("concept must be an object"); concept = {}
        for field, message in [
            ("integrated_prototype_exists", "integrated_prototype_exists must remain false until evidence-backed source update"),
            ("measured_integrated_performance_exists", "measured_integrated_performance_exists must remain false until evidence-backed source update"),
            ("strain_level_claimed", "strain_level_claimed must remain false without binder-specific validation"),
            ("whole_room_claimed", "whole_room_claimed must remain false for this surface-sampling concept"),
        ]:
            if concept.get(field) is not False: errors.append(message)

        names = manifest.get("source_files")
        if not isinstance(names, list) or not names: errors.append("source_files must be a non-empty list")
        else:
            strings = [x for x in names if isinstance(x, str)]
            if len(strings) != len(names): errors.append("every source_files entry must be a string")
            if len(set(strings)) != len(strings): errors.append("source_files must contain unique file names")
            if len(source) != len(strings): errors.append("every source_files entry must be retained and read safely")

        try: draft = draft_raw.decode("utf-8")
        except UnicodeDecodeError: errors.append("PROPOSAL-DRAFT.md must be UTF-8"); draft = ""
        for heading in REQUIRED_PROPOSAL_HEADINGS:
            if heading not in draft: errors.append(f"proposal draft missing form heading: {heading}")
        if OFFICIAL_URL not in draft: errors.append("proposal draft missing official challenge URL")
        try: science = science_raw.decode("utf-8")
        except UnicodeDecodeError: errors.append("SCIENTIFIC-BASIS.md must be UTF-8"); science = ""
        for ref in REQUIRED_SCIENCE_REFS:
            if ref not in science: errors.append(f"scientific basis missing required precedent: {ref}")

        gates = manifest.get("human_observations")
        if not isinstance(gates, dict): errors.append("human_observations must be an object"); gates = {}
        missing = sorted(REQUIRED_GATES - set(gates)); extra = sorted(set(gates) - REQUIRED_GATES)
        if missing: errors.append("missing human observations: " + ", ".join(missing))
        if extra: errors.append("unknown human observations: " + ", ".join(extra))
        for name in REQUIRED_GATES & set(gates):
            if not isinstance(gates[name], bool): errors.append(f"human_observations.{name} must be boolean")

        external = manifest.get("external_observations")
        if not isinstance(external, dict): errors.append("external_observations must be an object"); external = {}
        missing = sorted(EXTERNAL_OBSERVATIONS - set(external)); extra = sorted(set(external) - EXTERNAL_OBSERVATIONS)
        if missing: errors.append("missing external observations: " + ", ".join(missing))
        if extra: errors.append("unknown external observations: " + ", ".join(extra))
        for name in EXTERNAL_OBSERVATIONS & set(external):
            if external[name] is not False:
                errors.append(f"external_observations.{name} is candidate-controlled and must remain false; supply an external provider event record instead")

        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict): errors.append("artifacts must be an object"); artifacts = {}
        final = artifacts.get("final_proposal")
        if not isinstance(final, dict): errors.append("artifacts.final_proposal must be an object"); final = {}
        final_path, final_sha = final.get("path"), final.get("sha256")
        if (final_path is None) != (final_sha is None): errors.append("final proposal path and sha256 must be set together")
        proposal_raw: bytes | None = None; proposal_digest: str | None = None
        if final_path is not None:
            if not isinstance(final_path, str) or not isinstance(final_sha, str): errors.append("final proposal path and sha256 must be strings")
            elif not _hex_digest(final_sha): errors.append("artifacts.final_proposal.sha256 must be 64 hex characters")
            else:
                try: proposal_raw = _read_root(fd, final_path, "artifacts.final_proposal.path")
                except ValueError as exc: errors.append(str(exc))
                if proposal_raw is not None:
                    proposal_digest = _sha256(proposal_raw)
                    if proposal_digest != final_sha.lower(): errors.append("final proposal sha256 does not match retained file bytes")
        source_digest = _bundle_digest(source) if source else None

        if state == "BLOCKED" and owner_release_raw is not None:
            errors.append("BLOCKED candidate cannot coexist with a retained owner-release authorization")
        if state == "READY":
            false = sorted(name for name in REQUIRED_GATES if gates.get(name) is not True)
            if false: errors.append("READY candidate observations require every human gate true: " + ", ".join(false))
            if now > DEADLINE_UTC: errors.append("READY is expired: verifier-owned UTC is after the official deadline")
            if final_path is None or proposal_raw is None or proposal_digest is None:
                errors.append("READY requires a retained hashed final human proposal artifact")
            elif final_path == "PROPOSAL-DRAFT.md":
                errors.append("READY final proposal must be a separate human-rewritten artifact, not PROPOSAL-DRAFT.md")
            else:
                try: text = proposal_raw.decode("utf-8")
                except UnicodeDecodeError: errors.append("final human proposal must be UTF-8"); text = ""
                for marker in ("[HUMAN:", "[UNMEASURED", "DO NOT SUBMIT THIS FILE VERBATIM"):
                    if marker in text: errors.append(f"final human proposal still contains draft marker: {marker}")
            if owner_release_raw is None:
                errors.append(f"READY requires retained owner authority at fixed host path {authority_root / OWNER_RELEASE_NAME}")
            elif proposal_digest is not None and source_digest is not None:
                try: record = _load_json_bytes(owner_release_raw, "owner release")
                except ValueError as exc: errors.append(str(exc))
                else: _owner_release(record, manifest, proposal_digest, source_digest, now, errors)

        _events(event_records, manifest, proposal_digest, now, errors)
        return str(state or "UNKNOWN"), errors
    finally:
        os.close(fd)

def _bind_validation_surfaces(impl):
    """Bind current authority/time once; module-global rebinding cannot redirect production validation."""
    fixed_authority_root = AUTHORITY_ROOT
    process_now = datetime.now
    utc = timezone.utc

    def current_validate(root: Path) -> tuple[str, list[str]]:
        return impl(root, authority_root=fixed_authority_root, now_utc=process_now(utc))

    def test_only_validate(root: Path, *, authority_root: Path, now_utc: datetime) -> tuple[str, list[str]]:
        state, errors = impl(root, authority_root=authority_root, now_utc=now_utc)
        return f"TEST_ONLY_{state}", errors

    return current_validate, test_only_validate

validate, _validate_with_context_for_tests = _bind_validation_surfaces(_validate_impl)
del _validate_impl
del _bind_validation_surfaces

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    p.add_argument("--require-ready", action="store_true")
    a = p.parse_args(argv)
    state, errors = validate(a.root)
    print(json.dumps({"state": state, "valid": not errors, "errors": errors}, indent=2, sort_keys=True))
    if errors: return 1
    if a.require_ready and state != "READY": return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
