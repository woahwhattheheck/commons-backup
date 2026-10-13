# Exact Egyptian-fraction decomposition navigator

The new complete search for 7/19 finds 0, 0, 5 and 202 representations using exactly one, two, three and four distinct unit fractions respectively. No denominator cap is imposed. The exact minimum for this rational is three.

The retained 125-node DAG contains every necessary prefix branch and final-two divisor candidate, with complete negative records. All 207 representations are exported in the saved 36-query reader, including six inverse rank matches and exact prefix-completion counts. Reader navigation repeats no residual, gcd, factor or divisor calculation.

Read [the API guide](EGYPTIAN_DECOMPOSITION_API.md) for the finite completeness argument, source conventions, input/work caps, all five minimal representations and exact query accounting. [The manifest](snapshot_manifest.json) and five node shards reconstruct the complete original snapshot exactly.

Tenenbaum–Yokota distinguish term-count minimization from largest-denominator minimization; Formal304 supplies the exact distinct-denominator contract and current asymptotic question. This package computes one rational's finite term families, not the worst-case N(b), an asymptotic upper bound or a prize result.
