"""Deterministic synthetic acceptance fixture for the conformance kernel."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
try:
    from .kernel import canonical_bytes, canonical_sha256, evaluate, sha256_hex, verify_report
except ImportError:
    from kernel import canonical_bytes, canonical_sha256, evaluate, sha256_hex, verify_report

CLIENTS = ["copilot", "claude-code", "cursor", "postman-agent", "customer-agent"]
PROTOCOL = "2025-06-18"
TOOLS = ["getCodeSample", "getOperationPermissions", "getOperationSchema", "listOperations"]
SCHEMA_RESOURCE = {"operation":"vm.list","params":{"page":{"type":"integer"},"filter":{"type":"string"}},"returns":{"type":"array"}}
RAW_RESOURCE = b"\x00mcp-conformance\xfffixture\x10"

def make_manifest() -> Dict[str, Any]:
    fixture_payload = {"fixture":"synthetic-v4-schema-v1","operations":["vm.list","vm.get","cluster.list"],"policy":"read-discovery-only"}
    return {
        "schema":"mcp-cross-client-conformance/v1",
        "server_build":"synthetic-buyer-neutral-build-001",
        "fixture":{"id":"synthetic-v4-schema-v1","sha256":canonical_sha256(fixture_payload)},
        "supported_protocol_versions":[PROTOCOL,"2026-03-26"],
        "clients":list(CLIENTS),
        "expected_tools":list(TOOLS),
        "resources":[
            {"id":"schema:vm.list","kind":"json","sha256":sha256_hex(canonical_bytes(SCHEMA_RESOURCE))},
            {"id":"raw:sample.bin","kind":"raw","sha256":sha256_hex(RAW_RESOURCE)},
        ],
        "hostile_expectations":{
            "corrupt_binary":"HOLD","omitted_tool":"HOLD","silent_downgrade":"REJECT",
            "stale_schema":"HOLD","unreachable_listing":"UNVERIFIED","unsupported_protocol":"REJECT",
        },
        "clean_runs_per_client":2,
        "production_action_limit":0,
    }

def base_observation(manifest: Dict[str, Any], client: str, run_id: str) -> Dict[str, Any]:
    return {
        "observation_id":f"{client}:{run_id}","client_id":client,"run_id":run_id,"case":"clean",
        "server_build":manifest["server_build"],"fixture_sha256":manifest["fixture"]["sha256"],
        "requested_protocol_version":PROTOCOL,"negotiated_protocol_version":PROTOCOL,
        "negotiation_status":"OK","listing_status":"OK","listed_tools":list(TOOLS),
        "resource_hashes":{r["id"]:r["sha256"] for r in manifest["resources"]},"production_action_count":0,
    }

def make_acceptance() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    manifest = make_manifest(); observations: List[Dict[str, Any]] = []
    for client in CLIENTS:
        observations += [base_observation(manifest, client, "clean-1"), base_observation(manifest, client, "clean-2")]
    first = CLIENTS[0]
    obs = base_observation(manifest, first, "hostile-unsupported-protocol")
    obs.update(observation_id="hostile:unsupported_protocol",case="unsupported_protocol",requested_protocol_version="1900-01-01",negotiated_protocol_version=None,negotiation_status="REJECTED",listing_status="REJECTED",listed_tools=[],resource_hashes={}); observations.append(obs)
    obs = base_observation(manifest, first, "hostile-silent-downgrade")
    obs.update(observation_id="hostile:silent_downgrade",case="silent_downgrade",requested_protocol_version="2026-03-26",negotiated_protocol_version=PROTOCOL,negotiation_status="DOWNGRADED"); observations.append(obs)
    obs = base_observation(manifest, first, "hostile-omitted-tool")
    obs.update(observation_id="hostile:omitted_tool",case="omitted_tool",listed_tools=TOOLS[:-1]); observations.append(obs)
    obs = base_observation(manifest, first, "hostile-stale-schema"); hashes = dict(obs["resource_hashes"]); hashes["schema:vm.list"] = "0"*64
    obs.update(observation_id="hostile:stale_schema",case="stale_schema",resource_hashes=hashes); observations.append(obs)
    obs = base_observation(manifest, first, "hostile-corrupt-binary"); hashes = dict(obs["resource_hashes"]); hashes["raw:sample.bin"] = "1"*64
    obs.update(observation_id="hostile:corrupt_binary",case="corrupt_binary",resource_hashes=hashes); observations.append(obs)
    obs = base_observation(manifest, first, "hostile-unreachable")
    obs.update(observation_id="hostile:unreachable_listing",case="unreachable_listing",listing_status="UNREACHABLE",listed_tools=[],resource_hashes={}); observations.append(obs)
    return manifest, observations

def acceptance_result() -> Dict[str, Any]:
    manifest, observations = make_acceptance(); report = evaluate(manifest, observations)
    return {"manifest":manifest,"observations":observations,"report":report,"verified":verify_report(report)}

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--write", type=Path, default=None); args = parser.parse_args(argv)
    result = acceptance_result(); payload = canonical_bytes(result) + b"\n"
    if args.write: args.write.write_bytes(payload)
    else: sys.stdout.buffer.write(payload)
    return 0 if result["verified"] and result["report"]["overall"] == "PASS" else 2
if __name__ == "__main__": raise SystemExit(main())
