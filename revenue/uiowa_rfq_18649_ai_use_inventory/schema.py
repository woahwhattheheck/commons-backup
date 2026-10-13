#!/usr/bin/env python3
"""UIOWA-071 -- AI-use inventory: the field contract.

Why this is code and not a table in a document: an AI-use inventory is the
easiest place in an assessment to manufacture an adoption number.  Somebody
says "we use AI for testing", it lands in a cell, and three documents later
it is a finding with nothing behind it.  The work order is explicit -- the
inventory must "leave unsupported University adoption claims unfilled" -- so
the rule is enforced where a record is read, not left to the discipline of
whoever fills the spreadsheet.

Everything in this lane is SYNTHETIC.  No University input has been
collected.  Source locators use the synthetic:// scheme so a fictional
record can never be read as a real one.

Join keys (group / area / synthetic:// source_ref) match the shapes already
landed in revenue/uiowa_rfq_18649_workshare so this inventory can be
consumed by the evidence register.  This module does not write into that
register; it only emits keys that fit it.
"""

UNKNOWN = "UNKNOWN"

# The five work functions the order names.
FUNCTIONS = ("development", "documentation", "testing", "support", "analysis")

# Organizational groups already in use across this solicitation's lanes.
GROUPS = ("ESS", "RIS", "IAM")

# Area tag for the assessment matrix.  Every row in this lane is AI.
AREA = "AI"

# What the respondent says about the use.  This is a claim, not a finding.
DECLARED_STATUS = ("ACTIVE", "INFORMAL", "PLANNED")

FREQUENCY = ("DAILY", "WEEKLY", "MONTHLY", "AD_HOC", "ONCE", "NOT_YET", UNKNOWN)

# Only these establish a recurring, running workflow.  AD_HOC and ONCE are
# real answers but they describe experimentation, not operation.
RECURRING_FREQUENCY = ("DAILY", "WEEKLY", "MONTHLY")

# What the inventory concludes.  Five buckets, reported separately, never
# collapsed into an adoption percentage or a maturity score.
CLASSIFICATIONS = (
    "ACTIVE_USE",
    "INFORMAL_EXPERIMENT",
    "PLANNED_USE",
    "UNSUPPORTED_CLAIM",
    UNKNOWN,
)

# How an integrations answer was given.  A blank is not an absence.
INTEGRATION_STATES = ("REPORTED", "NONE_REPORTED", UNKNOWN)

REQUIRED_FIELDS = ("entry_id", "group", "function", "task")

OPTIONAL_FIELDS = (
    "users",
    "inputs",
    "outputs",
    "integrations",
    "frequency",
    "observed_benefits",
    "known_limitations",
    "declared_status",
    "evidence_refs",
    "captured_at",
    "respondent_role",
    "notes",
)

# This inventory assesses organizational capability.  It never rates a
# person, so it carries no field that identifies one.  A record that smuggles
# one in is rejected rather than quietly stored.
BANNED_IDENTITY_KEYS = (
    "person_name",
    "employee_id",
    "individual",
    "netid",
    "staff_name",
    "email",
    "username",
)

VALIDATION_CODES = (
    "MISSING_REQUIRED_FIELD",
    "UNKNOWN_VOCABULARY_VALUE",
    "INDIVIDUAL_IDENTIFIER_PRESENT",
    "BAD_TYPE",
    "DUPLICATE_ENTRY_ID",
    "MALFORMED_BENEFIT",
)


class ValidationIssue(object):
    """One problem with one record.  Records are never dropped for having
    one -- a dropped record is an invisible gap, which is the failure this
    whole lane exists to prevent."""

    __slots__ = ("entry_id", "code", "field", "detail")

    def __init__(self, entry_id, code, field, detail):
        assert code in VALIDATION_CODES, code
        self.entry_id = entry_id
        self.code = code
        self.field = field
        self.detail = detail

    def as_dict(self):
        return {
            "entry_id": self.entry_id,
            "code": self.code,
            "field": self.field,
            "detail": self.detail,
        }

    def __repr__(self):  # pragma: no cover - debugging aid
        return "ValidationIssue(%s,%s,%s)" % (self.entry_id, self.code, self.field)


