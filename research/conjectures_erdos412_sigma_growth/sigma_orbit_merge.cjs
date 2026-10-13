"use strict";

/**
 * Exact finite sigma-orbit merge for the released Erdős 412 carrier.
 * Pure CommonJS / connected V8: no imports, native execution, network or I/O.
 * See SIGMA_ORBIT_MERGE_API.md for the accepted growth dependency and finite scope.
 */
const limits = Object.freeze({
  factor_input_max: "1000000000000",
  seed_decimal_digits: 256,
  max_transitions: 1024,
  default_max_transitions: 256,
  max_advance_transitions: 16,
  max_record_page: 256,
  remainder_tests_per_transition_upper_bound: 500040,
  quotient_divisions_per_transition_upper_bound: 39
});
const HARD_FACTOR_MAX = BigInt(limits.factor_input_max);

function fail(code, message) {
  const error = new Error(message);
  error.code = code;
  throw error;
}

function natural(value, name, maxDigits = limits.seed_decimal_digits) {
  let result;
  if (typeof value === "bigint") result = value;
  else if (typeof value === "number" && Number.isSafeInteger(value)) result = BigInt(value);
  else if (typeof value === "string" && /^(0|[1-9][0-9]*)$/.test(value)
      && value.length <= maxDigits) result = BigInt(value);
  else fail("INVALID_INTEGER", name + " must be a nonnegative BigInt, safe integer, or canonical decimal string");
  if (result < 0n || result.toString().length > maxDigits)
    fail("INTEGER_OUT_OF_RANGE", name + " is outside the supported natural-number range");
  return result;
}

function boundedNumber(value, name, minimum, maximum) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum)
    fail("INVALID_BOUND", name + " must be an integer from " + minimum + " through " + maximum);
  return value;
}

function copy(value) {
  return JSON.parse(JSON.stringify(value));
}

/**
 * Factor a positive input at most 10^12 by deterministic trial division.
 * Factor and quotient arithmetic stays within Number's exact integer range.
 * Prime powers, geometric sums, products and sigma use BigInt.
 */
function sigmaFactorization(value) {
  const original = natural(value, "value");
  if (original < 1n || original > HARD_FACTOR_MAX)
    fail("FACTOR_INPUT_OUT_OF_RANGE", "factor input must be from 1 through " + limits.factor_input_max);
  let remaining = Number(original);
  let divisor = 2;
  let remainderTests = 0;
  let quotientDivisions = 0;
  let trialCandidates = 0;
  let lastTestedDivisor = null;
  let factorProduct = 1n;
  let sigmaProduct = 1n;
  const factors = [];

  while (divisor * divisor <= remaining) {
    trialCandidates += 1;
    lastTestedDivisor = divisor;
    let exponent = 0;
    let primePower = 1n;
    let geometricSum = 1n;
    const prime = BigInt(divisor);
    for (;;) {
      remainderTests += 1;
      if (remaining % divisor !== 0) break;
      remaining /= divisor;
      quotientDivisions += 1;
      exponent += 1;
      primePower *= prime;
      geometricSum += primePower;
      if (remaining === 1) break;
    }
    if (exponent > 0) {
      factors.push({
        prime: prime.toString(),
        exponent,
        prime_power: primePower.toString(),
        geometric_sum: geometricSum.toString(),
        extraction: "trial_division"
      });
      factorProduct *= primePower;
      sigmaProduct *= geometricSum;
    }
    if (remaining === 1) break;
    divisor = divisor === 2 ? 3 : divisor + 2;
  }

  const terminalResidual = remaining;
  const terminalDivisor = divisor;
  if (remaining > 1) {
    const prime = BigInt(remaining);
    factors.push({
      prime: prime.toString(),
      exponent: 1,
      prime_power: prime.toString(),
      geometric_sum: (prime + 1n).toString(),
      extraction: "terminal_prime"
    });
    factorProduct *= prime;
    sigmaProduct *= prime + 1n;
  }
  if (factorProduct !== original)
    fail("INTERNAL_FACTORIZATION_ERROR", "factor product did not reconstruct the input");
  if (remainderTests > limits.remainder_tests_per_transition_upper_bound
      || quotientDivisions > limits.quotient_divisions_per_transition_upper_bound)
    fail("INTERNAL_WORK_BOUND_ERROR", "deterministic factorization work exceeded its declared bound");

  return {
    schema: "erdos412.sigma_factorization/v1",
    input: original.toString(),
    sigma: sigmaProduct.toString(),
    prime_powers: factors,
    factor_product: factorProduct.toString(),
    sigma_product: sigmaProduct.toString(),
    work: {
      remainder_tests: remainderTests,
      exact_quotient_divisions: quotientDivisions,
      trial_candidates: trialCandidates,
      last_tested_divisor: lastTestedDivisor === null ? null : String(lastTestedDivisor)
    },
    terminal: {
      reason: terminalResidual === 1 ? "residual_one" : "divisor_square_exceeds_residual",
      residual: String(terminalResidual),
      divisor: String(terminalDivisor),
      divisor_square: String(terminalDivisor * terminalDivisor),
      residual_is_appended_prime: terminalResidual > 1
    }
  };
}

