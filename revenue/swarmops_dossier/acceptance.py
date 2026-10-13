from __future__ import annotations

import hashlib
import json

from .engine import OUTPUT_SCHEMA, compile_dossier, render_markdown, verify_dossier


def h(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def fixture():
    packet = {
        "schema": "commons.swarmops-dossier/v1",
        "portfolio_id": "commons-swarmops-public-demo",
        "evidence": [
            {
                "capability_id": "guarded-shipping",
                "source_id": "merge-receipt-1",
                "source_kind": "GIT_COMMIT",
                "source_ref": "github:commons#merge1",
                "source_sha256": h("merge1"),
                "observed_state": "LANDED_VERIFIED",
                "observed_at": "2026-09-13T13:00:00Z",
                "freshness_seconds": 86400,
                "prospect_class": "PUBLIC",
                "required": True,
                "claim": "A guarded repository change landed with an immutable source receipt.",
            },
            {
                "capability_id": "deterministic-verification",
                "source_id": "test-receipt-1",
                "source_kind": "TEST_RECEIPT",
                "source_ref": "receipt:test1",
                "source_sha256": h("test1"),
                "observed_state": "TESTED_LOCAL",
                "observed_at": "2026-09-13T13:01:00Z",
                "freshness_seconds": 86400,
                "prospect_class": "PROSPECT_SAFE",
                "required": True,
                "claim": "Focused deterministic verification passed on the exact published source bytes.",
            },
            {
                "capability_id": "hosted-ci",
                "source_id": "ci-run-1",
                "source_kind": "CI_RUN",
                "source_ref": "github-actions:run347",
                "source_sha256": h("ci1"),
                "observed_state": "QUEUED",
                "observed_at": "2026-09-13T13:02:00Z",
                "freshness_seconds": 86400,
                "prospect_class": "PUBLIC",
                "required": False,
                "claim": "A hosted CI run exists but remains queued and is not represented green.",
            },
            {
                "capability_id": "outreach",
                "source_id": "provider-send-1",
                "source_kind": "PROVIDER_RECEIPT",
                "source_ref": "gmail:message1",
                "source_sha256": h("send1"),
                "observed_state": "SENT_NOT_ACCEPTED",
                "observed_at": "2026-09-13T13:03:00Z",
                "freshness_seconds": 86400,
                "prospect_class": "PROSPECT_SAFE",
                "required": False,
                "claim": "An outbound offer has a provider send receipt; no buyer acceptance is inferred.",
            },
            {
                "capability_id": "private-runtime",
                "source_id": "internal-1",
                "source_kind": "TEST_RECEIPT",
                "source_ref": "receipt:internal1",
                "source_sha256": h("internal1"),
                "observed_state": "TESTED_LOCAL",
                "observed_at": "2026-09-13T13:04:00Z",
                "freshness_seconds": 86400,
                "prospect_class": "INTERNAL_ONLY",
                "required": False,
                "claim": "Internal-only runtime evidence.",
            },
        ],
    }
    policy = {"required_capabilities":["guarded-shipping","deterministic-verification"],"max_evidence_age_seconds":86400,"max_rows":100}
    return packet, policy


def main() -> int:
    packet, policy = fixture()
    out = compile_dossier(packet, policy, "2026-09-13T14:00:00Z")
    assert out["schema"] == OUTPUT_SCHEMA
    assert out["evaluation_mode"] == "HISTORICAL_REPLAY"
    assert out["status"] == "HISTORICAL_READY"
    assert out["summary"] == {"DEMONSTRATED":2,"LIMITED":2,"HELD":0,"UNKNOWN":0,"required_capabilities":["deterministic-verification","guarded-shipping"],"missing_required_capabilities":[]}
    assert out["external_truth"] == {"buyer_accepted":False,"paid":False,"revenue_recognized":False}
    assert len(out["what_we_can_show_now"]) == 2
    assert verify_dossier(packet, policy, "2026-09-13T14:00:00Z", out)
    md = render_markdown(out)
    assert "queued" not in md.lower() or "not represented green" not in md.lower()  # projection only shows demonstrated section + counts
    print(json.dumps({"status":out["status"],"summary":out["summary"],"external_truth":out["external_truth"],"receipt_sha256":out["receipt_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
