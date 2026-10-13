"use strict";

// Exact finite integer-plane line incidence, with reusable subset views.
// Coordinates use BigInt internally. Counts and point/line IDs are bounded
// small integers. This module performs no I/O and imports no dependencies.

const LIMITS = Object.freeze({
  max_input_points: 512,
  max_distinct_points: 256,
  max_coordinate_digits: 128,
  max_coefficient_digits: 257,
  max_page_size: 1000,
  max_pairs: 32640
});

function object(value, name) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(name + " must be an object");
  }
  return value;
}

function integer(value, name, minimum, maximum) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new RangeError(name + " must be a safe integer in [" + minimum + ", " + maximum + "]");
  }
  return value;
}

function coordinate(value, name, digitLimit = LIMITS.max_coordinate_digits) {
  let text;
  if (typeof value === "bigint") text = value.toString();
  else if (typeof value === "number" && Number.isSafeInteger(value)) text = String(value);
  else if (typeof value === "string" && /^(?:0|-?[1-9][0-9]*)$/.test(value)) text = value;
  else throw new TypeError(name + " must be a canonical integer string, BigInt, or safe integer");
  const digits = text[0] === "-" ? text.length - 1 : text.length;
  if (digits > digitLimit) throw new RangeError(name + " exceeds the coordinate digit limit");
  return BigInt(text);
}

function compareInteger(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}

function chooseTwo(n) {
  return n * (n - 1) / 2;
}

function gcdPlain(a, b) {
  if (a < 0n) a = -a;
  if (b < 0n) b = -b;
  while (b !== 0n) {
    const next = a % b;
    a = b;
    b = next;
  }
  return a;
}

function ratio(numerator, denominator) {
  if (denominator === 0) return null;
  let a = BigInt(numerator), b = BigInt(denominator);
  const divisor = gcdPlain(a, b);
  a /= divisor;
  b /= divisor;
  return { numerator: a.toString(), denominator: b.toString() };
}

function page(items, options, copy) {
  const opts = options === undefined ? {} : object(options, "page options");
  const offset = opts.offset === undefined ? 0 : integer(opts.offset, "offset", 0, Number.MAX_SAFE_INTEGER);
  const limit = opts.limit === undefined ? 100 : integer(opts.limit, "limit", 1, LIMITS.max_page_size);
  const start = Math.min(offset, items.length);
  const end = Math.min(start + limit, items.length);
  return {
    offset,
    limit,
    total: items.length,
    returned: end - start,
    next_offset: end < items.length ? end : null,
    items: items.slice(start, end).map(copy)
  };
}

