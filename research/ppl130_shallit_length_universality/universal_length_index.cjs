"use strict";

/**
 * Exact universal-length navigation for a bounded epsilon-free finite NFA.
 * Source conventions and the published prime-cycle consumer are documented
 * in UNIVERSAL_LENGTH_API.md. No external package or native runtime is used.
 */
const UNIVERSAL_LENGTH_LIMITS = Object.freeze({
  max_states: 64,
  max_alphabet: 8,
  max_symbol_code_units: 32,
  max_source_id_code_units: 512,
  max_state_subsets: 4096,
  max_family_members: 4096,
  max_families: 4096,
  max_total_family_members: 262144,
  max_total_predecessors: 262144,
  max_transition_visits: 1048576,
  max_query_digits: 1024,
  max_word_length: 4096,
  max_page: 128
});

const SCHEMA = "commons.universal_length_family_index/v1";

function integer(value, lo, hi, name) {
  if (!Number.isSafeInteger(value) || value < lo || value > hi) {
    throw new RangeError(name + " must be a safe integer in [" + lo + "," + hi + "]");
  }
  return value;
}

function sourceId(value, name) {
  if (typeof value !== "string" || value.length === 0 ||
      value.length > UNIVERSAL_LENGTH_LIMITS.max_source_id_code_units) {
    throw new TypeError(name + " must be a nonempty bounded string");
  }
  return value;
}

function array(value, lo, hi, name) {
  if (!Array.isArray(value) || value.length < lo || value.length > hi) {
    throw new RangeError(name + " has an invalid array length");
  }
  return value;
}

function ids(value, bound, name, strict) {
  array(value, 0, bound, name);
  const result = value.map((x) => integer(x, 0, bound - 1, name + " entry"));
  if (strict) {
    for (let i = 1; i < result.length; i++) {
      if (result[i - 1] >= result[i]) throw new TypeError(name + " must be strictly increasing");
    }
    return result;
  }
  return [...new Set(result)].sort((a, b) => a - b);
}

function normalizeAutomaton(value, strict) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError("automaton must be an object");
  }
  if (Object.prototype.hasOwnProperty.call(value, "epsilon_transitions")) {
    throw new TypeError("epsilon_transitions are not supported; eliminate them before using this API");
  }
  const n = integer(value.state_count, 1, UNIVERSAL_LENGTH_LIMITS.max_states, "state_count");
  array(value.alphabet, 1, UNIVERSAL_LENGTH_LIMITS.max_alphabet, "alphabet");
  const alphabet = value.alphabet.map((symbol) => {
    if (typeof symbol !== "string" || symbol.length === 0 ||
        symbol.length > UNIVERSAL_LENGTH_LIMITS.max_symbol_code_units) {
      throw new TypeError("each alphabet symbol must be a nonempty bounded string");
    }
    return symbol;
  });
  if (new Set(alphabet).size !== alphabet.length) throw new TypeError("alphabet symbols must be distinct");
  const initial = ids(value.initial_states, n, "initial_states", strict);
  const finals = ids(value.final_states, n, "final_states", strict);
  array(value.transitions, n, n, "transitions");
  const transitions = value.transitions.map((row, state) => {
    array(row, alphabet.length, alphabet.length, "transition row");
    return row.map((destinations, symbol) =>
      ids(destinations, n, "transitions[" + state + "][" + symbol + "]", strict));
  });
  return { state_count: n, alphabet, initial_states: initial, final_states: finals, transitions };
}

function maskOf(stateIds) {
  let mask = 0n;
  for (const state of stateIds) mask |= 1n << BigInt(state);
  return mask;
}

function queryInteger(value, name) {
  let text;
  if (typeof value === "bigint") {
    if (value < 0n) throw new RangeError(name + " must be nonnegative");
    text = value.toString();
  } else if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || value < 0) {
      throw new RangeError(name + " must be a nonnegative safe integer or canonical decimal");
    }
    text = String(value);
  } else if (typeof value === "string" && /^(?:0|[1-9][0-9]*)$/.test(value)) {
    text = value;
  } else {
    throw new TypeError(name + " must be a nonnegative integer in canonical decimal form");
  }
  if (text.length > UNIVERSAL_LENGTH_LIMITS.max_query_digits) {
    throw new RangeError(name + " exceeds the input digit cap");
  }
  return BigInt(text);
}

