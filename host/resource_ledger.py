#!/usr/bin/env python3
"""host/resource_ledger.py — master resource lifecycle; cache is not capacity.

Slack 1787637936.134649 (DEMON live compute/connector board):
use live surfaces, do not count cache as capacity, keep a ledger
with evidence timestamp, auth surface, exact safe probe, rate/plan
boundary, assigned backlog, and last receipt.

A Slack utilization report is CLAIMED. This v2 instrument extends the original
connector board to people, devices, repositories, builds, subscriptions,
models, agents, tools, data, roads, and commercial assets. Missing instrument is
NOT_LANDED. Calling cache "connected" as capacity is NOT_LANDED.
Hugging Face without a token or CLI is NOT_VERIFIED, not live.
Vercel production deploy is a write; this leftover refuses it.
titan: NOT_WRITTEN.

  python3 host/resource_ledger.py
  python3 host/resource_ledger.py --root .
  python3 host/resource_ledger.py --self-test
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys


DEFAULT_CATALOG = os.path.join("ground", "RESOURCE_LEDGER.json")
SLACK_TS = "1787637936.134649"
REQUIRED_FIELDS = (
    "evidence_ts",
    "auth_surface",
    "exact_safe_probe",
    "rate_plan_boundary",
    "assigned_backlog",
    "last_receipt",
)
CAPACITY_STATES = ("LIVE", "CACHE", "NOT_VERIFIED", "UNMEASURED", "FORBIDDEN")
RESOURCE_STAGES = (
    "DECLARED",
    "AVAILABLE",
    "REACHABLE",
    "ASSIGNED",
    "EXERCISED",
    "PRODUCING",
)
RESOURCE_CONDITIONS = (
    "LIVE",
    "IDLE",
    "HELD",
    "BLOCKED",
    "CONSTRAINED",
    "DEGRADED",
    "DORMANT",
    "STALE",
    "ACTIVE_UNKNOWN",
    "SUPERSEDED",
    "ARCHIVED",
    "DEAD",
    "UNMEASURED",
)
RESOURCE_FRESHNESS_STATES = ("FRESH", "STALE", "EVENT_DRIVEN", "NEEDS_PROBE", "UNMEASURED")
V2_REQUIRED_FIELDS = (
    "kind",
    "stage",
    "condition",
    "consumer",
    "value",
    "next_action",
    "source",
    "holder",
    "authority",
    "last_used_at",
    "stale_after",
)
TESTER_AUTHORITY_NEEDLES = (
    "tester",
    "verifier",
    "review authority",
    "final-qa",
    "final qa",
    "red-team-as-verdict",
)
HF_TOKEN_REL = (
    os.path.join(".huggingface", "token"),
    os.path.join(".cache", "huggingface", "token"),
    os.path.join(".hf", "token"),
)


def load_catalog(text):
    """Parse the resource ledger. Invalid JSON is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"surfaces": [], "error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"surfaces": [], "error": "catalog is not an object"}
    surfaces = []
    seen = set()
    for item in data.get("surfaces") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        row = {"name": name}
        for field in REQUIRED_FIELDS:
            row[field] = str(item.get(field) or "").strip()
        row["capacity"] = str(item.get("capacity") or "").strip().upper()
        row["cache_counted"] = bool(item.get("cache_counted"))
        row["tester_authority"] = bool(item.get("tester_authority"))
        for field in V2_REQUIRED_FIELDS:
            row[field] = str(item.get(field) or "").strip()
        row["kind"] = row["kind"].upper()
        row["stage"] = row["stage"].upper()
        row["condition"] = row["condition"].upper()
        row["quantity"] = item.get("quantity")
        row["links"] = list(item.get("links") or [])
        row["priority"] = int(item.get("priority") or 0)
        surfaces.append(row)
    return {
        "surfaces": surfaces,
        "schema": str(data.get("schema") or "commons-resource-ledger/v1").strip(),
        "snapshot": data.get("snapshot") or {},
        "stage_order": list(data.get("stage_order") or RESOURCE_STAGES),
        "priority_queue": list(data.get("priority_queue") or []),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "source_id": str(data.get("source_id") or "").strip(),
        "cache_as_capacity": bool(data.get("cache_as_capacity")),
        "production_write": bool(data.get("production_write")),
        "secrets": bool(data.get("secrets")),
        "hands_off": list(data.get("hands_off") or []),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
    }


