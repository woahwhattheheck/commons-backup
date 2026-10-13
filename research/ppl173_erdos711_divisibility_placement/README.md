# Erdős 711: exact divisibility-placement certificates

This directory provides a bounded connected-V8/CommonJS solver for the least width $W(n,m)$ admitting distinct labeled multiples of $1,\ldots,n$ inside $(m,m+W]$. Every completed result retains an assignment at the minimum and a Hall obstruction one position earlier.

The complete new $n=11$ period has 27,720 rows and establishes

$$
\max_{m\ge1} W(11,m)=20.
$$

Its 254 maximizing classes are precisely $m\equiv100\pmod{110}$, together with $m\equiv12145$ or $15555\pmod{27720}$. The exact period mean is $195271/13860$; the diagonal width is $W(11,11)=14$, whose endpoint is 25.

## Files

| File | Contents |
|---|---|
| [divisibility_placement.cjs](divisibility_placement.cjs) | Incremental matching and Hall certificates, complete-period compiler, explicit shard assembler, retained lookup and paging. |
| [DIVISIBILITY_PLACEMENT_API.md](DIVISIBILITY_PLACEMENT_API.md) | Source conventions, self-contained algorithm reasoning, exact fixed-$n$ result, API contracts, limits and data format. |
| [period_n11_manifest.json](period_n11_manifest.json) | Complete period header and summary, source references, ordered shard descriptors, all maximizing residues and actual large-$m$ consumers. |
| [period_n11_rows_00000_13859.json](period_n11_rows_00000_13859.json) | Explicit certificates for residues 0–13,859. |
| [period_n11_rows_13860_27719.json](period_n11_rows_13860_27719.json) | Explicit certificates for residues 13,860–27,719. |

The row shards are complete data, not sampled witnesses. The public assembler refuses missing or inconsistent shard premises. The retained index reuses those rows without rerunning matching; its structural checks do not independently authenticate or validate their mathematics.

## Attribution and boundary

The right-inclusive width and lcm-periodic framework follow [Erdős and Pomerance (1980)](https://math.dartmouth.edu/~carlp/PDF/matching.pdf). Their one-variable function is an endpoint, while an equivalent integer open-right width needs an extra one. [Van Doorn (2026)](https://math.colgate.edu/~integers/aa7/aa7.pdf) already settles the divergence part of problem 711.

The present result covers every positive $m$ at fixed $n=11$. It makes no asymptotic, priority, external-frontier or sponsor claim. One complete period computation and one retained-data consumer produced the saved results; earlier accepted inputs and the published $n=10$ example remain unrerun.

