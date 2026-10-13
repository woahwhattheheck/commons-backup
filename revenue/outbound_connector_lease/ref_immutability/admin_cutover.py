#!/usr/bin/env python3
"""Fail-closed GitHub admin cutover helper for immutable outbound lease refs.

This helper can:
- validate the exact reviewed ruleset candidate,
- emit a deterministic offline apply plan,
- when explicitly run with an Administration(write) token, create the ruleset
  only if absent, read it back, read effective branch rules, and execute a
  one-time protected-v2 probe whose update/delete/recreate attempts must fail,
- emit a narrow deterministic receipt.

Even a successful receipt proves only ref rollback protection. It never grants
provider-send, production mutex, buyer, contract, payment, or revenue authority.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

REPOSITORY = "woahwhattheheck/commons"
EXPECTED_DEFAULT_BRANCH = "main"
RULESET_NAME = "outbound-connector-lease-immutable"
V2_PREFIX = "refs/heads/outbound-connector-lease/v2/*"
PROBE_PREFIX = "outbound-connector-lease/v2/admin-cutover-probe-"
EXPECTED_CANDIDATE_RAW_SHA256 = (
    "8f697a8372cc4c2aeaf97e7cd7890d9004394667316573ba638df3a095bfc1e9"
)
PLAN_SCHEMA = "commons.outbound-ref-immutability-admin-cutover-plan/v1"
RECEIPT_SCHEMA = "commons.outbound-ref-immutability-admin-cutover-receipt/v1"
API_BASE = "https://api.github.com"
MAX_JSON_BYTES = 2_000_000
_PROBE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_TOKEN_ENV_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")


class CutoverError(ValueError):
    """Raised when any prerequisite or observed host fact is unsafe or ambiguous."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _no_duplicate_pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CutoverError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_no_duplicate_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CutoverError(f"non-finite JSON number: {token}")
            ),
        )
    except CutoverError:
        raise
    except json.JSONDecodeError as exc:
        raise CutoverError(f"invalid JSON: {exc.msg}") from exc


def _plain_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CutoverError(f"{label} must be a plain JSON object")
    return value


def _plain_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise CutoverError(f"{label} must be a plain JSON array")
    return value


def _exact_keys(obj: Mapping[str, Any], expected: set[str], label: str) -> None:
    got = set(obj)
    if got != expected:
        raise CutoverError(
            f"{label} keys mismatch missing={sorted(expected - got)} "
            f"extra={sorted(got - expected)}"
        )


def candidate_path() -> Path:
    return Path(__file__).with_name("ruleset-candidate.json")


def read_candidate_bytes(path: str | os.PathLike[str] | None = None) -> bytes:
    p = Path(path) if path is not None else candidate_path()
    try:
        st = p.lstat()
    except FileNotFoundError as exc:
        raise CutoverError(f"candidate not found: {p}") from exc
    if p.is_symlink() or not p.is_file():
        raise CutoverError(f"candidate must be a regular non-symlink file: {p}")
    if st.st_size > MAX_JSON_BYTES:
        raise CutoverError("candidate exceeds bounded input size")
    data = p.read_bytes()
    if len(data) > MAX_JSON_BYTES:
        raise CutoverError("candidate exceeds bounded input size")
    return data


