"use strict";

/**
 * Exact inverse and ratio classifiers for P(x)=(x+1)...(x+5), x in N.
 * For t>=3, (t-1)^5 < t^5-5t^3+4t < t^5. Hence P(m)=Y has only
 * the possible offset m=floor(Y^(1/5))-2. The adjacent guide proves this
 * bound and the integer-root iteration, and distinguishes finite queries
 * from the global Erdős 686/four problem. No imports or I/O are required.
 */

const limits = Object.freeze({
  max_n_decimal_digits: 256,
  max_target_decimal_digits: 1282,
  max_newton_iterations: 256,
  max_scan_n_decimal_digits: 32,
  max_scan_points: 10000,
  max_advance_points: 1000,
  max_record_page_size: 1000
});

function natural(value, label, maxDigits) {
  let out;
  if (typeof value === "bigint") out = value;
  else if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || value < 0) {
      throw new RangeError(label + " must be an exact nonnegative integer");
    }
    out = BigInt(value);
  } else if (typeof value === "string" && /^(0|[1-9][0-9]*)$/.test(value)) {
    if (value.length > maxDigits) throw new RangeError(label + " exceeds the decimal digit limit");
    out = BigInt(value);
  } else {
    throw new TypeError(label + " must be a BigInt, safe integer or canonical natural decimal string");
  }
  if (out < 0n || out.toString().length > maxDigits) {
    throw new RangeError(label + " is outside the permitted natural-number range");
  }
  return out;
}

function boundedInteger(value, low, high, label) {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < low || value > high) {
    throw new RangeError(label + " must be an integer Number in [" + low + ", " + high + "]");
  }
  return value;
}

function optionsObject(value, keys, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(label + " must be an options object");
  }
  for (const key of Object.keys(value)) {
    if (!keys.includes(key)) throw new TypeError("unknown " + label + " option: " + key);
  }
}

function fifthPower(x) {
  const square = x * x;
  return square * square * x;
}

function windowFive(x) {
  return (x + 1n) * (x + 2n) * (x + 3n) * (x + 4n) * (x + 5n);
}

function floorFifthRoot(valueInput) {
  const value = natural(valueInput, "value", limits.max_target_decimal_digits);
  let root = 0n;
  let iterations = 0;
  if (value !== 0n) {
    const bitLength = value.toString(2).length;
    root = 1n << BigInt(Math.floor((bitLength + 4) / 5));
    for (;;) {
      if (iterations >= limits.max_newton_iterations) {
        throw new RangeError("the fifth-root iteration budget was exhausted");
      }
      const square = root * root;
      const next = (4n * root + value / (square * square)) / 5n;
      iterations++;
      if (next >= root) break;
      root = next;
    }
  }
  const lower = fifthPower(root);
  const upper = fifthPower(root + 1n);
  if (lower > value || upper <= value) throw new Error("internal fifth-root bracket failure");
  return {
    schema: "erdos686.fifth_root_bracket/v1",
    value: value.toString(),
    floor_root: root.toString(),
    lower_power: lower.toString(),
    upper_power: upper.toString(),
    lower_gap: (value - lower).toString(),
    upper_gap: (upper - value).toString(),
    is_perfect_fifth_power: value === lower,
    newton_iterations: iterations,
    integer_divisions: 2 * iterations
  };
}

function locateWindowFiveProduct(valueInput) {
  const value = natural(valueInput, "value", limits.max_target_decimal_digits);
  const bracket = floorFifthRoot(value);
  if (value < 120n) {
    return {
      schema: "erdos686.window_five_inverse/v1",
      status: "BELOW_MINIMUM_PRODUCT",
      target: value.toString(),
      minimum_product: "120",
      root_bracket: bracket,
      candidate_m: null,
      candidate_product: null,
      floor_window_offset: null,
      ceiling_window_offset: "0",
      signed_difference: null,
      equals_target: false
    };
  }
  const candidate = BigInt(bracket.floor_root) - 2n;
  const product = windowFive(candidate);
  const difference = product - value;
  return {
    schema: "erdos686.window_five_inverse/v1",
    status: difference === 0n ? "WINDOW_PRODUCT" : "NOT_A_WINDOW_PRODUCT",
    target: value.toString(),
    minimum_product: "120",
    root_bracket: bracket,
    candidate_m: candidate.toString(),
    candidate_product: product.toString(),
    floor_window_offset: (difference > 0n ? candidate - 1n : candidate).toString(),
    ceiling_window_offset: (difference < 0n ? candidate + 1n : candidate).toString(),
    signed_difference: difference.toString(),
    equals_target: difference === 0n
  };
}

function classifyLengthFiveRatio(nInput) {
  const n = natural(nInput, "n", limits.max_n_decimal_digits);
  const product = windowFive(n);
  const target = 4n * product;
  const inverse = locateWindowFiveProduct(target);
  if (inverse.candidate_m === null) throw new Error("internal ratio target below minimum");
  const candidate = BigInt(inverse.candidate_m);
  const minimumM = n + 5n;
  const disjoint = candidate >= minimumM;
  return {
    schema: "erdos686.length_five_ratio_classification/v1",
    status: inverse.equals_target ? (disjoint ? "ELIGIBLE_WITNESS" : "OVERLAPPING_EQUALITY") : "NO_EQUALITY",
    n: n.toString(),
    numerator_multiplier: "4",
    denominator_product: product.toString(),
    minimum_eligible_m: minimumM.toString(),
    candidate_is_disjoint: disjoint,
    inverse
  };
}

