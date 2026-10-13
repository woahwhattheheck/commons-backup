"use strict";

// Finite dictionaries, contiguous factors of L*, and exact shortest-word navigation.
// Classical trie/restart NFA and subset construction; no complexity-bound claim.

const FACTOR_INDEX_LIMITS = Object.freeze({
  alphabet_size: 8,
  raw_words: 1024,
  word_symbols: 128,
  raw_word_symbols: 32768,
  nfa_states: 512,
  subsets: 16384,
  transitions: 131072,
  nfa_membership_visits: 8388608,
  depth: 1024,
  page_size: 128,
  source_id_chars: 512
});

function factorInteger(value, name, low, high) {
  if (!Number.isSafeInteger(value) || value < low || value > high) {
    throw new RangeError(name + " must be a safe integer in [" + low + "," + high + "]");
  }
  return value;
}

function factorSourceId(value) {
  if (typeof value !== "string" || !value.trim() ||
      value.length > FACTOR_INDEX_LIMITS.source_id_chars) {
    throw new TypeError("source_id must be a nonempty string of at most 512 code units");
  }
  return value;
}

function factorAlphabet(value) {
  if (!Array.isArray(value) || value.length > FACTOR_INDEX_LIMITS.alphabet_size) {
    throw new TypeError("alphabet must be an ordered array of at most 8 distinct Unicode scalar symbols");
  }
  const seen = new Set();
  for (const symbol of value) {
    if (typeof symbol !== "string" || Array.from(symbol).length !== 1 ||
        (symbol.codePointAt(0) >= 0xd800 && symbol.codePointAt(0) <= 0xdfff) ||
        seen.has(symbol)) {
      throw new TypeError("alphabet entries must be distinct single Unicode scalar values");
    }
    seen.add(symbol);
  }
  return value.slice();
}

function factorWordIds(word, alphabetMap, maxLength, name) {
  if (typeof word !== "string") throw new TypeError(name + " must be a string");
  const ids = [];
  for (const symbol of word) {
    if (!alphabetMap.has(symbol)) throw new RangeError(name + " contains a symbol outside the alphabet");
    ids.push(alphabetMap.get(symbol));
    if (ids.length > maxLength) throw new RangeError(name + " exceeds its symbol-length limit");
  }
  return ids;
}

function factorRank(value, name) {
  if (typeof value === "bigint") {
    if (value < 0n) throw new RangeError(name + " must be nonnegative");
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || value < 0) throw new RangeError(name + " must be an exact nonnegative integer");
    return BigInt(value);
  }
  if (typeof value !== "string" || value.length > 1024 || !/^(0|[1-9][0-9]*)$/.test(value)) {
    throw new TypeError(name + " must be a nonnegative BigInt, safe integer, or canonical decimal string");
  }
  return BigInt(value);
}

function factorCopy(value) {
  return JSON.parse(JSON.stringify(value));
}

