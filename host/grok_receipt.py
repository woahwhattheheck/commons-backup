#!/usr/bin/env python3
"""host/grok_receipt.py — exact-one-fence Grok envelope; last-fence is collision.

Slack 1787650886.402809 (DEMON HEAVY DAMAGE-CONTROL UPDATE):
PR 2320 / last-fence is COLLISION (scratch-smuggling). Unique leftover
is exact-one-fence (thought/text excluded, raw SHA, explicit exits)
plus finder failures as null/UNMEASURED, generator-backed pixel
receipt, Gemma path correction, and the two live false-zero patches.

Do not merge PR 2320. Do not remint rivet-ship-grok-receipt-20260825-01.
Do not remint PIXEL_HEARTBEAT leftover / STRANDED_MAP leftover /
H-002 / HEAVY_LANES / BUILD_SWEEP_ACT / HUMAN_OUTCOMES / JOJO
LDA-Subzero. Do not hand-edit STRANDED_MAP.json. Titan helper
fail-open is BOUNDARY_ONLY — not an active Titan mutation path.
No Titan mutation. DIO/JOJO names stay. Claude stays quarantined
candidate generation only. Every Grok envelope is CANDIDATE.
Current-main bytes + non-Grok tests decide. Never 0.

  python3 host/grok_receipt.py
  python3 host/grok_receipt.py --root .
  python3 host/grok_receipt.py --self-test
  python3 host/grok_receipt.py --check completed-envelope.json
  python3 host/grok_receipt.py --output normalized.json completed-envelope.json
  grok ... --output-format json | python3 host/grok_receipt.py --check -
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "GROK_RECEIPT.json")
DEFAULT_CARD = os.path.join("ground", "GROK_RECEIPT.md")
H009_CARD = os.path.join("ground", "H009.md")
H009_CATALOG = os.path.join("ground", "H009.json")
SLACK_TS = "1787650886.402809"
PRIOR_SLACK_TS = "1787649265.015869"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "grok_receipt.py"),
    H009_CARD,
    H009_CATALOG,
    os.path.join("host", "device_path_census.py"),
    os.path.join("host", "device_churn.py"),
    os.path.join("ground", "PIXEL_HEARTBEAT.json"),
    os.path.join("ground", "GEMMA_TOKENIZER_MAP.md"),
    os.path.join("ground", "GEMMA_INGRESS.md"),
    os.path.join("pixels", "RIVET.json"),
    os.path.join("infra", "host", "muhl_dump_litertlm.py"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("ground", "H002.md"),
    os.path.join("ground", "HEAVY_LANES.md"),
    os.path.join("ground", "PIXEL_HEARTBEAT.md"),
    os.path.join("ground", "STRANDED_MAP.md"),
    os.path.join("ground", "HUMAN_OUTCOMES.md"),
)
REQUIRED_PHRASES = (
    "exact-one-fence",
    "last-fence is collision",
    "thought/text excluded",
    "raw sha",
    "explicit exits",
    "finder-failed",
    "finder-unverified",
    "never 0",
    "every grok envelope is candidate",
    "do not merge pr 2320",
    "boundary_only",
    "no titan mutation",
    "open door",
    "no auth",
    "no gate",
    "talk is not a land",
)
CANDIDATE_RECEIPTS = (
    "H-001 ARCHITECT",
    "SKEPTIC",
    "H-004 FALSE-ZERO",
    "H-003 integration",
    "H-005 frontier",
    "H-002 contamination",
)
H009_PATCHED = (
    "device_ls_tree_collapse",
    "device_missing_dir_zero",
)
EXIT_INTEGRATED = 0
EXIT_NOT_LANDED = 1
EXIT_UNMEASURED = 2
EXIT_FINDER_FAILED = 3

# Completed Grok Build envelope exits are namespaced so the existing land-desk
# 0/1/2/3 contract above remains stable for callers such as land.js.
RECEIPT_SCHEMA = "grok-receipt/v1"
SCHEMA = RECEIPT_SCHEMA
RECEIPT_EXIT_OK = 0
RECEIPT_EXIT_MISSING_FILE = 3
RECEIPT_EXIT_INVALID_ENVELOPE = 4
RECEIPT_EXIT_ZERO_FENCES = 5
RECEIPT_EXIT_MULTIPLE_FENCES = 6
RECEIPT_EXIT_INVALID_INNER_JSON = 7
RECEIPT_EXIT_WRONG_TYPE = 8
RECEIPT_EXIT_MISSING_PACKET_ID = 9
RECEIPT_EXIT_WRITE_FAILURE = 10
RECEIPT_EXIT_REVISION_CONTRADICTION = 11
RECEIPT_EXIT_FINDER_FAILED = 12
RECEIPT_EXIT_DUPLICATE_KEY = 13
RECEIPT_MAX_SOURCE_BYTES = 8 * 1024 * 1024
SOURCE_REVISION_KEYS = frozenset(
    {"source_head", "git_head", "source_rev", "source_rev_file"}
)
HEX_REV_RE = re.compile(r"^[0-9a-f]{7,40}$")
MEASURED_NAMES = (
    "H-001-ARCHITECT.json",
    "H-001-SKEPTIC.json",
    "H-002-CONTAMINATION.json",
)
SMOKE_ENV = "GROK_HEAVY_RECEIPTS"

RECEIPT_STATUS_BY_EXIT = {
    RECEIPT_EXIT_OK: "OK",
    RECEIPT_EXIT_MISSING_FILE: "MISSING_FILE",
    RECEIPT_EXIT_INVALID_ENVELOPE: "INVALID_ENVELOPE",
    RECEIPT_EXIT_ZERO_FENCES: "ZERO_FENCES",
    RECEIPT_EXIT_MULTIPLE_FENCES: "MULTIPLE_FENCES",
    RECEIPT_EXIT_INVALID_INNER_JSON: "INVALID_INNER_JSON",
    RECEIPT_EXIT_WRONG_TYPE: "WRONG_TYPE",
    RECEIPT_EXIT_MISSING_PACKET_ID: "MISSING_PACKET_ID",
    RECEIPT_EXIT_WRITE_FAILURE: "WRITE_FAILURE",
    RECEIPT_EXIT_REVISION_CONTRADICTION: "REVISION_CONTRADICTION",
    RECEIPT_EXIT_FINDER_FAILED: "FINDER_FAILED",
    RECEIPT_EXIT_DUPLICATE_KEY: "DUPLICATE_KEY",
}

RECEIPT_OPTIONAL_OUTER_FIELDS = (
    "stopReason",
    "requestId",
    "num_turns",
    "total_cost_usd",
    "total_cost_usd_ticks",
)


class DuplicateJSONKey(ValueError):
    """A JSON object repeated a member name and therefore has no unique meaning."""

    def __init__(self, key):
        super().__init__("duplicate JSON object key %r" % key)
        self.key = key


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKey(key)
        result[key] = value
    return result


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def raw_sha(root):
    """Exact git SHA of root. Failure is null, never a guessed hash."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode:
        return None
    sha = (proc.stdout or "").strip()
    if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
        return None
    return sha


