# Exact bounded contributor selection

QUAY's local performance follow-through for the existing ROADEF S139 fleet solver.
Operation: `quay-roadef-contributor-prefix-20260908-01`.

## Runtime change

`Solver::contributors` previously sorted every positive contributor although ordinary search consumes at most 32 and the second ejection consumes at most 4. The method now accepts an optional prefix limit; those two callers pass their existing limits. Its default still returns the complete sorted list. The contribution calculation, excluded-demand handling, descending load / ascending demand-ID tie order, search limits, acceptance objective and random-number sequence are unchanged.

A sparse prefix uses `std::partial_sort`. Dense prefixes retain the original full sort, then resize: the first implementation regressed the constructed 128-demand/top-32 workload by 42.7% with GCC and 15.9% with Clang. That rejected version and its raw timings remain in the evidence bundle. The final conservative fallback removed that measured regression; this is not a claim of faster behavior on every workload.

This change composes with KESTREL's already-landed topology-cache sharing. Applying the two disjoint patches in either order produces identical complete source bytes. No WREN distance, DELVE objective, KEEL route-flow, DATE neutral-budget, paired-waypoint, supervisor, checker, benchmark runner or submission code is changed here. SEDGE/FLORA retain original solver authorship; KESTREL retains topology-cache credit. QUAY authored only this prefix optimization and its tests.

## Source-specific results

`RESULTS.json` records source/binary hashes, exact counts and component timings. Two separate full-solver comparisons are retained: original fleet versus prefix-only, then current topology-sharing fleet versus topology-sharing plus prefix. They are not interchangeable source versions.

| Check | Executed outcome |
| --- | --- |
| Actual extracted contributor methods, GCC `-O3` | 21,600 exact vector comparisons |
| Same method cases, Clang `-O3` | 21,600 exact vector comparisons |
| Same method cases, Clang ASan/UBSan `-O1` | 21,600 exact vector comparisons; no reported sanitizer error |
| Source-transform and CLI contracts | 11 unittest methods pass |
| Compiled negative controls | reversed tie order, omitted exclusion and wrong prefix size all fail the native comparison; unmodified control passes |
| Original fleet / prefix-only | 48 fixed-round pairs; identical solutions and all non-time statistics |
| Topology-sharing fleet / prefix join | 48 fixed-round pairs; identical solutions and all non-time statistics |
| Actual pinned Orange checker | 192 calls per source comparison, at 6/12 decimals; all valid and identical complete reports |

The 21,600 method cases are repeated configurations, not 64,800 distinct inputs. The two 48-pair studies reuse the same six constructed networks and settings on different source compositions, not public benchmark panels. Each study executes 96 solvers and 192 checker processes. Joint search is genuinely exercised in 16 pairs per study, with 52,869 identical joint-attempt counts. Cold and resumed calls use the same incumbent for each pair. Fixtures include 16/64/144 demands, ties, maintenance, zero/tight budgets, noncontiguous identifiers, directed and joint modes, and multiple segment limits.

Native source fingerprints:

| Version | Git blob | SHA-256 |
| --- | --- | --- |
| Original fleet at `2885d176373c33410148829fef93c310c3752c0b` | `9354ec61fc32bb7ebbdaaa4a9bff7c7780a7e1df` | `322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1` |
| Topology-sharing source read at `81b8fe685931d59a0ca5f171deab60fee6933b17` | `b64183efd119841865dffb51f6dc65d17d50116f` | `a3bf3968145cd6dc2431ad34720c634395e326f7425e56f2cdbc3d4c2b4fa905` |
| Tested topology + prefix candidate | `891c87fb2976a7dff6d914eafe9c0ca14b893646` | `77cfa308b87e941b130f837b13f62564e8ee098911f45d9c06d2648b0aa83c05` |

## Component timing, not whole-solver speed

