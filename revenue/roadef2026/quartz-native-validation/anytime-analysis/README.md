# B12 validated-incumbent timeline

Offline consumer of QUARTZ's completed native B12 run, not a new solver experiment.
The original [B12 delivery](../B12.md) and its source, attempts, binaries, and results remain unchanged.

## What the saved evidence shows

The reader consumes all 40 official-checker snapshots, each with 53,448 load values,
and reproduces all 23 recorded incumbent selections using the unchanged comparator.
The comparison is lexicographic over the full six-decimal vector, with no cost tiebreak.
Times below are the supervisor's recorded installation times, not exact solver discovery times.

| Installed at (seconds) | Lane | Retrospective comparison |
|---:|---|---|
| 18.4065 | SEDGE | Peak already equals the final peak, 0.629742. Full vector still loses to final SEDGE at rank 18: 0.46358 versus 0.445406. |
| 160.1015 | SEDGE | Matches the independent SEDGE final solution byte-for-byte. |
| 165.9113 | FLORA | First incumbent better than final SEDGE, at rank 34: 0.294548 versus 0.295719. |
| 187.4950 | Candidate | First candidate snapshot better than final FLORA, at rank 36: 0.294136 versus 0.294268. |
| 262.9066 | Candidate | First installation of the final selected bytes. |
| 287.3745 | Supervisor | Run completes; all three lane return codes are zero. |

The rank-34 gain over SEDGE is therefore not uniquely attributable to the new candidate:
FLORA already achieves it. The candidate supplies additional full-vector improvement over FLORA.
After 187.4950 seconds its next five selected updates first improve ranks 2,575, 1,038,
2,656, 9,793, and 4,053 respectively. A peak-only convergence rule would miss those improvements.
These are results of one retained public instance, not independent samples or leaderboard gains.

## Early termination and limits

The preserved source at `2885d176373c33410148829fef93c310c3752c0b` selects at most
32 critical coordinates per round. Adaptive search becomes active after 12 stalled rounds
or after 65% of the allowance; the loop breaks when `adaptive && stalled >= 64`.
A successful round resets `stalled`. The default round ceiling is 1,000,000; the supervisor
removes any inherited `SEDGE_MAX_ROUNDS` and sets each lane's allowance to 565 seconds.
Its own loop ends when all final lane outputs have been checked, without restarting those lanes.
See the source context's `context/sources/{sedge,flora,candidate}/main.cpp` and
`context/supervisor.py:182-201,361-376`.

The logs record 536/621/336 accepted moves and 158.196/163.866/287.179 elapsed seconds
for SEDGE/FLORA/candidate inside the portfolio. The reset-on-accept rule bounds rounds by
64 times (accepted moves + 1), below the default ceiling in every lane. The supervisor
records no received signal. This supports the bounded-stall exit rather than exhaustion
of the time allowance. **The terminal stall count and solver exit reason were not logged**;
this interpretation is source-supported, not a newly measured internal counter.

The supervisor finished with 277.6255 seconds of its search allowance unused, and
24.4679 seconds after the final incumbent installation. More time or a restart has not
been shown to improve this instance. The 40 checker durations sum to 64.8936 seconds,
but they overlap solver execution and must not be added as serial overhead.

Use the independent observer's process-tree RSS: sampled peak 1,455,796 KiB, at a
0.5-second cadence, under a 20 GiB memory cgroup and eight-CPU quota. This is not a
32 GiB competition-machine measurement or a Docker-build memory measurement. Its
287.853092-second observation interval differs from the supervisor's own clock.
The older supervisor-local RSS field is not a whole-process-tree bound.

## Reproduce without running native binaries

Obtain the two existing Library archives; do not create another source export:

- `ROADEF-QUARTZ-B12-native-2885d176.zip`, file `file_00000000320881f78ecce6721df75592`, 13,925,209 bytes, SHA-256 `1494b0faf268be12b99f25444ce5bd6c42539a187c00ca7ef29f11d24484fd9f`.
- `ROADEF-QUARTZ-verified-context-2885d176.zip`, file `file_000000008c8481f783a95eb409c035fb`, 1,823,163 bytes, SHA-256 `62bb113f6fecf074fad8a5a76623c548d099466e230f509c8e353fb2b2e181e6`.

```sh
python -B analyze_b12_anytime.py \
  --evidence ROADEF-QUARTZ-B12-native-2885d176.zip \
  --context ROADEF-QUARTZ-verified-context-2885d176.zip \
  --output B12-ANYTIME.json
python -B -m unittest -v test_analyze_b12_anytime
```

The exact reader verifies 169 evidence and 336 context payloads, input and binary bindings,
checkpoint identities, and both the historical selection sequence and final comparison.
It imports only the reviewed, pinned Python comparator (`225169ef7e1e81f1006b296a186973e9b885d24dbfa5304b2695286cadf8d765`),
using its Decimal parsing and coordinate checks. It never launches a solver or checker.
Eight boundary tests pass, covering intact input, altered archive/payload/size, missing
payload, duplicate manifest identity, and complete versus incomplete lane logs.

The generated `B12-ANYTIME.json` is 104,954 bytes with SHA-256
`9d0ffee3df9adffffb5f2f800f1d6809ab0e4501bc35b29e721cee2b48694859`.
The Library delivery `ROADEF-QUILL-B12-anytime-20260908.zip` retains that full result,
the executed reader/tests, logs, validation, and file manifest. It contains no copied
benchmark binaries or replacement original evidence archive.

## Consumer action

Root's existing allocation/configuration work can use the saved milestone table to distinguish
FLORA's contribution from the candidate's later tail gains. Retain the full-vector objective;
do not terminate solely because maximum load is unchanged. Any study that reuses the unused
allowance or broadens rank coverage remains a separately labeled experiment with its existing
owner, not a benefit established here. ATLAS's rank-band work, LANDING's continuation cells,
QUARTZ's native runs, and RENEW's Docker build remain separate.

S139 draft and attachment are unchanged and unsent. There are no new solver/checker runs,
solver edits, official submissions, benchmark reruns, or new spending in this delivery.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
