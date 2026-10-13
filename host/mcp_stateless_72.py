#!/usr/bin/env python3
"""Validate and verify the MCP 2026-07-28 static compatibility evidence pack."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = Path("revenue/mcp_stateless_72/prospects.json")
SCHEMA_PATH = Path("revenue/mcp_stateless_72/prospects.schema.json")
BUILD_PATHS = (
    "revenue/mcp_stateless_72/prospects.schema.json",
    "revenue/mcp_stateless_72/prospects.json",
    "host/mcp_stateless_72.py",
    "test_mcp_stateless_72.py",
)
BASE_SHA = "6827afadf7428e2139299da704a0821567b0037f"
CHECKED_AT = "2026-08-26T23:39:00Z"
EXPECTED_SCHEMA_SHA256 = "c9a6b2747b8026733b81c335021c6747d233ad5b7019889fd02688ccd7d48e50"
EXPECTED_PACK_SHA256 = "2c2dbb4ad8eab97b69fdef5da99adf7a9f9fe09b813d1420ded8d818376d58ff"
SCHEMA_URL = "https://woahwhattheheck.github.io/commons/revenue/mcp_stateless_72/prospects.schema.json"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ID_TEXT = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
REPOSITORY_TEXT = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
EXPECTED_OFFICIAL_IDS = (
    "mcp-2026-07-28-changelog",
    "mcp-2026-07-28-streamable-http",
)
EXPECTED_PROSPECT_IDS = (
    "modelcontextprotocol-python-sdk",
    "modelcontextprotocol-typescript-sdk",
    "modelcontextprotocol-go-sdk",
    "modelcontextprotocol-conformance",
    "modelcontextprotocol-java-sdk",
    "modelcontextprotocol-rust-sdk",
    "mark3labs-mcp-go",
    "openai-agents-python",
    "modelcontextprotocol-kotlin-sdk",
    "modelcontextprotocol-csharp-sdk",
)
EXPECTED_TRUTH = {
    "static_protocol_signal_only": True,
    "defect_confirmed": False,
    "vulnerability_confirmed": False,
    "buyer_confirmed": False,
    "pain_confirmed": False,
    "demand_confirmed": False,
    "willingness_to_pay_confirmed": False,
    "contact_permission_confirmed": False,
    "delivery_readiness_confirmed": False,
    "acceptance_confirmed": False,
    "revenue_confirmed": False,
    "cash_received_usd": 0,
}
EXPECTED_OMISSIONS = (
    "contact_email",
    "contact_phone",
    "credentials",
    "mailing_addresses",
    "payment_routing",
    "personal_names",
    "private_urls",
    "tokens",
)
ROOT_KEYS = {
    "$schema",
    "schema_version",
    "kind",
    "generated_at",
    "generated_from_main",
    "schema_sha256",
    "owner",
    "scope",
    "official_sources",
    "truth",
    "unapproved_candidate_material",
    "omitted_private_fields",
    "prospects",
}
PROVENANCE_KEYS = {
    "id",
    "repository",
    "commit",
    "path",
    "raw_url",
    "commit_url",
    "checked_at",
    "byte_count",
    "sha256",
    "git_blob_sha1",
    "newline",
    "line_count",
}
OFFICIAL_KEYS = PROVENANCE_KEYS | {"facts"}
PROSPECT_KEYS = PROVENANCE_KEYS | {
    "signals",
    "observations",
    "evidence_state",
    "owner",
    "analysis",
    "nonclaims",
}
SIGNAL_KEYS = {"mcp_session_id", "legacy_initialize", "legacy_protocol_version"}
SIGNAL_NAMES = {
    "MCP_SESSION_ID": "mcp_session_id",
    "LEGACY_INITIALIZE": "legacy_initialize",
    "LEGACY_PROTOCOL_VERSION": "legacy_protocol_version",
}
PRIVATE_KEYS = {
    "api_key",
    "bank_details",
    "contact_email",
    "contact_phone",
    "credential",
    "credentials",
    "mailing_address",
    "payment_routing",
    "personal_name",
    "private_url",
    "routing_number",
    "secret",
    "token",
}
MAX_SOURCE_BYTES = 5_000_000


class EvidenceError(ValueError):
    """The evidence pack does not meet its fail-closed public contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _exact_keys(value, required: set[str], at: str) -> None:
    _require(isinstance(value, dict), "%s must be an object" % at)
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    _require(not missing, "%s missing keys %r" % (at, missing))
    _require(not extra, "%s has extra keys %r" % (at, extra))


def _reject_duplicate_pairs(pairs):
    parsed = {}
    for key, value in pairs:
        _require(key not in parsed, "duplicate JSON key %r" % key)
        parsed[key] = value
    return parsed


