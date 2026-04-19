"""
OMNIVEX — Schwab → Neon Sync
Pulls live positions, balance, and order history from Schwab
and writes them to the Neon portfolio tables.

Run after market close alongside run_daily.py, or on demand:
  python schwab_sync.py
  python schwab_sync.py --positions-only
  python schwab_sync.py --trades-only
"""

import os
import argparse
from datetime import date, datetime

from data.schwab_client import get_positions, get_account_balance, get_order_history
from data.db_writer import get_connection


# ─────────────────────────────────────────────
# SYNC POSITIONS → holdings table
# ─────────────────────────────────────────────

def sync_positions(tier_map: dict = None) -> int:
    """
    Pull positions from Schwab and upsert into holdings table.
    tier_map: {ticker: tier} — optional override, else uses latest scores from DB.
    Returns number of positions synced.
    """
    positions = get_positions()
    if not positions:
        print("  [Schwab Sync] No equity positions found.")
        return 0

    conn = get_connection()
    cur  = conn.cursor()

    # Pull current tier assignments from latest scores if not provided
    if tier_map is None:
        cur.execute("""
            SELECT ticker, tier FROM scores
            WHERE run_date = (SELECT MAX(run_date) FROM runs)
        """)
        tier_map = {row[0]: row[1] for row in cur.fetchall()}

    for p in positions:
        ticker = p["ticker"]
        tier   = tier_map.get(ticker, "MONITOR")

        cur.execute("""
            INSERT INTO holdings (
                ticker, shares, avg_cost, current_price,
                market_value, unrealized_pnl, unrealized_pnl_pct,
                tier, updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s, NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                shares             = EXCLUDED.shares,
                current_price      = EXCLUDED.current_price,
                market_value       = EXCLUDED.market_value,
                unrealized_pnl     = EXCLUDED.unrealized_pnl,
                unrealized_pnl_pct = EXCLUDED.unrealized_pnl_pct,
                tier               = EXCLUDED.tier,
                updated_at         = NOW()
        """, (
            ticker,
            p["shares"],
            p["avg_cost"],
            p["current_price"],
            p["market_value"],
            p["unrealized_pnl"],
            p["unrealized_pnl_pct"],
        ))

    conn.commit()
    cur.close()
    conn.close()

    print(f"  [Schwab Sync] ✓ Holdings synced — {len(positions)} positions")
    return len(positions)


# ─────────────────────────────────────────────
# SYNC TRADES → trades table
# ─────────────────────────────────────────────