function factorIndex(snapshot, origin) {
  const alphabet = snapshot.input.alphabet;
  const alphabetMap = new Map(alphabet.map((symbol, id) => [symbol, id]));
  const states = snapshot.subset_states;
  const missing = snapshot.status === "SHORTEST_MISSING_WORDS";
  const counts = missing ? states.map(state => BigInt(state.shortest_suffix_count)) : null;
  const total = missing ? counts[0] : null;
  const distance = snapshot.shortest_missing_length;
  const summary = {
    schema: "finite_dictionary.factor_index_summary/v1",
    status: snapshot.status,
    source_id: snapshot.input.source_id,
    provenance: origin,
    alphabet: alphabet.slice(),
    dictionary_words: snapshot.input.words.length,
    nfa_states: snapshot.nfa.nodes.length,
    subset_states: states.length,
    shortest_missing_length: distance,
    shortest_missing_count: total === null ? null : total.toString(),
    exact_decision: snapshot.status === "FACTOR_UNIVERSAL" || snapshot.empty_subset_id !== null,
    all_shortest_words_accounted: missing,
    factor_universal: snapshot.status === "FACTOR_UNIVERSAL" ? true : snapshot.empty_subset_id !== null ? false : null,
    resource_stop: snapshot.resource_stop
  };

  function requireMissing() {
    if (!missing) {
      const error = new Error(snapshot.status === "FACTOR_UNIVERSAL" ?
        "There is no missing word: factor universality was established." :
        "The bounded search did not finish an all-shortest-word certificate.");
      error.name = snapshot.status === "FACTOR_UNIVERSAL" ? "NoMissingWordError" : "IncompleteFactorSearchError";
      throw error;
    }
  }

  function selectShortest(rank) {
    requireMissing();
    let remaining = factorRank(rank, "rank");
    if (remaining >= total) throw new RangeError("rank is outside the shortest-word family");
    const originalRank = remaining.toString();
    const symbols = [];
    const statePath = [0];
    let stateId = 0;
    for (let depth = 0; depth < distance; depth++) {
      let chosen = false;
      for (let symbol = 0; symbol < alphabet.length; symbol++) {
        const next = states[stateId].transitions[symbol];
        const ways = next !== null && states[next].depth === depth + 1 ? counts[next] : 0n;
        if (remaining >= ways) {
          remaining -= ways;
        } else {
          symbols.push(alphabet[symbol]);
          stateId = next;
          statePath.push(next);
          chosen = true;
          break;
        }
      }
      if (!chosen) throw new Error("Retained shortest-word counts are inconsistent with the transition table");
    }
    if (stateId !== snapshot.empty_subset_id || remaining !== 0n) {
      throw new Error("Retained shortest-word selection did not end at the empty subset");
    }
    return {rank: originalRank, word: symbols.join(""), length: distance, subset_path: statePath};
  }

  function rankShortest(word) {
    requireMissing();
    const symbols = factorWordIds(word, alphabetMap, FACTOR_INDEX_LIMITS.depth, "word");
    if (symbols.length !== distance) throw new RangeError("word does not have the shortest missing length");
    let rank = 0n;
    let stateId = 0;
    const statePath = [0];
    for (let depth = 0; depth < distance; depth++) {
      const actual = symbols[depth];
      for (let symbol = 0; symbol < actual; symbol++) {
        const next = states[stateId].transitions[symbol];
        if (next !== null && states[next].depth === depth + 1) rank += counts[next];
      }
      const next = states[stateId].transitions[actual];
      if (next === null || states[next].depth !== depth + 1 || counts[next] === 0n) {
        throw new RangeError("word is not a shortest missing word");
      }
      stateId = next;
      statePath.push(next);
    }
    if (stateId !== snapshot.empty_subset_id) throw new RangeError("word is not a shortest missing word");
    return {rank: rank.toString(), word, length: distance, subset_path: statePath};
  }

  function pageShortest(request) {
    requireMissing();
    if (!request || typeof request !== "object" || Array.isArray(request)) {
      throw new TypeError("page request must be an object");
    }
    const start = factorRank(request.start_rank === undefined ? 0 : request.start_rank, "start_rank");
    const limit = factorInteger(request.limit === undefined ? 32 : request.limit, "limit", 0, FACTOR_INDEX_LIMITS.page_size);
    if (start > total) throw new RangeError("start_rank exceeds the family size");
    const records = [];
    let rank = start;
    while (rank < total && records.length < limit) {
      records.push(selectShortest(rank));
      rank++;
    }
    return {start_rank: start.toString(), total: total.toString(), records,
      next_rank: rank < total ? rank.toString() : null};
  }

  return Object.freeze({
    describe: () => factorCopy(summary),
    snapshot: () => factorCopy(snapshot),
    selectShortest,
    rankShortest,
    pageShortest
  });
}

