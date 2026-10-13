#!/usr/bin/env python3
"""Validate and summarize the dated Commons phone-agent capability map."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = Path("revenue/ip/phone_agent_capability_map.json")
SCHEMA_PATH = Path("revenue/ip/phone_agent_capability_map.schema.json")
DIMENSIONS = (
    "interruption",
    "latency",
    "tool_use",
    "recovery",
    "receipts",
    "deployment_boundary",
    "data_handling",
)
STATUSES = {"MEASURED", "SOURCE_DOCUMENTED", "UNKNOWN"}
SOURCE_KINDS = {"COMMONS_GIT", "PROVIDER_PRIMARY", "NONE"}
BOUNDARIES = {"DEVICE_CONTROL_AGENT", "REALTIME_AUDIO_API", "VOICE_AGENT_PLATFORM"}
HEX40 = re.compile(r"^[0-9a-f]{40}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
PRIMARY_HOSTS = {
    "openai": {"developers.openai.com", "platform.openai.com", "openai.com"},
    "google": {"ai.google.dev"},
    "xai": {"docs.x.ai"},
    "elevenlabs": {"elevenlabs.io"},
}
TRUTH_KEYS = {
    "benchmark_performed",
    "win_claimed",
    "external_deployment_verified",
    "buyer_interest_verified",
    "cash_received",
}


class CapabilityMapError(ValueError):
    """The map violates its source or comparison contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CapabilityMapError(message)


def _exact_keys(value: dict, required: set[str], at: str) -> None:
    _require(isinstance(value, dict), f"{at} must be an object")
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    _require(not missing, f"{at} missing keys {missing!r}")
    _require(not extra, f"{at} has extra keys {extra!r}")


def _safe_path(value: str, at: str) -> str:
    _require(isinstance(value, str) and value, f"{at} path is empty")
    _require("\\" not in value, f"{at} path must use POSIX separators")
    parsed = PurePosixPath(value)
    _require(not parsed.is_absolute(), f"{at} path must be relative")
    _require(".." not in parsed.parts, f"{at} path escapes root")
    _require(str(parsed) == value, f"{at} path is not canonical")
    return value


def _git(root: Path, *args: str, binary: bool = False):
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise CapabilityMapError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout if binary else completed.stdout.decode("utf-8").strip()


def _validate_source(root: Path, base: str, provider_id: str, claim: dict, at: str) -> None:
    source = claim["source"]
    _exact_keys(
        source,
        {"kind", "url", "source_date", "observed_at", "path", "blob_sha", "evidence_phrase"},
        f"{at}.source",
    )
    _require(source["kind"] in SOURCE_KINDS, f"{at}.source kind invalid")
    _require(source["observed_at"] == "2026-08-26", f"{at}.source observed_at drift")
    status = claim["status"]
    if status == "UNKNOWN":
        _require(source["kind"] == "NONE", f"{at} UNKNOWN must use NONE source")
        _require(source["url"] == "" and source["path"] == "" and source["blob_sha"] == "", f"{at} UNKNOWN source must be empty")
        _require(source["source_date"] == "UNKNOWN" and source["evidence_phrase"] == "", f"{at} UNKNOWN source sentinels invalid")
        _require(claim["statement"].startswith("UNKNOWN:"), f"{at} UNKNOWN statement must be explicit")
        _require("not assessed as absent" in claim["statement"], f"{at} UNKNOWN must calibrate absence")
        return

    _require(source["kind"] != "NONE", f"{at} documented claim has no source")
    _require(isinstance(source["url"], str) and source["url"].startswith("https://"), f"{at}.source URL invalid")
    _require(source["source_date"] == "UNKNOWN" or DATE.fullmatch(source["source_date"]), f"{at}.source date invalid")
    _require(isinstance(source["evidence_phrase"], str) and len(source["evidence_phrase"]) >= 8, f"{at}.source evidence phrase too short")

    if source["kind"] == "COMMONS_GIT":
        path = _safe_path(source["path"], f"{at}.source")
        _require(bool(HEX40.fullmatch(source["blob_sha"])), f"{at}.source blob invalid")
        actual = _git(root, "rev-parse", f"{base}:{path}")
        _require(actual == source["blob_sha"], f"{at}.source blob drift: {actual}")
        raw = _git(root, "cat-file", "blob", actual, binary=True).decode("utf-8", "replace")
        _require(source["evidence_phrase"].casefold() in raw.casefold(), f"{at}.source evidence phrase missing")
        expected = f"https://github.com/woahwhattheheck/commons/blob/{base}/{path}"
        _require(source["url"] == expected, f"{at}.source Git URL mismatch")
    else:
        _require(source["path"] == "" and source["blob_sha"] == "", f"{at}.source external path/blob must be empty")
        hosts = PRIMARY_HOSTS.get(provider_id)
        _require(hosts is not None, f"{at} external provider has no primary-host policy")
        _require(urlparse(source["url"]).hostname in hosts, f"{at}.source is not provider-primary")


