"use strict";

/**
 * Complete labelled binary-DFA separation catalogues for compressed words.
 * See RLE_DFA_SEPARATOR_API.md for conventions, proof, source attribution,
 * and the distinction between separate and common accepting-state choices.
 */
const DFA_SEPARATOR_LIMITS = Object.freeze({
  max_states: 4,
  max_raw_runs_per_word: 32,
  max_exponent_digits: 256,
  max_source_id_code_units: 512,
  max_page: 128
});
const SCHEMA = "commons.rle_dfa_separator_index/v1";
const CODE_ORDER = "zero_code + states^states * one_code; each unary code uses base-states digits in state order";
const ENDPOINT_ENCODING = "two lowercase hex characters per transition code; byte=a+q*b+q^2*a_reverse+q^3*b_reverse";
const ORIENTATIONS = Object.freeze(["forward", "reverse", "joint"]);

function integer(value, lo, hi, name) {
  if (!Number.isSafeInteger(value) || value < lo || value > hi) {
    throw new RangeError(name + " must be a safe integer in [" + lo + "," + hi + "]");
  }
  return value;
}

function array(value, lo, hi, name) {
  if (!Array.isArray(value) || value.length < lo || value.length > hi) {
    throw new RangeError(name + " has an invalid array length");
  }
  return value;
}

function sourceId(value, name) {
  if (typeof value !== "string" || value.length === 0 ||
      value.length > DFA_SEPARATOR_LIMITS.max_source_id_code_units) {
    throw new TypeError(name + " must be a nonempty bounded string");
  }
  return value;
}

function exponent(value, name, strict) {
  let text;
  if (!strict && typeof value === "bigint" && value >= 0n) text = value.toString();
  else if (!strict && typeof value === "number" && Number.isSafeInteger(value) && value >= 0) text = String(value);
  else if (typeof value === "string" && /^(?:0|[1-9][0-9]*)$/.test(value)) text = value;
  else throw new TypeError(name + " must be a canonical nonnegative integer");
  if (text.length > DFA_SEPARATOR_LIMITS.max_exponent_digits) throw new RangeError(name + " exceeds digit cap");
  return BigInt(text);
}

function normalizeRuns(value, name, strict = false) {
  array(value, 0, DFA_SEPARATOR_LIMITS.max_raw_runs_per_word, name);
  const result = [];
  for (const run of value) {
    array(run, 2, 2, name + " run");
    const symbol = integer(run[0], 0, 1, "run symbol");
    const count = exponent(run[1], "run exponent", strict);
    if (strict && count === 0n) throw new TypeError("retained runs must be positive");
    if (count === 0n) continue;
    if (result.length && result[result.length - 1][0] === symbol) {
      if (strict) throw new TypeError("retained adjacent runs must use different symbols");
      const sum = BigInt(result[result.length - 1][1]) + count;
      if (sum.toString().length > DFA_SEPARATOR_LIMITS.max_exponent_digits) {
        throw new RangeError("merged run exponent exceeds digit cap");
      }
      result[result.length - 1][1] = sum.toString();
    } else {
      result.push([symbol, count.toString()]);
    }
  }
  return result;
}

function wordLength(runs) {
  return runs.reduce((sum, run) => sum + BigInt(run[1]), 0n).toString();
}

function exponentList(a, b) {
  return [...new Set(a.concat(b).map((run) => run[1]))].sort((x, y) =>
    x.length - y.length || (x < y ? -1 : x > y ? 1 : 0));
}

function decodeFunction(code, states) {
  const result = [];
  let remaining = code;
  for (let i = 0; i < states; i++) {
    result.push(remaining % states);
    remaining = Math.floor(remaining / states);
  }
  return result;
}

function orbitOf(map, start, work) {
  const first = new Array(map.length).fill(-1);
  const path = [];
  let state = start;
  while (first[state] === -1) {
    first[state] = path.length;
    path.push(state);
    state = map[state];
    work.unary_orbit_steps++;
  }
  const preperiod = first[state];
  work.unary_orbits++;
  return [path, preperiod, path.length - preperiod];
}

function powerFromOrbit(orbit, count, work) {
  const [path, preperiod, period] = orbit;
  work.power_targets++;
  if (count < BigInt(path.length)) return path[Number(count)];
  work.power_reductions++;
  return path[preperiod + Number((count - BigInt(preperiod)) % BigInt(period))];
}

