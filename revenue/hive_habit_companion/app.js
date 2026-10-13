'use strict';

const ui = {
  connection: document.querySelector('#connection-status'),
  revision: document.querySelector('#revision-status'),
  error: document.querySelector('#error-banner'),
  goals: document.querySelector('#goals'),
  emptyGoals: document.querySelector('#empty-goals'),
  reminders: document.querySelector('#reminders'),
  focus: document.querySelector('#focus-sessions'),
  emptyFocus: document.querySelector('#empty-focus'),
  history: document.querySelector('#history'),
  emptyHistory: document.querySelector('#empty-history'),
  summaryActive: document.querySelector('#summary-active'),
  summaryDone: document.querySelector('#summary-done'),
  summaryPaused: document.querySelector('#summary-paused'),
  summaryFocus: document.querySelector('#summary-focus'),
  goalForm: document.querySelector('#goal-form'),
  goalId: document.querySelector('#goal-id'),
  goalTitle: document.querySelector('#goal-title'),
  goalIntention: document.querySelector('#goal-intention'),
  goalReminder: document.querySelector('#goal-reminder'),
  goalFocus: document.querySelector('#goal-focus'),
  goalSubmit: document.querySelector('#goal-submit'),
  noteForm: document.querySelector('#note-form'),
  noteGoal: document.querySelector('#note-goal'),
  noteBody: document.querySelector('#note-body'),
  restoreFile: document.querySelector('#restore-file'),
  eraseConfirm: document.querySelector('#erase-confirm'),
};

let state = null;
let csrfToken = '';
let focusRenderEpoch = performance.now();
let reminderRefreshInFlight = false;
const notified = new Set();

function operationId(prefix) {
  if (globalThis.crypto?.randomUUID) return `${prefix}-${crypto.randomUUID()}`;
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return `${prefix}-${Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')}`;
}

function showError(message) {
  ui.error.textContent = message;
  ui.error.classList.remove('hidden');
}

function clearError() {
  ui.error.textContent = '';
  ui.error.classList.add('hidden');
}

async function responseError(response) {
  try {
    const body = await response.json();
    return `${body.error || response.statusText}${body.code ? ` (${body.code})` : ''}`;
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

async function fetchState() {
  clearError();
  const response = await fetch('/api/state', {cache: 'no-store'});
  if (!response.ok) throw new Error(await responseError(response));
  state = await response.json();
  csrfToken = state.csrf_token;
  focusRenderEpoch = performance.now();
  render();
  return state;
}

async function change(action, payload) {
  clearError();
  const response = await fetch('/api/change', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Paceboard-CSRF': csrfToken,
    },
    body: JSON.stringify({action, operation_id: operationId(action.replace('.', '-')), payload}),
  });
  if (!response.ok) throw new Error(await responseError(response));
  await response.json();
  return fetchState();
}

function run(task) {
  Promise.resolve().then(task).catch(error => {
    showError(error?.message || String(error));
    ui.connection.textContent = 'Needs attention';
  });
}

function timeLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function duration(seconds) {
  const value = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const remainder = value % 60;
  if (hours) return `${hours}:${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`;
  return `${minutes}:${String(remainder).padStart(2, '0')}`;
}

function button(label, className, handler) {
  const node = document.createElement('button');
  node.type = 'button';
  node.textContent = label;
  if (className) node.className = className;
  node.addEventListener('click', handler);
  return node;
}

function latestText(goal) {
  const latest = goal.latest_checkin;
  if (!latest) return 'No check-in yet. Starting small still counts.';
  const messages = {
    DONE: 'Done was recorded',
    PAUSED: 'Paused without penalty',
    RESUMED: 'Resumed when ready',
  };
  const note = latest.note ? ` — ${latest.note}` : '';
  return `${messages[latest.kind]} · ${timeLabel(latest.created_at)}${note}`;
}

function fillGoalForm(goal = null) {
  ui.goalId.value = goal?.goal_id || '';
  ui.goalTitle.value = goal?.title || '';
  ui.goalIntention.value = goal?.intention || '';
  ui.goalReminder.value = String(goal?.reminder_minutes ?? 0);
  ui.goalFocus.value = String(goal?.target_focus_minutes ?? 25);
  ui.goalSubmit.textContent = goal ? 'Update goal' : 'Save goal';
  ui.goalForm.classList.remove('hidden');
  ui.goalTitle.focus();
}

