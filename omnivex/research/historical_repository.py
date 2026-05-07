"""
OMNIVEX — Historical Research Repository

Builds a synthetic historical run repository using free data sources.

Important limitation:
    Price/volume and market-regime features are built point-in-time from
    historical bars, but fundamentals and some event fields are sourced from
    current/free snapshots and reused as a static approximation. This is good
    enough for research and ranking exploration, not institutional-grade
    point-in-time testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from core.scorer import score_ticker
from core.strategy import STRATEGY_VERSION
from data.db_writer import get_connection
from data.fetcher import (
    _calc_atr,
    _calc_rsi,
    _gap_count,
    _is_atr_compressed,
    _period_return,
)
from output.reporter import assign_action, calc_suggested_weight

BASE_DIR = Path(__file__).resolve().parents[1]
CACHE_DIR = BASE_DIR / "research_cache"
PRICE_CACHE_DIR = CACHE_DIR / "prices"

MARKET_TICKERS = ["SPY", "IWM", "ARKK", "^VIX", "^TNX", "^IRX"]


@dataclass
class HistoricalRepositoryConfig:
    start_date: str
    end_date: str
    frequency: str = "W-FRI"
    universe_name: str = "current_static"
    max_tickers: int = 75
    use_db_universe: bool = True


def _ensure_cache_dirs() -> None:
    PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _load_default_universe(config: HistoricalRepositoryConfig) -> list[str]:
    if config.use_db_universe:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT ticker, MAX(run_date) AS last_seen
                FROM scores
                GROUP BY ticker
                ORDER BY last_seen DESC, ticker ASC
                LIMIT %s
                """,
                (config.max_tickers,),
            )
            rows = cur.fetchall()
            if rows:
                return [row[0] for row in rows]
        finally:
            conn.close()

    from data.fetcher import build_equity_universe

    return build_equity_universe(target_size=config.max_tickers)[: config.max_tickers]


def _download_history(tickers: list[str], start_date: str, end_date: str) -> dict[str, pd.DataFrame]:
    end_exclusive = (pd.to_datetime(end_date) + timedelta(days=5)).date().isoformat()
    data = yf.download(
        tickers=tickers,
        start=start_date,
        end=end_exclusive,
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )

    history_map: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                frame = data.copy()
            else:
                frame = data[ticker].copy()
            if frame.empty:
                continue
            frame = frame.dropna(how="all")
            frame.index = pd.to_datetime(frame.index)
            history_map[ticker] = frame
        except Exception:
            continue
    return history_map


def _persist_price_cache(history_map: dict[str, pd.DataFrame]) -> None:
    _ensure_cache_dirs()
    for ticker, frame in history_map.items():
        output = PRICE_CACHE_DIR / f"{ticker.replace('^', '_')}.csv"
        frame.to_csv(output)


