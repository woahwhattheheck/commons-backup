from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from revenue.partner_conversion_ledger import ledger

D = lambda ch: ch * 64
AT = "2026-09-15T20:30:00Z"


def base_packet(candidate_count: int = 1):
    candidates = []
    for i in range(candidate_count):
        candidates.append(
            {
                "candidate_id": f"cand-{i+1}",
                "org_ref": f"org-{i+1}",
                "route_digest": D(str((i + 1) % 10)),
                "fit_evidence": [{"id": f"fit-{i+1}", "digest": D("a")}],
                "exceptions": [],
                "events": [],
            }
        )
    return {
        "schema": ledger.INPUT_SCHEMA,
        "ledger_id": "ledger-1",
        "opportunities": [
            {
                "opportunity_id": "opp-1",
                "qualification": {
                    "posture": "PARTNER_FIRST",
                    "digest": D("b"),
                    "captured_at": "2026-09-01T00:00:00Z",
                    "valid_until": "2026-12-31T23:59:59Z",
                    "source_refs": [{"id": "src-1", "digest": D("c")}],
                },
                "candidates": candidates,
            }
        ],
    }


def sent(event_id="send-1", at="2026-09-10T12:00:00Z", message="msg-1", thread="thr-1", exception_id=None):
    return {
        "event_id": event_id,
        "type": "SENT",
        "at": at,
        "evidence_digest": D("d"),
        "provider_message_id": message,
        "provider_thread_id": thread,
        "exception_id": exception_id,
    }


def reply(event_id="reply-1", at="2026-09-10T13:00:00Z", message="msg-2", thread="thr-1", reply_class="POSITIVE"):
    return {
        "event_id": event_id,
        "type": "REPLY",
        "at": at,
        "evidence_digest": D("e"),
        "provider_message_id": message,
        "provider_thread_id": thread,
        "reply_class": reply_class,
    }


def handoff(event_id="handoff-1", at="2026-09-10T14:00:00Z"):
    return {
        "event_id": event_id,
        "type": "HANDOFF",
        "at": at,
        "evidence_digest": D("f"),
        "owner_ref": "owner-1",
    }


class PartnerLedgerTestCase(unittest.TestCase):
    def compile(self, packet):
        return ledger._compile_at(packet, AT)

    def state(self, report, candidate_index=0):
        return report["opportunities"][0]["candidates"][candidate_index]["state"]

    def reasons(self, report, candidate_index=0):
        return report["opportunities"][0]["candidates"][candidate_index]["reasons"]
