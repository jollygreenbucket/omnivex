"""
OMNIVEX — Finnhub Data Layer
Free tier: 60 API calls/minute
Covers: analyst ratings, insider transactions, earnings surprises

Requires env var: FINNHUB_API_KEY
Get free key at: finnhub.io/register
"""

import os
import requests
import time
from datetime import datetime, timedelta


FINNHUB_BASE = "https://finnhub.io/api/v1"


def _get_key() -> str | None:
    return os.environ.get("FINNHUB_API_KEY")


def _get(endpoint: str, params: dict) -> dict | None:
    key = _get_key()
    if not key:
        return None
    try:
        params["token"] = key
        resp = requests.get(
            f"{FINNHUB_BASE}/{endpoint}",
            params=params,
            timeout=8,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


# ─────────────────────────────────────────────
# ANALYST RATINGS
# ─────────────────────────────────────────────

def get_analyst_events(ticker: str, window_days: int = 10) -> list:
    """
    Pull analyst recommendation changes for a ticker.
    Returns list of dicts formatted for scorer.score_ticker() analyst_events arg.

    Each event: {event_type, source_tier, days_ago}
    event_type: upgrade | downgrade | pt_raise | pt_cut | initiation_buy | initiation_sell
    source_tier: tier1 | tier2 | tier3
    """
    data = _get("stock/recommendation", {"symbol": ticker})
    if not data or not isinstance(data, list):
        return []

    events = []
    cutoff = datetime.today() - timedelta(days=window_days)

    # Finnhub returns monthly aggregates: {period, strongBuy, buy, hold, sell, strongSell}
    # Use most recent two periods to detect direction change
    recent = sorted(data, key=lambda x: x.get("period", ""), reverse=True)[:2]

    if len(recent) >= 2:
        curr = recent[0]
        prev = recent[1]

        curr_bull = curr.get("strongBuy", 0) + curr.get("buy", 0)
        prev_bull = prev.get("strongBuy", 0) + prev.get("buy", 0)
        curr_bear = curr.get("sell", 0) + curr.get("strongSell", 0)
        prev_bear = prev.get("sell", 0) + prev.get("strongSell", 0)

        # Net change in bullish recommendations
        bull_change = curr_bull - prev_bull
        bear_change = curr_bear - prev_bear

        if bull_change >= 3:
            events.append({"event_type": "upgrade", "source_tier": "tier2", "days_ago": 5})
        elif bull_change >= 1:
            events.append({"event_type": "pt_raise", "source_tier": "tier2", "days_ago": 5})
        elif bull_change <= -2:
            events.append({"event_type": "downgrade", "source_tier": "tier2", "days_ago": 5})
        elif bull_change <= -1:
            events.append({"event_type": "pt_cut", "source_tier": "tier2", "days_ago": 5})

    return events


# ─────────────────────────────────────────────
# INSIDER TRANSACTIONS
# ─────────────────────────────────────────────

def get_insider_events(ticker: str, lookback_days: int = 30) -> list:
    """
    Pull insider transactions from Finnhub.
    Returns list of dicts formatted for scorer.score_ticker() insider_events arg.

    Each event: {title, buy_value, is_open_market_buy}
    """
    data = _get("stock/insider-transactions", {"symbol": ticker})
    if not data or "data" not in data:
        return []

    events = []
    cutoff = datetime.today() - timedelta(days=lookback_days)

    qualified_titles = ["CEO", "CFO", "Chairman", "Director", "Chair", "President", "COO"]

    for txn in data.get("data", []):
        # Filter by date
        txn_date_str = txn.get("transactionDate", "")
        try:
            txn_date = datetime.strptime(txn_date_str[:10], "%Y-%m-%d")
            if txn_date < cutoff:
                continue
        except Exception:
            continue

        name = txn.get("name", "")
        title = txn.get("officerTitle", "") or ""
        transaction_type = txn.get("transactionCode", "")
        shares = txn.get("share", 0) or 0
        price = txn.get("transactionPrice", 0) or 0
        value = abs(shares * price)

        # Only open-market buys (code P) and sells (code S)
        if transaction_type not in ("P", "S"):
            continue

        is_qualified = any(t.lower() in title.lower() for t in qualified_titles)
        if not is_qualified:
            continue

        is_buy = transaction_type == "P"
        events.append({
            "title": title or "Director",
            "buy_value": value if is_buy else -value,
            "is_open_market_buy": is_buy,
        })

    return events


# ─────────────────────────────────────────────
# EARNINGS SURPRISE (for PSOS severity)
# ─────────────────────────────────────────────

def get_earnings_surprise_score(ticker: str) -> float:
    """
    Get post-earnings move score (0-100) based on recent earnings surprises.
    Higher = bigger/more consistent earnings beats = higher severity/catalyst.
    """
    data = _get("stock/earnings", {"symbol": ticker, "limit": 4})
    if not data or not isinstance(data, list) or len(data) == 0:
        return 50.0  # neutral

    surprises = []
    for q in data:
        actual = q.get("actual")
        estimate = q.get("estimate")
        if actual is not None and estimate is not None and estimate != 0:
            surprise_pct = abs((actual - estimate) / abs(estimate)) * 100
            surprises.append(surprise_pct)

    if not surprises:
        return 50.0

    avg_surprise = sum(surprises) / len(surprises)

    # Map surprise % to 0-100 score
    if avg_surprise >= 20:
        return 90.0
    elif avg_surprise >= 10:
        return 75.0
    elif avg_surprise >= 5:
        return 60.0
    elif avg_surprise >= 2:
        return 50.0
    else:
        return 35.0


# ─────────────────────────────────────────────
# BATCH FETCH — all data for one ticker
# ─────────────────────────────────────────────

def get_finnhub_data(ticker: str) -> dict:
    """
    Fetch all Finnhub data for a ticker in one call.
    Returns dict with analyst_events, insider_events, earnings_surprise_score.
    Falls back gracefully if API key not set or calls fail.
    """
    if not _get_key():
        return {
            "analyst_events": [],
            "insider_events": [],
            "earnings_surprise_score": 50.0,
            "finnhub_available": False,
        }

    analyst = get_analyst_events(ticker)
    time.sleep(0.1)  # respect rate limit
    insider = get_insider_events(ticker)
    time.sleep(0.1)
    earnings = get_earnings_surprise_score(ticker)

    return {
        "analyst_events": analyst,
        "insider_events": insider,
        "earnings_surprise_score": earnings,
        "finnhub_available": True,
    }
