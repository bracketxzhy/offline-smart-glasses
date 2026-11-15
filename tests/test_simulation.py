import unittest

from glasses.simulation import simulate


class SimulationTests(unittest.TestCase):
    def test_pipeline_stages_and_workload_weights_are_not_double_counted(self):
        workload = {"object": .5, "face": .25, "complex": .25}
        paths = {"object": {"stages_ms": {"vision": 20, "tts": 5}, "energy_j": .1}, "face": {"stages_ms": {"vision": 30}, "energy_j": .2}, "complex": {"stages_ms": {"vlm": 100}, "energy_j": .3}}
        result = simulate(workload, paths)
        self.assertEqual(result["coverage"], 1)
        self.assertEqual(result["expected_latency_ms"], 45)
        self.assertAlmostEqual(result["expected_energy_j"], .175)

    def test_unsupported_queries_do_not_make_architecture_appear_faster(self):
        result = simulate({"object": .75, "complex": .25}, {"object": {"stages_ms": {"vision": 20}}, "complex": None})
        self.assertEqual(result["coverage"], .75)
        self.assertIsNone(result["expected_latency_ms"])
        self.assertEqual(result["latency_given_supported_ms"], 20)
        self.assertIsNone(result["expected_energy_j"])

    def test_invalid_weights_and_negative_measurements_are_rejected(self):
        for workload, paths in [({"object": .5}, {"object": None}), ({"object": 1}, {"object": {"stages_ms": {"bad": -1}}}), ({"object": 1}, {})]:
            with self.assertRaises(ValueError):
                simulate(workload, paths)


if __name__ == "__main__":
    unittest.main()
