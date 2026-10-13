# Synthetic AI Performance Evaluation Evidence — DAF26TZ06-NV006 proof

This is a **provider-neutral, synthetic/offline technical proof** supporting Commons issue #13984. It does not connect to AFSIM, TETK, JSE, live sensors, military systems, DSIP, or any external provider. It produces evaluation evidence only and makes no operational, deployment, mission, procurement, award, or payment decision.

## What it measures

The compiler consumes a strict versioned scenario/result set and an explicit policy. All score thresholds use integer basis points; no floating-point threshold decisions occur.

- **Nominal performance** — classification accuracy on successful nominal cases.
- **Reliability** — successful cases / all cases, so timeout/error cases remain visible.
- **Robustness** — accuracy on successful perturbation cases.
- **Drift** — nominal-vs-drift accuracy drop in basis points.
- **Latency** — maximum latency among successful evaluated cases.
- **Explainability evidence coverage** — successful cases carrying at least one bounded explanation-evidence identifier.

`PASS` means only that the supplied synthetic/research-owned evidence satisfies the supplied policy. It is not a finding that any system is safe, mission-ready, deployable, trustworthy, compliant, or acceptable to the Air Force.

## Adapter boundary

`provider.class` is limited to `SYNTHETIC` or `RESEARCH_OWNED`; a provider name/version/source digest identifies the fixture generation boundary. The proof does not claim compatibility with a named government simulator. A future adapter can translate research-owned simulation output into this schema without changing evaluation semantics.

## Run

```bash
cd revenue/daf_ai_eval
python -m py_compile eval_tool.py test_eval_tool.py
python -m unittest -v test_eval_tool.py
python -O -m unittest -v test_eval_tool.py
python eval_tool.py compile-current --suite synthetic_suite.json --policy policy.json --out report.json
python eval_tool.py verify-integrity --suite synthetic_suite.json --policy policy.json --report report.json
```

## Opportunity truth ceiling

`source_ledger.json` retains the official DSIP topic pointer but explicitly records that the controlling official text was not captured in this harness. Current dates/Q&A are secondary cross-checks only. Proposal readiness remains `HOLD_ELIGIBILITY_AND_CONTROLLING_INSTRUCTIONS` until the exact Release-6 instructions and applicant/RI-partner evidence are bound.

No code here contacts DoD/USAF, registers, asks TPOC questions, accepts terms, submits a proposal, uses credentials, spends money, represents a research partner, or claims an award/payment/revenue event.
