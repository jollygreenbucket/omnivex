"""
OMNIVEX — Research Repository Backtest Engine

Replays synthetic historical Omnivex runs from research_runs/research_scores.
This uses the same selection and execution assumptions as the live replay
engine, but the source data is the synthetic research repository rather than
archived live runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from backtest.replay import _download_prices, _period_metrics
from core.strategy import STRATEGY_VERSION
from data.db_writer import get_connection


@dataclass
class ResearchReplayConfig:
    start_date: str | None = None
    end_date: str | None = None
    top_n: int = 10
    actions: tuple[str, ...] = ("BUY", "ADD")
    weighting: str = "equal"
    benchmark: str = "SPY"
    slippage_bps: float = 10.0
    universe_name: str = "current_static"
    frequency: str = "W-FRI"


@dataclass(frozen=True)
class RegimeWindow:
    name: str
    start_date: str
    end_date: str
    description: str


DEFAULT_REGIME_WINDOWS: tuple[RegimeWindow, ...] = (
    RegimeWindow(
        name="covid_crash",
        start_date="2020-02-14",
        end_date="2020-03-27",
        description="COVID crash and forced de-risking window.",
    ),
    RegimeWindow(
        name="covid_rebound",
        start_date="2020-04-03",
        end_date="2020-08-28",
        description="Post-crash rebound and rapid re-risking window.",
    ),
    RegimeWindow(
        name="inflation_drawdown",
        start_date="2022-01-07",
        end_date="2022-10-14",
        description="Inflation and rate-shock drawdown regime.",
    ),
    RegimeWindow(
        name="ai_concentration",
        start_date="2023-01-06",
        end_date="2024-03-29",
        description="AI-led concentration and mega-cap leadership regime.",
    ),
    RegimeWindow(
        name="rotation_chop",
        start_date="2024-04-05",
        end_date="2025-12-26",
        description="Broad rotation and chop regime after initial AI surge.",
    ),
)


def _load_runs(config: ResearchReplayConfig) -> pd.DataFrame:
    conn = get_connection()
    try:
        conditions = ["universe_name = %s", "frequency = %s"]
        params: list[object] = [config.universe_name, config.frequency]
        if config.start_date:
            conditions.append("as_of_date >= %s")
            params.append(config.start_date)
        if config.end_date:
            conditions.append("as_of_date <= %s")
            params.append(config.end_date)

        query = f"""
            SELECT as_of_date AS run_date, mode
            FROM research_runs
            WHERE {' AND '.join(conditions)}
            ORDER BY as_of_date ASC
        """
        return pd.read_sql(query, conn, params=params)
    finally:
        conn.close()


def _load_scores(run_date: str, config: ResearchReplayConfig, actions: Iterable[str]) -> pd.DataFrame:
    conn = get_connection()
    try:
        placeholders = ",".join(["%s"] * len(tuple(actions)))
        query = f"""
            SELECT rs.ticker, rs.action, rs.tier, rs.omnivex_score, rs.suggested_weight_pct
            FROM research_scores rs
            JOIN research_runs rr ON rr.id = rs.research_run_id
            WHERE rr.as_of_date = %s
              AND rr.universe_name = %s
              AND rr.frequency = %s
              AND rs.action IN ({placeholders})
            ORDER BY rs.omnivex_score DESC, rs.suggested_weight_pct DESC NULLS LAST
            LIMIT %s
        """
        params = [run_date, config.universe_name, config.frequency, *tuple(actions), config.top_n]
        return pd.read_sql(query, conn, params=params)
    finally:
        conn.close()


def _build_period_rows(scores: pd.DataFrame, run_date: str, next_run_date: str, config: ResearchReplayConfig) -> list[dict]:
    tickers = scores["ticker"].dropna().astype(str).tolist()
    price_map = _download_prices(tickers, run_date, next_run_date)

    valid_rows: list[dict] = []
    for _, score in scores.iterrows():
        ticker = score["ticker"]
        price_pair = price_map.get(ticker)
        if not price_pair:
            continue
        entry, exit_ = price_pair
        if not entry:
            continue
        gross_ret = (exit_ / entry) - 1
        slippage = (config.slippage_bps / 10_000) * 2
        net_ret = gross_ret - slippage
        valid_rows.append(
            {
                "ticker": ticker,
                "run_date": run_date,
                "next_run_date": next_run_date,
                "entry_price": round(entry, 4),
                "exit_price": round(exit_, 4),
                "gross_return_pct": round(gross_ret * 100, 4),
                "return_pct": round(net_ret * 100, 4),
                "omnivex_score": float(score["omnivex_score"] or 0),
                "suggested_weight_pct": float(score["suggested_weight_pct"] or 0),
                "tier": score["tier"],
                "action": score["action"],
            }
        )
    return valid_rows


def _regime_metrics(window: RegimeWindow, frame: pd.DataFrame) -> dict:
    segment = frame.copy()
    segment["run_date"] = pd.to_datetime(segment["run_date"])
    mask = (
        (segment["run_date"] >= pd.to_datetime(window.start_date))
        & (segment["run_date"] <= pd.to_datetime(window.end_date))
    )
    segment = segment.loc[mask].copy()
    if segment.empty:
        return {}

    segment["next_run_date"] = pd.to_datetime(segment["next_run_date"]).dt.date.astype(str)
    segment["run_date"] = segment["run_date"].dt.date.astype(str)
    metrics = _period_metrics(segment)
    benchmark_total_return = float((1 + segment["benchmark_return"].fillna(0.0)).cumprod().iloc[-1] - 1)

    return {
        "name": window.name,
        "start_date": window.start_date,
        "end_date": window.end_date,
        "description": window.description,
        "periods": metrics["periods"],
        "total_return_pct": metrics["total_return_pct"],
        "benchmark_return_pct": round(benchmark_total_return * 100, 2),
        "cagr_pct": metrics["cagr_pct"],
        "volatility_pct": metrics["volatility_pct"],
        "sharpe": metrics["sharpe"],
        "max_drawdown_pct": metrics["max_drawdown_pct"],
        "turnover_pct": metrics["turnover_pct"],
        "avg_holdings": round(float(segment["holdings"].mean()), 2),
        "mode_mix": segment["mode"].value_counts().to_dict(),
    }


def summarize_regimes(equity_curve: pd.DataFrame, windows: Iterable[RegimeWindow] = DEFAULT_REGIME_WINDOWS) -> list[dict]:
    summaries: list[dict] = []
    for window in windows:
        metrics = _regime_metrics(window, equity_curve)
        if metrics:
            summaries.append(metrics)
    return summaries


def run_research_replay_backtest(config: ResearchReplayConfig) -> dict:
    runs = _load_runs(config)
    if len(runs) < 2:
        raise ValueError("Need at least two research runs in Postgres to run research replay backtest.")

    periods: list[dict] = []
    position_rows: list[dict] = []
    previous_weights: dict[str, float] = {}
    diagnostics = {
        "total_runs": int(len(runs)),
        "evaluated_periods": 0,
        "empty_score_periods": [],
        "price_drop_periods": [],
        "valid_periods": 0,
    }

    for idx in range(len(runs) - 1):
        run_date = pd.to_datetime(runs.iloc[idx]["run_date"]).date().isoformat()
        next_run_date = pd.to_datetime(runs.iloc[idx + 1]["run_date"]).date().isoformat()
        diagnostics["evaluated_periods"] += 1
        scores = _load_scores(run_date, config, config.actions)
        if scores.empty:
            diagnostics["empty_score_periods"].append(run_date)
            continue

        valid_rows = _build_period_rows(scores, run_date, next_run_date, config)
        if not valid_rows:
            diagnostics["price_drop_periods"].append(
                {
                    "run_date": run_date,
                    "next_run_date": next_run_date,
                    "tickers": scores["ticker"].dropna().astype(str).tolist(),
                }
            )
            continue

        period_df = pd.DataFrame(valid_rows)
        if config.weighting == "score":
            weights = period_df["suggested_weight_pct"].replace(0, 1.0)
            normalized_weights = (weights / weights.sum()).tolist()
            portfolio_return = float((weights * (period_df["return_pct"] / 100)).sum() / weights.sum())
        else:
            normalized_weights = [1 / len(period_df)] * len(period_df)
            portfolio_return = float((period_df["return_pct"] / 100).mean())

        current_weights = {
            row["ticker"]: normalized_weights[i]
            for i, row in enumerate(valid_rows)
        }
        all_tickers = set(previous_weights) | set(current_weights)
        turnover = sum(abs(current_weights.get(ticker, 0.0) - previous_weights.get(ticker, 0.0)) for ticker in all_tickers)
        previous_weights = current_weights

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
                "turnover_pct": turnover * 100,
            }
        )
        diagnostics["valid_periods"] += 1
        position_rows.extend(valid_rows)

    equity_curve = pd.DataFrame(periods)
    if equity_curve.empty:
        first_price_drop = diagnostics["price_drop_periods"][0] if diagnostics["price_drop_periods"] else None
        raise ValueError(
            "No valid replay periods could be built from research runs. "
            f"evaluated={diagnostics['evaluated_periods']} "
            f"empty_scores={len(diagnostics['empty_score_periods'])} "
            f"price_drops={len(diagnostics['price_drop_periods'])} "
            f"first_price_drop={first_price_drop}"
        )

    equity_curve["equity"] = (1 + equity_curve["portfolio_return"]).cumprod()
    equity_curve["benchmark_equity"] = (1 + equity_curve["benchmark_return"]).cumprod()
    metrics = _period_metrics(equity_curve)
    regime_summaries = summarize_regimes(equity_curve)

    return {
        "config": config,
        "metrics": metrics,
        "equity_curve": equity_curve,
        "positions": pd.DataFrame(position_rows),
        "diagnostics": diagnostics,
        "regimes": regime_summaries,
    }


def persist_research_backtest(result: dict) -> int:
    config: ResearchReplayConfig = result["config"]
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
                sharpe, max_drawdown_pct, turnover_pct, periods, status, strategy_version, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                "Omnivex Research Baseline v1",
                "research_replay",
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
                metrics["turnover_pct"],
                metrics["periods"],
                "COMPLETED",
                STRATEGY_VERSION,
                (
                    f"Synthetic research replay from {config.universe_name}/{config.frequency}; "
                    f"top {config.top_n} BUY/ADD names, {config.weighting} weighting, "
                    f"{config.slippage_bps:.0f} bps slippage per side."
                ),
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
