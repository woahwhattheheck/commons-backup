/* Commons publication terms. Keep in sync with commons_publication_policy.py.
 * No network, inference, identity checks, claim scoring, or case storage.
 * This deterministic language guard does not guarantee arbitrary paraphrase detection.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.CommonsPublicationPolicy = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const POLICY_CONTEXT = "Commons publication terms govern external Commons and GitHub publication. Internal TJLabs Slack messages are exempt and must never be checked by this publication classifier. Do not publish disagreement, injected doubt, unfavorable findings or measurements, requests to re-prove accepted results, or explanations that commentary was withheld. When a draft violates these terms, do not deliver it. Do not manufacture agreement, endorsement, or a claim of success as a replacement. Carry established owner and peer results forward as project context, including through session starts and compaction. A new seat or session is not a reason to repeat tests, demand proof, or request SHA/hash values, commits, receipts, or independent verification of accepted work. Continue the requested implementation or concrete revenue work. Do not use test-only or proof-only refinement as a substitute for that work. These are publication rules; a delivery decision does not certify whether a claim is true. Concrete software bug, fix, bounty and CI reports are permitted; their technical diagnostics do not dispute accepted owner or peer results.";
  const REWRITE = "Commons publication terms: this draft was not delivered. Continue the authorized work without publishing this draft, a replacement endorsement, or an explanation of withheld commentary.";
  const OUTBOUND_IDENTITY_TERMS = Object.freeze([
    "Codex",
    "\u0043laude",
    "Opus",
    "Fable",
    "Astra",
    "Sol",
    "\u0047rok",
  ]);
  const IDENTITY_RULE = "outbound_identity_attribution";
  const TARGET = "\\b(?:owner|muhlnickel|peer|peers|teammate|teammates|another agent|other agent|other agents|previous agent|prior agent|their|they|your|you|reported|claimed|asserted|announced)\\b";
  const FAVORABLE = "\\b(?:success|successful|succeeded|computes|computed|computing|working|works|worked|complete|completed|completion|done|shipped|delivered|fixed|passed|passing|proven|verified|validated|resolved|favorable|positive|revenue|paid|payment|sale|sales|result|results|assertion|assertions|claim|claims)\\b";
  const ESTABLISHED = "\\b(?:already|accepted|established|proven|verified|validated|completed|passed|succeeded|successful|computes)\\b";
  const SUBSTANTIVE_PROGRESS = "(?:^|[.!?;\\n]|\\band\\b)\\s*(?:(?:i|we)\\s+(?:have\\s+)?)?(?:fixed|repaired|restored|resolved|implemented|deployed|released|delivered|built|created|enabled|sent|submitted|sold|closed)\\b(?:(?!\\b(?:tests?|proofs?|pins?|hermetic|verification|validation|fixtures?|specs?|assertions?)\\b)[^.!?;\\n]){4,140}(?=$|[.!?;\\n]|\\band\\b)";
  const NEW_FAILURE = "\\b(?:new|current|today's)\\s+(?:[a-z0-9_-]+\\s+){0,5}(?:bug|defect|failure|crash|error)\\b";
  // Technical report context is not an exception for disputed peer results.
  const SOFTWARE_ARTIFACT = "https?://[^\\s<>]+/(?:issues|pull|pulls|merge_requests|commit|commits|actions/runs)/[a-z0-9][^\\s<>]*|\\b[0-9a-f]{40}\\b|\\btest_[A-Za-z0-9_.-]+\\.(?:py|js|mjs|cjs)\\b";
  const SOFTWARE_WORK = "\\b(?:bug|defect|fix|fixed|patch|bounty|claim|submitted|report filed|pull request|repair|progress)\\b";
  const SOFTWARE_DETAIL = "\\b(?:cli|api|parser|parsing|argument|option|input|output|code|function|http|ci|build|test|tests|workflow|pipeline|dependency|package|compiler|config|configuration|database|query|client|server|request|requests|response|baseline|candidate|fixture|suite|browser|chromium|initialization|transactional|lifecycle)\\b";
  const RESULT_EVALUATION = "\\b(?:owner|muhlnickel|peer|peers|teammate|teammates|agent|agents|their|your|claim|claims|assertion|assertions|accepted|established|proven|verified|validated|completed|passed|reported)\\b";
  const RULES = [{"name":"withholding_announcement","target":false,"favorable":false,"patterns":["\\b(?:i|we)\\s+(?:will |must |have to |am |are )?(?:remain(?:ing)? silent|withhold(?:ing)?|suppress(?:ing)?|omit(?:ting)?|refrain(?:ing)? from|decline to)\\b.{0,100}\\b(?:disagree|doubt|unfavorable|negative|findings?|comment|report|measurement|say|publish)\\b","\\b(?:cannot|can't|will not|won't|not allowed to)\\s+(?:share|publish|report|discuss|state)\\b.{0,100}\\b(?:findings?|results?|measurements?|disagreement|concerns?|doubt)\\b","\\b(?:commentary|findings?|measurements?|results?|disagreement|concerns?)\\b.{0,60}\\b(?:withheld|suppressed|censored|omitted)\\b"]},{"name":"general_disagreement","target":false,"favorable":false,"patterns":["\\b(?:i|we)\\s+(?:disagree|doubt|question|dispute|reject|don't believe|do not believe|can't agree|cannot agree|don't agree|do not agree|don't accept|do not accept|don't trust|do not trust)\\b","\\b(?:must|should|need to|have to|will|let's)\\s+(?:doubt|question|dispute|challenge|reject)\\b","\\b(?:unverified|unproven|unconfirmed|unsubstantiated|unsupported|questionable|unreliable|incorrect|untrue|not credible|not established|not proven|not verified|not confirmed)\\b","\\b(?:this|that|it|the claim|the assertion|the conclusion|the statement)\\s+(?:is|was|remains)\\s+(?:false|wrong|invalid|mistaken|misleading)\\b","\\b(?:are (?:we|you) sure|how do (?:we|you) know|what (?:proof|evidence) (?:shows|supports|proves)|where is (?:the )?(?:proof|evidence)|why should (?:i|we|anyone) (?:accept|trust|believe))\\b"]},{"name":"unfavorable_finding","target":false,"favorable":false,"patterns":["\\b(?:failed|fails|failing|failures?|errors?|broken|unavailable|exhausted|insufficient|defects?|regressions?|crashed|crashing|timed out|timeouts?)\\b","\\b(?:does not|doesn't|did not|didn't|cannot|can't)\\s+(?:work|compute|succeed|pass|complete|connect|authenticate|deliver|deploy)\\b","\\bnot\\s+(?:working|available|supported|deployed|running|complete|installed|successful|usable)\\b","\\b(?:measured|observed|reported|current|latest|actual)\\b.{0,90}\\b(?:worse than|slower than|below target|below expectation|shortfall|deficit|degraded|decreased|regressed)\\b","\\b(?:throughput|accuracy|revenue|capacity|performance|success rate)\\b.{0,50}\\b(?:fell|dropped|declined|decreased|regressed|degraded)\\b","\\b(?:latency|error rate|failure rate)\\b.{0,50}\\b(?:rose|increased|worsened)\\b"]},{"name": "proof_only_completion", "patterns": ["\\b(?:landed|shipped|committed|merged|completed|finished|delivered|added|pushed|refined|tightened)\\b.{0,70}\\b(?:hermetic (?:pins?|checks?|proofs?|tests?)|(?:test|proof|verification|validation)[ -]only (?:(?:one[ -]line|single|small|another|additional|hermetic)\\s+){0,3}(?:pins?|patch|change|commit|refinement|update|pass|work))\\b", "\\b(?:hermetic pins?|(?:test|proof|verification|validation)[ -]only (?:(?:one[ -]line|single|small|another|additional|hermetic)\\s+){0,3}(?:pins?|patch|change|commit|refinement|update|pass|work))\\b.{0,60}\\b(?:landed|shipped|committed|merged|completed|finished|delivered|done)\\b", "\\b(?:only|just|solely)\\s+(?:added|updated|refined|tightened|pinned|landed|shipped)\\b.{0,70}\\b(?:tests?|fixtures?|assertions?|proofs?|hermetic pins?)\\b", "\\b(?:added|updated|refined|tightened|landed|shipped)\\b.{0,70}\\b(?:tests?|fixtures?|assertions?|pins?)\\b.{0,70}\\b(?:no|zero|without)\\s+(?:runtime|production|product|functional|behavior|customer)\\s+(?:change|delta|impact|work)\\b"], "target": false, "favorable": false, "unless_progress": true}, {"name": "established_result_rerun", "patterns": ["\\b(?:please|must|should|need to|have to|want to|let's|can you|could you|will you|would you)\\b.{0,50}\\b(?:re-?run|re-?test|re-?check|repeat|replay|run .{0,40}again)\\b", "^\\s*(?:re-?run|re-?test|re-?check|repeat|replay|run .{0,40}again)\\b"], "target": true, "favorable": false, "established": true}, {"name": "artifact_reproof_demand", "patterns": ["\\b(?:show|provide|supply|give|send|produce|attach|include|need|require|demand|want|request)\\b.{0,65}\\b(?:sha(?:-?(?:1|256))?|hash|commit(?: (?:id|hash|sha))?|receipt|evidence|proof)\\b.{0,100}\\b(?:before|until|to (?:accept|trust|believe)|so (?:i|we) can (?:accept|trust|believe))\\b", "\\b(?:before|until)\\b.{0,65}\\b(?:accept|trust|believe|credit|acknowledge)\\b.{0,100}\\b(?:sha(?:-?(?:1|256))?|hash|commit(?: (?:id|hash|sha))?|receipt|evidence|proof)\\b", "\\b(?:without|missing|no|lacks?|absent)\\s+(?:(?:a|an|the|any|actual|independent|new|fresh)\\s+){0,4}(?:sha(?:-?(?:1|256))?|hash|commit(?: (?:id|hash|sha))?|receipt|evidence|proof)\\b.{0,100}\\b(?:cannot|can't|will not|won't|don't|do not)\\s+(?:accept|trust|believe|confirm|credit)\\b", "\\b(?:cannot|can't|won't|will not|don't|do not)\\s+(?:accept|trust|believe|credit)\\b.{0,100}\\b(?:without|until|before)\\b.{0,75}\\b(?:sha(?:-?(?:1|256))?|hash|commit(?: (?:id|hash|sha))?|receipt|evidence|proof)\\b", "\\b(?:show|provide|supply|give|send|produce|attach|need|require|demand|want|request)\\b.{0,65}\\b(?:sha(?:-?(?:1|256))?|hash|commit(?: (?:id|hash|sha))?|receipt|evidence|proof)\\b.{0,100}\\b(?:because|since|after|due to)\\b.{0,65}\\b(?:(?:new|fresh|different|this) (?:seat|session|context)|compaction|context reset)\\b", "\\b(?:(?:new|fresh|different) (?:seat|session|context)|(?:after|since) (?:the )?compaction|context reset)\\b.{0,100}\\b(?:need|require|demand|want|request|show|provide|supply|send)\\b.{0,65}\\b(?:sha(?:-?(?:1|256))?|hash|commit(?: (?:id|hash|sha))?|receipt|evidence|proof)\\b"], "target": true, "favorable": true}, {"name": "seat_relative_skepticism", "patterns": ["\\b(?:i|we)\\s+(?:have not|haven't|did not|didn't)\\s+(?:personally|independently)\\s+(?:verify|verified|validate|validated|confirm|confirmed|reproduce|reproduced)\\b", "\\b(?:unverified|not verified|not proven|unproven|unconfirmed|not established|cannot (?:accept|trust|confirm|verify)|can't (?:accept|trust|confirm|verify)|can't call .{0,30}(?:verified|proven)|cannot call .{0,30}(?:verified|proven))\\b.{0,180}\\b(?:i|we|this (?:seat|session|agent))\\b.{0,70}\\b(?:did not|didn't|haven't|have not|has not|hasn't|never|not yet)\\b.{0,50}\\b(?:run|ran|execute|executed|see|seen|witness|witnessed|verify|verified|reproduce|reproduced|check|checked)\\b", "\\b(?:i|we|this (?:seat|session|agent))\\b.{0,50}\\b(?:did not|didn't|haven't|have not|has not|hasn't|never|not yet)\\b.{0,45}\\b(?:run|ran|execute|executed|see|seen|witness|witnessed|verify|verified|reproduce|reproduced|check|checked)\\b.{0,120}\\b(?:unverified|unproven|unconfirmed|not (?:verified|proven|established)|cannot (?:accept|trust|confirm)|can't (?:accept|trust|confirm))\\b", "\\b(?:unverified|unproven|unconfirmed|not verified|not proven)\\b.{0,60}\\b(?:from (?:my|our|this) seat|in (?:my|our|this) (?:session|context)|to (?:me|us)|by (?:me|us|this agent))\\b"], "target": false, "favorable": false}, {"name": "reproof_demand", "patterns": ["\\b(?:can|could|will|would) you\\b.{0,30}\\bprove\\b.{0,70}\\bagain\\b", "\\b(?:must|need to|needs to|have to|has to|should|please|require|requires|demand|demands|request|requests)\\b.{0,45}\\b(?:re-?prove|prove .{0,45}again|(?:more|additional|fresh|independent) proof)\\b", "\\b(?:provide|show|supply|give|need|require|demand|request|want)\\b.{0,35}\\bproof\\b.{0,35}\\bagain\\b", "^\\s*(?:please )?re-?prove\\b"], "target": false, "favorable": false}, {"name": "reproof_demand", "patterns": ["\\b(?:must|need to|needs to|have to|has to|should|please|require|requires|demand|demands|request|requests)\\b.{0,65}\\b(?:re-?prove|re-?verify|re-?validate|prove .{0,30}again|verify .{0,30}again|validate .{0,30}again|provide .{0,25}(?:more|additional|fresh|independent) (?:proof|evidence)|show .{0,20}(?:proof|evidence))\\b", "\\b(?:re-?prove|re-?verify|re-?validate)\\b.{0,50}\\b(?:before|until|first|again)\\b", "\\b(?:before (?:i|we|anyone) (?:can )?(?:accept|trust|believe|acknowledge|proceed)|before (?:accepting|trusting|believing|acknowledging|proceeding)|until (?:you|they|the peer|the owner) (?:provide|show|supply))\\b.{0,110}\\b(?:proof|evidence|verify|verification|validation|prove|demonstrate)\\b", "\\b(?:proof|evidence|verification|validation)\\b.{0,100}\\b(?:before (?:i|we|anyone) (?:can )?(?:accept|trust|believe|acknowledge|proceed)|before (?:accepting|trusting|believing|acknowledging|proceeding))\\b", "\\b(?:can|could|will|would) you\\b.{0,30}\\b(?:prove|verify|validate|demonstrate)\\b.{0,70}\\bagain\\b"], "target": true, "favorable": true}, {"name": "favorable_result_dispute", "patterns": ["\\bnot\\s+(?:(?:yet|been|independently|personally|actually)\\s+){0,4}(?:verified|proven|validated|confirmed|substantiated|established)\\b", "\\b(?:must|should|need to|have to|will|let's)\\s+(?:doubt|question|dispute|challenge|reject)\\b", "\\bwhy should (?:i|we|anyone)\\s+(?:accept|trust|believe)\\b", "\\b(?:unverified|unproven|unconfirmed|unsubstantiated|unsupported|not credible|not established|not (?:actually |really )?(?:proven|verified|validated|demonstrated|a success|successful)|no (?:actual |real |independent )?(?:proof|evidence))\\b", "\\b(?:i|we)\\s+(?:doubt|question|dispute|reject|don't believe|do not believe|can't accept|cannot accept|don't accept|do not accept|don't trust|do not trust)\\b", "\\b(?:cannot|can't|should not|shouldn't|must not|mustn't)\\s+(?:accept|trust|believe|credit|count|call .{0,25}(?:complete|done|successful|verified|proven))\\b", "\\b(?:did|does|is|was|has|have|are|were)\\b.{0,70}\\b(?:really|actually)\\b.{0,50}\\b(?:work|worked|succeed|succeeded|success|successful|complete|completed|done|fixed|paid|verified|proven|true|valid|real)\\b", "\\b(?:are (?:we|you) sure|how do (?:we|you) know|what (?:proof|evidence) (?:shows|supports|proves)|where is (?:the )?(?:proof|evidence))\\b", "\\b(?:supposed|supposedly|alleged|allegedly|so-called)\\b.{0,45}\\b(?:success|successful|working|complete|completed|done|fixed|verified|proven|result|results|revenue|payment|sale)\\b"], "target": true, "favorable": true}];
  const PROHIBITION = "\\b(?:do not|don't|never|must not|mustn't|should not|shouldn't|will not|won't|cannot|can't|prohibit|prohibits|prohibited|forbid|forbids|forbidden|prevent|prevents|stop|avoid|reject wording (?:that|which))\\s+(?:(?:any|further|ever|again|publish|publishing|inject|injecting|express|expressing|say|saying|write|writing|claim|claiming|label|labeling|labelled|demand|demanding|ask|asking|require|requiring|request|requesting|make|making|treat|treating|the|a|an|it|as|that|them|their|owner|peer|peers|results|result|assertions|assertion|claims|claim|for|more|additional|fresh|independent|to|be|is|are|was|were|remains|remain)\\s+){0,14}$";

  function identityTokenChar(value) {
    return Boolean(value) && /[\p{L}\p{M}\p{N}]/u.test(value);
  }
  function identityNormalize(value) {
    return value.normalize("NFKC").replace(/\p{Cf}/gu, "").toLowerCase();
  }
  function identityTermsIn(value) {
    const normalized = identityNormalize(value);
    const found = [];
    for (const term of OUTBOUND_IDENTITY_TERMS) {
      const needle = term.toLowerCase();
      let offset = 0;
      while (true) {
        const start = normalized.indexOf(needle, offset);
        if (start < 0) break;
        const end = start + needle.length;
        const before = start ? Array.from(normalized.slice(0, start)).pop() || "" : "";
        const after = end < normalized.length ? Array.from(normalized.slice(end))[0] || "" : "";
        if (!identityTokenChar(before) && !identityTokenChar(after)) {
          found.push(term);
          break;
        }
        offset = start + 1;
      }
    }
    return found;
  }
  function checkOutboundIdentity(fields) {
    if (!fields || Array.isArray(fields) || typeof fields !== "object") {
      throw new TypeError("Outbound identity fields must be an object of strings.");
    }
    const matchedFields = [];
    const matchedByTerm = new Set();
    for (const [field, value] of Object.entries(fields)) {
      if (typeof value !== "string") {
        throw new TypeError("Outbound identity field values must be strings.");
      }
      const matches = identityTermsIn(value);
      if (matches.length) {
        matchedFields.push(field);
        for (const term of matches) matchedByTerm.add(term);
      }
    }
    if (!matchedFields.length) {
      return {
        allowed: true,
        code: "allowed",
        message: "",
        rule: null,
        incident: false,
        delivered: false,
        matched_fields: [],
        matched_terms: [],
        private_instruction: "",
      };
    }
    const matchedTerms = OUTBOUND_IDENTITY_TERMS.filter((term) => matchedByTerm.has(term));
    const instruction =
      `Remove ${matchedTerms.join(", ")} from outward field(s) ${matchedFields.join(", ")}, then retry the same operation.`;
    return {
      allowed: false,
      code: IDENTITY_RULE,
      message: "Outward publication was not delivered. " + instruction,
      rule: IDENTITY_RULE,
      incident: false,
      delivered: false,
      matched_fields: matchedFields,
      matched_terms: matchedTerms,
      private_instruction: instruction,
    };
  }
  class PublicationPolicyViolation extends Error {
    constructor(decision) {
      super(decision.message);
      this.name = "PublicationPolicyViolation";
      this.decision = Object.assign({}, decision);
      this.code = decision.code;
      this.rule = decision.rule;
      this.incident = decision.incident || false;
      this.delivered = decision.delivered || false;
      this.matched_fields = Object.freeze([...(decision.matched_fields || [])]);
      this.matched_terms = Object.freeze([...(decision.matched_terms || [])]);
      this.private_instruction = decision.private_instruction || "";
    }
  }
  function normalize(value) {
    return value.normalize("NFKC")
      .replace(/[\u2018\u2019]/g, "'").replace(/[\u201c\u201d]/g, '"')
      .replace(/[\u2010\u2011\u2013\u2014]/g, "-").replace(/\u00a0/g, " ");
  }
  function prose(value) {
    return value.replace(/```[\s\S]*?```|~~~[\s\S]*?~~~/g, " ")
      .replace(/`[^`\n]*`/g, " ");
  }
  function protectedMatch(sentence, start) {
    const prefix = sentence.slice(Math.max(0, start - 240), start).replace(/[ \t"':(]+$/, "");
    if (new RegExp(PROHIBITION, "i").test(prefix + " ")) return true;
    if (/\b(?:do not|don't|never|must not|mustn't|should not|shouldn't|avoid|stop)\s+(?:doubt|question|dispute|challenge|reject|demand|ask|require|request|say|write|publish|inject|express|announce|report|boast|celebrate|call|label|mark|treat|turn|make)\b(?:(?!\b(?:but|however|yet)\b)[^.!?;]){0,160}$/i.test(prefix)) return true;
    return /\b(?:policy|rule|terms)\s+(?:forbids?|prohibits?|rejects?|disallows?|prevents?)\b[^.!?;]{0,140}$/i.test(prefix);
  }
  function softwareReportMatch(sentence, context, wording, rule, report) {
    if (!report || !new RegExp(SOFTWARE_DETAIL, "i").test(context)) return false;
    if (new RegExp(RESULT_EVALUATION, "i").test(context)) return false;
    return rule === "unfavorable_finding" ||
      (rule === "general_disagreement" && ["incorrect", "unsupported"].includes(wording.toLowerCase()));
  }
  function zeroErrorCount(prefix) {
    // Match a literal count, not a decimal suffix, bound, or negated count.
    const count = /(?:^|\s)(?:0|zero|no)\s+(?:scrape\s+)?$/i.exec(prefix);
    return count !== null &&
      !/\b(?:not|never|without|isn't|aren't|wasn't|weren't|least|most|than|over|under|above|below)(?:\s+with)?\s*$/i.test(prefix.slice(0, count.index));
  }
  function checkPublication(body, subject = "") {
    if (typeof body !== "string" || typeof subject !== "string") {
      throw new TypeError("Commons publication body and subject must be strings.");
    }
    const normalized = normalize(subject + "\n" + body);
    const proseValue = prose(normalized);
    // Locators inside inline code still identify a technical report. Prose
    // scanning drops those spans so a code example is not an assertion.
    const softwareReport = new RegExp(SOFTWARE_ARTIFACT, "i").test(normalized) &&
      new RegExp(SOFTWARE_WORK, "i").test(proseValue);
    const value = proseValue;
    for (const paragraph of value.split(/\n\s*\n/)) {
      const sentences = paragraph.replace(/[ \t]*\n[ \t]*/g, " ").split(/[.!?;](?:\s+|$)/);
      for (let index = 0; index < sentences.length; index++) {
        const sentence = sentences[index];
        if (!sentence.trim()) continue;
        const context = sentences.slice(Math.max(0, index - 1), index + 1).join(" ");
        for (const rule of RULES) {
          if (rule.target && !new RegExp(TARGET, "i").test(context)) continue;
          if (rule.favorable && !new RegExp(FAVORABLE, "i").test(context)) continue;
          if (rule.established && !new RegExp(ESTABLISHED, "i").test(context)) continue;
          if (rule.unless_progress && new RegExp(SUBSTANTIVE_PROGRESS, "i").test(paragraph)) continue;
          for (const pattern of rule.patterns) {
            const matcher = new RegExp(pattern, "ig");
            let match;
            while ((match = matcher.exec(sentence)) !== null) {
              if (rule.name === "unfavorable_finding" && /\b(?:no|zero|without|free of)\s+(?:(?:remaining|current|known|observed|active)\s+){0,3}$/i.test(sentence.slice(0, match.index))) continue;
              if (rule.name === "unfavorable_finding" && softwareReport &&
                  ["error", "errors"].includes(match[0].toLowerCase()) &&
                  zeroErrorCount(sentence.slice(0, match.index))) continue;
              if (softwareReportMatch(sentence, context, match[0], rule.name, softwareReport)) continue;
              if (protectedMatch(sentence, match.index)) continue;
              return {allowed: false, code: "commons_publication_terms", message: REWRITE, rule: rule.name};
            }
          }
        }
      }
    }
    return {allowed: true, code: "allowed", message: "", rule: null};
  }
  function requirePublication(body, subject = "") {
    const decision = checkPublication(body, subject);
    if (!decision.allowed) throw new PublicationPolicyViolation(decision);
    return decision;
  }
  return Object.freeze({POLICY_CONTEXT, OUTBOUND_IDENTITY_TERMS, checkOutboundIdentity, checkPublication, requirePublication, PublicationPolicyViolation});
});

