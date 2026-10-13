'use strict';
(() => {
  const payload = JSON.parse(atob(document.getElementById('payload').textContent));
  const report = payload.report;
  const $ = id => document.getElementById(id);
  const human = value => value === null || value === undefined ? 'UNKNOWN' : String(value).replaceAll('_', ' ');
  const anchor = (kind, id) => kind + '-' + Array.from(new TextEncoder().encode(id), b => b.toString(16).padStart(2, '0')).join('');
  const element = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const paragraph = (parent, text, cls) => parent.appendChild(element('p', text, cls));
  const sources = new Map(report.sources.map(row => [row.id, row]));
  const incidents = new Map(report.incidents.map(row => [row.id, row]));
  const refs = (parent, ids, kind = 'source') => {
    const box = element('div', undefined, 'refs');
    if (!ids.length) box.appendChild(element('span', 'UNKNOWN — no source reference supplied', 'unknown'));
    for (const id of ids) {
      const link = element('a', id, 'ref');
      link.href = '#' + anchor(kind, id);
      box.appendChild(link);
    }
    parent.appendChild(box);
  };
  const details = (parent, label) => {
    const box = element('details'); box.appendChild(element('summary', label)); parent.appendChild(box); return box;
  };
  const pairs = (parent, values) => {
    const list = element('dl');
    for (const [name, value] of values) {list.appendChild(element('dt', name)); list.appendChild(element('dd', human(value)));}
    parent.appendChild(list);
  };
  const sourceIds = value => {
    const ids = new Set();
    function walk(v) {
      if (!v || typeof v !== 'object') return;
      for (const [key, child] of Object.entries(v)) {
        if (key.endsWith('evidence_ids') && Array.isArray(child)) child.forEach(id => ids.add(id));
        else walk(child);
      }
    }
    walk(value); return Array.from(ids);
  };
  const searchText = row => JSON.stringify(row).toLocaleLowerCase() + ' ' + sourceIds(row).map(id => JSON.stringify(sources.get(id))).join(' ').toLocaleLowerCase();
  $('classification').textContent = report.classification === 'synthetic' ? 'FICTIONAL REHEARSAL · NOT UNIVERSITY FINDINGS' : 'ENGAGEMENT RECORDS · CONTROLLED HANDLING REQUIRED';
  $('asof').textContent = 'Assessment snapshot: ' + report.as_of + ' · no live clock or automatic refresh';
  report.limits.forEach(text => paragraph($('limits'), text));
  for (const [value, label] of [[report.summary.incidents, 'supplied incidents'], [report.summary.actions, 'unique corrective actions'], [report.summary.overdue_unresolved, 'overdue unresolved actions'], [report.sources.length, 'supplied source records']]) {
    const card = element('div', undefined, 'stat'); card.appendChild(element('strong', value)); card.appendChild(element('span', label)); $('stats').appendChild(card);
  }
  const incidentCards = [];
  for (const row of report.incidents) {
    const card = element('article', undefined, 'card'); card.id = anchor('incident', row.id);
    card.appendChild(element('span', row.group, 'badge'));
    card.appendChild(element('span', 'Coverage: ' + row.coverage, 'badge' + (row.coverage === 'complete' ? '' : ' attention')));
    card.appendChild(element('h3', row.id + ' · ' + row.service)); paragraph(card, row.impact);
    const list = element('ol', undefined, 'timeline');
    const events = new Map(row.events.map(event => [event.kind, event]));
    for (const kind of payload.presentation.timeline_order[row.id]) {
      const event = events.get(kind), supported = row.milestones_with_evidence.includes(kind);
      const point = element('li', undefined, supported ? '' : 'unsupported');
      point.appendChild(element('strong', human(kind)));
      const time = element('time', event.at); time.dateTime = event.at; point.appendChild(time);
      paragraph(point, event.note); paragraph(point, supported ? 'Endpoint evidence linked' : 'Endpoint evidence not established', supported ? 'meta' : 'unknown');
      refs(point, event.evidence_ids); list.appendChild(point);
    }
    card.appendChild(list);
    const metrics = element('div', undefined, 'metrics');
    for (const [name, value] of Object.entries(row.minutes)) {
      const metric = element('div', undefined, 'metric'); metric.appendChild(element('span', human(name)));
      metric.appendChild(element('strong', value === null ? 'UNKNOWN' : value + ' min', value === null ? 'unknown' : '')); metrics.appendChild(metric);
    }
    card.appendChild(metrics);
    paragraph(card, 'Missing or unsupported milestones: ' + (row.milestones_missing_evidence.map(human).join(', ') || 'none in supplied records'), 'meta');
    const review = details(card, 'Analysis, unresolved questions and action links');
    paragraph(review, row.review.analysis);
    pairs(review, [['Analysis sources present', row.analysis_supported], ['Sharing sources present', row.sharing_supported]]);
    refs(review, row.review.analysis_evidence_ids);
    row.review.unresolved_questions.forEach(question => paragraph(review, question));
    paragraph(review, 'Related actions'); refs(review, row.action_ids, 'action');
    paragraph(review, 'Contributing conditions'); refs(review, row.condition_ids, 'condition');
    $('incident-list').appendChild(card); incidentCards.push({row, card, search: searchText(row)});
  }
  const actionCards = [];
  for (const row of report.actions) {
    const card = element('article', undefined, 'card'); card.id = anchor('action', row.id);
    card.appendChild(element('span', human(row.evidence_state), 'badge' + (row.evidence_state === 'closure_unverified' ? ' attention' : '')));
    if (row.overdue_unresolved) card.appendChild(element('span', row.days_past_due + ' days overdue unresolved', 'badge attention'));
    card.appendChild(element('h3', row.id + ' · ' + row.description));
    pairs(card, [['Accountable role', row.owner_role], ['Reported status', row.reported_status], ['Created', row.created_at], ['Due', row.due_at], ['Reported completion', row.completed_at]]);
    paragraph(card, 'Incident links'); refs(card, row.incident_ids, 'incident');
    if (row.replacement) {
      paragraph(card, 'Documented replacement — not proof of completion', 'unknown');
      refs(card, [row.replacement.action_id], 'action'); paragraph(card, row.replacement.reason); refs(card, row.replacement.evidence_ids);
    }
    const evidence = details(card, 'Implementation, verification and follow-up');
    paragraph(evidence, 'Implementation references'); refs(evidence, row.implementation_evidence_ids);
    paragraph(evidence, 'Verification references'); refs(evidence, row.verification_evidence_ids);
    row.issues.forEach(issue => paragraph(evidence, human(issue), 'unknown'));
    if (!row.issues.length) paragraph(evidence, 'No follow-up emitted by structural checks. This is not analyst approval.');
    const measurement = details(card, 'Descriptive outcome measurement');
    paragraph(measurement, human(row.effectiveness.state));
    paragraph(measurement, 'No causal conclusion. Counts, exposure, cohorts and windows remain explicit.');
    measurement.appendChild(element('pre', JSON.stringify({comparison: row.effectiveness, measurement: row.measurement}, null, 2)));
    refs(measurement, sourceIds(row.measurement));
    $('action-list').appendChild(card);
    const groups = Array.from(new Set(row.incident_ids.map(id => incidents.get(id).group)));
    actionCards.push({row, card, groups, search: searchText(row)});
  }
  for (const row of report.conditions) {
    const card = element('article', undefined, 'card'); card.id = anchor('condition', row.id);
    card.appendChild(element('h3', row.id + ' · ' + row.description)); paragraph(card, row.interpretation);
    pairs(card, [['Shared dependency', row.shared_dependency], ['Supplied incident count', row.observed_incident_count], ['Groups represented', row.groups.join(', ')]]);
    paragraph(card, 'Linked incidents'); refs(card, row.incident_ids, 'incident');
    paragraph(card, 'Unresolved action links');
    if (row.unresolved_action_ids.length) refs(card, row.unresolved_action_ids, 'action'); else paragraph(card, 'None identified by the canonical analyzer; review the source limits.');
    refs(card, row.evidence_ids); $('condition-list').appendChild(card);
  }
  for (const row of report.sources) {
    const card = element('details', undefined, 'source'); card.id = anchor('source', row.id);
    card.appendChild(element('summary', row.id + ' · ' + human(row.kind)));
    pairs(card, [['Observed at', row.observed_at], ['Locator (not fetched)', row.locator]]);
    card.appendChild(element('blockquote', row.excerpt)); $('source-list').appendChild(card);
  }
  $('provenance').textContent = 'Input SHA-256: ' + payload.input_sha256 + ' · ' + payload.input_bytes + ' bytes. Canonical report SHA-256: ' + payload.report_sha256 + '. ' + payload.notice;
  function filters() {return {group: $('group').value, action_state: $('state').value, query: $('query').value};}
  function apply() {
    const selected = filters(), query = selected.query.trim().toLocaleLowerCase();
    let incidentCount = 0, actionCount = 0;
    for (const item of incidentCards) {
      item.card.hidden = !((selected.group === 'all' || item.row.group === selected.group) && item.search.includes(query));
      if (!item.card.hidden) incidentCount++;
    }
    for (const item of actionCards) {
      const state = selected.action_state;
      const matchesState = state === 'all' || (state === 'overdue' ? item.row.overdue_unresolved : state === 'unresolved' ? !['implementation_verified', 'replacement_documented'].includes(item.row.evidence_state) : item.row.evidence_state === state);
      item.card.hidden = !((selected.group === 'all' || item.groups.includes(selected.group)) && matchesState && item.search.includes(query));
      if (!item.card.hidden) actionCount++;
    }
    $('visible').textContent = `Visible: ${incidentCount} of ${report.incidents.length} incidents · ${actionCount} of ${report.actions.length} unique actions. Full source appendix retained.`;
    $('no-incidents').hidden = incidentCount !== 0; $('no-actions').hidden = actionCount !== 0;
  }
  ['group', 'state'].forEach(id => $(id).addEventListener('change', apply));
  $('query').addEventListener('input', apply);
  $('reset').addEventListener('click', () => {$('group').value = 'all'; $('state').value = 'all'; $('query').value = ''; apply();});
  function reveal() {
    let id; try {id = decodeURIComponent(location.hash.slice(1));} catch (_) {return;}
    const target = $(id); if (!target) return;
    const hidden = target.closest('[hidden]');
    if (hidden) {$('reset').click(); $('visible').textContent += ' Filters reset to reveal the linked record.';}
    for (let node = target; node; node = node.parentElement) if (node.tagName === 'DETAILS') node.open = true;
    target.scrollIntoView({block: 'start'});
  }
  window.addEventListener('hashchange', reveal);
  document.addEventListener('click', event => {const link = event.target.closest('a[href^="#"]'); if (link && link.hash === location.hash) reveal();});
  function selection() {
    return {...filters(), incident_ids: incidentCards.filter(item => !item.card.hidden).map(item => item.row.id), action_ids: actionCards.filter(item => !item.card.hidden).map(item => item.row.id)};
  }
  function download(name, content, type) {
    const url = URL.createObjectURL(new Blob([content], {type}));
    const link = element('a'); link.href = url; link.download = name; document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  $('export-json').addEventListener('click', () => {
    download('incident-review-selection.json', JSON.stringify({schema: 'uiowa-067-review-selection/v1', selection: selection(), source: payload, notice: 'A view selection only; no finding, approval or resolution has been recorded.'}, null, 2) + '\n', 'application/json');
  });
  $('export-input').addEventListener('click', () => {
    const raw = Uint8Array.from(atob(payload.original_packet_base64), character => character.charCodeAt(0));
    download('incident-original-packet.json', raw, 'application/json');
  });
  $('export-text').addEventListener('click', () => {
    const selected = selection(), lines = ['INCIDENT REVIEW — ' + report.classification.toUpperCase(), 'As of ' + report.as_of, 'Input SHA-256 ' + payload.input_sha256, ...report.limits, '', 'Filters: ' + JSON.stringify(filters()), 'This is a filtered view, not a decision or the full report.', ''];
    for (const item of incidentCards.filter(item => !item.card.hidden)) lines.push(item.row.id + ' / ' + item.row.group + ' / ' + item.row.service, item.row.impact, 'Intervals in minutes: ' + JSON.stringify(item.row.minutes), 'Missing or unsupported: ' + item.row.milestones_missing_evidence.join(', '), ...item.row.review.unresolved_questions, '');
    for (const item of actionCards.filter(item => !item.card.hidden)) lines.push(item.row.id + ' / ' + item.row.evidence_state, item.row.description, 'Role: ' + human(item.row.owner_role), 'Due: ' + human(item.row.due_at), 'Overdue unresolved: ' + item.row.overdue_unresolved, 'Implementation refs: ' + item.row.implementation_evidence_ids.join(', '), 'Verification refs: ' + item.row.verification_evidence_ids.join(', '), 'Replacement: ' + JSON.stringify(item.row.replacement), ...item.row.issues, '');
    lines.push('Selected record IDs: ' + JSON.stringify(selected), 'Use the JSON selection export for the complete original packet, source excerpts and canonical report.');
    download('incident-review-summary.txt', lines.join('\n') + '\n', 'text/plain;charset=utf-8');
  });
  let closedBeforePrint = [];
  window.addEventListener('beforeprint', () => {closedBeforePrint = Array.from(document.querySelectorAll('details:not([open])')); closedBeforePrint.forEach(node => node.open = true);});
  window.addEventListener('afterprint', () => {closedBeforePrint.forEach(node => node.open = false); closedBeforePrint = [];});
  $('print').addEventListener('click', () => window.print());
  apply(); if (location.hash) reveal();
})();
