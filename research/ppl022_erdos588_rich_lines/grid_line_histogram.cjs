"use strict";

// Exact theorem-derived grid line counts; see GRID_LINE_HISTOGRAM_API.md.
const GRID_HISTOGRAM_LIMITS = Object.freeze({
  min_side_length: 2,
  max_side_length: 1024,
  min_dimension: 1,
  max_dimension: 4096,
  max_power_digits: 512,
  max_term_records: 8192
});
const POWER_LIMIT = 10n ** BigInt(GRID_HISTOGRAM_LIMITS.max_power_digits) - 1n;

function countGridLineHistogram(options) {
  if (options === null || typeof options !== "object" || Array.isArray(options)) {
    throw new TypeError("options must be an object");
  }
  const k = options.side_length;
  const dimension = options.dimension;
  if (!Number.isSafeInteger(k) ||
      k < GRID_HISTOGRAM_LIMITS.min_side_length ||
      k > GRID_HISTOGRAM_LIMITS.max_side_length) {
    throw new RangeError("side_length must be an integer from 2 through 1024");
  }
  if (!Number.isSafeInteger(dimension) ||
      dimension < GRID_HISTOGRAM_LIMITS.min_dimension ||
      dimension > GRID_HISTOGRAM_LIMITS.max_dimension) {
    throw new RangeError("dimension must be an integer from 1 through 4096");
  }
  const includeTerms = options.include_terms === undefined ? false : options.include_terms;
  if (typeof includeTerms !== "boolean") {
    throw new TypeError("include_terms must be a boolean");
  }
  const work = {
    exponentiation_calls: 0,
    exponentiation_multiplications: 0,
    exponentiation_squarings: 0,
    point_count_square_multiplications: 0,
    power_cache_hits: 0,
    step_basis_cache_hits: 0,
    sieve_composite_marks: 0,
    mobius_terms_considered: 0,
    nonzero_mobius_terms_added: 0,
    zero_mobius_terms_skipped: 0,
    retained_term_records: 0,
    points_enumerated: 0,
    point_pairs_enumerated: 0,
    individual_lines_enumerated: 0,
    projected_coordinates_enumerated: 0
  };

  function checkedProduct(left, right, label) {
    if (left !== 0n && right > POWER_LIMIT / left) {
      throw new RangeError(label + " exceeds the power digit limit");
    }
    return left * right;
  }
  function boundedPower(base) {
    work.exponentiation_calls++;
    let exponent = dimension;
    let result = 1n;
    let factor = base;
    while (exponent > 0) {
      if (exponent % 2 === 1) {
        result = checkedProduct(result, factor, "integer power");
        work.exponentiation_multiplications++;
      }
      exponent = Math.floor(exponent / 2);
      if (exponent > 0) {
        factor = checkedProduct(factor, factor, "integer power");
        work.exponentiation_squarings++;
      }
    }
    return result;
  }

  const kb = BigInt(k);
  const pointCount = boundedPower(kb);
  const maximumPower = checkedProduct(pointCount, pointCount, "squared point count");
  work.point_count_square_multiplications++;
  const powerCache = new Map([
    [kb.toString(), { base: kb, value: pointCount, construction: "bounded_exponentiation" }],
    [(kb * kb).toString(), { base: kb * kb, value: maximumPower, construction: "squared_point_count" }]
  ]);
  function cachedPower(base) {
    const key = base.toString();
    if (powerCache.has(key)) {
      work.power_cache_hits++;
      return powerCache.get(key).value;
    }
    const value = boundedPower(base);
    powerCache.set(key, { base, value, construction: "bounded_exponentiation" });
    return value;
  }

  const bound = k - 1;
  const mu = Array(bound + 1).fill(0);
  const leastPrime = Array(bound + 1).fill(0);
  const primes = [];
  mu[1] = 1;
  for (let value = 2; value <= bound; value++) {
    if (leastPrime[value] === 0) {
      leastPrime[value] = value;
      primes.push(value);
      mu[value] = -1;
    }
    for (const prime of primes) {
      const multiple = value * prime;
      if (multiple > bound) break;
      leastPrime[multiple] = prime;
      work.sieve_composite_marks++;
      if (value % prime === 0) {
        mu[multiple] = 0;
        break;
      }
      mu[multiple] = -mu[value];
    }
  }

  const basis = new Map();
  function stepBasis(scale) {
    if (basis.has(scale)) {
      work.step_basis_cache_hits++;
      return basis.get(scale);
    }
    const a = BigInt(scale);
    const maximumCoordinate = BigInt(bound) / a;
    const singleCoordinate = kb + 2n * kb * maximumCoordinate -
      a * maximumCoordinate * (maximumCoordinate + 1n);
    const power = cachedPower(singleCoordinate);
    const record = {
      scale,
      maximum_abs_direction_coordinate: Number(maximumCoordinate),
      one_coordinate_weight: singleCoordinate,
      cartesian_weight: power,
      nonzero_direction_weight: power - pointCount
    };
    basis.set(scale, record);
    return record;
  }

  const segmentCounts = Array(k + 3).fill(0n);
  const segmentRows = [];
  const terms = includeTerms ? [] : null;
  for (let length = 2; length <= k; length++) {
    const divisorLimit = Math.floor(bound / (length - 1));
    let numerator = 0n;
    for (let g = 1; g <= divisorLimit; g++) {
      const scale = (length - 1) * g;
      work.mobius_terms_considered++;
      let contribution = 0n;
      if (mu[g] === 0) {
        work.zero_mobius_terms_skipped++;
      } else {
        contribution = BigInt(mu[g]) * stepBasis(scale).nonzero_direction_weight;
        numerator += contribution;
        work.nonzero_mobius_terms_added++;
      }
      if (includeTerms) {
        if (terms.length >= GRID_HISTOGRAM_LIMITS.max_term_records) {
          throw new RangeError("too many retained Mobius term records");
        }
        terms.push({
          segment_length: length,
          divisor: g,
          mobius: mu[g],
          step_scale: scale,
          signed_contribution: contribution.toString()
        });
      }
    }
    if (numerator < 0n || numerator % 2n !== 0n) {
      throw new Error("primitive-segment orientation accounting failed");
    }
    segmentCounts[length] = numerator / 2n;
    segmentRows.push({
      segment_length: length,
      divisor_limit: divisorLimit,
      oriented_primitive_segment_count: numerator.toString(),
      unoriented_consecutive_segments: segmentCounts[length].toString()
    });
  }
  for (let length = k + 1; length <= k + 2; length++) {
    segmentRows.push({
      segment_length: length,
      divisor_limit: 0,
      oriented_primitive_segment_count: "0",
      unoriented_consecutive_segments: "0"
    });
  }

  const histogram = [];
  let cumulative = 0n;
  let representedPairs = 0n;
  let incidences = 0n;
  let segmentSum = 0n;
  for (let length = k; length >= 2; length--) {
    const exact = segmentCounts[length] - 2n * segmentCounts[length + 1] +
      segmentCounts[length + 2];
    if (exact < 0n) throw new Error("negative exact line count");
    cumulative += exact;
    representedPairs += BigInt(length * (length - 1) / 2) * exact;
    incidences += BigInt(length) * exact;
    segmentSum += segmentCounts[length];
    histogram.push({
      points_per_line: length,
      exact_lines: exact.toString(),
      at_least_lines: cumulative.toString()
    });
  }
  histogram.reverse();
  const pairCount = pointCount * (pointCount - 1n) / 2n;
  if (representedPairs !== pairCount || segmentSum !== pairCount) {
    throw new Error("complete grid pair accounting failed");
  }
  work.retained_term_records = terms === null ? 0 : terms.length;
  const topCount = segmentCounts[k];

  return {
    schema: "erdos588.grid_line_histogram/v1",
    side_length: k,
    dimension,
    point_count: pointCount.toString(),
    maximum_collinearity: k,
    determined_line_count: cumulative.toString(),
    point_line_incidences: incidences.toString(),
    histogram,
    segment_counts: segmentRows,
    mobius_table: Array.from({ length: bound }, (_, index) => {
      const g = index + 1;
      return { g, mobius: mu[g], least_prime_divisor: g === 1 ? null : leastPrime[g] };
    }),
    power_values: [...powerCache.values()].sort((a, b) =>
      a.base < b.base ? -1 : a.base > b.base ? 1 : 0).map(row => ({
      base: row.base.toString(),
      exponent: dimension,
      value: row.value.toString(),
      construction: row.construction
    })),
    step_basis: [...basis.values()].sort((a, b) => a.scale - b.scale).map(row => ({
      scale: row.scale,
      maximum_abs_direction_coordinate: row.maximum_abs_direction_coordinate,
      one_coordinate_weight: row.one_coordinate_weight.toString(),
      cartesian_weight: row.cartesian_weight.toString(),
      excluded_zero_direction_weight: pointCount.toString(),
      nonzero_direction_weight: row.nonzero_direction_weight.toString()
    })),
    terms_included: includeTerms,
    mobius_terms: terms,
    accounting: {
      unordered_point_pairs: pairCount.toString(),
      sum_line_pair_counts: representedPairs.toString(),
      sum_consecutive_segment_counts: segmentSum.toString(),
      exact: true
    },
    finite_planar_interpretation: {
      property_P_side_length: true,
      exact_side_length_lines: topCount.toString(),
      existence_basis: "the proved finite integer incidence-preserving projection",
      projected_coordinates_computed: false,
      individual_incidence_records_computed: false,
      erdos_lower_bound: k >= 4 ? {
        notation: "f_k(n)",
        k,
        n: pointCount.toString(),
        at_least: topCount.toString()
      } : null,
      extremal_equality_claimed: false,
      external_frontier_claimed: false
    },
    limits: { ...GRID_HISTOGRAM_LIMITS },
    work
  };
}

