# ROADEF S139 fleet candidate validation

The owner requested a stronger competitive solver and explicitly held qualification submission. Keep the existing S139 Gmail draft and attachment unchanged and unsent. This source snapshot is for implementation and validation by the fleet.

## Candidate

The new candidate derives from SEDGE and FLORA. It ranks all potential waypoints by prospective bottleneck load, explores insertion/deletion/replacement up to the instance's segment limit, and evaluates two-demand exchanges atomically against every affected transition budget and the full six-decimal load vector. Feature controls permit directed-search and exchange ablations. The portfolio runs unchanged SEDGE, unchanged FLORA, and the new candidate in parallel, validating frozen checkpoints with Orange's checker before replacing its output.

## Existing measurements

`NATIVE-VALIDATION.json` contains the actual Windows native fallback results and the new constructed-case evidence. The new joint-exchange cases pass the official checker: peak load 10 to 9, and rank-three improvement at unchanged peak 10 and transition cost 3. Disabled-exchange controls, fixed-round repeatability, and same-file resume pass. The 30-second SEDGE baseline is valid on all twelve B instances; all 369,960 predicted loads match the official checker within tolerance. These native measurements do not establish the new candidate's public-instance performance, container behavior, or competition ranking.

## Cloud execution

Use an existing available ephemeral Linux/cloud worker. No additional paid infrastructure or Cursor/Grokbot allocation is requested. Retrieve this directory at the exact published Git commit. Run `python3 prepare_context.py --output /tmp/roadef-context` to assemble pinned source dependencies, then `docker build -t roadef-fleet /tmp/roadef-context`. The build downloads happen before runtime; run the finished image with `--network none`, the official UID, eight CPUs, and a 32GB memory limit.

First validate the actual compiled candidate with:

```sh
python3 verify_joint.py --solver /path/to/candidate --checker /path/to/checker --output /tmp/joint-evidence
```

Build matching native executables with the context's `build.sh` if needed for measured comparisons. Extract official challenge data from the same pinned API archive used by the bootstrap. Then run:

```sh
python3 benchmark.py --data /path/to/challenge --checker /path/to/checker \
  --solver sedge=/path/to/sedge --solver candidate=/path/to/candidate \
  --seconds 30 --workers 1 --output /tmp/roadef-comparison-30
```

The 30-second run is a development screen. Compare all twelve B instances using the exact six-decimal official vector, including improvements below the maximum load. Do not use transition cost as a tiebreak. Retain actual source/binary/checker/input/output identities and wall times. If defaults trade wins for losses, retain the validated SEDGE fallback in the portfolio and evaluate useful configuration changes, without hard-coding instance names.

Test the actual portfolio through its four-argument `run.sh`, beginning with B01, B11, and B12. Record valid output, selected lane, checker durations, process memory, and full wall time. Exercise TERM during preparation, search, and final draining; a valid checkpoint must survive, and descendants must exit within the grace window. Confirm a killed or failing candidate lane and a transient checker failure preserve the previous validated result. Use the real checker for final claims; synthetic controls alone do not establish readiness.

Run retained candidates at the official 600-second envelope (portfolio default 585, search deadline 565), including the large B11/B12 cases. Compare against the same-resource unchanged baseline. Preserve complete results in a cloud artifact and report the immutable source commit and artifact/run ID to the existing ROADEF Slack thread. Qualification uses hidden X instances; public results support candidate selection but do not establish a winning rank.

Before the eventual entry package is selected, produce the matching at-most-two-page method document, build the exact final Docker context, and retain its actual runtime evidence. Submission remains held unless Bryce gives a new explicit release.

Official sources: [challenge repository](https://gitlab.com/Orange-OpenSource/network-optimization-tools/challenge-roadef-2026/-/tree/d84d319a7fdb8de3b1866830d2eaa2937871e5ae) and [qualification schedule](https://roadef.org/challenge/2026/en/calendrier.php).

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