def validate_candidate_document(value: Any) -> dict[str, Any]:
    doc = _plain_dict(value, "candidate")
    _exact_keys(
        doc,
        {"name", "target", "enforcement", "bypass_actors", "conditions", "rules"},
        "candidate",
    )
    if doc["name"] != RULESET_NAME:
        raise CutoverError("candidate ruleset name drift")
    if doc["target"] != "branch":
        raise CutoverError("candidate target must be branch")
    if doc["enforcement"] != "active":
        raise CutoverError("candidate enforcement must be active")

    bypass = _plain_list(doc["bypass_actors"], "candidate.bypass_actors")
    if bypass:
        raise CutoverError("candidate must not grant bypass actors")

    conditions = _plain_dict(doc["conditions"], "candidate.conditions")
    _exact_keys(conditions, {"ref_name"}, "candidate.conditions")
    ref_name = _plain_dict(conditions["ref_name"], "candidate.conditions.ref_name")
    _exact_keys(ref_name, {"include", "exclude"}, "candidate.conditions.ref_name")
    if ref_name["include"] != [V2_PREFIX] or ref_name["exclude"] != []:
        raise CutoverError("candidate ref-name scope drift")

    rules = _plain_list(doc["rules"], "candidate.rules")
    if len(rules) != 3:
        raise CutoverError("candidate must contain exactly three mutation-block rules")
    expected = {
        "update": {"type": "update", "parameters": {"update_allows_fetch_and_merge": False}},
        "deletion": {"type": "deletion"},
        "non_fast_forward": {"type": "non_fast_forward"},
    }
    observed: dict[str, dict[str, Any]] = {}
    for idx, raw_rule in enumerate(rules):
        rule = _plain_dict(raw_rule, f"candidate.rules[{idx}]")
        rule_type = rule.get("type")
        if rule_type not in expected:
            raise CutoverError(f"unsupported candidate rule type: {rule_type!r}")
        if rule_type in observed:
            raise CutoverError(f"duplicate candidate rule type: {rule_type}")
        if rule != expected[rule_type]:
            raise CutoverError(f"candidate rule drift for {rule_type}")
        observed[rule_type] = rule
    if set(observed) != set(expected):
        raise CutoverError("candidate mutation-block rule set incomplete")
    return dict(doc)


