# Supplemental evidence component

`supplemental_receipt.py` is an additive, pure helper for the existing
`check_joint_receipt.py` reader. It is not another CLI, workflow, archive reader,
or result producer. It has no filesystem or network operations and does not
import the base reader, so the base can call it without a circular import.
Python 3.10+; standard library only.

```python
from pathlib import Path
import check_joint_receipt as core

path = Path("/path/to/existing-validation.zip")
receipt = core.inspect_archive(
    path,
    expected_sha256="1323e92edc15bfe7a767dc02c60ffb3c45a0254f802397cf8b820522094a49ab",
    expected_checkout="428b4437cbce55785c558252911a8acb826d8f59",
    expected_run_id="34166821802", expected_attempt="1",
)
print(receipt["status"], receipt["reported_test_methods"])
```

The integrated reader already invokes this helper. Do not call the helper again
on that final result. A custom reader implementing its own original three-suite
phase can call `inspect_supplemental(members, snapshot, three_suite_receipt)`
with its already-read objects rather than read the ZIP again. The helper never modifies
any input. `core_receipt` is the original three-suite result before adding
supplemental counts; do not pass an already-expanded total and count it twice.

The result has `suites`, source hashes, issues, represented-suite count and
reported method totals. `status` describes the supplemental checks only;
`core_status` is carried separately. Preserve both statuses and combine their
problems in the one reader. A supplemental `COMPLETE_PASS` with zero represented
suites is not a claim that an incomplete historical core passed.

Coverage includes the represented loader (at least 7 methods), empty-lot
(15), joined-wrapper (6), capture-binding (22), score-schedule (10), and
workflow-bindings (8) suites. Representation is the suite's **test-source**
snapshot row or a log/report member. A shared runtime dependency alone does not
declare execution of a newer test. Missing logs then remain explicit;
`require_all=True` requests all six even from an older artifact. Count,
completion order, qualified/failed summaries, UTF-8, source hashes, loader
report schema, errors and declared gameplay scope are checked. CRLF logs are
supported. Log-only suites bind through the existing workflow checkout/source
snapshot; this is consistency checking, not execution attestation.

Funded-join and later suites, provider-digest/engine validation, unknown-log
handling and aggregate `COMBINED-RESULTS.json` schema belong to the enclosing
reader/producer. RECEIPT owns that reader integration; ATLAS owns the producer.
This helper does not claim those further suites as covered.

## Executed inputs and tests

Existing artifact10034414947 / run34166821802 attempt1, SHA-256
`1323e92edc15bfe7a767dc02c60ffb3c45a0254f802397cf8b820522094a49ab`:
unchanged core reader47c15bde gives51 methods; helper gives28 supplemental
methods,79 together, no helper problems. Exact checkout is in the example.
These are existing FINCH/ATLAS/WREN/INTEGRATION/GPT results, not rerun suites.

Historical artifact10033736596 / run34164624483 attempt1, SHA-256
`cb8ed67dd2749ecd69d414802c31d7b31c58cd2744675dd5c6b4e1a8a96a5d31`:
the original37 methods and core `INCOMPLETE` remain unchanged. There are zero
represented supplemental suites. No absence is relabeled as execution.

```sh
cd revenue/kaggriculture/cloud-selected-joint-checks
python3 -m unittest test_supplemental_receipt test_supplemental_cover -v
```

All 44 helper tests pass: the original 22 keep their historical three-suite
fixture, and 22 new methods exercise the added contracts. These are synthetic
parser fixtures, not the archived agent suites. The initial source/artifact
receipt stays in `SUPPLEMENTAL-VALIDATION.json`; current-source evidence is in
`SUPPLEMENTAL-COVER-VALIDATION.json`. The base reader, its tests, README and
VALIDATION remain owned by RECEIPT and are not modified by this component.
No new provider job, game, seed, source export, default-policy change or
owner-PC action is part of this change.

## Added COVER contracts and actual 159-method input

The existing signature and tuple layout in `SUPPLEMENTS` are unchanged, so
RECEIPT's enclosing reader can derive the new labels directly. The first source
path in each tuple is its test-source anchor; later paths bind dependencies.
`capture_binding` reads the producer's actual nested `tests` object with
`run`, `failures`, `errors`, and `success`; this report does not use the loader's
schema. It also checks `runtime_sha256`, `optimizer_sha256`, and `games=0`.
Score-schedule and workflow-bindings are log-only contracts tied to their test
and runtime/workflow source snapshot rows.

Existing artifact10037249764, run34175970193 attempt1, checkout
`4ab883af10561fa7f685f90a79e98f80f7061fc0`, SHA-256
`ddacdc557419258c072e1c2ef62ebe4d101a5f3b79e6967a153a650268a6d42d`
was read without rerunning any archived method. The helper reports 68 methods:
the original 28 plus capture22 + score10 + workflow8. The unchanged historical
core boundary reports51, giving119 for that boundary plus this helper. Funded16
and reporter24 belong to the enclosing reader, which is responsible for the
complete159 result and aggregate/input-digest checks. Do not add those counts
inside this helper or pass an already-expanded core subtotal.

Six in-memory alterations of this real input were also exercised: removing each
added log produces INCOMPLETE, and changing the capture test failure record,
runtime hash or optimizer hash produces FAIL. The original provider ZIP is
unchanged. Real79 and37 archives retain their previous helper coverage and core
statuses. Deadline cancellation and other later schemas remain separate.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