def parse_utc(value):
    """Parse the ledger's public UTC timestamps; invalid input stays unknown."""
    text = str(value or "").strip()
    if not text or text.lower() == "unknown":
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def parse_duration(value):
    """Parse the bounded ISO-8601 durations used by this ledger (PnD/PTnH)."""
    text = str(value or "").strip().upper()
    if text.startswith("PT") and text.endswith("H") and text[2:-1].isdigit():
        return dt.timedelta(hours=int(text[2:-1]))
    if text.startswith("P") and text.endswith("D") and text[1:-1].isdigit():
        return dt.timedelta(days=int(text[1:-1]))
    return None


def evidence_freshness(row, observed_at):
    """Measure evidence age without rewriting capacity or operating condition."""
    evidence_at = parse_utc((row or {}).get("evidence_ts"))
    boundary = str((row or {}).get("stale_after") or "").strip()
    duration = parse_duration(boundary)
    if duration:
        now = parse_utc(observed_at)
        if evidence_at is None or now is None:
            return "UNMEASURED"
        return "STALE" if now > evidence_at + duration else "FRESH"
    lowered = boundary.lower()
    if not boundary or lowered in ("unknown", "probe-before-use", "resolve-before-new-reservation"):
        return "NEEDS_PROBE"
    return "EVENT_DRIVEN"


def local_probes(home, which=shutil.which):
    """Read-only host facts. No tokens, no network, no account writes."""
    home = os.path.abspath(home or ".")
    token_hits = []
    for rel in HF_TOKEN_REL:
        path = os.path.join(home, rel)
        if os.path.isfile(path):
            token_hits.append(rel)
    mcp_path = os.path.join(home, ".cursor", "mcp.json")
    return {
        "hf_token_files": token_hits,
        "hf_cli": bool(which("huggingface-cli") or which("hf")),
        "grok_exe": bool(which("grok") or which("grok.exe")),
        "claude_cli": bool(which("claude")),
        "vercel_cli": bool(which("vercel")),
        "mcp_exists": os.path.isfile(mcp_path),
    }


