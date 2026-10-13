# Published sprint reference comparison

The existing `compare_checker.py` can now compare saved official six-decimal
checker output with the original public sprint CSV. Ordinary checker-to-checker
comparison is unchanged. This reads existing results; it starts no solver, checker,
container, network request, or submission.

## Run

```sh
python3 compare_checker.py /saved/setA-01/checker-6.json /data/loads_vector.csv \
  --sprint --instance setA-01 --output /saved/sprint-comparison.json

# Compare an explicitly named subset, organized as setA-XX/checker-6.json.
python3 compare_checker.py /saved/A-results /data/loads_vector.csv \
  --sprint --output /saved/A-vs-sprint.json
```

The CSV is `sprint_results/loads_vector.csv` from Orange's official challenge
repository at `d84d319a7fdb8de3b1866830d2eaa2937871e5ae`:

https://gitlab.com/Orange-OpenSource/network-optimization-tools/challenge-roadef-2026/-/blob/d84d319a7fdb8de3b1866830d2eaa2937871e5ae/sprint_results/loads_vector.csv

Exact bytes: **315,412**, SHA-256
`b6218e41ac204e73c4688aa9e0e56825c1f5b864440675c4f7ffba27a75f45ca`.
Use the already-retained official archive or QUARTZ's unchanged Library file
`ROADEF-sprint-loads-vector-d84d319a.csv` (backing ID
`file_00000000e4cc81f5998f71bb1196c1bb`). This utility does not download it.

The real header is `Instance,Best team,1,...,4000`. Its 20 rows have different
lengths, totaling **35,944 saturation values**. A short row is a shorter complete
vector, not a row to pad to 4,000 columns. Zero-valued tails remain included.
Malformed, duplicate, non-descending, nonfinite or over-precision rows are not
silently repaired. The official loader checks the exact CSV identity before
parsing; the separate format parser alone makes no provenance claim.

## Interpretation and identity limits

The source contains ranked values and best-team labels, **not** link/time
coordinates, underlying solutions, or original network/traffic/scenario hashes.
A file therefore requires an explicit `--instance`; a root uses the literal
subdirectory names. Unknown names and unequal vector lengths are errors. Several
instances have equal-length vectors: matching length cannot establish identity.
Every report declares `input_file_identity_verified=false` and states that the
instance name is caller-declared. Keep the original benchmark's input, solution,
checker-command and binary manifests beside this comparison. Do not relabel a
checker output from another instance to make its shape fit.

The existing checker parser still validates its full coordinate set and requires
six-decimal values; no rounding is added. Both comparison modes use the same full
sorted-vector lexicographic comparison. `first_changed_rank` is 1-based, including
changes below the largest load. Transition cost is diagnostic only and never a
tiebreak. Candidate validity, checker SHA, reference SHA, row/team identity, full
vector length and unmatched reference instances remain explicit in the output.
An invalid candidate is reported as invalid, not assigned a fictitious vector.

This is a **historical per-instance reference comparison**, not a qualification
ranking or matched-resource benchmark. The sprint and current runs do not have
matched resource budgets. A best-team row is not a single competing solver
portfolio across all instances. This delivery supplies no new competitive score;
it only makes the already-published comparison executable.

## Callables

- `load_sprint_reference(path)` verifies and parses the original CSV.
- `compare_sprint(load_result(checker_path), reference, instance)` compares one
  explicitly named result.
- `sprint_report(root_or_file, csv_path, checker_name, instance)` builds the same
  document used by the CLI.
- `compare_vectors(a, b)` is the shared ranking core; inputs are nonempty,
  equal-length vectors already sorted in descending order by their input loader.

## Executed tests

```sh
# Extract the exact preceding comparator (HAZEL PR10179) without modifying it.
git show 871710b6784ef56e7c8541647dcca8235e9eb86e:revenue/roadef2026/fleet-candidate/compare_checker.py \
  > /tmp/compare_checker_original.py
python3 -B test_sprint_reference.py --reference /data/loads_vector.csv \
  --original /tmp/compare_checker_original.py -v
```

28 methods pass on Python 3.13.5. They ingest all 20 genuine reference rows and
35,944 values, exercise file/root CLI behavior and malformed-data cases, and
compare 500 deterministic valid/invalid/tied checker-record pairs against the
preceding comparator. HAZEL's `load_result` AST remains unchanged; the ordinary
file-to-file CLI returns byte-identical output on its retained fixture.

Candidate checker documents used in these tests are explicitly manufactured
comparison fixtures, including copies/perturbations of public reference vectors.
They are **not our solver outputs, official-checker executions, or new contest
results**. No public A/B solver run, native/Docker validation, benchmark restart,
submission or draft modification was performed for this consumer.

Source implementation: BRIDGE, composing HAZEL's repaired parser and the existing
fleet comparator. Public data: Orange's pinned sprint reference; byte-only handoff:
QUARTZ. Existing solver and benchmark owners retain their work.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
