(function () {
  "use strict";

  var HOLD = {
    HOLD_DO_NOT_RESEND: true,
    HOLD_DO_NOT_CONTACT: true,
    HOLD_BUILD_AND_VERIFY: true,
    OWNER_HOLD: true,
    DNR_OUTREACH: true,
    NOT_HOT: true,
    BOUNCED: true
  };

  function text(tag, value, className) {
    var node = document.createElement(tag);
    node.textContent = String(value == null ? "" : value);
    if (className) node.className = className;
    return node;
  }

  function cell(value, label) {
    var node = document.createElement("span");
    node.appendChild(text("b", value));
    node.appendChild(document.createTextNode(label));
    return node;
  }

  function hotClass(row) {
    var role = row && row.role;
    if (role !== "external_prospect" && role !== "inbound_contact") return null;
    if (!row.live) return null;
    if (row.decision === "HOLD_BUILD_AND_VERIFY") return null;
    if (row.decision === "OWNER_HOLD" || row.decision === "BOUNCED") return null;
    if (row.dnr || HOLD[row.decision]) return null;
    if (row.decision === "MATERIAL_REPLY") return "material_reply";
    if (row.decision === "SENT_AWAITING_REPLY") return "sent_awaiting_reply";
    if (row.decision === "READY_TO_DRAFT") return "ready_to_draft";
    if (row.decision === "VERIFIED_LEAD_UNSENT") return "verified_lead_unsent";
    return null;
  }

  function laneOf(row) {
    if (hotClass(row)) return "HOT";
    if (row && row.decision === "OWNER_HOLD") return "OWNER_HOLD";
    if (row && row.decision === "BOUNCED") return "BOUNCED";
    if (row && row.decision === "SENT_AWAITING_REPLY" && row.dnr) return "SENT_DNR";
    if (row && row.decision === "HOLD_BUILD_AND_VERIFY") return "HOLD_BUILD";
    if (row && (row.dnr || HOLD[row.decision])) return "DNR";
    return "LIVE";
  }

  var HOT_RANK = {
    material_reply: 0,
    sent_awaiting_reply: 1,
    ready_to_draft: 2,
    verified_lead_unsent: 3
  };

  function parseIndex(raw) {
    var rows = [];
    var header = null;
    String(raw || "").split(/\n/).forEach(function (line) {
      line = line.trim();
      if (!line) return;
      var item = JSON.parse(line);
      if (item.kind === "LM_GTM_INDEX_HEADER") header = item;
      else if (item.kind === "LM_GTM_INDEX_ROW") rows.push(item);
    });
    return { header: header, rows: rows };
  }

  function renderState(state) {
    if (!state || state.kind !== "LM_GTM_INDEX_STATE") {
      throw new Error("unsupported GTM index state");
    }
    var truth = state.truth || {};
    var status = document.getElementById("index-status");
    if (status) {
      status.textContent =
        "Recorded projection composed " +
        state.composed_at +
        ". Canonical CRM " +
        state.canonical_crm +
        ". " +
        (truth.hot_next_actions || 0) +
        " hot, " +
        truth.live_next_actions +
        " live next-actions, " +
        truth.external_prospects +
        " external prospects, mailbox " +
        truth.mailbox +
        ". Current settlement: unverified. Public projection is not a CRM.";
    }
    var truthRoot = document.getElementById("truth");
    if (truthRoot) {
      truthRoot.replaceChildren(
        cell(truth.hot_next_actions || 0, "hot"),
        cell(truth.hold_build_actions || 0, "hold-build"),
        cell(truth.sent_awaiting_dnr_actions || 0, "sent-dnr"),
        cell(truth.live_next_actions, "live next"),
        cell(truth.external_prospects, "prospects"),
        cell(truth.inbound_contacts, "inbound"),
        cell(truth.seller_context_rows, "seller context"),
        cell(truth.transport_actions, "sent by this composer"),
        cell("Unverified", "current settlement")
      );
    }
  }

  function renderTable(id, rows, cellsFor) {
    var body = document.getElementById(id);
    if (!body) return;
    body.replaceChildren();
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      cellsFor(row).forEach(function (value) {
        tr.appendChild(text("td", value));
      });
      body.appendChild(tr);
    });
  }

  function renderHot(parsed) {
    var ranked = [];
    (parsed.rows || []).forEach(function (row) {
      var klass = hotClass(row);
      if (!klass) return;
      ranked.push({ row: row, klass: klass, rank: HOT_RANK[klass] });
    });
    ranked.sort(function (a, b) {
      if (a.rank !== b.rank) return a.rank - b.rank;
      return String(a.row.id).localeCompare(String(b.row.id));
    });
    renderTable("hot-actions", ranked, function (item) {
      var row = item.row;
      return [item.klass, row.id, row.organization || "", row.person || "", row.decision || "", row.next_action || "", row.owner || "UNSEATED"];
    });
  }

  function renderSentDnr(parsed) {
    var rows = (parsed.rows || []).filter(function (row) {
      return row.live && row.dnr && (row.decision === "SENT_AWAITING_REPLY" || row.decision === "BOUNCED");
    });
    rows.sort(function (a, b) {
      return String(a.id).localeCompare(String(b.id));
    });
    renderTable("sent-dnr-actions", rows, function (row) {
      return [row.id, row.organization || "", row.person || "", row.route_ref || row.route_kind || "", row.next_action || ""];
    });
  }

  function renderHold(parsed) {
    var rows = (parsed.rows || []).filter(function (row) {
      return row.live && row.decision === "HOLD_BUILD_AND_VERIFY";
    });
    rows.sort(function (a, b) {
      return String(a.id).localeCompare(String(b.id));
    });
    renderTable("hold-actions", rows, function (row) {
      var source = (row.source_paths || []).join(" ");
      return [row.id, row.organization || "", row.person || "", row.next_action || "", source];
    });
  }

  function renderIndex(parsed) {
    var body = document.getElementById("next-actions");
    if (!body) return;
    body.replaceChildren();
    (parsed.rows || []).forEach(function (row) {
      if (!row.live) return;
      var tr = document.createElement("tr");
      tr.appendChild(text("td", laneOf(row)));
      tr.appendChild(text("td", row.id));
      tr.appendChild(text("td", row.organization || ""));
      tr.appendChild(text("td", row.decision || ""));
      tr.appendChild(text("td", row.next_action || ""));
      tr.appendChild(text("td", row.route_ref || row.route_kind || ""));
      tr.appendChild(text("td", row.owner || "UNSEATED"));
      body.appendChild(tr);
    });
  }

  Promise.all([
    fetch("./revenue/lm_gtm_index/state.json", { cache: "no-store" }).then(function (response) {
      if (!response.ok) throw new Error("state.json " + response.status);
      return response.json();
    }),
    fetch("./revenue/lm_gtm_index/INDEX.jsonl", { cache: "no-store" }).then(function (response) {
      if (!response.ok) throw new Error("INDEX.jsonl " + response.status);
      return response.text();
    })
  ])
    .then(function (pair) {
      renderState(pair[0]);
      var parsed = parseIndex(pair[1]);
      renderHot(parsed);
      renderSentDnr(parsed);
      renderHold(parsed);
      renderIndex(parsed);
    })
    .catch(function (error) {
      var status = document.getElementById("index-status");
      if (status) {
        status.textContent =
          "Live INDEX unavailable. Noscript numbers remain the last landed snapshot. " +
          error.message;
      }
    });
})();
