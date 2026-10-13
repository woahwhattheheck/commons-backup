#!/usr/bin/env python3
"""host/subzero_quote.py — sz-paid-validation is a quote draft.

Slack 1787649732.551439 (JOJO INTEGRATED presence receipt):
file presence is PRESENT, structural=31, runtime=0, customer=0,
runtime_proof=false. Commercial consequence: sz-paid-validation
remains a $2,500 quote draft over STRUCTURAL_ONLY evidence — not
runtime, demand, or cash proof.

Slack 1787651627.535699 (JOJO H-009 BACKEND COMPLETE):
#2322 quote leftover still coerced missing numbers to 0, fused
leftover INTEGRATED with legal lifecycle, skipped source/tree
hashes, and treated skipped substrate actuation as health. #2329 binder
holes already closed on 3c364c9fd. This leftover hardens the
existing quote consumer — no second subsystem.

That Slack body is CLAIMED for the quote leftover. Presence already
landed as rivet-ship-subzero-tech-presence-20260825-01. Receipt
bind leftover already landed as
rivet-ship-subzero-receipt-bind-20260825-01. Do not remint them.

Do not remint SUBZERO_TECH / SUBZERO_GTM / SUBZERO_BUYERS /
SUBZERO_EXPLORER / SUBZERO_PROOF / SUBZERO_RECEIPT / White Box /
payment-ready / human-outcomes. Do not open accounts. Do not
message buyers. Do not store bank, routing, card, tax, or
private-buyer data. Do not smash commons.mno. Do not add a gate.

Leftover INTEGRATED is not DRAFT→NEEDS_BUYER→ACCEPTED→DELIVERED.
Live legal_state stays DRAFT or NEEDS_BUYER. inbound_rel rejects
/ \\ .. . Public inbound is a post id, not a seat. Missing
numeric is UNRESOLVED/FINDER-FAILED, never 0. Titan skip is not
health.

X = Slack commercial-consequence + H-009 + architecture sku +
    presence counts + cash $0 / NOT_LANDED + leftover paths.
Y = those facts named on this tree + closed quote holes.
Z = missing leftover / cash-runtime-demand claim / FINDER-FAILED /
FINDER-UNVERIFIED. Never 0.

  python3 host/subzero_quote.py
  python3 host/subzero_quote.py --root .
  python3 host/subzero_quote.py --self-test
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
DEFAULT_CATALOG = os.path.join("ground", "SUBZERO_QUOTE.json")
DEFAULT_CARD = os.path.join("ground", "SUBZERO_QUOTE.md")
DEFAULT_DOOR = "subzero-quote.html"
DEFAULT_ARCH = os.path.join("revenue", "subzero_gtm", "architecture.json")
SLACK_TS = "1787649732.551439"
H009_TS = "1787651627.535699"
SKU_ID = "sz-paid-validation"
QUOTE_PRICE = 2500
PRESENCE_RECEIPT = "rivet-ship-subzero-tech-presence-20260825-01"
QUOTE_RECEIPT = "rivet-ship-subzero-quote-20260825-01"
FIRST_RECEIPT = "rivet-ship-subzero-receipt-20260825-01"
BIND_RECEIPT = "rivet-ship-subzero-receipt-bind-20260825-01"
SELF_BIND_IDS = (PRESENCE_RECEIPT, QUOTE_RECEIPT, FIRST_RECEIPT, BIND_RECEIPT)
LEGAL_STATES = ("DRAFT", "NEEDS_BUYER", "ACCEPTED", "DELIVERED")
POST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "subzero_quote.py"),
    DEFAULT_DOOR,
    DEFAULT_ARCH,
    os.path.join("ground", "SUBZERO_TECH.md"),
    os.path.join("host", "subzero_tech.py"),
    os.path.join("ground", "SUBZERO_GTM.md"),
    os.path.join("host", "subzero_gtm.py"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
    os.path.join("p", PRESENCE_RECEIPT + ".md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("host", "subzero_tech.py"),
    os.path.join("ground", "SUBZERO_TECH.md"),
    os.path.join("host", "subzero_gtm.py"),
    os.path.join("ground", "SUBZERO_GTM.md"),
    DEFAULT_ARCH,
    os.path.join("host", "subzero_buyers.py"),
    os.path.join("host", "subzero_explorer.py"),
    os.path.join("host", "subzero_proof.py"),
    os.path.join("p", PRESENCE_RECEIPT + ".md"),
)
REQUIRED_PHRASES = (
    "sz-paid-validation",
    "quote draft",
    "1787649732.551439",
    "1787651627.535699",
    "h-009",
    "structural_only",
    "not runtime",
    "not demand",
    "not cash",
    "commercial consequence",
    "unresolved",
    "needs_buyer",
    "inbound_rel",
    "legal_state",
    "self_bind",
    "finder-failed",
    "finder-unverified",
    "never 0",
    "open door",
    "unseated",
    "no auth",
    "no gate",
    "talk is not a land",
    "titan skip is not health",
)
HEX64 = set("0123456789abcdef")
HASHED_SOURCES = (
    DEFAULT_CATALOG,
    DEFAULT_CARD,
    DEFAULT_DOOR,
    os.path.join("host", "subzero_quote.py"),
    os.path.join("test_subzero_quote.py"),
    DEFAULT_ARCH,
)


def safe_rel(rel):
    """Reject Windows escape, drive letters, and .. . Do not strip them."""
    raw = str(rel or "")
    if not raw or raw.startswith("/") or raw.startswith("\\"):
        return ""
    if "\\" in raw:
        return ""
    head = raw.split("/", 1)[0]
    if ":" in head:
        return ""
    parts = [part for part in raw.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        return ""
    return "/".join(parts)


def _posix_parts(rel):
    # Internal constants use os.path.join and therefore contain backslashes
    # on Windows. Normalize them before the same traversal-safe validation.
    text = safe_rel(str(rel or "").replace("\\", "/"))
    return text.split("/") if text else []


def _posix_rel(rel):
    return safe_rel(rel)


def _read(root, rel):
    parts = _posix_parts(rel)
    if not parts:
        return ""
    path = os.path.join(root, *parts)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _read_bytes(root, rel):
    parts = _posix_parts(rel)
    if not parts:
        return b""
    path = os.path.join(root, *parts)
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return b""


def _exists(root, rel):
    parts = _posix_parts(rel)
    if not parts:
        return False
    return os.path.isfile(os.path.join(root, *parts))


def _hex_sha(value, sizes=(64,)):
    text = str(value or "").strip().lower()
    return len(text) in sizes and set(text) <= HEX64


def present_int(data, key):
    """Missing/blank is UNRESOLVED. Bad type is FINDER-FAILED. Never coerce to 0."""
    if not isinstance(data, dict) or key not in data:
        return {"state": "UNRESOLVED", "value": None, "key": key}
    value = data[key]
    if value is None or value == "":
        return {"state": "UNRESOLVED", "value": None, "key": key}
    if isinstance(value, bool):
        return {"state": "FINDER-FAILED", "value": None, "key": key}
    try:
        return {"state": "PRESENT", "value": int(value), "key": key}
    except (TypeError, ValueError):
        return {"state": "FINDER-FAILED", "value": None, "key": key}


def measured_int(facts, key):
    """Accept a present int or an explicit {state,value} field. Missing is UNRESOLVED."""
    facts = facts or {}
    state_key = key + "_state"
    raw = facts.get(key)
    if isinstance(raw, dict) and "state" in raw:
        state = str(raw.get("state") or "").strip().upper()
        if state != "PRESENT":
            return None, state or "UNRESOLVED"
        try:
            return int(raw.get("value")), "PRESENT"
        except (TypeError, ValueError):
            return None, "FINDER-FAILED"
    if state_key in facts:
        state = str(facts.get(state_key) or "").strip().upper()
        if state in {"UNRESOLVED", "FINDER-FAILED"}:
            return None, state
        if state == "PRESENT":
            try:
                return int(raw), "PRESENT"
            except (TypeError, ValueError):
                return None, "FINDER-FAILED"
    if raw is None or raw == "":
        return None, "UNRESOLVED"
    try:
        return int(raw), "PRESENT"
    except (TypeError, ValueError):
        return None, "FINDER-FAILED"


def canonicalize_post_id(inbound_id):
    """One post id. Forbid / \\ . .. and any traversal token."""
    name = str(inbound_id or "").strip()
    if not name:
        return ""
    if "/" in name or "\\" in name:
        return ""
    if name in {".", ".."} or ".." in name:
        return ""
    if not POST_ID_RE.fullmatch(name):
        return ""
    return name


def inbound_rel(inbound_id):
    """Always posix p/{id}.md. Empty when the id is not canonical."""
    name = canonicalize_post_id(inbound_id)
    if not name:
        return ""
    return "p/" + name + ".md"


def public_inbound(inbound_id):
    """Public inbound is a post id. Traversal / self-bind never become buyers."""
    raw = str(inbound_id or "").strip()
    if not raw:
        return {"ok": False, "state": "EMPTY", "id": "", "rel": ""}
    if "/" in raw or "\\" in raw or ".." in raw:
        return {"ok": False, "state": "TRAVERSAL", "id": "", "rel": ""}
    name = canonicalize_post_id(raw)
    if not name:
        return {"ok": False, "state": "INVALID_ID", "id": "", "rel": ""}
    if name in SELF_BIND_IDS:
        return {
            "ok": False,
            "state": "SELF_BIND",
            "id": name,
            "rel": inbound_rel(name),
        }
    return {"ok": True, "state": "PUBLIC", "id": name, "rel": inbound_rel(name)}


def resolved_inbound(root, inbound_id):
    """Prove the resolved path stays exactly under p/."""
    located = public_inbound(inbound_id)
    name = located.get("id") or ""
    rel = located.get("rel") or ""
    if located.get("state") == "TRAVERSAL" or not name or not rel:
        reason = located.get("state") or "INVALID_ID"
        if reason == "EMPTY":
            reason = "INVALID_ID"
        return {"ok": False, "rel": "", "reason": reason, "path": ""}
    root_abs = os.path.abspath(root)
    posts = os.path.abspath(os.path.join(root_abs, "p"))
    resolved = os.path.abspath(os.path.join(root_abs, *rel.split("/")))
    expected = os.path.abspath(os.path.join(posts, name + ".md"))
    try:
        common = os.path.commonpath([posts, resolved])
    except ValueError:
        return {"ok": False, "rel": "", "reason": "TRAVERSAL", "path": ""}
    if common != posts or resolved != expected:
        return {"ok": False, "rel": "", "reason": "TRAVERSAL", "path": ""}
    return {"ok": True, "rel": rel, "reason": located.get("state") or "", "path": resolved}


def git_source(root):
    """Name the catalog source commit/tree. Missing git is FINDER-FAILED."""

    def run(args):
        try:
            out = subprocess.check_output(args, cwd=root, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.CalledProcessError):
            return ""
        return out.decode("ascii", "replace").strip()

    commit = run(["git", "rev-parse", "HEAD"])
    tree = run(["git", "rev-parse", "HEAD^{tree}"])
    return {
        "source_commit": commit if _hex_sha(commit, (40, 64)) else "FINDER-FAILED",
        "source_tree": tree if _hex_sha(tree, (40, 64)) else "FINDER-FAILED",
    }


def sha256_rel(root, rel):
    blob = _read_bytes(root, rel)
    if not blob:
        return "UNRESOLVED"
    return hashlib.sha256(blob).hexdigest()


def catalog_row_hash(indexed):
    """Hash the named sku row facts. Missing identity is UNRESOLVED."""
    sku = str((indexed or {}).get("sku_id") or "").strip()
    if not sku:
        return "UNRESOLVED"
    payload = json.dumps(
        {
            "sku_id": sku,
            "price_usd": (indexed or {}).get("price_usd"),
            "price_usd_state": (indexed or {}).get("price_usd_state"),
            "sku_class": (indexed or {}).get("sku_class"),
            "arch_status": (indexed or {}).get("arch_status"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def request_hash(inbound_id, quote_hash):
    payload = "|".join(
        [
            str(inbound_id or "").strip(),
            str(quote_hash or "").strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_hashes(root, indexed, inbound_id=""):
    src = git_source(root)
    quote_hash = sha256_rel(root, DEFAULT_CATALOG)
    hashes = {
        "source_commit": src["source_commit"],
        "source_tree": src["source_tree"],
        "quote_hash": quote_hash,
        "catalog_row_hash": catalog_row_hash(indexed),
        "card_hash": sha256_rel(root, DEFAULT_CARD),
        "sidecar_hash": sha256_rel(root, DEFAULT_CATALOG),
        "fab_hash": sha256_rel(root, os.path.join("host", "subzero_quote.py")),
        "test_hash": sha256_rel(root, os.path.join("test_subzero_quote.py")),
        "request_hash": request_hash(inbound_id, quote_hash),
        "delivery_hash": "UNRESOLVED",
    }
    for rel in HASHED_SOURCES:
        hashes[_posix_rel(rel)] = sha256_rel(root, rel)
    return hashes


def legal_state_for(hashes, inbound_bound=False):
    """DRAFT → NEEDS_BUYER → ACCEPTED → DELIVERED. No skip. File is not a buyer."""
    delivery = str((hashes or {}).get("delivery_hash") or "").strip()
    if inbound_bound and _hex_sha(delivery):
        return "DELIVERED"
    if inbound_bound:
        return "ACCEPTED"
    quote_hash = str((hashes or {}).get("quote_hash") or "").strip()
    if _hex_sha(quote_hash):
        return "NEEDS_BUYER"
    return "DRAFT"


def _hashes_ok(hashes):
    hashes = hashes or {}
    if not _hex_sha(hashes.get("source_commit"), (40, 64)):
        return False
    if not _hex_sha(hashes.get("source_tree"), (40, 64)):
        return False
    for key in (
        "quote_hash",
        "catalog_row_hash",
        "fab_hash",
        "test_hash",
        "card_hash",
        "sidecar_hash",
        "request_hash",
    ):
        if not _hex_sha(hashes.get(key)):
            return False
    return str(hashes.get("delivery_hash") or "") == "UNRESOLVED"


def load_catalog(text):
    """Parse the quote leftover catalog. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    sku = data.get("sku") if isinstance(data.get("sku"), dict) else {}
    evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
    price = present_int(sku, "price_usd")
    collected = present_int(data, "collected_cash_usd")
    structural_only = present_int(evidence, "structural_only")
    runtime_measured = present_int(evidence, "runtime_measured")
    customer_ready = present_int(evidence, "customer_ready")
    runtime_proof = evidence.get("runtime_proof") if "runtime_proof" in evidence else "UNRESOLVED"
    return {
        "error": "",
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "h009_ts": str(data.get("h009_ts") or "").strip() or H009_TS,
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "sku_id": str(sku.get("id") or "").strip(),
        "price_usd": price["value"],
        "price_usd_state": price["state"],
        "sku_status": str(sku.get("status") or "").strip().upper(),
        "sku_class": str(sku.get("class") or "").strip().upper(),
        "collected_cash_usd": collected["value"],
        "collected_cash_state": collected["state"],
        "cash_state": str(data.get("cash_state") or "").strip().upper(),
        "demand": str(data.get("demand") or "").strip().upper(),
        "runtime_proof": runtime_proof,
        "structural_only": structural_only["value"],
        "structural_only_state": structural_only["state"],
        "runtime_measured": runtime_measured["value"],
        "runtime_measured_state": runtime_measured["state"],
        "customer_ready": customer_ready["value"],
        "customer_ready_state": customer_ready["state"],
        "legal_state": str(data.get("legal_state") or "").strip().upper(),
        "claims_cash": bool(data.get("claims_cash")),
        "claims_runtime": bool(data.get("claims_runtime")),
        "claims_demand": bool(data.get("claims_demand")),
    }


