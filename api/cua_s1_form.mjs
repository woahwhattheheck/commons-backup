/** Cloud browser runner for the CUA-S1-FORMS hosted scorer.
 *
 * Launches an isolated Chromium inside a Vercel Node function. It never uses
 * the owner's desktop browser or accepts executable code from the caller.
 */
import dns from 'node:dns/promises';
import { isIP } from 'node:net';

const MAX_BODY = 64 * 1024;
const MAX_CONTROLS = 40;
const MAX_ENTITIES = 29; // 32 options including check, click, skip.

function failure(code, status = 400) {
  return { status, body: { ok: false, error: { code } } };
}

function publicAddress(address) {
  if (isIP(address) === 4) {
    const p = address.split('.').map(Number);
    return !(p[0] === 0 || p[0] === 10 || p[0] === 127 || p[0] >= 224 ||
      (p[0] === 100 && p[1] >= 64 && p[1] <= 127) ||
      (p[0] === 169 && p[1] === 254) ||
      (p[0] === 172 && p[1] >= 16 && p[1] <= 31) ||
      (p[0] === 192 && (p[1] === 168 || p[1] === 0)) ||
      (p[0] === 198 && p[1] >= 18 && p[1] <= 19));
  }
  if (isIP(address) === 6) {
    const a = address.toLowerCase();
    return !(a === '::' || a === '::1' || a.startsWith('fc') || a.startsWith('fd') ||
      a.startsWith('fe8') || a.startsWith('fe9') || a.startsWith('fea') ||
      a.startsWith('feb') || a.startsWith('::ffff:'));
  }
  return false;
}

async function resolvePublicTarget(raw, resolver = dns.lookup) {
  if (typeof raw !== 'string' || !raw.trim() || raw.length > 2048) throw new Error('BAD_URL');
  let url;
  try { url = new URL(raw); } catch { throw new Error('BAD_URL'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.hash) {
    throw new Error('BAD_URL');
  }
  const host = url.hostname.toLowerCase();
  if (!host || host === 'localhost' || host.endsWith('.localhost') ||
      host.endsWith('.local') || host.endsWith('.internal')) throw new Error('PRIVATE_URL');
  const addresses = isIP(host) ? [{ address: host }] : await resolver(host, { all: true });
  if (!Array.isArray(addresses) || !addresses.length ||
      addresses.some(row => !publicAddress(row.address))) throw new Error('PRIVATE_URL');
  const pinnedAddress = addresses.find(row => isIP(row.address) === 4)?.address;
  if (!pinnedAddress) throw new Error('NO_IPV4_TARGET');
  return { href: url.href, host, pinnedAddress };
}

export async function validateUrl(raw, resolver = dns.lookup) {
  return (await resolvePublicTarget(raw, resolver)).href;
}

export function browserNetworkRules(host, pinnedAddress) {
  if (!/^[A-Za-z0-9.-]+$/.test(host) || isIP(pinnedAddress) !== 4 ||
      !publicAddress(pinnedAddress)) throw new Error('PRIVATE_URL');
  return `--host-resolver-rules=MAP ${host} ${pinnedAddress}, MAP * ^NOTFOUND`;
}

export function validateRequest(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('BAD_REQUEST');
  const { url, form_title: title, entities } = input;
  if (typeof url !== 'string' || typeof title !== 'string' || !title.trim() || title.length > 256) {
    throw new Error('BAD_REQUEST');
  }
  if (!Array.isArray(entities) || entities.length > MAX_ENTITIES || entities.some(e =>
    !e || typeof e.label !== 'string' || !e.label.trim() || e.label.length > 80 ||
    typeof e.value !== 'string' || !e.value.trim() || e.value.length > 256)) {
    throw new Error('BAD_ENTITIES');
  }
  if (new Set(entities.map(e => `fill ${e.label}: ${e.value}`)).size !== entities.length) {
    throw new Error('BAD_ENTITIES');
  }
  for (const flag of ['execute', 'submit']) {
    if (input[flag] !== undefined && typeof input[flag] !== 'boolean') throw new Error('BAD_FLAGS');
  }
  const confidence = input.min_confidence ?? 0.5;
  if (typeof confidence !== 'number' || !Number.isFinite(confidence) ||
      confidence < 0 || confidence > 1) throw new Error('BAD_CONFIDENCE');
  return { url, title, entities, execute: input.execute === true,
    submit: input.submit === true, confidence };
}

const SNAPSHOT = () => {
  const controls = [...document.querySelectorAll('input,textarea,button,select')];
  const visible = el => el.getClientRects().length > 0 &&
    getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).display !== 'none';
  return controls.filter(el => visible(el) && !el.disabled).map((el, index) => {
    if (!el.dataset.commonsCuaToken) el.dataset.commonsCuaToken = crypto.randomUUID();
    const type = (el.getAttribute('type') || '').toLowerCase();
    const tag = el.tagName.toLowerCase();
    const label = (el.labels && [...el.labels].map(x => x.innerText).join(' ')) ||
      el.getAttribute('aria-label') || el.getAttribute('placeholder') ||
      el.getAttribute('name') || el.innerText || '';
    const role = type === 'checkbox' ? 'CheckBox' :
      (tag === 'button' || type === 'submit') ? 'Button' :
      tag === 'select' ? 'ComboBox' : 'Edit';
    return { index, token: el.dataset.commonsCuaToken, role, label: label.trim(),
      value: el.value || '', checked: type === 'checkbox' ? el.checked : null,
      type, tag };
  });
};