def _get_static_fundamentals(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}

    total_debt = info.get("totalDebt")
    total_cash = info.get("totalCash")
    ebitda = info.get("ebitda")
    interest_expense = info.get("interestExpense")
    market_cap = info.get("marketCap")
    fcf = info.get("freeCashflow")

    net_debt_ebitda = None
    if total_debt and total_cash is not None and ebitda and ebitda > 0:
        net_debt_ebitda = round((total_debt - total_cash) / ebitda, 2)

    interest_coverage = None
    if ebitda and interest_expense:
        try:
            if interest_expense != 0:
                interest_coverage = round(abs(ebitda / interest_expense), 2)
        except Exception:
            interest_coverage = None

    fcf_yield = None
    if fcf and market_cap:
        try:
            if market_cap > 0:
                fcf_yield = round(fcf / market_cap, 4)
        except Exception:
            fcf_yield = None

    return {
        "sector": info.get("sector", "Unknown"),
        "industry": info.get("industry", "Unknown"),
        "market_cap": market_cap,
        "beta": info.get("beta"),
        "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
        "peg_ratio": info.get("pegRatio"),
        "gross_margin": info.get("grossMargins"),
        "operating_margin": info.get("operatingMargins"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "roe": info.get("returnOnEquity"),
        "roic": info.get("returnOnAssets"),
        "fcf": fcf,
        "total_cash": total_cash,
        "total_debt": total_debt,
        "ebitda": ebitda,
        "interest_expense": interest_expense,
        "institutional_pct": info.get("heldPercentInstitutions") or info.get("institutionsPercentHeld"),
        "short_percent": info.get("shortPercentOfFloat"),
        "net_debt_ebitda": net_debt_ebitda,
        "interest_coverage": interest_coverage,
        "fcf_yield": fcf_yield,
    }


def _snapshot_from_history(ticker: str, history: pd.DataFrame, as_of_date: pd.Timestamp, static: dict) -> dict | None:
    slice_ = history.loc[:as_of_date].copy()
    if len(slice_) < 210:
        return None

    close = slice_["Close"]
    volume = slice_["Volume"]
    price = float(close.iloc[-1])
    avg_volume = float(volume.tail(20).mean()) if len(volume) >= 20 else None

    result = {
        "ticker": ticker,
        "data_quality": "OK",
        "error": None,
        "price": round(price, 2),
        "prev_close": round(float(close.iloc[-2]), 2) if len(close) > 1 else None,
        "daily_return_pct": round((close.iloc[-1] / close.iloc[-2] - 1) * 100, 2) if len(close) > 1 else None,
        "ma_50": round(float(close.tail(50).mean()), 2),
        "ma_200": round(float(close.tail(200).mean()), 2),
        "above_50dma": price > float(close.tail(50).mean()),
        "above_200dma": price > float(close.tail(200).mean()),
        "rsi": _calc_rsi(close, 14),
        "atr": _calc_atr(slice_, 14),
        "atr_20d_low": _is_atr_compressed(slice_, 20),
        "avg_volume_20d": int(avg_volume) if avg_volume else None,
        "volume_today": int(volume.iloc[-1]) if not volume.empty else None,
        "volume_ratio": round(float(volume.iloc[-1]) / avg_volume, 2) if avg_volume and avg_volume > 0 else None,
        "return_1m": _period_return(close, 21),
        "return_3m": _period_return(close, 63),
        "return_6m": _period_return(close, 126),
        "gap_count_20d": _gap_count(slice_, 20),
        "52w_high": round(float(close.tail(252).max()), 2) if len(close) >= 252 else round(float(close.max()), 2),
        "52w_low": round(float(close.tail(252).min()), 2) if len(close) >= 252 else round(float(close.min()), 2),
        "earnings_date": None,
        "earnings_proximity_days": None,
        "post_earnings_move_score": 50.0,
        **static,
    }

    return result


def _market_context_from_history(history_map: dict[str, pd.DataFrame], as_of_date: pd.Timestamp) -> dict:
    ctx: dict[str, object] = {}

    vix = history_map.get("^VIX")
    spy = history_map.get("SPY")
    iwm = history_map.get("IWM")
    arkk = history_map.get("ARKK")
    tnx = history_map.get("^TNX")
    irx = history_map.get("^IRX")

    if vix is not None:
        vix_slice = vix.loc[:as_of_date]["Close"].dropna()
        if len(vix_slice) >= 3:
            ctx["vix"] = round(float(vix_slice.iloc[-1]), 2)
            ctx["vix_rising"] = bool(vix_slice.iloc[-1] > vix_slice.iloc[-3])

    if spy is not None:
        spy_close = spy.loc[:as_of_date]["Close"].dropna()
        if len(spy_close) >= 200:
            ma50 = float(spy_close.tail(50).mean())
            ma200 = float(spy_close.tail(200).mean())
            ctx["spy_price"] = round(float(spy_close.iloc[-1]), 2)
            ctx["spy_daily_pct"] = round(float((spy_close.iloc[-1] / spy_close.iloc[-2] - 1) * 100), 2)
            ctx["spy_ma50"] = round(ma50, 2)
            ctx["spy_ma200"] = round(ma200, 2)
            ctx["spy_above_50dma"] = bool(spy_close.iloc[-1] > ma50)
            ctx["spy_above_200dma"] = bool(spy_close.iloc[-1] > ma200)

    if arkk is not None:
        arkk_close = arkk.loc[:as_of_date]["Close"].dropna()
        if len(arkk_close) >= 2:
            ctx["arkk_daily_pct"] = round(float((arkk_close.iloc[-1] / arkk_close.iloc[-2] - 1) * 100), 2)

    if tnx is not None and irx is not None:
        tnx_close = tnx.loc[:as_of_date]["Close"].dropna()
        irx_close = irx.loc[:as_of_date]["Close"].dropna()
        if not tnx_close.empty and not irx_close.empty:
            rate_10y = float(tnx_close.iloc[-1]) / 100
            short_proxy = float(irx_close.iloc[-1]) / 100 * 4
            ctx["yield_10y"] = round(rate_10y, 4)
            ctx["yield_short_end_proxy"] = round(short_proxy, 4)
            ctx["yield_curve_inverted"] = bool(short_proxy > rate_10y)
            ctx["yield_curve_state"] = "INVERTED" if short_proxy > rate_10y else "NORMAL"

    if iwm is not None and spy is not None:
        iwm_close = iwm.loc[:as_of_date]["Close"].dropna()
        spy_close = spy.loc[:as_of_date]["Close"].dropna()
        if len(iwm_close) >= 2 and len(spy_close) >= 2:
            iwm_ret = float(iwm_close.iloc[-1] / iwm_close.iloc[-2] - 1)
            spy_ret = float(spy_close.iloc[-1] / spy_close.iloc[-2] - 1)
            ctx["ad_ratio_proxy"] = round(1.0 + ((iwm_ret - spy_ret) * 10), 2)

    return ctx


def _spy_momentum_from_history(history_map: dict[str, pd.DataFrame], as_of_date: pd.Timestamp) -> dict:
    spy = history_map.get("SPY")
    if spy is None:
        return {"spy_3m": None, "spy_6m": None}
    close = spy.loc[:as_of_date]["Close"].dropna()
    return {
        "spy_3m": _period_return(close, 63),
        "spy_6m": _period_return(close, 126),
    }


def _research_run_dates(history_map: dict[str, pd.DataFrame], config: HistoricalRepositoryConfig) -> list[pd.Timestamp]:
    spy = history_map.get("SPY")
    if spy is None or spy.empty:
        return []
    close = spy.loc[config.start_date:config.end_date]["Close"].dropna()
    if close.empty:
        return []
    return list(close.resample(config.frequency).last().dropna().index)


def persist_historical_repository(result: dict) -> None:
    for run in result["runs"]:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO research_runs (
                    as_of_date, frequency, universe_name, ticker_count, mode,
                    source_note, strategy_version
                ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (as_of_date, universe_name, frequency) DO UPDATE SET
                    ticker_count = EXCLUDED.ticker_count,
                    mode = EXCLUDED.mode,
                    source_note = EXCLUDED.source_note,
                    strategy_version = EXCLUDED.strategy_version,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    run["as_of_date"],
                    result["config"].frequency,
                    result["config"].universe_name,
                    run["ticker_count"],
                    run["mode"],
                    run["source_note"],
                    STRATEGY_VERSION,
                ),
            )
            research_run_id = cur.fetchone()[0]
            cur.execute("DELETE FROM research_scores WHERE research_run_id = %s", (research_run_id,))

            score_rows = [
                (
                    research_run_id,
                    run["as_of_date"],
                    row["ticker"],
                    row.get("sector"),
                    row.get("tier"),
                    row.get("omnivex_score"),
                    row.get("qtech"),
                    row.get("psos"),
                    row.get("signal_confidence"),
                    row.get("action"),
                    row.get("suggested_weight_pct"),
                    "|".join(row.get("flags", [])),
                    row.get("data_quality"),
                    row.get("price"),
                    row.get("return_1m"),
                    row.get("return_3m"),
                    row.get("return_6m"),
                    row.get("volume_ratio"),
                )
                for row in run["scores"]
            ]
            cur.executemany(
                """
                INSERT INTO research_scores (
                    research_run_id, as_of_date, ticker, sector, tier,
                    omnivex_score, qtech, psos, signal_conf, action,
                    suggested_weight_pct, flags, data_quality, price,
                    return_1m, return_3m, return_6m, volume_ratio
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                score_rows,
            )

            conn.commit()
        finally:
            conn.close()


def build_historical_repository(config: HistoricalRepositoryConfig) -> dict:
    universe = _load_default_universe(config)
    all_tickers = sorted(set(universe + MARKET_TICKERS))
    history_map = _download_history(all_tickers, config.start_date, config.end_date)
    _persist_price_cache({ticker: frame for ticker, frame in history_map.items() if ticker in universe})

    static_map = {ticker: _get_static_fundamentals(ticker) for ticker in universe}
    run_dates = _research_run_dates(history_map, config)
    runs: list[dict] = []

    for as_of_date in run_dates:
        market_ctx = _market_context_from_history(history_map, as_of_date)
        spy_momentum = _spy_momentum_from_history(history_map, as_of_date)
        scores: list[dict] = []

        for ticker in universe:
            history = history_map.get(ticker)
            static = static_map.get(ticker, {})
            if history is None:
                continue
            snapshot = _snapshot_from_history(ticker, history, as_of_date, static)
            if not snapshot:
                continue
            scored = score_ticker(snapshot, market_ctx, spy_momentum, analyst_events=[], insider_events=[])
            scores.append(scored)

        if not scores:
            continue

        scores.sort(key=lambda row: row.get("omnivex_score", 0), reverse=True)
        mode = "CORE"
        mode_result = {"mode": "CORE"}
        try:
            from core.mode_detector import detect_mode

            mode_result = detect_mode(market_ctx, scores)
            mode = mode_result.get("mode", "CORE")
        except Exception:
            mode = "CORE"
            mode_result = {"mode": "CORE"}

        for scored in scores:
            scored["action"] = assign_action(scored, portfolio={}, mode=mode)
            scored["suggested_weight_pct"] = calc_suggested_weight(scored, mode)

        runs.append(
            {
                "as_of_date": as_of_date.date().isoformat(),
                "mode": mode,
                "ticker_count": len(scores),
                "source_note": (
                    "Historical bars are point-in-time; fundamentals are static/current "
                    "free-source approximations."
                ),
                "scores": scores,
            }
        )

    return {
        "config": config,
        "universe": universe,
        "run_dates": [d.date().isoformat() for d in run_dates],
        "runs": runs,
        "cache_dir": str(CACHE_DIR),
    }
