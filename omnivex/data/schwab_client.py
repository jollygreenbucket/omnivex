"""
OMNIVEX — Schwab API Client
OAuth2 + account data via schwab-py.

First-time setup (run once locally):
  python -m omnivex.data.schwab_client --auth

After that, the token is saved to SCHWAB_TOKEN_PATH and refreshes automatically.

Required env vars:
  SCHWAB_API_KEY       — from developer.schwab.com app
  SCHWAB_API_SECRET    — from developer.schwab.com app
  SCHWAB_TOKEN_PATH    — path to token JSON file (default: ~/.omnivex_schwab_token.json)
  SCHWAB_ACCOUNT_HASH  — account hash (printed on first auth, save it)
"""

import os
import json
from pathlib import Path


def _get_client():
    """Return an authenticated schwab-py client."""
    try:
        import schwab
    except ImportError:
        raise ImportError(
            "schwab-py not installed. Run: pip install schwab-py"
        )

    api_key    = os.environ.get("SCHWAB_API_KEY")
    api_secret = os.environ.get("SCHWAB_API_SECRET")
    token_path = os.environ.get(
        "SCHWAB_TOKEN_PATH",
        str(Path.home() / ".omnivex_schwab_token.json")
    )

    if not api_key or not api_secret:
        raise EnvironmentError(
            "SCHWAB_API_KEY and SCHWAB_API_SECRET must be set."
        )

    return schwab.auth.client_from_token_file(
        token_path=token_path,
        api_key=api_key,
        app_secret=api_secret,
    )


def run_auth_flow():
    """
    One-time OAuth2 browser flow. Run locally to generate token file.
    Token auto-refreshes on subsequent runs.
    """
    try:
        import schwab
    except ImportError:
        raise ImportError("schwab-py not installed. Run: pip install schwab-py")

    api_key    = os.environ.get("SCHWAB_API_KEY")
    api_secret = os.environ.get("SCHWAB_API_SECRET")
    token_path = os.environ.get(
        "SCHWAB_TOKEN_PATH",
        str(Path.home() / ".omnivex_schwab_token.json")
    )
    callback_url = os.environ.get(
        "SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182"
    )

    if not api_key or not api_secret:
        raise EnvironmentError(
            "Set SCHWAB_API_KEY and SCHWAB_API_SECRET before running auth."
        )

    schwab.auth.client_from_login_flow(
        api_key=api_key,
        app_secret=api_secret,
        callback_url=callback_url,
        token_path=token_path,
    )
    print(f"  [Schwab] Token saved to {token_path}")
    print("  [Schwab] Set SCHWAB_TOKEN_PATH to this path in your env.")


# ─────────────────────────────────────────────
# ACCOUNT DATA
# ─────────────────────────────────────────────

def get_account_hash() -> str:
    """Return the encrypted account hash for the first linked account."""
    client = _get_client()
    resp = client.get_account_numbers()
    resp.raise_for_status()
    accounts = resp.json()
    if not accounts:
        raise ValueError("No accounts found on this Schwab login.")
    account_hash = accounts[0]["hashValue"]
    print(f"  [Schwab] Account hash: {account_hash}")
    print("  [Schwab] Save this as SCHWAB_ACCOUNT_HASH in your env.")
    return account_hash


def get_positions() -> list:
    """
    Fetch current positions from Schwab.
    Returns list of dicts with standardized field names.
    """
    client = _get_client()
    account_hash = os.environ.get("SCHWAB_ACCOUNT_HASH")
    if not account_hash:
        raise EnvironmentError("SCHWAB_ACCOUNT_HASH not set.")

    resp = client.get_account(
        account_hash,
        fields=[client.Account.Fields.POSITIONS]
    )
    resp.raise_for_status()
    data = resp.json()

    raw_positions = (
        data.get("securitiesAccount", {}).get("positions", [])
    )

    positions = []
    for p in raw_positions:
        instrument = p.get("instrument", {})
        asset_type = instrument.get("assetType", "")
        if asset_type != "EQUITY":
            continue

        positions.append({
            "ticker":              instrument.get("symbol"),
            "shares":              p.get("longQuantity", 0),
            "avg_cost":            p.get("averagePrice"),
            "current_price":       p.get("marketValue", 0) / p.get("longQuantity", 1)
                                   if p.get("longQuantity") else None,
            "market_value":        p.get("marketValue"),
            "unrealized_pnl":      p.get("currentDayProfitLoss"),
            "unrealized_pnl_pct":  p.get("currentDayProfitLossPercentage"),
        })

    return positions


