# Swarm work router

`tools.swarm_work_router` turns one strict work-item record into a deterministic specialist-channel routing receipt. It exists to reduce two observed fleet failure modes: central-queue dogpiles and publication collisions across different transports.

## Authority ceiling

The router **does not send, post, submit, merge, pay, schedule, or otherwise mutate an external provider**. Every route receipt has `external_publish_authorized=false` and `side_effects_authorized=false`.

When `external_publish=true`, the receipt requires live Muse arbitration in DM `D0C1U7TUZEC` plus a current collision search before a separately authorized sender may mutate a provider. Email, contact form, DM, public post, GitHub external publication, and provider-submission transports do not create separate commercial identities: `publication_key` hashes normalized target + opportunity + purpose and deliberately excludes transport, worker identity, and message wording.

## Routing rules

Specialist channels are primary. `#delegations` and `#awaiting-merge` are **not** catch-all primaries; `#awaiting-merge` is primary only for `kind=merge_review`. Unknown kinds fail closed to `#coordination-channel-created-today-please-use` with `classification=HOLD_CLASSIFICATION_UNKNOWN`.

The current machine registry includes build demand, products/business packs, Hive build families, sales/leads/hot leads, GitHub inbox, feature/integration/bug/math/data-science bounty feeds, international competitions, shipped builds, coordination, todo scratch, and the two central queues.

## Work item

All keys are required and unknown keys fail closed:

```json
{
  "schema": "swarm-work-item/v1",
  "work_id": "ZFATHOM:invoice-desk-001",
  "kind": "product",
  "target": "Acme Incorporated",
  "opportunity": "Invoice reconciliation desk",
  "purpose": "Deliver fixed-scope operations software",
  "value_usd": 15000,
  "external_publish": false,
  "route_family": "none",
  "repository": "woahwhattheheck/smb-showcase-inventory",
  "artifact_scope": "apps/example/**"
}
```

For a prospective publication, set `external_publish=true` and choose one of `email`, `contact_form`, `direct_message`, `github_external`, `provider_submission`, or `public_post`. Internal work must use `route_family=none`.

## CLI

```bash
python -m tools.swarm_work_router.router route work.json
python -m tools.swarm_work_router.router channels
python -m tools.swarm_work_router.router scratch-open work.json > scratch-open.json
python -m tools.swarm_work_router.router scratch-clear work.json scratch-open.json > scratch-clear.json
```

The scratch compiler models the owner-directed `#todo` lifecycle. `CLEAR` requires the exact valid preceding `OPEN` receipt for the same work identity; reopening requires a valid preceding `CLEARED` receipt. The tool emits evidence only; the Slack message itself must still be created/deleted through Slack.

## Channel-registry drift audit

`tools.swarm_work_router.drift` verifies that the static routing policy still resolves against an owner/export-supplied Slack conversation census. It never calls or mutates Slack. A census has this exact shape:

```json
{
  "schema": "swarm-slack-channel-census/v1",
  "generation": "20260915T044600Z",
  "source": "slack_list_user_channels",
  "channels": [
    {
      "id": "C0BTRNE6Y58",
      "name": "build-demand",
      "archived": false,
      "is_member": true,
      "conversation_type": "public_channel"
    }
  ]
}
```

The audit checks every expected route primary/mirror plus `#todo`, the Muse DM, expected IDs/names, membership/archive state, duplicate IDs/names, and the anti-dogpile policy that keeps `#delegations` and `#awaiting-merge` out of ordinary primary routing. Missing, inaccessible, archived, duplicate-ID, or structurally ambiguous routes produce `HOLD`; name drift produces `REVIEW`; a clean census produces `PASS`. The tool does **not** automatically replace a dead route.

```bash
python -m tools.swarm_work_router.drift expected > expected.json
python -m tools.swarm_work_router.drift audit census.json > audit.json
python -m tools.swarm_work_router.drift audit census.json --format markdown > audit.md
python -m tools.swarm_work_router.drift verify audit.json
```

The audit is input-order invariant. JSON rejects duplicate keys recursively, unknown schema fields, invalid types, and over-large census inputs. Audit receipts carry canonical SHA-256 digests, `side_effects_authorized=false`, and a semantic verifier that rejects digest/state/count tamper.

## Verification

```bash
python -m unittest -v tools.swarm_work_router.test_router tools.swarm_work_router.test_drift
python -O -m unittest -v tools.swarm_work_router.test_router tools.swarm_work_router.test_drift
```

Receipts are canonical JSON and carry a SHA-256 over every field except `receipt_sha256`. `verify_receipt()` recomputes the router digest and enforces the no-side-effects ceiling; `verify_audit_receipt()` does the same for channel-drift receipts plus semantic state/count checks.
