# Solicitation / amendment ingest

Source-bound ingestion immediately upstream of
`revenue/procurement_response_module_library`. It turns buyer-official
solicitation and amendment captures into:

1. an active requirement set
2. a selector compatible with `procurement-response-modules/solicitation/v1`
3. a deadline / readiness record
4. a human evidence-gap worklist (JSON + Markdown) plus a deterministic receipt

Secondary sources may never create or supersede requirements or deadlines.
Unknown supersession targets, same/later-sequence supersession, duplicate or
cyclic lineage, and two active values for one lineage fail closed. Zero or
multiple active submission deadlines HOLD. OCR / table guesses are not buyer
truth. Attachment IDs, hashes, and source bindings are retained.

`MANDATORY` and `SCORED` requirements are blocking for module selection
(`required: true`). `INFORMATIONAL` remains optional.

`OWNER_REVIEW_READY` is not submission approval. Packet, readiness, gaps, and
receipt hard-code all of these as `false`: proposal, submission, buyer/prime
contact, portal action, signature, certification, price commitment, payment,
and award/revenue recognition.

The included pack is **synthetic demo data only**.

```bash
python -m revenue.procurement_solicitation_ingest.ingest compile \
  --pack revenue/procurement_solicitation_ingest/fixtures/synthetic_pack.json \
  --out-dir /tmp/psi

python -m revenue.procurement_solicitation_ingest.ingest verify \
  --pack revenue/procurement_solicitation_ingest/fixtures/synthetic_pack.json \
  --selector /tmp/psi/selector.json \
  --active-set /tmp/psi/active_set.json \
  --gaps /tmp/psi/gaps.json \
  --markdown /tmp/psi/gaps.md \
  --readiness /tmp/psi/readiness.json \
  --receipt /tmp/psi/receipt.json
```
