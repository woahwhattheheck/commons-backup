# Judge quickstart

Commercial Decision Relay is the **Professional Agents** entry inside the public
`woahwhattheheck/commons` repository.

## Public source

- Code repository: https://github.com/woahwhattheheck/commons
- Direct project tree: https://github.com/woahwhattheheck/commons/tree/main/revenue/agents_for_humans/commercial_decision_relay
- Original merged project PR: https://github.com/woahwhattheheck/commons/pull/13700
- Repository license: Apache-2.0
- Project package license: MIT

The monorepo is large. Judges should use the direct project-tree link above; all
source, fixtures, setup instructions, architecture, tests, and submission
material for this project are contained in that subtree.

## Fastest zero-credential evaluation

From `revenue/agents_for_humans/commercial_decision_relay`:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -O -m unittest discover -s tests -v

PYTHONPATH=src python -m decision_relay.cli reconcile \
  --batch fixtures/demo-batch.json \
  --output /tmp/decision-relay-receipt.json

PYTHONPATH=src python -m decision_relay.web_demo \
  --batch fixtures/demo-batch.json
```

Open `http://127.0.0.1:8080` for the local decision board.

The deterministic path is intentionally provider-independent: it lets a judge
inspect evidence semantics, decision cards, authority boundaries, replay
behavior, and the dashboard without model credentials or AWS spend.

## What to look for

The demo fixture contains routine and decision-worthy commercial states. The
product should stay quiet for routine waiting/decline and surface human decision
cards for exact acceptance, counteroffer, clarification, expiry, late reply, or
conflicting evidence.

`HUMAN_CLOSING_READY` means only that reviewed evidence matches the current
offer closely enough that a human has a closing decision. It never means this
agent signed, executed a contract, charged a buyer, began fulfillment, or
recognized revenue.

## Strands path

The Strands layer lives at `src/decision_relay/strands_app.py`. It defines five
business tools plus before/after lifecycle hooks. With normal provider
configuration, use the CLI's `agent` command as described in the README.

The source package's original local validation established 37/37 standard
unittests, 37/37 optimized-mode unittests, 38/38 pytest tests, deterministic CLI
reconcile/verify behavior, and an HTTP-200 local dashboard. The constrained
build runtime did **not** execute a live Strands model-provider invocation; do
not read the local deterministic evidence as proof of a live Bedrock call.

## Submission-state verifier

This package includes a side-effect-free submission manifest and checker:

```bash
python submission/check_submission.py
python -m unittest -v submission.test_check_submission
python -O -m unittest -v submission.test_check_submission
```

The checker deliberately reports `INTERNAL_READY_EXTERNAL_PENDING` until the
human/login-dependent Devpost fields are actually complete. It never submits to
Devpost, publishes a video, mutates an AWS account, claims a prize, or recognizes
revenue.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../../plant-downtime-handoff.html)
