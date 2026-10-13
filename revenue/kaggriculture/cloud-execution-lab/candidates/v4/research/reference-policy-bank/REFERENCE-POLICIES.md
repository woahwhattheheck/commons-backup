# BASALT: runnable reference policies for the one V4 gauntlet

This additive bridge lives in canonical `main:candidates/v4`, alongside REFORGE's
COK/lonespear bank and FIELDBANK's inner-exception observer. It does not introduce
another simulator, controller, production policy, or Kaggle submission.

## What is actually recovered

Apex V7 is a pinned public source version by VELVRIN: its unmodified Python
entrypoint, C++ policy, tape and four supporting source/header files are
available. It is a runnable adaptive source policy, not a fixed replay stream
and not a recovered current leaderboard team's agent. The registry term
`independent_public_policy` means a separately sourced public policy, **not**
proved disjoint ancestry or independent strategic coverage. Count Apex as one
explicit family, not several labels. Arlene v14 is an ancestor control; it is
not additional independent-opponent coverage.

Kaito v43 and Igor Multi-Route have exact historical source hash records, but
this checkpoint did not recover their executable bytes. They were not run or
counted here. Preparation fails until those exact files are supplied; an old
score report cannot satisfy source custody.

Sources remain at their existing repository paths. No third-party policy was
modified or duplicated into this research folder. Apex/Arlene license and
notice files are verified and copied into each ephemeral prepared runtime.

## Recover and prepare

Existing `woahwhattheheck/commons` Actions artifact **10030763484** contains
`titan-reusable-sources.tar`, `SOURCE-MANIFEST.json`, and a separate historical
checkpoint. The ZIP SHA-256 is
`68f78694fa56976fa1476ffd1d1fb6b3bfd4935392dfd0023a170c7efcd35e62`.
All 88 declared source files were checked against the source manifest. The
source snapshot is `7f92f6c0f4e3961be8109b2e3dc6da3e4e356d9f`.
Extract the verified source tar into a fresh cloud working directory and set
`KG` to its `revenue/kaggriculture` directory. Existing repository sources with
matching hashes are equally usable; do not refresh a dependency silently.

Set `ENGINE` to the official three-file engine cache pinned to
`Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
Artifact **10175943272** contains that cache under
`final-pressure-runtime/checks/reference/engine`. It also contains the
historical native candidate used in this acceptance run. This is existing
transport, not an instruction to dispatch a new paid workflow.

From this directory, on Linux with Python, g++, and libseccomp:

```sh
python -B reference_policies.py --key apex_v7 --kg-root "$KG" --out /tmp/apex-reference
# For the ancestor control, use --key arlene_v14 and a different fresh output.
BASALT_KG_ROOT="$KG" BASALT_ENGINE_DIR="$ENGINE" python -B test_reference_policies.py
BASALT_KG_ROOT="$KG" BASALT_ENGINE_DIR="$ENGINE" python -B -O test_reference_policies.py
```

Preparation verifies the source closure, compiles Apex before game startup,
and reuses `cloud-pack/pack.py::write_adapter`. The existing pinned raw-file
loader selects the last callable and handles its supported arity. First import
and policy setup are inside first-action timing; native compilation is not.
The runtime manifest records source, adapter, compiled library, compiler,
license, loader, evaluator and bridge identities. Keep the manifest in a
trusted location and bind its hash externally when freezing a gauntlet run:
file hashes detect drift against that trusted manifest, not a malicious
replacement of both bytes and their manifest. Reprepare after relocation;
existing adapters deliberately embed absolute paths.

## Consume, do not clone the evaluator

```python
from pathlib import Path
from reference_policies import ReferencePolicy

# Create within each match, never once per worker/thread or whole seed panel.
with ReferencePolicy(Path('/tmp/apex-reference'), Path(engine_cache),
                     rng_seed=20260908) as opponent:
    # Call once for each consecutive observation.step starting at 0.
    # configuration must not expose the private game seed.
    action = opponent(observation, configuration)
