"use strict";

// Exact navigation of intersections of initial-digit alphabets.
// Concrete Erdős 376 input: base 3 digits <=1, base 5 <=2, base 7 <=3.
// Classical digit/carry attribution and prior computed ranges are in
// DIGIT_NAVIGATION_API.md. No infinitude or new external-frontier claim.

const NATURAL = /^(?:0|[1-9][0-9]*)(?![\s\S])/;
const LIMITS = Object.freeze({
  max_decimal_digits: 256,
  max_rules: 16,
  max_base: 36,
  max_calls_per_advance: 10000,
  default_saved_values: 4096,
  max_saved_values: 65536,
  default_saved_jumps: 64,
  max_saved_jumps: 4096
});
const DEFAULT_RULES = Object.freeze([
  Object.freeze({base: 3, max_digit: 1}),
  Object.freeze({base: 5, max_digit: 2}),
  Object.freeze({base: 7, max_digit: 3})
]);

function boundedInteger(value, label, minimum, maximum) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new RangeError(label + " must be an integer from " + minimum + " through " + maximum);
  }
  return value;
}

function natural(value, label) {
  let parsed;
  if (typeof value === "bigint") parsed = value;
  else if (typeof value === "number" && Number.isSafeInteger(value)) parsed = BigInt(value);
  else if (typeof value === "string" && value.length <= LIMITS.max_decimal_digits && NATURAL.test(value)) parsed = BigInt(value);
  else throw new TypeError(label + " must be a bigint, safe integer number, or canonical natural decimal string");
  if (parsed < 0n) throw new RangeError(label + " must be nonnegative");
  if (parsed.toString().length > LIMITS.max_decimal_digits) {
    throw new RangeError(label + " exceeds the decimal digit limit");
  }
  return parsed;
}

function checkedObject(value, label, allowed) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(label + " must be an object");
  }
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) throw new TypeError("unknown " + label + " field: " + key);
  }
  return value;
}

function parseRule(value, label) {
  checkedObject(value, label, ["base", "max_digit"]);
  const base = boundedInteger(value.base, label + ".base", 2, LIMITS.max_base);
  const maxDigit = boundedInteger(value.max_digit, label + ".max_digit", 0, base - 1);
  return Object.freeze({base, max_digit: maxDigit});
}

function copyRule(rule) {
  return {base: rule.base, max_digit: rule.max_digit};
}

// Least y >= value with every base-b digit in {0,...,cap}.
// Null occurs only for cap=0 and value>0.
function ceilingValue(value, rule) {
  const cap = rule.max_digit;
  if (cap === 0) return value === 0n ? 0n : null;
  if (cap === rule.base - 1) return value;
  const digits = Array.from(value.toString(rule.base), character => {
    const code = character.charCodeAt(0);
    return code <= 57 ? code - 48 : code - 87;
  });
  const bad = digits.findIndex(digit => digit > cap);
  if (bad === -1) return value;

  // A valid greater number must increase a digit before the first bad digit.
  // Increase the rightmost such digit that has room, then use a zero suffix.
  let position = bad - 1;
  while (position >= 0 && digits[position] === cap) position -= 1;
  let rounded;
  if (position < 0) {
    rounded = [1, ...Array(digits.length).fill(0)];
  } else {
    rounded = digits.slice(0, position);
    rounded.push(digits[position] + 1);
    rounded.push(...Array(digits.length - position - 1).fill(0));
  }
  const base = BigInt(rule.base);
  let next = 0n;
  for (const digit of rounded) next = next * base + BigInt(digit);
  return next;
}

/** Return the exact ceiling in one initial-digit alphabet, with a skip interval. */
function ceilingRestrictedDigits(value, ruleInput) {
  const input = natural(value, "value");
  const rule = parseRule(ruleInput, "rule");
  const next = ceilingValue(input, rule);
  return {
    schema: "erdos376.restricted_digit_ceiling/v1",
    value: input.toString(),
    rule: copyRule(rule),
    next_admissible: next === null ? null : next.toString(),
    input_digits_msd: input.toString(rule.base),
    output_digits_msd: next === null ? null : next.toString(rule.base),
    changed: next === null || next !== input,
    skipped_interval: next === input ? null : {
      from: input.toString(),
      through: next === null ? null : (next - 1n).toString()
    },
    no_admissible_at_or_above: next === null
  };
}

/**
 * Enumerate the exact intersection in inclusive [from,through].
 * advance(budget) bounds individual ceiling calls, not the interval's width.
 * A fresh factory can consume result.resume_options without revisiting the
 * covered prefix. It restarts checks on the first unprocessed candidate.
 */