def get_account_balance() -> dict:
    """Return cash balance and total account value."""
    client = _get_client()
    account_hash = os.environ.get("SCHWAB_ACCOUNT_HASH")
    if not account_hash:
        raise EnvironmentError("SCHWAB_ACCOUNT_HASH not set.")

    resp = client.get_account(account_hash, fields=[])
    resp.raise_for_status()
    data = resp.json()

    balances = data.get("securitiesAccount", {}).get("currentBalances", {})
    return {
        "cash":        balances.get("cashBalance", 0),
        "total_value": balances.get("liquidationValue", 0),
        "buying_power": balances.get("buyingPower", 0),
    }


def get_order_history(days: int = 30) -> list:
    """Fetch filled orders from the last N days."""
    from datetime import datetime, timedelta, timezone

    client = _get_client()
    account_hash = os.environ.get("SCHWAB_ACCOUNT_HASH")
    if not account_hash:
        raise EnvironmentError("SCHWAB_ACCOUNT_HASH not set.")

    from_dt = datetime.now(timezone.utc) - timedelta(days=days)
    to_dt   = datetime.now(timezone.utc)

    resp = client.get_orders_for_account(
        account_hash,
        from_entered_datetime=from_dt,
        to_entered_datetime=to_dt,
        status=client.Order.Status.FILLED,
    )
    resp.raise_for_status()
    orders = resp.json()

    trades = []
    for o in orders:
        legs = o.get("orderLegCollection", [])
        for leg in legs:
            instrument = leg.get("instrument", {})
            if instrument.get("assetType") != "EQUITY":
                continue
            activity = o.get("orderActivityCollection", [{}])[0]
            trades.append({
                "trade_date":  o.get("closeTime", o.get("enteredTime", ""))[:10],
                "ticker":      instrument.get("symbol"),
                "action":      leg.get("instruction", ""),   # BUY / SELL
                "shares":      leg.get("quantity", 0),
                "price":       activity.get("executionLegs", [{}])[0].get("price"),
                "total_value": o.get("price", 0) * leg.get("quantity", 0),
            })

    return trades


# ─────────────────────────────────────────────
# QUOTE DATA (replaces yfinance for live prices)
# ─────────────────────────────────────────────

def get_quotes(tickers: list) -> dict:
    """
    Fetch real-time quotes for a list of tickers.
    Returns {ticker: {price, change_pct, volume}} dict.
    """
    client = _get_client()
    resp = client.get_quotes(tickers)
    resp.raise_for_status()
    raw = resp.json()

    quotes = {}
    for ticker, data in raw.items():
        q = data.get("quote", {})
        quotes[ticker] = {
            "price":      q.get("lastPrice") or q.get("mark"),
            "change_pct": q.get("netPercentChangeInDouble"),
            "volume":     q.get("totalVolume"),
            "bid":        q.get("bidPrice"),
            "ask":        q.get("askPrice"),
        }
    return quotes


if __name__ == "__main__":
    import sys
    if "--auth" in sys.argv:
        run_auth_flow()
    elif "--account" in sys.argv:
        get_account_hash()
    else:
        print("Usage:")
        print("  python -m data.schwab_client --auth      # First-time OAuth flow")
        print("  python -m data.schwab_client --account   # Print account hash")