def _receipt_json_fence(text):
    """Return one JSON fence whose opener ends a line.

    Heavy receipts use two measured opener dialects: a marker on its own line,
    or the same marker appended to the end of a prose line.  Inline prose that
    continues after a literal marker is not a fence, and marker strings inside
    the JSON body stay packet data.  Every qualifying opener is counted,
    including an unclosed extra opener after a complete block.
    """
    lines = str(text).splitlines(keepends=True)

    def is_json_opener(line):
        logical = line.rstrip("\r\n").rstrip(" \t").casefold()
        marker = "```json"
        if logical.count(marker) != 1:
            return False
        if logical == marker:
            return True
        if not logical.endswith(marker):
            return False
        prefix = logical[: -len(marker)]
        return bool(prefix) and not prefix.endswith("`")

    opener_lines = [
        position
        for position, line in enumerate(lines)
        if is_json_opener(line)
    ]
    openers = len(opener_lines)
    if not openers:
        return None, RECEIPT_EXIT_ZERO_FENCES, "text contains no fenced JSON object", 0
    if openers != 1:
        return (
            None,
            RECEIPT_EXIT_MULTIPLE_FENCES,
            "text contains %d JSON fence openers; exactly one is required" % openers,
            openers,
        )
    opener = opener_lines[0]
    closer = next(
        (
            position
            for position in range(opener + 1, len(lines))
            if lines[position].strip() == "```"
        ),
        None,
    )
    if closer is None:
        return (
            None,
            RECEIPT_EXIT_INVALID_INNER_JSON,
            "JSON fence is not closed",
            openers,
        )
    return "".join(lines[opener + 1 : closer]), RECEIPT_EXIT_OK, "", openers


