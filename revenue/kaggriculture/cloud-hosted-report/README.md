# Offline hosted-results reporter

Read saved Kaggriculture replay JSON and optional own-agent logs without running an agent, simulating games, polling a service, or changing a submission. Python 3.10 or newer; standard library only.

## Usage

From this directory:

```sh
python -B -m unittest discover -s tests -v
python src/hosted_recent_report.py /path/to/private/replays \
  --team 'Our team' \
  --output /path/to/private/results/report.json \
  --markdown /path/to/private/results/report.md
```

Use an exact `TeamNames` entry; the reporter resolves either seat rather than assuming seat zero. Replay filenames are `<episode>.json`; agent logs are `<episode>-<seat>.json`. Duplicate download suffixes such as `(1)` are supported. A directory input is searched recursively for these names. Explicitly supplied unsupported filenames are input errors.

Output paths must be new. Exit code 0 means the supplied inputs were processed without input issues, not that a latest-20/50 history exists. Exit code 2 indicates malformed, conflicting, orphan, absent input, or an output error. Valid observations and input diagnostics are retained when a report can be written.

## Optional latest-window snapshot

```sh
python src/hosted_recent_report.py /path/to/private/replays \
  --team 'Our team' --feed-manifest /path/to/private/provider-feed.json \
  --windows 20 50 --output /path/to/private/results/feed-report.json
```

The caller supplies the ordered feed; this utility does not fetch or independently authenticate it. The following is an illustrative schema with synthetic IDs, not provider evidence:

```json
{
  "schema_version": 1,
  "as_of": "2026-09-08T10:00:00Z",
  "source_reference": "saved provider response reference and digest",
  "own_submission_id": 100,
  "latest_completed_episode_ids_newest_first": [102, 101],
  "episodes": [
    {"episode_id": 102, "own_submission_id": 100,
     "finished_at": "2026-09-08T09:59:00Z", "opponent_rating": null},
    {"episode_id": 101, "own_submission_id": 100,
     "finished_at": "2026-09-08T09:58:00Z", "opponent_rating": null}
  ]
}
```

A latest-N window requires at least N explicitly listed episodes, original replay coverage, scored terminal outcomes, and matching submission metadata. Episode IDs, UUIDs, upload times, and filesystem times are never used as chronology. Missing ratings remain missing. Conflicting feed order, duplicate identities, or supplied completion times after capture are rejected. A selected replay sample is not a population win rate.

## Provenance and limits

The reporter retains input byte counts and SHA-256 digests; equivalent copies count once, conflicting copies are explicitly excluded. Top-level scores and statuses must agree with final replay states. Faulted and unscored episodes remain visible.

Own logs bind to the exact filename episode and seat, not to another replay or the rival. The log format supplies no independent embedded identity. Frame-count mismatches are reported. Recorded timing percentiles and maxima are not independent measurements of hosted deadline enforcement or proof that all runtime faults are absent.

This directory contains only generic source, synthetic tests, and validation metadata. Keep raw replays, own-agent logs, generated reports, and their private source references in participating-owner private storage. No agent runtime, release pointer, evaluation runner, seed allocation, or submission is modified by this utility.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
