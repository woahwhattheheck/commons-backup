import unittest

from validate_readiness import REQUIRED_EXTERNAL, validate


class ReadinessTests(unittest.TestCase):
    def test_checked_in_shape_is_blocked(self):
        data = {"submission_state": "BLOCKED", **{key: False for key in REQUIRED_EXTERNAL}}
        ready, missing = validate(data)
        self.assertFalse(ready)
        self.assertEqual(set(missing), set(REQUIRED_EXTERNAL))

    def test_false_ready_claim_is_rejected(self):
        data = {"submission_state": "READY", **{key: False for key in REQUIRED_EXTERNAL}}
        ready, errors = validate(data)
        self.assertFalse(ready)
        self.assertIn("submission_state must remain BLOCKED while external gates are incomplete", errors)

    def test_all_gates_can_become_ready(self):
        data = {"submission_state": "READY", **{key: True for key in REQUIRED_EXTERNAL}}
        ready, missing = validate(data)
        self.assertTrue(ready)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
