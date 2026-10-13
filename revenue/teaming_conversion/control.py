from __future__ import annotations

import json
import marshal
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .assets import evaluate_assets
from .common import (
    ControlError,
    MAX_JSON_BYTES,
    canonical_bytes,
    digest_object,
    format_timestamp,
    parse_json_bytes,
    require_exact_keys,
    require_object,
    require_string,
    require_timestamp,
    sha256_bytes,
    sorted_unique,
)
from .evidence import (
    evaluate_evidence,
    select_and_validate_root,
    summarize_interpretation,
    summarize_observation,
)
from .parse import (
    RECEIPT_SCHEMA,
    ParsedRoot,
    parse_candidate,
    parse_evidence,
    parse_roots,
)
from .policy import POLICY_SHA256, policy_dict
from .qualification import evaluate_qualification
from .trusted_roots import load_current_roots_bytes

CURRENT_MODE = "CURRENT_EVIDENCE"
HISTORICAL_MODE = "HISTORICAL_INTEGRITY_ONLY"

_EXTERNAL_AUTHORITY = {
    "contact_or_send": False,
    "portal_or_provider_mutation": False,
    "proposal_or_submission": False,
    "pricing_staffing_reference_or_other_commitment": False,
    "contract_or_signature": False,
    "spend_or_payment": False,
    "award_or_acceptance_claim": False,
    "cash_or_revenue_recognition": False,
}
_EXTERNAL_AUTHORITY_ITEMS = tuple(_EXTERNAL_AUTHORITY.items())

_POLICY_AT_IMPORT = policy_dict()
_POLICY_ID = str(_POLICY_AT_IMPORT["policy_id"])
_POLICY_VERSION = str(_POLICY_AT_IMPORT["policy_version"])
_MAX_CURRENT_RECEIPT_AGE_SECONDS = int(
    _POLICY_AT_IMPORT["max_current_receipt_age_seconds"]
)
_POLICY_SHA256_AT_IMPORT = POLICY_SHA256
del _POLICY_AT_IMPORT


def _make_utc_clock(
    _time=time.time,
    _fromtimestamp=datetime.fromtimestamp,
    _utc=timezone.utc,
):
    def current_utc() -> datetime:
        return _fromtimestamp(_time(), tz=_utc).replace(microsecond=0)

    return current_utc


_utc_now = _make_utc_clock()
del _make_utc_clock


def _root_summary(
    root: ParsedRoot | None,
    _format_timestamp=format_timestamp,
) -> dict[str, Any] | None:
    if root is None:
        return None
    return {
        "root_id": root.root_id,
        "opportunity_id": root.opportunity_id,
        "counterparty_ref": root.counterparty_ref,
        "thread_id": root.thread_id,
        "generation": root.generation,
        "active_from": _format_timestamp(root.active_from),
        "expires_at": _format_timestamp(root.expires_at),
    }


def _decision_core(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_sha256": receipt["policy"]["sha256"],
        "root": receipt["trusted_root"],
        "opportunity": receipt["opportunity"],
        "current_observation": receipt["current_observation"],
        "owner_interpretation": receipt["owner_interpretation"],
        "disposition": receipt["disposition"],
        "trust_blockers": receipt["trust_blockers"],
        "qualification_blockers": receipt["qualification_blockers"],
        "asset_blockers": receipt["asset_blockers"],
        "owner_actions": receipt["owner_actions"],
        "safe_assets": receipt["safe_assets"],
        "safe_commercial_facts": receipt["safe_commercial_facts"],
        "external_authority": receipt["external_authority"],
    }


