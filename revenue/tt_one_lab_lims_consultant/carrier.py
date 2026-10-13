from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any


class CarrierError(ValueError):
    pass


def _build_strict_loader():
    error_cls = CarrierError
    json_loads = json.loads
    decode_error = json.JSONDecodeError
    type_error = TypeError

    def strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise error_cls(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def reject_constant(token: str):
        raise error_cls(f"non-finite JSON number: {token}")

    def loader(text: str) -> Any:
        try:
            return json_loads(
                text,
                object_pairs_hook=strict_pairs,
                parse_constant=reject_constant,
            )
        except error_cls:
            raise
        except (decode_error, type_error) as exc:
            raise error_cls(f"invalid JSON: {exc}") from exc

    return loader


loads_strict = _build_strict_loader()


def _load_json_object(name: str) -> dict[str, Any]:
    value = loads_strict(
        (Path(__file__).resolve().parent / name).read_text(encoding="utf-8")
    )
    if type(value) is not dict:
        raise CarrierError(f"{name} must be a JSON object")
    return value


def _load_manifest() -> dict[str, Any]:
    return _load_json_object("source_manifest.json")


def _load_integrity_boundary() -> dict[str, Any]:
    return _load_json_object("INTEGRITY_BOUNDARY.json")


def _build_semantic_generation(source: dict[str, Any], boundary: dict[str, Any]):
    """Capture a cooperative semantic generation.

    The returned runtime functions close over primitive values, immutable tuples,
    compiled regexes, and captured stdlib/helper callables. This prevents ordinary
    module-global/helper rebinding from changing compiler/verifier meaning together.
    It is deliberately not a hostile same-process Python integrity boundary; the
    exact non-claim is emitted in every packet and documented by the boundary file.
    """

    error_cls = CarrierError
    value_error = ValueError
    type_ = type
    dict_ = dict
    list_ = list
    set_ = set
    str_ = str
    int_ = int
    bool_ = bool
    tuple_ = tuple
    frozenset_ = frozenset
    sorted_ = sorted
    len_ = len
    all_ = all
    sum_ = sum
    enumerate_ = enumerate
    json_dumps = json.dumps
    sha256 = hashlib.sha256
    deep_copy = deepcopy
    fromisoformat = datetime.fromisoformat
    sha_re = re.compile(r"^[0-9a-f]{64}$")
    iso_currency_re = re.compile(r"^[A-Z]{3}$")

    expected_top = frozenset_(
        {
            "source_manifest_digest",
            "evaluated_at",
            "candidate",
            "commercial",
            "submission",
        }
    )
    expected_candidate = frozenset_(
        {
            "degree_evidence_digest",
            "experience_years",
            "experience_evidence_digest",
            "reference_evidence_digests",
            "nine_month_availability",
            "in_country_availability",
            "availability_evidence_digest",
            "lims_health_system_evidence_digest",
            "cross_sector_integration_evidence_digest",
            "training_evidence_digest",
            "conflict_disclosure",
        }
    )
    expected_commercial = frozenset_(
        {"currency", "price_rows_minor", "all_inclusive_owner_confirmed"}
    )
    expected_submission = frozenset_({"email", "subject", "validity_days"})
    expected_authority = {
        "award_claimed": False,
        "buyer_contact_authorized": False,
        "clarification_authorized": False,
        "contract_acceptance_authorized": False,
        "payment_claimed": False,
        "pricing_commitment_authorized": False,
        "revenue_claimed": False,
        "signature_authorized": False,
        "submission_authorized": False,
        "travel_spend_authorized": False,
    }
    expected_boundary = {
        "schema": "tt-one-lab-lims-integrity-boundary/v1",
        "public_api_boundary": "COOPERATIVE_IN_PROCESS_ONLY_NOT_HOSTILE_RUNTIME",
        "resists_module_global_rebinding": True,
        "resists_helper_symbol_rebinding": True,
        "resists_public_compiler_symbol_rebinding_in_verifier": True,
        "resists_cpython_closure_cell_mutation": False,
        "hostile_same_process_python_supported": False,
        "machine_strong_same_process_integrity_claimed": False,
        "externally_isolated_source_verified_runner_provided": False,
        "caller_supplied_evaluation_time": "REPLAY_ONLY_NOT_CURRENT",
        "current_submission_authority_claimed": False,
        "required_external_boundary_for_hostile_runtime": "Run reviewed source in a separately trusted, source-verified execution environment outside the potentially hostile Python process.",
        "rationale": "CPython exposes writable function closure cells and mutable function/runtime objects to code already executing in the same interpreter. This carrier hardens accidental/cooperative rebinding but does not claim to defend against arbitrary reflective mutation by hostile same-process code.",
    }

    def canonical(value: Any) -> bytes:
        return json_dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")

    def digest(value: Any) -> str:
        return sha256(canonical(value)).hexdigest()

    source_digest = digest(source)
    if boundary != expected_boundary:
        raise error_cls("integrity boundary sidecar must match code-owned contract")
    boundary_digest = digest(expected_boundary)
    boundary_items = tuple_(sorted_(expected_boundary.items()))

    if type_(source.get("buyer_facts")) is not dict_:
        raise error_cls("source buyer_facts must be an object")
    if source.get("authority") != expected_authority:
        raise error_cls("source authority must match the all-false code-owned contract")

    buyer_source = source["buyer_facts"]
    price_rows = tuple_(buyer_source.get("price_rows", ()))
    deliverables = tuple_(buyer_source.get("deliverables", ()))
    if len_(price_rows) != 7 or len_(frozenset_(price_rows)) != 7:
        raise error_cls("source must contain seven distinct mandatory price rows")
    if len_(deliverables) != 6:
        raise error_cls("source must contain six TOR delivery milestones")

    evaluation_weights_source = buyer_source.get("evaluation_weights")
    if type_(evaluation_weights_source) is not dict_:
        raise error_cls("source evaluation_weights must be an object")
    evaluation_weight_items = tuple_(sorted_(evaluation_weights_source.items()))
    if any(type_(value) is not int_ for _, value in evaluation_weight_items):
        raise error_cls("source evaluation weights must be strict integers")
    if sum_(value for _, value in evaluation_weight_items) != 100:
        raise error_cls("source evaluation weights must sum to 100")

    buyer_procuring_entity = buyer_source["procuring_entity"]
    buyer_project = buyer_source["project"]
    buyer_consultancy = buyer_source["consultancy"]
    buyer_deadline_text = buyer_source["proposal_deadline_local"]
    buyer_submission_email = buyer_source["submission_email"]
    buyer_submission_subject = buyer_source["submission_subject"]
    buyer_clarification_cutoff = buyer_source["clarification_cutoff_date"]
    buyer_clarification_email = buyer_source["clarification_email_as_printed_in_pdf"]
    buyer_clarification_conflict = buyer_source["clarification_route_conflict"]
    buyer_minimum_experience = buyer_source["minimum_experience_years"]
    buyer_minimum_references = buyer_source["minimum_references"]
    buyer_validity_days = buyer_source["proposal_validity_days"]

    scalar_string_values = (
        buyer_procuring_entity,
        buyer_project,
        buyer_consultancy,
        buyer_deadline_text,
        buyer_submission_email,
        buyer_submission_subject,
        buyer_clarification_cutoff,
        buyer_clarification_email,
    )
    if not all_(type_(value) is str_ and value for value in scalar_string_values):
        raise error_cls("source buyer string contract invalid")
    if type_(buyer_clarification_conflict) is not bool_ or not buyer_clarification_conflict:
        raise error_cls("source clarification route conflict must remain explicit")
    if type_(buyer_minimum_experience) is not int_ or buyer_minimum_experience < 0:
        raise error_cls("source minimum experience must be a strict non-negative integer")
    if type_(buyer_minimum_references) is not int_ or buyer_minimum_references < 1:
        raise error_cls("source minimum references must be a strict positive integer")
    if type_(buyer_validity_days) is not int_ or buyer_validity_days < 1:
        raise error_cls("source validity days must be a strict positive integer")

    deadline = fromisoformat(buyer_deadline_text)
    if deadline.tzinfo is None or deadline.utcoffset() is None:
        raise error_cls("source proposal deadline must be offset-aware")

    authority_items = tuple_(sorted_(expected_authority.items()))
    evaluation_weights_items = evaluation_weight_items
    conflict_states = frozenset_(
        {"UNKNOWN", "NO_KNOWN_CONFLICT", "DISCLOSED_CONFLICT"}
    )

    def exact_object(value: Any, keys: frozenset[str], label: str) -> dict[str, Any]:
        if type_(value) is not dict_:
            raise error_cls(f"{label} must be an object")
        actual = frozenset_(value)
        if actual != keys:
            missing = sorted_(keys - actual)
            extra = sorted_(actual - keys)
            raise error_cls(f"{label} keys mismatch missing={missing} extra={extra}")
        return value

    def sha_or_none(value: Any, label: str) -> str | None:
        if value is None:
            return None
        if type_(value) is not str_ or not sha_re.fullmatch(value):
            raise error_cls(f"{label} must be null or lowercase sha256")
        return value

    def strict_bool(value: Any, label: str) -> bool:
        if type_(value) is not bool_:
            raise error_cls(f"{label} must be boolean")
        return value

    def strict_int(value: Any, label: str, minimum: int = 0) -> int:
        if type_(value) is not int_ or value < minimum:
            raise error_cls(f"{label} must be integer >= {minimum}")
        return value

    def evaluation_time(value: Any):
        if type_(value) is not str_:
            raise error_cls("evaluated_at must be an ISO timestamp string")
        try:
            parsed = fromisoformat(value)
        except value_error as exc:
            raise error_cls("evaluated_at is not valid ISO 8601") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise error_cls("evaluated_at must include an offset")
        return parsed

    def validate_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
        exact_object(candidate, expected_candidate, "candidate")
        digests: dict[str, str | None] = {}
        for key in (
            "degree_evidence_digest",
            "experience_evidence_digest",
            "availability_evidence_digest",
            "lims_health_system_evidence_digest",
            "cross_sector_integration_evidence_digest",
            "training_evidence_digest",
        ):
            digests[key] = sha_or_none(candidate[key], f"candidate.{key}")

        years = strict_int(candidate["experience_years"], "candidate.experience_years")
        nine_month = strict_bool(
            candidate["nine_month_availability"], "candidate.nine_month_availability"
        )
        in_country = strict_bool(
            candidate["in_country_availability"], "candidate.in_country_availability"
        )

        refs = candidate["reference_evidence_digests"]
        if type_(refs) is not list_:
            raise error_cls("candidate.reference_evidence_digests must be an array")
        if len_(refs) > 20:
            raise error_cls("candidate.reference_evidence_digests is unbounded")
        checked_refs: list[str] = []
        seen: set[str] = set_()
        for idx, value in enumerate_(refs):
            receipt = sha_or_none(
                value, f"candidate.reference_evidence_digests[{idx}]"
            )
            if receipt is None:
                raise error_cls("reference digest cannot be null")
            if receipt in seen:
                raise error_cls("duplicate reference evidence digest")
            seen.add(receipt)
            checked_refs.append(receipt)

        conflict = candidate["conflict_disclosure"]
        if conflict not in conflict_states:
            raise error_cls("candidate.conflict_disclosure invalid")

        return {
            **digests,
            "experience_years": years,
            "reference_evidence_digests": checked_refs,
            "nine_month_availability": nine_month,
            "in_country_availability": in_country,
            "conflict_disclosure": conflict,
        }

    def validate_commercial(commercial: dict[str, Any]) -> dict[str, Any]:
        exact_object(commercial, expected_commercial, "commercial")
        currency = commercial["currency"]
        if currency is not None and (
            type_(currency) is not str_ or not iso_currency_re.fullmatch(currency)
        ):
            raise error_cls(
                "commercial.currency must be null or 3-letter uppercase code"
            )

        rows = commercial["price_rows_minor"]
        if type_(rows) is not dict_:
            raise error_cls("commercial.price_rows_minor must be an object")
        if frozenset_(rows) != frozenset_(price_rows):
            raise error_cls(
                "commercial.price_rows_minor must contain exactly seven buyer rows"
            )

        normalized: dict[str, int | None] = {}
        for name in price_rows:
            value = rows[name]
            if value is None:
                normalized[name] = None
            else:
                normalized[name] = strict_int(
                    value, f"commercial.price_rows_minor[{name}]"
                )
        all_inclusive = strict_bool(
            commercial["all_inclusive_owner_confirmed"],
            "commercial.all_inclusive_owner_confirmed",
        )
        return {
            "currency": currency,
            "price_rows_minor": normalized,
            "all_inclusive_owner_confirmed": all_inclusive,
        }

    def validate_submission(submission: dict[str, Any]) -> dict[str, Any]:
        exact_object(submission, expected_submission, "submission")
        email = submission["email"]
        subject = submission["subject"]
        validity = strict_int(
            submission["validity_days"], "submission.validity_days", 1
        )
        if type_(email) is not str_ or type_(subject) is not str_:
            raise error_cls("submission email/subject must be strings")
        return {"email": email, "subject": subject, "validity_days": validity}

    def score_readiness(candidate: dict[str, Any]) -> dict[str, Any]:
        evidence_present = {
            "minimum_education": candidate["degree_evidence_digest"] is not None,
            "minimum_experience": (
                candidate["experience_years"] >= buyer_minimum_experience
                and candidate["experience_evidence_digest"] is not None
            ),
            "three_references": (
                len_(candidate["reference_evidence_digests"]) >= buyer_minimum_references
            ),
            "nine_month_availability": (
                candidate["nine_month_availability"]
                and candidate["availability_evidence_digest"] is not None
            ),
            "in_country_availability": (
                candidate["in_country_availability"]
                and candidate["availability_evidence_digest"] is not None
            ),
        }
        optional_score_evidence = {
            "lims_health_system": (
                candidate["lims_health_system_evidence_digest"] is not None
            ),
            "cross_sector_integration": (
                candidate["cross_sector_integration_evidence_digest"] is not None
            ),
            "training": candidate["training_evidence_digest"] is not None,
        }
        return {
            "essential_owner_evidence_present": evidence_present,
            "score_bearing_owner_evidence_present": optional_score_evidence,
            "all_essential_owner_evidence_present": all_(evidence_present.values()),
        }

    def buyer_projection() -> dict[str, Any]:
        return {
            "procuring_entity": buyer_procuring_entity,
            "project": buyer_project,
            "consultancy": buyer_consultancy,
            "deadline_local": buyer_deadline_text,
            "submission_email": buyer_submission_email,
            "submission_subject": buyer_submission_subject,
            "clarification_cutoff_date": buyer_clarification_cutoff,
            "clarification_email_as_printed_in_pdf": buyer_clarification_email,
            "clarification_route_conflict": buyer_clarification_conflict,
        }

    def authority_projection() -> dict[str, bool]:
        return dict_(authority_items)

    def boundary_projection() -> dict[str, Any]:
        return dict_(boundary_items)

    def compile_impl(owner_input: dict[str, Any]) -> dict[str, Any]:
        top = exact_object(owner_input, expected_top, "owner_input")
        if top["source_manifest_digest"] != source_digest:
            raise error_cls("source_manifest_digest mismatch")

        evaluated = evaluation_time(top["evaluated_at"])
        candidate = validate_candidate(top["candidate"])
        commercial = validate_commercial(top["commercial"])
        submission = validate_submission(top["submission"])
        readiness = score_readiness(candidate)

        replay_deadline_open = evaluated.astimezone(deadline.tzinfo) <= deadline
        commercial_complete = (
            commercial["currency"] is not None
            and commercial["all_inclusive_owner_confirmed"]
            and all_(
                value is not None
                for value in commercial["price_rows_minor"].values()
            )
        )
        submission_matches_buyer = (
            submission["email"] == buyer_submission_email
            and submission["subject"] == buyer_submission_subject
            and submission["validity_days"] >= buyer_validity_days
        )
        conflict_resolved = candidate["conflict_disclosure"] != "UNKNOWN"

        blockers: list[str] = []
        if not replay_deadline_open:
            blockers.append("PROPOSAL_DEADLINE_PASSED")
        if not readiness["all_essential_owner_evidence_present"]:
            blockers.append("OWNER_CREDENTIAL_EVIDENCE_INCOMPLETE")
        if not commercial_complete:
            blockers.append("OWNER_PRICING_INCOMPLETE")
        if not submission_matches_buyer:
            blockers.append("SUBMISSION_METADATA_MISMATCH")
        if not conflict_resolved:
            blockers.append("CONFLICT_DISCLOSURE_UNRESOLVED")

        if not replay_deadline_open:
            posture = "NO_BID_DEADLINE_PASSED"
        elif blockers:
            posture = "HOLD_OWNER_EVIDENCE"
        else:
            posture = "OWNER_REVIEW_PACKET_COMPLETE_NOT_SUBMISSION_AUTHORITY"

        normalized_input = {
            "source_manifest_digest": source_digest,
            "evaluated_at": top["evaluated_at"],
            "candidate": candidate,
            "commercial": commercial,
            "submission": submission,
        }
        packet = {
            "schema": "tt-one-lab-lims-owner-review-packet/v3",
            "source_manifest_digest": source_digest,
            "integrity_boundary": boundary_projection(),
            "integrity_boundary_digest": boundary_digest,
            "evaluated_at": top["evaluated_at"],
            "evaluation_time_authority": "CALLER_SUPPLIED_REPLAY_ONLY_NOT_CURRENT",
            "current_deadline_readiness_claimed": False,
            "buyer": buyer_projection(),
            "candidate_evidence": deep_copy(candidate),
            "readiness": readiness,
            "commercial": deep_copy(commercial),
            "submission": deep_copy(submission),
            "blockers": blockers,
            "posture": posture,
            "evaluation_weights": dict_(evaluation_weights_items),
            "authority": authority_projection(),
        }
        packet["input_digest"] = digest(normalized_input)
        packet["packet_digest"] = digest(packet)
        return packet

    def verify_impl(packet: dict[str, Any], owner_input: dict[str, Any]) -> bool:
        if type_(packet) is not dict_:
            return False
        expected = compile_impl(owner_input)
        return canonical(packet) == canonical(expected)

    def source_digest_impl() -> str:
        return source_digest

    def example_input_impl() -> dict[str, Any]:
        return {
            "source_manifest_digest": source_digest,
            "evaluated_at": "2026-09-17T01:00:00-04:00",
            "candidate": {
                "degree_evidence_digest": None,
                "experience_years": 0,
                "experience_evidence_digest": None,
                "reference_evidence_digests": [],
                "nine_month_availability": False,
                "in_country_availability": False,
                "availability_evidence_digest": None,
                "lims_health_system_evidence_digest": None,
                "cross_sector_integration_evidence_digest": None,
                "training_evidence_digest": None,
                "conflict_disclosure": "UNKNOWN",
            },
            "commercial": {
                "currency": None,
                "price_rows_minor": {name: None for name in price_rows},
                "all_inclusive_owner_confirmed": False,
            },
            "submission": {
                "email": buyer_submission_email,
                "subject": buyer_submission_subject,
                "validity_days": buyer_validity_days,
            },
        }

    return compile_impl, verify_impl, source_digest_impl, example_input_impl


def _publish_generation(generation):
    compile_impl, verify_impl, source_digest_impl, example_input_impl = generation

    def compile_packet(owner_input: dict[str, Any]) -> dict[str, Any]:
        return compile_impl(owner_input)

    def verify_packet(packet: dict[str, Any], owner_input: dict[str, Any]) -> bool:
        return verify_impl(packet, owner_input)

    def source_manifest_digest() -> str:
        return source_digest_impl()

    def example_owner_input() -> dict[str, Any]:
        return example_input_impl()

    return compile_packet, verify_packet, source_manifest_digest, example_owner_input


(
    compile_packet,
    verify_packet,
    source_manifest_digest,
    example_owner_input,
) = _publish_generation(
    _build_semantic_generation(_load_manifest(), _load_integrity_boundary())
)
