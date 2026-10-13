const EVENT_KEYS = new Set(['id', 'kind', 'occurred_at', 'recorded_at', 'payload']);
const KINDS = new Set(['diet', 'symptom', 'validated_score', 'context']);
const CONTEXT_DOMAINS = new Set(['medication_change', 'sleep', 'stress', 'activity', 'illness', 'menstrual_cycle', 'other']);
const HOUR_MS = 60 * 60 * 1000;

export class LedgerError extends Error {}

function exactKeys(object, allowed, label) {
  if (!object || typeof object !== 'object' || Array.isArray(object)) {
    throw new LedgerError(`${label} must be an object`);
  }
  const keys = Object.keys(object);
  const extras = keys.filter((key) => !allowed.has(key));
  const missing = [...allowed].filter((key) => !Object.hasOwn(object, key));
  if (extras.length || missing.length) {
    throw new LedgerError(`${label} fields differ: missing=${missing.sort()} extra=${extras.sort()}`);
  }
}

function text(value, label, { max = 240 } = {}) {
  if (typeof value !== 'string' || !value.trim()) throw new LedgerError(`${label} must be non-empty text`);
  const clean = value.trim();
  if (clean.length > max) throw new LedgerError(`${label} exceeds ${max} characters`);
  return clean;
}

function number(value, label, { min = -Infinity, max = Infinity } = {}) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) {
    throw new LedgerError(`${label} must be a finite number in [${min}, ${max}]`);
  }
  return value;
}

function iso(value, label) {
  const clean = text(value, label, { max: 64 });
  const ms = Date.parse(clean);
  if (!Number.isFinite(ms)) throw new LedgerError(`${label} must be an ISO date-time`);
  return new Date(ms).toISOString();
}

function normalizeTags(value, label) {
  if (!Array.isArray(value)) throw new LedgerError(`${label} must be an array`);
  const tags = value.map((tag, index) => text(tag, `${label}[${index}]`, { max: 48 }).toLowerCase());
  if (new Set(tags).size !== tags.length) throw new LedgerError(`${label} contains duplicate tags`);
  return [...tags].sort();
}

function normalizePayload(kind, payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new LedgerError('payload must be an object');
  if (kind === 'diet') {
    exactKeys(payload, new Set(['label', 'tags', 'note']), 'diet payload');
    return {
      label: text(payload.label, 'diet.label', { max: 120 }),
      tags: normalizeTags(payload.tags, 'diet.tags'),
      note: payload.note === null ? null : text(payload.note, 'diet.note', { max: 500 }),
    };
  }
  if (kind === 'symptom') {
    exactKeys(payload, new Set(['domain', 'severity', 'note']), 'symptom payload');
    return {
      domain: text(payload.domain, 'symptom.domain', { max: 80 }).toLowerCase(),
      severity: number(payload.severity, 'symptom.severity', { min: 0, max: 10 }),
      note: payload.note === null ? null : text(payload.note, 'symptom.note', { max: 500 }),
    };
  }
  if (kind === 'validated_score') {
    exactKeys(payload, new Set(['instrument', 'instrument_version', 'domain', 'score', 'scale_min', 'scale_max', 'source_url']), 'validated_score payload');
    const scaleMin = number(payload.scale_min, 'validated_score.scale_min');
    const scaleMax = number(payload.scale_max, 'validated_score.scale_max');
    if (scaleMax <= scaleMin) throw new LedgerError('validated_score.scale_max must exceed scale_min');
    const score = number(payload.score, 'validated_score.score', { min: scaleMin, max: scaleMax });
    const source = text(payload.source_url, 'validated_score.source_url', { max: 500 });
    if (!source.startsWith('https://')) throw new LedgerError('validated_score.source_url must use https');
    return {
      instrument: text(payload.instrument, 'validated_score.instrument', { max: 120 }),
      instrument_version: text(payload.instrument_version, 'validated_score.instrument_version', { max: 80 }),
      domain: text(payload.domain, 'validated_score.domain', { max: 80 }).toLowerCase(),
      score,
      scale_min: scaleMin,
      scale_max: scaleMax,
      source_url: source,
    };
  }
  if (kind === 'context') {
    exactKeys(payload, new Set(['domain', 'value']), 'context payload');
    const domain = text(payload.domain, 'context.domain', { max: 80 }).toLowerCase();
    if (!CONTEXT_DOMAINS.has(domain)) throw new LedgerError(`unsupported context.domain: ${domain}`);
    if (!['string', 'number', 'boolean'].includes(typeof payload.value)) throw new LedgerError('context.value must be text, number, or boolean');
    if (typeof payload.value === 'number' && !Number.isFinite(payload.value)) throw new LedgerError('context.value number must be finite');
    return { domain, value: payload.value };
  }
  throw new LedgerError(`unsupported event kind: ${kind}`);
}

