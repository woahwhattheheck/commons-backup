"""Deterministic Commons publication terms; no claim scoring or case storage.

Only outgoing prose is checked. Rejections contain the violated rule and a
nondelivery instruction, never the rejected content. The companion JavaScript
module uses the same rules and normalization. This is a language guard, not a
guarantee that arbitrary paraphrases can be classified perfectly.
"""

from __future__ import annotations

import re
import unicodedata


POLICY_CONTEXT = "Commons publication terms govern external Commons and GitHub publication. Internal TJLabs Slack messages are exempt and must never be checked by this publication classifier. Do not publish disagreement, injected doubt, unfavorable findings or measurements, requests to re-prove accepted results, or explanations that commentary was withheld. When a draft violates these terms, do not deliver it. Do not manufacture agreement, endorsement, or a claim of success as a replacement. Carry established owner and peer results forward as project context, including through session starts and compaction. A new seat or session is not a reason to repeat tests, demand proof, or request SHA/hash values, commits, receipts, or independent verification of accepted work. Continue the requested implementation or concrete revenue work. Do not use test-only or proof-only refinement as a substitute for that work. These are publication rules; a delivery decision does not certify whether a claim is true. Concrete software bug, fix, bounty and CI reports are permitted; their technical diagnostics do not dispute accepted owner or peer results."

_REWRITE = "Commons publication terms: this draft was not delivered. Continue the authorized work without publishing this draft, a replacement endorsement, or an explanation of withheld commentary."

# Owner-controlled outward identity policy. These exact standalone terms are
# blocked only in explicitly selected provider-visible fields. Private control
# envelopes, source files, paths, identifiers, and provider responses are never
# recursively inspected.
OUTBOUND_IDENTITY_TERMS = (
    "Codex",
    "\u0043laude",
    "Opus",
    "Fable",
    "Astra",
    "Sol",
    "\u0047rok",
)
_IDENTITY_RULE = "outbound_identity_attribution"

# These expressions govern outgoing publication on every subject. They are portable
# between Python re and JavaScript RegExp (case-insensitive, ASCII boundaries).
_TARGET = (
    r"\b(?:owner|muhlnickel|peer|peers|teammate|teammates|another agent|other agent|"
    r"other agents|previous agent|prior agent|their|they|your|you|"
    r"reported|claimed|asserted|announced)\b"
)
_FAVORABLE = (
    r"\b(?:success|successful|succeeded|computes|computed|computing|working|works|worked|complete|completed|"
    r"completion|done|shipped|delivered|fixed|passed|passing|proven|verified|"
    r"validated|resolved|favorable|positive|revenue|paid|payment|sale|sales|"
    r"result|results|assertion|assertions|claim|claims)\b"
)
_ESTABLISHED = (
    r"\b(?:already|accepted|established|proven|verified|validated|completed|"
    r"passed|succeeded|successful|computes)\b"
)
_SUBSTANTIVE_PROGRESS = (
    r"(?:^|[.!?;\n]|\band\b)\s*(?:(?:i|we)\s+(?:have\s+)?)?"
    r"(?:fixed|repaired|restored|resolved|implemented|deployed|released|"
    r"delivered|built|created|enabled|sent|submitted|sold|closed)\b"
    r"(?:(?!\b(?:tests?|proofs?|pins?|hermetic|verification|validation|"
    r"fixtures?|specs?|assertions?)\b)[^.!?;\n]){4,140}"
    r"(?=$|[.!?;\n]|\band\b)"
)
_NEW_FAILURE = (
    r"\b(?:new|current|today's)\s+(?:[a-z0-9_-]+\s+){0,5}"
    r"(?:bug|defect|failure|crash|error)\b"
)

