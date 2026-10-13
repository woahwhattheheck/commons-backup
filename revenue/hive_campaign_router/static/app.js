// SPDX-License-Identifier: Apache-2.0
"use strict";

const state = {products: [], offers: [], presets: [], links: [], recent_events: [], report: {campaigns: []}};
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
let loadRevision = 0;

function text(value) {
  return String(value ?? "");
}

function notice(message, kind = "ok") {
  const node = $("#notice");
  node.textContent = message;
  node.dataset.kind = kind;
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
  });
  const payload = await response.json().catch(() => ({message: `HTTP ${response.status}`}));
  if (!response.ok) throw new Error(payload.message || `HTTP ${response.status}`);
  return payload;
}

function option(value, label) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = label;
  return node;
}

function refillSelects() {
  $$('[data-products]').forEach((select) => {
    const previous = select.value;
    select.replaceChildren(option("", "Choose a product"), ...state.products.map((p) => option(p.id, `${p.brand} · ${p.name}`)));
    select.value = previous;
  });
  $$('[data-offers]').forEach((select) => {
    const previous = select.value;
    select.replaceChildren(option("", "No offer (direct only)"), ...state.offers.map((o) => option(o.id, o.name)));
    select.value = previous;
  });
  $$('[data-presets]').forEach((select) => {
    const previous = select.value;
    select.replaceChildren(option("", "No UTM preset"), ...state.presets.map((p) => option(p.id, `${p.name} · ${p.utm_campaign}`)));
    select.value = previous;
  });
}

function linkCard(link) {
  const article = document.createElement("article");
  article.className = "link-card";
  article.dataset.slug = link.slug;

  const head = document.createElement("div");
  head.className = "link-card-head";
  const title = document.createElement("div");
  const eyebrow = document.createElement("p"); eyebrow.className = "eyebrow"; eyebrow.textContent = link.product_name;
  const h3 = document.createElement("h3"); h3.textContent = link.slug;
  const url = document.createElement("a"); url.href = link.short_url; url.target = "_blank"; url.rel = "noreferrer"; url.textContent = link.short_url;
  title.append(eyebrow, h3, url);
  const counts = document.createElement("div"); counts.className = "link-counts";
  counts.innerHTML = `<span><strong>${Number(link.clicks || 0)}</strong> clicks</span><span><strong>${Number(link.conversions || 0)}</strong> conversions</span>`;
  head.append(title, counts);

  const form = document.createElement("form");
  form.className = "link-edit";
  form.dataset.linkEdit = link.slug;
  form.innerHTML = `
    <label>Destination<input name="destination" type="url" maxlength="2048" required></label>
    <label>Mode<select name="route_mode"><option value="offer">Offer page</option><option value="redirect">Direct redirect</option></select></label>
    <label>Status<select name="active"><option value="true">Active</option><option value="false">Paused</option></select></label>
    <button class="primary-button" type="submit">Save changes</button>`;
  $("[name=destination]", form).value = link.destination;
  $("[name=route_mode]", form).value = link.route_mode;
  $("[name=active]", form).value = String(Boolean(link.active));

  const actions = document.createElement("div");
  actions.className = "link-actions";
  actions.innerHTML = `
    <a class="secondary-button" href="${link.qr_url}" download="${link.slug}.svg">Download QR</a>
    <button class="secondary-button" type="button" data-copy="${link.short_url}">Copy link</button>
    <button class="secondary-button" type="button" data-test-conversion="${link.slug}">Log test conversion</button>`;

  article.append(head, form, actions);
  return article;
}

function render() {
  refillSelects();
  const clicks = state.links.reduce((sum, item) => sum + Number(item.clicks || 0), 0);
  const conversions = state.links.reduce((sum, item) => sum + Number(item.conversions || 0), 0);
  $("#metric-products").textContent = state.products.length;
  $("#metric-links").textContent = state.links.length;
  $("#metric-clicks").textContent = clicks;
  $("#metric-conversions").textContent = conversions;

  $("#links-empty").hidden = state.links.length > 0;
  $("#links-list").replaceChildren(...state.links.map(linkCard));

  const report = $("#campaign-report");
  report.replaceChildren();
  for (const row of state.report.campaigns || []) {
    const tr = document.createElement("tr");
    for (const key of ["utm_campaign", "utm_source", "utm_medium", "links", "clicks", "conversions"]) {
      const td = document.createElement("td"); td.textContent = text(row[key]); tr.append(td);
    }
    report.append(tr);
  }
  if (!report.children.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td"); td.colSpan = 6; td.className = "muted"; td.textContent = "No attributed events yet.";
    tr.append(td); report.append(tr);
  }

  const recent = $("#recent-events");
  recent.replaceChildren();
  for (const event of state.recent_events) {
    const li = document.createElement("li");
    const strong = document.createElement("strong"); strong.textContent = event.event_type;
    const details = document.createElement("span");
    details.textContent = `${event.slug} · ${event.utm_campaign || "direct"} · ${new Date(event.occurred_at).toLocaleString()}`;
    li.append(strong, details); recent.append(li);
  }
  if (!recent.children.length) {
    const li = document.createElement("li"); li.className = "muted"; li.textContent = "No events yet."; recent.append(li);
  }
}