def normalize_envelope(text):
    """Exact-one-fence is authoritative. Last-fence is scratch-smuggling.

    0 fences or 2+ fences: FINDER-FAILED, authoritative=None.
    Unfenced prose is ignored structurally; packet strings are never scrubbed.
    The completed-envelope boundary excludes outer thought/text separately.
    Every envelope stays CANDIDATE until current-main bytes + non-Grok tests decide.
    """
    raw, fence_exit, fence_error, count = _receipt_json_fence(text)
    if count != 1 or fence_exit != RECEIPT_EXIT_OK:
        return {
            "status": "CANDIDATE",
            "authoritative": None,
            "error": (
                "exact-one-fence required. fence_count=%s. %s. "
                "Last-fence is collision / scratch-smuggling. "
                "FINDER-FAILED, never 0."
                % (count, fence_error)
            ),
            "excluded": "scratch/thought/text plus extra fences",
            "fence_count": count,
        }
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {
            "status": "CANDIDATE",
            "authoritative": None,
            "error": "the one fence is not JSON. FINDER-FAILED, never 0.",
            "excluded": "scratch/thought/text",
            "fence_count": 1,
        }
    return {
        "status": "CANDIDATE",
        "authoritative": parsed,
        "error": "",
        "excluded": "scratch/thought/text",
        "fence_count": 1,
    }


def receipt_sha256(raw):
    """SHA-256 of the exact completed-envelope source bytes."""
    return hashlib.sha256(bytes(raw)).hexdigest()


def collect_revision_values(obj):
    """Collect authoritative revision-key shapes from the inner packet only."""
    grouped = {key: [] for key in SOURCE_REVISION_KEYS}
    stack = [(obj, "$", False)]
    while stack:
        value, path, in_schema_template = stack.pop()
        if isinstance(value, dict):
            for key, child in reversed(list(value.items())):
                child_path = "%s/%s" % (path, str(key).replace("~", "~0").replace("/", "~1"))
                key_lower = str(key).casefold()
                child_in_schema_template = (
                    in_schema_template
                    or key_lower == "schema"
                    or key_lower.endswith("_schema")
                )
                if key in SOURCE_REVISION_KEYS and not in_schema_template:
                    if isinstance(child, dict):
                        kind, scalar = "object", None
                    elif isinstance(child, (str, int)) and not isinstance(child, bool):
                        kind, scalar = "scalar", str(child)
                    else:
                        kind, scalar = type(child).__name__, None
                    grouped[key].append(
                        {"path": child_path, "type": kind, "value": scalar}
                    )
                if isinstance(child, (dict, list)):
                    stack.append((child, child_path, child_in_schema_template))
        elif isinstance(value, list):
            for position in range(len(value) - 1, -1, -1):
                child = value[position]
                if isinstance(child, (dict, list)):
                    stack.append(
                        (child, "%s/%d" % (path, position), in_schema_template)
                    )
    return {key: rows for key, rows in grouped.items() if rows}


def revisions_compatible(left, right):
    """Accept exact identities and canonical hex prefix/full-SHA pairs."""
    if left == right:
        return True
    left = str(left).strip().lower()
    right = str(right).strip().lower()
    if not HEX_REV_RE.fullmatch(left) or not HEX_REV_RE.fullmatch(right):
        return False
    return left.startswith(right) or right.startswith(left)


def detect_revision_contradictions(packet):
    """Return stable truth labels for incompatible inner revision facts."""
    contradictions = []
    for key, rows in sorted(collect_revision_values(packet).items()):
        types = {row["type"] for row in rows}
        invalid_types = sorted(types - {"object", "scalar"})
        paths = [row["path"] for row in rows]
        values = sorted(
            {row["value"] for row in rows if row["type"] == "scalar"}
        )
        if invalid_types:
            contradictions.append(
                {
                    "key": key,
                    "reason": "INVALID_REVISION_TYPE",
                    "paths": paths,
                    "types": sorted(types),
                    "values": values,
                }
            )
            continue
        if "object" in types and "scalar" in types:
            contradictions.append(
                {
                    "key": key,
                    "reason": "SCALAR_OBJECT_CONFLICT",
                    "paths": paths,
                    "types": sorted(types),
                    "values": values,
                }
            )
            continue
        incompatible = any(
            not revisions_compatible(left, right)
            for position, left in enumerate(values)
            for right in values[position + 1 :]
        )
        if incompatible:
            contradictions.append(
                {
                    "key": key,
                    "reason": "INCOMPATIBLE_REVISIONS",
                    "paths": paths,
                    "types": sorted(types),
                    "values": values,
                }
            )
    return contradictions


