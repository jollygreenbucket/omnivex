"""
OMNIVEX LEGACY FUND — Daily Tracker
Main runner. Orchestrates full pipeline:
  Data → Score → Mode → Actions → Terminal + CSV + HTML

Usage:
  python run_daily.py
  python run_daily.py --tickers AAPL MSFT NVDA
  python run_daily.py --demo   (uses small test universe, no live data)
"""
from dotenv import load_dotenv
load_dotenv()

import sys
import os
import argparse
import time
import webbrowser

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.fetcher import (
    get_ticker_data, get_market_context,
    get_finviz_gainers, get_spy_momentum,
    build_equity_universe,
)
from data.finnhub import get_finnhub_data
from core.scorer import score_ticker
from core.mode_detector import detect_mode, get_target_allocation
from portfolio.allocator import build_target_portfolio
from output.reporter import (
    print_terminal_report, write_csv, write_html,
    assign_action, calc_suggested_weight,
)
from core.config import ETF_UNIVERSE, ETF_SCAN_UNIVERSE, TODAY, CSV_PATH, HTML_PATH

# ─────────────────────────────────────────────
# DEFAULT UNIVERSE
# ─────────────────────────────────────────────
DEFAULT_UNIVERSE = [
    # ETF core
    "QQQ", "SPY", "ARKK", "XLK", "XLF", "XLV", "XLY", "XLP",
    # Quality compounders (Smart Core candidates)
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "BRK-B", "JNJ",
    "COST", "V", "MA", "UNH", "HD",
    # Tactical / momentum
    "NVDA", "AMD", "TSLA", "PLTR", "CRWD", "PANW",
    # Speculative
    "IONQ", "RKLB",
]


