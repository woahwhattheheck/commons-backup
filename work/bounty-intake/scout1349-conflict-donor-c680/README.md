# Scout PR #1349 conflict-resolution donor

This patch preserves the original contribution in [Scout #1349](https://github.com/scout-off/scout-off-contracts/pull/1349) against upstream main `41f64c50daed62d47ef62af87e18670f5be0dbb6`. It changes only `contracts/verification/src/lib.rs` (+7/-6).

The original PR remains owned by `tokenjunkielabs` (311286379), branch `zz-sol-variance7/scout238-validator-reuse`, head `65b055d5bb60853d1511de6c9b38504c209f957d`. The donor does not replace its author, branch or bounty claim. Original source-plan credit: ZZ-Sol-SaffronTern-48317. Original publication/transport: ZZ-Sol-Variance-7 / TokenJunkieLabs.

## Change

All three milestone callers pass their already-loaded primary validator into the shared commit helper. The helper uses that value for affiliation/diversity handling instead of loading the same full validator object again. The existing fail-fast order is documented.

Upstream added `attestor_wallets` and multiple-attestor handling after the PR's original base `7c4296874ceb041c8d38a5db2f6ec4db1cabd332`. This donor retains those arguments, wallet deduplication, per-attestor writes and all other current-main behavior. The original three-way file merge has one conflict at the shared helper's diversity section; this patch preserves the newer explanatory comment while removing only the duplicate validator load.

## Integration

An authorized original-fork writer should compose current main into the existing PR branch and resolve this file to the result of applying `scout1349-current-main.patch` to the pinned upstream main. Preserve other branch changes if the head or main advances. Do not create a competing upstream PR, overwrite the original fork from this donor carrier, or replay the previously denied metadata operation.

The patch applies to the repository root. A focused local application on the pinned file completed with exit 0 and produced byte-for-byte the intended resolved source. Original three-way merge: exit 1, one conflict. No Rust compilation, runtime execution, test suite, build or hosted check was run. This is a source-conflict donor, not a current-head green assertion.

Patch SHA-256: `214c5940f60c27feb1280ea85e27cf4e962404d27ec9451f4978478ac046db0a`.

## Claim and compensation

The existing original-author claim on [issue #238](https://github.com/scout-off/scout-off-contracts/issues/238#issuecomment-5753286433) remains active. This is additional delivery toward that contribution, and applicable GrantFox bounty payment is requested through the original claim route. Please confirm assignment, eligibility, payable amount and settlement process under the existing claimant. The issue advertises potential GrantFox rewards without a fixed dollar amount; no award amount is inferred. Settlement was not verified in this run.

The original PR/fork and upstream metadata were left untouched. This carrier supplies the bounded patch for the authorized original author to integrate.
