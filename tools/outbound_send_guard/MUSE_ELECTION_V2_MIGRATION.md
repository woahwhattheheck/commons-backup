# Canonical Muse publication election v2 — migration and operator runbook

Canonical Muse publication-election v2 landed on `main` through #14878 and was hardened by #14884 and later authority-boundary work. For **new publication elections**, use `tools/outbound_send_guard/muse_election_v2.py` and this runbook.

## Predecessor status

Two predecessor request protocols remain in the repository only for historical verification and forensic reconstruction:

- `muse_election.py` / `MUSE_ELECTION.md` — Z-Anvil / ZANV v1 source lineage;
- `muse_selection_gate.py` / `MUSE_SELECTION_GATE.md` — Z-IronwoodQuarry / ZIQ-K4R9 selection-gate lineage.

**Both predecessor request protocols are superseded for new publication elections.** Do not mint a new v1 request merely because a historical receipt still verifies under its own version. Old receipts are not silently reinterpreted as v2 and retain their original schemas and semantics.

Canonical-v2 source/finalizer lineage is ZIQ-K4R9, with later integration, negative-authority, review, and hardening credit preserved in #14878 and #14884. ZAT-0310 retains the original #15394 migration/runbook and discoverability closeout credit; this successor changes only retained-CI topology after #15394's standalone workflow failed the repository workflow-surface contract.

## What v2 binds

One v2 request binds both collision identity and exact-candidate identity:

- publication collision key: buyer scope, recipient fingerprint, offer scope, route kind;
- exact candidate: claimant, operation, intent digest, body digest, request generation, and public v3 lease binding;
- code-pinned Muse route: user `U0C0TKRTQHZ`, DM `D0C1U7TUZEC`;
- exact deterministic request message;
- complete prior-receipt ledger and relevant competing Muse-DM decision history.

The collision key intentionally excludes claimant and body wording so near-simultaneous workers targeting the same commercial publication collide instead of self-selecting by changing prose.

## Authority ceiling

The repository compiler is not the Slack provider and cannot authenticate a caller-authored snapshot merely because it contains real-looking Slack IDs or timestamps.

Current supported v2 therefore treats raw/caller-provided Muse snapshots as analysis evidence only. Raw terminal `SELECTED` and raw terminal `NOT_SELECTED` do not become positive machine send authority. The current-authority envelope fails closed, clears positive winner/selection authority where required, and keeps `external_send_authorized=false` and `side_effects_authorized=false`.

That does **not** mean operators may skip live Muse arbitration. It means the live Slack decision and the repository evidence compiler are separate trust boundaries until a reviewed provider-authenticated adapter exists. Live-runtime deployment/adapter work is tracked separately (including #14696); closing #14503 does not close or imply completion of that deployment lane.

## Migration from either v1

For every new election:

1. Stop constructing new `muse_election.py` v1 requests and stop constructing new `muse_selection_gate.py` raw-selection requests.
2. Preserve any historical v1 receipt byte-for-byte under its original verifier. Never edit or relabel it as v2.
3. Derive the canonical buyer scope, recipient fingerprint, offer scope, route kind, intent digest, and body digest.
4. Verify the current-worker connector-capability lease independently and carry only its **public v3 binding** into the candidate. Never put the private capability in Slack, GitHub, or candidate JSON.
5. Prepare a v2 request with a unique request id and request generation timestamp.
6. Send the emitted request message unchanged to the pinned Muse DM through the trusted orchestration/provider path.
7. Read a complete provider-side decision window for that publication key, including competing candidates and later cancellation/revocation events.
8. Compile against a complete prior v2 receipt ledger. Missing/incomplete history is a hold, not permission.
9. Treat the repository receipt as coordination evidence only. Immediately before any provider mutation, independently re-run relationship/DNR/route/content gates, prove current-worker lease possession, and perform a fresh provider/mailbox preflight.
10. Consume at most the separately authorized provider mutation. A Muse receipt never proves an email was sent, accepted, paid, or replied to.

## Prepare a v2 request

The supported CLI has no caller-controlled observation clock:

```bash
python -m tools.outbound_send_guard.muse_election_v2 prepare \
  --buyer-scope-sha256 "$BUYER_SHA" \
  --recipient-fingerprint "$RECIPIENT_SHA" \
  --offer-scope-sha256 "$OFFER_SHA" \
  --route-kind EMAIL \
  --intent-sha256 "$INTENT_SHA" \
  --body-sha256 "$BODY_SHA" \
  --claimant Z-EXAMPLE \
  --operation-id EXAMPLE-OP-20260917 \
  --lease-binding public-v3-lease-binding.json \
  --request-id example-20260917-0001 \
  --requested-at 2026-09-17T00:00:00Z \
  > muse-v2-request.json
```

The request artifact contains the deterministic Muse message. Transport that exact message; do not paraphrase it and then claim the resulting response belongs to the original digest.

## Compile and verify analysis evidence

```bash
python -m tools.outbound_send_guard.muse_election_v2 compile \
  --request muse-v2-request.json \
  --snapshot muse-v2-snapshot.json \
  --prior-ledger muse-v2-prior-receipts.json \
  --ledger-complete \
  > muse-v2-receipt.json

python -m tools.outbound_send_guard.muse_election_v2 verify \
  --request muse-v2-request.json \
  --receipt muse-v2-receipt.json
```

Exit behavior remains fail-closed: invalid inputs are errors; negative/hold analysis does not become provider permission. Do not build automation that interprets a parseable receipt as permission to send.

## Required conflict semantics

A complete snapshot/ledger must fail closed for, among other cases:

- two different bodies/workers selected under the same publication key;
- wrong claimant/candidate echo;
- cancellation or revocation after an earlier positive-looking event;
- stale/future/impossible ordering;
- wrong Muse route or arbiter identity;
- conflicting/reused message IDs or receipt replay;
- incomplete prior history;
- caller-authored positive-looking snapshots with no independent provider authentication.

Requester-side hard negatives such as HOLD/WITHDRAW/CANCEL/NO SEND are production evidence that must not be treated as new outbound candidate identity. A future trusted adapter must bind structured canonical identity and generation ordering rather than scrape positive-looking prose.

## Retained validation

Commons keeps its active workflow surface capped. Canonical Muse v2 therefore does **not** add a standalone workflow. Root `test_muse_election_v2_retained.py` is discovered by the existing retained `tests.yml` battery and:

- imports and executes both canonical nested Muse v2 suites in normal Python;
- separately launches both complete suites under `python -O`;
- syntax-compiles the canonical source/test surfaces in memory without creating untracked bytecode in the checkout.

The root bridge itself path-triggers `tests.yml`, so changes to this retained acceptance surface receive hosted execution without creating a 68th workflow. Queued, absent, cancelled, or unknown hosted jobs are never represented as green.