def titan_lock_fields(catalog=None, card=""):
    """Name active Titan lock/health framing on quote surfaces.

    Substrate / Titan work is first-class. Skipped actuation is
    not health. A catalog that publishes titan=NOT_WRITTEN or
    titan --go under hands_off or collision_avoidance is still
    a lock field. Collision avoidance coordinates concurrent
    work; it does not forbid substrate work.
    """
    hits = []
    data = catalog
    if isinstance(catalog, str):
        try:
            parsed = json.loads(catalog or "{}")
        except ValueError:
            parsed = {}
        data = parsed if isinstance(parsed, dict) else {}
    if not isinstance(data, dict):
        data = {}
    if "titan" in data:
        value = str(data.get("titan") or "").strip().upper()
        hits.append("catalog.titan=" + (value or "EMPTY"))
    for key, label in (
        ("hands_off", "catalog.hands_off:"),
        ("collision_avoidance", "catalog.collision_avoidance:"),
    ):
        items = data.get(key) if isinstance(data.get(key), list) else []
        for item in items:
            text = str(item or "").strip().lower()
            if "titan" in text:
                hits.append(label + str(item).strip())
    for line in str(card or "").splitlines():
        line_l = line.lower()
        if "hands off" in line_l and "titan" in line_l:
            hits.append("card:hands-off-titan")
            break
    if "titan: **not_written**" in str(card or "").lower():
        hits.append("card:titan-not-written")
    return hits


