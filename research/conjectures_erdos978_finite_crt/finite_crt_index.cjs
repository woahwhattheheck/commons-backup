"use strict";

// Erdős 978(iii): executable finite local filtering and CRT addressing.
// Local Hensel / mod-8 facts are credited to contribution 9a9241fd706f8b096cd34d40d7d6ba62d230f954361dd8d648e3fb21591f0d0b.
// Finite CRT composition follows Commons #16072. No infinite-tail claim.

const INTEGER = /^(?:0|-?[1-9][0-9]*)(?![\s\S])/;
const LIMITS = Object.freeze({
  max_prime: 1000000,
  max_interval_width: 4096,
  max_rules: 256,
  max_forbidden_per_rule: 4096,
  max_total_forbidden: 65536,
  default_root_checks: 1000000,
  max_root_checks: 5000000
});

function integer(value, label) {
  if (typeof value === "bigint") return value;
  if (typeof value === "number" && Number.isSafeInteger(value)) return BigInt(value);
  if (typeof value === "string" && INTEGER.test(value)) return BigInt(value);
  throw new TypeError(label + " must be a bigint, safe integer number, or canonical decimal integer string");
}

function mod(value, modulus) {
  const residue = value % modulus;
  return residue < 0n ? residue + modulus : residue;
}

function inverse(value, modulus) {
  let remainder = modulus;
  let nextRemainder = mod(value, modulus);
  let coefficient = 0n;
  let nextCoefficient = 1n;
  while (nextRemainder !== 0n) {
    const quotient = remainder / nextRemainder;
    [remainder, nextRemainder] = [nextRemainder, remainder - quotient * nextRemainder];
    [coefficient, nextCoefficient] = [nextCoefficient, coefficient - quotient * nextCoefficient];
  }
  if (remainder !== 1n) throw new RangeError("modular inverse requires coprime arguments");
  return mod(coefficient, modulus);
}

function isPrime(value) {
  if (value < 2) return false;
  if (value % 2 === 0) return value === 2;
  for (let divisor = 3; divisor * divisor <= value; divisor += 2) {
    if (value % divisor === 0) return false;
  }
  return true;
}

function boundedInteger(value, label, lower, upper) {
  if (!Number.isSafeInteger(value) || value < lower || value > upper) {
    throw new RangeError(label + " must be an integer from " + lower + " through " + upper);
  }
  return value;
}

/**
 * Compute all prime-square obstruction classes for n^4+2 in a bounded interval.
 * This scans roots modulo p and lifts them; it does not scan the p^2 residue space.
 */
function buildQuarticPrimeBlock(options) {
  if (options === null || typeof options !== "object" || Array.isArray(options)) {
    throw new TypeError("options must be an object");
  }
  const allowed = new Set(["min_exclusive", "max_inclusive", "max_root_checks"]);
  for (const key of Object.keys(options)) {
    if (!allowed.has(key)) throw new TypeError("unknown prime-block option: " + key);
  }
  const lower = boundedInteger(options.min_exclusive, "min_exclusive", 0, LIMITS.max_prime);
  const upper = boundedInteger(options.max_inclusive, "max_inclusive", lower, LIMITS.max_prime);
  if (upper - lower > LIMITS.max_interval_width) {
    throw new RangeError("prime interval exceeds max_interval_width");
  }
  const budget = options.max_root_checks === undefined
    ? LIMITS.default_root_checks
    : boundedInteger(options.max_root_checks, "max_root_checks", 0, LIMITS.max_root_checks);
  const primes = [];
  for (let candidate = Math.max(2, lower + 1); candidate <= upper; candidate += 1) {
    if (isPrime(candidate)) primes.push(candidate);
  }
  if (primes.length > LIMITS.max_rules) {
    throw new RangeError("prime block exceeds max_rules");
  }
  const required = primes.reduce((sum, p) =>
    sum + (p !== 2 && (p % 8 === 1 || p % 8 === 3) ? p : 0), 0);
  if (required > budget) {
    throw new RangeError("prime block requires " + required + " root checks; budget is " + budget);
  }

  const records = [];
  for (const p of primes) {
    const prime = BigInt(p);
    const modulus = prime * prime;
    const roots = [];
    const lifts = [];
    let method = "MOD8_NO_ROOTS";
    let rootChecks = 0;

    if (p === 2) {
      // The only root modulo 2 is 0; it does not lift to a root modulo 4.
      roots.push("0");
      method = "MOD4_NO_OBSTRUCTION";
    } else if (p % 8 === 1 || p % 8 === 3) {
      method = "ROOT_SCAN_AND_HENSEL_LIFT";
      rootChecks = p;
      for (let candidate = 0; candidate < p; candidate += 1) {
        // p <= 10^6 makes both modular squarings exact safe-integer operations.
        const square = (candidate * candidate) % p;
        if ((square * square + 2) % p !== 0) continue;
        const root = BigInt(candidate);
        const derivative = mod(4n * root * root * root, prime);
        const derivativeInverse = inverse(derivative, prime);
        const quotient = mod((root ** 4n + 2n) / prime, prime);
        const coefficient = mod(-quotient * derivativeInverse, prime);
        const residue = root + prime * coefficient;
        roots.push(root.toString());
        lifts.push({
          root_mod_p: root.toString(),
          quotient_mod_p: quotient.toString(),
          derivative_mod_p: derivative.toString(),
          derivative_inverse_mod_p: derivativeInverse.toString(),
          lift_coefficient: coefficient.toString(),
          residue_mod_p2: residue.toString()
        });
      }
    }
    const bad = lifts.map(lift => BigInt(lift.residue_mod_p2))
      .sort((left, right) => left < right ? -1 : left > right ? 1 : 0);
    records.push({
      p,
      p_mod_8: p % 8,
      modulus: modulus.toString(),
      method,
      root_checks: rootChecks,
      roots_mod_p: roots,
      bad_residues: bad.map(value => value.toString()),
      good_count: (modulus - BigInt(bad.length)).toString(),
      lifts
    });
  }
  return {
    schema: "erdos978.quartic_prime_block/v1",
    interval: {min_exclusive: lower, max_inclusive: upper},
    scope: "Only prime squares whose prime lies in the stated interval.",
    prime_count: records.length,
    active_prime_count: records.filter(record => record.bad_residues.length !== 0).length,
    bad_class_count: records.reduce((sum, record) => sum + record.bad_residues.length, 0),
    root_residue_checks: required,
    root_check_budget: budget,
    records
  };
}

