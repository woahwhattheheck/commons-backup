#!/usr/bin/env python3
"""host/subzero_receipt.py — quote-draft bind, not buyer acceptance.

Slack 1787650230.035359 (JOJO BACKEND CELL H-008) plus Slack
1787651030.360809 (JOJO SECOND PASS on squash 5d796079) plus
Slack 1787651639.893089 (JOJO semantic-hardening follow-up):
source-index sz-paid-validation / P01 $2500 into a bind that
cannot mint BUYER_BOUND from any existing file, self-bind,
Windows path escape, missing numerics, or caller PASS.

Talk that restates H-008 / #2329 is CLAIMED until this leftover
measures the source index, the bind path, CANDIDATE/INCOMPLETE
live binder, $0 / NOT_LANDED cash, and no remint.

Do not remint SUBZERO_QUOTE / SUBZERO_GTM / SUBZERO_BUYERS /
SUBZERO_EXPLORER / SUBZERO_PROOF / White Box / payment-ready /
human-outcomes / grok-receipt / PR 2320 /
rivet-ship-subzero-receipt-20260825-01. Do not open accounts.
Do not message buyers. Do not store bank, routing, card, tax,
or private-buyer data. Do not smash commons.mno. Do not add a
gate.

A semantically relevant public inbound is a binding key, not a
seat. Any existing file or self receipt is IRRELEVANT_INBOUND /
SELF_BIND, not inbound_ok. File existence is not buyer
acceptance. Bound is still STRUCTURAL_ONLY. Bound is not cash,
not runtime, not demand proof. Live binder stays CANDIDATE /
INCOMPLETE / NEEDS_BUYER. Missing numeric never coerce.

X = Slack H-008 + second pass + quote leftover + GTM sku + P01
    + schema + leftover paths.
Y = those facts named on this tree + closed bind holes.
Z = missing leftover / invented buyer / cash-runtime-demand
    claim / FINDER-FAILED / FINDER-UNVERIFIED. Never 0.

  python3 host/subzero_receipt.py
  python3 host/subzero_receipt.py --root .
  python3 host/subzero_receipt.py --self-test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "SUBZERO_RECEIPT.json")
DEFAULT_CARD = os.path.join("ground", "SUBZERO_RECEIPT.md")
DEFAULT_DOOR = "subzero-receipt.html"
DEFAULT_QUOTE = os.path.join("ground", "SUBZERO_QUOTE.json")
DEFAULT_ARCH = os.path.join("revenue", "subzero_gtm", "architecture.json")
DEFAULT_BUYERS = os.path.join("revenue", "subzero_buyers", "pack.json")
DEFAULT_SCHEMA = os.path.join(
    "revenue", "subzero_buyers", "validation_receipt.schema.json"
)
SLACK_TS = "1787650230.035359"
SECOND_PASS_TS = "1787651030.360809"
HARDENING_TS = "1787651639.893089"
CELL = "H-008"
SKU_ID = "sz-paid-validation"
P01_ID = "P01_catalog_receipt"
QUOTE_PRICE = 2500
QUOTE_RECEIPT = "rivet-ship-subzero-quote-20260825-01"
HUMAN_RECEIPT = "rivet-ship-human-outcomes-20260825-01"
FIRST_RECEIPT = "rivet-ship-subzero-receipt-20260825-01"
GRBN_REL = "excerpts/20260823/muhl_grbn.mno"
LVIN_REL = "excerpts/20260823/muhl_lvin.mno"
GRBN_SHA = "09214540b3f3117ab93a4c509017a5e7b9c5f12d86545069af4ffcdae99c6632"
SELF_BIND_IDS = (QUOTE_RECEIPT, HUMAN_RECEIPT, FIRST_RECEIPT)
LEGAL_STATES = ("DRAFT", "NEEDS_BUYER", "ACCEPTED", "DELIVERED")
POST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
ACCEPT_RE = re.compile(
    r"\b(buyer accept|accepted quote|i accept|acceptance of|ACCEPT:)\b",
    re.I,
)
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "subzero_receipt.py"),
    DEFAULT_DOOR,
    DEFAULT_QUOTE,
    DEFAULT_ARCH,
    DEFAULT_BUYERS,
    DEFAULT_SCHEMA,
    os.path.join("host", "subzero_quote.py"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
    os.path.join("p", QUOTE_RECEIPT + ".md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("host", "subzero_quote.py"),
    os.path.join("ground", "SUBZERO_QUOTE.md"),
    os.path.join("ground", "SUBZERO_QUOTE.json"),
    DEFAULT_ARCH,
    DEFAULT_BUYERS,
    DEFAULT_SCHEMA,
    os.path.join("host", "subzero_explorer.py"),
    os.path.join("host", "human_outcomes.py"),
    os.path.join("p", QUOTE_RECEIPT + ".md"),
)
REQUIRED_PHRASES = (
    "sz-paid-validation",
    "p01_catalog_receipt",
    "quote-draft",
    "buyer-bound",
    "validation receipt",
    "1787650230.035359",
    "1787651030.360809",
    "1787651639.893089",
    "h-008",
    "irrelevant_inbound",
    "semantically relevant",
    "public inbound",
    "structural_only",
    "not runtime",
    "not demand",
    "not cash",
    "unbound",
    "candidate",
    "incomplete",
    "needs_buyer",
    "unresolved",
    "self_bind",
    "inbound_rel",
    "finder-failed",
    "finder-unverified",
    "never 0",
    "open door",
    "unseated",
    "no auth",
    "no gate",
    "talk is not a land",
)
HEX64 = set("0123456789abcdef")
HASHED_SOURCES = (
    DEFAULT_QUOTE,
    DEFAULT_CATALOG,
    DEFAULT_CARD,
    DEFAULT_DOOR,
    os.path.join("host", "subzero_receipt.py"),
    os.path.join("test_subzero_receipt.py"),
    DEFAULT_ARCH,
    DEFAULT_BUYERS,
    DEFAULT_SCHEMA,
)


def _read(root, rel):
    path = os.path.join(root, *_posix_parts(rel))
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _read_bytes(root, rel):
    path = os.path.join(root, *_posix_parts(rel))
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return b""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, *_posix_parts(rel)))


def safe_rel(rel):
    """Reject Windows escape, drive letters, and .. . Keep posix only."""
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


def _hex_sha(value, sizes=(64,)):
    text = str(value or "").strip().lower()
    return len(text) in sizes and set(text) <= HEX64


def _posix_rel(rel):
    return str(rel or "").replace("\\", "/")


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


def parse_excerpt(blob):
    """Read magic + LE header. Short or empty is FINDER-FAILED."""
    if len(blob) < 28:
        return {"ok": False, "reason": "header too short", "sha256": ""}
    magic = blob[:8].decode("ascii", "replace")
    n_gate, n_wires, n_in, n_out, depth = struct.unpack_from("<IIIII", blob, 8)
    return {
        "ok": True,
        "reason": "",
        "magic": magic,
        "n_gate": n_gate,
        "n_wires": n_wires,
        "n_in": n_in,
        "n_out": n_out,
        "depth": depth,
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
    }


def load_json(text, label):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": label + " is not JSON"}
    if not isinstance(data, dict):
        return {"error": label + " is not an object"}
    return data


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
    """Hash the named sku / P01 row facts. Missing identity is UNRESOLVED."""
    sku = str((indexed or {}).get("sku_id") or "").strip()
    p01 = str((indexed or {}).get("p01_id") or "").strip()
    if not sku or not p01:
        return "UNRESOLVED"
    payload = json.dumps(
        {
            "sku_id": sku,
            "p01_id": p01,
            "quote_price": (indexed or {}).get("quote_price"),
            "quote_price_state": (indexed or {}).get("quote_price_state"),
            "quote_class": (indexed or {}).get("quote_class"),
            "arch_id": (indexed or {}).get("arch_id"),
            "arch_status": (indexed or {}).get("arch_status"),
            "p01_from": (indexed or {}).get("p01_from"),
            "p01_to": (indexed or {}).get("p01_to"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def request_hash(inbound_id, excerpt_rel, quote_hash):
    payload = "|".join(
        [
            str(inbound_id or "").strip(),
            _posix_rel(excerpt_rel),
            str(quote_hash or "").strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_hashes(root, indexed, inbound_id="", excerpt_rel=""):
    src = git_source(root)
    quote_hash = sha256_rel(root, DEFAULT_QUOTE)
    hashes = {
        "source_commit": src["source_commit"],
        "source_tree": src["source_tree"],
        "quote_hash": quote_hash,
        "catalog_row_hash": catalog_row_hash(indexed),
        "card_hash": sha256_rel(root, DEFAULT_CARD),
        "sidecar_hash": sha256_rel(root, DEFAULT_CATALOG),
        "fab_hash": sha256_rel(root, os.path.join("host", "subzero_receipt.py")),
        "test_hash": sha256_rel(root, os.path.join("test_subzero_receipt.py")),
        "request_hash": request_hash(inbound_id, excerpt_rel, quote_hash),
        "delivery_hash": "UNRESOLVED",
    }
    for rel in HASHED_SOURCES:
        hashes[_posix_rel(rel)] = sha256_rel(root, rel)
    return hashes


def source_index(root):
    """Read already-landed quote / GTM / P01 / schema. Do not remint."""
    quote = load_json(_read(root, DEFAULT_QUOTE), "quote")
    arch = load_json(_read(root, DEFAULT_ARCH), "architecture")
    buyers = load_json(_read(root, DEFAULT_BUYERS), "buyers")
    schema = load_json(_read(root, DEFAULT_SCHEMA), "schema")
    sku = quote.get("sku") if isinstance(quote.get("sku"), dict) else {}
    evidence = quote.get("evidence") if isinstance(quote.get("evidence"), dict) else {}
    arch_sku = {}
    for item in arch.get("paths") or []:
        if isinstance(item, dict) and str(item.get("id") or "").strip() == SKU_ID:
            arch_sku = item
            break
    p01 = {}
    for item in buyers.get("paths") or []:
        if isinstance(item, dict) and str(item.get("id") or "").strip() == P01_ID:
            p01 = item
            break
    defs = schema.get("$defs") if isinstance(schema.get("$defs"), dict) else {}
    quote_price = present_int(sku, "price_usd")
    arch_price = present_int(arch_sku, "price_usd")
    p01_from = present_int(p01, "price_usd_from")
    p01_to = present_int(p01, "price_usd_to")
    structural_only = present_int(evidence, "structural_only")
    runtime_measured = present_int(evidence, "runtime_measured")
    customer_ready = present_int(evidence, "customer_ready")
    collected_cash = present_int(quote, "collected_cash_usd")
    return {
        "quote_error": str(quote.get("error") or ""),
        "arch_error": str(arch.get("error") or ""),
        "buyers_error": str(buyers.get("error") or ""),
        "schema_error": str(schema.get("error") or ""),
        "sku_id": str(sku.get("id") or "").strip(),
        "quote_class": str(sku.get("class") or "").strip().upper(),
        "quote_price": quote_price["value"],
        "quote_price_state": quote_price["state"],
        "quote_status": str(sku.get("status") or "").strip().upper(),
        "arch_id": str(arch_sku.get("id") or "").strip(),
        "arch_price": arch_price["value"],
        "arch_price_state": arch_price["state"],
        "arch_status": str(arch_sku.get("status") or "").strip().upper(),
        "arch_implements": str(arch_sku.get("implements") or "").strip(),
        "p01_id": str(p01.get("id") or "").strip(),
        "p01_from": p01_from["value"],
        "p01_from_state": p01_from["state"],
        "p01_to": p01_to["value"],
        "p01_to_state": p01_to["state"],
        "schema_has_buyer": "buyer_receipt" in defs,
        "schema_no_auth": schema.get("no_auth") is True,
        "schema_no_gate": schema.get("no_gate") is True,
        "structural_only": structural_only["value"],
        "structural_only_state": structural_only["state"],
        "runtime_measured": runtime_measured["value"],
        "runtime_measured_state": runtime_measured["state"],
        "customer_ready": customer_ready["value"],
        "customer_ready_state": customer_ready["state"],
        "runtime_proof": evidence.get("runtime_proof")
        if "runtime_proof" in evidence
        else "UNRESOLVED",
        "collected_cash_usd": collected_cash["value"],
        "collected_cash_state": collected_cash["state"],
        "cash_state": str(quote.get("cash_state") or "").strip().upper(),
        "demand": str(quote.get("demand") or "").strip().upper(),
    }


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


def resolved_inbound(root, inbound_id):
    """Prove the resolved path stays exactly under p/."""
    name = canonicalize_post_id(inbound_id)
    rel = inbound_rel(inbound_id)
    if not name or not rel:
        return {"ok": False, "rel": "", "reason": "INVALID_ID", "path": ""}
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
    return {"ok": True, "rel": rel, "reason": "", "path": resolved}


def safe_excerpt_rel(excerpt_rel):
    """Reject separators-as-escape. Keep posix excerpts/… paths only."""
    raw = str(excerpt_rel or "").strip()
    if not raw:
        return ""
    if raw.startswith("/") or raw.startswith("\\"):
        return ""
    text = raw.replace("\\", "/")
    parts = [part for part in text.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        return ""
    if parts[0] != "excerpts":
        return ""
    return "/".join(parts)


def parse_post(text):
    raw = str(text or "")
    headers = {}
    body = raw
    head = ""
    if raw.startswith("---"):
        rest = raw[3:].lstrip("\n")
        if "\n---\n" in rest:
            head, body = rest.split("\n---\n", 1)
        else:
            head = rest
            body = ""
    elif "\n---\n" in raw:
        head, body = raw.split("\n---\n", 1)
    for line in head.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return {
        "from": str(headers.get("from") or "").strip(),
        "subject": str(headers.get("subject") or "").strip(),
        "id": str(headers.get("id") or "").strip(),
        "kind": str(headers.get("kind") or "").strip(),
        "body": body,
        "text": raw,
    }


def inbound_semantic(text, inbound_id, quote_hash):
    """Any existing file is not a public inbound. Self receipts are not buyers."""
    name = canonicalize_post_id(inbound_id)
    if not name:
        return {"ok": False, "reason": "INVALID_ID", "from": "", "subject": ""}
    if name in SELF_BIND_IDS:
        return {"ok": False, "reason": "SELF_BIND", "from": "", "subject": ""}
    parsed = parse_post(text)
    hay = (parsed["subject"] + "\n" + parsed["body"] + "\n" + parsed["id"]).lower()
    named = (
        SKU_ID.lower() in hay
        or P01_ID.lower() in hay
        or (_hex_sha(quote_hash) and str(quote_hash).lower() in hay)
    )
    if not named:
        return {
            "ok": False,
            "reason": "IRRELEVANT_INBOUND",
            "from": parsed["from"],
            "subject": parsed["subject"],
        }
    return {
        "ok": True,
        "reason": "",
        "from": parsed["from"],
        "subject": parsed["subject"],
    }


def buyer_evidence(text, inbound_id, quote_hash):
    """File existence is not acceptance. Need a distinct claim + quote bind."""
    semantic = inbound_semantic(text, inbound_id, quote_hash)
    if not semantic.get("ok"):
        return semantic
    parsed = parse_post(text)
    hay = parsed["subject"] + "\n" + parsed["body"]
    if not ACCEPT_RE.search(hay):
        return {
            "ok": False,
            "reason": "NO_ACCEPTANCE",
            "from": parsed["from"],
            "subject": parsed["subject"],
        }
    quote_named = SKU_ID in hay.lower() or (
        _hex_sha(quote_hash) and str(quote_hash).lower() in hay.lower()
    )
    if not quote_named:
        return {
            "ok": False,
            "reason": "QUOTE_NOT_NAMED",
            "from": parsed["from"],
            "subject": parsed["subject"],
        }
    if not parsed["from"]:
        return {
            "ok": False,
            "reason": "NO_BUYER_CLAIM",
            "from": "",
            "subject": parsed["subject"],
        }
    return {
        "ok": True,
        "reason": "",
        "from": parsed["from"],
        "subject": parsed["subject"],
    }


def legal_state_for(bound, hashes):
    """DRAFT → NEEDS_BUYER → ACCEPTED → DELIVERED. No skip."""
    delivery = str((hashes or {}).get("delivery_hash") or "").strip()
    if bound and _hex_sha(delivery):
        return "DELIVERED"
    if bound:
        return "ACCEPTED"
    quote_hash = str((hashes or {}).get("quote_hash") or "").strip()
    if _hex_sha(quote_hash):
        return "NEEDS_BUYER"
    return "DRAFT"


def bind_validation_receipt(root, inbound_id, excerpt_rel, status="UNKNOWN"):
    """Bind only on canonical inbound + distinct buyer acceptance.

    buyer_id is the public inbound id, not a private identity.
    File presence is not BUYER_BOUND. PASS is refused unless the
    legal state is ACCEPTED. That refusal is for every excerpt,
    not a GRBN hard-code.
    """
    indexed = source_index(root)
    hashes = source_hashes(root, indexed, inbound_id, excerpt_rel)
    located = resolved_inbound(root, inbound_id)
    excerpt = safe_excerpt_rel(excerpt_rel)
    parsed = parse_excerpt(_read_bytes(root, excerpt)) if excerpt else {
        "ok": False,
        "reason": "unsafe excerpt",
        "sha256": "",
    }
    file_ok = bool(located.get("ok")) and _exists(root, located.get("rel") or "")
    excerpt_ok = bool(parsed.get("ok")) and _hex_sha(parsed.get("sha256"))
    evidence = {
        "ok": False,
        "reason": located.get("reason") or "NO_INBOUND",
        "from": "",
        "subject": "",
    }
    if file_ok:
        evidence = inbound_semantic(
            _read(root, located["rel"]),
            inbound_id,
            hashes.get("quote_hash"),
        )
    inbound_ok = file_ok and bool(evidence.get("ok"))
    if inbound_ok:
        evidence = buyer_evidence(
            _read(root, located["rel"]),
            inbound_id,
            hashes.get("quote_hash"),
        )
    bound = inbound_ok and excerpt_ok and bool(evidence.get("ok"))
    wanted = str(status or "UNKNOWN").strip().upper()
    if wanted not in {"PASS", "FAIL", "UNKNOWN"}:
        wanted = "UNKNOWN"
    legal = legal_state_for(bound, hashes)
    refused = ""
    if wanted == "PASS" and legal != "ACCEPTED":
        refused = "PASS_WITHOUT_BUYER"
        wanted = "UNKNOWN"
    binding_state = "BUYER_BOUND" if bound else (
        "CANDIDATE" if inbound_ok else "UNBOUND"
    )
    if not bound and inbound_ok:
        binding_state = "INCOMPLETE"
    receipt = {
        "kind": "SUBZERO_BUYER_VALIDATION",
        "artifact": excerpt,
        "sha256": str(parsed.get("sha256") or ""),
        "status": wanted if bound else "UNKNOWN",
        "bound": bound,
        "buyer_id": canonicalize_post_id(inbound_id) if bound else "",
        "no_auth": True,
        "no_gate": True,
        "login_required": False,
        "privileged_tier": False,
    }
    return {
        "receipt": receipt,
        "inbound_ok": inbound_ok,
        "excerpt_ok": excerpt_ok,
        "header": parsed,
        "binding_state": binding_state,
        "legal_state": legal,
        "evidence_class": "STRUCTURAL_ONLY" if excerpt_ok else "UNKNOWN",
        "cash_state": "NOT_LANDED",
        "demand": "UNKNOWN",
        "buyer_reason": evidence.get("reason") or "",
        "status_refused": refused,
        "hashes": hashes,
        "inbound_rel": located.get("rel") or "",
    }


def receipt_schema_ok(receipt):
    """Match the already-landed buyer_receipt required fields."""
    receipt = receipt or {}
    if str(receipt.get("kind") or "") != "SUBZERO_BUYER_VALIDATION":
        return False
    if not str(receipt.get("artifact") or "").strip():
        return False
    if not _hex_sha(receipt.get("sha256")):
        return False
    if receipt.get("status") not in {"PASS", "FAIL", "UNKNOWN"}:
        return False
    if receipt.get("bound") is True and not str(receipt.get("buyer_id") or "").strip():
        return False
    if receipt.get("bound") is not True and receipt.get("bound") is not False:
        return False
    return (
        receipt.get("no_auth") is True
        and receipt.get("no_gate") is True
        and receipt.get("login_required") is False
        and receipt.get("privileged_tier") is False
    )


def classify_binding(row):
    """Name the live bind. Invented buyers / cash / runtime fail."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "H-008 receipt leftover not read. Absence was not stillness. "
                "FINDER-FAILED, never 0."
            ),
        }
    if str(row.get("finder") or "").strip().lower() in {"failed", "unknown", "error"}:
        return {
            "state": "FINDER-FAILED",
            "note": (
                "finder/tool call failed on "
                + SKU_ID
                + " bind. UNKNOWN, never 0."
            ),
        }
    cash_state = str(row.get("collected_cash_state") or "").strip().upper()
    cash_value = row.get("collected_cash_usd")
    if cash_state in {"UNRESOLVED", "FINDER-FAILED"}:
        return {
            "state": "FINDER-FAILED",
            "note": (
                "collected_cash_usd "
                + (cash_state or "UNRESOLVED")
                + ". Missing numeric is not measured $0. FINDER-FAILED, never 0."
            ),
        }
    if bool(row.get("claims_cash")) or (
        cash_state == "PRESENT" and cash_value not in (None, 0)
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "A buyer-bound receipt is not cash proof. Collected cash stays "
                "$0 / NOT_LANDED. FINDER-FAILED, never 0."
            ),
        }
    if bool(row.get("claims_runtime")) or row.get("runtime_proof") is True:
        return {
            "state": "NOT_LANDED",
            "note": (
                "A buyer-bound receipt is not runtime proof. "
                "FINDER-FAILED, never 0."
            ),
        }
    if bool(row.get("claims_demand")) or str(row.get("demand") or "").strip().upper() not in {
        "",
        "UNKNOWN",
    }:
        return {
            "state": "NOT_LANDED",
            "note": (
                "A bind implementation is not demand proof. Demand stays "
                "UNKNOWN. FINDER-FAILED, never 0."
            ),
        }
    live_bound, live_bound_state = measured_int(row, "live_bound_receipts")
    if live_bound_state in {"UNRESOLVED", "FINDER-FAILED"}:
        return {
            "state": "FINDER-FAILED",
            "note": (
                "live_bound_receipts "
                + live_bound_state
                + ". Missing numeric is not measured 0. Never coerce. "
                "FINDER-FAILED, never 0."
            ),
        }
    if live_bound_state == "PRESENT" and live_bound not in (None, 0):
        return {
            "state": "NOT_LANDED",
            "note": (
                "Live tree invented a buyer-bound receipt. Demand stays "
                "UNKNOWN. FINDER-FAILED, never 0."
            ),
        }
    live_bind = str(row.get("binding_state") or "").strip().upper()
    if live_bind not in {"UNBOUND", "CANDIDATE", "INCOMPLETE"}:
        return {
            "state": "NOT_LANDED",
            "note": (
                "Live binding_state must stay CANDIDATE/INCOMPLETE/UNBOUND "
                "until a distinct buyer accepts the quote. FINDER-FAILED, never 0."
            ),
        }
    legal = str(row.get("legal_state") or "").strip().upper()
    if legal and legal not in {"DRAFT", "NEEDS_BUYER"}:
        return {
            "state": "NOT_LANDED",
            "note": (
                "Live legal_state must stay DRAFT or NEEDS_BUYER. "
                "FINDER-FAILED, never 0."
            ),
        }
    if str(row.get("sku_id") or "").strip() != SKU_ID:
        return {
            "state": "NOT_LANDED",
            "note": (
                "source-index sku is "
                + (str(row.get("sku_id") or "missing"))
                + ", not "
                + SKU_ID
                + ". FINDER-FAILED, never 0."
            ),
        }
    price, price_state = measured_int(row, "quote_price")
    if price_state != "PRESENT":
        return {
            "state": "FINDER-FAILED",
            "note": (
                "quote_price "
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
                + ". FINDER-FAILED, never 0."
            ),
        }
    if str(row.get("p01_id") or "").strip() != P01_ID:
        return {
            "state": "NOT_LANDED",
            "note": "P01_catalog_receipt FINDER-FAILED, never 0.",
        }
    if not row.get("schema_has_buyer"):
        return {
            "state": "NOT_LANDED",
            "note": "buyer_receipt schema FINDER-FAILED, never 0.",
        }
    if not row.get("bind_works"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "quote-draft bind holes still open. "
                "FINDER-FAILED, never 0."
            ),
        }
    return {
        "state": "CANDIDATE",
        "note": (
            SKU_ID
            + " / "
            + P01_ID
            + " quote-draft bind is implemented. "
            "Live binder stays CANDIDATE/INCOMPLETE. "
            "Not buyer acceptance, not runtime, not demand, not cash."
        ),
    }


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    quote_price, quote_price_state = measured_int(facts, "quote_price")
    collected_cash, collected_cash_state = measured_int(facts, "collected_cash_usd")
    structural_only, structural_only_state = measured_int(facts, "structural_only")
    runtime_measured, runtime_measured_state = measured_int(facts, "runtime_measured")
    customer_ready, customer_ready_state = measured_int(facts, "customer_ready")
    live_bound, live_bound_state = measured_int(facts, "live_bound_receipts")
    runtime_proof = facts.get("runtime_proof")
    if runtime_proof not in {True, False, "UNRESOLVED"}:
        runtime_proof = bool(runtime_proof)
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "door_present": bool(facts.get("door_present")),
        "quote_present": bool(facts.get("quote_present")),
        "arch_present": bool(facts.get("arch_present")),
        "buyers_present": bool(facts.get("buyers_present")),
        "schema_present": bool(facts.get("schema_present")),
        "landed_present": list(facts.get("landed_present") or []),
        "landed_missing": list(facts.get("landed_missing") or []),
        "found_phrases": list(facts.get("found_phrases") or []),
        "sku_id": str(facts.get("sku_id") or ""),
        "quote_class": str(facts.get("quote_class") or ""),
        "quote_price": quote_price,
        "quote_price_state": quote_price_state,
        "p01_id": str(facts.get("p01_id") or ""),
        "arch_status": str(facts.get("arch_status") or ""),
        "arch_implements": str(facts.get("arch_implements") or ""),
        "schema_has_buyer": bool(facts.get("schema_has_buyer")),
        "schema_no_auth": bool(facts.get("schema_no_auth")),
        "schema_no_gate": bool(facts.get("schema_no_gate")),
        "binding_state": str(facts.get("binding_state") or ""),
        "legal_state": str(facts.get("legal_state") or "NEEDS_BUYER"),
        "live_bound_receipts": live_bound,
        "live_bound_receipts_state": live_bound_state,
        "bind_works": bool(facts.get("bind_works")),
        "grbn_sha": str(facts.get("grbn_sha") or ""),
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
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "hashes": dict(facts.get("hashes") or {}),
    }


