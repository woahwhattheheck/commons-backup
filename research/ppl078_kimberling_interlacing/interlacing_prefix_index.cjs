"use strict";

/**
 * Exact value-prefix index for Kimberling's interlacing triangles.
 * Primary convention: all labels 1..h(h+1)/2 occur once, and each upper
 * entry is strictly between its two adjacent lower entries. Rows are
 * not required to increase. No runtime dependencies.
 */
const INTERLACING_LIMITS = Object.freeze({
  height: 7,
  states: 65536,
  transitions: 1048576,
  candidate_checks: 2097152,
  count_decimal_digits: 64,
  page_size: 128
});

function integer(value, name, lo, hi) {
  if (!Number.isSafeInteger(value) || value < lo || value > hi)
    throw new RangeError(name + " must be an integer in [" + lo + "," + hi + "]");
  return value;
}

function label(value) {
  if (typeof value !== "string" || value.length === 0 || value.length > 512)
    throw new TypeError("source_id must be a nonempty string of at most 512 code units");
  return value;
}

function natural(value, name) {
  if (typeof value === "bigint") {
    if (value < 0n || value.toString().length > INTERLACING_LIMITS.count_decimal_digits)
      throw new RangeError(name + " is outside the nonnegative decimal bound");
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || value < 0)
      throw new TypeError(name + " Number must be a nonnegative safe integer");
    return BigInt(value);
  }
  if (typeof value !== "string" || !/^(0|[1-9][0-9]*)$/.test(value) ||
      value.length > INTERLACING_LIMITS.count_decimal_digits)
    throw new TypeError(name + " must be a bounded canonical nonnegative integer");
  return BigInt(value);
}

function decimal(value, name) {
  if (typeof value !== "string") throw new TypeError(name + " must be a decimal string");
  natural(value, name);
  return value;
}

function detached(value) { return JSON.parse(JSON.stringify(value)); }

function geometry(height) {
  integer(height, "height", 1, INTERLACING_LIMITS.height);
  const size = height * (height + 1) / 2;
  const cells = [], rules = Array.from({length: size}, () => ({below: null, above: []}));
  const offset = row => row * (row + 1) / 2;
  for (let row = 0; row < height; row++) for (let column = 0; column <= row; column++)
    cells.push({index: offset(row) + column, row, column});
  for (let row = 0; row + 1 < height; row++) for (let column = 0; column <= row; column++) {
    const top = offset(row) + column;
    const left = offset(row + 1) + column, right = left + 1;
    rules[top].below = [2 ** left, 2 ** right];
    rules[left].above.push([2 ** top, 2 ** right]);
    rules[right].above.push([2 ** top, 2 ** left]);
  }
  return {height, size, cells, rules, full: 2 ** size - 1};
}

function allowedAddition(mask, cell, shape, work) {
  const rule = shape.rules[cell];
  if (rule.below) {
    if (work) work.local_clause_checks++;
    const a = (mask & rule.below[0]) !== 0, b = (mask & rule.below[1]) !== 0;
    if (a === b) return false;
  }
  for (const [top, sibling] of rule.above) {
    if (work) work.local_clause_checks++;
    if ((mask & top) === 0 && (mask & sibling) !== 0) return false;
  }
  return true;
}

function budgetOf(input) {
  if (input !== undefined && (input === null || typeof input !== "object" || Array.isArray(input)))
    throw new TypeError("budget must be an object");
  const result = {};
  for (const key of ["states", "transitions", "candidate_checks"])
    result[key] = input && input[key] !== undefined
      ? integer(input[key], "budget." + key, 1, INTERLACING_LIMITS[key])
      : INTERLACING_LIMITS[key];
  if (input) for (const key of Object.keys(input))
    if (!(key in result)) throw new TypeError("Unknown budget field " + key);
  return result;
}