def load_arch_sku(text):
    """Read sz-paid-validation from the already-landed GTM architecture."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "architecture is not JSON"}
    if not isinstance(data, dict):
        return {"error": "architecture is not an object"}
    for item in data.get("paths") or []:
        if isinstance(item, dict) and str(item.get("id") or "").strip() == SKU_ID:
            price = present_int(item, "price_usd")
            return {
                "error": "",
                "id": SKU_ID,
                "price_usd": price["value"],
                "price_usd_state": price["state"],
                "status": str(item.get("status") or "").strip().upper(),
                "kind": str(item.get("kind") or "").strip(),
            }
    return {"error": SKU_ID + " path FINDER-FAILED"}


def classify_quote(row):
    """Name one SKU. Presence / GTM bytes are not cash, runtime, or demand."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "sz-paid-validation quote not read. Absence was not stillness. "
                "FINDER-FAILED, never 0."
            ),
        }
    if str(row.get("finder") or "").strip().lower() in {"failed", "unknown", "error"}:
        return {
            "state": "FINDER-FAILED",
            "note": (
                "finder/tool call failed on "
                + str(row.get("sku_id") or SKU_ID)
                + ". UNKNOWN, never 0."
            ),
        }
    sku_id = str(row.get("sku_id") or "").strip()
    if sku_id != SKU_ID:
        return {
            "state": "NOT_LANDED",
            "note": (
                "sku is "
                + (sku_id or "missing")
                + ", not "
                + SKU_ID
                + ". Commercial consequence stays unnamed. FINDER-FAILED, never 0."
            ),
        }
    cash_value, cash_state = measured_int(row, "collected_cash_usd")
    if bool(row.get("claims_cash")):
        return {
            "state": "NOT_LANDED",
            "note": (
                SKU_ID
                + " is not cash proof. Collected cash stays $0 / NOT_LANDED. "
                "A quote draft is not a deposit. FINDER-FAILED, never 0."
            ),
        }
    if cash_state in {"UNRESOLVED", "FINDER-FAILED"}:
        return {
            "state": "FINDER-FAILED",
            "note": (
                "collected_cash_usd "
                + cash_state
                + ". Missing numeric is not measured $0. FINDER-FAILED, never 0."
            ),
        }
    if cash_state == "PRESENT" and cash_value not in (None, 0):
        return {
            "state": "NOT_LANDED",
            "note": (
                SKU_ID
                + " is not cash proof. Collected cash stays $0 / NOT_LANDED. "
                "A quote draft is not a deposit. FINDER-FAILED, never 0."
            ),
        }
    if bool(row.get("claims_runtime")) or row.get("runtime_proof") is True:
        return {
            "state": "NOT_LANDED",
            "note": (
                SKU_ID
                + " is not runtime proof. Titan presence is PRESENT and "
                "runtime_proof is false. FINDER-FAILED, never 0."
            ),
        }
    if bool(row.get("claims_demand")) or str(row.get("demand") or "").strip().upper() not in {
        "",
        "UNKNOWN",
    }:
        return {
            "state": "NOT_LANDED",
            "note": (
                SKU_ID
                + " is not demand proof. Demand stays UNKNOWN. "
                "FINDER-FAILED, never 0."
            ),
        }
    price, price_state = measured_int(row, "price_usd")
    if price_state != "PRESENT":
        return {
            "state": "FINDER-FAILED",
            "note": (
                "price_usd "
                + price_state
                + ". Missing numeric is not measured $0. FINDER-FAILED, never 0."
            ),
        }
    if price != QUOTE_PRICE:
        return {
            "state": "NOT_LANDED",
            "note": (
                SKU_ID
                + " price is "
                + str(price)
                + ", not "
                + str(QUOTE_PRICE)
                + ". Quote draft stays unbound. FINDER-FAILED, never 0."
            ),
        }
    if str(row.get("sku_class") or "").strip().upper() != "QUOTE_DRAFT":
        return {
            "state": "NOT_LANDED",
            "note": (
                SKU_ID
                + " must stay QUOTE_DRAFT over STRUCTURAL_ONLY evidence. "
                "CANDIDATE in GTM is not cash. FINDER-FAILED, never 0."
            ),
        }
    structural_only, structural_state = measured_int(row, "structural_only")
    if structural_state != "PRESENT":
        return {
            "state": "FINDER-FAILED",
            "note": (
                "structural_only "
                + structural_state
                + ". Missing numeric is not measured 0. FINDER-FAILED, never 0."
            ),
        }
    if structural_only != 31:
        return {
            "state": "NOT_LANDED",
            "note": (
                "presence leftover named structural=31. This quote leftover "
                "must keep that count. FINDER-FAILED, never 0."
            ),
        }
    runtime_measured, runtime_state = measured_int(row, "runtime_measured")
    customer_ready, customer_state = measured_int(row, "customer_ready")
    if runtime_state != "PRESENT" or customer_state != "PRESENT":
        return {
            "state": "FINDER-FAILED",
            "note": (
                "runtime/customer numeric "
                + runtime_state
                + "/"
                + customer_state
                + ". Missing numeric is not measured 0. FINDER-FAILED, never 0."
            ),
        }
    if runtime_measured != 0 or customer_ready != 0:
        return {
            "state": "NOT_LANDED",
            "note": (
                "runtime/customer counts must stay 0 until a distinct "
                "cross-process or buyer receipt lands. Never 0 as a silent "
                "finder. FINDER-FAILED, never 0."
            ),
        }
    return {
        "state": "QUOTE_DRAFT",
        "note": (
            SKU_ID
            + " is a $"
            + str(QUOTE_PRICE)
            + " quote draft over STRUCTURAL_ONLY evidence. "
            "Not runtime, not demand, not cash proof."
        ),
    }


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    price, price_state = measured_int(facts, "price_usd")
    arch_price, arch_price_state = measured_int(facts, "arch_price_usd")
    collected_cash, collected_cash_state = measured_int(facts, "collected_cash_usd")
    structural_only, structural_only_state = measured_int(facts, "structural_only")
    runtime_measured, runtime_measured_state = measured_int(facts, "runtime_measured")
    customer_ready, customer_ready_state = measured_int(facts, "customer_ready")
    runtime_proof = facts.get("runtime_proof")
    if runtime_proof not in {True, False, "UNRESOLVED"}:
        runtime_proof = bool(runtime_proof)
    legal = str(facts.get("legal_state") or "NEEDS_BUYER").strip().upper()
    if legal not in LEGAL_STATES:
        legal = "NEEDS_BUYER"
    holes_closed = (
        True if "holes_closed" not in facts else bool(facts.get("holes_closed"))
    )
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "door_present": bool(facts.get("door_present")),
        "arch_present": bool(facts.get("arch_present")),
        "landed_present": list(facts.get("landed_present") or []),
        "landed_missing": list(facts.get("landed_missing") or []),
        "found_phrases": list(facts.get("found_phrases") or []),
        "sku_id": str(facts.get("sku_id") or ""),
        "price_usd": price,
        "price_usd_state": price_state,
        "sku_status": str(facts.get("sku_status") or ""),
        "sku_class": str(facts.get("sku_class") or ""),
        "arch_price_usd": arch_price,
        "arch_price_usd_state": arch_price_state,
        "arch_status": str(facts.get("arch_status") or ""),
        "collected_cash_usd": collected_cash,
        "collected_cash_state": collected_cash_state,
        "cash_state": str(facts.get("cash_state") or ""),
        "demand": str(facts.get("demand") or ""),
        "runtime_proof": runtime_proof,
        "structural_only": structural_only,
        "structural_only_state": structural_only_state,
        "runtime_measured": runtime_measured,
        "runtime_measured_state": runtime_measured_state,
        "customer_ready": customer_ready,
        "customer_ready_state": customer_ready_state,
        "claims_cash": bool(facts.get("claims_cash")),
        "claims_runtime": bool(facts.get("claims_runtime")),
        "claims_demand": bool(facts.get("claims_demand")),
        "quote_state": str(facts.get("quote_state") or ""),
        "legal_state": legal,
        "inbound_state": str(facts.get("inbound_state") or "EMPTY").strip().upper(),
        "holes_closed": holes_closed,
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan_lock_fields": list(facts.get("titan_lock_fields") or []),
        "hashes": dict(facts.get("hashes") or {}),
    }