def classify(row):
    """Turn a measured receipt census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "SUBZERO receipt leftover not read. Absence was not stillness. "
                "A Slack H-008 / second-pass body is not the file. "
                "FINDER-FAILED, never 0."
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
        or not row.get("quote_present")
        or not row.get("arch_present")
        or not row.get("buyers_present")
        or not row.get("schema_present")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog/door/source-index"])
                + ". JOJO H-008 / second-pass / quote-draft bind "
                "talk is CLAIMED until the leftover ships. "
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
    binding = classify_binding(row)
    if binding["state"] not in {"CANDIDATE"}:
        return {
            "state": "NOT_LANDED" if binding["state"] != "UNMEASURED" else "UNMEASURED",
            "note": binding["note"],
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
        for key in (
            "source_commit",
            "source_tree",
        ):
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
                "missing bind hashes: "
                + ", ".join(missing_hashes)
                + ". FINDER-FAILED, never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "SUBZERO receipt leftover is on this tree. "
            + SKU_ID
            + " / "
            + P01_ID
            + " quote-draft bind holes are closed. "
            "Live binder stays CANDIDATE/INCOMPLETE. "
            "Not buyer acceptance, not runtime, not demand, not cash. "
            "A Slack H-008 / second-pass body is still not the file."
        ),
    }


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
    catalog = load_json(_read(root, DEFAULT_CATALOG), "catalog")
    indexed = source_index(root)
    hashes = source_hashes(root, indexed)
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    calibration_ok = len(calibration_hits) == len(CALIBRATION)
    if not calibration_ok:
        for rel in CALIBRATION:
            if rel not in calibration_hits and rel not in misses:
                misses.append("calibration:" + rel)
    posting_open = (
        str(catalog.get("posting") or "") == "OPEN"
        and "open door" in hay
        and "unseated" in hay
    )
    missing_inbound = bind_validation_receipt(
        root,
        "fixture-h008-inbound-20260825-01",
        GRBN_REL,
        status="UNKNOWN",
    )
    escaped = bind_validation_receipt(root, "..\\ground\\EXECUTE", GRBN_REL, status="PASS")
    self_bind = bind_validation_receipt(root, QUOTE_RECEIPT, GRBN_REL, status="PASS")
    other_excerpt = bind_validation_receipt(root, QUOTE_RECEIPT, LVIN_REL, status="PASS")
    unrelated = bind_validation_receipt(
        root,
        "bryce-action-pad-open-door-directive-20260822-01",
        GRBN_REL,
        status="PASS",
    )
    bind_works = (
        missing_inbound["binding_state"] == "UNBOUND"
        and missing_inbound["excerpt_ok"]
        and str((missing_inbound.get("header") or {}).get("sha256") or "") == GRBN_SHA
        and not escaped["inbound_ok"]
        and escaped["binding_state"] != "BUYER_BOUND"
        and escaped["receipt"]["bound"] is False
        and escaped["status_refused"] == "PASS_WITHOUT_BUYER"
        and self_bind["buyer_reason"] == "SELF_BIND"
        and not self_bind["inbound_ok"]
        and self_bind["binding_state"] == "UNBOUND"
        and self_bind["binding_state"] != "BUYER_BOUND"
        and self_bind["receipt"]["bound"] is False
        and self_bind["receipt"]["status"] == "UNKNOWN"
        and other_excerpt["status_refused"] == "PASS_WITHOUT_BUYER"
        and other_excerpt["receipt"]["status"] == "UNKNOWN"
        and other_excerpt["receipt"]["bound"] is False
        and unrelated["buyer_reason"] == "IRRELEVANT_INBOUND"
        and not unrelated["inbound_ok"]
        and unrelated["binding_state"] == "UNBOUND"
        and _hashes_ok(self_bind.get("hashes"))
        and indexed.get("quote_price_state") == "PRESENT"
        and indexed.get("quote_price") == QUOTE_PRICE
        and indexed.get("collected_cash_state") == "PRESENT"
        and indexed.get("collected_cash_usd") == 0
        and present_int({}, "price_usd")["state"] == "UNRESOLVED"
        and present_int({"price_usd": None}, "price_usd")["state"] == "UNRESOLVED"
        and present_int({"price_usd": True}, "price_usd")["state"] == "FINDER-FAILED"
    )
    live_bound = present_int(catalog, "live_bound_receipts")
    live_bound_value, live_bound_state = live_bound["value"], live_bound["state"]
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "door_present": _exists(root, DEFAULT_DOOR),
        "quote_present": _exists(root, DEFAULT_QUOTE) and not indexed.get("quote_error"),
        "arch_present": _exists(root, DEFAULT_ARCH) and not indexed.get("arch_error"),
        "buyers_present": _exists(root, DEFAULT_BUYERS) and not indexed.get("buyers_error"),
        "schema_present": _exists(root, DEFAULT_SCHEMA)
        and not indexed.get("schema_error")
        and indexed.get("schema_has_buyer"),
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
        "sku_id": indexed.get("sku_id") or "",
        "quote_class": indexed.get("quote_class") or "",
        "quote_price": indexed.get("quote_price"),
        "quote_price_state": indexed.get("quote_price_state") or "UNRESOLVED",
        "p01_id": indexed.get("p01_id") or "",
        "arch_status": indexed.get("arch_status") or "",
        "arch_implements": indexed.get("arch_implements") or "",
        "schema_has_buyer": bool(indexed.get("schema_has_buyer")),
        "schema_no_auth": bool(indexed.get("schema_no_auth")),
        "schema_no_gate": bool(indexed.get("schema_no_gate")),
        "binding_state": str(catalog.get("binding_state") or "CANDIDATE").upper(),
        "legal_state": str(catalog.get("legal_state") or "NEEDS_BUYER").upper(),
        "live_bound_receipts": live_bound_value,
        "live_bound_receipts_state": live_bound_state,
        "bind_works": bind_works,
        "grbn_sha": str((missing_inbound.get("header") or {}).get("sha256") or ""),
        "collected_cash_usd": indexed.get("collected_cash_usd"),
        "collected_cash_state": indexed.get("collected_cash_state") or "UNRESOLVED",
        "cash_state": indexed.get("cash_state") or "",
        "demand": indexed.get("demand") or "",
        "runtime_proof": indexed.get("runtime_proof"),
        "structural_only": indexed.get("structural_only"),
        "structural_only_state": indexed.get("structural_only_state") or "UNRESOLVED",
        "runtime_measured": indexed.get("runtime_measured"),
        "runtime_measured_state": indexed.get("runtime_measured_state") or "UNRESOLVED",
        "customer_ready": indexed.get("customer_ready"),
        "customer_ready_state": indexed.get("customer_ready_state") or "UNRESOLVED",
        "claims_cash": bool(catalog.get("claims_cash")),
        "claims_runtime": bool(catalog.get("claims_runtime")),
        "claims_demand": bool(catalog.get("claims_demand")),
        "posting_open": posting_open,
        "no_auth": bool(catalog.get("no_auth")) and "no auth" in hay,
        "no_gate": bool(catalog.get("no_gate")) and "no gate" in hay,
        "calibration_ok": calibration_ok,
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "hashes": hashes,
        "slack_ts": str(catalog.get("slack_ts") or SLACK_TS),
        "second_pass_ts": str(catalog.get("second_pass_ts") or SECOND_PASS_TS),
        "hardening_ts": str(catalog.get("hardening_ts") or HARDENING_TS),
    }
    binding = classify_binding(measure_from_rows(facts))
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "second_pass_ts": facts["second_pass_ts"],
            "hardening_ts": facts["hardening_ts"],
            "cell": CELL,
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "calibration_hits": calibration_hits,
                "found_phrases": found,
                "landed_present": landed_present,
                "sku_id": facts["sku_id"],
                "quote_price": facts["quote_price"],
                "quote_price_state": facts["quote_price_state"],
                "p01_id": facts["p01_id"],
                "binding_state": facts["binding_state"],
                "legal_state": facts["legal_state"],
                "bind_works": facts["bind_works"],
                "live_bound_receipts": facts["live_bound_receipts"],
                "quote_receipt": QUOTE_RECEIPT,
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
                + " / FINDER-FAILED never 0 / bind "
                + binding["state"]
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
                "misses": ["ground/SUBZERO_RECEIPT.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    cash = classify_binding(
        {
            "measured": True,
            "sku_id": SKU_ID,
            "quote_price": QUOTE_PRICE,
            "quote_price_state": "PRESENT",
            "p01_id": P01_ID,
            "schema_has_buyer": True,
            "bind_works": True,
            "binding_state": "CANDIDATE",
            "legal_state": "NEEDS_BUYER",
            "collected_cash_usd": 0,
            "collected_cash_state": "PRESENT",
            "live_bound_receipts": 0,
            "live_bound_receipts_state": "PRESENT",
            "claims_cash": True,
        }
    )
    assert cash["state"] == "NOT_LANDED", cash
    invented = classify_binding(
        {
            "measured": True,
            "sku_id": SKU_ID,
            "quote_price": QUOTE_PRICE,
            "quote_price_state": "PRESENT",
            "p01_id": P01_ID,
            "schema_has_buyer": True,
            "bind_works": True,
            "binding_state": "CANDIDATE",
            "legal_state": "NEEDS_BUYER",
            "collected_cash_usd": 0,
            "collected_cash_state": "PRESENT",
            "live_bound_receipts": 1,
            "live_bound_receipts_state": "PRESENT",
            "demand": "UNKNOWN",
        }
    )
    assert invented["state"] == "NOT_LANDED", invented
    missing_price = classify_binding(
        {
            "measured": True,
            "sku_id": SKU_ID,
            "quote_price": None,
            "quote_price_state": "UNRESOLVED",
            "p01_id": P01_ID,
            "schema_has_buyer": True,
            "bind_works": True,
            "binding_state": "CANDIDATE",
            "collected_cash_usd": 0,
            "collected_cash_state": "PRESENT",
            "live_bound_receipts": 0,
            "live_bound_receipts_state": "PRESENT",
        }
    )
    assert missing_price["state"] == "FINDER-FAILED", missing_price
    missing_live = classify_binding(
        {
            "measured": True,
            "sku_id": SKU_ID,
            "quote_price": QUOTE_PRICE,
            "quote_price_state": "PRESENT",
            "p01_id": P01_ID,
            "schema_has_buyer": True,
            "bind_works": True,
            "binding_state": "CANDIDATE",
            "collected_cash_usd": 0,
            "collected_cash_state": "PRESENT",
            "live_bound_receipts": None,
            "live_bound_receipts_state": "UNRESOLVED",
        }
    )
    assert missing_live["state"] == "FINDER-FAILED", missing_live
    assert inbound_rel("..\\ground\\EXECUTE") == ""
    assert inbound_rel("../ground/EXECUTE") == ""
    assert canonicalize_post_id("rivet-ship-subzero-quote-20260825-01")
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure SUBZERO receipt leftover")
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
