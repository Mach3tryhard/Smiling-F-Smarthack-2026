import unittest

import numpy as np

from evplacement.synthetic.generator import candidate_uplift, generate_city, total_expected_usage
from evplacement.synthetic.model import FEATURES, candidate_incremental, true_portfolio_utility
from evplacement.synthetic.model import _true_greedy


class SyntheticGeneratorTest(unittest.TestCase):
    def test_same_seed_is_reproducible(self):
        a = generate_city(7, n_nodes=180)
        b = generate_city(7, n_nodes=180)
        np.testing.assert_allclose(a.nodes["latent_demand"], b.nodes["latent_demand"])
        np.testing.assert_allclose(a.station_usage, b.station_usage)
        self.assertEqual(len(a.edges), len(b.edges))

    def test_usage_is_positive_and_matches_stations(self):
        city = generate_city(11, n_nodes=220)
        self.assertGreater(len(city.station_nodes), 0)
        self.assertEqual(len(city.station_usage), len(city.station_nodes))
        self.assertTrue(np.all(city.station_usage > 0))

    def test_candidate_uplift_is_non_negative(self):
        city = generate_city(13, n_nodes=180)
        candidates = np.where(city.nodes["is_station"].to_numpy() == 0)[0][:20]
        uplift = candidate_uplift(city, candidates)
        self.assertTrue(np.all(uplift["uplift"] >= 0))
        self.assertGreaterEqual(total_expected_usage(city), 0)

    def test_model_features_do_not_contain_ground_truth(self):
        self.assertNotIn("latent_demand", FEATURES)
        self.assertNotIn("observed_usage", FEATURES)
        self.assertNotIn("is_station", FEATURES)

    def test_vectorised_counterfactual_matches_direct_simulation(self):
        city = generate_city(17, n_nodes=200)
        candidates = np.where(city.nodes["is_station"].to_numpy() == 0)[0][:10]
        vector = candidate_incremental(city, candidates)
        for row in vector.itertuples():
            direct = total_expected_usage(
                city,
                np.append(city.station_nodes, row.node_id),
                np.append(city.station_capacity, 1.0),
            )
            self.assertAlmostEqual(row.total_with_site, direct, places=6)

    def test_true_greedy_improves_true_utility(self):
        city = generate_city(19, n_nodes=220)
        candidates = np.where(city.nodes["is_station"].to_numpy() == 0)[0]
        selected = _true_greedy(city, candidates, 3)
        self.assertGreaterEqual(true_portfolio_utility(city, selected), total_expected_usage(city))


if __name__ == "__main__":
    unittest.main()
