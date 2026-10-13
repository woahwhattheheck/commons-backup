"use strict";
/**
 * Finite alternating-game certificates on an explicit retained transition graph.
 * The caller supplies the graph. This module never computes 3n +/- 1.
 * State 1 is terminal; its supplied edges are provenance, not playable moves.
 */
const VERSION = "1.0.0";
const SCHEMA = "commons.finite-alternating-game.v1";
const MAX_NODES = 1024;
const MAX_STATE = 1000000000000;
const MAX_JSON = 8000000;
function fail(message) { throw new Error(message); }
function copy(x) { return JSON.parse(JSON.stringify(x)); }
function integer(x, name, lo, hi) {
  if (!Number.isSafeInteger(x) || x < lo || x > hi) fail(name + " outside integer contract");
  return x;
}
function odd(x, name) {
  integer(x, name, 1, MAX_STATE);
  if (x % 2 !== 1) fail(name + " must be positive odd");
  return x;
}
function big(x, name) {
  if (typeof x === "bigint") x = x.toString();
  if (typeof x === "number") { integer(x, name, 0, Number.MAX_SAFE_INTEGER); x = String(x); }
  if (typeof x !== "string" || !/^(0|[1-9][0-9]*)$/.test(x) || x.length > 400) fail(name + " must be a canonical nonnegative integer of at most 400 digits");
  return BigInt(x);
}
function graph(input) {
  if (!input || !Array.isArray(input.nodes)) fail("input.nodes required");
  integer(input.nodes.length, "node count", 1, MAX_NODES);
  const nodes = copy(input.nodes), map = new Map();
  let previous = 0;
  for (const node of nodes) {
    odd(node.state, "state");
    if (node.state <= previous) fail("states must be strictly increasing");
    previous = node.state;
    if (!Array.isArray(node.edges) || node.edges.length !== 2) fail("each source node needs exactly two signed edges");
    for (let j = 0; j < 2; j++) {
      if (node.edges[j].sign !== (j === 0 ? -1 : 1)) fail("edges must be ordered by signs -1,+1");
      odd(node.edges[j].target, "target");
    }
    map.set(node.state, node);
  }
  if (!map.has(1)) fail("terminal state 1 must be supplied");
  return { nodes, map };
}
function compileFiniteGame(input) {
  const started = Date.now();
  const { nodes, map } = graph(input);
  const statuses = new Map([[1, { status: "T", remoteness: 0 }]]);
  const layers = [{ depth: 0, states: [1] }];
  let rounds = 0, nodeVisits = 0, edgeVisits = 0;
  for (;;) {
    const pending = [];
    for (const node of nodes) {
      if (statuses.has(node.state)) continue;
      nodeVisits++;
      const targets = node.edges.map(e => { edgeVisits++; return statuses.get(e.target); });
      const losing = targets.filter(t => t && (t.status === "T" || t.status === "L"));
      if (losing.length) {
        pending.push({ state: node.state, status: "W", remoteness: 1 + Math.min(...losing.map(t => t.remoteness)) });
      } else if (targets.every(t => t && t.status === "W")) {
        pending.push({ state: node.state, status: "L", remoteness: 1 + Math.max(...targets.map(t => t.remoteness)) });
      }
    }
    if (!pending.length) break;
    rounds++;
    for (const row of pending) {
      if (row.remoteness !== rounds) fail("internal synchronous-depth invariant");
      statuses.set(row.state, { status: row.status, remoteness: row.remoteness });
    }
    layers.push({ depth: rounds, states: pending.map(r => r.state) });
  }
  const records = [], counts = { T: 0, W: 0, L: 0, U: 0 }, exitTargets = new Set();
  for (const node of nodes) {
    const result = statuses.get(node.state) || { status: "U", remoteness: null };
    counts[result.status]++;
    const moves = node.state === 1 ? [] : node.edges.map(e => {
      const inside = map.has(e.target), t = statuses.get(e.target);
      if (!inside) exitTargets.add(e.target);
      return {
        sign: e.sign, target: e.target, in_domain: inside,
        target_status: t ? t.status : "U",
        target_remoteness: t ? t.remoteness : null
      };
    });
    let choices = [], proof = [];
    if (result.status === "W") {
      proof = moves.filter(m => (m.target_status === "T" || m.target_status === "L") &&
        m.target_remoteness + 1 === result.remoteness);
      choices = proof.map(m => m.sign);
    } else if (result.status === "L") {
      proof = moves;
      choices = moves.filter(m => m.target_remoteness + 1 === result.remoteness).map(m => m.sign);
    } else if (result.status === "U") {
      proof = moves.filter(m => m.target_status === "U");
      choices = proof.map(m => m.sign);
    }
    if (node.state !== 1 && !choices.length) fail("internal nonempty policy invariant");
    records.push({
      state: node.state, status: result.status, remoteness: result.remoteness,
      moves, policy_signs: choices, certificate_moves: proof
    });
  }
  const policyRows = records.filter(r => r.state !== 1);
  const suffix = Array(policyRows.length + 1).fill("1");
  for (let i = policyRows.length - 1; i >= 0; i--)
    suffix[i] = (BigInt(suffix[i + 1]) * BigInt(policyRows[i].policy_signs.length)).toString();
  return {
    schema: SCHEMA, version: VERSION,
    semantics: {
      terminal_state: 1,
      initial_terminal: "already_terminal; no preceding winner is inferred",
      source_terminal_edges: "retained as provenance, overridden by game termination",
      outside: "unresolved in original game; exit stops the explicitly censored game",
      remoteness: "W minimizes time to win; L maximizes delay; synchronous finite proof depth",
      policy: "fastest W, longest-delay L, U-to-U-or-exit; signs -1 before +1",
      unresolved: "not an original-game draw certificate"
    },
    provenance: copy(input.provenance || {}),
    nodes, records, layers,
    policy: {
      states: policyRows.map(r => r.state),
      options: policyRows.map(r => r.policy_signs),
      suffix_counts: suffix, count: suffix[0]
    },
    summary: {
      nodes: nodes.length, retained_source_edges: 2 * nodes.length,
      playable_edges: 2 * (nodes.length - 1), counts,
      greatest_finite_remoteness: rounds,
      unresolved_states: records.filter(r => r.status === "U").map(r => r.state),
      exit_targets: [...exitTargets].sort((a, b) => a - b),
      policy_count: suffix[0]
    },
    construction: {
      synchronous_rounds: rounds, unresolved_node_visits: nodeVisits,
      classification_edge_visits: edgeVisits,
      source_transition_evaluations: 0, source_scc_recomputations: 0,
      stochastic_system_evaluations: 0, elapsed_ms_observation: Date.now() - started
    }
  };
}
function openFiniteGame(value) {
  if (typeof value === "string") {
    if (value.length > MAX_JSON) fail("snapshot exceeds JSON limit");
    value = JSON.parse(value);
  }
  const encoded = JSON.stringify(value);
  if (encoded.length > MAX_JSON) fail("snapshot exceeds JSON limit");
  const snap = JSON.parse(encoded);
  if (!snap || snap.schema !== SCHEMA || snap.version !== VERSION) fail("unsupported snapshot");
  const { nodes } = graph(snap);
  if (!Array.isArray(snap.records) || snap.records.length !== nodes.length) fail("record shape");
  const records = snap.records, byState = new Map();
  for (let i = 0; i < records.length; i++) {
    const r = records[i];
    if (r.state !== nodes[i].state || !["T", "W", "L", "U"].includes(r.status)) fail("record identity/status");
    if ((r.state === 1) !== (r.status === "T")) fail("terminal identity");
    if (r.status === "U") { if (r.remoteness !== null) fail("unresolved remoteness"); }
    else integer(r.remoteness, "remoteness", 0, nodes.length - 1);
    if (!Array.isArray(r.moves) || r.moves.length !== (r.state === 1 ? 0 : 2)) fail("move shape");
    if (!Array.isArray(r.policy_signs) || !Array.isArray(r.certificate_moves)) fail("certificate shape");
    const allowed = r.policy_signs;
    if (r.state === 1 ? allowed.length !== 0 : (allowed.length < 1 || allowed.length > 2)) fail("policy arity");
    if (allowed.some((s, j) => (s !== -1 && s !== 1) || (j && s <= allowed[j - 1]))) fail("policy signs");
    for (let j = 0; j < r.moves.length; j++) {
      const m = r.moves[j], e = nodes[i].edges[j];
      if (m.sign !== e.sign || m.target !== e.target || typeof m.in_domain !== "boolean" ||
          !["T", "W", "L", "U"].includes(m.target_status)) fail("saved move identity");
    }
    byState.set(r.state, r);
  }
  const p = snap.policy;
  if (!p || !Array.isArray(p.states) || !Array.isArray(p.options) || !Array.isArray(p.suffix_counts) ||
      p.states.length !== nodes.length - 1 || p.options.length !== p.states.length ||
      p.suffix_counts.length !== p.states.length + 1) fail("policy shape");
  const policyPosition = new Map();
  let total = 1n;
  if (p.suffix_counts[p.states.length] !== "1") fail("policy terminal count");
  for (let i = p.states.length - 1; i >= 0; i--) {
    const r = records[i + 1];
    if (p.states[i] !== r.state || JSON.stringify(p.options[i]) !== JSON.stringify(r.policy_signs)) fail("policy binding");
    total *= BigInt(p.options[i].length);
    if (big(p.suffix_counts[i], "suffix count") !== total) fail("saved mixed-radix identity");
    policyPosition.set(r.state, i);
  }
  if (big(p.count, "policy count") !== total) fail("total count");
  if (!Array.isArray(snap.layers)) fail("layers shape");
  for (const layer of snap.layers) {
    integer(layer.depth, "depth", 0, nodes.length - 1);
    if (!Array.isArray(layer.states) || layer.states.some(s => !byState.has(s))) fail("layer references");
  }
  const stats = {
    opened_records: records.length, queries: 0, policy_digit_steps: 0,
    playout_steps: 0, classification_recomputations: 0,
    source_transition_evaluations: 0, source_scc_recomputations: 0,
    stochastic_system_evaluations: 0
  };
  function found(state) {
    odd(state, "query state");
    const r = byState.get(state);
    if (!r) fail("state outside retained domain");
    return r;
  }
  function select(rank) {
    rank = big(rank, "rank");
    if (rank >= total) fail("policy rank out of range");
    const original = rank, moves = [];
    for (let i = 0; i < p.states.length; i++) {
      const block = BigInt(p.suffix_counts[i + 1]), digit = Number(rank / block);
      rank %= block;
      moves.push({ state: p.states[i], sign: p.options[i][digit] });
      stats.policy_digit_steps++;
    }
    return { rank: original.toString(), moves };
  }
  return {
    summary() { stats.queries++; return copy(snap.summary); },
    record(state) { stats.queries++; return copy(found(state)); },
    recordsPage(start = 0, limit = 32) {
      stats.queries++; integer(start, "start", 0, records.length); integer(limit, "limit", 1, 64);
      return { start, total: records.length, records: copy(records.slice(start, start + limit)),
        next: Math.min(records.length, start + limit) < records.length ? start + limit : null };
    },
    layer(depth) {
      stats.queries++; integer(depth, "depth", 0, nodes.length - 1);
      return copy(snap.layers.find(l => l.depth === depth) || { depth, states: [] });
    },
    policyCount(restrictions = []) {
      stats.queries++;
      if (!Array.isArray(restrictions) || restrictions.length > p.states.length) fail("restriction shape");
      const seen = new Set(); let count = total;
      for (const v of restrictions) {
        const i = policyPosition.get(v.state);
        if (i === undefined || seen.has(v.state) || (v.sign !== -1 && v.sign !== 1)) fail("restriction state/sign");
        seen.add(v.state);
        count = p.options[i].includes(v.sign) ? count / BigInt(p.options[i].length) : 0n;
      }
      return count.toString();
    },
    selectPolicy(rank) { stats.queries++; return copy(select(rank)); },
    rankPolicy(policy) {
      stats.queries++;
      const moves = Array.isArray(policy) ? policy : policy && policy.moves;
      if (!Array.isArray(moves) || moves.length !== p.states.length) fail("complete policy required");
      let rank = 0n;
      for (let i = 0; i < moves.length; i++) {
        const v = moves[i], digit = p.options[i].indexOf(v.sign);
        if (v.state !== p.states[i] || digit < 0) fail("policy state/sign outside family");
        rank += BigInt(digit) * BigInt(p.suffix_counts[i + 1]);
        stats.policy_digit_steps++;
      }
      return rank.toString();
    },
    play(start, rank) {
      stats.queries++;
      const initial = found(start);
      const parsedRank = big(rank, "rank");
      if (parsedRank >= total) fail("policy rank out of range");
      if (start === 1) return { start, policy_rank: parsedRank.toString(), outcome: "already_terminal", winner: null, trace: [] };
      const policy = select(parsedRank), signs = new Map(policy.moves.map(m => [m.state, m.sign]));
      const trace = [], seen = new Map();
      let state = start, player = 0;
      for (let i = 0; i <= 2 * records.length; i++) {
        const key = state + ":" + player;
        if (seen.has(key)) return { start, policy_rank: policy.rank, initial_status: initial.status,
          outcome: "censored_repetition", winner: null, repeated_state: state,
          repeated_player: player, cycle_start: seen.get(key), trace,
          original_game_status: "unresolved; this policy trace is not an unrestricted draw proof" };
        seen.set(key, trace.length);
        const row = byState.get(state), sign = signs.get(state), move = row.moves.find(m => m.sign === sign);
        if (!move) fail("saved policy has no matching move");
        trace.push({ ply: trace.length + 1, player, state, sign, target: move.target });
        stats.playout_steps++;
        if (move.target === 1) return { start, policy_rank: policy.rank, initial_status: initial.status,
          outcome: "reached_one", winner: player, plies: trace.length, trace };
        if (!byState.has(move.target)) return { start, policy_rank: policy.rank, initial_status: initial.status,
          outcome: "censored_exit", winner: null, exit_target: move.target, trace,
          original_game_status: "unresolved outside retained domain" };
        state = move.target; player = 1 - player;
      }
      fail("saved policy exceeded finite state/turn bound");
    },
    statistics() { return copy(stats); }
  };
}
module.exports = { VERSION, compileFiniteGame, openFiniteGame };
