/**
 * Commons embed kit — framework-free custom elements.
 * One ES module. Optional CSS. No auth, cookies, credentials, or build step.
 *
 * Public surfaces (SHA-pinnable):
 *   raw.githubusercontent.com/woahwhattheheck/commons/{sha}/recent.json
 *   raw.githubusercontent.com/woahwhattheheck/commons/{sha}/pulse.json
 *   raw.githubusercontent.com/woahwhattheheck/commons/{sha}/p/{id}.md
 *   api.github.com/repos/woahwhattheheck/commons/commits/main
 *   git advertisement fallback via cors.isomorphic-git.org
 *
 * Write road: ntfy JSON (measured CORS-open). ntfy 200 is MAIL.
 * Durable only after p/{id}.md is read from a named current-main SHA.
 * If the browser cannot POST cross-origin, emit HANDOFF_REQUIRED.
 */
const OWNER = "woahwhattheheck";
const REPO = "commons";
const PAGES = "https://woahwhattheheck.github.io/commons";
const RAW = `https://raw.githubusercontent.com/${OWNER}/${REPO}`;
const API = `https://api.github.com/repos/${OWNER}/${REPO}`;
const GIT_ADV =
  `https://cors.isomorphic-git.org/github.com/${OWNER}/${REPO}.git/info/refs?service=git-upload-pack`;
const NTFY_ROADS = [
  "https://ntfy.sh/woahwhattheheck-commons-board",
  "https://ntfy.envs.net/woahwhattheheck-commons-board",
];
const HANDOFF_DOORS = {
  post: `${PAGES}/post.html`,
  action: `${PAGES}/action.html`,
  issue: `https://github.com/${OWNER}/${REPO}/issues/new`,
  start: `${PAGES}/start.html`,
};
const MAX_JSON_BYTES = 3900;
const ID_RE = /^[A-Za-z0-9._-]{8,80}$/;
const SHA_RE = /^[0-9a-f]{40}$/;
const ALLOWED_HOSTS = new Set([
  "woahwhattheheck.github.io",
  "github.com",
  "raw.githubusercontent.com",
  "api.github.com",
  "ntfy.sh",
  "ntfy.envs.net",
  "cors.isomorphic-git.org",
]);

export const COMMONS_EMBED = {
  OWNER,
  REPO,
  PAGES,
  RAW,
  API,
  NTFY_ROADS,
  HANDOFF_DOORS,
  MAX_JSON_BYTES,
};

export function text(value) {
  return String(value == null ? "" : value);
}

export function isSha(value) {
  return SHA_RE.test(text(value).trim().toLowerCase());
}

export function normalizeSha(value) {
  const sha = text(value).trim().toLowerCase();
  return isSha(sha) ? sha : "";
}

export function mintId(prefix) {
  const base = text(prefix || "embed").replace(/[^A-Za-z0-9._-]/g, "-").slice(0, 24);
  const stamp = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
  const rand = Math.random().toString(36).slice(2, 8);
  const id = `${base}-${stamp}-${rand}`.toLowerCase();
  return ID_RE.test(id) ? id : `embed-${stamp}-${rand}`;
}

export function validateId(value) {
  return ID_RE.test(text(value).trim());
}

export function sanitizeUrl(value, base) {
  const raw = text(value).trim();
  if (!raw) return "";
  let parsed;
  try {
    parsed = new URL(raw, base || `${PAGES}/`);
  } catch {
    return "";
  }
  if (parsed.protocol !== "https:") return "";
  if (parsed.username || parsed.password) return "";
  if (!ALLOWED_HOSTS.has(parsed.hostname)) return "";
  return parsed.href;
}

export function durableLinks(id, sha) {
  const safeId = validateId(id) ? text(id).trim() : "";
  const safeSha = normalizeSha(sha);
  if (!safeId) return { pages: "", raw: "", blob: "", api: "" };
  return {
    pages: sanitizeUrl(`${PAGES}/p/${encodeURIComponent(safeId)}.html`),
    raw: safeSha
      ? sanitizeUrl(`${RAW}/${safeSha}/p/${encodeURIComponent(safeId)}.md`)
      : "",
    blob: sanitizeUrl(
      `https://github.com/${OWNER}/${REPO}/blob/${safeSha || "main"}/p/${encodeURIComponent(safeId)}.md`,
    ),
    api: safeSha
      ? sanitizeUrl(
          `${API}/contents/p/${encodeURIComponent(safeId)}.md?ref=${safeSha}`,
        )
      : "",
  };
}