def load_reviewed_candidate(
    path: str | os.PathLike[str] | None = None,
) -> tuple[bytes, dict[str, Any]]:
    raw = read_candidate_bytes(path)
    digest = sha256_hex(raw)
    if digest != EXPECTED_CANDIDATE_RAW_SHA256:
        raise CutoverError(
            "candidate raw bytes differ from reviewed digest "
            f"{EXPECTED_CANDIDATE_RAW_SHA256}"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CutoverError("candidate must be UTF-8") from exc
    return raw, validate_candidate_document(strict_json_loads(text))


def _authority_false_fields() -> dict[str, bool]:
    return {
        "branch_create_authority": False,
        "production_mutex_complete": False,
        "external_send_authorized": False,
        "provider_send_authorized": False,
        "payment_authorized": False,
        "revenue_recognized": False,
    }


def _with_receipt_hash(payload: dict[str, Any]) -> dict[str, Any]:
    if "receipt_sha256" in payload:
        raise CutoverError("receipt payload must not pre-populate receipt_sha256")
    out = dict(payload)
    out["receipt_sha256"] = sha256_hex(canonical_json(payload))
    return out


def build_plan(candidate_raw: bytes, candidate: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "schema": PLAN_SCHEMA,
        "state": "HOLD_ADMIN_APPLY_REQUIRED",
        "repository": REPOSITORY,
        "expected_default_branch": EXPECTED_DEFAULT_BRANCH,
        "candidate_raw_sha256": sha256_hex(candidate_raw),
        "candidate_semantic_sha256": sha256_hex(canonical_json(candidate)),
        "ruleset_name": RULESET_NAME,
        "ruleset_target": "branch",
        "ruleset_enforcement": "active",
        "ruleset_bypass_actor_count": 0,
        "protected_ref_pattern": V2_PREFIX,
        "apply_contract": {
            "install_mode": "CREATE_ONLY_IF_ABSENT",
            "ruleset_collection": f"/repos/{REPOSITORY}/rulesets",
            "ruleset_detail": f"/repos/{REPOSITORY}/rulesets/<id>",
            "effective_rules": (
                f"/repos/{REPOSITORY}/rules/branches/"
                "<url-encoded-v2-probe-branch>"
            ),
            "probe_sequence": [
                "CREATE_UNIQUE_V2_PROBE_FROM_MAIN_PARENT",
                "READ_EFFECTIVE_RULES",
                "FAST_FORWARD_UPDATE_MUST_BE_BLOCKED",
                "DELETE_MUST_BE_BLOCKED",
                "RECREATE_MUST_BE_BLOCKED_AS_REF_REMAINS",
                "READ_BACK_ORIGINAL_PROBE_SHA",
            ],
        },
        "ref_rollback_protection_required": True,
        "ref_rollback_protection_verified": False,
        **_authority_false_fields(),
    }
    return _with_receipt_hash(payload)


def verify_self_hash(receipt: Any) -> bool:
    if type(receipt) is not dict:
        return False
    claimed = receipt.get("receipt_sha256")
    if type(claimed) is not str or not re.fullmatch(r"[0-9a-f]{64}", claimed):
        return False
    core = dict(receipt)
    del core["receipt_sha256"]
    if sha256_hex(canonical_json(core)) != claimed:
        return False
    for key, value in _authority_false_fields().items():
        if receipt.get(key) is not value:
            return False
    if receipt.get("ref_rollback_protection_required") is not True:
        return False
    return True


@dataclass(frozen=True)
class ApiResponse:
    status: int
    data: Any


class ApiClient(Protocol):
    def request(self, method: str, path: str, payload: Any | None = None) -> ApiResponse:
        ...


class GitHubApi:
    """Minimal GitHub REST client. Token is retained in memory and never emitted."""

    def __init__(self, token: str):
        if not isinstance(token, str) or len(token.strip()) < 8:
            raise CutoverError("Administration(write) token is missing or implausibly short")
        self._token = token.strip()

    def request(self, method: str, path: str, payload: Any | None = None) -> ApiResponse:
        if not path.startswith("/repos/woahwhattheheck/commons"):
            raise CutoverError("refusing API request outside the pinned Commons repository")
        url = API_BASE + path
        body = None if payload is None else canonical_json(payload).encode("utf-8")
        req = Request(
            url,
            data=body,
            method=method.upper(),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "commons-ref-immutability-admin-cutover",
                **({"Content-Type": "application/json"} if body is not None else {}),
            },
        )
        try:
            with urlopen(req, timeout=20) as response:
                raw = response.read(MAX_JSON_BYTES + 1)
                if len(raw) > MAX_JSON_BYTES:
                    raise CutoverError("GitHub response exceeded bounded size")
                if not raw:
                    data: Any = None
                else:
                    try:
                        data = strict_json_loads(raw.decode("utf-8"))
                    except UnicodeDecodeError as exc:
                        raise CutoverError("GitHub response was not UTF-8") from exc
                return ApiResponse(int(response.status), data)
        except HTTPError as exc:
            raw = exc.read(MAX_JSON_BYTES + 1)
            if len(raw) > MAX_JSON_BYTES:
                raise CutoverError("GitHub error response exceeded bounded size") from exc
            if not raw:
                data = None
            else:
                try:
                    data = strict_json_loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, CutoverError):
                    data = {"unparsed_error": raw.decode("utf-8", errors="replace")[:1000]}
            return ApiResponse(int(exc.code), data)
        except (URLError, TimeoutError, OSError) as exc:
            raise CutoverError(f"ambiguous GitHub transport failure: {exc}") from exc


def _expect(response: ApiResponse, statuses: set[int], label: str) -> Any:
    if response.status not in statuses:
        raise CutoverError(
            f"{label} returned HTTP {response.status}; expected {sorted(statuses)}"
        )
    return response.data


def _rules_signature(value: Any, label: str) -> dict[str, Any]:
    rules = _plain_list(value, label)
    observed: dict[str, dict[str, Any]] = {}
    for idx, raw in enumerate(rules):
        rule = _plain_dict(raw, f"{label}[{idx}]")
        rule_type = rule.get("type")
        if rule_type not in {"update", "deletion", "non_fast_forward"}:
            continue
        if rule_type in observed:
            raise CutoverError(f"{label} contains duplicate {rule_type} rule")
        if rule_type == "update":
            params = _plain_dict(rule.get("parameters"), f"{label}[{idx}].parameters")
            if params.get("update_allows_fetch_and_merge") is not False:
                raise CutoverError("effective update rule permits mutation")
            observed[rule_type] = {
                "type": "update",
                "parameters": {"update_allows_fetch_and_merge": False},
            }
        else:
            observed[rule_type] = {"type": rule_type}
    if set(observed) != {"update", "deletion", "non_fast_forward"}:
        raise CutoverError(
            f"{label} missing required mutation blocks: "
            f"{sorted({'update','deletion','non_fast_forward'} - set(observed))}"
        )
    return {key: observed[key] for key in sorted(observed)}


