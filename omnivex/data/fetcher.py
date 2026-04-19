"""
OMNIVEX — Data Ingestion Layer
Pulls from yfinance (primary) with graceful fallback on missing data.
Finviz scraping for gainers/volume leaders.
"""

import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import warnings
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────
# MARKET DATA
# ─────────────────────────────────────────────

def get_ticker_data(ticker: str, period: str = "1y") -> dict:
    """
    Fetch comprehensive data for a single ticker.
    Returns dict with all fields needed for scoring.
    Missing fields return None — caller must handle gracefully.
    """
    result = {
        "ticker": ticker,
        "data_quality": "OK",
        "error": None,
    }

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        hist = t.history(period=period)

        if hist.empty:
            result["data_quality"] = "MISSING"
            result["error"] = "No price history"
            return result

        # ── Price / Technical ──
        close = hist["Close"]
        volume = hist["Volume"]

        result["price"] = round(close.iloc[-1], 2)
        result["prev_close"] = round(close.iloc[-2], 2) if len(close) > 1 else None
        result["daily_return_pct"] = round(
            (close.iloc[-1] / close.iloc[-2] - 1) * 100, 2
        ) if len(close) > 1 else None

        # Moving averages
        result["ma_50"] = round(close.tail(50).mean(), 2) if len(close) >= 50 else None
        result["ma_200"] = round(close.tail(200).mean(), 2) if len(close) >= 200 else None
        result["above_50dma"] = (
            result["price"] > result["ma_50"]
        ) if result["ma_50"] else None
        result["above_200dma"] = (
            result["price"] > result["ma_200"]
        ) if result["ma_200"] else None

        # RSI (14-day)
        result["rsi"] = _calc_rsi(close, 14)

        # ATR (14-day)
        result["atr"] = _calc_atr(hist, 14)
        result["atr_20d_low"] = _is_atr_compressed(hist, 20)

        # Volume
        avg_vol = volume.tail(20).mean()
        result["avg_volume_20d"] = int(avg_vol) if avg_vol else None
        result["volume_today"] = int(volume.iloc[-1]) if not volume.empty else None
        result["volume_ratio"] = round(
            volume.iloc[-1] / avg_vol, 2
        ) if avg_vol and avg_vol > 0 else None

        # Momentum — 3M and 6M relative vs SPY
        result["return_3m"] = _period_return(close, 63)
        result["return_6m"] = _period_return(close, 126)

        # ── Fundamentals (from info) ──
        result["market_cap"] = info.get("marketCap")
        result["sector"] = info.get("sector", "Unknown")
        result["industry"] = info.get("industry", "Unknown")
        result["beta"] = info.get("beta")
        result["pe_ratio"] = info.get("trailingPE") or info.get("forwardPE")
        result["peg_ratio"] = info.get("pegRatio")
        result["gross_margin"] = info.get("grossMargins")
        result["operating_margin"] = info.get("operatingMargins")
        result["revenue_growth"] = info.get("revenueGrowth")  # yoy decimal
        result["earnings_growth"] = info.get("earningsGrowth")
        result["roe"] = info.get("returnOnEquity")
        result["roic"] = info.get("returnOnAssets")  # proxy — true ROIC unavailable in free tier
        result["fcf"] = info.get("freeCashflow")
        result["total_cash"] = info.get("totalCash")
        result["total_debt"] = info.get("totalDebt")
        result["ebitda"] = info.get("ebitda")
        result["interest_expense"] = info.get("interestExpense")
        result["dividend_yield"] = info.get("dividendYield")
        result["institutional_pct"] = (
            info.get("heldPercentInstitutions") or info.get("institutionsPercentHeld")
        )
        result["short_percent"] = info.get("shortPercentOfFloat")
        result["52w_high"] = info.get("fiftyTwoWeekHigh")
        result["52w_low"] = info.get("fiftyTwoWeekLow")

        # Derived — Net Debt / EBITDA
        if result["total_debt"] and result["total_cash"] and result["ebitda"] and result["ebitda"] > 0:
            net_debt = result["total_debt"] - result["total_cash"]
            result["net_debt_ebitda"] = round(net_debt / result["ebitda"], 2)
        else:
            result["net_debt_ebitda"] = None

        # Interest coverage proxy
        if result["ebitda"] and result["interest_expense"] and result["interest_expense"] != 0:
            result["interest_coverage"] = round(
                abs(result["ebitda"] / result["interest_expense"]), 2
            )
        else:
            result["interest_coverage"] = None

        # FCF Yield proxy
        if result["fcf"] and result["market_cap"] and result["market_cap"] > 0:
            result["fcf_yield"] = round(result["fcf"] / result["market_cap"], 4)
        else:
            result["fcf_yield"] = None

        # Earnings date proximity
        result["earnings_date"] = _get_earnings_date(t)
        result["earnings_proximity_days"] = _days_to_earnings(result["earnings_date"])

        # Data quality check
        critical_fields = ["price", "rsi", "pe_ratio", "gross_margin"]
        missing = [f for f in critical_fields if result.get(f) is None]
        if missing:
            result["data_quality"] = "PARTIAL"
            result["missing_fields"] = missing

    except Exception as e:
        result["data_quality"] = "MISSING"
        result["error"] = str(e)

    return result