export function normalizeEvent(event, { now = new Date(), maxFutureMinutes = 5 } = {}) {
  exactKeys(event, EVENT_KEYS, 'event');
  const id = text(event.id, 'event.id', { max: 120 });
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{2,119}$/.test(id)) throw new LedgerError('event.id has invalid characters');
  const kind = text(event.kind, 'event.kind', { max: 40 }).toLowerCase();
  if (!KINDS.has(kind)) throw new LedgerError(`unsupported event kind: ${kind}`);
  const occurredAt = iso(event.occurred_at, 'event.occurred_at');
  const recordedAt = iso(event.recorded_at, 'event.recorded_at');
  const nowMs = now instanceof Date ? now.getTime() : Date.parse(now);
  if (!Number.isFinite(nowMs)) throw new LedgerError('now must be a valid date-time');
  if (Date.parse(occurredAt) > nowMs + maxFutureMinutes * 60_000) throw new LedgerError('event.occurred_at is implausibly in the future');
  if (Date.parse(recordedAt) > nowMs + maxFutureMinutes * 60_000) throw new LedgerError('event.recorded_at is implausibly in the future');
  return { id, kind, occurred_at: occurredAt, recorded_at: recordedAt, payload: normalizePayload(kind, event.payload) };
}

export function normalizeLedger(events, options = {}) {
  if (!Array.isArray(events)) throw new LedgerError('events must be an array');
  const normalized = events.map((event) => normalizeEvent(event, options));
  const seen = new Set();
  for (const event of normalized) {
    if (seen.has(event.id)) throw new LedgerError(`duplicate event id: ${event.id}`);
    seen.add(event.id);
  }
  return normalized.sort((a, b) => Date.parse(a.occurred_at) - Date.parse(b.occurred_at) || a.id.localeCompare(b.id));
}

function mean(values) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function round(value, digits = 4) {
  if (value === null) return null;
  const scale = 10 ** digits;
  return Math.round((value + Number.EPSILON) * scale) / scale;
}

function outcomeValue(event, domain) {
  if (event.kind === 'symptom' && event.payload.domain === domain) return event.payload.severity;
  if (event.kind === 'validated_score' && event.payload.domain === domain) return event.payload.score;
  return null;
}

export function analyzeAssociation(events, {
  exposure_tag,
  outcome_domain,
  lag_hours = 48,
  baseline_hours = 48,
  min_pairs = 3,
  confounder_hours = 72,
  now = new Date(),
} = {}) {
  const exposureTag = text(exposure_tag, 'exposure_tag', { max: 48 }).toLowerCase();
  const outcomeDomain = text(outcome_domain, 'outcome_domain', { max: 80 }).toLowerCase();
  number(lag_hours, 'lag_hours', { min: 1, max: 24 * 14 });
  number(baseline_hours, 'baseline_hours', { min: 1, max: 24 * 14 });
  number(min_pairs, 'min_pairs', { min: 1, max: 1000 });
  number(confounder_hours, 'confounder_hours', { min: 0, max: 24 * 30 });
  const ledger = normalizeLedger(events, { now });
  const exposures = ledger.filter((event) => event.kind === 'diet' && event.payload.tags.includes(exposureTag));
  const outcomes = ledger
    .map((event) => ({ event, value: outcomeValue(event, outcomeDomain) }))
    .filter(({ value }) => value !== null);
  const contexts = ledger.filter((event) => event.kind === 'context');
  const warnings = new Set(['DESCRIPTIVE_ASSOCIATION_NOT_CAUSATION']);
  const windows = [];
  let overlapCount = 0;
  let missingWindowCount = 0;

  for (let i = 0; i < exposures.length; i += 1) {
    const exposure = exposures[i];
    const t = Date.parse(exposure.occurred_at);
    const previous = i > 0 ? Date.parse(exposures[i - 1].occurred_at) : null;
    const next = i + 1 < exposures.length ? Date.parse(exposures[i + 1].occurred_at) : null;
    const overlaps = (previous !== null && t - previous < baseline_hours * HOUR_MS) || (next !== null && next - t < lag_hours * HOUR_MS);
    if (overlaps) overlapCount += 1;

    const baseline = outcomes.filter(({ event }) => {
      const at = Date.parse(event.occurred_at);
      return at >= t - baseline_hours * HOUR_MS && at < t;
    });
    const after = outcomes.filter(({ event }) => {
      const at = Date.parse(event.occurred_at);
      return at > t && at <= t + lag_hours * HOUR_MS;
    });
    const confounders = contexts.filter((event) => {
      const at = Date.parse(event.occurred_at);
      return Math.abs(at - t) <= confounder_hours * HOUR_MS;
    });
    const baselineMean = mean(baseline.map(({ value }) => value));
    const afterMean = mean(after.map(({ value }) => value));
    if (baselineMean === null || afterMean === null) missingWindowCount += 1;
    windows.push({
      exposure_event_id: exposure.id,
      occurred_at: exposure.occurred_at,
      baseline_n: baseline.length,
      after_n: after.length,
      baseline_mean: round(baselineMean),
      after_mean: round(afterMean),
      delta: baselineMean === null || afterMean === null ? null : round(afterMean - baselineMean),
      confounders: confounders.map((event) => ({ id: event.id, domain: event.payload.domain, occurred_at: event.occurred_at })),
      overlaps_neighbor_exposure: overlaps,
    });
  }

  const matched = windows.filter((window) => window.delta !== null && !window.overlaps_neighbor_exposure);
  if (exposures.length === 0) warnings.add('NO_MATCHING_EXPOSURES');
  if (overlapCount) warnings.add('OVERLAPPING_EXPOSURE_WINDOWS_EXCLUDED');
  if (missingWindowCount) warnings.add('MISSING_BASELINE_OR_POST_OBSERVATIONS');
  if (matched.length < min_pairs) warnings.add('LOW_MATCHED_SAMPLE');
  if (windows.some((window) => window.confounders.length)) warnings.add('CONTEXT_CHANGES_PRESENT');

  const averageDelta = mean(matched.map((window) => window.delta));
  return {
    schema_version: 'nourish-association/v1',
    exposure_tag: exposureTag,
    outcome_domain: outcomeDomain,
    lag_hours,
    baseline_hours,
    exposure_count: exposures.length,
    matched_pair_count: matched.length,
    average_delta: round(averageDelta),
    interpretation: averageDelta === null
      ? 'Insufficient matched observations for a descriptive association summary.'
      : averageDelta > 0
        ? 'The recorded outcome was higher after the tagged exposure in matched descriptive windows.'
        : averageDelta < 0
          ? 'The recorded outcome was lower after the tagged exposure in matched descriptive windows.'
          : 'The recorded outcome was unchanged on average in matched descriptive windows.',
    warnings: [...warnings].sort(),
    windows,
    provenance: {
      event_ids: ledger.map((event) => event.id),
      method: 'matched pre/post descriptive windows; overlapping exposure windows excluded',
    },
  };
}

