"""
OMNIVEX — Replay Backtest Engine

Replays historical Omnivex runs already stored in Postgres.
This is intentionally conservative: it uses the archived daily runs
that Omnivex actually produced and measures next-period performance
until the next recorded run date.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

import pandas as pd
import yfinance as yf

from data.db_writer import get_connection


@dataclass
class ReplayConfig:
    start_date: str | None = None
    end_date: str | None = None
    top_n: int = 10
    actions: tuple[str, ...] = ("BUY", "ADD")
    weighting: str = "equal"
    benchmark: str = "SPY"


def _load_runs(config: ReplayConfig) -> pd.DataFrame:
    conn = get_connection()
    try:
        conditions = []
        params: list[object] = []
        if config.start_date:
            conditions.append("run_date >= %s")
            params.append(config.start_date)
        if config.end_date:
            conditions.append("run_date <= %s")
            params.append(config.end_date)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT run_date, mode
            FROM runs
            {where}
            ORDER BY run_date ASC
        """
        return pd.read_sql(query, conn, params=params)
    finally:
        conn.close()


def _load_scores(run_date: str, actions: Iterable[str], top_n: int) -> pd.DataFrame:
    conn = get_connection()
    try:
        placeholders = ",".join(["%s"] * len(tuple(actions)))
        query = f"""
            SELECT ticker, action, tier, omnivex_score, suggested_weight_pct
            FROM scores
            WHERE run_date = %s
              AND action IN ({placeholders})
            ORDER BY omnivex_score DESC, suggested_weight_pct DESC NULLS LAST
            LIMIT %s
        """
        params = [run_date, *tuple(actions), top_n]
        return pd.read_sql(query, conn, params=params)
    finally:
        conn.close()


def _download_prices(tickers: list[str], start_date: str, end_date: str) -> dict[str, float]:
    if not tickers:
        return {}

    prices: dict[str, float] = {}
    end_exclusive = (pd.to_datetime(end_date).date() + timedelta(days=1)).isoformat()
    data = yf.download(
        tickers=tickers,
        start=start_date,
        end=end_exclusive,
        progress=False,
        auto_adjust=True,
        group_by="ticker",
        threads=True,
    )

    for ticker in tickers:
        try:
            if len(tickers) == 1:
                close = data["Close"].dropna()
            else:
                close = data[ticker]["Close"].dropna()
            if len(close) >= 2:
                prices[ticker] = float(close.iloc[0]), float(close.iloc[-1])
        except Exception:
            continue

    return prices


