#!/usr/bin/env python3
"""Validate, summarize, and optionally reverify Commons collaboration targets."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = Path("revenue/ip/collaboration_targets.json")
SCHEMA_PATH = Path("revenue/ip/collaboration_targets.schema.json")
ROUTES = ("LAB_REPRODUCTION", "VENDOR_INTEGRATION", "RESEARCHER_EVALUATION")
TARGET_IDS = (
    "eleutherai-lm-eval-harness",
    "mlcommons-inference",
    "hugging-face-hub",
    "nvidia-tensorrt-llm",
    "ggml-llama-cpp",
    "bitsandbytes-foundation",
)
EXPECTED_ASSOCIATIONS = {
    "eleutherai-lm-eval-harness": (
        "whitebox-joint-paper-reproduction", "EleutherAI/lm-evaluation-harness",
        "dd417662e5bda6a247489ec28d2ff46a45d1c42c", "README.md",
        "bdf7de36c33c4484487c5269d4d9790b64b72283", "# Language Model Evaluation Harness",
    ),
    "mlcommons-inference": (
        "whitebox-sponsored-benchmark", "mlcommons/inference",
        "cfb0df14b21a3898521891f021a1c6aadec2ab2c", "README.md",
        "81fb646d6e9fb1351bdf227be288b1b6f808b55f",
        "MLPerf Inference is a benchmark suite for measuring how fast systems can run models",
    ),
    "hugging-face-hub": (
        "whitebox-private-evaluation", "huggingface/huggingface_hub",
        "2c60641c98afa344892600e6ba76e010959ed637", "README.md",
        "d626032c129815d0373f5c4cc12e811933839068",
        "The `huggingface_hub` library allows you to interact with the [Hugging Face Hub]",
    ),
    "nvidia-tensorrt-llm": (
        "whitebox-private-evaluation", "NVIDIA/TensorRT-LLM",
        "767af6f2856bcfb9dbd888b00b02d105dedee4b5", "README.md",
        "d94ad93c9b26a35c732d4c55f01ed495e68dbb06",
        "TensorRT LLM optimizes inference for LLMs and Visual Gen models",
    ),
    "ggml-llama-cpp": (
        "whitebox-joint-paper-reproduction", "ggml-org/llama.cpp",
        "925e1179947ea0c0ebfb0032df18af3a729822be", "README.md",
        "0b5598c6e5bd9a8130136ee5009cbc500729c953",
        "llama cli -hf ggml-org/Qwen3.5-0.8B-GGUF",
    ),
    "bitsandbytes-foundation": (
        "whitebox-sponsored-benchmark", "bitsandbytes-foundation/bitsandbytes",
        "4f1fc6c249d72a95145b5563927656f291378cad", "README.md",
        "e2501a99a5c07e0f97a7b4366bdada809da33703",
        "`bitsandbytes` enables accessible large language models via k-bit quantization for PyTorch",
    ),
}
OFFER_IDS = {
    "whitebox-sponsored-benchmark",
    "whitebox-joint-paper-reproduction",
    "whitebox-private-evaluation",
}
TRUTH_KEYS = {"contacted", "interest_verified", "agreement_signed", "delivery_completed", "cash_received"}
HEX40 = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class CollaborationTargetError(ValueError):
    """The target ledger violates its evidence or commercial boundary."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CollaborationTargetError(message)


def _exact_keys(value: dict, required: set[str], at: str) -> None:
    _require(isinstance(value, dict), f"{at} must be an object")
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    _require(not missing, f"{at} missing keys {missing!r}")
    _require(not extra, f"{at} has extra keys {extra!r}")


def _safe_path(value: str, at: str) -> str:
    _require(isinstance(value, str) and value and "\\" not in value, f"{at} path invalid")
    parsed = PurePosixPath(value)
    _require(not parsed.is_absolute() and ".." not in parsed.parts and str(parsed) == value, f"{at} path escapes root")
    return value


