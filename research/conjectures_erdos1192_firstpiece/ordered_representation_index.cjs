"use strict";

/**
 * Exact finite ordered representation counts and witnesses for Erdős 1192.
 * Counts are coefficients of (sum_{a in B} z^a)^r. The input is a set of
 * natural numbers; coordinates are ordered and may repeat. See the adjacent
 * ORDERED_REPRESENTATION_API.md for sources, derivation and evidence scope.
 * This module performs no I/O and requires no imports or native runtime.
 */

const limits = Object.freeze({
  max_input_entries: 256,
  max_order: 64,
  max_value_decimal_digits: 256,
  max_query_decimal_digits: 512,
  max_normalized_span: 65536,
  max_final_degree: 65536,
  max_table_cells: 262144,
  max_coefficient_update_bound: 4000000,
  max_page_size: 4096
});

function natural(value, label, maxDigits) {
  let out;
  if (typeof value === "bigint") {
    out = value;
  } else if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || value < 0) {
      throw new RangeError(label + " must be an exact nonnegative integer");
    }
    out = BigInt(value);
  } else if (typeof value === "string" && /^(0|[1-9][0-9]*)$/.test(value)) {
    if (value.length > maxDigits) {
      throw new RangeError(label + " exceeds the decimal digit limit");
    }
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

function objectOptions(value, allowed, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(label + " must be an options object");
  }
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) throw new TypeError("unknown " + label + " option: " + key);
  }
}

function gcd(a, b) {
  while (b !== 0n) {
    const rest = a % b;
    a = b;
    b = rest;
  }
  return a;
}

