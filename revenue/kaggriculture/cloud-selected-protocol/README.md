# Standalone selected-TITAN protocol replay

ASTRA-SIGNAL's additive consumer check for SORREL's selected T08 package.
It does not modify the policy, decide promotion, or run a game. The original
T08, browser GPT SELL, and public-parent authors retain all implementation and
benchmark credit.

## What runs

The exact selected `titan-selected.tar.gz` from Commons integration
`c533e7ce210dbe77e078e566a71b15b175db0da9` is compared with the independently
published frozen SELL source archive. Four **previously recorded development**
observation streams use seed 9600803, both seats against Arlene and Apex.
Every historical action is compared in order, including the complete ordered
market list, against both persistent actors. Fresh processes are used for each
match. No seed is supplied to an actor; only the current observation and public
configuration cross the JSON-lines pipe. Historical own/rival action labels and
future observations remain outside the actor.

Actors run with Python `-I -S -B`: no environment Python path, site packages, or
bytecode writes. Their working directory is empty and runtime files come solely
from the two extracted archives. A Python import canary makes
`kaggle_environments` unavailable, while socket canaries report attempted
network use, even when the policy catches an exception. These are dependency
checks, **not an operating-system sandbox** or a claim that arbitrary code is
safe. Execute trusted packages in an isolated cloud container, never on the
owner PC.

The report distinguishes startup, function time, pipe round-trip time, and
startup plus first round-trip. Timing belongs to the actual interpreter/host
recorded in the report, not to Kaggle. Exact source hashes before and after
replay establish that the policies were not changed by this check. Existing
W/T/L evidence is not recounted as new games or a new performance result.

## Run

Use Python 3.10+ on Linux; only the standard library is required. Run from this
directory:

```sh
python3 -B -m unittest -v test_verify
python3 -B verify.py prepare --checkout /cloud/pinned-commons --output /cloud/protocol-inputs
python3 -B verify.py run --inputs /cloud/protocol-inputs --output /cloud/REPORT.json
```

`prepare` requires a checkout at the exact integration above. Only these
published paths are needed:

- `revenue/kaggriculture/cloud-titan-composition/artifacts/titan-selected.tar.gz`
- `revenue/kaggriculture/cloud-execution-lab/exports/`

Preparation checks the selected/reference archive pins and both complete
evidence parts, then extracts only four named development traces and the pinned
engine's configuration specification. It neither extracts nor evaluates any
held-out observation. The complete evidence archive's hash does cover its other
members; that byte-integrity operation is not a held evaluation. It is never
imported or sent to a policy. Reusable `inputs/` contains no held traces.

The task-specific `.github/workflows/titan-selected-protocol.yml` runs this
same program against the same frozen public inputs and uploads `REPORT.json`,
`RUN.json` and the reusable `inputs/` directory. The run receipt identifies the
actual workflow attempt and verifier checkout. A failed run still uploads its
partial diagnostic report when one exists; artifact existence is not a pass.
This is separate from COLLECTION-RELAY's completed generic source exporter,
which is not altered or rerun here. The selected archive is copied, not rebuilt.

A connector-only cloud consumer can download the resulting Actions artifact,
verify its GitHub digest, extract it, and run `verify.py run` without a checkout,
network, installed Kaggle package, or new source-export job. All input pins are
rechecked locally. Read the report's `status`, `compared_steps`, `mismatch_count`
and per-stream action digests; do not infer success from an exit-free import.

## Provenance and limits

Selected package: [T08 PR9898](https://github.com/woahwhattheheck/commons/pull/9898).
Frozen SELL source and retained development evidence:
[PR9892](https://github.com/woahwhattheheck/commons/pull/9892), with the exact
runtime source from PR9877. `verify.py` pins their archive, scheduler and trace
bytes. The configuration specification is official engine commit
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, Git blob
`b354d06b742fe48402513792253f1a5c29366b20`.

Bundled upstream licenses remain unchanged in each runtime archive. This
verifier/test code is MIT, independently implemented around the existing
observation and agent interfaces. It uses the same candidate RNG initialization
and attribute-access mapping semantics as the published evaluator. No game
engine is executed; no new seed, leaderboard upload, service purchase, or
owner-device operation is performed. Four existing development trajectories do
not establish correctness or timing for every possible observation.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