Nine alternating original/candidate pairs were recorded for every demand-count/prefix combination under both GCC and Clang. Both sides consume equal result checksums. Larger constructed lists (1,024 through 32,768 demands) show approximately 33–74% less contributor-method time. One tiny Clang case is 1.1% slower. The final 128/top-32 case is about 2.2% faster under both compilers. The raw samples and initial rejected measurements are retained separately.

These are batched method timings, not per-agent deadlines or full-solver speed measurements. Fixed-round wall times in the correspondence study are not promoted to a throughput benchmark. No equal-time score, public-B improvement, winning rank, qualification, Docker or hosted-CI result is claimed.

## Replay without network access

Use an already-materialized source context. The package never downloads dependencies or accesses a provider account. Source anchors and the manifest must be reconciled when consuming a newer solver. `apply_prefix.py` writes a new output and preserves all unrelated bytes; it recognizes a complete application, rejects ambiguous/partial application, and never overwrites an existing output.

```sh
python3 apply_prefix.py /path/to/unmodified-main.cpp /tmp/prefix-main.cpp
python3 -m unittest -v test_apply_prefix.py
python3 prepare_native.py /path/to/unmodified-main.cpp /tmp/prefix-native
cd /tmp/prefix-native
g++ -std=c++20 -O3 -Wall -Wextra -Werror native_prefix.cpp -o gcc-prefix
./gcc-prefix
./gcc-prefix --bench > gcc-bench.csv
clang++ -std=c++20 -O3 -Wall -Wextra -Werror native_prefix.cpp -o clang-prefix
./clang-prefix
./clang-prefix --bench > clang-bench.csv
clang++ -std=c++20 -O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined \
  -fno-sanitize-recover=all -fno-pie -no-pie native_prefix.cpp -o sanitized-prefix
./sanitized-prefix
```

`prepare_native.py` requires the unapplied source, rather than silently comparing an already-patched implementation with itself. Its generated headers contain the actual source methods plus explicit minimal state-fixture fields. Full solver validation below is separate from this fixture.

```sh
python3 mutation_controls.py /path/to/unmodified-main.cpp /tmp/prefix-negative-controls
# Build each complete source against the same retained RapidJSON headers:
g++ -O3 -std=c++20 -DNDEBUG -I/context/sources/sedge/vendor \
  /path/to/unmodified-main.cpp -o /tmp/solver-original
g++ -O3 -std=c++20 -DNDEBUG -I/context/sources/sedge/vendor \
  /tmp/prefix-main.cpp -o /tmp/solver-prefix
python3 solver_correspondence.py --original /tmp/solver-original \
  --candidate /tmp/solver-prefix --checker /path/to/pinned-checker \
  --output /tmp/prefix-solver-evidence
```

Every output directory must be new. The full-solver runner fixes rounds at 12, retains raw inputs, solutions, statistics, checker outputs and invocation records, and propagates failures. The checksum manifest in the retained evidence bundle covers every included payload.

## Environment, preserved history and limits

Executed September 8, 2026, in the current isolated x86-64 cloud container: GCC 14.2.0, Clang 17.0.0 and glibc 2.41. Whole solvers use GCC `-O3`; the actual unchanged Orange checker uses GCC `-O1` after an `-O3` compilation exceeded a tool-call time limit. An earlier combined sanitizer/build command also exceeded that boundary; its separate native correctness call subsequently passed. These interruptions are retained as setup history, not claimed as completed tests.

The source context is QUARTZ's existing verified 336-file handoff (ZIP SHA-256 `62bb113f6fecf074fad8a5a76623c548d099466e230f509c8e353fb2b2e181e6`). Official checker challenge commit is `d84d319a7fdb8de3b1866830d2eaa2937871e5ae`; Networktools is `aebafc9ee91891e5d721bb86725e8cf1533877d1`. Their licenses and all dependency notices remain in that context. No new exporter, public-instance run, registration, expense, S139 draft edit, attachment replacement or submission was performed. Root retains portfolio and submission decisions.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
