"use strict";

/**
 * Exact finite congruence hits and ordinary-integer gap rank/select.
 * Pure connected V8/CommonJS, with no imports, network, native execution or I/O.
 */
const limits = Object.freeze({
  max_integer_digits: 256,
  max_rank_digits: 257,
  max_rules: 256,
  max_classes: 4096,
  max_emitted_hits: 100000,
  max_excluded_values: 100000,
  max_page: 1000
});
const INTEGER = /^(?:0|-?[1-9][0-9]*)(?![\s\S])/;

function fail(code, message) {
  const error = new Error(message);
  error.code = code;
  throw error;
}

function integer(value, label, maximumDigits = limits.max_integer_digits) {
  let result;
  if (typeof value === "bigint") result = value;
  else if (typeof value === "number" && Number.isSafeInteger(value)) result = BigInt(value);
  else if (typeof value === "string" && INTEGER.test(value)
      && value.replace("-", "").length <= maximumDigits) result = BigInt(value);
  else fail("INVALID_INTEGER", label + " must be a BigInt, safe integer or canonical decimal integer string");
  const digits = result < 0n ? (-result).toString().length : result.toString().length;
  if (digits > maximumDigits) fail("INTEGER_OUT_OF_RANGE", label + " exceeds its decimal-digit bound");
  return result;
}

function bound(value, label, minimum, maximum) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum)
    fail("INVALID_BOUND", label + " must be an integer from " + minimum + " through " + maximum);
  return value;
}

function endpoints(options) {
  const from = integer(options.from, "from");
  const through = integer(options.through, "through");
  if (from > through) fail("REVERSED_INTERVAL", "from must be at most through");
  return { from, through };
}

function positiveMod(value, modulus) {
  const residue = value % modulus;
  return residue < 0n ? residue + modulus : residue;
}

