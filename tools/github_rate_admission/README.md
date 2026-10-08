# GitHub admission ledger (single shared host)

A **no-network, no-credential** optional safety/admission layer for workers that share one GitHub identity and one machine. Its SQLite `BEGIN IMMEDIATE` transactions keep competing same-resource writers from starting simultaneously and keep at most four same-account operations in flight by default. Every operation must have a stable **unique operation ID**. An operation ID is **never** automatically replayed, even after settlement, and an expired reservation becomes `unknown` until its actual provider effect has been reconciled.

## Use with a shared cloud VM

All *same-host* publisher agents must use the **same** `--db` path on a local filesystem that supports SQLite locking/WAL (not NFS, SMB, or a network-mounted SQLite database). This is **not a cross-VM lock service**. Separate cloud hosts require the existing central publisher/operation journal or another authoritative shared service. If the publisher already has a canonical operation journal, preserve that and treat this local ledger as admission only. It never selects credentials, changes GitHub identities, submits claims, contacts sponsors, or changes payouts.

`account` is the verified GitHub actor (e.g. `woahwhattheheck`); `bucket` is its provider quota group (e.g. `github-app`); `resource` is a stable action+target key (e.g. `create_pull_request:Centurylong/sanctifier:339`). Different resources can proceed concurrently up to `--max-inflight` without duplicate same-resource writes. Avoid running tools at all after `acquire` denies admission.

```sh
DB=/var/lib/commons/github-rate-admission.db
python3 tools/github_rate_admission/admission.py --db "$DB" acquire --account woahwhattheheck --bucket github-app --resource create_pull_request:Centurylong/sanctifier:339 --operation GF-SANCTIFIER339-ONCE
# Only after admitted:true, make one provider call with that same operation ID.
# When the provider specifically responds HTTP 403 "Resource not accessible by integration":
python3 tools/github_rate_admission/admission.py --db "$DB" observe --account woahwhattheheck --bucket github-app --resource create_pull_request:Centurylong/sanctifier:339 --event GF339-HTTP403-001 --operation GF-SANCTIFIER339-ONCE --http-status 403 --message 'Resource not accessible by integration'
python3 tools/github_rate_admission/admission.py --db "$DB" settle --operation GF-SANCTIFIER339-ONCE --outcome no-effect
python3 tools/github_rate_admission/admission.py --db "$DB" status --account woahwhattheheck --bucket github-app
```

A **primary GitHub quota-exhaustion** response such as HTTP 403 `API rate limit exceeded for user ID ...` is `PRIMARY_LIMIT`, **not** a secondary/abuse throttle. `observe --reset-epoch <integer>` optionally accepts the provider's actual `X-RateLimit-Reset` UTC Unix timestamp; if it is later than the observation time, the account-wide gate lasts until at least that timestamp (or later `Retry-After`). If the response has **no future provider reset timestamp** (including a missing or already-past header), the primary-quota gate remains **indefinite** (`until_epoch: null`) instead of recycling the secondary throttle's estimated 300-second backoff. Even a `Retry-After` value alone does not prove primary quota recovery. Independently verify restored quota from the provider, then use the audited `clear-gate --resource '*' --reason 'provider quota confirmed recovered ...'` operation before admitting more work. A later throttling observation must not silently shorten an indefinite hold. Never fabricate a reset timestamp. `status` exposes both the classification and exact `until_epoch`, preserving fleet visibility. This applies per verified account + quota bucket; the tool does not change identities or bypass exhausted account quotas. An observation ID remains idempotent.

For explicit secondary-limit response (`HTTP 403` **with secondary-limit text** or `429`), `observe` opens an **account-wide** timed gate, honoring larger provider `Retry-After` seconds or a bounded 5/10/20/40/60-minute escalating backoff. Duplicated `--event` IDs do not increase strikes. On expiry, another admission is allowed, but no previously used operation ID can be replayed. An App installation permission 403 creates an **indefinite target-specific** gate. An unclassified 403 also requires reconciliation; `401` blocks the account bucket. A pre-provider tool/harness denial records evidence but does not burn a GitHub quota token or create a gate.

A focused test for the primary-reset boundary can be run against `classify`, `observe`, and `acquire` with a fresh in-memory SQLite `SCHEMA` and fixed observation time: primary 403 should produce `PRIMARY_LIMIT` and an account gate until its observed reset; a distinct operation must be denied before the reset and may be admitted after it, whereas secondary-limit, App-permission and generic 403 classifications remain unchanged. A separate test-file publication was blocked before reaching GitHub; no committed automated regression file or passing check is claimed for this change.

A timeout, ambiguous write result, or lost provider receipt must be marked `settle --outcome unknown` (including after an expired reservation). This fences that action/resource until the operator independently reads current provider state and completes `settle --outcome confirmed` or `no-effect`. **Never retry an uncertain write** without reconciliation and a fresh operation ID. Use `clear-gate --reason 'specific verified access repair or provider quota resolution...'` only after verified repair; this action is recorded in an audit table. `status` yields portable JSON for an operator to paste into Slack; the script does **not** post it automatically.

## Design boundaries

- This guards external calls **only if all participating workers use it**. It is not a substitute for current issue assignments, Slack TAKE receipts, fresh expected-head compares, or provider readback.
- The cooldown is an **admission pause**, not a promise that GitHub has replenished quota. Avoid excessive status polling; the ledger is local.
- Distinguish genuine secondary throttling from `Resource not accessible by integration` (a permission problem) and pre-provider safety blocks. Do **not** change accounts or route around access denial to obtain a retry.
- Never put raw tokens, passwords, billing details, email, or provider request bodies in operation IDs, event IDs, or this SQLite journal.
- No broad CI/suite integration. The author ran a one-shot local deterministic admission/cooldown/permission/unknown-effect self-check; its test source is not published on this branch because the connector blocked that separate create_file action before provider.