# Simultaneous small-divisor navigation

Exact CRT navigation for k in [0,n) such that neither n+k nor n+k² is divisible by a supplied modulus. A survivor is not a primality certificate.

The one input n=10^1000+477965 with moduli 2,3,5,7,11,13 has 4,800 survivor phases modulo 30,030. Its complete 5,339 stage rows and 30 saved-reader outputs are retained. The first surviving k is 2, the last n−13; no primality testing was performed.

- [API, proof and source scope](SIMULTANEOUS_DIVISOR_SIEVE_API.md)
- [CommonJS module](simultaneous_divisor_sieve.cjs)
- [Complete CRT certificate](huge_integer_crt_certificate.json)
- [Complete saved queries](saved_reader_queries.json)

Sun’s author-written [OEIS A185636](https://oeis.org/A185636) supplies the strict 0≤k<n convention. The implementation requires n larger than every supplied modulus, so exclusions provide proper-factor witnesses. General pairwise coprime moduli are allowed without a primality premise. The result is a finite filter and navigation capability, not a simultaneous-prime or conjecture claim.