def sync_trades(days: int = 7) -> int:
    """
    Pull recent filled orders from Schwab and insert into trades table.
    Skips duplicates via (trade_date, ticker, action, shares) uniqueness check.
    Returns number of new trades inserted.
    """
    orders = get_order_history(days=days)
    if not orders:
        print(f"  [Schwab Sync] No filled orders in last {days} days.")
        return 0

    conn = get_connection()
    cur  = conn.cursor()

    # Pull latest scores for omnivex_score + tier at time of trade
    cur.execute("""
        SELECT ticker, omnivex_score, tier, mode
        FROM scores s
        JOIN runs r ON s.run_date = r.run_date
        WHERE s.run_date = (SELECT MAX(run_date) FROM runs)
    """)
    score_map = {row[0]: {"score": row[1], "tier": row[2], "mode": row[3]}
                 for row in cur.fetchall()}

    inserted = 0
    for t in orders:
        ticker = t["ticker"]
        meta   = score_map.get(ticker, {})

        # Normalize action: Schwab uses BUY/SELL → our schema uses BUY/REDUCE
        action = t["action"].upper()
        if action == "SELL":
            action = "REDUCE"

        # Skip if already recorded
        cur.execute("""
            SELECT 1 FROM trades
            WHERE trade_date = %s AND ticker = %s
              AND action = %s AND shares = %s
        """, (t["trade_date"], ticker, action, t["shares"]))

        if cur.fetchone():
            continue

        cur.execute("""
            INSERT INTO trades (
                trade_date, ticker, action, shares, price,
                total_value, omnivex_score, tier, mode
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            t["trade_date"],
            ticker,
            action,
            t["shares"],
            t["price"],
            t["total_value"],
            meta.get("score"),
            meta.get("tier"),
            meta.get("mode"),
        ))
        inserted += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"  [Schwab Sync] ✓ Trades synced — {inserted} new records")
    return inserted


# ─────────────────────────────────────────────
# SYNC SNAPSHOT → portfolio_snapshots table
# ─────────────────────────────────────────────

def sync_snapshot() -> bool:
    """
    Write today's portfolio snapshot (total value, cash, tier breakdown).
    """
    balance   = get_account_balance()
    positions = get_positions()

    total_value    = balance.get("total_value", 0)
    cash           = balance.get("cash", 0)
    invested_value = total_value - cash

    # Tier breakdown
    conn = get_connection()
    cur  = conn.cursor()

    cur.execute("""
        SELECT ticker, tier FROM scores
        WHERE run_date = (SELECT MAX(run_date) FROM runs)
    """)
    tier_map = {row[0]: row[1] for row in cur.fetchall()}

    tier_values = {"SMART_CORE": 0, "TACTICAL": 0, "SPECULATIVE": 0}
    for p in positions:
        tier = tier_map.get(p["ticker"], "OTHER")
        if tier in tier_values:
            tier_values[tier] += p.get("market_value", 0)

    def pct(v):
        return round(v / total_value, 4) if total_value else 0

    # Pull SPY daily pct from latest run
    cur.execute("SELECT spy_daily_pct, mode FROM runs ORDER BY run_date DESC LIMIT 1")
    row = cur.fetchone()
    spy_daily_pct = row[0] if row else None
    mode          = row[1] if row else "CORE"

    today = date.today().isoformat()
    cur.execute("""
        INSERT INTO portfolio_snapshots (
            snapshot_date, total_value, cash, invested_value,
            spy_daily_pct, smart_core_pct, tactical_pct,
            speculative_pct, cash_pct, mode
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (snapshot_date) DO UPDATE SET
            total_value     = EXCLUDED.total_value,
            cash            = EXCLUDED.cash,
            invested_value  = EXCLUDED.invested_value,
            spy_daily_pct   = EXCLUDED.spy_daily_pct,
            smart_core_pct  = EXCLUDED.smart_core_pct,
            tactical_pct    = EXCLUDED.tactical_pct,
            speculative_pct = EXCLUDED.speculative_pct,
            cash_pct        = EXCLUDED.cash_pct,
            mode            = EXCLUDED.mode
    """, (
        today,
        total_value,
        cash,
        invested_value,
        spy_daily_pct,
        pct(tier_values["SMART_CORE"]),
        pct(tier_values["TACTICAL"]),
        pct(tier_values["SPECULATIVE"]),
        pct(cash),
        mode,
    ))

    conn.commit()
    cur.close()
    conn.close()

    print(f"  [Schwab Sync] ✓ Snapshot written — ${total_value:,.0f} total, "
          f"${cash:,.0f} cash")
    return True


# ─────────────────────────────────────────────
# FULL SYNC
# ─────────────────────────────────────────────

def run_full_sync(trades_days: int = 7) -> dict:
    """Run positions + trades + snapshot sync. Returns summary dict."""
    print("\n  [Schwab Sync] Starting full sync...")
    results = {}
    try:
        results["positions"] = sync_positions()
    except Exception as e:
        print(f"  [Schwab Sync] Positions failed: {e}")
        results["positions"] = 0

    try:
        results["trades"] = sync_trades(days=trades_days)
    except Exception as e:
        print(f"  [Schwab Sync] Trades failed: {e}")
        results["trades"] = 0

    try:
        results["snapshot"] = sync_snapshot()
    except Exception as e:
        print(f"  [Schwab Sync] Snapshot failed: {e}")
        results["snapshot"] = False

    print(f"  [Schwab Sync] Done — {results}")
    return results


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="Omnivex Schwab Sync")
    parser.add_argument("--positions-only", action="store_true")
    parser.add_argument("--trades-only", action="store_true")
    parser.add_argument("--snapshot-only", action="store_true")
    parser.add_argument("--days", type=int, default=7,
                        help="Days of order history to pull (default: 7)")
    args = parser.parse_args()

    if args.positions_only:
        sync_positions()
    elif args.trades_only:
        sync_trades(days=args.days)
    elif args.snapshot_only:
        sync_snapshot()
    else:
        run_full_sync(trades_days=args.days)
