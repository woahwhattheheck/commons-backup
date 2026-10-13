import subprocess
import sys
import unittest
from pathlib import Path

import pressure_trace_counterexample as pt
from pressure_trace_counterexample import (
    certificate,
    fully_weak_low_degree_witness,
    local_p4_boundary_triangle_witness,
    square_annulus_witness,
)


class PressureTraceCounterexampleTests(unittest.TestCase):
    def test_low_degree_weak_boundary_defect_is_exact(self):
        w = fully_weak_low_degree_witness()
        self.assertEqual(w["velocity_degree"], 0)
        self.assertEqual(w["divergence"], "0")
        self.assertEqual(w["forcing_pairing"], "1")
        self.assertEqual(w["pressure_volume_pairing"], "0")
        self.assertEqual(w["pressure_boundary_flux"], "1")
        self.assertEqual(w["pressure_free_kernel_lhs_at_u_zero"], "0")
        self.assertEqual(w["consistency_defect_lhs_minus_rhs"], "-1")

    def test_p4_compatible_boundary_triangle_is_exactly_divergence_free(self):
        w = local_p4_boundary_triangle_witness()
        self.assertEqual(w["velocity_degree"], 3)
        self.assertTrue(w["contained_in_full_P4_velocity_space"])
        self.assertEqual(w["divergence_polynomial"], {})
        self.assertTrue(w["zero_extension_trace_zero"])

    def test_bad_local_velocities_cannot_mint_positive_certificate(self):
        psi = pt.mul(pt.X, pt.X, pt.Y, pt.Y)
        vx = pt.derivative(psi, "y")
        vy = pt.scale(pt.derivative(psi, "x"), -1)

        with self.assertRaisesRegex(pt.CertificateError, "not divergence-free"):
            pt._certify_local_p4_velocity(pt.add(vx, pt.X), vy)

        bad_trace_psi = pt.add(psi, pt.mul(pt.X, pt.Y))
        bad_trace_vx = pt.derivative(bad_trace_psi, "y")
        bad_trace_vy = pt.scale(pt.derivative(bad_trace_psi, "x"), -1)
        self.assertFalse(
            pt.add(
                pt.derivative(bad_trace_vx, "x"),
                pt.derivative(bad_trace_vy, "y"),
            )
        )
        with self.assertRaisesRegex(pt.CertificateError, "zero vector trace"):
            pt._certify_local_p4_velocity(bad_trace_vx, bad_trace_vy)

    def test_bad_witness_is_rejected_under_real_optimized_python(self):
        module_dir = Path(__file__).resolve().parents[1]
        code = r"""
import pressure_trace_counterexample as pt

if __debug__:
    raise SystemExit("optimized interpreter required")

psi = pt.mul(pt.X, pt.X, pt.Y, pt.Y)
vx = pt.derivative(psi, "y")
vy = pt.scale(pt.derivative(psi, "x"), -1)

try:
    pt._certify_local_p4_velocity(pt.add(vx, pt.X), vy)
except pt.CertificateError:
    pass
else:
    raise SystemExit("non-divergence-free witness was certified")

bad_trace_psi = pt.add(psi, pt.mul(pt.X, pt.Y))
bad_trace_vx = pt.derivative(bad_trace_psi, "y")
bad_trace_vy = pt.scale(pt.derivative(bad_trace_psi, "x"), -1)
try:
    pt._certify_local_p4_velocity(bad_trace_vx, bad_trace_vy)
except pt.CertificateError:
    pass
else:
    raise SystemExit("bad zero-extension trace was certified")

local = pt.local_p4_boundary_triangle_witness()
annulus = pt.square_annulus_witness()
if local["divergence_polynomial"] != {} or not local["zero_extension_trace_zero"]:
    raise SystemExit("local positive certificate changed")
if annulus["divergence_polynomial"] != {} or not annulus["strong_outer_trace_zero"]:
    raise SystemExit("annulus positive certificate changed")
"""
        run = subprocess.run(
            [sys.executable, "-O", "-c", code],
            cwd=module_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            run.returncode,
            0,
            msg=f"optimized hostile failed\nstdout={run.stdout}\nstderr={run.stderr}",
        )

    def test_p4_compatible_boundary_triangle_exposes_pressure_defect(self):
        w = local_p4_boundary_triangle_witness()
        self.assertEqual(w["forcing_pairing"], "1/30")
        self.assertEqual(w["pressure_boundary_flux"], "1/30")
        self.assertEqual(w["pressure_volume_pairing"], "0")
        self.assertEqual(w["pressure_free_kernel_lhs_at_u_zero"], "0")
        self.assertEqual(w["consistency_defect_lhs_minus_rhs"], "-1/30")

    def test_mixed_boundary_witness_has_zero_strong_outer_trace(self):
        w = square_annulus_witness()
        self.assertTrue(w["strong_outer_trace_zero"])
        self.assertEqual(w["velocity_degree"], 8)
        self.assertEqual(w["divergence_polynomial"], {})

    def test_mixed_boundary_pressure_flux_matches_forcing(self):
        w = square_annulus_witness()
        self.assertEqual(w["forcing_pairing"], "-2436/5")
        self.assertEqual(w["pressure_boundary_flux"], "-2436/5")
        self.assertEqual(w["pressure_volume_pairing"], "0")
        self.assertEqual(w["consistency_defect_lhs_minus_rhs"], "2436/5")

    def test_mixed_boundary_edge_flux_partition_is_exact(self):
        w = square_annulus_witness()
        self.assertEqual(
            w["inner_edge_fluxes"],
            {
                "inner_right_x=1": "-162",
                "inner_left_x=-1": "-162",
                "inner_top_y=1": "-816/5",
                "inner_bottom_y=-1": "0",
            },
        )

    def test_certificate_truth_ceiling_stays_partial(self):
        ceiling = certificate()["theorem_ceiling"]
        self.assertIn("does not prove the full prize convergence theorem", ceiling)
        self.assertIn("curved-domain error lower bound", ceiling)


if __name__ == "__main__":
    unittest.main()
