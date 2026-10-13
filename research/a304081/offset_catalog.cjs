"use strict";

// Shared exact squarefree base offsets for OEIS A304081.
// The parity reformulation is stated in OEIS A304122; this API preserves pairs.
const MAX_N = 1000000000000n;
const CATALOG_SCHEMA = "commons.a304081.offset_catalog/v1";
const CANDIDATE_SCHEMA = "commons.a304081.prime_candidates/v1";

function integer(value, name) {
  let parsed;
  if (typeof value === "bigint") {
    parsed = value;
  } else if (typeof value === "number" && Number.isSafeInteger(value)) {
    parsed = BigInt(value);
  } else if (typeof value === "string" && /^(?:0|[1-9][0-9]*)$/.test(value)) {
    if (value.length > 13) throw new RangeError(name + " exceeds the catalog limit");
    parsed = BigInt(value);
  } else {
    throw new TypeError(name + " must be a nonnegative exact integer");
  }
  if (parsed < 0n || parsed > MAX_N) {
    throw new RangeError(name + " must be between 0 and 1000000000000");
  }
  return parsed;
}

function squareRoot(value) {
  if (value < 2n) return value;
  let low = 1n;
  let high = value;
  let result = 1n;
  while (low <= high) {
    const middle = (low + high) / 2n;
    if (middle * middle <= value) {
      result = middle;
      low = middle + 1n;
    } else {
      high = middle - 1n;
    }
  }
  return result;
}

function factorPrimes(limit) {
  const composite = new Uint8Array(limit + 1);
  const primes = [];
  for (let value = 2; value <= limit; value += 1) {
    if (composite[value] !== 0) continue;
    primes.push(BigInt(value));
    if (value * value <= limit) {
      for (let multiple = value * value; multiple <= limit; multiple += value) {
        composite[multiple] = 1;
      }
    }
  }
  return primes;
}

function squarefree(value, primes) {
  let remaining = value;
  for (const prime of primes) {
    if (prime * prime > remaining) break;
    if (remaining % prime !== 0n) continue;
    remaining /= prime;
    if (remaining % prime === 0n) return false;
  }
  return true;
}

/**
 * Prepare all squarefree bases 2^j + 5^m <= max_n - 3, j >= 1, m >= 0.
 * The inclusive max_n is bounded before allocating the factor sieve.
 * Numeric duplicates retain their separate exponent pairs.
 */
function createOffsetCatalog(max_n) {
  const maximum = integer(max_n, "max_n");
  const baseBound = maximum >= 3n ? maximum - 3n : 0n;
  const sieveLimit = Number(squareRoot(baseBound));
  const primes = factorPrimes(sieveLimit);
  const classification = new Map();
  const bases = [];
  const distinctSquarefree = new Set();
  let considered = 0;
  let rejected = 0;

  for (let power2 = 2n, j = 1; power2 + 1n <= baseBound; power2 *= 2n, j += 1) {
    for (let power5 = 1n, m = 0; power2 + power5 <= baseBound; power5 *= 5n, m += 1) {
      const value = power2 + power5;
      considered += 1;
      if (!classification.has(value)) {
        classification.set(value, squarefree(value, primes));
      }
      if (classification.get(value)) {
        bases.push({value, j, m});
        distinctSquarefree.add(value);
      } else {
        rejected += 1;
      }
    }
  }
  bases.sort((left, right) =>
    left.value < right.value ? -1 : left.value > right.value ? 1 :
      left.j - right.j || left.m - right.m
  );

  const statistics = Object.freeze({
    base_exponent_pairs_considered: considered,
    distinct_base_values_examined: classification.size,
    squarefree_base_exponent_pairs: bases.length,
    distinct_squarefree_base_values: distinctSquarefree.size,
    rejected_base_exponent_pairs: rejected,
    squarefree_classifications: classification.size,
    factor_sieve_limit: sieveLimit,
    factor_primes: primes.length
  });

  function listBaseOffsets() {
    return bases.map(row => ({j: row.j, m: row.m, base_offset: row.value.toString()}));
  }

  function candidatesFor(n) {
    const target = integer(n, "n");
    if (target > maximum) throw new RangeError("n exceeds this catalog's inclusive max_n");
    const coefficient = target % 2n === 0n ? 1n : 2n;
    const candidates = [];
    const distinctOffsets = new Set();
    for (const row of bases) {
      const offset = coefficient * row.value;
      if (offset + 3n > target) break;
      candidates.push({
        prime_candidate: (target - offset).toString(),
        offset: offset.toString(),
        base_offset: row.value.toString(),
        j: row.j,
        k: row.j + (coefficient === 2n ? 1 : 0),
        m: row.m
      });
      distinctOffsets.add(offset);
    }
    return {
      schema: CANDIDATE_SCHEMA,
      n: target.toString(),
      coefficient: Number(coefficient),
      prime_status: "not_evaluated",
      coverage: {
        complete_offsets_for_n: true,
        catalog_max_n: maximum.toString(),
        minimum_prime_candidate: "3"
      },
      exponent_pair_count: candidates.length,
      distinct_offset_count: distinctOffsets.size,
      candidates
    };
  }

  return Object.freeze({
    schema: CATALOG_SCHEMA,
    max_n: maximum.toString(),
    base_bound: baseBound.toString(),
    statistics,
    listBaseOffsets,
    candidatesFor
  });
}

module.exports = {createOffsetCatalog};