def get_market_context() -> dict:
    """
    Fetch market-wide context needed for mode detection.
    VIX, SPY moving averages, yield curve, A/D ratio proxy.
    """
    ctx = {}

    try:
        # VIX
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="5d")
        ctx["vix"] = round(vix_hist["Close"].iloc[-1], 2) if not vix_hist.empty else None
        ctx["vix_rising"] = (
            vix_hist["Close"].iloc[-1] > vix_hist["Close"].iloc[-3]
        ) if len(vix_hist) >= 3 else None

        # SPY moving averages
        spy = yf.Ticker("SPY")
        spy_hist = spy.history(period="1y")
        if not spy_hist.empty:
            spy_close = spy_hist["Close"]
            ctx["spy_price"] = round(spy_close.iloc[-1], 2)
            ctx["spy_daily_pct"] = round(
                (spy_close.iloc[-1] / spy_close.iloc[-2] - 1) * 100, 2
            ) if len(spy_close) > 1 else None
            ctx["spy_ma50"] = round(spy_close.tail(50).mean(), 2)
            ctx["spy_ma200"] = round(spy_close.tail(200).mean(), 2)
            ctx["spy_above_50dma"] = spy_close.iloc[-1] > ctx["spy_ma50"]
            ctx["spy_above_200dma"] = spy_close.iloc[-1] > ctx["spy_ma200"]

        # ARKK daily move
        arkk = yf.Ticker("ARKK")
        arkk_hist = arkk.history(period="5d")
        if not arkk_hist.empty and len(arkk_hist) >= 2:
            ctx["arkk_daily_pct"] = round(
                (arkk_hist["Close"].iloc[-1] / arkk_hist["Close"].iloc[-2] - 1) * 100, 2
            )
        else:
            ctx["arkk_daily_pct"] = None

        # Yield curve proxy (2Y vs 10Y)
        try:
            tnx = yf.Ticker("^TNX").history(period="5d")  # 10Y
            irx = yf.Ticker("^IRX").history(period="5d")  # 13-week ~ proxy for short end
            if not tnx.empty and not irx.empty:
                rate_10y = tnx["Close"].iloc[-1]
                rate_2y = irx["Close"].iloc[-1] / 100 * 4  # rough annualized proxy
                ctx["yield_10y"] = round(rate_10y / 100, 4)
                ctx["yield_2y_proxy"] = round(rate_2y, 4)
                ctx["yield_curve_inverted"] = rate_2y > (rate_10y / 100)
                ctx["yield_curve_state"] = "INVERTED" if ctx["yield_curve_inverted"] else "NORMAL"
            else:
                ctx["yield_curve_state"] = "UNKNOWN"
                ctx["yield_curve_inverted"] = False
        except Exception:
            ctx["yield_curve_state"] = "UNKNOWN"
            ctx["yield_curve_inverted"] = False

        # A/D Ratio proxy using broad market breadth ETFs
        # True NYSE A/D not available free — use IWM vs SPY relative strength as proxy
        try:
            iwm = yf.Ticker("IWM").history(period="5d")
            if not iwm.empty and len(iwm) >= 2:
                iwm_ret = iwm["Close"].iloc[-1] / iwm["Close"].iloc[-2] - 1
                spy_ret = (ctx.get("spy_daily_pct", 0) or 0) / 100
                # positive spread = breadth expanding (small caps leading)
                breadth_spread = iwm_ret - spy_ret
                # rough A/D proxy: 1.0 neutral, >1.3 bullish, <0.8 defensive
                ctx["ad_ratio_proxy"] = round(1.0 + (breadth_spread * 10), 2)
            else:
                ctx["ad_ratio_proxy"] = 1.0
        except Exception:
            ctx["ad_ratio_proxy"] = 1.0

    except Exception as e:
        ctx["error"] = str(e)

    return ctx


def get_etf_holdings(etf_ticker: str, top_n: int = 20) -> list:
    """
    Pull top N equity holdings from an ETF via yfinance funds_data.
    Returns list of ticker strings. Falls back gracefully on failure.
    """
    try:
        t = yf.Ticker(etf_ticker)
        # yfinance >= 0.2.28 exposes funds_data.top_holdings
        holdings_df = t.funds_data.top_holdings
        if holdings_df is not None and not holdings_df.empty:
            tickers = holdings_df.index.tolist()[:top_n]
            # Filter out non-equity symbols (bonds, cash, etc.)
            tickers = [
                tk for tk in tickers
                if isinstance(tk, str) and tk.replace("-", "").isalpha() and len(tk) <= 5
            ]
            return tickers
    except Exception:
        pass
    return []