function context(title, element) {
  const state = element.role === 'CheckBox' ?
    (element.checked ? 'checked' : 'unchecked') :
    `value="${String(element.value).slice(0, 48)}"`;
  return `TASK fill the form from the document, then submit\nFORM ${title.slice(0, 64)}\n` +
    `ELEMENT ${element.role} "${element.label.slice(0, 72)}" ${state}`;
}

export function scoreOptions(entities) {
  return [...entities.map(e => `fill ${e.label}: ${e.value}`), 'check', 'click', 'skip'];
}

async function launchChromium(target) {
  const [{ default: puppeteer }, { default: chromium }] = await Promise.all([
    import('puppeteer-core'), import('@sparticuz/chromium'),
  ]);
  return puppeteer.launch({ args: [...chromium.args, '--no-proxy-server',
    browserNetworkRules(target.host, target.pinnedAddress)], executablePath: await chromium.executablePath(),
    headless: true });
}

async function scoreElement(element, title, entities, score) {
  const options = scoreOptions(entities);
  const result = await score({ context: context(title, element), options });
  const index = result?.selected_index;
  const probability = result?.choices?.[index]?.probability;
  if (!Number.isInteger(index) || index < 0 || index >= options.length ||
      typeof probability !== 'number' || !Number.isFinite(probability) ||
      result.choices[index].option !== options[index]) throw new Error('BAD_SCORE_REPLY');
  const action = index < entities.length ? 'fill' : ['check', 'click', 'skip'][index - entities.length];
  return { token: element.token, index: element.index, role: element.role, label: element.label,
    action, entity_index: action === 'fill' ? index : null, probability };
}

async function controlByToken(page, token) {
  return page.evaluate(token => {
    const matches = [...document.querySelectorAll('[data-commons-cua-token]')]
      .filter(el => el.dataset.commonsCuaToken === token);
    if (matches.length !== 1) return { count: matches.length };
    const el = matches[0];
    return { count: 1, tag: el.tagName.toLowerCase(), type: (el.getAttribute('type') || '').toLowerCase(),
      value: el.value || '', checked: el.type === 'checkbox' ? el.checked : null,
      label: (el.labels && [...el.labels].map(x => x.innerText).join(' ')) ||
        el.getAttribute('aria-label') || el.getAttribute('placeholder') ||
        el.getAttribute('name') || el.innerText || '' };
  }, token);
}

