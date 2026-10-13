"use strict";

// Exact point counts using the attributed shared A304081 offset catalog.
const MAX_N = 1000000000000n;
const STRONG_BASES = Object.freeze([2n, 3n, 5n, 7n, 11n]);
const STRONG_BOUND_EXCLUSIVE = 2152302898747n;

function exactInteger(value, name) {
  let result;
  if (typeof value === "bigint") result = value;
  else if (typeof value === "number" && Number.isSafeInteger(value)) result = BigInt(value);
  else if (typeof value === "string" && /^(?:0|[1-9][0-9]*)$/.test(value)) {
    if (value.length > 13) throw new RangeError(name + " exceeds 1000000000000");
    result = BigInt(value);
  } else throw new TypeError(name + " must be a nonnegative exact integer");
  if (result < 0n || result > MAX_N) {
    throw new RangeError(name + " must be between 0 and 1000000000000");
  }
  return result;
}

function squareRoot(value) {
  let low = 0n, high = value + 1n;
  while (high - low > 1n) {
    const middle = (low + high) / 2n;
    if (middle * middle <= value) low = middle;
    else high = middle;
  }
  return low;
}

function sievePrimes(limit) {
  const composite = new Uint8Array(limit + 1);
  const primes = [];
  for (let value = 2; value <= limit; value++) {
    if (composite[value]) continue;
    primes.push(BigInt(value));
    if (value * value <= limit) {
      for (let multiple = value * value; multiple <= limit; multiple += value) {
        composite[multiple] = 1;
      }
    }
  }
  return primes;
}


/**
 * Jaeschke's first-five-prime bound makes this finite-domain decision exact.
 * The caller has already removed small prime divisors and enforces MAX_N.
 * Keep all actual strong-base residues so the decision can be inspected.
 */
function strongPrimeEvidence(value) {
  if (value <= 11n || value > MAX_N || value >= STRONG_BOUND_EXCLUSIVE) {
    throw new RangeError("strong-base input is outside the admitted domain");
  }
  let oddPart = value - 1n, twos = 0;
  while (oddPart % 2n === 0n) {
    oddPart /= 2n;
    twos++;
  }
  const evidence = {
    method: "bounded_strong_prime_bases",
    exclusive_bound: STRONG_BOUND_EXCLUSIVE.toString(),
    odd_part: oddPart.toString(),
    two_power: twos,
    base_results: [],
    modular_multiplications: 0,
    all_bases_passed: true
  };
  function powerMod(base) {
    let result = 1n, power = base, exponent = oddPart;
    while (exponent > 0n) {
      if (exponent % 2n === 1n) {
        result = (result * power) % value;
        evidence.modular_multiplications++;
      }
      exponent /= 2n;
      if (exponent > 0n) {
        power = (power * power) % value;
        evidence.modular_multiplications++;
      }
    }
    return result;
  }
  for (const base of STRONG_BASES) {
    let residue = powerMod(base);
    const row = {
      base: base.toString(),
      initial_residue: residue.toString(),
      squared_residues: [],
      passed: residue === 1n || residue === value - 1n
    };
    if (!row.passed) {
      for (let step = 1; step < twos; step++) {
        residue = (residue * residue) % value;
        evidence.modular_multiplications++;
        row.squared_residues.push(residue.toString());
        if (residue === value - 1n) {
          row.passed = true;
          break;
        }
        if (residue === 1n) break;
      }
    }
    evidence.base_results.push(row);
    if (!row.passed) {
      evidence.all_bases_passed = false;
      break;
    }
  }
  return evidence;
}

/**
 * Prepare one bounded counter. In CommonJS, the local catalog is loaded
 * automatically; a connected runtime passes its complete catalog export.
 * Each count call returns all candidate pairs and distinct classifications.
 */
