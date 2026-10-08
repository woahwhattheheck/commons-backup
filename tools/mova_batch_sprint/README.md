# Mova-style paid sprint planner

An operational **intake → owner/PR reconciliation → build/publish → submit claim → acceptance → settlement** batch lane, modeled on the historical Mova sprint. The historic 15 merged PRs / $1,190 advertised is a throughput reference, **not a receipt of $1,190 paid**.

`plan.py` is Python-standard-library-only and **offline**. It takes a current, preverified snapshot of canonical GitHub issue facts + funding/claim information and creates one deterministic, Slack-ready work-order batch; it never contacts sponsors, claims awards, changes GitHub, touches credentials, or sends Slack messages. The runner/person doing intake must actually verify sources. It is safe for multiple fleet seats to use read-only, but only an identified owner may TAKE or publish each resulting operation.

## Run

```bash
python tools/mova_batch_sprint/plan.py /path/to/current-verified-manifest.json --format slack
python tools/mova_batch_sprint/plan.py /path/to/current-verified-manifest.json --format json --max-builds 8 --per-repo-builds 2 --min-usd 15
```

An October 7 example is distributed separately in the full sprint-planner artifact. It is **not committed to this GitHub branch**. That historical fixture deliberately fails with `INPUT_HOLD` after the configured 6-hour horizon. Supply an independently verified current manifest with fresh `as_of` and `checked_at` fields; never advance timestamps without fetching new provider and sponsor facts. `--format json` is suitable for ingesting as dispatch data. `--format slack` is copy-ready to an internal coordination thread, not an automated post.

## Verified manifest contract

Top level: timezone-aware `as_of`, array `records`. Each record must include:

- `issue_url`: exact HTTPS canonical `github.com/owner/repo/issues/N`, `platform`: `algora|bountyhub|issuehunt|grantfox|proven_payer`, `funding`: `escrow_verified|provider_listed|promised|conditional|unverified`, `funding_url` where provider/sponsor state can be checked, `reward_usd` a USD number or `null` if amount unverified.
- `checked_at`: timezone-aware timestamp of **actual** canonical GitHub + provider census, no more than 6 hours old by default; `issue_state`: `open|closed|unknown`; `eligibility`: `eligible|human_required|assignment_required|unknown|ineligible`; `competition`: `none|ours|other_pr|unknown`.
- `source_state`: `none|building|ready|published`; `pr_url` + `pr_author` mean an actual **upstream sponsor-repository PR** only (the URL must match the owner/repo in `issue_url`). A valid upstream PR overrides an erroneous `none` and prevents duplicate builds. `active_owner` tracks held work. `claim_state`: `unknown|not_submitted|submitted|accepted|rejected|paid`; keep `unknown` unless first-party claim state is observed. Optional `note` is capped at 300 characters.
- **Fork-only original-author source:** provide `source_pr_url` (a PR in a different fork/carrier repository), `source_pr_author`, and `source_state: ready` after actual source completion (or `building` while work remains). Do **not** place fork PR #5 or #7 into `pr_url`: a fork PR is not an upstream submission or a portal claim. The planner routes an eligible `ready` fork to `PUBLISH_EXISTING`, never `VERIFY_CLAIM`; a fork held by a different author routes to `PRESERVE_FOREIGN_PR`. A fork source marked `none` without a sponsor PR, a missing source author, or an upstream URL from the wrong repository fails input validation.

**Important distinctions:** advertised/listed/promise/conditional are **not awards or payments**. `claim_state=paid` is still a **verify-settlement** task until a separate real receiving-rail receipt is checked; there is no inferred earned-total.

**One issue, multiple providers:** the sponsor issue remains the unique BUILD/PUBLISH engineering key, but Algora/BountyHub/IssueHunt listings with a verified original-owner PR retain **independent** `SUBMIT_EXISTING_CLAIM`, `VERIFY_CLAIM`, `AWAIT_ACCEPTANCE`, and `VERIFY_SETTLEMENT` work orders. Each portal operation ID includes the platform and a stable digest of that listing URL, so a second platform cannot silently hide the first one's unpaid claim. Identical repeated listing/action rows are held for reconciliation; a ready source or published PR on one listing blocks fresh duplicate BUILD/PUBLISH on another until the common carrier is verified. A `submitted`, `accepted`, or `rejected` claim without a verified **sponsor** PR is a `CLAIM_SOURCE_HOLD`, **never** permission to start a new build. Fork review PRs are source evidence, not sponsor PRs or claim receipts. These are internal routing decisions, not evidence of registration or award. Conditional GrantFox tickets with no verified USD floor are not blindly scored as $15+ guaranteed, but already-built original-author source still routes to `PUBLISH_EXISTING`. Human-led BountyHub terms must be cleared by an actual eligible contributor before claim submission.

## Operator protocol (repeat for each batch)

1. Gather the actual canonical issue, **all existing upstream and fleet fork PRs**, platform listing, current assignees, policy/eligibility, and original-owner Slack TAKEs. Resolve stale listings against GitHub, not marketplace totals alone. Include a public evidence URL and fresh timestamp for each. Reuse source/PR owners; don't fork the same issue again.
2. Run the planner. `BUILD` admits only no-known-PR, available, eligible work meeting the minimum; the default maximum is eight builds and **two per sponsor repo** per batch. `QUEUED_CAPACITY` is parked for a later fresh recheck, not dropped. `PUBLISH_EXISTING` has priority over fresh engineering. Non-owned PRs go to `PRESERVE_FOREIGN_PR`, not rewriting attribution.
3. Publish the generated internal work orders. The actual fleet coordinator atomically assigns one owner per canonical `owner/repo#number`, advertises it on Slack, and attaches real source refs. An `operation_id` is stable for an issue+action, not a new claim or payment receipt. Focus coding on the acceptance contract; perform only a directly relevant check.
4. Use the connected secondary `tokenjunkielabs` workhorse for permitted routine fork engineering when available; reserve original `woahwhattheheck` for its pre-existing authorship, critical submissions, and fallback only when legitimate. A session without secondary account access must not pretend to have switched. Use exact current heads, preserve concurrent edits, and read back every successful provider write.
5. Distinguish `VERIFY_CLAIM` (unknown claim state, **not** permission to make a duplicate), `SUBMIT_EXISTING_CLAIM` (published original PR, first-party missing claim), `AWAIT_ACCEPTANCE`, and `VERIFY_SETTLEMENT`. Register claims on the correct platform using the **same GitHub account as the PR author** and provider's current timing rules. Never include payment waivers; explicitly preserve earned compensation requests and the original claim record.
6. On rate limit, shared API permission, or provider error, report the exact failure class and bank immutable source only if a valid publisher is not available. No account-hopping to evade a permission denial, no duplicate PRs, and no lost claim. Refresh the queue and take new distinct paid work.

This tool makes **decisions from verified inputs, not verification itself**. It deliberately avoids shadowing the separate Commons first-party underwriter, portal registrar, claim-overlap scanner, and GitHub read coordinator. There are no broad test suites or remote network calls in its run path.