function compileInterlacingPrefixIndex(request) {
  if (!request || typeof request !== "object" || Array.isArray(request))
    throw new TypeError("request must be an object");
  const source_id = label(request.source_id), shape = geometry(request.height);
  const budget = budgetOf(request.budget);
  const work = {
    candidate_checks: 0, local_clause_checks: 0, transitions: 0,
    forward_count_additions: 0, suffix_count_additions: 0,
    marginal_weight_products: 0, marginal_count_additions: 0
  };
  const nodes = [{mask: 0, depth: 0, edges: []}], byMask = new Map([[0, 0]]);
  function partial(reason, node, cell) {
    return {
      schema: "kimberling.interlacing_partial/v1",
      status: "RESOURCE_LIMIT", source_id, height: shape.height, cell_count: shape.size,
      stop: {reason, completed_nodes: node, partial_node_index: node, next_cell: cell},
      budget, work: {...work},
      graph_rows: nodes.map(n => [n.mask.toString(16), n.depth, n.edges.map(e => e.slice())]),
      graph_columns: ["prefix_mask_hex", "assigned_labels", "outgoing_cell_and_node_index"],
      exact_total_count: null,
      scope: "Discovered graph only; the partial node may have an unfinished outgoing row. No completion counts were claimed."
    };
  }
  for (let at = 0; at < nodes.length; at++) {
    const node = nodes[at];
    for (let cell = 0; cell < shape.size; cell++) {
      const bit = 2 ** cell;
      if ((node.mask & bit) !== 0) continue;
      if (work.candidate_checks === budget.candidate_checks)
        return partial("candidate_checks", at, cell);
      work.candidate_checks++;
      if (!allowedAddition(node.mask, cell, shape, work)) continue;
      if (work.transitions === budget.transitions) return partial("transitions", at, cell);
      const childMask = node.mask + bit;
      let child = byMask.get(childMask);
      if (child === undefined) {
        if (nodes.length === budget.states) return partial("states", at, cell);
        child = nodes.length;
        byMask.set(childMask, child);
        nodes.push({mask: childMask, depth: node.depth + 1, edges: []});
      }
      node.edges.push([cell, child]);
      work.transitions++;
    }
  }
  const terminal = byMask.get(shape.full);
  if (terminal === undefined) throw new Error("Complete traversal lacks the full prefix");
  const forward = Array(nodes.length).fill(0n), suffix = Array(nodes.length).fill(0n);
  forward[0] = 1n;
  for (let at = 0; at < nodes.length; at++) for (const [, child] of nodes[at].edges) {
    forward[child] += forward[at];
    work.forward_count_additions++;
  }
  suffix[terminal] = 1n;
  for (let at = nodes.length - 1; at >= 0; at--) for (const [, child] of nodes[at].edges) {
    suffix[at] += suffix[child];
    work.suffix_count_additions++;
  }
  const marginal = Array.from({length: shape.size}, () => Array(shape.size).fill(0n));
  const layers = Array.from({length: shape.size + 1}, (_, assigned_labels) =>
    ({assigned_labels, prefix_states: 0}));
  for (let at = 0; at < nodes.length; at++) {
    const node = nodes[at];
    layers[node.depth].prefix_states++;
    for (const [cell, child] of node.edges) {
      marginal[cell][node.depth] += forward[at] * suffix[child];
      work.marginal_weight_products++;
      work.marginal_count_additions++;
    }
  }
  const records = nodes.map((node, index) =>
    [node.mask.toString(16), forward[index].toString(), suffix[index].toString()]);
  records.sort((a, b) => parseInt(a[0], 16) - parseInt(b[0], 16));
  const snapshot = {
    schema: "kimberling.interlacing_prefix_index/v1",
    source_id, height: shape.height, cell_count: shape.size,
    ordering: "zero-based lexicographic order of row-major cell indices occupied by labels 1,2,...,N",
    prefix_mask_convention: "bit c is one exactly when row-major cell c already holds one of the assigned smallest labels",
    record_columns: ["prefix_mask_hex", "ways_to_reach_prefix", "ways_to_complete_prefix"],
    cell_coordinates: shape.cells,
    total_count: suffix[0].toString(),
    state_count: nodes.length, transition_count: work.transitions,
    layer_state_counts: layers,
    cell_value_counts: marginal.map(row => row.map(x => x.toString())),
    records
  };
  return {
    schema: "kimberling.interlacing_compilation/v1",
    status: "EXACT_PREFIX_INDEX", source_id, height: shape.height, cell_count: shape.size,
    total_count: snapshot.total_count, state_count: nodes.length,
    transition_count: work.transitions, budget, work, snapshot,
    scope: "Exact finite height. No closed-form enumeration, asymptotic, novelty, or external-frontier claim."
  };
}

