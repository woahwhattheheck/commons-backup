# Procurement buyer Q&A answer delta

`revenue.procurement_qa_answer_delta` turns retained **buyer-official clarification Q&A / answer-addendum facts** into exact, source-bound deltas against the landed solicitation active-set and evidence-gap worklist.

The use case is operational: after a buyer publishes answers, the bid team should not reread every Q&A generation and manually rediscover which evidence gap, response module, requirement, or submission deadline changed. This compiler produces a deterministic owner-review worklist while keeping buyer truth and external authority narrow.

## What it trusts

The compiler does **not** parse or interpret a buyer PDF, infer meaning from answer prose, or independently prove that an extracted row reflects source bytes. Acquisition/extraction custody remains upstream.

Instead, the input binds three canonical artifacts already emitted by `revenue/procurement_solicitation_ingest`:

- `procurement-solicitation-ingest/active-set/v1`
- `procurement-solicitation-ingest/gaps/v1`
- `procurement-solicitation-ingest/receipt/v1`

The caller supplies the exact canonical SHA-256 for all three. The receipt must bind the same active-set/gap digests, pack, status, and hard-false authority boundary. Any drift fails closed before buyer-answer processing begins.

Question intents are retained mapping facts. A requirement-bound question must match a real active lineage, section, source id/SHA and emitted upstream gap. Deadline/general questions may omit lineage only for `COMMERCIAL_ASSUMPTION` or `INFORMATIONAL_CURIOSITY`, and still bind the active buyer source generation.

Buyer Q&A rows are admitted structured extraction facts. Every answer binds:

- buyer-official source identity/reference/SHA-256;
- capture timestamp and explicit monotonically ordered source sequence;
- answer id + section coordinate;
- question id + optional requirement lineage;
- an explicit structured effect;
- any explicit after-state fact;
- affected response-module ids.

Free-form `answer_text` is retained for human context but **never parsed to invent an effect**.

## Exact classifications

The only emitted classifications are:

- `CLOSED_GAP` — a mapped upstream gap is explicitly closed;
- `REOPENED_GAP` — a later answer explicitly reopens a previously closed gap;
- `REQUIREMENT_CHANGED` — the same active lineage has an explicit changed structured requirement;
- `DEADLINE_CHANGED` — an explicit buyer answer changes the source-bound active submission deadline;
- `INFORMATIONAL_ONLY` — answer is retained but carries no admitted mutating after-fact;
- `SOURCE_CONFLICT` — chronology, source, mapping, freshness, or structured-effect evidence is unsafe.

A source conflict makes the whole packet `HOLD_SOURCE_CONFLICT`. Otherwise the strongest state is `OWNER_REVIEW_READY`.

## Supersession rules

Later buyer answers do **not** silently overwrite earlier answers.

For a second answer to the same question:

1. `supersedes_answer_id` must name the currently active prior answer;
2. the new answer must come from a strictly later source sequence;
3. both answers must remain on the same question identity;
4. skipped active generations, same-sequence overrides, or unknown targets become `SOURCE_CONFLICT`.

Valid superseded rows remain in `delta.json` with `active=false` and `superseded_by=<answer-id>`. This preserves reconstructable history while owner actions are generated only from active deltas.

`REOPEN_GAP` additionally requires the explicitly superseded active answer to have classified `CLOSED_GAP`.

## Fail-closed conditions

Semantic conflicts become `SOURCE_CONFLICT` + HOLD, including:

- non-buyer-official, stale, or future Q&A sources;
- duplicate source sequences;
- missing explicit answer supersession;
- question/gap/lineage/source/section drift;
- unknown question mappings;
- reopening without a prior closed gap;
- requirement-change lineage drift or a claimed change with no actual structured delta;
- deadline change without a unique upstream deadline or with no actual timestamp delta;
- informational answers carrying mutating after-facts.

Malformed evidence fails immediately, including duplicate JSON keys, non-integer JSON numbers, invalid timestamps/SHA-256 values, duplicate question/answer ids, intent remapping, upstream canonical-byte drift, receipt mismatch, or upstream authority amplification.

## Outputs

Compile emits create-exclusive:

- `delta.json` — exact before/after rows, active/superseded history, classifications, affected module ids, and deterministic owner actions;
- `delta.md` — concise human worklist;
- `receipt.json` — exact input/delta/Markdown digests plus upstream artifact digests and status.

Verification recompiles all three artifacts from the exact input bytes and refuses any difference.

## Synthetic run

The included fixture is synthetic and asserts no real buyer, bid, award, payment, or revenue fact.

```bash
TMP="$(mktemp -d)"
python -m revenue.procurement_qa_answer_delta compile \
  --input revenue/procurement_qa_answer_delta/fixtures/synthetic_pack.json \
  --out-dir "$TMP/delta"

python -m revenue.procurement_qa_answer_delta verify \
  --input revenue/procurement_qa_answer_delta/fixtures/synthetic_pack.json \
  --delta "$TMP/delta/delta.json" \
  --markdown "$TMP/delta/delta.md" \
  --receipt "$TMP/delta/receipt.json"
```

Compile output files are exclusive: existing paths are not overwritten. Inputs/outputs are opened without following symlinks and must be regular files.

## Owner-review actions, not proposal mutation

Actions such as `REBUILD_EVIDENCE_GAP`, `RESELECT_RESPONSE_MODULES`, or `UPDATE_DEADLINE_CONTROL` are worklist instructions for a human/operator. This module does not modify proposal text, select a final answer, change a price, sign, certify, submit, or contact anyone.

## Authority ceiling

Every output hard-codes these false:

- buyer contact;
- email/DM;
- portal/form action;
- clarification submission;
- Muse request;
- proposal submission;
- signature/certification;
- price commitment;
- contract acceptance;
- award claim;
- payment action;
- revenue recognition.

A later real outbound still requires its own current pursuit-specific collision/DNR check and Muse single-writer arbitration immediately before send.