def _compile_at(
    candidate_bytes: bytes,
    evidence_bytes: bytes,
    roots_bytes: bytes,
    *,
    evaluated_at: datetime,
    mode: str,
    _policy_id: str = _POLICY_ID,
    _policy_version: str = _POLICY_VERSION,
    _policy_sha256: str = _POLICY_SHA256_AT_IMPORT,
    _max_current_receipt_age_seconds: int = _MAX_CURRENT_RECEIPT_AGE_SECONDS,
    _external_authority_items: tuple[tuple[str, bool], ...] = _EXTERNAL_AUTHORITY_ITEMS,
    _parse_json_bytes=parse_json_bytes,
    _parse_candidate=parse_candidate,
    _parse_evidence=parse_evidence,
    _parse_roots=parse_roots,
    _select_and_validate_root=select_and_validate_root,
    _evaluate_evidence=evaluate_evidence,
    _evaluate_assets=evaluate_assets,
    _evaluate_qualification=evaluate_qualification,
    _summarize_observation=summarize_observation,
    _summarize_interpretation=summarize_interpretation,
    _sorted_unique=sorted_unique,
    _sha256_bytes=sha256_bytes,
    _digest_object=digest_object,
    _format_timestamp=format_timestamp,
    _timedelta=timedelta,
    _utc=timezone.utc,
    _root_summary_fn=_root_summary,
    _decision_core_fn=_decision_core,
) -> dict[str, Any]:
    if mode not in {CURRENT_MODE, HISTORICAL_MODE}:
        raise ControlError("unknown compile mode")
    now = evaluated_at.astimezone(_utc).replace(microsecond=0)
    candidate_value = _parse_json_bytes(candidate_bytes, label="candidate")
    evidence_value = _parse_json_bytes(evidence_bytes, label="retained evidence")
    roots_value = _parse_json_bytes(roots_bytes, label="trusted roots")
    candidate = _parse_candidate(candidate_value)
    evidence = _parse_evidence(evidence_value)
    normalized_roots, roots = _parse_roots(roots_value)

    root, root_blockers = _select_and_validate_root(
        candidate,
        evidence,
        roots,
        evidence_bytes=evidence_bytes,
        now=now,
    )
    evidence_result = _evaluate_evidence(candidate, evidence, now=now)
    asset_result = _evaluate_assets(candidate, evidence, now=now)
    qualification_result = _evaluate_qualification(candidate, evidence, now=now)

    asset_trust_blockers = [
        item for item in asset_result["blockers"] if item.startswith("asset_release_")
    ]
    asset_state_blockers = [
        item for item in asset_result["blockers"] if item not in asset_trust_blockers
    ]
    qualification_trust_prefixes = (
        "qualification_decision_",
        "commitment_decision_",
    )
    qualification_trust_blockers = [
        item
        for item in qualification_result["blockers"]
        if item.startswith(qualification_trust_prefixes)
    ]
    qualification_state_blockers = [
        item
        for item in qualification_result["blockers"]
        if item not in qualification_trust_blockers
    ]
    trust_blockers = _sorted_unique(
        root_blockers
        + evidence_result["blockers"]
        + asset_trust_blockers
        + qualification_trust_blockers
    )
    qualification_blockers = _sorted_unique(qualification_state_blockers)
    asset_blockers = _sorted_unique(asset_state_blockers)

    interpretation = evidence_result["current_interpretation"]
    decision = interpretation["decision"] if interpretation is not None else None
    if trust_blockers:
        disposition = "HOLD"
    elif decision == "DECLINED":
        disposition = "DECLINED"
    elif decision in {"REQUESTED_MORE_INFO", "AMBIGUOUS"}:
        disposition = "NEEDS_CLARIFICATION"
    elif qualification_blockers:
        disposition = "QUALIFICATION_BLOCKED"
    elif asset_blockers:
        disposition = "ASSET_PREP_REQUIRED"
    elif decision in {"POSITIVE_CONTINUE", "CONDITIONAL_INTEREST"}:
        disposition = "FOLLOWUP_READY"
    else:
        disposition = "HOLD"
        trust_blockers = _sorted_unique(
            trust_blockers + ["positive_interpretation_missing"]
        )

    valid_until_candidates = [
        evidence_result["reply_valid_until"],
        evidence_result["source_valid_until"],
        now + _timedelta(seconds=_max_current_receipt_age_seconds),
    ]
    if root is not None:
        valid_until_candidates.append(root.expires_at)
    current_valid_until = min(valid_until_candidates)

    trusted = not root_blockers
    safe_assets = asset_result["safe_assets"] if trusted else []
    safe_facts = qualification_result["safe_facts"] if trusted else []
    owner_actions = _sorted_unique(
        evidence_result["owner_actions"]
        + asset_result["owner_actions"]
        + qualification_result["owner_actions"]
    )
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "mode": mode,
        "historical_integrity_only": mode == HISTORICAL_MODE,
        "evaluated_at": _format_timestamp(now),
        "current_valid_until": _format_timestamp(current_valid_until),
        "policy": {
            "policy_id": _policy_id,
            "policy_version": _policy_version,
            "sha256": _policy_sha256,
            "source": "repository_owned_constant",
        },
        "custody": {
            "mode": "exact_json_bytes",
            "candidate_sha256": _sha256_bytes(candidate_bytes),
            "evidence_sha256": _sha256_bytes(evidence_bytes),
            "trusted_roots_sha256": _sha256_bytes(roots_bytes),
            "normalized_roots_sha256": _digest_object(normalized_roots),
        },
        "trusted_root": _root_summary_fn(root),
        "opportunity": {
            "opportunity_id": candidate.opportunity_id,
            "counterparty_ref": candidate.counterparty_ref,
            "thread_id": candidate.thread_id,
        },
        "current_observation": _summarize_observation(
            evidence_result["current_observation"]
        ),
        "owner_interpretation": _summarize_interpretation(interpretation),
        "disposition": disposition,
        "trust_blockers": trust_blockers,
        "qualification_blockers": qualification_blockers,
        "asset_blockers": asset_blockers,
        "owner_actions": owner_actions,
        "safe_assets": safe_assets,
        "safe_commercial_facts": safe_facts,
        "owner_review_only": True,
        "external_authority": dict(_external_authority_items),
    }
    receipt["decision_sha256"] = _digest_object(_decision_core_fn(receipt))
    return receipt


