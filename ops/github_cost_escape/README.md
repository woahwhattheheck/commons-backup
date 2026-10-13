# GitHub Cost Escape Planner

Offline planning for reducing repository and CI cost without changing repository state.

## Scope

The planner treats repository visibility and hosted CI as separate cost levers.

- Private repositories with no explicit release evidence default to review.
- Repositories marked customer, regulated, secret-bearing, or proprietary remain private.
- Zero-size private repositories can be flagged for retirement review when no retention requirement exists.
- A repository can be marked for a public-core/private-overlay split without changing the private original.
- A reviewed release is still only a candidate and requires separate human approval before any visibility change.
- CI recommendations are independent: consolidate duplicate fanout, move deterministic checks to existing free capacity, or profile usage before the next run.

The tool performs no network calls, deletes nothing, changes no visibility, and triggers no workflows.

## Usage

```bash
python repo_cost_escape.py inventory.json --policy policy.json --format markdown --output plan.md
python repo_cost_escape.py inventory.json --policy policy.json --format json
python -m unittest -v test_repo_cost_escape.py
```

Inventory may be a repository list or an object containing `repositories`, `items`, or `result.repositories`.

## Decision classes

- `keep_private`
- `review_required`
- `empty_private_retirement_candidate`
- `archive_cost_review`
- `split_public_core_private_data`
- `publish_safe_candidate`
- `already_public`

## Operator sequence

1. Export repository metadata through an authorized provider.
2. Add explicit custody/release facts in the policy overlay.
3. Run the planner offline on free cloud capacity.
4. Review retirement candidates first.
5. For split candidates, publish only separately reviewed reusable files into a fresh public repository.
6. For private repositories that must remain private, reduce CI spend independently.
7. Require explicit approval before any destructive action or visibility change.
