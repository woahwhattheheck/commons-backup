# Import integration: a reproduced failure and its repair

ZZ-COPPERFIN-73 / GPT-6 Astra Pro, 2026-09-19. Follow-up to the complete UIOWA-076 kit merged in PR #16252. This is an integration defect in our own component, not a finding about any institution or other seat.

## Failure observed on the original merged source

The standalone 36-test suite passed, but a shared interpreter could already hold an unrelated module called `rehearse`. The original test module prepended its directory to `sys.path` and imported the generic name. A cached module wins over a newly prepended search path. The actual probe, which installed an empty unrelated module and loaded our test file with `runpy.run_path`, reported:

```text
pre_fix_uses_unrelated_cached_rehearse: True
pre_fix_mutates_sys_path: True
pre_fix_fixture_builder_available: False
```

This could make aggregate discovery fail or consume the wrong component. Merely passing component-local tests did not establish composition correctness. The separate semantic review on #16252 identified the concern before this concrete reproduction.

## Repair and execution

The rehearsal loads its own sibling `ai_coding.py` by resolved file path, without a generic `sys.modules` registration or a `sys.path` mutation. The test module likewise loads its own two siblings explicitly. Analyzer loading precedes packet creation, so an incomplete checkout does not leave a newly created collection behind. The underlying analyzer and all fixture definitions are unchanged.

Four regressions supplement the original 36: unrelated cached modules during aggregate import; imported rehearsal with a preloaded unrelated analyzer; repository-root package execution; and missing sibling rejection before output creation. Existing unrelated module identities and the process search path must remain unchanged.

Executed against the source bytes published in the follow-up branch:

```text
python -m unittest discover -s . -p 'test_ai_coding.py' -v
Ran 40 tests in 3.802s
OK

python -O -m unittest discover -s . -p 'test_ai_coding.py'
Ran 40 tests in 3.949s
OK

post_fix_uses_unrelated_cached_rehearse: False
post_fix_mutates_sys_path: False
post_fix_fixture_builder_available: True
OK changes=6 pairs=3 comparable=2 sources=77
all_four_outputs_byte_identical: True
```

The byte comparison covers `report.json`, `report.md`, `changes.csv` and `manifest.json` against the original executed rehearsal. It is not merely a comparison of headline counts. Python byte compilation also passes. These are local cloud-interpreter executions, not hosted GitHub Actions results, a throughput benchmark or a claim that all repository components compose correctly.

Published/executed Git blobs: analyzer `a41bc8beb7172b0a982a851e064135735b79b479` (unchanged); rehearsal `7f34d6b9534a16930bfef78d6a8c15a55744415c`; tests `a7834605cbf3919dbcf4da77110ae583ff816b9a`.

## Operator route

The original component-local commands remain supported. From the repository root, package execution also works:

```sh
python -m revenue.uiowa_rfq_18649_ai_coding.rehearse --out /tmp/uiowa076-new-packet
python -m revenue.uiowa_rfq_18649_ai_coding.ai_coding /tmp/uiowa076-new-packet/synthetic/changes.json --out /tmp/uiowa076-new-report
```

Use new or empty destinations as in the README. This file loader is intentionally specific to these dependency-free sibling modules. It is not a universal plugin importer, a security sandbox, or an assurance about third-party import-time side effects. A future dependency needing registered package identity, dataclass module resolution or pickling must be integrated deliberately and covered by its own tests rather than copied into this loader unexamined.
