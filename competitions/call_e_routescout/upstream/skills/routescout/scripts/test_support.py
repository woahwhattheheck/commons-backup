import copy
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("routescout", HERE / "routescout.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

INQUIRY = {
    "schema_version": 1,
    "inquiry_id": "demo-route-001",
    "caller_org": "Example Integrations",
    "target_org": "Example Manufacturing",
    "phone_e164": "+15551234567",
    "region": "US",
    "locale": "en-US",
    "source_url": "https://example.com/procurement",
    "inquiry_kind": "procurement_process",
    "inquiry_reference": "Integration inquiry sent 2026-09-13",
    "inquiry_topic": "Official process for submitting a solicitation clarification",
    "requested_function": "Procurement or solicitation Q&A desk",
    "operator_approved": True,
    "published_business_route": True,
}

def structured(**overrides):
    base = {
        "organization_confirmed": True,
        "consented_to_continue": True,
        "routing_answered": True,
        "department_or_role": "Procurement",
        "channel_type": "email",
        "channel_value": "procurement@example.com",
        "channel_is_business": True,
        "permission_state": "permitted",
        "do_not_contact": False,
        "verbatim_route": "Please send solicitation questions to procurement@example.com and reference RFP-123.",
        "notes": "",
    }
    base.update(overrides)
    return base

def terminal(**overrides):
    base = {
        "id": "call_demo_1",
        "status": "completed",
        "task_completed": True,
        "metadata": {
            "workflow": "routescout",
            "schema_version": "1",
            "inquiry_id": INQUIRY["inquiry_id"],
            "inquiry_digest_sha256": r.inquiry_digest(INQUIRY),
        },
        "recipients": [{"structured_result": structured()}],
        "evidence": ["Recipient said: Please send solicitation questions to procurement@example.com and reference RFP-123."],
    }
    base.update(overrides)
    return base

class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps(self.payload).encode()