```

The existing `cloud-eval.Actor` provides the fresh persistent subprocess,
private working directory and JSON IPC. Use a constant policy RNG seed
independent of the engine seed and seat for paired comparisons. Each instance
belongs to one seat of one game. Always close it. Non-JSON output, external
exceptions and timeouts remain failures; they are never replaced by PASS.
A policy's own internal `try/except` can still hide errors: FIELDBANK's separate
observer addresses that boundary without changing ordinary loader ownership.
The existing offline guard is installed before policy load; it is not a general
filesystem security sandbox. Execute only reviewed policies in an isolated
cloud/container environment. Do not run untrusted imports on the owner's PC.

REFORGE owns COK/lonespear's existing `public_bank.make_agent` branch semantics.
Its prepared entries and caller-frozen manifest must retain that loader and
optional-dependency identity. Do not reinterpret a lonespear SciPy/greedy pair
as separate ancestry families. This Apex adapter does not claim that bank's
entry contract has already been composed through this class.

## Completed acceptance, not a V4 strength claim

15/15 tests passed normally and 15/15 with `-O`, **zero skips** with the real
recovered evaluator and engine. Without the two environment variables, eleven
process tests intentionally skip; a four-test run is not full acceptance.
Tests cover fresh globals/RNG/process/working-directory isolation, raw-loader
last-callable behavior, one-argument functions, parent observation/configuration
isolation, hidden game seed, ordered steps/seat ownership, no TypeError retry,
timeout cleanup, invalid JSON, source/support drift, guarded network calls,
and first-import timing.

`verify_reference_games.py` wraps the existing `cloud-eval.play`, changing only
Actor selection. Ten games completed all 719 decision rounds without an
external agent, engine, protocol or timeout failure. Four direct-vs-bridge
controls used Apex against the official starter at seed 11. In both seats the
bridge produced exactly the same scores **and complete trace SHA-256** as the
direct loader: 194720/3441 (Apex seat 0), 3451/173450 (Apex seat 1). These four
controls are not candidate wins.

The remaining six games compared historical native archive
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`
against Apex, serially (`workers=1`) to avoid multicore contention noise:

| Seed | Native seat | Native cash | Apex cash | Native margin |
| --- | --- | --- | --- | --- |
| 11 | 0 | 69640 | 60275 | 9365 |
| 11 | 1 | 70089 | 67155 | 2934 |
| 22 | 0 | 74538 | 67617 | 6921 |
| 22 | 1 | 72020 | 61317 | 10703 |
| 33 | 0 | 63080 | 47382 | 15698 |
| 33 | 1 | 63080 | 47382 | 15698 |

That is historical-parent 6W/0T/0L on this small declared panel, **not** a new
policy gain, composed-current-V4 result, held-out generalization result,
current leaderboard rank, or proof that this opponent is strong enough alone.
Seed/seat and timing-sensitive native differences remain visible in the raw
record. No clamp rejects legitimate margins or scores above 100000.

The full report (daily cash, timings, sources, trace hashes and all ten rows)
is retained losslessly in four ordered `apex-engine-results.json.gz.b64.01` through
`.04` text parts. `read_reference_results.py` verifies both compressed and raw
hashes before decoding JSON; it executes no policy. The decompressed
28,821 bytes have SHA-256
`deeb664f8bae5f8ad1dc423bae3e970a797838f28bb52a0ee84a7c8d15f3a0d2`.
Read it without executing any policy:

```sh
python -B read_reference_results.py
python -B verify_reference_games.py --kg-root "$KG" --engine-dir "$ENGINE" \
  --reference-runtime /tmp/apex-reference --candidate /path/to/frozen/main.py \
  --seeds 11,22,33 --out /tmp/reference-acceptance.json
```

Bind any supplied candidate to its whole archive/source closure externally,
not merely the main.py hash. `BASALT-VALIDATION.json` records this checkpoint's
exact artifact and executable identities. Source recovery and direct engine
acceptance are complete here; wiring these callables into Riot's separately
held `gauntlet.py/opponents.json` is not claimed without those files or a
subsequent integration receipt.
