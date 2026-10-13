from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.sun_a308734_ternary5.ternary5 import (
    Ternary5Witness,
    bad_prime_obstructions,
    certify_b_menu_failure,
    certify_bounded_failure,
    certify_fixed_menu_size_at_most_two,
    find_witness,
    lift_witness_by_25,
    primitive_25_core,
)


EVIDENCE = Path(__file__).with_name("evidence") / "bounded_shortcut_falsifiers_v1.json"
FIXED_MENU_EVIDENCE = (
    Path(__file__).with_name("evidence") / "fixed_menu_falsifiers_v1.json"
)


def test_source_base_case_and_local_congruence() -> None:
    witness = find_witness(5)
    assert witness == Ternary5Witness(0, 1, 1, 0)
    assert witness.value == 5
    assert witness.restricted_square % 12 == 4
    residual = 5 - witness.restricted_square
    assert residual % 12 == 1


def test_25_adic_primitive_descent_and_lift() -> None:
    core, k = primitive_25_core(5 * 25**4)
    assert (core, k) == (5, 4)
    core_witness = Ternary5Witness(0, 1, 1, 0)
    lifted = lift_witness_by_25(core_witness, k)
    lifted.verify(5 * 25**4)
    assert lifted == Ternary5Witness(0, 625, 1, 4)


def test_b_zero_shortcut_is_exactly_falsified() -> None:
    rows = certify_bounded_failure(12233, 0)
    assert {(row["a"], row["b"]) for row in rows} == {
        (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0)
    }
    assert find_witness(12233, max_b=0) is None
    assert find_witness(12233) is not None


def test_b_at_most_one_shortcut_fails_but_conjecture_witness_exists() -> None:
    rows = certify_bounded_failure(1_595_477, 1)
    assert len(rows) == 17
    assert find_witness(1_595_477, max_b=1) is None

    witness = find_witness(1_595_477)
    assert witness == Ternary5Witness(831, 946, 2, 2)
    witness.verify(1_595_477)


def test_nonconsecutive_b_menu_zero_two_is_exactly_falsified() -> None:
    rows = certify_b_menu_failure(1_750_109, (0, 2))
    assert len(rows) == 15
    assert {row["b"] for row in rows} == {0, 2}

    witness = Ternary5Witness(403, 1260, 1, 1)
    witness.verify(1_750_109)
    assert witness.b not in {0, 2}


@pytest.mark.parametrize(
    ("menu", "target", "row_count"),
    [
        ((1,), 5, 0),
        ((1, 2), 5, 0),
        ((0,), 12_233, 6),
        ((0, 1), 1_595_477, 17),
        ((0, 2), 1_750_109, 15),
        ((0, 3), 12_233, 6),
        ((0, 100_000), 12_233, 6),
    ],
)
def test_every_fixed_b_menu_of_size_at_most_two_is_excluded(
    menu: tuple[int, ...], target: int, row_count: int
) -> None:
    certificate = certify_fixed_menu_size_at_most_two(menu)
    assert certificate["b_values"] == list(menu)
    assert certificate["n"] == target
    assert len(certificate["positive_residual_failures"]) == row_count
    witness = Ternary5Witness(**certificate["outside_menu_witness"])
    witness.verify(target)
    assert witness.b not in menu


def test_evidence_fixture_replays_exactly() -> None:
    fixture = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert fixture["status"] == "FINITE_EXACT_EVIDENCE_NOT_FULL_PROOF"
    for case in fixture["cases"]:
        rows = certify_bounded_failure(case["n"], case["max_b"])
        assert rows
        declared = case.get("unbounded_witness")
        if declared:
            witness = Ternary5Witness(**declared)
            witness.verify(case["n"])


def test_fixed_menu_fixture_replays_exactly() -> None:
    fixture = json.loads(FIXED_MENU_EVIDENCE.read_text(encoding="utf-8"))
    assert fixture["status"] == "FINITE_EXACT_EVIDENCE_NOT_FULL_PROOF"
    case = fixture["cases"][0]
    rows = certify_b_menu_failure(case["n"], case["b_values"])
    assert len(rows) == case["expected_positive_residual_failures"]
    witness = Ternary5Witness(**case["outside_menu_witness"])
    witness.verify(case["n"])
    assert witness.b not in case["b_values"]


def test_known_obstruction_certificate() -> None:
    # 12233 - 4 = 12229 = 7 * 1747; both bad-prime valuations are odd.
    assert bad_prime_obstructions(12229) == ((7, 1), (1747, 1))


@pytest.mark.parametrize("bad", [0, 1, 2, 6, 13, 25])
def test_non_targets_rejected(bad: int) -> None:
    with pytest.raises(ValueError):
        primitive_25_core(bad)


def test_legal_5_mod_12_target_is_accepted() -> None:
    # 17 ≡ 5 (mod 12) is a legal target. A landed fixture listed it as invalid.
    assert primitive_25_core(17) == (17, 0)
    witness = find_witness(17)
    assert witness == Ternary5Witness(2, 3, 1, 0)
    witness.verify(17)