function createCounter(max_n, catalogFactory, accelerated) {
  const maximum = exactInteger(max_n, "max_n");
  if (catalogFactory === undefined) {
    if (typeof require !== "function") {
      throw new TypeError("pass createOffsetCatalog as the second argument in a connected runtime");
    }
    catalogFactory = require("./offset_catalog.cjs").createOffsetCatalog;
  }
  if (typeof catalogFactory !== "function") {
    throw new TypeError("catalogFactory must be the createOffsetCatalog export");
  }
  const catalog = catalogFactory(maximum);
  if (!catalog || catalog.schema !== "commons.a304081.offset_catalog/v1" ||
      catalog.max_n !== maximum.toString() || typeof catalog.candidatesFor !== "function") {
    throw new TypeError("catalogFactory returned an incompatible offset catalog");
  }
  const sieveLimit = Number(squareRoot(maximum));
  const primes = sievePrimes(sieveLimit);
  const preparation = Object.freeze({
    max_n: maximum.toString(),
    catalog_schema: catalog.schema,
    catalog_base_bound: catalog.base_bound,
    catalog_statistics: catalog.statistics,
    prime_sieve_limit: sieveLimit,
    prime_sieve_count: primes.length,
    method: accelerated ? "exact_small_divisors_then_bounded_strong_prime_bases" :
      "exact_trial_division",
    division_bound: "floor(sqrt(prime_candidate))",
    ...(accelerated ? {
      strong_prime_bases: Object.freeze(STRONG_BASES.map(String)),
      strong_prime_bound_exclusive: STRONG_BOUND_EXCLUSIVE.toString(),
      small_trial_prime_limit: 37,
      composite_witness: "least_prime_divisor_from_complete_ascending_trial_division"
    } : {})
  });

  function classify(value) {
    let divisions = 0;
    for (const prime of primes) {
      if (prime * prime > value) break;
      divisions++;
      if (value % prime === 0n) {
        return {prime_candidate: value.toString(), is_prime: false,
          least_divisor: prime.toString(), cofactor: (value / prime).toString(),
          trial_divisions: divisions};
      }
    }
    return {prime_candidate: value.toString(), is_prime: true,
      least_divisor: null, cofactor: null, trial_divisions: divisions};
  }


  function classifyFast(value) {
    let divisions = 0, nextPrime = 0;
    function result(isPrime, divisor, evidence) {
      return {
        prime_candidate: value.toString(), is_prime: isPrime,
        least_divisor: divisor === null ? null : divisor.toString(),
        cofactor: divisor === null ? null : (value / divisor).toString(),
        trial_divisions: divisions,
        modular_multiplications: evidence.modular_multiplications || 0,
        strong_base_evaluations: evidence.base_results ? evidence.base_results.length : 0,
        primality_evidence: evidence
      };
    }
    for (; nextPrime < primes.length && primes[nextPrime] <= 37n; nextPrime++) {
      const prime = primes[nextPrime];
      if (prime * prime > value) {
        return result(true, null, {method: "complete_trial_division"});
      }
      divisions++;
      if (value % prime === 0n) {
        return result(false, prime, {method: "least_prime_divisor"});
      }
    }
    if (nextPrime === primes.length) {
      return result(true, null, {method: "complete_trial_division"});
    }
    const evidence = strongPrimeEvidence(value);
    if (evidence.all_bases_passed) return result(true, null, evidence);

    // Resume after every already-attempted small prime; no factor work repeats.
    for (; nextPrime < primes.length; nextPrime++) {
      const prime = primes[nextPrime];
      if (prime * prime > value) break;
      divisions++;
      if (value % prime === 0n) return result(false, prime, evidence);
    }
    throw new Error("strong compositeness witness has no factor within the complete sieve");
  }

  function count(n) {
    const target = exactInteger(n, "n");
    if (target > maximum) throw new RangeError("n exceeds this counter's inclusive max_n");
    const view = catalog.candidatesFor(target);
    if (!view || view.schema !== "commons.a304081.prime_candidates/v1" ||
        view.n !== target.toString() || !Array.isArray(view.candidates) ||
        view.exponent_pair_count !== view.candidates.length) {
      throw new TypeError("offset catalog returned an incompatible candidate view");
    }
    const byValue = new Map();
    const classifications = [];
    const candidatePairs = [];
    const representations = [];
    let trialDivisions = 0;
    let modularMultiplications = 0, strongBaseEvaluations = 0;
    let distinctPrimes = 0;
    for (const row of view.candidates) {
      const value = exactInteger(row.prime_candidate, "prime_candidate");
      if (value < 3n || value > target || value % 2n !== 1n) {
        throw new RangeError("offset catalog returned an out-of-domain prime candidate");
      }
      let index = byValue.get(row.prime_candidate);
      if (index === undefined) {
        const result = accelerated ? classifyFast(value) : classify(value);
        index = classifications.length;
        byValue.set(row.prime_candidate, index);
        classifications.push(result);
        trialDivisions += result.trial_divisions;
        if (accelerated) {
          modularMultiplications += result.modular_multiplications;
          strongBaseEvaluations += result.strong_base_evaluations;
        }
        if (result.is_prime) distinctPrimes++;
      }
      candidatePairs.push({...row, classification_index: index});
      if (classifications[index].is_prime) {
        representations.push({p: row.prime_candidate, k: row.k, m: row.m,
          offset: row.offset, base_offset: row.base_offset, j: row.j});
      }
    }
    return {
      schema: accelerated ? "commons.a304081.fast_representation_count/v1" :
        "commons.a304081.representation_count/v1",
      n: target.toString(),
      coefficient: view.coefficient,
      prime_status: "evaluated_exactly",
      preparation,
      coverage: {
        complete_offsets_for_n: view.coverage.complete_offsets_for_n,
        all_distinct_candidates_classified: true,
        minimum_prime_candidate: "3",
        scope: "single_n"
      },
      candidate_pair_count: candidatePairs.length,
      distinct_candidate_count: classifications.length,
      representation_count: representations.length,
      distinct_prime_candidate_count: distinctPrimes,
      composite_pair_count: candidatePairs.length - representations.length,
      trial_divisions: trialDivisions,
      ...(accelerated ? {
        modular_multiplications: modularMultiplications,
        strong_base_evaluations: strongBaseEvaluations
      } : {}),
      representations,
      candidate_pairs: candidatePairs,
      classifications
    };
  }

  return Object.freeze({
    schema: accelerated ? "commons.a304081.fast_representation_counter/v1" :
      "commons.a304081.representation_counter/v1",
    max_n: maximum.toString(), preparation, count
  });
}

/** Preserve the original constructor and exact trial-division result contract. */
function createRepresentationCounter(max_n, catalogFactory) {
  return createCounter(max_n, catalogFactory, false);
}

/** Opt in to bounded deterministic strong-prime decisions and retained residues. */
function createFastRepresentationCounter(max_n, catalogFactory) {
  return createCounter(max_n, catalogFactory, true);
}

module.exports = {createRepresentationCounter, createFastRepresentationCounter};
