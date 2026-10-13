# MCC 1017-27 — collaborative AI workspace partner-first pursuit

Status: INTERNAL RESEARCH / PARTNER-FIRST / NO OUTBOUND

Current machine state is intentionally fail-closed:

- current buyer-authoritative package and addenda confirmation: EMPTY
- three mirrored base documents: RECOVERED on 2026-10-03
- direct-prime evidence: EMPTY
- direct-prime readiness: false
- partner candidate Presidio: PUBLIC_FIT_ONLY
- proposed TJLabs workshare: $24,000 fixed / PROPOSED_NOT_ACCEPTED
- partner contact: false
- buyer contact: false
- portal mutation: false
- proposal submission: false
- award/payment/revenue: false

The discovery target is Metropolitan Community College (Kansas City, Missouri) IFB 1017-27, Cloud-Based Collaborative AI Workspace Software. The three named base documents are now recovered unchanged from Bidscope's public document links. The bid package states that bids must arrive before October 5, 2026 at 11:00 AM CT and questions before noon September 25. The previous packet attached a -05:00 offset to the index's 16:00/17:00 values, placing both cutoffs five hours later than the literal base document. The two packet values now match the document's Central time and bind its exact digest.

These are mirrored buyer-authored base files. The current Public Purchase package, addenda and Q&A have not been confirmed, so the recovered records and deadline bindings remain SECONDARY_DISCOVERY in the existing schema. The compiler still reports the current buyer-package gap and unknown current response-window status. See [sources.md](sources.md) for the three download URLs, byte counts, hashes and remaining source step. Experience/reference qualification and the proposed workshare remain unproven.

## Why partner-first

No retained evidence here proves that TJLabs has the indexed five years of qualifying enterprise/higher-ed SaaS/cloud-AI experience or three acceptable higher-education references. The gate therefore cannot reach direct-prime readiness while the controlling buyer package is absent.

Presidio is recorded only as a public-capability candidate. Its current first-party material describes a dedicated education practice, higher-education delivery examples, cloud/data/AI services, and a 2026 University of Michigan AI/data-science collaboration. None of that establishes intent to bid, MCC eligibility, acceptable references, willingness to prime, or acceptance of TJLabs' workshare.

## Carrier

- current_packet.json — source-bound current truth
- research_secondary.json — exact internal snapshot of secondary procurement discovery
- partner_presidio_public_fit.json — exact internal snapshot of first-party public capability facts
- pursuit_gate.py — deterministic compiler/verifier with hard-false external authority
- test_gate.py — hostile proof
- sources.md — authority separation and buyer-package gap
- partner_matrix.md — candidate qualification matrix
- paid_workshare.md — bounded $24k implementation/assurance scope
- decision_checklist.md — exact next gate before any external action

## Run

From repository root:

    python -m unittest -v test_mcc_1017_27_ai_workspace_20260917.py
    python -O -m unittest -v test_mcc_1017_27_ai_workspace_20260917.py
    python -m py_compile revenue/mcc_1017_27_ai_workspace_20260917/pursuit_gate.py revenue/mcc_1017_27_ai_workspace_20260917/test_gate.py test_mcc_1017_27_ai_workspace_20260917.py

Compile the current internal state with an explicit evidence time:

    python revenue/mcc_1017_27_ai_workspace_20260917/pursuit_gate.py revenue/mcc_1017_27_ai_workspace_20260917/current_packet.json --evaluated-at 2026-09-17T21:25:00-04:00

Expected current state: HOLD_MISSING_BUYER_PACKAGE.

## Authority ceiling

This package performs internal research, qualification, workshare planning and evidence checking only. It does not authorize contact, Public Purchase activity, proposal submission, signature, spend, award, payment, cash, or recognized revenue. A future external touch requires a fresh provider/relationship census and a new single-writer arbitration for the exact recipient × opportunity × purpose.
