'use strict';

/**
 * Exact proper-divisor refinement for arithmetic candidate intervals.
 * See NONPRIMITIVE_REFINEMENT.md for the Erdős 1142 application and attribution.
 * No imports, provider calls, primality tests, or ambient runtime dependencies.
 */

const MAX_INTEGER = Number.MAX_SAFE_INTEGER;
const MAX_MODULUS = Math.floor(MAX_INTEGER / 2);

function integer(value, label, minimum, maximum = MAX_INTEGER) {
  if (!Number.isSafeInteger(value)) {
    throw new TypeError(label + ' must be a safe integer');
  }
  if (value < minimum || value > maximum) {
    throw new RangeError(label + ' must be in [' + minimum + ', ' + maximum + ']');
  }
  return value;
}

function record(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(label + ' must be an object');
  }
  return value;
}

function prepareFilters(filters) {
  if (!Array.isArray(filters) || filters.length === 0) {
    throw new TypeError('filters must be a nonempty array');
  }
  return filters.map((raw, index) => {
    record(raw, 'filters[' + index + ']');
    const modulus = integer(raw.modulus, 'filter modulus', 2, MAX_MODULUS);
    const maxExponent = integer(raw.max_exponent, 'filter max_exponent', 1, 52);
    const earliest = new Map();
    let power = 1;
    for (let exponent = 1; exponent <= maxExponent; exponent += 1) {
      power *= 2;
      const residue = power % modulus;
      if (!earliest.has(residue)) earliest.set(residue, {exponent, power});
    }
    return {modulus, max_exponent: maxExponent, earliest};
  });
}

function prepareIntervals(intervals) {
  if (!Array.isArray(intervals)) throw new TypeError('intervals must be an array');
  let previousUpper = 0;
  return intervals.map((raw, index) => {
    record(raw, 'intervals[' + index + ']');
    const lower = integer(raw.lower_exclusive, 'interval lower_exclusive', 0);
    const upper = integer(raw.upper_inclusive, 'interval upper_inclusive', lower);
    const divisor = integer(raw.required_divisor, 'interval required_divisor', 1);
    if (index > 0 && lower < previousUpper) {
      throw new RangeError('intervals must be ordered and nonoverlapping');
    }
    previousUpper = upper;
    return {lower_exclusive: lower, upper_inclusive: upper, required_divisor: divisor};
  });
}

function findWitness(n, filters) {
  for (let index = 0; index < filters.length; index += 1) {
    const filter = filters[index];
    const hit = filter.earliest.get(n % filter.modulus);
    if (!hit) continue;
    const difference = n - hit.power;
    // Equality is prime-compatible when the modulus itself is prime.
    // A positive proper divisor is the only reason to exclude a candidate.
    if (difference > filter.modulus) {
      return {
        filter_index: index,
        n,
        exponent: hit.exponent,
        power: hit.power,
        difference,
        divisor: filter.modulus,
        cofactor: difference / filter.modulus,
      };
    }
  }
  return null;
}

function createPowerDifferenceSieve(filters) {
  const compiled = prepareFilters(filters);

  function classify(n) {
    integer(n, 'n', 0);
    const witness = findWitness(n, compiled);
    return witness
      ? {status: 'EXCLUDED', witness}
      : {status: 'SURVIVES_FILTERS', witness: null};
  }

  function refineIntervals(intervals, options = {}) {
    record(options, 'options');
    if (options.include_survivors !== undefined &&
        typeof options.include_survivors !== 'boolean') {
      throw new TypeError('include_survivors must be a boolean');
    }
    const ranges = prepareIntervals(intervals);
    const kept = options.include_survivors === true ? [] : null;
    const totals = compiled.map(() => 0);
    const firstWitnesses = compiled.map(() => null);
    const rows = [];
    let candidatesSeen = 0;
    let excluded = 0;
    let survivorCount = 0;

    for (const range of ranges) {
      const row = {
        ...range,
        candidates_seen: 0,
        excluded: 0,
        survivor_count: 0,
        first_survivor: null,
        last_survivor: null,
        excluded_by_filter: compiled.map(() => 0),
      };
      const delta = range.required_divisor -
        (range.lower_exclusive % range.required_divisor);
      if (delta <= range.upper_inclusive - range.lower_exclusive) {
        let n = range.lower_exclusive + delta;
        for (;;) {
          row.candidates_seen += 1;
          candidatesSeen += 1;
          const witness = findWitness(n, compiled);
          if (witness) {
            row.excluded += 1;
            excluded += 1;
            const index = witness.filter_index;
            row.excluded_by_filter[index] += 1;
            totals[index] += 1;
            if (firstWitnesses[index] === null) firstWitnesses[index] = witness;
          } else {
            row.survivor_count += 1;
            survivorCount += 1;
            if (row.first_survivor === null) row.first_survivor = n;
            row.last_survivor = n;
            if (kept !== null) kept.push(n);
          }
          // Check the remaining distance before adding, to avoid overflow.
          if (range.required_divisor > range.upper_inclusive - n) break;
          n += range.required_divisor;
        }
      }
      rows.push(row);
    }

    const result = {
      schema: 'erdos1142.power_difference_sieve/v1',
      status: 'COMPLETE',
      evidence_scope: 'proper_divisor_refinement_only',
      candidates_seen: candidatesSeen,
      excluded,
      survivor_count: survivorCount,
      filters: compiled.map((filter, index) => ({
        modulus: filter.modulus,
        max_exponent: filter.max_exponent,
        covered_residue_count: filter.earliest.size,
        excluded: totals[index],
        first_witness: firstWitnesses[index],
      })),
      intervals: rows,
    };
    if (kept !== null) result.survivors = kept;
    return result;
  }

  return Object.freeze({classify, refineIntervals});
}

module.exports = {createPowerDifferenceSieve};
