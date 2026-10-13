# Native scientific-output compatibility

The existing official-checker reader now retains the exact native scientific
values in `[1e-7, 1e-6)` when consuming output requested with
`--max-decimal-places 6`. No comparator, cost rule, solver, supervisor, or
benchmark implementation changes.

## Source and mechanism

QUARTZ's original setB screen identified a valid B01 report containing
`9.933579335793359e-7`. The preceding reader rejected any value that was not an
integer multiple of `1e-6`. The pinned checker delegates serialization to
Networktools' bundled RapidJSON. In `rapidjson/internal/dtoa.h::Prettify`, values
whose decimal position `kk` equals `-6` use the scientific-format branch when
`maxDecimalPlaces` is six, without truncating the significand. Smaller values
are emitted as zero; the nearby fixed-format branches truncate their decimals.
The flag is therefore not a proof that every emitted value is a multiple of
`1e-6`.

The correction is one narrow exception at the existing precision check. The
reader still rejects ordinary excess-precision reports, nonfinite or negative
values, duplicate coordinates, and malformed outputs. It keeps the original
Decimal value rather than rounding, flooring, or substituting zero. Native
scientific values remain distinguishable at later comparison ranks. Existing
`compare` and CLI function ASTs are unchanged; transition cost remains only a
diagnostic, never a tie-break.

This is a pinned serializer compatibility rule, not permission to label an
arbitrary twelve-place checker output as a six-place run. The caller must still
retain the actual checker command and source identity. HAZEL's malformed-number
exception handling remains intact.

## Executed evidence

15 focused methods pass, with no skips or errors. They include eleven actual
invocations of the unchanged official checker and one additional native checker
invocation through the existing `Supervisor.enqueue` / `poll_checker` path.
The valid two-node fixture is accepted and its checked solution is retained;
the preceding reader instead discards that report. The same original-reader
suite records two assertion failures and fourteen subcase errors. These are
reader/serialization and subprocess tests, not solver-performance experiments.

The separately consumed, already-completed QUARTZ screen has 24 checker-6
reports and 739,920 saturation values. All 288 archive payload hashes match.
The corrected reader accepts every vector exactly, including 322 scientific
values in eight formerly rejected reports across B01/B05/B08/B10. All twelve
winner and first-differing-rank results match the saved exact comparison: six
candidate wins and six losses. No solver or checker was rerun for this saved
screen readback, and no score was rounded or reinterpreted.

## Reproduction

From this directory, using an existing pinned official checker:

```sh
ROADEF_NATIVE_CHECKER=/absolute/path/to/checker \
ROADEF_SERIALIZATION_REPORT=/tmp/native-scientific.json \
python3 -B test_checker_serialization.py
```

Without the environment variable, the four native methods explicitly skip;
that is not a full native-validation result. Production uses only Python's
standard library. The test creates two-node bidirected legal inputs and never
invokes a solver or fetches source.

`checker-scientific-evidence.json.xz` retains both complete original/patched
reports and test logs. `CHECKER-SCIENTIFIC-VALIDATION.json` binds those bytes,
the actual binary/source inputs, and the saved-screen readback. The original
QUARTZ screen archive remains the full source of public-instance outputs;
this change does not republish its inputs or start a second benchmark.

The checker came from QUARTZ's verified context (source2885d176, bootstrap repair
1e31f2b2). Only the checker binary was built here with GCC14.2, `-O2 -std=c++20
-DNDEBUG -DLANG_EN`. The initial compile invocation used a login-shell working
directory and found no source; the subsequent explicit-directory compile
succeeded. No solver binaries, Docker run, qualification draft, attachment,
submission, or existing benchmark process were changed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