function hideGoalForm() {
  ui.goalForm.reset();
  ui.goalId.value = '';
  ui.goalReminder.value = '0';
  ui.goalFocus.value = '25';
  ui.goalForm.classList.add('hidden');
}

function renderGoals() {
  ui.goals.replaceChildren();
  const goals = state.goals || [];
  ui.emptyGoals.classList.toggle('hidden', goals.length > 0);
  for (const goal of goals) {
    const fragment = document.querySelector('#goal-template').content.cloneNode(true);
    const card = fragment.querySelector('.goal-card');
    fragment.querySelector('.goal-title').textContent = goal.title;
    fragment.querySelector('.goal-intention').textContent = goal.intention || 'No intention note — the goal can stay simple.';
    const stateBadge = fragment.querySelector('.goal-state');
    stateBadge.textContent = goal.state;
    stateBadge.classList.toggle('archived', goal.state === 'ARCHIVED');
    fragment.querySelector('.latest-checkin').textContent = latestText(goal);
    const actions = fragment.querySelector('.goal-actions');
    const active = goal.state === 'ACTIVE';
    if (active) {
      actions.append(
        button('Done', '', () => recordCheckin(goal, 'DONE')),
        button('Pause day', 'pause', () => recordCheckin(goal, 'PAUSED')),
      );
      if (goal.latest_checkin?.kind === 'PAUSED') {
        actions.append(button('Resume', '', () => recordCheckin(goal, 'RESUMED')));
      }
      actions.append(button('Start focus', 'quiet', () => startFocus(goal)));
    }
    actions.append(
      button('Edit', 'quiet', () => fillGoalForm(goal)),
      button(active ? 'Archive' : 'Reactivate', 'quiet', () => run(() => change('goal.archive', {
        goal_id: goal.goal_id,
        state: active ? 'ARCHIVED' : 'ACTIVE',
      }))),
      button('Delete', 'delete', () => deleteItem('goal', goal.goal_id, `Delete “${goal.title}” and all of its history?`)),
    );
    card.dataset.goalId = goal.goal_id;
    ui.goals.append(fragment);
  }
}

function recordCheckin(goal, kind) {
  const prompts = {
    DONE: 'Anything you want to remember about what helped? (optional)',
    PAUSED: 'What made today a pause day? No explanation is required. (optional)',
    RESUMED: 'What made resuming possible? (optional)',
  };
  const note = window.prompt(prompts[kind], '');
  if (note === null) return;
  run(() => change('checkin.record', {goal_id: goal.goal_id, kind, note}));
}

function startFocus(goal) {
  const raw = window.prompt('Minutes for this focus session', String(goal.target_focus_minutes));
  if (raw === null) return;
  const planned = Number(raw);
  if (!Number.isInteger(planned) || planned < 1 || planned > 720) {
    showError('Focus minutes must be a whole number from 1 to 720.');
    return;
  }
  run(() => change('focus.start', {goal_id: goal.goal_id, planned_minutes: planned}));
}

function renderReminders() {
  ui.reminders.replaceChildren();
  const reminders = state.reminders || [];
  ui.reminders.classList.toggle('hidden', reminders.length === 0);
  for (const reminder of reminders) {
    const node = document.createElement('div');
    node.className = 'reminder';
    const when = reminder.minutes_overdue === 0 ? 'due now' : `${reminder.minutes_overdue} minute(s) past your chosen interval`;
    node.textContent = `Gentle reminder: ${reminder.title} is ${when}. Pausing is still a valid check-in.`;
    ui.reminders.append(node);
    maybeNotify(reminder);
  }
}

function maybeNotify(reminder) {
  const key = `${reminder.goal_id}:${reminder.due_at}`;
  if (notified.has(key) || !('Notification' in window) || Notification.permission !== 'granted') return;
  notified.add(key);
  new Notification('Paceboard reminder', {
    body: `${reminder.title} is ready when you are. Pausing is also a valid choice.`,
    tag: key,
    renotify: false,
  });
}