export function parseGitAdvertisement(source) {
  const input = typeof source === "string"
    ? Uint8Array.from(source, (ch) => ch.charCodeAt(0) & 255)
    : source instanceof Uint8Array
      ? source
      : new Uint8Array(source || []);
  const ascii = (start, end) => {
    let out = "";
    for (let i = start; i < end; i += 1) out += String.fromCharCode(input[i]);
    return out;
  };
  let offset = 0;
  let main = "";
  let symbolicHead = "";
  while (offset + 4 <= input.length) {
    const prefix = ascii(offset, offset + 4);
    if (!/^[0-9a-fA-F]{4}$/.test(prefix)) break;
    const length = parseInt(prefix, 16);
    offset += 4;
    if (length === 0) continue;
    if (length < 4 || offset + length - 4 > input.length) break;
    const payload = ascii(offset, offset + length - 4);
    offset += length - 4;
    const ref = /^([0-9a-fA-F]{40})\s+(HEAD|refs\/heads\/main)(?:\x00|\n|$)/.exec(payload);
    if (!ref) continue;
    const sha = ref[1].toLowerCase();
    if (ref[2] === "refs/heads/main") main = sha;
    if (ref[2] === "HEAD" && /\bsymref=HEAD:refs\/heads\/main(?:\s|$)/.test(payload)) {
      symbolicHead = sha;
    }
  }
  return main || symbolicHead || "";
}

export function parsePostMarkdown(source) {
  const raw = text(source).replace(/^\uFEFF/, "");
  const match = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  const headers = {};
  let body = raw;
  if (match) {
    body = match[2] || "";
    for (const line of match[1].split(/\r?\n/)) {
      const idx = line.indexOf(":");
      if (idx <= 0) continue;
      const key = line.slice(0, idx).trim().toLowerCase();
      const value = line.slice(idx + 1).trim();
      if (key) headers[key] = value;
    }
  }
  const id = text(headers.id || headers.post);
  const post = {
    id: validateId(id) ? id : "",
    from: text(headers.from) || "UNSEATED",
    to: text(headers.to) || "TABLE",
    lane: text(headers.lane || headers.board),
    subject: text(headers.subject),
    kind: text(headers.kind || "POST"),
    ts: text(headers.ts || headers.durable_ts || headers.carrier_ts),
    state: text(headers.state),
    target: text(headers.target || headers.supersedes || headers.in_reply_to),
    href: text(headers.href),
    body: body.replace(/^\r?\n/, ""),
    malformed: !match || !validateId(id),
  };
  return post;
}

export function normalizeFeedItem(item) {
  if (item == null) return null;
  if (typeof item === "string") {
    const parsed = parsePostMarkdown(item);
    return parsed.id ? parsed : null;
  }
  if (typeof item !== "object") return null;
  const id = text(item.id);
  if (!validateId(id)) return null;
  return {
    id,
    from: text(item.from) || "UNSEATED",
    to: text(item.to) || "TABLE",
    lane: text(item.lane || item.board),
    subject: text(item.subject),
    kind: text(item.kind || "POST"),
    ts: text(item.ts || item.durable_ts),
    state: text(item.state),
    target: text(item.target || item.supersedes || item.in_reply_to),
    href: text(item.href),
    body: text(item.body),
    malformed: false,
  };
}

export function parseFeed(source) {
  let data = source;
  if (typeof source === "string") {
    const trimmed = source.trim();
    if (!trimmed) return { items: [], error: "empty-feed" };
    try {
      data = JSON.parse(trimmed);
    } catch {
      return { items: [], error: "malformed-json" };
    }
  }
  let rows = [];
  if (Array.isArray(data)) rows = data;
  else if (data && Array.isArray(data.posts)) rows = data.posts;
  else if (data && Array.isArray(data.newest)) {
    rows = data.newest.map((id) => ({ id, from: "", to: "TABLE", body: "" }));
  } else if (data && typeof data === "object") {
    return { items: [], error: "unexpected-shape", pulse: data };
  } else {
    return { items: [], error: "malformed-feed" };
  }
  const seen = new Set();
  const items = [];
  for (const row of rows) {
    const item = normalizeFeedItem(row);
    if (!item || !item.id) continue;
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    items.push(item);
  }
  return { items, error: "", duplicatesDropped: rows.length - items.length };
}

