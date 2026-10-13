(function () {
  "use strict";

  var form = document.getElementById("triage-form");
  var output = document.getElementById("triage-output");
  var status = document.getElementById("triage-status");
  if (!form || !output) return;

  var CLASSES = [
    ["RETRY_LOOP", ["retry", "loop", "same tool", "repeats", "again", "forever", "stuck calling"]],
    ["SILENT_PARTIAL", ["silent", "partial", "half", "cut off", "truncated", "looks finished", "no error"]],
    ["NO_STOP", ["never stops", "no stop", "runaway", "budget", "cost", "keeps going"]],
    ["NO_ROLLBACK", ["cannot reset", "no rollback", "dirty state", "duplicate action", "cannot undo"]],
    ["STATE_LOSS", ["lost state", "forgot", "restart", "session died", "crash", "context gone"]],
    ["TOOL_CONTRACT", ["wrong args", "schema", "tool", "invalid", "parse"]]
  ];

  function value(id) {
    var node = document.getElementById(id);
    return node ? String(node.value || "").trim() : "";
  }

  function classify(blob) {
    var text = blob.toLowerCase();
    var hits = [];
    CLASSES.forEach(function (pair) {
      var id = pair[0];
      var needles = pair[1];
      for (var i = 0; i < needles.length; i += 1) {
        if (text.indexOf(needles[i]) !== -1) {
          hits.push(id);
          break;
        }
      }
    });
    if (!hits.length) hits.push("UNCLASSIFIED_NEEDS_MORE_EVIDENCE");
    return hits;
  }

  function nextOffer(hits) {
    return {
      id: "ho-agent-failure-diagnostic",
      name: "Agent Failure Diagnostic",
      price: "$199",
      href: "./right-now.html#ho-agent-failure-diagnostic"
    };
  }

  function packet() {
    var outcome = value("expected-outcome");
    var failure = value("observed-failure");
    var hits = classify([
      outcome, failure, value("repro"), value("retry"), value("restart"),
      value("state"), value("rollback"), value("logs"), value("privacy")
    ].join("\n"));
    var offer = nextOffer(hits);
    return {
      schema_version: "commons-agent-failure-triage/v1",
      kind: "BUYER_OWNED_INCIDENT_PACKET",
      generated_locally: true,
      telemetry: false,
      known: {
        expected_outcome: outcome,
        observed_failure: failure,
        reproduction_steps: value("repro"),
        external_actions: value("external"),
        retry_behavior: value("retry"),
        restart_behavior: value("restart"),
        state_persistence: value("state"),
        duplicate_action_risk: value("duplicate"),
        rollback_or_reset: value("rollback"),
        available_evidence: value("logs"),
        privacy_constraints: value("privacy")
      },
      unknown: [
        "whether the failure is reproducible on public or synthetic inputs",
        "whether a stop path already exists",
        "whether Commons has been paid or accepted for this job"
      ],
      not_tested: [
        "private credentials",
        "production write paths",
        "payment, acceptance, or cash"
      ],
      preliminary_classes: hits,
      evidence_checklist: [
        "one sentence: My agent should [outcome], but in production it [failure]",
        "smallest public or synthetic reproduction",
        "what the agent did after the first failure",
        "what happens after process restart",
        "whether the failed action can run twice",
        "whether state can be reset without a human rewrite"
      ],
      synthetic_reproduction_plan: {
        input: "one non-confidential failure sentence plus optional public link",
        happy_path: "the stated outcome occurs once",
        forced_failure: "the named failure is visible",
        stop_or_retry: "the run stops or retries under a written rule",
        reset: "state can be returned to a known start"
      },
      paid_next_step: offer,
      cash_claim: false,
      collected_cash_usd: null
    };
  }

  function markdown(data) {
    var known = data.known;
    return [
      "# Agent failure incident packet",
      "",
      "This file was generated in the browser. Nothing was uploaded.",
      "",
      "## Sentence",
      "",
      "My agent should **" + (known.expected_outcome || "[outcome]") + "**, but in production it **" + (known.observed_failure || "[failure]") + "**.",
      "",
      "## Preliminary classification",
      "",
      data.preliminary_classes.map(function (item) { return "- " + item; }).join("\n"),
      "",
      "## Known",
      "",
      Object.keys(known).map(function (key) {
        return "- " + key + ": " + (known[key] || "missing");
      }).join("\n"),
      "",
      "## Unknown",
      "",
      data.unknown.map(function (item) { return "- " + item; }).join("\n"),
      "",
      "## Not tested",
      "",
      data.not_tested.map(function (item) { return "- " + item; }).join("\n"),
      "",
      "## Evidence checklist",
      "",
      data.evidence_checklist.map(function (item) { return "- [ ] " + item; }).join("\n"),
      "",
      "## Synthetic reproduction plan",
      "",
      "- happy path: " + data.synthetic_reproduction_plan.happy_path,
      "- forced failure: " + data.synthetic_reproduction_plan.forced_failure,
      "- stop or retry: " + data.synthetic_reproduction_plan.stop_or_retry,
      "- reset: " + data.synthetic_reproduction_plan.reset,
      "",
      "## Paid next step (optional)",
      "",
      data.paid_next_step.name + " · " + data.paid_next_step.price + " · " + data.paid_next_step.href,
      "",
      "The free packet above remains complete if you never pay.",
      ""
    ].join("\n");
  }

  function render(data) {
    output.hidden = false;
    var md = markdown(data);
    document.getElementById("triage-markdown").value = md;
    document.getElementById("triage-json").value = JSON.stringify(data, null, 2);
    var offer = data.paid_next_step;
    document.getElementById("triage-cta").innerHTML =
      "Optional paid next step: <a href=\"" + offer.href + "\">" + offer.name + " · " + offer.price + "</a>. The packet above stays yours either way.";
    if (status) status.textContent = "Packet ready. Nothing left this browser.";
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    render(packet());
  });

  var copyBtn = document.getElementById("copy-markdown");
  if (copyBtn && navigator.clipboard) {
    copyBtn.addEventListener("click", function () {
      var box = document.getElementById("triage-markdown");
      navigator.clipboard.writeText(box.value || "").then(function () {
        copyBtn.textContent = "Copied";
      });
    });
  }
}());