function openRetainedInterlacingPrefixIndex(request) {
  if (!request || typeof request !== "object" || Array.isArray(request))
    throw new TypeError("request must be an object");
  const source_id = label(request.source_id), saved = request.snapshot;
  if (!saved || saved.schema !== "kimberling.interlacing_prefix_index/v1")
    throw new TypeError("A complete interlacing prefix snapshot is required");
  const shape = geometry(saved.height);
  if (saved.cell_count !== shape.size) throw new RangeError("cell_count disagrees with height");
  if (saved.ordering !== "zero-based lexicographic order of row-major cell indices occupied by labels 1,2,...,N")
    throw new RangeError("Snapshot ordering does not match this interface");
  label(saved.source_id);
  integer(saved.state_count, "state_count", 1, INTERLACING_LIMITS.states);
  integer(saved.transition_count, "transition_count", 0, INTERLACING_LIMITS.transitions);
  const total = natural(decimal(saved.total_count, "total_count"), "total_count");
  if (!Array.isArray(saved.records) || saved.records.length !== saved.state_count)
    throw new RangeError("records must have the stated state_count");
  const byMask = new Map();
  let previous = -1;
  for (let row = 0; row < saved.records.length; row++) {
    const record = saved.records[row];
    if (!Array.isArray(record) || record.length !== 3 || typeof record[0] !== "string" ||
        !/^(0|[1-9a-f][0-9a-f]*)$/.test(record[0]) || record[0].length > 7)
      throw new TypeError("Invalid prefix record at row " + row);
    const mask = parseInt(record[0], 16);
    if (!Number.isSafeInteger(mask) || mask <= previous || mask > shape.full)
      throw new RangeError("Prefix masks must be strictly increasing within the finite cell mask");
    const prefix = natural(decimal(record[1], "prefix count"), "prefix count");
    const suffix = natural(decimal(record[2], "suffix count"), "suffix count");
    byMask.set(mask, {prefix, suffix});
    previous = mask;
  }
  if (!byMask.has(0) || !byMask.has(shape.full))
    throw new RangeError("The empty and full prefix records are required");
  if (!Array.isArray(saved.cell_value_counts) || saved.cell_value_counts.length !== shape.size ||
      saved.cell_value_counts.some(row => !Array.isArray(row) || row.length !== shape.size))
    throw new RangeError("cell_value_counts must be a square N by N array");
  for (const row of saved.cell_value_counts) for (const count of row) decimal(count, "marginal count");
  const snapshot = detached(saved);
  const boundary = {
    source_id, snapshot_source_id: saved.source_id,
    source_authenticated: false, prefix_admissibility_rechecked: false,
    state_coverage_recomputed: false, count_recurrences_replayed: false,
    marginal_counts_recomputed: false,
    validation: "Bounded shapes, integer encodings, ordering and required endpoints only. Saved mathematics and completeness remain a trusted source premise."
  };
  function nextOptions(mask) {
    const options = [];
    for (let cell = 0; cell < shape.size; cell++) {
      const bit = 2 ** cell;
      if ((mask & bit) !== 0 || !allowedAddition(mask, cell, shape)) continue;
      const childMask = mask + bit, row = byMask.get(childMask);
      if (!row) throw new Error("Retained premise lacks a required successor prefix");
      options.push({cell, mask: childMask, count: row.suffix});
    }
    return options;
  }
  function prefixPositions(positions) {
    if (!Array.isArray(positions) || positions.length > shape.size)
      throw new TypeError("label_positions must contain at most N row-major cell indices");
    let mask = 0;
    for (let at = 0; at < positions.length; at++) {
      const cell = integer(positions[at], "label_positions[" + at + "]", 0, shape.size - 1);
      const bit = 2 ** cell;
      if ((mask & bit) !== 0)
        return {valid: false, first_invalid_label: at + 1, reason: "cell_reused"};
      if (!allowedAddition(mask, cell, shape))
        return {valid: false, first_invalid_label: at + 1, reason: "interlacing_prefix_violation"};
      mask += bit;
      if (!byMask.has(mask)) throw new Error("Retained premise lacks this valid prefix");
    }
    return {valid: true, mask};
  }
  function select(input) {
    if (!input || typeof input !== "object") throw new TypeError("select requires {rank}");
    const requested = natural(input.rank, "rank");
    if (requested >= total) throw new RangeError("rank is outside the retained complete count");
    let remaining = requested, mask = 0;
    const positions = [], branch_trace = [], values = Array(shape.size).fill(0);
    for (let value = 1; value <= shape.size; value++) {
      let chosen = null, skipped = 0n;
      for (const option of nextOptions(mask)) {
        if (remaining < option.count) { chosen = option; break; }
        remaining -= option.count; skipped += option.count;
      }
      if (!chosen) throw new Error("Retained branch counts do not cover the requested rank");
      positions.push(chosen.cell); values[chosen.cell] = value;
      branch_trace.push({label: value, cell: chosen.cell, prior_branch_count: skipped.toString(),
        chosen_branch_count: chosen.count.toString(), rank_within_branch: remaining.toString()});
      mask = chosen.mask;
    }
    const rows = [];
    for (let row = 0, at = 0; row < shape.height; row++) {
      rows.push(values.slice(at, at + row + 1)); at += row + 1;
    }
    return {status: "SELECTED", rank: requested.toString(), rows, label_positions: positions,
      branch_trace, source_id, retained_counts_reused: true};
  }
  function rank(rows) {
    if (!Array.isArray(rows) || rows.length !== shape.height ||
        rows.some((row, index) => !Array.isArray(row) || row.length !== index + 1))
      throw new TypeError("rows must have lengths 1,2,...,height");
    const positions = Array(shape.size).fill(-1);
    let cell = 0;
    for (const row of rows) for (const value of row) {
      integer(value, "array label", 1, shape.size);
      if (positions[value - 1] !== -1) throw new RangeError("array labels must be distinct");
      positions[value - 1] = cell++;
    }
    let answer = 0n, mask = 0;
    for (let at = 0; at < positions.length; at++) {
      let chosen = null;
      for (const option of nextOptions(mask)) {
        if (option.cell === positions[at]) { chosen = option; break; }
        if (option.cell < positions[at]) answer += option.count;
      }
      if (!chosen || chosen.count === 0n)
        return {status: "INVALID_ARRAY", first_invalid_label: at + 1,
          reason: "interlacing_prefix_violation", source_id};
      mask = chosen.mask;
    }
    return {status: "RANKED", rank: answer.toString(), label_positions: positions,
      source_id, retained_counts_reused: true};
  }
  return Object.freeze({
    describe() {
      return {status: "OPEN_RETAINED_INDEX", height: shape.height, cell_count: shape.size,
        total_count: snapshot.total_count, state_count: snapshot.state_count,
        transition_count: snapshot.transition_count, ordering: snapshot.ordering,
        boundary: detached(boundary)};
    },
    countCompletions(input) {
      if (!input || typeof input !== "object") throw new TypeError("countCompletions requires {label_positions}");
      const p = prefixPositions(input.label_positions);
      if (!p.valid) return {status: "INVALID_PREFIX", ...p, source_id};
      const row = byMask.get(p.mask);
      return {status: "COUNTED_PREFIX", assigned_labels: input.label_positions.length,
        prefix_mask_hex: p.mask.toString(16), completion_count: row.suffix.toString(),
        all_prefix_orders_to_this_mask: row.prefix.toString(), source_id,
        boundary: "completion_count is for this one supplied valid prefix order; the other prefix orders are not multiplied into it"};
    },
    cellValueCounts(input) {
      if (!input || typeof input !== "object") throw new TypeError("cellValueCounts requires {row,column}");
      const row = integer(input.row, "row", 0, shape.height - 1);
      const column = integer(input.column, "column", 0, row);
      const cell = row * (row + 1) / 2 + column;
      return {status: "RETAINED_CELL_MARGINAL", cell, row, column,
        counts_by_label_1_through_N: snapshot.cell_value_counts[cell].slice(), source_id};
    },
    select, rank,
    page(input = {}) {
      const start = natural(input.start_rank === undefined ? 0 : input.start_rank, "start_rank");
      if (start > total) throw new RangeError("start_rank exceeds the retained count");
      const limit = integer(input.limit === undefined ? 32 : input.limit, "limit", 1, INTERLACING_LIMITS.page_size);
      const entries = [];
      let at = start;
      while (at < total && entries.length < limit) { entries.push(select({rank: at})); at++; }
      return {start_rank: start.toString(), entries, next_rank: at < total ? at.toString() : null,
        total_count: total.toString(), source_id};
    },
    snapshot() { return detached(snapshot); }
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {compileInterlacingPrefixIndex, openRetainedInterlacingPrefixIndex,
    INTERLACING_LIMITS};
}
