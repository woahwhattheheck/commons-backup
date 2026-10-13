const state = { all: [], filtered: [] };
const $ = (id) => document.getElementById(id);
const statusOrder = ["New", "In Transit", "Delayed", "Delivered"];
const statusColors = { New: "#4d8dff", "In Transit": "#5ce1e6", Delayed: "#ff6b76", Delivered: "#65d394" };

function esc(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function fmtDate(value, withTime = false) {
  const date = new Date(value);
  const options = withTime
    ? { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }
    : { month: "short", day: "numeric" };
  return new Intl.DateTimeFormat("en-US", options).format(date);
}

function slug(value) { return String(value).toLowerCase().replaceAll(" ", "-"); }

function renderCards(rows) {
  const counts = Object.fromEntries(statusOrder.map((status) => [status, rows.filter((row) => row.status === status).length]));
  $("new-count").textContent = counts.New;
  $("transit-count").textContent = counts["In Transit"];
  $("delayed-count").textContent = counts.Delayed;
  $("delivered-count").textContent = counts.Delivered;
}

function renderMix(rows) {
  const total = rows.length;
  $("mix-total").textContent = `${total} request${total === 1 ? "" : "s"}`;
  $("status-mix").innerHTML = statusOrder.map((status) => {
    const count = rows.filter((row) => row.status === status).length;
    const pct = total ? Math.round((count / total) * 100) : 0;
    return `<div class="mix-row"><span>${esc(status)}</span><div class="track"><div class="fill" style="width:${pct}%;background:${statusColors[status]}"></div></div><b>${count}</b></div>`;
  }).join("");
}

function renderTrend(rows) {
  const latest = state.all.reduce((max, row) => Math.max(max, new Date(row.received_at).getTime()), 0) || Date.now();
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(latest);
    date.setUTCHours(0, 0, 0, 0);
    date.setUTCDate(date.getUTCDate() - (6 - index));
    return date;
  });
  const values = days.map((day) => rows.filter((row) => {
    const value = new Date(row.received_at);
    return value.toISOString().slice(0, 10) === day.toISOString().slice(0, 10);
  }).length);
  const max = Math.max(1, ...values);
  const points = values.map((value, index) => ({ x: 48 + index * 100, y: 138 - (value / max) * 100, value }));
  const line = points.map((point) => `${point.x},${point.y}`).join(" ");
  const area = `48,138 ${line} 648,138`;
  $("trend-total").textContent = `${values.reduce((sum, value) => sum + value, 0)} in window`;
  $("trend").innerHTML = `
    <defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5ce1e6" stop-opacity=".3"/><stop offset="1" stop-color="#5ce1e6" stop-opacity="0"/></linearGradient></defs>
    <line class="axis" x1="48" y1="138" x2="648" y2="138"/><polygon class="trend-area" points="${area}"/><polyline class="trend-line" points="${line}"/>
    ${points.map((point, index) => `<circle class="dot" cx="${point.x}" cy="${point.y}" r="5"><title>${point.value} requests</title></circle><text class="chart-label" x="${point.x}" y="162" text-anchor="middle">${days[index].toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" })}</text>`).join("")}`;
}

function renderRows(rows) {
  $("loading").classList.add("hidden");
  $("error").classList.add("hidden");
  $("empty").classList.toggle("hidden", rows.length > 0);
  $("request-table").classList.toggle("hidden", rows.length === 0);
  $("rows").innerHTML = rows.map((row) => `
    <tr tabindex="0" data-id="${esc(row.id)}">
      <td><strong>${esc(row.id)}</strong></td><td>${fmtDate(row.received_at, true)}</td><td>${esc(row.customer)}</td>
      <td><span class="route">${esc(row.origin)} → ${esc(row.destination)}</span></td><td>${esc(row.cargo)}</td>
      <td><span class="badge ${slug(row.status)}">${esc(row.status)}</span></td><td class="temp">${esc(row.current_temp_c.toFixed(1))}°</td><td>${fmtDate(row.eta)}</td>
    </tr>`).join("");
  $("rows").querySelectorAll("tr").forEach((row) => {
    const open = () => showDetail(state.all.find((item) => item.id === row.dataset.id));
    row.addEventListener("click", open);
    row.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } });
  });
}

