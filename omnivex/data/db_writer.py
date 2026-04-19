"""
OMNIVEX — Vercel Postgres Writer
Writes daily run results to Vercel Postgres.
Called from run_daily.py after scoring completes.

Requires environment variable: POSTGRES_URL
"""

import os
import json
from datetime import date

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


def write_run(mode_result: dict, scored: list, run_date: str = None) -> bool:
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

        # ── Insert run metadata ──
        buys = sum(1 for s in scored if s.get("action") in ("BUY", "ADD"))
        reduces = sum(1 for s in scored if s.get("action") in ("REDUCE", "REMOVE"))
        flagged = sum(1 for s in scored if s.get("flags"))

        cur.execute("""
            INSERT INTO runs (
                run_date, mode, chop_guard, vix, ad_ratio, spy_daily_pct,
                spy_above_50dma, spy_above_200dma, yield_curve_state,
                alpha_trigger_count, hedge_trigger_count,
                tickers_scored, tickers_flagged, tickers_buy, tickers_reduce
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                tickers_reduce = EXCLUDED.tickers_reduce
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

        conn.commit()
        cur.close()
        conn.close()

        print(f"  [DB] ✓ Written to Vercel Postgres — {len(scored)} tickers, run: {today}")
        return True

    except Exception as e:
        print(f"  [DB] Write failed: {e}")
        print("       Continuing — CSV/HTML outputs unaffected")
        return False
