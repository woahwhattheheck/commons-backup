# Offline hosted-result recency

`hosted_recency.py` turns supplied Kaggriculture replay JSON into an auditable
result ledger and completion-time windows. It does not download data, execute
agents, run simulations, change a submission, or infer a rating from a cash margin.
Python 3.10+ standard library only; validated in a Python 3.13 cloud runtime.

## Run

```sh
python hosted_recency.py /private/path/manifest.json --output /private/path/report.json
python -m unittest -v test_hosted_recency
```

Keep replay files, manifests, and generated reports in participating-owner private
storage. Public source and synthetic parser tests contain no real match data.
Exit 0 means all supplied inputs parsed without conflicts, **not** that history is
complete. Exit 1 preserves a report with rejected inputs or conflicting snapshots;
exit 2 identifies a manifest, command, or output error. Output cannot overwrite an
input manifest or replay, including an existing hard link.

## Input contract

The manifest is this tool's explicit local schema, not a claimed Kaggle API schema.
Paths are absolute or relative to the manifest. Example values below are illustrative:

```json
{
  "schema_version": 1,
  "submission_id": 123,
  "identity_evidence": "Reference binding this submission to the supplied episode and own seat",
  "as_of": "2026-01-02T00:00:00Z",
  "coverage_complete": false,
  "coverage_evidence": "Selected uploads only; full history has not been supplied",
  "entries": [
    {
      "replay": "episode.json",
      "episode_id": 456,
      "own_seat": 0,
      "completed_at": null,
      "opponent_rating_before": null
    }
  ]
}
```

`submission_id`, `identity_evidence`, and each entry's `own_seat` are explicit.
The parser reads `info.EpisodeId` from the replay and checks a supplied `episode_id`.
It does not use a filename, display name, or replay UUID as a substitute identity.
Optional `completed_at` needs a timezone. Completion time and pregame opponent
rating each require an entry-level `metadata_evidence` string. Missing values stay
null. Do not use upload time as game completion time or a later rating as a pregame
rating. `coverage_complete: true` requires `as_of` and `coverage_evidence`; the report
labels this as a caller declaration, not an independently verified provider census.

## Classification and counting

A normal completion needs two final DONE statuses, the configured `episodeSteps`
number of frames, finite rewards, agreement between top-level and final-frame
statuses/rewards, and no ERROR/TIMEOUT/INVALID status anywhere in the recorded
states. Present observation step indices must be contiguous. Initial frame zero
is not counted as an executed decision round. Runtime failures are separate from
normal results, including opponent failures. Partial bank balances and early DONE
records do not become final cash scores. Official forfeit outcomes are not inferred.

Repeated `(submission_id, episode_id, own_seat)` snapshots count once. All input
paths and SHA-256 digests remain in the result. A terminal snapshot can supersede
an ACTIVE partial snapshot; contradictory terminal values or metadata are retained
as conflicts, not silently selected. Multiple own-seat bindings for one submission
and episode also remain conflicts; this tool does not turn alternate views of a
single hosted game into independent games. Explicit self-play analysis is outside
this one-submission-perspective contract.

The `available_completed` summary describes only the supplied normal completions.
It is not automatically a hosted win rate. `win_rate` is W/N; `result_score_rate`
is (W + 0.5*T)/N. Name strata are labels, not verified opponent identities or source
families. Rating bands use only supplied pregame ratings and mechanical cutoffs
2000 and 2500; an unknown bucket is retained. These are not calibrated strength bands.

`latest_normal_completion_windows` provides 20/50 normal-completion windows, not
all provider-ranked outcomes. A window is supported only with declared full
coverage, enough dated normal completions, no rejected inputs/conflicts, and no
missing completion times. If a timestamp tie crosses the boundary, the full tied
cohort is retained and the exact-size window remains unsupported. Supplied dated
subsets can still have statistics when coverage is incomplete, with explicit reasons;
when no completion times exist, window statistics are null. IDs and filenames never
break chronology ties. Selected loss uploads cannot establish a recent win-rate trend.

## Validation

Synthetic tests cover identity, rewards/statuses, failure accounting, duplicate and
partial snapshots, missing files and times, source-bound metadata, UTC ordering,
boundary ties, coverage declarations, rating buckets, and executable CLI behavior.
Real replay analysis is separate private evidence; tests add no hosted games or
simulation samples. Use the current implementation on new supplied evidence without
rerunning games or changing the candidate package.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