function copy(value) {
  return value === null ? null : JSON.parse(JSON.stringify(value));
}

function createLengthFiveRatioScan(options) {
  optionsObject(options, ["from", "through"], "scan");
  const from = natural(options.from, "from", limits.max_scan_n_decimal_digits);
  const through = natural(options.through, "through", limits.max_scan_n_decimal_digits);
  if (through < from) throw new RangeError("scan requires from <= through");
  const requested = through - from + 1n;
  if (requested > BigInt(limits.max_scan_points)) {
    throw new RangeError("the inclusive scan exceeds the point limit");
  }
  let next = from;
  let processed = 0;
  let iterations = 0;
  let minimumIterations = null;
  let maximumIterations = 0;
  let disjoint = 0;
  let equalities = 0;
  let perfectTargets = 0;
  const signs = { negative: 0, zero: 0, positive: 0 };
  const witnesses = [];
  const compact = [];
  let first = null;
  let last = null;

  function describe() {
    return {
      schema: "erdos686.length_five_ratio_scan/v1",
      status: next > through ? "COMPLETE" : "IN_PROGRESS",
      from: from.toString(),
      through: through.toString(),
      requested_points: requested.toString(),
      processed_points: String(processed),
      covered_through: processed ? (next - 1n).toString() : null,
      next_n: next > through ? null : next.toString(),
      candidate_is_disjoint_count: String(disjoint),
      equality_count: String(equalities),
      eligible_witness_count: String(witnesses.length),
      eligible_witnesses: witnesses.map(witness => ({ ...witness })),
      perfect_fifth_power_targets: String(perfectTargets),
      difference_sign_counts: { negative: String(signs.negative), zero: String(signs.zero), positive: String(signs.positive) },
      work: {
        fifth_root_calls: processed,
        newton_iterations: iterations,
        minimum_newton_iterations: minimumIterations,
        maximum_newton_iterations: maximumIterations,
        integer_divisions: 2 * iterations,
        window_product_evaluations: 2 * processed,
        candidate_product_comparisons: processed,
        root_bracket_comparisons: 2 * processed,
        search_over_m: false
      },
      record_count: processed,
      records_truncated: false,
      record_format: ["floor_root_of_4P(n)", "P(floor_root-2)-4P(n)"],
      record_n: "from + zero_based_record_index",
      first_point: copy(first),
      last_point: copy(last)
    };
  }

  function advance(budget) {
    boundedInteger(budget, 1, limits.max_advance_points, "budget");
    let advanced = 0;
    while (next <= through && advanced < budget) {
      const point = classifyLengthFiveRatio(next);
      const inverse = point.inverse;
      const root = inverse.root_bracket;
      const delta = BigInt(inverse.signed_difference);
      const record = [root.floor_root, inverse.signed_difference];
      // Commit this point to retained state only after its entire classification.
      compact.push(record);
      if (first === null) first = point;
      last = point;
      if (point.candidate_is_disjoint) disjoint++;
      if (inverse.equals_target) equalities++;
      if (root.is_perfect_fifth_power) perfectTargets++;
      signs[delta < 0n ? "negative" : delta > 0n ? "positive" : "zero"]++;
      if (point.status === "ELIGIBLE_WITNESS") witnesses.push({ n: point.n, m: inverse.candidate_m });
      iterations += root.newton_iterations;
      if (minimumIterations === null || root.newton_iterations < minimumIterations) {
        minimumIterations = root.newton_iterations;
      }
      if (root.newton_iterations > maximumIterations) maximumIterations = root.newton_iterations;
      next++;
      processed++;
      advanced++;
    }
    if (BigInt(processed) !== next - from || compact.length !== processed) {
      throw new Error("internal scan coverage accounting failure");
    }
    return describe();
  }

  function records(query = {}) {
    optionsObject(query, ["start_index", "limit"], "records");
    const start = boundedInteger(query.start_index === undefined ? 0 : query.start_index,
      0, compact.length, "start_index");
    const pageSize = boundedInteger(query.limit === undefined ? limits.max_record_page_size : query.limit,
      1, limits.max_record_page_size, "limit");
    const end = Math.min(compact.length, start + pageSize);
    return {
      schema: "erdos686.length_five_ratio_records/v1",
      scan_status: next > through ? "COMPLETE" : "IN_PROGRESS",
      from: from.toString(),
      through: through.toString(),
      start_index: start,
      end_index_exclusive: end,
      available_records: compact.length,
      requested_points: requested.toString(),
      record_format: ["floor_root_of_4P(n)", "P(floor_root-2)-4P(n)"],
      record_n: "from + zero_based_record_index",
      records: compact.slice(start, end).map(record => record.slice()),
      next_start_index: end === compact.length ? null : end,
      pagination_scope: "currently_processed_points"
    };
  }

  return Object.freeze({ describe, advance, records });
}

module.exports = {
  floorFifthRoot,
  locateWindowFiveProduct,
  classifyLengthFiveRatio,
  createLengthFiveRatioScan,
  limits
};
