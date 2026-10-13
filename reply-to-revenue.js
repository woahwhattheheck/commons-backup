(function () {
  "use strict";

  function text(tag, value, className) {
    var node = document.createElement(tag);
    node.textContent = String(value == null ? "" : value);
    if (className) node.className = className;
    return node;
  }

  function render(funnel) {
    if (!funnel || funnel.kind !== "REPLY_TO_REVENUE_FUNNEL") {
      throw new Error("unsupported funnel snapshot");
    }
    var truth = funnel.truth || {};
    var status = document.getElementById("funnel-status");
    if (status) {
      status.textContent =
        "Measured " +
        funnel.measured_at +
        ". " +
        truth.distinct_contacts +
        " contacts, " +
        truth.inbound_recorded +
        " inbound, " +
        truth.auto_acks +
        " auto-acks, " +
        truth.human_positive +
        " human-positive, " +
        truth.resends +
        " resends. Recorded cash at that snapshot: USD " +
        truth.cash_usd +
        ". Current settlement is unverified.";
    }
    var truthRoot = document.getElementById("truth");
    if (truthRoot) {
      truthRoot.replaceChildren(
        cell(truth.distinct_contacts, "contacts"),
        cell(truth.inbound_recorded, "inbound"),
        cell(truth.auto_acks, "auto-acks"),
        cell(truth.human_positive, "human-positive"),
        cell(truth.resends, "resends"),
        cell("Unverified", "current settlement")
      );
    }
    var surfacesRoot = document.getElementById("surfaces");
    var empty = document.getElementById("surfaces-empty");
    if (surfacesRoot) {
      surfacesRoot.replaceChildren();
      (funnel.surfaces || []).forEach(function (row) {
        var card = document.createElement("article");
        card.className = "card";
        card.appendChild(text("h3", row.organization));
        card.appendChild(text("p", row.context));
        card.appendChild(text("p", "Next: " + row.next_action + " → " + row.handoff, "note"));
        surfacesRoot.appendChild(card);
      });
      if (empty) empty.hidden = (funnel.surfaces || []).length > 0;
    }
    var body = document.getElementById("contacts");
    if (body) {
      body.replaceChildren();
      (funnel.contacts || []).forEach(function (row) {
        var tr = document.createElement("tr");
        tr.appendChild(text("td", row.organization));
        var lane = text("td", "");
        lane.appendChild(text("span", row.lane, "lane " + row.lane));
        tr.appendChild(lane);
        tr.appendChild(text("td", row.next_action));
        tr.appendChild(text("td", row.inbound_count));
        tr.appendChild(text("td", row.hard_dnr ? "HARD DNR" : "open"));
        body.appendChild(tr);
      });
    }
  }

  function cell(value, label) {
    var node = document.createElement("span");
    node.appendChild(text("b", value));
    node.appendChild(document.createTextNode(label));
    return node;
  }

  fetch("./revenue/reply_to_revenue/funnel.json", { cache: "no-store" })
    .then(function (response) {
      if (!response.ok) throw new Error("funnel.json " + response.status);
      return response.json();
    })
    .then(render)
    .catch(function (error) {
      var status = document.getElementById("funnel-status");
      if (status) status.textContent = "Live funnel.json unavailable. Noscript numbers remain the last landed snapshot. " + error.message;
    });
})();