function unpackEndpoints(byte, states) {
  const ends = [];
  let remaining = byte;
  for (let i = 0; i < 4; i++) {
    ends.push(remaining % states);
    remaining = Math.floor(remaining / states);
  }
  return ends;
}

function bitCount(mask) {
  let count = 0;
  for (let value = mask; value; value &= value - 1) count++;
  return count;
}

function constraints(ends, states, orientation) {
  let required;
  let forbidden;
  if (orientation === "forward") {
    required = 1 << ends[0];
    forbidden = 1 << ends[1];
  } else if (orientation === "reverse") {
    required = 1 << ends[2];
    forbidden = 1 << ends[3];
  } else {
    required = (1 << ends[0]) | (1 << ends[2]);
    forbidden = (1 << ends[1]) | (1 << ends[3]);
  }
  const conflict = (required & forbidden) !== 0;
  const freeMask = ((1 << states) - 1) & ~(required | forbidden);
  return { required_mask: required, forbidden_mask: forbidden, free_mask: freeMask,
    choices: conflict ? 0 : 1 << bitCount(freeMask) };
}

function emptyProfile() {
  return {
    transition_tables: 0,
    forward_distinguishing_tables: 0,
    reverse_distinguishing_tables: 0,
    both_distinguishing_tables: 0,
    forward_only_tables: 0,
    reverse_only_tables: 0,
    neither_tables: 0,
    joint_final_tables: 0,
    forward_oriented_dfas: 0,
    reverse_oriented_dfas: 0,
    joint_oriented_dfas: 0
  };
}

function includeEndpoints(profile, ends, states) {
  const forward = constraints(ends, states, "forward");
  const reverse = constraints(ends, states, "reverse");
  const joint = constraints(ends, states, "joint");
  const f = forward.choices > 0;
  const r = reverse.choices > 0;
  profile.transition_tables++;
  if (f) profile.forward_distinguishing_tables++;
  if (r) profile.reverse_distinguishing_tables++;
  if (f && r) profile.both_distinguishing_tables++;
  else if (f) profile.forward_only_tables++;
  else if (r) profile.reverse_only_tables++;
  else profile.neither_tables++;
  if (joint.choices > 0) profile.joint_final_tables++;
  profile.forward_oriented_dfas += forward.choices;
  profile.reverse_oriented_dfas += reverse.choices;
  profile.joint_oriented_dfas += joint.choices;
  return [forward.choices, reverse.choices, joint.choices];
}

function compileDfaSeparatorIndex(request) {
  if (!request || typeof request !== "object") throw new TypeError("request must be an object");
  const origin = sourceId(request.source_id, "source_id");
  const a = normalizeRuns(request.word_a_runs, "word_a_runs");
  const b = normalizeRuns(request.word_b_runs, "word_b_runs");
  if (JSON.stringify(a) === JSON.stringify(b)) throw new TypeError("the two words must be distinct");
  const maxStates = integer(request.max_states === undefined ? 4 : request.max_states, 1,
    DFA_SEPARATOR_LIMITS.max_states, "max_states");
  const exponents = exponentList(a, b);
  const exponentValues = exponents.map(BigInt);
  const exponentIds = new Map(exponents.map((value, index) => [value, index]));
  const references = [a, b, a.slice().reverse(), b.slice().reverse()].map((runs) =>
    runs.map(([symbol, count]) => [symbol, exponentIds.get(count)]));
  const work = {
    unary_functions: 0,
    unary_orbits: 0,
    unary_orbit_steps: 0,
    power_targets: 0,
    power_reductions: 0,
    transition_tables: 0,
    compressed_word_evaluations: 0,
    run_power_lookups: 0,
    expanded_word_symbols: 0,
    final_subsets_enumerated: 0
  };
  const levels = [];
  for (let states = 1; states <= maxStates; states++) {
    const unaryCount = states ** states;
    const maps = Array.from({ length: unaryCount }, (_, code) => decodeFunction(code, states));
    work.unary_functions += unaryCount;
    const orbits = maps.map((map) => Array.from({ length: states }, (_, start) => orbitOf(map, start, work)));
    const powers = exponentValues.map((count) =>
      orbits.map((rows) => rows.map((orbit) => powerFromOrbit(orbit, count, work))));
    const bytes = [];
    const profile = emptyProfile();
    for (let oneCode = 0; oneCode < unaryCount; oneCode++) {
      for (let zeroCode = 0; zeroCode < unaryCount; zeroCode++) {
        const functionCodes = [zeroCode, oneCode];
        const ends = references.map((runs) => {
          let state = 0;
          for (const [symbol, exponentId] of runs) {
            state = powers[exponentId][functionCodes[symbol]][state];
            work.run_power_lookups++;
          }
          work.compressed_word_evaluations++;
          return state;
        });
        const byte = ends[0] + states * (ends[1] + states * (ends[2] + states * ends[3]));
        bytes.push(byte.toString(16).padStart(2, "0"));
        includeEndpoints(profile, ends, states);
        work.transition_tables++;
      }
    }
    levels.push({
      states,
      unary_function_count: unaryCount,
      transition_table_count: unaryCount * unaryCount,
      unary_maps: maps,
      unary_orbits: orbits,
      power_outputs: powers,
      endpoints_hex: bytes.join(""),
      profile
    });
  }
  return {
    status: "COMPLETE",
    snapshot: {
      schema: SCHEMA,
      status: "COMPLETE",
      source_id: origin,
      alphabet: [0, 1],
      initial_state: 0,
      words: { a_runs: a, b_runs: b, a_length: wordLength(a), b_length: wordLength(b) },
      word_order: ["a", "b", "a_reverse", "b_reverse"],
      max_states: maxStates,
      exponents,
      code_order: CODE_ORDER,
      endpoint_encoding: ENDPOINT_ENCODING,
      levels
    },
    work
  };
}