def _reject_nonfinite(value: str):
    raise EvidenceError("non-finite JSON constant %s" % value)


def _parse_json(raw: bytes, at: str):
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise EvidenceError("%s is not UTF-8" % at) from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except json.JSONDecodeError as exc:
        raise EvidenceError("%s is malformed JSON" % at) from exc


def _repository_bytes(raw: bytes, at: str) -> bytes:
    """Return Git-canonical LF bytes while rejecting non-CRLF carriage returns."""
    normalized = raw.replace(b"\r\n", b"\n")
    _require(b"\r" not in normalized, "%s contains an unsupported carriage return" % at)
    return normalized


def _assert_closed_schema(value, at: str = "$schema") -> None:
    if isinstance(value, dict):
        if value.get("type") == "object":
            _require(value.get("additionalProperties") is False, "%s object schema is open" % at)
        for key, child in value.items():
            _assert_closed_schema(child, "%s.%s" % (at, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_closed_schema(child, "%s[%d]" % (at, index))


def _walk_private_keys(value, at: str = "$") -> None:
    if isinstance(value, dict):
        found = sorted(PRIVATE_KEYS.intersection(value))
        _require(not found, "%s publishes private keys %r" % (at, found))
        for key, child in value.items():
            _walk_private_keys(child, "%s.%s" % (at, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_private_keys(child, "%s[%d]" % (at, index))


def _nonempty_text(value, at: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), "%s must be nonempty text" % at)
    return value


def _safe_path(value, at: str) -> str:
    path = _nonempty_text(value, at)
    _require(not path.startswith(("/", "\\")), "%s must be repository-relative" % at)
    _require("\\" not in path, "%s contains a backslash" % at)
    parts = path.split("/")
    _require(all(part not in {"", ".", ".."} for part in parts), "%s contains traversal" % at)
    return path


def _safe_https(value, host: str, at: str) -> str:
    text = _nonempty_text(value, at)
    _require("\\" not in text, "%s contains a backslash" % at)
    parsed = urlsplit(text)
    _require(parsed.scheme == "https" and parsed.hostname == host, "%s has wrong HTTPS host" % at)
    _require(parsed.username is None and parsed.password is None, "%s embeds credentials" % at)
    try:
        port = parsed.port
    except ValueError as exc:
        raise EvidenceError("%s has an invalid port" % at) from exc
    _require(port is None, "%s must not include a port" % at)
    _require(not parsed.query and not parsed.fragment, "%s has query or fragment" % at)
    decoded = unquote(parsed.path)
    _require("\\" not in decoded, "%s decodes to a backslash" % at)
    _require(all(part not in {".", ".."} for part in decoded.split("/")), "%s contains traversal" % at)
    return text


def _validate_provenance(item, at: str) -> None:
    _require(bool(ID_TEXT.fullmatch(_nonempty_text(item["id"], at + ".id"))), "%s.id is malformed" % at)
    repository = _nonempty_text(item["repository"], at + ".repository")
    _require(bool(REPOSITORY_TEXT.fullmatch(repository)), "%s.repository is malformed" % at)
    commit = _nonempty_text(item["commit"], at + ".commit")
    _require(bool(HEX40.fullmatch(commit)), "%s.commit is not a full lowercase SHA" % at)
    path = _safe_path(item["path"], at + ".path")
    raw_url = _safe_https(item["raw_url"], "raw.githubusercontent.com", at + ".raw_url")
    commit_url = _safe_https(item["commit_url"], "github.com", at + ".commit_url")
    encoded_path = quote(path, safe="/")
    _require(
        raw_url == "https://raw.githubusercontent.com/%s/%s/%s" % (repository, commit, encoded_path),
        "%s.raw_url does not match repository, commit, and path" % at,
    )
    _require(
        commit_url == "https://github.com/%s/blob/%s/%s" % (repository, commit, encoded_path),
        "%s.commit_url does not match repository, commit, and path" % at,
    )
    _require(item["checked_at"] == CHECKED_AT, "%s.checked_at drifted" % at)
    _require(isinstance(item["byte_count"], int) and not isinstance(item["byte_count"], bool), "%s.byte_count is not an integer" % at)
    _require(0 < item["byte_count"] <= MAX_SOURCE_BYTES, "%s.byte_count is outside bounds" % at)
    _require(isinstance(item["sha256"], str) and bool(HEX64.fullmatch(item["sha256"])), "%s.sha256 is malformed" % at)
    _require(isinstance(item["git_blob_sha1"], str) and bool(HEX40.fullmatch(item["git_blob_sha1"])), "%s.git_blob_sha1 is malformed" % at)
    _require(item["newline"] == "LF", "%s.newline must be LF" % at)
    _require(isinstance(item["line_count"], int) and not isinstance(item["line_count"], bool) and item["line_count"] > 0, "%s.line_count is invalid" % at)


def _validate_line_evidence(values, allowed_names: set[str] | None, line_count: int, at: str) -> None:
    _require(isinstance(values, list) and bool(values), "%s must be a nonempty list" % at)
    seen = set()
    for index, value in enumerate(values):
        item_at = "%s[%d]" % (at, index)
        required = {"line", "excerpt"} | ({"signal"} if allowed_names is not None else {"statement"})
        _exact_keys(value, required, item_at)
        label_key = "signal" if allowed_names is not None else "statement"
        label = _nonempty_text(value[label_key], item_at + "." + label_key)
        if allowed_names is not None:
            _require(label in allowed_names, "%s.signal is unknown" % item_at)
        line = value["line"]
        _require(isinstance(line, int) and not isinstance(line, bool) and 1 <= line <= line_count, "%s.line is outside source" % item_at)
        excerpt = _nonempty_text(value["excerpt"], item_at + ".excerpt")
        _require("\r" not in excerpt and "\n" not in excerpt, "%s.excerpt spans lines" % item_at)
        key = (label, line)
        _require(key not in seen, "%s duplicates line evidence" % item_at)
        seen.add(key)


def validate(root: Path, pack, schema) -> dict:
    _assert_closed_schema(schema)
    _exact_keys(pack, ROOT_KEYS, "$")
    _require(pack["$schema"] == SCHEMA_URL, "$.$schema drifted")
    _require(pack["schema_version"] == "1.0.0", "$.schema_version drifted")
    _require(pack["kind"] == "MCP_STATELESS_72_VERIFIED_STATIC_SIGNAL_PACK", "$.kind drifted")
    _require(pack["generated_at"] == CHECKED_AT, "$.generated_at drifted")
    _require(pack["generated_from_main"] == BASE_SHA, "$.generated_from_main drifted")
    _require(pack["schema_sha256"] == EXPECTED_SCHEMA_SHA256, "$.schema_sha256 drifted")
    _require(pack["owner"] == "COMMONS_ANY_PEER", "$.owner must remain nonexclusive")
    _nonempty_text(pack["scope"], "$.scope")
    _require(pack["truth"] == EXPECTED_TRUTH, "$.truth must remain exact and noncommercial")
    _require(pack["unapproved_candidate_material"] == {"present": False, "owner_approved": False}, "$.unapproved_candidate_material drifted")
    _require(tuple(pack["omitted_private_fields"]) == EXPECTED_OMISSIONS, "$.omitted_private_fields drifted")

    sources = pack["official_sources"]
    _require(isinstance(sources, list), "$.official_sources must be an array")
    _require(tuple(item.get("id") for item in sources if isinstance(item, dict)) == EXPECTED_OFFICIAL_IDS, "$.official_sources ids or order drifted")
    for index, source in enumerate(sources):
        at = "$.official_sources[%d]" % index
        _exact_keys(source, OFFICIAL_KEYS, at)
        _validate_provenance(source, at)
        _validate_line_evidence(source["facts"], None, source["line_count"], at + ".facts")

    prospects = pack["prospects"]
    _require(isinstance(prospects, list), "$.prospects must be an array")
    _require(tuple(item.get("id") for item in prospects if isinstance(item, dict)) == EXPECTED_PROSPECT_IDS, "$.prospects ids or order drifted")
    for index, prospect in enumerate(prospects):
        at = "$.prospects[%d]" % index
        _exact_keys(prospect, PROSPECT_KEYS, at)
        _validate_provenance(prospect, at)
        _exact_keys(prospect["signals"], SIGNAL_KEYS, at + ".signals")
        _require(all(isinstance(value, bool) for value in prospect["signals"].values()), "%s.signals must be booleans" % at)
        _validate_line_evidence(prospect["observations"], set(SIGNAL_NAMES), prospect["line_count"], at + ".observations")
        observed = {SIGNAL_NAMES[item["signal"]] for item in prospect["observations"]}
        declared = {name for name, present in prospect["signals"].items() if present}
        _require(observed == declared, "%s.signals do not match observations" % at)
        _require(prospect["evidence_state"] == "VERIFIED_STATIC_SIGNAL", "%s.evidence_state drifted" % at)
        _require(prospect["owner"] == "COMMONS_ANY_PEER", "%s.owner must remain nonexclusive" % at)
        analysis = _nonempty_text(prospect["analysis"], at + ".analysis")
        _require(analysis.startswith("ANALYSIS: "), "%s.analysis must be labeled" % at)
        _require(bool(analysis[len("ANALYSIS: ") :].strip()), "%s.analysis must contain non-whitespace analysis" % at)
        _require(isinstance(prospect["nonclaims"], list) and prospect["nonclaims"] == ["No defect, buyer, demand, contact permission, readiness, acceptance, or revenue is inferred."], "%s.nonclaims drifted" % at)

    all_ids = [item["id"] for item in sources + prospects]
    _require(len(all_ids) == len(set(all_ids)), "evidence ids are duplicated")
    _walk_private_keys(pack)
    return {"status": "VALID", "kind": pack["kind"], "sources": len(sources), "prospects": len(prospects)}


def load(root: Path = ROOT):
    pack_raw = _repository_bytes((root / PACK_PATH).read_bytes(), str(PACK_PATH))
    schema_raw = _repository_bytes((root / SCHEMA_PATH).read_bytes(), str(SCHEMA_PATH))
    _require(hashlib.sha256(pack_raw).hexdigest() == EXPECTED_PACK_SHA256, "prospects.json raw SHA-256 drifted")
    _require(hashlib.sha256(schema_raw).hexdigest() == EXPECTED_SCHEMA_SHA256, "prospects.schema.json raw SHA-256 drifted")
    pack = _parse_json(pack_raw, str(PACK_PATH))
    schema = _parse_json(schema_raw, str(SCHEMA_PATH))
    validate(root, pack, schema)
    return pack, schema


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _git_blob_sha1(raw: bytes) -> str:
    header = b"blob " + str(len(raw)).encode("ascii") + b"\0"
    return hashlib.sha1(header + raw).hexdigest()


def _verify_source(item, opener) -> None:
    request = Request(
        item["raw_url"],
        headers={"Accept-Encoding": "identity", "User-Agent": "Commons-MCP-Stateless-72/1.0"},
        method="GET",
    )
    try:
        with opener.open(request, timeout=20) as response:
            _require(getattr(response, "status", None) == 200, "%s returned non-200" % item["id"])
            _require(response.geturl() == item["raw_url"], "%s final URL changed" % item["id"])
            length = response.headers.get("Content-Length")
            if length is not None:
                _require(length.isdigit(), "%s returned invalid Content-Length" % item["id"])
                _require(int(length) == item["byte_count"], "%s Content-Length drifted" % item["id"])
            raw = response.read(min(item["byte_count"], MAX_SOURCE_BYTES) + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise EvidenceError("%s fetch failed: %s" % (item["id"], exc)) from exc
    _require(len(raw) == item["byte_count"], "%s byte count drifted" % item["id"])
    _require(hashlib.sha256(raw).hexdigest() == item["sha256"], "%s SHA-256 drifted" % item["id"])
    _require(_git_blob_sha1(raw) == item["git_blob_sha1"], "%s git blob SHA-1 drifted" % item["id"])
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise EvidenceError("%s is not UTF-8" % item["id"]) from exc
    _require("\r" not in text, "%s is not LF-only" % item["id"])
    lines = text.splitlines()
    _require(len(lines) == item["line_count"], "%s line count drifted" % item["id"])
    evidence = item.get("facts", item.get("observations", []))
    for observation in evidence:
        _require(lines[observation["line"] - 1] == observation["excerpt"], "%s line %d excerpt drifted" % (item["id"], observation["line"]))


def verify_sources(pack) -> dict:
    opener = build_opener(_NoRedirect())
    items = pack["official_sources"] + pack["prospects"]
    for item in items:
        _verify_source(item, opener)
    return {"status": "VERIFIED", "sources": len(items), "checked_at": CHECKED_AT}


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _command_list(pack) -> dict:
    return {
        "status": "VERIFIED_STATIC_SIGNAL_LIST",
        "prospects": [
            {
                "id": item["id"],
                "repository": item["repository"],
                "commit": item["commit"],
                "commit_url": item["commit_url"],
                "evidence_state": item["evidence_state"],
                "signals": item["signals"],
            }
            for item in pack["prospects"]
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "list", "next", "verify-sources"))
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        pack, _schema = load(args.root.resolve())
        if args.command == "validate":
            result = validate(args.root.resolve(), pack, _schema)
        elif args.command == "list":
            result = _command_list(pack)
        elif args.command == "next":
            result = {"status": "NONE_READY", "reason": "STATIC_PROTOCOL_SIGNAL_EVIDENCE_ONLY"}
        else:
            result = verify_sources(pack)
    except (EvidenceError, OSError) as exc:
        print(_canonical({"status": "ERROR", "error": str(exc)}), file=sys.stderr)
        return 2
    print(_canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
