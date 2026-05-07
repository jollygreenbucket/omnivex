import unittest
from unittest.mock import patch

import pandas as pd

from backtest.replay import _download_prices
from backtest.research_replay import (
    RegimeWindow,
    ResearchReplayConfig,
    _build_period_rows,
    run_research_replay_backtest,
    summarize_regimes,
)


class ResearchReplayTests(unittest.TestCase):
    @patch("backtest.replay.yf.download")
    def test_download_prices_handles_single_ticker_multiindex(self, mock_download):
        idx = pd.to_datetime(["2024-04-05", "2024-04-08", "2024-04-12", "2024-04-15"])
        mock_download.return_value = pd.DataFrame(
            {
                ("SPY", "Close"): [100.0, 101.0, 103.0, 104.0],
            },
            index=idx,
        )

        prices = _download_prices(["SPY"], "2024-04-05", "2024-04-12")

        self.assertEqual(prices["SPY"], (101.0, 104.0))

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

    def test_summarize_regimes_builds_segment_metrics(self):
        equity_curve = pd.DataFrame(
            [
                {
                    "run_date": "2022-01-07",
                    "next_run_date": "2022-01-14",
                    "mode": "HEDGE",
                    "holdings": 8,
                    "portfolio_return": -0.02,
                    "benchmark_return": -0.03,
                    "turnover_pct": 40.0,
                },
                {
                    "run_date": "2022-01-14",
                    "next_run_date": "2022-01-21",
                    "mode": "HEDGE",
                    "holdings": 7,
                    "portfolio_return": 0.01,
                    "benchmark_return": -0.01,
                    "turnover_pct": 20.0,
                },
            ]
        )
        windows = (
            RegimeWindow(
                name="test_window",
                start_date="2022-01-01",
                end_date="2022-01-31",
                description="Synthetic test window",
            ),
        )

        summaries = summarize_regimes(equity_curve, windows)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["name"], "test_window")
        self.assertEqual(summaries[0]["periods"], 2)
        self.assertIn("HEDGE", summaries[0]["mode_mix"])


if __name__ == "__main__":
    unittest.main()