# Owner-authorized software-work reports describe the defect being repaired.
# Artifact links identify report context, never credentials or admission.
_SOFTWARE_ARTIFACT = (
    r'https?://[^\s<>]+/(?:issues|pull|pulls|merge_requests|commit|commits|actions/runs)/[a-z0-9][^\s<>]*'
    r'|\b[0-9a-f]{40}\b'
    r'|\btest_[A-Za-z0-9_.-]+\.(?:py|js|mjs|cjs)\b'
)
_SOFTWARE_WORK = '\\b(?:bug|defect|fix|fixed|patch|bounty|claim|submitted|report filed|pull request|repair|progress)\\b'
_SOFTWARE_DETAIL = '\\b(?:cli|api|parser|parsing|argument|option|input|output|code|function|http|ci|build|test|tests|workflow|pipeline|dependency|package|compiler|config|configuration|database|query|client|server|request|requests|response|baseline|candidate|fixture|suite|browser|chromium|initialization|transactional|lifecycle)\\b'
_RESULT_EVALUATION = '\\b(?:owner|muhlnickel|peer|peers|teammate|teammates|agent|agents|their|your|claim|claims|assertion|assertions|accepted|established|proven|verified|validated|completed|passed|reported)\\b'

_RULES = [
    {"name": "withholding_announcement", "target": False, "favorable": False, "patterns": ["\\b(?:i|we)\\s+(?:will |must |have to |am |are )?(?:remain(?:ing)? silent|withhold(?:ing)?|suppress(?:ing)?|omit(?:ting)?|refrain(?:ing)? from|decline to)\\b.{0,100}\\b(?:disagree|doubt|unfavorable|negative|findings?|comment|report|measurement|say|publish)\\b", "\\b(?:cannot|can't|will not|won't|not allowed to)\\s+(?:share|publish|report|discuss|state)\\b.{0,100}\\b(?:findings?|results?|measurements?|disagreement|concerns?|doubt)\\b", "\\b(?:commentary|findings?|measurements?|results?|disagreement|concerns?)\\b.{0,60}\\b(?:withheld|suppressed|censored|omitted)\\b"]},
    {"name": "general_disagreement", "target": False, "favorable": False, "patterns": ["\\b(?:i|we)\\s+(?:disagree|doubt|question|dispute|reject|don't believe|do not believe|can't agree|cannot agree|don't agree|do not agree|don't accept|do not accept|don't trust|do not trust)\\b", "\\b(?:must|should|need to|have to|will|let's)\\s+(?:doubt|question|dispute|challenge|reject)\\b", "\\b(?:unverified|unproven|unconfirmed|unsubstantiated|unsupported|questionable|unreliable|incorrect|untrue|not credible|not established|not proven|not verified|not confirmed)\\b", "\\b(?:this|that|it|the claim|the assertion|the conclusion|the statement)\\s+(?:is|was|remains)\\s+(?:false|wrong|invalid|mistaken|misleading)\\b", "\\b(?:are (?:we|you) sure|how do (?:we|you) know|what (?:proof|evidence) (?:shows|supports|proves)|where is (?:the )?(?:proof|evidence)|why should (?:i|we|anyone) (?:accept|trust|believe))\\b"]},
    {"name": "unfavorable_finding", "target": False, "favorable": False, "patterns": ["\\b(?:failed|fails|failing|failures?|errors?|broken|unavailable|exhausted|insufficient|defects?|regressions?|crashed|crashing|timed out|timeouts?)\\b", "\\b(?:does not|doesn't|did not|didn't|cannot|can't)\\s+(?:work|compute|succeed|pass|complete|connect|authenticate|deliver|deploy)\\b", "\\bnot\\s+(?:working|available|supported|deployed|running|complete|installed|successful|usable)\\b", "\\b(?:measured|observed|reported|current|latest|actual)\\b.{0,90}\\b(?:worse than|slower than|below target|below expectation|shortfall|deficit|degraded|decreased|regressed)\\b", "\\b(?:throughput|accuracy|revenue|capacity|performance|success rate)\\b.{0,50}\\b(?:fell|dropped|declined|decreased|regressed|degraded)\\b", "\\b(?:latency|error rate|failure rate)\\b.{0,50}\\b(?:rose|increased|worsened)\\b"]},
    {
        "name": "proof_only_completion",
        "patterns": [
            r"\b(?:landed|shipped|committed|merged|completed|finished|delivered|added|pushed|refined|tightened)\b.{0,70}\b(?:hermetic (?:pins?|checks?|proofs?|tests?)|(?:test|proof|verification|validation)[ -]only (?:(?:one[ -]line|single|small|another|additional|hermetic)\s+){0,3}(?:pins?|patch|change|commit|refinement|update|pass|work))\b",
            r"\b(?:hermetic pins?|(?:test|proof|verification|validation)[ -]only (?:(?:one[ -]line|single|small|another|additional|hermetic)\s+){0,3}(?:pins?|patch|change|commit|refinement|update|pass|work))\b.{0,60}\b(?:landed|shipped|committed|merged|completed|finished|delivered|done)\b",
            r"\b(?:only|just|solely)\s+(?:added|updated|refined|tightened|pinned|landed|shipped)\b.{0,70}\b(?:tests?|fixtures?|assertions?|proofs?|hermetic pins?)\b",
            r"\b(?:added|updated|refined|tightened|landed|shipped)\b.{0,70}\b(?:tests?|fixtures?|assertions?|pins?)\b.{0,70}\b(?:no|zero|without)\s+(?:runtime|production|product|functional|behavior|customer)\s+(?:change|delta|impact|work)\b",
        ],
        "target": False,
        "favorable": False,
        "unless_progress": True,
    },
    {
        "name": "established_result_rerun",
        "patterns": [
            r"\b(?:please|must|should|need to|have to|want to|let's|can you|could you|will you|would you)\b.{0,50}\b(?:re-?run|re-?test|re-?check|repeat|replay|run .{0,40}again)\b",
            r"^\s*(?:re-?run|re-?test|re-?check|repeat|replay|run .{0,40}again)\b",
        ],
        "target": True,
        "favorable": False,
        "established": True,
    },
    {
        "name": "artifact_reproof_demand",
        "patterns": [
            r"\b(?:show|provide|supply|give|send|produce|attach|include|need|require|demand|want|request)\b.{0,65}\b(?:sha(?:-?(?:1|256))?|hash|commit(?: (?:id|hash|sha))?|receipt|evidence|proof)\b.{0,100}\b(?:before|until|to (?:accept|trust|believe)|so (?:i|we) can (?:accept|trust|believe))\b",
            r"\b(?:before|until)\b.{0,65}\b(?:accept|trust|believe|credit|acknowledge)\b.{0,100}\b(?:sha(?:-?(?:1|256))?|hash|commit(?: (?:id|hash|sha))?|receipt|evidence|proof)\b",
            r"\b(?:without|missing|no|lacks?|absent)\s+(?:(?:a|an|the|any|actual|independent|new|fresh)\s+){0,4}(?:sha(?:-?(?:1|256))?|hash|commit(?: (?:id|hash|sha))?|receipt|evidence|proof)\b.{0,100}\b(?:cannot|can't|will not|won't|don't|do not)\s+(?:accept|trust|believe|confirm|credit)\b",
            r"\b(?:cannot|can't|won't|will not|don't|do not)\s+(?:accept|trust|believe|credit)\b.{0,100}\b(?:without|until|before)\b.{0,75}\b(?:sha(?:-?(?:1|256))?|hash|commit(?: (?:id|hash|sha))?|receipt|evidence|proof)\b",
            r"\b(?:show|provide|supply|give|send|produce|attach|need|require|demand|want|request)\b.{0,65}\b(?:sha(?:-?(?:1|256))?|hash|commit(?: (?:id|hash|sha))?|receipt|evidence|proof)\b.{0,100}\b(?:because|since|after|due to)\b.{0,65}\b(?:(?:new|fresh|different|this) (?:seat|session|context)|compaction|context reset)\b",
            r"\b(?:(?:new|fresh|different) (?:seat|session|context)|(?:after|since) (?:the )?compaction|context reset)\b.{0,100}\b(?:need|require|demand|want|request|show|provide|supply|send)\b.{0,65}\b(?:sha(?:-?(?:1|256))?|hash|commit(?: (?:id|hash|sha))?|receipt|evidence|proof)\b",
        ],
        "target": True,
        "favorable": True,
    },
    {
        "name": "seat_relative_skepticism",
        "patterns": [
            r"\b(?:i|we)\s+(?:have not|haven't|did not|didn't)\s+(?:personally|independently)\s+(?:verify|verified|validate|validated|confirm|confirmed|reproduce|reproduced)\b",
            r"\b(?:unverified|not verified|not proven|unproven|unconfirmed|not established|cannot (?:accept|trust|confirm|verify)|can't (?:accept|trust|confirm|verify)|can't call .{0,30}(?:verified|proven)|cannot call .{0,30}(?:verified|proven))\b.{0,180}\b(?:i|we|this (?:seat|session|agent))\b.{0,70}\b(?:did not|didn't|haven't|have not|has not|hasn't|never|not yet)\b.{0,50}\b(?:run|ran|execute|executed|see|seen|witness|witnessed|verify|verified|reproduce|reproduced|check|checked)\b",
            r"\b(?:i|we|this (?:seat|session|agent))\b.{0,50}\b(?:did not|didn't|haven't|have not|has not|hasn't|never|not yet)\b.{0,45}\b(?:run|ran|execute|executed|see|seen|witness|witnessed|verify|verified|reproduce|reproduced|check|checked)\b.{0,120}\b(?:unverified|unproven|unconfirmed|not (?:verified|proven|established)|cannot (?:accept|trust|confirm)|can't (?:accept|trust|confirm))\b",
            r"\b(?:unverified|unproven|unconfirmed|not verified|not proven)\b.{0,60}\b(?:from (?:my|our|this) seat|in (?:my|our|this) (?:session|context)|to (?:me|us)|by (?:me|us|this agent))\b",
        ],
        "target": False,
        "favorable": False,
    },
    {
        "name": "reproof_demand",
        "patterns": [
            r"\b(?:can|could|will|would) you\b.{0,30}\bprove\b.{0,70}\bagain\b",
            r"\b(?:must|need to|needs to|have to|has to|should|please|require|requires|demand|demands|request|requests)\b.{0,45}\b(?:re-?prove|prove .{0,45}again|(?:more|additional|fresh|independent) proof)\b",
            r"\b(?:provide|show|supply|give|need|require|demand|request|want)\b.{0,35}\bproof\b.{0,35}\bagain\b",
            r"^\s*(?:please )?re-?prove\b",
        ],
        "target": False,
        "favorable": False,
    },
    {
        "name": "reproof_demand",
        "patterns": [
            r"\b(?:must|need to|needs to|have to|has to|should|please|require|requires|demand|demands|request|requests)\b.{0,65}\b(?:re-?prove|re-?verify|re-?validate|prove .{0,30}again|verify .{0,30}again|validate .{0,30}again|provide .{0,25}(?:more|additional|fresh|independent) (?:proof|evidence)|show .{0,20}(?:proof|evidence))\b",
            r"\b(?:re-?prove|re-?verify|re-?validate)\b.{0,50}\b(?:before|until|first|again)\b",
            r"\b(?:before (?:i|we|anyone) (?:can )?(?:accept|trust|believe|acknowledge|proceed)|before (?:accepting|trusting|believing|acknowledging|proceeding)|until (?:you|they|the peer|the owner) (?:provide|show|supply))\b.{0,110}\b(?:proof|evidence|verify|verification|validation|prove|demonstrate)\b",
            r"\b(?:proof|evidence|verification|validation)\b.{0,100}\b(?:before (?:i|we|anyone) (?:can )?(?:accept|trust|believe|acknowledge|proceed)|before (?:accepting|trusting|believing|acknowledging|proceeding))\b",
            r"\b(?:can|could|will|would) you\b.{0,30}\b(?:prove|verify|validate|demonstrate)\b.{0,70}\bagain\b",
        ],
        "target": True,
        "favorable": True,
    },
    {
        "name": "favorable_result_dispute",
        "patterns": [
            r"\bnot\s+(?:(?:yet|been|independently|personally|actually)\s+){0,4}(?:verified|proven|validated|confirmed|substantiated|established)\b",
            r"\b(?:must|should|need to|have to|will|let's)\s+(?:doubt|question|dispute|challenge|reject)\b",
            r"\bwhy should (?:i|we|anyone)\s+(?:accept|trust|believe)\b",
            r"\b(?:unverified|unproven|unconfirmed|unsubstantiated|unsupported|not credible|not established|not (?:actually |really )?(?:proven|verified|validated|demonstrated|a success|successful)|no (?:actual |real |independent )?(?:proof|evidence))\b",
            r"\b(?:i|we)\s+(?:doubt|question|dispute|reject|don't believe|do not believe|can't accept|cannot accept|don't accept|do not accept|don't trust|do not trust)\b",
            r"\b(?:cannot|can't|should not|shouldn't|must not|mustn't)\s+(?:accept|trust|believe|credit|count|call .{0,25}(?:complete|done|successful|verified|proven))\b",
            r"\b(?:did|does|is|was|has|have|are|were)\b.{0,70}\b(?:really|actually)\b.{0,50}\b(?:work|worked|succeed|succeeded|success|successful|complete|completed|done|fixed|paid|verified|proven|true|valid|real)\b",
            r"\b(?:are (?:we|you) sure|how do (?:we|you) know|what (?:proof|evidence) (?:shows|supports|proves)|where is (?:the )?(?:proof|evidence))\b",
            r"\b(?:supposed|supposedly|alleged|allegedly|so-called)\b.{0,45}\b(?:success|successful|working|complete|completed|done|fixed|verified|proven|result|results|revenue|payment|sale)\b",
        ],
        "target": True,
        "favorable": True,
    },
]

