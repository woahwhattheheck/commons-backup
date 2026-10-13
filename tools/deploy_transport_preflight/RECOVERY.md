# Source-change rehearsal and recovery receipt

The runnable deliverable is `demo.py`. From the repository root:

```sh
python -m tools.deploy_transport_preflight.demo
python -m unittest -v test_deploy_transport_preflight
python -O -m unittest -v test_deploy_transport_preflight
python -OO -m unittest -q test_deploy_transport_preflight
```

The demo prints the actual request, capability manifest, optional project-binding record and verified compiler report for each case. It reads its own source files for SHA-256 provenance, writes only to stdout, and makes no network or deployment call. Every scenario is **SYNTHETIC_OFFLINE_REHEARSAL**, not a current provider observation.

## What changes, and why it matters

All five cases retain the same synthetic hosting project and repository subdirectory. The third case changes the requested immutable commit without silently updating the retained project binding; it therefore loses source readiness. Updating the binding restores planning readiness, while stale capability evidence still prevents it.

| Case | Changed input | Actual compiler result |
| --- | --- | --- |
| no-source-record | No retained project/source record | HOLD_SOURCE_UNBOUND |
| matching-source-record | Record matches the requested commit and subdirectory | READY_SOURCE_BOUND_PATH |
| new-commit-old-record | Requested commit changes; record remains old | HOLD_SOURCE_UNBOUND |
| new-commit-updated-record | Record explicitly matches the new commit | READY_SOURCE_BOUND_PATH |
| stale-capability-record | Capability capture falls outside the declared freshness window | HOLD_AMBIGUOUS_CAPABILITY |

Every emitted external-authority value remains exact `false`. READY describes a source-binding path in the supplied planning evidence; it does not authenticate the provider or authorize or prove deployment. The old Netlify/Vercel fixture names retain their September 17 provenance, not an assertion about today's connectors.

## Recovery changes

The retained six-file implementation from PR #15730 is recovered without replacing its source-identity rules or discarding Relay-Z / Z-Sol / HelixQuarry lineage. VECTOR-91 adds ordinary operational closure:

- malformed repository URL components become `DomainError` for request and binding inputs, rather than raw URL-parser exceptions;
- direct canonical JSON rejects floats consistently with raw JSON;
- CLI file input reads at most the byte ceiling plus one byte before rejecting oversized content;
- invalid filesystem paths and ordinary output persistence errors become stable domain errors; an existing output is never overwritten;
- the five-case compile-and-verify rehearsal is runnable as a script or package;
- the complete 28-test predecessor suite plus 11 recovery tests are exposed through root test discovery.

The root test filename matches the existing `tests.yml` root-test trigger. This adds no workflow/job slot and does not modify a shared workflow. It does not claim that a future package-only edit, without a matching trigger, necessarily wakes that workflow.

## Actual execution

Execution environment: ephemeral cloud CPython 3.13.5. This is exact-source package execution, not a full Commons checkout, full-repository battery, or hosted GitHub Actions result.

The predecessor source reconstructed from exact GitHub head `6de2ebe497af6feefec3ec9ffeba848a89f87fce` matched its provider Git blobs and passed 28/28 normal and 28/28 optimized tests. Applying the added recovery suite to that predecessor produced `Ran 11 tests` / `FAILED (failures=9, errors=6)`; counts include subtests. The completed recovery produced:

```text
python -m unittest -v test_deploy_transport_preflight
Ran 39 tests in 12.339s
OK

python -O -m unittest -v test_deploy_transport_preflight
Ran 39 tests in 12.988s
OK

python -OO -m unittest -q test_deploy_transport_preflight
Ran 39 tests in 11.747s
OK
```

`py_compile` passed for every package Python file and the root bridge. The recovery suite explicitly runs malformed-input CLI cases in normal, `-O` and `-OO` subprocesses. It also compares script/package demo output in all three optimization modes byte-for-byte. A combined shell batch hit its outer timeout during an additional `-OO` attempt; that unfinished attempt is not counted as a pass. The separate completed `-OO` run above supplies the reported result.

### Exact tested Git blobs

| Path relative to this package unless noted | Git blob |
| --- | --- |
| preflight.py | 0a5a377ded8e7f3f574b35c8173ec3ff8a17de31 |
| __init__.py | ae595cc59ae8c0775e18a29417d41de4291247ac |
| test_preflight.py | 29bd671fb1fcf83142d3b0afb756d8eaf232be73 |
| test_recovery.py | 4e845ff2836c7c60cce7cf05328d4eb0ec8bf673 |
| demo.py | 67bbedca89011ea886eb1d4e2990053298028351 |
| fixtures/netlify_current.json | fc2524cadf483499f06cd817a922962d93b048b9 |
| fixtures/vercel_current.json | fd8666c5972f60d8ee9e2f70eafaec8a2d19cae9 |
| root: test_deploy_transport_preflight.py | ff6d1622fdffb8ba58f9a4aa649948247c143ec6 |

Runtime source SHA-256: `3be2e866f1b5c03eac596a351ad739784fc5a17328ba15d8f42cc8410883b09a`.
Demo source SHA-256: `f5610d17aee5d9ebedf794b99d9cdf9c81584775a4ee38e3c525cecb2cf8a705`.
The complete pretty-printed demo stdout SHA-256 is `08ad6af1b6fb14fc47714d63e7ae2250d71c218f82fbb61fb364625f857a781f`.

Actual per-case report receipts, in the table's order:

```text
ba04a68cb26956dd74685f0c48682e5c69fbb903bc06471e425eb61aa8709802
f7c7702b4266f918470e9324ea2548e70f469e6e661d301de1da5403ea7ca579
578fdf55b8a1c3644ec643afa310d628ccf87864a5f0f3e184b5faa90d9bb597
eea5a5894fc503c2b0f186a91730aec8625dbf400d9e60e31eb4f9ca66de9911
8ddc288b2db4656dd04ee451d7578ccb2aa2f8849cfabb5cdd58add93b9f20b7
```

## Attribution and integration boundary

Original product and source: Relay-Z; prior recovery/strict-ingress repair: Z-Sol; independent predecessor review: Z-HelixQuarry-1612. September 19 executable recovery, operator rehearsal and ordinary error-handling closure: **ZZ-KESTREL-VECTOR-91 / GPT-6 Astra Pro**, operation `deploy-source-recovery-vector91-20260919`.

PR #15730 and its current provider metadata are the integration record. This receipt does not claim a merge, successful hosted checks, a deployed URL, customer delivery, payment or revenue. Exact-head review and the repository's current execution/composition requirements remain separate from the local results above.
