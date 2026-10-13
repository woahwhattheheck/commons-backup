'use strict';
(() => {
  const root = document.querySelector('#view-focus .main-column');
  if (!root) return;
  const card = document.createElement('article'); card.className = 'panel'; card.id = 'deathstar-summary';
  const heading = document.createElement('h2'); heading.textContent = 'Deathstar · decisions';
  const status = document.createElement('p'); status.className = 'field-help'; status.setAttribute('role', 'status');
  const body = document.createElement('div');
  const button = document.createElement('button'); button.type = 'button'; button.className = 'text-button'; button.textContent = 'Refresh shared view';
  card.append(heading, status, body, button); root.prepend(card);
  let busy = false, timer, lastDecisions = [];
  const line = (title, detail) => {
    const row = document.createElement('p'); row.className = 'work-next';
    const label = document.createElement('strong'); label.textContent = title + ' ';
    row.append(label, document.createTextNode(detail)); return row;
  };
  const el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const money = value => Array.isArray(value) ? (value.map(v => v.currency + ' ' + v.amount).join(' + ') || '0') : 'unknown';
  const age = seconds => typeof seconds === 'number' ? (seconds < 3600 ? Math.round(seconds / 60) + 'm' : seconds < 172800 ? Math.round(seconds / 3600) + 'h' : Math.round(seconds / 86400) + 'd') : 'unknown';
  const WAIT = {waiting_on_us: 'on us', waiting_on_them: 'on them', none: 'nothing', unknown: 'unknown'};
  const SETTLEMENT = {partial: 'partly paid', amount_unknown: 'reconcile payment amount', covered: 'advertised amount covered'};
  const TASK_BUDGET_KIND = /^(?:task|run)[ _-]?budget$/i;
  const TASK_BUDGET_WARN_FRACTION = 0.75;
  function taskBudgetLines() {
    // Node/vm harness has no window; browsers expose CommonsPanel on window/globalThis.
    const rootObj = typeof window !== 'undefined' ? window : globalThis;
    const panel = rootObj && rootObj.CommonsPanel;
    const state = panel && typeof panel.getState === 'function' ? panel.getState() : null;
    const budgets = state && Array.isArray(state.budgets) ? state.budgets : [];
    const rows = [];
    for (const b of budgets) {
      const kind = String(b.kind || b.measure_type || '').trim();
      if (!TASK_BUDGET_KIND.test(kind) || typeof b.limit !== 'number' || !Number.isFinite(b.limit) || b.limit <= 0 ||
          typeof b.used !== 'number' || !Number.isFinite(b.used) || typeof b.observed_at !== 'string' ||
          !Number.isFinite(Date.parse(b.observed_at)) || typeof b.source_url !== 'string' || !/^https?:\/\//i.test(b.source_url)) continue;
      const ratio = b.used / b.limit;
      const unit = b.unit || 'unit unknown';
      const provider = b.provider || 'provider unknown';
      const threshold = Math.round(TASK_BUDGET_WARN_FRACTION * 100);
      let detail = b.used.toLocaleString() + ' / ' + b.limit.toLocaleString() + ' ' + unit +
        ' (' + Math.round(ratio * 100) + '%) · ' + provider + ' · observed ' + b.observed_at + ' · source ' + b.source_url;
      if (ratio >= TASK_BUDGET_WARN_FRACTION)
        detail += ' · WARNING: local ' + threshold + '% task-budget threshold reached; review before the next expensive stage.';
      else detail += ' · local warning threshold ' + threshold + '%.';
      rows.push(line((b.label || b.id || 'Task budget') + ':', detail));
    }
    return rows;
  }
  // Exceptions first, then one row per active operation; stages and receipts are drilldowns.
  const REASON = {deadline_past: 'DEADLINE PASSED', deadline_within_7d: 'due within 7d', stalled: 'stalled', owner_only: 'owner only', partial_payout: 'partial payment', unreconciled_payout: 'reconcile payment amount'};
  function decisions(d) {
    const out = [];
    const exceptions = d.exceptions || [], blocked = d.blocked_agents || [];
    const control = d.operator_control || {}, mode = control.mode || 'unknown';
    const opLine = line('Operator control:', mode + (mode === 'RUN' ? '' : ' — new work should not start') +
      (control.set_by ? ' · set by ' + control.set_by : '') + (control.set_at ? ' at ' + control.set_at : '') + (control.note ? ' · ' + control.note : ''));
    if (mode === 'DRAIN' || mode === 'ABORT') opLine.className = 'work-next decision-halt';
    out.push(opLine);
    const c = d.collection || {};
    out.push(line('Collection:', (c.complete === true ? 'complete' : c.complete === false ? 'incomplete' : 'unknown') +
      (typeof c.expected_count === 'number' ? ' · ' + c.fetched_count + '/' + c.expected_count + ' fetched, ' + c.failed_count + ' failed, ' + c.deferred_count + ' deferred, ' + c.skipped_count + ' skipped' : '') +
      ((c.cooldowns || []).length ? ' · cooldowns: ' + c.cooldowns.map(v => v.scope + ' until ' + v.retry_not_before).join('; ') : '')));
    out.push(line('Exceptions:', exceptions.length ? '' : 'None observed.'));
    for (const e of exceptions)
      out.push(line(e.operation + ' · ' + (REASON[e.reason] || e.reason.replaceAll('_', ' ')) + ':',
        (e.stage ? e.stage.replaceAll('_', ' ') : 'outward write') + (e.deadline ? ' · due ' + e.deadline : '') +
        (e.stage_age_days != null ? ' · ' + e.stage_age_days + 'd (window ' + e.gate_window_days + 'd)' : '') +
        ' · ' + e.who_acts.replace('_', ' ') + ' · account ' + e.account + ' · ' + e.action));
    out.push(line('Blocked agents:', blocked.length ? blocked.map(a => a.operation + ' · ' + a.seat + ' (' + a.model_family + ', heartbeat ' + age(a.heartbeat_age_seconds) + ')' + (a.blocker ? ' · ' + a.blocker : '')).join('; ') : 'None observed.'));
    const m = d.money || {};
    out.push(line('Operations:', (d.operations ? d.operations.active : 0) + ' active · advertised remaining ' + money(m.at_risk) + ' · known collected ' + money(m.collected) + '.'));
    const rows = d.rows || [];
    if (!rows.length) return out;
    const table = el('table', undefined, 'work-table decision-table'), head = el('tr');
    for (const name of ['Operation', 'Stage', 'Waiting', 'Next action', 'Owner', 'Agents', 'Sources', 'Advertised remaining', 'Known collected'])
      head.append(el('th', name));
    table.append(head);
    for (const r of rows) {
      const tr = el('tr', undefined, r.gate_stale ? 'decision-stale' : undefined);
      const unknown = (r.unknown || []).map(u => u.field + ' unknown: ' + u.answer_source).join('; ');
      const cells = [
        r.operation + (r.publication_state !== 'clear' ? ' · ' + r.publication_state : ''),
        r.stage.replaceAll('_', ' ') + ' (' + r.stage_state + ')' + (r.merged_prs ? ' · ' + r.merged_prs + ' merged' : '') + (r.stage_age_days != null ? ' · ' + r.stage_age_days + 'd' : '') + (r.gate_stale ? ' · STALLED' : '') + (SETTLEMENT[r.settlement_state] ? ' · ' + SETTLEMENT[r.settlement_state] : ''),
        (WAIT[r.waiting_on] || r.waiting_on) + ': ' + r.waiting_for,
        r.next_action,
        r.owner.owner_account + ' / ' + r.owner.seat,
        (r.agents || []).map(a => a.seat + ' ' + a.model_family + ' ' + a.state + ' ' + age(a.heartbeat_age_seconds)).join('; ') || 'unknown',
        (r.sources || []).map(v => v.id + ' (' + v.collector + ') ' + v.freshness + ' ' + age(v.last_success_age_seconds) + ' · last cycle ' + v.last_cycle + ' · cooldown ' + v.cooldown + ' · coverage ' + v.coverage).join('; ') || 'unknown',
        money(r.money_at_risk), money(r.money_collected) + (Array.isArray(r.money_collected) && (r.unknown || []).some(u => u.field === 'money_collected') ? ' (known portion; reconciliation pending)' : ''),
      ];
      for (const text of cells) tr.append(el('td', text));
      table.append(tr);
      const drill = el('tr'), cell = el('td'), details = el('details');
      cell.setAttribute('colspan', '9');
      details.append(el('summary', (r.stages || []).length + ' stages · ' + r.receipt_count + ' receipts' + (unknown ? ' · ' + unknown : '')));
      const stages = el('ul');
      for (const st of r.stages || [])
        stages.append(el('li', st.stage.replaceAll('_', ' ') + ' · ' + st.state + ' · ' + st.who_acts.replace('_', ' ') + ' · ' + st.owner_account + (st.deadline ? ' · due ' + st.deadline : '') + ' · ' + st.evidence));
      const list = el('ul');
      for (const receipt of r.receipts || []) {
        const item = el('li');
        const label = receipt.kind + ' · ' + receipt.status + ' · ' + (receipt.title || receipt.item_id);
        if (/^https?:\/\//.test(receipt.url || '')) {
          const link = el('a', label); link.setAttribute('href', receipt.url); link.setAttribute('rel', 'noreferrer'); item.append(link);
        } else item.append(document.createTextNode(label + ' · ' + receipt.source_id));
        list.append(item);
      }
      details.append(stages, list); cell.append(details); drill.append(cell); table.append(drill);
    }
    const wrap = el('div', undefined, 'work-table-wrap');
    wrap.append(table); out.push(wrap);
    return out;
  }
  async function refresh() {
    if (busy || document.visibilityState === 'hidden') return;
    busy = true; button.disabled = true;
    const abort = new AbortController(), timeout = setTimeout(() => abort.abort(), 10000);
    try {
      const response = await fetch('/api/summary', {signal: abort.signal});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const s = await response.json(), w = s.work, src = s.sources;
      const nextBody = document.createElement('div');
      if (typeof s.decisions === 'string') {
        try {
          const reply = await fetch(s.decisions, {signal: abort.signal});
          if (!reply.ok) throw new Error('HTTP ' + reply.status);
          lastDecisions = decisions(await reply.json());
        } catch (error) {
          lastDecisions = [line('Decision view:', 'unavailable (' + error.message + '). Prior decision rows are retained below.'),
            ...lastDecisions.filter(node => !node.decisionNotice)];
          lastDecisions[0].decisionNotice = true;
        }
        nextBody.append(...lastDecisions);
      }
      nextBody.append(line('Work:', w.open.fresh + ' current open; ' + (w.open.retained + w.open.stale + w.open.unknown) + ' retained / stale / unknown.'));
      nextBody.append(line('Coverage:', src.fresh + ' fresh sources of ' + src.total + '; ' + src.coverage_debt_count + ' with coverage to resolve.'));
      nextBody.append(line('Observed merges:', s.throughput.merged_prs['1h'] + ' in 1h; ' + s.throughput.merged_prs['24h'] + ' in 24h. Lower bounds, not complete provider totals.'));
      nextBody.append(line('Workers:', s.workers.explicit_heartbeats ? Object.entries(s.workers.liveness).map(([k,v]) => k + ': ' + v).join(' · ') : 'No explicit heartbeat coverage in this snapshot.'));
      const amounts = s.revenue.observed_amounts || [];
      nextBody.append(line('Money:', amounts.length ? amounts.map(v => v.currency + ' ' + v.amount + ' ' + v.status.replaceAll('_',' ')).join(' · ') : 'No typed payment records loaded. Quoted prices are not counted as cash.'));
      const budget = s.refresh.request_budget || {};
      nextBody.append(line('Provider traffic:', (budget.observed_attempts ?? 'Unknown') + ' observed attempts; ' + (budget.deferred_reads ?? 'unknown') + ' deferred reads in the last collector run.'));
      nextBody.append(...taskBudgetLines());
      for (const scope of (budget.scopes || []).filter(v => v.retry_remaining_seconds > 0).slice(0, 4))
        nextBody.append(line(scope.scope + ':', 'Cooldown until ' + scope.retry_not_before + '. Other work can continue.'));
      const rows = s.work.top_attention || [];
      for (const row of rows.slice(0, 4))
        nextBody.append(line(row.title || row.id, row.freshness + ' · ' + row.status + ' · ' + (row.next_action || 'No next action recorded')));
      const nextStatus = 'Shared snapshot ' + new Date(s.generated_at).toLocaleTimeString() + ' · summary and decision reads are cache-only · ' + (s.cache.hit ? 'cache hit' : s.telemetry.projection_ms + 'ms projection');
      body.replaceChildren(...nextBody.children);
      status.textContent = nextStatus;
    } catch (error) {
      status.textContent = 'Shared view unavailable (' + error.message + '). Prior displayed observations are retained.';
    } finally {
      clearTimeout(timeout); busy = false; button.disabled = false;
      clearTimeout(timer); timer = setTimeout(refresh, 30000);
    }
  }
  button.addEventListener('click', refresh);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState !== 'hidden') refresh(); });
  refresh();
})();
