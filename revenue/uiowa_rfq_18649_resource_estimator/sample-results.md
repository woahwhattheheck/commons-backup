# Reproduced fictional resource-planning cases

All values below were produced by the CLI. These are synthetic assumptions, not University facts or measured performance. Ranges are low / central / high person-hours.

| Case | Horizon months | One-time total | Known one-time subtotal | Maintenance per month | Full horizon total |
|---|---:|---|---|---|---|
| release | 3 | 52 / 84.0 / 128 | 52 / 84.0 / 128 | 6.00 / 10.0 / 16 | 70.00 / 114.0 / 176 |
| security | 2 | 52 / 84.0 / 122 | 52 / 84.0 / 122 | 2.0 / 4 / 6.0 | 56.0 / 92.0 / 134.0 |
| reliability | 6 | UNKNOWN | 34 / 56 / 90 | 3 / 4 / 6 | UNKNOWN |
| worksheet | 3 | UNKNOWN | 0 / 0 / 0 | UNKNOWN | UNKNOWN |

## Release handoff

Seven activities serve two recommendations. Shared learner attendance is 12 / 18.0 / 24 hours and shared facilitation is 4 / 6 / 8 hours. These are counted once even though both recommendations reference them. The operations role is scenario-dependent, not an unconditional capacity pass. The central horizon total is 84 + 3 × 10 = 114 hours.

## Secure-development practice

The specialist needs 20 / 28 / 42 one-time hours against 8 / 12 / 16 hours available over two months. The lowest demand exceeds the highest capacity. Spare developer hours cannot substitute for the required specialist skill. A resourcing conversation must change scope, sequencing, capacity or the horizon; the tool makes none of those decisions for the operator.

## Operational reliability

Instrumentation unit effort is unassessed, so its estimate and the complete one-time/horizon totals remain UNKNOWN. The known one-time subtotal is 34 / 56 / 90 hours. Recurring effort is known (3 / 4 / 6 hours/month), but the operations maintenance allocation is not: UNKNOWN_CAPACITY. Neither unknown becomes zero.

## Blank worksheet

The editable template starts with unknown implementation and maintenance quantities, effort and capacity. Both total categories and the horizon total stay UNKNOWN. Zero known subtotal is not a zero-cost estimate.

## Execution receipt

Environment: CPython 3.13.5, Linux x86_64; ephemeral cloud execution, not GitHub Actions.

`python -m unittest discover -s revenue/uiowa_rfq_18649_resource_estimator -p "test_*.py" -v`: 27 tests, OK.
`python -O -m unittest discover -s revenue/uiowa_rfq_18649_resource_estimator -p "test_*.py" -v`: 27 tests, OK.
`python -m py_compile` on estimator, fixtures and tests: exit 0.
Four actual CLI runs (three examples plus blank worksheet): exit 0; JSON/CSV/Markdown/input files generated. The unittest also launches real CLI subprocesses and checks output consistency, no-overwrite behavior, and invalid-input handling.

Reproduction commands and full semantics are in README.md. No current University input, staffing commitment, calendar event, paid service, purchase or maturity outcome is asserted.
