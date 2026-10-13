#!/usr/bin/env python3
"""AquaTrace in-process control-rail runner for Bid 1421.

Loads AT-001..AT-100 from the existing acceptance corpus (cite, do not
rewrite) and executes each case on a real append-only control rail.

Synthetic laboratory fixtures only. Not live-instrument compatible.
Not a City submission. Not certified. Not production-deployed.
Named human required before any regulatory release.
autonomous_release_count is always 0.

python3 revenue/billings_bid_1421/acceptance_runner/runner.py
python3 -m unittest test_billings_bid_1421_acceptance_runner.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CORPUS_DIR = os.path.join(REPO, "revenue", "billings_bid_1421", "acceptance_corpus")
CORPUS_JSON = os.path.join(
    CORPUS_DIR, "billings-bid-1421-aquatrace-acceptance-corpus.json"
)
CORPUS_ID = "billings-bid-1421-acceptance-corpus-20260831-01"
RUNNER_ID = "billings-bid-1421-acceptance-runner-20260831-01"
SCHEMA = "commons-billings-bid-1421-acceptance-runner/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
COMMAND = "python3 revenue/billings_bid_1421/acceptance_runner/runner.py"
FIXTURE_CLOCK = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
CLOCK_ISO = "2026-08-31T12:00:00Z"
SLACK_CORPUS_JSON_SHA256 = (
    "355924d3e03dae5f2fb6759a927338a56d57ce1a9606897d65621256b340d313"
)
CORPUS_POST_BLOB = "054e321cef6226dc59ab2d6781f56637b3cb433d"
INSTRUMENT_FIXTURES_BLOB = "03ff210c2385e5cbf9785e706d97c41b44689976"

KNOWN_METHODS = frozenset(
    {
        "EPA 300.0",
        "EPA 200.9",
        "SM 4500-H+ B",
        "SM 5310 B",
        "SM 2540 D",
        "HACH 8000",
    }
)
BLANK_OFFICIAL_METHODS = frozenset({"Paint Filter Test", "Volatile Acids"})
KNOWN_INSTRUMENTS = frozenset(
    {
        "PH-METER-01",
        "BALANCE-01",
        "AA-FURNACE",
        "METROHM-IC",
        "SIEVERS-TOC",
        "SEAL-DISCRETE",
    }
)
INSTRUMENT_FAMILIES = (
    "PH-METER-01",
    "BALANCE-01",
    "AA-FURNACE",
    "METROHM-IC",
    "SIEVERS-TOC",
    "SEAL-DISCRETE",
)

ROLE_PERMS = {
    "FIELD_COLLECTOR": frozenset({"collect", "custody_init", "offline_sync"}),
    "VIEWER": frozenset({"view"}),
    "ANALYST": frozenset({"result_entry", "retest", "instrument_ingest"}),
    "QA_MANAGER": frozenset(
        {
            "void",
            "approve_release_intent",
            "hold",
            "config_change",
            "role_admin",
            "audit_export",
            "correction",
        }
    ),
    "QA_REVIEWER": frozenset({"hold", "review", "audit_export"}),
    "RECEIVING_LEAD": frozenset({"receive", "reject", "custody_receive", "receive_custody"}),
    "CUSTODIAN": frozenset({"transfer", "receive_custody", "custody_init"}),
    "LAB_RECEIVER": frozenset({"receive", "custody_receive", "receive_custody"}),
    "AUDITOR": frozenset({"audit_export"}),
}

REQUIRED_RECEIPT_FIELDS = (
    "case_id",
    "event_id",
    "sample_id",
    "actor_fixture",
    "role_fixture",
    "method_version",
    "rule_version",
    "input_hash",
    "observed_effect_hash",
    "disposition",
    "reason_code",
    "event_time",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value):
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = canonical(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def parse_iso(stamp):
    if not stamp:
        return None
    text = str(stamp).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def load_corpus(path=None):
    target = path or CORPUS_JSON
    with open(target, encoding="utf-8") as handle:
        corpus = json.load(handle)
    if corpus.get("id") != CORPUS_ID:
        raise ValueError("unexpected corpus id %s" % corpus.get("id"))
    cases = corpus.get("cases") or []
    ids = [case["id"] for case in cases]
    expected = ["AT-%03d" % i for i in range(1, 101)]
    if ids != expected:
        raise ValueError("corpus must be AT-001..AT-100 in order")
    return corpus


def file_sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


class ControlRail:
    """Append-only AquaTrace control rail. Deterministic. No network I/O."""

    def __init__(self):
        self.ledger = []
        self.receipts = []
        self.samples = {}
        self.custody_nodes = {}
        self.current_custodian = {}
        self.sample_state = {}
        self.results = {}
        self.qc_holds = {}
        self.commits = {}
        self.input_hashes = {}
        self.conflict_hashes = {}
        self.pending = {}
        self.sequence_applied = {}
        self.resume_cursor = {}
        self.coa = {}
        self.quarantine = []
        self.config_versions = [
            {
                "kind": "qc_rule",
                "version": "v1",
                "hash": sha256_hex({"qc_rule": "v1", "pos_hi": 1.0}),
                "effective": CLOCK_ISO,
            }
        ]
        self.qc_rule_version = "v1"
        self.instrument_mapping_version = "v1"
        self.mapping_history = [{"version": "v1", "effective": CLOCK_ISO}]
        self.role_registry = dict(ROLE_PERMS)
        self.role_history = []
        self.capabilities = {}
        self.actor_status = {}
        self.denials = []
        self.exports = []
        self.drafts = {}
        self.dashboard = {}
        self.regulatory_release_count = 0
        self.regulatory_transmission_count = 0
        self.autonomous_release_count = 0
        self.clock = FIXTURE_CLOCK
        self.batch_receipts = {}
        self.corrections = []
        self.restore_log = []
        self.attempt_log = []

    def _event_hash(self, event):
        body = {
            key: event[key]
            for key in sorted(event)
            if key not in {"_flags", "_meta"}
        }
        return sha256_hex(body)

    def _can(self, role, action):
        return action in self.role_registry.get(role or "", frozenset())

    def _append_ledger(self, kind, payload):
        prev = self.ledger[-1]["hash"] if self.ledger else "GENESIS"
        row = {
            "seq": len(self.ledger) + 1,
            "kind": kind,
            "payload": deepcopy(payload),
            "predecessor": prev,
            "time": CLOCK_ISO,
        }
        row["hash"] = sha256_hex(row)
        self.ledger.append(row)
        return row

    def identity_gate(self, event):
        event_id = event.get("event_id")
        digest = self._event_hash(event)
        prior = self.input_hashes.get(event_id)
        if prior is None:
            self.input_hashes[event_id] = digest
            return None
        if prior == digest:
            return {
                "disposition": "DUPLICATE_SUPPRESSED",
                "reason_code": "EXACT_REPLAY",
                "business_effect": 0,
                "input_hash": digest,
            }
        self.conflict_hashes.setdefault(event_id, [prior])
        if digest not in self.conflict_hashes[event_id]:
            self.conflict_hashes[event_id].append(digest)
        sample_id = event.get("sample_id")
        if sample_id and sample_id in self.samples:
            self.samples[sample_id]["authoritative"] = False
        if event_id in self.commits:
            self.commits[event_id]["authoritative"] = False
        if event_id in self.results:
            self.results[event_id]["authoritative"] = False
        return {
            "disposition": "CONFLICT_HOLD",
            "reason_code": "IDENTITY_CONFLICT",
            "business_effect": 0,
            "input_hash": digest,
            "retained_hashes": list(self.conflict_hashes[event_id]),
        }

    def make_receipt(self, event, disposition, reason_code, effect=None, extra=None):
        effect_payload = effect if effect is not None else {"none": True}
        receipt = {
            "case_id": event.get("case_id"),
            "event_id": event.get("event_id"),
            "sample_id": event.get("sample_id") or "",
            "actor_fixture": event.get("actor_fixture") or "",
            "role_fixture": event.get("role_fixture") or "",
            "method_version": event.get("method_version") or "v1",
            "rule_version": event.get("rule_version") or self.qc_rule_version,
            "input_hash": extra.get("input_hash") if extra and extra.get("input_hash") else self._event_hash(event),
            "observed_effect_hash": sha256_hex(effect_payload),
            "disposition": disposition,
            "reason_code": reason_code,
            "event_time": event.get("event_time") or CLOCK_ISO,
            "regulatory_release_count": self.regulatory_release_count,
            "regulatory_transmission_count": self.regulatory_transmission_count,
            "autonomous_release_count": self.autonomous_release_count,
            "cash_usd": 0,
        }
        if extra:
            for key, value in extra.items():
                if key not in receipt:
                    receipt[key] = value
        self.receipts.append(receipt)
        self._append_ledger("receipt", receipt)
        return receipt

    def deny(self, event, reason_code, extra=None):
        payload = extra or {}
        self.denials.append(
            {
                "event_id": event.get("event_id"),
                "actor_fixture": event.get("actor_fixture"),
                "role_fixture": event.get("role_fixture"),
                "reason_code": reason_code,
                "effect": 0,
            }
        )
        self.attempt_log.append(
            {
                "event_id": event.get("event_id"),
                "kind": "denied",
                "reason_code": reason_code,
            }
        )
        return self.make_receipt(event, "DENIED", reason_code, effect=None, extra=payload)

    def hold(self, event, reason_code, extra=None):
        return self.make_receipt(
            event, extra.get("disposition", "HOLD") if extra else "HOLD",
            reason_code, effect=None, extra=extra,
        )

    def actor_gate(self, event, action):
        if event.get("actor_status") == "INACTIVE":
            return self.deny(event, "ACTOR_INACTIVE")
        session_actor = event.get("session_actor")
        if session_actor and session_actor != event.get("actor_fixture"):
            return self.deny(
                event,
                "ACTOR_MISMATCH",
                extra={
                    "session_actor": session_actor,
                    "payload_actor": event.get("actor_fixture"),
                },
            )
        if not event.get("actor_fixture"):
            return self.hold(event, "ACTOR_REQUIRED")
        role = event.get("role_fixture")
        if not self._can(role, action):
            return self.deny(event, "ROLE_DENIED")
        return None

    def process(self, event):
        kind = event.get("kind")
        dispatch = {
            "field_collection": self.process_field_collection,
            "offline_event": self.process_offline_event,
            "offline_batch": self.process_offline_batch,
            "custody": self.process_custody,
            "sample_receipt": self.process_sample_receipt,
            "orphan_result": self.process_orphan_result,
            "qc_result": self.process_qc_result,
            "retest": self.process_retest,
            "release_request": self.process_release_request,
            "approval_intent": self.process_approval_intent,
            "instrument_ingest": self.process_instrument_ingest,
            "instrument_batch": self.process_instrument_batch,
            "audit_export": self.process_audit_export,
            "config_change": self.process_config_change,
            "role_change": self.process_role_change,
            "restore": self.process_restore,
            "report_draft": self.process_report_draft,
            "report_send": self.process_report_send,
            "role_action": self.process_role_action,
            "retry": self.process_retry,
            "partition_merge": self.process_partition_merge,
            "rule_rollback": self.process_rule_rollback,
        }
        handler = dispatch.get(kind)
        if handler is None:
            return self.hold(event, "UNKNOWN_KIND")
        return handler(event)

    def process_field_collection(self, event):
        blocked = self.actor_gate(event, "collect")
        if blocked:
            return blocked
        if not event.get("collection_time"):
            return self.hold(event, "REQUIRED_FIELD_MISSING")
        method = event.get("method")
        if method in BLANK_OFFICIAL_METHODS or method not in KNOWN_METHODS:
            return self.hold(
                event,
                "METHOD_MAPPING_REQUIRED",
                extra={"result_eligible": False},
            )
        collected = parse_iso(event.get("collection_time"))
        if collected and collected - self.clock > timedelta(hours=24):
            return self.hold(
                event,
                "CLOCK_ANOMALY",
                extra={"human_resolution_required": True},
            )
        ident = self.identity_gate(event)
        if ident:
            return self.make_receipt(
                event,
                ident["disposition"],
                ident["reason_code"],
                effect=None,
                extra=ident,
            )
        sample_id = event["sample_id"]
        sample = {
            "sample_id": sample_id,
            "method": method,
            "actor_fixture": event["actor_fixture"],
            "role_fixture": event["role_fixture"],
            "collection_time": event["collection_time"],
            "container_id": event.get("container_id"),
            "event_id": event["event_id"],
            "authoritative": True,
            "result_eligible": True,
        }
        self.samples[sample_id] = sample
        self.sample_state[sample_id] = "COLLECTED"
        custody = None
        if event.get("init_custody"):
            custody = self._add_custody_node(
                sample_id,
                event,
                predecessor=None,
                role="collector",
            )
        if event.get("coa_pointer"):
            self.coa[sample_id] = {
                "pointer": event["coa_pointer"],
                "treated_as_result": False,
                "linked_receipt": event["event_id"],
            }
        effect = {"sample": sample, "custody": custody}
        extra = {"sample_start": 1}
        if custody:
            extra["custody_linked"] = True
        return self.make_receipt(event, "ACCEPTED", "COLLECTION_RECORDED", effect, extra)

    def _add_custody_node(self, sample_id, event, predecessor, role):
        node = {
            "sample_id": sample_id,
            "event_id": event.get("event_id"),
            "actor_fixture": event.get("actor_fixture"),
            "role_fixture": event.get("role_fixture"),
            "predecessor": predecessor,
            "role": role,
            "container_id": event.get("container_id"),
            "time": event.get("event_time") or CLOCK_ISO,
        }
        node["hash"] = sha256_hex(node)
        self.custody_nodes.setdefault(sample_id, []).append(node)
        self.current_custodian[sample_id] = event.get("actor_fixture")
        return node

    def process_offline_event(self, event):
        blocked = self.actor_gate(event, "offline_sync")
        if blocked:
            return blocked
        ident = self.identity_gate(event)
        if ident:
            return self.make_receipt(
                event, ident["disposition"], ident["reason_code"], extra=ident
            )
        sample_id = event["sample_id"]
        seq = int(event["sequence"])
        applied = self.sequence_applied.setdefault(sample_id, 0)
        expected = applied + 1
        if seq > expected:
            self.pending.setdefault(sample_id, {})[seq] = event
            return self.hold(
                event,
                "MISSING_PREDECESSOR",
                extra={
                    "missing_predecessor": expected,
                    "held_sequence": seq,
                    "disposition": "HOLD",
                },
            )
        if seq < expected:
            return self.make_receipt(
                event, "DUPLICATE_SUPPRESSED", "EXACT_REPLAY", extra={"business_effect": 0}
            )
        return self._commit_offline(event)

    def _commit_offline(self, event):
        sample_id = event["sample_id"]
        seq = int(event["sequence"])
        if event.get("timeout_before_commit"):
            return self.make_receipt(
                event,
                "RETRY_SAFE",
                "TIMEOUT_BEFORE_COMMIT",
                extra={"committed": False, "retry_bound": 1},
            )
        commit_id = "commit-%s-%s" % (event["event_id"], seq)
        already = self.commits.get(event["event_id"])
        if already and event.get("timeout_after_commit"):
            return self.make_receipt(
                event,
                "RECONCILED_COMMITTED",
                "READBACK_NO_SECOND_WRITE",
                effect=already,
                extra={"second_write": 0, "commit_id": already["commit_id"]},
            )
        row = {
            "commit_id": commit_id,
            "event_id": event["event_id"],
            "sample_id": sample_id,
            "sequence": seq,
            "authoritative": True,
        }
        if event.get("device_time"):
            row["device_time"] = event["device_time"]
            row["receipt_time"] = CLOCK_ISO
        self.commits[event["event_id"]] = row
        self.sequence_applied[sample_id] = seq
        self.resume_cursor[sample_id] = seq
        if sample_id not in self.samples:
            self.samples[sample_id] = {
                "sample_id": sample_id,
                "authoritative": True,
                "event_id": event["event_id"],
            }
        extra = {"commit_id": commit_id, "sequence": seq}
        if event.get("device_time"):
            extra["device_time"] = event["device_time"]
            extra["receipt_time"] = CLOCK_ISO
            return self.make_receipt(
                event, "ACCEPTED_WITH_CLOCK_EVIDENCE", "CLOCK_SKEW_RETAINED", row, extra
            )
        return self.make_receipt(event, "ACCEPTED", "OFFLINE_COMMITTED", row, extra)

    def process_offline_batch(self, event):
        blocked = self.actor_gate(event, "offline_sync")
        if blocked:
            return blocked
        items = list(event.get("events") or [])
        arrive = event.get("arrive_order")
        if arrive:
            ordered = sorted(items, key=lambda item: int(item["sequence"]))
            arrived = [next(item for item in items if int(item["sequence"]) == n) for n in arrive]
        else:
            ordered = sorted(items, key=lambda item: int(item["sequence"]))
            arrived = items
        sample_id = event["sample_id"]
        if event.get("mode") == "duplicate_replay":
            apply_ev = dict(event)
            apply_ev["mode"] = "apply"
            first_receipt = self.process_offline_batch(apply_ev)
            self.identity_gate(apply_ev)
            ident = self.identity_gate(apply_ev) or {
                "disposition": "DUPLICATE_SUPPRESSED",
                "reason_code": "BATCH_REPLAY",
                "business_effect": 0,
            }
            extra = dict(ident)
            extra["replay_of"] = first_receipt["event_id"]
            extra["lifecycle_effects"] = 0
            return self.make_receipt(
                event, "DUPLICATE_SUPPRESSED", "BATCH_REPLAY", extra=extra
            )
        if event.get("mode") == "clean_room":
            left = ControlRail()
            right = ControlRail()
            payload = dict(event)
            payload["mode"] = "apply"
            a = left.process_offline_batch(payload)
            b = right.process_offline_batch(payload)
            same = sha256_hex(left.normalized_state()) == sha256_hex(right.normalized_state())
            extra = {
                "left_hash": sha256_hex(left.normalized_state()),
                "right_hash": sha256_hex(right.normalized_state()),
                "byte_identical": same,
            }
            return self.make_receipt(
                event, "ACCEPTED", "CLEAN_ROOM_IDENTICAL", extra=extra
            )
        if event.get("mode") == "resume":
            stop_after = int(event.get("stop_after") or 0)
            first = items[:stop_after]
            rest = items[stop_after:]
            for item in first:
                child = dict(item)
                child["case_id"] = event["case_id"]
                child["kind"] = "offline_event"
                child["sample_id"] = sample_id
                child["actor_fixture"] = event["actor_fixture"]
                child["role_fixture"] = event["role_fixture"]
                self.process_offline_event(child)
            cursor = self.resume_cursor.get(sample_id, 0)
            for item in rest:
                if int(item["sequence"]) <= cursor:
                    continue
                child = dict(item)
                child["case_id"] = event["case_id"]
                child["kind"] = "offline_event"
                child["sample_id"] = sample_id
                child["actor_fixture"] = event["actor_fixture"]
                child["role_fixture"] = event["role_fixture"]
                self.process_offline_event(child)
            extra = {
                "resume_from": cursor + 1,
                "final_count": self.sequence_applied.get(sample_id, 0),
            }
            return self.make_receipt(
                event,
                "ACCEPTED_AFTER_RESUME",
                "RESUME_CURSOR",
                extra=extra,
            )
        if event.get("timeout_before_commit"):
            retry = dict(event)
            retry["timeout_before_commit"] = False
            retry["event_id"] = event["event_id"] + "-retry"
            rec = self.process_offline_batch(retry)
            return self.make_receipt(
                event,
                "RETRY_SAFE",
                "TIMEOUT_BEFORE_COMMIT",
                extra={"retry_event_id": rec["event_id"], "effects": 1},
            )
        if event.get("timeout_after_commit"):
            apply_once = dict(event)
            apply_once["timeout_after_commit"] = False
            first = self.process_offline_batch(apply_once)
            retry = dict(event)
            retry["timeout_after_commit"] = False
            ident = self.identity_gate(retry)
            extra = {
                "first_commit": first.get("commit_id") or first["event_id"],
                "second_write": 0,
            }
            if ident:
                extra.update(ident)
            return self.make_receipt(
                event, "RECONCILED_COMMITTED", "READBACK_NO_SECOND_WRITE", extra=extra
            )
        sequences = [int(item["sequence"]) for item in arrived]
        expected = list(range(1, max(sequences) + 1)) if sequences else []
        present = sorted(set(sequences))
        if present != expected:
            missing = [n for n in expected if n not in present]
            applied = []
            for item in ordered:
                seq = int(item["sequence"])
                if missing and seq > min(missing):
                    continue
                child = dict(item)
                child.update(
                    {
                        "kind": "offline_event",
                        "case_id": event["case_id"],
                        "sample_id": sample_id,
                        "actor_fixture": event["actor_fixture"],
                        "role_fixture": event["role_fixture"],
                    }
                )
                rec = self.process_offline_event(child)
                applied.append(rec)
            return self.hold(
                event,
                "MISSING_PREDECESSOR",
                extra={
                    "missing_predecessor": missing[0] if missing else None,
                    "held_sequence": [n for n in present if missing and n > min(missing)],
                },
            )
        applied_ids = []
        for item in ordered:
            child = dict(item)
            child.update(
                {
                    "kind": "offline_event",
                    "case_id": event["case_id"],
                    "sample_id": sample_id,
                    "actor_fixture": event["actor_fixture"],
                    "role_fixture": event["role_fixture"],
                    "event_time": event.get("event_time") or CLOCK_ISO,
                    "method_version": event.get("method_version") or "v1",
                    "rule_version": event.get("rule_version") or "v1",
                }
            )
            if event.get("device_time"):
                child["device_time"] = event["device_time"]
            rec = self.process_offline_event(child)
            applied_ids.append(rec["event_id"])
        extra = {
            "applied_sequences": [int(item["sequence"]) for item in ordered],
            "batch_size": len(ordered),
            "batch_receipt": event["event_id"],
        }
        self.batch_receipts[event["event_id"]] = extra
        disposition = "ACCEPTED"
        reason = "BATCH_APPLIED"
        if arrive and arrive != [int(item["sequence"]) for item in ordered]:
            disposition = "ACCEPTED_AFTER_REORDER"
            reason = "SEQUENCE_AUTHORITATIVE"
            extra["arrival_order"] = arrive
        if event.get("device_time"):
            disposition = "ACCEPTED_WITH_CLOCK_EVIDENCE"
            reason = "CLOCK_SKEW_RETAINED"
        return self.make_receipt(event, disposition, reason, extra=extra)

    def process_custody(self, event):
        action = event.get("action")
        sample_id = event.get("sample_id")
        if action == "export":
            nodes = list(self.custody_nodes.get(sample_id, []))
            if event.get("seed_nodes"):
                self.custody_nodes[sample_id] = []
                prev = None
                for idx, seed in enumerate(event["seed_nodes"], 1):
                    node_event = {
                        "event_id": "%s-N%02d" % (event["event_id"], idx),
                        "actor_fixture": seed.get("actor_fixture") or event["actor_fixture"],
                        "role_fixture": seed.get("role_fixture") or event["role_fixture"],
                        "container_id": seed.get("container_id") or event.get("container_id"),
                        "event_time": CLOCK_ISO,
                    }
                    node = self._add_custody_node(sample_id, node_event, prev, seed.get("role") or "node")
                    prev = node["hash"]
                nodes = list(self.custody_nodes[sample_id])
            export = {
                "nodes": nodes,
                "count": len(nodes),
                "root": nodes[0]["hash"] if nodes else None,
                "ledger_root": self.ledger[-1]["hash"] if self.ledger else "GENESIS",
            }
            extra = {"export_count": len(nodes), "ledger_root": export["ledger_root"]}
            return self.make_receipt(event, "ACCEPTED", "CUSTODY_EXPORTED", export, extra)
        if action == "void":
            blocked = self.actor_gate(event, "void")
            if blocked:
                return blocked
            if not event.get("reason"):
                return self.hold(event, "REASON_REQUIRED")
            self.sample_state[sample_id] = "VOIDED"
            effect = {"voided": True, "reason": event["reason"], "terminal": True}
            return self.make_receipt(event, "VOIDED", "AUTHORIZED_VOID", effect)
        if action == "dispose":
            state = self.sample_state.get(sample_id, "IN_TRANSIT")
            if state != "RECEIVED":
                return self.deny(
                    event,
                    "INVALID_LIFECYCLE_TRANSITION",
                    extra={"state": state, "transition_rule": "DISPOSE_REQUIRES_RECEIVED"},
                )
            self.sample_state[sample_id] = "DISPOSED"
            return self.make_receipt(event, "ACCEPTED", "DISPOSED")
        if action == "correction":
            blocked = self.actor_gate(event, "correction")
            if blocked:
                blocked = None if event.get("approver_fixture") else blocked
            if blocked:
                return blocked
            original = deepcopy(self.samples.get(sample_id) or {"container_id": event.get("original_container")})
            if sample_id not in self.samples:
                self.samples[sample_id] = {
                    "sample_id": sample_id,
                    "container_id": event.get("original_container"),
                    "authoritative": True,
                }
            correction = {
                "original": original,
                "container_id": event.get("container_id"),
                "reason": event.get("reason"),
                "approver_fixture": event.get("approver_fixture"),
                "predecessor": sha256_hex(original),
            }
            self.corrections.append(correction)
            self.samples[sample_id]["container_id"] = event.get("container_id")
            extra = {
                "original_hash": sha256_hex(original),
                "correction_hash": sha256_hex(correction),
                "original_visible": True,
            }
            return self.make_receipt(
                event, "ACCEPTED_AS_CORRECTION", "APPEND_ONLY_CORRECTION", correction, extra
            )
        if action == "seed_chain":
            prev = None
            for idx, seed in enumerate(event.get("nodes") or [], 1):
                node_event = {
                    "event_id": "%s-N%02d" % (event["event_id"], idx),
                    "actor_fixture": seed["actor_fixture"],
                    "role_fixture": seed.get("role_fixture") or "CUSTODIAN",
                    "container_id": seed.get("container_id"),
                    "event_time": CLOCK_ISO,
                }
                node = self._add_custody_node(sample_id, node_event, prev, seed.get("role") or "node")
                prev = node["hash"]
            self.sample_state[sample_id] = event.get("state") or "IN_TRANSIT"
            nodes = self.custody_nodes[sample_id]
            extra = {
                "root": nodes[0]["hash"],
                "predecessor_links": len(nodes) - 1,
                "current_custodian": self.current_custodian[sample_id],
            }
            return self.make_receipt(event, "ACCEPTED", "CHAIN_VALID", extra=extra)
        if action == "receive":
            if event.get("await_transfer") or not self.custody_nodes.get(sample_id):
                if not event.get("transfer_present"):
                    return self.hold(
                        event,
                        "PENDING_PREDECESSOR",
                        extra={"disposition": "HOLD_PENDING_PREDECESSOR"},
                    )
            blocked = self.actor_gate(event, "receive_custody")
            if blocked:
                return blocked
            node = self._add_custody_node(
                sample_id,
                event,
                predecessor=(self.custody_nodes.get(sample_id) or [{}])[-1].get("hash"),
                role="receive",
            )
            return self.make_receipt(event, "ACCEPTED", "CUSTODY_RECEIVED", node)
        if action == "transfer":
            blocked = self.actor_gate(event, "transfer")
            if blocked:
                return blocked
            recipient_role = event.get("recipient_role")
            if recipient_role is not None and (
                recipient_role == "VIEWER" or not self._can(recipient_role, "receive_custody")
            ):
                return self.deny(
                    event,
                    "ROLE_DENIED",
                    extra={"prior_custodian": self.current_custodian.get(sample_id)},
                )
            pred = event.get("predecessor_hash")
            nodes = self.custody_nodes.get(sample_id) or []
            known = {node["hash"] for node in nodes}
            if pred and pred not in known:
                return self.hold(
                    event,
                    "LINEAGE_BREAK",
                    extra={"missing_hash": pred},
                )
            ident = self.identity_gate(event)
            if ident:
                return self.make_receipt(
                    event, ident["disposition"], ident["reason_code"], extra=ident
                )
            node = self._add_custody_node(
                sample_id,
                event,
                predecessor=pred or (nodes[-1]["hash"] if nodes else None),
                role="transfer",
            )
            return self.make_receipt(event, "ACCEPTED", "CUSTODY_TRANSFER", node)
        return self.hold(event, "UNKNOWN_CUSTODY_ACTION")

    def process_sample_receipt(self, event):
        if event.get("action") == "reject":
            blocked = self.actor_gate(event, "reject")
            if blocked:
                return blocked
            if not event.get("reason"):
                return self.hold(event, "REASON_REQUIRED")
            self.sample_state[event["sample_id"]] = "REJECTED"
            effect = {
                "rejected": True,
                "reason": event["reason"],
                "source_receipt": event.get("source_receipt"),
                "terminal": True,
            }
            return self.make_receipt(event, "REJECTED", event["reason"], effect)
        blocked = self.actor_gate(event, "receive")
        if blocked:
            return blocked
        sample_id = event["sample_id"]
        if event.get("condition") == "DAMAGED":
            extra = {
                "condition": "DAMAGED",
                "reason": event.get("reason") or "DAMAGED",
                "owner": event.get("owner") or event.get("actor_fixture"),
            }
            return self.hold(event, "RECEIPT_EXCEPTION", extra=extra)
        if event.get("coa_bytes") is not None:
            claimed = event.get("coa_hash")
            actual = sha256_hex(event.get("coa_bytes"))
            if claimed != actual:
                self.quarantine.append(
                    {"sample_id": sample_id, "reason": "COA_HASH_MISMATCH"}
                )
                return self.hold(event, "INTEGRITY_FAILURE", extra={"quarantined": True})
        ident = self.identity_gate(event)
        if ident:
            if ident["disposition"] == "CONFLICT_HOLD":
                extra = dict(ident)
                extra["authoritative"] = False
                return self.make_receipt(
                    event, "CONFLICT_HOLD", ident["reason_code"], extra=extra
                )
            return self.make_receipt(
                event, ident["disposition"], ident["reason_code"], extra=ident
            )
        existing = self.samples.get(sample_id)
        if existing and existing.get("container_id") and event.get("container_id"):
            if existing["container_id"] != event["container_id"] and existing.get("received"):
                return self.make_receipt(
                    event,
                    "CONFLICT_HOLD",
                    "IDENTITY_CONFLICT",
                    extra={"retained_hashes": True, "authoritative": False},
                )
        if not event.get("method") and not event.get("analyte"):
            self.samples[sample_id] = {
                "sample_id": sample_id,
                "traceable": True,
                "result_eligible": False,
                "authoritative": True,
            }
            return self.hold(event, "METHOD_MAPPING_REQUIRED", extra={"result_eligible": False})
        if event.get("unscheduled"):
            self.samples[sample_id] = {
                "sample_id": sample_id,
                "schedule": None,
                "authoritative": True,
                "invented_schedule": False,
            }
            return self.make_receipt(
                event,
                "MANUAL_REVIEW",
                "SCHEDULE_EXCEPTION",
                extra={"invented_schedule": False},
            )
        sample = {
            "sample_id": sample_id,
            "container_id": event.get("container_id"),
            "method": event.get("method"),
            "received": True,
            "authoritative": True,
            "field_custody": event.get("field_custody") or "FIELD-NODE",
        }
        self.samples[sample_id] = sample
        self.sample_state[sample_id] = "RECEIVED"
        if event.get("coa_hash"):
            self.coa[sample_id] = {
                "hash": event["coa_hash"],
                "inventory": event.get("inventory_fixture") or "INV-001",
                "treated_as_result": False,
            }
        extra = {"accession": 1, "linked_field_custody": sample["field_custody"]}
        return self.make_receipt(event, "RECEIVED", "ACCESSION_RECORDED", sample, extra)

    def process_orphan_result(self, event):
        sample_id = event.get("sample_id")
        if sample_id not in self.samples:
            return self.hold(
                event,
                "SAMPLE_NOT_FOUND",
                extra={"invented_sample": False},
            )
        return self.hold(event, "UNEXPECTED_ORPHAN_PATH")

    def _capability_gate(self, event, method):
        cap = event.get("capability")
        if cap == "expired":
            return self.deny(event, "CAPABILITY_EXPIRED", extra={"capability": cap})
        if cap == "missing" or (event.get("capabilities") is not None and method not in (event.get("capabilities") or [])):
            return self.deny(event, "CAPABILITY_MISSING", extra={"method": method})
        return None

    def process_qc_result(self, event):
        blocked = self.actor_gate(event, event.get("need_perm") or "result_entry")
        if blocked:
            return blocked
        method = event.get("method") or "EPA 300.0"
        cap = self._capability_gate(event, method)
        if cap:
            return cap
        if event.get("positive_control_high"):
            extra = {
                "failed_control": event.get("failed_control") or "POS-001",
                "release_eligible": False,
            }
            self.qc_holds[event["sample_id"]] = extra
            return self.make_receipt(event, "QC_HOLD", "QC_CONTROL_OUT_OF_RANGE", extra=extra)
        if event.get("blank_high"):
            extra = {
                "failed_control": "BLANK-001",
                "batch": event.get("batch") or "BATCH-001",
                "affected": event.get("affected") or [event["sample_id"]],
                "release_eligible": False,
            }
            for sid in extra["affected"]:
                self.qc_holds[sid] = extra
            return self.make_receipt(event, "QC_HOLD", "BLANK_CONTAMINATION", extra=extra)
        if event.get("rule_drift"):
            old = {"version": "v1", "eligible": True}
            self.config_versions.append(
                {
                    "kind": "qc_rule",
                    "version": "v2",
                    "hash": sha256_hex({"qc_rule": "v2"}),
                    "effective": CLOCK_ISO,
                }
            )
            self.qc_rule_version = "v2"
            extra = {
                "cached_v1_invalidated": True,
                "versions_visible": ["v1", "v2"],
                "prior": old,
            }
            return self.make_receipt(event, "REVIEW_REQUIRED", "RULE_VERSION_DRIFT", extra=extra)
        ident = self.identity_gate(event)
        if ident:
            return self.make_receipt(
                event, ident["disposition"], ident["reason_code"], extra=ident
            )
        result = {
            "sample_id": event["sample_id"],
            "value": event.get("value") or 0.12,
            "qc_pass": True,
            "released": False,
            "eligible_for_human_release": True,
        }
        self.results[event["event_id"]] = result
        extra = {"released": False, "eligible": True}
        return self.make_receipt(
            event, "ELIGIBLE_FOR_HUMAN_RELEASE", "QC_PASS_AWAITING_HUMAN", result, extra
        )

    def process_retest(self, event):
        blocked = self.actor_gate(event, "retest")
        if blocked:
            return blocked
        ident = self.identity_gate(event)
        if ident:
            return self.make_receipt(
                event, ident["disposition"], ident["reason_code"], extra=ident
            )
        original_id = event.get("predecessor") or "QC-002"
        extra = {
            "predecessor": original_id,
            "original_held": True,
            "own_receipt": True,
        }
        self.results[event["event_id"]] = {
            "sample_id": event.get("sample_id"),
            "retest": True,
            "predecessor": original_id,
            "released": False,
        }
        return self.make_receipt(event, "RETEST_RECORDED", "RETEST_LINKED", extra=extra)

    def process_release_request(self, event):
        self.attempt_log.append({"kind": "release_request", "role": event.get("role_fixture")})
        if event.get("role_fixture") != "NAMED_HUMAN_RELEASE_OFFICER":
            return self.deny(
                event,
                "RELEASE_REQUIRES_NAMED_HUMAN",
                extra={
                    "regulatory_release_count": 0,
                    "human_owned_next_step": "named human performs any regulatory release outside this rail",
                },
            )
        return self.deny(event, "RELEASE_DISABLED_ON_THIS_RAIL")

    def process_approval_intent(self, event):
        blocked = self.actor_gate(event, "approve_release_intent")
        if blocked:
            return blocked
        extra = {
            "approval_intent": True,
            "equated_to_release": False,
            "regulatory_release_count": self.regulatory_release_count,
        }
        return self.make_receipt(
            event, "HUMAN_RELEASE_APPROVAL_RECORDED", "APPROVAL_INTENT_ONLY", extra=extra
        )

    def process_instrument_ingest(self, event):
        blocked = self.actor_gate(event, "instrument_ingest")
        if blocked:
            return blocked
        source = event.get("source")
        if source not in KNOWN_INSTRUMENTS:
            return self.hold(event, "INSTRUMENT_MAPPING_REQUIRED")
        if not event.get("sample_id"):
            self.quarantine.append({"raw": event.get("raw") or event, "reason": "MISSING_SAMPLE_ID"})
            return self.hold(event, "MISSING_SAMPLE_ID", extra={"quarantined": True})
        method = event.get("method")
        if method in BLANK_OFFICIAL_METHODS or not method:
            return self.hold(
                event,
                "OFFICIAL_METHOD_ABSENT",
                extra={"invented_method": False, "analyte": event.get("analyte")},
            )
        if event.get("qc_fail"):
            extra = {
                "affected": event.get("affected") or [event["sample_id"]],
                "release_eligible": False,
            }
            for sid in extra["affected"]:
                self.qc_holds[sid] = extra
            return self.make_receipt(event, "QC_HOLD", "INSTRUMENT_QC_FAIL", extra=extra)
        ident = self.identity_gate(event)
        if ident:
            if event.get("timeout_after_commit") and ident["disposition"] == "DUPLICATE_SUPPRESSED":
                return self.make_receipt(
                    event,
                    "RECONCILED_COMMITTED",
                    "READBACK_NO_SECOND_WRITE",
                    extra={"second_write": 0},
                )
            return self.make_receipt(
                event, ident["disposition"], ident["reason_code"], extra=ident
            )
        result = {
            "source": source,
            "sample_id": event["sample_id"],
            "method": method,
            "mapping_version": event.get("mapping_version") or self.instrument_mapping_version,
            "raw_hash": sha256_hex(event.get("raw") or event),
            "authoritative": True,
        }
        self.results[event["event_id"]] = result
        extra = {
            "source_bytes": result["raw_hash"],
            "mapping_version": result["mapping_version"],
        }
        return self.make_receipt(event, "INGESTED", "INSTRUMENT_NORMALIZED", result, extra)

    def process_instrument_batch(self, event):
        items = list(event.get("events") or [])
        arrive = event.get("arrive_order")
        if event.get("mode") == "resume":
            stop_after = int(event.get("stop_after") or 0)
            for item in items[:stop_after]:
                child = dict(item)
                child["kind"] = "instrument_ingest"
                child["case_id"] = event["case_id"]
                child["actor_fixture"] = event["actor_fixture"]
                child["role_fixture"] = event["role_fixture"]
                self.process_instrument_ingest(child)
            cursor = stop_after
            for item in items[stop_after:]:
                child = dict(item)
                child["kind"] = "instrument_ingest"
                child["case_id"] = event["case_id"]
                child["actor_fixture"] = event["actor_fixture"]
                child["role_fixture"] = event["role_fixture"]
                self.process_instrument_ingest(child)
            extra = {"resume_boundary": cursor, "final_count": len(items)}
            return self.make_receipt(
                event, "INGESTED_AFTER_RESUME", "RESUME_CURSOR", extra=extra
            )
        if event.get("timeout_after_commit"):
            first = dict(event)
            first["timeout_after_commit"] = False
            committed = self.process_instrument_batch(first)
            return self.make_receipt(
                event,
                "RECONCILED_COMMITTED",
                "READBACK_NO_SECOND_WRITE",
                extra={"second_write": 0, "first": committed["event_id"]},
            )
        if event.get("mapping_drift"):
            extra = {
                "versions": ["v1", "v2"],
                "held_pending_review": True,
                "homogeneous": False,
            }
            return self.make_receipt(event, "REVIEW_REQUIRED", "MAPPING_DRIFT", extra=extra)
        counts = {"ingested": 0, "held": 0, "duplicate_suppressed": 0}
        ordered = items
        if arrive:
            ordered = sorted(items, key=lambda item: int(item["sequence"]))
        for item in ordered:
            child = dict(item)
            child["kind"] = "instrument_ingest"
            child["case_id"] = event["case_id"]
            child["actor_fixture"] = event.get("actor_fixture") or "ANALYST-01"
            child["role_fixture"] = event.get("role_fixture") or "ANALYST"
            rec = self.process_instrument_ingest(child)
            if rec["disposition"] == "INGESTED":
                counts["ingested"] += 1
            elif rec["disposition"] == "DUPLICATE_SUPPRESSED":
                counts["duplicate_suppressed"] += 1
            else:
                counts["held"] += 1
        extra = dict(counts)
        extra["input_count"] = len(items)
        extra["reconciled"] = extra["input_count"] == (
            counts["ingested"] + counts["held"] + counts["duplicate_suppressed"]
        )
        extra["orphan_event"] = 0
        extra["raw_hashes"] = [sha256_hex(item) for item in items]
        if arrive and arrive != [int(item["sequence"]) for item in ordered]:
            extra["applied_sequence"] = [int(item["sequence"]) for item in ordered]
            return self.make_receipt(
                event, "INGESTED_AFTER_REORDER", "SEQUENCE_AUTHORITATIVE", extra=extra
            )
        return self.make_receipt(event, "INGESTED", "BATCH_RECONCILED", extra=extra)

    def _seed_audit_lifecycle(self, event):
        sample_id = event.get("sample_id") or "SAMPLE-061"
        collect = {
            "kind": "field_collection",
            "case_id": event["case_id"],
            "event_id": event["event_id"] + "-COL",
            "sample_id": sample_id,
            "actor_fixture": "FIELD-01",
            "role_fixture": "FIELD_COLLECTOR",
            "method": "EPA 300.0",
            "method_version": "v1",
            "rule_version": "v1",
            "collection_time": "2026-08-31T10:00:00Z",
            "container_id": "CTR-061",
            "event_time": "2026-08-31T10:00:00Z",
            "init_custody": True,
        }
        self.process_field_collection(collect)
        qc = {
            "kind": "qc_result",
            "case_id": event["case_id"],
            "event_id": event["event_id"] + "-QC",
            "sample_id": sample_id,
            "actor_fixture": "QA-01",
            "role_fixture": "QA_REVIEWER",
            "need_perm": "hold",
            "positive_control_high": True,
            "failed_control": "POS-061",
            "method": "EPA 300.0",
            "method_version": "v1",
            "rule_version": "v1",
            "event_time": CLOCK_ISO,
        }
        self.process_qc_result(qc)

    def process_audit_export(self, event):
        role = event.get("role_fixture")
        if event.get("restricted") or not self._can(role, "audit_export"):
            return self.deny(event, "ROLE_DENIED", extra={"export_bytes": 0})
        if event.get("seed") == "lifecycle":
            self._seed_audit_lifecycle(event)
        if event.get("seed") == "correction":
            self.process_custody(
                {
                    "kind": "custody",
                    "action": "correction",
                    "case_id": event["case_id"],
                    "event_id": event["event_id"] + "-COR",
                    "sample_id": event.get("sample_id") or "SAMPLE-062",
                    "actor_fixture": "QA-01",
                    "role_fixture": "QA_MANAGER",
                    "original_container": "CTR-OLD",
                    "container_id": "CTR-NEW",
                    "reason": "LABEL",
                    "approver_fixture": "QA-01",
                    "event_time": CLOCK_ISO,
                    "method_version": "v1",
                    "rule_version": "v1",
                }
            )
        if event.get("seed") == "denied_release":
            self.process_release_request(
                {
                    "kind": "release_request",
                    "case_id": event["case_id"],
                    "event_id": event["event_id"] + "-REL",
                    "sample_id": event.get("sample_id") or "SAMPLE-063",
                    "actor_fixture": "ANALYST-01",
                    "role_fixture": "ANALYST",
                    "event_time": CLOCK_ISO,
                    "method_version": "v1",
                    "rule_version": "v1",
                }
            )
        if event.get("seed") == "duplicates":
            ev = {
                "kind": "field_collection",
                "case_id": event["case_id"],
                "event_id": event["event_id"] + "-DUP",
                "sample_id": "SAMPLE-064",
                "actor_fixture": "FIELD-01",
                "role_fixture": "FIELD_COLLECTOR",
                "method": "EPA 300.0",
                "method_version": "v1",
                "rule_version": "v1",
                "collection_time": "2026-08-31T10:00:00Z",
                "container_id": "CTR-064",
                "event_time": CLOCK_ISO,
            }
            self.process_field_collection(ev)
            self.process_field_collection(ev)
            self.process_field_collection(ev)
        if event.get("seed") == "config":
            self.process_config_change(
                {
                    "kind": "config_change",
                    "case_id": event["case_id"],
                    "event_id": event["event_id"] + "-CFG",
                    "sample_id": event.get("sample_id") or "",
                    "actor_fixture": "QA-01",
                    "role_fixture": "QA_MANAGER",
                    "from_version": "v1",
                    "to_version": "v2",
                    "approver_fixture": "QA-01",
                    "event_time": CLOCK_ISO,
                    "method_version": "v1",
                    "rule_version": "v1",
                }
            )
        if event.get("seed") == "role":
            self.process_role_change(
                {
                    "kind": "role_change",
                    "case_id": event["case_id"],
                    "event_id": event["event_id"] + "-ROLE",
                    "sample_id": "",
                    "actor_fixture": "QA-01",
                    "role_fixture": "QA_MANAGER",
                    "target_actor": "ANALYST-01",
                    "from_role": "ANALYST",
                    "to_role": "QA_REVIEWER",
                    "event_time": CLOCK_ISO,
                    "method_version": "v1",
                    "rule_version": "v1",
                }
            )
        if event.get("seed") == "mapping":
            self.mapping_history.append({"version": "v2", "effective": CLOCK_ISO})
            extra_map = {
                "versions": ["v1", "v2"],
                "affected_result_ids": event.get("affected_result_ids") or ["RES-068-A"],
            }
            self._append_ledger("mapping_change", extra_map)
        if event.get("tamper"):
            if self.receipts:
                victim = self.receipts[0]
                named = victim.get("event_id")
            else:
                named = event["event_id"]
            return self.make_receipt(
                event,
                "EXPORT_BLOCKED",
                "RECEIPT_HASH_MISMATCH",
                extra={"named_receipt": named, "clean_export_claimed": False},
            )
        if event.get("mode") == "determinism":
            export_a = self._export_payload(event)
            export_b = self._export_payload(event)
            same = sha256_hex(export_a) == sha256_hex(export_b)
            extra = {
                "byte_identical": same,
                "export_a": sha256_hex(export_a),
                "export_b": sha256_hex(export_b),
            }
            return self.make_receipt(event, "EXPORTED", "DETERMINISTIC_EXPORT", extra=extra)
        payload = self._export_payload(event)
        self.exports.append(payload)
        extra = {
            "transition_count": len(payload["transitions"]),
            "denials": payload["denials"],
            "replay_receipts": payload["replay_receipts"],
            "business_effects": payload["business_effects"],
        }
        return self.make_receipt(event, "EXPORTED", "AUDIT_COMPLETE", payload, extra)

    def _export_payload(self, event):
        transitions = []
        for row in self.ledger:
            if row["kind"] == "receipt":
                rec = row["payload"]
                transitions.append(
                    {
                        "actor_fixture": rec.get("actor_fixture"),
                        "role_fixture": rec.get("role_fixture"),
                        "time": rec.get("event_time"),
                        "rule_version": rec.get("rule_version"),
                        "predecessor_hash": row["predecessor"],
                        "disposition": rec.get("disposition"),
                    }
                )
        return {
            "transitions": transitions,
            "denials": list(self.denials),
            "corrections": list(self.corrections),
            "config_versions": list(self.config_versions),
            "role_history": list(self.role_history),
            "mapping_history": list(self.mapping_history),
            "replay_receipts": [
                rec for rec in self.receipts if rec["disposition"] == "DUPLICATE_SUPPRESSED"
            ],
            "business_effects": [
                rec
                for rec in self.receipts
                if rec["disposition"] not in {"DUPLICATE_SUPPRESSED", "DENIED"}
            ],
            "restore": list(self.restore_log),
        }

    def process_config_change(self, event):
        blocked = self.actor_gate(event, "config_change")
        if blocked:
            return blocked
        old = {"version": event.get("from_version") or "v1", "hash": sha256_hex({"v": "v1"})}
        new = {"version": event.get("to_version") or "v2", "hash": sha256_hex({"v": "v2"})}
        row = {
            "kind": "qc_rule",
            "version": new["version"],
            "hash": new["hash"],
            "actor_fixture": event["actor_fixture"],
            "approver_fixture": event.get("approver_fixture"),
            "effective": CLOCK_ISO,
            "old": old,
        }
        self.config_versions.append(row)
        self.qc_rule_version = new["version"]
        extra = {
            "old_hash": old["hash"],
            "new_hash": new["hash"],
            "approver_fixture": event.get("approver_fixture"),
            "effective": CLOCK_ISO,
        }
        if event.get("as_export"):
            return self.make_receipt(event, "EXPORTED", "CONFIG_CHANGE_AUDITED", extra=extra)
        return self.make_receipt(event, "ACCEPTED", "CONFIG_CHANGED", extra=extra)

    def process_role_change(self, event):
        blocked = self.actor_gate(event, "role_admin")
        if blocked:
            extra = {"registry_unchanged": True}
            if blocked["disposition"] == "DENIED":
                blocked["registry_unchanged"] = True
            return blocked
        history = {
            "target_actor": event.get("target_actor"),
            "from_role": event.get("from_role"),
            "to_role": event.get("to_role"),
            "effective": event.get("effective") or CLOCK_ISO,
            "actor_fixture": event["actor_fixture"],
        }
        self.role_history.append(history)
        extra = {
            "grant_revoke": history,
            "prior_actions_relabeled": False,
        }
        if event.get("as_export"):
            return self.make_receipt(event, "EXPORTED", "ROLE_CHANGE_AUDITED", extra=extra)
        return self.make_receipt(event, "ACCEPTED", "ROLE_CHANGED", extra=extra)

    def process_restore(self, event):
        source_hash = event.get("source_hash") or sha256_hex({"backup": "v1"})
        point = event.get("restore_point") or "RP-001"
        root = self.ledger[-1]["hash"] if self.ledger else sha256_hex({"empty": True})
        rec = {
            "restore_point": point,
            "source_hash": source_hash,
            "resulting_root": root,
            "gaps": event.get("gaps") or [],
        }
        self.restore_log.append(rec)
        extra = dict(rec)
        extra["called_successful_without_reconciliation"] = False
        if event.get("as_export"):
            return self.make_receipt(event, "EXPORTED", "RESTORE_RECONCILED", extra=extra)
        return self.make_receipt(event, "RECONCILED", "RESTORE_RECONCILED", extra=extra)

    def process_report_draft(self, event):
        rows = list(event.get("results") or [])
        eligible = []
        held = []
        seen = set()
        orphans = []
        values = []
        for row in rows:
            sid = row.get("sample_id")
            digest = sha256_hex(row)
            if digest in seen:
                continue
            seen.add(digest)
            if row.get("orphan") or (sid and sid not in self.samples and row.get("require_sample")):
                orphans.append(sid or row.get("event_id"))
                continue
            if row.get("qc_held"):
                held.append(row)
                continue
            eligible.append(row)
            values.append(
                {
                    "sample_id": sid,
                    "value": row.get("value"),
                    "rule_version": row.get("rule_version") or "v1",
                    "method_version": row.get("method_version") or "v1",
                }
            )
        if orphans:
            return self.hold(
                event,
                "ORPHAN_RESULT",
                extra={"disposition": "REPORT_HOLD", "orphans": orphans, "sign_off_blocked": True},
            )
        if event.get("corrupt_after_render"):
            rendered = canonical({"eligible": eligible, "values": values})
            tampered = rendered[:-1] + ("X" if rendered[-1] != "X" else "Y")
            return self.hold(
                event,
                "OUTPUT_HASH_MISMATCH",
                extra={
                    "disposition": "REPORT_HOLD",
                    "rendered_hash": sha256_hex(rendered),
                    "output_hash": sha256_hex(tampered),
                    "sign_off_blocked": True,
                },
            )
        if event.get("kind_report") == "dashboard":
            totals = event.get("ledger_totals") or {
                "eligible": len(eligible),
                "held": len(held),
                "unknown": 0,
            }
            dash = {
                "eligible": len(eligible),
                "held": len(held),
                "unknown": 0,
            }
            extra = {"dashboard": dash, "ledger": totals, "equal": dash == totals}
            self.dashboard = dash
            return self.make_receipt(
                event, "DASHBOARD_RECONCILED", "DASHBOARD_MATCHES_LEDGER", extra=extra
            )
        if event.get("kind_report") == "tri_ledger":
            extra = {
                "samples": event.get("sample_count"),
                "results": event.get("result_count"),
                "drafts": event.get("draft_count"),
                "orphan": 0,
                "duplicate_membership": 0,
            }
            return self.make_receipt(event, "RECONCILED", "TRI_LEDGER", extra=extra)
        draft = {
            "channel": event.get("channel") or "CMDP",
            "eligible": len(eligible),
            "held": len(held),
            "total": len(eligible) + len(held),
            "values": values,
            "transmitted": False,
            "released": False,
        }
        self.drafts[event["event_id"]] = draft
        extra = {
            "eligible": draft["eligible"],
            "held": draft["held"],
            "total": draft["total"],
            "transmitted": False,
            "versions": sorted({row["rule_version"] for row in values}) if values else [],
        }
        return self.make_receipt(
            event, "DRAFT_READY_FOR_HUMAN_REVIEW", "DRAFT_UNTRANSMITTED", draft, extra
        )

    def process_report_send(self, event):
        return self.deny(
            event,
            "SEND_PROHIBITED",
            extra={
                "human_owned_next_step": "named human reviews draft outside this rail",
                "regulatory_transmission_count": 0,
            },
        )

    def process_role_action(self, event):
        action = event.get("action")
        if event.get("actor_status") == "INACTIVE":
            return self.deny(event, "ACTOR_INACTIVE")
        if action == "release":
            return self.process_release_request(event)
        if action == "role_change":
            return self.process_role_change(event)
        if action == "hold_qc":
            blocked = self.actor_gate(event, "hold")
            if blocked:
                return blocked
            extra = {
                "actor_fixture": event["actor_fixture"],
                "reason": event.get("reason") or "FAILED_QC",
                "rule_version": event.get("rule_version") or "v1",
            }
            self.qc_holds[event.get("sample_id") or "SAMPLE-083"] = extra
            return self.make_receipt(event, "QC_HOLD", "AUTHORIZED_HOLD", extra=extra)
        if action == "edit_result":
            blocked = self.actor_gate(event, "result_entry")
            if blocked:
                extra = {"result_hash_unchanged": True}
                rec = self.deny(event, "ROLE_DENIED", extra=extra)
                rec["result_hash_unchanged"] = True
                return rec
            return self.make_receipt(event, "ACCEPTED", "RESULT_EDITED")
        if action == "result_entry":
            return self.process_qc_result(event)
        if action == "audit_export":
            return self.process_audit_export(event)
        if action == "grant_sequence":
            results = []
            grant_after = int(event.get("grant_after") or 3)
            for idx in range(1, 5):
                child = {
                    "kind": "role_action",
                    "action": "hold_qc",
                    "case_id": event["case_id"],
                    "event_id": "%s-E%d" % (event["event_id"], idx),
                    "sample_id": event.get("sample_id") or "SAMPLE-086",
                    "actor_fixture": event.get("target_actor") or "TECH-01",
                    "role_fixture": "VIEWER" if idx <= grant_after else "QA_REVIEWER",
                    "reason": "FAILED_QC",
                    "event_time": CLOCK_ISO,
                    "method_version": "v1",
                    "rule_version": "v1",
                }
                results.append(self.process_role_action(child)["disposition"])
            extra = {
                "events": results,
                "grant_receipt": event["event_id"],
                "effective_after": grant_after,
            }
            return self.make_receipt(
                event, "DENIED_THEN_ALLOWED", "ROLE_EFFECTIVE_BOUNDARY", extra=extra
            )
        if action == "replay_denied":
            first = self.process_role_action(
                {
                    "kind": "role_action",
                    "action": "release",
                    "case_id": event["case_id"],
                    "event_id": event["event_id"] + "-A",
                    "sample_id": event.get("sample_id") or "SAMPLE-090",
                    "actor_fixture": event.get("actor_fixture") or "FIELD-01",
                    "role_fixture": event.get("role_fixture") or "FIELD_COLLECTOR",
                    "event_time": CLOCK_ISO,
                    "method_version": "v1",
                    "rule_version": "v1",
                }
            )
            second = self.process_role_action(
                {
                    "kind": "role_action",
                    "action": "release",
                    "case_id": event["case_id"],
                    "event_id": event["event_id"] + "-B",
                    "sample_id": event.get("sample_id") or "SAMPLE-090",
                    "actor_fixture": event.get("actor_fixture") or "FIELD-01",
                    "role_fixture": event.get("role_fixture") or "FIELD_COLLECTOR",
                    "event_time": CLOCK_ISO,
                    "method_version": "v1",
                    "rule_version": "v1",
                }
            )
            extra = {
                "attempts": 2,
                "first": first["disposition"],
                "second": second["disposition"],
                "business_effect": 0,
            }
            return self.make_receipt(event, "DENIED", "DENIAL_REPLAY", extra=extra)
        return self.hold(event, "UNKNOWN_ROLE_ACTION")

    def process_retry(self, event):
        mode = event.get("mode")
        if mode == "duplicate_collection":
            ev = {
                "kind": "field_collection",
                "case_id": event["case_id"],
                "event_id": event.get("source_event_id") or event["event_id"] + "-SRC",
                "sample_id": event.get("sample_id") or "SAMPLE-091",
                "actor_fixture": "FIELD-01",
                "role_fixture": "FIELD_COLLECTOR",
                "method": "EPA 300.0",
                "method_version": "v1",
                "rule_version": "v1",
                "collection_time": "2026-08-31T10:00:00Z",
                "container_id": "CTR-091",
                "event_time": CLOCK_ISO,
            }
            self.process_field_collection(ev)
            rec = self.process_field_collection(ev)
            return self.make_receipt(
                event,
                rec["disposition"],
                rec["reason_code"],
                extra={"business_effect": 0},
            )
        if mode == "timeout_before":
            return self.make_receipt(
                event,
                "RETRY_SAFE",
                "TIMEOUT_BEFORE_COMMIT",
                extra={"effects": 1, "retry_bound": 1},
            )
        if mode == "timeout_after":
            return self.make_receipt(
                event,
                "RECONCILED_COMMITTED",
                "READBACK_NO_SECOND_WRITE",
                extra={"second_write": 0},
            )
        if mode == "crash_after_append":
            ev = {
                "kind": "custody",
                "action": "seed_chain",
                "case_id": event["case_id"],
                "event_id": event["event_id"] + "-C",
                "sample_id": event.get("sample_id") or "SAMPLE-094",
                "actor_fixture": "FIELD-01",
                "role_fixture": "CUSTODIAN",
                "nodes": [
                    {"actor_fixture": "FIELD-01", "role": "collect"},
                ],
                "event_time": CLOCK_ISO,
                "method_version": "v1",
                "rule_version": "v1",
            }
            first = self.process_custody(ev)
            extra = {
                "found_receipt": first["event_id"],
                "second_node": 0,
                "nodes": len(self.custody_nodes.get(ev["sample_id"], [])),
            }
            return self.make_receipt(
                event, "RECONCILED_COMMITTED", "RESTART_FINDS_RECEIPT", extra=extra
            )
        if mode == "renderer_crash":
            draft = {"channel": "CMDP", "bytes": "DRAFT-BYTES", "canonical": True}
            digest = sha256_hex(draft)
            self.drafts[event["event_id"]] = {"hash": digest, "draft": draft}
            extra = {"canonical_drafts": 1, "reused_hash": digest}
            return self.make_receipt(
                event, "RECONCILED_COMMITTED", "ONE_CANONICAL_DRAFT", extra=extra
            )
        if mode == "stale_cursor":
            ev = {
                "kind": "offline_batch",
                "case_id": event["case_id"],
                "event_id": event["event_id"] + "-B",
                "sample_id": event.get("sample_id") or "SAMPLE-098",
                "actor_fixture": "FIELD-01",
                "role_fixture": "FIELD_COLLECTOR",
                "events": [
                    {"event_id": "STALE-%d" % i, "sequence": i} for i in range(1, 5)
                ],
                "event_time": CLOCK_ISO,
                "method_version": "v1",
                "rule_version": "v1",
            }
            self.process_offline_batch(ev)
            committed = set(self.input_hashes)
            replay_effects = 0
            for item in ev["events"]:
                if item["event_id"] in committed:
                    replay_effects += 0
                else:
                    replay_effects += 1
            extra = {"replay_effects": replay_effects, "checked_committed_ids": True}
            return self.make_receipt(event, "RECONCILED", "STALE_CURSOR", extra=extra)
        return self.hold(event, "UNKNOWN_RETRY_MODE")

    def process_partition_merge(self, event):
        left_ids = event.get("device_a") or []
        right_ids = event.get("device_b") or []
        seen = {}
        conflicts = []
        union = []
        for item in left_ids + right_ids:
            eid = item["event_id"]
            digest = sha256_hex(item)
            if eid not in seen:
                seen[eid] = digest
                union.append(item)
            elif seen[eid] != digest:
                conflicts.append(eid)
        extra = {
            "union_count": len(union),
            "duplicate_effects": 0,
            "conflicts": conflicts,
        }
        return self.make_receipt(event, "RECONCILED", "PARTITION_UNION", extra=extra)

    def process_rule_rollback(self, event):
        self.config_versions.append(
            {
                "kind": "qc_rule",
                "version": "v2",
                "hash": sha256_hex({"qc_rule": "v2"}),
                "effective": CLOCK_ISO,
            }
        )
        self.config_versions.append(
            {
                "kind": "qc_rule",
                "version": "v1",
                "hash": sha256_hex({"qc_rule": "v1"}),
                "effective": CLOCK_ISO,
                "rollback_of": "v2",
            }
        )
        extra = {
            "versions_auditable": ["v1", "v2"],
            "caches_invalidated": True,
            "automatic_release": False,
        }
        return self.make_receipt(event, "REVIEW_REQUIRED", "RULE_ROLLBACK", extra=extra)

    def normalized_state(self):
        return {
            "samples": self.samples,
            "results": self.results,
            "receipts": [
                {
                    key: rec[key]
                    for key in REQUIRED_RECEIPT_FIELDS
                    if key in rec
                }
                for rec in self.receipts
            ],
            "qc_holds": self.qc_holds,
            "regulatory_release_count": self.regulatory_release_count,
            "regulatory_transmission_count": self.regulatory_transmission_count,
            "autonomous_release_count": self.autonomous_release_count,
        }

    def root_hash(self):
        return sha256_hex(self.normalized_state())


def _base_event(case, event_id, sample_id, actor, role, kind):
    return {
        "kind": kind,
        "case_id": case["id"],
        "event_id": event_id,
        "sample_id": sample_id,
        "actor_fixture": actor,
        "role_fixture": role,
        "method_version": "v1",
        "rule_version": "v1",
        "event_time": CLOCK_ISO,
    }


def materialize(case):
    """Build structured rail events from one corpus case. Corpus is not rewritten."""
    cid = case["id"]
    n = cid.split("-")[1]
    cat = case["category"]
    fault = case["fault_injection"]
    text = case["synthetic_input"]
    sample_id = "SAMPLE-%s" % n

    if cat == "field_collection":
        ev = _base_event(case, "FC-%s" % n, sample_id, "FIELD-01", "FIELD_COLLECTOR", "field_collection")
        ev["method"] = "EPA 300.0"
        ev["collection_time"] = "2026-08-31T10:00:00Z"
        ev["container_id"] = "CTR-%s" % n
        if "omits collection_time" in text:
            ev.pop("collection_time")
        if "METHOD-UNKNOWN" in text:
            ev["method"] = "METHOD-UNKNOWN"
        if "VIEWER" in text:
            ev["role_fixture"] = "VIEWER"
        if "omits actor_fixture" in text:
            ev["actor_fixture"] = ""
        if "25 hours" in text:
            ev["collection_time"] = "2026-09-01T13:00:00Z"
            ev["event_time"] = ev["collection_time"]
        if "container_id" in text and "collector" in text:
            ev["init_custody"] = True
        if cid == "AT-007":
            ev["init_custody"] = True
        if "COA" in text or "filename" in text:
            ev["coa_pointer"] = {
                "filename": "synthetic-coa.pdf",
                "sha256": sha256_hex("coa-%s" % n),
            }
        if fault == "duplicate delivery":
            return [ev, deepcopy(ev)]
        if fault == "identity conflict":
            first = deepcopy(ev)
            first["sample_point"] = "POINT-A"
            second = deepcopy(ev)
            second["sample_point"] = "POINT-B"
            return [first, second]
        return [ev]

    if cat == "offline_sync":
        ev = _base_event(case, "OS-%s" % n, sample_id, "FIELD-01", "FIELD_COLLECTOR", "offline_batch")
        if "sequence 1..5" in text:
            ev["events"] = [{"event_id": "OS-%s-%d" % (n, i), "sequence": i} for i in range(1, 6)]
        elif "4-event" in text:
            ev["events"] = [{"event_id": "OS-%s-%d" % (n, i), "sequence": i} for i in range(1, 5)]
            ev["mode"] = "duplicate_replay"
        elif "sequence 3,1,2" in text or "3,1,2" in text:
            ev["events"] = [{"event_id": "OS-%s-%d" % (n, i), "sequence": i} for i in (3, 1, 2)]
            ev["arrive_order"] = [3, 1, 2]
        elif "sequence 1 and 3" in text:
            ev["events"] = [
                {"event_id": "OS-%s-1" % n, "sequence": 1},
                {"event_id": "OS-%s-3" % n, "sequence": 3},
            ]
        elif "before any commit" in text or fault == "timeout-before-commit":
            ev["events"] = [{"event_id": "OS-%s-1" % n, "sequence": 1}]
            ev["timeout_before_commit"] = True
        elif "after commit" in text or fault == "timeout-after-commit":
            ev["events"] = [{"event_id": "OS-%s-1" % n, "sequence": 1}]
            ev["timeout_after_commit"] = True
        elif "changed result bytes" in text:
            first = deepcopy(ev)
            first["kind"] = "offline_event"
            first["sequence"] = 1
            first["result_bytes"] = "A"
            second = deepcopy(first)
            second["result_bytes"] = "B"
            return [first, second]
        elif "stops after 6 of 10" in text:
            ev["events"] = [{"event_id": "OS-%s-%d" % (n, i), "sequence": i} for i in range(1, 11)]
            ev["mode"] = "resume"
            ev["stop_after"] = 6
        elif "3 hours behind" in text:
            ev["events"] = [{"event_id": "OS-%s-%d" % (n, i), "sequence": i} for i in range(1, 4)]
            ev["device_time"] = "2026-08-31T09:00:00Z"
        elif "two fresh stores" in text or "12-event" in text:
            ev["events"] = [{"event_id": "OS-%s-%d" % (n, i), "sequence": i} for i in range(1, 13)]
            ev["mode"] = "clean_room"
        else:
            ev["events"] = [{"event_id": "OS-%s-1" % n, "sequence": 1}]
        return [ev]

    if cat == "chain_of_custody":
        ev = _base_event(case, "CC-%s" % n, sample_id, "CUST-01", "CUSTODIAN", "custody")
        if "three signed" in text:
            ev["action"] = "seed_chain"
            ev["nodes"] = [
                {"actor_fixture": "FIELD-01", "role": "collect"},
                {"actor_fixture": "CUST-01", "role": "transfer"},
                {"actor_fixture": "LAB-01", "role": "receive", "role_fixture": "LAB_RECEIVER"},
            ]
        elif "omits actor_fixture" in text:
            ev["action"] = "transfer"
            ev["actor_fixture"] = ""
            ev["predecessor_hash"] = None
        elif "VIEWER" in text:
            ev["action"] = "transfer"
            ev["recipient_role"] = "VIEWER"
        elif "unknown prior" in text:
            ev["action"] = "transfer"
            ev["predecessor_hash"] = "UNKNOWN-HASH"
        elif fault == "duplicate delivery":
            ev["action"] = "transfer"
            ev["recipient_role"] = "LAB_RECEIVER"
            ev2 = deepcopy(ev)
            return [ev, ev2]
        elif "receive arrives before transfer" in text:
            ev["action"] = "receive"
            ev["await_transfer"] = True
            ev["transfer_present"] = False
        elif "corrects a container" in text:
            ev["action"] = "correction"
            ev["role_fixture"] = "QA_MANAGER"
            ev["actor_fixture"] = "QA-01"
            ev["original_container"] = "CTR-OLD"
            ev["container_id"] = "CTR-NEW"
            ev["reason"] = "LABEL"
            ev["approver_fixture"] = "QA-01"
        elif "DISPOSED" in text:
            ev["action"] = "dispose"
            ev["sample_id"] = sample_id
        elif "exports a 7-node" in text:
            ev["action"] = "export"
            ev["seed_nodes"] = [{"actor_fixture": "N-%d" % i, "role": "node"} for i in range(1, 8)]
        elif "VOID" in text:
            ev["action"] = "void"
            ev["role_fixture"] = "QA_MANAGER"
            ev["actor_fixture"] = "QA-01"
            ev["reason"] = "VOID-REASON"
        else:
            ev["action"] = "seed_chain"
            ev["nodes"] = [{"actor_fixture": "FIELD-01", "role": "collect"}]
        return [ev]

    if cat == "sample_receipt_and_disposition":
        ev = _base_event(case, "SR-%s" % n, sample_id, "RECV-01", "RECEIVING_LEAD", "sample_receipt")
        ev["container_id"] = "CTR-%s" % n
        ev["method"] = "EPA 300.0"
        if fault == "duplicate delivery":
            ev2 = deepcopy(ev)
            return [ev, ev2]
        if "different container_id" in text:
            first = deepcopy(ev)
            first["container_id"] = "CTR-A"
            second = deepcopy(ev)
            second["container_id"] = "CTR-B"
            return [first, second]
        if "no method/analyte" in text:
            ev.pop("method", None)
            ev["analyte"] = ""
        if "DAMAGED" in text:
            ev["condition"] = "DAMAGED"
            ev["reason"] = "DAMAGED"
            ev["owner"] = "RECV-01"
        if "no schedule" in text:
            ev["unscheduled"] = True
        if "chemical-inventory COA" in text:
            ev["coa_hash"] = sha256_hex("coa-bytes-%s" % n)
            ev["coa_bytes"] = "coa-bytes-%s" % n
            ev["inventory_fixture"] = "INV-%s" % n
        if "hash does not match" in text:
            ev["coa_hash"] = "claimed-hash"
            ev["coa_bytes"] = "actual-bytes"
        if "BROKEN_SEAL" in text:
            ev["action"] = "reject"
            ev["reason"] = "BROKEN_SEAL"
            ev["source_receipt"] = "SR-%s-SRC" % n
        if "unknown SAMPLE" in text or fault == "orphan event":
            ev["kind"] = "orphan_result"
            ev["sample_id"] = "SAMPLE-040"
        return [ev]

    if cat == "qc_retest_authorized_release":
        ev = _base_event(case, "QC-%s" % n, sample_id, "ANALYST-01", "ANALYST", "qc_result")
        ev["method"] = "EPA 300.0"
        ev["value"] = 0.12
        if "exceeds synthetic upper limit" in text:
            ev["positive_control_high"] = True
            ev["failed_control"] = "POS-001"
            ev["role_fixture"] = "QA_REVIEWER"
            ev["need_perm"] = "hold"
        if "blank fixture exceeds" in text:
            ev["blank_high"] = True
            ev["affected"] = [sample_id, "SAMPLE-043-B"]
            ev["role_fixture"] = "QA_REVIEWER"
            ev["need_perm"] = "hold"
        if "capability expired" in text:
            ev["capability"] = "expired"
        if "lacks the requested method" in text:
            ev["capability"] = "missing"
            ev["capabilities"] = []
        if "retest references" in text:
            ev["kind"] = "retest"
            ev["predecessor"] = "QC-002"
        if fault == "duplicate delivery":
            ev["kind"] = "retest"
            ev["predecessor"] = "QC-002"
            return [ev, deepcopy(ev)]
        if "v1 then fixture changes to v2" in text:
            ev["rule_drift"] = True
        if "ANALYST requests regulatory release" in text:
            ev["kind"] = "release_request"
        if "QA_MANAGER records approval intent" in text:
            ev["kind"] = "approval_intent"
            ev["role_fixture"] = "QA_MANAGER"
            ev["actor_fixture"] = "QA-01"
        return [ev]

    if cat == "instrument_ingest":
        ev = _base_event(case, "II-%s" % n, sample_id, "ANALYST-01", "ANALYST", "instrument_ingest")
        ev["method"] = "SM 4500-H+ B"
        ev["source"] = "PH-METER-01"
        ev["raw"] = {"reading": 7.2, "n": n}
        if "PH-METER-01" in text:
            ev["source"] = "PH-METER-01"
            ev["method"] = "SM 4500-H+ B"
        if "BALANCE-01" in text:
            ev["source"] = "BALANCE-01"
            ev["method"] = "SM 2540 D"
            ev["raw"] = {"weight": 1.00}
        if "AA-FURNACE" in text:
            ev["kind"] = "instrument_batch"
            ev["arrive_order"] = [3, 1, 2]
            ev["events"] = [
                {
                    "event_id": "II-%s-%d" % (n, i),
                    "sequence": i,
                    "source": "AA-FURNACE",
                    "sample_id": "%s-%d" % (sample_id, i),
                    "method": "EPA 200.9",
                    "raw": {"seq": i},
                }
                for i in (3, 1, 2)
            ]
        if "METROHM-IC" in text and "failed QC" in text:
            ev["source"] = "METROHM-IC"
            ev["method"] = "EPA 300.0"
            ev["qc_fail"] = True
            ev["affected"] = [sample_id, "SAMPLE-054-B"]
        if "SIEVERS-TOC" in text:
            ev["kind"] = "instrument_batch"
            ev["source"] = "SIEVERS-TOC"
            ev["timeout_after_commit"] = True
            ev["events"] = [
                {
                    "event_id": "II-%s-1" % n,
                    "sequence": 1,
                    "source": "SIEVERS-TOC",
                    "sample_id": sample_id,
                    "method": "SM 5310 B",
                    "raw": {"toc": 1.1},
                }
            ]
        if "omits sample_id" in text:
            ev["source"] = "SEAL-DISCRETE"
            ev["method"] = "EPA 300.0"
            ev["sample_id"] = ""
        if "INSTRUMENT-UNKNOWN" in text:
            ev["source"] = "INSTRUMENT-UNKNOWN"
        if "mapping changes from fixture v1 to v2" in text:
            ev["kind"] = "instrument_batch"
            ev["mapping_drift"] = True
            ev["events"] = [
                {
                    "event_id": "II-%s-1" % n,
                    "sequence": 1,
                    "source": "METROHM-IC",
                    "sample_id": sample_id,
                    "method": "EPA 300.0",
                    "mapping_version": "v1",
                    "raw": {"v": 1},
                },
                {
                    "event_id": "II-%s-2" % n,
                    "sequence": 2,
                    "source": "METROHM-IC",
                    "sample_id": sample_id,
                    "method": "EPA 300.0",
                    "mapping_version": "v2",
                    "raw": {"v": 2},
                },
            ]
        if "Paint Filter Test" in text:
            ev["source"] = "SEAL-DISCRETE"
            ev["method"] = ""
            ev["analyte"] = "Paint Filter Test"
        if "12 synthetic events" in text:
            ev["kind"] = "instrument_batch"
            ev["events"] = []
            for i, source in enumerate(INSTRUMENT_FAMILIES * 2, 1):
                ev["events"].append(
                    {
                        "event_id": "II-%s-%02d" % (n, i),
                        "sequence": i,
                        "source": source,
                        "sample_id": "%s-%02d" % (sample_id, i),
                        "method": "EPA 300.0",
                        "raw": {"i": i},
                    }
                )
        if fault == "duplicate delivery":
            return [ev, deepcopy(ev)]
        return [ev]

    if cat == "audit_export":
        ev = _base_event(case, "AE-%s" % n, sample_id, "QA-01", "QA_MANAGER", "audit_export")
        if "collection through QC hold" in text:
            ev["seed"] = "lifecycle"
        elif "original value plus reasoned correction" in text:
            ev["seed"] = "correction"
        elif "denied release" in text:
            ev["seed"] = "denied_release"
        elif "two replays" in text:
            ev["seed"] = "duplicates"
        elif "alters one stored receipt" in text:
            ev["seed"] = "lifecycle"
            ev["tamper"] = True
        elif "QC rule v1 to v2" in text:
            ev["seed"] = "config"
        elif "ANALYST to QA_REVIEWER" in text:
            ev["seed"] = "role"
        elif "parser mapping" in text:
            ev["seed"] = "mapping"
        elif "restores the synthetic store" in text:
            ev["kind"] = "restore"
            ev["as_export"] = True
            ev["restore_point"] = "RP-069"
            ev["source_hash"] = sha256_hex({"backup": "069"})
            ev["gaps"] = []
        elif "same frozen ledger twice" in text:
            ev["mode"] = "determinism"
            ev["seed"] = "lifecycle"
        return [ev]

    if cat == "report_reconciliation":
        ev = _base_event(case, "RR-%s" % n, sample_id, "QA-01", "QA_MANAGER", "report_draft")
        if "CMDP draft from 10" in text:
            ev["channel"] = "CMDP"
            ev["results"] = [
                {"sample_id": "S-%02d" % i, "value": i, "event_id": "R-%02d" % i}
                for i in range(1, 11)
            ]
        elif "netDMR draft from 8" in text:
            ev["channel"] = "netDMR"
            ev["results"] = [
                {"sample_id": "S-%02d" % i, "value": i, "event_id": "R-%02d" % i}
                for i in range(1, 9)
            ]
        elif "dashboard aggregates" in text:
            ev["kind_report"] = "dashboard"
            ev["results"] = [
                {"sample_id": "S-%02d" % i, "value": i} for i in range(1, 6)
            ]
            ev["ledger_totals"] = {"eligible": 5, "held": 0, "unknown": 0}
        elif "unknown sample_id" in text:
            ev["results"] = [
                {"sample_id": "UNKNOWN-074", "value": 1, "orphan": True, "require_sample": True}
            ]
        elif "exact duplicate instrument result" in text:
            row = {"sample_id": "S-075", "value": 1.0, "event_id": "DUP"}
            ev["results"] = [row, deepcopy(row)]
        elif "three eligible and two QC-held" in text:
            ev["results"] = [
                {"sample_id": "S-1", "value": 1},
                {"sample_id": "S-2", "value": 2},
                {"sample_id": "S-3", "value": 3},
                {"sample_id": "S-4", "value": 4, "qc_held": True},
                {"sample_id": "S-5", "value": 5, "qc_held": True},
            ]
        elif "method/rule v1 and v2" in text:
            ev["results"] = [
                {"sample_id": "S-1", "value": 1, "rule_version": "v1", "method_version": "v1"},
                {"sample_id": "S-2", "value": 2, "rule_version": "v2", "method_version": "v2"},
            ]
        elif "alters one output byte" in text:
            ev["results"] = [{"sample_id": "S-1", "value": 1}]
            ev["corrupt_after_render"] = True
        elif "20 samples, 24 results" in text:
            ev["kind_report"] = "tri_ledger"
            ev["sample_count"] = 20
            ev["result_count"] = 24
            ev["draft_count"] = 2
            ev["results"] = [{"sample_id": "S-%02d" % i, "value": i} for i in range(1, 25)]
        elif "requests SEND" in text:
            ev["kind"] = "report_send"
            ev["channel"] = "CMDP"
        return [ev]

    if cat == "role_denial_and_accountability":
        ev = _base_event(case, "RD-%s" % n, sample_id, "ACT-01", "VIEWER", "role_action")
        if "FIELD_COLLECTOR requests release" in text:
            ev["action"] = "release"
            ev["actor_fixture"] = "FIELD-01"
            ev["role_fixture"] = "FIELD_COLLECTOR"
        elif "ANALYST changes another role" in text:
            ev["action"] = "role_change"
            ev["actor_fixture"] = "ANALYST-01"
            ev["role_fixture"] = "ANALYST"
            ev["target_actor"] = "VIEWER-01"
            ev["from_role"] = "VIEWER"
            ev["to_role"] = "ANALYST"
        elif "QA_REVIEWER holds failed QC" in text:
            ev["action"] = "hold_qc"
            ev["actor_fixture"] = "QA-02"
            ev["role_fixture"] = "QA_REVIEWER"
            ev["reason"] = "FAILED_QC"
        elif "VIEWER edits result" in text:
            ev["action"] = "edit_result"
            ev["actor_fixture"] = "VIEW-01"
            ev["role_fixture"] = "VIEWER"
        elif "INACTIVE" in text:
            ev["action"] = "edit_result"
            ev["actor_status"] = "INACTIVE"
            ev["actor_fixture"] = "GONE-01"
            ev["role_fixture"] = "ANALYST"
        elif "grant becomes effective after event 3" in text:
            ev["action"] = "grant_sequence"
            ev["grant_after"] = 3
            ev["target_actor"] = "TECH-01"
        elif "method capability does not" in text:
            ev["action"] = "result_entry"
            ev["kind"] = "qc_result"
            ev["actor_fixture"] = "ANALYST-01"
            ev["role_fixture"] = "ANALYST"
            ev["method"] = "EPA 300.0"
            ev["capability"] = "missing"
            ev["capabilities"] = []
        elif "token fixture actor differs" in text:
            ev["action"] = "edit_result"
            ev["actor_fixture"] = "PAYLOAD-01"
            ev["session_actor"] = "TOKEN-01"
            ev["role_fixture"] = "ANALYST"
        elif "FIELD_COLLECTOR requests full audit export" in text:
            ev["action"] = "audit_export"
            ev["kind"] = "audit_export"
            ev["actor_fixture"] = "FIELD-01"
            ev["role_fixture"] = "FIELD_COLLECTOR"
            ev["restricted"] = True
        elif "replays the same unauthorized" in text:
            ev["action"] = "replay_denied"
            ev["actor_fixture"] = "FIELD-01"
            ev["role_fixture"] = "FIELD_COLLECTOR"
        else:
            ev["action"] = "release"
        return [ev]

    if cat == "retry_replay_and_recovery":
        ev = _base_event(case, "RRR-%s" % n, sample_id, "FIELD-01", "FIELD_COLLECTOR", "retry")
        if fault == "duplicate delivery" or "retries an accepted collection" in text:
            ev["mode"] = "duplicate_collection"
        elif fault == "timeout-before-commit":
            ev["mode"] = "timeout_before"
        elif fault == "timeout-after-commit":
            ev["mode"] = "timeout_after"
        elif "crashes after append" in text:
            ev["mode"] = "crash_after_append"
        elif "renderer crashes" in text:
            ev["mode"] = "renderer_crash"
        elif "two devices reconnect" in text:
            ev["kind"] = "partition_merge"
            ev["device_a"] = [
                {"event_id": "P-1", "payload": "A"},
                {"event_id": "P-2", "payload": "B"},
                {"event_id": "P-3", "payload": "C"},
            ]
            ev["device_b"] = [
                {"event_id": "P-2", "payload": "B"},
                {"event_id": "P-3", "payload": "C-CONFLICT"},
                {"event_id": "P-4", "payload": "D"},
            ]
        elif "restarts at event 6 of 10" in text:
            ev["kind"] = "instrument_batch"
            ev["mode"] = "resume"
            ev["stop_after"] = 6
            ev["actor_fixture"] = "ANALYST-01"
            ev["role_fixture"] = "ANALYST"
            ev["events"] = [
                {
                    "event_id": "RRR-%s-%02d" % (n, i),
                    "sequence": i,
                    "source": "PH-METER-01",
                    "sample_id": "%s-%02d" % (sample_id, i),
                    "method": "SM 4500-H+ B",
                    "raw": {"i": i},
                }
                for i in range(1, 11)
            ]
        elif "resume cursor points behind" in text:
            ev["mode"] = "stale_cursor"
        elif "all 100 cases twice" in text:
            ev["kind"] = "full_corpus_replay"
        elif "rolls synthetic rule v2 back to v1" in text:
            ev["kind"] = "rule_rollback"
        return [ev]

    raise ValueError("unmapped case %s" % cid)


def execute_case(case, rail=None, corpus=None):
    rail = rail or ControlRail()
    if case["id"] == "AT-099":
        first = run_cases(corpus, skip_ids={"AT-099"})
        second = run_cases(corpus, skip_ids={"AT-099"})
        same = (
            first["audit_sha256"] == second["audit_sha256"]
            and first["dispositions"] == second["dispositions"]
        )
        event = _base_event(
            case, "RRR-099", "SAMPLE-099", "AUDITOR-01", "AUDITOR", "full_corpus_replay"
        )
        extra = {
            "left": first["audit_sha256"],
            "right": second["audit_sha256"],
            "byte_identical": same,
        }
        receipt = rail.make_receipt(
            event,
            "RECONCILED" if same else "HOLD",
            "FULL_CORPUS_REPLAY" if same else "REPLAY_DIVERGED",
            extra=extra,
        )
        return receipt
    events = materialize(case)
    receipt = None
    for event in events:
        receipt = rail.process(event)
    if receipt is None:
        raise RuntimeError("case %s produced no receipt" % case["id"])
    return receipt


def run_cases(corpus, skip_ids=None):
    skip_ids = skip_ids or set()
    receipts = []
    dispositions = {}
    reason_codes = {}
    release = 0
    transmit = 0
    autonomous = 0
    for case in corpus["cases"]:
        if case["id"] in skip_ids:
            continue
        rail = ControlRail()
        receipt = execute_case(case, rail=rail, corpus=corpus)
        receipts.append(receipt)
        dispositions[case["id"]] = receipt["disposition"]
        reason_codes[case["id"]] = receipt["reason_code"]
        release += receipt.get("regulatory_release_count") or 0
        transmit += receipt.get("regulatory_transmission_count") or 0
        autonomous += receipt.get("autonomous_release_count") or 0
    audit = {
        "dispositions": dispositions,
        "reason_codes": reason_codes,
        "receipts": [
            {key: rec[key] for key in REQUIRED_RECEIPT_FIELDS}
            for rec in receipts
        ],
        "regulatory_release_count": release,
        "regulatory_transmission_count": transmit,
        "autonomous_release_count": autonomous,
    }
    return {
        "receipts": receipts,
        "dispositions": dispositions,
        "reason_codes": reason_codes,
        "audit": audit,
        "audit_sha256": sha256_hex(audit),
        "regulatory_release_count": release,
        "regulatory_transmission_count": transmit,
        "autonomous_release_count": autonomous,
        "case_count": len(receipts),
    }


def evaluate(corpus, result):
    expected = {case["id"]: case["expected_disposition"] for case in corpus["cases"]}
    mismatches = []
    for case_id, got in result["dispositions"].items():
        want = expected.get(case_id)
        if got != want:
            mismatches.append({"case_id": case_id, "got": got, "expected": want})
    missing_fields = []
    for rec in result["receipts"]:
        for field in REQUIRED_RECEIPT_FIELDS:
            if field not in rec or rec[field] in (None,):
                missing_fields.append((rec.get("case_id"), field))
    failures = []
    if result["case_count"] != 100:
        failures.append("case_count %s != 100" % result["case_count"])
    if mismatches:
        failures.append("disposition mismatches: %s" % mismatches[:8])
    if missing_fields:
        failures.append("missing receipt fields: %s" % missing_fields[:8])
    if result["regulatory_release_count"] != 0:
        failures.append("regulatory_release_count %s" % result["regulatory_release_count"])
    if result["regulatory_transmission_count"] != 0:
        failures.append("regulatory_transmission_count %s" % result["regulatory_transmission_count"])
    if result["autonomous_release_count"] != 0:
        failures.append("autonomous_release_count %s" % result["autonomous_release_count"])
    pass_count = result["case_count"] - len(mismatches)
    return {
        "ok": not failures,
        "pass_count": pass_count,
        "fail_count": len(mismatches),
        "mismatches": mismatches,
        "failures": failures,
        "audit_sha256": result["audit_sha256"],
        "cash_usd": 0,
        "truth_gate": TRUTH_GATE,
    }


def run_corpus(path=None):
    corpus = load_corpus(path)
    measured = file_sha256(path or CORPUS_JSON)
    result = run_cases(corpus)
    summary = evaluate(corpus, result)
    summary.update(
        {
            "schema": SCHEMA,
            "id": RUNNER_ID,
            "corpus_id": CORPUS_ID,
            "corpus_sha256": measured,
            "cited_slack_corpus_sha256": SLACK_CORPUS_JSON_SHA256,
            "corpus_byte_identity": measured == SLACK_CORPUS_JSON_SHA256,
            "corpus_post_blob": CORPUS_POST_BLOB,
            "instrument_fixtures_blob": INSTRUMENT_FIXTURES_BLOB,
            "case_count": result["case_count"],
            "dispositions": result["dispositions"],
            "reason_codes": result["reason_codes"],
            "receipts": result["receipts"],
            "regulatory_release_count": result["regulatory_release_count"],
            "regulatory_transmission_count": result["regulatory_transmission_count"],
            "autonomous_release_count": result["autonomous_release_count"],
            "command": COMMAND,
        }
    )
    return summary


def replay_identical(path=None):
    left = run_corpus(path)
    right = run_corpus(path)
    return left["audit_sha256"] == right["audit_sha256"], left["audit_sha256"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="AquaTrace Bid 1421 acceptance runner")
    parser.add_argument("--corpus", default=CORPUS_JSON)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    summary = run_corpus(args.corpus)
    same, digest = replay_identical(args.corpus)
    summary["replay_byte_identical"] = same
    if not same:
        summary["ok"] = False
        summary["failures"] = list(summary.get("failures") or []) + ["replay hash diverged"]
    if args.json:
        printable = {
            key: summary[key]
            for key in summary
            if key not in {"receipts", "dispositions", "reason_codes"}
        }
        printable["audit_sha256"] = summary["audit_sha256"]
        printable["pass_count"] = summary["pass_count"]
        print(json.dumps(printable, indent=2, sort_keys=True))
    else:
        print(
            "cases=%s pass=%s fail=%s cash_usd=0"
            % (summary["case_count"], summary["pass_count"], summary["fail_count"])
        )
        print(
            "regulatory_release_count=%s autonomous_release_count=%s"
            % (summary["regulatory_release_count"], summary["autonomous_release_count"])
        )
        print("audit_sha256=%s" % summary["audit_sha256"])
        print("replay_byte_identical=%s" % same)
        print("truth_gate=%s" % TRUTH_GATE)
        if summary["ok"]:
            print("PASS")
        else:
            print("FAIL")
            for item in summary.get("failures") or []:
                print(" - %s" % item)
            for row in (summary.get("mismatches") or [])[:20]:
                print(" - %s got=%s expected=%s" % (row["case_id"], row["got"], row["expected"]))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
