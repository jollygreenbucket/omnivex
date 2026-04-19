"""
OMNIVEX — Mode Detection Engine
Omnivex Alpha v1.0 / Omnivex Hedge v1.0 / Omnivex Core v1.0 / Chop Guard
All thresholds sourced from knowledge base v2.3
"""

from core.config import (
    ALPHA_THRESHOLDS, HEDGE_THRESHOLDS, CHOP_GUARD, AD_SMOOTHING_DAYS
)


def detect_mode(market_ctx: dict, scored_tickers: list,
                ad_history: list = None) -> dict:
    """
    Detect current operating mode from market context + scored universe.

    market_ctx: from fetcher.get_market_context()
    scored_tickers: list of score dicts from scorer.score_ticker()
    ad_history: list of recent A/D ratios for 3-day smoothing (optional)

    Returns mode dict with full trigger breakdown.
    """

    # ── A/D Ratio (smoothed) ──
    ad_raw = market_ctx.get("ad_ratio_proxy", 1.0) or 1.0
    if ad_history and len(ad_history) >= AD_SMOOTHING_DAYS:
        recent = ad_history[-AD_SMOOTHING_DAYS:]
        ad_smoothed = sum(recent) / len(recent)
    else:
        ad_smoothed = ad_raw

    # ── ALPHA TRIGGERS ──
    turbo_triggers = {}

    turbo_triggers["vix_below_18"] = (
        market_ctx.get("vix") is not None
        and market_ctx["vix"] < ALPHA_THRESHOLDS["vix_max"]
    )

    turbo_triggers["spy_above_both_mas"] = (
        market_ctx.get("spy_above_50dma") is True
        and market_ctx.get("spy_above_200dma") is True
    )

    turbo_triggers["ad_ratio_above_1_3"] = ad_smoothed > ALPHA_THRESHOLDS["ad_ratio_min"]

    rsi_breakouts = sum(
        1 for t in scored_tickers
        if (t.get("signal_confidence_detail", {})
            .get("components", {})
            .get("rsi_strength", 0)) >= 90  # 90 maps to RSI 70-80 breakout zone
    )
    turbo_triggers["rsi_breakouts_3plus"] = rsi_breakouts >= ALPHA_THRESHOLDS["rsi_breakout_min_tickers"]

    turbo_triggers["arkk_surge_2pct"] = (
        market_ctx.get("arkk_daily_pct") is not None
        and market_ctx["arkk_daily_pct"] > ALPHA_THRESHOLDS["arkk_move_min_pct"]
    )

    # Fed Funds Futures — not available free; default False, flag as manual
    turbo_triggers["fed_pricing_cuts"] = False
    turbo_triggers["fed_data_note"] = "Manual input required — Fed Funds Futures not in free data"

    turbo_trigger_count = sum(1 for v in turbo_triggers.values() if v is True)

    # ── ANTI-FUND TRIGGERS ──
    af_triggers = {}

    af_triggers["vix_above_22"] = (
        market_ctx.get("vix") is not None
        and market_ctx["vix"] > HEDGE_THRESHOLDS["vix_min"]
    )

    af_triggers["yield_curve_inverted"] = market_ctx.get("yield_curve_inverted") is True

    af_triggers["spy_below_200dma"] = market_ctx.get("spy_above_200dma") is False

    af_triggers["ad_ratio_below_0_8"] = ad_smoothed < HEDGE_THRESHOLDS["ad_ratio_max"]

    low_score_tickers = sum(
        1 for t in scored_tickers
        if t.get("omnivex_score", 100) < HEDGE_THRESHOLDS["low_score_threshold"]
    )
    high_confidence_bearish = sum(
        1 for t in scored_tickers
        if t.get("omnivex_score", 100) < 40
        and t.get("signal_confidence", 100) > 60
    )
    af_triggers["broad_score_collapse"] = (
        low_score_tickers >= HEDGE_THRESHOLDS["low_score_ticker_count"]
        and high_confidence_bearish >= HEDGE_THRESHOLDS["bearish_high_confidence_count"]
    )

    af_trigger_count = sum(1 for v in af_triggers.values() if v is True)

    # ── CHOP GUARD ──
    atr_compressed = any(
        t.get("qtech_detail", {}).get("components", {}) for t in scored_tickers
    )
    # Check market-level ATR compression via VIX vs SPY flat
    vix_rising = market_ctx.get("vix_rising") is True
    spy_flat = abs(market_ctx.get("spy_daily_pct") or 0) < 0.3
    chop_guard_active = vix_rising and spy_flat

    # ── MODE DETERMINATION ──
    if af_trigger_count >= HEDGE_THRESHOLDS["triggers_required"]:
        mode = "HEDGE"
    elif turbo_trigger_count >= ALPHA_THRESHOLDS["triggers_required"]:
        mode = "ALPHA"
    else:
        mode = "CORE"

    # ── MODE SHIFT WARNING ──
    turbo_needed = ALPHA_THRESHOLDS["triggers_required"] - turbo_trigger_count
    af_needed = HEDGE_THRESHOLDS["triggers_required"] - af_trigger_count

    return {
        "mode": mode,
        "chop_guard_active": chop_guard_active,

        "alpha_triggers": turbo_triggers,
        "alpha_trigger_count": turbo_trigger_count,
        "alpha_triggers_needed": max(0, turbo_needed),
        "alpha_pct_active": round(
            turbo_trigger_count / ALPHA_THRESHOLDS["total_triggers"] * 100, 1
        ),

        "hedge_triggers": af_triggers,
        "hedge_trigger_count": af_trigger_count,
        "hedge_triggers_needed": max(0, af_needed),
        "hedge_pct_active": round(
            af_trigger_count / HEDGE_THRESHOLDS["total_triggers"] * 100, 1
        ),

        "ad_ratio": round(ad_smoothed, 2),
        "ad_ratio_raw": round(ad_raw, 2),
        "vix": market_ctx.get("vix"),
        "spy_daily_pct": market_ctx.get("spy_daily_pct"),
        "arkk_daily_pct": market_ctx.get("arkk_daily_pct"),
        "yield_curve_state": market_ctx.get("yield_curve_state", "UNKNOWN"),
        "spy_above_50dma": market_ctx.get("spy_above_50dma"),
        "spy_above_200dma": market_ctx.get("spy_above_200dma"),

        "mode_shift_watch": _mode_shift_watch(mode, turbo_needed, af_needed),
    }


def _mode_shift_watch(current_mode: str, turbo_needed: int, af_needed: int) -> str:
    if current_mode == "CORE":
        if turbo_needed == 1:
            return "⚠ 1 trigger from ALPHA MODE"
        if af_needed == 1:
            return "⚠ 1 trigger from ANTI-FUND MODE"
    if current_mode == "ALPHA" and af_needed <= 2:
        return "⚠ Bearish signals building"
    if current_mode == "HEDGE" and turbo_needed <= 2:
        return "⚠ Recovery signals building"
    return "Mode stable"


def get_target_allocation(mode_result: dict) -> dict:
    """Return target allocation ranges for current mode."""
    from core.config import TIER_ALLOCATION
    mode = mode_result["mode"]
    chop = mode_result.get("chop_guard_active", False)

    alloc = TIER_ALLOCATION.get(mode, TIER_ALLOCATION["CORE"]).copy()

    if chop and mode == "ALPHA":
        # Cap speculative at 10%
        alloc["speculative"] = (
            alloc["speculative"][0],
            min(alloc["speculative"][1], 0.10),
        )
        alloc["chop_guard_note"] = "Speculative capped at 10% — Chop Guard active"

    return alloc
