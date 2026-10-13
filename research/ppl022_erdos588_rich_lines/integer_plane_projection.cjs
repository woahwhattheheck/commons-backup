"use strict";

// Exact finite-set projection; see INTEGER_PLANE_PROJECTION_API.md.
const PROJECTION_LIMITS = Object.freeze({
  min_dimension: 1,
  max_dimension: 8,
  max_input_points: 512,
  max_distinct_points: 256,
  max_input_coordinate_digits: 128,
  max_output_coordinate_digits: 128
});

const OUTPUT_LIMIT = 10n ** BigInt(PROJECTION_LIMITS.max_output_coordinate_digits) - 1n;

function integerCoordinate(value, label) {
  let text;
  if (typeof value === "bigint") {
    text = value.toString();
  } else if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) {
      throw new TypeError(label + " must be a safe integer Number");
    }
    text = BigInt(value).toString();
  } else if (typeof value === "string") {
    if (!/^(?:0|-?[1-9][0-9]*)$/.test(value)) {
      throw new TypeError(label + " must be a canonical integer string");
    }
    text = value;
  } else {
    throw new TypeError(label + " must be an integer string, BigInt or safe Number");
  }
  const digits = text[0] === "-" ? text.length - 1 : text.length;
  if (digits > PROJECTION_LIMITS.max_input_coordinate_digits) {
    throw new RangeError(label + " exceeds the input coordinate digit limit");
  }
  return BigInt(text);
}

/**
 * Translate a bounded integer point set coordinatewise to zero minima, then use
 * X = sum z_i * t^i and Y = sum z_i * t^(dimension*i), where
 * t = max(2, 2*D^2 + 1) and D is the largest coordinate span.
 *
 * Integer coefficient dominance proves injectivity and preservation of every
 * collinear/noncollinear triple. No pairs or triples are enumerated here.
 */
