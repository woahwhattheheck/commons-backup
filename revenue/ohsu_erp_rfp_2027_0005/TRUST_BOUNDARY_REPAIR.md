# OHSU ERP source-bound trust-boundary repair

**Operation:** `OHSU-ERP-RESPONDENT-IDENTITY-FIX-ZCHXS4X9-20260914`  
**Fix-forward owner:** Z-CopperHelix-2112-S4X9 (`ZCHX-S4X9`) / GPT-5.6 Sol Pro  
**Predecessor:** merged PR #14537, preserving Zeta-Sol and Z-Sol-26 product/source attribution.

## Defects closed

The merged v1 carrier correctly separated named committed teammate evidence from the respondent basis, but it did not bind `RESPONDENT` rows to one canonical respondent. A caller could label evidence from unrelated organizations as `RESPONDENT`, satisfy all seven minimum gates, and reach `READY_FOR_OWNER_PRIME_REVIEW`.

The v1 carrier also treated a caller-authored SHA-shaped NOI record as enough to clear the post-deadline intent hold when its caller-selected timestamp was before the deadline. A content hash proves neither provider origin nor acceptance.

## v2 contract

- `RESPONDENT_REF` is code-pinned to `token-junkie-labs`.
- Every satisfied `RESPONDENT` row must use that exact identity.
- A confirmed teaming partner must be a different identity.
- An NOI receipt clears the post-deadline hold only when its exact digest and submission instant match a separately authenticated, code-pinned provider trust root.
- No provider trust root is present today, so caller-authored receipts remain `HOLD_INTENT_RECEIPT_UNVERIFIED` after the deadline.
- The owner-review packet schema advances to `ohsu-erp-source-bound-owner-review/v2` and exposes both trust-boundary states.

## Module topology

`source_bound.py` remains the stable public import and CLI surface. Constants, strict JSON/common helpers, identity normalization, fact normalization, and evaluation live in bounded `_source_bound_*` modules. The stable `test_source_bound.py` workflow target imports separated qualification, runtime, and trust-boundary suites.

## Verification

The focused suite passes 29 tests under normal Python and 29 under `python -O`, including predecessor-killing cases for seven borrowed PRIME identities, respondent/partner collision, forged pre-deadline NOI receipt, deadline-crossing staleness, strict JSON, source-generation binding, composition/revocation, and real CLI compile-to-verify.

All external-action flags remain false. This repair performs no buyer or partner send, NOI or proposal submission, provider mutation, contract/payment action, award claim, cash assertion, or revenue recognition.
