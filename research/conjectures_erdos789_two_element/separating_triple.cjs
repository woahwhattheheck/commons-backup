"use strict";

// Implements the triple criterion and five-nonzero guarantee in sections 3-4 of
// https://www.erdosproblemaday.com/report/789 (2026-07-28).
// The integer-set / nonempty-subset convention follows FormalConjectures #789.
// This module performs no I/O and uses no host dependencies.

const DECIMAL_INTEGER = /^(?:0|-?[1-9][0-9]*)(?![\s\S])/;

function integer(value, index) {
  if (typeof value === "bigint") return value;
  if (typeof value === "number" && Number.isSafeInteger(value)) return BigInt(value);
  if (typeof value === "string" && DECIMAL_INTEGER.test(value)) return BigInt(value);
  throw new TypeError(
    "values[" + index + "] must be a bigint, a safe integer number, or a canonical decimal integer string"
  );
}

function readSet(values) {
  if (!Array.isArray(values)) throw new TypeError("values must be an array");
  const seen = new Set();
  const entries = [];
  for (let index = 0; index < values.length; index += 1) {
    const value = integer(values[index], index);
    if (!seen.has(value)) {
      seen.add(value);
      entries.push({value, input_index: index});
    }
  }
  return entries;
}

function collision(values, kind, leftIndices, rightIndices) {
  return {
    kind,
    left_indices: leftIndices,
    right_indices: rightIndices,
    common_sum: leftIndices.reduce((sum, index) => sum + values[index], 0n).toString()
  };
}

function findCollision(values) {
  const zero = values.findIndex(value => value === 0n);
  if (zero !== -1) {
    const other = zero === 0 ? 1 : 0;
    return collision(values, "ZERO_MEMBER", [other], [zero, other].sort((a, b) => a - b));
  }
  for (let first = 0; first < 2; first += 1) {
    for (let second = first + 1; second < 3; second += 1) {
      if (values[first] + values[second] === 0n) {
        return collision(values, "OPPOSITE_PAIR", [3 - first - second], [0, 1, 2]);
      }
    }
  }
  for (let single = 0; single < 3; single += 1) {
    const pair = [0, 1, 2].filter(index => index !== single);
    if (values[single] === values[pair[0]] + values[pair[1]]) {
      return collision(values, "SINGLETON_EQUALS_PAIR", [single], pair);
    }
  }
  return null;
}

function describe(entries) {
  return {
    values: entries.map(entry => entry.value.toString()),
    input_indices: entries.map(entry => entry.input_index)
  };
}

function separatingSums(values) {
  return {
    "1": values.map(value => value.toString()),
    "2": [
      values[0] + values[1],
      values[0] + values[2],
      values[1] + values[2]
    ].map(value => value.toString()),
    "3": [(values[0] + values[1] + values[2]).toString()]
  };
}

/**
 * Classify exactly three distinct integers, in the caller's order.
 * The output is JSON-safe; collision indices refer to output.values.
 */
function classifySeparatingTriple(values) {
  const entries = readSet(values);
  if (values.length !== 3 || entries.length !== 3) {
    throw new RangeError("classifySeparatingTriple requires exactly three distinct integers");
  }
  const exact = entries.map(entry => entry.value);
  const obstruction = findCollision(exact);
  return {
    schema: "erdos789.triple_classification/v1",
    status: obstruction ? "COLLISION" : "SEPARATING",
    ...describe(entries),
    collision: obstruction,
    subset_sums_by_cardinality: obstruction ? null : separatingSums(exact)
  };
}

/**
 * Find a separating triple in an integer set represented by an array.
 * Equal values are deduplicated, retaining their first input index.
 * Every input item is validated. At most ten candidate triples are classified.
 */
function constructSeparatingTriple(values) {
  const entries = readSet(values);
  const nonzero = entries.filter(entry => entry.value !== 0n);
  const zero = entries.find(entry => entry.value === 0n);
  const pool = nonzero.slice(0, 5);
  const rejected = [];
  let candidateCount = 0;
  const common = {
    schema: "erdos789.triple_construction/v1",
    input_count: values.length,
    distinct_count: entries.length,
    nonzero_distinct_count: nonzero.length,
    candidate_pool: describe(pool),
    candidate_limit: 10
  };
  for (let first = 0; first < pool.length - 2; first += 1) {
    for (let second = first + 1; second < pool.length - 1; second += 1) {
      for (let third = second + 1; third < pool.length; third += 1) {
        const triple = [pool[first], pool[second], pool[third]];
        const exact = triple.map(entry => entry.value);
        const obstruction = findCollision(exact);
        candidateCount += 1;
        if (!obstruction) {
          return {
            ...common,
            status: "SEPARATING_TRIPLE",
            candidate_count: candidateCount,
            triple: describe(triple),
            subset_sums_by_cardinality: separatingSums(exact),
            obstruction: null
          };
        }
        rejected.push({...describe(triple), collision: obstruction});
      }
    }
  }

  // The cited five-nonzero guarantee makes this state unreachable for valid
  // input. Do not silently turn a construction failure into a false negative.
  if (pool.length === 5) {
    throw new Error("five-nonzero construction invariant failed");
  }

  return {
    ...common,
    status: "NO_SEPARATING_TRIPLE",
    candidate_count: candidateCount,
    triple: null,
    subset_sums_by_cardinality: null,
    obstruction: {
      reason: entries.length < 3 ? "TOO_FEW_DISTINCT_VALUES" : "ALL_TRIPLES_HAVE_COLLISIONS",
      zero_input_index: zero ? zero.input_index : null,
      zero_containing_triples: zero && entries.length >= 3
        ? {kind: "ZERO_MEMBER", identity: "a = a + 0", subset_cardinalities: [1, 2]}
        : null,
      nonzero_triples: rejected
    }
  };
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {classifySeparatingTriple, constructSeparatingTriple};
}