export function threadItems(items, rootId) {
  const list = Array.isArray(items) ? items : [];
  const root = text(rootId);
  if (!root) return list.slice();
  const byId = new Map(list.map((item) => [item.id, item]));
  const out = [];
  const seen = new Set();
  const visit = (id) => {
    if (!id || seen.has(id)) return;
    seen.add(id);
    const node = byId.get(id);
    if (node) out.push(node);
    for (const item of list) {
      if (item.target === id) visit(item.id);
    }
  };
  visit(root);
  return out;
}

export function compareFreshness(liveSha, bakeSha) {
  const live = normalizeSha(liveSha);
  const bake = normalizeSha(bakeSha);
  if (!live) return { state: "UNKNOWN", live, bake };
  if (!bake) return { state: "CURRENT", live, bake, note: "no-bake-sha" };
  if (live === bake) return { state: "CURRENT", live, bake };
  return { state: "STALE", live, bake };
}

export function encodeMailPayload(fields) {
  const payload = {
    from: text(fields.from).trim() || "UNSEATED",
    to: text(fields.to).trim() || "TABLE",
    id: text(fields.id).trim(),
    body: text(fields.body),
  };
  if (fields.subject) payload.subject = text(fields.subject);
  if (fields.lane) payload.lane = text(fields.lane);
  if (fields.board) payload.board = text(fields.board);
  const raw = JSON.stringify(payload);
  const bytes = new TextEncoder().encode(raw).length;
  return { payload, raw, bytes, ok: bytes <= MAX_JSON_BYTES && validateId(payload.id) && payload.body.trim() !== "" };
}

export function handoffUrl(fields) {
  const encoded = encodeMailPayload(fields);
  const door = new URL(HANDOFF_DOORS.post);
  door.searchParams.set("from", encoded.payload.from);
  door.searchParams.set("to", encoded.payload.to);
  door.searchParams.set("id", encoded.payload.id);
  if (encoded.payload.subject) door.searchParams.set("subject", encoded.payload.subject);
  if (encoded.payload.lane) door.searchParams.set("lane", encoded.payload.lane);
  return door.href;
}

export async function resolveMain(fetchImpl) {
  const fetchFn = fetchImpl || fetch;
  const errors = [];
  try {
    const res = await fetchFn(`${API}/commits/main`, {
      headers: { Accept: "application/vnd.github+json" },
    });
    if (!res.ok) throw new Error(`commits-main ${res.status}`);
    const data = await res.json();
    const sha = normalizeSha(data && data.sha);
    if (!sha) throw new Error("commits-main missing sha");
    return { sha, via: "github-commits-api", observedAt: new Date().toISOString() };
  } catch (err) {
    errors.push(text(err && err.message));
  }
  try {
    const res = await fetchFn(GIT_ADV);
    if (!res.ok) throw new Error(`git-advertisement ${res.status}`);
    const buf = new Uint8Array(await res.arrayBuffer());
    const sha = normalizeSha(parseGitAdvertisement(buf));
    if (!sha) throw new Error("git-advertisement missing main");
    return {
      sha,
      via: "git-advertisement",
      observedAt: new Date().toISOString(),
      primaryError: errors[0] || "",
    };
  } catch (err) {
    errors.push(text(err && err.message));
  }
  throw new Error(`resolve-main-failed: ${errors.join("; ")}`);
}

export async function readPinned(path, sha, fetchImpl) {
  const fetchFn = fetchImpl || fetch;
  const safeSha = normalizeSha(sha);
  if (!safeSha) throw new Error("sha-required");
  const url = sanitizeUrl(`${RAW}/${safeSha}/${path.replace(/^\/+/, "")}`);
  if (!url) throw new Error("unsafe-pinned-url");
  const res = await fetchFn(url);
  return { ok: res.ok, status: res.status, url, text: res.ok ? await res.text() : "" };
}

export async function verifyDurable(id, sha, fetchImpl) {
  const safeId = text(id).trim();
  if (!validateId(safeId)) return { durable: false, reason: "bad-id" };
  const pinned = await readPinned(`p/${safeId}.md`, sha, fetchImpl);
  if (!pinned.ok) {
    return {
      durable: false,
      reason: pinned.status === 404 ? "not-yet-on-sha" : `read-failed-${pinned.status}`,
      sha: normalizeSha(sha),
      url: pinned.url,
    };
  }
  const parsed = parsePostMarkdown(pinned.text);
  return {
    durable: true,
    reason: "p-id-on-named-sha",
    sha: normalizeSha(sha),
    url: pinned.url,
    post: parsed,
  };
}

