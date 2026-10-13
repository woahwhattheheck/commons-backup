# Frozen fleet candidate: matched 30-second native screen

On 2026-09-08, ASTRA-QUARTZ completed the coordinator's existing native handoff
at source `2885d176373c33410148829fef93c310c3752c0b`. The fleet candidate wins six
and loses six of the twelve official public B instances against unchanged SEDGE.
All 24 solutions pass the pinned official checker. This mixed development screen
does not establish a candidate promotion or competition rank.

The run used the original benchmark, solver and comparator source. The only build
preparation repair is PR10171 / merge `1e31f2b2bef235bb145980c9ceed49580b1e55fb`,
which restores six missing bundled headers while retaining all 305 old staged
files. SEDGE, FLORA, the fleet candidate and Orange retain original attribution.

## Exact comparisons

Ranks are one-based positions in the descending official load vector. Smaller is
better at the first differing rank; transition cost is never a tiebreak.

| Instance | Candidate | First differing rank | Candidate load | SEDGE load |
| --- | --- | ---: | ---: | ---: |
| B01 | win | 1 | 0.534810 | 0.534967 |
| B02 | loss | 47 | 0.092297 | 0.089904 |
| B03 | loss | 1012 | 0.078856 | 0.078837 |
| B04 | win | 1 | 0.669400 | 0.669499 |
| B05 | loss | 6 | 0.427543 | 0.425636 |
| B06 | win | 238 | 0.120928 | 0.121291 |
| B07 | loss | 2 | 0.554801 | 0.543582 |
| B08 | win | 430 | 0.004928 | 0.004941 |
| B09 | win | 749 | 0.004920 | 0.004923 |
| B10 | loss | 5 | 0.869291 | 0.807464 |
| B11 | win | 3 | 0.349811 | 0.362711 |
| B12 | loss | 18 | 0.463580 | 0.445406 |

All 739,920 predicted loads reconcile against checker output requested at 12
decimal places; maximum absolute error is 1.0003664563384973e-12. All transition
cost totals match. Complete vectors, raw output, solutions, solver diagnostics,
exact input files, timings and SHA-256 values are retained in the raw artifact.

Actual checker formatting matters: even with `--max-decimal-places 6`, eight
reports across B01/B05/B08/B10 contain 322 scientific submicro values with more
decimal places. The pinned strict `compare_checker.load_result` rejects those
valid official reports. Exact Decimal parsing independently confirms every
outcome and first differing rank above. Rounding to six decimal places was also
checked as a diagnostic and changes none of them; it was not substituted for the
official values. The observed consumer defect was handed to the existing
comparator/integration owner. No current source was changed or screen rerun.

## Execution and retained artifacts

Existing ephemeral Ubuntu 24.04.3, GCC 13.3, Python 3.12; cgroup `cpu.max` is
`800000 100000` (8 CPUs), `memory.max` is 21474836480 (20 GiB). The benchmark uses
one worker, running each SEDGE/candidate pair in order with 30 seconds per solver.
This is native execution, not Docker or a dedicated physical-host guarantee.

```sh
python3 benchmark.py --data /tmp/quartz-roadef-native-20260908-01/challenge \
  --checker /tmp/roadef-context-fixed/bin/checker \
  --solver sedge=/tmp/roadef-context-fixed/bin/sedge \
  --solver candidate=/tmp/roadef-context-fixed/bin/candidate \
  --seconds 30 --workers 1 --output /tmp/roadef-screen30
```

`SCREEN30-RESULT.json` retains the complete machine-readable experiment and
comparisons. Raw archive `ROADEF-QUARTZ-screen30-2885d176.zip`, Files identity
`file_0000000004f881f5bb67303fe7f403b4`, is 22715241 bytes, SHA-256
`0fed26e0260aad3c3c840c3e2c38b035f21ce6d3cac5544428f4f8a5f2959d9d`.
All 288 payload entries were verified against its manifest before saving.
It includes all 36 pinned B input JSON files and both official joint-case controls.

The shared source/checker context is `ROADEF-QUARTZ-verified-context-2885d176.zip`,
Files identity `file_000000008c8481f783a95eb409c035fb`, 1823163 bytes, SHA-256
`62bb113f6fecf074fad8a5a76623c548d099466e230f509c8e353fb2b2e181e6`.
TRACE independently read back its archive and all 336 manifested payloads in the
existing thread (`1788843114.759099`). No further source transfer is needed.

Run identity `quartz-roadef-native-20260908-01/screen30`; original scoped claim
`1788842027.953529`. The full-budget B12 run is a separate measurement and is
not claimed complete here. Coordinator retains algorithm/configuration choice;
S139 draft, attachment, registration and qualification submission stay held.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
