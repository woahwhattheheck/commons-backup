# Revenue Collection Desk

Internal, deterministic collection-state compiler for sanitized retained evidence.

It keeps these facts separate:

- submitted work is not accepted work;
- accepted work does not prove the proposed compensation was agreed or allocated;
- confirmed compensation entitlement is not paid work;
- a provider/email statement that payment was sent is not bank settlement;
- a hosted token balance or reference valuation is not USD cash;
- a sent collection message is not proof of delivery;
- a hard-bounced route is not a successful contact;
- silence never authorizes another collection message.

## Lifecycle

Financial states:

`WORK_SUBMITTED` → `ACCEPTED_AWAITING_PAYMENT` → optionally
`PAYMENT_ASSERTED_HOLD` → `PAYMENT_AVAILABLE` → `SETTLED_CASH`.

`DISPUTED` and `CLOSED_NO_PAY` are explicit alternatives. Direct settlement from an
accepted/asserted state is allowed only when a retained `SETTLED_CASH` event supplies
the exact settlement currency and amount. The compiler never calculates FX or
token-to-USD value.

Compensation-basis evidence is orthogonal to work acceptance. A receipt-bound
`ENTITLEMENT_CONFIRMED` event must carry `entitlement_instrument` and
`entitlement_amount`; the instrument must exactly match the claim and the amount
must be the same exact decimal value. Its source reference/digest and bound economics
are retained as `entitlement_evidence` and folded into `economics_receipt_sha256`.
That prevents a generic acceptance or unrelated compensation receipt from making a
different claim collectible. Without valid bound evidence, accepted work remains
`VERIFY_ENTITLEMENT`, is counted only in
`accepted_unconfirmed`, and cannot enter the collection route. A proposed quote or
merge by itself is not entitlement evidence. Direct retained payment evidence may
still advance the financial lifecycle without this event.

Collection-route events are orthogonal:

- `COLLECTION_CONTACT_SENT` requires confirmed entitlement plus an explicit `cooldown_until`;
- `DELIVERY_CONFIRMED` records delivery evidence but never changes financial state;
- `DELIVERY_BOUNCED` marks the route dead and yields `ROUTE_REPAIR_REQUIRED`;
- `ROUTE_REPAIRED` clears the dead route;
- `COLLECTION_RELEASED` is the explicit retained-evidence generation that can end
  a prior contact DNR. Mere passage of time never does.

## CLI

From a checkout containing this version, use the included fictional example:

```bash
python -m tools.revenue_collection_desk compile tools/revenue_collection_desk/example.json --pretty
python -m tools.revenue_collection_desk queue tools/revenue_collection_desk/example.json
python -m tools.revenue_collection_desk verify tools/revenue_collection_desk/example.json report.json
```

`compile` emits its report to stdout. For `verify`, supply a saved copy of that
report as `report.json`; do not overwrite the ledger. Verification exits 0 for an
exact replay, 1 for a different report, and 2 for invalid input or an I/O error.
`queue` emits Markdown to stdout. No command sends a collection message.

Input is strict JSON: duplicate keys and non-finite constants are rejected; unknown
fields fail closed; amounts are exact positive decimal strings; event timestamps
must be strictly increasing within a claim; source references are opaque bounded
identifiers plus SHA-256 digests, never email bodies or secrets.

Timestamp offsets must normalize to a UTC date in years 1 through 9999. Values
outside that range are invalid input and return the CLI's documented exit 2.

The report sorts claims by `claim_id`, so claim-list order does not change the
receipt. Event order is evidence chronology and is intentionally validated rather
than reordered.

## Exact totals and replay

Receivable buckets are summed separately by instrument; supplied settlements are
summed separately by settlement currency. Aggregation derives enough precision
from the finite input coefficients, finest input exponent and term count to retain
every digit and carry. It runs in a fresh private Decimal context. Caller precision,
rounding, exponent bounds, traps and existing flags cannot change the result or its
receipt, and the caller's context is not mutated. Original amount/evidence strings
remain intact; only aggregate display strings lose insignificant trailing zeros.
There is no float conversion, fixed two-place currency rounding or mixed-currency
sum. Valid amounts can contain large integers and at most 18 fractional places.