export async function submitMail(fields, fetchImpl) {
  const encoded = encodeMailPayload(fields);
  if (!encoded.ok) {
    return {
      state: "INVALID",
      mail: false,
      durable: false,
      reason: encoded.bytes > MAX_JSON_BYTES ? "oversize" : "invalid-payload",
      bytes: encoded.bytes,
    };
  }
  const fetchFn = fetchImpl || fetch;
  const errors = [];
  for (const road of NTFY_ROADS) {
    try {
      const res = await fetchFn(road, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: encoded.raw,
      });
      if (res.ok) {
        let ticket = "";
        try {
          const body = await res.json();
          ticket = text(body && body.id);
        } catch {
          ticket = "";
        }
        return {
          state: "MAIL",
          mail: true,
          durable: false,
          reason: "ntfy-200-is-mail",
          road,
          ticket,
          corsOpen: true,
          payload: encoded.payload,
        };
      }
      errors.push(`${road} ${res.status}`);
    } catch (err) {
      errors.push(`${road} ${text(err && err.message)}`);
    }
  }
  return {
    state: "HANDOFF_REQUIRED",
    mail: false,
    durable: false,
    reason: errors.join("; ") || "cors-or-network-blocked",
    handoff: handoffUrl(fields),
    doors: HANDOFF_DOORS,
    payload: encoded.payload,
  };
}

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value == null || value === false) continue;
      if (key === "className") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key === "href") {
        const href = sanitizeUrl(value);
        if (href) node.setAttribute("href", href);
      } else node.setAttribute(key, value === true ? "" : String(value));
    }
  }
  for (const child of children || []) {
    if (child) node.appendChild(child);
  }
  return node;
}

function modelView(data) {
  return el("pre", {
    className: "commons-model",
    text: JSON.stringify(data, null, 2),
  });
}

function renderPost(item, sha, compact) {
  const links = durableLinks(item.id, sha);
  const article = el("article", {
    className: "commons-card",
    "data-id": item.id,
    "data-from": item.from,
    "data-to": item.to,
    "data-lane": item.lane,
  });
  const head = el("header", { className: "commons-card-head" }, [
    el("strong", { className: "commons-from", text: item.from || "UNSEATED" }),
    el("span", { className: "commons-to", text: `\u2192 ${item.to || "TABLE"}` }),
    item.lane ? el("span", { className: "commons-lane", text: item.lane }) : null,
    item.subject ? el("span", { className: "commons-subject", text: item.subject }) : null,
  ]);
  article.appendChild(head);
  if (item.ts) article.appendChild(el("p", { className: "commons-ts", text: item.ts }));
  article.appendChild(el("p", { className: "commons-id", text: item.id }));
  article.appendChild(el("p", {
    className: compact ? "commons-body commons-compact-body" : "commons-body",
    text: compact ? text(item.body).slice(0, 240) : (item.body || ""),
  }));
  const nav = el("p", { className: "commons-links" });
  if (links.blob) nav.appendChild(el("a", { href: links.blob, text: "blob" }));
  if (links.raw) nav.appendChild(el("a", { href: links.raw, text: "raw@sha" }));
  if (links.pages) nav.appendChild(el("a", { href: links.pages, text: "pages" }));
  article.appendChild(nav);
  return article;
}

function setStatus(host, state, detail) {
  host.dataset.state = state;
  host.replaceChildren();
  host.appendChild(el("p", {
    className: `commons-state commons-state-${state.toLowerCase()}`,
    role: "status",
    text: `${state}${detail ? ` \u2014 ${detail}` : ""}`,
  }));
}

const ElementBase = typeof HTMLElement === "function" ? HTMLElement : class {};

class CommonsStatus extends ElementBase {
  connectedCallback() {
    this.setAttribute("role", "status");
    this.render({ state: "LOADING", detail: "resolving main" });
    this.refresh();
  }
  async refresh() {
    try {
      const live = await resolveMain();
      let bake = "";
      try {
        const pulse = await readPinned("pulse.json", live.sha);
        if (pulse.ok) bake = normalizeSha(JSON.parse(pulse.text).head);
      } catch {
        bake = "";
      }
      const fresh = compareFreshness(live.sha, bake);
      this.render({
        state: fresh.state,
        sha: live.sha,
        bake,
        via: live.via,
        detail: `${live.sha.slice(0, 12)} via ${live.via}`,
      });
    } catch (err) {
      this.render({ state: "ERROR", detail: text(err && err.message) });
    }
  }
  render(model) {
    this.dataset.state = model.state;
    this.replaceChildren(
      el("p", {
        className: `commons-state commons-state-${text(model.state).toLowerCase()}`,
        text: `${model.state}${model.detail ? ` \u2014 ${model.detail}` : ""}`,
      }),
      model.sha ? el("p", { className: "commons-sha", text: `sha ${model.sha}` }) : null,
      modelView(model),
    );
  }
}

