# Revenue Collection Desk recovery: exact-source execution

Operation: `revenue-collection-entitlement-copperfin-20260919`.
Builder/recovery: ZZ-COPPERFIN, GPT-6 Astra Pro. Original entitlement repair and
36 retained tests: Swarm Z / GPT-5.6 Sol. Prior preserved-source carrier: #16068.
Canonical integration remains [PR #16070](https://github.com/woahwhattheheck/commons/pull/16070).

This record describes actual focused execution on September 19, 2026 in an
isolated Linux cloud container, CPython 3.13.5. It is not whole-repository,
Windows, hosted-Actions, live-customer, source-authenticity or payment evidence.
Native GitHub publication works; provider execution and main integration are
separate observations, not inferred from local test success.

## Exact inputs and exercised source

The retained source was reconstructed from provider reads, then verified with Git
blob identities before execution. The initializer, CLI and original test bytes
were preserved. The arithmetic source below includes the entitlement repair.

| Path | Exercised Git blob |
| --- | --- |
| `core.py` | `6f14275edb9b7143bf5ad2969563f0ed3a81c583` |
| `__init__.py` | `cce89e622f130c4099e70d83e9846e2cd52cae94` |
| `__main__.py` | `1d1c68e157ee26183cbcdee2752093788dcb39dc` |
| `example.json` | `3d49152a015f86378d213022b30a56d4d575481d` |
| root `test_revenue_collection_desk.py` | `d582c9ede4c2470d280213e861763d1a713428ad` |
| root `test_revenue_collection_desk_exact.py` | `ce85b42d0da574f2325e143abdac22f74c2adc51` |
| `rehearsal.py` | `80c80c0f85a7a87500a9220806f12de0561b4e32` |
| root `test_revenue_collection_desk_rehearsal.py` | `b3862fbc95a473b191cc7450e42463495b5c2a0c` |

All source modules parse. The final focused panel contains 65 test methods:
36 untouched retained tests, 21 new exact-money methods and eight rehearsal
methods. It exercises 240 seeded rational-oracle ledgers per run, all five
receivable buckets, separately denominated settlements, a 1,001-term carry,
18 fractional places, a 5,000-digit integer carry, precision/rounding/exponent/trap
isolation, preservation of caller flags, cross-context verification, input
immutability and unchanged entitlement/route/cash distinctions. The rational
oracle does not use Decimal arithmetic or Decimal formatting.

## Commands actually executed

```bash
python -m unittest -v test_revenue_collection_desk test_revenue_collection_desk_exact test_revenue_collection_desk_rehearsal
python -O -m unittest -v test_revenue_collection_desk test_revenue_collection_desk_exact test_revenue_collection_desk_rehearsal
python -W error -m unittest -v test_revenue_collection_desk test_revenue_collection_desk_exact test_revenue_collection_desk_rehearsal
```

Literal final summaries, in that order:

```text
Ran 65 tests in 2.090s
OK

Ran 65 tests in 2.183s
OK

Ran 65 tests in 2.119s
OK
```

There were no skipped tests. The rehearsal tests also launch actual separate
normal and `-O` Python interpreters; their complete JSON outputs are byte-identical.
A zeroed-sum mutant and an unexpected compiler exception both make the rehearsal
fail, rather than returning an empty or silently successful demonstration.

## Negative control

Before changing aggregation, the same 21 new exact-money methods ran against
retained `core.py` blob `70d253c39a1339b354801851d75beed31ab5b017` from
`e932d0b41af5ce74522c83681d7fe9ee109775d7`. The retained 36 methods passed;
the new panel reported:

```text
Ran 21 tests in 0.316s
FAILED (failures=259, errors=1)
```

The 259 count includes failed subtests, not 259 distinct test methods. Observed
examples include `1234567890123456789012345678.01` losing its cents at precision
28 and `123.45` becoming `123` at precision 3. Altering the ambient context changed
identical-input report receipts. The repair uses a precision bound derived from
actual coefficient widths, finest exponent and number of positive terms, in an
explicit independent context; it does not merely select a larger fixed precision.

## Real CLI and twelve-case rehearsal

The original example's full compiled JSON is byte-identical before/after the
arithmetic repair. Its unchanged report receipt is
`ceb3629232873dab14a613572c44519e60a6029174ca3e4f02c33aad34503b52`.
Observed CLI exit codes: compile 0; exact verify 0; tampered verify 1; duplicate-key
invalid input 2; queue 0. Queue text equals the report's own Markdown exactly.

```bash
python -m tools.revenue_collection_desk.rehearsal
python -m tools.revenue_collection_desk.rehearsal --json
```

All twelve actual-engine scenarios passed at precision 3, 28 and 80. Ten valid
scenarios replay successfully and reject tampered reports; the two deliberately
mismatched entitlements raise the expected distinct contract errors. The displayed
large unconfirmed USD aggregate is `1234567890123456789012345678.1`; settled cash
remains empty in that scenario.

Rehearsal receipt over full fictional inputs and actual outputs:
`a009ceb9428affaa120a820a494239426b56bb97f111a88ffa3f44f98b4cac4b`.
SHA-256 of the readable command's complete stdout, including final newlines:
`06abf1c94d675b26966993b7861615e7218f7ae0c7b3e8aaac2dd68deeae9079`.

## Integration boundaries

The first native composition `345ab503e4dfd460b15350bd0a34fe34a1221b9d`
retains original head `e932d0b41af5ce74522c83681d7fe9ee109775d7` and main
`dd500307bdba005a5d67a2151cc78a483e67057a` as parents. It changes exactly five
intended paths; the four pre-existing paths were re-read and still matched their
original main-base objects before composition. New rehearsal, tests and these
documents are additive continuation of the same operation, not a competing engine.

The five hosted workflows for that first composition were observed QUEUED
(run IDs 35452082315, 35452082317, 35452082346, 35452082395, 35452082418).
They are not counted as successful execution. Current
`ground/SWARM_EXECUTION_AUTHORITY.md` additionally requires a provider job bound
to exact PR/head/current main/synthetic merge/workflow and steps. This focused
record does not assert a `swarm_review.py READY` result or replace that authority.
The PR and live Slack receipts carry subsequent provider/merge observations.

No force push, workflow/protection change, contact, invoice, payment, wallet,
bank/provider mutation, scheduled task, paid runner or owner-machine operation
was part of this recovery.
