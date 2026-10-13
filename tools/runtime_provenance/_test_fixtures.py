import json
from datetime import datetime, timezone
from pathlib import Path


NOW = datetime(2026, 9, 15, 8, 0, 0, tzinfo=timezone.utc)
NOW_TEXT = "2026-09-15T08:00:00Z"
DEPLOYED_AT = "2026-09-15T07:00:00Z"
EVIDENCE_AT = "2026-09-15T07:30:00Z"
PROBE_AT = "2026-09-15T07:45:00Z"
GEN = "deploy:abc123"
SHA_A = "a" * 64
SHA_B = "b" * 64


def proven_record():
    return {
        "runtime_id": "muse.slack.production",
        "provider_ids": {
            "slack_user_id": "U0C0TKRTQHZ",
            "slack_conversation_id": "D0C1U7TUZEC",
        },
        "custodian": "runtime-owner:example",
        "runtime_surface": "service:muse-arbiter",
        "config_location": "config:muse/prod/prompt-v2",
        "deployed_generation": GEN,
        "source_commitment": {"kind": "sha256", "value": SHA_A},
        "config_commitment": {"kind": "sha256", "value": SHA_B},
        "trigger": {"mechanism": "event-loop", "cadence": "event-driven"},
        "authority_surfaces": ["slack:leads", "slack:hot-leads", "gmail:sent-history"],
        "decision_contract": "muse-single-writer-decision/v2",
        "deployment_at": DEPLOYED_AT,
        "evidence_at": EVIDENCE_AT,
        "probe": {
            "suite": "muse-live-hostiles/v1",
            "generation": GEN,
            "observed_at": PROBE_AT,
            "result": "PASS",
        },
        "lifecycle": "DEPLOYMENT_PROVEN",
        "evidence": [
            {
                "kind": "DEPLOYMENT_RECEIPT",
                "ref": "provider:deploy/abc123",
                "observed_at": EVIDENCE_AT,
                "generation": GEN,
            },
            {
                "kind": "BLACK_BOX_PROBE",
                "ref": "probe:muse-live-hostiles/42",
                "observed_at": PROBE_AT,
                "generation": GEN,
            },
        ],
    }


def registry(record=None):
    return {
        "schema": "fleet-runtime-provenance/v1",
        "registry_generation": "test-generation",
        "records": [record or proven_record()],
    }

