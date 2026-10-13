# Partner Workshare Conversion Data Room

This product turns a source-bound opportunity + proposed prime/specialist split into a deterministic owner-review packet. It is built for the moment between "there is a credible teaming seam" and "a human is ready to negotiate it": capability slices, evidence, role allocation, exclusions, access/security dependencies, pricing basis, acceptance questions, and exact blockers travel together rather than being scattered across chat threads.

The compiler can emit only `READY_FOR_OWNER_REVIEW` or `HOLD`. Its commercial state is always `PROPOSED_NOT_ACCEPTED`. Readiness is internal evidence readiness only: every external-send, buyer/partner-acceptance, submission, contract, invoice, payment, cash, and revenue authority flag is hard-false.

## Evidence rules

Risk-bearing claims (`QUALIFICATION`, `CERTIFICATION`, `REFERENCE`, `SECURITY`, `PRICING`, `LEGAL`, `STAFFING`) need current retained evidence from a primary authority (`BUYER_OFFICIAL`, `PARTNER_OFFICIAL`, `OWNER_VERIFIED`, or `SIGNED_RECORD`). Future or expired evidence holds. A `SUPPORTED` claim without evidence holds. Capability slices depending on proposed claims hold. Required assumptions and `PROVEN` security/access requirements need current evidence. Proposed pricing needs a current retained `OWNER_PRICING_AUTHORITY` record; otherwise the packet holds.

Input is strict JSON: duplicate keys, unknown fields, bool-as-int, non-finite numbers, malformed IDs/hashes/URLs, conflicting workshare ownership, duplicate assignments, and dangling refs fail closed. Lists are normalized by stable IDs, so logically identical input ordering produces byte-identical output.

## CLI

```bash
python -m revenue.partner_workshare_conversion_data_room.cli compile INPUT.json OUT
python -m revenue.partner_workshare_conversion_data_room.cli verify INPUT.json OUT.packet.json OUT.packet.md OUT.receipt.json
```

Compile uses create-exclusive outputs and refuses overwrite. Verify performs a full semantic recompile and byte-compares JSON, Markdown, and receipt; changing content and resealing one digest is insufficient.

## Demo

`example.json` is synthetic. Run the two commands above. The example is intentionally `READY_FOR_OWNER_REVIEW`, but that state still does not authorize a send or prove acceptance/payment/revenue.