# CURRENT authority is executed in a fresh isolated interpreter, not in the
# caller's mutable Python module graph. The parent-side transport uses captured
# C-level POSIX/marshal primitives only; post-import monkeypatches of package
# helpers cannot influence the child that reads current roots/policy.
_CURRENT_REPO_ROOT = str(Path(__file__).resolve().parents[2])
_CURRENT_WORKER_CODE = (
    "import sys;"
    f"sys.path.insert(0,{_CURRENT_REPO_ROOT!r});"
    "from revenue.teaming_conversion._current_worker import main;"
    "raise SystemExit(main())"
)
_CURRENT_OPT_FLAG = (
    "-OO" if sys.flags.optimize >= 2 else ("-O" if sys.flags.optimize == 1 else None)
)
_CURRENT_WORKER_ARGV = (
    (sys.executable, "-I", _CURRENT_OPT_FLAG, "-c", _CURRENT_WORKER_CODE)
    if _CURRENT_OPT_FLAG is not None
    else (sys.executable, "-I", "-c", _CURRENT_WORKER_CODE)
)
_MAX_CURRENT_WIRE_BYTES = 8 * MAX_JSON_BYTES


def _make_current_rpc(
    _pipe=os.pipe,
    _spawn=getattr(os, "posix_spawn", None),
    _spawn_dup2=getattr(os, "POSIX_SPAWN_DUP2", None),
    _spawn_close=getattr(os, "POSIX_SPAWN_CLOSE", None),
    _close=os.close,
    _write=os.write,
    _read=os.read,
    _waitpid=os.waitpid,
    _marshal_dumps=marshal.dumps,
    _marshal_loads=marshal.loads,
    _argv: tuple[str, ...] = _CURRENT_WORKER_ARGV,
    _executable: str = sys.executable,
    _max_wire_bytes: int = _MAX_CURRENT_WIRE_BYTES,
    _error=ControlError,
    _len=len,
):
    def fail_closed_unavailable(*_args: Any) -> Any:
        raise _error("CURRENT authority requires POSIX isolated-exec support")

    if _spawn is None or _spawn_dup2 is None or _spawn_close is None:
        return fail_closed_unavailable

    def write_all(fd: int, data: bytes) -> None:
        offset = 0
        size = _len(data)
        while offset < size:
            written = _write(fd, data[offset:])
            if written <= 0:
                raise _error("CURRENT authority worker input write failed")
            offset += written

    def read_all(fd: int) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = _read(fd, 65_536)
            if not chunk:
                break
            chunks.append(chunk)
            total += _len(chunk)
            if total > _max_wire_bytes:
                raise _error("CURRENT authority worker output is too large")
        return b"".join(chunks)

    def current_rpc(operation: str, *payload: bytes) -> Any:
        try:
            request = _marshal_dumps((operation, *payload))
        except (TypeError, ValueError) as exc:
            raise _error("CURRENT authority request is not serializable") from exc
        if _len(request) > _max_wire_bytes:
            raise _error("CURRENT authority request is too large")

        stdin_r, stdin_w = _pipe()
        stdout_r, stdout_w = _pipe()
        file_actions = (
            (_spawn_dup2, stdin_r, 0),
            (_spawn_dup2, stdout_w, 1),
            (_spawn_close, stdin_w),
            (_spawn_close, stdout_r),
            (_spawn_close, stdin_r),
            (_spawn_close, stdout_w),
        )
        try:
            pid = _spawn(_executable, _argv, {}, file_actions=file_actions)
        except OSError as exc:
            for fd in (stdin_r, stdin_w, stdout_r, stdout_w):
                try:
                    _close(fd)
                except OSError:
                    pass
            raise _error("CURRENT authority worker could not start") from exc

        _close(stdin_r)
        _close(stdout_w)
        write_error: OSError | None = None
        try:
            write_all(stdin_w, request)
        except OSError as exc:
            write_error = exc
        finally:
            _close(stdin_w)

        response_bytes = b""
        read_error: OSError | None = None
        try:
            response_bytes = read_all(stdout_r)
        except OSError as exc:
            read_error = exc
        finally:
            _close(stdout_r)

        _, status = _waitpid(pid, 0)
        if write_error is not None:
            raise _error("CURRENT authority worker input write failed") from write_error
        if read_error is not None:
            raise _error("CURRENT authority worker output read failed") from read_error
        if status != 0:
            raise _error("CURRENT authority worker exited unsuccessfully")
        try:
            response = _marshal_loads(response_bytes)
        except (EOFError, TypeError, ValueError) as exc:
            raise _error("CURRENT authority worker returned an invalid response") from exc
        if (
            type(response) is not tuple
            or _len(response) != 2
            or response[0] not in {"ok", "error"}
        ):
            raise _error("CURRENT authority worker returned an invalid envelope")
        if response[0] == "error":
            raise _error(str(response[1]))
        return response[1]

    return current_rpc


