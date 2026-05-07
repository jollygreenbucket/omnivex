import unittest
from unittest.mock import patch

import pandas as pd

from backtest.research_replay import (
    ResearchReplayConfig,
    _build_period_rows,
    run_research_replay_backtest,
)


class ResearchReplayTests(unittest.TestCase):
    def test_build_period_rows_uses_downloaded_prices(self):
        scores = pd.DataFrame(
            [
                {"ticker": "AAA", "action": "BUY", "tier": "SMART_CORE", "omnivex_score": 80, "suggested_weight_pct": 5.0},
                {"ticker": "BBB", "action": "ADD", "tier": "TACTICAL", "omnivex_score": 75, "suggested_weight_pct": 4.0},
            ]
        )
        config = ResearchReplayConfig()
        with patch(
            "backtest.research_replay._download_prices",
            return_value={"AAA": (100.0, 110.0), "BBB": (50.0, 52.0)},
        ):
            rows = _build_period_rows(scores, "2024-11-01", "2024-11-08", config)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["ticker"], "AAA")
        self.assertAlmostEqual(rows[0]["return_pct"], 9.8, places=2)

    def test_research_replay_collects_diagnostics_when_prices_missing(self):
        runs = pd.DataFrame(
            [
                {"run_date": pd.Timestamp("2024-11-01"), "mode": "CORE"},
                {"run_date": pd.Timestamp("2024-11-08"), "mode": "CORE"},
            ]
        )
        scores = pd.DataFrame(
            [
                {"ticker": "AAA", "action": "BUY", "tier": "SMART_CORE", "omnivex_score": 80, "suggested_weight_pct": 5.0},
            ]
        )
        config = ResearchReplayConfig(start_date="2024-11-01", end_date="2024-11-08")

        with patch("backtest.research_replay._load_runs", return_value=runs), patch(
            "backtest.research_replay._load_scores", return_value=scores
        ), patch("backtest.research_replay._download_prices", return_value={}):
            with self.assertRaises(ValueError) as ctx:
                run_research_replay_backtest(config)

        message = str(ctx.exception)
        self.assertIn("price_drops=1", message)
        self.assertIn("AAA", message)


if __name__ == "__main__":
    unittest.main()
