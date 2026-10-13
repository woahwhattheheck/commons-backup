"use strict";

// Fixed fresh E366 interval. Arithmetic is exact BigInt; JSON values are strings.
// Prime completeness is a precondition supplied by the banked accepted prefix.
// This module performs no sieve, primality proof, filesystem, network or CLI work.
const ENGINE = "erdos366-range-shards-v1";
const LOWER = 1000000000000n;
const UPPER = 2000000000000n;
const SHARDS = 4;
const CAPS = Object.freeze({
  upper: "2000000000000",
  candidates: 100000,
  coefficient_pairs: 10000,
  trial_steps: 10000000,
  trial_steps_per_shard: 2500000,
});
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);

class RangeWorkError extends Error {
  constructor(message, phase, partial, cause) {
    super(message);
    this.name = "RangeWorkError";
    this.phase = phase;
    this.partial = partial;
    if (cause !== undefined) this.cause = cause;
  }
}

function jsonCopy(value) {
  return JSON.parse(JSON.stringify(value, (_, item) =>
    typeof item === "bigint" ? item.toString() : item));
}

function decimal(value, label) {
  if (typeof value !== "string" || value.length > 32 ||
      !/^(0|[1-9][0-9]*)$/.test(value)) {
    throw new TypeError(label + " must be a canonical nonnegative decimal string");
  }
  return BigInt(value);
}

function count(value, label, maximum) {
  if (!Number.isSafeInteger(value) || value < 0 || value > maximum) {
    throw new RangeError(label + " is outside its declared integer bound");
  }
  return value;
}

function increment(work, key, amount = 1, maximum = Number.MAX_SAFE_INTEGER) {
  if (!Number.isSafeInteger(amount) || amount < 0 ||
      work[key] > maximum - amount) {
    const error = new RangeError(key + " cap would be exceeded");
    error.limit = {counter: key, current: work[key], attempted_increment: amount, maximum};
    throw error;
  }
  work[key] += amount;
}

function rootFloor(n, degree, work) {
  increment(work, "integer_root_calls");
  if (n < 0n) throw new RangeError("integer root input must be nonnegative");
  if (n < 2n) return n;
  const k = BigInt(degree);
  let low = 0n;
  let high = 1n;
  for (;;) {
    increment(work, "integer_root_power_comparisons");
    if (high ** k > n) break;
    high *= 2n;
    increment(work, "integer_root_doublings");
  }
  while (low + 1n < high) {
    const middle = (low + high) / 2n;
    increment(work, "integer_root_bisections");
    increment(work, "integer_root_power_comparisons");
    if (middle ** k <= n) low = middle;
    else high = middle;
  }
  return low;
}

function squareRootFloor(n, work) {
  increment(work, "square_root_calls");
  if (n < 0n) throw new RangeError("square root input must be nonnegative");
  if (n < 2n) return n;
  let x = n;
  let y = (x + 1n) / 2n;
  while (y < x) {
    x = y;
    y = (x + n / x) / 2n;
    increment(work, "square_root_iterations");
    increment(work, "square_root_divisions");
  }
  return x;
}

function coprimeFactors(left, right, work) {
  let i = 0;
  let j = 0;
  while (i < left.length && j < right.length) {
    increment(work, "coprime_factor_comparisons");
    if (left[i] === right[j]) return false;
    if (left[i] < right[j]) i++;
    else j++;
  }
  return true;
}

/**
 * Required input:
 * {lower_exclusive:"1000000000000", upper_inclusive:"2000000000000",
 *  shards:4, primes:[1900 ascending safe integers, first2,last16381],
 *  prime_source?: bounded JSON object describing the accepted literal prefix}.
 * Count/endpoints/order checks do NOT re-prove primality or completeness.
 * Build once; bank this exact JSON plan, then pass its unchanged data to shards.
 */
