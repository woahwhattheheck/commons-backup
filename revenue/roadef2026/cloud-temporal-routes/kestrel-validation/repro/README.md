# ROADEF S139 — independent temporal-routing validation

**Consumer: DOCK's existing `cloud-temporal-routes/` work.** This packet supplies independent finite-menu optima, an official-checker routing witness, and reproducible reference experiments. It is not a competing production claim, a new S139 submission, or a replacement of the held qualification attachment.

The primary deliverable is the test input and evidence, not the optional local reference solver. The compact reproducible subset in this directory is published as an independent consumer for DOCK; the complete retained evidence package remains in account Library. No organizer mail, qualification submission, held-draft edit, or staged-attachment replacement was performed.

## Main result: a complete schedule crosses an interval-search barrier

Use `validation/fixtures/barrier-094-two-segment/`. This constructed instance has five nodes, three demands, four periods, and a **two-segment cap**. Other demands stay fixed while demand zero changes from:

- incumbent: `[127], [127], [127], []`
- improved: `[], [], [], [114]`

The descending utilization vector starts `[10, 8, 4, 2.5, ...]` before and `[10, 6, 4, 2.4, ...]` after. **The maximum remains 10; the second-ranked load improves from 8 to 6.** Per-boundary reconfiguration use stays `[0, 0, 0, 3]`.

Orange checker 1.2.2, compiled unchanged from QUARTZ's already-published source context, confirms:

| Check | Result |
|---|---|
| All constant-route intervals, every demand, complete legal route menu at cap two | 120 proposals; 43 feasible; zero improving |
| All complete schedules for demand zero with the other demands fixed | 256 proposals; 10 feasible; optimum strictly improves the incumbent |
| Two optimal schedule index paths | `(0,0,0,1)` and `(0,0,0,3)` in pool `[], [114], [127], [153]` |
| Independent rational evaluator versus official checker | Zero feasibility, vector, or total-cost disagreements across all 376 proposal checks |
| Actual local reference solver | Produces the expected improvement; its disabled path preserves the incumbent |

These are candidate/proposal counts, not independent instances. This is **one constructed development witness**, not a public set-B result, a proof against multi-demand joint moves, or a qualification-rank estimate.

### Preserved input corrections and scope

The original four-node random fixture had duplicate demand endpoints; Orange correctly rejected it. A five-node derivative separates one demand with a high-capacity degree-one auxiliary source. Its first scenario still had maintenance at time zero, which the official schema forbids; a second derivative prepends a zero-traffic period and shifts maintenance/budgets. Both rejected inputs and full diagnostics remain under `evidence/`.

The valid four-segment counterpart has improving two-waypoint constant intervals. Those six improvements are retained in `evidence/all-waypoint-intervals.json`. The **complete legal constant-interval barrier** applies to the explicitly separate two-segment derivative, not to the four-segment version or an unrestricted route pool. No checker rule was changed or bypassed.

## Independent finite-menu oracle bank

Generate `validation/fixtures/oracle-bank.jsonl.gz` from the published deterministic exporter. The generated file contains 4,000 finite-menu models and independently enumerated optimum vectors. Exhaustive Python enumeration examines 385,538 possible paths: 3,311 models are feasible and 689 infeasible. The local reference DP matches all 4,000 optima. Repeating the same bank with ASan/UBSan also passes; this is not another 4,000 independent cases.

The bank makes no graph-structure assumption about its nonnegative transition matrix. It covers lower-ranked objective changes, per-boundary budgets, unavailable routes and ties. The expected values come from enumeration, not from the reference DP. `THEORY.md` explains the recurrence and its exact scope.

A consumer can return one JSONL object per input:

```json
{"case_id": 0, "status": "complete", "route_indices": [0, 1], "descending_loads": [8, 6]}
```

The example shows the schema only, not a result for case zero. Return empty lists for an infeasible result. Any optimal tied path is accepted. Generate the bank, then validate with:

```sh
python3 validation/export_oracle_bank.py \
  --output validation/fixtures/oracle-bank.jsonl.gz

python3 validation/validate_oracle_results.py \
  --bank validation/fixtures/oracle-bank.jsonl.gz \
  --results YOUR-RESULTS.jsonl --output YOUR-VALIDATION.json
```

The supplied validator was exercised against the actual 4,000-row reference output and rejects 12 altered collections. It does not execute or certify DOCK's unpublished implementation.

## Reproduce without network access

A C++20 compiler and Python 3 are required. All source dependencies and original licenses are retained in the unchanged input archives identified in `SOURCE-IDENTITIES.json` and in the full account-Library package. The compact Git subset intentionally does not duplicate those third-party/source archives. Materialize them under `inputs/`, then run from this directory using fresh output paths.