function projectIntegerPointsToPlane(options) {
  if (options === null || typeof options !== "object" || Array.isArray(options)) {
    throw new TypeError("options must be an object");
  }
  const dimension = options.dimension;
  if (!Number.isSafeInteger(dimension) ||
      dimension < PROJECTION_LIMITS.min_dimension ||
      dimension > PROJECTION_LIMITS.max_dimension) {
    throw new RangeError("dimension must be an integer from 1 through 8");
  }
  if (!Array.isArray(options.points)) {
    throw new TypeError("points must be an array");
  }
  if (options.points.length > PROJECTION_LIMITS.max_input_points) {
    throw new RangeError("too many input point entries");
  }

  const work = {
    input_coordinate_values: 0,
    translated_coordinate_values: 0,
    horner_accumulator_initializations: 0,
    horner_multiplications: 0,
    horner_additions: 0,
    point_pairs_enumerated: 0,
    point_triples_enumerated: 0
  };
  const unique = new Map();
  const inputKeys = [];
  for (let index = 0; index < options.points.length; index++) {
    const point = options.points[index];
    if (!Array.isArray(point) || point.length !== dimension) {
      throw new TypeError("point " + index + " must have exactly dimension coordinates");
    }
    const coordinates = [];
    for (let coordinate = 0; coordinate < dimension; coordinate++) {
      coordinates.push(integerCoordinate(point[coordinate],
        "point " + index + ", coordinate " + coordinate));
      work.input_coordinate_values++;
    }
    const key = coordinates.map(String).join(",");
    inputKeys.push(key);
    if (!unique.has(key)) {
      unique.set(key, coordinates);
      if (unique.size > PROJECTION_LIMITS.max_distinct_points) {
        throw new RangeError("too many distinct points");
      }
    }
  }

  const sorted = [...unique.entries()].sort((left, right) => {
    for (let i = 0; i < dimension; i++) {
      if (left[1][i] < right[1][i]) return -1;
      if (left[1][i] > right[1][i]) return 1;
    }
    return 0;
  });
  const minimum = Array(dimension).fill(0n);
  const maximum = Array(dimension).fill(0n);
  if (sorted.length) {
    for (let i = 0; i < dimension; i++) {
      minimum[i] = sorted[0][1][i];
      maximum[i] = sorted[0][1][i];
    }
    for (const [, point] of sorted) {
      for (let i = 0; i < dimension; i++) {
        if (point[i] < minimum[i]) minimum[i] = point[i];
        if (point[i] > maximum[i]) maximum[i] = point[i];
      }
    }
  }

  const spans = minimum.map((value, i) => maximum[i] - value);
  let largestSpan = 0n;
  for (const span of spans) if (span > largestSpan) largestSpan = span;
  // Some translated coordinate equals largestSpan, and X is a sum of
  // nonnegative digits times positive powers. This early rejection is exact.
  if (largestSpan > OUTPUT_LIMIT) {
    throw new RangeError("the translated coordinate span exceeds the output digit limit");
  }
  const coefficientBound = 2n * largestSpan * largestSpan;
  const base = coefficientBound + 1n > 2n ? coefficientBound + 1n : 2n;
  const multiplicationLimit = OUTPUT_LIMIT / base;

  function boundedHorner(coordinates, step, label) {
    let accumulator = coordinates[dimension - 1];
    work.horner_accumulator_initializations++;
    if (accumulator > OUTPUT_LIMIT) {
      throw new RangeError(label + " exceeds the output coordinate digit limit");
    }
    for (let i = dimension - 2; i >= 0; i--) {
      for (let j = 0; j < step; j++) {
        if (accumulator > multiplicationLimit) {
          throw new RangeError(label + " exceeds the output coordinate digit limit");
        }
        accumulator *= base;
        work.horner_multiplications++;
      }
      if (coordinates[i] > OUTPUT_LIMIT - accumulator) {
        throw new RangeError(label + " exceeds the output coordinate digit limit");
      }
      accumulator += coordinates[i];
      work.horner_additions++;
    }
    return accumulator;
  }

  const keyToId = new Map();
  const records = [];
  let outputMinimum = null;
  let outputMaximum = null;
  for (let id = 0; id < sorted.length; id++) {
    const [key, original] = sorted[id];
    keyToId.set(key, id);
    const translated = original.map((value, i) => value - minimum[i]);
    work.translated_coordinate_values += dimension;
    const x = boundedHorner(translated, 1, "projected x for source point " + id);
    const y = boundedHorner(translated, dimension, "projected y for source point " + id);
    if (outputMinimum === null) {
      outputMinimum = [x, y];
      outputMaximum = [x, y];
    } else {
      if (x < outputMinimum[0]) outputMinimum[0] = x;
      if (y < outputMinimum[1]) outputMinimum[1] = y;
      if (x > outputMaximum[0]) outputMaximum[0] = x;
      if (y > outputMaximum[1]) outputMaximum[1] = y;
    }
    records.push({
      source_point_id: id,
      original: original.map(String),
      translated: translated.map(String),
      projected: [x.toString(), y.toString()]
    });
  }

  return {
    schema: "erdos588.integer_plane_projection/v1",
    algorithm: "separated_exponent_integer_projection/v1",
    dimension,
    input_entries: options.points.length,
    distinct_points: records.length,
    duplicates_removed: options.points.length - records.length,
    source_point_order: "numeric lexicographic original coordinates",
    input_to_source_point_ids: inputKeys.map(key => keyToId.get(key)),
    translation: {
      minimum_coordinates: minimum.map(String),
      maximum_coordinates: maximum.map(String),
      coordinate_spans: spans.map(String),
      maximum_span: largestSpan.toString()
    },
    parameters: {
      coefficient_bound: coefficientBound.toString(),
      base: base.toString(),
      first_coordinate_exponents: Array.from({ length: dimension }, (_, i) => i),
      second_coordinate_exponents: Array.from({ length: dimension }, (_, i) => dimension * i),
      maximum_input_coordinate_digits: PROJECTION_LIMITS.max_input_coordinate_digits,
      maximum_output_coordinate_digits: PROJECTION_LIMITS.max_output_coordinate_digits
    },
    points: records.map(record => [...record.projected]),
    records,
    output_coordinate_minima: outputMinimum === null ? null : outputMinimum.map(String),
    output_coordinate_maxima: outputMaximum === null ? null : outputMaximum.map(String),
    guarantee: {
      scope: "the listed distinct finite input points",
      distinct_points_preserved: true,
      collinear_triples_preserved: true,
      noncollinear_triples_preserved: true,
      justification: "integer coefficient dominance with distinct exponents i + dimension*j",
      point_pairs_enumerated: false,
      point_triples_enumerated: false,
      extrema_or_asymptotics_claimed: false
    },
    work
  };
}

module.exports = Object.freeze({ projectIntegerPointsToPlane, PROJECTION_LIMITS });
