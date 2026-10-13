/* Dependency-free data model shared by the organizer and portable exhibitor portal. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ExhibitorDesk = api;
})(globalThis, function () {
  'use strict';
  const FIELDS = ['company', 'contact', 'email', 'booth', 'dimensions', 'power', 'accessibility', 'notes', 'changeRequest'];
  const copy = value => JSON.parse(JSON.stringify(value));
  const stamp = value => value || new Date().toISOString();
  const uid = () => {
    if (globalThis.crypto.randomUUID) return globalThis.crypto.randomUUID();
    const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    const hex = Array.from(bytes, n => n.toString(16).padStart(2, '0')).join('');
    return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-');
  };
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const text = (value, name) => { check(typeof value === 'string', name + ' must be text.'); return value; };
  const integer = (value, name) => { check(Number.isSafeInteger(value) && value >= 0, name + ' must be a nonnegative integer.'); return value; };
  const object = (value, name) => { check(value && typeof value === 'object' && !Array.isArray(value), name + ' must be an object.'); return value; };
  function instant(value) {
    text(value, 'Deadline');
    check(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value) && Number.isFinite(Date.parse(value)), 'Use a valid UTC deadline.');
    const normalized = new Date(value).toISOString();
    check(normalized === value || normalized.replace('.000Z', 'Z') === value, 'Deadline contains an invalid date.');
    return normalized;
  }
  function fields(value) {
    object(value, 'Exhibitor details');
    const result = {};
    for (const key of FIELDS) result[key] = text(value[key] ?? '', key);
    check(result.company.trim(), 'Company is required.');
    return result;
  }
  function asset(value) {
    object(value, 'Asset');
    for (const key of ['id', 'name', 'mime', 'base64']) text(value[key], 'Asset ' + key);
    check(value.id && value.name, 'Asset ID and file name are required.');
    integer(value.size, 'Asset size');
    check(/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value.base64), 'Asset encoding is invalid.');
    const decoded = atob(value.base64);
    check(decoded.length === value.size, 'Asset size does not match its bytes.');
    return {id: value.id, name: value.name, mime: value.mime, base64: value.base64, size: value.size};
  }
  function assets(values) {
    check(Array.isArray(values), 'Assets must be an array.');
    const seen = new Set();
    return values.map(value => { const result = asset(value); check(!seen.has(result.id), 'Duplicate asset ID.'); seen.add(result.id); return result; });
  }
  function event(value) {
    object(value, 'Event');
    for (const key of ['id', 'name', 'venue', 'eventDate', 'instructions']) text(value[key], 'Event ' + key);
    check(value.id && value.name.trim(), 'Event ID and name are required.');
    return {id: value.id, name: value.name, venue: value.venue, eventDate: value.eventDate,
      instructions: value.instructions, deadline: instant(value.deadline), revision: integer(value.revision, 'Event revision')};
  }
  function details(value) { const out = fields(value); out.assets = assets(value.assets || []); return out; }
  function blank(now) {
    const deadline = new Date(stamp(now)); deadline.setUTCDate(deadline.getUTCDate() + 14);
    return {kind: 'exhibitor-desk', schema: 1, event: {id: uid(), name: 'Untitled event', venue: '', eventDate: '',
      deadline: deadline.toISOString(), instructions: '', revision: 1}, exhibitors: [], eventHistory: []};
  }
  function find(state, id) { const row = state.exhibitors.find(item => item.id === id); check(row, 'Exhibitor not found.'); return row; }
  function saveEvent(state, values, now) {
    const next = copy(state), previous = copy(next.event);
    next.event = event({...next.event, ...values, id: next.event.id, revision: next.event.revision + 1});
    next.eventHistory.push({at: stamp(now), previous, current: copy(next.event)});
    return next;
  }
  function saveExhibitor(state, id, values, now) {
    const next = copy(state);
    let row;
    if (id) row = find(next, id);
    else {
      row = {id: uid(), revision: 0, ...Object.fromEntries(FIELDS.map(key => [key, ''])), assets: [],
        acknowledgedEventRevision: 0, resolution: '', history: [], submissions: []};
      next.exhibitors.push(row);
    }
    const prior = row.revision ? {revision: row.revision, ...details(row), resolution: row.resolution} : null;
    Object.assign(row, fields({...row, ...values}));
    if (values.assets !== undefined) row.assets = assets(values.assets);
    if (values.resolution !== undefined) row.resolution = text(values.resolution, 'Resolution');
    row.revision += 1;
    row.history.push({at: stamp(now), action: prior ? 'Organizer revision' : 'Onboarded', previous: prior});
    return {state: next, id: row.id};
  }
  function portal(state, id) {
    const row = find(state, id);
    return {kind: 'exhibitor-portal', schema: 1, event: copy(state.event), exhibitorId: row.id,
      baseRevision: row.revision, details: details(row), resolution: row.resolution,
      acknowledgedEventRevision: row.acknowledgedEventRevision};
  }
  function submission(payload, values, acknowledged, now) {
    check(payload.kind === 'exhibitor-portal' && payload.schema === 1, 'Unsupported portal.');
    const current = event(payload.event);
    return {kind: 'exhibitor-submission', schema: 1, id: uid(), eventId: current.id,
      exhibitorId: text(payload.exhibitorId, 'Exhibitor ID'), baseRevision: integer(payload.baseRevision, 'Base revision'),
      acknowledgedEventRevision: acknowledged ? current.revision : integer(payload.acknowledgedEventRevision, 'Acknowledged revision'),
      at: stamp(now), details: details({...payload.details, ...values})};
  }
  function validateSubmission(value) {
    object(value, 'Submission');
    check(value.kind === 'exhibitor-submission' && value.schema === 1, 'This is not an exhibitor submission.');
    for (const key of ['id', 'eventId', 'exhibitorId', 'at']) text(value[key], key);
    check(value.id && value.eventId && value.exhibitorId, 'Submission identifiers are missing.');
    return {kind: value.kind, schema: 1, id: value.id, eventId: value.eventId, exhibitorId: value.exhibitorId,
      baseRevision: integer(value.baseRevision, 'Base revision'), acknowledgedEventRevision: integer(value.acknowledgedEventRevision, 'Acknowledged revision'),
      at: instant(value.at), details: details(value.details)};
  }
  function importSubmission(state, input, now) {
    const value = validateSubmission(input);
    check(value.eventId === state.event.id, 'Submission belongs to a different event; current workspace is unchanged.');
    const next = copy(state), row = find(next, value.exhibitorId);
    check(value.acknowledgedEventRevision <= state.event.revision, 'Submission refers to an event revision newer than this workspace.');
    const prior = row.submissions.find(item => item.value.id === value.id);
    if (prior) {
      check(JSON.stringify(prior.value) === JSON.stringify(value), 'Submission ID has different content; neither version was overwritten.');
      return {state: next, status: 'duplicate', id: row.id};
    }
    const status = value.baseRevision === row.revision ? 'applied' : 'conflict';
    row.submissions.push({status, receivedAt: stamp(now), value});
    if (status === 'applied') {
      row.history.push({at: stamp(now), action: 'Exhibitor submission', previous: {revision: row.revision, ...details(row), resolution: row.resolution}});
      Object.assign(row, value.details);
      row.acknowledgedEventRevision = value.acknowledgedEventRevision;
      row.resolution = ''; row.revision += 1;
    }
    return {state: next, status, id: row.id};
  }
  function resolveSubmission(state, id, submissionId, selectedFields, now) {
    const next = copy(state), row = find(next, id);
    const entry = row.submissions.find(item => item.value.id === submissionId);
    check(entry && entry.status === 'conflict', 'No unresolved submission with that ID.');
    check(Array.isArray(selectedFields) && selectedFields.length, 'Select the fields to merge.');
    for (const key of selectedFields) check(FIELDS.includes(key) || key === 'assets', 'Unknown field: ' + key);
    const previous = {revision: row.revision, ...details(row), resolution: row.resolution};
    for (const key of selectedFields) {
      if (key === 'assets') {
        for (const item of entry.value.details.assets) {
          const old = row.assets.find(old => old.id === item.id);
          check(!old || JSON.stringify(old) === JSON.stringify(item), 'Asset ID has different bytes; retained submission is unchanged.');
          if (!old) row.assets.push(copy(item));
        }
      } else row[key] = entry.value.details[key];
    }
    fields(row);
    // A partial merge does not imply acceptance of an updated event notice.
    entry.status = 'reviewed'; entry.mergedFields = [...selectedFields];
    row.resolution = ''; row.revision += 1;
    row.history.push({at: stamp(now), action: 'Reviewed submission: ' + selectedFields.join(', '), previous});
    return next;
  }
  function dismissSubmission(state, id, submissionId, reason, now) {
    check(typeof reason === 'string' && reason.trim(), 'A disposition note is required.');
    const next = copy(state), row = find(next, id);
    const entry = row.submissions.find(item => item.value.id === submissionId);
    check(entry && entry.status === 'conflict', 'No unresolved submission with that ID.');
    entry.status = 'kept-current'; entry.reason = reason;
    row.history.push({at: stamp(now), action: 'Kept current details: ' + reason, previous: null});
    return next;
  }
  function status(state, row, now) {
    if (row.submissions.some(item => item.status === 'conflict')) return 'Submission to review';
    if (row.changeRequest.trim() && !row.resolution.trim()) return 'Change needs review';
    if (row.acknowledgedEventRevision < state.event.revision) return Date.parse(stamp(now)) > Date.parse(state.event.deadline) ? 'Deadline passed — notice unacknowledged' : 'Current notice unacknowledged';
    return 'Current notice acknowledged';
  }
  function reminder(state, id) {
    const row = find(state, id), e = state.event;
    return `To: ${row.contact || row.company}${row.email ? ' <' + row.email + '>' : ''}\nSubject: ${e.name} — exhibitor requirements\n\nHello ${row.contact || row.company},\n\nThe current requirements deadline is ${e.deadline} (UTC).\nEvent notice revision: ${e.revision}.\nBooth: ${row.booth || 'Not assigned'}.\n\n${e.instructions}\n\nPlease use the latest exhibitor portal to send your requirements, files, and acknowledgement.\n${row.changeRequest ? '\nYour change request: ' + row.changeRequest + '\n' : ''}${row.resolution ? 'Organizer response: ' + row.resolution + '\n' : ''}\nDraft only — not sent.`;
  }
  function csvCell(value) {
    let s = String(value ?? '');
    if (/^[\s]*[=+\-@\t\r]/.test(s) || /^[\t\r]/.test(s)) s = "'" + s;
    return '"' + s.replace(/"/g, '""') + '"';
  }
  function floorplan(state) {
    const headings = ['Exhibitor ID', 'Company', 'Booth', 'Dimensions', 'Power', 'Accessibility', 'Requirements', 'Change request', 'Organizer response', 'Revision'];
    return [headings, ...state.exhibitors.map(r => [r.id, r.company, r.booth, r.dimensions, r.power, r.accessibility, r.notes, r.changeRequest, r.resolution, r.revision])].map(row => row.map(csvCell).join(',')).join('\r\n') + '\r\n';
  }
  function calendar(state, id, now) {
    const row = find(state, id), e = state.event;
    const esc = s => String(s).replace(/\\/g, '\\\\').replace(/\r\n|\r|\n/g, '\\n').replace(/;/g, '\\;').replace(/,/g, '\\,');
    const date = s => new Date(s).toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
    const fold = line => { const result = []; let chunk = '', size = 0; for (const c of line) {const n = new TextEncoder().encode(c).length; if (size + n > 75) {result.push(chunk); chunk = ' '; size = 1;} chunk += c; size += n;} result.push(chunk); return result.join('\r\n'); };
    return ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Commons//Exhibitor Desk//EN', 'CALSCALE:GREGORIAN', 'BEGIN:VEVENT',
      'UID:' + esc(e.id + '-' + row.id + '@exhibitor-desk'), 'SEQUENCE:' + e.revision, 'DTSTAMP:' + date(stamp(now)),
      'DTSTART:' + date(e.deadline), 'SUMMARY:' + esc(e.name + ': exhibitor requirements deadline'),
      'DESCRIPTION:' + esc(e.instructions + '\nBooth: ' + (row.booth || 'Not assigned') + '\nEvent notice revision: ' + e.revision),
      'END:VEVENT', 'END:VCALENDAR'].map(fold).join('\r\n') + '\r\n';
  }
  function validateWorkspace(value) {
    object(value, 'Workspace');
    check(value.kind === 'exhibitor-desk' && value.schema === 1, 'Unsupported workspace format.');
    const result = {kind: value.kind, schema: 1, event: event(value.event), exhibitors: [], eventHistory: []};
    check(Array.isArray(value.exhibitors) && Array.isArray(value.eventHistory), 'Workspace collections are missing.');
    const seen = new Set();
    for (const entry of value.eventHistory) {
      object(entry, 'Event history');
      result.eventHistory.push({at: instant(entry.at), previous: event(entry.previous), current: event(entry.current)});
    }
    for (const row of value.exhibitors) {
      object(row, 'Exhibitor'); text(row.id, 'Exhibitor ID'); check(row.id && !seen.has(row.id), 'Missing or duplicate exhibitor ID.'); seen.add(row.id);
      integer(row.revision, 'Exhibitor revision'); integer(row.acknowledgedEventRevision, 'Acknowledged revision');
      check(row.acknowledgedEventRevision <= result.event.revision, 'Acknowledgement is newer than this event.');
      check(Array.isArray(row.history) && Array.isArray(row.submissions), 'Exhibitor history is missing.');
      const clean = {id: row.id, revision: row.revision, ...details(row), acknowledgedEventRevision: row.acknowledgedEventRevision,
        resolution: text(row.resolution, 'Resolution'), history: [], submissions: []};
      for (const entry of row.history) {
        object(entry, 'History'); const h = {at: instant(entry.at), action: text(entry.action, 'History action'), previous: null};
        if (entry.previous !== null) { object(entry.previous, 'Previous revision'); h.previous = {revision: integer(entry.previous.revision, 'Previous revision'), ...details(entry.previous), resolution: text(entry.previous.resolution, 'Previous resolution')}; }
        clean.history.push(h);
      }
      const submissionIds = new Set();
      for (const entry of row.submissions) {
        object(entry, 'Received submission'); const v = validateSubmission(entry.value);
        check(v.eventId === result.event.id && v.exhibitorId === row.id, 'Submission is assigned to a different event or exhibitor.');
        check(!submissionIds.has(v.id), 'Duplicate submission ID in backup.'); submissionIds.add(v.id);
        check(['applied', 'conflict', 'reviewed', 'kept-current'].includes(entry.status), 'Unknown submission disposition.');
        const item = {status: entry.status, receivedAt: instant(entry.receivedAt), value: v};
        if (entry.reason !== undefined) item.reason = text(entry.reason, 'Disposition note');
        if (entry.mergedFields !== undefined) {check(Array.isArray(entry.mergedFields) && entry.mergedFields.every(f => FIELDS.includes(f) || f === 'assets'), 'Unknown merge field.'); item.mergedFields = [...entry.mergedFields];}
        clean.submissions.push(item);
      }
      result.exhibitors.push(clean);
    }
    return result;
  }
  function sample(now) {
    let state = blank(now);
    state = saveEvent(state, {name: 'Demo Makers Exchange', venue: 'Sample Exhibition Hall', eventDate: 'Sample event — replace before use',
      instructions: 'Synthetic demonstration. Upload your logo and booth requirements. Tell the organizer about any changed requirement.'}, now);
    state = saveExhibitor(state, null, {company: 'Sample Studio North', contact: 'Demo exhibitor', email: 'exhibitor@example.invalid',
      booth: 'B-12', dimensions: '3 m × 3 m', power: 'One outlet requested — organizer to confirm', notes: 'Display table and two chairs'}, now).state;
    return state;
  }
  return {FIELDS, uid, blank, sample, find, saveEvent, saveExhibitor, portal, submission, importSubmission, resolveSubmission,
    dismissSubmission, status, reminder, floorplan, calendar, validateWorkspace, validateSubmission, asset, instant, copy};
});
