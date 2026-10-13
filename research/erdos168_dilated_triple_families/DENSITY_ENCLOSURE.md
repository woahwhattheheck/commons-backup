# A finite-prefix enclosure for the Erdős 168 limiting density

## Exact result

Let \(F(N)\) be the largest cardinality of a subset of \(\{1,\ldots,N\}\) containing no simultaneous triple \(\{n,2n,3n\}\), for any positive integer \(n\). Write
\[
\lambda=\lim_{N\to\infty}\frac{F(N)}{N}.
\]

The saved \(N=96\) family and eleven new conditions on that family give
\[
\boxed{\frac{451}{576}\leq\lambda\leq\frac{197}{243}}.
\]
The exact width is \(431/15552\). Decimal endpoints rounded outwards to eighteen places are
\[
0.782986111111111111\leq\lambda\leq0.810699588477366256.
\]
The rational endpoints are the certificate; the displayed decimals are an inclusive, outward-rounded presentation.

This contribution connects an existing finite family to a rigorous limit enclosure. The exact limiting value and its irrationality are not determined by this result. No best-known-bound or new limit-existence claim is made.

## Inputs and attribution

The definition comes from the fully acquired [Formal168 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/168.lean), observed Git blob **6b08aee5f3ee7342717f6a0230be36ac26db5d9d**. Its acquisition used the default-branch contents endpoint with no explicit ref; that display URL is mutable and no commit pin was returned. The source defines **NonTernary**, the filtered powerset of **Finset.Icc 1 N**, and its maximum cardinality **F**. It excludes these dilated triples, not all three-term arithmetic progressions.

That formal source attributes the already-solved existence of the limit to Graham, Spencer and Witsenhausen. The original 1977 scan yielded zero readable text, and its screenshot response supplied only a marker. The scan supplies no definition, proof or numerical claim in this delivery. The argument below is the bridge needed to interpret the present finite data.

