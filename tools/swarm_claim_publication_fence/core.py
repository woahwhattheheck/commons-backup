from __future__ import annotations

import hashlib
import json
import os
import stat
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .schema import MAX_INPUT_BYTES, ValidationError, claim_key, message_key, parse_slack_ts, validate_snapshot

class VerificationError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise ValidationError(f"non-finite JSON number forbidden: {value}")


def _object_pairs_no_duplicates(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValidationError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict_json(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_object_pairs_no_duplicates, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON: {exc.msg}") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _target_claim(snapshot: Dict[str, Any]) -> Dict[str, str]:
    return {**snapshot["identity"], **snapshot["candidate"]}


def _same_target(claim: Dict[str, str], target: Dict[str, str]) -> bool:
    return claim_key(claim) == claim_key(target)


def _claim_summary(claim: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
    if claim is None:
        return None
    return {
        "channel_id": claim["channel_id"],
        "message_ts": claim["message_ts"],
        "author_id": claim["author_id"],
        "seat_id": claim["seat_id"],
    }


def classify(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    target = _target_claim(snapshot)
    history_claims: List[Dict[str, str]] = snapshot["history"]["claims"]
    material = [row for row in history_claims if _same_target(row, target)]
    material.sort(key=lambda row: (parse_slack_ts(row["message_ts"], "message_ts"), row["author_id"], row["seat_id"]))
    # Exact search only indexes the requested digest. The complete channel
    # census must also expose other digests for this SAME work key and role:
    # differing scope descriptions must not silently authorize two writers.
    scope_conflicts = [
        row for row in history_claims
        if row["work_key"] == target["work_key"]
        and row["role"] == target["role"]
        and row["scope_digest_sha256"] != target["scope_digest_sha256"]
    ]
    scope_conflicts.sort(key=lambda row: (parse_slack_ts(row["message_ts"], "message_ts"), row["author_id"], row["seat_id"]))
    history_by_message = {message_key(row): row for row in material}
    search_matches: List[Dict[str, str]] = snapshot["search"]["matches"]
    search_by_message = {message_key(row): row for row in search_matches}
    candidate_key = message_key(target)

    candidate_visible = False
    retained_candidate = history_by_message.get(candidate_key)
    if retained_candidate is not None:
        candidate_visible = retained_candidate == target

    search_extra_keys = set(search_by_message) - set(history_by_message)
    search_missing_keys = set(history_by_message) - set(search_by_message)
    shared_mismatch_keys = {
        key for key in (set(search_by_message) & set(history_by_message))
        if search_by_message[key] != history_by_message[key]
    }
    search_extra = sorted(search_extra_keys | shared_mismatch_keys, key=lambda key: parse_slack_ts(key[1], "search message_ts"))
    search_missing = sorted(search_missing_keys | shared_mismatch_keys, key=lambda key: parse_slack_ts(key[1], "history message_ts"))
    earliest = material[0] if material else None
    candidate_is_earliest = bool(candidate_visible and earliest is not None and message_key(earliest) == candidate_key and earliest == target)
    earlier_claim = earliest if earliest is not None and parse_slack_ts(earliest["message_ts"], "earliest.message_ts") < parse_slack_ts(target["message_ts"], "candidate.message_ts") else None

    if not snapshot["history"]["complete"]:
        status = "HOLD_NO_HISTORY_CENSUS"
        next_action = "REFRESH_FULL_CHANNEL"
        reason = "supplied history window is not asserted complete"
    elif not candidate_visible:
        status = "HOLD_CANDIDATE_NOT_VISIBLE"
        next_action = "REFRESH_FULL_CHANNEL"
        reason = "candidate TAKE is not visible as the exact retained history row"
    elif earlier_claim is not None:
        status = "HOLD_EARLIER_CLAIM"
        next_action = "YIELD_EARLIER"
        reason = "an earlier materially-same retained TAKE is visible in full history"
    elif search_extra:
        status = "HOLD_HISTORY_MISMATCH"
        next_action = "REFRESH_FULL_CHANNEL"
        reason = "exact search contains message identities absent from supplied full history"
    elif search_missing:
        status = "HOLD_INDEX_DIVERGENCE"
        next_action = "WAIT_INDEX_CONVERGENCE"
        reason = "full history contains materially-same claims missing from exact search results"
    elif scope_conflicts:
        status = "HOLD_SCOPE_DIGEST_CONFLICT"
        next_action = "RECONCILE_SCOPE_OWNERSHIP"
        reason = "full history contains another TAKE for the same work key and role with a different scope digest"
    elif candidate_is_earliest:
        status = "CANDIDATE_VISIBLE_EARLIEST"
        next_action = "PROCEED_TO_SEPARATE_MUTATION_FENCE"
        reason = "candidate is visible and earliest; retained history/search sets converge"
    else:
        status = "HOLD_HISTORY_MISMATCH"
        next_action = "REFRESH_FULL_CHANNEL"
        reason = "retained candidate identity does not establish earliest exact custody"

    return {
        "status": status,
        "reason": reason,
        "recommended_next_action": next_action,
        "candidate_visible_in_history": candidate_visible,
        "candidate_is_earliest": candidate_is_earliest,
        "index_divergence": bool(search_missing),
        "history_search_mismatch": bool(search_extra),
        "material_history_claim_count": len(material),
        "scope_digest_conflict_count": len(scope_conflicts),
        "scope_digest_conflict_message_ts": [row["message_ts"] for row in scope_conflicts],
        "search_match_count": len(search_matches),
        "search_missing_message_ts": [key[1] for key in search_missing],
        "search_extra_message_ts": [key[1] for key in search_extra],
        "earliest_claim": _claim_summary(earliest),
    }


def render_markdown(report: Dict[str, Any]) -> str:
    c = report["classification"]
    identity = report["identity"]
    lines = [
        "# Swarm claim publication fence",
        "",
        f"- Status: `{c['status']}`",
        f"- Work key: `{identity['work_key']}`",
        f"- Role: `{identity['role']}`",
        f"- Scope digest: `{identity['scope_digest_sha256']}`",
        f"- Candidate visible: `{str(c['candidate_visible_in_history']).lower()}`",
        f"- Candidate earliest: `{str(c['candidate_is_earliest']).lower()}`",
        f"- Index divergence: `{str(c['index_divergence']).lower()}`",
        f"- History/search mismatch: `{str(c['history_search_mismatch']).lower()}`",
        f"- Same-work scope conflicts: `{c['scope_digest_conflict_count']}`",
        f"- Scope-conflict message timestamps: `{', '.join(c['scope_digest_conflict_message_ts']) or 'none'}`",
        f"- Next action: `{c['recommended_next_action']}`",
        "",
        c["reason"],
        "",
        "## Authority ceiling",
        "",
        "This retained-packet consistency result does not authenticate Slack, mint a lease, authorize GitHub/Slack/Muse mutation, authorize external/provider send, or recognize payment/cash/revenue. Even `CANDIDATE_VISIBLE_EARLIEST` requires a fresh live provider recensus and a separate mutation fence.",
        "",
    ]
    return "\n".join(lines)


def compile_snapshot(raw_snapshot: Any) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
    snapshot = validate_snapshot(raw_snapshot)
    snapshot_text = canonical_json(snapshot)
    compiler_id = "swarm-claim-publication-fence/v1"
    report: Dict[str, Any] = {
        "schema_version": 1,
        "compiler": compiler_id,
        "snapshot_sha256": sha256_text(snapshot_text),
        "issued_at": snapshot["issued_at"],
        "identity": snapshot["identity"],
        "candidate": snapshot["candidate"],
        "classification": classify(snapshot),
        "authority": {
            "slack_authenticated": False,
            "slack_lease_authorized": False,
            "github_mutation_authorized": False,
            "slack_mutation_authorized": False,
            "muse_mutation_authorized": False,
            "external_outbound_authorized": False,
            "provider_send_authorized": False,
            "payment_authorized": False,
            "cash_or_revenue_recognized": False,
        },
    }
    report_text = canonical_json(report)
    markdown = render_markdown(report)
    receipt = {
        "schema_version": 1,
        "compiler": compiler_id,
        "snapshot_sha256": report["snapshot_sha256"],
        "report_json_sha256": sha256_text(report_text),
        "report_markdown_sha256": sha256_text(markdown),
        "semantic_verification": "EXACT_RECOMPILE_REQUIRED",
    }
    return report, markdown, receipt


def verify_compilation(raw_snapshot: Any, raw_report: Any, report_markdown: str, raw_receipt: Any) -> None:
    expected_report, expected_markdown, expected_receipt = compile_snapshot(raw_snapshot)
    if canonical_json(raw_report) != canonical_json(expected_report):
        raise VerificationError("report JSON does not equal semantic recompilation")
    if report_markdown != expected_markdown:
        raise VerificationError("report Markdown does not equal semantic recompilation")
    if canonical_json(raw_receipt) != canonical_json(expected_receipt):
        raise VerificationError("receipt does not equal semantic recompilation")


def read_text_file(path: str, *, max_bytes: int = MAX_INPUT_BYTES) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValidationError(f"not a regular file: {path}")
        if st.st_size > max_bytes:
            raise ValidationError(f"file exceeds {max_bytes} bytes: {path}")
        chunks = []
        remaining = max_bytes + 1
        while remaining > 0:
            data = os.read(fd, min(65_536, remaining))
            if not data:
                break
            chunks.append(data)
            remaining -= len(data)
        raw = b"".join(chunks)
        if len(raw) > max_bytes:
            raise ValidationError(f"file exceeds {max_bytes} bytes: {path}")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError(f"file is not UTF-8: {path}") from exc
    finally:
        os.close(fd)


def _output_dir_flags() -> int:
    if not hasattr(os, "O_DIRECTORY") or os.open not in os.supports_dir_fd or os.unlink not in os.supports_dir_fd:
        raise ValidationError("platform lacks required descriptor-anchored output custody")
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _assert_output_dir_identity(parent_path: str, expected: Tuple[int, int]) -> None:
    check_fd = os.open(parent_path, _output_dir_flags())
    try:
        st = os.fstat(check_fd)
        if not stat.S_ISDIR(st.st_mode) or (st.st_dev, st.st_ino) != expected:
            raise ValidationError("output directory generation changed during publication")
    finally:
        os.close(check_fd)


def _write_new_at(dir_fd: int, name: str, text: str, created: List[str]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(name, flags, 0o600, dir_fd=dir_fd)
    try:
        # Rollback owns this path as soon as exclusive creation succeeds.
        created.append(name)
        data = text.encode("utf-8")
        offset = 0
        while offset < len(data):
            written = os.write(fd, data[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(fd)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValidationError("output is not regular file")
        if st.st_mode & 0o777 != 0o600:
            raise ValidationError("output mode is not 0600")
    finally:
        os.close(fd)


def _read_back_at(dir_fd: int, name: str, expected_text: str) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(name, flags, dir_fd=dir_fd)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValidationError("published output is not regular file")
        expected = expected_text.encode("utf-8")
        chunks = []
        remaining = len(expected) + 1
        while remaining > 0:
            data = os.read(fd, min(65_536, remaining))
            if not data:
                break
            chunks.append(data)
            remaining -= len(data)
        if b"".join(chunks) != expected:
            raise ValidationError("published output readback mismatch")
    finally:
        os.close(fd)


def write_compilation(prefix: str, report: Dict[str, Any], markdown: str, receipt: Dict[str, Any]) -> List[str]:
    if type(prefix) is not str or not prefix:
        raise ValidationError("output prefix must be a non-empty string")
    parent_path = os.path.abspath(os.path.dirname(prefix) or ".")
    base = os.path.basename(prefix)
    if base in ("", ".", ".."):
        raise ValidationError("output prefix basename is invalid")
    outputs = [
        (base + ".report.json", prefix + ".report.json", canonical_json(report)),
        (base + ".report.md", prefix + ".report.md", markdown),
        (base + ".receipt.json", prefix + ".receipt.json", canonical_json(receipt)),
    ]
    dir_fd = os.open(parent_path, _output_dir_flags())
    created: List[str] = []
    try:
        parent_stat = os.fstat(dir_fd)
        if not stat.S_ISDIR(parent_stat.st_mode):
            raise ValidationError("output parent is not a directory")
        identity = (parent_stat.st_dev, parent_stat.st_ino)
        for name, visible_path, text in outputs:
            _assert_output_dir_identity(parent_path, identity)
            _write_new_at(dir_fd, name, text, created)
        _assert_output_dir_identity(parent_path, identity)
        for name, _, text in outputs:
            _read_back_at(dir_fd, name, text)
        os.fsync(dir_fd)
        _assert_output_dir_identity(parent_path, identity)
        return [visible_path for _, visible_path, _ in outputs]
    except Exception:
        for name in reversed(created):
            try:
                os.unlink(name, dir_fd=dir_fd)
            except FileNotFoundError:
                pass
        try:
            os.fsync(dir_fd)
        except OSError:
            pass
        raise
    finally:
        os.close(dir_fd)
