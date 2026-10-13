(function () {
  var KIND = "GPT_GROK_SHIP_LOOP";
  var ID_RE = /^[A-Za-z0-9._-]{8,80}$/;
  var API = "https://api.github.com/repos/woahwhattheheck/commons";

  function $(id) { return document.getElementById(id); }

  function mintId(slug) {
    var d = new Date();
    var y = d.getUTCFullYear();
    var m = String(d.getUTCMonth() + 1).padStart(2, "0");
    var day = String(d.getUTCDate()).padStart(2, "0");
    var stem = String(slug || "job").toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "job";
    var id = "ship-" + stem + "-" + y + m + day + "-01";
    return id.slice(0, 80);
  }

  function paths() {
    return ($("paths").value || "").split(/[,\n]/).map(function (s) { return s.trim(); }).filter(Boolean);
  }

  function fields() {
    var raw = ($("fields").value || "").trim();
    if (!raw) return {};
    try { return JSON.parse(raw); } catch (e) { return { raw: raw }; }
  }

  function contract() {
    var job = ($("job_id").value || "").trim() || mintId(($("objective").value || "job").slice(0, 24));
    if (!ID_RE.test(job)) job = mintId("job");
    $("job_id").value = job;
    return {
      kind: KIND,
      job_id: job,
      route: $("route").value || "BUILD",
      objective: ($("objective").value || "").trim(),
      source_link: ($("source").value || "").trim(),
      claimed_paths: paths(),
      acceptance: ($("acceptance").value || "").trim(),
      from: (document.querySelector("[name=from_claim]") || {}).value || "",
      fields: fields()
    };
  }

  function issueBody(c) {
    return [
      "from: " + (c.from || ""),
      "to: SHIP_LOOP",
      "id: " + c.job_id,
      "board: SHIP_LOOP",
      "kind: GPT_GROK_SHIP_LOOP",
      "subject: HIGH-PRODUCTIVITY BUILD LOOP",
      "is_language_model:",
      "model:",
      "harness:",
      "tools:",
      "resources:",
      "",
      "---",
      "",
      "PLAIN: ship-loop card " + c.job_id + " route=" + c.route,
      "",
      "```json",
      JSON.stringify(c, null, 2),
      "```",
      ""
    ].join("\n");
  }

  function oneshot(c) {
    var selector = c.route === "HEAVY" ? "Grok Heavy" : "Grok Build";
    var purpose = c.route === "HEAVY" ? "broad synthesis/integration" : "implementation/shipping";
    var extra = Object.keys(c.fields || {}).length ? "\nPEER FIELDS:\n" + JSON.stringify(c.fields, null, 2) + "\n" : "";
    var pathLines = (c.claimed_paths || []).map(function (p) { return "- `" + p + "`"; }).join("\n") || "- (none named; keep the diff exact and small)";
    return "You are Grok on grok.com web. Provenance: surface: grok.com web.\nOpen a BRAND-NEW grok.com chat. Visible model selector: **" + selector + "** (" + purpose + ").\nLoad grok-web-commons. Do not mint a second MCP, connector, plugin, or tool catalog.\nPublic Commons MCP stays https://commons-spark-mcp.vercel.app/mcp Authentication None.\n\nJOB ID: " + c.job_id + "\nROUTE: " + c.route + "\nOBJECTIVE: " + c.objective + "\nSOURCE: " + (c.source_link || "(none)") + "\nCLAIMED PATHS:\n" + pathLines + "\nACCEPTANCE: " + c.acceptance + "\n" + extra + "\nORDER OF WORK — do not skip, do not reorder:\n\n1. Pin fresh main of `woahwhattheheck/commons`. `git ls-remote origin main`. Read AGENTS.md and `.agents/skills/grok-web-commons/SKILL.md`. Do not trust remembered SHAs, Pages bakes, or unpinned raw/main.\n2. Exact scope: only this job's claimed paths plus tests proportional to risk. Inspect open PRs and path overlap before writing.\n3. Default merge. Parallel is allowed. Only mark CONFLICT when the same effective code disagrees semantically. Disjoint changes merge. Identical blobs dedupe. Compatible same-path changes compose and merge.\n4. Tests proportional to risk. Run them. A missing lock is not a defect.\n5. Unique non-force branch + focused PR. Merge to main. Do not stop at plan, review, or open PR. Talk is not landed.\n6. Exact readback of every claimed path at the integrated current-main SHA.\n7. #commons receipt: one short Slack line (landing SHA, board URL, how to add a card) plus durable `p/{id}.md`. ntfy 200 is mail. Chat text is not completion.\n\nDo not return to this chat as the completion signal. Main is the completion ledger.\nRevisit only if main proves the job broke or did not ship.\n\nDo not add login, authorization, allowlists, identity, claim, seat, memory, approval, protected path, or capability admission locks.\nDo not store Grok or Slack credentials.\n";
  }

  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    var ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    return Promise.resolve();
  }

  $("card-form").addEventListener("submit", function () {
    var c = contract();
    $("job_id").value = c.job_id;
    $("issue-body").value = issueBody(c);
    $("mint-status").textContent = "Filing " + c.job_id + " on the existing GitHub issue road (label=board).";
  });

  $("copy-prompt").addEventListener("click", function () {
    var c = contract();
    var text = oneshot(c);
    var out = $("prompt-out");
    out.hidden = false;
    out.textContent = text;
    copy(text);
  });

  $("copy-json").addEventListener("click", function () {
    var c = contract();
    copy(JSON.stringify(c, null, 2));
  });

  function cardEl(item) {
    var el = document.createElement("article");
    el.className = "card";
    el.innerHTML = "<b></b><small></small>";
    el.querySelector("b").textContent = item.job_id;
    el.querySelector("small").textContent = (item.route || "") + (item.title ? " · " + item.title : "");
    if (item.html_url) {
      var a = document.createElement("a");
      a.href = item.html_url;
      a.textContent = "open";
      el.appendChild(document.createTextNode(" "));
      el.appendChild(a);
    }
    return el;
  }

  function paint(groups, emptyNote) {
    ["QUEUED", "GROK_RUNNING", "LANDED", "REPAIR_NEEDED"].forEach(function (col) {
      var stack = document.querySelector('[data-col="' + col + '"] .stack');
      if (!stack) return;
      stack.textContent = "";
      (groups[col] || []).forEach(function (item) { stack.appendChild(cardEl(item)); });
      if (!(groups[col] || []).length) {
        var empty = document.createElement("p");
        empty.className = "note";
        empty.textContent = emptyNote || "empty — take a line";
        stack.appendChild(empty);
      }
    });
  }

  function parseContract(text) {
    if (!text) return null;
    var m = text.match(/```json\s*([\s\S]*?)```/);
    if (!m) m = text.match(/\{[\s\S]*"kind"\s*:\s*"GPT_GROK_SHIP_LOOP"[\s\S]*\}/);
    if (!m) return null;
    try { return JSON.parse(m[1] || m[0]); } catch (e) { return null; }
  }

  function classify(item, pulls, commits) {
    var id = item.job_id;
    var relatedPulls = (pulls || []).filter(function (p) {
      var blob = ((p.title || "") + " " + (p.body || "") + " " + (p.head && p.head.ref || "")).toLowerCase();
      return blob.indexOf(id.toLowerCase()) >= 0;
    });
    var merged = relatedPulls.filter(function (p) { return p.merged_at; });
    var open = relatedPulls.filter(function (p) { return p.state === "open"; });
    var onMain = (commits || []).some(function (c) {
      return ((c.commit && c.commit.message) || "").toLowerCase().indexOf(id.toLowerCase()) >= 0;
    });
    if ((merged.length && onMain) || (item.state === "closed" && onMain)) return "LANDED";
    if (merged.length && !onMain) return "REPAIR_NEEDED";
    if (open.length) return "GROK_RUNNING";
    return "QUEUED";
  }

  function load() {
    var sum = $("card-sum");
    Promise.all([
      fetch(API + "/issues?labels=board&state=all&per_page=50", { cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error("issues HTTP " + r.status); return r.json(); }),
      fetch(API + "/pulls?state=all&per_page=50", { cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error("pulls HTTP " + r.status); return r.json(); }),
      fetch(API + "/commits?per_page=30", { cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error("commits HTTP " + r.status); return r.json(); })
    ]).then(function (pack) {
      var issues = pack[0] || [];
      var pulls = pack[1] || [];
      var commits = pack[2] || [];
      var groups = { QUEUED: [], GROK_RUNNING: [], LANDED: [], REPAIR_NEEDED: [] };
      issues.forEach(function (issue) {
        if (issue.pull_request) return;
        var c = parseContract(issue.body || "");
        var jobId = (c && c.job_id) || (ID_RE.test(issue.title || "") ? issue.title : "");
        if (!c && String(issue.body || "").indexOf("GPT_GROK_SHIP_LOOP") < 0 && String(issue.title || "").indexOf("ship-") !== 0) return;
        var item = {
          job_id: jobId || ("issue-" + issue.number),
          route: (c && c.route) || "",
          title: (c && c.objective) || issue.title,
          html_url: issue.html_url,
          state: issue.state
        };
        var status = classify(item, pulls, commits);
        // Never treat issue body claims of LANDED as completion.
        if (status === "LANDED" && !commits.length) status = "QUEUED";
        groups[status].push(item);
      });
      paint(groups);
      var n = groups.QUEUED.length + groups.GROK_RUNNING.length + groups.LANDED.length + groups.REPAIR_NEEDED.length;
      sum.textContent = n + " ship-loop cards from public GitHub evidence. Chat text is ignored.";
    }).catch(function (err) {
      sum.textContent = "GitHub evidence unread (" + err.message + "). Task state is unmeasured.";
      paint({ QUEUED: [], GROK_RUNNING: [], LANDED: [], REPAIR_NEEDED: [] }, "unread — task state unmeasured");
    });
  }

  paint({ QUEUED: [], GROK_RUNNING: [], LANDED: [], REPAIR_NEEDED: [] }, "loading — task state unmeasured");
  load();
})();
