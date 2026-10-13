'use strict';
(() => {
  const api = window.CommonsPanel;
  const view = document.getElementById('view-work');
  if (!api || !view) return;
  const node = (tag, cls = '', value) => {
    const element = document.createElement(tag);
    if (cls) element.className = cls;
    if (value !== undefined) element.textContent = String(value);
    return element;
  };
  const known = value => value !== undefined && value !== null && value !== '' && value !== 'UNKNOWN';
  const value = field => known(field) ? String(field) : 'Unknown';
  const date = field => {
    const parsed = typeof field === 'string' ? Date.parse(field) : NaN;
    return Number.isFinite(parsed) ? new Date(parsed).toLocaleString() : 'Unknown';
  };
  const badge = label => node('span', 'badge ' + (/BLOCKED|stale|unread|recoverable/i.test(label) ? 'warn' : label === 'SHIPPED' ? 'good' : 'neutral'), label);
  const panel = node('article', 'panel');
  panel.id = 'canonical-task-panel';
  const heading = node('div', 'panel-heading');
  const title = node('div');
  title.append(node('h2', '', 'Canonical task queue'), node('p', '', 'One task state from shared claims, alongside the source records below.'));
  const refreshButton = node('button', 'button button-small button-quiet', 'Refresh tasks');
  refreshButton.type = 'button';
  heading.append(title, refreshButton);
  const note = node('p', 'field-help', 'Task state has not been read yet.');
  note.id = 'canonical-task-note';
  note.setAttribute('role', 'status');
  const counts = node('div', 'work-stage-grid');
  counts.id = 'canonical-task-counts';
  const filters = node('div', 'filter-bar work-filter-bar');
  const search = node('input');
  search.type = 'search'; search.placeholder = 'Search canonical tasks, workers or blockers';
  search.setAttribute('aria-label', 'Search canonical tasks');
  const searchLabel = node('label', 'search-field'); searchLabel.append(search);
  const stateFilter = node('select'); stateFilter.setAttribute('aria-label', 'Filter canonical lifecycle');
  [['working', 'Open, active and blocked'], ['all', 'All task states'], ['recoverable', 'Recoverable tasks'],
    ...['OPEN', 'ACTIVE', 'SHIPPED', 'BLOCKED', 'SUPERSEDED', 'ABANDONED'].map(state => [state, state])]
    .forEach(([id, label]) => { const option = node('option', '', label); option.value = id; stateFilter.append(option); });
  filters.append(searchLabel, stateFilter);
  const rows = node('div', 'work-table-wrap'); rows.id = 'canonical-task-rows';
  const coverage = node('details', 'raw-details');
  coverage.append(node('summary', '', 'Source coverage and projection details'));
  const details = node('div'); coverage.append(details);
  panel.append(heading, note, counts, filters, rows, coverage);
  view.querySelector('.page-heading').after(panel);
  let snapshot = null, error = '', inFlight = null, rerun = false, lastAttempt = 0, retryAt = 0, freshnessTimer;
  let selectedState = 'working', query = '';
  let exactTask = new URLSearchParams(location.search).get('swarm_task') || '';
  if (exactTask) { selectedState = 'all'; stateFilter.value = 'all'; search.value = exactTask; }

  function freshness() {
    if (!snapshot) return 'unread';
    const age = Date.now() - Date.parse(snapshot.observed_at);
    if (!Number.isFinite(age) || age < -300000) return 'unknown observation time';
    return error || age >= 90000 ? 'retained / stale observation' : 'current observation';
  }
  function taskLink(task) {
    if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(task.repo || '')) return null;
    for (const [kind, raw] of [['pull', task.pr], ['issues', task.issue]]) {
      const number = Number(raw);
      if (Number.isSafeInteger(number) && number > 0) return 'https://github.com/' + task.repo + '/' + kind + '/' + number;
    }
    return null;
  }
  function taskURL(key) {
    const target = new URL(location.href);
    target.searchParams.set('swarm_task', key); target.hash = 'work';
    return target.href;
  }
  function render() {
    clearTimeout(freshnessTimer);
    const age = snapshot ? Date.now() - Date.parse(snapshot.observed_at) : NaN;
    const deadlines = [];
    if (!error && Number.isFinite(age) && age >= -300000 && age < 90000) deadlines.push(90000 - age);
    if (retryAt > Date.now()) deadlines.push(retryAt - Date.now());
    if (deadlines.length) freshnessTimer = setTimeout(render, Math.max(1, Math.min(...deadlines)));
    rows.replaceChildren(); counts.replaceChildren(); details.replaceChildren();
    const retryNote = retryAt > Date.now() ? ' Retry available after ' + date(new Date(retryAt).toISOString()) + '.' : '';
    refreshButton.disabled = !!inFlight || retryAt > Date.now();
    note.className = error ? 'source-error' : 'field-help';
    if (!snapshot) {
      note.textContent = error ? 'Task read failed: ' + error + '. No canonical state is available.' + retryNote : 'Reading shared task state…';
      rows.append(node('p', 'field-help', 'Unread task state does not mean the queue is empty.'));
      return;
    }
    const summary = snapshot.summary || {};
    const tasks = snapshot.tasks;
    const sources = snapshot.coverage && typeof snapshot.coverage === 'object' ? Object.entries(snapshot.coverage) : [];
    const partial = sources.filter(([, source]) => source?.complete !== true).length;
    const matches = tasks.filter(task => {
      if (exactTask && task.task_key !== exactTask) return false;
      const stateMatches = selectedState === 'all' || selectedState === 'working' && ['OPEN', 'ACTIVE', 'BLOCKED'].includes(task.state) ||
        selectedState === 'recoverable' && task.recoverable === true || task.state === selectedState;
      return stateMatches && [task.task_key, task.title, task.worker, task.blocker, task.next_action, task.exact_error]
        .filter(known).join(' ').toLowerCase().includes(query);
    });
    const order = {ACTIVE: 0, BLOCKED: 1, OPEN: 2, SHIPPED: 3, SUPERSEDED: 4, ABANDONED: 5};
    matches.sort((a, b) => (order[a.state] ?? 6) - (order[b.state] ?? 6) || String(a.task_key).localeCompare(String(b.task_key)));
    const shown = matches.slice(0, 200);
    note.textContent = (error ? 'Read failed: ' + error + '. Previous snapshot retained.' + retryNote + ' ' : '') +
      freshness() + ' · observed ' + date(snapshot.observed_at) + ' · ' + shown.length + ' shown / ' + matches.length +
      ' matching / ' + tasks.length + ' loaded / ' + value(snapshot.total) + ' total tasks' +
      (snapshot.truncated ? ' · Partial task list: filters cover loaded rows only.' : '.') +
      (matches.length > shown.length ? ' Narrow the filters to see the remaining matches.' : '') +
      (sources.length ? ' ' + partial + ' of ' + sources.length + ' source coverages partial or unknown.' : ' Source coverage is unknown.');
    for (const [state, count] of Object.entries(summary.counts || {})) {
      const card = node('div', 'work-stage'); card.append(node('strong', '', count), node('span', '', state)); counts.append(card);
    }
    const metrics = node('p', 'field-help work-stage-note', value(summary.recoverable_count) + ' recoverable · ' +
      value(summary.stale_seat_count) + ' stale seats · ' + value(summary.collision_count) + ' recorded collisions');
    counts.append(metrics);
    if (!shown.length) {
      let message = 'No matching tasks in the returned snapshot. Source coverage below may be partial.';
      if (exactTask) message = tasks.some(task => task.task_key === exactTask)
        ? 'The linked task is outside the selected lifecycle filter. Choose All task states to see it.'
        : 'Linked task ' + exactTask + ' is not in the returned snapshot. It may be outside the loaded task limit or source coverage.';
      rows.append(node('p', 'field-help', message));
    }
    else {
      const table = node('table', 'work-table'), head = node('thead'), headings = node('tr'), body = node('tbody');
      ['Task / next action', 'Lifecycle', 'Worker', 'Activity / evidence'].forEach(label => headings.append(node('th', '', label)));
      head.append(headings); table.append(head, body);
      for (const task of shown) {
        const row = node('tr'), taskCell = node('td'), lifecycle = node('td'), worker = node('td'), evidence = node('td');
        const url = taskLink(task);
        const label = node(url ? 'a' : 'strong', 'work-title', known(task.title) ? task.title : task.task_key);
        if (url) { label.href = url; label.target = '_blank'; label.rel = 'noopener noreferrer'; }
        const permalink = node('a', 'work-row-sub', value(task.task_key));
        permalink.href = taskURL(task.task_key); permalink.target = '_blank'; permalink.rel = 'noopener noreferrer';
        permalink.title = 'Open current state for this exact task';
        taskCell.append(label, permalink, node('p', 'work-next', 'Next: ' + value(task.next_action)));
        if (known(task.blocker)) taskCell.append(node('p', 'source-error', 'Blocker: ' + value(task.blocker)));
        if (known(task.exact_error) && task.exact_error !== task.blocker) taskCell.append(node('p', 'source-error', 'Provider: ' + value(task.exact_error)));
        lifecycle.append(badge(value(task.state)));
        if (task.recoverable === true) lifecycle.append(badge('recoverable'));
        if (known(task.reconciliation_needed)) lifecycle.append(node('p', 'field-help', 'Needs reconciliation: ' + value(task.reconciliation_needed)));
        if (known(task.superseded_by)) lifecycle.append(node('p', 'field-help', 'Superseded by ' + value(task.superseded_by)));
        worker.append(node('span', '', value(task.worker)));
        if (known(task.owner_liveness)) worker.append(node('span', 'work-row-sub', 'Owner ' + value(task.owner_liveness)));
        const heartbeat = known(task.lease?.heartbeat) ? task.lease.heartbeat : task.heartbeat;
        if (known(heartbeat)) worker.append(node('span', 'work-row-sub', 'Heartbeat ' + date(heartbeat)));
        evidence.append(node('span', '', date(task.latest_activity)), node('span', 'work-row-sub', 'Head ' + value(task.head_sha)));
        if (known(task.merge_sha)) evidence.append(node('span', 'work-row-sub', 'Merged ' + value(task.merge_sha)));
        if (known(task.landed_sha)) evidence.append(node('span', 'work-row-sub', 'Landed ' + value(task.landed_sha)));
        row.append(taskCell, lifecycle, worker, evidence); body.append(row);
      }
      rows.append(table);
    }
    details.append(node('p', 'field-help', 'Authority: ' + value(snapshot.authority) + ' · claim tip ' + value(snapshot.tip)),
      node('p', 'field-help', 'Consumed feed cursor: ' + value(snapshot.feed_cursor)),
      node('p', 'field-help', (Array.isArray(snapshot.rejected) ? snapshot.rejected.length : 'Unknown') + ' rejected events in the returned window.'));
    if (/^[0-9a-f]{40}$/i.test(snapshot.tip || '')) {
      const ledger = node('a', 'source-link', 'Open exact task ledger ↗');
      ledger.href = 'https://github.com/woahwhattheheck/commons/blob/' + snapshot.tip + '/holdings/swarm-runtime.json';
      ledger.target = '_blank'; ledger.rel = 'noopener noreferrer'; details.append(ledger);
    }
    if (!sources.length) details.append(node('p', 'field-help', 'Source coverage is unknown.'));
    sources.forEach(([name, source]) => {
      const item = node('details', 'raw-details');
      item.append(node('summary', '', name + ' · ' + (source?.complete === true ? 'complete for stated scope' : source?.complete === false ? 'partial' : 'unknown coverage')),
        node('pre', '', JSON.stringify(source, null, 2))); details.append(item);
    });
    if (Array.isArray(snapshot.collisions) && snapshot.collisions.length) details.append(node('h3', '', 'Recent collision observations'), node('pre', '', JSON.stringify(snapshot.collisions, null, 2)));
  }
  function refresh(explicit = false) {
    if (inFlight) { if (explicit) rerun = true; return inFlight; }
    if (document.hidden || Date.now() < retryAt || !explicit && (view.hidden || Date.now() - lastAttempt < 30000)) { render(); return Promise.resolve(); }
    lastAttempt = Date.now(); refreshButton.disabled = true;
    inFlight = (async () => {
      try {
        const {body} = await api.request('/api/swarm/tasks?limit=1000' + (explicit ? '&refresh=1' : ''));
        if (!body || body.ok !== true || !Array.isArray(body.tasks)) {
          const failure = new Error(body?.message || body?.reason || body?.error || 'Canonical task response is missing its task list.');
          failure.body = body; throw failure;
        }
        snapshot = body; error = ''; retryAt = 0;
      } catch (failure) {
        error = failure.message || String(failure);
        const delay = failure.body?.retry_after;
        retryAt = typeof delay === 'number' && Number.isFinite(delay) && delay > 0 ? Date.now() + delay * 1000 : 0;
      }
      finally {
        inFlight = null; refreshButton.disabled = false; render();
        if (rerun) { rerun = false; refresh(true); }
      }
    })();
    return inFlight;
  }
  search.addEventListener('input', () => {
    if (exactTask) { const target = new URL(location.href); target.searchParams.delete('swarm_task'); history.replaceState(null, '', target); }
    exactTask = ''; query = search.value.trim().toLowerCase(); render();
  });
  stateFilter.addEventListener('change', () => { selectedState = stateFilter.value; render(); });
  refreshButton.addEventListener('click', () => refresh(true));
  document.getElementById('refresh-button').addEventListener('click', () => { if (!view.hidden) refresh(true); });
  document.querySelector('[data-view="work"]')?.addEventListener('click', () => refresh());
  window.addEventListener('commons-state', () => refresh());
  window.addEventListener('hashchange', () => { if (location.hash === '#work') refresh(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  render(); refresh();
})();
