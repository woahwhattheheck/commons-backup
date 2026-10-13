# World Resources Institute — Open Timber Portal backend consultancy

**Owner-review proposal draft — not yet authorized for submission**

Prepared from the source-bound Open Timber Portal carrier in Commons. The public buyer repository establishes the technical baseline below. The controlling WRI procurement page remains unavailable to the current retriever, so submission route, exact deadline time/timezone, mandatory qualifications/forms, evaluation method, pricing instructions, and formal role title remain unresolved. This draft is intentionally complete on delivery approach and intentionally incomplete where only WRI or owner evidence can establish truth.

## Executive summary

We propose a six-month, evidence-driven maintenance and modernization engagement for the Open Timber Portal (OTP) Rails backend. The delivery model is designed for a live public-interest platform: small reversible changes, reproducible defect evidence, explicit API compatibility notes, regression coverage before release, and a bi-weekly decision cadence with WRI.

The buyer-owned `wri/fti_api` repository is the technical source of truth for this draft. The retained baseline is a Ruby on Rails backend exposing a JSON API and admin interface, with Sidekiq/Redis background processing, PostgreSQL/PostGIS, AWS infrastructure described through Terraform and host provisioning, Capistrano deployment, and RSpec/parallel test paths. We will treat that repository evidence as a starting point rather than a claim about WRI production credentials, access, acceptance, or current private infrastructure.

The engagement is organized around the five work areas already carried in the source-bound opportunity package: reference/runtime updates; performance and security; targeted platform fixes; maintenance and bug solving; and a ranked forward-improvement register.

## Delivery principles

1. **Measure before changing.** Each material change begins with a reproducible baseline, failing case, or source-linked maintenance reason.
2. **Prefer bounded, reversible work.** Runtime, dependency, schema, and deployment changes carry explicit rollback notes and migration evidence.
3. **Keep API behavior observable.** Backend changes that affect API contracts include compatibility notes and concrete request/response examples for coordination with the separate frontend workstream.
4. **Keep release evidence with the change.** Tests, decision notes, deployment state, and rollback instructions travel with the corresponding implementation.
5. **Separate findings from assumptions.** Security, performance, and modernization observations are labeled as measured findings, hardening opportunities, or items requiring WRI confirmation.
6. **Leave a usable handoff.** Completed, deferred, blocked, and proposed work are separated at closeout, with a ranked evidence-linked improvement register.

## Technical baseline

This proposal draft is bound to the reviewed buyer-owned repository evidence already retained in Commons:

- Application: Ruby on Rails backend with JSON API, admin interface, and Sidekiq jobs.
- Runtime: Ruby 4.0.5 in the retained repository evidence.
- Data: PostgreSQL 18 with PostGIS 3.6.
- Queue/cache support: Sidekiq with Redis.
- Hosting/provisioning described in the retained repository: self-contained EC2 hosts, Terraform-managed AWS resources, and `bin/provision`.
- Deployment: Capistrano release path.
- Test paths: `bundle exec rspec` and `bundle exec parallel:spec`.

These are public-repository facts, not representations that Token Junkie Labs currently holds WRI production access, WRI credentials, or authority to deploy.

## Work plan

### Workstream 1 — Reference layers and runtime updates

**Objective.** Keep reference layers and the Rails platform current through small, reversible, source-reviewed upgrades rather than a broad rewrite.

**Proposed activities.**
- Establish a dependency/runtime inventory and an update order with rollback checkpoints.
- Update reference-layer ingestion and validation paths against WRI-approved source fixtures.
- Upgrade gems/runtime components only with focused regression and migration evidence.
- Record any schema or runtime compatibility impact before deployment.

**Acceptance evidence.**
- Before/after dependency and runtime manifest.
- Focused and full RSpec results for affected paths.
- Migration/rollback note for every schema or runtime change.

### Workstream 2 — Performance and security

**Objective.** Measure first, then harden the API, PostGIS queries, background jobs, and host/deploy surface with evidence-bound changes.

**Proposed activities.**
- Profile representative API, PostGIS, and Sidekiq workloads selected with WRI.
- Identify bounded bottlenecks before proposing optimization.
- Review dependency, secret-handling, authentication/authorization behavior, input validation, and deployment controls in source scope.
- Apply prioritized fixes with regression, load, and rollback evidence.

**Acceptance evidence.**
- Reproducible baseline and post-change measurements for WRI-approved scenarios.
- Security finding register separating confirmed issues, hardening opportunities, and non-findings.
- No-regression evidence and rollback steps for each accepted change.

Sensitive findings would use a WRI-approved private disclosure route once the controlling engagement instructions are known.

### Workstream 3 — Targeted platform fixes

**Objective.** Resolve prioritized defects spanning API, admin/back-office, background jobs, and observations-tool interactions without claiming control of the separate frontend codebase.

**Proposed activities.**
- Reproduce each WRI-prioritized defect with a minimal failing test or fixture where feasible.
- Trace the behavior to the smallest responsible backend change.
- Add regression coverage with the fix.
- Coordinate contract changes with the frontend consultant through explicit API examples and compatibility notes.

**Acceptance evidence.**
- Failing-then-passing regression for automatable defects.
- API compatibility note for behavior or schema changes.
- WRI review receipt for UX-affecting behavior that backend tests alone cannot establish.