function createFiniteFactorIndex(request) {
  if (!request || typeof request !== "object" || Array.isArray(request)) {
    throw new TypeError("request must be an object");
  }
  const sourceId = factorSourceId(request.source_id);
  const alphabet = factorAlphabet(request.alphabet);
  const alphabetMap = new Map(alphabet.map((symbol, id) => [symbol, id]));
  if (!Array.isArray(request.words) || request.words.length > FACTOR_INDEX_LIMITS.raw_words) {
    throw new TypeError("words must be an array with at most 1024 entries");
  }
  const normalized = new Map();
  let rawSymbols = 0;
  let emptyEntries = 0;
  for (const word of request.words) {
    const ids = factorWordIds(word, alphabetMap, FACTOR_INDEX_LIMITS.word_symbols, "dictionary word");
    rawSymbols += ids.length;
    if (rawSymbols > FACTOR_INDEX_LIMITS.raw_word_symbols) throw new RangeError("raw dictionary symbol limit exceeded");
    if (ids.length === 0) emptyEntries++;
    else if (!normalized.has(word)) normalized.set(word, ids);
  }
  const wordEntries = Array.from(normalized.entries());
  wordEntries.sort((left, right) => {
    const a = left[1], b = right[1];
    for (let i = 0; i < Math.min(a.length, b.length); i++) if (a[i] !== b[i]) return a[i] - b[i];
    return a.length - b.length;
  });
  const suppliedBudget = request.budget === undefined ? {} : request.budget;
  if (!suppliedBudget || typeof suppliedBudget !== "object" || Array.isArray(suppliedBudget)) {
    throw new TypeError("budget must be an object");
  }
  const budget = {};
  for (const name of ["subsets", "transitions", "nfa_membership_visits", "depth"]) {
    budget[name] = factorInteger(suppliedBudget[name] === undefined ?
      FACTOR_INDEX_LIMITS[name] : suppliedBudget[name], "budget." + name, 1, FACTOR_INDEX_LIMITS[name]);
  }
  for (const name of Object.keys(suppliedBudget)) {
    if (!Object.prototype.hasOwnProperty.call(budget, name)) throw new TypeError("unknown budget field: " + name);
  }

  const nodes = [{id: 0, prefix: "", terminal: false, children: Array(alphabet.length).fill(-1)}];
  for (const [word, ids] of wordEntries) {
    let nodeId = 0;
    for (const symbol of ids) {
      let next = nodes[nodeId].children[symbol];
      if (next === -1) {
        if (nodes.length >= FACTOR_INDEX_LIMITS.nfa_states) throw new RangeError("dictionary trie exceeds 512 nodes");
        next = nodes.length;
        nodes[nodeId].children[symbol] = next;
        nodes.push({id: next, prefix: nodes[nodeId].prefix + alphabet[symbol],
          terminal: false, children: Array(alphabet.length).fill(-1)});
      }
      nodeId = next;
    }
    nodes[nodeId].terminal = true;
  }
  const bits = nodes.map((_, id) => 1n << BigInt(id));
  const rows = nodes.map(node => node.children.map(child =>
    child < 0 ? 0n : bits[child] | (nodes[child].terminal ? 1n : 0n)));
  const fullMask = (1n << BigInt(nodes.length)) - 1n;
  const states = [{mask: fullMask, members: nodes.map(node => node.id), depth: 0,
    first_parent: null, transitions: Array(alphabet.length).fill(null)}];
  const known = new Map([[fullMask.toString(16), 0]]);
  const work = {trie_nodes: nodes.length, raw_dictionary_symbol_visits: rawSymbols,
    subset_transitions_computed: 0, subset_transitions_recorded: 0,
    nfa_membership_visits: 0, new_subset_bit_probes: 0,
    shortest_count_additions: 0, enumerated_words: 0};
  let cursor = 0, shortest = null, emptyId = null, resourceStop = null;
  let completeRows = 0;
  search:
  while (cursor < states.length) {
    const state = states[cursor];
    if (shortest !== null && state.depth >= shortest) break;
    if (alphabet.length && state.depth >= budget.depth) {
      resourceStop = {kind: "depth", limit: budget.depth, state_id: cursor, symbol_id: 0};
      break;
    }
    for (let symbol = 0; symbol < alphabet.length; symbol++) {
      if (work.subset_transitions_computed >= budget.transitions) {
        resourceStop = {kind: "transitions", limit: budget.transitions, state_id: cursor, symbol_id: symbol};
        break search;
      }
      if (work.nfa_membership_visits + state.members.length > budget.nfa_membership_visits) {
        resourceStop = {kind: "nfa_membership_visits", limit: budget.nfa_membership_visits,
          state_id: cursor, symbol_id: symbol, next_transition_memberships: state.members.length};
        break search;
      }
      let nextMask = 0n;
      for (const member of state.members) nextMask |= rows[member][symbol];
      work.nfa_membership_visits += state.members.length;
      work.subset_transitions_computed++;
      const key = nextMask.toString(16);
      let nextId = known.get(key);
      if (nextId === undefined) {
        if (states.length >= budget.subsets) {
          resourceStop = {kind: "subsets", limit: budget.subsets, state_id: cursor,
            symbol_id: symbol, computed_unrecorded_destination_mask_hex: key};
          break search;
        }
        nextId = states.length;
        const members = [];
        for (let id = 0; id < nodes.length; id++) {
          work.new_subset_bit_probes++;
          if ((nextMask & bits[id]) !== 0n) members.push(id);
        }
        states.push({mask: nextMask, members, depth: state.depth + 1,
          first_parent: {state_id: cursor, symbol_id: symbol},
          transitions: Array(alphabet.length).fill(null)});
        known.set(key, nextId);
      }
      state.transitions[symbol] = nextId;
      work.subset_transitions_recorded++;
      if (nextMask === 0n && shortest === null) {
        shortest = state.depth + 1;
        emptyId = nextId;
      }
    }
    completeRows++;
    cursor++;
  }
  const status = resourceStop ? "RESOURCE_LIMIT" :
    shortest !== null ? "SHORTEST_MISSING_WORDS" : "FACTOR_UNIVERSAL";
  let firstMissing = null;
  if (emptyId !== null) {
    const reversed = [];
    let stateId = emptyId;
    while (stateId !== 0) {
      const parent = states[stateId].first_parent;
      reversed.push(alphabet[parent.symbol_id]);
      stateId = parent.state_id;
    }
    firstMissing = reversed.reverse().join("");
  }
  const suffixCounts = status === "SHORTEST_MISSING_WORDS" ? states.map(() => 0n) : null;
  if (suffixCounts) {
    suffixCounts[emptyId] = 1n;
    for (let id = states.length - 1; id >= 0; id--) {
      if (states[id].depth >= shortest) continue;
      for (const next of states[id].transitions) {
        if (next !== null && states[next].depth === states[id].depth + 1) {
          suffixCounts[id] += suffixCounts[next];
          work.shortest_count_additions++;
        }
      }
    }
  }
  const snapshot = {
    schema: "finite_dictionary.factor_index/v1",
    status,
    input: {source_id: sourceId, alphabet, words: wordEntries.map(entry => entry[0]),
      raw_word_count: request.words.length, raw_symbol_count: rawSymbols,
      empty_entries_removed: emptyEntries,
      repeated_nonempty_entries_removed: request.words.length - emptyEntries - wordEntries.length,
      alphabet_order: "explicit input order", symbol_model: "Unicode scalar values without normalization",
      empty_word_in_star_and_factors: true},
    nfa: {construction: "prefix trie; terminal-to-root epsilon restart; all states initial and final",
      root_id: 0, nodes: nodes.map(node => ({id: node.id, prefix: node.prefix,
        terminal: node.terminal, children: node.children.slice(),
        epsilon_closed_transition_masks_hex: rows[node.id].map(mask => mask.toString(16))})),
      initial_subset_mask_hex: fullMask.toString(16),
      mask_bit_convention: "bit i identifies trie node i; lowercase hexadecimal, no prefix"},
    subset_states: states.map((state, id) => ({id, mask_hex: state.mask.toString(16),
      depth: state.depth, first_parent: state.first_parent,
      transitions: state.transitions.slice(),
      shortest_suffix_count: suffixCounts ? suffixCounts[id].toString() : null})),
    empty_subset_id: emptyId,
    shortest_missing_length: shortest,
    first_missing_word: firstMissing,
    shortest_missing_count: suffixCounts ? suffixCounts[0].toString() : null,
    coverage: {subset_discovery: "breadth-first with alphabet-ordered transitions",
      complete_transition_rows: completeRows, next_row_id: cursor < states.length ? cursor : null,
      all_reachable_subsets_closed: status === "FACTOR_UNIVERSAL",
      all_layers_before_missing_length_complete: status === "SHORTEST_MISSING_WORDS",
      all_shortest_words_represented_by_distance_dag: status === "SHORTEST_MISSING_WORDS",
      all_words_through_length_known_present: shortest !== null ? shortest - 1 :
        resourceStop ? states[cursor].depth : null,
      finite_dictionary_decision_only: true, general_complexity_or_length_bound_claimed: false},
    resource_stop: resourceStop, budget, limits: FACTOR_INDEX_LIMITS, work
  };
  return factorIndex(snapshot, {kind: "compiled_in_this_call", source_id: sourceId,
    independent_certificate_validation: false});
}

