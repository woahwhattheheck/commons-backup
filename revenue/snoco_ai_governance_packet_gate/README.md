# Snohomish County RFP-26-0791BC packet gate

This package is the **slice-A authority gate** for Snohomish County's `RFP-26-0791BC — AI Governance Solution`.

It does not submit a proposal and it does not treat procurement mirrors as the solicitation.

## Current conclusion

`HOLD_PACKET_REQUIRED`

As of 2026-09-13, the anonymously accessible evidence is enough to prove the solicitation identity, the October 1 proposal deadline, several signature/submission mechanics, and—critically—the document-access boundary. It is **not** enough to build a complete compliance response.

Snohomish County's own supplier guidance says its Purchasing Portal is the only official source for active RFP documents (other than Public Works). The County's current ProcureWare guide says users must be logged in to view/download those documents and that addenda are posted there. Under this carrier's no-login/no-registration boundary, the controlling RFP packet and addenda therefore remain unavailable.

## Official evidence used

1. Snohomish County Purchasing Division legal notice, published 2026-09-04:
   `https://sound.ipublishmarketplace.com/washington/advert/-general_18078`
2. Snohomish County — Info for Suppliers:
   `https://snohomishcountywa.gov/6004/Info-for-Suppliers`
3. Snohomish County — Bids/RFxs Opportunities:
   `https://snohomishcountywa.gov/3706/Purchasing-Portal`
4. Snohomish County — Finding Available Bid or RF Documents in ProcureWare:
   `https://www.snohomishcountywa.gov/DocumentCenter/View/142331/Finding-Available-Bid-or-RF-Documents-in-ProcureWare`
5. Snohomish County ProcureWare public portal:
   `https://snoco.procureware.com/Bids`

Third-party mirrors are retained only as non-assertable discovery evidence. Their technical-scope, clarification-deadline, term, and similar claims stay `PACKET_REQUIRED` until verified in controlling County documents.

## What is currently official enough to rely on

The public legal notice supports these facts:

- solicitation: `RFP-26-0791BC`, **AI Governance Solution**;
- proposals due **October 1, 2026, no later than 1:00 p.m. Pacific Local Time**;
- late submittals are not accepted;
- electronic submittal is preferred;
- electronic proposal first page must be digitally signed by an authorized representative;
- the RFP number should be in the email subject line for identification;
- hard-copy proposal first page requires an original authorized signature;
- hand delivery is accepted only at the County Purchasing Division.

The package intentionally does **not** infer the electronic-submission address, solicitation-specific clarification deadline, scoring, minimum qualifications, references, insurance, pricing form, security/privacy terms, contract term, teaming rules, required forms, page/file limits, or addenda-acknowledgement mechanics.

## Files

- `sources.json` — source/authority registry. Official sources are assertable; mirrors are structurally non-assertable.
- `matrix.json` — 24-control compliance/gap matrix.
- `packet_gate.py` — deterministic fail-closed validator and receipt builder.
- `test_packet_gate.py` — hostile tests for authority escalation, mirror promotion, tamper, unknown fields, missing official support, and false packet completeness.

## Run

```bash
cd revenue/snoco_ai_governance_packet_gate
python3 -m unittest -v test_packet_gate.py
python3 packet_gate.py > receipt.json
python3 packet_gate.py --verify --receipt receipt.json
```

A valid receipt must remain `EVIDENCE_MATRIX_READY_PACKET_BLOCKED / HOLD_PACKET_REQUIRED` while any packet-required control exists.

## Handoff needed to advance

A human/owner who is authorized to register/log in to the County Purchasing Portal must retrieve the exact RFP packet and every current addendum/Q&A artifact. Those raw files should be hashed before requirement extraction. Only after that evidence is ingested should another carrier replace packet gaps with `CONFIRMED_OFFICIAL` controls and make a `TEAMING_BID | NO_BID | HOLD` recommendation.

## Authority ceiling

This package never authorizes portal login, vendor registration, County contact, question submission, pricing commitment, signature, proposal submission, award claims, or revenue recognition.