def _git(root: Path, *args: str, binary: bool = False):
    completed = subprocess.run(
        ["git", "-C", str(root), *args], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise CollaborationTargetError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout if binary else completed.stdout.decode("utf-8").strip()


def _git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def load(root: Path = ROOT) -> tuple[dict, dict]:
    data = json.loads((root / LEDGER_PATH).read_text(encoding="utf-8"))
    schema = json.loads((root / SCHEMA_PATH).read_text(encoding="utf-8"))
    return data, schema


def validate(root: Path, data: dict, schema: dict) -> dict:
    _require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "schema draft mismatch")
    _require(schema.get("$id", "").endswith("/revenue/ip/collaboration_targets.schema.json"), "schema id mismatch")
    _require(schema.get("additionalProperties") is False, "schema root must be closed")
    _exact_keys(
        data,
        {
            "schema_version", "kind", "generated_at", "generated_from_main", "assessed_at", "scope",
            "boundary", "truth", "offer_catalog_source", "targets",
        },
        "ledger",
    )
    _require(data["schema_version"] == "commons-collaboration-targets/v1", "schema_version mismatch")
    _require(data["kind"] == "COLLABORATION_TARGETS", "kind mismatch")
    _require(bool(HEX40.fullmatch(data["generated_from_main"])), "generated_from_main invalid")
    _git(root, "cat-file", "-e", f"{data['generated_from_main']}^{{commit}}")
    _require(data["assessed_at"] == "2026-08-26", "assessed_at drift")
    _require(isinstance(data["generated_at"], str) and "T" in data["generated_at"], "generated_at invalid")
    _require("not outreach" in data["boundary"].lower(), "research-only boundary missing")
    _require("owner white box archive is excluded" in data["boundary"].lower(), "archive exclusion missing")
    _exact_keys(data["truth"], TRUTH_KEYS, "truth")
    _require(not any(data["truth"].values()), "truth block may not invent contact or commercial outcomes")

    offer_source = data["offer_catalog_source"]
    _exact_keys(offer_source, {"path", "blob_sha"}, "offer_catalog_source")
    offer_path = _safe_path(offer_source["path"], "offer_catalog_source")
    actual_offer_blob = _git(root, "rev-parse", f"{data['generated_from_main']}:{offer_path}")
    _require(actual_offer_blob == offer_source["blob_sha"], f"offer catalog blob drift: {actual_offer_blob}")
    offer_catalog = json.loads(_git(root, "cat-file", "blob", actual_offer_blob, binary=True))
    available_offers = {offer["id"] for offer in offer_catalog["offers"]}
    _require(OFFER_IDS.issubset(available_offers), "mapped offers missing from source catalog")

    targets = data["targets"]
    _require(isinstance(targets, list) and len(targets) == 6, "exactly six targets required")
    _require([target.get("id") for target in targets] == list(TARGET_IDS), "target order/set drift")
    route_counts = Counter()
    entities = set()
    repositories = set()
    mapped_counts = Counter()
    target_keys = {
        "id", "entity", "route", "status", "mapped_offer_id", "collaboration_hypothesis", "evidence_limit",
        "next_action", "asset_boundary", "uses_owner_archive_payload", "source",
    }
    source_keys = {
        "repository", "commit_sha", "readme_path", "readme_blob_sha", "evidence_phrase", "immutable_url", "observed_at"
    }
    for index, target in enumerate(targets):
        at = f"targets[{index}]"
        _exact_keys(target, target_keys, at)
        _require(target["route"] in ROUTES, f"{at} route invalid")
        route_counts[target["route"]] += 1
        _require(target["status"] == "RESEARCHED_NOT_CONTACTED", f"{at} contact state drift")
        _require(target["mapped_offer_id"] in OFFER_IDS, f"{at} mapped offer invalid")
        mapped_counts[target["mapped_offer_id"]] += 1
        _require(target["asset_boundary"] == "CUSTOMER_OWNED_OR_INDEPENDENTLY_CLEARED", f"{at} asset boundary drift")
        _require(target["uses_owner_archive_payload"] is False, f"{at} archive payload use must remain false")
        for key in ("entity", "collaboration_hypothesis", "evidence_limit", "next_action"):
            _require(isinstance(target[key], str) and len(target[key]) >= 8, f"{at}.{key} empty")
        _require(target["entity"] not in entities, f"{at} duplicate entity")
        entities.add(target["entity"])

        source = target["source"]
        _exact_keys(source, source_keys, f"{at}.source")
        actual_association = (
            target["mapped_offer_id"], source["repository"], source["commit_sha"], source["readme_path"],
            source["readme_blob_sha"], source["evidence_phrase"],
        )
        _require(actual_association == EXPECTED_ASSOCIATIONS[target["id"]], f"{at} target source/offer association drift")
        _require(bool(REPO.fullmatch(source["repository"])), f"{at}.source repository invalid")
        _require(source["repository"] not in repositories, f"{at}.source duplicate repository")
        repositories.add(source["repository"])
        _require(bool(HEX40.fullmatch(source["commit_sha"])), f"{at}.source commit invalid")
        _require(bool(HEX40.fullmatch(source["readme_blob_sha"])), f"{at}.source blob invalid")
        readme_path = _safe_path(source["readme_path"], f"{at}.source")
        expected_url = f"https://github.com/{source['repository']}/blob/{source['commit_sha']}/{readme_path}"
        _require(source["immutable_url"] == expected_url, f"{at}.source immutable URL drift")
        _require(source["observed_at"] == "2026-08-26", f"{at}.source observed_at drift")
        _require(isinstance(source["evidence_phrase"], str) and len(source["evidence_phrase"]) >= 8, f"{at}.source phrase too short")

    _require(route_counts == Counter({route: 2 for route in ROUTES}), "route buckets must remain 2/2/2")
    _require(all(mapped_counts[offer_id] > 0 for offer_id in OFFER_IDS), "all executable collaboration offers must be represented")
    return {
        "status": "VALID",
        "targets": len(targets),
        "route_counts": {route: route_counts[route] for route in ROUTES},
        "mapped_offers": len(mapped_counts),
        "contacted": data["truth"]["contacted"],
        "cash_received": data["truth"]["cash_received"],
    }


def verify_remote(data: dict, timeout: float = 20.0) -> dict:
    verified = 0
    for index, target in enumerate(data["targets"]):
        source = target["source"]
        url = f"https://raw.githubusercontent.com/{source['repository']}/{source['commit_sha']}/{source['readme_path']}"
        request = urllib.request.Request(url, headers={"User-Agent": "commons-collaboration-targets/1"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except (OSError, urllib.error.URLError) as exc:
            raise CollaborationTargetError(f"targets[{index}].source fetch failed: {exc}") from exc
        _require(_git_blob_sha(raw) == source["readme_blob_sha"], f"targets[{index}].source remote blob drift")
        text = raw.decode("utf-8", "replace")
        _require(source["evidence_phrase"] in text, f"targets[{index}].source remote phrase missing")
        verified += 1
    return {"status": "REMOTE_VERIFIED", "sources": verified}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("validate", "summary", "verify-remote"), default="validate")
    parser.add_argument("--root", default=str(ROOT), help="Commons repository root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        data, schema = load(root)
        result = validate(root, data, schema)
        if args.command == "verify-remote":
            result = verify_remote(data)
    except (CollaborationTargetError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"COLLABORATION TARGETS INVALID: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