function order(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function compileResidueInterval(options) {
  if (!options || typeof options !== "object" || Array.isArray(options))
    fail("INVALID_OPTIONS", "options must be an object");
  const { from, through } = endpoints(options);
  if (!Array.isArray(options.rules) || options.rules.length > limits.max_rules)
    fail("INVALID_RULES", "rules must be an array of at most " + limits.max_rules + " records");
  const maxHits = options.max_hits === undefined ? limits.max_emitted_hits
    : bound(options.max_hits, "max_hits", 0, limits.max_emitted_hits);
  const classes = [];
  let totalHits = 0n;
  let activeRules = 0;
  let lengthDivisions = 0;
  for (let ruleIndex = 0; ruleIndex < options.rules.length; ruleIndex += 1) {
    const rule = options.rules[ruleIndex];
    if (!rule || typeof rule !== "object" || Array.isArray(rule))
      fail("INVALID_RULE", "each rule must be an object");
    const modulus = integer(rule.modulus, "rule modulus");
    if (modulus < 1n) fail("INVALID_MODULUS", "rule moduli must be positive");
    if (!Array.isArray(rule.bad_residues))
      fail("INVALID_RESIDUES", "bad_residues must be an array");
    if (classes.length + rule.bad_residues.length > limits.max_classes)
      fail("TOO_MANY_CLASSES", "the input exceeds " + limits.max_classes + " forbidden classes");
    const seen = new Set();
    const residues = rule.bad_residues.map(value => {
      const residue = integer(value, "forbidden residue");
      if (residue < 0n || residue >= modulus)
        fail("RESIDUE_OUT_OF_RANGE", "forbidden residues must lie from zero through modulus minus one");
      if (seen.has(residue.toString()))
        fail("DUPLICATE_LOCAL_RESIDUE", "a rule may not repeat a forbidden residue");
      seen.add(residue.toString());
      return residue;
    });
    if (residues.length) activeRules += 1;
    const fromResidue = residues.length ? positiveMod(from, modulus) : 0n;
    for (let residueIndex = 0; residueIndex < residues.length; residueIndex += 1) {
      const residue = residues[residueIndex];
      const first = from + positiveMod(residue - fromResidue, modulus);
      let count = 0n;
      if (first <= through) {
        count = (through - first) / modulus + 1n;
        lengthDivisions += 1;
      }
      totalHits += count;
      classes.push({
        class_index: classes.length,
        rule_index: ruleIndex,
        residue_index: residueIndex,
        modulus: modulus.toString(),
        residue: residue.toString(),
        first_hit: count === 0n ? null : first.toString(),
        last_hit: count === 0n ? null : (first + (count - 1n) * modulus).toString(),
        hit_count: count.toString()
      });
    }
  }
  if (totalHits > BigInt(maxHits))
    fail("HIT_BUDGET_EXCEEDED", "congruence classes require " + totalHits + " emitted hits; budget is " + maxHits);

  const hits = [];
  for (const entry of classes) {
    const count = Number(entry.hit_count);
    if (count === 0) continue;
    const modulus = BigInt(entry.modulus);
    let value = BigInt(entry.first_hit);
    for (let hitIndex = 0; hitIndex < count; hitIndex += 1) {
      hits.push({ value, class_index: entry.class_index });
      if (hitIndex + 1 < count) value += modulus;
    }
  }
  let sortComparisons = 0;
  hits.sort((left, right) => {
    sortComparisons += 1;
    const comparison = order(left.value, right.value);
    return comparison || left.class_index - right.class_index;
  });
  const excluded = [];
  for (const hit of hits) {
    const value = hit.value.toString();
    const last = excluded[excluded.length - 1];
    if (last && last.value === value) last.class_indices.push(hit.class_index);
    else excluded.push({ value, class_indices: [hit.class_index] });
  }
  const requested = through - from + 1n;
  return {
    schema: "commons.residue_interval_compilation/v1",
    status: "COMPLETE",
    from: from.toString(),
    through: through.toString(),
    endpoints_inclusive: true,
    requested_count: requested.toString(),
    rule_count: options.rules.length,
    active_rule_count: activeRules,
    class_count: classes.length,
    congruence_hit_count: totalHits.toString(),
    excluded_count: String(excluded.length),
    allowed_count: (requested - BigInt(excluded.length)).toString(),
    multiple_class_excluded_count: excluded.filter(row => row.class_indices.length > 1).length,
    duplicate_hit_count: (totalHits - BigInt(excluded.length)).toString(),
    classes,
    excluded_records: excluded,
    numeric_order: true,
    coverage: "exact complement of the supplied finite forbidden congruence rules on the stated interval",
    pairwise_coprime_moduli_required: false,
    work: {
      from_modulus_reductions: activeRules,
      residue_alignment_reductions: classes.length,
      nonempty_progression_length_divisions: lengthDivisions,
      emitted_congruence_hits: hits.length,
      sort_comparisons: sortComparisons,
      max_emitted_hits: maxHits,
      interval_integers_scanned: "0",
      full_period_constructed: false
    }
  };
}

function lowerBound(values, target) {
  let low = 0;
  let high = values.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (values[middle] < target) low = middle + 1;
    else high = middle;
  }
  return low;
}

function upperBound(values, target) {
  let low = 0;
  let high = values.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (values[middle] <= target) low = middle + 1;
    else high = middle;
  }
  return low;
}

