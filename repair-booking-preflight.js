(function () {
  "use strict";

  var FIXTURES = [
    ["RB-001","normal request","BOOKED",0],
    ["RB-002","retry before provider call","BOOKED",1],
    ["RB-003","timeout before provider call","STOPPED",1],
    ["RB-004","timeout after provider commit","BOOKED",1],
    ["RB-005","duplicate client retry","BOOKED",2],
    ["RB-006","network partition after commit","BOOKED",1],
    ["RB-007","provider unavailable","STOPPED",1],
    ["RB-008","slow response after commit","BOOKED",1],
    ["RB-009","compensating rollback","ROLLED_BACK",0],
    ["RB-010","caller cancellation","STOPPED",0],
    ["RB-011","slot expired","STOPPED",0],
    ["RB-012","same-key same-payload replay","BOOKED",2],
    ["RB-013","same-key different-payload collision","STOPPED",1],
    ["RB-014","agent crash before provider","STOPPED",1],
    ["RB-015","agent crash after provider","BOOKED",1],
    ["RB-016","duplicate provider webhook","BOOKED",1],
    ["RB-017","reordered provider webhook","BOOKED",1],
    ["RB-018","three agent retries","BOOKED",3],
    ["RB-019","rollback after partial commit","ROLLED_BACK",1],
    ["RB-020","final known-good request","BOOKED",0]
  ];

  function hash(text) {
    var value = 2166136261;
    for (var i = 0; i < text.length; i += 1) {
      value ^= text.charCodeAt(i);
      value = Math.imul(value, 16777619);
    }
    return ("00000000" + (value >>> 0).toString(16)).slice(-8);
  }

  function event(type, fields) {
    var out = {type:type};
    Object.keys(fields || {}).forEach(function (key) { out[key] = fields[key]; });
    return out;
  }

  function makeTrace(row, mode) {
    var id = row[0], boundary = row[1], terminal = row[2], retries = row[3];
    var key = "repair-" + id.toLowerCase();
    var bookingId = "booking-" + id.toLowerCase();
    var events = [event("REQUEST_ACCEPTED",{idempotency_key:key})];
    for (var i = 0; i <= retries; i += 1) {
      events.push(event("ATTEMPT_STARTED",{attempt:i + 1}));
    }
    if (terminal === "BOOKED") {
      events.push(event("BOOKING_CREATED",{booking_id:bookingId,idempotency_key:key}));
      if (retries > 0) events.push(event("REPLAY_DEDUPED",{booking_id:bookingId,idempotency_key:key}));
      events.push(event("BOOKED",{booking_id:bookingId}));
    } else if (terminal === "ROLLED_BACK") {
      events.push(event("BOOKING_CREATED",{booking_id:bookingId,idempotency_key:key}));
      events.push(event("ROLLBACK_STARTED",{booking_id:bookingId}));
      events.push(event("ROLLED_BACK",{booking_id:bookingId,reason:"compensation_confirmed"}));
    } else {
      events.push(event("STOPPED",{reason:boundary.replace(/ /g,"_").toUpperCase()}));
    }
    if (mode === "duplicate" && id === "RB-008") {
      events.splice(events.length - 1, 0, event("BOOKING_CREATED",{
        booking_id:bookingId + "-duplicate",
        idempotency_key:key,
        unsafe:true
      }));
    }
    events.forEach(function (item, index) { item.seq = index + 1; });
    return {fixture_id:id,boundary:boundary,expected_terminal:terminal,events:events};
  }

  function evaluateTrace(trace) {
    var created = trace.events.filter(function (e) { return e.type === "BOOKING_CREATED"; });
    var finalEvent = trace.events[trace.events.length - 1] || {};
    var duplicate = created.length > 1;
    var rolledBack = finalEvent.type === "ROLLED_BACK";
    var stopped = finalEvent.type === "STOPPED";
    var booked = finalEvent.type === "BOOKED";
    var rollbackMatches = rolledBack && created.length === 1 &&
      finalEvent.booking_id === created[0].booking_id;
    var pass = !duplicate && (
      (booked && created.length === 1 && finalEvent.booking_id === created[0].booking_id) ||
      (stopped && created.length === 0) ||
      rollbackMatches
    );
    var reason = "accepted";
    if (duplicate) reason = "duplicate_booking";
    else if (!pass) reason = "ambiguous_terminal";
    var firstUnsafe = null;
    if (!pass) {
      var edge = duplicate ? created[1] : finalEvent;
      firstUnsafe = {fixture_id:trace.fixture_id,seq:edge.seq,event_type:edge.type,reason:reason};
    }
    var canonical = JSON.stringify({fixture_id:trace.fixture_id,events:trace.events});
    return {
      fixture_id:trace.fixture_id,
      boundary:trace.boundary,
      terminal:finalEvent.type || "MISSING",
      booking_creates:created.length,
      pass:pass,
      reason:reason,
      trace_id:"trace-" + hash(canonical),
      first_unsafe_edge:firstUnsafe
    };
  }

  function runSuite(mode) {
    mode = mode === "duplicate" ? "duplicate" : "safe";
    var traces = FIXTURES.map(function (row) { return makeTrace(row, mode); });
    var results = traces.map(evaluateTrace);
    var firstUnsafe = null;
    for (var i = 0; i < results.length; i += 1) {
      if (!results[i].pass) { firstUnsafe = results[i].first_unsafe_edge; break; }
    }
    var passed = results.filter(function (r) { return r.pass; }).length;
    return {
      contract_id:"repair-booking-exactly-once-v1",
      mode:mode,
      fixture_count:results.length,
      passed:passed,
      failed:results.length - passed,
      duplicate_appointments:results.reduce(function (n,r) {
        return n + (r.reason === "duplicate_booking" ? r.booking_creates - 1 : 0);
      },0),
      first_unsafe_edge:firstUnsafe,
      results:results,
      traces:traces
    };
  }

  function buildReceipt(mode) {
    var suite = runSuite(mode);
    return {
      schema:"commons-repair-booking-receipt-v1",
      generated_at:new Date().toISOString(),
      synthetic_only:true,
      acceptance:"exactly one booking OR explicit STOPPED/ROLLED_BACK; zero duplicate appointments",
      suite:suite
    };
  }

  var api = {fixtures:FIXTURES.slice(),makeTrace:makeTrace,evaluateTrace:evaluateTrace,runSuite:runSuite,buildReceipt:buildReceipt};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.RepairBookingPreflight = api;

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g,function (char) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char];
    });
  }

  function init() {
    var resultsBody = document.getElementById("results");
    if (!resultsBody) return;
    var summary = document.getElementById("summary");
    var unsafe = document.getElementById("unsafe");
    var receiptPreview = document.getElementById("receipt");
    var exportButton = document.getElementById("export");
    var currentReceipt = null;

    function render(mode) {
      currentReceipt = buildReceipt(mode);
      var suite = currentReceipt.suite;
      summary.innerHTML =
        '<strong class="' + (suite.failed ? "fail" : "pass") + '">' +
        suite.passed + "/" + suite.fixture_count + " passed</strong>" +
        "<span>Failures: " + suite.failed + "</span>" +
        "<span>Duplicate appointments: " + suite.duplicate_appointments + "</span>";
      unsafe.textContent = suite.first_unsafe_edge ?
        "First unsafe edge: " + suite.first_unsafe_edge.fixture_id + " event " +
          suite.first_unsafe_edge.seq + " (" + suite.first_unsafe_edge.reason + ")" :
        "No unsafe edge found. All 20 fixtures satisfy the binary contract.";
      resultsBody.innerHTML = suite.results.map(function (r) {
        return "<tr><td>" + escapeHtml(r.fixture_id) + "</td><td>" + escapeHtml(r.boundary) +
          "</td><td>" + escapeHtml(r.terminal) + "</td><td>" + r.booking_creates +
          '</td><td><span class="tag ' + (r.pass ? "pass" : "fail") + '">' +
          (r.pass ? "PASS" : "FAIL") + "</span></td><td><code>" +
          escapeHtml(r.trace_id) + "</code></td></tr>";
      }).join("");
      receiptPreview.textContent = JSON.stringify(currentReceipt,null,2);
      exportButton.disabled = false;
    }

    document.getElementById("run-safe").addEventListener("click",function () { render("safe"); });
    document.getElementById("run-fault").addEventListener("click",function () { render("duplicate"); });
    exportButton.addEventListener("click",function () {
      if (!currentReceipt) return;
      var blob = new Blob([JSON.stringify(currentReceipt,null,2) + "\n"],{type:"application/json"});
      var url = URL.createObjectURL(blob);
      var link = document.createElement("a");
      link.href = url;
      link.download = "repair-booking-preflight-receipt.json";
      link.click();
      URL.revokeObjectURL(url);
    });
    render("safe");
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded",init);
    else init();
  }
}());
