(function () {
  "use strict";

  var target = document.getElementById("revenue-control");
  if (!target || typeof fetch !== "function") return;

  function text(tag, value, className) {
    var node = document.createElement(tag);
    node.textContent = String(value);
    if (className) node.className = className;
    return node;
  }

  function formatTotals(rows) {
    if (!Array.isArray(rows) || !rows.length) return "None evidenced";
    return rows.map(function (row) {
      return row.amount + " " + row.currency;
    }).join(" · ");
  }

  function snapshotNote(control) {
    var snapshotAsOf = typeof control.as_of === "string" && control.as_of
      ? control.as_of : "date unavailable";
    var cashAsOf = control.settled_cash && typeof control.settled_cash.as_of === "string" &&
      control.settled_cash.as_of ? control.settled_cash.as_of : "date unavailable";
    return "Recorded control snapshot as of " + snapshotAsOf +
      ". Provider cash evidence as of " + cashAsOf +
      ". Current settlement: unverified.";
  }

  function render(control) {
    target.replaceChildren();
    var truth = control.truth;
    var cash = control.settled_cash;
    var settled = control.settled_awards;
    target.append(text("p", snapshotNote(control), "note"));
    var summary = document.createElement("div");
    summary.className = "metrics";
    [
      ["Recorded USD cash", "USD " + truth.collected_cash_usd],
      ["Provider cash receipts", truth.settled_cash_receipts],
      ["Paid awards", truth.paid_awards],
      ["Settled award value", formatTotals(truth.settled_amounts_by_currency)],
      ["Offers", control.offers.length],
      ["Opportunities", truth.prospects_evaluated],
      ["Ready to draft", truth.ready_to_draft],
      ["Transport actions", truth.transport_actions]
    ].forEach(function (pair) {
      var metric = document.createElement("div");
      metric.className = "metric";
      metric.append(text("span", pair[0], "metric-label"));
      metric.append(text("strong", pair[1]));
      summary.append(metric);
    });
    target.append(summary);

    target.append(text("h3", "Recorded provider cash evidence"));
    var cashList = document.createElement("ol");
    cashList.className = "queue";
    cash.receipts.forEach(function (receipt) {
      var row = document.createElement("li");
      row.append(text(
        "strong",
        receipt.program + " — USD " + receipt.amount_usd + " PAID"
      ));
      row.append(text(
        "span",
        "Evidence " + receipt.provider_receipt_id + " · " +
          receipt.evidenced_at + ". Collection: do not resend."
      ));
      cashList.append(row);
    });
    if (!cash.receipts.length) {
      cashList.append(text("li", "No provider-confirmed USD cash receipts are recorded."));
    }
    target.append(cashList);
    target.append(text(
      "p",
      "Provider-paid cash is counted only from PAID receipts. Bank availability and withdrawability are not asserted.",
      "note"
    ));

    target.append(text("h3", "Recorded paid awards"));
    var awardList = document.createElement("ol");
    awardList.className = "queue";
    settled.awards.forEach(function (award) {
      var row = document.createElement("li");
      row.append(text(
        "strong",
        award.program + " — " + award.amount + " " + award.currency + " PAID"
      ));
      row.append(text(
        "span",
        "Paid " + award.paid_at + " to hosted handle " +
          award.destination_reference + ". Collection: do not resend."
      ));
      awardList.append(row);
    });
    if (!settled.awards.length) {
      awardList.append(text("li", "No sponsor-confirmed paid awards are recorded."));
    }
    target.append(awardList);
    target.append(text(
      "p",
      "Award currencies remain separate. No USD conversion, bank availability, or withdrawability is asserted.",
      "note"
    ));

    target.append(text("h3", "Recorded execution queue"));
    var list = document.createElement("ol");
    list.className = "queue";
    control.execution_queue.forEach(function (item) {
      var row = document.createElement("li");
      row.append(text("strong", item.organization + " — " + item.decision));
      row.append(text("span", "Fit " + item.fit_score + "/100 · " + item.next_action));
      list.append(row);
    });
    if (!control.execution_queue.length) {
      list.append(text("li", "No evidenced opportunities are in this recorded snapshot."));
    }
    target.append(list);

    target.append(text("h3", "Shortest honest blockers"));
    var blockerList = document.createElement("ol");
    blockerList.className = "queue";
    control.blockers.forEach(function (item) {
      var row = document.createElement("li");
      row.append(text("strong", item.id));
      row.append(text("span", item.condition + " Recorded: " + item.current));
      blockerList.append(row);
    });
    target.append(blockerList);
  }

  fetch("./revenue/right_now/control.json", {cache: "no-store"})
    .then(function (response) {
      if (!response.ok) throw new Error("control snapshot unavailable");
      return response.json();
    })
    .then(render)
    .catch(function () {
      target.dataset.state = "fallback";
    });
}());
