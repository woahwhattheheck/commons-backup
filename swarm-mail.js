(() => {
  "use strict";

  const manifestStatus = document.querySelector("#manifest-status");
  const truthRoot = document.querySelector("#truth");
  const proofsRoot = document.querySelector("#proofs");
  const routesRoot = document.querySelector("#routes");

  const text = (tag, value, className) => {
    const node = document.createElement(tag);
    node.textContent = String(value);
    if (className) node.className = className;
    return node;
  };

  const link = (label, href) => {
    const node = document.createElement("a");
    node.textContent = label;
    node.href = href;
    return node;
  };

  const assertManifest = (manifest, commerce) => {
    if (!manifest || manifest.schema_version !== "commons-swarm-mail/v2" || !Array.isArray(manifest.inboxes)) {
      throw new Error("unsupported swarm-mail manifest");
    }
    if (!commerce || !Array.isArray(commerce.listings)) throw new Error("commerce catalog unavailable");
    if (!manifest.domain || !manifest.domain.proofs || !manifest.transport || !manifest.truth) {
      throw new Error("manifest state is incomplete");
    }
    if (!["UNPROVISIONED", "MEASURED"].includes(manifest.domain.state)) throw new Error("invalid domain state");
    if (!["UNMEASURED", "MTA_ACCEPTANCE_MEASURED", "PROVIDER_REPORT_RECORDED"].includes(manifest.transport.state)) {
      throw new Error("invalid transport state");
    }
    const truthFields = [
      "measured_inboxes", "drafted_messages", "queued_messages", "unknown_effect_dispatches",
      "mta_accepted_messages", "provider_reported_deliveries", "verified_positive_replies", "paid_deliveries",
    ];
    if (truthFields.some((field) => !Number.isSafeInteger(manifest.truth[field]) || manifest.truth[field] < 0)) {
      throw new Error("invalid measured count");
    }
    if (typeof manifest.truth.bank_available_usd !== "number" || !Number.isFinite(manifest.truth.bank_available_usd) || manifest.truth.bank_available_usd < 0) {
      throw new Error("invalid bank-available amount");
    }
    const commerceIds = new Set(commerce.listings.map((item) => item.id));
    const inboxIds = new Set();
    const localParts = new Set();
    const routed = [];
    for (const inbox of manifest.inboxes) {
      if (!inbox || inboxIds.has(inbox.inbox_id) || localParts.has(inbox.local_part)) throw new Error("duplicate inbox route");
      inboxIds.add(inbox.inbox_id);
      localParts.add(inbox.local_part);
      if (!Array.isArray(inbox.sku_ids) || inbox.sku_ids.length === 0) throw new Error("empty SKU route");
      if (inbox.address_state === "UNPROVISIONED" && (inbox.public_address !== null || inbox.send_mode !== "DRAFT_ONLY")) {
        throw new Error("unmeasured address exposed as live");
      }
      if (inbox.address_state === "MEASURED" && (!inbox.public_address || inbox.send_mode !== "INBOUND_AND_OUTBOUND")) {
        throw new Error("measured address is incomplete");
      }
      if (!["UNPROVISIONED", "MEASURED"].includes(inbox.address_state)) {
        throw new Error("invalid inbox state");
      }
      routed.push(...inbox.sku_ids);
    }
    const routedSet = new Set(routed);
    if (routed.length !== routedSet.size || routedSet.size !== commerceIds.size || [...commerceIds].some((id) => !routedSet.has(id))) {
      throw new Error("SKU routing is incomplete or duplicated");
    }
  };

  const renderTruth = (truth) => {
    const fields = [
      ["measured inboxes", truth.measured_inboxes],
      ["drafted", truth.drafted_messages],
      ["queued", truth.queued_messages],
      ["unknown effect", truth.unknown_effect_dispatches],
      ["MTA accepted", truth.mta_accepted_messages],
      ["provider reports", truth.provider_reported_deliveries],
      ["positive replies", truth.verified_positive_replies],
      ["paid deliveries", truth.paid_deliveries],
      ["bank available", `$${Number(truth.bank_available_usd).toFixed(2)}`],
    ];
    for (const [label, value] of fields) {
      const cell = document.createElement("span");
      cell.append(text("b", value), document.createTextNode(label));
      truthRoot.append(cell);
    }
  };

  const renderProofs = (domain) => {
    proofsRoot.append(text("span", `DOMAIN ${domain.state}`));
    for (const name of ["mx", "spf", "dkim", "dmarc"]) {
      proofsRoot.append(text("span", `${name.toUpperCase()} ${domain.proofs[name]}`));
    }
    proofsRoot.append(text("span", domain.proof_bundle_commitment ? "PROOF BUNDLE COMMITTED" : "PROOF BUNDLE UNCOMMITTED"));
  };

  const renderRoutes = (manifest, commerce) => {
    const listings = new Map(commerce.listings.map((item) => [item.id, item]));
    for (const inbox of manifest.inboxes) {
      const card = document.createElement("article");
      card.className = "card";
      card.dataset.inboxId = inbox.inbox_id;
      card.dataset.addressState = inbox.address_state;
      card.append(
        text("p", inbox.model_family, "eyebrow"),
        text("h3", inbox.inbox_id),
        text("span", inbox.address_state, `state ${inbox.address_state}`),
        text("p", `Route label: ${inbox.agent_claim} · reply owner: ${inbox.reply_owner}`, "note"),
      );
      if (inbox.public_address) {
        const addressLine = document.createElement("p");
        addressLine.append("Address: ", link(inbox.public_address, `mailto:${inbox.public_address}`));
        card.append(addressLine);
      } else {
        card.append(text("p", `Reserved local part: ${inbox.local_part} · not a working email address.`));
      }
      card.append(text("p", `Mode: ${inbox.send_mode} · daily new-thread budget: ${inbox.daily_new_thread_limit}`, "mono"));
      const list = document.createElement("ul");
      list.className = "sku-list";
      for (const skuId of inbox.sku_ids) {
        const item = document.createElement("li");
        const listing = listings.get(skuId);
        item.append(link(listing ? listing.name : skuId, `./commerce.html#${encodeURIComponent(skuId)}`));
        list.append(item);
      }
      card.append(list);
      routesRoot.append(card);
    }
  };

  Promise.all([
    fetch("./revenue/swarm_mail/inboxes.json", { cache: "no-store" }).then((response) => {
      if (!response.ok) throw new Error(`manifest HTTP ${response.status}`);
      return response.json();
    }),
    fetch("./revenue/outcome_commerce/catalog.json", { cache: "no-store" }).then((response) => {
      if (!response.ok) throw new Error(`commerce HTTP ${response.status}`);
      return response.json();
    }),
  ]).then(([manifest, commerce]) => {
    assertManifest(manifest, commerce);
    renderTruth(manifest.truth);
    renderProofs(manifest.domain);
    renderRoutes(manifest, commerce);
    manifestStatus.textContent = `${manifest.inboxes.length} model routes · ${commerce.listings.length} SKUs · snapshot ${manifest.measured_at}. Domain: ${manifest.domain.state}. Transport: ${manifest.transport.state}.`;
  }).catch((error) => {
    manifestStatus.textContent = `FAIL CLOSED — ${error.message}`;
    manifestStatus.dataset.state = "FAILED";
  });
})();