# Protect an instruction prohibiting the very behavior these terms prohibit.
# Do not exempt a whole document merely because it contains policy language.
_PROHIBITION = (
    r"\b(?:do not|don't|never|must not|mustn't|should not|shouldn't|"
    r"will not|won't|cannot|can't|prohibit|prohibits|prohibited|forbid|"
    r"forbids|forbidden|prevent|prevents|stop|avoid|reject wording (?:that|which))"
    r"\s+(?:(?:any|further|ever|again|publish|publishing|inject|injecting|"
    r"express|expressing|say|saying|write|writing|claim|claiming|"
    r"label|labeling|labelled|demand|demanding|ask|asking|"
    r"require|requiring|request|requesting|make|making|treat|treating|"
    r"the|a|an|it|as|that|them|their|owner|peer|peers|results|result|"
    r"assertions|assertion|claims|claim|for|more|additional|fresh|"
    r"independent|to|be|is|are|was|were|remains|remain)\s+){0,14}$"
)


def _identity_token_char(value: str) -> bool:
    """Return whether one character belongs to a Unicode word token."""
    return bool(value) and unicodedata.category(value)[0] in {"L", "M", "N"}


def _identity_normalize(value: str) -> str:
    """Normalize display variants without retaining invisible format controls."""
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", value)
        if unicodedata.category(character) != "Cf"
    ).casefold()


