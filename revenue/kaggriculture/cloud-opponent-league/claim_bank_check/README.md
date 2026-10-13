# Offline claim-bank checker

A dependency-free diagnostic for overlapping inclusive integer seed banks in a supplied snapshot. It is a command-line tool and Python function, not a reservation service, allocator, runtime gate, or simulation runner.

## Run

From the repository root:

```sh
python -B revenue/kaggriculture/cloud-opponent-league/claim_bank_check/bank_check.py snapshot.json
python -B -m unittest discover -s revenue/kaggriculture/cloud-opponent-league/claim_bank_check -p 'test_*.py' -v
```

Pass `-` instead of a filename to read JSON from standard input. Requires Python 3.9 or later. The 40-test suite was exercised with Python 3.13.5 in the provided cloud container. It retains the original 31 tests and adds nine scaling/equivalence tests, including 200 deterministic synthetic snapshots. No game execution is part of this test command.

Exit status is 0 when the supplied snapshot has no reported conflicts, 1 when interval overlaps, blocked supersessions, supersession forks, or reused active operation IDs are present, and 2 for invalid input or file errors. Reports are JSON on stdout; input errors are JSON on stderr. An empty inventory is valid but says nothing about unseen claims.

## Input

This example is synthetic; it does not assign a real worker or reserve a seed bank.

```json
{
  "snapshot_ts": "1000.000002",
  "coverage_note": "Synthetic example only; no live allocation.",
  "claims": [
    {
      "claim_id": "example-a",
      "message_ts": "1000.000001",
      "label": "example worker",
      "bank": [1, 10],
      "phase": "claimed",
      "operation_id": "example-operation",
      "supersedes": []
    }
  ]
}
```

Each claim has a stable event/subclaim ID, a timestamp string with six decimal places, and an inclusive interval of two positive integers. Distinct subclaim suffixes represent independent assignments from one message. Matching display names or operation IDs never collapse independent claims. Identical replay of the same complete event is deduplicated; inconsistent replay is an input error.

`phase` defaults to `claimed`; `started` and `completed` are also supported. These phases describe supplied evidence, not a verification performed by the helper. Started/completed records remain active even when a later record names them in `supersedes`, and produce a blocked-supersession diagnostic. Completed work remains in the overlap inventory so its bank is not silently treated as unused.

Use `supersedes` only for the exact established original event and accepted replacement. Name-only instructions, unacknowledged offers, and ambiguous worker identities do not establish that correspondence. Missing targets and non-forward supersessions are input errors. Multiple replacements of one original remain a reported fork; interpreting a later resolution is a coordinator decision. Reused active operation IDs are a diagnostic, not evidence of duplicate execution.

## Scope and integration

`audit(document)` returns active records, superseded IDs, overlap intervals, blocked supersessions, forks, and reused active operation IDs. It preserves the snapshot timestamp and coverage note. It does not modify the input document or invoke network, game, or provider operations.

The checker trusts the supplied correspondence and phase assertions. It does not fetch Slack, authenticate authors, query GitHub, allocate ranges, launch or cancel jobs, infer available runtime, or count queued games as complete. Active intervals are sorted, and each left interval stops scanning when the next start exceeds its end. For `n` active claims and `k` overlapping pairs, sorting plus overlap discovery uses `O(n log n + k)` time and the overlap output uses `O(k)` space, excluding validation and the other report fields. Dense overlaps still require quadratic output. Report order, inclusive endpoints, and all supersession diagnostics are unchanged. The regression suite includes an independent exhaustive reference and deterministic endpoint-access bounds, not machine-speed thresholds. A clear result applies only to the supplied snapshot, not unseen or subsequently posted messages.

Existing T09 allocation and runtime owners remain unchanged. This directory contains reusable source, tests, and this usage guide only. Historical operational snapshots, scenario reports, raw game files, and private trajectories are not included. Keep private input and result files outside the repository.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