def load(root: Path = ROOT) -> tuple[dict, dict]:
    data = json.loads((root / MAP_PATH).read_text(encoding="utf-8"))
    schema = json.loads((root / SCHEMA_PATH).read_text(encoding="utf-8"))
    return data, schema


def validate(root: Path, data: dict, schema: dict) -> dict:
    _require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "schema draft mismatch")
    _require(schema.get("$id", "").endswith("/revenue/ip/phone_agent_capability_map.schema.json"), "schema id mismatch")
    _require(schema.get("additionalProperties") is False, "schema root must be closed")
    _exact_keys(
        data,
        {
            "schema_version", "kind", "generated_at", "generated_from_main", "assessed_at",
            "scope", "comparison_boundary", "commercial_use", "truth", "dimensions", "systems",
        },
        "map",
    )
    _require(data["schema_version"] == "commons-phone-agent-capability-map/v1", "schema_version mismatch")
    _require(data["kind"] == "PHONE_AGENT_CAPABILITY_MAP", "kind mismatch")
    _require(bool(HEX40.fullmatch(data["generated_from_main"])), "generated_from_main invalid")
    _git(root, "cat-file", "-e", f"{data['generated_from_main']}^{{commit}}")
    _require(data["assessed_at"] == "2026-08-26", "assessed_at drift")
    _require(isinstance(data["generated_at"], str) and "T" in data["generated_at"], "generated_at invalid")
    for key in ("scope", "comparison_boundary", "commercial_use"):
        _require(isinstance(data[key], str) and data[key], f"{key} empty")
    _require("not a ranking" in data["comparison_boundary"].lower(), "comparison boundary must reject direct ranking")
    _exact_keys(data["truth"], TRUTH_KEYS, "truth")
    _require(not any(data["truth"].values()), "truth block may not invent commercial or benchmark outcomes")
    _require(data["dimensions"] == list(DIMENSIONS), "dimension order/set drift")

    systems = data["systems"]
    _require(isinstance(systems, list) and len(systems) == 5, "exactly five systems required")
    ids = []
    boundary_counts = Counter()
    status_counts = Counter()
    for index, system in enumerate(systems):
        at = f"systems[{index}]"
        _exact_keys(system, {"id", "provider", "offering", "boundary_kind", "evidence_scope", "claims"}, at)
        _require(bool(ID.fullmatch(system["id"])), f"{at}.id invalid")
        ids.append(system["id"])
        _require(system["boundary_kind"] in BOUNDARIES, f"{at}.boundary_kind invalid")
        boundary_counts[system["boundary_kind"]] += 1
        for key in ("provider", "offering", "evidence_scope"):
            _require(isinstance(system[key], str) and system[key], f"{at}.{key} empty")
        claims = system["claims"]
        _exact_keys(claims, set(DIMENSIONS), f"{at}.claims")
        for dimension in DIMENSIONS:
            claim = claims[dimension]
            claim_at = f"{at}.claims.{dimension}"
            _exact_keys(claim, {"status", "statement", "limitations", "source"}, claim_at)
            _require(claim["status"] in STATUSES, f"{claim_at}.status invalid")
            _require(isinstance(claim["statement"], str) and claim["statement"], f"{claim_at}.statement empty")
            _require(isinstance(claim["limitations"], str) and claim["limitations"], f"{claim_at}.limitations empty")
            if claim["status"] == "MEASURED":
                _require(system["id"] == "commons-lda-titan", f"{claim_at} external provider may not be marked MEASURED")
            status_counts[claim["status"]] += 1
            _validate_source(root, data["generated_from_main"], system["id"], claim, claim_at)
    _require(len(ids) == len(set(ids)), "duplicate system ids")
    _require(boundary_counts["DEVICE_CONTROL_AGENT"] == 1, "exactly one device-control system required")
    _require(status_counts["UNKNOWN"] > 0, "map must preserve unknowns")
    return {
        "status": "VALID",
        "systems": len(systems),
        "dimensions": len(DIMENSIONS),
        "claims": len(systems) * len(DIMENSIONS),
        "status_counts": dict(sorted(status_counts.items())),
        "boundary_counts": dict(sorted(boundary_counts.items())),
        "benchmark_performed": data["truth"]["benchmark_performed"],
        "cash_received": data["truth"]["cash_received"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("validate", "summary"), default="validate")
    parser.add_argument("--root", default=str(ROOT), help="Commons repository root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        data, schema = load(root)
        result = validate(root, data, schema)
    except (CapabilityMapError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"PHONE AGENT CAPABILITY MAP INVALID: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
