(function () {
  const ACCEPTED = "./revenue/scope_to_delivery/fixtures/project-accepted-complete.json";
  const UNACCEPTED = "./revenue/scope_to_delivery/fixtures/project-unaccepted.json";
  const CATALOG = "./revenue/scope_to_delivery/fixtures/catalog-view.json";

  function el(id) {
    return document.getElementById(id);
  }

  function pill(text, kind) {
    return '<span class="pill ' + kind + '">' + text + "</span>";
  }

  function row(label, value) {
    return '<div class="row"><span>' + label + "</span><code>" + value + "</code></div>";
  }

  function kindFor(state) {
    const pass = ["ACCEPTED", "LOCKED_SOW", "ISSUED", "PASS", "DELIVERED", "CONFIRMED"];
    const miss = ["NOT_DELIVERED", "MISS", "REJECTED", "ABSENT"];
    if (pass.indexOf(state) >= 0 || state === true) return "pass";
    if (miss.indexOf(state) >= 0 || state === false) return "miss";
    return "idle";
  }

  function renderCatalog(view) {
    const items = (view.listings || []).map(function (item) {
      return "<li><strong>" + item.name + "</strong> — " + item.currency + " " + item.amount +
        " · " + item.state + " · rows " + item.acceptance_row_count + "</li>";
    });
    el("sku-list").innerHTML = items.join("");
  }

  function renderProject(project) {
    const agreement = project.sow || {};
    el("card-agreement").innerHTML = [
      pill(project.agreement_state, kindFor(project.agreement_state)),
      row("SKU", project.sku_name + " / " + project.sku_id),
      row("Agreement", project.agreement_id),
      row("Quote", (agreement.quote || {}).currency + " " + (agreement.quote || {}).amount),
      row("Buyer ref", (agreement.parties || {}).buyer_ref || "—"),
      row("Parties", "REDACTED_PUBLIC / NOT_ON_PUBLIC_MAIN"),
    ].join("");

    el("card-sow").innerHTML = [
      pill(agreement.lock, kindFor(agreement.lock)),
      pill((project.work_packet || {}).state, kindFor((project.work_packet || {}).state)),
      row("Window", ((agreement.window || {}).start || "") + " → " + ((agreement.window || {}).end || "")),
      row("Rows", String(((project.work_packet || {}).acceptance_rows || agreement.acceptance_rows || []).length)),
      "<p class='note'>" + ((project.work_packet || {}).reason || "Packet follows the locked SOW.") + "</p>",
    ].join("");

    const status = project.execution_status || {};
    const rows = (status.rows || []).map(function (item) {
      return row(item.id, item.result);
    }).join("");
    el("card-status").innerHTML = [
      pill(status.status, kindFor(status.status)),
      "<p class='note'>" + (status.reason || "") + "</p>",
      rows,
    ].join("");

    const receipt = project.delivery_receipt || {};
    const invoice = project.invoice || {};
    const pay = (project.payment_state || {}).payment_truth || {};
    el("card-money").innerHTML = [
      pill(receipt.delivery_state, kindFor(receipt.delivery_state)),
      pill("invoice " + invoice.state, kindFor(invoice.state === "ISSUED" ? "ISSUED" : "NOT_ISSUED")),
      row("Delivered", String(receipt.delivered)),
      row("Authorization", pay.authorization || "UNMEASURED"),
      row("Settlement", pay.settlement || "UNMEASURED"),
      row("Payout", pay.payout || "UNMEASURED"),
      row("Bank available", pay.bank_available || "UNMEASURED"),
      row("Cash claimed", String((project.payment_state || {}).cash_claimed)),
      "<p class='note'>Payment does not prove delivery. Current settlement is unverified in this view.</p>",
    ].join("");

    const gaps = ((project.handoff || {}).gaps || []).map(function (gap) {
      return "<li>" + gap + "</li>";
    });
    el("handoff-gaps").innerHTML = gaps.join("") || "<li>None recorded.</li>";
    el("handoff-md").textContent = (project.handoff || {}).markdown || project.markdown || "";
  }

  function load(url, pressed) {
    el("btn-accepted").setAttribute("aria-pressed", pressed === "accepted" ? "true" : "false");
    el("btn-unaccepted").setAttribute("aria-pressed", pressed === "unaccepted" ? "true" : "false");
    fetch(url, { cache: "no-store" })
      .then(function (response) { return response.json(); })
      .then(renderProject)
      .catch(function (error) {
        el("card-agreement").textContent = "Fixture failed to load: " + error;
      });
  }

  fetch(CATALOG, { cache: "no-store" })
    .then(function (response) { return response.json(); })
    .then(renderCatalog)
    .catch(function () {
      el("sku-list").innerHTML = "<li>Catalog fixture failed to load. CLI still works.</li>";
    });

  el("btn-accepted").addEventListener("click", function () { load(ACCEPTED, "accepted"); });
  el("btn-unaccepted").addEventListener("click", function () { load(UNACCEPTED, "unaccepted"); });
  load(ACCEPTED, "accepted");
})();