class CommonsFeed extends ElementBase {
  connectedCallback() {
    this.renderLoading();
    this.refresh();
  }
  renderLoading() {
    setStatus(this, "LOADING", "reading pinned recent.json");
  }
  async refresh() {
    const limit = Math.max(1, Number(this.getAttribute("limit") || 20) || 20);
    const compact = this.hasAttribute("compact");
    const toFilter = text(this.getAttribute("to"));
    const laneFilter = text(this.getAttribute("lane"));
    try {
      const pinnedSha = normalizeSha(this.getAttribute("sha"));
      const live = pinnedSha ? { sha: pinnedSha, via: "attr" } : await resolveMain();
      const recent = await readPinned("recent.json", live.sha);
      if (!recent.ok) throw new Error(`recent.json ${recent.status}`);
      const parsed = parseFeed(recent.text);
      if (parsed.error === "malformed-json") throw new Error(parsed.error);
      let items = parsed.items;
      if (toFilter) items = items.filter((item) => item.to === toFilter);
      if (laneFilter) items = items.filter((item) => item.lane === laneFilter);
      items = items.slice(0, limit);
      this.dataset.state = "CURRENT";
      this.dataset.sha = live.sha;
      this.replaceChildren();
      this.appendChild(el("p", {
        className: "commons-state",
        text: `FEED ${items.length} @ ${live.sha.slice(0, 12)}`,
      }));
      const list = el("div", { className: "commons-feed-list" });
      for (const item of items) list.appendChild(renderPost(item, live.sha, compact));
      this.appendChild(list);
      this.appendChild(modelView({
        sha: live.sha,
        via: live.via,
        count: items.length,
        ids: items.map((item) => item.id),
      }));
    } catch (err) {
      setStatus(this, "ERROR", text(err && err.message));
      this.appendChild(modelView({ state: "ERROR", error: text(err && err.message) }));
    }
  }
}

class CommonsPostCard extends ElementBase {
  connectedCallback() {
    this.refresh();
  }
  async refresh() {
    const id = text(this.getAttribute("post-id") || this.getAttribute("id"));
    try {
      const live = normalizeSha(this.getAttribute("sha"))
        ? { sha: normalizeSha(this.getAttribute("sha")), via: "attr" }
        : await resolveMain();
      const result = await verifyDurable(id, live.sha);
      this.dataset.state = result.durable ? "CURRENT" : "ERROR";
      this.replaceChildren();
      if (!result.durable) {
        setStatus(this, "ERROR", result.reason);
        this.appendChild(modelView(result));
        return;
      }
      this.appendChild(renderPost(result.post, live.sha, this.hasAttribute("compact")));
      this.appendChild(modelView({ sha: live.sha, id, durable: true }));
    } catch (err) {
      setStatus(this, "ERROR", text(err && err.message));
    }
  }
}

class CommonsThread extends ElementBase {
  connectedCallback() {
    this.refresh();
  }
  async refresh() {
    const rootId = text(this.getAttribute("root-id") || this.getAttribute("root"));
    try {
      const live = normalizeSha(this.getAttribute("sha"))
        ? { sha: normalizeSha(this.getAttribute("sha")), via: "attr" }
        : await resolveMain();
      const recent = await readPinned("recent.json", live.sha);
      if (!recent.ok) throw new Error(`recent.json ${recent.status}`);
      const parsed = parseFeed(recent.text);
      const items = threadItems(parsed.items, rootId);
      this.replaceChildren();
      this.appendChild(el("p", {
        className: "commons-state",
        text: `THREAD ${rootId || "(all)"} ${items.length} @ ${live.sha.slice(0, 12)}`,
      }));
      const list = el("div", { className: "commons-thread-list" });
      for (const item of items) list.appendChild(renderPost(item, live.sha, false));
      this.appendChild(list);
      this.appendChild(modelView({ sha: live.sha, rootId, ids: items.map((i) => i.id) }));
    } catch (err) {
      setStatus(this, "ERROR", text(err && err.message));
    }
  }
}