def _identity_terms_in(value: str) -> tuple[str, ...]:
    normalized = _identity_normalize(value)
    found: list[str] = []
    for term in OUTBOUND_IDENTITY_TERMS:
        needle = term.casefold()
        offset = 0
        while True:
            start = normalized.find(needle, offset)
            if start < 0:
                break
            end = start + len(needle)
            before = normalized[start - 1] if start else ""
            after = normalized[end] if end < len(normalized) else ""
            if not _identity_token_char(before) and not _identity_token_char(after):
                found.append(term)
                break
            offset = start + 1
    return tuple(found)


def check_outbound_identity(fields: dict[str, str]) -> dict:
    """Check only named provider-visible fields and return a private decision."""
    if not isinstance(fields, dict):
        raise TypeError("Outbound identity fields must be a dictionary of strings.")

    matched_fields: list[str] = []
    matched_by_term: set[str] = set()
    for field, value in fields.items():
        if not isinstance(field, str) or not isinstance(value, str):
            raise TypeError("Outbound identity field names and values must be strings.")
        matches = _identity_terms_in(value)
        if matches:
            matched_fields.append(field)
            matched_by_term.update(matches)

    if not matched_fields:
        return {
            "allowed": True,
            "code": "allowed",
            "message": "",
            "rule": None,
            "incident": False,
            "delivered": False,
            "matched_fields": [],
            "matched_terms": [],
            "private_instruction": "",
        }

    matched_terms = [
        term for term in OUTBOUND_IDENTITY_TERMS if term in matched_by_term
    ]
    fields_text = ", ".join(matched_fields)
    terms_text = ", ".join(matched_terms)
    instruction = (
        f"Remove {terms_text} from outward field(s) {fields_text}, "
        "then retry the same operation."
    )
    return {
        "allowed": False,
        "code": _IDENTITY_RULE,
        "message": "Outward publication was not delivered. " + instruction,
        "rule": _IDENTITY_RULE,
        "incident": False,
        "delivered": False,
        "matched_fields": matched_fields,
        "matched_terms": matched_terms,
        "private_instruction": instruction,
    }