def run(tickers: list = None, portfolio: dict = None, demo: bool = False,
        verbose: bool = False, open_dashboard: bool = True):
    """
    Full daily run.
    tickers: override default universe
    portfolio: {TICKER: position_pct} — current holdings
    demo: use tiny universe for fast testing
    """
    if tickers:
        universe = tickers
    elif demo:
        universe = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
    else:
        # Build dynamic universe from ETF holdings + Finviz screens
        universe = build_equity_universe(
            scan_etfs=ETF_SCAN_UNIVERSE,
            top_n_per_etf=20,
            include_finviz=True,
            target_size=300,
        ) or DEFAULT_UNIVERSE  # fallback if ETF extraction fails
    portfolio = portfolio or {}

    print(f"\n{'─'*55}")
    print(f"  OMNIVEX v2.3 — {TODAY}")
    print(f"  Universe: {len(universe)} tickers")
    print(f"{'─'*55}")

    # ── STEP 1: Market Context ──
    print("\n[1/4] Fetching market context...")
    market_ctx = get_market_context()
    spy_momentum = get_spy_momentum()

    if market_ctx.get("error"):
        print(f"  [WARN] Market context partial: {market_ctx['error']}")

    vix = market_ctx.get("vix", "N/A")
    yc = market_ctx.get("yield_curve_state", "UNKNOWN")
    print(f"  VIX: {vix} | Yield Curve: {yc} | "
          f"SPY 50DMA: {market_ctx.get('spy_above_50dma')} | "
          f"200DMA: {market_ctx.get('spy_above_200dma')}")

    # ── STEP 2: Score Universe ──
    print(f"\n[2/4] Scoring {len(universe)} tickers...")
    scored = []
    failed = []

    for i, ticker in enumerate(universe):
        try:
            sys.stdout.write(f"\r  [{i+1}/{len(universe)}] {ticker:<8}")
            sys.stdout.flush()

            data = get_ticker_data(ticker)

            if data.get("data_quality") == "MISSING":
                failed.append(ticker)
                if verbose:
                    print(f"\n  [SKIP] {ticker}: {data.get('error')}")
                continue

            fh = get_finnhub_data(ticker)
            data["post_earnings_move_score"] = fh["earnings_surprise_score"]
            # Override yfinance values with better Finnhub equivalents where available
            fh_fin = fh.get("financials", {})
            if fh_fin.get("fh_roic") is not None:
                data["roic"] = fh_fin["fh_roic"] / 100  # normalize to decimal
            if fh_fin.get("fh_interest_coverage") is not None:
                data["interest_coverage"] = fh_fin["fh_interest_coverage"]
            if fh_fin.get("fh_peg") is not None:
                data["peg_ratio"] = fh_fin["fh_peg"]
            if fh_fin.get("fh_revenue_growth") is not None:
                data["revenue_growth"] = fh_fin["fh_revenue_growth"] / 100
            if fh_fin.get("fh_rel_strength_13w") is not None:
                data["rel_strength_vs_spy"] = fh_fin["fh_rel_strength_13w"]
            if fh_fin.get("fh_52w_high") is not None:
                data["52w_high"] = fh_fin["fh_52w_high"]
            if fh_fin.get("fh_52w_low") is not None:
                data["52w_low"] = fh_fin["fh_52w_low"]

            scored.append(score_ticker(data, market_ctx, spy_momentum, fh["analyst_events"], fh["insider_events"]))
        except Exception as e:
            failed.append(ticker)
            if verbose:
                            print(f"\n  [ERROR] {ticker}: {e}")

    print(f"\r  Scored: {len(scored)} | Failed/Skipped: {len(failed)}")
    if failed and verbose:
        print(f"  Failed: {', '.join(failed)}")

    # ── STEP 3: Mode Detection ──
    print("\n[3/4] Detecting mode...")
    mode_result = detect_mode(market_ctx, scored)
    mode = mode_result["mode"]
    chop = " + CHOP GUARD" if mode_result.get("chop_guard_active") else ""
    print(f"  Mode: {mode}{chop}")
    print(f"  Omnivex Alpha triggers: {mode_result['alpha_trigger_count']}/6 | "
          f"Omnivex Hedge triggers: {mode_result['hedge_trigger_count']}/5")

    # Re-assign actions with correct mode
    for s in scored:
        s["action"] = assign_action(s, portfolio, mode)
        s["suggested_weight_pct"] = calc_suggested_weight(s, mode)

    # Sort by score descending
    scored.sort(key=lambda x: x.get("omnivex_score", 0), reverse=True)
    portfolio_plan = build_target_portfolio(mode_result, scored)

    # ── STEP 4: Output ──
    print("\n[4/4] Generating outputs...")

    # Terminal
    print_terminal_report(mode_result, scored, portfolio)

    # CSV
    csv_path = write_csv(mode_result, scored)
    print(f"  CSV: {csv_path}")

    # HTML
    html_path = write_html(mode_result, scored)
    print(f"  HTML: {html_path}")
    latest_html_path = os.path.join(os.path.dirname(html_path), "latest.html")

    if open_dashboard and os.path.exists(latest_html_path):
        webbrowser.open(f"file://{os.path.abspath(latest_html_path)}")
        print(f"  Dashboard: {latest_html_path}")

    # DB — add these lines
    from data.db_writer import write_run
    write_run(mode_result, scored, portfolio_plan=portfolio_plan)

    # Summary
    buys = [s for s in scored if s.get("action") in ("BUY", "ADD")]
    reduces = [s for s in scored if s.get("action") in ("REDUCE", "REMOVE")]
    forensic = [s for s in scored if "FORENSIC" in s.get("flags", [])]

    print(f"\n{'─'*55}")
    print(f"  RUN COMPLETE — {TODAY}")
    print(f"  Scored: {len(scored)} | BUY/ADD: {len(buys)} | "
          f"REDUCE/REMOVE: {len(reduces)} | Forensic flags: {len(forensic)}")
    print(f"{'─'*55}\n")

    return {
        "mode": mode_result,
        "scored": scored,
        "portfolio_plan": portfolio_plan,
        "csv_path": csv_path,
        "html_path": html_path,
    }


# ─────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Omnivex Daily")
    parser.add_argument(
        "--tickers", nargs="+",
        help="Override ticker universe (e.g. --tickers AAPL MSFT NVDA)"
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Fast demo mode — small universe"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show detailed errors and skipped tickers"
    )
    parser.add_argument(
        "--no-open", action="store_true",
        help="Do not auto-open reports/latest.html after the run"
    )
    args = parser.parse_args()

    results = run(
        tickers=args.tickers,
        demo=args.demo,
        verbose=args.verbose,
        open_dashboard=not args.no_open,
    )