function createIntegerLineIncidenceIndex(options) {
  const opts = object(options, "options");
  const restoring = Object.prototype.hasOwnProperty.call(opts, "snapshot");
  if (restoring && opts.points !== undefined) throw new TypeError("supply points or snapshot, not both");
  const work = { pair_constructions: 0, gcd_calls: 0, gcd_remainder_steps: 0 };
  function gcd(a, b) {
    work.gcd_calls++;
    if (a < 0n) a = -a;
    if (b < 0n) b = -b;
    while (b !== 0n) {
      work.gcd_remainder_steps++;
      const next = a % b;
      a = b;
      b = next;
    }
    return a;
  }
  let points, lines, allIds, sourceLineCount, baseMetadata;

  if (restoring) {
    const saved = object(opts.snapshot, "snapshot");
    if (saved.schema !== "erdos588.integer_line_snapshot/v1") throw new TypeError("unsupported snapshot schema");
    const description = object(saved.description, "snapshot description");
    const sourcePointCount = integer(description.source_point_count, "source_point_count", 0, LIMITS.max_distinct_points);
    sourceLineCount = integer(description.source_line_count, "source_line_count", 0, LIMITS.max_pairs);
    if (!Array.isArray(saved.points) || saved.points.length > LIMITS.max_distinct_points) {
      throw new RangeError("snapshot points must be a bounded array");
    }
    if (!Array.isArray(saved.lines) || saved.lines.length > LIMITS.max_pairs) {
      throw new RangeError("snapshot lines must be a bounded array");
    }
    points = Array(sourcePointCount);
    allIds = [];
    let previousId = -1, previousPoint = null;
    for (const value of saved.points) {
      const p = object(value, "snapshot point");
      const id = integer(p.point_id, "point_id", 0, Math.max(0, sourcePointCount - 1));
      if (sourcePointCount === 0 || id <= previousId) throw new RangeError("snapshot point IDs must be strictly increasing");
      const point = { x: coordinate(p.x, "point.x"), y: coordinate(p.y, "point.y") };
      if (previousPoint && (compareInteger(previousPoint.x, point.x) || compareInteger(previousPoint.y, point.y)) >= 0) {
        throw new RangeError("snapshot points must be distinct and lexicographically increasing");
      }
      points[id] = point;
      allIds.push(id);
      previousId = id;
      previousPoint = point;
    }
    if (description.point_count !== allIds.length) throw new RangeError("snapshot point_count does not match its points");
    const available = new Set(allIds);
    lines = [];
    let previousLineId = -1, previousCoefficients = null;
    work.line_records_validated = 0;
    work.point_line_checks = 0;
    for (const value of saved.lines) {
      const line = object(value, "snapshot line");
      const id = integer(line.line_id, "line_id", 0, Math.max(0, sourceLineCount - 1));
      if (sourceLineCount === 0 || id <= previousLineId) throw new RangeError("snapshot line IDs must be strictly increasing");
      const a = coordinate(line.a, "line.a", LIMITS.max_coefficient_digits);
      const b = coordinate(line.b, "line.b", LIMITS.max_coefficient_digits);
      const c = coordinate(line.c, "line.c", LIMITS.max_coefficient_digits);
      if (a < 0n || (a === 0n && b <= 0n) || gcd(gcd(a, b), c) !== 1n) {
        throw new RangeError("snapshot line coefficients must be nonzero, primitive, and sign-normalized");
      }
      if (previousCoefficients && (
        compareInteger(previousCoefficients.a, a) ||
        compareInteger(previousCoefficients.b, b) ||
        compareInteger(previousCoefficients.c, c)
      ) >= 0) throw new RangeError("snapshot lines must have distinct coefficients in canonical order");
      if (!Array.isArray(line.point_ids) || line.point_ids.length < 2 || line.point_ids.length > allIds.length) {
        throw new RangeError("snapshot line point_ids must contain at least two available points");
      }
      const pointIds = [];
      let previousPointId = -1;
      for (const pointId of line.point_ids) {
        integer(pointId, "line point_id", 0, Math.max(0, sourcePointCount - 1));
        if (pointId <= previousPointId || !available.has(pointId)) throw new RangeError("line point IDs must be increasing and available");
        const p = points[pointId];
        work.point_line_checks++;
        if (a * p.x + b * p.y + c !== 0n) throw new RangeError("snapshot point does not lie on its stated line");
        pointIds.push(pointId);
        previousPointId = pointId;
      }
      const pairs = chooseTwo(pointIds.length);
      if (line.multiplicity !== pointIds.length || line.unordered_point_pairs !== pairs) {
        throw new RangeError("snapshot line counts do not match its incidence list");
      }
      lines.push({ id, a: a.toString(), b: b.toString(), c: c.toString(), pointIds, unorderedPairs: pairs });
      previousLineId = id;
      previousCoefficients = { a, b, c };
      work.line_records_validated++;
    }
    baseMetadata = {
      kind: "restored",
      parent_point_count: null,
      input_entries: allIds.length,
      duplicates_removed: 0,
      work
    };
  } else {
    const supplied = opts.points;
    if (!Array.isArray(supplied)) throw new TypeError("points must be an array");
    if (supplied.length > LIMITS.max_input_points) throw new RangeError("too many input point entries");
    const unique = new Map();
    for (let index = 0; index < supplied.length; index++) {
      const p = supplied[index];
      if (!Array.isArray(p) || p.length !== 2) throw new TypeError("each point must be [x,y]");
      const x = coordinate(p[0], "points[" + index + "][0]");
      const y = coordinate(p[1], "points[" + index + "][1]");
      const key = x.toString() + "," + y.toString();
      if (!unique.has(key)) unique.set(key, { x, y });
    }
    if (unique.size > LIMITS.max_distinct_points) throw new RangeError("too many distinct points");
    points = [...unique.values()].sort((p, q) => compareInteger(p.x, q.x) || compareInteger(p.y, q.y));
    if (chooseTwo(points.length) > LIMITS.max_pairs) throw new RangeError("pair budget exceeded");
    const byLine = new Map();
    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        work.pair_constructions++;
        const p = points[i], q = points[j];
        let a = p.y - q.y;
        let b = q.x - p.x;
        let c = p.x * q.y - q.x * p.y;
        const divisor = gcd(gcd(a, b), c);
        a /= divisor;
        b /= divisor;
        c /= divisor;
        if (a < 0n || (a === 0n && b < 0n)) {
          a = -a;
          b = -b;
          c = -c;
        }
        const key = a.toString() + "," + b.toString() + "," + c.toString();
        let line = byLine.get(key);
        if (!line) {
          line = { a, b, c, pointIds: new Set(), observedPairs: 0 };
          byLine.set(key, line);
        }
        line.pointIds.add(i);
        line.pointIds.add(j);
        line.observedPairs++;
      }
    }
    const ordered = [...byLine.values()].sort((u, v) =>
      compareInteger(u.a, v.a) || compareInteger(u.b, v.b) || compareInteger(u.c, v.c));
    lines = ordered.map((line, id) => {
      const pointIds = [...line.pointIds].sort((a, b) => a - b);
      if (line.observedPairs !== chooseTwo(pointIds.length)) {
        throw new Error("internal line pair-accounting invariant failed");
      }
      return {
        id,
        a: line.a.toString(),
        b: line.b.toString(),
        c: line.c.toString(),
        pointIds,
        unorderedPairs: line.observedPairs
      };
    });
    allIds = points.map((_, id) => id);
    sourceLineCount = lines.length;
    baseMetadata = {
      kind: "compiled",
      parent_point_count: null,
      input_entries: supplied.length,
      duplicates_removed: supplied.length - points.length,
      work
    };
  }

  function copyPoint(id) {
    return { point_id: id, x: points[id].x.toString(), y: points[id].y.toString() };
  }
  function copyLine(line) {
    return {
      line_id: line.id,
      a: line.a,
      b: line.b,
      c: line.c,
      point_ids: line.pointIds.slice(),
      multiplicity: line.pointIds.length,
      unordered_point_pairs: line.unorderedPairs
    };
  }

  function makeView(pointIds, records, metadata) {
    const selected = new Set(pointIds);
    const n = pointIds.length;
    const exact = Array(n + 2).fill(0);
    let maximum = n === 0 ? 0 : 1;
    let representedPairs = 0, incidenceCount = 0;
    for (const line of records) {
      const count = line.pointIds.length;
      exact[count]++;
      maximum = Math.max(maximum, count);
      representedPairs += line.unorderedPairs;
      incidenceCount += count;
    }
    if (representedPairs !== chooseTwo(n)) throw new Error("internal view pair-accounting invariant failed");
    const cumulative = Array(n + 3).fill(0);
    for (let k = n; k >= 2; k--) cumulative[k] = cumulative[k + 1] + exact[k];

    function describe() {
      return {
        schema: "erdos588.integer_line_view/v1",
        kind: metadata.kind,
        source_point_count: points.length,
        source_line_count: sourceLineCount,
        parent_point_count: metadata.parent_point_count,
        point_count: n,
        determined_line_count: records.length,
        maximum_collinearity: maximum,
        unordered_point_pairs: chooseTwo(n),
        represented_unordered_point_pairs: representedPairs,
        point_line_incidences: incidenceCount,
        input_entries: metadata.input_entries,
        duplicates_removed: metadata.duplicates_removed,
        work: { ...metadata.work }
      };
    }

    function profile() {
      const rows = [];
      for (let k = 2; k <= maximum; k++) {
        rows.push({ multiplicity: k, exact_lines: exact[k] || 0, at_least_lines: cumulative[k] || 0 });
      }
      return { point_count: n, maximum_collinearity: maximum, rows };
    }

    function linePage(options) {
      const args = options === undefined ? {} : object(options, "line page options");
      const minimum = args.min_points === undefined ? 2 : integer(args.min_points, "min_points", 2, Number.MAX_SAFE_INTEGER);
      const maximumRequested = args.max_points === undefined ? Number.MAX_SAFE_INTEGER :
        integer(args.max_points, "max_points", minimum, Number.MAX_SAFE_INTEGER);
      const chosen = minimum === 2 && maximumRequested >= n ? records :
        records.filter(line => line.pointIds.length >= minimum && line.pointIds.length <= maximumRequested);
      return page(chosen, args, copyLine);
    }

    function assess(options) {
      const args = object(options, "assessment options");
      const k = integer(args.k, "k", 4, Number.MAX_SAFE_INTEGER);
      const exactCount = k <= n ? exact[k] || 0 : 0;
      const atLeastCount = k <= n ? cumulative[k] || 0 : 0;
      const tooMany = k < n ? cumulative[k + 1] || 0 : 0;
      const admissible = maximum <= k;
      const first = tooMany === 0 ? null : records.find(line => line.pointIds.length > k);
      return {
        point_count: n,
        k,
        property_P_k: admissible,
        exact_k_lines: exactCount,
        at_least_k_lines: atLeastCount,
        overfull_line_count: tooMany,
        first_overfull_line: first ? copyLine(first) : null,
        exact_k_over_n_squared: ratio(exactCount, n * n),
        finite_extremal_lower_bound: admissible && n > 0 ? {
          notation: "f_k(n)",
          n,
          k,
          at_least: exactCount
        } : null,
        extremality_claimed: false,
        asymptotic_claimed: false
      };
    }

    function subset(options) {
      const args = object(options, "subset options");
      if (!Array.isArray(args.point_ids)) throw new TypeError("point_ids must be an array");
      if (args.point_ids.length > LIMITS.max_input_points) throw new RangeError("too many point-id entries");
      const wanted = new Set();
      for (const id of args.point_ids) {
        integer(id, "point_id", 0, Math.max(0, points.length - 1));
        if (!selected.has(id)) throw new RangeError("point_id is outside the current view");
        wanted.add(id);
      }
      const ids = [...wanted].sort((a, b) => a - b);
      const kept = [];
      let membershipReads = 0;
      for (const line of records) {
        const inside = [];
        for (const id of line.pointIds) {
          membershipReads++;
          if (wanted.has(id)) inside.push(id);
        }
        if (inside.length >= 2) {
          kept.push({
            id: line.id,
            a: line.a,
            b: line.b,
            c: line.c,
            pointIds: inside,
            unorderedPairs: chooseTwo(inside.length)
          });
        }
      }
      return makeView(ids, kept, {
        kind: "subset",
        parent_point_count: n,
        input_entries: args.point_ids.length,
        duplicates_removed: args.point_ids.length - ids.length,
        work: {
          pair_constructions: 0,
          gcd_calls: 0,
          gcd_remainder_steps: 0,
          parent_line_records_scanned: records.length,
          point_membership_reads: membershipReads
        }
      });
    }

    function snapshot() {
      return {
        schema: "erdos588.integer_line_snapshot/v1",
        description: describe(),
        profile: profile(),
        points: pointIds.map(copyPoint),
        lines: records.map(copyLine)
      };
    }

    return Object.freeze({
      describe,
      profile,
      assess,
      pointPage(options) { return page(pointIds, options, copyPoint); },
      linePage,
      subset,
      snapshot
    });
  }

  return makeView(allIds, lines, baseMetadata);
}

module.exports = Object.freeze({ createIntegerLineIncidenceIndex, LIMITS });
