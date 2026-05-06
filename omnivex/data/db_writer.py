"""
OMNIVEX — Vercel Postgres Writer
Writes daily run results to Vercel Postgres.
Called from run_daily.py after scoring completes.

Requires environment variable: POSTGRES_URL
"""

import os
import json
from datetime import date

from portfolio.allocator import build_target_portfolio
from core.strategy import STRATEGY_VERSION, build_strategy_snapshot

try:
    import psycopg2
    from psycopg2.extras import execute_values
    from psycopg2.extensions import register_adapter, AsIs
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# Register numpy type adapters so psycopg2 handles all numpy scalars natively
try:
    import numpy as np
    if HAS_PSYCOPG2:
        def _float_adapter(v):
            return AsIs("NULL") if np.isnan(v) else AsIs(float(v))

        register_adapter(np.bool_,    lambda v: AsIs(bool(v)))
        register_adapter(np.int8,     lambda v: AsIs(int(v)))
        register_adapter(np.int16,    lambda v: AsIs(int(v)))
        register_adapter(np.int32,    lambda v: AsIs(int(v)))
        register_adapter(np.int64,    lambda v: AsIs(int(v)))
        register_adapter(np.uint8,    lambda v: AsIs(int(v)))
        register_adapter(np.uint16,   lambda v: AsIs(int(v)))
        register_adapter(np.uint32,   lambda v: AsIs(int(v)))
        register_adapter(np.uint64,   lambda v: AsIs(int(v)))
        register_adapter(np.float16,  _float_adapter)
        register_adapter(np.float32,  _float_adapter)
        register_adapter(np.float64,  _float_adapter)
        # numpy 2.x renamed float128 → longdouble on some platforms
        for _t in ("float128", "longdouble"):
            _cls = getattr(np, _t, None)
            if _cls is not None:
                register_adapter(_cls, _float_adapter)
except (ImportError, Exception):
    pass


def _to_bool(val):
    """Convert numpy.bool_ (and friends) to Python bool; preserve None."""
    return bool(val) if val is not None else None


def get_connection():
    url = os.environ.get("POSTGRES_URL")
    if not url:
        raise EnvironmentError(
            "POSTGRES_URL not set. Add it to your environment or .env file."
        )
    # Vercel Postgres URLs use postgres:// — psycopg2 needs postgresql://
    url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url, sslmode="require")