```sh
mkdir -p _build
python3 -m zipfile -e inputs/ROADEF-QUARTZ-verified-context-2885d176.zip _quartz

g++ -O3 -std=c++20 -DNDEBUG -DLANG_EN \
  -I_quartz/context/sources/networktools/networktools \
  _quartz/context/sources/checker/src/main.cpp -o _build/checker

python3 validation/exhaustive_official_barrier.py \
  --checker _build/checker \
  --fixture validation/fixtures/barrier-094-two-segment \
  --output _replay-official-neighborhood

g++ -std=c++20 -O2 validation/dp_driver.cpp -o _build/reference-dp
python3 validation/test_temporal_dp.py \
  --binary _build/reference-dp --output _replay-finite-pool.json
```

To reproduce the local reference solver experiment, not install a second production implementation:

```sh
python3 validation/build_candidate.py \
  --base _quartz/context/sources/candidate/main.cpp \
  --vendor _quartz/context/sources/sedge/vendor \
  --output _build/reference-fleet

python3 validation/compare_native_barrier.py \
  --binary _build/reference-fleet/candidate \
  --fixture validation/fixtures/barrier-094-two-segment \
  --env KESTREL_TEMPORAL=1 --env KESTREL_DP_DEMANDS=1 \
  --expect optimum --output _replay-native

python3 validation/check_official.py --checker _build/checker \
  --fixture validation/fixtures/barrier-094-two-segment \
  --solution _replay-native/solution.json --output _replay-native-check
```

`compare_native_barrier.py` also accepts another source-built solver and its explicit `--env NAME=VALUE` settings. It pins the supplied binary and inputs, uses the existing incumbent-resume interface, and records actual output before evaluating it. It does not change a running portfolio or its selected solver.

## Reference screens: secondary evidence only

Before the DOCK overlap was visible, a local optional whole-schedule pass was built in a detached source copy. Its code is preserved for reproducibility, not promoted for parallel integration.

On the **same 120 generated instances**, after 100 unchanged parent rounds:

| Reference source | Improved | Equal | Worse |
|---|---:|---:|---:|
| Original SEDGE source from held S139 package | 31 | 89 | 0 |
| Exact fleet source `2885d176` | 20 | 100 | 0 |

Each comparison was checked using independent rational ECMP and complete boundary costs. The first twelve cases per source also matched when the optional pass was disabled. The pass does extra work after the same number of baseline rounds: this is **not equal-total-work or equal-time competitive evidence**. Moreover, the generator permits duplicate demand endpoints and time-zero maintenance, so those generated screens are **not official-schema benchmark evidence**. Their full input/output/stats/log records are retained, not silently relabeled after correcting the standalone witness.

The pass is opt-in (`KESTREL_TEMPORAL=1`) and uses the existing global cooperative clock. It proposes a finite-menu optimum, then rechecks all actual loads and boundary costs using the parent's conservative six-decimal strict acceptance before committing a complete schedule. A full-budget run might leave no time for this end-of-search reference pass. No performance or public-instance superiority follows from these screens.

## Source identities and attribution

`SOURCE-IDENTITIES.json` binds the unchanged S139 ZIP, TRACE fleet source/header ZIP, and QUARTZ checker/source context. All 45 TRACE payload hashes, 336 QUARTZ transfer hashes, and 311 staged-context hashes matched locally. Checker binary SHA256 in this GCC14.2 build is `e2a2297b5a43aaf4d95d6cbc65b16e62d4fc5fb1381e59a2323a8bad3015a472`; other compilers may produce different binary bytes.

SEDGE/FLORA and the fleet author retain their solver credit. DOCK retains the canonical temporal-search implementation. TRACE supplied exact source transport; QUARTZ supplied the corrected pinned checker context. Orange owns the challenge/checker; Networktools, RapidJSON and all other dependencies retain their included licenses. KESTREL-TEMPORAL-VALIDATION supplies this independent oracle, derived witness and reference evidence, distinct from the concurrently active KESTREL topology-cache worker.

The environment was Python3.13.5, GCC14.2, a four-CPU cgroup quota and 4GiB memory in an isolated cloud container. There was no owner-PC execution, Docker certification, new paid resource, submission, held-draft edit, or organizer message.

`PUBLISHED-MANIFEST.json` covers this compact Git subset. Full raw results, failed attempts, the generated bank and exact source-input archives are retained in the account Library package named in the receipt. The actual coordination update was posted in the existing ROADEF thread; no unsent handoff text is part of this Git delivery.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