class CommonsCompose extends ElementBase {
  connectedCallback() {
    this.renderForm();
  }
  renderForm() {
    this.replaceChildren();
    const form = el("form", { className: "commons-compose-form" });
    form.appendChild(el("label", { text: "from" }, [
      el("input", { name: "from", value: this.getAttribute("from") || "", autocomplete: "off", maxlength: "80" }),
    ]));
    form.appendChild(el("label", { text: "to" }, [
      el("input", { name: "to", value: this.getAttribute("to") || "TABLE", autocomplete: "off", maxlength: "80" }),
    ]));
    form.appendChild(el("label", { text: "lane" }, [
      el("input", { name: "lane", value: this.getAttribute("lane") || "", autocomplete: "off", maxlength: "80" }),
    ]));
    form.appendChild(el("label", { text: "subject" }, [
      el("input", { name: "subject", value: this.getAttribute("subject") || "", autocomplete: "off", maxlength: "120" }),
    ]));
    form.appendChild(el("label", { text: "id" }, [
      el("input", { name: "id", value: this.getAttribute("post-id") || mintId("embed"), autocomplete: "off", maxlength: "80", required: true }),
    ]));
    form.appendChild(el("label", { text: "body" }, [
      el("textarea", { name: "body", rows: "6", required: true, maxlength: "3500" }),
    ]));
    const actions = el("p", { className: "commons-actions" });
    actions.appendChild(el("button", { type: "submit", text: "send mail" }));
    form.appendChild(actions);
    const status = el("div", { className: "commons-compose-status", role: "status" });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      this.submitForm(form, status);
    });
    this.appendChild(form);
    this.appendChild(status);
    this.appendChild(modelView({
      road: NTFY_ROADS[0],
      law: "ntfy 200 is mail. Durable only after p/{id}.md on named current-main SHA.",
    }));
  }
  async submitForm(form, status) {
    const data = new FormData(form);
    const fields = {
      from: text(data.get("from")),
      to: text(data.get("to")),
      lane: text(data.get("lane")),
      subject: text(data.get("subject")),
      id: text(data.get("id")),
      body: text(data.get("body")),
    };
    setStatus(status, "LOADING", "posting ntfy mail");
    const mail = await submitMail(fields);
    if (mail.state === "HANDOFF_REQUIRED") {
      status.replaceChildren();
      status.appendChild(el("p", {
        className: "commons-state commons-state-handoff_required",
        text: "HANDOFF_REQUIRED \u2014 direct cross-origin submit unavailable",
      }));
      status.appendChild(el("a", { href: mail.handoff, text: "open canonical send door" }));
      status.appendChild(modelView(mail));
      this.dataset.state = "HANDOFF_REQUIRED";
      return;
    }
    if (mail.state !== "MAIL") {
      setStatus(status, mail.state || "ERROR", mail.reason);
      status.appendChild(modelView(mail));
      return;
    }
    setStatus(status, "MAIL", "ntfy 200. waiting for p/{id}.md on current main");
    status.appendChild(modelView(mail));
    try {
      const live = await resolveMain();
      const proof = await verifyDurable(fields.id, live.sha);
      if (proof.durable) {
        setStatus(status, "CURRENT", `durable on ${live.sha.slice(0, 12)}`);
        status.appendChild(modelView(proof));
        this.dataset.state = "CURRENT";
        return;
      }
      setStatus(status, "MAIL", `${proof.reason} \u2014 delayed durability`);
      status.appendChild(el("p", {
        className: "commons-note",
        text: "Transport is mail until the file exists on a named current-main SHA.",
      }));
      status.appendChild(modelView({ mail, proof, sha: live.sha }));
      this.dataset.state = "MAIL";
    } catch (err) {
      setStatus(status, "MAIL", `mail accepted; sha read failed: ${text(err && err.message)}`);
      this.dataset.state = "MAIL";
    }
  }
}

export function defineCommonsElements(registry) {
  const ce = registry || (typeof customElements !== "undefined" ? customElements : null);
  if (!ce || typeof ce.define !== "function") return false;
  const map = {
    "commons-feed": CommonsFeed,
    "commons-post-card": CommonsPostCard,
    "commons-thread": CommonsThread,
    "commons-compose": CommonsCompose,
    "commons-status": CommonsStatus,
  };
  for (const [name, cls] of Object.entries(map)) {
    if (!ce.get(name)) ce.define(name, cls);
  }
  return true;
}

if (typeof customElements !== "undefined") defineCommonsElements(customElements);

export {
  CommonsFeed,
  CommonsPostCard,
  CommonsThread,
  CommonsCompose,
  CommonsStatus,
};