async function refreshReminders() {
  if (!state || document.hidden || reminderRefreshInFlight) return;
  const current = state;
  const token = csrfToken;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  reminderRefreshInFlight = true;
  try {
    const response = await fetch('/api/state', {cache: 'no-store', signal: controller.signal});
    if (!response.ok) return;
    const next = await response.json();
    // Do not mix a newer workspace with controls the user is still editing.
    if (document.hidden || state !== current || csrfToken !== token ||
        next.csrf_token !== token || next.revision !== current.revision ||
        next.workspace_created_at !== current.workspace_created_at ||
        !Array.isArray(next.reminders)) return;
    if (JSON.stringify(next.reminders) !== JSON.stringify(current.reminders)) {
      current.reminders = next.reminders;
      renderReminders();
    }
  } catch {
    // Background availability must not erase an actionable mutation error or a draft.
  } finally {
    clearTimeout(timeout);
    reminderRefreshInFlight = false;
  }
}

function sessionElapsed(session) {
  const extra = session.state === 'RUNNING' ? Math.floor((performance.now() - focusRenderEpoch) / 1000) : 0;
  return session.elapsed_seconds + extra;
}

function renderFocus() {
  ui.focus.replaceChildren();
  const sessions = (state.focus_sessions || []).slice(0, 20);
  ui.emptyFocus.classList.toggle('hidden', sessions.length > 0);
  const goals = new Map(state.goals.map(goal => [goal.goal_id, goal]));
  for (const session of sessions) {
    const card = document.createElement('article');
    card.className = 'focus-card';
    card.dataset.sessionId = session.session_id;
    card.dataset.baseElapsed = String(session.elapsed_seconds);
    card.dataset.state = session.state;
    const info = document.createElement('div');
    const heading = document.createElement('h3');
    heading.textContent = goals.get(session.goal_id)?.title || 'Deleted goal';
    const meta = document.createElement('div');
    meta.className = 'focus-meta';
    meta.textContent = `${session.state} · target ${Math.floor(session.planned_seconds / 60)} min · started ${timeLabel(session.started_at)}`;
    info.append(heading, meta);
    const controls = document.createElement('div');
    controls.className = 'focus-controls';
    const timer = document.createElement('span');
    timer.className = 'focus-time';
    timer.textContent = duration(sessionElapsed(session));
    controls.append(timer);
    if (session.state === 'RUNNING') {
      controls.append(button('Pause', 'pause', () => run(() => change('focus.pause', {session_id: session.session_id}))));
      controls.append(button('Finish', '', () => run(() => change('focus.finish', {session_id: session.session_id}))));
    } else if (session.state === 'PAUSED') {
      controls.append(button('Resume', '', () => run(() => change('focus.resume', {session_id: session.session_id}))));
      controls.append(button('Finish', 'quiet', () => run(() => change('focus.finish', {session_id: session.session_id}))));
    } else {
      controls.append(button('Delete', 'quiet', () => deleteItem('focus', session.session_id, 'Delete this focus-session record?')));
    }
    card.append(info, controls);
    ui.focus.append(card);
  }
}

function renderHistory() {
  ui.history.replaceChildren();
  const history = (state.history || []).slice(0, 200);
  ui.emptyHistory.classList.toggle('hidden', history.length > 0);
  for (const entry of history) {
    const node = document.createElement('article');
    node.className = 'history-entry';
    const time = document.createElement('time');
    time.className = 'history-time';
    time.dateTime = entry.created_at;
    time.textContent = timeLabel(entry.created_at);
    const body = document.createElement('div');
    const label = document.createElement('div');
    label.className = 'history-label';
    label.textContent = `${entry.goal_title} · ${entry.label}`;
    const detail = document.createElement('div');
    detail.className = 'history-detail';
    detail.textContent = entry.detail || 'No note';
    body.append(label, detail);
    const entity = entry.type === 'focus' ? 'focus' : entry.type;
    const remove = button('Delete', '', () => deleteItem(entity, entry.id, 'Delete this private history item?'));
    node.append(time, body, remove);
    ui.history.append(node);
  }
}

function renderGoalOptions() {
  const selected = ui.noteGoal.value;
  ui.noteGoal.replaceChildren(new Option('General note', ''));
  for (const goal of state.goals.filter(goal => goal.state === 'ACTIVE')) {
    ui.noteGoal.append(new Option(goal.title, goal.goal_id));
  }
  if ([...ui.noteGoal.options].some(option => option.value === selected)) ui.noteGoal.value = selected;
}