function upperBound(sorted, value) {
  let lo = 0;
  let hi = sorted.length;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (sorted[mid] <= value) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

class ResourceLimit extends Error {
  constructor(code) {
    super(code);
    this.name = "UniversalLengthResourceLimit";
    this.code = code;
  }
}

function compileUniversalLengthIndex(request) {
  if (!request || typeof request !== "object") throw new TypeError("request must be an object");
  const origin = sourceId(request.source_id, "source_id");
  const automaton = normalizeAutomaton(request.automaton, false);
  const alphabetSize = automaton.alphabet.length;
  const finalMask = maskOf(automaton.final_states);
  const transitionMasks = automaton.transitions.map((row) => row.map(maskOf));
  const work = {
    input_transition_edges: automaton.transitions.reduce((sum, row) =>
      sum + row.reduce((part, destinations) => part + destinations.length, 0), 0),
    state_subsets: 0,
    families: 0,
    family_member_rows: 0,
    predecessor_rows: 0,
    family_steps: 0,
    family_member_visits: 0,
    transition_visits: 0,
    subset_transition_computations: 0,
    subset_transition_cache_hits: 0,
    state_transition_unions: 0,
    acceptance_mask_checks: 0
  };
  const masks = [];
  const subsetMap = new Map();
  const subsetTransitions = [];
  const layers = [];
  const seenFamilies = new Map();

  function intern(mask) {
    const key = mask.toString();
    if (subsetMap.has(key)) return subsetMap.get(key);
    if (masks.length >= UNIVERSAL_LENGTH_LIMITS.max_state_subsets) {
      throw new ResourceLimit("STATE_SUBSET_CAP");
    }
    const id = masks.length;
    masks.push(mask);
    subsetMap.set(key, id);
    subsetTransitions.push(new Array(alphabetSize).fill(null));
    work.state_subsets++;
    return id;
  }

  function advance(subset, symbol) {
    if (work.transition_visits >= UNIVERSAL_LENGTH_LIMITS.max_transition_visits) {
      throw new ResourceLimit("TRANSITION_VISIT_CAP");
    }
    work.transition_visits++;
    const cached = subsetTransitions[subset][symbol];
    if (cached !== null) {
      work.subset_transition_cache_hits++;
      return cached;
    }
    let destination = 0n;
    const mask = masks[subset];
    for (let state = 0; state < automaton.state_count; state++) {
      if ((mask & (1n << BigInt(state))) !== 0n) {
        destination |= transitionMasks[state][symbol];
        work.state_transition_unions++;
      }
    }
    work.subset_transition_computations++;
    const next = intern(destination);
    subsetTransitions[subset][symbol] = next;
    return next;
  }

  function makeLayer(subsets) {
    let rejected = null;
    for (const subset of subsets) {
      work.acceptance_mask_checks++;
      if ((masks[subset] & finalMask) === 0n && rejected === null) rejected = subset;
    }
    work.families++;
    work.family_member_rows += subsets.length;
    return {
      subset_ids: subsets,
      universal: rejected === null,
      rejected_subset_id: rejected,
      next_layer: null,
      predecessors: []
    };
  }

  function retainedParts() {
    return {
      automaton,
      initial_subset_id: 0,
      state_subsets: masks.map((mask) => mask.toString()),
      subset_transitions: subsetTransitions,
      layers
    };
  }

  const first = intern(maskOf(automaton.initial_states));
  layers.push(makeLayer([first]));
  seenFamilies.set(String(first), 0);

  try {
    for (;;) {
      const currentIndex = layers.length - 1;
      const current = layers[currentIndex];
      const predecessors = new Map();
      for (const previous of current.subset_ids) {
        work.family_member_visits++;
        for (let symbol = 0; symbol < alphabetSize; symbol++) {
          const next = advance(previous, symbol);
          if (!predecessors.has(next)) {
            if (predecessors.size >= UNIVERSAL_LENGTH_LIMITS.max_family_members) {
              throw new ResourceLimit("FAMILY_MEMBER_CAP");
            }
            predecessors.set(next, [next, previous, symbol]);
          }
        }
      }
      const nextSubsets = [...predecessors.keys()].sort((a, b) => a - b);
      const nextKey = nextSubsets.join(",");
      const nextPredecessors = nextSubsets.map((subset) => predecessors.get(subset));
      if (work.predecessor_rows + nextPredecessors.length >
          UNIVERSAL_LENGTH_LIMITS.max_total_predecessors) {
        throw new ResourceLimit("PREDECESSOR_ROW_CAP");
      }
      if (seenFamilies.has(nextKey)) {
        const preperiod = seenFamilies.get(nextKey);
        current.next_layer = preperiod;
        current.predecessors = nextPredecessors;
        work.predecessor_rows += nextPredecessors.length;
        work.family_steps++;
        const prefix = [];
        const cycle = [];
        for (let i = 0; i < layers.length; i++) {
          if (layers[i].universal) {
            if (i < preperiod) prefix.push(i);
            else cycle.push(i - preperiod);
          }
        }
        return {
          status: "COMPLETE",
          snapshot: {
            schema: SCHEMA,
            status: "COMPLETE",
            source_id: origin,
            ...retainedParts(),
            preperiod,
            period: layers.length - preperiod,
            universal_prefix_lengths: prefix,
            universal_cycle_offsets: cycle
          },
          work: { ...work }
        };
      }
      if (layers.length >= UNIVERSAL_LENGTH_LIMITS.max_families) {
        throw new ResourceLimit("FAMILY_COUNT_CAP");
      }
      if (work.family_member_rows + nextSubsets.length >
          UNIVERSAL_LENGTH_LIMITS.max_total_family_members) {
        throw new ResourceLimit("TOTAL_FAMILY_MEMBER_CAP");
      }
      const nextIndex = layers.length;
      const nextLayer = makeLayer(nextSubsets);
      current.next_layer = nextIndex;
      current.predecessors = nextPredecessors;
      work.predecessor_rows += nextPredecessors.length;
      work.family_steps++;
      seenFamilies.set(nextKey, nextIndex);
      layers.push(nextLayer);
    }
  } catch (error) {
    if (!(error instanceof ResourceLimit)) throw error;
    const observed = [];
    for (let i = 0; i < layers.length; i++) if (layers[i].universal) observed.push(i);
    return {
      status: "INCOMPLETE",
      reason: error.code,
      source_id: origin,
      observed_length_range: [0, layers.length - 1],
      observed_universal_lengths: observed,
      least_universal_length_in_observed_prefix: observed.length ? observed[0] : null,
      existence_status: observed.length ? "WITNESS_FOUND" : "UNRESOLVED",
      unfinished_layer: layers.length - 1,
      prefix: retainedParts(),
      work: { ...work }
    };
  }
}

function validateSnapshot(input) {
  if (!input || typeof input !== "object" || input.schema !== SCHEMA || input.status !== "COMPLETE") {
    throw new TypeError("a COMPLETE universal-length snapshot is required");
  }
  const origin = sourceId(input.source_id, "snapshot.source_id");
  const automaton = normalizeAutomaton(input.automaton, true);
  if (input.initial_subset_id !== 0) throw new TypeError("initial_subset_id must be zero");
  array(input.state_subsets, 1, UNIVERSAL_LENGTH_LIMITS.max_state_subsets, "state_subsets");
  const maskLimit = 1n << BigInt(automaton.state_count);
  const stateSubsets = input.state_subsets.map((value) => {
    if (typeof value !== "string" || value.length > 20 || !/^(?:0|[1-9][0-9]*)$/.test(value) ||
        BigInt(value) >= maskLimit) {
      throw new TypeError("state_subsets must contain bounded canonical bitmask strings");
    }
    return value;
  });
  if (new Set(stateSubsets).size !== stateSubsets.length) throw new TypeError("duplicate subset bitmask");
  const subsetCount = stateSubsets.length;
  array(input.subset_transitions, subsetCount, subsetCount, "subset_transitions");
  const subsetTransitions = input.subset_transitions.map((row) => {
    array(row, automaton.alphabet.length, automaton.alphabet.length, "subset transition row");
    return row.map((id) => integer(id, 0, subsetCount - 1, "subset transition target"));
  });
  array(input.layers, 1, UNIVERSAL_LENGTH_LIMITS.max_families, "layers");
  const preperiod = integer(input.preperiod, 0, input.layers.length - 1, "preperiod");
  const period = integer(input.period, 1, input.layers.length, "period");
  if (preperiod + period !== input.layers.length) throw new TypeError("period does not close the retained layers");
  let memberRows = 0;
  let predecessorRows = 0;
  const familyKeys = new Set();
  const layers = input.layers.map((layer, index) => {
    if (!layer || typeof layer !== "object") throw new TypeError("each layer must be an object");
    array(layer.subset_ids, 1, Math.min(subsetCount, UNIVERSAL_LENGTH_LIMITS.max_family_members), "family");
    const members = layer.subset_ids.map((id) => integer(id, 0, subsetCount - 1, "family subset"));
    for (let j = 1; j < members.length; j++) {
      if (members[j - 1] >= members[j]) throw new TypeError("family subsets must be strictly increasing");
    }
    const key = members.join(",");
    if (familyKeys.has(key)) throw new TypeError("retained families must be distinct");
    familyKeys.add(key);
    memberRows += members.length;
    if (memberRows > UNIVERSAL_LENGTH_LIMITS.max_total_family_members) throw new RangeError("family member cap");
    if (typeof layer.universal !== "boolean") throw new TypeError("universal flag must be Boolean");
    let rejected = null;
    if (layer.universal) {
      if (layer.rejected_subset_id !== null) throw new TypeError("universal layer has a rejection ID");
    } else {
      rejected = integer(layer.rejected_subset_id, 0, subsetCount - 1, "rejected_subset_id");
      if (!members.includes(rejected)) throw new TypeError("rejected subset is outside its family");
    }
    const expectedNext = index + 1 === input.layers.length ? preperiod : index + 1;
    if (layer.next_layer !== expectedNext) throw new TypeError("unexpected retained next_layer");
    array(layer.predecessors, 1, UNIVERSAL_LENGTH_LIMITS.max_family_members, "predecessors");
    predecessorRows += layer.predecessors.length;
    if (predecessorRows > UNIVERSAL_LENGTH_LIMITS.max_total_predecessors) throw new RangeError("predecessor cap");
    const rows = layer.predecessors.map((row) => {
      array(row, 3, 3, "predecessor row");
      return [
        integer(row[0], 0, subsetCount - 1, "predecessor target"),
        integer(row[1], 0, subsetCount - 1, "predecessor source"),
        integer(row[2], 0, automaton.alphabet.length - 1, "predecessor symbol")
      ];
    });
    return {
      subset_ids: members,
      universal: layer.universal,
      rejected_subset_id: rejected,
      next_layer: expectedNext,
      predecessors: rows
    };
  });
  if (layers[0].subset_ids.length !== 1 || layers[0].subset_ids[0] !== 0) {
    throw new TypeError("the initial family must consist of initial_subset_id");
  }
  for (const layer of layers) {
    const nextMembers = layers[layer.next_layer].subset_ids;
    if (layer.predecessors.length !== nextMembers.length) throw new TypeError("incomplete retained predecessor list");
    const previousMembers = new Set(layer.subset_ids);
    for (let i = 0; i < nextMembers.length; i++) {
      const [target, previous, symbol] = layer.predecessors[i];
      if (target !== nextMembers[i] || !previousMembers.has(previous) ||
          subsetTransitions[previous][symbol] !== target) {
        throw new TypeError("inconsistent retained predecessor arc");
      }
    }
  }
  const prefix = [];
  const cycle = [];
  for (let i = 0; i < layers.length; i++) {
    if (layers[i].universal) {
      if (i < preperiod) prefix.push(i);
      else cycle.push(i - preperiod);
    }
  }
  function requireSame(actual, expected, name) {
    array(actual, expected.length, expected.length, name);
    for (let i = 0; i < expected.length; i++) {
      if (actual[i] !== expected[i]) throw new TypeError(name + " disagrees with the retained flags");
    }
  }
  requireSame(input.universal_prefix_lengths, prefix, "universal_prefix_lengths");
  requireSame(input.universal_cycle_offsets, cycle, "universal_cycle_offsets");
  return {
    snapshot: {
      schema: SCHEMA,
      status: "COMPLETE",
      source_id: origin,
      automaton,
      initial_subset_id: 0,
      state_subsets: stateSubsets,
      subset_transitions: subsetTransitions,
      layers,
      preperiod,
      period,
      universal_prefix_lengths: prefix,
      universal_cycle_offsets: cycle
    },
    structural_rows: { state_subsets: subsetCount, families: layers.length, family_members: memberRows,
      predecessors: predecessorRows }
  };
}

function openRetainedUniversalLengthIndex(request) {
  if (!request || typeof request !== "object") throw new TypeError("request must be an object");
  const retainedSource = sourceId(request.source_id, "source_id");
  const validated = validateSnapshot(request.snapshot);
  const saved = validated.snapshot;
  const prefix = saved.universal_prefix_lengths;
  const cycle = saved.universal_cycle_offsets;
  const mu = BigInt(saved.preperiod);
  const lambda = BigInt(saved.period);
  const prefixCount = BigInt(prefix.length);
  const cycleCount = BigInt(cycle.length);
  const stats = {
    restored_rows: validated.structural_rows,
    membership_queries: 0,
    count_queries: 0,
    select_queries: 0,
    rank_queries: 0,
    page_queries: 0,
    returned_page_rows: 0,
    rejected_word_queries: 0,
    witness_steps: 0,
    subset_transition_unions: 0,
    family_transitions_recomputed: 0
  };

  function canonical(length) {
    if (length < mu) return Number(length);
    return saved.preperiod + Number((length - mu) % lambda);
  }

  function countThrough(length) {
    if (length < mu) return BigInt(upperBound(prefix, Number(length)));
    const tail = length - mu;
    return prefixCount + (tail / lambda) * cycleCount +
      BigInt(upperBound(cycle, Number(tail % lambda)));
  }

  function selected(rank) {
    if (rank < prefixCount) return BigInt(prefix[Number(rank)]);
    if (cycle.length === 0) return null;
    const tail = rank - prefixCount;
    return mu + (tail / cycleCount) * lambda + BigInt(cycle[Number(tail % cycleCount)]);
  }

  function lookup(length) {
    const layerId = canonical(length);
    const layer = saved.layers[layerId];
    return {
      length: length.toString(),
      layer_id: layerId,
      in_prefix: length < mu,
      universal: layer.universal,
      reachable_subset_count: layer.subset_ids.length,
      rejected_subset_id: layer.rejected_subset_id
    };
  }

  function predecessorFor(layer, target) {
    const rows = layer.predecessors;
    let lo = 0;
    let hi = rows.length;
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2);
      if (rows[mid][0] < target) lo = mid + 1;
      else hi = mid;
    }
    if (lo === rows.length || rows[lo][0] !== target) {
      throw new Error("retained predecessor is missing");
    }
    return rows[lo];
  }

  return Object.freeze({
    summary() {
      const first = selected(0n);
      return {
        schema: SCHEMA,
        status: "COMPLETE",
        retained_source_id: retainedSource,
        origin_source_id: saved.source_id,
        state_count: saved.automaton.state_count,
        alphabet_size: saved.automaton.alphabet.length,
        state_subset_count: saved.state_subsets.length,
        family_count: saved.layers.length,
        preperiod: saved.preperiod,
        period: saved.period,
        universal_prefix_lengths: prefix.slice(),
        universal_cycle_offsets: cycle.slice(),
        first_universal_length: first === null ? null : first.toString(),
        universal_length_count: cycle.length ?
          { kind: "INFINITE" } : { kind: "FINITE", count: prefixCount.toString() }
      };
    },

    lookupLength(length) {
      const parsed = queryInteger(length, "length");
      stats.membership_queries++;
      return lookup(parsed);
    },

    countUniversalThrough(length) {
      const parsed = queryInteger(length, "length");
      stats.count_queries++;
      return { through: parsed.toString(), inclusive: true, count: countThrough(parsed).toString() };
    },

    selectUniversal(rank) {
      const parsed = queryInteger(rank, "rank");
      stats.select_queries++;
      const length = selected(parsed);
      return length === null ?
        { status: "RANK_OUT_OF_RANGE", rank: parsed.toString(), finite_count: prefixCount.toString() } :
        { status: "FOUND", rank: parsed.toString(), length: length.toString() };
    },

    rankUniversal(length) {
      const parsed = queryInteger(length, "length");
      stats.rank_queries++;
      const universal = saved.layers[canonical(parsed)].universal;
      return {
        status: universal ? "UNIVERSAL" : "NOT_UNIVERSAL",
        length: parsed.toString(),
        rank: universal ? (countThrough(parsed) - 1n).toString() : null
      };
    },

    pageUniversal(request = {}) {
      if (!request || typeof request !== "object") throw new TypeError("page request must be an object");
      const start = queryInteger(request.start_rank === undefined ? "0" : request.start_rank, "start_rank");
      const limit = integer(request.limit === undefined ? 32 : request.limit, 0,
        UNIVERSAL_LENGTH_LIMITS.max_page, "limit");
      stats.page_queries++;
      const items = [];
      for (let i = 0; i < limit; i++) {
        const rank = start + BigInt(i);
        const length = selected(rank);
        if (length === null) break;
        items.push({ rank: rank.toString(), length: length.toString() });
      }
      stats.returned_page_rows += items.length;
      const next = start + BigInt(items.length);
      return {
        status: "OK",
        start_rank: start.toString(),
        items,
        next_rank: next.toString(),
        has_more: cycle.length > 0 || next < prefixCount
      };
    },

    rejectedWord(request) {
      if (!request || typeof request !== "object") throw new TypeError("word request must be an object");
      const length = queryInteger(request.length, "length");
      stats.rejected_word_queries++;
      const info = lookup(length);
      if (info.universal) return { status: "UNIVERSAL", ...info };
      if (length > BigInt(UNIVERSAL_LENGTH_LIMITS.max_word_length)) {
        return { status: "WORD_LENGTH_CAP", ...info, max_word_length: UNIVERSAL_LENGTH_LIMITS.max_word_length };
      }
      let target = info.rejected_subset_id;
      const wordIndices = [];
      const subsetPath = [target];
      for (let step = Number(length); step > 0; step--) {
        // The outgoing map at the actual previous length is essential at a cycle entry.
        const previousLayer = saved.layers[canonical(BigInt(step - 1))];
        const row = predecessorFor(previousLayer, target);
        target = row[1];
        wordIndices.push(row[2]);
        subsetPath.push(target);
        stats.witness_steps++;
      }
      wordIndices.reverse();
      subsetPath.reverse();
      return {
        status: "REJECTED_WORD",
        ...info,
        word_symbol_indices: wordIndices,
        word: wordIndices.map((symbol) => saved.automaton.alphabet[symbol]),
        subset_ids: subsetPath,
        final_subset_mask: saved.state_subsets[info.rejected_subset_id],
        ordering: "deterministic retained predecessor choices; no lexicographic minimum claim"
      };
    },

    snapshot() {
      return clone(saved);
    },

    work() {
      return clone(stats);
    }
  });
}

module.exports = {
  compileUniversalLengthIndex,
  openRetainedUniversalLengthIndex,
  UNIVERSAL_LENGTH_LIMITS
};
