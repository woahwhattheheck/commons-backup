"""Evidence-bound bid deadline to owner-action critical-path compiler.

The compiler schedules and explains owner actions. It never authenticates to a
portal, signs, submits, contacts a buyer, recognizes an award, or recognizes
payment/revenue.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA = "bid-deadline-critical-path/input/v1"
PACKET_SCHEMA = "bid-deadline-critical-path/packet/v1"
RECEIPT_SCHEMA = "bid-deadline-critical-path/receipt/v1"
TRUTH_BOUNDARY = "OWNER_ACTION_PLANNING_ONLY"
CURRENTNESS_BASIS = "OWNER_SUPPLIED_EVALUATION_TIME_NOT_BUYER_CLOCK"

SOURCE_AUTHORITIES = {"BUYER_OFFICIAL", "CURATED_EXPORT", "SYNTHETIC_FIXTURE"}
AMENDMENT_STATES = {
    "CLEAR_NO_OPEN_AMENDMENT",
    "ACKNOWLEDGED_CURRENT",
    "OPEN_UNACKNOWLEDGED",
    "UNKNOWN",
    "DNR",
}
QUALIFICATION_STATES = {
    "PRIME_SUPPORTED",
    "PARTNER_SUPPORTED",
    "HOLD_MISSING_EVIDENCE",
    "DISQUALIFIED",
    "DNR",
}
ACTORS = {"OWNER", "SWARM", "PARTNER", "SYSTEM"}
ACTION_CLASSES = {
    "PREPARE",
    "REVIEW",
    "PARTNER_DOC",
    "PORTAL_LOGIN",
    "SIGNATURE",
    "UPLOAD",
    "FINAL_REVIEW",
    "SUBMIT",
}
ACTION_STATES = {"PENDING", "COMPLETE", "BLOCKED", "NOT_APPLICABLE"}
SENSITIVE_OWNER_ONLY = {"PORTAL_LOGIN", "SIGNATURE", "SUBMIT"}

TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,159}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
UTC_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class CriticalPathError(ValueError):
    pass


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise CriticalPathError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _bad_number(value):
    raise CriticalPathError(f"non-integer JSON number forbidden: {value}")


def load_json(raw: bytes, label: str = "input") -> dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)):
        raise CriticalPathError(f"{label}: bytes required")
    raw = bytes(raw)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CriticalPathError(f"{label}: BOM forbidden")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_float=_bad_number,
            parse_constant=_bad_number,
        )
    except CriticalPathError:
        raise
    except Exception as exc:
        raise CriticalPathError(f"{label}: invalid JSON/UTF-8") from exc
    if not isinstance(value, dict):
        raise CriticalPathError(f"{label}: object required")
    return value


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _keys(value: Any, wanted: list[str], where: str) -> None:
    if not isinstance(value, dict) or set(value) != set(wanted):
        raise CriticalPathError(f"{where}: keys mismatch")


def _string(value: Any, where: str, *, token: bool = False, limit: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise CriticalPathError(f"{where}: invalid string")
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
        raise CriticalPathError(f"{where}: control character")
    if token and not TOKEN.fullmatch(value):
        raise CriticalPathError(f"{where}: invalid token")
    return value


def _boolean(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise CriticalPathError(f"{where}: bool required")
    return value


def _integer(value: Any, where: str, lo: int = 0, hi: int = 10**12) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise CriticalPathError(f"{where}: integer required")
    return value


def _enum(value: Any, choices: set[str], where: str) -> str:
    value = _string(value, where, token=True, limit=64)
    if value not in choices:
        raise CriticalPathError(f"{where}: unsupported value")
    return value


def _sha(value: Any, where: str) -> str:
    value = _string(value, where, limit=64)
    if not SHA256.fullmatch(value):
        raise CriticalPathError(f"{where}: sha256 required")
    return value


def _timestamp(value: Any, where: str) -> str:
    value = _string(value, where, limit=20)
    try:
        if not UTC_SECOND.fullmatch(value):
            raise ValueError
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CriticalPathError(f"{where}: explicit UTC second timestamp required") from exc
    return value


def _dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_seconds(now: str, observed: str, where: str) -> int:
    age = int((_dt(now) - _dt(observed)).total_seconds())
    if age < 0:
        raise CriticalPathError(f"{where}: future timestamp")
    return age


def _tokens(value: Any, where: str, *, max_items: int = 64) -> list[str]:
    if not isinstance(value, list) or len(value) > max_items:
        raise CriticalPathError(f"{where}: invalid list")
    out = [_string(item, f"{where}[{i}]", token=True) for i, item in enumerate(value)]
    if len(out) != len(set(out)):
        raise CriticalPathError(f"{where}: duplicate item")
    return out


def authority_flags() -> dict[str, bool]:
    return {
        "portal_login_authorized": False,
        "signature_authorized": False,
        "upload_authorized": False,
        "submission_authorized": False,
        "buyer_contact_authorized": False,
        "buyer_acceptance_recognized": False,
        "award_recognized": False,
        "invoice_authorized": False,
        "payment_authorized": False,
        "cash_or_revenue_recognized": False,
    }


def normalize(value: dict[str, Any]) -> dict[str, Any]:
    _keys(
        value,
        [
            "schema",
            "truth_boundary",
            "case_id",
            "evaluation_time",
            "max_source_age_seconds",
            "fixture",
            "solicitation",
            "amendment",
            "qualification",
            "final_submission_buffer_seconds",
            "actions",
        ],
        "input",
    )
    if value["schema"] != INPUT_SCHEMA or value["truth_boundary"] != TRUTH_BOUNDARY:
        raise CriticalPathError("input: unsupported schema/truth boundary")

    now = _timestamp(value["evaluation_time"], "evaluation_time")
    max_age = _integer(value["max_source_age_seconds"], "max_source_age_seconds", 1, 315_360_000)
    fixture = _boolean(value["fixture"], "fixture")
    case_id = _string(value["case_id"], "case_id", token=True)
    final_buffer = _integer(
        value["final_submission_buffer_seconds"], "final_submission_buffer_seconds", 0, 2_592_000
    )

    solicitation = value["solicitation"]
    _keys(
        solicitation,
        [
            "solicitation_id",
            "submission_deadline_utc",
            "timezone_label",
            "source_authority",
            "source_uri",
            "source_sha256",
            "observed_at",
        ],
        "solicitation",
    )
    deadline = _timestamp(solicitation["submission_deadline_utc"], "solicitation.submission_deadline_utc")
    observed = _timestamp(solicitation["observed_at"], "solicitation.observed_at")
    age = _age_seconds(now, observed, "solicitation.observed_at")
    sol = {
        "solicitation_id": _string(solicitation["solicitation_id"], "solicitation.solicitation_id", token=True),
        "submission_deadline_utc": deadline,
        "timezone_label": _string(solicitation["timezone_label"], "solicitation.timezone_label", limit=128),
        "source_authority": _enum(
            solicitation["source_authority"], SOURCE_AUTHORITIES, "solicitation.source_authority"
        ),
        "source_uri": _string(solicitation["source_uri"], "solicitation.source_uri", limit=2048),
        "source_sha256": _sha(solicitation["source_sha256"], "solicitation.source_sha256"),
        "observed_at": observed,
        "stale": age > max_age,
    }

    amendment = value["amendment"]
    _keys(amendment, ["state", "source_authority", "source_uri", "source_sha256", "observed_at"], "amendment")
    amend_observed = _timestamp(amendment["observed_at"], "amendment.observed_at")
    amend_age = _age_seconds(now, amend_observed, "amendment.observed_at")
    amend = {
        "state": _enum(amendment["state"], AMENDMENT_STATES, "amendment.state"),
        "source_authority": _enum(amendment["source_authority"], SOURCE_AUTHORITIES, "amendment.source_authority"),
        "source_uri": _string(amendment["source_uri"], "amendment.source_uri", limit=2048),
        "source_sha256": _sha(amendment["source_sha256"], "amendment.source_sha256"),
        "observed_at": amend_observed,
        "stale": amend_age > max_age,
    }

    qualification = value["qualification"]
    _keys(qualification, ["state", "source_uri", "source_sha256", "observed_at", "gaps"], "qualification")
    qual_observed = _timestamp(qualification["observed_at"], "qualification.observed_at")
    qual_age = _age_seconds(now, qual_observed, "qualification.observed_at")
    gaps = qualification["gaps"]
    if not isinstance(gaps, list) or len(gaps) > 64:
        raise CriticalPathError("qualification.gaps: invalid list")
    norm_gaps = [_string(item, f"qualification.gaps[{i}]", limit=512) for i, item in enumerate(gaps)]
    if len(norm_gaps) != len(set(norm_gaps)):
        raise CriticalPathError("qualification.gaps: duplicate item")
    qual = {
        "state": _enum(qualification["state"], QUALIFICATION_STATES, "qualification.state"),
        "source_uri": _string(qualification["source_uri"], "qualification.source_uri", limit=2048),
        "source_sha256": _sha(qualification["source_sha256"], "qualification.source_sha256"),
        "observed_at": qual_observed,
        "gaps": norm_gaps,
        "stale": qual_age > max_age,
    }

    actions = value["actions"]
    if not isinstance(actions, list) or not 1 <= len(actions) <= 128:
        raise CriticalPathError("actions: non-empty list required")
    normalized_actions: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, item in enumerate(actions):
        where = f"actions[{index}]"
        _keys(
            item,
            [
                "action_id",
                "label",
                "actor_class",
                "action_class",
                "state",
                "duration_seconds",
                "handoff_buffer_seconds",
                "depends_on",
                "evidence_uri",
                "evidence_sha256",
                "evidence_observed_at",
            ],
            where,
        )
        action_id = _string(item["action_id"], where + ".action_id", token=True)
        if action_id in ids:
            raise CriticalPathError("actions: duplicate action_id")
        ids.add(action_id)
        actor = _enum(item["actor_class"], ACTORS, where + ".actor_class")
        action_class = _enum(item["action_class"], ACTION_CLASSES, where + ".action_class")
        if action_class in SENSITIVE_OWNER_ONLY and actor != "OWNER":
            raise CriticalPathError(f"{where}: {action_class} must be OWNER")
        evidence_observed = _timestamp(item["evidence_observed_at"], where + ".evidence_observed_at")
        evidence_age = _age_seconds(now, evidence_observed, where + ".evidence_observed_at")
        normalized_actions.append(
            {
                "action_id": action_id,
                "label": _string(item["label"], where + ".label", limit=256),
                "actor_class": actor,
                "action_class": action_class,
                "state": _enum(item["state"], ACTION_STATES, where + ".state"),
                "duration_seconds": _integer(item["duration_seconds"], where + ".duration_seconds", 0, 2_592_000),
                "handoff_buffer_seconds": _integer(
                    item["handoff_buffer_seconds"], where + ".handoff_buffer_seconds", 0, 604_800
                ),
                "depends_on": _tokens(item["depends_on"], where + ".depends_on"),
                "evidence_uri": _string(item["evidence_uri"], where + ".evidence_uri", limit=2048),
                "evidence_sha256": _sha(item["evidence_sha256"], where + ".evidence_sha256"),
                "evidence_observed_at": evidence_observed,
                "evidence_stale": evidence_age > max_age,
            }
        )
    idset = {item["action_id"] for item in normalized_actions}
    for item in normalized_actions:
        unknown = set(item["depends_on"]) - idset
        if unknown:
            raise CriticalPathError(f"actions.{item['action_id']}: unknown dependency")
        if item["action_id"] in item["depends_on"]:
            raise CriticalPathError(f"actions.{item['action_id']}: self dependency")

    amap = {item["action_id"]: item for item in normalized_actions}
    state: dict[str, int] = {}
    order: list[str] = []

    def visit(action_id: str) -> None:
        mark = state.get(action_id, 0)
        if mark == 1:
            raise CriticalPathError("actions: dependency cycle")
        if mark == 2:
            return
        state[action_id] = 1
        for dep in amap[action_id]["depends_on"]:
            visit(dep)
        state[action_id] = 2
        order.append(action_id)

    for action_id in sorted(amap):
        visit(action_id)

    return {
        "case_id": case_id,
        "evaluation_time": now,
        "fixture": fixture,
        "max_source_age_seconds": max_age,
        "solicitation": sol,
        "amendment": amend,
        "qualification": qual,
        "final_submission_buffer_seconds": final_buffer,
        "actions": normalized_actions,
        "action_map": amap,
        "topological_order": order,
    }


def _schedule(n: dict[str, Any]) -> list[dict[str, Any]]:
    amap = n["action_map"]
    order = n["topological_order"]
    successors: dict[str, list[str]] = {action_id: [] for action_id in amap}
    for action_id, item in amap.items():
        for dep in item["depends_on"]:
            successors[dep].append(action_id)

    deadline = _dt(n["solicitation"]["submission_deadline_utc"])
    terminal_finish = deadline - timedelta(seconds=n["final_submission_buffer_seconds"])
    result: dict[str, dict[str, Any]] = {}

    for action_id in reversed(order):
        action = amap[action_id]
        child_starts = [
            _dt(result[child]["latest_safe_start_utc"])
            for child in successors[action_id]
            if child in result
        ]
        latest_finish = min(child_starts) if child_starts else terminal_finish
        remaining_duration = 0 if action["state"] in {"COMPLETE", "NOT_APPLICABLE"} else action["duration_seconds"]
        remaining_buffer = 0 if action["state"] in {"COMPLETE", "NOT_APPLICABLE"} else action["handoff_buffer_seconds"]
        latest_start = latest_finish - timedelta(seconds=remaining_duration + remaining_buffer)
        slack = int((latest_start - _dt(n["evaluation_time"])).total_seconds())
        result[action_id] = {
            "action_id": action_id,
            "label": action["label"],
            "actor_class": action["actor_class"],
            "action_class": action["action_class"],
            "state": action["state"],
            "depends_on": sorted(action["depends_on"]),
            "waiting_on_action_ids": sorted(
                dep for dep in action["depends_on"]
                if amap[dep]["state"] not in {"COMPLETE", "NOT_APPLICABLE"}
            ),
            "duration_seconds": action["duration_seconds"],
            "handoff_buffer_seconds": action["handoff_buffer_seconds"],
            "latest_safe_start_utc": _ts(latest_start),
            "latest_safe_finish_utc": _ts(latest_finish),
            "slack_seconds": slack,
            "evidence_sha256": action["evidence_sha256"],
            "evidence_observed_at": action["evidence_observed_at"],
            "evidence_stale": action["evidence_stale"],
        }
    return [result[action_id] for action_id in order]


def _decision(n: dict[str, Any], schedule: list[dict[str, Any]]) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    owner_actions: list[str] = []
    sol = n["solicitation"]
    amend = n["amendment"]
    qual = n["qualification"]

    if amend["state"] == "DNR" or qual["state"] == "DNR":
        return "DNR", ["do-not-pursue state present"], ["do not submit or contact buyer"]

    if n["fixture"]:
        return "HOLD_SOURCE", ["synthetic fixture cannot establish a live bid deadline"], ["replace fixture with retained buyer/source evidence"]

    if sol["source_authority"] != "BUYER_OFFICIAL" or sol["stale"]:
        if sol["source_authority"] != "BUYER_OFFICIAL":
            blockers.append("submission deadline is not buyer-official evidence")
        if sol["stale"]:
            blockers.append("submission deadline source is stale")
        return "HOLD_SOURCE", blockers, ["refresh authoritative deadline evidence before acting"]

    if (
        amend["source_authority"] != "BUYER_OFFICIAL"
        or amend["stale"]
        or amend["state"] not in {"CLEAR_NO_OPEN_AMENDMENT", "ACKNOWLEDGED_CURRENT"}
    ):
        if amend["source_authority"] != "BUYER_OFFICIAL":
            blockers.append("amendment state is not buyer-official evidence")
        if amend["stale"]:
            blockers.append("amendment evidence is stale")
        blockers.append(f"amendment state {amend['state']} is not current-clear")
        return "HOLD_AMENDMENT", blockers, ["refresh amendment census and acknowledge/apply authoritative amendments"]

    if qual["stale"] or qual["state"] not in {"PRIME_SUPPORTED", "PARTNER_SUPPORTED"}:
        if qual["stale"]:
            blockers.append("qualification evidence is stale")
        blockers.append(f"qualification state {qual['state']} is not supported")
        if qual["gaps"]:
            blockers.extend(f"qualification gap: {gap}" for gap in qual["gaps"])
        return "HOLD_QUALIFICATION", blockers, ["close qualification/workshare evidence gaps before submission planning"]

    action_blockers = [
        item for item in schedule
        if item["state"] == "BLOCKED" or (item["state"] == "PENDING" and item["evidence_stale"])
    ]
    if action_blockers:
        for item in action_blockers:
            reason = "blocked" if item["state"] == "BLOCKED" else "evidence stale"
            blockers.append(f"{item['action_id']}: {reason}")
        return "HOLD_DEPENDENCY", blockers, ["resolve blocked/stale dependency evidence and recompile"]

    now = _dt(n["evaluation_time"])
    deadline = _dt(sol["submission_deadline_utc"])
    if now >= deadline:
        return "MISSED_WINDOW", ["authoritative submission deadline has passed"], ["do not represent the bid as submittable"]

    late = [
        item for item in schedule
        if item["state"] == "PENDING" and item["slack_seconds"] < 0
    ]
    if late:
        blockers.extend(
            f"{item['action_id']}: latest safe start passed by {-item['slack_seconds']} seconds"
            for item in late
        )
        return "MISSED_WINDOW", blockers, ["owner decides whether an authoritative extension/amendment exists; otherwise do not submit"]

    pending = [item for item in schedule if item["state"] == "PENDING"]
    owner_pending = [item for item in pending if item["actor_class"] == "OWNER"]
    ready_owner = [item for item in owner_pending if not item["waiting_on_action_ids"]]
    if ready_owner:
        next_owner = min(ready_owner, key=lambda item: (item["latest_safe_start_utc"], item["action_id"]))
        owner_actions.append(
            f"next owner action {next_owner['action_id']} no later than {next_owner['latest_safe_start_utc']} UTC"
        )
    elif owner_pending:
        next_owner = min(owner_pending, key=lambda item: (item["latest_safe_start_utc"], item["action_id"]))
        waiting_on = ", ".join(next_owner["waiting_on_action_ids"])
        owner_actions.append(
            f"owner action {next_owner['action_id']} waits for {waiting_on}; coordinate prerequisite completion "
            f"before its latest safe start {next_owner['latest_safe_start_utc']} UTC"
        )
    elif pending:
        owner_actions.append("coordinate remaining planned work before the final owner submission decision")
    else:
        owner_actions.append("owner performs final submission decision outside this compiler")
    owner_actions.append("refresh buyer deadline/amendment evidence immediately before irreversible owner portal action")
    owner_actions.append("this packet does not authorize login, signature, upload, submission, buyer contact, award, payment, or revenue recognition")
    return "READY_FOR_OWNER_ACTION", blockers, owner_actions


def compile_bundle(raw: bytes) -> tuple[bytes, bytes, bytes]:
    n = normalize(load_json(raw))
    schedule = _schedule(n)
    decision, blockers, owner_actions = _decision(n, schedule)
    packet = {
        "schema": PACKET_SCHEMA,
        "truth_boundary": TRUTH_BOUNDARY,
        "currentness_basis": CURRENTNESS_BASIS,
        "case_id": n["case_id"],
        "evaluation_time": n["evaluation_time"],
        "decision": decision,
        "blockers": blockers,
        "owner_actions": owner_actions,
        "solicitation": {
            key: n["solicitation"][key]
            for key in [
                "solicitation_id",
                "submission_deadline_utc",
                "timezone_label",
                "source_authority",
                "source_sha256",
                "observed_at",
                "stale",
            ]
        },
        "amendment": {
            key: n["amendment"][key]
            for key in ["state", "source_authority", "source_sha256", "observed_at", "stale"]
        },
        "qualification": {
            key: n["qualification"][key]
            for key in ["state", "source_sha256", "observed_at", "gaps", "stale"]
        },
        "final_submission_buffer_seconds": n["final_submission_buffer_seconds"],
        "critical_path": schedule,
        "authority": authority_flags(),
    }
    packet_bytes = canonical_json(packet)
    markdown_bytes = render_markdown(packet)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "truth_boundary": TRUTH_BOUNDARY,
        "case_id": n["case_id"],
        "decision": decision,
        "input_sha256": digest(raw),
        "packet_sha256": digest(packet_bytes),
        "markdown_sha256": digest(markdown_bytes),
        "authority": authority_flags(),
    }
    return packet_bytes, markdown_bytes, canonical_json(receipt)


def render_markdown(packet: dict[str, Any]) -> bytes:
    lines = [
        "# Bid deadline owner-action critical path",
        "",
        "> **OWNER ACTION PLANNING ONLY — NOT A SUBMISSION.**",
        "> No portal login, signature, upload, submission, buyer contact, award, payment, or revenue authority is granted.",
        "",
        f"- Decision: **{packet['decision']}**",
        f"- Case: `{packet['case_id']}`",
        f"- Solicitation: `{packet['solicitation']['solicitation_id']}`",
        f"- Deadline (UTC): `{packet['solicitation']['submission_deadline_utc']}`",
        f"- Source timezone label: `{packet['solicitation']['timezone_label']}`",
        f"- Amendment state: `{packet['amendment']['state']}`",
        f"- Qualification: `{packet['qualification']['state']}`",
        "",
        "## Critical path",
        "",
        "| action | actor | class | state | waiting on | latest safe start UTC | latest safe finish UTC | slack seconds |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: |",
    ]
    for item in packet["critical_path"]:
        lines.append(
            f"| `{item['action_id']}` | {item['actor_class']} | {item['action_class']} | {item['state']} | "
            f"{', '.join(item['waiting_on_action_ids']) or '—'} | "
            f"`{item['latest_safe_start_utc']}` | `{item['latest_safe_finish_utc']}` | {item['slack_seconds']} |"
        )
    if packet["blockers"]:
        lines += ["", "## Holds", ""]
        lines.extend(f"- {item}" for item in packet["blockers"])
    lines += ["", "## Owner actions", ""]
    lines.extend(f"- {item}" for item in packet["owner_actions"])
    lines += [
        "",
        "## Authority ceiling",
        "",
        "- Portal login/signature/upload/submission: **false**",
        "- Buyer contact/acceptance/award: **false**",
        "- Invoice/payment/cash/revenue recognition: **false**",
        "",
        f"Currentness basis: `{packet['currentness_basis']}`.",
    ]
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def verify_bundle(raw: bytes, packet_bytes: bytes, markdown_bytes: bytes, receipt_bytes: bytes) -> str:
    expected = compile_bundle(raw)
    if (packet_bytes, markdown_bytes, receipt_bytes) != expected:
        raise CriticalPathError("bundle mismatch")
    packet = load_json(packet_bytes, "packet")
    receipt = load_json(receipt_bytes, "receipt")
    if packet.get("schema") != PACKET_SCHEMA or receipt.get("schema") != RECEIPT_SCHEMA:
        raise CriticalPathError("bundle schema mismatch")
    if packet.get("authority") != authority_flags() or receipt.get("authority") != authority_flags():
        raise CriticalPathError("authority mismatch")
    return "EXACT_CRITICAL_PATH_MATCH"


def _preflight(paths: list[Path]) -> None:
    if len({str(path.absolute()) for path in paths}) != len(paths):
        raise CriticalPathError("output paths must be distinct")
    for path in paths:
        if path.exists() or path.is_symlink():
            raise CriticalPathError(f"output exists: {path}")
        if not path.parent.exists() or not path.parent.is_dir():
            raise CriticalPathError(f"output parent missing: {path.parent}")


def _publish_atomic(outputs: list[tuple[Path, bytes]]) -> None:
    paths = [path for path, _ in outputs]
    _preflight(paths)
    staged: list[Path] = []
    published: list[Path] = []
    try:
        for path, data in outputs:
            fd, tmp_name = tempfile.mkstemp(prefix=".bid-critical-path-", dir=str(path.parent))
            tmp = Path(tmp_name)
            staged.append(tmp)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        for (path, _), tmp in zip(outputs, staged):
            os.link(tmp, path)
            published.append(path)
    except Exception:
        for path in reversed(published):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for tmp in staged:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bid-deadline-critical-path")
    sub = parser.add_subparsers(dest="command", required=True)
    cp = sub.add_parser("compile")
    cp.add_argument("input")
    cp.add_argument("--packet", required=True)
    cp.add_argument("--markdown", required=True)
    cp.add_argument("--receipt", required=True)
    vp = sub.add_parser("verify")
    vp.add_argument("input")
    vp.add_argument("packet")
    vp.add_argument("markdown")
    vp.add_argument("receipt")
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            raw = Path(args.input).read_bytes()
            packet, markdown, receipt = compile_bundle(raw)
            _publish_atomic(
                [
                    (Path(args.packet), packet),
                    (Path(args.markdown), markdown),
                    (Path(args.receipt), receipt),
                ]
            )
            sys.stdout.write(load_json(packet, "packet")["decision"] + "\n")
            return 0
        token = verify_bundle(
            Path(args.input).read_bytes(),
            Path(args.packet).read_bytes(),
            Path(args.markdown).read_bytes(),
            Path(args.receipt).read_bytes(),
        )
        sys.stdout.write(token + "\n")
        return 0
    except (CriticalPathError, OSError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2


def main() -> None:
    raise SystemExit(_cli())


if __name__ == "__main__":
    main()