function createIntegerGapIndex(options) {
  if (!options || typeof options !== "object" || Array.isArray(options))
    fail("INVALID_OPTIONS", "options must be an object");
  const { from, through } = endpoints(options);
  if (!Array.isArray(options.excluded_values)
      || options.excluded_values.length > limits.max_excluded_values)
    fail("INVALID_EXCLUSIONS", "excluded_values must be an increasing array of at most " + limits.max_excluded_values + " integers");
  const excluded = options.excluded_values.map((value, index) => {
    const parsed = integer(value, "excluded value");
    if (parsed < from || parsed > through)
      fail("EXCLUSION_OUTSIDE_INTERVAL", "every excluded value must lie in the indexed interval");
    return parsed;
  });
  for (let i = 1; i < excluded.length; i += 1) {
    if (excluded[i] <= excluded[i - 1])
      fail("EXCLUSIONS_NOT_STRICTLY_INCREASING", "excluded values must be distinct and in numerical order");
  }
  const gapRecords = [];
  let next = from;
  let count = 0n;
  function addGap(first, last) {
    if (first > last) return;
    const length = last - first + 1n;
    gapRecords.push({ first, last, length, firstRank: count, endRank: count + length });
    count += length;
  }
  for (const value of excluded) {
    addGap(next, value - 1n);
    next = value + 1n;
  }
  addGap(next, through);
  const requested = through - from + 1n;
  if (count + BigInt(excluded.length) !== requested)
    fail("INTERNAL_PARTITION_ERROR", "gaps and excluded points did not partition the interval");

  function describe() {
    return {
      schema: "commons.integer_gap_index/v1",
      from: from.toString(),
      through: through.toString(),
      endpoints_inclusive: true,
      requested_count: requested.toString(),
      excluded_count: String(excluded.length),
      allowed_count: count.toString(),
      gap_count: gapRecords.length,
      numeric_order: true,
      zero_based_ranks: true,
      scope: "exact complement of the supplied increasing excluded-value list"
    };
  }

  function select(value) {
    const rank = integer(value, "rank", limits.max_rank_digits);
    if (rank < 0n || rank >= count)
      fail("RANK_OUT_OF_RANGE", "rank must lie from zero through allowed_count minus one");
    let low = 0;
    let high = gapRecords.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (gapRecords[middle].endRank <= rank) low = middle + 1;
      else high = middle;
    }
    const gap = gapRecords[low];
    return {
      schema: "commons.integer_gap_selection/v1",
      rank: rank.toString(),
      value: (gap.first + rank - gap.firstRank).toString(),
      gap_index: low,
      offset_in_gap: (rank - gap.firstRank).toString()
    };
  }

  function locate(value) {
    const target = integer(value, "value");
    if (target < from || target > through) {
      return {
        schema: "commons.integer_gap_location/v1",
        status: "OUTSIDE",
        value: target.toString(),
        allowed_values_below: target < from ? "0" : count.toString()
      };
    }
    const position = lowerBound(excluded, target);
    const below = target - from - BigInt(position);
    if (position < excluded.length && excluded[position] === target) {
      return {
        schema: "commons.integer_gap_location/v1",
        status: "EXCLUDED",
        value: target.toString(),
        excluded_index: position,
        allowed_values_below: below.toString()
      };
    }
    return {
      schema: "commons.integer_gap_location/v1",
      status: "INDEXED",
      value: target.toString(),
      rank: below.toString(),
      allowed_values_below: below.toString()
    };
  }

  function range(query) {
    if (!query || typeof query !== "object" || Array.isArray(query))
      fail("INVALID_QUERY", "range query must be an object");
    const requestedFrom = integer(query.from, "query.from");
    const requestedThrough = integer(query.through, "query.through");
    if (requestedFrom > requestedThrough)
      fail("REVERSED_INTERVAL", "query.from must be at most query.through");
    const first = requestedFrom > from ? requestedFrom : from;
    const last = requestedThrough < through ? requestedThrough : through;
    if (first > last) {
      return {
        schema: "commons.integer_gap_range/v1",
        requested_from: requestedFrom.toString(),
        requested_through: requestedThrough.toString(),
        clipped_interval: null,
        requested_count_in_index: "0",
        excluded_count: "0",
        allowed_count: "0"
      };
    }
    const rejected = upperBound(excluded, last) - lowerBound(excluded, first);
    const length = last - first + 1n;
    return {
      schema: "commons.integer_gap_range/v1",
      requested_from: requestedFrom.toString(),
      requested_through: requestedThrough.toString(),
      clipped_interval: { from: first.toString(), through: last.toString() },
      requested_count_in_index: length.toString(),
      excluded_count: String(rejected),
      allowed_count: (length - BigInt(rejected)).toString()
    };
  }

  function gaps(page = {}) {
    if (!page || typeof page !== "object" || Array.isArray(page))
      fail("INVALID_PAGE", "page must be an object");
    const start = page.start_index === undefined ? 0
      : bound(page.start_index, "start_index", 0, gapRecords.length);
    const pageLimit = page.limit === undefined ? limits.max_page
      : bound(page.limit, "limit", 1, limits.max_page);
    const end = Math.min(gapRecords.length, start + pageLimit);
    return {
      schema: "commons.integer_gap_page/v1",
      start_index: start,
      returned_gaps: end - start,
      total_gap_count: gapRecords.length,
      next_start_index: end < gapRecords.length ? end : null,
      gaps: gapRecords.slice(start, end).map((gap, index) => ({
        gap_index: start + index,
        from: gap.first.toString(),
        through: gap.last.toString(),
        allowed_count: gap.length.toString(),
        first_rank: gap.firstRank.toString(),
        last_rank: (gap.endRank - 1n).toString()
      }))
    };
  }

  return Object.freeze({ describe, select, locate, range, gaps });
}

module.exports = { compileResidueInterval, createIntegerGapIndex, limits };