def find_measured_receipts(root, calibration_path=None):
    """Find measured smoke inputs without turning finder failure into zero."""
    base = os.fspath(root) if root else None
    if calibration_path is not None and not os.path.isfile(calibration_path):
        return {
            "state": "FINDER-FAILED",
            "count": None,
            "hits": [],
            "missing": list(MEASURED_NAMES),
            "z": "known-present calibration miss",
        }
    if not base or not os.path.isdir(base):
        return {
            "state": "FINDER-FAILED",
            "count": None,
            "hits": [],
            "missing": list(MEASURED_NAMES),
            "z": "receipt directory missing or unreadable",
        }
    hits = [name for name in MEASURED_NAMES if os.path.isfile(os.path.join(base, name))]
    missing = [name for name in MEASURED_NAMES if name not in hits]
    return {
        "state": "FOUND" if not missing else "FINDER-FAILED",
        "count": len(hits) if hits else None,
        "hits": hits,
        "missing": missing,
        "z": "" if not missing else "one or more named receipts were not found",
    }


def _receipt_source_name(source):
    """Keep private/absolute input paths out of normalized output."""
    if source in (None, "-"):
        return "-"
    return os.path.basename(os.fspath(source))


def _receipt_error(exit_code, message, raw=None, source="-"):
    payload = {
        "schema": RECEIPT_SCHEMA,
        "status": RECEIPT_STATUS_BY_EXIT[exit_code],
        "exit_code": exit_code,
        "error": str(message),
        "source": {"name": _receipt_source_name(source)},
    }
    if raw is not None:
        payload["source"]["bytes"] = len(raw)
        payload["source_sha256"] = receipt_sha256(raw)
    return payload, exit_code


def evaluate_receipt(raw, source="-"):
    """Validate completed Grok Build envelope bytes and normalize one packet.

    Only the outer ``text`` field is parsed. The optional outer ``thought``
    field is never inspected or merged into the packet.
    """
    try:
        raw = bytes(raw)
    except (TypeError, ValueError) as exc:
        return _receipt_error(
            RECEIPT_EXIT_INVALID_ENVELOPE,
            "outer envelope is not bytes: %s" % exc,
            source=source,
        )
    if len(raw) > RECEIPT_MAX_SOURCE_BYTES:
        return _receipt_error(
            RECEIPT_EXIT_INVALID_ENVELOPE,
            "source exceeds %d-byte receipt budget" % RECEIPT_MAX_SOURCE_BYTES,
            source=source,
        )
    try:
        envelope = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_json_object
        )
    except DuplicateJSONKey as exc:
        return _receipt_error(
            RECEIPT_EXIT_DUPLICATE_KEY,
            "outer envelope contains %s" % exc,
            raw,
            source,
        )
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        return _receipt_error(
            RECEIPT_EXIT_INVALID_ENVELOPE,
            "outer envelope is not UTF-8 JSON: %s" % exc,
            raw,
            source,
        )
    if not isinstance(envelope, dict):
        return _receipt_error(
            RECEIPT_EXIT_INVALID_ENVELOPE,
            "outer envelope must be an object",
            raw,
            source,
        )

    text = envelope.get("text")
    session_id = envelope.get("sessionId")
    usage = envelope.get("usage")
    model_usage = envelope.get("modelUsage")
    invalid = []
    if not isinstance(text, str):
        invalid.append("text:string")
    if not isinstance(session_id, str) or not session_id.strip():
        invalid.append("sessionId:nonempty-string")
    if not isinstance(usage, dict) or not usage:
        invalid.append("usage:nonempty-object")
    if (
        not isinstance(model_usage, dict)
        or not model_usage
        or not all(isinstance(value, dict) for value in model_usage.values())
    ):
        invalid.append("modelUsage:nonempty-object")
    if invalid:
        return _receipt_error(
            RECEIPT_EXIT_INVALID_ENVELOPE,
            "outer envelope missing/invalid " + ", ".join(invalid),
            raw,
            source,
        )

    body, fence_exit, fence_error, fence_count = _receipt_json_fence(text)
    if fence_exit != RECEIPT_EXIT_OK:
        return _receipt_error(fence_exit, fence_error, raw, source)
    try:
        packet = json.loads(body, object_pairs_hook=_unique_json_object)
    except DuplicateJSONKey as exc:
        return _receipt_error(
            RECEIPT_EXIT_DUPLICATE_KEY,
            "inner packet contains %s" % exc,
            raw,
            source,
        )
    except (ValueError, RecursionError) as exc:
        return _receipt_error(
            RECEIPT_EXIT_INVALID_INNER_JSON,
            "fenced body is not JSON: %s" % exc,
            raw,
            source,
        )
    if not isinstance(packet, dict):
        return _receipt_error(
            RECEIPT_EXIT_WRONG_TYPE,
            "fenced JSON must be an object",
            raw,
            source,
        )
    packet_id = packet.get("packet_id")
    if not isinstance(packet_id, str) or not packet_id.strip():
        return _receipt_error(
            RECEIPT_EXIT_MISSING_PACKET_ID,
            "fenced object requires packet_id:nonempty-string",
            raw,
            source,
        )

    models = sorted(str(name) for name in model_usage)
    outer = {
        name: envelope[name]
        for name in RECEIPT_OPTIONAL_OUTER_FIELDS
        if name in envelope
    }
    digest = receipt_sha256(raw)
    contradictions = detect_revision_contradictions(packet)
    exit_code = (
        RECEIPT_EXIT_REVISION_CONTRADICTION
        if contradictions
        else RECEIPT_EXIT_OK
    )
    result = {
        "schema": RECEIPT_SCHEMA,
        "status": RECEIPT_STATUS_BY_EXIT[exit_code],
        "exit_code": exit_code,
        "source_sha256": digest,
        "source": {
            "name": _receipt_source_name(source),
            "bytes": len(raw),
            "sha256": digest,
        },
        "sessionId": session_id,
        "model": models[0] if len(models) == 1 else None,
        "models": models,
        "usage": usage,
        "modelUsage": model_usage,
        "outer": outer,
        "packet_id": packet_id,
        "packet": packet,
        "fence_count": fence_count,
        "excluded_fields": ["text", "thought"],
        "revision_contradictions": contradictions,
    }
    if contradictions:
        result["error"] = "inner packet contains incompatible source revision facts"
    return result, exit_code