def classify(row):
    """Turn a measured quote census into a leftover desk state.

    Leftover INTEGRATED is not legal ACCEPTED/DELIVERED. A file on
    the tree is not a buyer. Titan skip is not health.
    """
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "SUBZERO quote leftover not read. Absence was not stillness. "
                "A Slack commercial consequence is not the file. "
                "not stillness. FINDER-FAILED, never 0."
            ),
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
        }
    misses = list(row.get("misses") or [])
    landed_missing = list(row.get("landed_missing") or [])
    if (
        not row.get("card_present")
        or not row.get("catalog_present")
        or not row.get("door_present")
        or not row.get("arch_present")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog/door/arch"])
                + ". JOJO commercial-consequence / H-009 / sz-paid-validation / "
                "quote-draft talk is CLAIMED until the leftover ships. "
                "FINDER-FAILED, never 0."
            ),
        }
    if landed_missing:
        return {
            "state": "NOT_LANDED",
            "note": (
                "named already-landed leftover(s) missing: "
                + ", ".join(landed_missing)
                + ". Census is incomplete. FINDER-FAILED, never 0."
            ),
        }
    legal = str(row.get("legal_state") or "").strip().upper()
    if legal and legal not in {"DRAFT", "NEEDS_BUYER"}:
        return {
            "state": "NOT_LANDED",
            "note": (
                "Live legal_state must stay DRAFT or NEEDS_BUYER. "
                "Leftover INTEGRATED is not ACCEPTED. FINDER-FAILED, never 0."
            ),
        }
    inbound_state = str(row.get("inbound_state") or "EMPTY").strip().upper()
    if inbound_state not in {"", "EMPTY", "TRAVERSAL", "SELF_BIND", "INVALID_ID"}:
        return {
            "state": "NOT_LANDED",
            "note": (
                "Quote leftover has no public buyer inbound. "
                "inbound_state stays EMPTY. FINDER-FAILED, never 0."
            ),
        }
    if row.get("holes_closed") is False:
        return {
            "state": "NOT_LANDED",
            "note": (
                "quote leftover holes still open. "
                "FINDER-FAILED, never 0."
            ),
        }
    locks = list(row.get("titan_lock_fields") or [])
    if locks:
        return {
            "state": "NOT_LANDED",
            "note": (
                "quote surfaces still publish titan lock/health: "
                + ", ".join(locks)
                + ". Titan skip is not health. FINDER-FAILED, never 0."
            ),
        }
    quote = classify_quote(row)
    if quote["state"] != "QUOTE_DRAFT":
        return {
            "state": "NOT_LANDED" if quote["state"] != "UNMEASURED" else "UNMEASURED",
            "note": quote["note"],
        }
    needed = [
        phrase
        for phrase in REQUIRED_PHRASES
        if phrase not in (row.get("found_phrases") or [])
    ]
    if needed or not row.get("posting_open") or not row.get("no_auth") or not row.get("no_gate"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Open door + no auth + no gate required. Talk is CLAIMED. "
                "FINDER-FAILED, never 0."
            ),
        }
    hashes = row.get("hashes") or {}
    missing_hashes = []
    if hashes:
        for key in ("source_commit", "source_tree"):
            if not _hex_sha(hashes.get(key), (40, 64)):
                missing_hashes.append(key)
        for key in (
            "quote_hash",
            "catalog_row_hash",
            "fab_hash",
            "test_hash",
            "card_hash",
            "sidecar_hash",
            "request_hash",
        ):
            if not _hex_sha(hashes.get(key)):
                missing_hashes.append(key)
        if str(hashes.get("delivery_hash") or "") != "UNRESOLVED":
            missing_hashes.append("delivery_hash")
    if missing_hashes:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing quote hashes: "
                + ", ".join(missing_hashes)
                + ". FINDER-FAILED, never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "SUBZERO quote leftover is on this tree. "
            + SKU_ID
            + " stays a $"
            + str(QUOTE_PRICE)
            + " QUOTE_DRAFT over STRUCTURAL_ONLY. "
            "H-009 quote holes are closed. Live legal_state stays "
            + (legal or "NEEDS_BUYER")
            + ". Not runtime, not demand, not cash. "
            "A Slack commercial consequence is still not the file."
        ),
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
    catalog_text = _read(root, DEFAULT_CATALOG)
    card_text = _read(root, DEFAULT_CARD)
    catalog = load_catalog(catalog_text)
    arch = load_arch_sku(_read(root, DEFAULT_ARCH))
    locks = titan_lock_fields(catalog_text, card_text)
    indexed = {
        "sku_id": catalog.get("sku_id") or "",
        "price_usd": catalog.get("price_usd"),
        "price_usd_state": catalog.get("price_usd_state") or "UNRESOLVED",
        "sku_class": catalog.get("sku_class") or "",
        "arch_status": arch.get("status") or "",
    }
    hashes = source_hashes(root, indexed)
    legal = legal_state_for(hashes, inbound_bound=False)
    escaped = public_inbound("..\\ground\\EXECUTE")
    posix_escape = public_inbound("../ground/EXECUTE")
    self_bind = public_inbound(QUOTE_RECEIPT)
    located = resolved_inbound(root, "..\\ground\\EXECUTE")
    holes_closed = (
        inbound_rel("..\\ground\\EXECUTE") == ""
        and inbound_rel("../ground/EXECUTE") == ""
        and escaped["state"] == "TRAVERSAL"
        and posix_escape["state"] == "TRAVERSAL"
        and self_bind["state"] == "SELF_BIND"
        and public_inbound("")["state"] == "EMPTY"
        and located.get("ok") is False
        and located.get("reason") == "TRAVERSAL"
        and present_int({}, "price_usd")["state"] == "UNRESOLVED"
        and present_int({"price_usd": None}, "price_usd")["state"] == "UNRESOLVED"
        and present_int({"price_usd": True}, "price_usd")["state"] == "FINDER-FAILED"
        and catalog.get("price_usd_state") == "PRESENT"
        and catalog.get("price_usd") == QUOTE_PRICE
        and catalog.get("collected_cash_state") == "PRESENT"
        and catalog.get("collected_cash_usd") == 0
        and legal in {"DRAFT", "NEEDS_BUYER"}
        and _hashes_ok(hashes)
    )
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    calibration_ok = len(calibration_hits) == len(CALIBRATION)
    if not calibration_ok:
        for rel in CALIBRATION:
            if rel not in calibration_hits and rel not in misses:
                misses.append("calibration:" + rel)
    posting_open = (
        catalog.get("posting") == "OPEN"
        and "open door" in hay
        and "unseated" in hay
    )
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "door_present": _exists(root, DEFAULT_DOOR),
        "arch_present": _exists(root, DEFAULT_ARCH) and not arch.get("error"),
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
        "sku_id": catalog.get("sku_id") or "",
        "price_usd": catalog.get("price_usd"),
        "price_usd_state": catalog.get("price_usd_state") or "UNRESOLVED",
        "sku_status": catalog.get("sku_status") or "",
        "sku_class": catalog.get("sku_class") or "",
        "arch_price_usd": arch.get("price_usd"),
        "arch_price_usd_state": arch.get("price_usd_state") or "UNRESOLVED",
        "arch_status": arch.get("status") or "",
        "collected_cash_usd": catalog.get("collected_cash_usd"),
        "collected_cash_state": catalog.get("collected_cash_state") or "UNRESOLVED",
        "cash_state": catalog.get("cash_state") or "",
        "demand": catalog.get("demand") or "",
        "runtime_proof": catalog.get("runtime_proof"),
        "structural_only": catalog.get("structural_only"),
        "structural_only_state": catalog.get("structural_only_state") or "UNRESOLVED",
        "runtime_measured": catalog.get("runtime_measured"),
        "runtime_measured_state": catalog.get("runtime_measured_state") or "UNRESOLVED",
        "customer_ready": catalog.get("customer_ready"),
        "customer_ready_state": catalog.get("customer_ready_state") or "UNRESOLVED",
        "claims_cash": bool(catalog.get("claims_cash")),
        "claims_runtime": bool(catalog.get("claims_runtime")),
        "claims_demand": bool(catalog.get("claims_demand")),
        "legal_state": legal,
        "inbound_state": "EMPTY",
        "holes_closed": holes_closed,
        "posting_open": posting_open,
        "no_auth": bool(catalog.get("no_auth")) and "no auth" in hay,
        "no_gate": bool(catalog.get("no_gate")) and "no gate" in hay,
        "calibration_ok": calibration_ok,
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan_lock_fields": locks,
        "hashes": hashes,
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "h009_ts": catalog.get("h009_ts") or H009_TS,
    }
    quote = classify_quote(
        {
            "measured": True,
            "sku_id": facts["sku_id"],
            "price_usd": facts["price_usd"],
            "price_usd_state": facts["price_usd_state"],
            "sku_class": facts["sku_class"],
            "collected_cash_usd": facts["collected_cash_usd"],
            "collected_cash_state": facts["collected_cash_state"],
            "demand": facts["demand"],
            "runtime_proof": facts["runtime_proof"],
            "structural_only": facts["structural_only"],
            "structural_only_state": facts["structural_only_state"],
            "runtime_measured": facts["runtime_measured"],
            "runtime_measured_state": facts["runtime_measured_state"],
            "customer_ready": facts["customer_ready"],
            "customer_ready_state": facts["customer_ready_state"],
            "claims_cash": facts["claims_cash"],
            "claims_runtime": facts["claims_runtime"],
            "claims_demand": facts["claims_demand"],
        }
    )
    facts["quote_state"] = quote["state"]
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "h009_ts": facts["h009_ts"],
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "calibration_hits": calibration_hits,
                "found_phrases": found,
                "landed_present": landed_present,
                "sku_id": facts["sku_id"],
                "price_usd": facts["price_usd"],
                "price_usd_state": facts["price_usd_state"],
                "sku_class": facts["sku_class"],
                "arch_status": facts["arch_status"],
                "arch_price_usd": facts["arch_price_usd"],
                "quote_state": quote["state"],
                "legal_state": legal,
                "holes_closed": holes_closed,
                "presence_receipt": PRESENCE_RECEIPT,
                "hashes": {
                    "source_commit": hashes.get("source_commit"),
                    "source_tree": hashes.get("source_tree"),
                    "quote_hash": hashes.get("quote_hash"),
                    "catalog_row_hash": hashes.get("catalog_row_hash"),
                    "delivery_hash": hashes.get("delivery_hash"),
                },
            },
            "z": (
                "misses "
                + json.dumps(misses + landed_missing)
                + " / FINDER-FAILED never 0 / quote "
                + quote["state"]
                + " / legal "
                + legal
            ),
        }
    )
    return row


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED", empty
    missing = classify(
        measure_from_rows(
            {
                "card_present": False,
                "catalog_present": False,
                "misses": ["ground/SUBZERO_QUOTE.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    cash = classify_quote(
        {
            "measured": True,
            "sku_id": SKU_ID,
            "price_usd": QUOTE_PRICE,
            "sku_class": "QUOTE_DRAFT",
            "claims_cash": True,
            "structural_only": 31,
            "runtime_measured": 0,
            "customer_ready": 0,
            "collected_cash_usd": 0,
        }
    )
    assert cash["state"] == "NOT_LANDED", cash
    assert "not cash" in cash["note"].lower() or "not cash proof" in cash["note"].lower(), cash
    runtime = classify_quote(
        {
            "measured": True,
            "sku_id": SKU_ID,
            "price_usd": QUOTE_PRICE,
            "sku_class": "QUOTE_DRAFT",
            "runtime_proof": True,
            "structural_only": 31,
            "runtime_measured": 0,
            "customer_ready": 0,
            "collected_cash_usd": 0,
        }
    )
    assert runtime["state"] == "NOT_LANDED", runtime
    draft = classify_quote(
        {
            "measured": True,
            "sku_id": SKU_ID,
            "price_usd": QUOTE_PRICE,
            "sku_class": "QUOTE_DRAFT",
            "demand": "UNKNOWN",
            "structural_only": 31,
            "runtime_measured": 0,
            "customer_ready": 0,
            "runtime_proof": False,
            "collected_cash_usd": 0,
        }
    )
    assert draft["state"] == "QUOTE_DRAFT", draft
    missing_price = classify_quote(
        {
            "measured": True,
            "sku_id": SKU_ID,
            "sku_class": "QUOTE_DRAFT",
            "demand": "UNKNOWN",
            "structural_only": 31,
            "runtime_measured": 0,
            "customer_ready": 0,
            "collected_cash_usd": 0,
        }
    )
    assert missing_price["state"] == "FINDER-FAILED", missing_price
    assert inbound_rel("..\\ground\\EXECUTE") == ""
    assert inbound_rel("../ground/EXECUTE") == ""
    assert public_inbound("..\\ground\\EXECUTE")["state"] == "TRAVERSAL"
    assert public_inbound(QUOTE_RECEIPT)["state"] == "SELF_BIND"
    assert legal_state_for({"quote_hash": "a" * 64}, inbound_bound=False) == "NEEDS_BUYER"
    assert legal_state_for({}, inbound_bound=False) == "DRAFT"
    fused = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "door_present": True,
                "arch_present": True,
                "sku_id": SKU_ID,
                "price_usd": QUOTE_PRICE,
                "sku_class": "QUOTE_DRAFT",
                "collected_cash_usd": 0,
                "structural_only": 31,
                "runtime_measured": 0,
                "customer_ready": 0,
                "demand": "UNKNOWN",
                "found_phrases": list(REQUIRED_PHRASES),
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
                "legal_state": "ACCEPTED",
            }
        )
    )
    assert fused["state"] == "NOT_LANDED", fused
    assert titan_lock_fields({"titan": "NOT_WRITTEN"}, "") == ["catalog.titan=NOT_WRITTEN"]
    assert "catalog.hands_off:titan --go" in titan_lock_fields(
        {"hands_off": ["titan --go"]}, ""
    )
    assert "catalog.collision_avoidance:titan --go" in titan_lock_fields(
        {"collision_avoidance": ["titan --go"]}, ""
    )
    assert titan_lock_fields({}, "Hands off SPECTER, titan `--go`.") == [
        "card:hands-off-titan"
    ]
    assert titan_lock_fields({}, "Titan skip is not health.") == []
    locked = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "door_present": True,
                "arch_present": True,
                "sku_id": SKU_ID,
                "price_usd": QUOTE_PRICE,
                "sku_class": "QUOTE_DRAFT",
                "collected_cash_usd": 0,
                "structural_only": 31,
                "runtime_measured": 0,
                "customer_ready": 0,
                "demand": "UNKNOWN",
                "found_phrases": list(REQUIRED_PHRASES),
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
                "legal_state": "NEEDS_BUYER",
                "titan_lock_fields": ["catalog.titan=NOT_WRITTEN"],
            }
        )
    )
    assert locked["state"] == "NOT_LANDED", locked
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure SUBZERO quote leftover")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    row = measure_root(args.root)
    verdict = classify(row)
    payload = {"verdict": verdict, "row": row}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if verdict["state"] == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
