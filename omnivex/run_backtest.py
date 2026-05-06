"""
OMNIVEX — Replay Backtest Runner

Runs a replay backtest from historical Omnivex runs stored in Postgres
and persists the result into the backtest tables.
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv

from backtest.replay import ReplayConfig, persist_backtest, run_replay_backtest


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Omnivex replay backtest")
    parser.add_argument("--start-date", help="Optional YYYY-MM-DD lower bound for replay runs")
    parser.add_argument("--end-date", help="Optional YYYY-MM-DD upper bound for replay runs")
    parser.add_argument("--top-n", type=int, default=10, help="Number of BUY/ADD names to hold per run")
    parser.add_argument(
        "--weighting",
        choices=("equal", "score"),
        default="equal",
        help="Portfolio weighting scheme for selected names",
    )
    parser.add_argument("--benchmark", default="SPY", help="Benchmark ticker")
    args = parser.parse_args()

    config = ReplayConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        top_n=args.top_n,
        weighting=args.weighting,
        benchmark=args.benchmark,
    )
    result = run_replay_backtest(config)
    backtest_id = persist_backtest(result)
    metrics = result["metrics"]

    print("\nOMNIVEX REPLAY BACKTEST")
    print(f"  Backtest ID: {backtest_id}")
    print(f"  Periods:     {metrics['periods']}")
    print(f"  Return:      {metrics['total_return_pct']}%")
    print(f"  CAGR:        {metrics['cagr_pct']}%")
    print(f"  Volatility:  {metrics['volatility_pct']}%")
    print(f"  Sharpe:      {metrics['sharpe']}")
    print(f"  Max DD:      {metrics['max_drawdown_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
