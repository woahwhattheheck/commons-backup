# UIOWA-084 — Recommendation prioritization calculator

This directory contains a dependency-free, offline planning tool for RFQ 18649 preparation.

**It does not contain University of Iowa findings.** The included recommendation set is synthetic and exists only to demonstrate the prioritization method.

## What it does

The calculator compares explicit 0–5 estimates for:

- expected quality effect;
- expected security effect;
- expected delivery effect; and
- implementation complexity.

For each configured profile:

```text
benefit = quality*w_q + security*w_s + delivery*w_d
priority = benefit - complexity*w_complexity
```

Quality, security, and delivery weights must sum to `1.0`. The complexity penalty is shown separately rather than hidden inside the benefit weights.

Required estimates are never silently converted to zero. If any of `quality`, `security`, `delivery`, or `complexity` is blank, the recommendation is emitted as `HOLD_MISSING_ESTIMATE` with no rank.

## Run

From this directory:

```bash
python prioritize.py recommendations.synthetic.csv weights.json --out-dir out
```

Outputs:

- `out/ranking_<profile>.csv` — one transparent ranking per weight profile;
- `out/sensitivity.csv` — best/worst rank and rank span across profiles;
- `out/report.md` — formula, profiles, rankings, sensitivity summary, and interpretation guardrails.

The default profiles intentionally emphasize different assumptions (`balanced`, `security_first`, `delivery_first`, `quality_first`, `complexity_sensitive`) so reviewers can see whether a recommendation is robust or weight-sensitive.

## Ties

`tie_epsilon` in `weights.json` is explicit. Recommendations whose scores fall within the epsilon of the group anchor share the same competition rank and carry a tie group/reason in CSV output. This avoids manufacturing precision when modeled scores are practically indistinguishable.

## Confidence

`confidence` is reported as an input but is **not** multiplied into the priority score. That keeps the formula auditable and prevents an implicit penalty from masquerading as impact. A future engagement can adopt a different confidence treatment only by changing the model explicitly.

## Validation

Run:

```bash
python -m unittest -v test_prioritize.py
```

The regression suite proves:

1. a missing estimate becomes a visible HOLD, not zero;
2. near-equal scores produce an explained shared rank;
3. changing weight assumptions changes the leading recommendation on the synthetic fixture;
4. invalid benefit weights are rejected; and
5. all profile, sensitivity, and Markdown outputs are generated end-to-end.

## Input schema

`recommendations.synthetic.csv` uses:

- `id`, `title`
- `quality`, `security`, `delivery`, `complexity`: 0–5 or blank
- `confidence`: optional 0–1 metadata
- `owner_role`, `dependencies`, `assumptions`: explanatory planning context

Replace the synthetic rows only with evidence-backed recommendations during a real engagement. The ranking supports discussion; it does not replace accountable human judgment or turn incomplete evidence into a numerical verdict.
