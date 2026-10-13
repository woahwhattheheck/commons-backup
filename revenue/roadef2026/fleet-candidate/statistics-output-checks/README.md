# Solver statistics and output preservation

Status: **source-pinned implementation and regression coverage prepared for ordinary main integration**.

This change preserves the ROADEF fleet solver's solution, input files, and last
complete statistics file when output paths collide or statistics publication
fails. It changes output handling only, not an optimization algorithm.

## Reproduced behavior

On original `main.cpp` Git blob `9354ec61fc32bb7ebbdaaa4a9bff7c7780a7e1df`,
setting `SEDGE_STATS` to the solution path finishes with exit code zero but
replaces the required `srpaths` solution object with statistics. A nonexistent
statistics parent also finishes with exit code zero, without a statistics file.
Input aliases and statistics write failures are covered by the regression suite.
All destructive witnesses use disposable copies, not supplied evidence files.

## Change

* Before constructing the solver, compare final and staging output roles with
  each other and with network, traffic, scenario, and initial-solution inputs.
  Resolve normal path aliases and symbolic links; recognize hard links. Preserve
  the existing supported case where the final solution replaces its own parsed
  initial-solution input. Reject an empty `SEDGE_STATS` value.
* Render statistics to the same-directory `.tmp` file. Check opening and closing
  the stream, then replace the final statistics file. A failed open, write,
  close, or rename reports failure rather than a successful process completion.
* Keep every search method, constructor, solution writer, rendering field, and
  optimization parameter unchanged. Reversing only these three source regions
  restores the complete original source bytes.

This is filesystem data preservation, not authentication, a network restriction,
or a change to permissible route moves.

## Executed validation

The same 24 native regression methods pass under GCC 14.2.0 and Clang 17.0.0.
The exact original source fails 18 methods, producing 25 assertion/subtest
failure records and zero execution errors. The counts are repeated compiler
configurations, not 48 independent methods.

The cases cover existing and absent destinations; relative, symbolic-link and
hard-link aliases; all problem inputs; both staging paths; initial-solution
handling; missing directories; open and rename failures; empty statistics paths;
and a real Linux file-size-limit write failure. For a statistics failure after
the solution has been produced, the valid solution remains available and the
process reports failure. The previous complete statistics survives staging
failures.

Six fixed-work settings (0, 3, and 12 rounds, joint search off/on) produce exactly
the original solution bytes and every original statistics value except elapsed
`seconds`. Separate official-checker execution covers two existing manufactured
fixture families, each with the original GCC, corrected GCC and corrected Clang
binary: six valid checker results, identical solutions, non-timing statistics,
and parsed checker outputs. These are not a new public-instance benchmark,
competitive improvement, Docker validation, full-budget run, or submission.

## Run the regression suite

In an existing prepared source context with its original RapidJSON headers:

```sh
F=/absolute/path/to/commons/revenue/roadef2026/fleet-candidate
BASELINE=/absolute/path/to/unchanged-2885d176/main.cpp
BUILD=$(mktemp -d)
g++ -std=c++17 -O2 -DNDEBUG -I "$F/vendor" "$BASELINE" -o "$BUILD/original"
g++ -std=c++17 -O2 -DNDEBUG -I "$F/vendor" "$F/main.cpp" -o "$BUILD/candidate"
python3 -B "$F/statistics-output-checks/test_statistics_output.py" \
  --binary "$BUILD/candidate" --reference-binary "$BUILD/original" \
  --fixtures "$F" --report "$BUILD/regressions.json"
```

The suite requires Linux/POSIX, Python 3.10 or newer, and a C++17 compiler.
It uses temporary directories and an actual child file-size limit. The supplied
fixtures are the existing `joint-*.json` and `joint-budget-*.json`, not new
contest data. Output reports use a fresh path.

When composing this change with other contributors' main.cpp changes, apply
only its output-I/O hunks; do not replace their distance, cache, comparator or
neighborhood edits with this source snapshot. Update only main.cpp's actual
size/hash record in PUBLIC-SOURCE-MANIFEST.json after composition. Existing
benchmark, supervisor, preparation and submission files remain untouched.

## Limits

Each final-file rename is atomic on a filesystem that supports same-directory
atomic replacement. This is **not** a transaction across solution and statistics,
not a power-loss durability guarantee, and not an fsync change. A failure can
leave a staging file for diagnosis; a valid previously written solution may
coexist with older statistics, with the nonzero process status distinguishing
that failure. Concurrent processes must continue to use disjoint output and
staging paths. The pre-execution alias check does not defend against concurrent
external path replacement. Existing destination symlinks/hard links are replaced
as entries during final publication rather than used to truncate their referents.

No competition draft, attachment, registration, or submission is changed by this delivery. S139 stays unsent. Temporary publication automation is removed from the delivered tree; the permanent change is the solver I/O repair plus its scoped regression evidence.

## Sources and attribution

Base source: woahwhattheheck/commons commit
`2885d176373c33410148829fef93c310c3752c0b`, fleet-candidate/main.cpp.
Original SHA-256: `322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1`.
Current composed source before this repair: Git blob `891c87fb2976a7dff6d914eafe9c0ca14b893646`, SHA-256 `77cfa308b87e941b130f837b13f62564e8ee098911f45d9c06d2648b0aa83c05`.
Repaired composed source: SHA-256 `79362dbf9d47ca921de508a9253e7c2642c57459487a88ea754780b673961724`.

SEDGE and FLORA retain the MIT-licensed algorithm attribution. TRACE's existing
source/vendor transport and QUARTZ's verified checker context were reused;
neither source exporter nor benchmark was repeated. RapidJSON and checker
sources retain their own notices. Only the output-preservation change and its
new regression suite are this contribution.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