export async function runForm(input, { launch = launchChromium, resolver = dns.lookup,
  score, onBrowser } = {}) {
  const request = validateRequest(input);
  const target = await resolvePublicTarget(request.url, resolver);
  const url = target.href;
  if (typeof score !== 'function') throw new Error('SCORER_UNAVAILABLE');
  const browser = await launch(target);
  try {
    if (onBrowser) onBrowser(browser);
    const page = await browser.newPage();
    await page.setRequestInterception(true);
    page.on('request', async req => {
      try {
        const requested = new URL(req.url());
        if (requested.hostname.toLowerCase() !== target.host ||
            !['http:', 'https:'].includes(requested.protocol)) throw new Error('CROSS_ORIGIN');
        req.continue();
      }
      catch { req.abort(); }
    });
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
    if (page.url() !== url) throw new Error('TARGET_CHANGED');
    const initial = await page.evaluate(SNAPSHOT);
    if (!Array.isArray(initial) || initial.length > MAX_CONTROLS ||
        initial.some(e => !e.token || !e.role || typeof e.label !== 'string')) throw new Error('INVALID_SNAPSHOT');
    const decisions = await Promise.all(initial.map(e => scoreElement(e, request.title, request.entities, score)));
    const selected = decisions.filter(d => d.action !== 'skip' && d.probability >= request.confidence);
    const fills = selected.filter(d => d.action === 'fill' && d.role === 'Edit');
    const checks = selected.filter(d => d.action === 'check' && d.role === 'CheckBox');
    const coveredEntities = new Set(fills.map(d => d.entity_index));
    const complete = request.entities.every((_, index) => coveredEntities.has(index));
    if (request.execute && !complete) throw new Error('INCOMPLETE_PLAN');
    const submits = request.submit && complete ? selected.filter(d => d.action === 'click' && d.role === 'Button' &&
      /^(submit|submit form)$/i.test(d.label.trim())).sort((a, b) => b.probability - a.probability).slice(0, 1) : [];
    const ordered = [...fills, ...checks, ...submits];
    const actions = [];
    if (request.execute) {
      for (const item of ordered) {
        if (page.url() !== url) throw new Error('TARGET_CHANGED');
        const before = await controlByToken(page, item.token);
        if (before.count !== 1 || before.label.trim() !== item.label.trim()) throw new Error('STALE_CONTROL');
        const locator = page.locator(`[data-commons-cua-token="${item.token}"]`);
        if (item.action === 'fill') {
          if (!['input', 'textarea'].includes(before.tag) ||
              (before.tag === 'input' && !['', 'text', 'email', 'tel', 'search', 'number', 'url'].includes(before.type)))
            throw new Error('UNSUPPORTED_CONTROL');
          const value = request.entities[item.entity_index].value;
          await locator.fill(value);
          const after = await controlByToken(page, item.token);
          if (after.count !== 1 || after.value !== value) throw new Error('FILL_NOT_CONFIRMED');
          actions.push({ ...item, status: 'delivered', verified_value: true });
        } else if (item.action === 'check') {
          if (before.type !== 'checkbox' || before.checked === null) throw new Error('CHECKBOX_STATE_UNKNOWN');
          if (!before.checked) await locator.fill(true);
          const after = await controlByToken(page, item.token);
          if (after.count !== 1 || after.checked !== true) throw new Error('CHECK_NOT_CONFIRMED');
          actions.push({ ...item, status: before.checked ? 'already_satisfied' : 'delivered', verified_checked: true });
        } else {
          if (!/^(submit|submit form)$/i.test(before.label.trim()) ||
              !(before.tag === 'button' || before.type === 'submit')) throw new Error('SUBMIT_CONTROL_CHANGED');
          await locator.click();
          actions.push({ ...item, status: 'click_delivered', submitted: 'unknown' });
        }
      }
    }
    return { ok: true, model: 'cua-ai/cua-s1-forms', url, final_url: page.url(),
      executed: request.execute, submit_requested: request.submit, elements_scored: decisions.length,
      all_decisions: decisions, execution_order: actions, planned_actions: ordered,
      submission_verified: false };
  } finally {
    await browser.close();
  }
}