function buildRangePlan(input) {
  const work = {
    prime_prefix_entries_checked: 0,
    prime_cube_multiplications: 0,
    integer_root_calls: 0,
    integer_root_power_comparisons: 0,
    integer_root_doublings: 0,
    integer_root_bisections: 0,
    squarefree_product_trials: 0,
    squarefree_values_created: 0,
    squarefree_power_multiplications: 0,
    coefficient_products: 0,
    coefficient_pairs: 0,
    coprime_factor_comparisons: 0,
    coprime_pairs: 0,
    coefficient_bound_divisions: 0,
    coefficients_retained: 0,
    empty_coefficients: 0,
    candidate_values_reserved: 0,
  };
  let phase = "validate_input";
  const partial = {engine: ENGINE, status: "incomplete", phase, work,
    prime_cubes: [], squarefree: [], coefficients: [], shard_summaries: [], active: null};
  try {
    if (!object(input)) throw new TypeError("input must be an object");
    const allowed = new Set(["lower_exclusive", "upper_inclusive", "shards", "primes", "prime_source"]);
    if (Object.keys(input).some(key => !allowed.has(key))) throw new TypeError("unsupported input field");
    if (decimal(input.lower_exclusive, "lower_exclusive") !== LOWER ||
        decimal(input.upper_inclusive, "upper_inclusive") !== UPPER ||
        input.shards !== SHARDS) {
      throw new RangeError("this engine supports only its fixed declared interval and four shards");
    }
    if (!Array.isArray(input.primes) || input.primes.length !== 1900) {
      throw new TypeError("primes must be the complete accepted 1900-entry prefix");
    }
    const primes = [];
    let previous = 1;
    for (const p of input.primes) {
      if (!Number.isSafeInteger(p) || p <= previous || p > 16381) {
        throw new TypeError("prime prefix must contain increasing safe integers through16381");
      }
      primes.push(p);
      previous = p;
      increment(work, "prime_prefix_entries_checked");
    }
    if (primes[0] !== 2 || primes[1899] !== 16381) {
      throw new TypeError("prime prefix endpoints must be2 and16381");
    }
    let primeSource = null;
    if (own(input, "prime_source")) {
      if (!object(input.prime_source)) throw new TypeError("prime_source must be a JSON object");
      const encoded = JSON.stringify(input.prime_source);
      if (typeof encoded !== "string" || encoded.length > 4096) {
        throw new RangeError("prime_source exceeds4096 JSON characters");
      }
      primeSource = JSON.parse(encoded);
    }

    phase = "prime_cubes";
    const primeCubes = partial.prime_cubes;
    for (const p of primes) {
      const value = BigInt(p);
      const cube = value * value * value;
      increment(work, "prime_cube_multiplications", 2);
      primeCubes.push({prime: String(p), cube: cube.toString()});
    }
    if (BigInt(primeCubes[primeCubes.length - 1].cube) <= UPPER) {
      throw new RangeError("prime prefix does not reach the tail stopping boundary");
    }

    phase = "squarefree_plan";
    const bLimit = rootFloor(UPPER, 4, work);
    const cLimit = rootFloor(UPPER, 5, work);
    const small = primes.filter(p => BigInt(p) <= bLimit);
    const squarefree = partial.squarefree;
    squarefree.push({value: 1n, factors: []});
    increment(work, "squarefree_values_created");
    function visit(start, current, factors) {
      for (let i = start; i < small.length; i++) {
        const next = current * BigInt(small[i]);
        increment(work, "squarefree_product_trials");
        if (next > bLimit) break;
        const nextFactors = factors.concat(small[i]);
        squarefree.push({value: next, factors: nextFactors});
        increment(work, "squarefree_values_created");
        visit(i + 1, next, nextFactors);
      }
    }
    visit(0, 1n, []);
    squarefree.sort((a, b) => a.value < b.value ? -1 : a.value > b.value ? 1 : 0);
    for (const row of squarefree) {
      const square = row.value * row.value;
      row.fourth = square * square;
      row.fifth = row.fourth * row.value;
      increment(work, "squarefree_power_multiplications", 3);
    }

    phase = "coefficient_plan";
    const coefficients = partial.coefficients;
    const shardSummaries = Array.from({length: SHARDS}, (_, index) => ({
      index, coefficient_count: 0, empty_coefficient_count: 0,
      candidate_count: 0, trial_step_cap: CAPS.trial_steps_per_shard,
    }));
    partial.shard_summaries = shardSummaries;
    for (const c of squarefree) {
      if (c.value > cLimit) break;
      for (const b of squarefree) {
        const q = b.fourth * c.fifth;
        increment(work, "coefficient_products");
        if (q > UPPER) break;
        partial.active = {b: b.value, c: c.value, q, stage: "coefficient_pair"};
        // Count each q<=U pair before its coprimality test.
        increment(work, "coefficient_pairs", 1, CAPS.coefficient_pairs);
        if (!coprimeFactors(b.factors, c.factors, work)) continue;
        increment(work, "coprime_pairs");
        const first = rootFloor(LOWER / q, 3, work) + 1n;
        const last = rootFloor(UPPER / q, 3, work);
        increment(work, "coefficient_bound_divisions", 2);
        const candidateCount = last < first ? 0 : Number(last - first + 1n);
        partial.active = {b: b.value, c: c.value, q, a_min: first, a_max: last,
          candidate_count: candidateCount, stage: "reserve_candidates"};
        count(candidateCount, "coefficient candidate count", CAPS.candidates);
        increment(work, "candidate_values_reserved", candidateCount, CAPS.candidates);
        const ordinal = coefficients.length;
        const shard = ordinal % SHARDS;
        coefficients.push({
          ordinal, shard, b: b.value.toString(), c: c.value.toString(), q: q.toString(),
          b_prime_factors: b.factors.map(String),
          c_prime_factors: c.factors.map(String),
          a_min: first.toString(), a_max: last.toString(), candidate_count: candidateCount,
        });
        increment(work, "coefficients_retained");
        shardSummaries[shard].coefficient_count++;
        shardSummaries[shard].candidate_count += candidateCount;
        if (candidateCount === 0) {
          increment(work, "empty_coefficients");
          shardSummaries[shard].empty_coefficient_count++;
        }
      }
    }
    return {
      schema: "commons.erdos366.range_plan/v1", engine: ENGINE,
      lower_exclusive: LOWER.toString(), upper_inclusive: UPPER.toString(),
      shards: SHARDS, caps: {...CAPS},
      canonical_form: "m=a^3*b^4*c^5; b,c squarefree; gcd(b,c)=1; a>=1",
      coefficient_order: "c ascending, then b ascending; ordinal starts0",
      shard_assignment: "coefficient ordinal modulo4",
      a_order: "ascending within each coefficient",
      prime_completeness: "caller-supplied accepted complete1900-prime prefix; not re-proved",
      prime_source: primeSource,
      prime_cubes: primeCubes,
      squarefree_limit: bLimit.toString(), c_limit: cLimit.toString(),
      squarefree: squarefree.map(row => ({
        value: row.value.toString(), prime_factors: row.factors.map(String),
        fourth_power: row.fourth.toString(), fifth_power: row.fifth.toString(),
      })),
      coefficients, shard_summaries: shardSummaries,
      candidate_count: work.candidate_values_reserved,
      plan_work: work,
      plan_integrity: "Use this unchanged banked buildRangePlan output. Structural shard checks do not authenticate or reconstruct it.",
      interpretation: "Only L<m<=U is emitted or predecessor-tested. No global nonexistence or literature-bound claim.",
    };
  } catch (error) {
    partial.phase = phase;
    if (error && error.limit) partial.blocked_limit = error.limit;
    throw new RangeWorkError(String(error && error.message || error), phase, jsonCopy(partial), error);
  }
}

