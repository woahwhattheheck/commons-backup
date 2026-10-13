from __future__ import annotations

import unittest

from adapter import (
    BTRACK_UINT32_MAX,
    AdapterError,
    Detection,
    Scale,
    VoxelBounds,
    _positive_btrack_float,
    build_btrack_payload,
    solve_dataset,
)


class AbiRangeTests(unittest.TestCase):
    def test_uint32_time_boundary_is_preserved(self):
        detection = Detection(
            dataset="dataset_a",
            t=BTRACK_UINT32_MAX,
            detection_id=0,
            z=1,
            y=1,
            x=1,
        )
        payload, _ = build_btrack_payload(
            [detection],
            Scale(1.0, 1.0, 1.0),
            VoxelBounds(0, 2, 0, 2, 0, 2),
        )
        self.assertEqual(payload["t"], [BTRACK_UINT32_MAX])

    def test_time_above_uint32_is_rejected_before_tracker_factory(self):
        detection = Detection(
            dataset="dataset_a",
            t=BTRACK_UINT32_MAX + 1,
            detection_id=0,
            z=1,
            y=1,
            x=1,
        )
        factory_called = False

        def forbidden_factory():
            nonlocal factory_called
            factory_called = True
            raise AssertionError("tracker factory must not be reached")

        with self.assertRaisesRegex(AdapterError, "uint32"):
            solve_dataset(
                [detection],
                scale=Scale(1.0, 1.0, 1.0),
                bounds=VoxelBounds(0, 2, 0, 2, 0, 2),
                configuration=object(),
                max_search_radius=1.0,
                tracker_factory=forbidden_factory,
            )
        self.assertFalse(factory_called)

    def test_search_radius_float32_boundary_is_preserved(self):
        float32_max = 3.4028234663852886e38
        self.assertEqual(
            _positive_btrack_float(float32_max, "max_search_radius"),
            float32_max,
        )

    def test_search_radius_float32_overflow_and_underflow_fail_before_tracker_factory(self):
        detection = Detection(
            dataset="dataset_a",
            t=0,
            detection_id=0,
            z=1,
            y=1,
            x=1,
        )
        for radius in (1e39, 1e-50):
            with self.subTest(radius=radius):
                factory_called = False

                def forbidden_factory():
                    nonlocal factory_called
                    factory_called = True
                    raise AssertionError("tracker factory must not be reached")

                with self.assertRaisesRegex(AdapterError, "float32"):
                    solve_dataset(
                        [detection],
                        scale=Scale(1.0, 1.0, 1.0),
                        bounds=VoxelBounds(0, 2, 0, 2, 0, 2),
                        configuration=object(),
                        max_search_radius=radius,
                        tracker_factory=forbidden_factory,
                    )
                self.assertFalse(factory_called)

    def test_scaled_detection_coordinate_must_remain_finite(self):
        detection = Detection(
            dataset="dataset_a",
            t=0,
            detection_id=0,
            z=1,
            y=1,
            x=10**307,
        )
        with self.assertRaisesRegex(AdapterError, "detection 0 x"):
            build_btrack_payload(
                [detection],
                Scale(1.0, 1.0, 100.0),
                VoxelBounds(0, 2, 0, 2, 0, 1e308),
            )

    def test_scaled_volume_endpoint_must_remain_finite(self):
        with self.assertRaisesRegex(AdapterError, "volume zhi"):
            VoxelBounds(0, 1e308, 0, 2, 0, 2).physical_btrack(
                Scale(2.0, 1.0, 1.0)
            )


if __name__ == "__main__":
    unittest.main()
