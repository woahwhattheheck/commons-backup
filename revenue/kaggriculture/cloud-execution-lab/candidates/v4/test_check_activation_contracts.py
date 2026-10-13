#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import check_activation_contracts as guard


class ActivationContractTests(unittest.TestCase):
    def assert_clean(self, source: str) -> None:
        self.assertEqual([], guard.analyze_source(source, path="x.py"))

    def assert_fails(self, source: str, count: int = 1) -> list[guard.Finding]:
        findings = guard.analyze_source(source, path="x.py")
        self.assertEqual(count, len(findings), findings)
        return findings

    def test_if_not_enabled_is_fail_open(self):
        findings = self.assert_fails(
            "def apply(action, *, enabled=False):\n"
            "    if not enabled:\n"
            "        return action\n"
            "    return {'changed': True}\n"
        )
        self.assertEqual("apply", findings[0].function)
        self.assertEqual(2, findings[0].line)

    def test_if_enabled_is_fail_open(self):
        self.assert_fails(
            "def apply(action, enabled=False):\n"
            "    if enabled:\n"
            "        return {'changed': True}\n"
            "    return action\n"
        )

    def test_bool_coercion_is_fail_open_even_outside_if(self):
        self.assert_fails(
            "def apply(enabled=False):\n"
            "    active = bool(enabled)\n"
            "    return active\n"
        )

    def test_return_and_truthiness_is_fail_open(self):
        findings = self.assert_fails(
            "def install(wrapped, enabled=False):\n"
            "    return enabled and wrapped\n"
        )
        self.assertEqual(2, findings[0].line)

    def test_assignment_or_truthiness_is_fail_open(self):
        self.assert_fails(
            "def apply(parent, enabled=False):\n"
            "    result = enabled or parent\n"
            "    return result\n"
        )

    def test_return_not_truthiness_is_fail_open(self):
        self.assert_fails(
            "def apply(enabled=False):\n"
            "    return not enabled\n"
        )

    def test_nested_call_argument_boolop_truthiness_is_fail_open(self):
        self.assert_fails(
            "def apply(emit, candidate, enabled=False):\n"
            "    return emit(enabled and candidate)\n"
        )

    def test_strict_guards_allow_expression_truthiness(self):
        self.assert_clean(
            "def apply(action, wrapped, enabled=False):\n"
            "    if enabled is not True:\n"
            "        return action\n"
            "    return enabled and wrapped\n"
        )
        self.assert_clean(
            "def apply(action, enabled=False):\n"
            "    if type(enabled) is not bool:\n"
            "        return action\n"
            "    return not enabled\n"
        )

    def test_equality_with_true_is_not_literal_bool_identity(self):
        self.assert_fails(
            "def apply(enabled=False):\n"
            "    if enabled == True:\n"
            "        return 1\n"
            "    return 0\n"
        )

    def test_identity_to_false_does_not_reject_nonbools(self):
        self.assert_fails(
            "def apply(action, enabled=False):\n"
            "    if enabled is False:\n"
            "        return action\n"
            "    return {'changed': True}\n"
        )
        self.assert_fails(
            "def apply(action, enabled=False):\n"
            "    if enabled is not False:\n"
            "        return {'changed': True}\n"
            "    return action\n"
        )

    def test_nonexiting_is_not_true_branch_is_not_a_guard(self):
        self.assert_fails(
            "def apply(action, enabled=False):\n"
            "    if enabled is not True:\n"
            "        action = {'changed': True}\n"
            "    return action\n"
        )

    def test_bool_membership_uses_equality_semantics(self):
        self.assert_fails(
            "def apply(enabled=False):\n"
            "    if enabled in (True,):\n"
            "        return 1\n"
            "    return 0\n"
        )

    def test_not_and_boolop_coercion_outside_condition_are_caught(self):
        self.assert_fails(
            "def apply(enabled=False):\n"
            "    active = not enabled\n"
            "    return active\n"
        )
        self.assert_fails(
            "def apply(enabled=False):\n"
            "    active = enabled and object()\n"
            "    return active\n"
        )

    def test_any_all_direct_container_truthiness_is_caught(self):
        self.assert_fails(
            "def apply(enabled=False):\n"
            "    return any([enabled])\n"
        )
        self.assert_fails(
            "def apply(enabled=False):\n"
            "    return all((enabled, True))\n"
        )


    def test_nonbool_direct_comparisons_are_fail_open(self):
        self.assert_fails(
            "def apply(enabled=False):\n"
            "    if enabled == 1:\n"
            "        return 1\n"
            "    return 0\n"
        )
        self.assert_fails(
            "def apply(enabled=False):\n"
            "    if enabled != 0:\n"
            "        return 1\n"
            "    return 0\n"
        )
        self.assert_fails(
            "def apply(enabled=False):\n"
            "    if enabled in (1,):\n"
            "        return 1\n"
            "    return 0\n"
        )
        self.assert_fails(
            "def apply(enabled=False):\n"
            "    if 0 < enabled:\n"
            "        return 1\n"
            "    return 0\n"
        )

    def test_any_all_comprehension_truthiness_is_caught(self):
        self.assert_fails(
            "def apply(rows, enabled=False):\n"
            "    return any(enabled for _ in rows)\n"
        )
        self.assert_fails(
            "def apply(rows, enabled=False):\n"
            "    return all([enabled for _ in rows])\n"
        )
        self.assert_fails(
            "def apply(rows, enabled=False):\n"
            "    return any({enabled for _ in rows})\n"
        )
        self.assert_fails(
            "def apply(rows, enabled=False):\n"
            "    return all({enabled: 1 for _ in rows})\n"
        )

    def test_strict_type_guard_allows_nonbool_comparison_and_comprehension(self):
        self.assert_clean(
            "def apply(rows, enabled=False):\n"
            "    if type(enabled) is not bool:\n"
            "        return False\n"
            "    return enabled == 1 or any(enabled for _ in rows)\n"
        )

    def test_literal_true_reject_guard_allows_later_truthiness(self):
        self.assert_clean(
            "def apply(action, enabled=False):\n"
            "    if enabled is not True:\n"
            "        return action\n"
            "    if enabled:\n"
            "        return {'changed': True}\n"
            "    return action\n"
        )

    def test_literal_true_positive_test_is_safe_without_coercion(self):
        self.assert_clean(
            "def apply(action, enabled=False):\n"
            "    if enabled is True:\n"
            "        return {'changed': True}\n"
            "    return action\n"
        )

    def test_strict_type_reject_guard_allows_later_truthiness(self):
        self.assert_clean(
            "def apply(action, *, enabled=False):\n"
            "    if type(enabled) is not bool:\n"
            "        return action\n"
            "    if not enabled:\n"
            "        return action\n"
            "    return {'changed': True}\n"
        )

    def test_strict_isinstance_reject_guard_allows_later_truthiness(self):
        self.assert_clean(
            "def apply(action, enabled=False):\n"
            "    if not isinstance(enabled, bool):\n"
            "        raise TypeError('enabled')\n"
            "    return 1 if enabled else 0\n"
        )

    def test_guard_after_truthiness_does_not_retroactively_prove_safety(self):
        self.assert_fails(
            "def apply(action, enabled=False):\n"
            "    if enabled:\n"
            "        action = {'changed': True}\n"
            "    if enabled is not True:\n"
            "        return action\n"
            "    return action\n"
        )

    def test_non_default_off_enabled_parameter_is_out_of_scope(self):
        self.assert_clean(
            "def apply(enabled=True):\n"
            "    return bool(enabled)\n"
        )
        self.assert_clean(
            "def apply(enabled=None):\n"
            "    if enabled:\n"
            "        return 1\n"
            "    return 0\n"
        )

    def test_nested_callable_is_analyzed_on_its_own_parameter(self):
        findings = self.assert_fails(
            "def outer(enabled=False):\n"
            "    if enabled is not True:\n"
            "        return 0\n"
            "    def inner(enabled=False):\n"
            "        if enabled:\n"
            "            return 1\n"
            "        return 0\n"
            "    return inner()\n"
        )
        self.assertEqual("inner", findings[0].function)

    def test_syntax_error_fails_closed(self):
        findings = self.assert_fails("def broken(:\n    pass\n")
        self.assertEqual("<module>", findings[0].function)
        self.assertIn("cannot parse Python source", findings[0].message)

    def test_scan_paths_is_scope_limited_deduplicated_and_deterministic(self):
        scope = guard.DEFAULT_SCOPE
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root.joinpath(*scope.parts, "repairs", "demo", "apply.py")
            target.parent.mkdir(parents=True)
            target.write_text(
                "def apply(action, enabled=False):\n"
                "    if enabled:\n"
                "        return {}\n"
                "    return action\n",
                encoding="utf-8",
            )
            outside = root / "elsewhere.py"
            outside.write_text(
                "def apply(enabled=False):\n    if enabled: return 1\n",
                encoding="utf-8",
            )
            rel = target.relative_to(root).as_posix()
            findings, errors = guard.scan_paths(
                root,
                [rel, rel, "elsewhere.py", "README.md"],
            )
        self.assertEqual([], errors)
        self.assertEqual(1, len(findings), findings)
        self.assertEqual(rel, findings[0].path)

    def test_unsafe_repo_relative_path_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            findings, errors = guard.scan_paths(Path(td), ["../escape.py"])
        self.assertEqual([], findings)
        self.assertEqual(["unsafe changed path '../escape.py'"], errors)


if __name__ == "__main__":
    unittest.main()