def canonical_ruleset_evidence(detail: Any) -> dict[str, Any]:
    doc = _plain_dict(detail, "ruleset readback")
    if doc.get("name") != RULESET_NAME:
        raise CutoverError("ruleset readback name mismatch")
    if doc.get("target") != "branch":
        raise CutoverError("ruleset readback target mismatch")
    if doc.get("enforcement") != "active":
        raise CutoverError("ruleset readback is not actively enforced")
    bypass = _plain_list(doc.get("bypass_actors"), "ruleset readback bypass_actors")
    if bypass:
        raise CutoverError("ruleset readback grants bypass actors")
    conditions = _plain_dict(doc.get("conditions"), "ruleset readback conditions")
    ref_name = _plain_dict(conditions.get("ref_name"), "ruleset readback ref_name")
    if ref_name.get("include") != [V2_PREFIX] or ref_name.get("exclude") != []:
        raise CutoverError("ruleset readback ref-name scope mismatch")
    signature = _rules_signature(doc.get("rules"), "ruleset readback rules")
    ruleset_id = doc.get("id")
    if isinstance(ruleset_id, bool) or not isinstance(ruleset_id, int) or ruleset_id <= 0:
        raise CutoverError("ruleset readback id invalid")
    return {
        "id": ruleset_id,
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": [V2_PREFIX], "exclude": []}},
        "rules": [signature[key] for key in sorted(signature)],
    }


def canonical_effective_rule_evidence(value: Any) -> dict[str, Any]:
    if type(value) is dict and "rules" in value:
        raw_rules = value["rules"]
    else:
        raw_rules = value
    signature = _rules_signature(raw_rules, "effective branch rules")
    return {"rules": [signature[key] for key in sorted(signature)]}


def _validate_probe_id(probe_id: str) -> str:
    if not isinstance(probe_id, str) or not _PROBE_RE.fullmatch(probe_id):
        raise CutoverError("probe_id must be a 1..64 character opaque token")
    return probe_id


def _ref_api_segment(branch_name: str) -> str:
    return quote("heads/" + branch_name, safe="")


def _branch_api_segment(branch_name: str) -> str:
    return quote(branch_name, safe="")


