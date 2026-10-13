"use strict";

// Translation-weighted continuation of the exact prefix traversal introduced in
// Commons PR #31130, sidon_gap_search.cjs blob 82f165edd18b7d71f5746f96ff606ad14fe0aadf.
// Counts every original window subset while traversing only minimum-zero sets.
// The original objective, API, accepted finite inputs and reduction remain intact.

const LIMITS = Object.freeze({
  max_search_cardinality: 12,
  max_cutoff: 512,
  max_extensions_per_advance: 1000000,
  default_saved_minimizers: 4096,
  max_saved_minimizers: 65536,
  default_saved_minimizer_families: 4096,
  max_saved_minimizer_families: 65536
});

function boundedInteger(value, label, lower, upper) {
  if (!Number.isSafeInteger(value) || value < lower || value > upper) {
    throw new RangeError(label + " must be an integer from " + lower + " through " + upper);
  }
  return value;
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
 * Exact Sidon search over all n-subsets of {0,...,cutoff}, traversing only
 * normalized representatives whose minimum is zero.
 *
 * A complete representative of diameter d has cutoff-d+1 translations.
 * A rejected normalized prefix of length k ending at x accounts for
 * C(cutoff-x,n-k) normalized sets and C(cutoff-x+1,n-k+1) original sets.
 *
 * advance(budget) performs at most budget extension attempts and returns a fresh
 * JSON-safe result. Keep the same object to continue. This module has no I/O,
 * imports, or serialized-state restore. Partial output is not a complete proof.
 */
function createTranslatedSidonGapSearch(options) {
  if (options === null || typeof options !== "object" || Array.isArray(options)) {
    throw new TypeError("options must be an object");
  }
  const allowed = new Set([
    "n", "cutoff", "max_saved_minimizers", "max_saved_minimizer_families"
  ]);
  for (const key of Object.keys(options)) {
    if (!allowed.has(key)) throw new TypeError("unknown search option: " + key);
  }
  const n = boundedInteger(options.n, "n", 2, LIMITS.max_search_cardinality);
  const cutoff = boundedInteger(options.cutoff, "cutoff", 0, LIMITS.max_cutoff);
  const saveLimit = options.max_saved_minimizers === undefined
    ? LIMITS.default_saved_minimizers
    : boundedInteger(options.max_saved_minimizers, "max_saved_minimizers", 1, LIMITS.max_saved_minimizers);
  const familyLimit = options.max_saved_minimizer_families === undefined
    ? LIMITS.default_saved_minimizer_families
    : boundedInteger(options.max_saved_minimizer_families, "max_saved_minimizer_families", 1, LIMITS.max_saved_minimizer_families);

  const choose = binomialTable(cutoff + 1, n);
  const totalSubsets = choose[cutoff + 1][n];
  const normalizedTotalSubsets = choose[cutoff][n - 1];
  const sumsetCardinality = n * (n + 1) / 2;

  // Coordinate zero is fixed, so depth-one extension attempts remain zero.
  const prefix = [0];
  const next = [0, 1];
  const differences = new Uint8Array(cutoff + 1);
  const histogram = new Map();
  const attemptsByDepth = Array(n).fill(0n);
  const rejectedByDepth = Array(n).fill(0n);
  let attempts = 0n;
  let rejectedPrefixes = 0n;
  let normalizedPrunedSubsets = 0n;
  let prunedSubsets = 0n;
  let normalizedSidonSubsets = 0n;
  let sidonSubsets = 0n;
  let minimum = null;
  let normalizedMinimizerCount = 0n;
  let minimizerCount = 0n;
  let minimizers = [];
  let minimizerFamilies = [];
  let complete = false;

  function retainMinimum(values, weight) {
    const translationMaximum = cutoff - values[values.length - 1];
    if (minimizerFamilies.length < familyLimit) {
      minimizerFamilies.push({
        normalized_values: values.slice(),
        translation_min: 0,
        translation_max: translationMaximum,
        translated_count: weight.toString()
      });
    }
    for (let shift = 0; shift <= translationMaximum && minimizers.length < saveLimit; shift += 1) {
      minimizers.push(values.map(value => value + shift));
    }
  }

  function describe() {
    return {
      schema: "erdos153.translated_sidon_gap_search/v1",
      status: complete ? "COMPLETE" : "IN_PROGRESS",
      normalization: "minimum_zero_with_exact_translation_weights",
      n,
      cutoff,
      sumset_cardinality: sumsetCardinality,
      total_subsets: totalSubsets.toString(),
      normalized_total_subsets: normalizedTotalSubsets.toString(),
      extension_attempts: attempts.toString(),
      attempts_by_depth: attemptsByDepth.map(value => value.toString()),
      rejected_prefixes: rejectedPrefixes.toString(),
      rejected_prefixes_by_depth: rejectedByDepth.map(value => value.toString()),
      pruned_non_sidon_subsets: prunedSubsets.toString(),
      normalized_pruned_non_sidon_subsets: normalizedPrunedSubsets.toString(),
      sidon_subsets: sidonSubsets.toString(),
      normalized_sidon_subsets: normalizedSidonSubsets.toString(),
      accounted_subsets: (prunedSubsets + sidonSubsets).toString(),
      normalized_accounted_subsets: (normalizedPrunedSubsets + normalizedSidonSubsets).toString(),
      minimum_gap_square_sum: minimum === null ? null : minimum.toString(),
      minimum_energy: minimum === null ? null : fraction(BigInt(minimum), BigInt(sumsetCardinality)),
      minimizer_count: minimizerCount.toString(),
      normalized_minimizer_count: normalizedMinimizerCount.toString(),
      minimizers: minimizers.map(values => values.slice()),
      max_saved_minimizers: saveLimit,
      minimizers_truncated: BigInt(minimizers.length) !== minimizerCount,
      minimizer_families: minimizerFamilies.map(family => ({
        normalized_values: family.normalized_values.slice(),
        translation_min: family.translation_min,
        translation_max: family.translation_max,
        translated_count: family.translated_count
      })),
      max_saved_minimizer_families: familyLimit,
      minimizer_families_truncated: BigInt(minimizerFamilies.length) !== normalizedMinimizerCount,
      energy_histogram: Array.from(histogram.entries())
        .sort(([left], [right]) => left - right)
        .map(([gapSum, counts]) => ({
          gap_square_sum: gapSum.toString(),
          count: counts.translated.toString(),
          normalized_count: counts.normalized.toString()
        }))
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
        if (depth === 1) {
          complete = true;
          if (normalizedPrunedSubsets + normalizedSidonSubsets !== normalizedTotalSubsets ||
              prunedSubsets + sidonSubsets !== totalSubsets) {
            throw new Error("finite-domain translation accounting invariant failed");
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
        normalizedPrunedSubsets += choose[cutoff - candidate][remaining - 1];
        prunedSubsets += choose[cutoff - candidate + 1][remaining];
        continue;
      }

      if (remaining === 1) {
        const values = [...prefix, candidate];
        const weight = BigInt(cutoff - candidate + 1);
        const gapSum = numericGapSquareSum(values);
        normalizedSidonSubsets += 1n;
        sidonSubsets += weight;
        const counts = histogram.get(gapSum) || {normalized: 0n, translated: 0n};
        counts.normalized += 1n;
        counts.translated += weight;
        histogram.set(gapSum, counts);
        if (minimum === null || gapSum < minimum) {
          minimum = gapSum;
          normalizedMinimizerCount = 1n;
          minimizerCount = weight;
          minimizers = [];
          minimizerFamilies = [];
          retainMinimum(values, weight);
        } else if (gapSum === minimum) {
          normalizedMinimizerCount += 1n;
          minimizerCount += weight;
          retainMinimum(values, weight);
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
  module.exports = {createTranslatedSidonGapSearch, limits: LIMITS};
}