// This loader consumes a retained complete certificate as a premise.
// It checks structure and indexing, not NFA transitions, BFS correctness, or count arithmetic.
function openRetainedFiniteFactorIndex(request) {
  if (!request || typeof request !== "object" || Array.isArray(request)) throw new TypeError("request must be an object");
  const sourceId = factorSourceId(request.source_id);
  const snapshot = request.snapshot;
  if (!snapshot || typeof snapshot !== "object" || snapshot.schema !== "finite_dictionary.factor_index/v1" ||
      !["FACTOR_UNIVERSAL", "SHORTEST_MISSING_WORDS"].includes(snapshot.status)) {
    throw new TypeError("a retained complete factor-index snapshot is required");
  }
  const alphabet = factorAlphabet(snapshot.input && snapshot.input.alphabet);
  factorSourceId(snapshot.input.source_id);
  if (!Array.isArray(snapshot.input.words) || snapshot.input.words.length > FACTOR_INDEX_LIMITS.raw_words) {
    throw new TypeError("invalid retained dictionary shape");
  }
  if (!snapshot.nfa || !Array.isArray(snapshot.nfa.nodes) ||
      !snapshot.nfa.nodes.length || snapshot.nfa.nodes.length > FACTOR_INDEX_LIMITS.nfa_states) {
    throw new TypeError("invalid retained NFA shape");
  }
  const states = snapshot.subset_states;
  if (!Array.isArray(states) || !states.length || states.length > FACTOR_INDEX_LIMITS.subsets) {
    throw new TypeError("invalid retained subset-state shape");
  }
  const n = snapshot.nfa.nodes.length;
  const bound = 1n << BigInt(n);
  const seen = new Set();
  const missing = snapshot.status === "SHORTEST_MISSING_WORDS";
  let emptyId = null;
  if (missing) {
    factorInteger(snapshot.shortest_missing_length, "shortest_missing_length", 1, FACTOR_INDEX_LIMITS.depth);
    emptyId = factorInteger(snapshot.empty_subset_id, "empty_subset_id", 0, states.length - 1);
  }
  for (let id = 0; id < states.length; id++) {
    const state = states[id];
    if (!state || state.id !== id || typeof state.mask_hex !== "string" ||
        state.mask_hex.length > Math.ceil(n / 4) || !/^(0|[1-9a-f][0-9a-f]*)$/.test(state.mask_hex) ||
        BigInt("0x" + state.mask_hex) >= bound || seen.has(state.mask_hex)) {
      throw new TypeError("invalid or repeated retained subset identity");
    }
    seen.add(state.mask_hex);
    factorInteger(state.depth, "subset depth", 0, FACTOR_INDEX_LIMITS.depth);
    if (!Array.isArray(state.transitions) || state.transitions.length !== alphabet.length) {
      throw new TypeError("invalid retained transition row");
    }
    for (const next of state.transitions) {
      if (next !== null) factorInteger(next, "transition destination", 0, states.length - 1);
      else if (!missing || state.depth < snapshot.shortest_missing_length) {
        throw new TypeError("a required complete transition row is missing");
      }
    }
    if (id === 0) {
      if (state.depth !== 0 || state.first_parent !== null ||
          state.mask_hex !== (bound - 1n).toString(16)) throw new TypeError("invalid initial retained subset");
    } else {
      const parent = state.first_parent;
      if (!parent) throw new TypeError("missing retained first parent");
      factorInteger(parent.state_id, "parent state", 0, id - 1);
      factorInteger(parent.symbol_id, "parent symbol", 0, alphabet.length - 1);
      if (states[parent.state_id].depth + 1 !== state.depth ||
          states[parent.state_id].transitions[parent.symbol_id] !== id) {
        throw new TypeError("retained parent indices disagree");
      }
    }
    if (missing) {
      if (typeof state.shortest_suffix_count !== "string") throw new TypeError("retained suffix counts must be decimal strings");
      factorRank(state.shortest_suffix_count, "shortest_suffix_count");
    }
  }
  if (missing) {
    if (states[emptyId].mask_hex !== "0" ||
        states[emptyId].depth !== snapshot.shortest_missing_length ||
        states[emptyId].shortest_suffix_count !== "1" ||
        states[0].shortest_suffix_count !== snapshot.shortest_missing_count ||
        factorRank(snapshot.shortest_missing_count, "shortest_missing_count") === 0n) {
      throw new TypeError("retained missing-word endpoint or count is inconsistent");
    }
  } else if (seen.has("0")) throw new TypeError("a universal retained index cannot contain the empty subset");
  return factorIndex(factorCopy(snapshot), {kind: "retained_snapshot_premise", source_id: sourceId,
    structural_checks: true, source_authenticated: false,
    nfa_transition_images_recomputed: false, breadth_first_search_replayed: false,
    shortest_count_recurrence_recomputed: false});
}

module.exports = {
  createFiniteFactorIndex,
  openRetainedFiniteFactorIndex,
  FACTOR_INDEX_LIMITS
};