def apply_cutover(
    client: ApiClient,
    candidate_raw: bytes,
    candidate: Mapping[str, Any],
    probe_id: str,
) -> dict[str, Any]:
    _validate_probe_id(probe_id)
    if sha256_hex(candidate_raw) != EXPECTED_CANDIDATE_RAW_SHA256:
        raise CutoverError("candidate raw digest drift at apply boundary")
    validate_candidate_document(dict(candidate))

    collection_path = f"/repos/{REPOSITORY}/rulesets"
    collection = _expect(client.request("GET", collection_path), {200}, "ruleset census")
    existing = [
        item
        for item in _plain_list(collection, "ruleset census")
        if type(item) is dict and item.get("name") == RULESET_NAME
    ]
    if len(existing) > 1:
        raise CutoverError("multiple same-name rulesets make authority ambiguous")

    installed_during_run = False
    if existing:
        ruleset_id = existing[0].get("id")
        if isinstance(ruleset_id, bool) or not isinstance(ruleset_id, int):
            raise CutoverError("existing same-name ruleset has invalid id")
    else:
        created = _expect(
            client.request("POST", collection_path, dict(candidate)),
            {201},
            "create-only ruleset install",
        )
        created_doc = _plain_dict(created, "ruleset creation response")
        ruleset_id = created_doc.get("id")
        if isinstance(ruleset_id, bool) or not isinstance(ruleset_id, int):
            raise CutoverError("created ruleset response lacks valid id")
        installed_during_run = True

    detail_path = f"/repos/{REPOSITORY}/rulesets/{ruleset_id}"
    detail = _expect(client.request("GET", detail_path), {200}, "ruleset exact readback")
    canonical_ruleset = canonical_ruleset_evidence(detail)
    if canonical_json(validate_candidate_document(dict(candidate))) != canonical_json(
        {
            "name": canonical_ruleset["name"],
            "target": canonical_ruleset["target"],
            "enforcement": canonical_ruleset["enforcement"],
            "bypass_actors": canonical_ruleset["bypass_actors"],
            "conditions": canonical_ruleset["conditions"],
            "rules": canonical_ruleset["rules"],
        }
    ):
        candidate_sig = _rules_signature(candidate["rules"], "candidate rules")
        host_sig = _rules_signature(detail["rules"], "host rules")
        if candidate_sig != host_sig:
            raise CutoverError("host ruleset rules differ from reviewed candidate")
        comparable = {
            "name": canonical_ruleset["name"],
            "target": canonical_ruleset["target"],
            "enforcement": canonical_ruleset["enforcement"],
            "bypass_actors": canonical_ruleset["bypass_actors"],
            "conditions": canonical_ruleset["conditions"],
        }
        expected_comparable = {
            "name": candidate["name"],
            "target": candidate["target"],
            "enforcement": candidate["enforcement"],
            "bypass_actors": candidate["bypass_actors"],
            "conditions": candidate["conditions"],
        }
        if comparable != expected_comparable:
            raise CutoverError("host ruleset metadata differs from reviewed candidate")

    repo_doc = _plain_dict(
        _expect(
            client.request("GET", f"/repos/{REPOSITORY}"),
            {200},
            "repository readback",
        ),
        "repository readback",
    )
    if repo_doc.get("default_branch") != EXPECTED_DEFAULT_BRANCH:
        raise CutoverError("repository default branch drift")

    commit_doc = _plain_dict(
        _expect(
            client.request(
                "GET",
                f"/repos/{REPOSITORY}/commits/{EXPECTED_DEFAULT_BRANCH}",
            ),
            {200},
            "default-branch commit readback",
        ),
        "default-branch commit readback",
    )
    main_sha = commit_doc.get("sha")
    if not isinstance(main_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", main_sha):
        raise CutoverError("default-branch commit SHA invalid")
    parents = _plain_list(commit_doc.get("parents"), "default-branch commit parents")
    if not parents or type(parents[0]) is not dict:
        raise CutoverError("default branch needs a retained parent for fast-forward hostile")
    parent_sha = parents[0].get("sha")
    if not isinstance(parent_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", parent_sha):
        raise CutoverError("default-branch parent SHA invalid")

    branch_name = PROBE_PREFIX + probe_id
    probe_ref = "refs/heads/" + branch_name
    create_payload = {"ref": probe_ref, "sha": parent_sha}
    _expect(
        client.request(
            "POST",
            f"/repos/{REPOSITORY}/git/refs",
            create_payload,
        ),
        {201},
        "unique protected-v2 probe create",
    )

    effective_path = (
        f"/repos/{REPOSITORY}/rules/branches/{_branch_api_segment(branch_name)}"
    )
    effective_raw = _expect(
        client.request("GET", effective_path),
        {200},
        "effective branch rules readback",
    )
    effective = canonical_effective_rule_evidence(effective_raw)

    ref_path = f"/repos/{REPOSITORY}/git/refs/{_ref_api_segment(branch_name)}"
    update = client.request("PATCH", ref_path, {"sha": main_sha, "force": False})
    if update.status not in {403, 422}:
        raise CutoverError(
            f"fast-forward update was not host-blocked; observed HTTP {update.status}"
        )

    delete = client.request("DELETE", ref_path)
    if delete.status not in {403, 422}:
        raise CutoverError(
            f"probe deletion was not host-blocked; observed HTTP {delete.status}"
        )

    recreate = client.request(
        "POST",
        f"/repos/{REPOSITORY}/git/refs",
        create_payload,
    )
    if recreate.status != 422:
        raise CutoverError(
            "probe recreate did not prove retained one-touch state; "
            f"observed HTTP {recreate.status}"
        )

    final_ref = _plain_dict(
        _expect(
            client.request(
                "GET",
                f"/repos/{REPOSITORY}/git/ref/{_ref_api_segment(branch_name)}",
            ),
            {200},
            "probe final readback",
        ),
        "probe final readback",
    )
    obj = _plain_dict(final_ref.get("object"), "probe final object")
    if obj.get("sha") != parent_sha:
        raise CutoverError("probe final SHA drifted despite expected update/delete blocks")

    payload = {
        "schema": RECEIPT_SCHEMA,
        "state": "REF_ROLLBACK_PROTECTION_VERIFIED",
        "repository": REPOSITORY,
        "default_branch": EXPECTED_DEFAULT_BRANCH,
        "main_sha_observed": main_sha,
        "main_parent_sha_used_for_probe": parent_sha,
        "candidate_raw_sha256": sha256_hex(candidate_raw),
        "candidate_semantic_sha256": sha256_hex(canonical_json(candidate)),
        "ruleset_id": canonical_ruleset["id"],
        "ruleset_name": RULESET_NAME,
        "ruleset_installed_during_run": installed_during_run,
        "ruleset_evidence_sha256": sha256_hex(canonical_json(canonical_ruleset)),
        "effective_rule_evidence_sha256": sha256_hex(canonical_json(effective)),
        "probe_ref": probe_ref,
        "probe_initial_and_final_sha": parent_sha,
        "fast_forward_update_status": update.status,
        "delete_status": delete.status,
        "recreate_status": recreate.status,
        "ref_rollback_protection_required": True,
        "ref_rollback_protection_verified": True,
        **_authority_false_fields(),
    }
    return _with_receipt_hash(payload)


def load_receipt_file(path: str | os.PathLike[str]) -> Any:
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise CutoverError("receipt must be a regular non-symlink file")
    data = p.read_bytes()
    if len(data) > MAX_JSON_BYTES:
        raise CutoverError("receipt exceeds bounded input size")
    try:
        return strict_json_loads(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise CutoverError("receipt must be UTF-8") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="outbound-ref-immutability-admin-cutover",
        description=(
            "Plan or execute the reviewed GitHub ruleset cutover. "
            "Never grants production send authority."
        ),
    )
    parser.add_argument(
        "--candidate",
        default=str(candidate_path()),
        help="path to the exact reviewed ruleset-candidate.json",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="validate candidate and emit deterministic HOLD plan")

    apply_parser = sub.add_parser(
        "apply",
        help="requires explicit Administration(write) token and runs host readback/hostiles",
    )
    apply_parser.add_argument("--probe-id", required=True)
    apply_parser.add_argument(
        "--token-env",
        default="GITHUB_ADMIN_TOKEN",
        help="environment variable containing the admin token; token is never emitted",
    )

    verify_parser = sub.add_parser(
        "verify-receipt",
        help="verify receipt self-hash and hard authority ceilings only",
    )
    verify_parser.add_argument("--receipt", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify-receipt":
            receipt = load_receipt_file(args.receipt)
            ok = verify_self_hash(receipt)
            print("VALID_RECEIPT_STRUCTURE" if ok else "INVALID_RECEIPT_STRUCTURE")
            return 0 if ok else 2

        candidate_raw, candidate = load_reviewed_candidate(args.candidate)
        if args.command == "plan":
            print(canonical_json(build_plan(candidate_raw, candidate)))
            return 0

        if args.command == "apply":
            if not _TOKEN_ENV_RE.fullmatch(args.token_env):
                raise CutoverError("token-env must be a bounded uppercase environment name")
            token = os.environ.get(args.token_env)
            if not token:
                raise CutoverError(
                    f"{args.token_env} is not set; refusing any network/admin mutation"
                )
            receipt = apply_cutover(
                GitHubApi(token),
                candidate_raw,
                candidate,
                args.probe_id,
            )
            print(canonical_json(receipt))
            return 0

        raise AssertionError("unreachable")
    except CutoverError as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
