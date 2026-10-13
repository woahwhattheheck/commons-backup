import unittest
import spawn_steering_oracle as s


class SpawnSteeringTests(unittest.TestCase):
    def test_corner_order_even_board(self):
        self.assertEqual(s.shed_access_tiles(10), ((4,4),(5,4),(4,5),(5,5)))

    def test_spawn_tie_breaks_nwse(self):
        self.assertEqual(s.spawn_index_from_occupancy((0,0,0,0)), 0)
        self.assertEqual(s.spawn_index_from_occupancy((1,0,0,0)), 1)
        self.assertEqual(s.spawn_index_from_occupancy((1,1,0,0)), 2)
        self.assertEqual(s.spawn_index_from_occupancy((1,1,1,0)), 3)
        self.assertEqual(s.spawn_index_from_occupancy((2,2,2,2)), 0)

    def test_minimal_certificates(self):
        expected=((0,0,0,0),(1,0,0,0),(1,1,0,0),(1,1,1,0))
        for target, occ in enumerate(expected):
            self.assertEqual(s.minimal_occupancy_certificate(target), occ)
            self.assertEqual(s.spawn_index_from_occupancy(occ), target)
            self.assertEqual(sum(occ), target)

    def test_one_move_can_force_ne(self):
        r=s.certify_same_callback_steer([[3,4]], [["EAST"]], 1)
        self.assertEqual(r["baseline_index"],0)
        self.assertEqual(r["steered_index"],1)
        self.assertTrue(r["target_reached"])
        self.assertEqual(r["moved_actors"],1)

    def test_two_moves_can_force_sw(self):
        r=s.certify_same_callback_steer([[3,4],[6,4]], [["EAST"],["WEST"]], 2)
        self.assertEqual(r["after_occupancy"],[1,1,0,0])
        self.assertEqual(r["steered_index"],2)

    def test_three_moves_can_force_se(self):
        r=s.certify_same_callback_steer(
            [[3,4],[6,4],[3,5]], [["EAST"],["WEST"],["EAST"]], 3)
        self.assertEqual(r["after_occupancy"],[1,1,1,0])
        self.assertEqual(r["steered_index"],3)

    def test_out_of_bounds_move_matches_engine_noop(self):
        out=s.apply_unit_moves([[0,0]], [["WEST"]])
        self.assertEqual(out,((0,0),))

    def test_non_move_refuses(self):
        with self.assertRaises(s.Refusal):
            s.apply_unit_moves([[4,4]], [["HARVEST"]])

    def test_duplicate_corner_occupancy_counts(self):
        self.assertEqual(s.occupancy_vector([[4,4],[4,4],[5,5]]),(2,0,0,1))
        self.assertEqual(s.spawn_tile([[4,4],[4,4],[5,5]]),(5,4))

    def test_invalid_bool_refuses(self):
        with self.assertRaises(s.Refusal):
            s.spawn_index_from_occupancy((False,0,0,0))

    def test_report_has_no_decision_authority(self):
        fake = b"x"
        old=s.ENGINE_GIT_BLOB
        try:
            s.ENGINE_GIT_BLOB=s.git_blob_id(fake)
            r=s.source_report(fake)
        finally:
            s.ENGINE_GIT_BLOB=old
        self.assertFalse(r["decision_authority"])
        self.assertEqual([x["existing_actors_required"] for x in r["minimal_zero_target_occupancy_certificates"]],
                         [0,1,2,3])


if __name__=="__main__":
    unittest.main()