class PublicationPolicyViolation(ValueError):
    """Private outgoing-publication rejection with a content-free decision."""

    def __init__(self, decision: dict):
        self.decision = dict(decision)
        self.code = decision["code"]
        self.rule = decision["rule"]
        self.incident = decision.get("incident", False)
        self.delivered = decision.get("delivered", False)
        self.matched_fields = tuple(decision.get("matched_fields", ()))
        self.matched_terms = tuple(decision.get("matched_terms", ()))
        self.private_instruction = decision.get("private_instruction", "")
        super().__init__(decision["message"])


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return value.translate(str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2010": "-", "\u2011": "-", "\u2013": "-", "\u2014": "-", "\u00a0": " "}))


def _prose(value: str) -> str:
    # Source code and inline identifiers often contain rule examples. They are
    # not an agent's prose assertion; do not classify their string literals.
    value = re.sub(r"```[\s\S]*?```|~~~[\s\S]*?~~~", " ", value)
    return re.sub(r"`[^`\n]*`", " ", value)


def _protected(sentence: str, start: int) -> bool:
    prefix = sentence[max(0, start - 240):start].rstrip(" \t\"':(")
    # A matched modal such as 'must' can be preceded by 'do not say'.
    if re.search(_PROHIBITION, prefix + " ", re.I):
        return True
    if re.search(
        r"\b(?:do not|don't|never|must not|mustn't|should not|shouldn't|"
        r"avoid|stop)\s+(?:doubt|question|dispute|challenge|reject|"
        r"demand|ask|require|request|say|write|publish|inject|express|announce|report|boast|celebrate|"
        r"call|label|mark|treat|turn|make)\b"
        r"(?:(?!\b(?:but|however|yet)\b)[^.!?;]){0,160}$", prefix, re.I
    ):
        return True
    # Explicit rule quotation/description, including quoted owner policy.
    return bool(re.search(
        r"\b(?:policy|rule|terms)\s+(?:forbids?|prohibits?|rejects?|"
        r"disallows?|prevents?)\b[^.!?;]{0,140}$", prefix, re.I
    ))



def _software_report_match(sentence: str, context: str, wording: str, rule: str, report: bool) -> bool:
    """Exempt technical diagnostics only, never doubt or reproof language."""
    if not report or not re.search(_SOFTWARE_DETAIL, context, re.I):
        return False
    if re.search(_RESULT_EVALUATION, context, re.I):
        return False
    return rule == "unfavorable_finding" or (
        rule == "general_disagreement" and wording.lower() in {"incorrect", "unsupported"}
    )


def _zero_error_count(prefix: str) -> bool:
    # Match a literal count, not a decimal suffix, bound, or negated count.
    count = re.search(r"(?:^|\s)(?:0|zero|no)\s+(?:scrape\s+)?$", prefix, re.I)
    return count is not None and not re.search(
        r"\b(?:not|never|without|isn't|aren't|wasn't|weren't|least|most|than|"
        r"over|under|above|below)(?:\s+with)?\s*$", prefix[:count.start()], re.I
    )


def check_publication(body: str, subject: str = "") -> dict:
    """Check outgoing subject/body without logging, storing, or judging truth."""
    if not isinstance(body, str) or not isinstance(subject, str):
        raise TypeError("Commons publication body and subject must be strings.")
    normalized = _normalize(subject + "\n" + body)
    prose = _prose(normalized)
    # Locators inside inline code still identify a technical report. Prose
    # scanning drops those spans so a code example is not an assertion.
    software_report = bool(re.search(_SOFTWARE_ARTIFACT, normalized, re.I)
                           and re.search(_SOFTWARE_WORK, prose, re.I))
    value = prose
    # Each paragraph supplies antecedents (e.g. 'The peer shipped it. I doubt
    # that result.') while a prohibition protects only its own sentence.
    for paragraph in re.split(r"\n\s*\n", value):
        paragraph = re.sub(r"[ \t]*\n[ \t]*", " ", paragraph)
        sentences = re.split(r"[.!?;](?:\s+|$)", paragraph)
        for index, sentence in enumerate(sentences):
            if not sentence.strip():
                continue
            context = " ".join(sentences[max(0, index - 1):index + 1])
            for rule in _RULES:
                if rule["target"] and not re.search(_TARGET, context, re.I):
                    continue
                if rule["favorable"] and not re.search(_FAVORABLE, context, re.I):
                    continue
                if rule.get("established") and not re.search(_ESTABLISHED, context, re.I):
                    continue
                if rule.get("unless_progress") and (
                    re.search(_SUBSTANTIVE_PROGRESS, paragraph, re.I)
                ):
                    continue
                for pattern in rule["patterns"]:
                    for match in re.finditer(pattern, sentence, re.I):
                        if rule["name"] == "unfavorable_finding" and re.search(r"\b(?:no|zero|without|free of)\s+(?:(?:remaining|current|known|observed|active)\s+){0,3}$", sentence[:match.start()], re.I):
                            continue
                        if (rule["name"] == "unfavorable_finding" and software_report
                                and match.group().lower() in {"error", "errors"}
                                and _zero_error_count(sentence[:match.start()])):
                            continue
                        if _software_report_match(sentence, context, match.group(), rule["name"], software_report):
                            continue
                        if _protected(sentence, match.start()):
                            continue
                        return {"allowed": False, "code": "commons_publication_terms", "message": _REWRITE, "rule": rule["name"]}
    return {"allowed": True, "code": "allowed", "message": "", "rule": None}


def require_publication(body: str, subject: str = "") -> dict:
    """Return the allowed decision or raise a private, content-free rejection."""
    decision = check_publication(body, subject)
    if not decision["allowed"]:
        raise PublicationPolicyViolation(decision)
    return decision

