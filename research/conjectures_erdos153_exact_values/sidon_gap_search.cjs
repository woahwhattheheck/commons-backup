"use strict";

// Exact finite premises for the accepted Contribution.Erdos153Gaps.f_eq_of_search
// interface, contribution d283fe047b326ca9bb9de8919c667b521df46d9500cc839b50916321fee0192b.
// Search prunes only non-Sidon prefixes. No asymptotic or Lean-execution claim.

const INTEGER = /^(?:0|-?[1-9][0-9]*)(?![\s\S])/;
const LIMITS = Object.freeze({
  max_objective_cardinality: 256,
  max_search_cardinality: 12,
  max_cutoff: 512,
  max_extensions_per_advance: 1000000,
  default_saved_minimizers: 4096,
  max_saved_minimizers: 65536
});

function integer(value, label) {
  if (typeof value === "bigint") return value;
  if (typeof value === "number" && Number.isSafeInteger(value)) return BigInt(value);
  if (typeof value === "string" && INTEGER.test(value)) return BigInt(value);
  throw new TypeError(label + " must be a bigint, safe integer number, or canonical decimal integer string");
}

function fraction(numerator, denominator) {
  let a = numerator;
  let b = denominator;
  while (b !== 0n) [a, b] = [b, a % b];
  return {
    numerator: (numerator / a).toString(),
    denominator: (denominator / a).toString()
  };
}

function boundedInteger(value, label, lower, upper) {
  if (!Number.isSafeInteger(value) || value < lower || value > upper) {
    throw new RangeError(label + " must be an integer from " + lower + " through " + upper);
  }
  return value;
}

/**
 * Evaluate one distinct finite set of natural numbers using the original
 * diagonal-inclusive sumset and the divisor |A+A|, with exact BigInt arithmetic.
 */
function evaluateSidonGapSet(input) {
  if (!Array.isArray(input)) throw new TypeError("values must be an array");
  if (input.length < 2 || input.length > LIMITS.max_objective_cardinality) {
    throw new RangeError("objective input cardinality must be from 2 through " + LIMITS.max_objective_cardinality);
  }
  const values = Array.from(input, (value, index) => {
    const parsed = integer(value, "values[" + index + "]");
    if (parsed < 0n) throw new RangeError("objective values must be nonnegative");
    return parsed;
  }).sort((left, right) => left < right ? -1 : left > right ? 1 : 0);
  for (let index = 1; index < values.length; index += 1) {
    if (values[index] === values[index - 1]) throw new RangeError("objective values must be distinct");
  }

  const pairs = new Map();
  for (let first = 0; first < values.length; first += 1) {
    for (let second = first; second < values.length; second += 1) {
      const sum = values[first] + values[second];
      const previous = pairs.get(sum);
      if (previous !== undefined) {
        return {
          schema: "erdos153.sidon_gap_objective/v1",
          status: "NOT_SIDON",
          values: values.map(value => value.toString()),
          collision: {
            sum: sum.toString(),
            first_pair_indices: previous,
            second_pair_indices: [first, second]
          }
        };
      }
      pairs.set(sum, [first, second]);
    }
  }
  const sumset = Array.from(pairs.keys())
    .sort((left, right) => left < right ? -1 : left > right ? 1 : 0);
  const gaps = [];
  let gapSquareSum = 0n;
  for (let index = 1; index < sumset.length; index += 1) {
    const gap = sumset[index] - sumset[index - 1];
    gaps.push(gap.toString());
    gapSquareSum += gap * gap;
  }
  return {
    schema: "erdos153.sidon_gap_objective/v1",
    status: "SIDON",
    values: values.map(value => value.toString()),
    cardinality: values.length,
    sumset: sumset.map(value => value.toString()),
    sumset_cardinality: sumset.length,
    gaps,
    gap_square_sum: gapSquareSum.toString(),
    energy: fraction(gapSquareSum, BigInt(sumset.length))
  };
}

function binomialTable(maximum, cardinality) {
  const rows = [];
  for (let top = 0; top <= maximum; top += 1) {
    const row = Array(cardinality + 1).fill(0n);
    row[0] = 1n;
    for (let bottom = 1; bottom <= cardinality && bottom <= top; bottom += 1) {
      row[bottom] = rows[top - 1][bottom - 1] + rows[top - 1][bottom];
    }
    rows.push(row);
  }
  return rows;
}

function numericGapSquareSum(values) {
  const sums = [];
  for (let first = 0; first < values.length; first += 1) {
    for (let second = first; second < values.length; second += 1) {
      sums.push(values[first] + values[second]);
    }
  }
  sums.sort((left, right) => left - right);
  let total = 0;
  for (let index = 1; index < sums.length; index += 1) {
    const gap = sums[index] - sums[index - 1];
    total += gap * gap;
  }
  return total;
}

/**
 * Stateful bounded traversal of all n-subsets of {0,...,cutoff}.
 * advance(budget) performs at most budget prefix-extension attempts and returns
 * a fresh JSON-safe progress/result object. Reuse the same returned search object
 * to continue; this API has no external-state restore or I/O.
 */