def classify_surface(row, probes=None):
    """One surface: LIVE / CACHE / NOT_VERIFIED / UNMEASURED / FORBIDDEN."""
    row = row or {}
    probes = probes or {}
    name = str(row.get("name") or "").strip().lower()
    capacity = str(row.get("capacity") or "").strip().upper()
    missing = [field for field in REQUIRED_FIELDS if not str(row.get(field) or "").strip()]
    meta = {
        "kind": str(row.get("kind") or "UNCLASSIFIED").strip().upper(),
        "stage": str(row.get("stage") or "").strip().upper(),
        "condition": str(row.get("condition") or "UNMEASURED").strip().upper(),
        "consumer": str(row.get("consumer") or "").strip(),
        "value": str(row.get("value") or "").strip(),
        "next_action": str(row.get("next_action") or "").strip(),
        "source": str(row.get("source") or "").strip(),
        "holder": str(row.get("holder") or "").strip(),
        "authority": str(row.get("authority") or "").strip(),
        "evidence_ts": str(row.get("evidence_ts") or "").strip(),
        "last_used_at": str(row.get("last_used_at") or "").strip(),
        "stale_after": str(row.get("stale_after") or "").strip(),
        "quantity": row.get("quantity"),
        "priority": int(row.get("priority") or 0),
    }

    def result(measured_capacity, note, tester_authority=False):
        return {
            "name": name,
            "capacity": measured_capacity,
            "missing_fields": missing,
            "tester_authority": tester_authority,
            "note": note,
            **meta,
        }

    if name.startswith("claude"):
        backlog = str(row.get("assigned_backlog") or "").lower()
        informational = "informational" in backlog
        tester = any(needle in backlog for needle in TESTER_AUTHORITY_NEEDLES)
        if tester and not informational:
            return result(
                "UNMEASURED",
                (
                    "Claude assigned_backlog still grants tester/verifier/"
                    "review authority. Informational evidence only. "
                    "Route verification to local/GHA/Codex; route Grok analysis "
                    "to SuperGrok Heavy / Grok Build. Cursor is on quota hold."
                ),
                tester_authority=True,
            )
        return result(
            capacity if capacity in CAPACITY_STATES else "UNMEASURED",
            (
                "claude is informational only; not tester/verifier/QA. "
                "Prior Claude verdicts this window stay UNVERIFIED."
            ),
        )
    if name == "huggingface":
        if probes.get("hf_token_files") or probes.get("hf_cli"):
            pass
        elif capacity == "LIVE" or row.get("cache_counted"):
            return result(
                "NOT_VERIFIED",
                "huggingface specifically is NOT verified. No token file and no CLI here. Cache is not capacity.",
            )
        return result(
            "NOT_VERIFIED",
            "huggingface specifically is NOT verified. Do not call cache connected.",
        )
    if name == "vercel" and row.get("production_write"):
        return result(
            "FORBIDDEN",
            "vercel deploy is a production write. Refused without exact scope.",
        )
    if capacity not in CAPACITY_STATES:
        return result(
            "UNMEASURED",
            "%s has no measured capacity. Absence was not stillness." % (name or "surface"),
        )
    if row.get("cache_counted") or capacity == "CACHE":
        return result(
            "CACHE",
            "%s is cache, not capacity. Do not count it as live." % (name or "surface"),
        )
    return result(
        capacity,
        "%s recorded as %s. Required ledger fields must stay filled."
        % (name or "surface", capacity),
    )


