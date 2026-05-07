"""
OMNIVEX — Research Replay Backtest Runner

Runs a backtest against synthetic historical runs stored in
research_runs/research_scores and persists the result into backtest tables.
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv

from backtest.research_replay import (
    ResearchReplayConfig,
    persist_research_backtest,
    run_research_replay_backtest,
)


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Omnivex research replay backtest")
    parser.add_argument("--start-date", help="Optional YYYY-MM-DD lower bound for research runs")
    parser.add_argument("--end-date", help="Optional YYYY-MM-DD upper bound for research runs")
    parser.add_argument("--top-n", type=int, default=10, help="Number of BUY/ADD names to hold per run")
    parser.add_argument(
        "--weighting",
        choices=("equal", "score"),
        default="equal",
        help="Portfolio weighting scheme for selected names",
    )
    parser.add_argument("--benchmark", default="SPY", help="Benchmark ticker")
    parser.add_argument("--slippage-bps", type=float, default=10.0, help="Slippage per side in basis points")
    parser.add_argument("--universe-name", default="current_static", help="Research universe label")
    parser.add_argument("--frequency", default="W-FRI", help="Research run frequency label")
    args = parser.parse_args()

    config = ResearchReplayConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        top_n=args.top_n,
        weighting=args.weighting,
        benchmark=args.benchmark,
        slippage_bps=args.slippage_bps,
        universe_name=args.universe_name,
        frequency=args.frequency,
    )

    result = run_research_replay_backtest(config)
    backtest_id = persist_research_backtest(result)
    metrics = result["metrics"]

    print("\nOMNIVEX RESEARCH REPLAY BACKTEST")
    print(f"  Backtest ID:  {backtest_id}")
    print(f"  Periods:      {metrics['periods']}")
    print(f"  Return:       {metrics['total_return_pct']}%")
    print(f"  CAGR:         {metrics['cagr_pct']}%")
    print(f"  Volatility:   {metrics['volatility_pct']}%")
    print(f"  Sharpe:       {metrics['sharpe']}")
    print(f"  Max DD:       {metrics['max_drawdown_pct']}%")
    print(f"  Turnover:     {metrics['turnover_pct']}% avg/rebalance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