function validateSnapshot(input) {
  if (!input || typeof input !== "object" || input.schema !== SCHEMA || input.status !== "COMPLETE") {
    throw new TypeError("a COMPLETE DFA separator snapshot is required");
  }
  const origin = sourceId(input.source_id, "snapshot.source_id");
  if (input.code_order !== CODE_ORDER || input.endpoint_encoding !== ENDPOINT_ENCODING) {
    throw new TypeError("unsupported transition or endpoint encoding");
  }
  if (JSON.stringify(input.alphabet) !== "[0,1]" || input.initial_state !== 0 ||
      JSON.stringify(input.word_order) !== '["a","b","a_reverse","b_reverse"]') {
    throw new TypeError("unexpected alphabet, start or endpoint order");
  }
  if (!input.words || typeof input.words !== "object") throw new TypeError("words are required");
  const a = normalizeRuns(input.words.a_runs, "a_runs", true);
  const b = normalizeRuns(input.words.b_runs, "b_runs", true);
  if (JSON.stringify(a) === JSON.stringify(b)) throw new TypeError("the two words must be distinct");
  if (input.words.a_length !== wordLength(a) || input.words.b_length !== wordLength(b)) {
    throw new TypeError("retained word lengths disagree with run lengths");
  }
  const maxStates = integer(input.max_states, 1, DFA_SEPARATOR_LIMITS.max_states, "max_states");
  const exponents = exponentList(a, b);
  if (JSON.stringify(exponents) !== JSON.stringify(input.exponents)) throw new TypeError("unexpected exponent index");
  array(input.levels, maxStates, maxStates, "levels");
  const endpointRows = [];
  const prefixes = [];
  const conflictCodes = [];
  const levels = [];
  let indexedRows = 0;
  for (let states = 1; states <= maxStates; states++) {
    const level = input.levels[states - 1];
    const unaryCount = states ** states;
    const tableCount = unaryCount * unaryCount;
    if (!level || typeof level !== "object" || level.states !== states ||
        level.unary_function_count !== unaryCount || level.transition_table_count !== tableCount) {
      throw new TypeError("unexpected level dimensions");
    }
    array(level.unary_maps, unaryCount, unaryCount, "unary_maps");
    const maps = level.unary_maps.map((map) => {
      array(map, states, states, "unary map");
      return map.map((target) => integer(target, 0, states - 1, "unary target"));
    });
    array(level.unary_orbits, unaryCount, unaryCount, "unary_orbits");
    const orbits = level.unary_orbits.map((rows) => {
      array(rows, states, states, "orbit rows");
      return rows.map((row, start) => {
        array(row, 3, 3, "orbit row");
        array(row[0], 1, states, "orbit path");
        const path = row[0].map((state) => integer(state, 0, states - 1, "orbit state"));
        if (path[0] !== start || new Set(path).size !== path.length) throw new TypeError("malformed orbit path");
        const mu = integer(row[1], 0, path.length - 1, "orbit preperiod");
        const period = integer(row[2], 1, path.length, "orbit period");
        if (mu + period !== path.length) throw new TypeError("orbit row does not close its retained positions");
        return [path, mu, period];
      });
    });
    array(level.power_outputs, exponents.length, exponents.length, "power_outputs");
    const powers = level.power_outputs.map((exponentRows) => {
      array(exponentRows, unaryCount, unaryCount, "power function rows");
      return exponentRows.map((row) => {
        array(row, states, states, "power start rows");
        return row.map((target) => integer(target, 0, states - 1, "power target"));
      });
    });
    if (typeof level.endpoints_hex !== "string" || level.endpoints_hex.length !== 2 * tableCount ||
        !/^[0-9a-f]+$/.test(level.endpoints_hex)) throw new TypeError("invalid complete endpoint encoding");
    const packed = new Uint8Array(tableCount);
    const sums = ORIENTATIONS.map(() => new Uint32Array(tableCount + 1));
    const conflicts = [];
    const profile = emptyProfile();
    for (let code = 0; code < tableCount; code++) {
      const byte = parseInt(level.endpoints_hex.slice(2 * code, 2 * code + 2), 16);
      if (byte >= states ** 4) throw new TypeError("endpoint byte exceeds its base-state range");
      packed[code] = byte;
      const choices = includeEndpoints(profile, unpackEndpoints(byte, states), states);
      if (choices[0] > 0 && choices[1] > 0 && choices[2] === 0) conflicts.push(code);
      for (let orientation = 0; orientation < ORIENTATIONS.length; orientation++) {
        sums[orientation][code + 1] = sums[orientation][code] + choices[orientation];
      }
      indexedRows++;
    }
    if (!level.profile || typeof level.profile !== "object") throw new TypeError("retained profile is missing");
    for (const key of Object.keys(profile)) {
      if (level.profile[key] !== profile[key]) throw new TypeError("profile disagrees with retained endpoints: " + key);
    }
    endpointRows.push(packed);
    prefixes.push(sums);
    conflictCodes.push(conflicts);
    levels.push({ states, unary_function_count: unaryCount, transition_table_count: tableCount,
      unary_maps: maps, unary_orbits: orbits, power_outputs: powers, endpoints_hex: level.endpoints_hex, profile });
  }
  return {
    snapshot: {
      schema: SCHEMA,
      status: "COMPLETE",
      source_id: origin,
      alphabet: [0, 1],
      initial_state: 0,
      words: { a_runs: a, b_runs: b, a_length: wordLength(a), b_length: wordLength(b) },
      word_order: ["a", "b", "a_reverse", "b_reverse"],
      max_states: maxStates,
      exponents,
      code_order: CODE_ORDER,
      endpoint_encoding: ENDPOINT_ENCODING,
      levels
    },
    endpoints: endpointRows,
    prefixes,
    conflict_codes: conflictCodes,
    indexed_rows: indexedRows
  };
}