def _ensure_strategy_config(cur) -> int | None:
    snapshot = build_strategy_snapshot()
    cur.execute(
        """
        INSERT INTO strategy_configs (version, config_json)
        VALUES (%s, %s::jsonb)
        ON CONFLICT (version) DO UPDATE SET
            config_json = EXCLUDED.config_json,
            updated_at = NOW()
        RETURNING id
        """,
        (STRATEGY_VERSION, json.dumps(snapshot)),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _load_portfolio_state(cur) -> tuple[list[dict], float | None, float]:
    cur.execute("""
        SELECT ticker, shares, avg_cost, current_price, market_value, tier
        FROM holdings
    """)
    holdings = [
        {
            "ticker": row[0],
            "shares": row[1],
            "avg_cost": row[2],
            "current_price": row[3],
            "market_value": row[4],
            "tier": row[5],
        }
        for row in cur.fetchall()
    ]

    cur.execute("""
        SELECT total_value, cash
        FROM portfolio_snapshots
        ORDER BY snapshot_date DESC
        LIMIT 1
    """)
    snapshot = cur.fetchone()
    total_value = snapshot[0] if snapshot else None
    cash = snapshot[1] if snapshot else 0.0
    return holdings, total_value, cash


def _write_portfolio_plan(cur, run_date: str, mode_result: dict, scored: list, portfolio_plan: dict | None = None, strategy_config_id: int | None = None):
    holdings, total_value, cash = _load_portfolio_state(cur)
    plan = portfolio_plan or build_target_portfolio(
        mode_result,
        scored,
        holdings=holdings,
        total_portfolio_value=total_value,
        cash=cash,
    )

    cur.execute("DELETE FROM rebalance_recommendations WHERE run_date = %s", (run_date,))
    cur.execute("DELETE FROM portfolio_targets WHERE run_date = %s", (run_date,))
    cur.execute("DELETE FROM portfolio_target_summary WHERE run_date = %s", (run_date,))

    cur.execute(
        """
        INSERT INTO portfolio_target_summary (
            run_date, mode, portfolio_base_value, current_cash, target_cash_pct,
            target_smart_core_pct, target_tactical_pct, target_speculative_pct,
            current_smart_core_pct, current_tactical_pct, current_speculative_pct, current_cash_pct,
            target_invested_pct, estimated_turnover_pct, max_positions, strategy_version, strategy_config_id, notes
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (run_date) DO UPDATE SET
            mode = EXCLUDED.mode,
            portfolio_base_value = EXCLUDED.portfolio_base_value,
            current_cash = EXCLUDED.current_cash,
            target_cash_pct = EXCLUDED.target_cash_pct,
            target_smart_core_pct = EXCLUDED.target_smart_core_pct,
            target_tactical_pct = EXCLUDED.target_tactical_pct,
            target_speculative_pct = EXCLUDED.target_speculative_pct,
            current_smart_core_pct = EXCLUDED.current_smart_core_pct,
            current_tactical_pct = EXCLUDED.current_tactical_pct,
            current_speculative_pct = EXCLUDED.current_speculative_pct,
            current_cash_pct = EXCLUDED.current_cash_pct,
            target_invested_pct = EXCLUDED.target_invested_pct,
            estimated_turnover_pct = EXCLUDED.estimated_turnover_pct,
            max_positions = EXCLUDED.max_positions,
            strategy_version = EXCLUDED.strategy_version,
            strategy_config_id = EXCLUDED.strategy_config_id,
            notes = EXCLUDED.notes
        """,
        (
            run_date,
            plan.get("mode"),
            plan.get("portfolio_base_value"),
            plan.get("cash"),
            plan.get("target_cash_pct"),
            plan.get("target_sleeves", {}).get("SMART_CORE"),
            plan.get("target_sleeves", {}).get("TACTICAL"),
            plan.get("target_sleeves", {}).get("SPECULATIVE"),
            plan.get("current_sleeves", {}).get("SMART_CORE"),
            plan.get("current_sleeves", {}).get("TACTICAL"),
            plan.get("current_sleeves", {}).get("SPECULATIVE"),
            plan.get("current_sleeves", {}).get("CASH"),
            plan.get("target_invested_pct"),
            plan.get("estimated_turnover_pct"),
            plan.get("max_positions"),
            STRATEGY_VERSION,
            strategy_config_id,
            " | ".join(plan.get("notes", [])),
        ),
    )

    target_rows = [
        (
            run_date,
            row["ticker"],
            row.get("sector"),
            row.get("tier"),
            row.get("sleeve"),
            row.get("rank_in_sleeve"),
            row.get("action"),
            row.get("omnivex_score"),
            row.get("signal_conf"),
            row.get("suggested_weight_pct"),
            row.get("target_weight_pct"),
            row.get("held"),
            row.get("reason"),
            row.get("flags"),
        )
        for row in plan.get("rows", [])
        if row.get("target_weight_pct", 0) > 0
    ]
    if target_rows:
        execute_values(
            cur,
            """
            INSERT INTO portfolio_targets (
                run_date, ticker, sector, tier, sleeve, rank_in_sleeve, action,
                omnivex_score, signal_conf, suggested_weight_pct, target_weight_pct,
                held, reason, flags
            ) VALUES %s
            ON CONFLICT (run_date, ticker) DO UPDATE SET
                sector = EXCLUDED.sector,
                tier = EXCLUDED.tier,
                sleeve = EXCLUDED.sleeve,
                rank_in_sleeve = EXCLUDED.rank_in_sleeve,
                action = EXCLUDED.action,
                omnivex_score = EXCLUDED.omnivex_score,
                signal_conf = EXCLUDED.signal_conf,
                suggested_weight_pct = EXCLUDED.suggested_weight_pct,
                target_weight_pct = EXCLUDED.target_weight_pct,
                held = EXCLUDED.held,
                reason = EXCLUDED.reason,
                flags = EXCLUDED.flags
            """,
            target_rows,
        )

    recommendation_rows = [
        (
            run_date,
            row["ticker"],
            row.get("sector"),
            row.get("tier"),
            row.get("action"),
            row.get("recommendation"),
            row.get("recommendation_reason"),
            row.get("omnivex_score"),
            row.get("signal_conf"),
            row.get("current_weight_pct"),
            row.get("target_weight_pct"),
            row.get("current_value"),
            row.get("target_value"),
            row.get("delta_weight_pct"),
            row.get("delta_value"),
            row.get("held"),
            row.get("sleeve"),
            row.get("flags"),
        )
        for row in plan.get("rows", [])
    ]
    if recommendation_rows:
        execute_values(
            cur,
            """
            INSERT INTO rebalance_recommendations (
                run_date, ticker, sector, tier, action, recommendation, recommendation_reason,
                omnivex_score, signal_conf, current_weight_pct, target_weight_pct,
                current_value, target_value, delta_weight_pct, delta_value, held, sleeve, flags
            ) VALUES %s
            ON CONFLICT (run_date, ticker) DO UPDATE SET
                sector = EXCLUDED.sector,
                tier = EXCLUDED.tier,
                action = EXCLUDED.action,
                recommendation = EXCLUDED.recommendation,
                recommendation_reason = EXCLUDED.recommendation_reason,
                omnivex_score = EXCLUDED.omnivex_score,
                signal_conf = EXCLUDED.signal_conf,
                current_weight_pct = EXCLUDED.current_weight_pct,
                target_weight_pct = EXCLUDED.target_weight_pct,
                current_value = EXCLUDED.current_value,
                target_value = EXCLUDED.target_value,
                delta_weight_pct = EXCLUDED.delta_weight_pct,
                delta_value = EXCLUDED.delta_value,
                held = EXCLUDED.held,
                sleeve = EXCLUDED.sleeve,
                flags = EXCLUDED.flags
            """,
            recommendation_rows,
        )


def write_run(mode_result: dict, scored: list, run_date: str = None, portfolio_plan: dict = None) -> bool:
    """
    Write full daily run to Postgres.
    Returns True on success, False on failure (never crashes the scorer).
    """
    if not HAS_PSYCOPG2:
        print("  [DB] psycopg2 not installed — skipping database write")
        print("       Run: pip install psycopg2-binary")
        return False

    today = run_date or date.today().isoformat()

    try:
        conn = get_connection()
        cur = conn.cursor()
        strategy_config_id = _ensure_strategy_config(cur)

        # ── Insert run metadata ──
        buys = sum(1 for s in scored if s.get("action") in ("BUY", "ADD"))
        reduces = sum(1 for s in scored if s.get("action") in ("REDUCE", "REMOVE"))
        flagged = sum(1 for s in scored if s.get("flags"))

        cur.execute("""
            INSERT INTO runs (
                run_date, mode, chop_guard, vix, ad_ratio, spy_daily_pct,
                spy_above_50dma, spy_above_200dma, yield_curve_state,
                alpha_trigger_count, hedge_trigger_count,
                tickers_scored, tickers_flagged, tickers_buy, tickers_reduce,
                strategy_version, strategy_config_id
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (run_date) DO UPDATE SET
                mode = EXCLUDED.mode,
                chop_guard = EXCLUDED.chop_guard,
                vix = EXCLUDED.vix,
                ad_ratio = EXCLUDED.ad_ratio,
                spy_daily_pct = EXCLUDED.spy_daily_pct,
                alpha_trigger_count = EXCLUDED.alpha_trigger_count,
                hedge_trigger_count = EXCLUDED.hedge_trigger_count,
                tickers_scored = EXCLUDED.tickers_scored,
                tickers_flagged = EXCLUDED.tickers_flagged,
                tickers_buy = EXCLUDED.tickers_buy,
                tickers_reduce = EXCLUDED.tickers_reduce,
                strategy_version = EXCLUDED.strategy_version,
                strategy_config_id = EXCLUDED.strategy_config_id
        """, (
            today,
            mode_result.get("mode", "CORE"),
            _to_bool(mode_result.get("chop_guard_active", False)),
            mode_result.get("vix"),
            mode_result.get("ad_ratio"),
            mode_result.get("spy_daily_pct"),
            _to_bool(mode_result.get("spy_above_50dma")),
            _to_bool(mode_result.get("spy_above_200dma")),
            mode_result.get("yield_curve_state", "UNKNOWN"),
            mode_result.get("alpha_trigger_count", 0),
            mode_result.get("hedge_trigger_count", 0),
            len(scored), flagged, buys, reduces,
            STRATEGY_VERSION,
            strategy_config_id,
        ))

        # ── Insert mode history ──
        cur.execute("""
            INSERT INTO mode_history (run_date, mode, vix, ad_ratio, yield_curve,
                alpha_triggers, hedge_triggers)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (run_date) DO NOTHING
        """, (
            today,
            mode_result.get("mode", "CORE"),
            mode_result.get("vix"),
            mode_result.get("ad_ratio"),
            mode_result.get("yield_curve_state", "UNKNOWN"),
            mode_result.get("alpha_trigger_count", 0),
            mode_result.get("hedge_trigger_count", 0),
        ))

        # ── Insert scores ──
        score_rows = []
        for s in scored:
            qd = s.get("qtech_detail", {}).get("components", {})
            scd = s.get("signal_confidence_detail", {}).get("components", {})
            pd = s.get("psos_detail", {})

            score_rows.append((
                today,
                s["ticker"],
                s.get("sector"),
                s.get("industry"),
                s.get("market_cap"),
                s.get("tier"),
                s.get("omnivex_score"),
                s.get("qtech"),
                s.get("psos_raw"),
                s.get("psos"),
                s.get("signal_confidence"),
                s.get("action"),
                s.get("suggested_weight_pct"),
                qd.get("roic"),
                qd.get("peg"),
                qd.get("fcf_stability"),
                qd.get("gross_margin"),
                qd.get("debt_health"),
                qd.get("revenue_growth"),
                scd.get("rsi_strength"),
                scd.get("momentum"),
                scd.get("volume_expansion"),
                scd.get("insider_activity"),
                scd.get("analyst_direction"),
                scd.get("trend_alignment"),
                bool(s.get("forensic_flags")),
                "|".join(s.get("forensic_flags", [])),
                s.get("override_applied", False),
                s.get("override_reason"),
                s.get("data_quality", "OK"),
                "|".join(s.get("flags", [])),
                s.get("earnings_proximity_days"),
            ))

        execute_values(cur, """
            INSERT INTO scores (
                run_date, ticker, sector, industry, market_cap, tier,
                omnivex_score, qtech, psos_raw, psos, signal_conf, action,
                suggested_weight_pct,
                roic_score, peg_score, fcf_score, margin_score, debt_score, rev_growth_score,
                rsi_score, momentum_score, volume_score, insider_score, analyst_score, trend_score,
                forensic_flag, forensic_detail, override_applied, override_reason,
                data_quality, flags, earnings_proximity_days
            ) VALUES %s
            ON CONFLICT (run_date, ticker) DO UPDATE SET
                omnivex_score = EXCLUDED.omnivex_score,
                qtech = EXCLUDED.qtech,
                psos = EXCLUDED.psos,
                signal_conf = EXCLUDED.signal_conf,
                action = EXCLUDED.action,
                tier = EXCLUDED.tier,
                flags = EXCLUDED.flags,
                forensic_flag = EXCLUDED.forensic_flag
        """, score_rows)

        try:
            _write_portfolio_plan(cur, today, mode_result, scored, portfolio_plan=portfolio_plan, strategy_config_id=strategy_config_id)
        except Exception as portfolio_error:
            print(f"  [DB] Portfolio plan write skipped: {portfolio_error}")

        conn.commit()
        cur.close()
        conn.close()

        print(f"  [DB] ✓ Written to Vercel Postgres — {len(scored)} tickers, run: {today}")
        return True

    except Exception as e:
        print(f"  [DB] Write failed: {e}")
        print("       Continuing — CSV/HTML outputs unaffected")
        return False