function createOrderedRepresentationIndex(options) {
  objectOptions(options, ["values", "order"], "index");
  if (!Array.isArray(options.values) || options.values.length > limits.max_input_entries) {
    throw new RangeError("values must be an array with at most " + limits.max_input_entries + " entries");
  }
  const order = boundedInteger(options.order, 0, limits.max_order, "order");
  const inputEntryCount = options.values.length;
  const unique = new Map();
  for (let i = 0; i < options.values.length; i++) {
    const value = natural(options.values[i], "values[" + i + "]", limits.max_value_decimal_digits);
    unique.set(value.toString(), value);
  }
  const values = Array.from(unique.values()).sort((a, b) => a < b ? -1 : a > b ? 1 : 0);
  const cardinality = values.length;
  const minimum = cardinality ? values[0] : 0n;
  let step = 0n;
  for (const value of values) step = gcd(step, value - minimum);
  if (step === 0n) step = 1n; // Empty sets and singletons have no nonzero difference.
  const spanBig = cardinality ? (values[cardinality - 1] - minimum) / step : 0n;
  if (spanBig > BigInt(limits.max_normalized_span)) {
    throw new RangeError("the shift/gcd-normalized span exceeds the table limit");
  }
  const span = Number(spanBig);
  const normalized = values.map(value => Number((value - minimum) / step));
  const degree = order * span;
  const tableCells = span * order * (order + 1) / 2 + order + 1;
  const updateBound = cardinality * (span * order * (order - 1) / 2 + order);
  if (degree > limits.max_final_degree ||
      tableCells > limits.max_table_cells ||
      updateBound > limits.max_coefficient_update_bound) {
    throw new RangeError("the requested order and normalized set exceed the exact table budget");
  }

  // C_j(s) = sum_{a in normalized B} C_{j-1}(s-a), with C_0(0)=1.
  // Store every suffix length once so rank/select need no tuple enumeration.
  const rows = [[1n]];
  const layers = [{ order: 0, coefficient_slots: 1, nonzero_coefficients: 1, coefficient_updates: 0 }];
  let actualUpdates = 0;
  for (let j = 1; j <= order; j++) {
    const previous = rows[j - 1];
    const next = Array(j * span + 1).fill(0n);
    let layerUpdates = 0;
    for (let sum = 0; sum < previous.length; sum++) {
      const count = previous[sum];
      if (count === 0n) continue;
      for (const value of normalized) {
        next[sum + value] += count;
        layerUpdates++;
      }
    }
    let nonzero = 0;
    for (const count of next) if (count !== 0n) nonzero++;
    rows.push(next);
    layers.push({
      order: j, coefficient_slots: next.length,
      nonzero_coefficients: nonzero, coefficient_updates: layerUpdates
    });
    actualUpdates += layerUpdates;
  }

  const final = rows[order];
  const massPrefix = [0n];
  const energyPrefix = [0n];
  const supportPrefix = [0];
  let firstSupport = null;
  let lastSupport = null;
  for (let i = 0; i < final.length; i++) {
    const count = final[i];
    massPrefix.push(massPrefix[i] + count);
    energyPrefix.push(energyPrefix[i] + count * count);
    supportPrefix.push(supportPrefix[i] + (count === 0n ? 0 : 1));
    if (count !== 0n) {
      if (firstSupport === null) firstSupport = i;
      lastSupport = i;
    }
  }
  const total = massPrefix[final.length];
  const expected = BigInt(cardinality) ** BigInt(order);
  if (total !== expected || actualUpdates > updateBound) {
    throw new Error("internal coefficient-table accounting failure");
  }
  const energy = energyPrefix[final.length];
  const totalSquared = total * total;
  const baseSum = BigInt(order) * minimum;
  const latticeMaximum = baseSum + step * BigInt(degree);
  const domainThrough = cardinality ? BigInt(order) * values[cardinality - 1] : 0n;
  const domainSize = domainThrough + 1n;
  const scaledEnergy = domainSize * energy;
  if (scaledEnergy < totalSquared) throw new Error("internal finite energy accounting failure");
  const valueStrings = values.map(String);
  const positionByValue = new Map(valueStrings.map((value, i) => [value, i]));

  function coefficient(row, sum) {
    return sum < 0 || sum >= row.length ? 0n : row[sum];
  }

  function latticeIndex(sum) {
    if (sum < baseSum || sum > latticeMaximum) return null;
    const shifted = sum - baseSum;
    if (shifted % step !== 0n) return null;
    return Number(shifted / step);
  }

  function describe() {
    return {
      schema: "erdos1192.ordered_representation_index/v1",
      status: "COMPLETE",
      order,
      values: valueStrings.slice(),
      input_entry_count: inputEntryCount,
      cardinality,
      duplicate_entries_removed: inputEntryCount - cardinality,
      semantics: {
        domain: "natural_numbers_including_zero",
        input: "set",
        coordinates: "ordered_with_repetition",
        rank: "zero_based_lexicographic_within_one_sum",
        zero_order: "one_empty_tuple_at_sum_zero"
      },
      normalization: {
        minimum_value: minimum.toString(),
        difference_gcd: step.toString(),
        singleton_or_empty_step_convention: "1",
        normalized_values: normalized.slice(),
        normalized_span: span,
        final_degree: degree,
        base_sum: baseSum.toString(),
        step: step.toString()
      },
      total_representations: total.toString(),
      energy: energy.toString(),
      represented_sum_count: String(supportPrefix[final.length]),
      support_minimum: firstSupport === null ? null : (baseSum + step * BigInt(firstSupport)).toString(),
      support_maximum: lastSupport === null ? null : (baseSum + step * BigInt(lastSupport)).toString(),
      finite_cauchy: {
        domain_from: "0",
        domain_through: domainThrough.toString(),
        domain_size: domainSize.toString(),
        total_representations_squared: totalSquared.toString(),
        scaled_energy: scaledEnergy.toString(),
        slack: (scaledEnergy - totalSquared).toString()
      },
      build: {
        coefficient_table_cells: tableCells,
        coefficient_update_bound: updateBound,
        actual_coefficient_updates: actualUpdates,
        layers: layers.map(layer => ({ ...layer })),
        tuple_enumeration: false
      }
    };
  }

  function count(sumInput) {
    const sum = natural(sumInput, "sum", limits.max_query_decimal_digits);
    const i = latticeIndex(sum);
    return (i === null ? 0n : final[i]).toString();
  }

  function interval(query) {
    objectOptions(query, ["from", "through"], "interval");
    const from = natural(query.from, "from", limits.max_query_decimal_digits);
    const through = natural(query.through, "through", limits.max_query_decimal_digits);
    if (through < from) throw new RangeError("interval requires from <= through");
    let mass = 0n;
    let intervalEnergy = 0n;
    let support = 0;
    if (through >= baseSum && from <= latticeMaximum) {
      const lowBig = from <= baseSum ? 0n : (from - baseSum + step - 1n) / step;
      const highBig = through >= latticeMaximum ? BigInt(degree) : (through - baseSum) / step;
      if (lowBig <= highBig && lowBig <= BigInt(degree)) {
        const low = Number(lowBig);
        const highExclusive = Number(highBig) + 1;
        mass = massPrefix[highExclusive] - massPrefix[low];
        intervalEnergy = energyPrefix[highExclusive] - energyPrefix[low];
        support = supportPrefix[highExclusive] - supportPrefix[low];
      }
    }
    const size = through - from + 1n;
    const zeros = size - BigInt(support);
    return {
      schema: "erdos1192.ordered_representation_interval/v1",
      from: from.toString(), through: through.toString(),
      integer_count: size.toString(),
      represented_sum_count: String(support),
      zero_sum_count: zeros.toString(),
      ordered_representations: mass.toString(),
      energy: intervalEnergy.toString(),
      fully_covered: zeros === 0n
    };
  }

  function distribution(query = {}) {
    objectOptions(query, ["start_index", "limit"], "distribution");
    const start = boundedInteger(query.start_index === undefined ? 0 : query.start_index,
      0, final.length, "start_index");
    const pageSize = boundedInteger(query.limit === undefined ? limits.max_page_size : query.limit,
      1, limits.max_page_size, "limit");
    const end = Math.min(final.length, start + pageSize);
    return {
      schema: "erdos1192.ordered_representation_distribution/v1",
      base_sum: baseSum.toString(),
      step: step.toString(),
      start_index: start,
      end_index_exclusive: end,
      total_coefficients: final.length,
      counts: final.slice(start, end).map(String),
      next_start_index: end === final.length ? null : end,
      sum_of_index: "base_sum + step * index",
      omitted_nonlattice_sums_have_count_zero: true
    };
  }

  function select(sumInput, rankInput) {
    const sum = natural(sumInput, "sum", limits.max_query_decimal_digits);
    const requestedRank = natural(rankInput, "rank", limits.max_query_decimal_digits);
    const i = latticeIndex(sum);
    const fiberCount = i === null ? 0n : final[i];
    if (requestedRank >= fiberCount) {
      return {
        schema: "erdos1192.ordered_representation_selection/v1",
        status: "RANK_OUT_OF_RANGE",
        sum: sum.toString(), rank: requestedRank.toString(),
        representation_count: fiberCount.toString(),
        tuple: null
      };
    }
    let residualRank = requestedRank;
    let residualSum = i;
    const tuple = [];
    for (let position = 0; position < order; position++) {
      const suffix = rows[order - position - 1];
      let chosen = false;
      for (let a = 0; a < normalized.length; a++) {
        const block = coefficient(suffix, residualSum - normalized[a]);
        if (residualRank >= block) {
          residualRank -= block;
        } else {
          tuple.push(valueStrings[a]);
          residualSum -= normalized[a];
          chosen = true;
          break;
        }
      }
      if (!chosen) throw new Error("internal representation selection failure");
    }
    if (residualSum !== 0 || residualRank !== 0n) {
      throw new Error("internal representation selection remainder");
    }
    return {
      schema: "erdos1192.ordered_representation_selection/v1",
      status: "SELECTED",
      sum: sum.toString(), rank: requestedRank.toString(),
      representation_count: fiberCount.toString(),
      tuple
    };
  }

  function rank(tupleInput) {
    if (!Array.isArray(tupleInput) || tupleInput.length !== order) {
      throw new RangeError("tuple must be an array of length order");
    }
    const positions = [];
    const tuple = [];
    let sum = 0n;
    let normalizedSum = 0;
    for (let i = 0; i < tupleInput.length; i++) {
      const value = natural(tupleInput[i], "tuple[" + i + "]", limits.max_value_decimal_digits);
      const key = value.toString();
      const position = positionByValue.get(key);
      if (position === undefined) throw new RangeError("tuple entry is not a member of the input set");
      positions.push(position);
      tuple.push(key);
      sum += value;
      normalizedSum += normalized[position];
    }
    const fiberCount = final[normalizedSum];
    let out = 0n;
    let residualSum = normalizedSum;
    for (let i = 0; i < order; i++) {
      const suffix = rows[order - i - 1];
      for (let a = 0; a < positions[i]; a++) {
        out += coefficient(suffix, residualSum - normalized[a]);
      }
      residualSum -= normalized[positions[i]];
    }
    if (residualSum !== 0 || out >= fiberCount) {
      throw new Error("internal representation rank failure");
    }
    return {
      schema: "erdos1192.ordered_representation_rank/v1",
      status: "RANKED",
      sum: sum.toString(), rank: out.toString(),
      representation_count: fiberCount.toString(),
      tuple
    };
  }

  return Object.freeze({ describe, count, interval, distribution, select, rank });
}

module.exports = { createOrderedRepresentationIndex, limits };
