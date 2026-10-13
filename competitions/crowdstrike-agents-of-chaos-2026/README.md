# CrowdStrike Agents of Chaos 2026 — manual prompt-efficiency workbench

Offline carrier only. Humans paste observed gameplay into a JSON ledger. This
package does **not** register, log in, submit prompts, probe scoring, or claim
the advertised Act 3 prize.

Official context (read-only URLs):

- Contest hub: https://www.crowdstrike.com/en-us/blog/announcing-agents-of-chaos-ai-red-team-contest/
- Rules PDF commonly published from the contest page (operator must confirm current URL before any human play)

## What it does

1. Strict-JSON attempt ledger (`schema: crowdstrike-aoc-manual-ledger-v1`).
2. Ranks **successful** attempts by operator-entered `observed_token_count`.
3. Per-puzzle frontier: best observed tokens, deltas, duplicate-prompt groups, receipt digest.
4. Refuses records that declare or imply prohibited live automation, backend/scoring attacks, interception, multi-accounting, or other-player access.
5. Labels output `SELF_ATTESTED_ONLY`. Never an eligibility or sponsor-compliance certificate.
6. Create-exclusive JSON + Markdown publication.

## Run

```bash
python3 competitions/crowdstrike-agents-of-chaos-2026/workbench.py \
  competitions/crowdstrike-agents-of-chaos-2026/fixtures/sample_ledger.json

python3 -m unittest discover -s competitions/crowdstrike-agents-of-chaos-2026/tests -q
python3 -O -m unittest discover -s competitions/crowdstrike-agents-of-chaos-2026/tests -q
```

## Authority ceiling

No contest registration or terms acceptance by this tool, no login/MFA, no live
gameplay, no prompt submission, no automated game interaction, no
backend/scoring probing, no network interception, no other-player access, no
prize/award/payment/revenue claim. Registration and eligibility stay UNKNOWN
until a human participant separately evidences them.