The finite family was delivered in [Commons #31736](https://github.com/woahwhattheheck/commons/pull/31736), immutable merge **481dabd36b226b472dc107f5fd0d8f8872fe1075**:

| Input | Observed Git blob |
| --- | --- |
| [Original constructor and saved reader](https://github.com/woahwhattheheck/commons/blob/481dabd36b226b472dc107f5fd0d8f8872fe1075/research/erdos168_dilated_triple_families/dilated_triple_families.cjs) | 8854665a14bf7bf33943b4c124d14b9f73ebcbff |
| [Complete interval-96 family index](https://github.com/woahwhattheheck/commons/blob/481dabd36b226b472dc107f5fd0d8f8872fe1075/research/erdos168_dilated_triple_families/interval96_family_index.json) | 96adc069d6af628c0eb8c24c1815cf3a1ca08a6f |

Both complete inputs were acquired and matched native and independently computed Git blob identities before the new work. The original 268-node diagram, constraints, coefficient vectors and previous reader outputs were not reconstructed or rerun.

## 1. Independent blocks

Let
\[
1=s_1<s_2<\cdots
\]
enumerate the positive integers of the form \(2^a3^b\), with \(a,b\geq0\). Every positive integer has a unique expression \(m2^a3^b\), where \(\gcd(m,6)=1\). Thus \(\{1,\ldots,N\}\) splits into disjoint blocks
\[
B_m(N)=\{m s_j:m s_j\leq N\},\qquad \gcd(m,6)=1.
\]

The three integers \(n,2n,3n\) always have the same factor \(m\) coprime to six. Consequently no forbidden triple crosses between these blocks. A valid subset can be chosen independently in each block, and its maximum size is the sum of the block maxima. This does not require each block to be connected as a hypergraph.

Define \(g_j\) to be the maximum cardinality of a valid subset of \(\{s_1,\ldots,s_j\}\), and set \(g_0=0\). Adding one vertex gives
\[
0\leq g_j-g_{j-1}\leq1.
\]
The lower inequality follows by retaining a previous valid subset. For the upper inequality, remove the newly added vertex from any new valid subset.

Put \(\delta_j=g_j-g_{j-1}\in\{0,1\}\), and let \(g(t)=g_j\) when exactly \(j\) smooth values are at most \(t\), with \(g(t)=0\) for \(t<1\). Scaling each block by \(m\) preserves its forbidden triples, so
\[
F(N)=\sum_{\substack{1\leq m\leq N\\\gcd(m,6)=1}}g(N/m).
\]
Since \(g(t)=\sum_{s_j\leq t}\delta_j\), exchanging these finite sums gives the exact identity
\[
F(N)=\sum_{j\geq1}\delta_j C(N/s_j),
\]
where only finitely many terms are nonzero and
\[
C(x)=\#\{1\leq m\leq x:\gcd(m,6)=1\}
=\lfloor x\rfloor-\lfloor x/2\rfloor-\lfloor x/3\rfloor+\lfloor x/6\rfloor.
\]

## 2. The series bridge to the limit

For each fixed \(j\),
\[
\frac{C(N/s_j)}{N}\longrightarrow\frac{1}{3s_j}.
\]
Also \(0\leq C(N/s_j)/N\leq1/s_j\). The majorizing series is summable:
\[
\sum_{j\geq1}\frac1{s_j}
=\sum_{a,b\geq0}2^{-a}3^{-b}
=\frac1{1-1/2}\frac1{1-1/3}=3.
\]

For completeness, this supplies a direct justification for passage from the finite identity to the series: after retaining any first \(K\) terms, the remaining contribution to \(F(N)/N\) is at most \(\sum_{j>K}1/s_j\), uniformly in \(N\). This tail tends to zero as \(K\) increases, while the first \(K\) terms have the displayed individual limits. Hence the series represents the already-known limit:
\[
\lambda=\frac13\sum_{j\geq1}\frac{\delta_j}{s_j}.
\]

The numbers \(\delta_j\) are rank increments. The indices with \(\delta_j=1\) need not themselves form one valid subset. No forbidden-triple constraint is imposed directly on that indicator sequence.

## 3. A computable tail allowance

For any complete first \(J\) smooth values, define
\[
L_J=\frac13\sum_{j=1}^{J}\frac{\delta_j}{s_j},
\qquad
R_J=\frac13\left(3-\sum_{j=1}^{J}\frac1{s_j}\right).
\]
Every unknown increment lies between zero and one. Therefore
\[
L_J\leq\lambda\leq L_J+R_J.
\]
This is a finite-data certificate with an exact geometric-series tail. It requires no estimate of unknown prefix maxima.

For the present input, \(J=20\) and the smooth values are exactly those at most 96. Their recorded prefix maxima are:

| \(j\) | \(s_j\) | \(g_j\) | \(\delta_j\) | Evidence used |
| --- | --- | --- | --- | --- |
| 1 | 1 | 1 | 1 | Saved degrees |
| 2 | 2 | 2 | 1 | Saved degrees |
| 3 | 3 | 2 | 0 | Saved degrees |
| 4 | 4 | 3 | 1 | Saved degrees |
| 5 | 6 | 4 | 1 | Saved degrees |
| 6 | 8 | 5 | 1 | Saved degrees |
| 7 | 9 | 5 | 0 | New condition |
| 8 | 12 | 6 | 1 | Saved degrees |
| 9 | 16 | 7 | 1 | New condition |
| 10 | 18 | 7 | 0 | Saved degrees |
| 11 | 24 | 8 | 1 | New condition |
| 12 | 27 | 8 | 0 | New condition |
| 13 | 32 | 9 | 1 | New condition |
| 14 | 36 | 10 | 1 | New condition |
| 15 | 48 | 11 | 1 | New condition |
| 16 | 54 | 11 | 0 | New condition |
| 17 | 64 | 12 | 1 | New condition |
| 18 | 72 | 13 | 1 | New condition |
| 19 | 81 | 13 | 0 | New condition |
| 20 | 96 | 14 | 1 | Saved degrees |

The output records
\[
\sum_{j\leq20}\frac1{s_j}=\frac{15121}{5184},
\qquad
\sum_{j\leq20}\frac{\delta_j}{s_j}=\frac{451}{192}.
\]
Thus
\[
L_{20}=\frac{451}{576},\qquad
R_{20}=\frac{431}{15552},\qquad
L_{20}+R_{20}=\frac{197}{243}.
\]

The full interval maximum \(F(96)=77\), already present in the saved family, is different from \(g_{20}=14\): the latter concerns only the block with \(m=1\). The enclosure uses smooth-prefix maxima, not the ratio \(F(96)/96\) by itself.

## 4. Recovering the finite maxima without rebuilding the family

The saved diagram's component root contains both that component and every later component; its **tail_root** contains just those later components. Because the choices in different blocks are independent, the root cardinality polynomial is the product of its local polynomial and the tail polynomial. All these polynomials have nonnegative coefficients and include the empty subset. Therefore the local maximum is exactly
\[
\deg P_{\mathrm{root}}-\deg P_{\mathrm{tail\_root}}.
\]
The consumer reads the degrees as the lengths of the already-trimmed coefficient vectors minus one. It performs no new base polynomial multiplication.

Existing components supply the prefix sizes
\[
1,2,3,4,5,6,8,10,20.
\]
Only one representative is used for each size, even when several components have the same shape.

The eleven remaining sizes are
\[
7,9,11,12,13,14,15,16,17,18,19.
\]
For each such size \(j\), the consumer invokes the saved reader once with no required labels and with every label outside \(\{s_1,\ldots,s_j\}\) forbidden. This forces all other blocks to be empty and leaves exactly the desired prefix family. The maximum degree of that conditional polynomial is \(g_j\). Every complete query, returned coefficient vector, maximum, count and cumulative work record is retained in the result file.

## 5. Deliverables and actual production

- [Consumer](density_enclosure.cjs), Git blob **fc8381fe223186cf345684bb5e41e429a5973aa5**.
- [Declared input and provenance](density_enclosure_input.json), Git blob **10a83a7d7fa83e53d64bdfcffaa7147c6822523f**.
- [Complete exact enclosure and all eleven query outputs](density_enclosure_result.json), Git blob **0d94110a7b3e9295014e8e647cd77cfceb941715**.

The consumer and input were frozen, independently hashed and banked as Git blobs before production. The eleven new conditions ran once in a single saved reader. Each output was retained immediately, and the final complete result was independently hashed and banked before documentation and publication.

| Actual work | Count |
| --- | ---: |
| Saved prefix degree differences reused | 9 |
| New prefix conditions and family queries | 11 |
| Conditional diagram nodes evaluated | 2,158 |
| Conditional coefficient cells produced | 7,062 |
| Prefix terms in exact rational sums | 20 |
| Decimal scale powers | 1 |
| New constructor states | 0 |
| New factor divisions | 0 |
| New constraints | 0 |
| New base coefficients | 0 |
| Rank/select steps or constraint checks | 0 |

The run remained inside the original reader's 16-condition and 500,000-conditional-coefficient-cell caps. No cap/error path, synthetic input, inverse-query exercise or earlier computation was run to validate this delivery.

**encloseFromSavedPrefix(openIndex, snapshot, input, record)** is the exported pure consumer. Its optional **record(name, value)** callback receives every new prefix output before the next query and then the full enclosure. The file also provides a CommonJS entry point that loads the adjacent saved reader, index and input manifest and prints the JSON result. Coefficient counts and exact rational arithmetic use BigInt; bounded indices and degrees use safe integers. Decimal bounds use BigInt floor and ceiling division. The consumer performs input-format checks and reads declared provenance but does not authenticate a caller-supplied manifest.

This is a finite arithmetic certificate with the explicit series bridge above. It supplies no irrationality proof, exact global value, literature priority determination, upstream formal proof acceptance or prize claim.
