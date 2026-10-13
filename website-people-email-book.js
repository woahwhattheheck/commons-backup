(function () {
  "use strict";

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

  function render(loop) {
    if (!loop || loop.kind !== "WEBSITE_PEOPLE_EMAIL_BOOK_LOOP") {
      throw new Error("unsupported loop snapshot");
    }
    var truth = loop.truth || {};
    var status = document.getElementById("loop-status");
    if (status) {
      status.textContent =
        "Measured " +
        loop.generated_at +
        ". " +
        truth.websites_ingested +
        " website, " +
        truth.prospects_found +
        " external prospects, " +
        truth.emails_drafted +
        " drafts, " +
        truth.calls_booked +
        " booked, " +
        truth.transport_actions +
        " sent, mailbox " +
        truth.mailbox +
        ".";
    }
    var truthRoot = document.getElementById("truth");
    if (truthRoot) {
      truthRoot.replaceChildren(
        cell(truth.websites_ingested, "website"),
        cell(truth.prospects_found, "prospects"),
        cell(truth.emails_drafted, "drafts"),
        cell(truth.calls_booked, "booked"),
        cell(truth.transport_actions, "sent"),
        cell("USD " + truth.cash_usd, "cash")
      );
    }
    var body = document.getElementById("people");
    if (body) {
      body.replaceChildren();
      (loop.prospects || []).forEach(function (row) {
        var tr = document.createElement("tr");
        tr.appendChild(text("td", row.organization));
        tr.appendChild(text("td", row.owner_role || ""));
        tr.appendChild(text("td", row.recipient_email || row.route.state));
        tr.appendChild(text("td", row.evidence.exact_quote + " — " + row.evidence.source_url));
        tr.appendChild(text("td", row.decision + ": " + (row.next_action || "")));
        body.appendChild(tr);
      });
    }
  }

  var button = document.getElementById("preview");
  if (button) {
    button.addEventListener("click", function () {
      var paste = document.getElementById("paste");
      var out = document.getElementById("preview-out");
      if (!paste || !out) return;
      var value = String(paste.value || "").trim();
      if (!/^https:\/\//i.test(value)) {
        out.textContent = "Use one public https:// website URL.";
        return;
      }
      out.textContent = JSON.stringify({
        command: "run",
        url: value,
        prospects: "revenue/smart_outreach/candidates.json",
        receipts: "revenue/payment_ready/outreach_receipts",
        transport: "STAGED_NOT_SENT"
      }, null, 2);
    });
  }

  fetch("./revenue/website_people_email_book/loop.json", { cache: "no-store" })
    .then(function (response) {
      if (!response.ok) throw new Error("loop.json " + response.status);
      return response.json();
    })
    .then(render)
    .catch(function (error) {
      var status = document.getElementById("loop-status");
      if (status) {
        status.textContent =
          "Live loop.json unavailable. Noscript numbers remain the last landed snapshot. " +
          error.message;
      }
    });
})();
