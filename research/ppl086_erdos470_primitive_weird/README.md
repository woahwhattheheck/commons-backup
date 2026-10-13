# Erdős 470: finite primitive-weird certificates

A bounded public API constructs and retains ordinary primitive weird numbers of the form \(2^k p q\), using an explicitly attributed sufficient criterion. Its saved reader navigates the numeric catalog, complete prime-trial witnesses and ordinary proper divisors.

## Delivered result

The single new constructor input is \(k=12\), with \(S=8191\), every source prime \(8191<p<16382\), and
\[
q=8191+\left\lfloor\frac{8191^2}{p-8191}\right\rfloor.
\]

From **872 candidates**, **95** have prime \(q\) and explicit primitive-weird certificates; **777** have composite \(q\) and are marked only as failures of this template. Every one of the 7,779 prime-trial quotient/remainder pairs is retained, together with 285 maximal-proper-divisor deficiency witnesses and 380 dyadic blocks. Each successful number has 51 ordinary proper divisors.

The least and greatest certified numbers within this template are **1,099,642,138,624** and **56,825,344,790,528**. There are 89 catalog values in \([10^{12},10^{13}]\). These are finite template counts and extrema, not an enumeration of all weird numbers in those intervals.

One fresh saved-reader run answered 15 queries. It exported all 211 prime-trial rows for the greatest catalog value and all 51 of that value's proper divisors. It repeated zero parameter constructions, prime classifications, trial divisions, certificates, sieves or subset searches. Divisor navigation uses its own exact bounded BigInt arithmetic.

## Files

- [primitive_weird_index.cjs](primitive_weird_index.cjs): pure CommonJS constructor and saved reader.
- [PRIMITIVE_WEIRD_API.md](PRIMITIVE_WEIRD_API.md): complete proof, source conventions, API and limits.
- [k12_prime_template_catalog.json](k12_prime_template_catalog.json): all candidates, trial pairs, certificates and actual query responses.

The constructor exports `compilePrimitiveWeirdIndex`; saved consumers use `openRetainedPrimitiveWeirdIndex(delivery.snapshot)`. The supported cap is \(1\le k\le12\), with an identified complete prime list through at least \(2S\). No I/O or external package is required.

## Mathematical and source boundary

Semiperfectness uses subsets of **distinct ordinary positive proper divisors**. Unitary restrictions do not apply. Weirdness is strict abundance plus failure of semiperfectness; primitive weirdness excludes every proper weird divisor.

The criterion \(S<\sigma(2^kpq)-2^{k+1}pq<p\) is the \(m=2^k\), two-prime, \(j=0\) specialization of Amato–Hasler–Melfi–Parton, Theorem 3.1.1, Riv. Mat. Univ. Parma 7(1) (2016), 153–163. [Author text](https://arxiv.org/html/1803.00324v1). Historical definitions retain Benkoski–Erdős credit: [original 1974 paper](https://www.renyi.hu/~p_erdos/1974-24.pdf).

The 1,900-prime basis through 16,384 is the accepted Commons #31426 input, blob `7decf4b5cbf9945cf707d392e0c7d3d68e4a75bd` at merge `8bcf059ef0fda877c0975f7a89a2ae565e71a3b8`, `snapshot.basis.primes` in `research/ppl040_kimberling_interspersion_primes/row493_columns10001_22000.json`. It is preserved as a premise; its sieve and row calculations were not replayed.

The reader checks saved structure and bindings without independently proving arithmetic rows or source authenticity. The executed source blob is `37323b6c85f404799af7fc30a1e02816bf96ca58`; complete data blob `24c572744b09f774c544ff63de3b740ba8cff046`. The guide identifies the source-inspected, unexercised branches.

This finite even construction does not resolve odd weirdness or infinitude of primitive weird numbers, assert novelty, or establish an external computational frontier.