function createSigmaOrbitMerge(options) {
  if (!options || typeof options !== "object" || Array.isArray(options))
    fail("INVALID_OPTIONS", "options must be an object");
  const leftSeed = natural(options.left, "left");
  const rightSeed = natural(options.right, "right");
  if (leftSeed < 2n || rightSeed < 2n)
    fail("SEED_OUT_OF_RANGE", "both orbit seeds must be at least 2");
  const factorLimit = options.factor_limit === undefined
    ? HARD_FACTOR_MAX : natural(options.factor_limit, "factor_limit");
  if (factorLimit < 2n || factorLimit > HARD_FACTOR_MAX)
    fail("INVALID_FACTOR_LIMIT", "factor_limit must be from 2 through " + limits.factor_input_max);
  const maxTransitions = options.max_transitions === undefined
    ? limits.default_max_transitions
    : boundedNumber(options.max_transitions, "max_transitions", 1, limits.max_transitions);
  let leftHead = leftSeed;
  let rightHead = rightSeed;
  let leftIndex = 0;
  let rightIndex = 0;
  let status = "IN_PROGRESS";
  let nextSide = null;
  let headOrderDecisions = 0;
  let remainderTests = 0;
  let quotientDivisions = 0;
  let trialCandidates = 0;
  let primePowerFactors = 0;
  const events = [];

  function settle() {
    headOrderDecisions += 1;
    if (leftHead === rightHead) {
      status = "MEETING";
      nextSide = null;
      return;
    }
    nextSide = leftHead < rightHead ? "left" : "right";
    const smaller = nextSide === "left" ? leftHead : rightHead;
    if (smaller > factorLimit) status = "FACTOR_LIMIT";
    else if (events.length >= maxTransitions) status = "TRANSITION_LIMIT";
    else status = "IN_PROGRESS";
  }

  function describe() {
    const larger = leftHead > rightHead ? leftHead : rightHead;
    const through = larger - 1n;
    const nextValue = nextSide === "left" ? leftHead : rightHead;
    return {
      schema: "erdos412.sigma_orbit_merge/v1",
      status,
      seeds: { left: leftSeed.toString(), right: rightSeed.toString() },
      heads: {
        left: { index: leftIndex, value: leftHead.toString() },
        right: { index: rightIndex, value: rightHead.toString() }
      },
      factor_limit: factorLimit.toString(),
      max_transitions: maxTransitions,
      completed_transitions: events.length,
      remaining_transition_capacity: maxTransitions - events.length,
      retained_transition_records: events.length,
      meeting: status === "MEETING" ? {
        value: leftHead.toString(),
        left_index: leftIndex,
        right_index: rightIndex,
        least_common_value: true
      } : null,
      bounded_nonintersection: {
        from: "0",
        through: through.toString(),
        endpoints_inclusive: true,
        basis: "accepted strict growth and the retained smaller-head merge decisions"
      },
      no_common_value_at_most_factor_limit: through >= factorLimit
        ? true : (status === "MEETING" ? false : null),
      next_required_transition: nextSide === null ? null : {
        side: nextSide,
        input_index: nextSide === "left" ? leftIndex : rightIndex,
        value: nextValue.toString(),
        within_factor_limit: nextValue <= factorLimit,
        within_hard_factor_cap: nextValue <= HARD_FACTOR_MAX
      },
      continuation: nextSide === null ? null : {
        tail_options: {
          left: leftHead.toString(),
          right: rightHead.toString(),
          factor_limit: factorLimit.toString(),
          max_transitions: maxTransitions
        },
        index_offsets: { left: leftIndex, right: rightIndex },
        semantics: "starts the two unprocessed tails with new local indices; compose with the retained offsets and prefix records",
        current_factor_limit_permits_transition: nextValue <= factorLimit,
        hard_factor_cap_permits_transition: nextValue <= HARD_FACTOR_MAX
      },
      work: {
        factorizations: events.length,
        head_order_decisions: headOrderDecisions,
        remainder_tests: remainderTests,
        exact_quotient_divisions: quotientDivisions,
        trial_candidates: trialCandidates,
        retained_prime_power_factors: primePowerFactors,
        total_remainder_tests_upper_bound:
          maxTransitions * limits.remainder_tests_per_transition_upper_bound,
        total_quotient_divisions_upper_bound:
          maxTransitions * limits.quotient_divisions_per_transition_upper_bound
      },
      evidence: {
        completed_prefix_records_retained_in_full: true,
        no_factorization_of_unprocessed_heads: true,
        infinite_nonintersection_claim: false
      }
    };
  }

  function advance(transitionBudget = limits.max_advance_transitions) {
    boundedNumber(transitionBudget, "transitionBudget", 1, limits.max_advance_transitions);
    let advanced = 0;
    while (status === "IN_PROGRESS" && advanced < transitionBudget) {
      const side = nextSide;
      const input = side === "left" ? leftHead : rightHead;
      const inputIndex = side === "left" ? leftIndex : rightIndex;
      const otherHead = side === "left" ? rightHead : leftHead;
      const otherIndex = side === "left" ? rightIndex : leftIndex;
      const factorization = sigmaFactorization(input);
      const output = BigInt(factorization.sigma);
      if (!(input < otherHead && output > input))
        fail("INTERNAL_ORBIT_ORDER_ERROR", "a new transition violated the merge contract");
      const event = {
        schema: "erdos412.sigma_orbit_transition/v1",
        event_index: events.length,
        side,
        input_index: inputIndex,
        output_index: inputIndex + 1,
        input: input.toString(),
        output: output.toString(),
        other_head: { index: otherIndex, value: otherHead.toString() },
        advanced_smaller_head: true,
        factorization
      };
      events.push(event);
      if (side === "left") {
        leftHead = output;
        leftIndex += 1;
      } else {
        rightHead = output;
        rightIndex += 1;
      }
      remainderTests += factorization.work.remainder_tests;
      quotientDivisions += factorization.work.exact_quotient_divisions;
      trialCandidates += factorization.work.trial_candidates;
      primePowerFactors += factorization.prime_powers.length;
      advanced += 1;
      settle();
    }
    return describe();
  }

  function records(page = {}) {
    if (!page || typeof page !== "object" || Array.isArray(page))
      fail("INVALID_PAGE", "page must be an object");
    const start = page.start_index === undefined ? 0
      : boundedNumber(page.start_index, "start_index", 0, events.length);
    const limit = page.limit === undefined ? limits.max_record_page
      : boundedNumber(page.limit, "limit", 1, limits.max_record_page);
    const end = Math.min(events.length, start + limit);
    return {
      schema: "erdos412.sigma_orbit_transition_page/v1",
      status,
      start_index: start,
      returned_records: end - start,
      processed_record_count: events.length,
      next_start_index: end < events.length ? end : null,
      record_scope: "completed transitions currently retained by this handle",
      records: copy(events.slice(start, end))
    };
  }

  settle();
  return Object.freeze({ describe, advance, records });
}

module.exports = { sigmaFactorization, createSigmaOrbitMerge, limits };