function assessPredecessor(n, primeCubes, work, active) {
  let remaining = n;
  const removed = [];
  active.remaining = remaining;
  active.removed_prime_powers = removed;
  for (let index = 0; index < primeCubes.length; index++) {
    const {prime: p, cube} = primeCubes[index];
    active.next_prime_index = index;
    active.next_prime = p;
    active.remaining = remaining;
    increment(work, "prime_visits");
    if (cube > remaining) {
      increment(work, "tail_stops");
      const root = squareRootFloor(remaining, work);
      const square = root * root === remaining;
      increment(work, "square_tests");
      if (square) increment(work, "square_tails");
      else increment(work, "nonsquare_tails");
      return {
        is_2_full: square,
        certificate: {
          type: square ? "square_tail" : "nonsquare_tail",
          removed_prime_powers: removed,
          residual: remaining.toString(),
          ...(square ? {square_tail_root: root.toString()} : {}),
          tested_prime_prefix_count: index,
          next_prime: p.toString(), next_prime_cube: cube.toString(),
          scope: square ? "square tail; root factorization not claimed"
            : "residual>1 nonsquare below next-prime cube; smaller primes exhausted",
        },
      };
    }
    increment(work, "trial_steps", 1, CAPS.trial_steps_per_shard);
    let residue = remaining % p;
    if (residue !== 0n) continue;
    let exponent = 0;
    while (residue === 0n) {
      remaining /= p;
      exponent++;
      increment(work, "factor_divisions");
      active.remaining = remaining;
      active.current_prime_exponent = exponent;
      if (remaining === 1n) break;
      increment(work, "trial_steps", 1, CAPS.trial_steps_per_shard);
      residue = remaining % p;
    }
    removed.push({prime: p.toString(), exponent});
    active.current_prime_exponent = 0;
    if (exponent === 1) {
      increment(work, "exponent_one_rejections");
      return {
        is_2_full: false,
        certificate: {
          type: "prime_exponent_one", removed_prime_powers: removed,
          rejecting_prime: p.toString(), rejecting_exponent: 1,
          residual: remaining.toString(), tested_prime_prefix_count: index + 1,
        },
      };
    }
  }
  throw new RangeError("banked prime plan ended before an exact tail decision");
}