def build_equity_universe(
    scan_etfs: list = None,
    top_n_per_etf: int = 20,
    include_finviz: bool = True,
    min_market_cap: int = 2_000_000_000,
    target_size: int = 150,
) -> list:
    """
    Build a dynamic equity universe from ETF holdings + Finviz screens.

    Process:
      1. Pull top N holdings from each scan ETF
      2. Merge and deduplicate
      3. Add Finviz top gainers and high-volume leaders
      4. Remove the ETF tickers themselves
      5. Cap at target_size (sorted by appearance frequency = conviction)

    Returns deduplicated list of equity tickers.
    """
    from core.config import ETF_SCAN_UNIVERSE

    etfs = scan_etfs or ETF_SCAN_UNIVERSE
    ticker_counts: dict[str, int] = {}

    print(f"  [Universe] Extracting holdings from {len(etfs)} ETFs...")
    for etf in etfs:
        holdings = get_etf_holdings(etf, top_n=top_n_per_etf)
        for tk in holdings:
            ticker_counts[tk] = ticker_counts.get(tk, 0) + 1
        time.sleep(0.2)

    if include_finviz:
        gainers = get_finviz_gainers(top_n=30)
        for tk in gainers:
            ticker_counts[tk] = ticker_counts.get(tk, 0) + 1

    # Remove ETF tickers from equity universe
    all_etf_tickers = set(etfs)
    # Sort by conviction (frequency across ETFs) — most cross-listed = highest conviction
    ranked = sorted(
        [(tk, cnt) for tk, cnt in ticker_counts.items() if tk not in all_etf_tickers],
        key=lambda x: x[1],
        reverse=True,
    )

    universe = [tk for tk, _ in ranked[:target_size]]
    print(f"  [Universe] Built: {len(universe)} tickers "
          f"(from {sum(ticker_counts.values())} raw holdings, "
          f"{len(set(ticker_counts))} unique)")
    return universe


def get_finviz_gainers(top_n: int = 20) -> list:
    """
    Scrape Finviz top gainers.
    Returns list of ticker strings.
    """
    url = "https://finviz.com/screener.ashx?v=111&s=ta_topgainers&f=cap_smallover"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Omnivex/1.0)"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        tickers = []
        for row in soup.select("tr.styled-row"):
            cells = row.find_all("td")
            if cells and len(cells) > 1:
                ticker = cells[1].get_text(strip=True)
                if ticker and ticker.isalpha():
                    tickers.append(ticker)
            if len(tickers) >= top_n:
                break
        return tickers
    except Exception as e:
        print(f"  [WARN] Finviz scrape failed: {e} — using empty list")
        return []


def get_spy_momentum() -> dict:
    """3M and 6M SPY returns for momentum relative scoring."""
    spy = yf.Ticker("SPY").history(period="1y")
    if spy.empty:
        return {"spy_3m": None, "spy_6m": None}
    close = spy["Close"]
    return {
        "spy_3m": _period_return(close, 63),
        "spy_6m": _period_return(close, 126),
    }


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _calc_rsi(close: pd.Series, period: int = 14) -> float | None:
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).tail(period * 2)
    loss = -delta.where(delta < 0, 0.0).tail(period * 2)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean().iloc[-1]
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _calc_atr(hist: pd.DataFrame, period: int = 14) -> float | None:
    if len(hist) < period:
        return None
    high = hist["High"]
    low = hist["Low"]
    close = hist["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return round(tr.tail(period).mean(), 4)


def _is_atr_compressed(hist: pd.DataFrame, days: int = 20) -> bool | None:
    """True if today's ATR is at a 20-day low."""
    if len(hist) < days + 14:
        return None
    atrs = []
    for i in range(days):
        window = hist.iloc[-(days + 14 - i):-(days - i) if (days - i) > 0 else len(hist)]
        atr = _calc_atr(window, 14)
        if atr is not None:
            atrs.append(atr)
    if not atrs:
        return None
    current_atr = _calc_atr(hist.tail(14 + days), 14)
    return current_atr is not None and current_atr <= min(atrs)


def _period_return(close: pd.Series, days: int) -> float | None:
    if len(close) < days:
        return None
    return round((close.iloc[-1] / close.iloc[-days] - 1) * 100, 2)


def _get_earnings_date(ticker_obj) -> str | None:
    try:
        cal = ticker_obj.calendar
        if cal is not None and not cal.empty:
            date_val = cal.columns[0] if hasattr(cal, "columns") else None
            return str(date_val) if date_val else None
    except Exception:
        pass
    return None


def _days_to_earnings(earnings_date_str: str | None) -> int | None:
    if not earnings_date_str:
        return None
    try:
        ed = datetime.strptime(earnings_date_str[:10], "%Y-%m-%d").date()
        return (ed - datetime.today().date()).days
    except Exception:
        return None