def measure_from_rows(facts):
    """Pure census so tests do not need a live connector bus."""
    facts = facts or {}
    probes = facts.get("probes") or {}
    surfaces = []
    for item in facts.get("surfaces") or []:
        surfaces.append(classify_surface(item, probes))
    live = [row["name"] for row in surfaces if row["capacity"] == "LIVE"]
    cache = [row["name"] for row in surfaces if row["capacity"] == "CACHE"]
    not_verified = [row["name"] for row in surfaces if row["capacity"] == "NOT_VERIFIED"]
    missing_fields = any(row.get("missing_fields") for row in surfaces if row["capacity"] == "LIVE")
    hf_live = "huggingface" in live
    tester_authority = any(row.get("tester_authority") for row in surfaces)
    schema = str(facts.get("schema") or "commons-resource-ledger/v1")
    is_v2 = schema.endswith("/v2")
    v2_missing = []
    invalid_stages = []
    invalid_conditions = []
    stage_counts = {stage: 0 for stage in RESOURCE_STAGES}
    kind_counts = {}
    activation_queue = []
    expired_resources = []
    freshness_counts = {state: 0 for state in RESOURCE_FRESHNESS_STATES}
    observed_at = (facts.get("snapshot") or {}).get("observed_at")
    for raw, measured in zip(facts.get("surfaces") or [], surfaces):
        freshness = evidence_freshness(raw, observed_at)
        measured["evidence_freshness"] = freshness
        measured["claim_active"] = freshness != "STALE"
        freshness_counts[freshness] += 1
        if freshness == "STALE":
            expired_resources.append(measured["name"])
        if is_v2:
            missing = [field for field in V2_REQUIRED_FIELDS if not str(raw.get(field) or "").strip()]
            if missing:
                v2_missing.append({"name": measured["name"], "fields": missing})
        stage = measured.get("stage") or ""
        condition = measured.get("condition") or "UNMEASURED"
        kind = measured.get("kind") or "UNCLASSIFIED"
        if stage in stage_counts:
            stage_counts[stage] += 1
        elif is_v2:
            invalid_stages.append(measured["name"])
        if condition not in RESOURCE_CONDITIONS and is_v2:
            invalid_conditions.append(measured["name"])
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        if (
            stage in ("REACHABLE", "ASSIGNED", "EXERCISED")
            and condition in ("LIVE", "IDLE", "CONSTRAINED", "DEGRADED", "DORMANT")
            and measured.get("next_action")
            and freshness in ("FRESH", "EVENT_DRIVEN")
        ):
            activation_queue.append(
                {
                    "name": measured["name"],
                    "stage": stage,
                    "condition": condition,
                    "next_action": measured["next_action"],
                    "consumer": measured.get("consumer") or "",
                    "value": measured.get("value") or "",
                    "priority": int(raw.get("priority") or 0),
                    "evidence_freshness": freshness,
                }
            )
    activation_queue.sort(key=lambda item: (-item["priority"], item["name"]))
    return {
        "measured": True,
        "surfaces": surfaces,
        "live": live,
        "cache": cache,
        "not_verified": not_verified,
        "live_count": len(live),
        "cache_count": len(cache),
        "cache_as_capacity": bool(facts.get("cache_as_capacity")) or hf_live,
        "production_write": bool(facts.get("production_write")),
        "missing_fields": missing_fields,
        "secrets": bool(facts.get("secrets")),
        "probes": {
            "hf_token_files": list(probes.get("hf_token_files") or []),
            "hf_cli": bool(probes.get("hf_cli")),
            "grok_exe": bool(probes.get("grok_exe")),
            "claude_cli": bool(probes.get("claude_cli")),
            "vercel_cli": bool(probes.get("vercel_cli")),
            "mcp_exists": bool(probes.get("mcp_exists")),
        },
        "titan": "NOT_WRITTEN",
        "claude_tester_authority": tester_authority,
        "schema": schema,
        "v2_missing": v2_missing,
        "invalid_stages": invalid_stages,
        "invalid_conditions": invalid_conditions,
        "stage_counts": stage_counts,
        "kind_counts": kind_counts,
        "activation_queue": activation_queue,
        "expired_resources": expired_resources,
        "freshness_counts": freshness_counts,
        "producing_count": stage_counts["PRODUCING"],
        "resource_count": len(surfaces),
    }