function openRetainedDfaSeparatorIndex(request) {
  if (!request || typeof request !== "object") throw new TypeError("request must be an object");
  const retainedSource = sourceId(request.source_id, "source_id");
  const validated = validateSnapshot(request.snapshot);
  const saved = validated.snapshot;
  const stats = {
    retained_endpoint_rows_indexed: validated.indexed_rows,
    final_weight_prefixes_built: 3 * saved.max_states,
    count_queries: 0,
    select_queries: 0,
    rank_queries: 0,
    page_queries: 0,
    returned_page_dfas: 0,
    table_lookups: 0,
    conflict_page_queries: 0,
    returned_conflict_tables: 0,
    trace_queries: 0,
    selected_run_power_lookups: 0,
    unary_orbits_rebuilt: 0,
    power_targets_recomputed: 0,
    // Bulk catalogue evaluations only; selected trace run lookups are counted above.
    catalogue_word_evaluations_recomputed: 0,
    expanded_word_symbols: 0
  };
  const exponentIds = new Map(saved.exponents.map((count, id) => [count, id]));
  const traceWords = [
    saved.words.a_runs, saved.words.b_runs,
    saved.words.a_runs.slice().reverse(), saved.words.b_runs.slice().reverse()
  ];

  function parameters(input) {
    if (!input || typeof input !== "object") throw new TypeError("query must be an object");
    const states = integer(input.states, 1, saved.max_states, "states");
    const orientation = input.orientation === undefined ? "forward" : input.orientation;
    const orientationId = ORIENTATIONS.indexOf(orientation);
    if (orientationId < 0) throw new TypeError("orientation must be forward, reverse or joint");
    return { states, orientation, orientationId, level: saved.levels[states - 1],
      prefix: validated.prefixes[states - 1][orientationId] };
  }

  function unpack(states, code) {
    return unpackEndpoints(validated.endpoints[states - 1][code], states);
  }

  function maskStates(mask, states) {
    const result = [];
    for (let state = 0; state < states; state++) if ((mask & (1 << state)) !== 0) result.push(state);
    return result;
  }

  function describe(states, code) {
    const level = saved.levels[states - 1];
    const zeroCode = code % level.unary_function_count;
    const oneCode = Math.floor(code / level.unary_function_count);
    const zero = level.unary_maps[zeroCode];
    const one = level.unary_maps[oneCode];
    const ends = unpack(states, code);
    return {
      states,
      transition_code: code,
      zero_function_code: zeroCode,
      one_function_code: oneCode,
      initial_state: 0,
      alphabet: [0, 1],
      transitions: zero.map((target, state) => [target, one[state]]),
      endpoints: { a: ends[0], b: ends[1], a_reverse: ends[2], b_reverse: ends[3] },
      final_choices: {
        forward: constraints(ends, states, "forward").choices,
        reverse: constraints(ends, states, "reverse").choices,
        joint: constraints(ends, states, "joint").choices
      }
    };
  }

  function select(parameters, rank) {
    const { states, orientation, prefix, level } = parameters;
    const total = prefix[level.transition_table_count];
    if (rank >= total) return { status: "RANK_OUT_OF_RANGE", states, orientation, rank, count: total };
    let lo = 0;
    let hi = level.transition_table_count;
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2);
      if (prefix[mid + 1] <= rank) lo = mid + 1;
      else hi = mid;
    }
    const code = lo;
    const localRank = rank - prefix[code];
    const rule = constraints(unpack(states, code), states, orientation);
    const free = maskStates(rule.free_mask, states);
    let finalMask = rule.required_mask;
    for (let i = 0; i < free.length; i++) if ((localRank & (1 << i)) !== 0) finalMask |= 1 << free[i];
    return {
      status: "FOUND",
      states,
      orientation,
      rank,
      transition_code: code,
      final_mask: finalMask,
      accepting_states: maskStates(finalMask, states),
      dfa: describe(states, code)
    };
  }

  function minimum(orientation) {
    const key = orientation === "joint" ? "joint_oriented_dfas" :
      orientation === "reverse" ? "reverse_oriented_dfas" : "forward_oriented_dfas";
    for (const level of saved.levels) {
      if (level.profile[key] > 0) return { status: "FOUND", states: level.states };
    }
    return { status: "NOT_FOUND_THROUGH_CAP", through_states: saved.max_states };
  }

  return Object.freeze({
    summary() {
      return {
        schema: SCHEMA,
        status: "COMPLETE",
        origin_source_id: saved.source_id,
        retained_source_id: retainedSource,
        max_states: saved.max_states,
        word_lengths: { a: saved.words.a_length, b: saved.words.b_length },
        counting_convention: "labelled complete binary DFAs with initial state zero; unreachable states allowed; no isomorphism quotient",
        ordering: "increasing transition_code, then increasing final_mask",
        minima: { forward: minimum("forward"), reverse: minimum("reverse"), joint: minimum("joint") },
        levels: saved.levels.map((level) => ({ states: level.states, ...level.profile }))
      };
    },

    countDfas(input) {
      const p = parameters(input);
      stats.count_queries++;
      return { states: p.states, orientation: p.orientation,
        count: p.prefix[p.level.transition_table_count] };
    },

    selectDfa(input) {
      const p = parameters(input);
      const rank = integer(input.rank, 0, Number.MAX_SAFE_INTEGER, "rank");
      stats.select_queries++;
      return select(p, rank);
    },

    rankDfa(input) {
      const p = parameters(input);
      const code = integer(input.transition_code, 0, p.level.transition_table_count - 1, "transition_code");
      const finalMask = integer(input.final_mask, 0, (1 << p.states) - 1, "final_mask");
      stats.rank_queries++;
      const rule = constraints(unpack(p.states, code), p.states, p.orientation);
      if (rule.choices === 0 || (finalMask & rule.required_mask) !== rule.required_mask ||
          (finalMask & rule.forbidden_mask) !== 0) {
        return { status: "NOT_A_SEPARATOR", states: p.states, orientation: p.orientation,
          transition_code: code, final_mask: finalMask, rank: null };
      }
      let localRank = 0;
      const free = maskStates(rule.free_mask, p.states);
      for (let i = 0; i < free.length; i++) if ((finalMask & (1 << free[i])) !== 0) localRank |= 1 << i;
      return { status: "RANKED", states: p.states, orientation: p.orientation,
        transition_code: code, final_mask: finalMask, rank: p.prefix[code] + localRank };
    },

    pageDfas(input) {
      const p = parameters(input);
      const start = integer(input.start_rank === undefined ? 0 : input.start_rank, 0,
        Number.MAX_SAFE_INTEGER, "start_rank");
      const limit = integer(input.limit === undefined ? 32 : input.limit, 0,
        DFA_SEPARATOR_LIMITS.max_page, "limit");
      stats.page_queries++;
      const total = p.prefix[p.level.transition_table_count];
      const items = [];
      for (let i = 0; i < limit && start + i < total; i++) items.push(select(p, start + i));
      stats.returned_page_dfas += items.length;
      return { status: "OK", states: p.states, orientation: p.orientation, start_rank: start,
        items, next_rank: start + items.length, has_more: start + items.length < total, count: total };
    },

    pageConflictTables(input) {
      const p = parameters(input);
      const start = integer(input.start_rank === undefined ? 0 : input.start_rank, 0,
        Number.MAX_SAFE_INTEGER, "start_rank");
      const limit = integer(input.limit === undefined ? 32 : input.limit, 0,
        DFA_SEPARATOR_LIMITS.max_page, "limit");
      stats.conflict_page_queries++;
      const codes = validated.conflict_codes[p.states - 1];
      const selectedCodes = start < codes.length ? codes.slice(start, Math.min(start + limit, codes.length)) : [];
      const items = selectedCodes.map((code, offset) => {
        const rule = constraints(unpack(p.states, code), p.states, "joint");
        return {
          conflict_rank: start + offset,
          ...describe(p.states, code),
          joint_required_accepting_mask: rule.required_mask,
          joint_required_rejecting_mask: rule.forbidden_mask,
          conflicting_states: maskStates(rule.required_mask & rule.forbidden_mask, p.states)
        };
      });
      stats.returned_conflict_tables += items.length;
      return { status: "OK", states: p.states, start_rank: start,
        category: "both pairs distinguishable separately, but no common accepting set",
        items, next_rank: start + items.length, has_more: start + items.length < codes.length,
        count: codes.length };
    },

    lookupTable(input) {
      const p = parameters(input);
      const code = integer(input.transition_code, 0, p.level.transition_table_count - 1, "transition_code");
      stats.table_lookups++;
      return describe(p.states, code);
    },

    traceTable(input) {
      const p = parameters(input);
      const code = integer(input.transition_code, 0, p.level.transition_table_count - 1, "transition_code");
      stats.trace_queries++;
      const functionCodes = [code % p.level.unary_function_count,
        Math.floor(code / p.level.unary_function_count)];
      const traces = traceWords.map((runs, word) => {
        let state = 0;
        let length = 0n;
        const boundaries = [{ length: "0", state: 0 }];
        for (const [symbol, count] of runs) {
          state = p.level.power_outputs[exponentIds.get(count)][functionCodes[symbol]][state];
          length += BigInt(count);
          boundaries.push({ length: length.toString(), state });
          stats.selected_run_power_lookups++;
        }
        return { word: saved.word_order[word], boundaries };
      });
      return { states: p.states, transition_code: code, traces };
    },

    snapshot() {
      return JSON.parse(JSON.stringify(saved));
    },

    work() {
      return JSON.parse(JSON.stringify(stats));
    }
  });
}

module.exports = {
  compileDfaSeparatorIndex,
  openRetainedDfaSeparatorIndex,
  DFA_SEPARATOR_LIMITS
};