### Workstream 4 — Maintenance and bug solving

**Objective.** Run a bi-weekly triage-to-merge maintenance loop that keeps urgent fixes bounded, reviewable, and recoverable.

**Proposed activities.**
- Maintain severity, reproducibility, owner, and acceptance state for each incoming issue.
- Reserve capacity for production-facing defects and dependency/security maintenance.
- Keep deploy/runbook changes in the same review stream as the code they affect.
- Record whether each release candidate was deployed, deferred, or blocked.

**Acceptance evidence.**
- Bi-weekly change and decision ledger.
- Issue-to-commit-to-test trace for completed maintenance work.
- Deployment receipt or explicit not-deployed state for every release candidate.

### Workstream 5 — Forward improvement register

**Objective.** Leave WRI with an evidence-ranked backlog instead of an unbounded wishlist.

**Proposed activities.**
- Record modernization, reliability, security, performance, data, and operability opportunities discovered during delivery.
- Score each item by evidence, user/operational impact, effort range, dependency, and rollback risk.
- Separate immediate defects from strategic architecture decisions requiring WRI product ownership.
- Mark every item completed, deferred, blocked, or proposed at closeout.

**Acceptance evidence.**
- Ranked improvement register with an evidence/source link for every recommendation.
- Explicit assumptions and decision owner for unresolved items.
- Final handoff separating completed, deferred, blocked, and proposed work.

## Six-month operating cadence

The current opportunity evidence supports an October-to-March engagement shape and a bi-weekly WRI coordination cadence as secondary-source planning hints, not controlling contractual terms.

- **Kickoff / first cycle:** confirm WRI priorities, authoritative repositories/environments, access model, release procedure, issue backlog, representative performance scenarios, and acceptance owners.
- **Every two weeks:** review priorities, decisions, completed evidence, blocked work, next changes, and release state.
- **Per change:** reproduce or baseline → implement bounded change → focused/full tests as appropriate → compatibility and rollback note → WRI review/release state.
- **Closeout:** hand off completed work, deferred blockers, release/runbook updates, and ranked forward-improvement register.

## Quality, security, and release evidence

For each accepted change, the delivery record should identify the source issue or maintenance reason, changed code, tests executed, observed result, compatibility impact, and rollback/recovery path. Performance work should retain before/after measurement conditions. Security work should distinguish confirmed findings from hardening suggestions and should not publish sensitive production details.

No production deployment is assumed. Deployment would occur only through WRI-owned access and procedures established during the engagement.

## Coordination and handoff

The backend consultant will keep backend/frontend boundaries explicit. API contract changes will include examples and compatibility notes so the frontend consultant can evaluate impact without reverse-engineering implementation details. Bi-weekly reviews will use a short decision ledger: completed, blocked, needs-WRI-decision, and next-priority.

The final handoff will include:
- change and decision ledger;
- test and release evidence for completed work;
- current deploy/runbook notes affected by the engagement;
- unresolved defects and blockers;
- ranked improvement register; and
- explicit separation of deployed, ready-but-not-deployed, deferred, and proposed items.

## Organization, staffing, and past performance

**[OWNER EVIDENCE REQUIRED BEFORE SUBMISSION]**

The current Commons carrier does not establish the bidding legal entity’s WRI vendor eligibility, named staffing, Ruby/Rails delivery history, or referenceable relevant past performance. This draft therefore does not invent biographies, years of experience, client references, certifications, insurance, availability, or staffing commitments.

Before submission, owner evidence must supply and independently review every company/personnel statement required by the controlling RFP.

## Commercial proposal

**[OWNER DECISION + CONTROLLING WRI PRICING INSTRUCTIONS REQUIRED]**

No fee is stated in this draft. Secondary procurement indexes are discovery evidence only and are not authority for a WRI budget ceiling, rate format, reimbursable rules, taxes, or required price schedule. Pricing must be constructed only after the controlling WRI instructions are recovered and the owner selects the actual commercial offer.

## Submission blockers that must be resolved

This draft must not be sent until controlling evidence resolves all of the following:

1. exact submission route, subject line, and delivery method;
2. exact proposal deadline time and timezone;
3. mandatory vendor/developer qualifications and minimum experience;
4. required forms, representations, references, insurance, tax/vendor, conflict, or safeguarding materials;
5. evaluation criteria, weights, interview mechanics, and award basis;
6. pricing instructions, budget/rate structure, reimbursables, tax treatment, and required schedule; and
7. the formal WRI role title for the Rails seat, because secondary indexes conflict even though the buyer-owned repository clearly establishes `fti_api` as the Rails backend.

Company eligibility, staffing, experience, and references remain separate owner-evidence gates even after the controlling procurement packet is recovered.

## Current state

- Technical proposal: **complete for owner review against the retained public-repository baseline**.
- Controlling procurement packet: **not recovered by this carrier**.
- Company evidence: **owner evidence required**.
- Pricing: **owner decision required after controlling instructions**.
- External contact/submission: **not authorized by this artifact**.
- Award/payment/revenue: **not claimed**.

This proposal can be converted rapidly into a sendable response once the controlling WRI packet and owner evidence replace the unresolved fields above.