function createSidonGapSearch(options) {
  if (options === null || typeof options !== "object" || Array.isArray(options)) {
    throw new TypeError("options must be an object");
  }
  const allowed = new Set(["n", "cutoff", "max_saved_minimizers"]);
  for (const key of Object.keys(options)) {
    if (!allowed.has(key)) throw new TypeError("unknown search option: " + key);
  }
  const n = boundedInteger(options.n, "n", 2, LIMITS.max_search_cardinality);
  const cutoff = boundedInteger(options.cutoff, "cutoff", 0, LIMITS.max_cutoff);
  const saveLimit = options.max_saved_minimizers === undefined
    ? LIMITS.default_saved_minimizers
    : boundedInteger(options.max_saved_minimizers, "max_saved_minimizers", 1, LIMITS.max_saved_minimizers);
  const choose = binomialTable(cutoff + 1, n);
  const totalSubsets = choose[cutoff + 1][n];
  const sumsetCardinality = n * (n + 1) / 2;
  const prefix = [];
  const next = [0];
  const differences = new Uint8Array(cutoff + 1);
  const histogram = new Map();
  const attemptsByDepth = Array(n).fill(0n);
  const rejectedByDepth = Array(n).fill(0n);
  let attempts = 0n;
  let rejectedPrefixes = 0n;
  let prunedSubsets = 0n;
  let sidonSubsets = 0n;
  let minimum = null;
  let minimizerCount = 0n;
  let minimizers = [];
  let complete = false;

  function describe() {
    return {
      schema: "erdos153.sidon_gap_search/v1",
      status: complete ? "COMPLETE" : "IN_PROGRESS",
      n,
      cutoff,
      sumset_cardinality: sumsetCardinality,
      total_subsets: totalSubsets.toString(),
      extension_attempts: attempts.toString(),
      attempts_by_depth: attemptsByDepth.map(value => value.toString()),
      rejected_prefixes: rejectedPrefixes.toString(),
      rejected_prefixes_by_depth: rejectedByDepth.map(value => value.toString()),
      pruned_non_sidon_subsets: prunedSubsets.toString(),
      sidon_subsets: sidonSubsets.toString(),
      accounted_subsets: (prunedSubsets + sidonSubsets).toString(),
      minimum_gap_square_sum: minimum === null ? null : minimum.toString(),
      minimum_energy: minimum === null ? null : fraction(BigInt(minimum), BigInt(sumsetCardinality)),
      minimizer_count: minimizerCount.toString(),
      minimizers: minimizers.map(values => values.slice()),
      max_saved_minimizers: saveLimit,
      minimizers_truncated: BigInt(minimizers.length) !== minimizerCount,
      energy_histogram: Array.from(histogram.entries())
        .sort(([left], [right]) => left - right)
        .map(([gapSum, count]) => ({gap_square_sum: gapSum.toString(), count: count.toString()}))
    };
  }

  function advance(budget) {
    boundedInteger(budget, "extension budget", 1, LIMITS.max_extensions_per_advance);
    let spent = 0;
    while (!complete && spent < budget) {
      const depth = prefix.length;
      const remaining = n - depth;
      const largest = cutoff - remaining + 1;
      const candidate = next[depth];
      if (candidate > largest) {
        if (depth === 0) {
          complete = true;
          if (prunedSubsets + sidonSubsets !== totalSubsets) {
            throw new Error("finite-domain accounting invariant failed");
          }
          break;
        }
        const last = prefix.pop();
        next.pop();
        for (const value of prefix) differences[last - value] = 0;
        continue;
      }

      next[depth] += 1;
      spent += 1;
      attempts += 1n;
      attemptsByDepth[depth] += 1n;
      let collision = false;
      for (const value of prefix) {
        if (differences[candidate - value] !== 0) {
          collision = true;
          break;
        }
      }
      if (collision) {
        rejectedPrefixes += 1n;
        rejectedByDepth[depth] += 1n;
        prunedSubsets += choose[cutoff - candidate][remaining - 1];
        continue;
      }

      if (remaining === 1) {
        const values = [...prefix, candidate];
        const gapSum = numericGapSquareSum(values);
        sidonSubsets += 1n;
        histogram.set(gapSum, (histogram.get(gapSum) || 0n) + 1n);
        if (minimum === null || gapSum < minimum) {
          minimum = gapSum;
          minimizerCount = 1n;
          minimizers = [values];
        } else if (gapSum === minimum) {
          minimizerCount += 1n;
          if (minimizers.length < saveLimit) minimizers.push(values);
        }
      } else {
        for (const value of prefix) differences[candidate - value] = 1;
        prefix.push(candidate);
        next.push(candidate + 1);
      }
    }
    return describe();
  }

  return Object.freeze({advance, describe});
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {evaluateSidonGapSet, createSidonGapSearch, limits: LIMITS};
}