function readRules(input) {
  if (!Array.isArray(input)) throw new TypeError("rules must be an array");
  if (input.length > LIMITS.max_rules) throw new RangeError("rules exceed max_rules");
  let totalForbidden = 0;
  return Array.from(input, (record, index) => {
    const label = "rules[" + index + "]";
    if (record === null || typeof record !== "object" || Array.isArray(record)) {
      throw new TypeError(label + " must be an object");
    }
    const modulus = integer(record.modulus, label + ".modulus");
    if (modulus < 2n) throw new RangeError(label + ".modulus must be at least 2");
    if (!Array.isArray(record.bad_residues)) {
      throw new TypeError(label + ".bad_residues must be an array");
    }
    if (record.bad_residues.length > LIMITS.max_forbidden_per_rule) {
      throw new RangeError(label + " exceeds max_forbidden_per_rule");
    }
    totalForbidden += record.bad_residues.length;
    if (totalForbidden > LIMITS.max_total_forbidden) {
      throw new RangeError("rules exceed max_total_forbidden");
    }
    const bad = Array.from(record.bad_residues, (value, residueIndex) => {
      const residue = integer(value, label + ".bad_residues[" + residueIndex + "]");
      if (residue < 0n || residue >= modulus) {
        throw new RangeError(label + " has a forbidden residue outside [0, modulus)");
      }
      return residue;
    }).sort((left, right) => left < right ? -1 : left > right ? 1 : 0);
    for (let i = 1; i < bad.length; i += 1) {
      if (bad[i] === bad[i - 1]) throw new RangeError(label + " has duplicate forbidden residues");
    }
    const goodCount = modulus - BigInt(bad.length);
    if (goodCount === 0n) throw new RangeError(label + " must leave an allowed residue");
    return {modulus, bad, goodCount};
  });
}

function selectLocal(digit, bad) {
  let residue = digit;
  for (const forbidden of bad) {
    if (forbidden > residue) break;
    residue += 1n;
  }
  return residue;
}

/**
 * Compile exact rank/select over pairwise coprime local forbidden-residue rules.
 * Input rule order is significant: the first rule is the least-significant digit.
 * The ordinal order is not the numerical order of the resulting CRT residues.
 */
function createFiniteCrtIndex(input) {
  const rules = readRules(input);
  let period = 1n;
  let count = 1n;
  for (const rule of rules) {
    period *= rule.modulus;
    count *= rule.goodCount;
  }
  const coefficients = rules.map((rule, index) => {
    const complement = period / rule.modulus;
    try {
      return complement * inverse(complement, rule.modulus);
    } catch (error) {
      if (error instanceof RangeError) {
        throw new RangeError("rule moduli must be pairwise coprime; failure at rule " + index);
      }
      throw error;
    }
  });

  function describe() {
    return {
      schema: "commons.finite_crt_index/v1",
      period: period.toString(),
      good_count: count.toString(),
      rule_count: rules.length,
      coordinate_order: "first_rule_least_significant",
      numeric_residue_order: false,
      local_good_counts: rules.map(rule => rule.goodCount.toString())
    };
  }

  function select(value) {
    const index = integer(value, "index");
    if (index < 0n || index >= count) {
      throw new RangeError("index must lie in [0, good_count)");
    }
    let remaining = index;
    let sum = 0n;
    const localResidues = [];
    for (let i = 0; i < rules.length; i += 1) {
      const rule = rules[i];
      const digit = remaining % rule.goodCount;
      remaining /= rule.goodCount;
      const residue = selectLocal(digit, rule.bad);
      localResidues.push(residue.toString());
      sum = mod(sum + residue * coefficients[i], period);
    }
    return {
      schema: "commons.finite_crt_selection/v1",
      index: index.toString(),
      residue: sum.toString(),
      period: period.toString(),
      local_residues: localResidues
    };
  }

  function locate(value) {
    const original = integer(value, "value");
    const residue = mod(original, period);
    let index = 0n;
    let place = 1n;
    for (let i = 0; i < rules.length; i += 1) {
      const rule = rules[i];
      const local = mod(residue, rule.modulus);
      let below = 0n;
      for (const forbidden of rule.bad) {
        if (forbidden === local) {
          return {
            schema: "commons.finite_crt_location/v1",
            status: "EXCLUDED",
            value: original.toString(),
            residue: residue.toString(),
            rule_index: i,
            modulus: rule.modulus.toString(),
            forbidden_residue: local.toString()
          };
        }
        if (forbidden > local) break;
        below += 1n;
      }
      index += (local - below) * place;
      place *= rule.goodCount;
    }
    return {
      schema: "commons.finite_crt_location/v1",
      status: "INDEXED",
      value: original.toString(),
      residue: residue.toString(),
      index: index.toString(),
      period: period.toString()
    };
  }

  return Object.freeze({describe, select, locate});
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {buildQuarticPrimeBlock, createFiniteCrtIndex, limits: LIMITS};
}
