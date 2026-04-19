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

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.fetcher import (
    get_ticker_data, get_market_context,
    get_finviz_gainers, get_spy_momentum,
)
from core.scorer import score_ticker
from core.mode_detector import detect_mode, get_target_allocation
from output.reporter import (
    print_terminal_report, write_csv, write_html,
    assign_action, calc_suggested_weight,
)
from core.config import ETF_UNIVERSE, TODAY, CSV_PATH, HTML_PATH


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
        verbose: bool = False):
    """
    Full daily run.
    tickers: override default universe
    portfolio: {TICKER: position_pct} — current holdings
    demo: use tiny universe for fast testing
    """
    universe = tickers or (
        ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"] if demo else DEFAULT_UNIVERSE
    )
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

            result = score_ticker(
                data=data,
                market_ctx=market_ctx,
                spy_momentum=spy_momentum,
                analyst_events=[],   # extend here with real analyst feed
                insider_events=[],   # extend here with real insider feed
            )

            # Assign action + weight
            result["action"] = assign_action(result, portfolio, mode="CORE")
            result["suggested_weight_pct"] = calc_suggested_weight(result)

            scored.append(result)
            time.sleep(0.3)  # rate limit yfinance

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

    # DB — add these lines
    from data.db_writer import write_run
    write_run(mode_result, scored)

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
    args = parser.parse_args()

    results = run(
        tickers=args.tickers,
        demo=args.demo,
        verbose=args.verbose,
    )
