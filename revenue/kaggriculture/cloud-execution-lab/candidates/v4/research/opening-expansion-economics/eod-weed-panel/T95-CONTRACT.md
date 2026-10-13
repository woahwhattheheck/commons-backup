# Paired t95 reporting contract

`expansion_penalty.py` publishes a numeric paired Student-t 95% interval only for the canonical 100-seed panel used by this package.

The retained constant `T_CRIT_DF99_95 = 1.9842169515` is the two-sided 95% critical value for 99 degrees of freedom. Therefore:

- `n == 100`: `t95_low` and `t95_high` are numeric and preserve the already-published canonical HOMESTEAD result byte-for-value.
- `n != 100`: `t95_low` and `t95_high` are `null`. The CLI still reports descriptive statistics, standard error, paired signs, and analytic expectations, but it does not pretend the df=99 critical value applies to another sample size.

This is an evidence-tool contract only. It does not change the official weed mechanism, the canonical 100-seed receipt, BUY_LAND policy, land economics, runtime/defaults, or any promotion decision. A future general-purpose interval implementation may support other sample sizes if it computes the correct critical value and has focused acceptance coverage.
