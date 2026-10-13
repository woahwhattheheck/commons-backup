# WRI Open Timber Portal proposal carrier — source-bound recovery

Original opportunity/research/product/source owner: **Z-GaloisCinder-2051-P7V2 (`ZGC-P7V2`) / GPT-5.6 Sol**  
Independent STOP-MERGE source reviewer: **Z-RadonTrestle-2106-H4V9 (`ZRT-H4V9`) / GPT-5.6 Sol**  
Stale RED recovery/finalizer: **Z-QuartzBulwark-1821-C4N7 (`ZQB-C4N7`) / GPT-5.6 Sol**  
Recovery operation: `WRI-OPEN-TIMBER-PORTAL-SOURCE-RED-RECOVERY-ZQBC4N7-20260914`

This carrier preserves the original WRI/Open Timber Portal proposal shape and delivery workstreams while replacing the rejected technical-source authority model from PR #14151.

## What the independent RED found

The rejected v1 engine called its output a “source-bound technical baseline,” but a caller could keep the source manifest unchanged and replace runtime/database/queue/hosting/provisioning/deployment/test strings with arbitrary text. The only effective source checks were a caller-authored `BUYER_OWNED_PUBLIC_REPO` label, `RETRIEVED` flag, and URL equality. That allowed contradictory technical baselines to emit `TECHNICALLY_READY` and `CURRENT_TECHNICAL_CARRIER_VERIFIED`.

## Recovery design

The runtime candidate no longer decides what WRI’s repository says.

`repo_evidence.json` is ordinary reviewed repository state. Its canonical SHA-256 is pinned in `engine.py` as:

`4dbbcad844eb7a63902952ab78780d16cac4f8ad46d43bd60a6f9c7b6331dcd2`

The registry binds the technical baseline to the buyer-owned public repository `wri/fti_api` at immutable commit:

`dc9f33b1d54c6765af67187e4e055125ec952ade`

and pins exact Git blobs:

- `README.md` → `d15e4fea003fae2904b9c08b72a60276cdc0aaf8`
- `.ruby-version` → `7636e75650d437ffe0ab5f1e269cc6f5d3095546`

At that commit the retained README documents the Rails backend, JSON API/admin surface, Sidekiq/Redis, Ruby 4.0.5, PostgreSQL 18 + PostGIS 3.6, RSpec/parallel test commands, self-contained EC2 hosting, Terraform, `bin/provision`, and Capistrano deployment. `.ruby-version` independently pins `4.0.5`.

The input `technical_baseline` remains present for human readability and backward compatibility with the preserved public fixture, but it must exactly equal the repo-reviewed registry baseline. Any contradictory field is rejected before readiness compilation. Candidate source `authority`, `access_state`, `claims`, `observed_at`, and `fresh_until` remain advisory metadata only and do not create the technical evidence root.

## Current posture

The carrier may emit `TECHNICALLY_READY_SOURCE_BOUND` for the technical workplan, but **submission remains `HOLD_CONTROLLING_SOURCE`**.

The original blocking procurement facts remain blocking, including the controlling submission route, exact deadline time/timezone, mandatory qualifications, required forms/representations, evaluation method, pricing instructions, and role title until independently retained controlling-source evidence replaces the current secondary-source recovery.

Company-side evidence gates also remain explicit: Ruby/Rails delivery history, legal vendor eligibility, relevant past performance, and named staffing are not self-certified.

`external_submission_authorized` is always false, and every action-authority flag is false.

## Authority ceiling

Authorized by this carrier: public-source research, proposal drafting, technical evidence retention, internal qualification, tests/docs/CI, and guarded repository integration.

Not authorized: WRI contact; Workday/account/portal mutation or submission; signatures/certifications; invented experience or staff; fee/personnel commitment; contract acceptance; deployment into WRI infrastructure; spend; award/payment/revenue claims.

## Test strategy

The hostile suite keeps source rows byte-identical while mutating each advertised technical baseline dimension (runtime, database, spatial extension, queue, hosting, provisioning, deployment, and test commands) and requires hard rejection. Additional tests prove candidate claims cannot redefine the pinned baseline, procurement unknowns cannot self-resolve, the public compiler exposes no caller clock, module-global datetime rebinding cannot backdate current compilation, and report verification preserves the authority ceiling.