Older reports produced by a rounded total will correctly fail exact replay under
this version. Recompile the retained ledger; do not edit totals or relabel an old
receipt as a new one. Reports whose old totals were already exact remain identical
when all other source behavior and input evidence are unchanged.

## Fictional operator rehearsal

```bash
python -m tools.revenue_collection_desk.rehearsal
python -m tools.revenue_collection_desk.rehearsal --json
```

Twelve scenarios call this actual compiler at precisions 3, 28 and 80. The readable
view explains acceptance without compensation, bound/mismatched entitlement,
payment holds, token availability, explicit settlement, delivery/silence, bounced
routes, closed unpaid work, disputes and the large-value lost-cent regression.
The JSON view includes every fictional ledger, observed compiler result, replay
check and tampered-report rejection. Failure exits 1 even under `python -O`.
Neither view writes files or contacts any external service.

The source-bound execution record is [EXECUTION.md](EXECUTION.md). All example
records, counterparties, references and digests are fictional. A deterministic
receipt binds the supplied bytes; it does not authenticate a real source or prove
that money moved. `DONE` alone does not mean paid: inspect financial state and the
explicit `settled_cash_by_currency` field.

## Authority

This package performs no network calls and grants no authority to send email/Slack,
submit claims, create invoices, move money, mutate wallets/banks/providers, or
recognize unsettled cash. `AUTHORITY` is hard-false. Customer/public artifacts
should not expose this internal control surface.


## Exact provider registration audit

`portal-audit` reconciles **already-retrieved** GitHub PRs and first-party
IssueHunt or BountyHub claim inventories. It is a read-only companion to the
collection compiler, not a payout or award authority:

```bash
python -m tools.revenue_collection_desk portal-audit portal-evidence.json --pretty
```

Input schema: `commons.portal_registration_audit/v1`, with two arrays:

- `submissions`: `provider` (`issuehunt` or `bountyhub`),
  `repository` (`owner/repo`), numeric `issue`, GitHub `claimant`,
  canonical GitHub `pr_url`, 40-character `head_sha` and
  `github_state` (`open`, `merged`, `closed`).
- `portal_snapshots`: same provider/repository/issue, canonical HTTPS
  `source_url` pointing at the first-party listing, offset-aware
  `observed_at`, Boolean `complete`, and `claims` containing exact
  `pr_url`, `claimant`, and nullable `awarded` / `is_paid` flags.
  `complete` means the operator actually inspected the entire applicable
  provider inventory, not a cropped search result or partial page.
  Unknown award or payout facts must be `null`, not fabricated `false`.

The audit matches **provider + repository + issue + GitHub author + PR URL**
rather than treating another author's older PR as registration for a later
contribution. It chooses the latest complete, consistent first-party snapshot
for each issue. Missing, partial and conflicting records are `UNKNOWN`.
With a full snapshot, a missing exact PR yields
`GITHUB_SUBMITTED_PORTAL_NOT_REGISTERED` and a stable `portal-reg:`
operation ID. A registered but unawarded claim yields
`PORTAL_REGISTERED_UNAWARDED` only with explicit false award evidence;
positive portal award/paid evidence yields `AWARDED`, **not cash settled**.
`PAID` requires both a portal paid flag and separately supplied
receiving-rail settled evidence (`settlement` object with `status=settled`,
a non-empty `receiving_rail` and supporting `evidence_sha256`). This is an
evidence-reduction convention; the audit cannot authenticate such evidence
itself, and must not be used as the source of financial settlement truth.

### BountyHub multiple listing IDs for one GitHub issue