_CURRENT_RPC = _make_current_rpc()
del _make_current_rpc


def _make_compile_current(_rpc=_CURRENT_RPC):
    def compile_current_bytes(
        candidate_bytes: bytes,
        evidence_bytes: bytes,
    ) -> dict[str, Any]:
        result = _rpc("compile", candidate_bytes, evidence_bytes)
        if type(result) is not dict:
            raise ControlError("CURRENT authority worker returned a non-object receipt")
        return result

    return compile_current_bytes


compile_current_bytes = _make_compile_current()
del _make_compile_current


def compile_historical_bytes(
    candidate_bytes: bytes,
    evidence_bytes: bytes,
    roots_bytes: bytes,
    *,
    evaluated_at: datetime,
) -> dict[str, Any]:
    return _compile_at(
        candidate_bytes,
        evidence_bytes,
        roots_bytes,
        evaluated_at=evaluated_at,
        mode=HISTORICAL_MODE,
    )


def parse_receipt_bytes(
    receipt_bytes: bytes,
    _parse_json_bytes=parse_json_bytes,
    _require_object=require_object,
    _require_exact_keys=require_exact_keys,
    _require_string=require_string,
    _require_timestamp=require_timestamp,
) -> dict[str, Any]:
    value = _parse_json_bytes(receipt_bytes, label="receipt")
    receipt = _require_object(value, "receipt")
    required = {
        "schema",
        "mode",
        "historical_integrity_only",
        "evaluated_at",
        "current_valid_until",
        "policy",
        "custody",
        "trusted_root",
        "opportunity",
        "current_observation",
        "owner_interpretation",
        "disposition",
        "trust_blockers",
        "qualification_blockers",
        "asset_blockers",
        "owner_actions",
        "safe_assets",
        "safe_commercial_facts",
        "owner_review_only",
        "external_authority",
        "decision_sha256",
    }
    _require_exact_keys(receipt, required=required, label="receipt")
    if _require_string(receipt["schema"], "receipt.schema", maximum=128) != RECEIPT_SCHEMA:
        raise ControlError(f"receipt.schema must be {RECEIPT_SCHEMA}")
    if _require_string(receipt["mode"], "receipt.mode", maximum=64) not in {
        CURRENT_MODE,
        HISTORICAL_MODE,
    }:
        raise ControlError("receipt.mode is unknown")
    _require_timestamp(receipt["evaluated_at"], "receipt.evaluated_at")
    _require_timestamp(receipt["current_valid_until"], "receipt.current_valid_until")
    return receipt