function headerValue(headers, name) {
  if (!headers) return undefined;
  if (typeof headers.get === 'function') {
    return headers.get(name) || headers.get(name.toLowerCase()) || undefined;
  }
  return headers[name] || headers[name.toLowerCase()] || undefined;
}

/** Prefer the public production alias for function-to-function scorer calls.
 * Deployment URLs (VERCEL_URL) often sit behind Vercel Authentication and return
 * non-OK to the form runner → SCORER_FAILED / HTTP 502. Web Request headers need
 * Headers.get, not plain-object indexing.
 */
export function resolveScorerBase(request = {}, env = process.env) {
  const explicit = env.COMMONS_CUA_SCORER_BASE || env.CUA_SCORER_BASE;
  if (typeof explicit === 'string' && explicit.trim()) {
    return explicit.replace(/\/$/, '');
  }
  const production = env.VERCEL_PROJECT_PRODUCTION_URL;
  if (typeof production === 'string' && production.trim()) {
    return `https://${production.replace(/^https?:\/\//, '').replace(/\/$/, '')}`;
  }
  const host = headerValue(request.headers, 'x-forwarded-host') || headerValue(request.headers, 'host');
  if (host) {
    const proto = String(headerValue(request.headers, 'x-forwarded-proto') || 'https')
      .split(',')[0].trim();
    return `${proto}://${String(host).split(',')[0].trim()}`;
  }
  // On any Vercel runtime, hard-prefer the stable production alias before
  // falling back to the protected deployment hostname.
  if (env.VERCEL_ENV === 'production' || env.VERCEL === '1') {
    return 'https://commons-spark-mcp.vercel.app';
  }
  if (typeof env.VERCEL_URL === 'string' && env.VERCEL_URL.trim()) {
    return `https://${env.VERCEL_URL.replace(/^https?:\/\//, '').replace(/\/$/, '')}`;
  }
  try { return new URL(request.url || '/', 'http://localhost').origin; }
  catch { return 'https://commons-spark-mcp.vercel.app'; }
}

async function fetchScorer(base, payload, fetchImpl = fetch) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const response = await fetchImpl(base + '/api/cua_s1', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
      body: JSON.stringify(payload),
    });
    if (response.ok) return response.json();
    if (![502, 503, 504].includes(response.status) || attempt === 2) break;
    await new Promise(r => setTimeout(r, 250 * (attempt + 1)));
  }
  throw new Error('SCORER_FAILED');
}

export async function handleRequest(request, deps = {}) {
  if (request.method === 'GET') return { status: 200, body: { ok: true, service: 'commons-cua-s1-form',
    browser_runtime: 'vercel-chromium', scoring_route: '/api/cua_s1' } };
  if (request.method !== 'POST') return failure('METHOD_NOT_ALLOWED', 405);
  let body;
  try {
    const raw = typeof request.text === 'function' ? await request.text() :
      (typeof request.body === 'string' ? request.body : JSON.stringify(request.body));
    if (Buffer.byteLength(raw) > MAX_BODY) return failure('BODY_TOO_LARGE', 413);
    body = JSON.parse(raw);
  } catch { return failure('BAD_JSON'); }
  try {
    // Prefer production alias for internal scorer fetch. VERCEL_URL is the
    // deployment hostname and often hits Deployment Protection / cold-route
    // 401-502 from Node→self, which surfaces as SCORER_FAILED on /cua-s1/form.
    const base = deps.scorerBase || resolveScorerBase(request, deps.env || process.env);
    const score = deps.score || (async payload => fetchScorer(base, payload, deps.fetch || fetch));
    return { status: 200, body: await runForm(body, { ...deps, score }) };
  } catch (error) {
    const code = typeof error?.message === 'string' && /^[A-Z_]+$/.test(error.message) ? error.message : 'BROWSER_FAILED';
    return failure(code, code === 'BAD_SCORE_REPLY' || code === 'SCORER_FAILED' ? 502 : 400);
  }
}

export default async function handler(request, response) {
  const result = await handleRequest(request);
  response.setHeader('content-type', 'application/json; charset=utf-8');
  response.setHeader('cache-control', 'no-store');
  response.status(result.status).json(result.body);
}
