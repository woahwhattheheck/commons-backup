# RFP clarification-question packet

This module turns an already-retained procurement solicitation/amendment generation plus its landed evidence-gap worklist into a **minimal buyer-safe clarification-question draft for owner review**.

It is deliberately downstream of `revenue/procurement_solicitation_ingest`. It does not parse a second copy of solicitation requirements, infer qualifications, contact a buyer, or submit questions.

## What it adds

The landed procurement ingest owns solicitation/amendment chronology, active requirement lineage, exact source SHA-256 identities, source coordinates, and evidence gaps. This module adds the missing clarification layer:

- a separately source-bound **question deadline** lineage;
- candidate question intents tied to exact upstream gap/source/section identities;
- deterministic suppression when a later buyer-official amendment resolves the same gap+intent;
- deterministic semantic dedupe by explicit `intent_id`;
- a buyer-safe Markdown projection that excludes internal notes and bid-risk analysis;
- a receipt/verifier that replays the recorded generation and separately reports whether the packet is still current **now**.

Question classes are:

- `MANDATORY_AMBIGUITY`
- `SCORED_AMBIGUITY`
- `COMMERCIAL_ASSUMPTION`
- `TECHNICAL_DEPENDENCY`
- `INFORMATIONAL_CURIOSITY`

The only terminal states are:

- `READY_FOR_OWNER_REVIEW`
- `HOLD_DEADLINE_PASSED`
- `HOLD_SOURCE_CONFLICT`

`READY_FOR_OWNER_REVIEW` is not send permission.

## Source contract

`solicitation_pack` is compiled by the existing procurement-ingest authority. Each candidate question must match a real emitted gap and bind the same buyer-official `source_id`, `source_sha256`, and `section_id`. Source/gap drift, killed source generations, invented gaps, or class/gap mismatch fail closed.

Question-deadline rows are retained extraction facts, not a second document parser. They must bind an exact buyer-official source generation/digest and section coordinate. Supersession is explicit and must move forward in official source sequence; unknown/multiple active deadlines or malformed/no-offset time values become `HOLD_SOURCE_CONFLICT`.

The module does **not** claim that an arbitrary text coordinate proves what the source bytes say. Acquisition/extraction custody remains upstream. This layer protects the retained deadline fact from cross-generation/source substitution once that fact is admitted.

The process clock is used for live readiness. Callers cannot supply `now` to `compile_current`. Verification first byte-replays the recorded evaluation instant and then recompiles with the current process clock so a formerly valid packet surfaces `HOLD_DEADLINE_PASSED` after the question window closes.

## Buyer-safe projection

`internal_note` and `bid_risk` never enter `questions.md`. Candidate text marked `buyer_safe=false` is suppressed. Buyer-safe text is also rejected from the projection if it contains obvious email/URL/path or secret/internal markers. This is a narrow leakage fence, not a general secret scanner; inputs must remain approved procurement evidence rather than arbitrary private corpora.

The JSON packet remains an **internal owner-review artifact** and includes `bid_risk` for prioritization. It is not itself a buyer message.

## Five-minute synthetic run

From repository root:

```bash
TMP="$(mktemp -d)"
python -m revenue.rfp_clarification_questions.compiler compile \
  --input revenue/rfp_clarification_questions/fixtures/synthetic_pack.json \
  --out-dir "$TMP/questions"

python -m revenue.rfp_clarification_questions.compiler verify \
  --input revenue/rfp_clarification_questions/fixtures/synthetic_pack.json \
  --packet "$TMP/questions/packet.json" \
  --markdown "$TMP/questions/questions.md" \
  --receipt "$TMP/questions/receipt.json"

cat "$TMP/questions/questions.md"
```

Outputs are create-exclusive. Existing output files, symlink/fifo/non-regular input, or tampered packet/Markdown/receipt are refused.

## Authority ceiling

Every emitted authority flag is false. This module authorizes none of the following:

- buyer/partner/customer email, Slack, DM, call, portal or form action;
- clarification-question submission;
- Muse request;
- proposal submission, signature, price commitment, or contract acceptance;
- award/payment/cash/revenue assertion or mutation.

If a human later elects to send one of these questions, perform a fresh pursuit-specific collision/DNR census and obtain Muse single-writer arbitration immediately before the outbound action. Do not infer that from this packet.
