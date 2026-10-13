# Hosted replay results and recent-window reporting

A standard-library-only offline helper for native Kaggriculture replay JSON and
per-seat provider logs. It is an analysis tool, not an agent or an alternative
TITAN package. It does not import agent code, run games, contact a provider, or
modify the input files. Use a cloud environment for project computation.

## Run

Python 3.10 or newer. From this directory:

```sh
python -B -m unittest -v test_hosted_results.py
python -B hosted_results.py /private/path/originals.zip \
  --agent-name 'TITAN' --submission-id 123 \
  --output /private/path/results.json \
  --markdown /private/path/results.md
```

Replace the example agent name and submission ID with the values in your inputs.
Multiple ZIP/JSON input paths are supported. A ZIP may contain the existing
`MANIFEST.json` with `files[].name`, `bytes`, `sha256`, `hosted_submission`, and
`archive`. All listed JSON members must match their manifest bytes and hashes;
unlisted JSON, ambiguous manifests, unsafe member names, and symlinks fail.
ZIP members are read directly without extracting them to the filesystem.

Own identity is matched against exactly one `info.Agents[].Name`. It is not
assumed to be seat zero. A log binds only to its exact episode/seat filename,
including copied names such as `100-0(1).json`. Repeated identical replay/log
bytes are counted once. Conflicting bytes for one episode/seat fail explicitly.
Submission identity must come from the bundle manifest or supplied history
metadata; the CLI does not fabricate it from an agent display name.

## Recent-20 and recent-50

Without a history source, output is **selected development evidence**. It never
uses episode ID, UUID, filesystem timestamps, or upload dates as completion time.

To compute recent windows, pass `--history-metadata /private/history.json`.
This file must contain:

* `kind`: `contiguous_completed_suffix` or `complete_submission_history`.
  `selected_development` is supported but never produces a recent window.
* `submission_id`, a timezone-aware ISO `as_of`, and an exact `source` reference.
* `episodes`, exactly matching the deduplicated replay IDs. Each row contains
  `episode_id`, the actual integer `own_seat`, timezone-aware `completed_at`,
  and `opponent_rating_pre` (a finite number or null).

Coverage is explicitly attributed to that supplied source, not independently
verified by the helper. At least N terminal, consistent episodes with completion
timestamps are required for a recent-N window. A timestamp tie across the window
boundary is reported as ambiguous rather than broken using an episode-ID proxy.
Missing pre-game ratings retain their missingness and sample denominator.

Early terminal runtime-failure episodes remain in the history. Missing rewards
remain UNKNOWN, not zero. `wins_per_episode` and `resolved_outcome_win_rate` have
separate denominators; unresolved outcomes are never silently discarded.

## Interpretation and outputs

Reports include manifest hashes, observed statuses, score/money consistency,
log coverage, duration summaries, missingness, duplicate counts, and unconsumed
opponent-log keys. Nonempty stderr is counted as text, not automatically labeled
an execution error. Durations are provider log values, not independent CPU
measurements. DONE statuses and empty stderr do not establish economic correctness.

Outputs are written atomically. Output paths may not alias the input paths,
history metadata, or each other. Replacing a hard-linked output does not mutate
the original input inode. CLI input failures return status 2.

50 regression tests cover data interpretation, history coverage, error retention,
deduplication, integrity, and input preservation. Synthetic test histories are
not provider evidence. Only reusable source, synthetic tests, and documentation belong in this public
directory. Keep match reports and original replays in private project storage.
Publication status is recorded separately from the generated analysis report.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