function applyFilters() {
  const query = $("search").value.trim().toLowerCase();
  const status = $("status").value;
  const location = $("location").value;
  const received = $("received").value;
  state.filtered = state.all.filter((row) => {
    const haystack = [row.id, row.customer, row.origin, row.destination, row.cargo].join(" ").toLowerCase();
    return (!query || haystack.includes(query)) && (!status || row.status === status) && (!location || row.origin === location) && (!received || row.received_at.slice(0, 10) >= received);
  });
  renderCards(state.filtered); renderTrend(state.filtered); renderMix(state.filtered); renderRows(state.filtered);
}

function showDetail(row) {
  if (!row) return;
  $("detail-title").textContent = row.id;
  const excursion = row.current_temp_c < row.min_temp_c || row.current_temp_c > row.max_temp_c;
  $("detail-body").innerHTML = `
    <section><h3>Request</h3><dl><dt>Customer</dt><dd>${esc(row.customer)}</dd><dt>Status</dt><dd><span class="badge ${slug(row.status)}">${esc(row.status)}</span></dd><dt>Received</dt><dd>${fmtDate(row.received_at, true)}</dd><dt>Dispatcher</dt><dd>${esc(row.dispatcher)}</dd></dl></section>
    <section><h3>Route</h3><dl><dt>Origin</dt><dd>${esc(row.origin)}</dd><dt>Destination</dt><dd>${esc(row.destination)}</dd><dt>Carrier</dt><dd>${esc(row.carrier)}</dd><dt>ETA</dt><dd>${fmtDate(row.eta, true)}</dd></dl></section>
    <section class="wide"><h3>Cold-chain condition</h3><dl><dt>Cargo</dt><dd>${esc(row.cargo)}</dd><dt>Current</dt><dd>${row.current_temp_c.toFixed(1)}°C</dd><dt>Allowed range</dt><dd>${row.min_temp_c.toFixed(1)}° to ${row.max_temp_c.toFixed(1)}°C</dd><dt>Condition</dt><dd style="color:${excursion ? "#ff9aa2" : "#8ce6b3"}">${excursion ? "Temperature excursion" : "Within range"}</dd></dl><div class="meter"><i style="width:${Math.min(100, Math.max(5, ((row.current_temp_c - row.min_temp_c) / (row.max_temp_c - row.min_temp_c)) * 100))}%;background:${excursion ? "#ff6b76" : "#65d394"}"></i></div></section>
    <section class="wide"><h3>Latest note</h3><div>${esc(row.note)}</div></section>`;
  $("detail-dialog").showModal();
}

async function load() {
  try {
    const response = await fetch("sample_requests.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`Data feed returned HTTP ${response.status}.`);
    const payload = await response.json();
    if (!payload || !Array.isArray(payload.requests)) throw new Error("Data feed does not contain a requests array.");
    state.all = payload.requests;
    $("updated").textContent = `Sample updated ${fmtDate(payload.generated_at, true)}`;
    const origins = [...new Set(state.all.map((row) => row.origin))].sort();
    $("location").insertAdjacentHTML("beforeend", origins.map((origin) => `<option>${esc(origin)}</option>`).join(""));
    applyFilters();
  } catch (error) {
    $("loading").classList.add("hidden"); $("error").classList.remove("hidden");
    $("error-message").textContent = error.message;
    ["new-count", "transit-count", "delayed-count", "delivered-count"].forEach((id) => { $(id).textContent = "—"; });
  }
}

["search", "status", "location", "received"].forEach((id) => $(id).addEventListener("input", applyFilters));
$("reset").addEventListener("click", () => { $("search").value = ""; $("status").value = ""; $("location").value = ""; $("received").value = ""; applyFilters(); });
$("detail-dialog").querySelector(".close").addEventListener("click", () => $("detail-dialog").close());
load();
