# GrantFox FWC26 workfeed compiler

This is an **offline intake compiler** for the Swarm ZZ GrantFox/FWC26 queue. It turns supplied GitHub issue snapshots into a deterministic JSON + Markdown workfeed without claiming work, assigning contributors, contacting maintainers, or pretending that discretionary campaign rewards are guaranteed payment.

## Safety / authority boundary

The compiler is advisory only. It never:

- calls GitHub, GrantFox, Slack, wallets, or payment systems;
- claims or assigns an issue;
- treats `MAYBE REWARDED` / “may be rewarded” as a guaranteed amount;
- converts a campaign pool mention into issue-specific compensation;
- treats an archived repository as an available source-publication target when archive evidence is supplied;
- overwrites an existing output directory.

A candidate is campaign-eligible only when all three labels are present:

- `GRANTFOX OSS`
- `MAYBE REWARDED`
- `Official Campaign | FWC26`

Open + unassigned issues become `READY` only when the supplied snapshot also contains no observed claimant comments and no open pull requests. If the issue text describes a required application/assignment step, it becomes `CLAIM_REQUIRED`; supplied claimant/PR observations become `CLAIMED_OR_PR_OPEN`. Assigned and closed/mislabeled issues remain visible but cannot enter `READY`. An issue in a repository confirmed archived is `REPOSITORY_ARCHIVED`, never `READY`, even if the issue remains open and unassigned.

## Input

JSON array or JSONL. Minimal object:

```json
{
  "repository": "StableRoute-Org/Stableroute-backend",
  "number": 551,
  "title": "sliding-window rate limiter scoped per tenant/API key",
  "url": "https://github.com/StableRoute-Org/Stableroute-backend/issues/551",
  "state": "open",
  "repository_archived": false,
  "labels": ["GRANTFOX OSS", "MAYBE REWARDED", "Official Campaign | FWC26"],
  "assignees": [],
  "claimant_comments": [],
  "open_pull_requests": [],
  "body": "Part of the campaign — this task may be rewarded. Run `npm test`."
}
```

`labels` may also contain GitHub-style objects with `name`; `assignees` may contain objects with `login`. **Do not use `assignees: []` as proof that a GrantFox campaign slot is vacant.** Include the live GitHub issue-comment census as `issue_comments`: an array of GitHub comment objects with `user.login` and `body`. A verified `grantfox-oss[bot]` comment stating `@contributor has been assigned to this issue` blocks `READY` as `ASSIGNED` and supplies the campaign assignee even when GitHub search/API assignees are empty. Quotes of that text by other commenters are not treated as authoritative; ordinary expressions of interest remain distinct from official assignments. A missing `issue_comments` field means **bot assignment not checked**, not evidence of a free campaign slot. An old bot assignment should be reconciled against current official campaign status before treating a later release as vacant. This compiler does not fetch comments on its own.

`claimant_comments` (or `claim_comments`) and `open_pull_requests` (or `open_prs`) are optional upstream coordination inputs; any supplied claimant or open PR blocks `READY`. `coordination_claims` (or `swarm_claims`) records active internal owners from Slack/workboard evidence and produces `SWARM_TAKEN`, preventing another seat from treating the same packet as free. `observed_at` (or `snapshot_observed_at`) may carry the timezone-aware evidence timestamp.

Each issue URL must identify the supplied `repository` and issue `number`; a different repository, issue number, or pull-request URL is rejected. GitHub repository names are compared without case sensitivity, including duplicate detection across the input. Display spelling is preserved. Accepted HTTP, trailing-slash, query, and fragment variants are emitted as the canonical HTTPS issue URL, so equivalent links do not become separate work targets.

Supply `repository_archived` (alias `repo_archived`) from a current canonical GitHub **repository** read. It accepts only a boolean or `null`; conflicting aliases and numeric/string stand-ins are errors. Explicit `true` blocks `READY` with `REPOSITORY_ARCHIVED` and appears in both outputs; explicit `false` means the observed repository was not archived. Missing/`null` means **archive state not checked**, not an active-repository guarantee. Intake publishers should include fresh repository evidence before dispatch. The compiler makes no additional network calls.

Optional `campaign_active` must be a real JSON boolean (`true` or `false`) or
`null`. It is **external sponsor campaign evidence**, not inferred from the issue's
`Official Campaign | FWC26` label; label presence does not prove a campaign is
currently taking/rewarding new work. Supply the flag only from a recent
canonical campaign-status observation and use the existing `observed_at` +
`--fresh-after` evidence floor to avoid stale snapshots. Explicit
`false` suppresses READY for otherwise dispatchable issues; missing/`null`
is **unknown**, never an implied `true`. Add `--require-active-campaign` to
suppress READY/CLAIM_REQUIRED for unknown activity; without that opt-in,
legacy input behavior remains unchanged. Assigned, archived, stale, externally
claimed and internally owned issues retain their existing precedence.
Neither campaign activity nor an explicit cash amount guarantees payment.

## Run

```bash
python -m tools.grantfox_fwc26_workfeed.compile issues.json --out-dir /tmp/gfox-feed

# Optional hard freshness floor: missing/older observed_at snapshots are not routable.
python -m tools.grantfox_fwc26_workfeed.compile issues.json --out-dir /tmp/gfox-feed-fresh \
  --fresh-after 2026-09-19T17:30:00-04:00

# Campaign-confirmed dispatch: suppress inactive and unverified campaigns.
python -m tools.grantfox_fwc26_workfeed.compile issues.json --out-dir /tmp/gfox-feed-live \
  --require-active-campaign --fresh-after 2026-10-07T00:00:00-04:00
```

Outputs:

- `queue.json` — schema-versioned machine-readable feed with explicit false authority flags.
- `QUEUE.md` — human-readable queue with status, reward-evidence class, security-sensitive marker, and extracted local verification commands.

The output directory is create-exclusive; reruns must use a new directory so an older evidence packet cannot be silently replaced.

## Tests

```bash
python -m unittest discover -s tools/grantfox_fwc26_workfeed/tests -v
python -O -m unittest discover -s tools/grantfox_fwc26_workfeed/tests -v
```

The existing tests cover campaign label gating, assignment state, claim-step detection, observed claimant/open-PR blocking, active swarm-owner collision blocking, timezone-aware freshness floors, discretionary-vs-explicit reward evidence, command extraction, security-sensitive marking, hostile duplicate keys, malformed coordination fields, invalid URLs/issue numbers, authority flags, and create-exclusive output. For archive evidence, run the real CLI on a mixed archived/live input and inspect `queue.json` and `QUEUE.md`; do not run broad suites.