def _render_receipt(payload):
    return (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _read_receipt_source(source, stdin=None):
    if source == "-":
        stream = stdin or sys.stdin.buffer
        raw = stream.read(RECEIPT_MAX_SOURCE_BYTES + 1)
        if len(raw) > RECEIPT_MAX_SOURCE_BYTES:
            return None, _receipt_error(
                RECEIPT_EXIT_INVALID_ENVELOPE,
                "source exceeds %d-byte receipt budget" % RECEIPT_MAX_SOURCE_BYTES,
                source=source,
            )
        return raw, None
    try:
        with open(source, "rb") as handle:
            raw = handle.read(RECEIPT_MAX_SOURCE_BYTES + 1)
        if len(raw) > RECEIPT_MAX_SOURCE_BYTES:
            return None, _receipt_error(
                RECEIPT_EXIT_INVALID_ENVELOPE,
                "source exceeds %d-byte receipt budget" % RECEIPT_MAX_SOURCE_BYTES,
                source=source,
            )
        return raw, None
    except FileNotFoundError:
        return None, _receipt_error(
            RECEIPT_EXIT_MISSING_FILE,
            "input file does not exist",
            source=source,
        )
    except OSError as exc:
        return None, _receipt_error(
            RECEIPT_EXIT_FINDER_FAILED,
            "input file could not be read: %s" % exc,
            source=source,
        )


def load_catalog(text):
    """Parse the grok-receipt catalog. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "receipts": []}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "receipts": []}
    receipts = []
    for item in data.get("receipts") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("id") or item.get("name") or "").strip()
        if name:
            receipts.append(
                {
                    "id": name,
                    "status": str(item.get("status") or "CANDIDATE").strip()
                    or "CANDIDATE",
                    "tokens": item.get("tokens"),
                }
            )
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "titan_helper": str(data.get("titan_helper") or "").strip(),
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "envelope_rule": str(data.get("envelope_rule") or "").strip(),
        "architect_rank_1": str(data.get("architect_rank_1") or "").strip(),
        "receipts": receipts,
        "error": "",
    }


def _pixel_has_rivet_heartbeat(text):
    """Generator-backed catalog must name RIVET with a heartbeat row."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    names = []
    for key in ("files", "index"):
        for item in data.get(key) or []:
            names.append(str(item or "").strip())
    if "RIVET.json" not in names:
        return False
    for item in data.get("heartbeats") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("name") or "") != "RIVET.json":
            continue
        freshness = str(item.get("freshness") or "").strip()
        ts = str(item.get("ts") or "").strip()
        valid = item.get("valid")
        return bool(freshness) and bool(ts) and valid is True
    return False


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "h009_present": bool(facts.get("h009_present")),
        "exact_one_fence": bool(facts.get("exact_one_fence")),
        "last_fence_absent": bool(facts.get("last_fence_absent")),
        "rivet_heartbeat_row": bool(facts.get("rivet_heartbeat_row")),
        "gemma_path_current": bool(facts.get("gemma_path_current")),
        "dump_impl_present": bool(facts.get("dump_impl_present")),
        "census_invalid_ref_null": bool(facts.get("census_invalid_ref_null")),
        "churn_missing_dir_null": bool(facts.get("churn_missing_dir_null")),
        "titan_helper_boundary": bool(facts.get("titan_helper_boundary")),
        "architect_rank_1_refused": bool(facts.get("architect_rank_1_refused")),
        "receipts_candidate": bool(facts.get("receipts_candidate")),
        "landed_present": list(facts.get("landed_present") or []),
        "landed_missing": list(facts.get("landed_missing") or []),
        "found_phrases": list(facts.get("found_phrases") or []),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "raw_sha": facts.get("raw_sha"),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "h009_patched": list(facts.get("h009_patched") or []),
    }