def _period_metrics(equity_curve: pd.DataFrame) -> dict[str, float | int | None]:
    if equity_curve.empty:
        return {
            "total_return_pct": None,
            "cagr_pct": None,
            "volatility_pct": None,
            "sharpe": None,
            "max_drawdown_pct": None,
            "periods": 0,
        }

    returns = equity_curve["portfolio_return"].fillna(0.0)
    cumulative = (1 + returns).cumprod()
    total_return = float(cumulative.iloc[-1] - 1)

    periods = len(equity_curve)
    start = pd.to_datetime(equity_curve["run_date"].iloc[0]).date()
    end = pd.to_datetime(equity_curve["next_run_date"].iloc[-1]).date()
    years = max((end - start).days / 365.25, 1 / 365.25)
    cagr = cumulative.iloc[-1] ** (1 / years) - 1 if cumulative.iloc[-1] > 0 else -1

    vol = float(returns.std(ddof=0) * math.sqrt(252)) if periods > 1 else 0.0
    mean_daily = float(returns.mean())
    sharpe = (mean_daily / returns.std(ddof=0) * math.sqrt(252)) if periods > 1 and returns.std(ddof=0) > 0 else 0.0

    running_max = cumulative.cummax()
    drawdown = cumulative / running_max - 1
    max_drawdown = float(drawdown.min())

    return {
        "total_return_pct": round(total_return * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "volatility_pct": round(vol * 100, 2),
        "sharpe": round(float(sharpe), 3),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "periods": periods,
    }


def run_replay_backtest(config: ReplayConfig) -> dict:
    runs = _load_runs(config)
    if len(runs) < 2:
        raise ValueError("Need at least two recorded runs in Postgres to run replay backtest.")

    periods: list[dict] = []
    benchmark_rows: list[dict] = []

    for idx in range(len(runs) - 1):
        run_date = pd.to_datetime(runs.iloc[idx]["run_date"]).date().isoformat()
        next_run_date = pd.to_datetime(runs.iloc[idx + 1]["run_date"]).date().isoformat()
        scores = _load_scores(run_date, config.actions, config.top_n)
        if scores.empty:
            continue

        tickers = scores["ticker"].dropna().astype(str).tolist()
        price_map = _download_prices(tickers, run_date, next_run_date)

        valid_rows = []
        for _, score in scores.iterrows():
            ticker = score["ticker"]
            price_pair = price_map.get(ticker)
            if not price_pair:
                continue
            entry, exit_ = price_pair
            if not entry:
                continue
            ret = (exit_ / entry) - 1
            valid_rows.append(
                {
                    "ticker": ticker,
                    "run_date": run_date,
                    "next_run_date": next_run_date,
                    "entry_price": round(entry, 4),
                    "exit_price": round(exit_, 4),
                    "return_pct": round(ret * 100, 4),
                    "omnivex_score": float(score["omnivex_score"] or 0),
                    "suggested_weight_pct": float(score["suggested_weight_pct"] or 0),
                    "tier": score["tier"],
                    "action": score["action"],
                }
            )

        if not valid_rows:
            continue

        period_df = pd.DataFrame(valid_rows)
        if config.weighting == "score":
            weights = period_df["suggested_weight_pct"].replace(0, 1.0)
            portfolio_return = float((weights * (period_df["return_pct"] / 100)).sum() / weights.sum())
        else:
            portfolio_return = float((period_df["return_pct"] / 100).mean())

        bench_prices = _download_prices([config.benchmark], run_date, next_run_date)
        bench_pair = bench_prices.get(config.benchmark)
        bench_return = ((bench_pair[1] / bench_pair[0]) - 1) if bench_pair else 0.0

        periods.append(
            {
                "run_date": run_date,
                "next_run_date": next_run_date,
                "mode": runs.iloc[idx]["mode"],
                "holdings": len(period_df),
                "portfolio_return": portfolio_return,
                "benchmark_return": bench_return,
            }
        )
        benchmark_rows.extend(valid_rows)

    equity_curve = pd.DataFrame(periods)
    if equity_curve.empty:
        raise ValueError("No valid replay periods could be built from stored runs.")

    equity_curve["equity"] = (1 + equity_curve["portfolio_return"]).cumprod()
    equity_curve["benchmark_equity"] = (1 + equity_curve["benchmark_return"]).cumprod()
    metrics = _period_metrics(equity_curve)

    return {
        "config": config,
        "metrics": metrics,
        "equity_curve": equity_curve,
        "positions": pd.DataFrame(benchmark_rows),
    }


def persist_backtest(result: dict) -> int:
    config: ReplayConfig = result["config"]
    metrics = result["metrics"]
    equity_curve: pd.DataFrame = result["equity_curve"]
    positions: pd.DataFrame = result["positions"]

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO backtest_runs (
                strategy_name, engine, benchmark, start_date, end_date,
                top_n, weighting, total_return_pct, cagr_pct, volatility_pct,
                sharpe, max_drawdown_pct, periods, status, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                "Omnivex Replay",
                "replay",
                config.benchmark,
                equity_curve["run_date"].iloc[0],
                equity_curve["next_run_date"].iloc[-1],
                config.top_n,
                config.weighting,
                metrics["total_return_pct"],
                metrics["cagr_pct"],
                metrics["volatility_pct"],
                metrics["sharpe"],
                metrics["max_drawdown_pct"],
                metrics["periods"],
                "COMPLETED",
                "Replay of recorded Omnivex runs using next-run holding periods.",
            ),
        )
        backtest_id = cur.fetchone()[0]

        curve_rows = [
            (
                backtest_id,
                row.run_date,
                row.next_run_date,
                float(row.equity),
                float(row.benchmark_equity),
                float(row.portfolio_return * 100),
                float(row.benchmark_return * 100),
                row.mode,
                int(row.holdings),
            )
            for row in equity_curve.itertuples(index=False)
        ]
        cur.executemany(
            """
            INSERT INTO backtest_equity_curve (
                backtest_id, run_date, next_run_date, equity, benchmark_equity,
                period_return_pct, benchmark_return_pct, mode, holdings
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            curve_rows,
        )

        position_rows = [
            (
                backtest_id,
                row.run_date,
                row.next_run_date,
                row.ticker,
                row.action,
                row.tier,
                float(row.omnivex_score),
                float(row.suggested_weight_pct),
                float(row.entry_price),
                float(row.exit_price),
                float(row.return_pct),
            )
            for row in positions.itertuples(index=False)
        ]
        cur.executemany(
            """
            INSERT INTO backtest_positions (
                backtest_id, run_date, next_run_date, ticker, action, tier,
                omnivex_score, suggested_weight_pct, entry_price, exit_price, return_pct
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            position_rows,
        )

        conn.commit()
        return backtest_id
    finally:
        conn.close()