def _is_str_list(value):
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def validate_record(rec):
    """Return a list of ValidationIssue for one raw record dict."""
    issues = []
    if not isinstance(rec, dict):
        return [ValidationIssue(UNKNOWN, "BAD_TYPE", "<record>", "record is not an object")]

    entry_id = rec.get("entry_id") or UNKNOWN

    for key in BANNED_IDENTITY_KEYS:
        if key in rec:
            issues.append(
                ValidationIssue(
                    entry_id,
                    "INDIVIDUAL_IDENTIFIER_PRESENT",
                    key,
                    "inventory rows are keyed to a task and a team; remove the individual identifier",
                )
            )

    for field in REQUIRED_FIELDS:
        value = rec.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            issues.append(
                ValidationIssue(entry_id, "MISSING_REQUIRED_FIELD", field, "required field is empty")
            )

    if rec.get("group") is not None and rec.get("group") not in GROUPS:
        issues.append(
            ValidationIssue(
                entry_id, "UNKNOWN_VOCABULARY_VALUE", "group",
                "expected one of %s, got %r" % (list(GROUPS), rec.get("group")),
            )
        )

    if rec.get("function") is not None and rec.get("function") not in FUNCTIONS:
        issues.append(
            ValidationIssue(
                entry_id, "UNKNOWN_VOCABULARY_VALUE", "function",
                "expected one of %s, got %r" % (list(FUNCTIONS), rec.get("function")),
            )
        )

    status = rec.get("declared_status")
    if status is not None and status not in DECLARED_STATUS:
        issues.append(
            ValidationIssue(
                entry_id, "UNKNOWN_VOCABULARY_VALUE", "declared_status",
                "expected one of %s, got %r" % (list(DECLARED_STATUS), status),
            )
        )

    freq = rec.get("frequency")
    if freq is not None and freq not in FREQUENCY:
        issues.append(
            ValidationIssue(
                entry_id, "UNKNOWN_VOCABULARY_VALUE", "frequency",
                "expected one of %s, got %r" % (list(FREQUENCY), freq),
            )
        )

    for field in ("inputs", "outputs", "integrations", "known_limitations", "evidence_refs"):
        value = rec.get(field)
        if value is not None and not _is_str_list(value):
            issues.append(
                ValidationIssue(entry_id, "BAD_TYPE", field, "expected a list of strings")
            )

    benefits = rec.get("observed_benefits")
    if benefits is not None:
        if not isinstance(benefits, list):
            issues.append(
                ValidationIssue(entry_id, "BAD_TYPE", "observed_benefits", "expected a list")
            )
        else:
            for i, b in enumerate(benefits):
                if not isinstance(b, dict) or "claim" not in b:
                    issues.append(
                        ValidationIssue(
                            entry_id, "MALFORMED_BENEFIT", "observed_benefits[%d]" % i,
                            "each benefit needs a 'claim' and may carry an 'example_ref'",
                        )
                    )

    users = rec.get("users")
    if users is not None and not isinstance(users, dict):
        issues.append(ValidationIssue(entry_id, "BAD_TYPE", "users", "expected an object"))

    return issues


def normalize_record(rec):
    """Apply the UNKNOWN discipline and return a stable dict.

    The point of this function is one distinction the rest of the pipeline
    depends on: a blank answer is UNKNOWN, an explicit "none" is a real
    answer.  Blank frequency does not become "never".  Blank integrations
    does not become "standalone".  Blank benefit does not become "no
    benefit".  An absent input is never turned into a zero.
    """
    out = {}
    out["entry_id"] = rec.get("entry_id") or UNKNOWN
    # An out-of-vocabulary group or function is mapped to UNKNOWN so it cannot
    # be silently placed in the coverage grid, and the value as given is kept
    # alongside it so the row stays visible and correctable.  A record that
    # disappears from a coverage report is an invisible gap, which is the
    # exact failure this lane exists to prevent.
    group = rec.get("group")
    out["group"] = group if group in GROUPS else UNKNOWN
    out["group_as_given"] = group if group else UNKNOWN
    function = rec.get("function")
    out["function"] = function if function in FUNCTIONS else UNKNOWN
    out["function_as_given"] = function if function else UNKNOWN
    out["area"] = AREA
    out["task"] = rec.get("task") or UNKNOWN
    out["declared_status"] = rec.get("declared_status") or UNKNOWN
    out["captured_at"] = rec.get("captured_at") or UNKNOWN
    out["respondent_role"] = rec.get("respondent_role") or UNKNOWN
    out["notes"] = rec.get("notes") or ""

    freq = rec.get("frequency")
    out["frequency"] = freq if freq in FREQUENCY else UNKNOWN

    users = rec.get("users") if isinstance(rec.get("users"), dict) else {}
    roles = users.get("roles")
    out["user_roles"] = list(roles) if _is_str_list(roles) else []
    count = users.get("approx_count")
    # An unstated headcount is UNKNOWN.  It is emphatically not zero users.
    out["user_count"] = count if isinstance(count, int) and count >= 0 else UNKNOWN

    for field in ("inputs", "outputs", "known_limitations", "evidence_refs"):
        value = rec.get(field)
        out[field] = list(value) if _is_str_list(value) else []
        out[field + "_state"] = "REPORTED" if _is_str_list(value) and value else (
            "NONE_REPORTED" if _is_str_list(value) else UNKNOWN
        )

    integrations = rec.get("integrations")
    if _is_str_list(integrations):
        out["integrations"] = list(integrations)
        out["integrations_state"] = "REPORTED" if integrations else "NONE_REPORTED"
    else:
        out["integrations"] = []
        out["integrations_state"] = UNKNOWN

    benefits = []
    raw_benefits = rec.get("observed_benefits")
    if isinstance(raw_benefits, list):
        for b in raw_benefits:
            if isinstance(b, dict) and "claim" in b:
                ref = b.get("example_ref")
                benefits.append(
                    {
                        "claim": b["claim"],
                        "example_ref": ref if isinstance(ref, str) and ref.strip() else None,
                    }
                )
    out["observed_benefits"] = benefits
    out["benefits_with_example"] = len([b for b in benefits if b["example_ref"]])
    out["benefits_unsupported"] = len([b for b in benefits if not b["example_ref"]])
    return out


def proposed_evidence_id(group, index):
    """A join key shaped like the evidence register's own IDs.

    This lane emits the key; it does not write anyone else's register.
    """
    g = group if group in GROUPS else "XXX"
    return "EV-SYN-%s-%s-INV-%03d" % (g, AREA, index)