function createDigitIntersectionSearch(options) {
  checkedObject(options, "search option", [
    "from", "through", "rules", "max_saved_values", "max_saved_jumps"
  ]);
  const lower = natural(options.from, "from");
  const upper = natural(options.through, "through");
  if (lower > upper) throw new RangeError("from must not exceed through");
  const suppliedRules = options.rules === undefined ? DEFAULT_RULES : options.rules;
  if (!Array.isArray(suppliedRules) || suppliedRules.length < 1 || suppliedRules.length > LIMITS.max_rules) {
    throw new RangeError("rules must contain from 1 through " + LIMITS.max_rules + " entries");
  }
  const rules = suppliedRules.map((rule, index) => parseRule(rule, "rules[" + index + "]"));
  const valueLimit = options.max_saved_values === undefined ? LIMITS.default_saved_values
    : boundedInteger(options.max_saved_values, "max_saved_values", 0, LIMITS.max_saved_values);
  const jumpLimit = options.max_saved_jumps === undefined ? LIMITS.default_saved_jumps
    : boundedInteger(options.max_saved_jumps, "max_saved_jumps", 0, LIMITS.max_saved_jumps);
  const requestedCount = upper - lower + 1n;
  const savedValues = [];
  const savedJumps = [];
  const callsByRule = Array(rules.length).fill(0n);
  const jumpsByRule = Array(rules.length).fill(0n);
  const excludedByRule = Array(rules.length).fill(0n);
  let candidate = lower;
  let ruleIndex = 0;
  let calls = 0n;
  let jumpCount = 0n;
  let excludedCount = 0n;
  let foundCount = 0n;
  let firstValue = null;
  let lastValue = null;
  let lastJump = null;
  let complete = false;
  let completionReason = null;

  function recordJump(from, through, next, index) {
    const mass = through - from + 1n;
    excludedCount += mass;
    excludedByRule[index] += mass;
    jumpCount += 1n;
    jumpsByRule[index] += 1n;
    const record = {
      from: from.toString(),
      through: through.toString(),
      rule_index: index,
      next_admissible: next === null ? null : next.toString()
    };
    lastJump = record;
    if (savedJumps.length < jumpLimit) savedJumps.push(record);
  }

  function finish(reason) {
    complete = true;
    completionReason = reason;
    if (excludedCount + foundCount !== requestedCount || candidate !== upper + 1n) {
      throw new Error("digit intersection interval accounting invariant failed");
    }
  }

  function describe() {
    const processed = excludedCount + foundCount;
    return {
      schema: "erdos376.digit_intersection_search/v1",
      status: complete ? "COMPLETE" : "IN_PROGRESS",
      from: lower.toString(),
      through: upper.toString(),
      rules: rules.map(copyRule),
      requested_count: requestedCount.toString(),
      processed_count: processed.toString(),
      excluded_count: excludedCount.toString(),
      found_count: foundCount.toString(),
      unprocessed_count: (requestedCount - processed).toString(),
      covered_through: processed === 0n ? null : (candidate - 1n).toString(),
      ceiling_calls: calls.toString(),
      calls_by_rule: callsByRule.map(value => value.toString()),
      jump_count: jumpCount.toString(),
      jumps_by_rule: jumpsByRule.map(value => value.toString()),
      excluded_by_rule: excludedByRule.map(value => value.toString()),
      first_value: firstValue,
      last_value: lastValue,
      values: savedValues.map(record => ({
        value: record.value,
        representations: record.representations.map(item => ({...item}))
      })),
      max_saved_values: valueLimit,
      values_truncated: BigInt(savedValues.length) !== foundCount,
      jump_intervals: savedJumps.map(record => ({...record})),
      last_jump: lastJump === null ? null : {...lastJump},
      max_saved_jumps: jumpLimit,
      jumps_truncated: BigInt(savedJumps.length) !== jumpCount,
      pending_rule_index: complete ? null : ruleIndex,
      resume_options: complete ? null : {
        from: candidate.toString(),
        through: upper.toString(),
        rules: rules.map(copyRule),
        max_saved_values: valueLimit,
        max_saved_jumps: jumpLimit
      },
      resume_rechecks_pending_candidate: !complete && ruleIndex !== 0,
      completion_reason: completionReason
    };
  }

  function advance(budget) {
    boundedInteger(budget, "ceiling-call budget", 1, LIMITS.max_calls_per_advance);
    let spent = 0;
    while (!complete && spent < budget) {
      const next = ceilingValue(candidate, rules[ruleIndex]);
      calls += 1n;
      callsByRule[ruleIndex] += 1n;
      spent += 1;
      if (next === null || next > upper) {
        recordJump(candidate, upper, next, ruleIndex);
        candidate = upper + 1n;
        ruleIndex = 0;
        finish("remaining_range_excluded_by_rule");
      } else if (next > candidate) {
        recordJump(candidate, next - 1n, next, ruleIndex);
        candidate = next;
        ruleIndex = 0;
      } else {
        ruleIndex += 1;
        if (ruleIndex === rules.length) {
          const value = candidate.toString();
          foundCount += 1n;
          if (firstValue === null) firstValue = value;
          lastValue = value;
          if (savedValues.length < valueLimit) {
            savedValues.push({
              value,
              representations: rules.map(rule => ({
                base: rule.base,
                max_digit: rule.max_digit,
                digits_msd: candidate.toString(rule.base)
              }))
            });
          }
          candidate += 1n;
          ruleIndex = 0;
          if (candidate > upper) finish("range_end_reached");
        }
      }
    }
    return describe();
  }

  return Object.freeze({advance, describe});
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    ceilingRestrictedDigits,
    createDigitIntersectionSearch,
    default_rules: DEFAULT_RULES,
    limits: LIMITS
  };
}