BountyHub can independently fund the same canonical GitHub issue under two
different listing UUIDs. A GitHub PR or claim present on one listing is **not**
registration, acceptance or payment on the other listing. For each distinct
BountyHub listing being reconciled, supply the optional
`submissions[].portal_source_url` as an exact validated first-party API
detail URL or public page URL. The auditor normalizes both forms to the same
listing UUID, then matches only `portal_snapshots[]` from that UUID.
The same original-author PR may therefore produce two separate provider
registration outcomes and stable, different operation IDs.

For legacy submissions without `portal_source_url`, one unambiguous listing
continues to behave as before. If evidence contains multiple distinct listing
UUIDs for the same provider and GitHub issue, legacy unscoped input returns
`UNKNOWN` with
`multiple_provider_listings_require_source_binding` and **no action**.
A bound source that is missing from the supplied evidence likewise remains
`UNKNOWN`. This prevents a newer but unrelated listing from masquerading as
a complete inventory for the submitted PR. It does not authenticate funding
or award status and does not submit any claim.

### Freshness, BountyHub authority and cross-repository submissions

Use **current first-party evidence**, never a marketplace title or historical
catalog, before asking the original claimant to register an already-submitted PR.
Set top-level `evaluated_at` to the evaluation clock (offset-aware ISO-8601).
Each `submissions[]` must include the retained first-party GitHub
`github_submitted_at` and `github_checked_at`. The GitHub read must be no
earlier than submission. Each `portal_snapshots[]` carries its own provider
`observed_at`; its inventory must be marked `complete: true` only after
inspecting all relevant provider pages. Both last-check timestamps must be
within the default 7,200-second age limit of `evaluated_at`, not in the
future; `max_evidence_age_seconds` is optional and bounded 60–604800.
Missing clocks, stale/future snapshots, provider reads predating the PR,
and closed-unmerged PRs produce `UNKNOWN` and **no registration action**.
The evaluator is offline and deterministic, so it cannot authenticate the
operator-supplied timestamps or refresh the data itself.

IssueHunt URLs intrinsically identify `/r/owner/repo/issues/N`. BountyHub
supports the canonical `https://api.bountyhub.dev/api/bounties/UUID` detail
or an exact `bountyhub.dev/{en/}bounty/view/UUID/slug` listing.
Because that URL alone does **not** identify the GitHub issue, BountyHub
snapshots additionally require `source_issue_url` copied from the **same**
first-party provider detail, equal to the current GitHub issue; without that
binding the result stays `UNKNOWN`. Do not copy an unrelated GitHub issue
link into a snapshot to force registration. A provider's paid or awarded
flag still does not establish cash settlement.

When the canonical PR repository differs from the funded issue repository,
set `submission_repository: "actual-owner/pr-repo"` on the GitHub submission
and retain the exact GitHub PR URL in the provider claim inventory. The
portal parser permits canonical PR URLs from other repositories in that
inventory, but counts registration only when the PR URL **and original-author
claimant** exactly match a separately verified GitHub submission. Without an
explicit matching `submission_repository`, the cross-repository GitHub PR
itself is invalid input, not an invented provider registration. The
operation identity still includes the funded issue repo, issue, claimant and
PR URL. A verified registered PR with nullable award state is reported as
`PORTAL_REGISTERED_AWARD_UNKNOWN`, not as an unregistered submission.
Review the `reason` and `snapshot_observed_at` before taking any action.

Exit `0`: no confirmed registration gaps; `1`: at least one actionable
registration gap; `2`: invalid input or file I/O error. The JSON output has
deterministic `rows`, deduplicated `actionable_registration_gaps` and
`audit_digest`. A GitHub PR alone is not IssueHunt or BountyHub
registration, a pledged creator amount is not a contributor award, and a
BountyHub creator's payment status is not `claims[].isPaid`. Registration
and payout must still be performed and confirmed under the existing
original-author provider account. Re-fetch both GitHub and the relevant
provider inventory before performing any follow-up; this audit never
submits claims, sends contact, or moves funds.
