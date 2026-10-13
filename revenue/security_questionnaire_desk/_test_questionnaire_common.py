"""Shared exact fixture with answer-generation evidence bindings."""
from __future__ import annotations

try:
    from . import security_questionnaire_desk as sq
    from . import test_security_questionnaire_desk_legacy as legacy
except ImportError:
    import security_questionnaire_desk as sq
    import test_security_questionnaire_desk_legacy as legacy

_ORIGINAL_FIXTURE = legacy.fixture


def fixture():
    data = _ORIGINAL_FIXTURE()
    questions = {row["question_id"]: row for row in data["questions"]}
    answers = {row["question_id"]: row for row in data["proposed_answers"]}
    for evidence in data["evidence"]:
        question_id = evidence["supports_question_id"]
        evidence["supports_answer_sha256"] = sq.answer_binding_sha256(
            questions[question_id], answers[question_id]["answer"]
        )
    return data


legacy.fixture = fixture
