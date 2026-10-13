import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validate_readiness import EXTERNAL_KEYS, RELEASE_KEYS, SCHEMA, validate


def packet(*, release=True, **external_overrides):
    external = {key: False for key in EXTERNAL_KEYS}
    external.update(external_overrides)
    return {
        "schema": SCHEMA,
        "release_gates": {key: release for key in RELEASE_KEYS},
        "external_state": external,
    }


class ReadinessTests(unittest.TestCase):
    def test_checked_in_shape_is_blocked_until_every_release_gate(self):
        state, missing = validate(packet(release=False))
        self.assertEqual(state, "BLOCKED")
        self.assertEqual(set(missing), RELEASE_KEYS)

    def test_all_release_evidence_can_be_ready_without_claiming_submission(self):
        state, missing = validate(packet(release=True))
        self.assertEqual(state, "READY_FOR_OWNER_SUBMISSION")
        self.assertEqual(missing, [])

    def test_submission_cannot_precede_release_evidence(self):
        with self.assertRaisesRegex(ValueError, "release gate"):
            validate(packet(release=False, submitted=True))

    def test_acceptance_cannot_precede_submission(self):
        with self.assertRaisesRegex(ValueError, "organizer_accepted"):
            validate(packet(release=True, organizer_accepted=True))

    def test_prize_cannot_precede_acceptance(self):
        with self.assertRaisesRegex(ValueError, "prize_awarded"):
            validate(packet(release=True, submitted=True, prize_awarded=True))

    def test_payment_cannot_precede_prize(self):
        with self.assertRaisesRegex(ValueError, "payment_received"):
            validate(packet(release=True, submitted=True, organizer_accepted=True, payment_received=True))

    def test_full_monotone_external_state_is_valid(self):
        state, missing = validate(packet(
            release=True,
            submitted=True,
            organizer_accepted=True,
            prize_awarded=True,
            payment_received=True,
        ))
        self.assertEqual(state, "READY_FOR_OWNER_SUBMISSION")
        self.assertEqual(missing, [])

    def test_unknown_key_rejected(self):
        raw = packet(release=False)
        raw["release_gates"]["invented"] = False
        with self.assertRaisesRegex(ValueError, "key mismatch"):
            validate(raw)

    def test_integer_is_not_boolean(self):
        raw = packet(release=False)
        raw["release_gates"][next(iter(RELEASE_KEYS))] = 0
        with self.assertRaisesRegex(ValueError, "booleans"):
            validate(raw)


if __name__ == "__main__":
    unittest.main()
