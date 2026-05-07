import unittest
from unittest.mock import patch

import pandas as pd

from research.historical_repository import (
    HistoricalRepositoryConfig,
    _research_run_dates,
    build_historical_repository,
)


class HistoricalRepositoryTests(unittest.TestCase):
    def test_research_run_dates_use_resample_frequency(self):
        idx = pd.date_range("2024-01-01", periods=400, freq="B")
        history_map = {
            "SPY": pd.DataFrame({"Close": range(len(idx))}, index=idx),
        }
        config = HistoricalRepositoryConfig(
            start_date="2024-01-01",
            end_date="2024-12-31",
            frequency="W-FRI",
            max_tickers=5,
        )
        run_dates = _research_run_dates(history_map, config)
        self.assertGreater(len(run_dates), 40)
        self.assertEqual(run_dates[0].weekday(), 4)

    @patch("core.mode_detector.detect_mode")
    @patch("research.historical_repository.assign_action")
    @patch("research.historical_repository.calc_suggested_weight")
    @patch("research.historical_repository._persist_price_cache")
    @patch("research.historical_repository._get_static_fundamentals")
    @patch("research.historical_repository._download_history")
    @patch("research.historical_repository._load_default_universe")
    def test_build_repository_assigns_actions_and_weights(
        self,
        mock_universe,
        mock_history,
        mock_static,
        _mock_cache,
        mock_weight,
        mock_action,
        mock_detect_mode,
    ):
        mock_universe.return_value = ["AAA"]
        idx = pd.date_range("2024-01-01", periods=400, freq="B")
        frame = pd.DataFrame(
            {
                "Open": [100 + i * 0.1 for i in range(len(idx))],
                "High": [101 + i * 0.1 for i in range(len(idx))],
                "Low": [99 + i * 0.1 for i in range(len(idx))],
                "Close": [100 + i * 0.1 for i in range(len(idx))],
                "Volume": [1_000_000] * len(idx),
            },
            index=idx,
        )
        history_map = {
            "AAA": frame,
            "SPY": frame,
            "IWM": frame,
            "ARKK": frame,
            "^VIX": frame,
            "^TNX": frame,
            "^IRX": frame,
        }
        mock_history.return_value = history_map
        mock_static.return_value = {
            "sector": "Technology",
            "industry": "Software",
            "market_cap": 1_000_000_000,
            "beta": 1.2,
            "pe_ratio": 20,
            "peg_ratio": 1.2,
            "gross_margin": 0.45,
            "operating_margin": 0.2,
            "revenue_growth": 0.12,
            "earnings_growth": 0.1,
            "roe": 0.15,
            "roic": 0.1,
            "fcf": 1_000_000,
            "total_cash": 500_000,
            "total_debt": 250_000,
            "ebitda": 800_000,
            "interest_expense": 20_000,
            "institutional_pct": 0.65,
            "short_percent": 0.03,
            "net_debt_ebitda": -0.31,
            "interest_coverage": 40.0,
            "fcf_yield": 0.04,
        }
        mock_action.return_value = "BUY"
        mock_weight.return_value = 5.0
        mock_detect_mode.return_value = {"mode": "CORE"}

        config = HistoricalRepositoryConfig(
            start_date="2024-01-01",
            end_date="2024-12-31",
            max_tickers=1,
        )
        result = build_historical_repository(config)

        self.assertGreater(len(result["runs"]), 0)
        first_score = result["runs"][0]["scores"][0]
        self.assertEqual(first_score["action"], "BUY")
        self.assertEqual(first_score["suggested_weight_pct"], 5.0)


if __name__ == "__main__":
    unittest.main()