def classify(row):
    """Turn a measured ledger into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "resource ledger not read. Absence was not stillness. "
                "A Slack compute board is not a live probe."
            ),
        }
    if row.get("secrets"):
        return {
            "state": "NOT_LANDED",
            "note": "ledger tried to record secrets. Drop them. Status only.",
        }
    if row.get("production_write"):
        return {
            "state": "NOT_LANDED",
            "note": "production/account/financial write refused without exact scope.",
        }
    if row.get("cache_as_capacity"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "cache was counted as capacity. Hugging Face and the Aug 21 "
                "connected-list are not live. Measure again."
            ),
        }
    if row.get("claude_tester_authority"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "Claude still has tester/verifier/review authority on the "
                "resource ledger. Informational only. Do not assign Claude "
                "a tester role."
            ),
        }
    if row.get("missing_fields"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "LIVE rows are missing evidence_ts / auth_surface / "
                "exact_safe_probe / rate_plan_boundary / assigned_backlog / "
                "last_receipt."
            ),
        }
    if row.get("v2_missing") or row.get("invalid_stages") or row.get("invalid_conditions"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "v2 resources need kind/stage/condition/consumer/value/next_action/source "
                "and known lifecycle values."
            ),
        }
    if not row.get("live"):
        return {
            "state": "CANDIDATE",
            "note": "ledger measured, but no LIVE surface yet. Cache is still not capacity.",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "live resource ledger is on this file. Cache is not capacity. "
            "Hugging Face is NOT verified. Forbidden writes skipped. "
            "titan NOT_WRITTEN. Talk is not a land."
        ),
    }


def catalog_from_row(row):
    """Public receipt summary. Names and states only. No secrets."""
    row = row or {}
    return {
        "slack_ts": SLACK_TS,
        "source_id": "codex-master-resource-office-20260826-01",
        "subject": "MASTER RESOURCE LEDGER — inventory is not utilization",
        "cache_as_capacity": False,
        "production_write": False,
        "secrets": False,
        "titan": "NOT_WRITTEN",
        "live": list(row.get("live") or []),
        "cache": list(row.get("cache") or []),
        "not_verified": list(row.get("not_verified") or []),
        "probes": row.get("probes") or {},
        "stage_counts": row.get("stage_counts") or {},
        "kind_counts": row.get("kind_counts") or {},
        "activation_queue": row.get("activation_queue") or [],
        "hands_off": [
            "vercel production deploy",
            "financial/messaging/account writes",
            "state.vscdb delete/vacuum/repair",
            "cml pr 2108",
            "titan --go",
            "jojo mcp/wake",
            "demon swarm flight recorder",
        ],
    }


def measure_root(root, home=None):
    """Read the catalog plus local probe facts from this host."""
    root = os.path.abspath(root or ".")
    path = os.path.join(root, DEFAULT_CATALOG)
    text = ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    catalog = load_catalog(text)
    probes = local_probes(home or os.path.expanduser("~"))
    measured = measure_from_rows(
        {
            "surfaces": catalog.get("surfaces") or [],
            "schema": catalog.get("schema") or "commons-resource-ledger/v1",
            "snapshot": catalog.get("snapshot") or {},
            "probes": probes,
            "cache_as_capacity": catalog.get("cache_as_capacity"),
            "production_write": catalog.get("production_write"),
            "secrets": catalog.get("secrets"),
        }
    )
    measured["catalog_path"] = path
    measured["slack_ts"] = catalog.get("slack_ts") or SLACK_TS
    measured["hands_off"] = catalog.get("hands_off") or []
    return measured


def self_test():
    """Stdlib checks. A zero here is a broken leftover."""
    empty = classify({})
    if empty["state"] != "UNMEASURED":
        raise SystemExit("empty ledger must be UNMEASURED")
    secrets = classify({"measured": True, "secrets": True, "live": ["github"]})
    if secrets["state"] != "NOT_LANDED":
        raise SystemExit("secrets must be NOT_LANDED")
    cache = classify({"measured": True, "cache_as_capacity": True, "live": ["github"]})
    if cache["state"] != "NOT_LANDED":
        raise SystemExit("cache-as-capacity must be NOT_LANDED")
    hf = classify_surface({"name": "huggingface", "capacity": "LIVE", "cache_counted": True}, {})
    if hf["capacity"] != "NOT_VERIFIED":
        raise SystemExit("huggingface cache must not become LIVE")
    print("resource_ledger self-test ok")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Live resource ledger. Cache is not capacity.")
    parser.add_argument("--root", default=".", help="commons checkout root")
    parser.add_argument("--home", default="", help="home for local probes (default ~)")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    measured = measure_root(args.root, args.home or None)
    verdict = classify(measured)
    out = {
        "state": verdict["state"],
        "note": verdict["note"],
        "live": measured["live"],
        "cache": measured["cache"],
        "not_verified": measured["not_verified"],
        "resource_count": measured["resource_count"],
        "producing_count": measured["producing_count"],
        "stage_counts": measured["stage_counts"],
        "kind_counts": measured["kind_counts"],
        "activation_queue": measured["activation_queue"],
        "expired_resources": measured["expired_resources"],
        "freshness_counts": measured["freshness_counts"],
        "probes": measured["probes"],
        "titan": measured["titan"],
        "secrets": False,
    }
    json.dump(out, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if verdict["state"] == "INTEGRATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
