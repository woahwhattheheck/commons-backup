# Muse provider receipt ledger v1

`muse_provider_receipt_ledger_v1.py` is the independent replay-resistance trust root for canonical Muse publication election v2. It does **not** replace the Slack provider adapter and does **not** authorize an external send. It answers one narrower question: has the fixed provider been re-read and proven to retain the complete, append-only prefix of canonical prior-election receipts for this request generation?

## Fixed provider boundary

The provider identity is code-owned: repository `woahwhattheheck/commons`, ref `refs/heads/muse-provider-receipt-ledger-v1`, manifest `provider/muse_receipt_ledger_v1/manifest.json`, and immutable receipt objects below `provider/muse_receipt_ledger_v1/receipts/<sha256>.json`. The bearer credential is read only from `MUSE_LEDGER_GITHUB_TOKEN`, sent only in the GitHub Authorization header, and is never serialized.

The supported writer has two mutations. `init` creates the fixed ref exclusively from the then-current `main` head and writes generation zero. `append` first verifies the complete remote chain, creates one receipt object plus the next manifest, creates a one-parent commit whose parent is the exact observed ledger head, then updates the fixed ref with GitHub `force=false`. It rereads the ref and the complete chain before returning. The reviewed writer has no force-push mode, arbitrary ref, arbitrary repository, arbitrary path, delete, rewrite, or reset command.

Provider-admin compromise or an out-of-band force rewrite of the fixed ref is outside this application boundary. Inside the reviewed boundary, rollback and forks cannot advance the ref: the new commit must be a direct child of the exact observed head and GitHub must accept a non-force update.

## Complete-prefix verification

`verify_remote_complete_prefix()` derives completeness from provider state, never from a caller boolean. It rereads the fixed current head, requires a non-truncated recursive tree, requires the manifest's declared receipt set to equal the provider tree's receipt set exactly, rereads every retained receipt blob, requires canonical JSON bytes and canonical v2 receipt verification, and then walks every ledger commit back to generation zero. Each generation must be the exact previous prefix plus one entry; generation, `previous_head_sha`, genesis parent, receipt/request uniqueness, selection-evidence uniqueness, and digest-derived object paths are all checked. The verifier rereads the fixed ref again at the end, so a head change during verification fails closed.

This is why a mutable local database, copied manifest, filename, path, receipt self-hash, `--ledger-complete`, omitted provider page, reordered entries, duplicated receipt, cross-generation remint, or stale proof cannot mint completeness. The CLI deliberately has no `--ledger-complete` option.

## Request-bound proof

`build_request_bound_proof(request)` first validates the canonical v2 request and the remote ledger. It refuses a request whose `request_sha256` already exists in the prior-receipt prefix. The resulting proof binds the exact provider head, generation, complete-prefix digest, manifest digest, request SHA, request id, publication key, and candidate generation. `verify_request_bound_proof()` rereads the provider and reproduces the proof exactly; a legitimate later append makes an old proof stale rather than silently current.

The proof can truthfully set only `prior_receipt_ledger_authenticated=true` and `ledger_complete=true`. It hard-codes `terminal_election_authorized=false`, `external_send_authorized=false`, and `side_effects_authorized=false`, while retaining `requires_current_worker_lease_possession=true` and `requires_fresh_provider_preflight=true`.

## Composition with Slack provider evidence

PR #15385 is a separate trust root that authenticates the pinned Slack/Muse observation and deliberately leaves ledger authority false. This product does not modify or race it. Once that adapter is present, `verify_terminal_coordination(request, slack_provider_receipt, ledger_proof)` requires both verifiers to re-read their providers and requires the exact same `request_sha256`, request id, publication key, and candidate SHA. The Slack effective observation must be `SELECTED`. Success means only that terminal Muse **coordination evidence** is current. It still does not authorize a send; current worker lease possession, fresh provider preflight, relationship/DNR/route/content gates, and the actual provider mutation remain independent requirements.

## Commands

Use `python -m tools.outbound_send_guard.muse_provider_receipt_ledger_v1 init` once with the provider credential. Append a verified canonical v2 receipt with `... append --receipt receipt.json`. Produce a current request-bound proof with `... proof --request request.json`. Re-read and verify it with `... verify-proof --request request.json --proof proof.json`.

The checked-in JSON Schema describes the exact manifest/entry/proof shapes. Runtime validation is stricter than schema shape alone because it also verifies provider identity, Git ancestry, canonical bytes, canonical Muse receipt semantics, complete-prefix history, uniqueness, and live remote currentness.

## Tests and authority ceiling

The root `test_muse_provider_receipt_ledger_v1.py` is automatically enrolled by the retained Commons root battery. Run it normally and under `python -O`. Hostiles cover exclusive initialization, immutable receipt reread, request replay, remint, reorder with recomputed local digest, truncated provider tree, concurrent sibling CAS, stale proof after head advance, caller self-hash forgery, exact request/candidate binding, unknown manifest fields, token non-disclosure, and dual-trust-root terminal composition with hard-false send/side-effect authority.

No Slack/Gmail send, Muse request, buyer contact, invoice/payment/revenue mutation, or provider mutation outside the reviewed fixed-ref CAS path is performed by this product.
