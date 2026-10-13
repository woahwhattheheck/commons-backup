/* Read-only views over the collector's projected telemetry. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const state = { view: 'overview', mode: 'api', snapshot: null, data: {}, resultMeta: {}, pages: {}, cursors: {}, sort: {}, filters: { q: '', provider: '', harness: '', source: '' }, loading: false, viewLoading: {}, loadedViews: {}, requests: {}, requestSerial: {}, errors: {}, failedAppends: {}, historyOpen: false, summaryPending: false, summaryError: null, summaryTimer: null };
  const labels = { overview: 'Recent activity', peers: 'Observed peers', work: 'Work in progress', accounts: 'Accounts & services', notifications: 'Notifications', sources: 'Collection sources' };
  const endpoints = { peers: 'peers', work: 'work', accounts: 'accounts', notifications: 'notifications', sources: 'coverage', events: 'events' };
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const present = (v) => v !== undefined && v !== null && v !== '';
  const first = (...values) => values.find(present);
  const number = (v) => present(v) && Number.isFinite(Number(v)) ? new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(Number(v)) : 'Unknown';
  const compact = (v) => present(v) && Number.isFinite(Number(v)) ? new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(Number(v)) : 'Unknown';
  const money = (v) => present(v) && Number.isFinite(Number(v)) ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(Number(v)) : 'Unknown';
  const title = (s) => present(s) ? String(s).replace(/_/g, ' ') : 'Unknown';
  function date(value, brief = false) {
    if (!present(value)) return 'Unknown';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return new Intl.DateTimeFormat(undefined, brief ? { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' } : { dateStyle: 'medium', timeStyle: 'short' }).format(d);
  }
  function relative(value) {
    const ms = Date.now() - new Date(value).getTime();
    if (!present(value) || !Number.isFinite(ms)) return 'Unknown';
    const minutes = Math.floor(ms / 60000);
    if (minutes < 0) return date(value, true);
    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;
    return `${Math.floor(minutes / 1440)}d ago`;
  }
  function link(url, label) {
    if (!present(url)) return '';
    try {
      const u = new URL(url, location.href);
      if (!['http:', 'https:'].includes(u.protocol)) return '';
      return `<a href="${escape(u.href)}" target="_blank" rel="noopener noreferrer">${escape(label)} ↗</a>`;
    } catch { return ''; }
  }
  function badge(value) {
    const s = String(value ?? 'unknown').toLowerCase();
    const good = /^(executing|running|active|connected|available|ok|healthy|complete|completed|sent|merged|ready|success|succeeded)$/;
    const warn = /waiting|pending|partial|stale|paused|blocked|draft|incomplete/;
    const bad = /error|failed|offline|unavailable|denied/;
    const cls = good.test(s) ? 'good' : warn.test(s) ? 'warn' : bad.test(s) ? 'bad' : 'neutral';
    return `<span class="badge ${cls}">${escape(title(value))}</span>`;
  }
  const rowId = (r) => first(r.agent_id, r.peer_id, r.session_id, r.event_id, r.work_id, r.entity_id, r.account_id, r.id, r.source, r.name);
  const rowSummary = (r) => first(r.summary, r.title, r.description, r.subject, r.message, r.body, r.name, rowId(r), 'Unnamed record');
  function sourceRecordLink(ref) {
    if (!ref) return '';
    const url = typeof ref === 'object' ? first(ref.url, ref.href) : /^(https?:|\/|\.\.?\/)/.test(String(ref)) ? ref : null;
    if (url) return link(url, 'Full original record');
    const id = typeof ref === 'object' ? first(ref.ref, ref.id, ref.source_id) : ref;
    return id && state.mode === 'api' ? link(`/api/telemetry/source-record?ref=${encodeURIComponent(id)}`, 'Full original record') : '';
  }
  function details(r) {
    const refs = Array.isArray(r.source_refs) ? r.source_refs : [];
    const links = [link(first(r.url, r.source_url, r.href), 'Open source'), sourceRecordLink(r.source_record_ref), ...refs.slice(0, 4).map((ref) => link(typeof ref === 'string' ? /^(https?:|\/|\.\.?\/)/.test(ref) ? ref : null : first(ref.url, ref.href), 'Source reference'))].filter(Boolean).join('');
    const fields = [['Agent', r.agent_id], ['Peer', r.peer_id], ['Session', r.session_id], ['Instance', r.instance_id], ['Parent', first(r.parent_agent_id, r.parent_session_id)], ['Work', r.work_id], ['Operation', r.operation_id], ['Source record', r.source_id], ['Observed', r.observed_at ? date(r.observed_at) : null], ['Reported state', r.reported_status], ['Source state', r.source_status], ['Observation basis', first(r.observation_basis, r.basis)], ['Next action', r.next_action]].filter(([,v]) => present(v));
    return `${links ? `<div class="row-links">${links}</div>` : ''}${fields.length ? `<details class="row-details"><summary>Context</summary><dl class="context-fields">${fields.map(([k,v]) => `<dt>${escape(k)}</dt><dd>${escape(v)}</dd>`).join('')}</dl></details>` : ''}`;
  }
  function primary(r, sub) {
    return `<div class="cell-title">${escape(rowSummary(r))}</div>${present(sub) ? `<div class="cell-sub mono">${escape(sub)}</div>` : ''}${details(r)}`;
  }
  const provider = (r) => first(r.provider, r.service, r.provider_name, r.attributes?.provider, r.attributes?.service);
  const harness = (r) => first(r.harness, r.harness_name, r.attributes?.harness);
  const source = (r) => first(r.source, r.source_type, r.collector, r.attributes?.source);
  function matches(r) {
    const f = state.filters;
    return (!f.provider || String(provider(r)) === f.provider) && (!f.harness || String(harness(r)) === f.harness) && (!f.source || String(source(r)) === f.source) && (!f.q || JSON.stringify(r).toLowerCase().includes(f.q.toLowerCase()));
  }
  function sorted(rows, view) {
    const sort = state.sort[view];
    if (!sort) return rows;
    return [...rows].sort((a, b) => {
      let x = sort.get(a), y = sort.get(b);
      if (!present(x)) return present(y) ? 1 : 0;
      if (!present(y)) return -1;
      return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true, sensitivity: 'base' })) * sort.direction;
    });
  }
  function empty(message = 'No collected records are available for this view.', filtered = false) {
    return `<div class="empty"><strong>${filtered ? 'No matching records' : 'No records collected'}</strong>${escape(message)}</div>`;
  }
  function panel(heading, body, subtitle = '', extra = '') {
    return `<section class="panel"><div class="panel-head"><div><h2>${escape(heading)}</h2>${subtitle ? `<p>${escape(subtitle)}</p>` : ''}</div>${extra}</div>${body}</section>`;
  }
  const columns = {
    events: [
      { name: 'Activity', get: rowSummary, render: (r) => primary(r, first(r.event_id, r.session_id)) },
      { name: 'Provider / model', get: provider, render: (r) => `<div>${escape(title(provider(r)))}</div><div class="cell-sub">${escape(first(r.model, 'Model unknown'))}</div>` },
      { name: 'Harness / source', get: harness, render: (r) => `<div>${escape(title(harness(r)))}</div><div class="cell-sub">${escape(title(source(r)))}</div>` },
      { name: 'State / event', get: (r) => first(r.status, r.event_type), render: (r) => `${badge(first(r.status, r.event_type))}${r.status && r.event_type ? `<div class="cell-sub">${escape(title(r.event_type))}</div>` : ''}` },
      { name: 'Observed activity', get: (r) => first(r.occurred_at, r.observed_at), render: (r) => `<span title="${escape(date(first(r.occurred_at, r.observed_at)))}">${escape(relative(first(r.occurred_at, r.observed_at)))}</span><div class="cell-sub">${escape(date(first(r.occurred_at, r.observed_at), true))}</div>` }
    ],
    peers: [
      { name: 'Captured session / source identifier', get: (r) => first(r.session_id, r.agent_id, r.peer_id), render: (r) => `<div class="cell-title mono">${escape(first(r.session_id, r.agent_id, r.peer_id, 'Unknown session identifier'))}</div><div class="cell-sub">${escape(rowSummary(r))}</div>${details(r)}` },
      { name: 'Provider / model', get: provider, render: (r) => `<div>${escape(title(provider(r)))}</div><div class="cell-sub">${escape(first(r.model, 'Model unknown'))}</div>` },
      { name: 'Harness', get: harness, render: (r) => escape(title(harness(r))) },
      { name: 'Recorded state / observation', get: (r) => first(r.status, r.runtime_status), render: (r) => `${badge(first(r.status, r.runtime_status))}<div class="cell-sub">${escape(first(r.observation_kind, r.observation_basis, r.census_source, 'Captured source session'))}</div>` },
      { name: 'Usage', get: (r) => r.usage?.input_tokens, render: (r) => `<div>${compact(r.usage?.input_tokens)} in · ${compact(r.usage?.output_tokens)} out</div><div class="cell-sub">${money(r.usage?.cost_usd)}</div>` },
      { name: 'Last observation', get: (r) => first(r.last_activity_at, r.observed_at), render: (r) => `<span title="${escape(date(first(r.last_activity_at, r.observed_at)))}">${escape(relative(first(r.last_activity_at, r.observed_at)))}</span><div class="cell-sub">${escape(date(first(r.last_activity_at, r.observed_at), true))}</div>` }
    ],
    runtime: [
      { name: 'Runtime / agent', get: (r) => first(r.agent_id, r.peer_id, r.instance_id, r.session_id), render: (r) => `<div class="cell-title mono">${escape(first(r.agent_id, r.peer_id, r.instance_id, r.session_id, 'Unknown runtime identifier'))}</div>${r.metadata?.pid ? `<div class="cell-sub">Process ${escape(r.metadata.pid)}</div>` : ''}${details(r)}` },
      { name: 'Provider / current model', get: provider, render: (r) => `<div>${escape(title(provider(r)))}</div><div class="cell-sub">${escape(first(r.model, 'Current model unknown'))}</div>${!r.model && r.recordedContext?.model ? `<div class="cell-sub">Last recorded model: ${escape(r.recordedContext.model)}</div>` : ''}` },
      { name: 'Harness', get: harness, render: (r) => escape(title(harness(r))) },
      { name: 'Task / context', get: (r) => first(r.task_title, r.title, r.name), render: (r) => `<div>${escape(first(r.task_title, r.task?.title, typeof r.task === 'string' ? r.task : null, r.title, r.name, r.metadata?.task_title, r.metadata?.title, 'Current task unknown'))}</div>${r.recordedContext?.summary ? `<div class="cell-sub">Recorded context: ${escape(r.recordedContext.summary)}</div>` : ''}` },
      { name: 'Execution state / basis', get: (r) => r.status, render: (r) => `${badge(first(r.status, r.runtime_status))}<div class="cell-sub">${escape(title(first(r.observation_kind, r.observation_basis, r.basis, 'Observation basis unknown')))}</div>${r.source_status ? `<div class="cell-sub">Source: ${escape(title(r.source_status))}</div>` : ''}` },
      { name: 'Source freshness', get: (r) => r.observed_at, render: (r) => `${badge(state.snapshot?.summary_live_stale || state.snapshot?.summary_live_from_cache || r.fresh === false ? 'stale' : r.fresh === true ? 'fresh' : first(r.freshness?.state, 'freshness unknown'))}<div class="cell-sub">Observed ${escape(relative(r.observed_at))}</div><div class="cell-sub">${escape(date(r.observed_at, true))}</div>${r.source_refs?.length ? `<div class="cell-sub">${escape(r.source_refs.map((ref) => typeof ref === 'string' ? title(ref) : first(ref.source, ref.ref, ref.id, 'Source reference')).join(' · '))}</div>` : ''}` }
    ],
    work: [
      { name: 'Work', get: rowSummary, render: (r) => primary(r, first(r.work_id, r.id)) },
      { name: 'Owner / peer', get: (r) => first(r.owner, r.agent_id, r.peer_id), render: (r) => escape(first(r.owner, r.agent_id, r.peer_id, 'Unknown')) },
      { name: 'State', get: (r) => r.status, render: (r) => badge(r.status) },
      { name: 'Next / remaining', get: (r) => first(r.next_action, r.remaining_work), render: (r) => escape(first(r.next_action, r.remaining_work, r.next_step, 'Unknown')) },
      { name: 'Updated', get: (r) => first(r.updated_at, r.last_activity_at, r.observed_at), render: (r) => escape(date(first(r.updated_at, r.last_activity_at, r.observed_at), true)) }
    ],
    accounts: [
      { name: 'Account / service', get: rowSummary, render: (r) => primary(r, first(r.account_id, r.id, r.account)) },
      { name: 'Provider', get: provider, render: (r) => escape(title(provider(r))) },
      { name: 'Observed state', get: (r) => first(r.connection_status, r.status), render: (r) => badge(first(r.connection_status, r.status)) },
      { name: 'Capability / resource', get: (r) => first(r.capabilities, r.capability, r.kind, r.entity_type), render: (r) => `${escape(Array.isArray(r.capabilities) ? r.capabilities.join(', ') : first(r.capability, r.attributes?.capability, r.kind, r.resource_type, r.entity_type, 'Unknown'))}${Array.isArray(r.relations) && r.relations.length ? `<div class="cell-sub">${escape(r.relations.map((x) => title(x.relation)).join(', '))}</div>` : ''}` },
      { name: 'Usage / quota', get: (r) => first(r.used, r.attributes?.used), render: (r) => r.entity_type === 'quota' || present(first(r.limit, r.remaining, r.used, r.attributes?.limit, r.attributes?.remaining, r.attributes?.used)) ? `${escape(first(r.used, r.attributes?.used, 'Unknown'))} used · ${escape(first(r.limit, r.attributes?.limit, 'Unknown'))} limit<div class="cell-sub">${escape(first(r.remaining, r.attributes?.remaining, 'Unknown'))} remaining ${escape(first(r.unit, r.attributes?.unit, ''))}</div>` : 'Unknown' },
      { name: 'Last observed', get: (r) => first(r.observed_at, r.updated_at, r.attributes?.updated_at), render: (r) => escape(date(first(r.observed_at, r.updated_at, r.attributes?.updated_at), true)) }
    ],
    notifications: [
      { name: 'Notification', get: rowSummary, render: (r) => primary(r, first(r.notification_id, r.id)) },
      { name: 'Channel / provider', get: (r) => first(r.channel, provider(r)), render: (r) => `<div>${escape(first(r.channel, r.destination, r.audience?.channels?.length ? r.audience.channels.join(', ') : null, r.audience?.owner_attention ? 'Owner attention' : null, 'Unknown'))}</div><div class="cell-sub">${escape(title(provider(r)))}</div>` },
      { name: 'Delivery', get: (r) => first(r.delivery_state, r.delivery_status, r.status), render: (r) => `${badge(first(r.delivery_state, r.delivery_status, r.status))}${r.type ? `<div class="cell-sub">${escape(title(r.type))}</div>` : ''}` },
      { name: 'Source', get: source, render: (r) => escape(title(source(r))) },
      { name: 'Time', get: (r) => first(r.sent_at, r.occurred_at, r.observed_at, r.created_at), render: (r) => escape(date(first(r.sent_at, r.occurred_at, r.observed_at, r.created_at), true)) }
    ],
    sources: [
      { name: 'Source', get: source, render: (r) => primary({ ...r, summary: first(r.source, r.name, r.provider, r.summary) }, first(r.path, r.kind)) },
      { name: 'Collection', get: (r) => r.status, render: (r) => badge(r.status) },
      { name: 'Read counts', get: (r) => first(r.records_read, r.records), render: readCounts },
      { name: 'Discovery / backfill', get: (r) => first(r.processed_files, r.backfill?.processed), render: progress },
      { name: 'Coverage', get: (r) => r.complete, render: (r) => `${r.complete === true ? badge('complete') : r.complete === false ? badge('partial') : badge('unknown')}<div class="cell-sub">${escape(first(r.coverage, r.reason, r.error, r.note, r.description, ''))}</div>` },
      { name: 'Collected', get: (r) => r.observed_at, render: (r) => escape(date(r.observed_at, true)) }
    ]
  };
  function table(view, rows, heading = labels[view], limit) {
    const filtered = sorted((rows || []).filter(matches), view);
    const pageSize = view === 'sources' ? 40 : null;
    const pageCount = pageSize ? Math.max(1, Math.ceil(filtered.length / pageSize)) : 1;
    const page = state.pages[view] = Math.max(0, Math.min(state.pages[view] || 0, pageCount - 1));
    const shown = pageSize ? filtered.slice(page * pageSize, (page + 1) * pageSize) : limit ? filtered.slice(0, limit) : filtered;
    const cols = columns[view];
    const sort = state.sort[view];
    const head = cols.map((c, i) => `<th scope="col" aria-sort="${sort?.index === i ? (sort.direction === 1 ? 'ascending' : 'descending') : 'none'}"><button type="button" data-sort="${view}" data-column="${i}" aria-label="Sort by ${escape(c.name)}">${escape(c.name)} <span aria-hidden="true">${sort?.index === i ? (sort.direction === 1 ? '↑' : '↓') : '↕'}</span></button></th>`).join('');
    const body = shown.length ? `<div class="table-wrap"><table><caption class="sr-only">${escape(heading)}</caption><thead><tr>${head}</tr></thead><tbody>${shown.map((r) => `<tr>${cols.map((c, i) => `<td class="${i === 0 ? 'primary' : ''}">${c.render(r)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : state.viewLoading[view] && !state.loadedViews[view] ? `<div class="loading"><span class="spinner" aria-hidden="true"></span><div><strong>Loading ${escape(heading.toLowerCase())}</strong><span class="loading-note">Reading collected records. Summary preparation runs independently.</span></div></div>` : state.errors[view] ? `<div class="empty"><strong>This view could not be loaded</strong>${escape(state.errors[view])}<button class="button secondary" type="button" data-retry="${view}">Retry this view</button></div>` : empty(rows?.length ? 'Try a different search or clear the filters.' : 'This source has no collected records in the current snapshot.', Boolean(rows?.length));
    const more = state.cursors[view] && state.mode === 'api' && !limit ? `<button class="button secondary" type="button" data-more="${view}" ${state.viewLoading[view] ? 'disabled' : ''}>${state.viewLoading[view] ? 'Loading…' : 'Load more'}</button>` : '';
    const meta = state.resultMeta[view] || {};
    const complete = meta.truncated === true || state.cursors[view] ? 'Partial result set' : meta.complete === true ? 'Complete result set' : meta.complete === false ? 'Partial result set' : 'Result completeness unknown';
    const pages = pageSize ? `<div class="pagination"><button class="button secondary" type="button" data-page="${view}" data-step="-1" ${page === 0 ? 'disabled' : ''}>Previous</button><span>Page ${page + 1} of ${pageCount}</span><button class="button secondary" type="button" data-page="${view}" data-step="1" ${page + 1 === pageCount ? 'disabled' : ''}>Next</button>${more}</div>` : more;
    return panel(heading, `${state.errors[view] && rows?.length ? `<div class="notice" role="status">${escape(state.errors[view])} Showing the last loaded records.<button class="button secondary" type="button" data-retry="${view}">Retry this view</button></div>` : ''}${body}<div class="table-footer"><span>${number(shown.length)} shown${pageSize ? ` · ${number(filtered.length)} matching loaded partitions` : ''}${present(meta.total) ? ` · ${number(meta.total)} available` : ''} · ${complete}${state.cursors[view] ? ' · more records available' : ''}${meta.observed_at ? ` · observed ${escape(date(meta.observed_at, true))}` : ''}</span>${pages || `<span>${state.viewLoading[view] ? 'Refreshing records…' : state.mode === 'static' ? 'Saved snapshot' : 'Collected records'}</span>`}</div>`, view === 'events' ? 'Source summaries and their latest observed state' : view === 'peers' ? 'Historical and captured source sessions, including channel and repository records; source identifiers retain their original meaning' : view === 'runtime' ? 'Instances observed by connected runtime sources; execution state, task binding, and source freshness appear only when recorded' : view === 'sources' ? 'Every loaded source partition, with exact scope and continuation state' : view === 'accounts' ? 'Account, service, capability and quota references; connection state appears only when recorded' : '', `<span class="section-meta">${number(rows?.length)} loaded</span>`);
  }
  function readMetrics(r) {
    const p = r.backfill || r.progress || r.discovery || {};
    return {
      records: first(r.records_read, r.records_processed, p.records_processed, r.records),
      files: first(r.files_read, r.processed_files, p.files_read, p.processed_files),
      pages: first(r.pages_read, p.pages_read),
      discoveredFiles: first(r.files_discoverable, r.files_discovered, r.discovered_files, r.total_files, p.discovered_files),
      unchangedFiles: first(r.files_unchanged, p.files_unchanged),
      pendingFiles: first(r.files_deferred, r.files_pending, r.pending_files, p.pending_files),
      bytes: first(r.captured_source_bytes, r.source_bytes, r.bytes_captured, p.captured_source_bytes),
      chars: first(r.captured_source_chars, r.source_chars, r.chars_captured, p.captured_source_chars)
    };
  }
  function readCounts(r) {
    const m = readMetrics(r);
    const parts = [['records', 'records'], ['files', 'files'], ['pages', 'pages']].filter(([key]) => present(m[key])).map(([key, label]) => `${number(m[key])} ${label}`);
    return parts.length ? parts.map((p) => `<div>${escape(p)}</div>`).join('') : '<span class="section-meta">Read count unknown</span>';
  }
  function progress(r) {
    const p = r.backfill || r.progress || r.discovery || {};
    const m = readMetrics(r);
    const done = first(p.processed, p.completed, p.processed_files, p.records_processed, r.processed_files, r.files_processed, m.files, r.records_processed);
    const discovered = first(p.discovered, p.total, m.discoveredFiles, p.records_discovered, r.records_discovered);
    const pending = first(p.pending, p.remaining, m.pendingFiles, r.pending_records);
    const phase = first(p.phase, p.status, r.backfill_status, r.discovery_status, r.phase);
    const parts = [];
    if (present(done)) parts.push(`${number(done)} processed`);
    if (present(discovered)) parts.push(`${number(discovered)} discovered`);
    if (present(pending)) parts.push(`${number(pending)} pending`);
    if (present(m.unchangedFiles)) parts.push(`${number(m.unchangedFiles)} unchanged files`);
    if (!parts.length) return present(phase) ? badge(phase) : r.complete === true ? badge('complete') : r.complete === false ? badge('pending') : '<span class="section-meta">Unknown</span>';
    return `${present(phase) ? badge(phase) : ''}<div class="cell-sub">${escape(parts.join(' · '))}</div>`;
  }
  function sourceGroups(rows) {
    const latest = new Map();
    for (const r of rows) {
      const key = first(r.source_id, r.partition_id, r.scope ? `${source(r)}:${r.scope}` : null, `${source(r) || r.name || 'inventory'}:${harness(r) || ''}:${r.account_id || ''}`);
      const previous = latest.get(key);
      if (!previous || String(first(r.observed_at, r.updated_at, '')) >= String(first(previous.observed_at, previous.updated_at, ''))) latest.set(key, r);
    }
    const groups = new Map();
    for (const r of latest.values()) {
      const name = first(source(r), r.service, r.name, r.source_counts ? 'account inventory' : null, 'Unidentified source');
      const account = first(r.account_name, r.account_id, r.account, r.attributes?.account_name, '');
      const host = first(harness(r), '');
      const key = `${name}\u001f${account}\u001f${host}`;
      if (!groups.has(key)) groups.set(key, { name, account, harness: host, partitions: 0, complete: 0, pending: 0, unknown: 0, statuses: {}, metrics: {}, observed_at: null });
      const g = groups.get(key);
      g.partitions++;
      if (r.complete === true) g.complete++; else if (r.complete === false) g.pending++; else g.unknown++;
      const status = first(r.status, 'unknown');
      g.statuses[status] = (g.statuses[status] || 0) + 1;
      if (r.observed_at && (!g.observed_at || r.observed_at > g.observed_at)) g.observed_at = r.observed_at;
      for (const [metric, value] of Object.entries(readMetrics(r))) {
        if (present(value) && Number.isFinite(Number(value))) {
          g.metrics[metric] ||= { value: 0, partitions: 0 };
          g.metrics[metric].value += Number(value);
          g.metrics[metric].partitions++;
        }
      }
    }
    return [...groups.values()].sort((a, b) => {
      const priority = (g) => g.metrics.records || g.metrics.files || g.metrics.pages ? 0 : 1;
      return priority(a) - priority(b) || b.partitions - a.partitions || a.name.localeCompare(b.name);
    });
  }
  function groupedCoverage(rows, recordedGroups) {
    let groups = recordedGroups?.length ? recordedGroups.filter((g) => matches({ source: g.name, provider: g.name, account_ref: g.account, harness: g.harness })) : sourceGroups(rows);
    if (recordedGroups?.length && state.snapshot?.source_grouping !== 'service') {
      const summary = new Map();
      for (const g of groups) {
        if (!summary.has(g.name)) summary.set(g.name, { name: g.name, accounts: new Set(), harnesses: new Set(), partitions: 0, complete: 0, pending: 0, unknown: 0, statuses: {}, metrics: {}, observed_at: null });
        const s = summary.get(g.name);
        if (g.account) s.accounts.add(g.account);
        if (g.harness) s.harnesses.add(g.harness);
        for (const key of ['partitions', 'complete', 'pending', 'unknown']) s[key] += Number(g[key] || 0);
        for (const [key, count] of Object.entries(g.statuses || {})) s.statuses[key] = (s.statuses[key] || 0) + count;
        if (g.observed_at && (!s.observed_at || g.observed_at > s.observed_at)) s.observed_at = g.observed_at;
      }
      groups = [...summary.values()].map((s) => ({ ...s, account: `${s.accounts.size} account references`, harness: [...s.harnesses].join(' · ') }));
    }
    if (!groups.length) return empty('Source coverage has not been collected.');
    const metric = (g, key, label) => {
      const m = g.metrics[key];
      if (!m) return '';
      return `<div>${number(m.value)} ${label}${m.partitions < g.partitions ? `<span class="cell-sub"> · ${m.partitions}/${g.partitions} partitions reporting</span>` : ''}</div>`;
    };
    return `<div class="table-wrap overview-coverage"><table><caption class="sr-only">Corpus collection grouped by source, account and harness</caption><thead><tr><th scope="col">Source / scope</th><th scope="col">Read so far</th><th scope="col">Partitions / pending</th><th scope="col">Collection</th></tr></thead><tbody>${groups.map((g) => `<tr><td><div class="cell-title">${escape(title(g.name))}</div>${g.account || g.harness ? `<div class="cell-sub">${escape([g.account, g.harness].filter(Boolean).join(' · '))}</div>` : ''}</td><td>${metric(g, 'records', 'records')}${metric(g, 'files', 'files read')}${metric(g, 'pages', 'pages')}${metric(g, 'bytes', 'bytes captured')}${metric(g, 'chars', 'characters captured')}${!g.metrics.records && !g.metrics.files && !g.metrics.pages ? '<span class="section-meta">Read count unknown</span>' : ''}${metric(g, 'discoveredFiles', 'files discoverable')}${metric(g, 'unchangedFiles', 'files unchanged')}${metric(g, 'pendingFiles', 'files deferred')}</td><td><div>${number(g.complete)} complete / ${number(g.partitions)} observed</div><div class="cell-sub">${number(g.pending)} pending${g.unknown ? ` · ${number(g.unknown)} completeness unknown` : ''}</div></td><td>${Object.entries(g.statuses).map(([status, count]) => `<span class="status-count">${badge(status)}${g.partitions > 1 ? ` ${number(count)}` : ''}</span>`).join(' ')}${g.observed_at ? `<div class="cell-sub">${escape(relative(g.observed_at))}</div>` : ''}</td></tr>`).join('')}</tbody></table></div><div class="table-footer"><span>${number(groups.length)} source groups · latest report per partition · read counts retain their units</span><button type="button" class="text-button" data-open="sources">Browse all partitions →</button></div>`;
  }
  function stat(label, value, note, accent = false, pending = false) {
    return `<div class="stat"><div class="stat-label">${escape(label)}</div><div class="stat-value ${accent ? 'accent' : ''}">${pending && !present(value) ? 'Preparing' : number(value)}</div><div class="stat-foot">${escape(note)}</div></div>`;
  }
  function activityChart(rows) {
    if (!rows?.length) return empty('Daily activity has not been collected yet.');
    const dated = rows.filter((r) => present(first(r.date, r.day))).sort((a, b) => String(first(a.date, a.day)).localeCompare(String(first(b.date, b.day)))).slice(-14);
    const max = Math.max(1, ...dated.map((r) => Number(first(r.events, r.count, 0)) || 0));
    return `<div class="panel-body"><div class="chart" role="img" aria-label="Activity by day: ${escape(dated.map((r) => `${first(r.date, r.day)}: ${number(first(r.events, r.count))} events`).join('; '))}">${dated.map((r) => {
      const count = first(r.events, r.count);
      const day = String(first(r.date, r.day));
      return `<div class="chart-column"><span class="chart-value">${compact(count)}</span><div class="chart-bar" style="height:${Math.max(2, Number(count || 0) / max * 103)}px" title="${escape(day)} · ${number(count)} events"></div><span class="chart-label">${escape(day.slice(5))}</span></div>`;
    }).join('')}</div><div class="chart-caption"><span>Collected event counts</span><span>Last ${dated.length} observed days</span></div></div>`;
  }
  function overview() {
    const s = state.snapshot || {}, c = s.counts || {}, u = s.usage || {}, census = s.census, live = census?.counts || {};
    const totalsPending = s.summary_totals_ready === false;
    const awaiting = '<div class="stat"><div class="stat-label">Live agent census</div><div class="stat-value awaiting">Awaiting live census</div><div class="stat-foot">Machine, cloud, and harness observations</div></div>';
    const censusStats = census ? `${stat('Observed runtime census', live.observed_instances, 'Observed instances · lower bound', true)}${stat('Executing', live.executing, 'Confirmed within observed sources')}${stat('Waiting', live.waiting, 'Confirmed within observed sources')}${stat('State unknown', live.unknown, 'Execution state or binding unavailable')}` : `${awaiting}${stat('Executing', null, 'Awaiting live census')}${stat('Waiting', null, 'Awaiting live census')}${stat('State unknown', null, 'Awaiting live census')}`;
    const censusStatus = census?.complete === true ? badge('complete') : census?.complete === false ? badge('partial') : badge('coverage unknown');
    const stats = `<div class="section-label"><h2>Live agent census</h2><span>${censusStatus} · ${census ? `Observed ${escape(date(first(census.observed_at, s.observed_at)))}` : 'Awaiting runtime observations'}</span></div><section class="stats census-stats" aria-label="Live agent census">${censusStats}</section><div class="section-label"><h2>Historical activity</h2><span>${totalsPending ? 'Preparing totals from captured history · detail views remain available' : 'Collected Slack, GitHub, machine, cloud, and harness records'}</span></div><section class="stats history-stats" aria-label="Historical activity totals">${stat('Historical sessions', c.sessions, 'Session records across collected history', false, totalsPending)}${stat('Historical events', c.events, 'Events already ingested', false, totalsPending)}</section>`;
    const accountingCoverage = typeof u.accounting_coverage === 'number' ? new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 1 }).format(u.accounting_coverage) : typeof u.accounting_coverage === 'object' && u.accounting_coverage !== null ? JSON.stringify(u.accounting_coverage) : title(u.accounting_coverage);
    const usage = totalsPending ? '<div class="panel-body">Historical usage totals are being prepared from captured records. Usage fields supplied by individual sources remain visible in their detail views.</div>' : `<div class="panel-body"><div class="usage-grid"><div class="usage-item"><span>Input tokens</span><strong>${compact(u.input_tokens)}</strong></div><div class="usage-item"><span>Output tokens</span><strong>${compact(u.output_tokens)}</strong></div><div class="usage-item"><span>Cached tokens</span><strong>${compact(u.cached_tokens)}</strong></div><div class="usage-item"><span>Recorded cost</span><strong>${money(u.cost_usd)}</strong></div></div><div class="coverage-note">Accounting coverage: ${escape(accountingCoverage)}. Values reflect the usage fields supplied by collected sources.</div></div>`;
    const providerBody = providerFootprint(s);
    const sources = (s.sources || s.coverage || []).filter(matches);
    const censusCoverage = coverageRows(census?.coverage).filter(matches);
    const censusBody = censusCoverage.length ? `<div class="panel-body mini-list">${censusCoverage.map((r) => {
      const m = readMetrics(r), instances = first(r.observed_instances, r.instances, r.count);
      const bits = [];
      if (present(instances)) bits.push(`${number(instances)} instances`);
      if (present(m.records)) bits.push(`${number(m.records)} records read`);
      if (present(m.pages)) bits.push(`${number(m.pages)} pages`);
      if (present(m.files)) bits.push(`${number(m.files)} files read`);
      if (r.observed_at) bits.push(relative(r.observed_at));
      const status = first(r.freshness?.state === 'STALE' ? 'stale' : null, r.status, r.complete === true ? 'complete' : r.complete === false ? 'partial' : 'unknown');
      return `<div class="mini-row"><div><div class="mini-label">${escape(title(first(r.harness, r.source, r.name, r.source_id)))}</div>${bits.length ? `<div class="mini-sub">${escape(bits.join(' · '))}</div>` : ''}</div><div class="mini-number">${badge(status)}${r.complete === false ? '<div class="mini-sub">Partial coverage</div>' : ''}</div></div>`;
    }).join('')}</div>` : empty(census ? 'Harness and source census coverage has not been reported.' : 'Awaiting live census across machine, cloud, and harness sources.');
    const capture = s.capture;
    const capturePanel = capture ? panel('Captured source', `<div class="panel-body capture-grid"><div class="usage-item"><span>Stored source records</span><strong>${number(capture.records)}</strong></div><div class="usage-item"><span>UTF-8 serialized bytes stored</span><strong>${number(capture.bytes)}</strong></div><div class="usage-item"><span>Characters stored</span><strong>${number(capture.characters)}</strong></div></div>`, 'Encrypted stored payloads · full original records are linked from activity') : '';
    const storage = s.storage;
    const storageNotice = storage?.status === 'pending_storage' ? `<div class="notice" role="status"><strong>Source backfill is awaiting storage capacity.</strong> ${number(Math.floor(Number(storage.free_bytes || 0) / 1048576))} MiB free on the collector drive. Captured originals and unread cursors are retained. Census and dashboard reads continue; swarm work proceeds independently.</div>` : '';
    const sourceBody = totalsPending && !sources.length && !s.source_groups?.length ? '<div class="panel-body">Source totals are being prepared. <button type="button" class="text-button" data-open="sources">Browse collected source partitions →</button></div>' : groupedCoverage(sources, s.source_groups);
    const activityBody = totalsPending && !s.activity?.length ? '<div class="panel-body">Daily historical activity totals are being prepared.</div>' : activityChart(s.activity);
    return `${storageNotice}${stats}${capturePanel}<div class="grid spaced-grid">${panel('Census harness & source coverage', censusBody, 'Live runtime discovery across the swarm')}${panel('Provider & model footprint', providerBody, 'Models and harnesses found in runtime and history')}</div>${panel('Full corpus collection & backfill', sourceBody, 'All recorded source partitions grouped by service; every account and detailed read count remains in Sources')}<div class="grid spaced-grid">${panel('Activity over time', activityBody, 'Daily historical event volume')}${panel('Recorded usage', usage, 'Historical collected totals · USD')}</div>${table('events', state.data.events || [], 'Recent activity')}`;
  }
  function providerFootprint(s) {
    const map = new Map();
    for (const r of s.providers || []) if (matches(r)) map.set(r.provider, { ...r, models: new Set(), harnesses: new Set() });
    const peers = new Map();
    for (const r of [...(state.data.peers || []), ...(s.census?.peers || [])]) peers.set(first(r.session_id, r.instance_id, r.agent_id, JSON.stringify(r)), r);
    for (const r of peers.values()) {
      if (!matches(r) || !provider(r)) continue;
      const name = provider(r);
      if (!map.has(name)) map.set(name, { provider: name, models: new Set(), harnesses: new Set() });
      const item = map.get(name);
      if (typeof r.model === 'string' && r.model.trim()) item.models.add(r.model);
      if (harness(r)) item.harnesses.add(harness(r));
    }
    if (!map.size) return empty('Provider footprint has not been collected.');
    return `<div class="panel-body mini-list provider-footprint">${[...map.values()].map((r) => `<div class="mini-row"><div><div class="mini-label">${escape(title(r.provider))}</div>${r.models.size ? `<div class="model-tags">${[...r.models].map((model) => `<span>${escape(model)}</span>`).join('')}</div>` : ''}${r.harnesses.size ? `<div class="mini-sub">${escape([...r.harnesses].join(' · '))}</div>` : ''}</div><div class="mini-number">${present(r.events) ? `${number(r.events)} events` : ''}${present(r.sessions) ? `<div class="mini-sub">${number(r.sessions)} historical sessions</div>` : ''}</div></div>`).join('')}</div>`;
  }
  function coverageRows(value) {
    if (Array.isArray(value)) return value;
    if (!value || typeof value !== 'object') return [];
    const rows = [];
    for (const [kind, items] of Object.entries(value)) {
      if (Array.isArray(items)) rows.push(...items.map((r) => ({ kind, ...r })));
      else if (items && typeof items === 'object') rows.push({ source: kind, ...items });
    }
    return rows;
  }
  function peersView() {
    const census = state.snapshot?.census;
    const captured = state.data.peers || [];
    const recordedBySession = new Map(captured.filter((r) => r.session_id).map((r) => [r.session_id, r]));
    const runtime = (census?.peers || []).map((r) => {
      const recorded = recordedBySession.get(r.session_id);
      return { ...r, recordedContext: recorded && provider(recorded) === provider(r) && harness(recorded) === harness(r) ? recorded : null };
    }).sort((a, b) => {
      const priority = (r) => r.status === 'executing' ? 0 : r.status === 'waiting' ? 1 : 2;
      return priority(a) - priority(b) || String(harness(a) || '').localeCompare(String(harness(b) || ''));
    });
    state.resultMeta.runtime = { complete: census?.complete, total: census?.counts?.observed_instances, observed_at: census?.observed_at };
    const counts = census?.counts || {};
    const totals = census ? `<div class="section-label"><h2>Observed runtime census</h2><span>${census.complete === true ? badge('complete') : census.complete === false ? badge('partial') : badge('coverage unknown')} · ${escape(first(census.scope, 'Connected runtime observations'))}</span></div><section class="stats census-stats" aria-label="Observed runtime census">${stat('Observed instances', counts.observed_instances, 'Connected runtime sources · lower bound', true)}${stat('Executing', counts.executing, 'Confirmed within observed sources')}${stat('Waiting', counts.waiting, 'Confirmed within observed sources')}${stat('State unknown', counts.unknown, 'Execution state or task binding unmeasured')}</section>` : panel('Runtime census is loading', '<div class="panel-body">Runtime instances will appear as the census becomes available. Captured session history can be opened below.</div>');
    const live = census ? table('runtime', runtime, 'Observed runtime instances') : '';
    const history = `<details id="captured-history" class="panel spaced-grid" ${state.historyOpen ? 'open' : ''}><summary class="panel-head"><div><strong>Captured session history</strong><p>${number(captured.length)} loaded records across captured sources · channel, repository, and session identifiers</p></div><span class="section-meta">${state.historyOpen ? 'Collapse' : 'Open history'}</span></summary>${state.historyOpen ? table('peers', captured, 'Captured source sessions') : ''}</details>`;
    const coverage = coverageRows(census?.coverage);
    const sources = coverage.length ? panel('Runtime source coverage', `<div class="panel-body mini-list">${coverage.map((r) => `<div class="mini-row"><div><div class="mini-label">${escape(title(first(source(r), r.name, r.source_id)))}</div>${r.scope ? `<div class="mini-sub">${escape(r.scope)}</div>` : ''}${r.unread_regions?.length ? `<div class="mini-sub">Unobserved: ${escape(r.unread_regions.join(' · '))}</div>` : ''}${r.observed_at ? `<div class="mini-sub">Source observed ${escape(date(r.observed_at))} · ${escape(relative(r.observed_at))}</div>` : ''}</div><div class="mini-number">${badge(first(r.freshness?.state === 'STALE' || r.fresh === false ? 'stale' : null, r.status, 'unknown'))}${r.complete === false ? '<div class="mini-sub">Partial coverage</div>' : ''}</div></div>`).join('')}</div>`, 'All reported runtime roads, including unavailable sources and unknown browser or cloud bindings') : '';
    return `${totals}${live}${history}${sources ? `<div class="spaced-grid">${sources}</div>` : ''}`;
  }
  function render() {
    document.querySelectorAll('.tab').forEach((b) => {
      const active = b.dataset.view === state.view;
      b.classList.toggle('active', active);
      if (active) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    const view = state.view === 'overview' ? 'events' : state.view;
    $('content').setAttribute('aria-busy', String(Boolean(state.viewLoading[view] || (state.view === 'overview' && state.loading))));
    $('content').innerHTML = state.view === 'overview' ? state.snapshot ? overview() : `${panel(state.summaryError ? 'Summary is unavailable' : 'Summary is being prepared', '<div class="panel-body">Collection totals will appear when the summary is available. You can browse every detail view and the latest collected activity below.</div>')}${table('events', state.data.events || [], 'Recent activity')}` : state.view === 'peers' ? peersView() : table(state.view, state.data[state.view] || []);
  }
  function updateFilters() {
    const all = state.view === 'overview' ? [...(state.data.events || []), ...(state.data.peers || []), ...(state.snapshot?.providers || []), ...(state.snapshot?.harnesses || []), ...(state.snapshot?.sources || []), ...(state.snapshot?.source_groups || []).map((group) => ({ source: group.name, harness: group.harness })), ...coverageRows(state.snapshot?.census?.coverage)] : state.view === 'peers' ? [...(state.snapshot?.census?.peers || []), ...(state.data.peers || [])] : state.data[state.view] || [];
    for (const [id, fn, label] of [['provider', provider, 'providers'], ['harness', harness, 'harnesses'], ['source', source, 'sources']]) {
      const values = [...new Set(all.map(fn).filter(present).map(String))].sort();
      if (state.filters[id] && !values.includes(state.filters[id])) values.push(state.filters[id]);
      $(id).innerHTML = `<option value="">All ${label}</option>${values.map((v) => `<option value="${escape(v)}">${escape(title(v))}</option>`).join('')}`;
      $(id).value = state.filters[id];
    }
  }
  async function fetchJson(url) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const r = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store', signal: controller.signal });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = await r.json();
      if (!body || body.ok === false) throw new Error(body?.error || 'No snapshot returned');
      return body;
    } finally { clearTimeout(timeout); }
  }
  const arrayFor = (data, view) => {
    const candidates = view === 'sources' ? ['coverage', 'resources', 'sources'] : view === 'accounts' ? ['accounts', 'resources'] : [view];
    for (const key of candidates) if (Array.isArray(data?.[key])) return data[key];
    return [];
  };
  function seed(data) {
    for (const view of Object.keys(endpoints)) {
      if (state.loadedViews[view]) continue;
      const rows = arrayFor(data, view);
      if (rows.length || !state.data[view]) state.data[view] = rows;
      const meta = data.result_metadata?.[view] || data[`${view}_metadata`] || data[`${view}_meta`];
      if (meta) state.resultMeta[view] = meta;
    }
    if (!state.data.sources?.length) state.data.sources = data.sources || [];
  }
  function header() {
    $('mode').textContent = state.mode === 'static' ? 'Saved snapshot' : state.summaryError ? state.snapshot?.census?.observed_at ? 'Runtime available · totals retrying' : 'Historical summary retrying' : state.summaryPending ? 'Preparing summary' : state.snapshot?.summary_totals_ready === false ? 'Live census · preparing totals' : state.snapshot?.summary_refreshing ? 'Refreshing summary' : state.snapshot ? 'Collected data' : 'Connecting';
    const runtimeObserved = state.snapshot?.census?.observed_at;
    const historicalObserved = state.snapshot?.summary_historical_observed_at || state.snapshot?.observed_at;
    $('observed-at').textContent = state.snapshot ? `${runtimeObserved ? `Runtime observed ${date(runtimeObserved)}` : 'Runtime observation pending'}${state.snapshot.summary_totals_ready === false ? ' · historical totals preparing' : historicalObserved ? ` · historical totals ${relative(historicalObserved)}` : ''}` : 'Waiting for the first completed summary · detail views remain available';
    $('json-link').href = state.mode === 'static' ? '../data-snapshot.json' : '/api/telemetry/snapshot';
    $('agent-tools').hidden = state.mode === 'static';
    $('peer-tab-count').textContent = present(state.snapshot?.census?.counts?.observed_instances) ? number(state.snapshot.census.counts.observed_instances) : '';
  }
  function loadView(view, append = false) {
    if (state.mode !== 'api') return Promise.resolve();
    const query = new URLSearchParams({ limit: view === 'events' || view === 'sources' || view === 'accounts' || view === 'notifications' ? '100' : '1000' });
    if (view === 'events') query.set('order', 'desc');
    if (append && state.cursors[view]) query.set('cursor', state.cursors[view]);
    if (view === 'events' || view === 'sources') for (const [k, v] of Object.entries(state.filters)) if (v) query.set(k, v);
    const key = query.toString();
    if (state.requests[view]?.key === key) return state.requests[view].promise;
    const serial = state.requestSerial[view] = (state.requestSerial[view] || 0) + 1;
    state.viewLoading[view] = true;
    render();
    const request = (async () => {
      try {
        const data = await fetchJson(`/api/telemetry/${endpoints[view]}?${query}`);
        if (serial !== state.requestSerial[view] || state.mode !== 'api') return;
        const rows = arrayFor(data, view);
        state.data[view] = append ? [...(state.data[view] || []), ...rows] : rows;
        state.loadedViews[view] = true;
        state.cursors[view] = data.has_more === false ? null : data.next_cursor || null;
        state.resultMeta[view] = { complete: data.complete, truncated: data.truncated, total: first(data.total, data.total_count, data.available), has_more: data.has_more, observed_at: data.observed_at };
        delete state.errors[view];
        delete state.failedAppends[view];
      } catch (e) {
        if (serial !== state.requestSerial[view] || state.mode !== 'api') return;
        state.errors[view] = `The ${endpoints[view]} view could not be refreshed (${e.name === 'AbortError' ? 'request timed out' : e.message}).`;
        state.failedAppends[view] = append;
      } finally {
        if (serial === state.requestSerial[view]) {
          state.viewLoading[view] = false;
          delete state.requests[view];
          updateFilters();
          render();
        }
      }
    })();
    state.requests[view] = { key, promise: request };
    return request;
  }
  function loadCurrentView() {
    return Promise.all((state.view === 'overview' ? ['events', 'peers'] : [state.view]).map((view) => loadView(view)));
  }
  async function refresh(reloadDetails = true) {
    if (state.loading) return;
    clearTimeout(state.summaryTimer);
    state.loading = true;
    $('refresh').disabled = true;
    let retryAfter = null;
    if (reloadDetails) loadCurrentView();
    header();
    render();
    try {
      let data;
      try { data = await fetchJson('/api/telemetry/summary'); state.mode = 'api'; }
      catch (summaryError) {
        if (location.protocol !== 'file:' && summaryError.message !== 'HTTP 404') throw summaryError;
        data = await fetchJson('../data-snapshot.json');
        state.mode = 'static';
        $('notice').textContent = 'Viewing the saved collection snapshot. Refresh reloads this file; its collection time is shown above.';
        $('notice').hidden = false;
      }
      if (state.mode === 'api' && data.summary_ready === false) {
        state.summaryPending = true;
        state.summaryError = data.summary_refresh_error || null;
        $('notice').textContent = data.summary_refresh_error ? `The summary refresh needs recovery (${data.summary_refresh_error}). Retrying while the collected records remain available.` : 'Preparing the complete summary from captured records. Source detail and original records remain available.';
        $('notice').hidden = false;
        retryAfter = 2000;
        return;
      }
      state.summaryPending = false;
      state.summaryError = data.summary_refresh_error || null;
      state.snapshot = data.snapshot || data;
      seed(state.snapshot);
      if (data.snapshot) seed(data);
      $('notice').hidden = state.mode !== 'static';
      if (state.snapshot.summary_live_error || state.snapshot.summary_live_from_cache || state.snapshot.summary_live_stale) {
        $('notice').textContent = `The runtime census read needs recovery${state.snapshot.summary_live_error ? ` (${state.snapshot.summary_live_error})` : ''}. Displaying the prior source observation while the live read retries; historical totals and detail views remain available.`;
        $('notice').hidden = false;
        retryAfter = 3000;
      } else if (state.snapshot.summary_refreshing || state.snapshot.summary_totals_ready === false || state.summaryError) {
        $('notice').textContent = state.summaryError ? `The historical totals refresh failed (${state.summaryError}); retrying while the runtime census and collected detail views remain available.` : state.snapshot.summary_totals_ready === false ? 'Runtime census is available. Historical totals are being prepared from captured records; every detail view remains available.' : 'Showing the last completed summary while the latest captured totals refresh. All source partitions remain included.';
        $('notice').hidden = false;
        retryAfter = 3000;
      }
    } catch (e) {
      state.summaryError = e.name === 'AbortError' ? 'request timed out' : e.message;
      $('notice').textContent = `The telemetry summary could not be refreshed (${state.summaryError}). ${state.snapshot ? 'Showing the last available summary while it retries.' : 'Retrying the summary.'} Collected detail views remain available.`;
      $('notice').hidden = false;
      if (state.mode !== 'static') retryAfter = 3000;
    } finally {
      state.loading = false;
      $('refresh').disabled = false;
      header();
      updateFilters();
      render();
      if (state.mode === 'api' && retryAfter === null) retryAfter = 10000;
      if (retryAfter !== null) state.summaryTimer = setTimeout(() => refresh(false), retryAfter);
    }
  }
  async function changeView(view, updateHistory = true) {
    if (!labels[view]) return;
    state.view = view;
    if (updateHistory && location.hash !== `#${view}`) history.pushState(null, '', `#${view}`);
    updateFilters();
    render();
    if (state.mode === 'api') await loadCurrentView();
  }
  document.querySelectorAll('.tab').forEach((b) => b.addEventListener('click', () => changeView(b.dataset.view)));
  const hashView = () => labels[location.hash.slice(1)] ? location.hash.slice(1) : 'overview';
  const syncView = () => { const view = hashView(); if (view !== state.view) changeView(view, false); };
  window.addEventListener('hashchange', syncView);
  window.addEventListener('popstate', syncView);
  $('refresh').addEventListener('click', () => refresh());
  let debounce;
  function filterChanged() {
    state.filters = { q: $('search').value.trim(), provider: $('provider').value, harness: $('harness').value, source: $('source').value };
    state.pages.sources = 0;
    render();
    clearTimeout(debounce);
    if (state.view === 'overview' && state.mode === 'api') debounce = setTimeout(() => loadView('events'), 300);
    if (state.view === 'sources' && state.mode === 'api') debounce = setTimeout(() => loadView('sources'), 300);
  }
  $('search').addEventListener('input', filterChanged);
  for (const id of ['provider', 'harness', 'source']) $(id).addEventListener('change', filterChanged);
  $('clear-filters').addEventListener('click', () => {
    $('search').value = '';
    for (const id of ['provider', 'harness', 'source']) $(id).value = '';
    filterChanged();
  });
  $('content').addEventListener('click', (event) => {
    const b = event.target.closest('button');
    if (!b) return;
    if (b.dataset.open) changeView(b.dataset.open);
    if (b.dataset.more) { b.disabled = true; b.textContent = 'Loading…'; loadView(b.dataset.more, true); }
    if (b.dataset.retry) loadView(b.dataset.retry, state.failedAppends[b.dataset.retry] === true);
    if (b.dataset.page) { state.pages[b.dataset.page] = (state.pages[b.dataset.page] || 0) + Number(b.dataset.step); render(); $('content').querySelector('.panel-head')?.scrollIntoView({ block: 'start' }); }
    if (b.dataset.sort) {
      const view = b.dataset.sort, index = Number(b.dataset.column), prev = state.sort[view];
      state.sort[view] = { index, get: columns[view][index].get, direction: prev?.index === index ? -prev.direction : 1 };
      state.pages[view] = 0;
      render();
      $('content').querySelector(`[data-sort="${view}"][data-column="${index}"]`)?.focus();
    }
  });
  $('content').addEventListener('toggle', (event) => {
    if (event.target.id !== 'captured-history' || event.target.open === state.historyOpen) return;
    state.historyOpen = event.target.open;
    render();
  }, true);
  state.view = hashView();
  refresh();
})();