/**
 * Run one shard of the unchanged saved plan. No roots/powers/coefficient plan
 * are rebuilt. Prime cubes are parsed, not recomputed. The caller banks and
 * matches the plan identity; structural checks are not a substitute.
 * Optional record(row) must be synchronous. A failure retains the already
 * appended record plus partial work; there is no automatic resume or retry.
 */
function runRangeShard(plan, index, record) {
  const work = {
    coefficient_ranges_started: 0, coefficient_ranges_completed: 0,
    candidate_started: 0, candidate_completed: 0,
    candidate_product_multiplications: 0,
    prime_visits: 0, trial_steps: 0, factor_divisions: 0,
    tail_stops: 0, square_tests: 0, square_tails: 0, nonsquare_tails: 0,
    exponent_one_rejections: 0, witnesses: 0,
    square_root_calls: 0, square_root_iterations: 0, square_root_divisions: 0,
    record_callback_calls: 0, record_callback_returns: 0,
  };
  let phase = "validate_banked_plan";
  const partial = {engine: ENGINE, status: "incomplete", shard_index: index, phase, work,
    coefficient_ranges: [], records: [], active: null};
  try {
    if (!object(plan) || plan.schema !== "commons.erdos366.range_plan/v1" ||
        plan.engine !== ENGINE || plan.lower_exclusive !== LOWER.toString() ||
        plan.upper_inclusive !== UPPER.toString() || plan.shards !== SHARDS) {
      throw new TypeError("plan must be this engine's unchanged banked fixed-range plan");
    }
    count(index, "shard index", SHARDS - 1);
    if (record !== undefined && typeof record !== "function") {
      throw new TypeError("record must be a synchronous function");
    }
    count(plan.candidate_count, "plan candidate count", CAPS.candidates);
    if (!Array.isArray(plan.prime_cubes) || plan.prime_cubes.length !== 1900 ||
        !Array.isArray(plan.coefficients) || plan.coefficients.length > CAPS.coefficient_pairs ||
        !Array.isArray(plan.shard_summaries) || plan.shard_summaries.length !== SHARDS) {
      throw new TypeError("banked plan tables have unsupported sizes");
    }
    const primeCubes = plan.prime_cubes.map(row => {
      if (!object(row)) throw new TypeError("prime cube row must be an object");
      return {prime: decimal(row.prime, "prime"), cube: decimal(row.cube, "prime cube")};
    });
    const summary = plan.shard_summaries[index];
    if (!object(summary) || summary.index !== index ||
        summary.trial_step_cap !== CAPS.trial_steps_per_shard) {
      throw new TypeError("shard summary does not match its fixed budget");
    }
    const candidateCap = count(summary.candidate_count, "shard candidate count", CAPS.candidates);
    const selected = [];
    for (let ordinal = 0; ordinal < plan.coefficients.length; ordinal++) {
      const row = plan.coefficients[ordinal];
      if (!object(row) || row.ordinal !== ordinal || row.shard !== ordinal % SHARDS) {
        throw new TypeError("banked coefficient order or shard assignment differs");
      }
      if (row.shard !== index) continue;
      const parsed = {
        ordinal, q: decimal(row.q, "coefficient q"),
        first: decimal(row.a_min, "a_min"), last: decimal(row.a_max, "a_max"),
        candidate_count: count(row.candidate_count, "coefficient candidate count", CAPS.candidates),
      };
      if (parsed.q < 1n || parsed.q > UPPER || parsed.first < 1n) {
        throw new RangeError("banked coefficient bounds are invalid");
      }
      selected.push(parsed);
      partial.coefficient_ranges.push({
        coefficient_ordinal: ordinal, a_min: row.a_min, a_max: row.a_max,
        planned_count: row.candidate_count, started: 0, completed: 0, status: "pending",
      });
    }
    if (selected.length !== summary.coefficient_count) {
      throw new TypeError("banked shard coefficient count differs");
    }
    phase = "run_shard";
    for (let position = 0; position < selected.length; position++) {
      const coefficient = selected[position];
      const range = partial.coefficient_ranges[position];
      range.status = "running";
      increment(work, "coefficient_ranges_started");
      for (let a = coefficient.first; a <= coefficient.last; a++) {
        partial.active = {coefficient_ordinal: coefficient.ordinal, a,
          stage: "check_candidate_caps"};
        if (range.started >= coefficient.candidate_count) {
          const error = new RangeError("banked coefficient candidate count would be exceeded");
          error.limit = {counter: "coefficient_candidates", current: range.started,
            attempted_increment: 1, maximum: coefficient.candidate_count};
          throw error;
        }
        increment(work, "candidate_started", 1, candidateCap);
        range.started++;
        const m = a * a * a * coefficient.q;
        increment(work, "candidate_product_multiplications", 3);
        partial.active.m = m;
        partial.active.stage = "check_fresh_interval";
        if (m <= LOWER || m > UPPER) {
          throw new RangeError("candidate lies outside the fresh interval");
        }
        partial.active.stage = "predecessor";
        const predecessor = assessPredecessor(m - 1n, primeCubes, work, partial.active);
        const row = {coefficient_ordinal: coefficient.ordinal,
          a: a.toString(), m: m.toString(), predecessor};
        partial.records.push(row);
        increment(work, "candidate_completed");
        range.completed++;
        if (predecessor.is_2_full) increment(work, "witnesses");
        partial.active.stage = "record_callback";
        if (record) {
          increment(work, "record_callback_calls");
          const returned = record(jsonCopy(row));
          if (returned && typeof returned.then === "function") {
            throw new TypeError("record callback returned a thenable; synchronous callback required");
          }
          increment(work, "record_callback_returns");
        }
        partial.active = null;
      }
      if (range.completed !== coefficient.candidate_count) {
        throw new RangeError("banked coefficient candidate count was not reached");
      }
      range.status = "complete";
      increment(work, "coefficient_ranges_completed");
    }
    if (work.candidate_completed !== candidateCap) {
      throw new RangeError("banked shard candidate count was not reached");
    }
    return {
      schema: "commons.erdos366.range_shard/v1", engine: ENGINE, status: "complete",
      shard_index: index, lower_exclusive: LOWER.toString(), upper_inclusive: UPPER.toString(),
      trial_step_cap: CAPS.trial_steps_per_shard,
      combined_four_shard_trial_step_cap: CAPS.trial_steps,
      coefficient_ranges: partial.coefficient_ranges, records: partial.records, work,
      certificate_binding: "coefficient_ordinal refers to the unchanged banked plan's a^3*b^4*c^5 data; no duplicated b/c factors",
      prime_completeness: plan.prime_completeness,
      interpretation: "This fresh interval and shard only. No old predecessor was tested; no global nonexistence claim.",
    };
  } catch (error) {
    partial.phase = phase;
    if (error && error.limit) partial.blocked_limit = error.limit;
    throw new RangeWorkError(String(error && error.message || error), phase, jsonCopy(partial), error);
  }
}

module.exports = {buildRangePlan, runRangeShard, RangeWorkError};