function renderSummary() {
  const summary = state.summary;
  ui.summaryActive.textContent = String(summary.active_goals);
  ui.summaryDone.textContent = String(summary.done_checkins);
  ui.summaryPaused.textContent = String(summary.paused_checkins);
  ui.summaryFocus.textContent = String(summary.finished_focus_minutes);
}

function render() {
  ui.connection.textContent = 'Local workspace ready';
  ui.revision.textContent = `Workspace revision ${state.revision}`;
  renderSummary();
  renderReminders();
  renderGoals();
  renderFocus();
  renderHistory();
  renderGoalOptions();
}

function deleteItem(entity, id, message) {
  if (!window.confirm(message)) return;
  run(() => change('item.delete', {entity, id}));
}

async function download(path, fallbackName) {
  const response = await fetch(path, {cache: 'no-store'});
  if (!response.ok) throw new Error(await responseError(response));
  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="([^"]+)"/);
  const name = match?.[1] || fallbackName;
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = name;
    anchor.click();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
}

document.querySelector('#show-goal-form').addEventListener('click', () => fillGoalForm());
document.querySelector('#cancel-goal').addEventListener('click', hideGoalForm);

ui.goalForm.addEventListener('submit', event => {
  event.preventDefault();
  const goalId = ui.goalId.value;
  const payload = {
    title: ui.goalTitle.value,
    intention: ui.goalIntention.value,
    reminder_minutes: Number(ui.goalReminder.value),
    target_focus_minutes: Number(ui.goalFocus.value),
  };
  if (goalId) payload.goal_id = goalId;
  run(async () => {
    await change(goalId ? 'goal.update' : 'goal.create', payload);
    hideGoalForm();
  });
});

ui.noteForm.addEventListener('submit', event => {
  event.preventDefault();
  run(async () => {
    await change('note.record', {goal_id: ui.noteGoal.value || null, body: ui.noteBody.value});
    ui.noteBody.value = '';
  });
});

document.querySelector('#export-json').addEventListener('click', () => run(() => download('/api/export.json', 'paceboard-backup.json')));
document.querySelector('#export-csv').addEventListener('click', () => run(() => download('/api/export.csv', 'paceboard-history.csv')));

document.querySelector('#restore-button').addEventListener('click', () => {
  const file = ui.restoreFile.files?.[0];
  if (!file) {
    showError('Choose a Paceboard JSON backup first.');
    return;
  }
  if (!window.confirm('Replace this entire local workspace with the selected backup?')) return;
  run(async () => {
    let backup;
    try {
      backup = JSON.parse(await file.text());
    } catch {
      throw new Error('The selected file is not valid JSON.');
    }
    await change('backup.restore', {backup});
    ui.restoreFile.value = '';
  });
});

document.querySelector('#erase-button').addEventListener('click', () => {
  const confirmText = ui.eraseConfirm.value;
  if (confirmText !== 'ERASE PACEBOARD') {
    showError('Type ERASE PACEBOARD exactly before erasing.');
    return;
  }
  if (!window.confirm('Permanently erase every local Paceboard item?')) return;
  run(async () => {
    await change('all.erase', {confirm: confirmText});
    ui.eraseConfirm.value = '';
  });
});

document.querySelector('#enable-notifications').addEventListener('click', () => {
  if (!('Notification' in window)) {
    showError('This browser does not expose local notifications. In-page reminders still work.');
    return;
  }
  run(async () => {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') throw new Error('Notification permission was not granted. In-page reminders remain available.');
    for (const reminder of state.reminders) maybeNotify(reminder);
  });
});

setInterval(() => {
  if (!state) return;
  for (const node of document.querySelectorAll('.focus-card[data-state="RUNNING"]')) {
    const session = state.focus_sessions.find(item => item.session_id === node.dataset.sessionId);
    const timer = node.querySelector('.focus-time');
    if (session && timer) timer.textContent = duration(sessionElapsed(session));
  }
}, 1000);

setInterval(refreshReminders, 15000);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) refreshReminders();
});

run(fetchState);