const GRID_COMPOSITION_LIMITS = Object.freeze({
  max_factors: 32,
  max_total_dimension: 4096,
  max_source_id_characters: 512,
  max_power_digits: 512,
  max_term_records: 8192
});

// Compose valid source-identified uniform results. This checks the required
// record structure and algebraic fields, but does not re-exponentiate their
// stored powers, re-sieve their Mobius values, or authenticate source IDs.
function composeRectangularGridLineHistograms(options) {
  if (options === null || typeof options !== "object" || Array.isArray(options)) {
    throw new TypeError("options must be an object");
  }
  if (!Array.isArray(options.factors) || options.factors.length < 1 ||
      options.factors.length > GRID_COMPOSITION_LIMITS.max_factors) {
    throw new RangeError("factors must contain from 1 through 32 source results");
  }
  const includeTerms = options.include_terms === undefined ? false : options.include_terms;
  if (typeof includeTerms !== "boolean") throw new TypeError("include_terms must be boolean");
  function missing(label) {
    const error = new Error("Missing or inconsistent source premise: " + label);
    error.name = "MissingPremiseError";
    throw error;
  }
  function integer(value, label) {
    if (typeof value !== "string" || !/^(?:0|[1-9][0-9]*)$/.test(value)) missing(label);
    if (value.length > GRID_COMPOSITION_LIMITS.max_power_digits) {
      throw new RangeError(label + " exceeds the power digit limit");
    }
    return BigInt(value);
  }
  function product(left, right, label) {
    if (left !== 0n && right > POWER_LIMIT / left) {
      throw new RangeError(label + " exceeds the combined power digit limit");
    }
    return left * right;
  }
  const work = {
    source_factors_read: options.factors.length,
    source_step_rows_checked: 0,
    source_mobius_rows_read: 0,
    point_count_factor_multiplications: 0,
    point_count_square_multiplications: 0,
    step_weight_multiplications: 0,
    mobius_terms_considered: 0,
    nonzero_mobius_terms_added: 0,
    zero_mobius_terms_skipped: 0,
    retained_term_records: 0,
    integer_powers_recomputed: 0,
    mobius_sieves_run: 0,
    points_enumerated: 0,
    point_pairs_enumerated: 0,
    individual_lines_enumerated: 0,
    projected_coordinates_enumerated: 0
  };
  const factors = [];
  let pointCount = 1n;
  let totalDimension = 0;
  let maximumSide = 0;
  let mobiusFactorIndex = -1;
  for (let index = 0; index < options.factors.length; index++) {
    const factor = options.factors[index];
    if (factor === null || typeof factor !== "object") missing("factor " + index);
    if (typeof factor.source_id !== "string" || !factor.source_id.trim() ||
        factor.source_id.length > GRID_COMPOSITION_LIMITS.max_source_id_characters) {
      missing("factor " + index + " source_id");
    }
    const result = factor.result;
    if (!result || result.schema !== "erdos588.grid_line_histogram/v1") {
      missing("factor " + index + " uniform result schema");
    }
    const side = result.side_length;
    const dimension = result.dimension;
    if (!Number.isSafeInteger(side) || side < 2 ||
        side > GRID_HISTOGRAM_LIMITS.max_side_length) missing("factor " + index + " side_length");
    if (!Number.isSafeInteger(dimension) || dimension < 1 ||
        dimension > GRID_HISTOGRAM_LIMITS.max_dimension) missing("factor " + index + " dimension");
    totalDimension += dimension;
    if (totalDimension > GRID_COMPOSITION_LIMITS.max_total_dimension) {
      throw new RangeError("combined dimension exceeds 4096");
    }
    const count = integer(result.point_count, "factor " + index + " point_count");
    if (count < 2n) missing("factor " + index + " positive grid point count");
    pointCount = product(pointCount, count, "combined point count");
    work.point_count_factor_multiplications++;
    if (!Array.isArray(result.step_basis) || result.step_basis.length !== side - 1) {
      missing("factor " + index + " complete step_basis");
    }
    const steps = new Map();
    for (const row of result.step_basis) {
      if (!row || !Number.isSafeInteger(row.scale) || row.scale < 1 ||
          row.scale >= side || steps.has(row.scale)) missing("factor " + index + " scale");
      const maximum = Math.floor((side - 1) / row.scale);
      const sb = BigInt(side), mb = BigInt(maximum), ab = BigInt(row.scale);
      const expectedWeight = sb + 2n * sb * mb - ab * mb * (mb + 1n);
      const one = integer(row.one_coordinate_weight, "factor " + index + " S-value");
      const weight = integer(row.cartesian_weight, "factor " + index + " stored power");
      const excluded = integer(row.excluded_zero_direction_weight, "factor " + index + " zero weight");
      const nonzero = integer(row.nonzero_direction_weight, "factor " + index + " nonzero weight");
      if (row.maximum_abs_direction_coordinate !== maximum || one !== expectedWeight ||
          excluded !== count || weight < count || nonzero !== weight - count) {
        missing("factor " + index + " step " + row.scale + " identities");
      }
      steps.set(row.scale, {
        scale: row.scale,
        maximum_abs_direction_coordinate: maximum,
        one_coordinate_weight: one.toString(),
        cartesian_weight: weight.toString(),
        excluded_zero_direction_weight: excluded.toString(),
        nonzero_direction_weight: nonzero.toString()
      });
      work.source_step_rows_checked++;
    }
    for (let scale = 1; scale < side; scale++) {
      if (!steps.has(scale)) missing("factor " + index + " scale " + scale);
    }
    if (!Array.isArray(result.mobius_table) || result.mobius_table.length !== side - 1) {
      missing("factor " + index + " complete mobius_table");
    }
    const mobius = new Map();
    for (const row of result.mobius_table) {
      if (!row || !Number.isSafeInteger(row.g) || row.g < 1 || row.g >= side ||
          mobius.has(row.g) || ![-1, 0, 1].includes(row.mobius)) {
        missing("factor " + index + " Mobius row");
      }
      mobius.set(row.g, row.mobius);
      work.source_mobius_rows_read++;
    }
    for (let g = 1; g < side; g++) if (!mobius.has(g)) missing("factor " + index + " mu(" + g + ")");
    if (mobius.get(1) !== 1) missing("factor " + index + " mu(1)");
    factors.push({ source_id: factor.source_id, side, dimension, count, steps, mobius });
    if (side > maximumSide) { maximumSide = side; mobiusFactorIndex = index; }
  }
  product(pointCount, pointCount, "squared combined point count");
  work.point_count_square_multiplications++;
  const mobius = factors[mobiusFactorIndex].mobius;
  for (let index = 0; index < factors.length; index++) {
    for (const [g, value] of factors[index].mobius) {
      if (value !== mobius.get(g)) missing("factor " + index + " shared mu(" + g + ")");
    }
  }

  const combinedBasis = [];
  const weights = Array(maximumSide).fill(0n);
  for (let scale = 1; scale < maximumSide; scale++) {
    let weight = 1n;
    const factorWeights = [];
    for (let index = 0; index < factors.length; index++) {
      const factor = factors[index];
      const constant = scale >= factor.side;
      const sourceRow = constant ? null : factor.steps.get(scale);
      if (!constant && sourceRow === undefined) missing("factor " + index + " required scale " + scale);
      const value = constant ? factor.count : BigInt(sourceRow.cartesian_weight);
      weight = product(weight, value, "combined step weight");
      work.step_weight_multiplications++;
      factorWeights.push({
        factor_index: index,
        source_scale: constant ? null : scale,
        all_direction_coordinates_zero: constant,
        one_coordinate_weight: constant ? String(factor.side) : sourceRow.one_coordinate_weight,
        cartesian_weight: value.toString()
      });
    }
    if (weight < pointCount) missing("combined scale " + scale + " below zero-direction weight");
    weights[scale] = weight - pointCount;
    combinedBasis.push({
      scale, factor_weights: factorWeights,
      cartesian_weight: weight.toString(),
      excluded_zero_direction_weight: pointCount.toString(),
      nonzero_direction_weight: weights[scale].toString()
    });
  }

  const segments = Array(maximumSide + 3).fill(0n);
  const segmentRows = [];
  const terms = includeTerms ? [] : null;
  for (let length = 2; length <= maximumSide; length++) {
    const limit = Math.floor((maximumSide - 1) / (length - 1));
    let numerator = 0n;
    for (let g = 1; g <= limit; g++) {
      if (!mobius.has(g)) missing("required mu(" + g + ")");
      const scale = (length - 1) * g;
      const coefficient = mobius.get(g);
      const contribution = BigInt(coefficient) * weights[scale];
      numerator += contribution;
      work.mobius_terms_considered++;
      if (coefficient === 0) work.zero_mobius_terms_skipped++;
      else work.nonzero_mobius_terms_added++;
      if (includeTerms) {
        if (terms.length >= GRID_COMPOSITION_LIMITS.max_term_records) {
          throw new RangeError("too many retained composition terms");
        }
        terms.push({ segment_length: length, divisor: g, mobius: coefficient,
          step_scale: scale, signed_contribution: contribution.toString() });
      }
    }
    if (numerator < 0n || numerator % 2n !== 0n) missing("composed segment orientation accounting");
    segments[length] = numerator / 2n;
    segmentRows.push({ segment_length: length, divisor_limit: limit,
      oriented_primitive_segment_count: numerator.toString(),
      unoriented_consecutive_segments: segments[length].toString() });
  }
  for (let length = maximumSide + 1; length <= maximumSide + 2; length++) {
    segmentRows.push({ segment_length: length, divisor_limit: 0,
      oriented_primitive_segment_count: "0", unoriented_consecutive_segments: "0" });
  }
  const histogram = [];
  let cumulative = 0n, pairs = 0n, incidences = 0n, segmentSum = 0n;
  for (let length = maximumSide; length >= 2; length--) {
    const exact = segments[length] - 2n * segments[length + 1] + segments[length + 2];
    if (exact < 0n) missing("composed nonnegative exact line counts");
    cumulative += exact;
    pairs += BigInt(length * (length - 1) / 2) * exact;
    incidences += BigInt(length) * exact;
    segmentSum += segments[length];
    histogram.push({ points_per_line: length, exact_lines: exact.toString(),
      at_least_lines: cumulative.toString() });
  }
  histogram.reverse();
  const expectedPairs = pointCount * (pointCount - 1n) / 2n;
  if (pairs !== expectedPairs || segmentSum !== expectedPairs) {
    missing("composed complete pair accounting");
  }
  work.retained_term_records = terms === null ? 0 : terms.length;
  return {
    schema: "erdos588.rectangular_grid_histogram/v1",
    status: "COMPOSED_FROM_IDENTIFIED_PREMISES",
    blocks: factors.map((f, index) => ({ factor_index: index, source_id: f.source_id,
      side_length: f.side, dimension: f.dimension, point_count: f.count.toString() })),
    dimension: totalDimension,
    point_count: pointCount.toString(),
    maximum_collinearity: maximumSide,
    determined_line_count: cumulative.toString(),
    point_line_incidences: incidences.toString(),
    histogram,
    segment_counts: segmentRows,
    factor_premises: factors.map((f, index) => ({
      factor_index: index, source_id: f.source_id,
      schema: "erdos588.grid_line_histogram/v1",
      side_length: f.side, dimension: f.dimension, point_count: f.count.toString(),
      step_basis: [...f.steps.values()].sort((a, b) => a.scale - b.scale),
      mobius_table: [...f.mobius.entries()].sort((a, b) => a[0] - b[0]).map(([g, value]) =>
        ({ g, mobius: value }))
    })),
    mobius_source_factor_index: mobiusFactorIndex,
    combined_step_basis: combinedBasis,
    terms_included: includeTerms,
    mobius_terms: terms,
    accounting: { unordered_point_pairs: expectedPairs.toString(),
      sum_line_pair_counts: pairs.toString(),
      sum_consecutive_segment_counts: segmentSum.toString(), exact: true },
    premise_validation: {
      required_structure_checked: true,
      coordinate_weight_formulas_checked: true,
      zero_direction_subtractions_checked: true,
      overlapping_mobius_entries_consistent: true,
      stored_integer_powers_recomputed: false,
      mobius_values_resieved: false,
      source_id_authenticity_checked: false,
      condition: "factor records must be valid exact uniform-grid results from their identified sources"
    },
    finite_planar_interpretation: {
      property_P_maximum_side: true,
      exact_maximum_side_lines: segments[maximumSide].toString(),
      existence_basis: "the proved finite integer incidence-preserving projection",
      projected_coordinates_computed: false,
      individual_incidence_records_computed: false,
      erdos_lower_bound: maximumSide >= 4 ? { notation: "f_k(n)", k: maximumSide,
        n: pointCount.toString(), at_least: segments[maximumSide].toString() } : null,
      extremal_equality_claimed: false, external_frontier_claimed: false
    },
    limits: { ...GRID_COMPOSITION_LIMITS },
    work
  };
}

module.exports = Object.freeze({
  countGridLineHistogram,
  composeRectangularGridLineHistograms,
  GRID_HISTOGRAM_LIMITS,
  GRID_COMPOSITION_LIMITS
});
