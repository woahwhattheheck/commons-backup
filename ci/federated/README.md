# Federated CI receipt engine

Provider-neutral job manifests, receipts, and reconciliation for Commons host-offload CI.

The muhlnickel is the computer. These files do not activate Cirrus, GitLab, Woodpecker, Oracle, or any other pipe. Provider names are observations, not gates. Unknown providers remain usable manifest targets. A checked-in workflow is not a measured run.

Cite PLUMB/Opus 5 #commons 2026-08-23. Do not remint.

## What is measured here

| provider | in this corpus | meaning |
| --- | --- | --- |
| `local-fixture` | MEASURED | `host_offload/federated_ci.py run-fixture` actually executed the echo shards on the authoring host |
| `github-actions` | FIXTURE/READBACK only | config blob for `.github/workflows/header-census.yml` on `38dad71081c1dc2e458004324046cebf4008c03c` is pinned; no live Actions run URL is claimed |
| `cirrus` `gitlab` `woodpecker` `unknown-lab` | SUPPORTED BY CONTRACT ONLY | legal targets; UNMEASURED |

## Layout

- `schema/` — job manifest, receipt, reconciliation schemas
- `manifests/header-echo.v1.json` — versioned two-shard echo job
- `receipts/` — local-fixture executions plus a GitHub Actions *shape* receipt (`terminal_state=FIXTURE`)
- `github_actions_readback.json` — config/readback card, same claim-boundary style as `ci/provider_readbacks/`
- `reconciliation/example.json` — reconciler output over the checked-in receipts

Engine: `host_offload/federated_ci.py`. Tests: `test_federated_ci.py`. Human page: `federated-ci.html`.

Receipt shape: source SHA, test identity, command envelope, exit code, duration, artifact paths/hashes, provider, run URL (nullable), terminal state. Reconciler findings: EQUIVALENT, MISSING_SHARD, STALE_SOURCE, ARTIFACT_DRIFT, CONTRADICTORY_EXIT, RETRY_LINEAGE, DUPLICATE_RECEIPT, HASH_MISMATCH, CANCELLED, MALFORMED.

Never invent external execution, URLs, quota, success, or failover.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
