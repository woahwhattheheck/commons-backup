# ProofLens durable replay integrity

ProofLens treats DynamoDB as a durable replay store, not as an implicit authority root. A row being present in the table is insufficient to make its evidence, decision, or delivery valid.

## Stored-row contract

Every retained row must contain exactly four DynamoDB string attributes:

- `event_id`
- `evidence_json`
- `receipt_json`
- `delivery`

`evidence_json` and `receipt_json` must use the same canonical JSON serialization emitted by the writer. `delivery` is closed to `RECORDED` or `REVIEW_QUEUED`.

Before a stored event can be returned as a replay or used to recover a human-review delivery, the runtime proves all of the following:

1. the retained DynamoDB partition-key value exactly equals the event ID that the current Lambda invocation queried;
2. the retained evidence is a strict ProofLens evidence packet and its `event_id` recomputes from the full canonical evidence payload;
3. the normalized evidence serializes to the exact writer-form bytes retained in `evidence_json`, preventing integer/float aliases such as `0` versus `0.0` from becoming alternate durable representations;
4. the evidence event ID equals the independently known queried key;
5. the retained receipt semantically recompiles from that evidence under the current declared ProofLens policy contract and serializes to the exact verified writer form;
6. the receipt binds the same event and policy and keeps `external_action_authorized=false`;
7. `REVIEW_QUEUED` is impossible unless the verified receipt decision is `REQUEST_HUMAN_REVIEW`.

Any malformed AttributeValue shape, unknown row field, noncanonical or non-writer-form JSON, invalid evidence, cross-event transplant, resealed wrong decision, wrong policy, external-action claim, or invalid delivery state fails closed before replay return or queue delivery.

## Why the queried key is an independent input

A retained row cannot validate itself merely by containing internally consistent JSON. `_existing()` starts from the event ID freshly computed from the exact current S3/baseline evidence path, performs a strongly consistent DynamoDB lookup for that key, and passes that query key separately into stored-row validation. The stored partition key and retained evidence must both match it.

This matters for collision/race recovery as well: a conditional-put loser must read and validate the winning row against the event ID it attempted to write. A pre-existing or corrupted row cannot silently replace the current evidence generation.

## Human-review recovery boundary

`delivery` is a progress marker, not independent proof that SQS accepted a review message. A retained `REQUEST_HUMAN_REVIEW` receipt is therefore reissued to the FIFO review queue on every valid replay whether the row says `RECORDED` or `REVIEW_QUEUED`. The send uses the exact `event_id` as `MessageDeduplicationId`.

Immediately before SQS, `_deliver_review()` must prove current durable custody rather than trusting the caller's in-memory snapshot. For a `RECORDED` row it conditionally advances `delivery` to `REVIEW_QUEUED` only when the exact canonical `evidence_json` and `receipt_json` still match the packet being delivered. If another invocation already advanced the marker, a strongly consistent read must prove an exact matching `REVIEW_QUEUED` row. In either path the runtime then strongly rereads the current row and requires the same verified evidence/receipt plus `REVIEW_QUEUED` before sending. A missing, deleted, replaced, or semantically changed row fails closed with zero SQS call.

The marker is intentionally advanced before the external send and still does **not** claim that SQS accepted anything. If SQS fails after that reservation, the next valid replay sees the exact `REVIEW_QUEUED` row and reissues the same event-id-deduplicated message. This preserves at-least-once recovery without turning a mutable progress bit into delivery proof.

This design intentionally prevents a poisoned or stale `REVIEW_QUEUED` bit from suppressing a required human-review recovery. It provides at-least-once recovery semantics, not global exactly-once delivery. SQS FIFO deduplication has a finite window, so any downstream human-review consumer must also preserve `event_id` as its durable idempotency key and tolerate a later duplicate with the same event ID.

ProofLens still queues only metadata and never turns a review request into a purchase, shutdown, safety/compliance conclusion, payment, or other high-authority external action.

## Policy evolution

Replay verification deliberately recompiles the retained receipt under the current declared ProofLens policy. A retained row from an incompatible historical policy fails closed rather than being silently trusted. Any future policy migration must be explicit and version-aware; this module does not auto-upgrade or reinterpret historical decisions.

## Authority and deployment ceiling

This repair changes only software integrity around retained replay evidence. It does not deploy AWS resources, incur cloud spend, register for or submit to the competition, establish held-out performance, authorize human conclusions, claim organizer acceptance, claim a prize, move money, or recognize revenue.