function reportPending(message) {
  $("#report-status").textContent = message;
  $("#campaign-report").replaceChildren();
  $$("[data-report-csv]").forEach((link) => {
    link.removeAttribute("href");
    link.setAttribute("aria-disabled", "true");
  });
}

async function load() {
  const revision = ++loadRevision;
  const query = new URLSearchParams();
  for (const key of ["start", "end"]) {
    const value = $(`[name=${key}]`, $("#report-filters")).value;
    if (value) query.set(key, value);
  }
  reportPending("Loading the selected UTC period…");
  $("#report-filters").setAttribute("aria-busy", "true");
  try {
    const [workspace, report] = await Promise.all([
      request("/api/state"),
      request(`/api/report?${query}`),
    ]);
    if (revision !== loadRevision) return;
    Object.assign(state, workspace, {report});
    render();
    const range = report.date_range;
    $("#report-status").textContent = range.start || range.end
      ? `UTC dates: ${range.start || "beginning"} through ${range.end || "present"} (inclusive).`
      : "All time. Report dates use UTC.";
    $$("[data-report-csv]").forEach((link) => {
      const csvQuery = new URLSearchParams(query);
      csvQuery.set("view", link.dataset.reportCsv);
      link.href = `/api/report.csv?${csvQuery}`;
      link.removeAttribute("aria-disabled");
    });
    notice("Workspace is current.");
  } catch (error) {
    if (revision !== loadRevision) return;
    reportPending(`Report unavailable: ${error.message}`);
    throw error;
  } finally {
    if (revision === loadRevision) $("#report-filters").setAttribute("aria-busy", "false");
  }
}

function formPayload(form) {
  const payload = Object.fromEntries(new FormData(form).entries());
  for (const key of ["product_id", "offer_id", "preset_id"]) {
    if (key in payload) payload[key] = payload[key] || null;
  }
  return payload;
}

async function submitForm(form, endpoint, label) {
  const payload = formPayload(form);
  await request(endpoint, {method: "POST", body: JSON.stringify(payload)});
  form.reset();
  await load();
  notice(`${label} created.`);
}

$("#product-form").addEventListener("submit", (event) => {
  event.preventDefault(); submitForm(event.currentTarget, "/api/products", "Product").catch((error) => notice(error.message, "error"));
});
$("#offer-form").addEventListener("submit", (event) => {
  event.preventDefault(); submitForm(event.currentTarget, "/api/offers", "Offer").catch((error) => notice(error.message, "error"));
});
$("#preset-form").addEventListener("submit", (event) => {
  event.preventDefault(); submitForm(event.currentTarget, "/api/presets", "Preset").catch((error) => notice(error.message, "error"));
});
$("#link-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formPayload(form);
  if (payload.route_mode === "offer" && !payload.offer_id) return notice("Offer routes require an offer.", "error");
  request("/api/links", {method: "POST", body: JSON.stringify(payload)})
    .then(() => { form.reset(); return load(); })
    .then(() => notice("Stable campaign link created."))
    .catch((error) => notice(error.message, "error"));
});

$("#links-list").addEventListener("submit", (event) => {
  const form = event.target.closest("[data-link-edit]");
  if (!form) return;
  event.preventDefault();
  const payload = formPayload(form);
  payload.active = payload.active === "true";
  request(`/api/links/${encodeURIComponent(form.dataset.linkEdit)}`, {method: "PATCH", body: JSON.stringify(payload)})
    .then(load).then(() => notice("Destination updated; short link and QR stayed unchanged."))
    .catch((error) => notice(error.message, "error"));
});

$("#links-list").addEventListener("click", async (event) => {
  const copyButton = event.target.closest("[data-copy]");
  const conversionButton = event.target.closest("[data-test-conversion]");
  if (copyButton) {
    await navigator.clipboard.writeText(copyButton.dataset.copy);
    return notice("Short link copied.");
  }
  if (conversionButton) {
    const id = `manual_${crypto.randomUUID().replaceAll("-", "")}`;
    try {
      await request("/api/events", {method: "POST", body: JSON.stringify({
        slug: conversionButton.dataset.testConversion,
        event_type: "conversion",
        event_id: id,
      })});
      await load();
      notice(`Test conversion ${id} attributed.`);
    } catch (error) {
      notice(error.message, "error");
    }
  }
});

$("#report-filters").addEventListener("submit", (event) => {
  event.preventDefault();
  load().catch((error) => notice(error.message, "error"));
});
$("#report-filters").addEventListener("input", () => {
  ++loadRevision;
  $("#report-filters").setAttribute("aria-busy", "false");
  reportPending("Filters changed. Apply them to load the selected UTC dates.");
});
$("#report-all-time").addEventListener("click", () => {
  $("#report-filters").reset();
  load().catch((error) => notice(error.message, "error"));
});
$("#refresh-button").addEventListener("click", () => load().catch((error) => notice(error.message, "error")));
load().catch((error) => notice(error.message, "error"));