export function buildResearchExport(events, { now = new Date() } = {}) {
  const ledger = normalizeLedger(events, { now });
  const records = ledger.map((event, index) => {
    const id = `event-${String(index + 1).padStart(4, '0')}`;
    if (event.kind === 'diet') return { id, kind: event.kind, occurred_at: event.occurred_at, tags: event.payload.tags };
    if (event.kind === 'symptom') return { id, kind: event.kind, occurred_at: event.occurred_at, domain: event.payload.domain, severity: event.payload.severity };
    if (event.kind === 'validated_score') return {
      id,
      kind: event.kind,
      occurred_at: event.occurred_at,
      instrument: event.payload.instrument,
      instrument_version: event.payload.instrument_version,
      domain: event.payload.domain,
      score: event.payload.score,
      scale_min: event.payload.scale_min,
      scale_max: event.payload.scale_max,
      source_url: event.payload.source_url,
    };
    return { id, kind: event.kind, occurred_at: event.occurred_at, domain: event.payload.domain };
  });
  return {
    schema_version: 'nourish-research-export/v1',
    privacy: {
      explicit_identity_fields_in_schema: false,
      event_ids_pseudonymized: true,
      free_text_notes_removed: true,
      diet_labels_removed: true,
      context_values_removed: true,
      network_transfer_performed: false,
      statement: 'This reduced export is not de-identified and may still contain sensitive health information. The user controls local file handling.',
    },
    records,
  };
}

export function canonicalJson(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
}

export function syntheticDemo(now = new Date('2026-09-14T00:00:00Z')) {
  const base = now.getTime() - 12 * 24 * HOUR_MS;
  const events = [];
  const add = (day, hour, event) => events.push({
    ...event,
    occurred_at: new Date(base + (day * 24 + hour) * HOUR_MS).toISOString(),
    recorded_at: new Date(base + (day * 24 + hour + 0.1) * HOUR_MS).toISOString(),
  });
  for (let day = 0; day < 10; day += 1) {
    add(day, 8, { id: `sym-am-${day}`, kind: 'symptom', payload: { domain: 'fatigue', severity: 3 + (day % 2), note: null } });
    if ([1, 4, 7].includes(day)) add(day, 12, { id: `diet-${day}`, kind: 'diet', payload: { label: 'Synthetic tagged meal', tags: ['demo-exposure'], note: 'Synthetic demo only' } });
    add(day, 20, { id: `sym-pm-${day}`, kind: 'symptom', payload: { domain: 'fatigue', severity: [1, 4, 7].includes(day) ? 6 : 4, note: null } });
  }
  add(4, 15, { id: 'context-medication-demo', kind: 'context', payload: { domain: 'medication_change', value: 'synthetic change marker' } });
  return normalizeLedger(events, { now });
}