def classify(row):
    """Turn a measured leftover census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "exact-one-fence leftover not read. Absence was not stillness. "
                "Talk is not a land."
            ),
            "exit": EXIT_UNMEASURED,
        }
    if row.get("calibration_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". Search-zero testing is instrument failure, not absence proof. "
                "FINDER-FAILED, never 0."
            ),
            "exit": EXIT_UNMEASURED,
        }
    if row.get("raw_sha") is None:
        return {
            "state": "UNMEASURED",
            "note": (
                "raw SHA is null. git rev-parse failed. FINDER-FAILED, never "
                "a guessed hash. Never 0."
            ),
            "exit": EXIT_UNMEASURED,
        }
    misses = list(row.get("misses") or [])
    landed_missing = list(row.get("landed_missing") or [])
    if (
        not row.get("card_present")
        or not row.get("catalog_present")
        or not row.get("h009_present")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog/H-009"])
                + ". HEAVY DAMAGE-CONTROL / exact-one-fence talk is CLAIMED "
                "until the leftover ships. FINDER-FAILED, never 0."
            ),
            "exit": EXIT_NOT_LANDED,
        }
    if landed_missing:
        return {
            "state": "NOT_LANDED",
            "note": (
                "named already-landed leftover(s) missing: "
                + ", ".join(landed_missing)
                + ". Do not remint. FINDER-FAILED, never 0."
            ),
            "exit": EXIT_NOT_LANDED,
        }
    needed = [
        phrase
        for phrase in REQUIRED_PHRASES
        if phrase not in (row.get("found_phrases") or [])
    ]
    deltas = [
        name
        for name, ok in (
            ("exact_one_fence", row.get("exact_one_fence")),
            ("last_fence_absent", row.get("last_fence_absent")),
            ("rivet_heartbeat_row", row.get("rivet_heartbeat_row")),
            ("gemma_path_current", row.get("gemma_path_current")),
            ("dump_impl_present", row.get("dump_impl_present")),
            ("census_invalid_ref_null", row.get("census_invalid_ref_null")),
            ("churn_missing_dir_null", row.get("churn_missing_dir_null")),
            ("titan_helper_boundary", row.get("titan_helper_boundary")),
            ("architect_rank_1_refused", row.get("architect_rank_1_refused")),
            ("receipts_candidate", row.get("receipts_candidate")),
        )
        if not ok
    ]
    if (
        needed
        or deltas
        or not row.get("posting_open")
        or not row.get("no_auth")
        or not row.get("no_gate")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Unreconciled leftovers: "
                + ", ".join(deltas)
                + ". Open door + no auth + no gate required. Talk is CLAIMED. "
                "FINDER-FAILED, never 0."
            ),
            "exit": EXIT_NOT_LANDED,
        }
    if len(row.get("h009_patched") or []) < len(H009_PATCHED):
        return {
            "state": "NOT_LANDED",
            "note": (
                "H-009 patched bugs missing. device_ls_tree_collapse and "
                "device_missing_dir_zero must be PATCH_LANDED. "
                "FINDER-FAILED, never 0."
            ),
            "exit": EXIT_NOT_LANDED,
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "exact-one-fence leftover is on this tree. Last-fence PR 2320 "
            "stays COLLISION. Finder failures are null/UNMEASURED. "
            "A Slack damage-control update is still not the file."
        ),
        "exit": EXIT_INTEGRATED,
    }


def measure_root(root):
    root = os.path.abspath(root)
    misses = []
    blobs = []
    for rel in SEARCH_SPACE:
        text = _read(root, rel)
        if not text:
            misses.append(rel)
        else:
            blobs.append(text)
    hay = "\n".join(blobs).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in hay]
    landed_present = [rel for rel in ALREADY_LANDED if _exists(root, rel)]
    landed_missing = [rel for rel in ALREADY_LANDED if not _exists(root, rel)]
    catalog = load_catalog(_read(root, DEFAULT_CATALOG))
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    calibration_ok = len(calibration_hits) == len(CALIBRATION)
    if not calibration_ok:
        for rel in CALIBRATION:
            if rel not in calibration_hits and rel not in misses:
                misses.append("calibration:" + rel)
    instrument = _read(root, os.path.join("host", "grok_receipt.py"))
    census = _read(root, os.path.join("host", "device_path_census.py"))
    churn = _read(root, os.path.join("host", "device_churn.py"))
    pixel_hb = _read(root, os.path.join("ground", "PIXEL_HEARTBEAT.json"))
    gemma = (
        _read(root, os.path.join("ground", "GEMMA_TOKENIZER_MAP.md"))
        + "\n"
        + _read(root, os.path.join("ground", "GEMMA_INGRESS.md"))
    )
    h009 = _read(root, H009_CARD) + "\n" + _read(root, H009_CATALOG)
    receipts = catalog.get("receipts") or []
    receipt_ids = " ".join(item.get("id") or "" for item in receipts)
    receipts_candidate = all(
        name.lower() in receipt_ids.lower() for name in CANDIDATE_RECEIPTS
    ) and all(
        str(item.get("status") or "").upper() == "CANDIDATE" for item in receipts
    )
    h009_patched = []
    for bug in H009_PATCHED:
        blob = h009.lower()
        if bug.lower() in blob and "patch_landed" in blob:
            h009_patched.append(bug)
    posting_open = (
        catalog.get("posting") == "OPEN"
        and "open door" in hay
        and "unseated" in hay
    )
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "h009_present": _exists(root, H009_CARD) and _exists(root, H009_CATALOG),
        "exact_one_fence": (
            "exact-one-fence" in instrument.lower()
            and "fence_count != 1" in instrument.replace(" ", "")
            or "count != 1" in instrument
        ),
        "last_fence_absent": str(catalog.get("envelope_rule") or "")
        .lower()
        .startswith("exact-one-fence")
        and "last-fence is collision" in hay,
        "rivet_heartbeat_row": _pixel_has_rivet_heartbeat(pixel_hb),
        "gemma_path_current": (
            "infra/host/muhl_dump_litertlm.py" in gemma
            and "python host/muhl_dump_litertlm.py" not in gemma
        ),
        "dump_impl_present": _exists(
            root, os.path.join("infra", "host", "muhl_dump_litertlm.py")
        ),
        "census_invalid_ref_null": (
            "tree_ok" in census
            and "FINDER-FAILED" in census
            and "never []" in census.lower()
        ),
        "churn_missing_dir_null": (
            "FINDER-FAILED" in churn
            and "never 0" in churn.lower()
            and "missing dir" in churn.lower()
        ),
        "titan_helper_boundary": (
            catalog.get("titan_helper") == "BOUNDARY_ONLY"
            and "no titan mutation" in hay
        ),
        "architect_rank_1_refused": catalog.get("architect_rank_1") == "REFUSED",
        "receipts_candidate": receipts_candidate,
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
        "posting_open": posting_open,
        "no_auth": bool(catalog.get("no_auth")) and "no auth" in hay,
        "no_gate": bool(catalog.get("no_gate")) and "no gate" in hay,
        "calibration_ok": calibration_ok,
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "raw_sha": raw_sha(root),
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "h009_patched": h009_patched,
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "calibration_hits": calibration_hits,
                "found_phrases": found,
                "raw_sha": facts["raw_sha"],
                "h009_patched": h009_patched,
                "rivet_heartbeat_row": facts["rivet_heartbeat_row"],
            },
            "z": (
                "misses "
                + json.dumps(misses + landed_missing)
                + " / FINDER-FAILED never 0"
            ),
        }
    )
    return row


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED", empty
    thought = (
        "thinking: ignore this {\"rank\": 1}\n"
        "```json\n{\"scratch\": true}\n```\n"
        "```json\n{\"ok\": true, \"rank\": 2}\n```\n"
    )
    got = normalize_envelope(thought)
    assert got["status"] == "CANDIDATE", got
    assert got["authoritative"] is None, got
    assert got["fence_count"] == 2, got
    assert "FINDER-FAILED" in got["error"], got
    one = normalize_envelope("```json\n{\"ok\": true, \"rank\": 2}\n```\n")
    assert one["authoritative"] == {"ok": True, "rank": 2}, one
    assert one["fence_count"] == 1, one
    no_fence = normalize_envelope("thought only, no fence")
    assert no_fence["authoritative"] is None, no_fence
    assert "FINDER-FAILED" in no_fence["error"], no_fence
    packet = {"packet_id": "synthetic-self-test", "value": 1}
    completed = {
        "text": "result\n```json\n%s\n```\n" % json.dumps(packet),
        "thought": "```json\n{\"packet_id\":\"scratch\"}\n```",
        "sessionId": "synthetic-session",
        "usage": {"total_tokens": 1},
        "modelUsage": {"synthetic-model": {"modelCalls": 1}},
    }
    normalized, code = evaluate_receipt(json.dumps(completed).encode("utf-8"))
    assert code == RECEIPT_EXIT_OK, normalized
    assert normalized["packet"] == packet, normalized
    assert normalized["revision_contradictions"] == [], normalized
    assert "thought" not in normalized, normalized
    assert "text" not in normalized, normalized
    conflicting = dict(completed)
    conflicting["text"] = "```json\n%s\n```\n" % json.dumps(
        {
            "packet_id": "synthetic-conflict",
            "source_head": "1111111",
            "nested": {"source_head": "2222222"},
        }
    )
    contradiction, code = evaluate_receipt(json.dumps(conflicting).encode("utf-8"))
    assert code == RECEIPT_EXIT_REVISION_CONTRADICTION, contradiction
    duplicate = dict(completed)
    duplicate["text"] = (
        "```json\n"
        '{"packet_id":"duplicate","source_head":"1111111",'
        '"source_head":"2222222"}\n'
        "```\n"
    )
    duplicate_error, code = evaluate_receipt(json.dumps(duplicate).encode("utf-8"))
    assert code == RECEIPT_EXIT_DUPLICATE_KEY, duplicate_error
    missing = classify(
        measure_from_rows(
            {
                "card_present": False,
                "catalog_present": False,
                "h009_present": False,
                "misses": ["ground/GROK_RECEIPT.md"],
                "calibration_ok": True,
                "raw_sha": "0" * 40,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    return "ok"


def main(argv=None, stdin=None, stdout=None):
    parser = argparse.ArgumentParser(
        description=(
            "Measure the grok-receipt leftover or normalize one completed "
            "Grok Build envelope"
        )
    )
    parser.add_argument("source", nargs="?", help="completed receipt JSON or -")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate/normalize source (use - or piped stdin if omitted)",
    )
    parser.add_argument("--output", help="also write normalized receipt JSON")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return EXIT_INTEGRATED

    receipt_mode = args.source is not None or args.check or args.output is not None
    if receipt_mode:
        source = args.source or "-"
        raw, read_error = _read_receipt_source(source, stdin=stdin)
        if read_error is not None:
            payload, code = read_error
        else:
            payload, code = evaluate_receipt(raw, source=source)
        rendered = _render_receipt(payload)
        if args.output and code in (
            RECEIPT_EXIT_OK,
            RECEIPT_EXIT_REVISION_CONTRADICTION,
        ):
            try:
                with open(args.output, "wb") as handle:
                    handle.write(rendered)
            except OSError as exc:
                payload, code = _receipt_error(
                    RECEIPT_EXIT_WRITE_FAILURE,
                    "normalized output could not be written: %s" % exc,
                    raw,
                    source,
                )
                rendered = _render_receipt(payload)
        out = stdout or sys.stdout.buffer
        out.write(rendered)
        return code

    row = measure_root(args.root)
    verdict = classify(row)
    payload = {"verdict": verdict, "row": row}
    print(json.dumps(payload, indent=2, sort_keys=True))
    exit_code = verdict.get("exit")
    if exit_code is None:
        return EXIT_FINDER_FAILED
    return int(exit_code)


if __name__ == "__main__":
    sys.exit(main())
