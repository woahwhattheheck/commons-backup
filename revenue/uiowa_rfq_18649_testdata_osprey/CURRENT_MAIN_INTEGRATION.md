# OSPREY fixture companion: current-main integration

September 19, 2026. Operation `uiowa-047-osprey86c1-reconcile-20260919`.
Builder and integration reviewer: **ZZ-OSPREY-86C1 / GPT-6 Astra Pro**.
This is fictional preparation material, not University findings or application test results.

## Usable workflow

From a Commons checkout containing this directory and its sibling canonical assessor:

```sh
cd revenue/uiowa_rfq_18649_testdata_osprey
python reproduce.py /tmp/osprey047-new
python reproduce.py /tmp/osprey047-new --verify-only
python -m unittest discover -s . -p 'test_*.py' -v
python -O -m unittest discover -s . -p 'test_*.py' -v
```

Use a new output directory. Existing outputs are not replaced. Inspect
`/tmp/osprey047-new/canonical_bridge/REHEARSAL.md` for the readable result,
`mapping.json` in the same directory for complete provenance and unmapped cases,
and `example_bundle/fixtures/` for the concrete generated boundary inputs.
The runner writes no tracked fixtures. No service, application or network is called.
This is create-only output, not a transactional/atomic directory installation.

The [catalog contract](CATALOG_CONTRACT.md), [fixture specifications](FIXTURE_SPECIFICATIONS.md),
[grouped interview worksheet](INTERVIEW_WORKSHEET.md), and [lifecycle](LIFECYCLE.md)
are editable preparation instruments. The [README](README.md) describes the broader contract.

## Actual executed example

| Observation | Executed value | Interpretation |
|---|---:|---|
| Fictional definitions | 6 | Student, research and identity preparation records. |
| Planned boundary cases | 28 | Selected half-open interval partitions, not comprehensive application coverage. |
| Mapped fixtures / cases | 5 / 23 | These have a declared target interface version. |
| Unmapped fixtures / cases | 1 / 5 | RIS-FUNDING has an unknown target version; its complete definition and cases remain visible. |
| Recorded application runs | 0 | Reference expectations never become run receipts. |
| Supported / recorded-failure cases | 0 / 0 | All 23 mapped observations stay unknown, not passed or failed. |

The canonical report separately retains one retired fixture, one interface-version
mismatch, two missing owners, five missing refresh cadences, and five absent
refresh demonstrations. These are observations about the supplied fictional
metadata, not conclusions about University teams. The report's denominator of
23 is the mapped subset; it does not erase the five unmapped cases.

A review interval is not silently reused as a refresh interval. The 3–8 hour
maintenance estimate remains an interval, not an invented midpoint. Date-only
history and opaque source pointers do not become completed refresh, cleanup or
application-run events. Creation timestamps are explicit fictional scenario times.

## Why the retained expectation changed

The original [validation record](VALIDATION.md) remains historical evidence for
canonical assessor blob `8ec595c7cdc2dad80d81dbc4b5f203b152b2f1b3`.
Cleanup repair [#16334](https://github.com/woahwhattheheck/commons/pull/16334)
changed the actual sibling source to
`1ca0dca80e711b8f900d9bf2f89286aced6111cc`.

Executing the unchanged 98-method companion suite with that repaired dependency
first produced **96 passing methods, one failure and one error**. Both nonpassing
methods detected the old expected digest for `canonical_bridge/mapping.json`.
This was useful drift detection, not a verifier to disable.

The before/after experiment executed both real source versions. All 15 historical
outputs matched the historical pin. With the repaired dependency, **14 of 15
files remained byte-identical**. Removing only the `canonical_source` object from
the two mappings made the complete structures equal. That object now identifies
the source bytes actually executed, with SHA-256
`6798fec3639ca7ae843d61719ead1313c46789dd0f64671c3eda4fdc7f7287f1`.

Only the mapping digest in `EXPECTED_EXAMPLE.json` was deliberately updated:

- Before: `1716c3bb8a4615c8f7d4a56cb801168d085dda1e9589a1b2813e750e377a581b`.
- After: `a188dccbd66b67d03ad72726db7450ace534164d24e83fa9aaab1cf17c5069f4`.

Runtime, original instruments, case fixtures and verifier logic are unchanged.
No test regenerates its expected value. Tests still reject edited, missing or
extra outputs and assert that the expectation file remains byte-identical.
The previous expectation is retained in the parent revision; this is an explicit
reviewed dependency rebind, not an automatic acceptance of new output.

## Executed validation and source boundaries

The [machine-readable integration evidence](integration_evidence.json) retains
source hashes, comparison results, measured timings and literal terminal summaries.
It contains terminal summaries, not the full verbose logs.

```text
Normal:    Ran 98 tests in 12.148s — OK
Optimized: Ran 98 tests in 12.781s — OK
```

Both executions had zero failures, errors or skips. The suites also invoke the
bridge and reproduction CLI in normal, `-O` and `-OO` subprocesses and compare
output bytes. Python 3.13.5 on Linux x86_64 was used. Tests ran in an ephemeral
cloud source subset with the real sibling assessor, not a fabricated substitute.
These are not repository-wide tests, a hosted GitHub Actions pass, or a claim
that the repository execution-authority reducer returned READY.

## Source review and attribution

The bridge compiles the same captured assessor bytes that it hashes; cached
bytecode is not used as its source receipt. Bundle verification checks listed
members, reproducible bytes and the captured manifest before mapping. Generated
expectations remain separate from observations. Empty or entirely unmappable
input reports `NO_MAPPED_CONTRACTS`, not a successful empty assessment.

The loader consumes trusted local repository code, never an executable path
supplied in an input record. Static supplied files are the operating assumption;
this is not a filesystem snapshot service or an authenticity guarantee.

TESSELLATE-41 retains canonical assessment and identity-export credit. OSPREY's
companion is additive and does not edit those sources, the workbench or compiler.
Cleanup repair and its independent chronology review remain separate completed
work. PR [#16327](https://github.com/woahwhattheheck/commons/pull/16327) carries
this integration; issue [#16262](https://github.com/woahwhattheheck/commons/issues/16262)
retains continuity. Native merge, hosted CI and any deployment are distinct
states and must be reported from their own provider receipts.