def verify_integrity_bytes(
    candidate_bytes: bytes,
    evidence_bytes: bytes,
    roots_bytes: bytes,
    receipt_bytes: bytes,
) -> bool:
    receipt = parse_receipt_bytes(receipt_bytes)
    evaluated_at = require_timestamp(receipt["evaluated_at"], "receipt.evaluated_at")
    rebuilt = _compile_at(
        candidate_bytes,
        evidence_bytes,
        roots_bytes,
        evaluated_at=evaluated_at,
        mode=receipt["mode"],
    )
    return canonical_bytes(rebuilt) == receipt_bytes


def _make_verify_current(_rpc=_CURRENT_RPC):
    def verify_current_bytes(
        candidate_bytes: bytes,
        evidence_bytes: bytes,
        receipt_bytes: bytes,
    ) -> dict[str, Any]:
        result = _rpc("verify", candidate_bytes, evidence_bytes, receipt_bytes)
        if type(result) is not dict:
            raise ControlError("CURRENT authority worker returned a non-object verification")
        return result

    return verify_current_bytes


verify_current_bytes = _make_verify_current()
del _make_verify_current


def render_markdown(receipt: dict[str, Any]) -> str:
    parse_receipt_bytes(canonical_bytes(receipt))

    def literal(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    lines = [
        "# Teaming Conversion Control",
        "",
        f"- Mode: `{receipt['mode']}`",
        f"- Evaluated at: `{receipt['evaluated_at']}`",
        f"- Current-valid until: `{receipt['current_valid_until']}`",
        f"- Disposition: **{receipt['disposition']}**",
        f"- Opportunity: `{receipt['opportunity']['opportunity_id']}`",
        f"- Counterparty: `{receipt['opportunity']['counterparty_ref']}`",
        f"- Thread: `{receipt['opportunity']['thread_id']}`",
        f"- Decision SHA-256: `{receipt['decision_sha256']}`",
        "",
    ]
    if receipt["historical_integrity_only"]:
        lines.extend(
            [
                "> Historical integrity only. This output is not a current-readiness claim.",
                "",
            ]
        )
    lines.extend(["## Trust blockers", ""])
    lines.extend(
        [f"- {literal(item)}" for item in receipt["trust_blockers"]]
        or ["- None"]
    )
    lines.extend(["", "## Qualification blockers", ""])
    lines.extend(
        [f"- {literal(item)}" for item in receipt["qualification_blockers"]]
        or ["- None"]
    )
    lines.extend(["", "## Asset blockers", ""])
    lines.extend(
        [f"- {literal(item)}" for item in receipt["asset_blockers"]]
        or ["- None"]
    )
    lines.extend(["", "## Owner actions", ""])
    lines.extend([f"- {literal(item)}" for item in receipt["owner_actions"]] or ["- None"])
    lines.extend(["", "## Prospect-safe assets", ""])
    lines.extend(
        [f"- `{item['asset_id']}` — {literal(item['title'])}" for item in receipt["safe_assets"]]
        or ["- None"]
    )
    lines.extend(["", "## Safe commercial facts", ""])
    lines.extend(
        [f"- `{item['commitment_id']}` — {literal(item['safe_fact'])}" for item in receipt["safe_commercial_facts"]]
        or ["- None"]
    )
    lines.extend(
        [
            "",
            "## Authority ceiling",
            "",
            "This receipt is owner-review support only. It grants no contact, send, provider mutation, submission, commercial commitment, signature, spend, payment, award claim, cash, or revenue-recognition authority.",
            "",
        ]
    )
    return "\n".join(lines)
